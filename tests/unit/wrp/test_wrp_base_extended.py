# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false, reportAny=false, reportUnknownArgumentType=false

from collections.abc import Callable
from typing import NoReturn
from unittest.mock import MagicMock

import pytest

from com.amivoice.wrp.Wrp import Wrp


class MockWrp(Wrp):  # noqa: D101
    def __init__(self, connected: bool = False) -> None:  # noqa: D107
        super().__init__()
        self._connected = connected

    def isConnected_(self) -> bool:  # noqa: D102
        return self._connected

    def connect_(self, *_args: object) -> None:  # noqa: D102
        pass

    def disconnect_(self) -> None:  # noqa: D102
        pass

    def sendRequest_(self, *_args: object) -> None:  # noqa: D102
        pass


def _always_raises(message: str) -> Callable[..., NoReturn]:
    def send_raises(*args: object) -> NoReturn:
        del args
        raise OSError(message)

    return send_raises


def _send_request_capture(captured: dict[str, object], wrp: MockWrp) -> Callable[[bytes, int, int, int], None]:
    def send_request(data: bytes, data_offset: int, data_bytes: int, command: int) -> None:
        captured["data"] = data
        captured["data_offset"] = data_offset
        captured["data_bytes"] = data_bytes
        captured["command"] = command
        captured["state_during_send"] = wrp.state_

    return send_request


def _send_request_command_only(captured: dict[str, int]) -> Callable[[bytes, int, int, int], None]:
    def send_request(data: bytes, data_offset: int, data_bytes: int, command: int) -> None:
        del data, data_offset, data_bytes
        captured["command"] = command

    return send_request


def _send_request_error_response(wrp: MockWrp) -> Callable[[bytes, int, int, int], None]:
    def send_request(data: bytes, data_offset: int, data_bytes: int, command: int) -> None:
        del data, data_offset, data_bytes, command
        wrp.onMessage_("e bad stop")

    return send_request


# ---------------------------------------------------------------------------
# connect() — exception path
# ---------------------------------------------------------------------------


def test_connect_exception_sets_error_state_and_returns_false() -> None:  # noqa: D103
    wrp = MockWrp()
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.setServerURL(
        "ws://example.com/asr",  # nosemgrep
    )

    def connect_raises(*args: object) -> NoReturn:
        del args
        raise OSError("connection refused")

    wrp.connect_ = connect_raises

    result = wrp.connect()

    assert result is False
    assert wrp.state_ == -1
    assert "can't connect to WebSocket server" in wrp.getLastMessage()
    assert "connection refused" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()
    assert "can't connect to WebSocket server" in listener.TRACE.call_args[0][0]


def test_connect_exception_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.setServerURL(
        "ws://example.com/asr",  # nosemgrep
    )

    def connect_raises(*args: object) -> NoReturn:
        del args
        raise RuntimeError("timeout")

    wrp.connect_ = connect_raises

    result = wrp.connect()

    assert result is False
    assert wrp.state_ == -1


# ---------------------------------------------------------------------------
# disconnect() — success path
# ---------------------------------------------------------------------------


def test_disconnect_when_connected_returns_true_and_traces() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    listener = MagicMock()
    wrp.setListener(listener)

    result = wrp.disconnect()

    assert result is True
    assert wrp.state_ == -1
    assert "disconnected from WebSocket server" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()
    assert "disconnected from WebSocket server" in listener.TRACE.call_args[0][0]


def test_disconnect_when_connected_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)

    result = wrp.disconnect()

    assert result is True
    assert wrp.state_ == -1


# ---------------------------------------------------------------------------
# feedDataResume() — guard paths
# ---------------------------------------------------------------------------


def test_feed_data_resume_when_not_connected_returns_false() -> None:  # noqa: D103
    wrp = MockWrp(connected=False)
    listener = MagicMock()
    wrp.setListener(listener)

    result = wrp.feedDataResume()

    assert result is False
    assert "disconnected" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_resume_when_already_started_returns_false() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = 2  # already in feeding state

    result = wrp.feedDataResume()

    assert result is False
    assert "already started" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_resume_ioerror_returns_false_with_error_message() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = 0

    wrp.sendRequest_ = _always_raises("network error")

    result = wrp.feedDataResume()

    assert result is False
    assert "can't start feeding data to WebSocket server" in wrp.getLastMessage()
    assert "network error" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_resume_oserror_returns_false_with_error_message() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 0

    wrp.sendRequest_ = _always_raises("broken pipe")

    result = wrp.feedDataResume()

    assert result is False
    assert "can't start feeding data to WebSocket server" in wrp.getLastMessage()


def test_feed_data_resume_builds_command_from_confidence_level() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 0
    captured: dict[str, bytes] = {}

    def send_request(data: bytes, data_offset: int, data_bytes: int, command: int) -> None:
        del data_offset, data_bytes, command
        captured["data"] = data
        wrp.state_ = 2

    wrp.sendRequest_ = send_request
    wrp.setConfidenceLevel("0.3")

    result = wrp.feedDataResume()

    assert result is True
    assert captured["data"] == b"s 16K \x01 confidenceLevel=0.3"


# ---------------------------------------------------------------------------
# feedData() — all branches
# ---------------------------------------------------------------------------


def test_feed_data_when_not_connected_returns_false() -> None:  # noqa: D103
    wrp = MockWrp(connected=False)
    listener = MagicMock()
    wrp.setListener(listener)

    result = wrp.feedData(b"audio", 0, 5)

    assert result is False
    assert "disconnected" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_when_not_connected_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp(connected=False)

    result = wrp.feedData(b"audio", 0, 5)

    assert result is False


def test_feed_data_wrong_state_returns_false() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = 0  # idle, not in feeding state

    result = wrp.feedData(b"audio", 0, 5)

    assert result is False
    assert "already stopped" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_wrong_state_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 0

    result = wrp.feedData(b"audio", 0, 5)

    assert result is False


def test_feed_data_success_calls_send_request_and_returns_true() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 2
    captured = {}

    wrp.sendRequest_ = _send_request_capture(captured, wrp)
    audio = b"audio data"

    result = wrp.feedData(audio, 0, len(audio))

    assert result is True
    assert captured["data"] is audio
    assert captured["data_offset"] == 0
    assert captured["data_bytes"] == len(audio)
    assert captured["command"] == 0x70  # 'p'
    assert captured["state_during_send"] == 3


def test_feed_data_from_state_3_also_succeeds() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 3  # already feeding
    captured = {}

    wrp.sendRequest_ = _send_request_command_only(captured)

    result = wrp.feedData(b"x", 0, 1)

    assert result is True
    assert captured["command"] == 0x70


def test_feed_data_ioerror_returns_false_with_error_message() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = 2

    wrp.sendRequest_ = _always_raises("write error")

    result = wrp.feedData(b"audio", 0, 5)

    assert result is False
    assert "can't feed data to WebSocket server" in wrp.getLastMessage()
    assert "write error" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_oserror_returns_false_with_error_message() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 2

    wrp.sendRequest_ = _always_raises("broken pipe")

    result = wrp.feedData(b"audio", 0, 5)

    assert result is False
    assert "can't feed data to WebSocket server" in wrp.getLastMessage()


def test_feed_data_ioerror_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 2

    wrp.sendRequest_ = _always_raises("write error")

    result = wrp.feedData(b"audio", 0, 5)

    assert result is False


# ---------------------------------------------------------------------------
# feedDataPause() — guard and exception paths
# ---------------------------------------------------------------------------


def test_feed_data_pause_when_not_connected_returns_false() -> None:  # noqa: D103
    wrp = MockWrp(connected=False)
    listener = MagicMock()
    wrp.setListener(listener)

    result = wrp.feedDataPause()

    assert result is False
    assert "disconnected" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_pause_when_not_connected_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp(connected=False)

    result = wrp.feedDataPause()

    assert result is False


def test_feed_data_pause_wrong_state_returns_false() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = 0  # idle, not feeding

    result = wrp.feedDataPause()

    assert result is False
    assert "already stopped" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_pause_wrong_state_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 0

    result = wrp.feedDataPause()

    assert result is False


def test_feed_data_pause_ioerror_returns_false_with_error_message() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = 2

    wrp.sendRequest_ = _always_raises("socket closed")

    result = wrp.feedDataPause()

    assert result is False
    assert "can't stop feeding data to WebSocket server" in wrp.getLastMessage()
    assert "socket closed" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()


def test_feed_data_pause_oserror_returns_false_with_error_message() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 2

    wrp.sendRequest_ = _always_raises("broken pipe")

    result = wrp.feedDataPause()

    assert result is False
    assert "can't stop feeding data to WebSocket server" in wrp.getLastMessage()


def test_feed_data_pause_ioerror_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 2

    wrp.sendRequest_ = _always_raises("error")

    result = wrp.feedDataPause()

    assert result is False


def test_feed_data_pause_error_response_returns_false() -> None:
    """When server responds with 'e bad stop', feedDataPause must return False."""
    wrp = MockWrp(connected=True)
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = 2

    wrp.sendRequest_ = _send_request_error_response(wrp)

    result = wrp.feedDataPause()

    assert result is False
    assert wrp.state_ == 5


# ---------------------------------------------------------------------------
# onOpen_() — no-op but exercised
# ---------------------------------------------------------------------------


def test_on_open_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.onOpen_()  # should not raise


# ---------------------------------------------------------------------------
# onClose_() — sets state_ = 0 and notifies
# ---------------------------------------------------------------------------


def test_on_close_sets_state_to_idle() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.state_ = 2

    wrp.onClose_()

    assert wrp.state_ == 0


# ---------------------------------------------------------------------------
# onError_() — early return and error-taking branches
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "initial_state",
    [-1, 0, 5],
    ids=["state_minus1", "state_0", "state_5"],
)
def test_on_error_early_return_for_inactive_states(initial_state: int) -> None:  # noqa: D103
    wrp = MockWrp()
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = initial_state

    wrp.onError_(Exception("some error"))

    assert wrp.state_ == initial_state  # unchanged
    assert listener.mock_calls == []


def test_on_error_active_state_sets_error_state_and_traces() -> None:  # noqa: D103
    wrp = MockWrp()
    listener = MagicMock()
    wrp.setListener(listener)
    wrp.state_ = 2  # active feeding state

    wrp.onError_(Exception("unexpected disconnect"))

    assert wrp.state_ == 5
    assert "caught exception" in wrp.getLastMessage()
    assert "unexpected disconnect" in wrp.getLastMessage()
    listener.TRACE.assert_called_once()
    assert "caught exception" in listener.TRACE.call_args[0][0]


def test_on_error_active_state_without_listener_does_not_raise() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.state_ = 3

    wrp.onError_(OSError("broken pipe"))

    assert wrp.state_ == 5
    assert "caught exception" in wrp.getLastMessage()


@pytest.mark.parametrize(
    "active_state",
    [1, 2, 3, 4],
    ids=["state_1", "state_2", "state_3", "state_4"],
)
def test_on_error_any_active_state_transitions_to_error(active_state: int) -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.state_ = active_state

    wrp.onError_(RuntimeError("error"))

    assert wrp.state_ == 5


# ---------------------------------------------------------------------------
# setServiceAuthorization() — sets authorization_ when non-None
# ---------------------------------------------------------------------------


def test_set_confidence_level_stores_value() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.setConfidenceLevel("0.3")

    assert wrp.confidenceLevel_ == "0.3"


def test_set_service_authorization_stores_value() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.setServiceAuthorization("Bearer token123")

    assert wrp.authorization_ == "Bearer token123"


def test_set_service_authorization_none_does_not_overwrite() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.authorization_ = "existing"
    wrp.setServiceAuthorization(None)

    assert wrp.authorization_ == "existing"


# ---------------------------------------------------------------------------
# setVoiceDetection() — two parsing branches
# ---------------------------------------------------------------------------


def test_set_voice_detection_none_does_not_set_attributes() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.setVoiceDetection(None)

    assert wrp.segmenterType_ is None
    assert wrp.segmenterProperties_ is None


def test_set_voice_detection_generic_string_sets_g4_and_full_value() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.setVoiceDetection("somevalue")

    assert wrp.segmenterType_ == "G4"
    assert wrp.segmenterProperties_ == "somevalue"


def test_set_voice_detection_short_string_uses_default_branch() -> None:
    """Strings of length <= 3 must not trigger the G-prefix branch."""
    wrp = MockWrp()
    wrp.setVoiceDetection("G4 ")  # length == 3, not > 3

    assert wrp.segmenterType_ == "G4"
    assert wrp.segmenterProperties_ == "G4 "


def test_set_voice_detection_g_prefix_format_splits_type_and_properties() -> None:
    """String like 'G4 10ms' (len>3, starts with G, char[2]==' ') triggers inner branch."""
    wrp = MockWrp()
    wrp.setVoiceDetection("G4 threshold=0.5")

    assert wrp.segmenterType_ == "G4"
    assert wrp.segmenterProperties_ == "threshold=0.5"


def test_set_voice_detection_g2_prefix_format() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.setVoiceDetection("G2 fast")

    assert wrp.segmenterType_ == "G2"
    assert wrp.segmenterProperties_ == "fast"


def test_set_voice_detection_no_space_at_index2_uses_default_branch() -> None:
    """String starting with G but char[2] != ' ' should fall through to default."""
    wrp = MockWrp()
    wrp.setVoiceDetection("GAx somevalue")  # char[2] == 'x', not ' '

    assert wrp.segmenterType_ == "G4"
    assert wrp.segmenterProperties_ == "GAx somevalue"


# ---------------------------------------------------------------------------
# getWaitingResults() — getter exercised
# ---------------------------------------------------------------------------


def test_get_waiting_results_returns_current_count() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.waitingResults_ = 3

    assert wrp.getWaitingResults() == 3


def test_feed_data_resume_builds_command_from_rule_grammar_parameters() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 0
    captured: dict[str, bytes] = {}

    def send_request(data: bytes, data_offset: int, data_bytes: int, command: int) -> None:
        del data_offset, data_bytes, command
        captured["data"] = data
        wrp.state_ = 2

    wrp.sendRequest_ = send_request
    wrp.setCompleteTimeout("5000")
    wrp.setWildcardModelPenalty("4.0")

    result = wrp.feedDataResume()

    assert result is True
    assert captured["data"] == b"s 16K \x01 completeTimeout=5000 wildcardModelPenalty=4.0"


def test_set_rule_grammar_parameters_stores_values() -> None:  # noqa: D103
    wrp = MockWrp()
    wrp.setCompleteTimeout("5000")
    wrp.setWildcardModelPenalty("4.0")

    assert wrp.completeTimeout_ == "5000"
    assert wrp.wildcardModelPenalty_ == "4.0"
