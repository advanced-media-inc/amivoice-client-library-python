# pyright: reportMissingImports=false, reportImplicitRelativeImport=false, reportAttributeAccessIssue=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

"""client モジュールのユニットテスト。

このファイルでは AmiVoiceClient クラスの基本動作を確認する。
"""

import pytest

from amivoice._stream import StreamConnectionManager
from amivoice.client import AmiVoiceClient
from amivoice.exceptions import AuthenticationError


def test_AmiVoiceClient_is_a_real_class() -> None:
    """AmiVoiceClient が実クラス（ファクトリではない）であることを確認する。"""
    # Given / When
    client = AmiVoiceClient(api_key="test-api-key")

    # Then: AmiVoiceClient のインスタンスが返る
    assert isinstance(client, AmiVoiceClient)


def test_AmiVoiceClient_has_transcribe_method() -> None:
    """AmiVoiceClient が transcribe メソッドを持つことを確認する。"""
    client = AmiVoiceClient(api_key="test-api-key")
    assert callable(client.transcribe)


def test_AmiVoiceClient_has_stream_method() -> None:
    """AmiVoiceClient が stream メソッドを持つことを確認する。"""
    client = AmiVoiceClient(api_key="test-api-key")
    assert callable(client.stream)


def test_AmiVoiceClient_stream_returns_connection_manager() -> None:
    """stream() が StreamConnectionManager を返すことを確認する。"""
    client = AmiVoiceClient(api_key="test-api-key")
    manager = client.stream()
    assert isinstance(manager, StreamConnectionManager)


def test_AmiVoiceClient_no_api_key_raises_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """api_key も環境変数も未設定のとき AuthenticationError が送出されることを確認する。"""
    monkeypatch.delenv("AMIVOICE_API_KEY", raising=False)

    with pytest.raises(AuthenticationError):
        AmiVoiceClient()
