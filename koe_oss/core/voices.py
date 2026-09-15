"""Voice registry and consent records.

Why this exists
---------------
A cloned voice is biometric-adjacent data. KOE OSS treats the *record of
permission* as part of the voice itself: you cannot synthesize with a voice
whose consent record is missing or stale, and revocation deletes the derived
data rather than just flipping a flag.

What this is NOT
----------------
- **It is not identity proof.** A consent record shows that someone, at some
  time, agreed to something. It does not prove *which* human was recorded.
  Any stronger claim would be false, so we do not make it.
- **It is not a DRM boundary.** Once audio leaves the device we cannot recall
  it. The spec says so instead of implying otherwise.

Consent states
--------------
- ``none``     — no record. Synthesis is refused.
- ``current``  — matches the current consent version and age gate.
- ``stale``    — a record exists but is an older version (or lacks the age
                 gate). Synthesis proceeds, but the UI must ask for renewal.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

__all__ = [
    "CONSENT_VERSION",
    "ConsentRecord",
    "Voice",
    "VoiceRegistry",
    "consent_state",
    "NONE",
    "CURRENT",
    "STALE",
]

CONSENT_VERSION = "2026-09-10"

NONE = "none"
CURRENT = "current"
STALE = "stale"

_HANDLE_RE = re.compile(r"[^a-z0-9_]")
MAX_HANDLE_LEN = 40


def normalize_handle(handle: str) -> str:
    """Lowercase, strip to [a-z0-9_], cap length. Empty input → empty output."""
    return _HANDLE_RE.sub("", (handle or "").lower())[:MAX_HANDLE_LEN]


@dataclass
class ConsentRecord:
    """Versioned permission for one voice."""

    version: str = CONSENT_VERSION
    consented_at: float = field(default_factory=time.time)
    age_ok: bool = False
    consented_by: str = "self"      # "self" | "admin" | "agent"
    operator: str = ""
    revoked_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConsentRecord":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


def consent_state(record: Optional[ConsentRecord], current: str = CONSENT_VERSION) -> str:
    """Three-valued: ``none`` / ``current`` / ``stale``. Revoked counts as none."""
    if record is None or record.revoked_at is not None:
        return NONE
    if record.version == current and record.age_ok:
        return CURRENT
    return STALE


@dataclass
class Voice:
    """One registered voice: a reference recording plus its transcript."""

    handle: str
    ref_audio: str
    ref_text: str
    lang: str = "ja"
    engine: str = ""
    created_at: float = field(default_factory=time.time)
    consent: Optional[ConsentRecord] = None
    source: str = "local"           # "local" | "import"
    notes: str = ""

    def __post_init__(self) -> None:
        h = normalize_handle(self.handle)
        if not h:
            raise ValueError("handle must contain [a-z0-9_]")
        self.handle = h
        if not self.ref_audio:
            raise ValueError("ref_audio is required")
        # An empty ref_text is allowed only for engines that support
        # speaker-embedding-only mode; `supports_ref_text_free` gates that.

    @property
    def consent_state(self) -> str:
        return consent_state(self.consent)

    def usable(self) -> bool:
        return self.consent_state in (CURRENT, STALE)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["consent"] = self.consent.to_dict() if self.consent else None
        d["consent_state"] = self.consent_state
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Voice":
        raw = dict(d)
        c = raw.pop("consent", None)
        raw.pop("consent_state", None)
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        v = cls(**{k: v for k, v in raw.items() if k in known})
        v.consent = ConsentRecord.from_dict(c) if c else None
        return v


class VoiceRegistry:
    """In-memory registry. Persistence is the caller's job (see server/)."""

    def __init__(self) -> None:
        self._voices: Dict[str, Voice] = {}

    def __len__(self) -> int:
        return len(self._voices)

    def __contains__(self, handle: str) -> bool:
        return normalize_handle(handle) in self._voices

    def add(self, voice: Voice) -> Voice:
        self._voices[voice.handle] = voice
        return voice

    def get(self, handle: str) -> Optional[Voice]:
        return self._voices.get(normalize_handle(handle))

    def require(self, handle: str) -> Voice:
        v = self.get(handle)
        if v is None:
            raise KeyError(f"unknown voice: {handle!r}")
        return v

    def remove(self, handle: str) -> Optional[Voice]:
        return self._voices.pop(normalize_handle(handle), None)

    def all(self) -> List[Voice]:
        return sorted(self._voices.values(), key=lambda v: v.handle)

    def grant_consent(
        self,
        handle: str,
        *,
        age_ok: bool,
        consented_by: str = "self",
        operator: str = "",
    ) -> Voice:
        v = self.require(handle)
        v.consent = ConsentRecord(
            version=CONSENT_VERSION,
            age_ok=bool(age_ok),
            consented_by=consented_by,
            operator=operator,
        )
        return v

    def revoke_consent(self, handle: str) -> Voice:
        """Revoke permission. The voice stays listed but becomes unusable.

        Callers must also delete derived data (reference audio, caches).
        ``delete_targets`` returns the keys to remove.
        """
        v = self.require(handle)
        if v.consent is not None:
            v.consent.revoked_at = time.time()
        else:
            v.consent = ConsentRecord(revoked_at=time.time(), age_ok=False)
        return v

    def to_dict(self) -> Dict[str, Any]:
        return {"voices": [v.to_dict() for v in self.all()]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VoiceRegistry":
        reg = cls()
        for raw in (d or {}).get("voices", []):
            reg.add(Voice.from_dict(raw))
        return reg


def delete_targets(handle: str) -> Dict[str, List[str]]:
    """Storage keys to remove when a voice is deleted or consent is revoked.

    Returned as ``{"keys": [...], "prefixes": [...]}`` — deterministic, so the
    caller can show the user exactly what will be removed before removing it.
    """
    h = normalize_handle(handle)
    if not h:
        return {"keys": [], "prefixes": []}
    return {
        "keys": [
            f"voices/{h}.json",
            f"ref/{h}.wav",
            f"consent/{h}.json",
        ],
        "prefixes": [
            f"audio/{h}/",
            f"cache/{h}/",
            f"jobs/{h}/",
        ],
    }
