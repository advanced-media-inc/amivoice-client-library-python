#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportAny=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false

import socket
from unittest.mock import MagicMock

import pytest

from com.amivoice.wrp.Wrp_ import Wrp_

_HANDSHAKE_RESPONSE = (
    b"HTTP/1.1 101 Switching Protocols\r\n"
    b"Upgrade: websocket\r\n"
    b"Connection: Upgrade\r\n"
    b"Sec-WebSocket-Accept: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
)


def _make_mock_socket() -> MagicMock:
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [_HANDSHAKE_RESPONSE]
    mock_socket.send.side_effect = len
    return mock_socket


@pytest.mark.parametrize(
    ("server_url", "expected_port", "secure"),
    [
        pytest.param(
            "ws://example.com/test",  # nosemgrep
            80,
            False,
            id="ws",
        ),
        pytest.param("wss://example.com/test", 443, True, id="wss"),
    ],
)
def test_connect_and_disconnect_are_mockable_without_real_network(  # noqa: D103
    monkeypatch: pytest.MonkeyPatch,
    server_url: str,
    expected_port: int,
    secure: bool,
) -> None:
    mock_socket = _make_mock_socket()
    mock_thread = MagicMock()
    create_connection = MagicMock(return_value=mock_socket)
    thread_factory = MagicMock(return_value=mock_thread)

    monkeypatch.setattr("com.amivoice.wrp.Wrp_.socket.create_connection", create_connection)
    monkeypatch.setattr("com.amivoice.wrp.Wrp_.threading.Thread", thread_factory)

    context = None
    if secure:
        context = MagicMock()
        context.wrap_socket.return_value = mock_socket
        monkeypatch.setattr(
            "com.amivoice.wrp.Wrp_.ssl.create_default_context",
            MagicMock(return_value=context),
        )

    wrp = Wrp_()

    wrp.connect_(server_url, None, 0, 0)

    create_connection.assert_called_once_with(("example.com", expected_port))
    if secure:
        assert context is not None
        context.wrap_socket.assert_called_once_with(mock_socket, server_hostname="example.com")
    assert wrp.socket_ is mock_socket
    thread_factory.assert_called_once()
    mock_thread.start.assert_called_once_with()

    wrp.disconnect_()

    mock_socket.shutdown.assert_called_once_with(socket.SHUT_RDWR)
    mock_socket.close.assert_called_once_with()
    mock_thread.join.assert_called_once_with()
    assert wrp.socket_ is None
