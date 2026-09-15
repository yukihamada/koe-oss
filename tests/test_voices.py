import pytest

from koe_oss.core.voices import (
    Voice,
    VoiceRegistry,
    ConsentRecord,
    consent_state,
    normalize_handle,
    delete_targets,
    CONSENT_VERSION,
    NONE,
    CURRENT,
    STALE,
)


def test_handle_is_normalized():
    v = Voice(handle="Yuki Hamada!", ref_audio="/tmp/a.wav", ref_text="あ")
    assert v.handle == "yukihamada"


def test_handle_must_be_usable():
    with pytest.raises(ValueError):
        Voice(handle="!!!", ref_audio="/tmp/a.wav", ref_text="あ")


def test_ref_audio_required():
    with pytest.raises(ValueError):
        Voice(handle="a", ref_audio="", ref_text="あ")


def test_empty_ref_text_allowed():
    """Engines with speaker-embedding-only mode need no transcript."""
    v = Voice(handle="a", ref_audio="/tmp/a.wav", ref_text="")
    assert v.ref_text == ""


def test_consent_state_none_without_record():
    assert consent_state(None) == NONE


def test_consent_current_requires_age_ok():
    assert consent_state(ConsentRecord(age_ok=False)) == STALE
    assert consent_state(ConsentRecord(age_ok=True)) == CURRENT


def test_old_version_is_stale():
    assert consent_state(ConsentRecord(version="2020-01-01", age_ok=True)) == STALE


def test_revoked_counts_as_none():
    r = ConsentRecord(age_ok=True, revoked_at=1.0)
    assert consent_state(r) == NONE


def test_grant_then_revoke():
    reg = VoiceRegistry()
    reg.add(Voice(handle="yuki", ref_audio="/tmp/a.wav", ref_text="あ"))
    reg.grant_consent("yuki", age_ok=True)
    assert reg.get("yuki").consent_state == CURRENT
    reg.revoke_consent("yuki")
    assert reg.get("yuki").consent_state == NONE
    assert reg.get("yuki").usable() is False


def test_stale_voice_is_still_usable():
    reg = VoiceRegistry()
    reg.add(Voice(handle="yuki", ref_audio="/tmp/a.wav", ref_text="あ"))
    reg.get("yuki").consent = ConsentRecord(version="2020-01-01", age_ok=True)
    assert reg.get("yuki").usable() is True


def test_registry_roundtrip():
    reg = VoiceRegistry()
    reg.add(Voice(handle="yuki", ref_audio="/tmp/a.wav", ref_text="あ"))
    reg.grant_consent("yuki", age_ok=True)
    reg2 = VoiceRegistry.from_dict(reg.to_dict())
    assert reg2.get("yuki").consent_state == CURRENT


def test_unknown_voice_raises():
    reg = VoiceRegistry()
    with pytest.raises(KeyError):
        reg.require("nope")


def test_delete_targets_are_deterministic():
    a = delete_targets("Yuki")
    b = delete_targets("yuki")
    assert a == b
    assert "voices/yuki.json" in a["keys"]
    assert "audio/yuki/" in a["prefixes"]


def test_delete_targets_empty_handle():
    assert delete_targets("!!!") == {"keys": [], "prefixes": []}


def test_normalize_handle_caps_length():
    assert len(normalize_handle("a" * 100)) == 40


def test_voice_to_dict_includes_consent_state():
    v = Voice(handle="a", ref_audio="/tmp/a.wav", ref_text="あ")
    assert v.to_dict()["consent_state"] == NONE
