from unittest.mock import MagicMock

from com.amivoice.hrp.Hrp_ import Hrp_

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hrp(resource: str = "/asr", host: str = "example.com") -> Hrp_:
    hrp = Hrp_()
    hrp.socket_ = MagicMock()
    hrp.socket_.send.side_effect = len
    hrp.host_ = host
    hrp.resource_ = resource
    hrp.proxyUserName_ = None
    hrp.proxyPassword_ = None
    return hrp


def _sent_bytes(hrp: Hrp_) -> bytes:
    calls = hrp.socket_.send.call_args_list
    return b"".join(bytes(c.args[0]) for c in calls)


def _sent_str(hrp: Hrp_) -> str:
    return _sent_bytes(hrp).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# type="sn"  (query-string, Content-Length)
# ---------------------------------------------------------------------------


class TestQueryStringContentLength:  # noqa: D101
    def test_basic_post_line_and_http_version(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 100)
        s = _sent_str(hrp)
        assert s.startswith("POST /asr HTTP/1.1\r\n")

    def test_host_header(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 100)
        s = _sent_str(hrp)
        assert "Host: example.com\r\n" in s

    def test_content_length_header_present(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 999)
        s = _sent_str(hrp)
        assert "Content-Length: 999\r\n" in s

    def test_no_transfer_encoding_chunked(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 100)
        s = _sent_str(hrp)
        assert "Transfer-Encoding" not in s

    def test_requestBodyChunked_is_none(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 100)
        assert hrp.requestBodyChunked_ is None

    def test_requestBodyParted_is_none(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 100)
        assert hrp.requestBodyParted_ is None

    def test_ends_with_double_crlf(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 0)
        b = _sent_bytes(hrp)
        assert b.endswith(b"\r\n\r\n")

    def test_domainId_appended_as_query_param(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_("myDomain", None, None, None, None, None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?d=myDomain" in s or "&d=myDomain" in s

    def test_codec_appended_as_query_param(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, "16k", None, None, None, None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?c=16k" in s or "&c=16k" in s

    def test_resultType_appended_as_query_param(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, "json", None, None, None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?r=json" in s or "&r=json" in s

    def test_resultEncoding_appended_as_query_param(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, "utf-8", None, None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?e=utf-8" in s or "&e=utf-8" in s

    def test_serviceAuthorization_appended_as_query_param(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, "svcauth", None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?u=svcauth" in s or "&u=svcauth" in s

    def test_voiceDetection_appended_as_query_param(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, "on", None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?v=on" in s or "&v=on" in s

    def test_multiple_params_use_ampersand_delimiter(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_("dom", "pcm", None, None, None, None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?d=dom&c=pcm" in s

    def test_resource_already_has_query_uses_ampersand(self) -> None:  # noqa: D102
        hrp = _make_hrp(resource="/asr?existing=1")
        hrp.sendRequestHeader_("dom", None, None, None, None, None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?d=dom" not in s
        assert "&d=dom" in s

    def test_acceptTopic_header_added(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, "topic123", None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "Accept-Topic: topic123\r\n" in s

    def test_contentType_header_added(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, "audio/pcm", None, "sn", 0)
        s = _sent_str(hrp)
        assert "Content-Type: audio/pcm\r\n" in s

    def test_accept_header_added(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, "application/json", "sn", 0)
        s = _sent_str(hrp)
        assert "Accept: application/json\r\n" in s

    def test_proxy_authorization_header_added(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.proxyUserName_ = "user"
        hrp.proxyPassword_ = "pass"
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "Proxy-Authorization: Basic " in s

    def test_none_or_empty_params_not_appended(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_("", None, "", None, "", None, None, None, None, "sn", 0)
        s = _sent_str(hrp)
        assert "?" not in s.split(" HTTP/1.1")[0]


# ---------------------------------------------------------------------------
# type="sc"  (query-string, chunked)
# ---------------------------------------------------------------------------


class TestQueryStringChunked:  # noqa: D101
    def test_transfer_encoding_chunked_present(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sc", 0)
        s = _sent_str(hrp)
        assert "Transfer-Encoding: chunked\r\n" in s

    def test_no_content_length_header(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sc", 0)
        s = _sent_str(hrp)
        assert "Content-Length" not in s

    def test_requestBodyChunked_is_set(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sc", 0)
        assert hrp.requestBodyChunked_ == b"0\r\n\r\n"

    def test_requestBodyParted_is_none(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sc", 0)
        assert hrp.requestBodyParted_ is None

    def test_domainId_in_query_string(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_("dom", None, None, None, None, None, None, None, None, "sc", 0)
        s = _sent_str(hrp)
        assert "?d=dom" in s or "&d=dom" in s


# ---------------------------------------------------------------------------
# type="mn"  (multipart, Content-Length)
# ---------------------------------------------------------------------------


class TestMultipartContentLength:  # noqa: D101
    def test_requestBodyParted_is_set(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mn", 0)
        assert hrp.requestBodyParted_ is not None

    def test_requestBodyParted_ends_with_epilogue(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mn", 0)
        assert bytes(hrp.requestBodyParted_).endswith(b"\r\n--1234567890ABCDEFGHIJ--\r\n")

    def test_multipart_content_type_header(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mn", 0)
        s = _sent_str(hrp)
        assert "Content-Type: multipart/form-data; boundary=1234567890ABCDEFGHIJ\r\n" in s

    def test_content_length_includes_parted_size(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mn", 100)
        s = _sent_str(hrp)
        assert "Content-Length: " in s
        cl_start = s.index("Content-Length: ") + len("Content-Length: ")
        cl_end = s.index("\r\n", cl_start)
        cl_val = int(s[cl_start:cl_end])
        assert cl_val > 100

    def test_requestBodyChunked_is_none(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mn", 0)
        assert hrp.requestBodyChunked_ is None

    def test_no_query_params_in_post_line(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_("dom", "pcm", None, None, None, None, None, None, None, "mn", 0)
        s = _sent_str(hrp)
        first_line = s.split("\r\n")[0]
        assert "?d=" not in first_line
        assert "&c=" not in first_line

    def test_domainId_in_multipart_body(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_("myDomain", None, None, None, None, None, None, None, None, "mn", 0)
        parted = bytes(hrp.requestBodyParted_)
        assert b'name="d"' in parted
        assert b"myDomain" in parted

    def test_codec_in_multipart_body(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, "pcm16k", None, None, None, None, None, None, None, "mn", 0)
        parted = bytes(hrp.requestBodyParted_)
        assert b'name="c"' in parted
        assert b"pcm16k" in parted

    def test_resultType_in_multipart_body(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, "json", None, None, None, None, None, None, "mn", 0)
        parted = bytes(hrp.requestBodyParted_)
        assert b'name="r"' in parted
        assert b"json" in parted

    def test_resultEncoding_in_multipart_body(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, "utf-8", None, None, None, None, None, "mn", 0)
        parted = bytes(hrp.requestBodyParted_)
        assert b'name="e"' in parted
        assert b"utf-8" in parted

    def test_serviceAuthorization_in_multipart_body(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, "token123", None, None, None, None, "mn", 0)
        parted = bytes(hrp.requestBodyParted_)
        assert b'name="u"' in parted
        assert b"token123" in parted

    def test_voiceDetection_in_multipart_body(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, "on", None, None, None, "mn", 0)
        parted = bytes(hrp.requestBodyParted_)
        assert b'name="v"' in parted
        assert b"on" in parted

    def test_acceptTopic_NOT_added_when_parted(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, "topic", None, None, "mn", 0)
        s = _sent_str(hrp)
        assert "Accept-Topic:" not in s

    def test_contentType_NOT_overridden_by_user_when_parted(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, "audio/pcm", None, "mn", 0)
        s = _sent_str(hrp)
        assert "audio/pcm" not in s
        assert "multipart/form-data" in s

    def test_accept_NOT_added_when_parted(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, "app/json", "mn", 0)
        s = _sent_str(hrp)
        assert "Accept: app/json" not in s


# ---------------------------------------------------------------------------
# type="mc"  (multipart, chunked)
# ---------------------------------------------------------------------------


class TestMultipartChunked:  # noqa: D101
    def test_requestBodyParted_is_set(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mc", 0)
        assert hrp.requestBodyParted_ is not None

    def test_requestBodyChunked_is_set(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mc", 0)
        assert hrp.requestBodyChunked_ == b"0\r\n\r\n"

    def test_transfer_encoding_chunked_present(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mc", 0)
        s = _sent_str(hrp)
        assert "Transfer-Encoding: chunked\r\n" in s

    def test_multipart_content_type_header(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mc", 0)
        s = _sent_str(hrp)
        assert "Content-Type: multipart/form-data; boundary=1234567890ABCDEFGHIJ\r\n" in s

    def test_no_content_length(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mc", 0)
        s = _sent_str(hrp)
        assert "Content-Length" not in s


# ---------------------------------------------------------------------------
# State reset on repeated calls
# ---------------------------------------------------------------------------


class TestStateReset:  # noqa: D101
    def test_repeated_call_resets_requestBodyChunked(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sc", 0)
        assert hrp.requestBodyChunked_ is not None
        hrp.socket_.send.reset_mock()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 0)
        assert hrp.requestBodyChunked_ is None

    def test_repeated_call_resets_requestBodyParted(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "mn", 0)
        assert hrp.requestBodyParted_ is not None
        hrp.socket_.send.reset_mock()
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 0)
        assert hrp.requestBodyParted_ is None

    def test_inDataBytes_reset(self) -> None:  # noqa: D102
        hrp = _make_hrp()
        hrp.inDataBytes_ = 42
        hrp.sendRequestHeader_(None, None, None, None, None, None, None, None, None, "sn", 0)
        assert hrp.inDataBytes_ == 0
