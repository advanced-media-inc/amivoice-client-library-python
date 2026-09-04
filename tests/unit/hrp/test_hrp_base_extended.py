# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false, reportAny=false, reportUnknownArgumentType=false
from collections.abc import Callable
from typing import NoReturn
from unittest.mock import MagicMock

import pytest

from com.amivoice.hrp.Hrp import Hrp


class MockHrp(Hrp):  # noqa: D101
    def __init__(self, connected: bool = False) -> None:  # noqa: D107
        super().__init__()
        self._connected = connected

    def isConnected_(self) -> bool:  # noqa: D102
        return self._connected

    def connect_(self, *args: object) -> None:  # noqa: D102
        pass

    def disconnect_(self) -> None:  # noqa: D102
        pass

    def sendRequestHeader_(self, *args: object) -> None:  # noqa: D102
        pass

    def sendRequestBody_(self, *args: object) -> None:  # noqa: D102
        pass


def _capture_header(captured: dict[str, str], hrp: MockHrp) -> Callable[[str, object], None]:
    def capture_header(domain_id: str, *args: object) -> None:
        del args
        captured["domainId"] = domain_id
        hrp.state_ = 2

    return capture_header


def _always_raises(message: str) -> Callable[..., NoReturn]:
    def send_raises(*args: object) -> NoReturn:
        del args
        raise OSError(message)

    return send_raises


def _send_body_error(hrp: MockHrp) -> Callable[[bytes | None, int, int], None]:
    def send_body_sets_error(data: bytes | None, data_offset: int, data_bytes: int) -> None:
        del data, data_offset, data_bytes
        with hrp.condition_:
            hrp.state_ = 5
            hrp.condition_.notify_all()

    return send_body_sets_error


def _send_body_close(hrp: MockHrp) -> Callable[[bytes | None, int, int], None]:
    def send_body_closes(data: bytes | None, data_offset: int, data_bytes: int) -> None:
        del data, data_offset, data_bytes
        with hrp.condition_:
            hrp.state_ = 0
            hrp.condition_.notify_all()

    return send_body_closes


def _send_body_capture(captured: dict[str, object], hrp: MockHrp) -> Callable[[bytes, int, int], None]:
    def send_body(data: bytes, data_offset: int, data_bytes: int) -> None:
        captured["data"] = data
        captured["offset"] = data_offset
        captured["bytes"] = data_bytes
        captured["state"] = hrp.state_

    return send_body


def _send_body_mark_called(captured: dict[str, bool]) -> Callable[[bytes, int, int], None]:
    def send_body(data: bytes, data_offset: int, data_bytes: int) -> None:
        del data, data_offset, data_bytes
        captured["called"] = True

    return send_body


def test_connect_exception_sets_error_state_and_returns_false() -> None:  # noqa: D103
    hrp = MockHrp()
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.setServerURL("http://example.com/asr")

    def connect_raises(*args: object) -> NoReturn:
        del args
        raise OSError("connection refused")

    hrp.connect_ = connect_raises

    result = hrp.connect()

    assert result is False
    assert hrp.state_ == -1
    assert "can't connect to HTTP server" in hrp.getLastMessage()
    assert "connection refused" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()
    assert "can't connect to HTTP server" in listener.TRACE.call_args[0][0]


def test_connect_exception_without_listener_does_not_raise() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setServerURL("http://example.com/asr")

    def connect_raises(*args: object) -> NoReturn:
        del args
        raise RuntimeError("timeout")

    hrp.connect_ = connect_raises

    result = hrp.connect()

    assert result is False
    assert hrp.state_ == -1


def test_connect_already_connected_returns_false_with_warning() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)

    result = hrp.connect()

    assert result is False
    assert "already connected" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_connect_missing_server_url_returns_false() -> None:  # noqa: D103
    hrp = MockHrp()
    listener = MagicMock()
    hrp.setListener(listener)

    result = hrp.connect()

    assert result is False
    assert "Missing server URL" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_disconnect_when_connected_returns_true_and_traces() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)

    result = hrp.disconnect()

    assert result is True
    assert hrp.state_ == -1
    assert "disconnected from HTTP server" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()
    assert "disconnected from HTTP server" in listener.TRACE.call_args[0][0]


def test_disconnect_when_connected_without_listener_does_not_raise() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)

    result = hrp.disconnect()

    assert result is True
    assert hrp.state_ == -1


def test_disconnect_when_not_connected_returns_false_with_warning() -> None:  # noqa: D103
    hrp = MockHrp(connected=False)
    listener = MagicMock()
    hrp.setListener(listener)

    result = hrp.disconnect()

    assert result is False
    assert "already disconnected" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_resume_when_not_connected_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=False)
    listener = MagicMock()
    hrp.setListener(listener)

    result = hrp.feedDataResume()

    assert result is False
    assert "disconnected" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_resume_when_already_started_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 2

    result = hrp.feedDataResume()

    assert result is False
    assert "already started" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_resume_ioerror_returns_false_with_error_message() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 0

    hrp.sendRequestHeader_ = _always_raises("network error")

    result = hrp.feedDataResume()

    assert result is False
    assert "can't start feeding data to HTTP server" in hrp.getLastMessage()
    assert "network error" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_resume_oserror_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0

    hrp.sendRequestHeader_ = _always_raises("broken pipe")

    result = hrp.feedDataResume()

    assert result is False
    assert "can't start feeding data to HTTP server" in hrp.getLastMessage()


def test_feed_data_resume_success_with_domain_id_traces() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 0
    hrp.setDomainId("test-domain")

    result = hrp.feedDataResume()

    assert result is True
    assert hrp.state_ == 2
    assert "started feeding data to HTTP server" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_resume_builds_domain_id_from_grammar_file_names() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setGrammarFileNames("file1.grm")

    hrp.feedDataResume()

    assert "grammarFileNames=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_mode() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setMode("fast")

    hrp.feedDataResume()

    assert "mode=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_profile_id() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setProfileId("pid-123")

    hrp.feedDataResume()

    assert "profileId=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_profile_words() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setProfileWords("word1 word2")

    hrp.feedDataResume()

    assert "profileWords=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_segmenter_type() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setSegmenterType("G4")

    hrp.feedDataResume()

    assert "segmenterType=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_segmenter_properties() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setSegmenterProperties("threshold=0.5")

    hrp.feedDataResume()

    assert "segmenterProperties=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_confidence_level() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setConfidenceLevel("0.3")

    hrp.feedDataResume()

    assert captured["domainId"] == "confidenceLevel=0.3"


def test_feed_data_resume_builds_domain_id_from_keep_filler_token() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setKeepFillerToken("1")

    hrp.feedDataResume()

    assert "keepFillerToken=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_result_updated_interval() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setResultUpdatedInterval("500")

    hrp.feedDataResume()

    assert "resultUpdatedInterval=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_max_decoding_time() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setMaxDecodingTime(10000)

    hrp.feedDataResume()

    assert "maxDecodingTime=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_max_response_time() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setMaxResponseTime(5000)

    hrp.feedDataResume()

    assert "maxResponseTime=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_max_decoding_rate() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setMaxDecodingRate(1.0)

    hrp.feedDataResume()

    assert "maxDecodingRate=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_target_response_time() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setTargetResponseTime(3000)

    hrp.feedDataResume()

    assert "targetResponseTime=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_target_decoding_rate() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setTargetDecodingRate(0.9)

    hrp.feedDataResume()

    assert "targetDecodingRate=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_recognition_timeout() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setRecognitionTimeout(30000)

    hrp.feedDataResume()

    assert "recognitionTimeout=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_extension() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setExtension("key=val")

    hrp.feedDataResume()

    assert "extension=" in captured["domainId"]


def test_feed_data_resume_builds_domain_id_from_authorization() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    captured = {}

    hrp.sendRequestHeader_ = _capture_header(captured, hrp)
    hrp.setAuthorization("Bearer tok")

    hrp.feedDataResume()

    assert "authorization=" in captured["domainId"]


def test_feed_data_when_not_connected_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=False)
    listener = MagicMock()
    hrp.setListener(listener)

    result = hrp.feedData(b"audio", 0, 5)

    assert result is False
    assert "disconnected" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_wrong_state_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 0

    result = hrp.feedData(b"audio", 0, 5)

    assert result is False
    assert "already stopped" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_success_from_state_2_calls_send_body() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 2
    captured = {}

    hrp.sendRequestBody_ = _send_body_capture(captured, hrp)
    audio = b"audio data"

    result = hrp.feedData(audio, 0, len(audio))

    assert result is True
    assert captured["data"] is audio
    assert captured["offset"] == 0
    assert captured["bytes"] == len(audio)
    assert captured["state"] == 3


def test_feed_data_success_from_state_3_also_succeeds() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 3
    captured = {}

    hrp.sendRequestBody_ = _send_body_mark_called(captured)

    result = hrp.feedData(b"x", 0, 1)

    assert result is True
    assert captured["called"] is True


def test_feed_data_ioerror_returns_false_with_error_message() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 2

    hrp.sendRequestBody_ = _always_raises("write error")

    result = hrp.feedData(b"audio", 0, 5)

    assert result is False
    assert "can't feed data to HTTP server" in hrp.getLastMessage()
    assert "write error" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_oserror_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 2

    hrp.sendRequestBody_ = _always_raises("broken pipe")

    result = hrp.feedData(b"audio", 0, 5)

    assert result is False
    assert "can't feed data to HTTP server" in hrp.getLastMessage()


def test_feed_data_pause_when_not_connected_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=False)
    listener = MagicMock()
    hrp.setListener(listener)

    result = hrp.feedDataPause()

    assert result is False
    assert "disconnected" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_pause_wrong_state_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 0

    result = hrp.feedDataPause()

    assert result is False
    assert "already stopped" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_pause_ioerror_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 2

    hrp.sendRequestBody_ = _always_raises("socket closed")

    result = hrp.feedDataPause()

    assert result is False
    assert "can't stop feeding data to HTTP server" in hrp.getLastMessage()
    assert "socket closed" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_pause_oserror_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 2

    hrp.sendRequestBody_ = _always_raises("broken pipe")

    result = hrp.feedDataPause()

    assert result is False
    assert "can't stop feeding data to HTTP server" in hrp.getLastMessage()


def test_feed_data_pause_error_state_returns_false_with_hrp_specific_message() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 2

    hrp.sendRequestBody_ = _send_body_error(hrp)

    result = hrp.feedDataPause()

    assert result is False
    assert hrp.state_ == 5
    assert "can't stop feeding data to HTTP server" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()
    assert "can't stop feeding data to HTTP server" in listener.TRACE.call_args[0][0]


def test_feed_data_pause_success_when_on_close_sets_state_to_0() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 2

    hrp.sendRequestBody_ = _send_body_close(hrp)

    result = hrp.feedDataPause()

    assert result is True
    assert "stopped feeding data to HTTP server" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_on_open_calls_listener_result_created() -> None:  # noqa: D103
    hrp = MockHrp()
    listener = MagicMock()
    hrp.setListener(listener)

    hrp.onOpen_("sess-abc123")

    listener.resultCreated.assert_called_once_with("sess-abc123")


def test_on_open_without_listener_does_not_raise() -> None:  # noqa: D103
    hrp = MockHrp()

    hrp.onOpen_("sess-abc123")


def test_on_close_sets_state_to_idle() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.state_ = 3

    hrp.onClose_()

    assert hrp.state_ == 0


@pytest.mark.parametrize(
    "initial_state",
    [-1, 0, 5],
    ids=["state_minus1", "state_0", "state_5"],
)
def test_on_error_early_return_for_inactive_states(initial_state: int) -> None:  # noqa: D103
    hrp = MockHrp()
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = initial_state

    hrp.onError_(Exception("some error"))

    assert hrp.state_ == initial_state
    assert listener.mock_calls == []


def test_on_error_active_state_sets_error_state_and_traces() -> None:  # noqa: D103
    hrp = MockHrp()
    listener = MagicMock()
    hrp.setListener(listener)
    hrp.state_ = 2

    hrp.onError_(Exception("unexpected disconnect"))

    assert hrp.state_ == 5
    assert "caught exception" in hrp.getLastMessage()
    assert "unexpected disconnect" in hrp.getLastMessage()
    listener.TRACE.assert_called_once()
    assert "caught exception" in listener.TRACE.call_args[0][0]


def test_on_error_active_state_without_listener_does_not_raise() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.state_ = 3

    hrp.onError_(OSError("broken pipe"))

    assert hrp.state_ == 5
    assert "caught exception" in hrp.getLastMessage()


@pytest.mark.parametrize(
    "active_state",
    [1, 2, 3, 4],
    ids=["state_1", "state_2", "state_3", "state_4"],
)
def test_on_error_any_active_state_transitions_to_error(active_state: int) -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.state_ = active_state

    hrp.onError_(RuntimeError("error"))

    assert hrp.state_ == 5


def test_on_message_with_partial_result_calls_result_updated() -> None:  # noqa: D103
    hrp = MockHrp()
    listener = MagicMock()
    hrp.setListener(listener)

    hrp.onMessage_('{"text":"hello"...')

    listener.resultUpdated.assert_called_once()
    listener.resultFinalized.assert_not_called()


def test_on_message_with_final_result_calls_result_finalized() -> None:  # noqa: D103
    hrp = MockHrp()
    listener = MagicMock()
    hrp.setListener(listener)

    hrp.onMessage_('{"text":"hello world"}')

    listener.resultFinalized.assert_called_once()
    listener.resultUpdated.assert_not_called()


def test_on_message_without_listener_does_not_raise() -> None:  # noqa: D103
    hrp = MockHrp()

    hrp.onMessage_('{"text":"hello world"}')


def test_set_confidence_level_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setConfidenceLevel("0.3")

    assert hrp.confidenceLevel_ == "0.3"


def test_set_service_authorization_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setServiceAuthorization("Bearer tok123")

    assert hrp.serviceAuthorization_ == "Bearer tok123"


def test_set_voice_detection_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setVoiceDetection("G4 threshold=0.5")

    assert hrp.voiceDetection_ == "G4 threshold=0.5"


def test_set_accept_topic_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setAcceptTopic("*")

    assert hrp.acceptTopic_ == "*"


def test_set_content_type_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setContentType("audio/x-pcm;bit=16;rate=16000;channels=1")

    assert hrp.contentType_ == "audio/x-pcm;bit=16;rate=16000;channels=1"


def test_set_accept_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setAccept("text/plain")

    assert hrp.accept_ == "text/plain"


def test_set_codec_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setCodec("MSM8K")

    assert hrp.codec_ == "MSM8K"


def test_set_result_type_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setResultType("json")

    assert hrp.resultType_ == "json"


def test_set_result_encoding_stores_value() -> None:  # noqa: D103
    hrp = MockHrp()
    hrp.setResultEncoding("UTF-8")

    assert hrp.resultEncoding_ == "UTF-8"
