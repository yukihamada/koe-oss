"""Black-box tests against the local HTTP API.

These are the contract the desktop app will be built against.
"""

import pytest
from fastapi.testclient import TestClient

from koe_oss.server import api
from koe_oss.core.capabilities import EngineCapabilities


@pytest.fixture()
def client():
    """Fresh state per test."""
    api.VOICES = api.VoiceRegistry()
    api.DICTIONARY = api.ReadingDictionary(lang="ja")
    api.JOBS = {}
    api._set_engine(
        EngineCapabilities(
            name="test-engine",
            languages={"ja", "en"},
            supports_clone=True,
            max_text_chars=1000,
        )
    )
    return TestClient(api.app)


def make_voice(client, handle="yuki", ref_text="こんにちは", lang="ja"):
    r = client.post(
        "/voices",
        json={"handle": handle, "ref_audio": "/tmp/a.wav", "ref_text": ref_text, "lang": lang},
    )
    assert r.status_code == 201, r.text
    return r.json()["voice"]


def test_health(client):
    assert client.get("/health").json()["ok"] is True


# --------------------------------------------------------------------- voices
def test_create_and_list_voice(client):
    make_voice(client)
    assert len(client.get("/voices").json()["voices"]) == 1


def test_duplicate_voice_conflicts(client):
    make_voice(client)
    r = client.post("/voices", json={"handle": "yuki", "ref_audio": "/tmp/b.wav"})
    assert r.status_code == 409


def test_unknown_voice_404(client):
    assert client.get("/voices/nope").status_code == 404


def test_delete_voice_reports_targets(client):
    make_voice(client)
    r = client.delete("/voices/yuki")
    assert r.status_code == 200
    assert "voices/yuki.json" in r.json()["targets"]["keys"]


def test_consent_gate(client):
    make_voice(client)
    r = client.post("/voices/yuki/consent", json={"age_ok": True})
    assert r.json()["voice"]["consent_state"] == "current"


def test_revoke_makes_voice_unusable(client):
    make_voice(client)
    client.post("/voices/yuki/consent", json={"age_ok": True})
    r = client.post("/voices/yuki/revoke")
    assert r.json()["voice"]["consent_state"] == "none"


# ------------------------------------------------------------------- readings
def test_set_and_apply_reading(client):
    client.put("/readings/弟子屈", json={"word": "弟子屈", "reading": "テシカガ"})
    r = client.post("/readings/apply", json={"text": "弟子屈へ"})
    assert r.json()["text"] == "テシカガへ"
    assert r.json()["spans"][0]["word"] == "弟子屈"


def test_confirm_flow(client):
    client.put("/readings/市場", json={"word": "市場", "reading": "イチバ"})
    client.post("/readings/市場/reject")
    assert client.post("/readings/apply", json={"text": "市場"}).json()["text"] == "市場"
    client.put("/readings/市場", json={"word": "市場", "reading": "イチバ"})
    client.post("/readings/市場/confirm")
    assert client.post("/readings/apply", json={"text": "市場"}).json()["text"] == "イチバ"


def test_unknown_reading_404(client):
    assert client.post("/readings/nope/confirm").status_code == 404


# --------------------------------------------------------------------- script
def test_split_endpoint(client):
    r = client.post("/script/split", json={"text": "一です。二です。", "max_chars": 20})
    assert r.json()["count"] == 2


# ----------------------------------------------------------------------- jobs
def test_job_lifecycle(client):
    make_voice(client)
    client.post("/voices/yuki/consent", json={"age_ok": True})
    client.post("/jobs", json={"id": "j1", "voice_id": "yuki"})
    client.post("/jobs/j1/state", json={"to": "preparing"})
    client.post("/jobs/j1/state", json={"to": "generating"})
    client.post("/jobs/j1/chunks/0")
    r = client.post("/jobs/j1/state", json={"to": "checking"})
    assert r.json()["job"]["state"] == "checking"
    r = client.post("/jobs/j1/state", json={"to": "completed"})
    assert r.json()["job"]["state"] == "completed"


def test_illegal_transition_409(client):
    client.post("/jobs", json={"id": "j1", "voice_id": "yuki"})
    r = client.post("/jobs/j1/state", json={"to": "completed"})
    assert r.status_code == 409


def test_duplicate_job_409(client):
    client.post("/jobs", json={"id": "j1", "voice_id": "yuki"})
    assert client.post("/jobs", json={"id": "j1", "voice_id": "yuki"}).status_code == 409


def test_unknown_job_404(client):
    assert client.get("/jobs/nope").status_code == 404


def test_cancel_job(client):
    client.post("/jobs", json={"id": "j1", "voice_id": "yuki"})
    r = client.post("/jobs/j1/cancel")
    assert r.json()["job"]["cancel_requested"] is True


# ------------------------------------------------------------------ preflight
def test_preflight_ok(client):
    make_voice(client)
    client.post("/voices/yuki/consent", json={"age_ok": True})
    r = client.post("/preflight", json={"id": "x", "voice_id": "yuki"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_preflight_refuses_unconsented_voice(client):
    make_voice(client)  # no consent granted
    r = client.post("/preflight", json={"id": "x", "voice_id": "yuki"})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "consent_missing"


def test_preflight_refuses_unknown_voice(client):
    r = client.post("/preflight", json={"id": "x", "voice_id": "ghost"})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "unknown_voice"


def test_preflight_refuses_unsupported_language(client):
    make_voice(client, lang="ja")
    client.post("/voices/yuki/consent", json={"age_ok": True})
    api._set_engine(
        EngineCapabilities(name="en-only", languages={"en"}, supports_clone=True)
    )
    r = client.post("/preflight", json={"id": "x", "voice_id": "yuki"})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "unsupported_language"
