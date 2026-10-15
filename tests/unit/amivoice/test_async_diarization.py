"""非同期HTTP専用話者設定の検証・マージ・通信前の警告を検証する"""

import logging
from dataclasses import FrozenInstanceError

import pytest

from amivoice import (
    USE_CLIENT_DEFAULT,
    AmiVoiceAsyncClient,
    AmiVoiceClient,
    ConfigurationError,
    RecognitionSettings,
    SegmenterProperties,
)
from amivoice._recognition_settings import merge_recognition_settings

from .test_async_client import RecordingTransport, completed, queued

FIELDS = ("speaker_diarization", "diarization_min_speaker", "diarization_max_speaker")


@pytest.mark.parametrize("enabled", [True, False, None])
def test_settings_diarization_override_valid_return_immutable_values(enabled: bool | None) -> None:
    """sentinel・上書き・解除と人数継承を維持する"""
    # Given: 不変なクライアント既定値
    base = RecognitionSettings(speaker_diarization=True, diarization_min_speaker=2, diarization_max_speaker=6)
    assert all(getattr(RecognitionSettings(), name) is USE_CLIENT_DEFAULT for name in FIELDS)
    # When: 一部だけを明示し残りは継承する
    resolved = merge_recognition_settings(base, RecognitionSettings(speaker_diarization=enabled, diarization_min_speaker=3))
    cleared = merge_recognition_settings(base, RecognitionSettings(**dict.fromkeys(FIELDS)))
    # Then: 自動有効化せず元のインスタンスも変更しない
    assert resolved.speaker_diarization is enabled
    assert resolved.diarization_min_speaker == 3 and resolved.diarization_max_speaker == 6
    assert all(getattr(cleared, name) is None for name in FIELDS)
    assert base.speaker_diarization is True and base.diarization_min_speaker == 2
    with pytest.raises(FrozenInstanceError):
        resolved.speaker_diarization = True


@pytest.mark.parametrize("operation", ["init", "submit"])
@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [("speaker_diarization", value, "bool or None") for value in (1, 0, "True")]
    + [(name, value, "1..20") for name in FIELDS[1:] for value in (0, 21, -1, True, False, 1.5, "5")],
)
def test_client_diarization_invalid_raise_before_audio(
    operation: str, field: str, value: object, expected: str, caplog: pytest.LogCaptureFixture
) -> None:
    """エンジン未指定の初期化でも型・範囲を検証し音声を開かない"""
    # Given: 不正設定と通信禁止のクライアント
    transport = RecordingTransport([])
    settings = RecognitionSettings(**{field: value})
    # When / Then: 音声ファイルを開く前に原因と許容値を案内する
    with pytest.raises(ConfigurationError) as caught:
        if operation == "init":
            AmiVoiceAsyncClient(api_key="dummy", settings=settings, transport=transport)
        else:
            client = AmiVoiceAsyncClient(
                api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general"), transport=transport
            )
            client.submit("does-not-exist.wav", settings=settings)
    assert field in str(caught.value) and expected in str(caught.value)
    assert not transport.calls and not caplog.records


@pytest.mark.parametrize("counts", [(1, 1), (5, 5), (1, 20), (20, 20), (15, None), (None, 1), (None, None)])
def test_submit_diarization_bounds_valid_return_wire(counts: tuple[int | None, int | None]) -> None:
    """既知人数と片側指定を許可しサーバー既定値を補完しない"""
    # Given: 有効な人数範囲
    transport = RecordingTransport([{"sessionid": "job1", "text": "..."}])
    client = AmiVoiceAsyncClient(
        api_key="dummy",
        settings=RecognitionSettings(
            grammar_file_names="-a-general",
            speaker_diarization=True,
            diarization_min_speaker=counts[0],
            diarization_max_speaker=counts[1],
        ),
        transport=transport,
    )
    # When: ジョブを登録する
    client.submit(b"audio")
    # Then: 指定した項目だけが送信される
    body = transport.calls[0][3]
    assert b"speakerDiarization=True" in body
    for key, value in zip(("diarizationMinSpeaker", "diarizationMaxSpeaker"), counts, strict=True):
        assert (f"{key}={value}".encode() in body) if value is not None else (key.encode() not in body)


@pytest.mark.parametrize("operation", ["init", "submit", "inherited"])
def test_client_diarization_reversed_invalid_raise_condition(operation: str) -> None:
    """有効時の両側指定はマージ後に大小比較する"""
    # Given: 最小値が最大値より大きい設定
    transport = RecordingTransport([])
    settings = RecognitionSettings(
        grammar_file_names="-a-general", speaker_diarization=True, diarization_min_speaker=15, diarization_max_speaker=10
    )
    # When / Then: 直接指定と片側継承のいずれも通信前に拒否する
    with pytest.raises(ConfigurationError, match=r"diarization_min_speaker.*<=.*diarization_max_speaker"):
        if operation == "init":
            AmiVoiceAsyncClient(api_key="dummy", settings=settings, transport=transport)
        else:
            base = RecognitionSettings(grammar_file_names="-a-general", speaker_diarization=True, diarization_max_speaker=10)
            client = AmiVoiceAsyncClient(api_key="dummy", settings=base, transport=transport)
            override = RecognitionSettings(diarization_min_speaker=15) if operation == "inherited" else settings
            client.submit(b"audio", settings=override)
    assert not transport.calls


def test_submit_diarization_clear_one_side_valid_return_no_default_comparison() -> None:
    """継承した最大値をNoneで解除すると比較しない"""
    # Given: 最大値のクライアント既定値
    transport = RecordingTransport([{"sessionid": "job1", "text": "..."}])
    client = AmiVoiceAsyncClient(
        api_key="dummy",
        settings=RecognitionSettings(grammar_file_names="-a-general", speaker_diarization=True, diarization_max_speaker=10),
        transport=transport,
    )
    # When: 最大値を送信解除する
    client.submit(b"audio", settings=RecognitionSettings(diarization_min_speaker=15, diarization_max_speaker=None))
    # Then: サーバー既定の10をSDKで補完しない
    assert b"diarizationMinSpeaker=15" in transport.calls[0][3]
    assert b"diarizationMaxSpeaker" not in transport.calls[0][3]


@pytest.mark.parametrize("enabled", [False, None, USE_CLIENT_DEFAULT])
@pytest.mark.parametrize("counts", [(15, None), (None, 1), (15, 1)])
@pytest.mark.parametrize("inherited", [False, True])
def test_submit_diarization_disabled_valid_return_one_warning(
    enabled: object, counts: tuple[int | None, int | None], inherited: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """人数設定だけでは有効化せず警告を一度だけ出して送信する"""
    # Given: 型と範囲は有効だが話者設定は無効、逆転も許可する
    caplog.set_level(logging.WARNING)
    transport = RecordingTransport([{"sessionid": "job1", "text": "..."}, queued(), completed()])
    values = dict(zip(FIELDS, (enabled, *counts), strict=True))
    base = (
        RecognitionSettings(grammar_file_names="-a-general", **values)
        if inherited
        else RecognitionSettings(grammar_file_names="-a-general")
    )
    client = AmiVoiceAsyncClient(api_key="secret-key", settings=base, transport=transport)
    assert not caplog.records
    # When: 検証後にsubmitだけが警告する
    client.submit(b"secret-audio", settings=USE_CLIENT_DEFAULT if inherited else RecognitionSettings(**values))
    client.get_job("job1")
    client.wait("job1")
    # Then: 情報を漏らさず原因と対処を案内し送信は継続する
    records = [record for record in caplog.records if record.name == "amivoice.async_client"]
    assert len(records) == 1 and records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    assert "diarization_min_speaker" in message and "diarization_max_speaker" in message
    assert "speaker_diarization=True" in message and "ignored" in message
    assert "secret-key" not in message and "secret-audio" not in message
    body = transport.calls[0][3]
    assert (b"speakerDiarization=False" in body) if enabled is False else (b"speakerDiarization=" not in body)
    for key, value in zip(("diarizationMinSpeaker", "diarizationMaxSpeaker"), counts, strict=True):
        if value is not None:
            assert f"{key}={value}".encode() in body


@pytest.mark.parametrize("enabled", [None, False])
@pytest.mark.parametrize("clear_counts", [False, True])
def test_submit_diarization_disable_defaults_valid_return_no_reenable(
    enabled: bool | None, clear_counts: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """有効な既定値から無効化すると人数は継承し、明示解除で警告も止まる"""
    # Given: 既定値は有効で人数を指定
    transport = RecordingTransport([{"sessionid": "job1", "text": "..."}])
    client = AmiVoiceAsyncClient(
        api_key="dummy",
        settings=RecognitionSettings(
            grammar_file_names="-a-general", speaker_diarization=True, diarization_min_speaker=2, diarization_max_speaker=6
        ),
        transport=transport,
    )
    override = {"speaker_diarization": enabled}
    if clear_counts:
        override.update(dict.fromkeys(FIELDS[1:]))
    # When: 無効化し必要なら人数も解除する
    client.submit(b"audio", settings=RecognitionSettings(**override))
    # Then: 自動有効化しない、完全解除なら人数も警告もない
    body = transport.calls[0][3]
    assert b"speakerDiarization=True" not in body
    assert (b"diarizationMinSpeaker=2" in body) is not clear_counts
    assert len(caplog.records) == (0 if clear_counts else 1)


@pytest.mark.parametrize("operation", ["init", "transcribe", "stream"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("speaker_diarization", True),
        ("speaker_diarization", False),
        ("diarization_min_speaker", 1),
        ("diarization_max_speaker", 20),
    ],
)
def test_sync_diarization_option_invalid_raise_async_guidance(operation: str, field: str, value: object) -> None:
    """同期クライアントの全入口で非同期専用設定を拒否する"""
    # Given: 同期で指定できない新しい設定
    settings = RecognitionSettings(**{field: value})
    # When / Then: Falseも無視せず代替APIを案内する
    with pytest.raises(ConfigurationError) as caught:
        if operation == "init":
            AmiVoiceClient(api_key="dummy", settings=settings)
        else:
            client = AmiVoiceClient(api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general"))
            if operation == "transcribe":
                client.transcribe("does-not-exist.wav", settings=settings)
            else:
                client.stream(settings=settings)
    message = str(caught.value)
    assert field in message and "AmiVoiceAsyncClient" in message
    assert "segmenter=SegmenterProperties(speaker_diarization=True)" in message


@pytest.mark.parametrize("value", [None, USE_CLIENT_DEFAULT])
def test_sync_diarization_unset_valid_return_segmenter(value: object) -> None:
    """未指定と解除を許可し同期の既存話者設定も維持する"""
    # Given: 非同期項目は解除または未指定
    settings = RecognitionSettings(
        grammar_file_names="-a-general", segmenter=SegmenterProperties(speaker_diarization=True), **dict.fromkeys(FIELDS, value)
    )
    client = AmiVoiceClient(api_key="dummy", settings=settings)
    # When: WebSocketセッションを作る（接続はしない）
    manager = client.stream(settings=RecognitionSettings(**dict.fromkeys(FIELDS, value)))
    # Then: 拒否されない
    assert manager is not None
