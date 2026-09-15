"""Job lifecycle — explicit states, explicit failures, resumable progress.

Why this exists
---------------
The most common complaint against local TTS studios is "it hung / it died /
I don't know if it finished". Almost always the tool had no notion of *where*
a job was. We model the states explicitly and forbid illegal transitions, so
the UI can always answer "what is happening?" and "what can I retry?".

States
------
    queued → preparing → generating → checking → completed
                 │            │           │
                 └────────────┴───────────┴──→ failed
    any active state → cancelled

Rules
-----
- ``completed``, ``failed`` and ``cancelled`` are terminal. No resurrection.
- A job may only enter ``generating`` once its chunks are known, so progress
  ("3 of 12") is always meaningful.
- Partial audio is tracked per chunk. A failure keeps completed chunks, which
  is what makes resume possible.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

__all__ = ["Job", "JobState", "TERMINAL_STATES", "ACTIVE_STATES"]

QUEUED = "queued"
PREPARING = "preparing"
GENERATING = "generating"
CHECKING = "checking"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL_STATES = (COMPLETED, FAILED, CANCELLED)
ACTIVE_STATES = (QUEUED, PREPARING, GENERATING, CHECKING)

_ALLOWED: Dict[str, set] = {
    QUEUED: {PREPARING, CANCELLED, FAILED},
    PREPARING: {GENERATING, CANCELLED, FAILED},
    GENERATING: {CHECKING, CANCELLED, FAILED},
    CHECKING: {COMPLETED, GENERATING, CANCELLED, FAILED},
}
_ALLOWED.update({s: set() for s in TERMINAL_STATES})


class JobState:
    """Namespace for the state constants (kept importable and greppable)."""

    QUEUED = QUEUED
    PREPARING = PREPARING
    GENERATING = GENERATING
    CHECKING = CHECKING
    COMPLETED = COMPLETED
    FAILED = FAILED
    CANCELLED = CANCELLED


class InvalidTransition(Exception):
    """Raised when a job is asked to move to a state it cannot reach."""


@dataclass
class Job:
    """One synthesis request for one script."""

    id: str
    voice_id: str
    lang: str = "ja"
    state: str = QUEUED
    total_chunks: int = 0
    done_chunks: List[int] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_requested: bool = False

    # ------------------------------------------------------------ transitions
    def transition(self, to: str, error: Optional[str] = None) -> "Job":
        if to not in _ALLOWED[self.state]:
            raise InvalidTransition(f"{self.state} → {to} is not allowed")
        self.state = to
        self.updated_at = time.time()
        if to in (FAILED, CANCELLED):
            self.error = error or self.error
        if to == COMPLETED:
            self.error = None
        return self

    def request_cancel(self) -> "Job":
        """Cooperative cancel: picked up between chunks, never mid-inference."""
        self.cancel_requested = True
        self.updated_at = time.time()
        return self

    # ---------------------------------------------------------------- chunks
    def set_total_chunks(self, n: int) -> "Job":
        if n < 0:
            raise ValueError("total_chunks must be >= 0")
        self.total_chunks = n
        self.updated_at = time.time()
        return self

    def mark_chunk_done(self, index: int) -> "Job":
        if index < 0 or (self.total_chunks and index >= self.total_chunks):
            raise IndexError(f"chunk {index} out of range (total={self.total_chunks})")
        if index not in self.done_chunks:
            self.done_chunks.append(index)
            self.done_chunks.sort()
        self.updated_at = time.time()
        return self

    # ------------------------------------------------------------------ read
    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def progress(self) -> float:
        """0.0–1.0. Zero until the chunk count is known — never a fake value."""
        if self.total_chunks <= 0:
            return 0.0
        return len(self.done_chunks) / self.total_chunks

    def remaining_chunks(self) -> List[int]:
        done = set(self.done_chunks)
        return [i for i in range(self.total_chunks) if i not in done]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "voice_id": self.voice_id,
            "lang": self.lang,
            "state": self.state,
            "total_chunks": self.total_chunks,
            "done_chunks": list(self.done_chunks),
            "remaining_chunks": self.remaining_chunks(),
            "progress": round(self.progress, 4),
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
