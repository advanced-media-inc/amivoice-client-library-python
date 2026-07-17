# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false, reportAny=false, reportUnknownArgumentType=false

from unittest.mock import MagicMock

from com.amivoice.wrp.Wrp_ import Wrp_


def _make_wrp() -> Wrp_:
    wrp = Wrp_()
    wrp.socket_ = MagicMock()
    wrp.socket_.send.side_effect = len
    return wrp


def _sent_bytes(wrp: Wrp_) -> bytes:
    all_calls = wrp.socket_.send.call_args_list
    return b"".join(bytes(c.args[0]) for c in all_calls)


def test_send_request_small_payload_no_command() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"hello"
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[0] == 0x81
    assert sent[1] == len(data)
    assert sent[2:] == data


def test_send_request_small_payload_with_command() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"abc"
    wrp.sendRequest_(data, 0, len(data), 0x70)
    sent = _sent_bytes(wrp)
    assert sent[0] == 0x82
    total_len = 1 + len(data)
    assert sent[1] == total_len
    assert sent[2] == 0x70
    assert sent[3:] == data


def test_send_request_small_payload_max_125() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"x" * 125
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[1] == 125
    assert sent[2:] == data


def test_send_request_medium_payload_uses_126_encoding() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"y" * 200
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[1] == 126
    length = (sent[2] << 8) | sent[3]
    assert length == 200
    assert sent[4:] == data


def test_send_request_medium_payload_boundary_126() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"z" * 126
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[1] == 126
    length = (sent[2] << 8) | sent[3]
    assert length == 126


def test_send_request_medium_payload_boundary_65535() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"a" * 65535
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[1] == 126
    length = (sent[2] << 8) | sent[3]
    assert length == 65535


def test_send_request_large_payload_uses_127_encoding() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"b" * 65536
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[1] == 127
    assert sent[2] == 0
    assert sent[3] == 0
    assert sent[4] == 0
    assert sent[5] == 0
    length = (sent[6] << 24) | (sent[7] << 16) | (sent[8] << 8) | sent[9]
    assert length == 65536
    assert sent[10:] == data


def test_send_request_large_payload_with_command() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"c" * 65535
    wrp.sendRequest_(data, 0, len(data), 0x70)
    sent = _sent_bytes(wrp)
    assert sent[1] == 127
    total_len = 1 + len(data)
    length = (sent[6] << 24) | (sent[7] << 16) | (sent[8] << 8) | sent[9]
    assert length == total_len
    assert sent[10] == 0x70
    assert sent[11:] == data


def test_send_request_uses_data_offset() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"XXXhello"
    wrp.sendRequest_(data, 3, 5, 0)
    sent = _sent_bytes(wrp)
    assert sent[1] == 5
    assert sent[2:] == b"hello"


def test_send_request_grows_outdata_buffer_for_large_payload() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"d" * 10000
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[1] == 126
    length = (sent[2] << 8) | sent[3]
    assert length == 10000
    assert sent[4:] == data


def test_send_request_command_zero_produces_text_opcode() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"test"
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[0] & 0x0F == 0x01


def test_send_request_nonzero_command_produces_binary_opcode() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"test"
    wrp.sendRequest_(data, 0, len(data), 0x70)
    sent = _sent_bytes(wrp)
    assert sent[0] & 0x0F == 0x02


def test_send_request_fin_bit_always_set() -> None:  # noqa: D103
    wrp = _make_wrp()
    data = b"test"
    wrp.sendRequest_(data, 0, len(data), 0)
    sent = _sent_bytes(wrp)
    assert sent[0] & 0x80 == 0x80
