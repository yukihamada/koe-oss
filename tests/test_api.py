"""Black-box tests against the local HTTP API.

These are the contract the desktop app will be built against.
"""

import pytest
from fastapi.testclient import TestClient

from koe_oss.core.capabilities import EngineCapabilities
from koe_oss.engines.base import SynthEngine, SynthRequest, SynthResult


class FakeEngine(SynthEngine):
    """Engine that pretends to synthesize. Proves wiring, not audio quality."""

    def __init__(self, langs=("ja", "en")):
        self.langs = set(langs)
        self.calls = []

    def capabilities(self):
        return EngineCapabilities(
            name="fake", languages=self.langs,
            supports_clone=True, max_text_chars=1000,
        )

    def is_available(self):
        return True

    def synthesize(self, req: SynthRequest) -> SynthResult:
        import pathlib

        self.calls.append(req)
        p = pathlib.Path(req.out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"RIFFfake")
        return SynthResult(
            audio_path=str(p), sample_rate=24000,
            duration_sec=1.0, engine="fake", gen_sec=0.01,
        )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fresh on-disk state per test."""
    monkeypatch.setenv("KOE_DATA_DIR", str(tmp_path))
    from koe_oss.server import api

    api.STORE = None
    api._set_engine(FakeEngine())
    return TestClient(api.app)


def make_voice(client, handle="yuki", ref_text="こんにちは", lang="ja", ref="/tmp/a.wav"):
    r = client.post("/voices", json={
        "handle": handle, "ref_audio": ref, "ref_text": ref_text, "lang": lang})
    assert r.status_code == 201, r.text
    return r.json()["voice"]


def test_health(client):
    h = client.get("/health").json()
    assert h["ok"] is True
    assert h["engine"] == "fake"


# --------------------------------------------------------------------- voices
def test_create_and_list_voice(client):
    make_voice(client)
    assert len(client.get("/voices").json()["voices"]) == 1


def test_duplicate_voice_conflicts(client):
    make_voice(client)
    assert client.post(
        "/voices", json={"handle": "yuki", "ref_audio": "/tmp/b.wav"}).status_code == 409


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
    assert client.post("/voices/yuki/revoke").json()["voice"]["consent_state"] == "none"


def test_voices_persist_across_client(client, tmp_path, monkeypatch):
    """State must survive a process restart — that is what Store is for."""
    make_voice(client)
    client.post("/voices/yuki/consent", json={"age_ok": True})

    from koe_oss.server import api

    api.STORE = None  # force a reload from disk
    c2 = TestClient(api.app)
    v = c2.get("/voices/yuki").json()["voice"]
    assert v["consent_state"] == "current"


# ------------------------------------------------------------------- readings
def test_set_and_apply_reading(client):
    client.put("/readings/弟子屈", json={"word": "弟子屈", "reading": "テシカガ"})
    r = client.post("/readings/apply", json={"text": "弟子屈へ"})
    assert r.json()["text"] == "テシカガへ"
    assert r.json()["spans"][0]["word"] == "弟子屈"


def test_readings_persist(client):
    client.put("/readings/市場", json={"word": "市場", "reading": "イチバ"})
    from koe_oss.server import api

    api.STORE = None
    c2 = TestClient(api.app)
    assert c2.post("/readings/apply", json={"text": "市場"}).json()["text"] == "イチバ"


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
    client.post("/jobs/j1/state", json={"to": "checking"})
    r = client.post("/jobs/j1/state", json={"to": "completed"})
    assert r.json()["job"]["state"] == "completed"


def test_illegal_transition_409(client):
    client.post("/jobs", json={"id": "j1", "voice_id": "yuki"})
    assert client.post("/jobs/j1/state", json={"to": "completed"}).status_code == 409


def test_unknown_job_404(client):
    assert client.get("/jobs/nope").status_code == 404


def test_jobs_persist(client):
    client.post("/jobs", json={"id": "j1", "voice_id": "yuki"})
    from koe_oss.server import api

    api.STORE = None
    assert TestClient(api.app).get("/jobs/j1").status_code == 200


# ------------------------------------------------------------------ preflight
def test_preflight_ok(client):
    make_voice(client)
    client.post("/voices/yuki/consent", json={"age_ok": True})
    assert client.post("/preflight", json={"id": "x", "voice_id": "yuki"}).json()["ok"]


def test_preflight_refuses_unconsented_voice(client):
    make_voice(client)
    r = client.post("/preflight", json={"id": "x", "voice_id": "yuki"})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "consent_missing"


def test_preflight_refuses_unknown_voice(client):
    r = client.post("/preflight", json={"id": "x", "voice_id": "ghost"})
    assert r.json()["detail"]["reason"] == "unknown_voice"


# ----------------------------------------------------------------- synthesis
def test_synth_returns_audio_path(client, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref))
    client.post("/voices/yuki/consent", json={"age_ok": True})
    r = client.post("/synth", json={"voice_id": "yuki", "text": "こんにちは"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert (tmp_path / body["audio_path"]).exists() or body["audio_path"]


def test_synth_applies_reading_dictionary(client, tmp_path):
    """The dictionary must reach the engine, not just the /readings endpoint."""
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref))
    client.post("/voices/yuki/consent", json={"age_ok": True})
    client.put("/readings/弟子屈", json={"word": "弟子屈", "reading": "テシカガ"})

    from koe_oss.server import api

    eng = api._engine()
    r = client.post("/synth", json={"voice_id": "yuki", "text": "弟子屈へ"})
    assert r.status_code == 200, r.text
    assert r.json()["corrected"] is True
    assert eng.calls[-1].text == "テシカガへ"


def test_synth_refuses_unconsented_voice(client, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref))
    r = client.post("/synth", json={"voice_id": "yuki", "text": "こんにちは"})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "consent_missing"


def test_synth_refuses_missing_reference(client, tmp_path):
    make_voice(client, ref=str(tmp_path / "nope.wav"))
    client.post("/voices/yuki/consent", json={"age_ok": True})
    r = client.post("/synth", json={"voice_id": "yuki", "text": "こんにちは"})
    assert r.status_code == 400


def test_synth_refuses_unsupported_language(client, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref), lang="ja")
    client.post("/voices/yuki/consent", json={"age_ok": True})
    from koe_oss.server import api

    api._set_engine(FakeEngine(langs=("en",)))
    r = client.post("/synth", json={"voice_id": "yuki", "text": "こんにちは"})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "unsupported_language"


def test_synth_without_engine_503(client, tmp_path, monkeypatch):
    """No engine installed is a capability failure, reported before anything else."""
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref))
    client.post("/voices/yuki/consent", json={"age_ok": True})
    from koe_oss.server import api

    api._set_engine(None)
    r = client.post("/synth", json={"voice_id": "yuki", "text": "こんにちは"})
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "engine_missing"


# ------------------------------------------------------------------ pairing
def test_pair_start_returns_code(client):
    r = client.post("/pair/start", json={"label": "phone"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["code"]) == 6
    assert body["expires_in"] > 0


def test_redeem_exchanges_code_for_token(client):
    code = client.post("/pair/start", json={}).json()["code"]
    r = client.post("/pair/redeem", json={"code": code})
    assert r.status_code == 200
    assert len(r.json()["token"]) > 20


def test_redeem_bad_code_401(client):
    client.post("/pair/start", json={})
    assert client.post("/pair/redeem", json={"code": "zzzzzz"}).status_code == 401


def test_remote_synth_requires_token(client, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref))
    client.post("/voices/yuki/consent", json={"age_ok": True})
    r = client.post("/remote/synth", json={"voice_id": "yuki", "text": "こんにちは"})
    assert r.status_code == 401


def test_remote_synth_with_token(client, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref))
    client.post("/voices/yuki/consent", json={"age_ok": True})
    code = client.post("/pair/start", json={}).json()["code"]
    token = client.post("/pair/redeem", json={"code": code}).json()["token"]

    r = client.post(
        "/remote/synth",
        json={"voice_id": "yuki", "text": "こんにちは"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_remote_synth_bad_token_401(client, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref))
    client.post("/voices/yuki/consent", json={"age_ok": True})
    r = client.post(
        "/remote/synth",
        json={"voice_id": "yuki", "text": "こんにちは"},
        headers={"Authorization": "Bearer nope"},
    )
    assert r.status_code == 401


def test_revoke_disables_token(client, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    make_voice(client, ref=str(ref))
    client.post("/voices/yuki/consent", json={"age_ok": True})
    code = client.post("/pair/start", json={}).json()["code"]
    token = client.post("/pair/redeem", json={"code": code}).json()["token"]

    assert client.post("/pair/revoke", json={"token": token}).status_code == 200
    r = client.post(
        "/remote/synth",
        json={"voice_id": "yuki", "text": "こんにちは"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


def test_revoke_all(client):
    client.post("/pair/start", json={})
    client.post("/pair/start", json={})
    assert client.post("/pair/revoke-all").json()["revoked"] == 2
    assert client.get("/pair/active").json()["pairings"] == []


def test_pairing_is_off_by_default(client):
    """No pairing started means no remote access — the default must be closed."""
    assert client.get("/pair/active").json()["pairings"] == []
