"""送信音声のMD5とサーバー応答の照合を検証する"""

import hashlib
import io
from pathlib import Path

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncJobSnapshot, AsyncJobSubmission, ConfigurationError
from amivoice._async_audio import AudioUpload

from .async_mock_server import AsyncMockServer
from .recognition_mock_servers import parse_recognition_multipart
from .test_async_client import RecordingTransport

_AUDIO = b"prefix-payload"
_DIGEST = hashlib.md5(_AUDIO, usedforsecurity=False).hexdigest()


class NonSeekable:
    """読み取ったバイト数を記録するseek不可ストリーム"""

    def __init__(self, data: bytes) -> None:
        """計数用の入力を用意する"""
        self.stream = io.BytesIO(data)
        self.read_bytes = 0

    def read(self, size: int) -> bytes:
        """返したバイト数を計数する"""
        data = self.stream.read(size)
        self.read_bytes += len(data)
        return data


@pytest.mark.parametrize("kind", ["bytes", "path", "stream", "nonseekable"])
def test_submit_audio_valid_return_local_integrity(kind: str, tmp_path: Path) -> None:
    """すべての入力形式で音声だけのダイジェストを保持する"""
    # Given: 同一音声と受付成功
    stream = io.BytesIO(_AUDIO)
    nonseekable = NonSeekable(_AUDIO)
    path = tmp_path / "audio.wav"
    path.write_bytes(_AUDIO)
    inputs = {"bytes": _AUDIO, "path": path, "stream": stream, "nonseekable": nonseekable}
    transport = RecordingTransport([{"sessionid": "job1", "text": "..."}])
    client = AmiVoiceAsyncClient(api_key="dummy", grammar_file_names="-a-general", transport=transport)
    # When: 音声を登録する
    submission = client.submit(inputs[kind])
    # Then: multipartではなく送信音声のMD5とサイズを保持する
    assert submission.audio_size == len(_AUDIO) and submission.audio_md5 == _DIGEST
    assert "audio_md5" not in submission.data
    assert not stream.closed and not nonseekable.stream.closed
    if kind == "nonseekable":
        assert nonseekable.read_bytes == len(_AUDIO)


def test_submit_stream_position_valid_return_remaining_integrity() -> None:
    """ストリームの現在位置から送信した部分だけを計算する"""
    # Given: 途中位置にあるストリーム
    stream = io.BytesIO(_AUDIO)
    stream.seek(len(b"prefix-"))
    client = AmiVoiceAsyncClient(
        api_key="dummy", grammar_file_names="-a-general", transport=RecordingTransport([{"sessionid": "job1"}])
    )
    # When: 残り部分を送信する
    submission = client.submit(stream)
    # Then: 元の全体とは異なるダイジェスト
    assert submission.audio_size == len(b"payload")
    assert submission.audio_md5 == hashlib.md5(b"payload", usedforsecurity=False).hexdigest()
    assert not stream.closed


def test_audio_upload_partial_edge_return_no_completed_digest() -> None:
    """送信途中では完成したダイジェストとして公開しない"""
    # Given: 複数チャンクに分かれる入力
    with AudioUpload(_AUDIO, chunk_size=2) as upload:
        # When: 最初のチャンクだけ読み取る
        iterator = upload.chunks()
        next(iterator)
        # Then: 未完了のMD5はNone
        assert upload.audio_md5 is None
        iterator.close()


@pytest.mark.parametrize(
    ("size", "digest", "expected"),
    [
        (len(_AUDIO), _DIGEST, True),
        (len(_AUDIO), _DIGEST.upper(), True),
        (1, _DIGEST, False),
        (len(_AUDIO), "0" * 32, False),
        (None, None, None),
        (len(_AUDIO), None, None),
        (None, _DIGEST, None),
        (1, None, False),
        (None, "0" * 32, False),
    ],
)
def test_submission_matches_audio_valid_return_tristate(size: int | None, digest: str | None, expected: bool | None) -> None:
    """不足情報は未確定とし比較可能な不一致は検出する"""
    # Given: ローカル音声情報とサーバーの観測値
    submission = AsyncJobSubmission("job1", "{}", {}, audio_size=len(_AUDIO), audio_md5=_DIGEST)
    snapshot = AsyncJobSnapshot("job1", "processing", "{}", {}, audio_size=size, audio_md5=digest)
    # When: 音声を照合する
    matches = submission.matches_audio(snapshot)
    # Then: 両方一致の場合だけTrue
    assert matches is expected


def test_submit_local_http_valid_return_matching_audio() -> None:
    """実際の分割送信と状態取得を通して音声を照合する"""
    # Given: 複数チャンクの音声と同じサイズ・MD5を返すローカルAPI
    audio = _AUDIO * 10000
    digest = hashlib.md5(audio, usedforsecurity=False).hexdigest()
    responses = [
        (200, {"sessionid": "job1"}),
        (200, {"session_id": "job1", "status": "processing", "audio_size": len(audio), "audio_md5": digest}),
    ]
    with AsyncMockServer(responses) as server:
        client = AmiVoiceAsyncClient(api_key="dummy", grammar_file_names="-a-general", api_url=server.url)
        # When: 登録した音声をサーバー観測値と照合する
        submission = client.submit(audio)
        snapshot = client.get_job(submission.session_id)
        # Then: 実送信の音声パートと一致する
        assert submission.matches_audio(snapshot) is True
        _, _, headers, body = server.received[0]
        assert parse_recognition_multipart(headers["Content-Type"], body)[-1][1] == audio


def test_submission_matches_audio_wrong_id_invalid_raise_ConfigurationError() -> None:
    """別ジョブの音声を同一と判定しない"""
    # Given: 同じ音声でも別のジョブ
    submission = AsyncJobSubmission("job1", "{}", {}, audio_size=len(_AUDIO), audio_md5=_DIGEST)
    snapshot = AsyncJobSnapshot("job2", "processing", "{}", {}, audio_size=len(_AUDIO), audio_md5=_DIGEST)
    # When / Then: 誤った照合対象を拒否
    with pytest.raises(ConfigurationError):
        submission.matches_audio(snapshot)


def test_submission_legacy_constructor_valid_return_unknown_integrity() -> None:
    """既存の3引数コンストラクタを維持する"""
    # Given: ローカル情報を持たない従来の受付モデル
    submission = AsyncJobSubmission("job1", "{}", {})
    snapshot = AsyncJobSnapshot("job1", "processing", "{}", {}, audio_size=len(_AUDIO), audio_md5=_DIGEST)
    # When: 音声を照合する
    matches = submission.matches_audio(snapshot)
    # Then: 値を捏造しない
    assert matches is None
    assert submission.audio_size is None and submission.audio_md5 is None
