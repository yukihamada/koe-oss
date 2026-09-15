"""Pairing is the one place we expose the voice beyond the machine, so it gets
tested hard: expiry, single-use codes, revocation, and auth failures.
"""

import time

import pytest

from koe_oss.core.pairing import (
    DEFAULT_TTL_SEC,
    Pairing,
    PairingStore,
    require_token,
)


@pytest.fixture()
def store(tmp_path):
    return PairingStore(tmp_path / "pairings.json")


def test_start_returns_code_and_keeps_token_secret(store):
    p = store.start()
    assert len(p.code) == 6
    assert len(p.token) > 20
    # The code is what a human types; the token must not be derivable from it.
    assert p.code not in p.token


def test_redeem_exchanges_code_for_token(store):
    p = store.start()
    got = store.redeem(p.code)
    assert got is not None and got.token == p.token


def test_redeem_is_case_insensitive(store):
    p = store.start()
    assert store.redeem(p.code.upper()) is not None


def test_redeem_wrong_code_fails(store):
    store.start()
    assert store.redeem("zzzzzz") is None


def test_redeem_empty_code_fails(store):
    store.start()
    assert store.redeem("") is None


def test_expired_pairing_is_rejected(store):
    p = store.start(ttl=0)
    assert store.by_token(p.token) is None
    assert store.redeem(p.code) is None


def test_expired_pairings_are_pruned(store):
    store.start(ttl=0)
    store.start(ttl=DEFAULT_TTL_SEC)
    assert len(store.active()) == 1


def test_revoke_kills_token(store):
    p = store.start()
    assert store.revoke(p.token) is True
    assert store.by_token(p.token) is None


def test_revoke_unknown_returns_false(store):
    assert store.revoke("nope") is False


def test_revoke_all(store):
    store.start()
    store.start()
    assert store.revoke_all() == 2
    assert store.active() == []


def test_touch_records_use(store):
    p = store.start()
    store.touch(p.token)
    assert store.by_token(p.token).use_count == 1
    assert store.by_token(p.token).last_used_at is not None


def test_persists_across_restart(tmp_path):
    s1 = PairingStore(tmp_path / "p.json")
    p = s1.start()
    s2 = PairingStore(tmp_path / "p.json")
    assert s2.by_token(p.token) is not None


def test_expired_not_reloaded(tmp_path):
    s1 = PairingStore(tmp_path / "p.json")
    p = s1.start(ttl=0)
    s2 = PairingStore(tmp_path / "p.json")
    assert s2.by_token(p.token) is None


def test_corrupt_file_starts_clean(tmp_path):
    (tmp_path / "p.json").write_text("{not json")
    s = PairingStore(tmp_path / "p.json")
    assert s.active() == []


def test_require_token_accepts_valid(store):
    p = store.start()
    assert require_token(store, f"Bearer {p.token}").token == p.token


def test_require_token_rejects_missing(store):
    with pytest.raises(ValueError):
        require_token(store, None)


def test_require_token_rejects_wrong_scheme(store):
    p = store.start()
    with pytest.raises(ValueError):
        require_token(store, f"Basic {p.token}")


def test_require_token_rejects_bad_token(store):
    with pytest.raises(ValueError):
        require_token(store, "Bearer nope")


def test_require_token_rejects_expired(store):
    p = store.start(ttl=0)
    with pytest.raises(ValueError):
        require_token(store, f"Bearer {p.token}")


def test_codes_are_unique(store):
    codes = {store.start().code for _ in range(20)}
    assert len(codes) == 20


def test_pairing_roundtrip():
    p = Pairing(code="abc123", token="t", created_at=1.0, expires_at=2.0)
    assert Pairing.from_dict(p.to_dict()).code == "abc123"


def test_expiry_boundary():
    now = time.time()
    p = Pairing(code="a", token="t", created_at=now, expires_at=now)
    assert p.expired(now) is True
    assert p.expired(now - 0.001) is False
