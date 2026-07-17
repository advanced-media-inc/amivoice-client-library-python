# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false, reportAny=false, reportUnknownArgumentType=false

from collections.abc import Sequence
from unittest.mock import MagicMock

import pytest

from com.amivoice.hrp.Hrp_ import Hrp_


def _make_hrp(recv_chunks: Sequence[bytes]) -> Hrp_:
    hrp = Hrp_()
    hrp.inData_ = bytearray()
    hrp.inDataBytes_ = 0
    hrp.inDataBytes__ = 0
    hrp.inDataEncoding__ = None
    hrp.result__ = ""
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = list(recv_chunks)
    hrp.socket_ = mock_socket
    return hrp


_VALID_HEADER = b"HTTP/1.1 200 OK\r\nX-Session-ID: sess123\r\nTransfer-Encoding: chunked\r\n\r\n"

_HEADER_WITH_CONTENT_LENGTH = b"HTTP/1.1 200 OK\r\nX-Session-ID: sess123\r\nContent-Length: 10\r\n\r\n"

_HEADER_NON_200 = b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n"

_HEADER_MISSING_SESSION_ID = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"

_HEADER_SHIFT_JIS = (
    b"HTTP/1.1 200 OK\r\n"
    b"X-Session-ID: sess456\r\n"
    b"Content-Type: text/plain; charset=SHIFT_JIS\r\n"
    b"Transfer-Encoding: chunked\r\n\r\n"
)

_HEADER_INVALID_CONTENT_LENGTH = b"HTTP/1.1 200 OK\r\nX-Session-ID: sess123\r\nContent-Length: abc\r\n\r\n"


def test_receive_response_header_valid_returns_session_id() -> None:  # noqa: D103
    hrp = _make_hrp([_VALID_HEADER])
    session_id = hrp.receiveResponseHeader_()
    assert session_id == "sess123"


def test_receive_response_header_sets_utf8_encoding_by_default() -> None:  # noqa: D103
    hrp = _make_hrp([_VALID_HEADER])
    hrp.receiveResponseHeader_()
    assert hrp.inDataEncoding__ == "UTF-8"


def test_receive_response_header_parses_content_length() -> None:  # noqa: D103
    hrp = _make_hrp([_HEADER_WITH_CONTENT_LENGTH])
    hrp.receiveResponseHeader_()
    assert hrp.inDataBytes__ == 10


def test_receive_response_header_non_200_raises() -> None:  # noqa: D103
    hrp = _make_hrp([_HEADER_NON_200])
    with pytest.raises(IOError, match="Invalid response code"):
        hrp.receiveResponseHeader_()


def test_receive_response_header_missing_session_id_raises() -> None:  # noqa: D103
    hrp = _make_hrp([_HEADER_MISSING_SESSION_ID])
    with pytest.raises(IOError, match="Missing session id"):
        hrp.receiveResponseHeader_()


def test_receive_response_header_eof_raises() -> None:  # noqa: D103
    hrp = _make_hrp([b""])
    with pytest.raises(IOError, match="Unexpected end of stream"):
        hrp.receiveResponseHeader_()


def test_receive_response_header_shift_jis_charset_maps_to_ms932() -> None:  # noqa: D103
    hrp = _make_hrp([_HEADER_SHIFT_JIS])
    session_id = hrp.receiveResponseHeader_()
    assert session_id == "sess456"
    assert hrp.inDataEncoding__ == "MS932"


def test_receive_response_header_invalid_content_length_raises() -> None:  # noqa: D103
    hrp = _make_hrp([_HEADER_INVALID_CONTENT_LENGTH])
    with pytest.raises(IOError, match="Invalid content length: abc"):
        hrp.receiveResponseHeader_()


def test_receive_response_header_custom_charset_preserved() -> None:  # noqa: D103
    header = (
        b"HTTP/1.1 200 OK\r\n"
        b"X-Session-ID: sess789\r\n"
        b"Content-Type: text/plain; charset=EUC-JP\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
    )
    hrp = _make_hrp([header])
    hrp.receiveResponseHeader_()
    assert hrp.inDataEncoding__ == "EUC-JP"


def test_receive_response_header_clears_indata_after_parsing() -> None:  # noqa: D103
    hrp = _make_hrp([_VALID_HEADER])
    hrp.receiveResponseHeader_()
    assert hrp.inDataBytes_ == 0


def test_receive_chunked_response_body_returns_true_on_data_chunk() -> None:  # noqa: D103
    chunk = b"5\r\nhello\r\n"
    hrp = _make_hrp([chunk])
    hrp.inDataEncoding__ = "UTF-8"
    result = hrp.receiveChunkedResponseBody_()
    assert result is True
    assert "hello" in hrp.result__


def test_receive_chunked_response_body_returns_false_on_terminal_chunk() -> None:  # noqa: D103
    chunk = b"0\r\n\r\n"
    hrp = _make_hrp([chunk])
    hrp.inDataEncoding__ = "UTF-8"
    result = hrp.receiveChunkedResponseBody_()
    assert result is False


def test_receive_chunked_response_body_eof_raises() -> None:  # noqa: D103
    hrp = _make_hrp([b""])
    hrp.inDataEncoding__ = "UTF-8"
    with pytest.raises(IOError, match="Unexpected end of stream"):
        hrp.receiveChunkedResponseBody_()


def test_receive_chunked_response_body_uppercase_hex() -> None:  # noqa: D103
    chunk = b"A\r\n" + b"x" * 10 + b"\r\n"
    hrp = _make_hrp([chunk])
    hrp.inDataEncoding__ = "UTF-8"
    result = hrp.receiveChunkedResponseBody_()
    assert result is True
    assert hrp.result__ == "x" * 10


def test_receive_chunked_response_body_lowercase_hex() -> None:  # noqa: D103
    chunk = b"a\r\n" + b"y" * 10 + b"\r\n"
    hrp = _make_hrp([chunk])
    hrp.inDataEncoding__ = "UTF-8"
    result = hrp.receiveChunkedResponseBody_()
    assert result is True
    assert hrp.result__ == "y" * 10


def test_receive_chunked_response_body_payload_eof_raises() -> None:  # noqa: D103
    hrp = _make_hrp([b"5\r\n", b""])
    hrp.inDataEncoding__ = "UTF-8"
    with pytest.raises(IOError, match="Unexpected end of stream"):
        hrp.receiveChunkedResponseBody_()


def test_receive_chunked_response_body_terminal_chunk_eof_raises() -> None:  # noqa: D103
    hrp = _make_hrp([b"0\r\n", b""])
    hrp.inDataEncoding__ = "UTF-8"
    with pytest.raises(IOError, match="Unexpected end of stream"):
        hrp.receiveChunkedResponseBody_()


def test_receive_chunked_response_body_accumulates_result() -> None:  # noqa: D103
    chunk1 = b"3\r\nabc\r\n"
    chunk2 = b"3\r\ndef\r\n"
    hrp = _make_hrp([chunk1])
    hrp.inDataEncoding__ = "UTF-8"
    hrp.receiveChunkedResponseBody_()

    mock_socket2 = MagicMock()
    mock_socket2.recv.side_effect = [chunk2]
    hrp.socket_ = mock_socket2
    hrp.receiveChunkedResponseBody_()

    assert hrp.result__ == "abcdef"


def test_receive_response_body_reads_exact_bytes() -> None:  # noqa: D103
    hrp = _make_hrp([b"hello"])
    hrp.inDataBytes__ = 5
    hrp.inDataEncoding__ = "UTF-8"
    hrp.receiveResponseBody_()
    assert hrp.result__ == "hello"


def test_receive_response_body_eof_raises() -> None:  # noqa: D103
    hrp = _make_hrp([b""])
    hrp.inDataBytes__ = 5
    hrp.inDataEncoding__ = "UTF-8"
    with pytest.raises(IOError, match="Unexpected end of stream"):
        hrp.receiveResponseBody_()
