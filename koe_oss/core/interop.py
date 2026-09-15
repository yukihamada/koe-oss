"""Shared data contract between the KOE service (koe-edge) and KOE OSS.

Why this module exists
----------------------
The hosted service stores voices as R2 objects:

    voiceprint/<handle>.wav   reference audio
    consent/<handle>          consent record (JSON)
    profile/<handle>.json     display name and profile
    speakervec/<handle>.json  speaker embedding (separate from the TTS ref)

KOE OSS stores the same concepts as local JSON. Two implementations of the same
idea drift — the hosted service has already been bitten once by a reading
dictionary duplicated in two files and edited in only one.

This module is the single definition of the *shape*. Both sides import it, and
`tests/test_interop.py` asserts the hosted R2 layout and the local layout agree.

Scope
-----
It defines keys and JSON shapes only. It does not talk to R2 or to disk — the
hosted side (Cloudflare Workers) and the local side (koe_oss.core.store) keep
their own I/O.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = [
    "SCHEMA_VERSION",
    "voice_keys",
    "consent_key",
    "normalize_handle",
    "voice_record",
    "consent_record",
    "reading_record",
    "parse_consent",
    "consent_state",
    "CONSENT_VERSION",
]

SCHEMA_VERSION = "1.0"

# Matches the hosted service's consent text version. Bump together with
# koe-edge/src/consent.js when the consent wording changes.
CONSENT_VERSION = "2026-09-10"

_HANDLE_RE = re.compile(r"[^a-z0-9_]")
MAX_HANDLE_LEN = 40


def normalize_handle(handle: str) -> str:
    """Handles are lowercase [a-z0-9_], capped at 40 chars — same rule as the
    hosted service, so a voice registered locally has the same id remotely."""
    return _HANDLE_RE.sub("", (handle or "").lower())[:MAX_HANDLE_LEN]


# ------------------------------------------------------------------ R2 layout
def voice_keys(handle: str) -> Dict[str, str]:
    """Object keys the hosted service uses for one voice."""
    h = normalize_handle(handle)
    return {
        "ref_audio": f"voiceprint/{h}.wav",
        "consent": f"consent/{h}",
        "profile": f"profile/{h}.json",
        "speaker": f"speakervec/{h}.json",
    }


def consent_key(handle: str) -> str:
    return f"consent/{normalize_handle(handle)}"


# --------------------------------------------------------------- JSON records
def consent_record(
    *,
    version: str = CONSENT_VERSION,
    age_ok: bool = False,
    consented_by: str = "self",
    operator: str = "",
    revoked_at: float | None = None,
    consented_at: float | None = None,
) -> Dict[str, Any]:
    """The consent object. Field names match koe-edge/src/consent.js so a record
    written by one side reads correctly on the other."""
    import time

    return {
        "consent_version": version,
        "consent_at": consented_at if consented_at is not None else time.time(),
        "age_ok": bool(age_ok),
        "consent_by": consented_by,
        "consent_operator": operator,
        "revoked_at": revoked_at,
        "schema": SCHEMA_VERSION,
    }


def voice_record(
    *,
    handle: str,
    ref_audio: str,
    ref_text: str = "",
    lang: str = "ja",
    engine: str = "",
    source: str = "local",
) -> Dict[str, Any]:
    """The local voice record. `ref_audio` is a path here and an R2 key there;
    everything else is identical."""
    import time

    return {
        "handle": normalize_handle(handle),
        "ref_audio": ref_audio,
        "ref_text": ref_text,
        "lang": lang,
        "engine": engine,
        "source": source,
        "created_at": time.time(),
        "schema": SCHEMA_VERSION,
    }


def reading_record(*, word: str, reading: str, state: str = "confirmed",
                   lang: str = "ja", source: str = "user") -> Dict[str, Any]:
    import time

    return {
        "word": word,
        "reading": reading,
        "state": state,
        "lang": lang,
        "source": source,
        "created_at": time.time(),
        "updated_at": time.time(),
        "schema": SCHEMA_VERSION,
    }


# -------------------------------------------------------------------- reading
def parse_consent(raw: Any) -> Dict[str, Any] | None:
    """Read a consent object written by either side.

    The hosted service has shipped records under slightly different field
    names over time; accept both rather than silently treating an old record
    as no record at all.
    """
    if not isinstance(raw, dict):
        return None
    version = raw.get("consent_version") or raw.get("version")
    if version is None:
        return None
    return {
        "version": version,
        "age_ok": bool(raw.get("age_ok", False)),
        "consented_by": raw.get("consent_by") or raw.get("consented_by") or "self",
        "operator": raw.get("consent_operator") or raw.get("operator") or "",
        "revoked_at": raw.get("revoked_at"),
        "consented_at": raw.get("consent_at") or raw.get("consented_at"),
    }


def consent_state(raw: Any, current: str = CONSENT_VERSION) -> str:
    """'none' | 'current' | 'stale'. Revoked reads as none."""
    rec = parse_consent(raw)
    if rec is None or rec["revoked_at"] is not None:
        return "none"
    if rec["version"] == current and rec["age_ok"]:
        return "current"
    return "stale"


def export_readings(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize reading entries for export to the hosted service."""
    out = []
    for e in entries:
        out.append(reading_record(
            word=e["word"], reading=e["reading"],
            state=e.get("state", "confirmed"),
            lang=e.get("lang", "ja"), source=e.get("source", "user")))
    return out
