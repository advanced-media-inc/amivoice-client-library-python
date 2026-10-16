"""大容量音声を全量コピーせず、長さが既知のmultipartとして送信する"""

import hashlib
import io
import os
import secrets
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
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


@dataclass(frozen=True, kw_only=True)
class _AsyncRecognitionOptions:
    """sentinelを解決した非同期HTTP専用設定、Noneは送信しない"""

    logging_opt_out: bool | None = None
    content_id: str | None = None
    compatible_with_sync: bool | None = None
    sentiment_analysis: bool | None = None
    speaker_diarization: bool | None = None
    diarization_min_speaker: int | None = None
    diarization_max_speaker: int | None = None


def validate_async_options(options: _AsyncRecognitionOptions) -> None:
    """非同期固有設定の型・範囲・制御文字を警告なしで検証する

    Args:
        options (_AsyncRecognitionOptions): 継承を解決済みの設定

    Raises:
        ConfigurationError: 設定の型・範囲・大小関係又は制御文字が不正な場合
    """
    for name in ("logging_opt_out", "compatible_with_sync", "speaker_diarization", "sentiment_analysis"):
        value = getattr(options, name)
        if value is not None and not isinstance(value, bool):
            raise ConfigurationError(f"{name} must be bool or None")
    if options.content_id is not None and (
        not isinstance(options.content_id, str) or any(ord(char) < 32 or ord(char) == 127 for char in options.content_id)
    ):
        raise ConfigurationError("content_id must be a string without control characters or None")
    for name in ("diarization_min_speaker", "diarization_max_speaker"):
        value = getattr(options, name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20):
            raise ConfigurationError(f"{name} must be an integer in 1..20 or None")
    if (
        options.diarization_min_speaker is not None
        and options.diarization_max_speaker is not None
        and options.diarization_min_speaker > options.diarization_max_speaker
    ):
        raise ConfigurationError("diarization_min_speaker must be <= diarization_max_speaker")


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
            try:
                stat = os.fstat(source.fileno())
            except (AttributeError, OSError, ValueError):
                # BytesIOや独自ストリームにはファイル記述子がない
                pass
            else:
                self._fingerprint = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
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
            self._restore_position(stream, start)
            return False
        self._restore_position(stream, start)
        self.size = end - start
        return True

    @staticmethod
    def _restore_position(stream: BinaryIO, start: int) -> None:
        """測定前の位置を維持し、復元不能な入力の部分送信を防ぐ

        Args:
            stream (BinaryIO): サイズ測定を試みたストリーム
            start (int): 測定前の位置

        Raises:
            ConfigurationError: 測定前の位置を復元できない場合
        """
        try:
            # seekを持たない又は拒否する入力は、位置が変わっていなければ退避できる
            if stream.tell() != start:
                stream.seek(start)
                if stream.tell() != start:
                    raise ValueError("Stream position was not restored")
        except (AttributeError, OSError, ValueError):
            raise ConfigurationError("Audio stream position could not be restored after measuring") from None

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
        options: _AsyncRecognitionOptions = _AsyncRecognitionOptions(),  # noqa: B008 -- frozenな不変設定を共有する
    ) -> None:
        """公式パラメータをURLエンコードし、小さいヘッダだけを保持する

        Args:
            audio (AudioUpload): サイズを確定した音声
            params (RecognitionParams): 共通の認識設定
            options (_AsyncRecognitionOptions): 解決済みの非同期HTTP専用設定
        """
        validate_async_options(options)
        self.audio = audio
        self.boundary = secrets.token_hex(24)
        values = _request_values(params, "async_http")
        for key, value in (
            ("loggingOptOut", options.logging_opt_out),
            ("contentId", options.content_id),
            ("compatibleWithSync", options.compatible_with_sync),
            ("sentimentAnalysis", options.sentiment_analysis),
            ("speakerDiarization", options.speaker_diarization),
            ("diarizationMinSpeaker", options.diarization_min_speaker),
            ("diarizationMaxSpeaker", options.diarization_max_speaker),
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
