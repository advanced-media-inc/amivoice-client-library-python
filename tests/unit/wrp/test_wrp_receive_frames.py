# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false, reportAny=false, reportUnknownArgumentType=false

from collections.abc import Sequence
from unittest.mock import MagicMock

import pytest

from com.amivoice.wrp.Wrp_ import Wrp_


def _make_wrp(recv_chunks: Sequence[bytes]) -> Wrp_:
    wrp = Wrp_()
    wrp.inData_ = bytearray()
    wrp.inDataBytes_ = 0
    wrp.result__ = None
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = list(recv_chunks)
    wrp.socket_ = mock_socket
    return wrp


def test_receive_response_returns_false_on_eof_with_zero_indata() -> None:  # noqa: D103
    wrp = _make_wrp([b""])
    result = wrp.receiveResponse_()
    assert result is False


def test_receive_response_raises_ioerror_on_eof_with_pending_data() -> None:  # noqa: D103
    wrp = _make_wrp([b""])
    wrp.inDataBytes_ = 1
    wrp.inData_ = bytearray([0x81])
    with pytest.raises(IOError, match="Unexpected end of stream"):
        wrp.receiveResponse_()


def test_receive_response_text_frame_small_payload() -> None:  # noqa: D103
    payload = b"hello"
    header = bytes([0x81, len(payload)])
    wrp = _make_wrp([header + payload])
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == "hello"


def test_receive_response_text_frame_strips_trailing_crlf() -> None:  # noqa: D103
    payload = b"hello\r\n"
    header = bytes([0x81, len(payload)])
    wrp = _make_wrp([header + payload])
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == "hello"


def test_receive_response_text_frame_strips_trailing_lf_only() -> None:  # noqa: D103
    payload = b"world\n"
    header = bytes([0x81, len(payload)])
    wrp = _make_wrp([header + payload])
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == "world"


def test_receive_response_extended_length_126() -> None:  # noqa: D103
    payload = b"x" * 200
    length = len(payload)
    header = bytes([0x81, 126, (length >> 8) & 0xFF, length & 0xFF])
    wrp = _make_wrp([header + payload])
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == "x" * 200


def test_receive_response_extended_length_127_valid() -> None:  # noqa: D103
    payload = b"y" * 5
    length = len(payload)
    header = bytes([0x81, 127, 0, 0, 0, 0, 0, 0, 0, length])
    wrp = _make_wrp([header + payload])
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == "yyyyy"


def test_receive_response_extended_length_127_top_bit_set_raises() -> None:  # noqa: D103
    header = bytes([0x81, 127, 0x80, 0, 0, 0, 0, 0, 0, 5])
    payload = b"hello"
    wrp = _make_wrp([header + payload])
    with pytest.raises(IOError, match="Invalid payload length"):
        wrp.receiveResponse_()


def test_receive_response_extended_length_126_eof_raises() -> None:  # noqa: D103
    header = bytes([0x81, 126])
    wrp = _make_wrp([header, b""])
    with pytest.raises(IOError, match="Unexpected end of stream"):
        wrp.receiveResponse_()


def test_receive_response_extended_length_127_eof_raises() -> None:  # noqa: D103
    header = bytes([0x81, 127])
    wrp = _make_wrp([header, b""])
    with pytest.raises(IOError, match="Unexpected end of stream"):
        wrp.receiveResponse_()


def test_receive_response_payload_eof_raises() -> None:  # noqa: D103
    header = bytes([0x81, 10])
    wrp = _make_wrp([header, b""])
    with pytest.raises(IOError, match="Unexpected end of stream"):
        wrp.receiveResponse_()


def test_receive_response_pong_frame_returns_true_empty_result() -> None:  # noqa: D103
    header = bytes([0x8A, 0])
    wrp = _make_wrp([header])
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == ""


def test_receive_response_invalid_opcode_raises() -> None:  # noqa: D103
    header = bytes([0x82, 0])
    wrp = _make_wrp([header])
    with pytest.raises((IOError, TypeError)):
        wrp.receiveResponse_()


def test_receive_response_text_frame_chunked_recv() -> None:  # noqa: D103
    payload = b"abc"
    header = bytes([0x81, len(payload)])
    wrp = Wrp_()
    wrp.inData_ = bytearray()
    wrp.inDataBytes_ = 0
    wrp.result__ = None
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [header[:1], header[1:] + payload[:1], payload[1:]]
    wrp.socket_ = mock_socket
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == "abc"


def test_receive_response_empty_text_frame() -> None:  # noqa: D103
    header = bytes([0x81, 0])
    wrp = _make_wrp([header])
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == ""


def test_receive_response_text_frame_125_byte_max_small() -> None:  # noqa: D103
    payload = b"z" * 125
    header = bytes([0x81, 125])
    wrp = _make_wrp([header + payload])
    result = wrp.receiveResponse_()
    assert result is True
    assert wrp.result__ == "z" * 125


def test_receive_response_extended_length_127_bytes_1_to_3_nonzero_raises() -> None:  # noqa: D103
    header = bytes([0x81, 127, 0, 0x01, 0, 0, 0, 0, 0, 5])
    payload = b"hello"
    wrp = _make_wrp([header + payload])
    with pytest.raises(IOError, match="Invalid payload length"):
        wrp.receiveResponse_()
