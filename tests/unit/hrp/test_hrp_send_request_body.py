from unittest.mock import MagicMock

from com.amivoice.hrp.Hrp_ import Hrp_

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hrp() -> Hrp_:
    hrp = Hrp_()
    hrp.socket_ = MagicMock()
    hrp.socket_.send.side_effect = len
    hrp.requestBodyChunked_ = None
    hrp.requestBodyParted_ = None
    hrp.requestBodyPartedOffset_ = 0
    return hrp


def _sent_bytes(hrp: Hrp_) -> bytes:
    calls = hrp.socket_.send.call_args_list
    return b"".join(bytes(c.args[0]) for c in calls)


def _chunked_value() -> bytes:
    return b"0\r\n\r\n"


def _make_parted_with_field(field_name: bytes = b"d", value: bytes = b"test") -> bytearray:
    body = bytearray()
    body.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="')
    body.extend(field_name)
    body.extend(b'"\r\n\r\n')
    body.extend(value)
    body.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="a"\r\n\r\n')
    body.extend(b"\r\n--1234567890ABCDEFGHIJ--\r\n")
    return body


# ---------------------------------------------------------------------------
# Plain (no chunked, no parted)
# ---------------------------------------------------------------------------


class TestPlainSend:  # noqa: D101
    def test_data_sent_directly(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestBody_(b"hello", 0, 5)
        assert _sent_bytes(hrp) == b"hello"

    def test_data_offset_slicing(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestBody_(b"xyhello", 2, 5)
        assert _sent_bytes(hrp) == b"hello"

    def test_zero_dataBytes_sends_nothing(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestBody_(b"hello", 0, 0)
        hrp.socket_.send.assert_not_called()

    def test_none_data_sends_nothing_without_chunked_or_parted(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestBody_(None, 0, 0)
        hrp.socket_.send.assert_not_called()


# ---------------------------------------------------------------------------
# Chunked, no parted
# ---------------------------------------------------------------------------


class TestChunkedNoParted:  # noqa: D101
    def test_data_wrapped_with_chunk_size_and_crlf(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        data = b"hello"
        hrp.sendRequestBody_(data, 0, len(data))
        sent = _sent_bytes(hrp)
        assert sent == b"5\r\nhello\r\n"

    def test_data_offset_respected_in_chunked(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.sendRequestBody_(b"xyhello", 2, 5)
        sent = _sent_bytes(hrp)
        assert sent == b"5\r\nhello\r\n"

    def test_termination_sends_terminal_chunk(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.sendRequestBody_(None, 0, 0)
        assert _sent_bytes(hrp) == b"0\r\n\r\n"

    def test_termination_with_zero_databytes_sends_terminal_chunk(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.sendRequestBody_(b"ignored", 0, 0)
        assert _sent_bytes(hrp) == b"0\r\n\r\n"

    def test_chunk_size_hex_encoded(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        data = b"A" * 16
        hrp.sendRequestBody_(data, 0, len(data))
        sent = _sent_bytes(hrp)
        assert sent.startswith(b"10\r\n")

    def test_large_chunk_size_hex(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        data = b"B" * 255
        hrp.sendRequestBody_(data, 0, len(data))
        sent = _sent_bytes(hrp)
        assert sent.startswith(b"ff\r\n")
        assert sent.endswith(b"\r\n")
        assert data in sent


# ---------------------------------------------------------------------------
# Parted (multipart), no chunked — first call (offset=0)
# ---------------------------------------------------------------------------


class TestPartedNoChunkedFirstCall:  # noqa: D101
    def test_preamble_sent_before_data_on_first_call(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyParted_ = _make_parted_with_field()
        data = b"audiodata"
        hrp.sendRequestBody_(data, 0, len(data))
        sent = _sent_bytes(hrp)
        parted = bytes(hrp.requestBodyParted_)
        preamble = parted[: hrp.requestBodyPartedOffset_]
        assert sent.startswith(preamble)
        assert sent.endswith(data)

    def test_requestBodyPartedOffset_set_on_first_call(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyParted_ = _make_parted_with_field()
        expected_offset = len(hrp.requestBodyParted_) - 28
        hrp.sendRequestBody_(b"x", 0, 1)
        assert hrp.requestBodyPartedOffset_ == expected_offset

    def test_preamble_not_sent_on_second_call(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyParted_ = _make_parted_with_field()
        hrp.sendRequestBody_(b"first", 0, 5)
        hrp.socket_.send.reset_mock()
        hrp.sendRequestBody_(b"second", 0, 6)
        sent = _sent_bytes(hrp)
        assert sent == b"second"


# ---------------------------------------------------------------------------
# Parted (multipart), no chunked — termination
# ---------------------------------------------------------------------------


class TestPartedNoChunkedTermination:  # noqa: D101
    def test_epilogue_sent_on_termination(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyParted_ = _make_parted_with_field()
        hrp.requestBodyPartedOffset_ = len(hrp.requestBodyParted_) - 28
        hrp.sendRequestBody_(None, 0, 0)
        sent = _sent_bytes(hrp)
        parted = bytes(hrp.requestBodyParted_)
        epilogue = parted[hrp.requestBodyPartedOffset_ :]
        assert sent == epilogue

    def test_epilogue_ends_with_boundary_close(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyParted_ = _make_parted_with_field()
        hrp.requestBodyPartedOffset_ = len(hrp.requestBodyParted_) - 28
        hrp.sendRequestBody_(None, 0, 0)
        assert _sent_bytes(hrp).endswith(b"\r\n--1234567890ABCDEFGHIJ--\r\n")


# ---------------------------------------------------------------------------
# Parted + chunked — first call (offset=0)
# ---------------------------------------------------------------------------


class TestPartedChunkedFirstCall:  # noqa: D101
    def test_chunked_preamble_size_sent_before_preamble(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.requestBodyParted_ = _make_parted_with_field()
        expected_preamble_len = len(hrp.requestBodyParted_) - 28
        hrp.sendRequestBody_(b"audio", 0, 5)
        sent = _sent_bytes(hrp)
        hex_size = format(expected_preamble_len, "x").encode()
        assert hex_size in sent

    def test_data_chunk_size_present_after_preamble(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.requestBodyParted_ = _make_parted_with_field()
        hrp.sendRequestBody_(b"audio", 0, 5)
        sent = _sent_bytes(hrp)
        assert b"5\r\naudio\r\n" in sent

    def test_full_chunked_parted_first_send_structure(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.requestBodyParted_ = _make_parted_with_field()
        preamble_len = len(hrp.requestBodyParted_) - 28
        hrp.sendRequestBody_(b"audio", 0, 5)
        sent = _sent_bytes(hrp)
        preamble_hex = format(preamble_len, "x").encode()
        parted = bytes(hrp.requestBodyParted_)
        preamble = parted[:preamble_len]
        assert preamble_hex + b"\r\n" + preamble + b"\r\n" in sent


# ---------------------------------------------------------------------------
# Parted + chunked — termination
# ---------------------------------------------------------------------------


class TestPartedChunkedTermination:  # noqa: D101
    def test_chunked_epilogue_followed_by_terminal_chunk(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.requestBodyParted_ = _make_parted_with_field()
        hrp.requestBodyPartedOffset_ = len(hrp.requestBodyParted_) - 28
        hrp.sendRequestBody_(None, 0, 0)
        sent = _sent_bytes(hrp)
        assert sent.endswith(b"0\r\n\r\n")

    def test_epilogue_size_hex_present(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.requestBodyParted_ = _make_parted_with_field()
        hrp.requestBodyPartedOffset_ = len(hrp.requestBodyParted_) - 28
        epilogue_len = len(hrp.requestBodyParted_) - hrp.requestBodyPartedOffset_
        hrp.sendRequestBody_(None, 0, 0)
        sent = _sent_bytes(hrp)
        assert format(epilogue_len, "x").encode() in sent

    def test_epilogue_content_included(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.requestBodyChunked_ = _chunked_value()
        hrp.requestBodyParted_ = _make_parted_with_field()
        hrp.requestBodyPartedOffset_ = len(hrp.requestBodyParted_) - 28
        hrp.sendRequestBody_(None, 0, 0)
        sent = _sent_bytes(hrp)
        assert b"--1234567890ABCDEFGHIJ--" in sent
