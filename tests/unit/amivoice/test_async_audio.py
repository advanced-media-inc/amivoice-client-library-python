"""大容量音声の読み込みとmultipart本文の境界を検証する"""

import hashlib
import io
from pathlib import Path

import pytest

from amivoice._async_audio import AudioUpload, MultipartUpload, _AsyncRecognitionOptions, validate_async_options
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


class TellOnlyStream(NonSeekable):
    """位置は取得できるがseekを提供しない入力"""

    def tell(self) -> int:
        """現在の読み取り位置を返す"""
        return self.stream.tell()


class UnsupportedSeekStream(TellOnlyStream):
    """seek操作を常に拒否する入力"""

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> None:
        """位置を変えずにseek非対応を通知する"""
        raise io.UnsupportedOperation("seek is unavailable")


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


@pytest.mark.parametrize("stream_type", [TellOnlyStream, UnsupportedSeekStream])
def test_upload_tell_without_seek_valid_return_remaining_audio(stream_type: type[TellOnlyStream]) -> None:
    """tellのみ又はseekを拒否する入力を現在位置から退避する"""
    # Given: 先頭を読み取り済みの非seekable入力
    source = stream_type(b"skip-audio")
    source.read(5)
    # When: 長さ不明の入力を退避して送信する
    with AudioUpload(source, chunk_size=2) as audio:
        assert audio.size == 5
        sent = b"".join(audio.chunks())
    # Then: 現在位置からの全音声を保持し利用者のストリームを閉じない
    assert sent == b"audio"
    assert not source.stream.closed


def test_upload_failed_seek_restore_invalid_raise_ConfigurationError() -> None:
    """位置を変えた後の復元不能な入力を部分音声として送信しない"""

    # Given: 終端への移動後に失敗し、元の位置へ戻せない入力
    class MovingSeekStream(TellOnlyStream):
        """失敗時にも位置を変更する独自ストリーム"""

        def seek(self, offset: int, whence: int = io.SEEK_SET) -> None:
            """終端へ移動した後に例外を送出する"""
            if whence == io.SEEK_END:
                self.stream.seek(0, io.SEEK_END)
            raise io.UnsupportedOperation("cannot restore")

    source = MovingSeekStream(b"audio")
    # When / Then: 元の音声を失った状態で退避せず、安全な設定例外を送出する
    with pytest.raises(ConfigurationError, match="could not be restored"), AudioUpload(source):
        pass
    assert not source.stream.closed


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
        upload = MultipartUpload(
            audio,
            params,
            options=_AsyncRecognitionOptions(logging_opt_out=False, content_id="日本 語", compatible_with_sync=True),
        )
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
    with AudioUpload(b"audio") as audio, pytest.raises(ConfigurationError) as caught:
        MultipartUpload(audio, params)
    assert "RecognitionSettings(speaker_diarization=True)" in str(caught.value)
    assert "synchronous HTTP / WebSocket" in str(caught.value)


@pytest.mark.parametrize("enabled", [True, False, None])
def test_multipart_diarization_valid_return_exact_domain_and_md5(enabled: bool | None, caplog: pytest.LogCaptureFixture) -> None:
    """新設定を正確に直列化しURLエンコード・長さ・末尾音声・MD5を維持する"""
    # Given: 日本語のユーザーIDと人数の境界値
    options = _AsyncRecognitionOptions(
        content_id="日本 語", speaker_diarization=enabled, diarization_min_speaker=1, diarization_max_speaker=20
    )
    params = RecognitionParams(grammar_file_names="-a-general")
    with AudioUpload(b"audio", chunk_size=2) as audio:
        validate_async_options(options)
        upload = MultipartUpload(audio, params, options=options)
        # When: 音声をチャンク送信する
        body = b"".join(upload.chunks())
        # Then: dの文字列全体とMD5が期待通りで警告は発行しない
        domain = b"grammarFileNames=-a-general contentId=%E6%97%A5%E6%9C%AC%20%E8%AA%9E"
        if enabled is not None:
            domain += f" speakerDiarization={enabled}".encode()
        domain += b" diarizationMinSpeaker=1 diarizationMaxSpeaker=20"
        assert body.split(b"\r\n\r\n", 1)[1].split(b"\r\n", 1)[0] == domain
        assert len(body) == upload.content_length
        assert body.endswith(b"audio\r\n--" + upload.boundary.encode() + b"--\r\n")
        assert audio.audio_md5 == hashlib.md5(b"audio", usedforsecurity=False).hexdigest()
        assert not caplog.records


def test_multipart_unset_options_valid_return_omitted_domain() -> None:
    """Noneの専用設定は一切送信しない"""
    # Given: 非同期固有設定を指定しない
    with AudioUpload(b"audio") as audio:
        # When: 既定optionsで本文を生成する
        upload = MultipartUpload(audio, RecognitionParams(grammar_file_names="-a-general"))
        # Then: dにはエンジンだけを含める
        assert b"".join(upload.chunks()).split(b"\r\n\r\n", 1)[1].split(b"\r\n", 1)[0] == b"grammarFileNames=-a-general"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("speaker_diarization", 1),
        ("diarization_min_speaker", True),
        ("diarization_max_speaker", 21),
        ("logging_opt_out", 1),
        ("compatible_with_sync", "True"),
        ("content_id", "bad\n"),
    ],
)
def test_multipart_invalid_options_invalid_raise_defensively(field: str, value: object) -> None:
    """内部直接呼び出しでも設定検証を省略しない"""
    # Given: 不正な解決済み設定
    options = _AsyncRecognitionOptions(**{field: value})
    # When / Then: 純粋関数とmultipartの双方でフィールド名付きエラー
    with pytest.raises(ConfigurationError, match=field):
        validate_async_options(options)
    with AudioUpload(b"audio") as audio, pytest.raises(ConfigurationError, match=field):
        MultipartUpload(audio, RecognitionParams(grammar_file_names="-a-general"), options=options)
