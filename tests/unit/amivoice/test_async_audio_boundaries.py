"""数GiBを確保せず音声サイズと清掃の境界を検証する"""

import io
import os
from pathlib import Path

import pytest

from amivoice._async_audio import MAX_AUDIO_BYTES, AudioUpload, MultipartUpload
from amivoice._params import RecognitionParams
from amivoice.exceptions import ConfigurationError

from .test_async_audio import NonSeekable


class VirtualAudio:
    """巨大なサイズだけを持ち、要求されたチャンクだけを生成する"""

    def __init__(self, size: int) -> None:
        """音声の全長と現在位置を設定する"""
        self.size = size
        self.position = 0

    def tell(self) -> int:
        """現在位置を返す"""
        return self.position

    def seek(self, position: int, whence: int = io.SEEK_SET) -> None:
        """サイズ確定時のseekを模擬する"""
        self.position = self.size + position if whence == io.SEEK_END else position

    def read(self, size: int) -> bytes:
        """有限のチャンクだけを生成する"""
        assert 0 < size <= 65536
        length = min(size, self.size - self.position)
        self.position += length
        return b"a" * length


def test_audio_maximum_size_edge_return_multipart_length() -> None:
    """約2GiBの上限をメモリ確保なしで確認する"""
    # Given: 実データを持たない上限サイズの入力
    source = VirtualAudio(MAX_AUDIO_BYTES)
    # When: 長さを確定しmultipartの長さを生成する
    with AudioUpload(source) as audio:
        upload = MultipartUpload(audio, RecognitionParams(grammar_file_names="-a-general"))
        # Then: 上限は音声だけに適用、本文の長さはヘッダも含む
        assert audio.size == MAX_AUDIO_BYTES
        assert upload.content_length > MAX_AUDIO_BYTES
        assert len(next(audio.chunks())) == 65536


def test_audio_over_maximum_edge_raise_before_read() -> None:
    """上限超過は巨大な入力を読み込む前に拒否する"""
    # Given: 上限より1バイト大きい仮想入力
    source = VirtualAudio(MAX_AUDIO_BYTES + 1)
    # When / Then: データを読まずに設定エラー
    with pytest.raises(ConfigurationError), AudioUpload(source):
        pass
    assert source.position == 0


def test_audio_spool_failure_invalid_return_closed_temporary(monkeypatch: pytest.MonkeyPatch) -> None:
    """退避途中のサイズ超過でも一時ファイルを閉じる"""
    # Given: 小さい上限と記録できる一時ファイル
    temporary = io.BytesIO()
    monkeypatch.setattr("amivoice._async_audio.tempfile.TemporaryFile", lambda **options: temporary)
    # When: seek不可の入力が上限を超える
    with pytest.raises(ConfigurationError), AudioUpload(NonSeekable(b"abcd"), max_bytes=3):
        pass
    # Then: 所有ファイルは例外時も回収
    assert temporary.closed


def test_audio_same_size_modified_invalid_raise_ConfigurationError(tmp_path: Path) -> None:
    """同じ長さのファイル変更を時刻情報で検出する"""
    # Given: 測定後に書き換える音声
    path = tmp_path / "audio.wav"
    path.write_bytes(b"before")
    with AudioUpload(path, chunk_size=2) as audio:
        chunks = audio.chunks()
        next(chunks)
        # When: 同じサイズの音声に書き換える
        path.write_bytes(b"after!")
        # ファイルシステムの時刻分解能に依存せず、観測可能な変更時刻を設定する
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        # Then: 全体を送った後も変更を通知
        with pytest.raises(ConfigurationError):
            list(chunks)
