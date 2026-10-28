"""公開sentinelの契約を検証する"""

import copy
import pickle

import amivoice


def test_sentinel_singleton_valid_return_same_member() -> None:
    """コピーと直列化でも同一性を保つ"""
    # Given: 公開された既定値継承のsentinel
    sentinel = amivoice.USE_CLIENT_DEFAULT
    # When: コピーと直列化を行う
    # 自分で生成したEnumのバイト列のみを復元し、外部入力は扱わない
    # nosemgrep: python.lang.security.deserialization.pickle.avoid-pickle
    copies = (copy.copy(sentinel), copy.deepcopy(sentinel), pickle.loads(pickle.dumps(sentinel)))
    # Then: すべて同じEnumメンバーを返す
    assert all(value is sentinel for value in copies)
    assert isinstance(sentinel, amivoice.UseClientDefault)
    assert repr(sentinel) == "USE_CLIENT_DEFAULT"
