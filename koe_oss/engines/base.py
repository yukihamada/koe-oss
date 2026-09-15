"""Synthesis engine interface.

Deliberately narrow: an engine takes a reference voice + text and returns
audio. Everything else (reading correction, splitting, job state, consent)
lives in ``koe_oss.core`` and is engine-independent.

Adding an engine means implementing ``SynthEngine``. No registry magic, no
plugin discovery — explicit construction keeps the failure modes visible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..core.capabilities import EngineCapabilities

__all__ = ["SynthRequest", "SynthResult", "SynthEngine", "EngineUnavailable"]


class EngineUnavailable(RuntimeError):
    """Raised when the engine's runtime (MLX / CUDA / model weights) is absent."""


@dataclass
class SynthRequest:
    """Everything an engine needs. No paths into user data beyond these."""

    text: str
    lang: str
    ref_audio: str
    ref_text: Optional[str] = None
    temperature: float = 0.5
    speed: float = 1.0
    # Where to write the wav. Required in practice; a temp file is used if unset.
    out_path: Optional[str] = None


@dataclass
class SynthResult:
    audio_path: str
    sample_rate: int
    duration_sec: float
    engine: str
    # Seconds spent in the engine itself, excluding queueing and I/O.
    gen_sec: float = 0.0


class SynthEngine(ABC):
    """Base class for synthesis backends."""

    @abstractmethod
    def capabilities(self) -> EngineCapabilities:
        """Declared capabilities. Must not probe the GPU at import time."""

    @abstractmethod
    def is_available(self) -> bool:
        """True if this engine can run on this machine right now."""

    @abstractmethod
    def synthesize(self, req: SynthRequest) -> SynthResult:
        """Synthesize one chunk. Blocking. Long work belongs in a subprocess."""
