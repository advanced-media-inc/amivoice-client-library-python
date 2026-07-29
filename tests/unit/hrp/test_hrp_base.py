from unittest.mock import MagicMock

import pytest

from com.amivoice.hrp.Hrp import Hrp
from com.amivoice.hrp.Hrp_ import Hrp_


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


def test_get_version() -> None:  # noqa: D103
    version = Hrp.getVersion()
    assert version.startswith("Hrp/1.0.06 Python/")
    assert "linux" in version or "win" in version or "darwin" in version


def test_construct_returns_hrp_instance() -> None:  # noqa: D103
    obj = Hrp.construct()
    assert isinstance(obj, Hrp_)


def test_construct_impl1_returns_hrp_instance() -> None:  # noqa: D103
    obj = Hrp.construct(1)
    assert isinstance(obj, Hrp_)


def test_construct_invalid_raises() -> None:  # noqa: D103
    with pytest.raises(ValueError, match="Unknown implementation"):
        Hrp.construct(99)


def test_connect_guard_missing_url() -> None:  # noqa: D103
    hrp = MockHrp(connected=False)
    result = hrp.connect()
    assert result is False
    assert "Missing server URL" in hrp.getLastMessage()


def test_connect_guard_already_connected() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.serverURL_ = "http://example.com"
    result = hrp.connect()
    assert result is False
    assert "already connected" in hrp.getLastMessage()


def test_disconnect_guard_not_connected() -> None:  # noqa: D103
    hrp = MockHrp(connected=False)
    result = hrp.disconnect()
    assert result is False
    assert "already disconnected" in hrp.getLastMessage()


def _capture_feed_data_resume_type(hrp: MockHrp, feed_type: str | None, data_bytes: int) -> tuple[bool, dict[str, object]]:
    captured: dict[str, object] = {}

    def mock_header(*args: object) -> None:
        request_type = args[9]
        request_data_bytes = args[10]
        captured["type"] = request_type
        captured["dataBytes"] = request_data_bytes
        hrp.state_ = 2

    hrp.sendRequestHeader_ = mock_header
    result = hrp.feedDataResume(type=feed_type, dataBytes=data_bytes)
    return result, captured


def test_feedDataResume_type_mc_when_databytes_zero() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    result, captured = _capture_feed_data_resume_type(hrp, "mc", 0)
    assert result is True
    assert captured["type"] == "mc"


def test_feedDataResume_type_sc_when_single_databytes_zero() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    result, captured = _capture_feed_data_resume_type(hrp, "s", 0)
    assert result is True
    assert captured["type"] == "sc"


def test_feedDataResume_type_m_when_databytes_positive() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    result, captured = _capture_feed_data_resume_type(hrp, "mc", 1)
    assert result is True
    assert captured["type"] == "mc"


def test_feedDataResume_type_s_when_databytes_positive() -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    result, captured = _capture_feed_data_resume_type(hrp, "s", 1)
    assert result is True
    assert captured["type"] == "s "


def test_feedDataResume_not_connected_returns_false() -> None:  # noqa: D103
    hrp = MockHrp(connected=False)
    hrp.state_ = 0
    result = hrp.feedDataResume()
    assert result is False
    assert "disconnected" in hrp.getLastMessage()


def test_connect_listener_trace_on_missing_url() -> None:  # noqa: D103
    listener = MagicMock()
    hrp = MockHrp(connected=False)
    hrp.setListener(listener)
    hrp.connect()
    listener.TRACE.assert_called_once()
    assert "Missing server URL" in listener.TRACE.call_args[0][0]
