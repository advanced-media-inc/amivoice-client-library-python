"""大容量音声を全量コピーせず、長さが既知のmultipartとして送信する"""

import hashlib
import io
import os
import secrets
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import BinaryIO

from ._params import RecognitionParams
from ._request_parameters import _encode_http_value, _request_values
from ._types import AudioSource
from .constants import Codec
from .exceptions import ConfigurationError

MAX_AUDIO_BYTES = 2_147_483_647
_CHUNK_SIZE = 65536


def _binary_read(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if not isinstance(data, (bytes, bytearray)) or len(data) > size:
        raise ConfigurationError("Audio stream must return no more than the requested number of binary bytes")
    return bytes(data)


def validate_async_options(logging_opt_out: bool | None, content_id: str | None, compatible_with_sync: bool | None) -> None:
    """非同期固有設定の型と制御文字を検証する

    Args:
        logging_opt_out (bool | None): ログ保存なし、Noneは送信しない
        content_id (str | None): アプリケーションのID
        compatible_with_sync (bool | None): 同期互換形式、Noneは送信しない

    Raises:
        ConfigurationError: 設定の型又は制御文字が不正な場合
    """
    for value in (logging_opt_out, compatible_with_sync):
        if value is not None and not isinstance(value, bool):
            raise ConfigurationError("Async HTTP boolean options must be bool or None")
    if content_id is not None and (
        not isinstance(content_id, str) or any(ord(char) < 32 or ord(char) == 127 for char in content_id)
    ):
        raise ConfigurationError("content_id must be a string without control characters")


class AudioUpload:
    """音声ソースの寿命を管理し、seek不可入力はサイズ上限付きで一時退避する"""

    def __init__(self, source: AudioSource, *, max_bytes: int = MAX_AUDIO_BYTES, chunk_size: int = _CHUNK_SIZE) -> None:
        """利用者のストリームを所有せずに保持する

        Args:
            source (AudioSource): bytes、ファイルパス、バイナリストリーム
            max_bytes (int): 音声サイズの上限、テストで小さい値にできる
            chunk_size (int): 各読み込みの最大バイト数
        """
        self._source = source
        self._maximum = max_bytes
        self._chunk_size = chunk_size
        self._stream: BinaryIO | None = None
        self._resources = ExitStack()
        self._fingerprint: tuple[int, int, int] | None = None
        self.size = 0
        self.audio_md5: str | None = None

    def __enter__(self) -> "AudioUpload":
        """サイズを確定し、所有するリソースを例外時にも閉じる

        Returns:
            AudioUpload: 送信できる入力

        Raises:
            ConfigurationError: 入力形式又は音声サイズが不正な場合
        """
        try:
            self._prepare()
            if not 1 <= self.size <= self._maximum:
                raise ConfigurationError(f"Audio data must contain between 1 and {self._maximum} bytes")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _prepare(self) -> None:
        source = self._source
        if isinstance(source, bytes):
            self._stream = self._resources.enter_context(io.BytesIO(source))
        elif isinstance(source, (str, Path)):
            self._stream = self._resources.enter_context(Path(source).open("rb"))  # noqa: SIM115 -- ExitStackが寿命を管理
            stat = os.fstat(self._stream.fileno())
            self._fingerprint = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        elif callable(getattr(source, "read", None)):
            self._stream = source
        else:
            raise ConfigurationError("Audio source must be bytes, a file path or a binary stream")
        stream = self._stream
        if self._measure(stream):
            return
        self._spool(stream)

    def _measure(self, stream: BinaryIO) -> bool:
        try:
            if callable(getattr(stream, "seekable", None)) and not stream.seekable():
                return False
            start = stream.tell()
        except (AttributeError, OSError, ValueError):
            return False
        try:
            stream.seek(0, io.SEEK_END)
            end = stream.tell()
        except (AttributeError, OSError, ValueError):
            # seekに失敗しても呼び出し元の位置を失わない
            stream.seek(start)
            return False
        stream.seek(start)
        self.size = end - start
        return True

    def _spool(self, stream: BinaryIO) -> None:
        temporary = self._resources.enter_context(tempfile.TemporaryFile(mode="w+b"))  # noqa: SIM115 -- ExitStackが寿命を管理
        self._stream = temporary
        self._fingerprint = None
        while True:
            data = _binary_read(stream, min(self._chunk_size, self._maximum - self.size + 1))
            if not data:
                break
            self.size += len(data)
            if self.size > self._maximum:
                raise ConfigurationError("Audio stream exceeds the async HTTP size limit")
            temporary.write(data)
        temporary.seek(0)

    def chunks(self) -> Iterator[bytes]:
        """測定した音声サイズを超えずに入力を送る

        Yields:
            bytes: 音声チャンク

        Raises:
            ConfigurationError: 測定後に音声が増減又は変更された場合
        """
        if self._stream is None:
            raise ConfigurationError("Audio upload must be opened before reading")
        remaining = self.size
        self.audio_md5 = None
        digest = hashlib.md5(usedforsecurity=False)
        while remaining:
            data = _binary_read(self._stream, min(self._chunk_size, remaining))
            if not data:
                raise ConfigurationError("Audio source became shorter during upload; submission may have been accepted")
            remaining -= len(data)
            digest.update(data)
            yield data
        if _binary_read(self._stream, 1):
            raise ConfigurationError("Audio source grew during upload; submission may have been accepted")
        if self._fingerprint is not None:
            stat = os.fstat(self._stream.fileno())
            if self._fingerprint != (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns):
                raise ConfigurationError("Audio file changed during upload; submission may have been accepted")
        self.audio_md5 = digest.hexdigest()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """ライブラリが所有するファイルだけを閉じる

        Args:
            exc_type (object): 例外の型
            exc_value (object): 例外
            traceback (object): トレースバック
        """
        self._resources.close()
        self._stream = None


class MultipartUpload:
    """音声を末尾に置いた長さ既知のmultipart本文"""

    def __init__(
        self,
        audio: AudioUpload,
        params: RecognitionParams,
        *,
        logging_opt_out: bool | None = None,
        content_id: str | None = None,
        compatible_with_sync: bool | None = None,
    ) -> None:
        """公式パラメータをURLエンコードし、小さいヘッダだけを保持する

        Args:
            audio (AudioUpload): サイズを確定した音声
            params (RecognitionParams): 共通の認識設定
            logging_opt_out (bool | None): 非同期のログ保存設定
            content_id (str | None): ユーザー定義ID
            compatible_with_sync (bool | None): 同期互換形式
        """
        validate_async_options(logging_opt_out, content_id, compatible_with_sync)
        self.audio = audio
        self.boundary = secrets.token_hex(24)
        values = _request_values(params, "async_http")
        for key, value in (
            ("loggingOptOut", logging_opt_out),
            ("contentId", content_id),
            ("compatibleWithSync", compatible_with_sync),
        ):
            if value is not None:
                values.append((key, str(value)))
        domain = " ".join(f"{key}={_encode_http_value(key, value)}" for key, value in values)
        parts = [("d", domain)]
        if params.codec is not None and Codec(params.codec) not in (Codec.HEADER_8K, Codec.HEADER_16K):
            parts.append(("c", Codec(params.codec).value))
        prefix = [
            f'--{self.boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8")
            for key, value in parts
        ]
        prefix.append(
            (
                f'--{self.boundary}\r\nContent-Disposition: form-data; name="a"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
        )
        self._prefix = b"".join(prefix)
        self._suffix = f"\r\n--{self.boundary}--\r\n".encode()
        self.content_length = len(self._prefix) + audio.size + len(self._suffix)
        self.content_type = f"multipart/form-data; boundary={self.boundary}"

    def chunks(self) -> Iterator[bytes]:
        """本文全体をコピーせず、順番に送信する

        Yields:
            bytes: ヘッダ、音声チャンク、終端
        """
        yield self._prefix
        yield from self.audio.chunks()
        yield self._suffix
