# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false, reportAny=false, reportUnknownArgumentType=false

from unittest.mock import MagicMock

import pytest

from com.amivoice.wrp.Wrp_ import Wrp_

_HANDSHAKE_RESPONSE = (
    b"HTTP/1.1 101 Switching Protocols\r\n"
    b"Upgrade: websocket\r\n"
    b"Connection: Upgrade\r\n"
    b"Sec-WebSocket-Accept: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
)


def _make_mock_socket(handshake: bytes = _HANDSHAKE_RESPONSE) -> MagicMock:
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [handshake]
    mock_socket.send.side_effect = len
    return mock_socket


def test_connect_raises_value_error_when_url_missing_scheme(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    wrp = Wrp_()
    with pytest.raises(ValueError, match="Invalid server URL"):
        wrp.connect_("example.com/path", None, 0, 0)


def test_connect_raises_value_error_for_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    wrp = Wrp_()
    with pytest.raises(ValueError, match="Invalid scheme: http"):
        wrp.connect_("http://example.com/path", None, 0, 0)


def test_connect_raises_value_error_for_invalid_port(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    create_connection = MagicMock()
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    wrp = Wrp_()
    with pytest.raises(ValueError, match="Invalid port: bad"):
        wrp.connect_(
            "ws://example.com:bad/path",  # nosemgrep
            None,
            0,
            0,
        )


def test_connect_uses_timeout_when_connect_timeout_positive(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = _make_mock_socket()
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)

    wrp = Wrp_()
    wrp.connect_(
        "ws://example.com/path",  # nosemgrep
        None,
        5000,
        0,
    )

    create_connection.assert_called_once_with(("example.com", 80), 5.0)


def test_connect_sets_receive_timeout_on_socket(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = _make_mock_socket()
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)

    wrp = Wrp_()
    wrp.connect_(
        "ws://example.com/path",  # nosemgrep
        None,
        0,
        3000,
    )

    mock_socket.settimeout.assert_called_once_with(3.0)


def test_connect_sets_none_timeout_when_receive_timeout_zero(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = _make_mock_socket()
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)

    wrp = Wrp_()
    wrp.connect_(
        "ws://example.com/path",  # nosemgrep
        None,
        0,
        0,
    )

    mock_socket.settimeout.assert_called_once_with(None)


def test_connect_wss_wraps_socket_with_ssl(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = _make_mock_socket()
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=MagicMock())
    context = MagicMock()
    context.wrap_socket.return_value = mock_socket

    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)
    monkeypatch.setattr(
        "com.amivoice.wrp.Wrp_.ssl.create_default_context",
        MagicMock(return_value=context),
    )

    wrp = Wrp_()
    wrp.connect_("wss://example.com/path", None, 0, 0)

    context.wrap_socket.assert_called_once_with(mock_socket, server_hostname="example.com")


def test_connect_ssl_failure_closes_socket_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = MagicMock()
    create_connection = MagicMock(return_value=mock_socket)
    context = MagicMock()
    context.wrap_socket.side_effect = OSError("ssl failed")

    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr(
        "com.amivoice.wrp.Wrp_.ssl.create_default_context",
        MagicMock(return_value=context),
    )

    wrp = Wrp_()
    with pytest.raises(OSError, match="ssl failed"):
        wrp.connect_("wss://example.com/path", None, 0, 0)

    mock_socket.close.assert_called_once()
    assert wrp.socket_ is None


def test_connect_raises_ioerror_when_handshake_returns_eof(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = MagicMock()
    mock_socket.recv.return_value = b""
    mock_socket.send.side_effect = len
    create_connection = MagicMock(return_value=mock_socket)

    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)

    wrp = Wrp_()
    with pytest.raises(IOError, match="Unexpected end of stream"):
        wrp.connect_(
            "ws://example.com/path",  # nosemgrep
            None,
            0,
            0,
        )


def test_connect_raises_ioerror_when_server_returns_non_101(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    non_101_response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n"
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [non_101_response]
    mock_socket.send.side_effect = len
    create_connection = MagicMock(return_value=mock_socket)

    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)

    wrp = Wrp_()
    with pytest.raises(IOError, match="Handshake error"):
        wrp.connect_(
            "ws://example.com/path",  # nosemgrep
            None,
            0,
            0,
        )


def test_connect_ws_default_port_is_80(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = _make_mock_socket()
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)

    wrp = Wrp_()
    wrp.connect_(
        "ws://example.com/path",  # nosemgrep
        None,
        0,
        0,
    )

    create_connection.assert_called_once_with(("example.com", 80))


def test_connect_wss_default_port_is_443(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = _make_mock_socket()
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=MagicMock())
    context = MagicMock()
    context.wrap_socket.return_value = mock_socket
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)
    monkeypatch.setattr(
        "com.amivoice.wrp.Wrp_.ssl.create_default_context",
        MagicMock(return_value=context),
    )

    wrp = Wrp_()
    wrp.connect_("wss://example.com/path", None, 0, 0)

    create_connection.assert_called_once_with(("example.com", 443))


def test_connect_custom_port_is_used(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = _make_mock_socket()
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)

    wrp = Wrp_()
    wrp.connect_(
        "ws://example.com:9090/path",  # nosemgrep
        None,
        0,
        0,
    )

    create_connection.assert_called_once_with(("example.com", 9090))


def test_connect_url_without_path_uses_slash_as_resource(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D103
    mock_socket = _make_mock_socket()
    sent_data = []
    mock_socket.send.side_effect = lambda data: sent_data.append(bytes(data)) or len(data)
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)

    wrp = Wrp_()
    wrp.connect_(
        "ws://example.com",  # nosemgrep
        None,
        0,
        0,
    )

    combined = b"".join(sent_data)
    assert b"GET / HTTP/1.1" in combined
