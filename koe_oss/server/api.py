"""Local HTTP API.

Binds to 127.0.0.1 only. There is no authentication because there is no
network exposure; if you need remote access, put it behind your own tunnel
and your own auth — do not widen this bind.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..core.capabilities import (
    CapabilityError,
    EngineCapabilities,
    preflight as check_preflight,
)
from ..core.jobs import Job, InvalidTransition
from ..core.readings import ReadingDictionary
from ..core.script import split_script
from ..core.voices import (
    ConsentRecord,
    Voice,
    VoiceRegistry,
    consent_state,
    delete_targets,
)

app = FastAPI(title="KOE OSS", version="0.1.0.dev0")

# Process-local state. A real deployment persists these; the API surface is
# what matters here, and keeping it in-memory keeps the core honest about
# having no hidden I/O.
VOICES = VoiceRegistry()
DICTIONARY = ReadingDictionary(lang="ja")
JOBS: Dict[str, Job] = {}
ENGINE_CAPS: Optional[EngineCapabilities] = None


def _set_engine(caps: Optional[EngineCapabilities]) -> None:
    global ENGINE_CAPS
    ENGINE_CAPS = caps


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


# ----------------------------------------------------------------- utilities
def _capability_http(exc: CapabilityError) -> HTTPException:
    # 422 rather than 500: the request was well-formed but cannot be honored.
    return HTTPException(status_code=422, detail=exc.to_dict())


# --------------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "voices": len(VOICES),
        "engine": ENGINE_CAPS.name if ENGINE_CAPS else None,
        "jobs": len(JOBS),
    }


# --- voices
@app.get("/voices")
def list_voices() -> dict:
    return {"voices": [v.to_dict() for v in VOICES.all()]}


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
    if voice.handle in VOICES:
        raise HTTPException(status_code=409, detail="voice already exists")
    return {"voice": VOICES.add(voice).to_dict()}


@app.get("/voices/{handle}")
def get_voice(handle: str) -> dict:
    v = VOICES.get(handle)
    if v is None:
        raise HTTPException(status_code=404, detail="unknown voice")
    return {"voice": v.to_dict()}


@app.delete("/voices/{handle}")
def delete_voice(handle: str) -> dict:
    v = VOICES.remove(handle)
    if v is None:
        raise HTTPException(status_code=404, detail="unknown voice")
    return {"deleted": v.handle, "targets": delete_targets(v.handle)}


@app.post("/voices/{handle}/consent")
def grant_consent(handle: str, body: ConsentIn) -> dict:
    try:
        v = VOICES.grant_consent(
            handle,
            age_ok=body.age_ok,
            consented_by=body.consented_by,
            operator=body.operator,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown voice")
    return {"voice": v.to_dict()}


@app.post("/voices/{handle}/revoke")
def revoke_consent(handle: str) -> dict:
    try:
        v = VOICES.revoke_consent(handle)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown voice")
    return {"voice": v.to_dict(), "targets": delete_targets(v.handle)}


# --- readings
@app.get("/readings")
def list_readings() -> dict:
    return {
        "lang": DICTIONARY.lang,
        "applied": [e.to_dict() for e in DICTIONARY.applied_entries()],
        "proposed": [e.to_dict() for e in DICTIONARY.proposed_entries()],
    }


@app.put("/readings/{word}")
def set_reading(word: str, body: ReadingIn) -> dict:
    e = DICTIONARY.set_reading(word, body.reading, note=body.note)
    return {"entry": e.to_dict()}


@app.post("/readings/{word}/confirm")
def confirm_reading(word: str) -> dict:
    e = DICTIONARY.confirm(word)
    if e is None:
        raise HTTPException(status_code=404, detail="unknown word")
    return {"entry": e.to_dict()}


@app.post("/readings/{word}/reject")
def reject_reading(word: str) -> dict:
    e = DICTIONARY.reject(word)
    if e is None:
        raise HTTPException(status_code=404, detail="unknown word")
    return {"entry": e.to_dict()}


@app.delete("/readings/{word}")
def remove_reading(word: str) -> dict:
    e = DICTIONARY.remove(word)
    if e is None:
        raise HTTPException(status_code=404, detail="unknown word")
    return {"removed": e.to_dict()}


@app.post("/readings/apply")
def apply_readings(body: ApplyIn) -> dict:
    return {
        "text": DICTIONARY.apply(body.text),
        "spans": DICTIONARY.spans(body.text),
    }


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
    if body.id in JOBS:
        raise HTTPException(status_code=409, detail="job id already exists")
    job = Job(id=body.id, voice_id=body.voice_id, lang=body.lang or "ja")
    JOBS[body.id] = job
    return {"job": job.to_dict()}


@app.get("/jobs")
def list_jobs() -> dict:
    return {"jobs": [j.to_dict() for j in JOBS.values()]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    j = JOBS.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return {"job": j.to_dict()}


@app.post("/jobs/{job_id}/state")
def transition_job(job_id: str, body: TransitionIn) -> dict:
    j = JOBS.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    try:
        j.transition(body.to, body.error)
    except InvalidTransition as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"job": j.to_dict()}


@app.post("/jobs/{job_id}/chunks/{index}")
def mark_chunk(job_id: str, index: int) -> dict:
    j = JOBS.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    try:
        j.mark_chunk_done(index)
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job": j.to_dict()}


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    j = JOBS.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="unknown job")
    j.request_cancel()
    return {"job": j.to_dict()}


# --- preflight: the "never silently substitute" gate
@app.post("/preflight")
def preflight(body: JobIn) -> dict:
    """Check that a synthesis request is possible. Does not synthesize."""
    try:
        lang = check_preflight(VOICES.get(body.voice_id), ENGINE_CAPS, body.lang)
    except CapabilityError as e:
        raise _capability_http(e)
    return {"ok": True, "lang": lang}
