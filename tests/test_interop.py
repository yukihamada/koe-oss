"""The hosted service and KOE OSS must agree on the shape of a voice.

If these tests break, a voice registered in one will not read correctly in the
other — which is exactly the class of bug this module exists to prevent.
"""

import json

import pytest

from koe_oss.core.interop import (
    CONSENT_VERSION,
    SCHEMA_VERSION,
    consent_key,
    consent_record,
    consent_state,
    export_readings,
    normalize_handle,
    parse_consent,
    reading_record,
    voice_keys,
    voice_record,
)
from koe_oss.core.readings import ReadingDictionary
from koe_oss.core.voices import ConsentRecord, Voice, VoiceRegistry

# The R2 layout used by koe-edge/src/index.js and src/consent.js.
HOSTED_KEYS = {
    "ref_audio": "voiceprint/yuki.wav",
    "consent": "consent/yuki",
    "profile": "profile/yuki.json",
    "speaker": "speakervec/yuki.json",
}


def test_keys_match_hosted_layout():
    assert voice_keys("yuki") == HOSTED_KEYS


def test_consent_key_matches_hosted():
    assert consent_key("yuki") == "consent/yuki"


def test_handle_normalization_matches_hosted():
    """Hosted service lowercases and strips to [a-z0-9_]."""
    assert normalize_handle("Yuki Hamada!") == "yukihamada"
    assert normalize_handle("yuki") == "yuki"


def test_consent_record_uses_hosted_field_names():
    r = consent_record(age_ok=True)
    assert r["consent_version"] == CONSENT_VERSION
    assert "consent_at" in r
    assert r["consent_by"] == "self"
    assert r["age_ok"] is True


def test_parse_consent_accepts_hosted_shape():
    """A record written by koe-edge/src/consent.js must parse here."""
    hosted = {
        "consent_version": CONSENT_VERSION,
        "consent_text": "…",
        "consent_at": 1757900000.0,
        "age_ok": True,
        "consent_by": "self",
    }
    rec = parse_consent(hosted)
    assert rec is not None
    assert rec["version"] == CONSENT_VERSION
    assert rec["age_ok"] is True
    assert consent_state(hosted) == "current"


def test_parse_consent_accepts_local_shape():
    local = consent_record(age_ok=True)
    assert consent_state(local) == "current"


def test_old_hosted_record_is_stale_not_missing():
    """An old record must read as 'stale', never as 'no consent'."""
    old = {"consent_version": "2020-01-01", "age_ok": True}
    assert consent_state(old) == "stale"


def test_revoked_reads_as_none():
    r = consent_record(age_ok=True, revoked_at=1.0)
    assert consent_state(r) == "none"


def test_garbage_reads_as_none():
    for bad in [None, "x", 42, {}, {"age_ok": True}]:
        assert consent_state(bad) == "none"


def test_local_voice_serializes_to_hosted_compatible_dict():
    v = Voice(handle="yuki", ref_audio="/tmp/a.wav", ref_text="あ", lang="ja")
    d = v.to_dict()
    assert d["handle"] == "yuki"
    assert set(["handle", "ref_audio", "ref_text", "lang"]) <= set(d)


def test_voice_roundtrip_through_registry():
    reg = VoiceRegistry()
    reg.add(Voice(handle="yuki", ref_audio="/tmp/a.wav", ref_text="あ"))
    reg.grant_consent("yuki", age_ok=True)
    reg2 = VoiceRegistry.from_dict(reg.to_dict())
    assert reg2.get("yuki").consent_state == "current"


def test_reading_export_shape():
    d = ReadingDictionary()
    d.set_reading("弟子屈", "テシカガ")
    d.propose("市場", "イチバ")
    out = export_readings([e.to_dict() for e in d.entries()])
    assert {e["word"]: e["state"] for e in out} == {
        "弟子屈": "confirmed", "市場": "proposed"}
    assert all(e["schema"] == SCHEMA_VERSION for e in out)


def test_reading_record_defaults():
    r = reading_record(word="x", reading="y")
    assert r["state"] == "confirmed"
    assert r["lang"] == "ja"


def test_records_are_json_serializable():
    """Everything must survive a JSON round-trip — that is how it travels."""
    for obj in [
        voice_record(handle="yuki", ref_audio="/tmp/a.wav"),
        consent_record(age_ok=True),
        reading_record(word="x", reading="y"),
        voice_keys("yuki"),
    ]:
        assert json.loads(json.dumps(obj)) == obj


def test_schema_version_present_everywhere():
    for obj in [
        voice_record(handle="y", ref_audio="/a"),
        consent_record(),
        reading_record(word="x", reading="y"),
    ]:
        assert obj["schema"] == SCHEMA_VERSION


def test_consent_version_matches_local_implementation():
    """koe_oss.core.voices and interop must not drift."""
    from koe_oss.core import voices as v

    assert v.CONSENT_VERSION == CONSENT_VERSION


def test_local_and_interop_consent_agree():
    """Same record, two implementations, same verdict."""
    raw = consent_record(age_ok=True)
    from koe_oss.core.voices import consent_state as local_state

    assert local_state(ConsentRecord.from_dict({
        "version": raw["consent_version"],
        "age_ok": raw["age_ok"],
        "revoked_at": raw["revoked_at"],
    })) == consent_state(raw)
