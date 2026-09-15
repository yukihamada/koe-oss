"""Local HTTP API.

Binds to 127.0.0.1 only. There is no authentication because there is no
network exposure; if you need remote access, put it behind your own tunnel
and your own auth — do not widen this bind.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
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

app = FastAPI(title="KOE OSS", version="0.1.0.dev0")

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
    return {"voice": v.to_dict(), "targets": delete_targets(v.handle)}


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
