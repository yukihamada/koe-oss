"""Local HTTP API.

Binds to 127.0.0.1 only. There is no authentication because there is no
network exposure; if you need remote access, put it behind your own tunnel
and your own auth — do not widen this bind.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..core.capabilities import (
    CapabilityError,
    EngineCapabilities,
    check_can_synthesize,
    preflight as check_preflight,
)
from ..core.jobs import Job, InvalidTransition
from ..core.readings import ReadingDictionary
from ..core.script import split_script
from ..core.store import Store
from ..core.voices import (
    Voice,
    VoiceRegistry,
    delete_targets,
)
from ..engines.base import EngineUnavailable, SynthRequest

app = FastAPI(title="KOE OSS", version="0.1.0")

# The desktop UI is served from a different origin than this API, so the
# browser needs CORS. Allowed origins are restricted to loopback only — this
# server is never meant to be reachable from the network.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1", "http://localhost",
        "http://127.0.0.1:8902", "http://localhost:8902",
        "tauri://localhost", "http://tauri.localhost",
    ],
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

STORE = Store(Path(os.environ["KOE_DATA_DIR"])) if os.environ.get("KOE_DATA_DIR") else None
_ENGINE = None


def _store() -> Store:
    """Lazily create the store so tests can point KOE_DATA_DIR at tmp_path."""
    global STORE
    if STORE is None:
        STORE = Store()
    return STORE


def _engine():
    """Return the configured engine, or None if none is installed."""
    return _ENGINE


def _set_engine(engine) -> None:
    global _ENGINE
    _ENGINE = engine


def autodetect_engine():
    """Pick the first engine that can actually run here.

    Called on server start so `uvicorn koe_oss.server.api:app` is enough —
    users should not have to wire the engine by hand.
    """
    try:
        from ..engines.mlx_qwen import MlxQwenEngine

        e = MlxQwenEngine()
        if e.is_available():
            return e
    except ImportError:
        pass
    return None


def _caps() -> Optional[EngineCapabilities]:
    e = _engine()
    return e.capabilities() if e is not None else None


def _voices() -> VoiceRegistry:
    return _store().load_voices()


def _readings() -> ReadingDictionary:
    return _store().load_readings()


def _jobs() -> Dict[str, Job]:
    return _store().load_jobs()


def _save_voices(reg: VoiceRegistry) -> None:
    _store().save_voices(reg)


def _save_readings(d: ReadingDictionary) -> None:
    _store().save_readings(d)


def _save_jobs(jobs: Dict[str, Job]) -> None:
    _store().save_jobs(jobs)


# --------------------------------------------------------------------- models
class VoiceIn(BaseModel):
    handle: str
    ref_audio: str
    ref_text: str = ""
    lang: str = "ja"
    engine: str = ""
    notes: str = ""


class ConsentIn(BaseModel):
    age_ok: bool = False
    consented_by: str = "self"
    operator: str = ""


class ReadingIn(BaseModel):
    word: str
    reading: str
    note: str = ""


class JobIn(BaseModel):
    id: str
    voice_id: str
    lang: Optional[str] = None


class TransitionIn(BaseModel):
    to: str
    error: Optional[str] = None


class SplitIn(BaseModel):
    text: str
    max_chars: int = 80


class ApplyIn(BaseModel):
    text: str


class SynthIn(BaseModel):
    voice_id: str
    text: str
    lang: Optional[str] = None
    out_path: Optional[str] = None


# ----------------------------------------------------------------- utilities
def _capability_http(exc: CapabilityError) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.to_dict())


# --------------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict:
    e = _engine()
    return {
        "ok": True,
        "voices": len(_voices()),
        "engine": e.capabilities().name if e is not None else None,
        "engine_available": bool(e is not None and e.is_available()),
        "jobs": len(_jobs()),
        "data_dir": str(_store().dir),
    }


# --- voices
@app.get("/voices")
def list_voices() -> dict:
    return {"voices": [v.to_dict() for v in _voices().all()]}


@app.post("/voices", status_code=201)
def create_voice(body: VoiceIn) -> dict:
    try:
        voice = Voice(
            handle=body.handle,
            ref_audio=body.ref_audio,
            ref_text=body.ref_text,
            lang=body.lang,
            engine=body.engine,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    reg = _voices()
    if voice.handle in reg:
        raise HTTPException(status_code=409, detail="voice already exists")

    # Copy the reference recording into the data dir when we can. If we only
    # stored the caller's path, revoking consent could not delete the
    # recording — the whole point of revocation — because it would live
    # somewhere we do not own. A missing file is not fatal at registration
    # time: the path is kept and synthesis will refuse later.
    try:
        voice.ref_audio = _store().import_ref_audio(
            voice.handle, body.ref_audio
        )
    except (FileNotFoundError, OSError, ValueError):
        pass

    reg.add(voice)
    _save_voices(reg)
    return {"voice": voice.to_dict()}


@app.get("/voices/{handle}")
def get_voice(handle: str) -> dict:
    v = _voices().get(handle)
    if v is None:
        raise HTTPException(status_code=404, detail="unknown voice")
    return {"voice": v.to_dict()}


@app.delete("/voices/{handle}")
def delete_voice(handle: str) -> dict:
    reg = _voices()
    v = reg.remove(handle)
    if v is None:
        raise HTTPException(status_code=404, detail="unknown voice")
    _save_voices(reg)
    removed = _store().delete_voice_data(v.handle)
    return {"deleted": v.handle, "targets": delete_targets(v.handle), "removed": removed}


@app.post("/voices/{handle}/consent")
def grant_consent(handle: str, body: ConsentIn) -> dict:
    reg = _voices()
    try:
        v = reg.grant_consent(
            handle, age_ok=body.age_ok,
            consented_by=body.consented_by, operator=body.operator,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown voice")
    _save_voices(reg)
    return {"voice": v.to_dict()}


@app.post("/voices/{handle}/revoke")
def revoke_consent(handle: str) -> dict:
    reg = _voices()
    try:
        v = reg.revoke_consent(handle)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown voice")
    _save_voices(reg)
    # Revocation that leaves the reference audio on disk is a flag flip, not a
    # revocation. core/voices.py says callers must delete derived data, so do
    # it here and report what actually went.
    removed = _store().delete_voice_data(v.handle)
    return {
        "voice": v.to_dict(),
        "targets": delete_targets(v.handle),
        "removed": removed,
    }


# --- readings
@app.get("/readings")
def list_readings() -> dict:
    d = _readings()
    return {
        "lang": d.lang,
        "applied": [e.to_dict() for e in d.applied_entries()],
        "proposed": [e.to_dict() for e in d.proposed_entries()],
    }


@app.put("/readings/{word}")
def set_reading(word: str, body: ReadingIn) -> dict:
    d = _readings()
    e = d.set_reading(word, body.reading, note=body.note)
    _save_readings(d)
    return {"entry": e.to_dict()}


@app.post("/readings/{word}/confirm")
def confirm_reading(word: str) -> dict:
    d = _readings()
    e = d.confirm(word)
    if e is None:
        raise HTTPException(status_code=404, detail="unknown word")
    _save_readings(d)
    return {"entry": e.to_dict()}


@app.post("/readings/{word}/reject")
def reject_reading(word: str) -> dict:
    d = _readings()
    e = d.reject(word)
    if e is None:
        raise HTTPException(status_code=404, detail="unknown word")
    _save_readings(d)
    return {"entry": e.to_dict()}


@app.delete("/readings/{word}")
def remove_reading(word: str) -> dict:
    d = _readings()
    e = d.remove(word)
    if e is None:
        raise HTTPException(status_code=404, detail="unknown word")
    _save_readings(d)
    return {"removed": e.to_dict()}


@app.post("/readings/apply")
def apply_readings(body: ApplyIn) -> dict:
    d = _readings()
    return {"text": d.apply(body.text), "spans": d.spans(body.text)}


# --- script
@app.post("/script/split")
def split(body: SplitIn) -> dict:
    chunks = split_script(body.text, body.max_chars)
    return {
        "count": len(chunks),
        "chunks": [{"index": c.index, "text": c.text, "chars": c.char_len} for c in chunks],
    }


# --- jobs
@app.post("/jobs", status_code=201)
def create_job(body: JobIn) -> dict:
    jobs = _jobs()
    if body.id in jobs:
        raise HTTPException(status_code=409, detail="job id already exists")
    job = Job(id=body.id, voice_id=body.voice_id, lang=body.lang or "ja")
    jobs[body.id] = job
    _save_jobs(jobs)
    return {"job": job.to_dict()}


@app.get("/jobs")
def list_jobs() -> dict:
    return {"jobs": [j.to_dict() for j in _jobs().values()]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    j = _jobs().get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return {"job": j.to_dict()}


@app.post("/jobs/{job_id}/state")
def transition_job(job_id: str, body: TransitionIn) -> dict:
    jobs = _jobs()
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    try:
        j.transition(body.to, body.error)
    except InvalidTransition as e:
        raise HTTPException(status_code=409, detail=str(e))
    _save_jobs(jobs)
    return {"job": j.to_dict()}


@app.post("/jobs/{job_id}/chunks/{index}")
def mark_chunk(job_id: str, index: int) -> dict:
    jobs = _jobs()
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    try:
        j.mark_chunk_done(index)
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _save_jobs(jobs)
    return {"job": j.to_dict()}


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    jobs = _jobs()
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    j.request_cancel()
    _save_jobs(jobs)
    return {"job": j.to_dict()}


# --- preflight: the "never silently substitute" gate
@app.post("/preflight")
def preflight(body: JobIn) -> dict:
    """Check that a synthesis request is possible. Does not synthesize."""
    try:
        lang = check_preflight(_voices().get(body.voice_id), _caps(), body.lang)
    except CapabilityError as e:
        raise _capability_http(e)
    return {"ok": True, "lang": lang}


# --- transcription
class TranscribeIn(BaseModel):
    path: str
    model: str = "mlx-community/whisper-large-v3-turbo"
    lang: str | None = None


@app.post("/transcribe")
def transcribe(body: TranscribeIn) -> dict:
    """Transcribe an audio file to text.

    Kept separate from /synth on purpose: transcription involves no voice, no
    enrolment and no consent, so it has no business in that lifecycle.
    """
    from fastapi import HTTPException

    base = _store().dir.resolve()
    target = Path(body.path).expanduser().resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=403, detail="path outside data directory")

    from koe_oss.engines.mlx_whisper_engine import (
        TranscriptionUnavailable,
        transcribe as run_transcribe,
    )

    try:
        r = run_transcribe(target, model=body.model, language=body.lang)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="audio file not found")
    except TranscriptionUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "text": r.text,
        "language": r.language,
        "seconds": r.seconds,
        "model": r.model,
    }


# --- synthesis
@app.post("/synth")
def synth(body: SynthIn) -> dict:
    """Synthesize text with a registered voice. Returns the wav path.

    Reading correction is applied first, so a dictionary entry changes what is
    spoken without the caller having to know about it.
    """
    engine = _engine()
    voice = _voices().get(body.voice_id)
    try:
        lang = check_can_synthesize(voice, _caps() if engine else None, body.text, body.lang)
    except CapabilityError as e:
        raise _capability_http(e)

    # Reference audio must exist before we claim we can synthesize. Checked
    # after the capability gate so a missing file cannot masquerade as a
    # consent or language problem.
    if engine is not None and not Path(voice.ref_audio).exists():
        raise HTTPException(
            status_code=400, detail=f"reference audio not found: {voice.ref_audio}"
        )

    if engine is None or not engine.is_available():
        raise HTTPException(status_code=503, detail="no synthesis engine available")

    spoken = _readings().apply(body.text)
    out = body.out_path or str(_store().dir / "audio" / voice.handle / "out.wav")

    # /audio and /transcribe already refuse paths outside the data dir. Without
    # the same check here, an unauthenticated caller could write a wav
    # anywhere the process can reach.
    base = _store().dir.resolve()
    target = Path(out).expanduser().resolve()
    if base != target and base not in target.parents:
        raise HTTPException(
            status_code=403, detail="out_path outside data directory"
        )
    out = str(target)
    try:
        result = engine.synthesize(
            SynthRequest(
                text=spoken,
                lang=lang,
                ref_audio=voice.ref_audio,
                ref_text=voice.ref_text,
                out_path=out,
            )
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EngineUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "ok": True,
        "audio_path": result.audio_path,
        "duration_sec": round(result.duration_sec, 2),
        "gen_sec": round(result.gen_sec, 2),
        "engine": result.engine,
        "lang": lang,
        "spoken": spoken,
        # Show the caller when the dictionary changed their text.
        "corrected": spoken != body.text,
    }


@app.on_event("startup")
def _startup() -> None:
    """Bind the best available engine so /synth works out of the box."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = autodetect_engine()


@app.get("/audio")
def get_audio(path: str):
    """Serve a generated wav from the local data directory.

    The UI cannot use file:// URLs (browsers block them), and generated audio
    lives inside the data dir. Only files under that dir are served.
    """
    from fastapi.responses import FileResponse

    base = _store().dir.resolve()
    target = Path(path).expanduser().resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=403, detail="path outside data directory")
    if not target.exists():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(str(target), media_type="audio/wav")


# ------------------------------------------------------------------- pairing
# LAN access to the local voice. Off by default; see core/pairing.py for the
# threat model. Start one with POST /pair/start, then the phone redeems the
# code and calls /remote/synth with the returned token.

def _pairings():
    from ..core.pairing import PairingStore

    return PairingStore(_store().dir / "pairings.json")


@app.post("/pair/start")
def pair_start(body: dict) -> dict:
    ttl = int(body.get("ttl", 900))
    p = _pairings().start(label=str(body.get("label", ""))[:60], ttl=ttl)
    return {
        "code": p.code,
        "expires_at": p.expires_at,
        "expires_in": int(p.expires_at - time.time()),
    }


@app.post("/pair/redeem")
def pair_redeem(body: dict) -> dict:
    p = _pairings().redeem(str(body.get("code", "")))
    if p is None:
        raise HTTPException(status_code=401, detail="invalid or expired code")
    return {"token": p.token, "expires_at": p.expires_at}


@app.get("/pair/active")
def pair_active() -> dict:
    return {"pairings": _pairings().active()}


@app.post("/pair/revoke")
def pair_revoke(body: dict) -> dict:
    ok = _pairings().revoke(str(body.get("token", "")))
    if not ok:
        raise HTTPException(status_code=404, detail="unknown token")
    return {"revoked": True}


@app.post("/pair/revoke-all")
def pair_revoke_all() -> dict:
    return {"revoked": _pairings().revoke_all()}


@app.post("/remote/synth")
def remote_synth(body: SynthIn, request: Request) -> dict:
    """Same as /synth but authenticated with a pairing token.

    Deliberately a separate route: the local UI must never require a token,
    and a remote caller must always have one.
    """
    from ..core.pairing import require_token

    try:
        require_token(_pairings(), request.headers.get("authorization"))
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    r = synth(body)  # same gate, same dictionary, same engine
    _pairings().touch(request.headers.get("authorization", "").split(" ")[-1])
    return r
