# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUntypedBaseClass=false, reportUnknownMemberType=false, reportUnusedParameter=false, reportUnannotatedClassAttribute=false, reportPrivateUsage=false, reportAny=false
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from com.amivoice.hrp.Hrp import Hrp


class MockHrp(Hrp):  # noqa: D101
    _connected: bool
    _captured_header: dict[str, object] | None
    state_: int

    def __init__(self, connected: bool = False) -> None:  # noqa: D107
        super().__init__()
        self._connected = connected
        self._captured_header = None

    def isConnected_(self) -> bool:  # noqa: D102
        return self._connected

    def connect_(self, *args: object) -> None:  # noqa: D102
        del args

    def disconnect_(self) -> None:  # noqa: D102
        pass

    def sendRequestHeader_(  # noqa: D102, PLR0913
        self,
        domainId: str,
        codec: object,
        resultType: object,
        resultEncoding: object,
        serviceAuthorization: object,
        voiceDetection: object,
        acceptTopic: object,
        contentType: object,
        accept: object,
        request_type: str,
        dataBytes: int,
    ) -> None:
        del codec
        del resultType
        del resultEncoding
        del serviceAuthorization
        del voiceDetection
        del acceptTopic
        del contentType
        del accept
        if self._captured_header is not None:
            self._captured_header["domainId"] = domainId
            self._captured_header["type"] = request_type
            self._captured_header["dataBytes"] = dataBytes
        self.state_ = 2

    def sendRequestBody_(self, *args: object) -> None:  # noqa: D102
        del args

    def capture_request_header_into(self, captured: dict[str, object]) -> None:  # noqa: D102
        self._captured_header = captured


def _capture_feed_data_resume_request(hrp: MockHrp, feed_type: str | None, data_bytes: int) -> tuple[bool, dict[str, object]]:
    captured: dict[str, object] = {}
    hrp.capture_request_header_into(captured)
    result = hrp.feedDataResume(type=feed_type, dataBytes=data_bytes)
    return result, captured


def _configure_explicit_domain_id(hrp: MockHrp) -> None:
    hrp.setDomainId("custom=ready")
    hrp.setGrammarFileNames("ignored grammar")
    hrp.setMode("ignored mode")


def _configure_derived_domain_id(hrp: MockHrp) -> None:
    hrp.setGrammarFileNames("main grammar")
    hrp.setMode("test mode")
    hrp.setAuthorization("token value")


@pytest.mark.parametrize(
    ("result_data", "expected_method"),
    [
        ("partial...", "resultUpdated"),
        ('{"text":"partial..."}', "resultUpdated"),
        ('{"text":"final"}', "resultFinalized"),
    ],
    ids=["plain_ellipsis", "json_ellipsis", "final_result"],
)
def test_result_routing_calls_expected_listener_method(result_data: str, expected_method: str) -> None:  # noqa: D103
    hrp = MockHrp()
    listener = MagicMock()

    hrp.setListener(listener)
    hrp.onMessage_(result_data)

    getattr(listener, expected_method).assert_called_once_with(result_data)
    if expected_method == "resultUpdated":
        listener.resultFinalized.assert_not_called()
    else:
        listener.resultUpdated.assert_not_called()


@pytest.mark.parametrize(
    "result_data",
    ["partial...", '{"text":"partial..."}', '{"text":"final"}'],
    ids=["plain_ellipsis", "json_ellipsis", "final_result"],
)
def test_result_routing_handles_missing_listener(result_data: str) -> None:  # noqa: D103
    hrp = MockHrp()

    hrp.onMessage_(result_data)


@pytest.mark.parametrize(
    ("feed_type", "data_bytes", "expected_type"),
    [
        (None, 0, "mc"),
        ("s", 0, "sc"),
        ("m", 0, "mc"),
        ("mc", 0, "mc"),
        ("sc", 0, "sc"),
        ("s", 100, "s "),
        ("m", 100, "m "),
        ("mc", 100, "mc"),
    ],
    ids=[
        "none_zero",
        "single_chunked_zero",
        "multipart_zero",
        "multipart_chunked_zero",
        "single_chunked_literal_zero",
        "single_positive",
        "multipart_positive",
        "multipart_chunked_positive",
    ],
)
def test_feed_data_resume_normalizes_type(feed_type: str | None, data_bytes: int, expected_type: str) -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0

    result, captured = _capture_feed_data_resume_request(hrp, feed_type, data_bytes)

    assert result is True
    assert captured["type"] == expected_type
    assert captured["dataBytes"] == data_bytes


@pytest.mark.parametrize(
    ("configurer", "expected_domain_id"),
    [
        (_configure_explicit_domain_id, "custom=ready"),
        (
            _configure_derived_domain_id,
            "grammarFileNames=main%20grammar mode=test%20mode authorization=token%20value",
        ),
    ],
    ids=["explicit_domain_id", "derived_query_string"],
)
def test_feed_data_resume_builds_domain_id(configurer: Callable[[MockHrp], None], expected_domain_id: str) -> None:  # noqa: D103
    hrp = MockHrp(connected=True)
    hrp.state_ = 0
    configurer(hrp)

    result, captured = _capture_feed_data_resume_request(hrp, "mc", 0)

    assert result is True
    assert captured["domainId"] == expected_domain_id
    assert captured["type"] == "mc"
