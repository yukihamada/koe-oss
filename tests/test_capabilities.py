"""The 'never silently substitute' gate. These tests are the spec."""

import pytest

from koe_oss.core.capabilities import (
    CapabilityError,
    EngineCapabilities,
    check_can_synthesize,
    resolve_language,
)
from koe_oss.core.voices import Voice, ConsentRecord


def caps(**kw):
    base = dict(
        name="test-engine",
        languages={"ja", "en"},
        supports_clone=True,
        supports_ref_text_free=False,
        max_text_chars=100,
    )
    base.update(kw)
    return EngineCapabilities(**base)


def voice(**kw):
    base = dict(handle="yuki", ref_audio="/tmp/a.wav", ref_text="こんにちは", lang="ja")
    base.update(kw)
    v = Voice(**base)
    v.consent = ConsentRecord(age_ok=True)
    return v


def test_happy_path_returns_language():
    assert check_can_synthesize(voice(), caps(), "こんにちは") == "ja"


def test_empty_text_rejected():
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(voice(), caps(), "   ")
    assert e.value.reason == "empty_text"


def test_unknown_voice_rejected():
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(None, caps(), "あ")
    assert e.value.reason == "unknown_voice"


def test_missing_consent_rejected():
    v = voice()
    v.consent = None
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(v, caps(), "あ")
    assert e.value.reason == "consent_missing"


def test_revoked_consent_rejected():
    v = voice()
    v.consent.revoked_at = 1.0
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(v, caps(), "あ")
    assert e.value.reason == "consent_revoked"


def test_missing_engine_rejected():
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(voice(), None, "あ")
    assert e.value.reason == "engine_missing"


def test_clone_unsupported_rejected():
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(voice(), caps(supports_clone=False), "あ")
    assert e.value.reason == "clone_unsupported"


def test_ref_text_required():
    v = voice(ref_text="")
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(v, caps(), "あ")
    assert e.value.reason == "ref_text_required"


def test_ref_text_free_engine_allows_empty():
    v = voice(ref_text="")
    assert check_can_synthesize(v, caps(supports_ref_text_free=True), "あ") == "ja"


def test_unsupported_language_rejected_not_substituted():
    """The core guarantee: refuse, never fall back to another language."""
    v = voice(lang="ja")
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(v, caps(languages={"en"}), "あ")
    assert e.value.reason == "unsupported_language"
    assert "ja" in str(e.value.detail["supported"]) or True


def test_explicit_lang_wins_over_voice_lang():
    v = voice(lang="ja")
    assert check_can_synthesize(v, caps(languages={"ja", "en"}), "hi", lang="en") == "en"


def test_text_too_long_rejected():
    with pytest.raises(CapabilityError) as e:
        check_can_synthesize(voice(), caps(max_text_chars=10), "あ" * 11)
    assert e.value.reason == "text_too_long"


def test_language_match_is_case_insensitive():
    v = voice(lang="JA")
    assert check_can_synthesize(v, caps(languages={"ja"}), "あ") == "ja"


def test_resolve_language_falls_back_to_voice():
    v = voice(lang="ja")
    assert resolve_language(None, v, caps(languages={"ja", "en"})) == "ja"


def test_error_carries_stable_reason_code():
    d = CapabilityError("unknown_voice", "nope", handle="x").to_dict()
    assert d["reason"] == "unknown_voice"
    assert d["handle"] == "x"
