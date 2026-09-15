"""Capability gating — refuse what we cannot do, loudly.

Why this exists
---------------
A reported defect in comparable local studios: "three engines ignore the
language they were given, and one silently mis-speaks unsupported languages".
Silent substitution is worse than an error, because the user ships the wrong
audio believing it is right.

KOE OSS resolves the voice and language **before** spending GPU time, and
raises ``CapabilityError`` rather than falling back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from .voices import Voice, consent_state, CURRENT, STALE

__all__ = [
    "CapabilityError",
    "EngineCapabilities",
    "check_can_synthesize",
    "preflight",
    "resolve_language",
]


class CapabilityError(Exception):
    """Raised when a request cannot be honored. Carries a stable reason code."""

    def __init__(self, reason: str, message: str, **detail: object) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.detail: Dict[str, object] = dict(detail)

    def to_dict(self) -> Dict[str, object]:
        return {"reason": self.reason, "message": self.message, **self.detail}


@dataclass
class EngineCapabilities:
    """What one engine install can actually do. Declared, never inferred."""

    name: str
    languages: Set[str] = field(default_factory=set)
    supports_clone: bool = False
    # True only if the engine can clone from a reference without a transcript.
    supports_ref_text_free: bool = False
    max_text_chars: int = 1200

    def supports(self, lang: str) -> bool:
        return self.canonical(lang) is not None

    def canonical(self, lang: str) -> Optional[str]:
        """The engine's own spelling of `lang`, or None if unsupported.

        Engines expect their exact spelling (``"Japanese"`` vs ``"ja"``), so we
        return the declared form rather than the caller's — a caller writing
        ``"JA"`` must still get ``"ja"`` out.
        """
        if not lang:
            return None
        needle = lang.lower()
        for declared in self.languages:
            if declared.lower() == needle:
                return declared
        return None


def resolve_language(
    requested: Optional[str], voice: Voice, caps: EngineCapabilities
) -> str:
    """Pick the language to synthesize in, or raise.

    Precedence: explicit request → voice language → error if unsupported.
    """
    candidates: List[str] = []
    if requested:
        candidates.append(requested)
    if voice.lang:
        candidates.append(voice.lang)
    for c in candidates:
        canonical = caps.canonical(c)
        if canonical is not None:
            return canonical
    raise CapabilityError(
        "unsupported_language",
        f"engine {caps.name!r} does not support any of {candidates!r}",
        requested=requested,
        voice_lang=voice.lang,
        supported=sorted(caps.languages),
    )


def check_can_synthesize(
    voice: Optional[Voice],
    caps: Optional[EngineCapabilities],
    text: str,
    lang: Optional[str] = None,
) -> str:
    """Validate a synthesis request. Returns the resolved language.

    Raises ``CapabilityError`` with a stable ``reason`` for every rejection:
      - ``unknown_voice``       — voice not registered
      - ``consent_missing``     — no consent record at all
      - ``consent_revoked``     — consent was withdrawn
      - ``engine_missing``      — no engine installed
      - ``clone_unsupported``   — engine cannot clone a voice
      - ``ref_text_required``   — engine needs a transcript for this voice
      - ``unsupported_language``
      - ``text_too_long``
      - ``empty_text``
    """
    if not text or not text.strip():
        raise CapabilityError("empty_text", "text is empty")

    resolved = preflight(voice, caps, lang)

    if len(text) > caps.max_text_chars:  # type: ignore[union-attr]
        raise CapabilityError(
            "text_too_long",
            f"text is {len(text)} chars; limit is {caps.max_text_chars}",  # type: ignore[union-attr]
            length=len(text),
            limit=caps.max_text_chars,  # type: ignore[union-attr]
        )

    return resolved


def preflight(
    voice: Optional[Voice],
    caps: Optional[EngineCapabilities],
    lang: Optional[str] = None,
) -> str:
    """Can we synthesize with this voice at all, ignoring the text?

    Split from ``check_can_synthesize`` so the UI can validate voice, consent
    and language *before* the user finishes typing — and so a preflight call
    never has to invent dummy text to get an answer.
    """
    if voice is None:
        raise CapabilityError("unknown_voice", "voice is not registered")

    state = consent_state(voice.consent)
    if state not in (CURRENT, STALE):
        raise CapabilityError(
            "consent_missing" if voice.consent is None else "consent_revoked",
            "this voice has no usable consent record",
            handle=voice.handle,
            consent_state=state,
        )

    if caps is None:
        raise CapabilityError("engine_missing", "no synthesis engine is installed")

    if not caps.supports_clone:
        raise CapabilityError(
            "clone_unsupported",
            f"engine {caps.name!r} cannot clone a voice",
            engine=caps.name,
        )

    if not voice.ref_text and not caps.supports_ref_text_free:
        raise CapabilityError(
            "ref_text_required",
            f"engine {caps.name!r} requires a transcript for the reference audio",
            handle=voice.handle,
        )

    return resolve_language(lang, voice, caps)
