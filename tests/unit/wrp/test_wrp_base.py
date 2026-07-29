from unittest.mock import MagicMock

import pytest

from com.amivoice.wrp.Wrp import Wrp
from com.amivoice.wrp.Wrp_ import Wrp_


class MockWrp(Wrp):  # noqa: D101
    def __init__(self, connected: bool = False) -> None:  # noqa: D107
        super().__init__()
        self._connected = connected

    def isConnected_(self) -> bool:  # noqa: D102
        return self._connected

    def connect_(self, *args: object) -> None:  # noqa: D102
        pass

    def disconnect_(self) -> None:  # noqa: D102
        pass

    def sendRequest_(self, *args: object) -> None:  # noqa: D102
        pass


def test_get_version() -> None:  # noqa: D103
    version = Wrp.getVersion()
    assert version.startswith("Wrp/1.0.06 Python/")
    assert "linux" in version or "win" in version or "darwin" in version


def test_construct_returns_wrp_instance() -> None:  # noqa: D103
    obj = Wrp.construct()
    assert isinstance(obj, Wrp_)


def test_construct_impl0_returns_wrp_instance() -> None:  # noqa: D103
    obj = Wrp.construct(0)
    assert isinstance(obj, Wrp_)


def test_construct_impl1_returns_wrp_instance() -> None:  # noqa: D103
    obj = Wrp.construct(1)
    assert isinstance(obj, Wrp_)


def test_construct_invalid_raises() -> None:  # noqa: D103
    with pytest.raises(ValueError, match="Unknown implementation"):
        Wrp.construct(99)


@pytest.mark.parametrize(
    ("input_url", "expected"),
    [
        (
            "http://example.com/path",
            "ws://example.com/path",  # nosemgrep
        ),
        ("https://example.com/path", "wss://example.com/path"),
        (
            "ws://example.com/path",  # nosemgrep
            "ws://example.com/path",  # nosemgrep
        ),
        ("wss://example.com/path", "wss://example.com/path"),
    ],
)
def test_set_server_url_conversion(input_url: str, expected: str) -> None:  # noqa: D103
    wrp = Wrp()
    wrp.setServerURL(input_url)
    assert wrp.serverURL_ == expected


def test_connect_guard_missing_url() -> None:  # noqa: D103
    wrp = MockWrp(connected=False)
    result = wrp.connect()
    assert result is False
    assert "Missing server URL" in wrp.getLastMessage()


def test_connect_guard_already_connected() -> None:  # noqa: D103
    wrp = MockWrp(connected=True)
    wrp.serverURL_ = "ws://example.com"  # nosemgrep
    result = wrp.connect()
    assert result is False
    assert "already connected" in wrp.getLastMessage()


def test_disconnect_guard_not_connected() -> None:  # noqa: D103
    wrp = MockWrp(connected=False)
    result = wrp.disconnect()
    assert result is False
    assert "already disconnected" in wrp.getLastMessage()


def test_connect_listener_trace_on_missing_url() -> None:  # noqa: D103
    listener = MagicMock()
    wrp = MockWrp(connected=False)
    wrp.setListener(listener)
    wrp.connect()
    listener.TRACE.assert_called_once()
    assert "Missing server URL" in listener.TRACE.call_args[0][0]
