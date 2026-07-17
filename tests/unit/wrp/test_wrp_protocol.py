# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false, reportAny=false, reportUnknownArgumentType=false
from collections.abc import Callable
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


def _assert_no_listener_calls(_wrp: MockWrp, listener: MagicMock) -> None:
    assert listener.mock_calls == []


def _assert_trace(expected_message: str) -> Callable[[MockWrp, MagicMock], None]:
    def _assert(wrp: MockWrp, listener: MagicMock) -> None:
        listener.TRACE.assert_called_once_with(expected_message)
        assert wrp.getLastMessage() == expected_message

    return _assert


def _assert_listener_call(method_name: str, *args: object) -> Callable[[MockWrp, MagicMock], None]:
    def _assert(_wrp: MockWrp, listener: MagicMock) -> None:
        getattr(listener, method_name).assert_called_once_with(*args)

    return _assert


@pytest.mark.parametrize(
    ("message", "initial_state", "initial_waiting", "expected_state", "expected_waiting", "assertion"),
    [
        pytest.param("", 3, 2, 3, 2, _assert_no_listener_calls, id="empty-message"),
        pytest.param(
            "s",
            1,
            0,
            2,
            0,
            _assert_trace("INFO: started feeding data to WebSocket server"),
            id="start-success",
        ),
        pytest.param(
            "s bad request",
            1,
            0,
            5,
            0,
            _assert_trace("ERROR: can't start feeding data to WebSocket server (bad request)"),
            id="start-error",
        ),
        pytest.param("p", 3, 0, 3, 0, _assert_no_listener_calls, id="pass-through"),
        pytest.param(
            "p bad chunk",
            3,
            0,
            5,
            0,
            _assert_trace("ERROR: can't feed data to WebSocket server (bad chunk)"),
            id="feed-error",
        ),
        pytest.param(
            "e",
            4,
            0,
            0,
            0,
            _assert_trace("INFO: stopped feeding data to WebSocket server"),
            id="stop-success",
        ),
        pytest.param(
            "e bad stop",
            4,
            0,
            5,
            0,
            _assert_trace("ERROR: can't stop feeding data to WebSocket server (bad stop)"),
            id="stop-error",
        ),
        pytest.param(
            "S 123",
            2,
            4,
            2,
            5,
            _assert_listener_call("utteranceStarted", 123),
            id="utterance-started",
        ),
        pytest.param(
            "E 456",
            2,
            4,
            2,
            4,
            _assert_listener_call("utteranceEnded", 456),
            id="utterance-ended",
        ),
        pytest.param(
            "C",
            2,
            4,
            2,
            4,
            _assert_listener_call("resultCreated"),
            id="result-created",
        ),
        pytest.param(
            "U partial result",
            2,
            4,
            2,
            4,
            _assert_listener_call("resultUpdated", "partial result"),
            id="result-updated",
        ),
        pytest.param(
            "A final result",
            2,
            2,
            2,
            1,
            _assert_listener_call("resultFinalized", "final result"),
            id="result-finalized-a",
        ),
        pytest.param(
            "R rejected result",
            2,
            2,
            2,
            1,
            _assert_listener_call("resultFinalized", "\001\001\001\001\001rejected result"),
            id="result-finalized-r",
        ),
        pytest.param(
            "Q event payload",
            2,
            1,
            2,
            1,
            _assert_listener_call("eventNotified", "Q", "event payload"),
            id="event-q",
        ),
        pytest.param(
            "G grammar payload",
            2,
            1,
            2,
            1,
            _assert_listener_call("eventNotified", "G", "grammar payload"),
            id="event-g",
        ),
    ],
)
def test_on_message_protocol_branches(  # noqa: D103, PLR0913
    message: str,
    initial_state: int,
    initial_waiting: int,
    expected_state: int,
    expected_waiting: int,
    assertion: Callable[[MockWrp, MagicMock], None],
) -> None:
    listener = MagicMock()
    wrp = MockWrp()
    wrp.setListener(listener)
    wrp.state_ = initial_state
    wrp.waitingResults_ = initial_waiting

    wrp.onMessage_(message)

    assert wrp.state_ == expected_state
    assert wrp.waitingResults_ == expected_waiting
    assertion(wrp, listener)


def _install_send_request(wrp: MockWrp, response_message: str | None) -> dict[str, object]:
    captured = {}

    def send_request(data: bytes, data_offset: int, data_bytes: int, command: int) -> None:
        captured["data"] = data
        captured["data_offset"] = data_offset
        captured["data_bytes"] = data_bytes
        captured["command"] = command
        captured["state_during_send"] = wrp.state_
        if response_message is not None:
            wrp.onMessage_(response_message)

    wrp.sendRequest_ = send_request
    return captured


def test_feed_data_resume_builds_default_start_command() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 0
    captured = _install_send_request(wrp, "s")

    assert wrp.feedDataResume() is True
    assert captured["data"] == b"s 16K \001"
    assert captured["data_offset"] == 0
    assert captured["data_bytes"] == len(captured["data"])
    assert captured["command"] == 0
    assert captured["state_during_send"] == 1
    assert wrp.state_ == 2


def test_feed_data_resume_builds_command_with_quoted_options() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 0
    wrp.codec_ = "8K"
    wrp.grammarFileNames_ = "grammar\001dict"
    wrp.mode_ = "auto mode"
    wrp.profileId_ = "profile id"
    wrp.profileWords_ = 'foo "bar" baz'
    wrp.segmenterType_ = "seg type"
    wrp.segmenterProperties_ = 'alpha "beta" gamma'
    wrp.keepFillerToken_ = "keep filler"
    wrp.resultUpdatedInterval_ = "250 ms"
    wrp.maxDecodingTime_ = "1000 ms"
    wrp.maxResponseTime_ = "2000 ms"
    wrp.maxDecodingRate_ = "2 x"
    wrp.targetResponseTime_ = "fast mode"
    wrp.targetDecodingRate_ = "steady pace"
    wrp.noInputTimeout_ = "300 ms"
    wrp.recognitionTimeout_ = "400 ms"
    wrp.extension_ = 'client "alpha"'
    wrp.authorization_ = "auth token"
    wrp.resultType_ = "json extended"
    captured = _install_send_request(wrp, "s")

    assert wrp.feedDataResume() is True
    assert captured["data"].decode("UTF-8") == (
        "s 8K grammar\001dict\001"
        ' mode="auto mode"'
        ' profileId="profile id"'
        ' profileWords="foo ""bar"" baz"'
        ' segmenterType="seg type"'
        ' segmenterProperties="alpha ""beta"" gamma"'
        ' keepFillerToken="keep filler"'
        ' resultUpdatedInterval="250 ms"'
        ' maxDecodingTime="1000 ms"'
        ' maxResponseTime="2000 ms"'
        ' maxDecodingRate="2 x"'
        ' targetResponseTime="fast mode"'
        ' targetDecodingRate="steady pace"'
        ' noInputTimeout="300 ms"'
        ' recognitionTimeout="400 ms"'
        ' extension="client ""alpha"""'
        ' authorization="auth token"'
        ' resultType="json extended"'
    )
    assert wrp.state_ == 2


def test_feed_data_pause_transitions_to_idle_state() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.state_ = 2
    captured = _install_send_request(wrp, "e")

    assert wrp.feedDataPause() is True
    assert captured["data"] == b"e"
    assert captured["data_offset"] == 0
    assert captured["data_bytes"] == 1
    assert captured["command"] == 0
    assert captured["state_during_send"] == 4
    assert wrp.state_ == 0


def test_invalid_start_response_transitions_feed_data_resume_to_error_state() -> None:  # noqa: D103
    listener = MagicMock()
    wrp = MockWrp(connected=True)
    wrp.setListener(listener)
    wrp.state_ = 0
    captured = _install_send_request(wrp, "s invalid request")

    assert wrp.feedDataResume() is False
    assert captured["data"] == b"s 16K \001"
    assert captured["state_during_send"] == 1
    assert wrp.state_ == 5
    listener.TRACE.assert_called_once_with("ERROR: can't start feeding data to WebSocket server (invalid request)")
