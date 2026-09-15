"""Reading dictionary — per-word reading overrides with a full audit trail.

Why this exists
---------------
A TTS engine will misread proper nouns (弟子屈 → テシカガ), brand names
(KOE → ケーオーイー) and numbers. KOE's answer is not "hope the model gets it
right"; it is **let the user say the reading once, and keep that decision**.

Design rules
------------
1. **Explicit over implicit.** A reading is only ever applied because a human
   (or an explicitly trusted import) put it there. We never guess.
2. **Auditable.** Every entry records when it was set, by whom, and from what
   source. ``source="auto"`` marks entries proposed by a checker; those stay
   *proposed* until a human confirms them.
3. **Revocable.** Removing an entry is a first-class operation, and the removal
   is itself recorded.
4. **Deterministic.** Applying the dictionary is a pure string transform:
   same input → same output, always.

Terminology (deliberately precise)
----------------------------------
- ``state="confirmed"`` — a human verified this reading. Applied to synthesis.
- ``state="proposed"``  — a checker suspects a misread. **Not** applied.
- ``state="rejected"``  — a human said "no, the current reading is fine".
  Kept so the checker stops re-proposing it.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    "ReadingEntry",
    "ReadingDictionary",
    "CONFIRMED",
    "PROPOSED",
    "REJECTED",
]

CONFIRMED = "confirmed"
PROPOSED = "proposed"
REJECTED = "rejected"

_STATES = (CONFIRMED, PROPOSED, REJECTED)

# Words longer than this are almost certainly a mistake (a whole sentence was
# pasted in). Refuse them so the dictionary stays a *word* dictionary.
MAX_WORD_LEN = 40


@dataclass
class ReadingEntry:
    """One word → reading rule."""

    word: str
    reading: str
    state: str = CONFIRMED
    source: str = "user"          # "user" | "auto" | "import"
    lang: str = "ja"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    note: str = ""

    def __post_init__(self) -> None:
        if not self.word or not self.word.strip():
            raise ValueError("word must be non-empty")
        if len(self.word) > MAX_WORD_LEN:
            raise ValueError(f"word too long (>{MAX_WORD_LEN}): {self.word!r}")
        if not self.reading or not self.reading.strip():
            raise ValueError("reading must be non-empty")
        if self.state not in _STATES:
            raise ValueError(f"unknown state: {self.state!r}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReadingEntry":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class ReadingDictionary:
    """An ordered, auditable set of reading overrides for one language.

    Longest-match-first application means 「毎月一日」 wins over 「一日」.
    """

    def __init__(self, lang: str = "ja") -> None:
        self.lang = lang
        self._entries: Dict[str, ReadingEntry] = {}
        self._history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ read
    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, word: str) -> bool:
        return word in self._entries

    def get(self, word: str) -> Optional[ReadingEntry]:
        return self._entries.get(word)

    def entries(self) -> List[ReadingEntry]:
        return sorted(self._entries.values(), key=lambda e: (-len(e.word), e.word))

    def applied_entries(self) -> List[ReadingEntry]:
        """Entries that actually change synthesis output."""
        return [e for e in self.entries() if e.state == CONFIRMED]

    def proposed_entries(self) -> List[ReadingEntry]:
        return [e for e in self.entries() if e.state == PROPOSED]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lang": self.lang,
            "entries": [e.to_dict() for e in self.entries()],
            "history": list(self._history),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReadingDictionary":
        dct = cls(lang=d.get("lang", "ja"))
        for raw in d.get("entries", []):
            e = ReadingEntry.from_dict(raw)
            dct._entries[e.word] = e
        dct._history = list(d.get("history", []))
        return dct

    # ----------------------------------------------------------------- write
    def set_reading(
        self,
        word: str,
        reading: str,
        *,
        state: str = CONFIRMED,
        source: str = "user",
        note: str = "",
    ) -> ReadingEntry:
        """Add or update a reading. Records the previous value in history."""
        prev = self._entries.get(word)
        entry = ReadingEntry(
            word=word,
            reading=reading,
            state=state,
            source=source,
            lang=self.lang,
            created_at=prev.created_at if prev else time.time(),
            updated_at=time.time(),
            note=note,
        )
        self._entries[word] = entry
        self._history.append(
            {
                "op": "set",
                "word": word,
                "reading": reading,
                "state": state,
                "source": source,
                "previous": prev.to_dict() if prev else None,
                "at": entry.updated_at,
            }
        )
        return entry

    def propose(self, word: str, reading: str, note: str = "") -> ReadingEntry:
        """A checker suspects a misread. Stays *proposed* until confirmed."""
        return self.set_reading(
            word, reading, state=PROPOSED, source="auto", note=note
        )

    def confirm(self, word: str) -> Optional[ReadingEntry]:
        """Promote a proposal to confirmed. No-op if the word is unknown."""
        e = self._entries.get(word)
        if e is None:
            return None
        e.state = CONFIRMED
        e.source = "user"
        e.updated_at = time.time()
        self._history.append({"op": "confirm", "word": word, "at": e.updated_at})
        return e

    def reject(self, word: str, note: str = "") -> Optional[ReadingEntry]:
        """Mark a proposal as wrong so the checker stops re-suggesting it."""
        e = self._entries.get(word)
        if e is None:
            return None
        e.state = REJECTED
        e.updated_at = time.time()
        if note:
            e.note = note
        self._history.append({"op": "reject", "word": word, "at": e.updated_at})
        return e

    def remove(self, word: str) -> Optional[ReadingEntry]:
        e = self._entries.pop(word, None)
        if e is not None:
            self._history.append({"op": "remove", "word": word, "at": time.time()})
        return e

    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ----------------------------------------------------------------- apply
    def apply(self, text: str) -> str:
        """Rewrite `text`, replacing each known word with its reading.

        Only ``confirmed`` entries are applied. Longest words first, so more
        specific rules win. Pure function: no I/O, no randomness.
        """
        out = text
        for e in self.applied_entries():
            out = out.replace(e.word, e.reading)
        return out

    def spans(self, text: str) -> List[Dict[str, Any]]:
        """Which rules fired, and where. Used by the UI to show corrections."""
        found: List[Dict[str, Any]] = []
        for e in self.applied_entries():
            start = 0
            while True:
                idx = text.find(e.word, start)
                if idx < 0:
                    break
                found.append(
                    {
                        "word": e.word,
                        "reading": e.reading,
                        "start": idx,
                        "end": idx + len(e.word),
                    }
                )
                start = idx + len(e.word)
        found.sort(key=lambda s: s["start"])
        return found


# --------------------------------------------------------------------- misc
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_for_compare(s: str) -> str:
    """Comparison-only normalization: collapse whitespace, strip edges."""
    return _WHITESPACE_RUN.sub("", s or "").strip()
