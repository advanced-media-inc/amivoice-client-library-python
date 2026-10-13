"""大容量音声の読み込みとmultipart本文の境界を検証する"""

import io
from pathlib import Path

import pytest

from amivoice._async_audio import AudioUpload, MultipartUpload
from amivoice._params import RecognitionParams
from amivoice.exceptions import ConfigurationError


class NonSeekable:
    """seekを持たないストリーム"""

    def __init__(self, data: bytes) -> None:
        """音声を用意する"""
        self.stream = io.BytesIO(data)

    def read(self, size: int) -> bytes:
        """有限サイズでのみ読み込む"""
        assert size > 0
        return self.stream.read(size)


@pytest.mark.parametrize("source_kind", ["bytes", "path", "stream", "nonseek"])
def test_upload_input_valid_return_same_audio(tmp_path: Path, source_kind: str) -> None:
    """各入力形式を小さいチャンクで送信し所有権を守る"""
    # Given: 呼び出し元が所有するストリームとファイル
    data = b"\x00\xff\r\naudio" * 20
    path = tmp_path / "audio.wav"
    path.write_bytes(data)
    stream = io.BytesIO(b"skip" + data)
    stream.seek(4)
    source = {"bytes": data, "path": path, "stream": stream, "nonseek": NonSeekable(data)}[source_kind]
    # When: 入力の長さを測り分割読み込みする
    with AudioUpload(source, chunk_size=7) as audio:
        assert audio.size == len(data)
        sent = b"".join(audio.chunks())
    # Then: 元音声を保持し利用者のファイルを閉じない
    assert sent == data
    assert not stream.closed


@pytest.mark.parametrize("size", [0, 11])
def test_upload_size_invalid_raise_ConfigurationError(size: int) -> None:
    """音声上限と空入力を送信前に拒否する"""
    # Given: テスト用の小さい上限
    source = NonSeekable(b"a" * size)
    # When / Then: サイズが不正なら受付前に終了
    with pytest.raises(ConfigurationError), AudioUpload(source, max_bytes=10):
        pass


def test_upload_exact_limit_valid_return_audio() -> None:
    """上限ちょうどは許可する"""
    # Given: 上限ちょうどの音声
    source = NonSeekable(b"a" * 10)
    # When: 入力を退避する
    with AudioUpload(source, max_bytes=10, chunk_size=3) as audio:
        # Then: 全データを保持する
        assert b"".join(audio.chunks()) == b"a" * 10


def test_upload_shortened_invalid_raise_ConfigurationError() -> None:
    """送信前後で入力サイズが変わったことを検出する"""
    # Given: 測定後に短くなる利用者ストリーム
    source = io.BytesIO(b"abcdef")
    with AudioUpload(source) as audio:
        source.truncate(3)
        # When / Then: 一部だけ送って成功としない
        with pytest.raises(ConfigurationError):
            list(audio.chunks())
    assert not source.closed


def test_multipart_fields_valid_return_length_and_logging_parameter() -> None:
    """非同期のログ設定と正確なContent-Lengthを生成する"""
    # Given: 日本語と明示Falseを含む設定
    params = RecognitionParams(grammar_file_names="-a-general", codec="LSB16K", profile_words="テスト てすと")
    with AudioUpload(b"audio") as audio:
        upload = MultipartUpload(audio, params, logging_opt_out=False, content_id="日本 語", compatible_with_sync=True)
        # When: 分割本文を取り出す
        body = b"".join(upload.chunks())
        # Then: 上限は音声サイズ、長さは全multipartである
        assert len(body) == upload.content_length
        assert b"loggingOptOut=False" in body
        assert b"compatibleWithSync=True" in body
        assert b"contentId=%E6%97%A5%E6%9C%AC%20%E8%AA%9E" in body
        assert b'name="c"' in body
        assert body.endswith(b"audio\r\n--" + upload.boundary.encode() + b"--\r\n")


@pytest.mark.parametrize("properties", ["useDiarizer=0", "useDiarizer=1", "diarizerAlpha=1e-20", "diarizerTransitionBias=0"])
def test_multipart_segmenter_invalid_raise_ConfigurationError(properties: str) -> None:
    """同期方式の話者分離は無効指定でも送信しない"""
    # Given: 非同期非対応のセグメンター設定
    params = RecognitionParams(grammar_file_names="-a-general", segmenter_properties=properties)
    # When / Then: 本文生成前に拒否する
    with AudioUpload(b"audio") as audio, pytest.raises(ConfigurationError):
        MultipartUpload(audio, params)
