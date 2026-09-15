"""Script splitting — deterministic, resumable chunking of long text.

Why this exists
---------------
Existing local TTS studios fail on long text in two ways: a chapter runs past a
compute limit and is abandoned (losing all prior work), or the audio is
truncated mid-sentence with no signal. Both are *bookkeeping* failures, not
model failures.

The fix is to make splitting a pure function of the text, so that:

- chunk N is always the same bytes for the same input (cacheable, resumable),
- a failed run can resume from the first chunk that has no audio yet,
- the caller always knows how many chunks exist before spending GPU time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

__all__ = ["Chunk", "split_script", "DEFAULT_MAX_CHARS"]

DEFAULT_MAX_CHARS = 80

# Sentence enders used across ja/en. Kept simple on purpose: this must be
# predictable, and a clever regex here is a bug generator.
_SENTENCE_RE = re.compile(r"[^。．！!？?\n]*[。．！!？?]*")
_SENTENCE_END = "。．！!？?"
_SOFT_BREAK = "、，, "


@dataclass(frozen=True)
class Chunk:
    """One synthesizable unit."""

    index: int
    text: str

    @property
    def char_len(self) -> int:
        return len(self.text)


def split_script(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> List[Chunk]:
    """Split `text` into chunks of at most `max_chars` characters.

    Rules, in order:
      1. Split on sentence enders (。．！!？? newline).
      2. A sentence longer than `max_chars` is split at the last soft break
         (、，, space) before the limit.
      3. A sentence with no soft break is hard-cut at the limit.

    Never returns an empty chunk. Empty input returns an empty list.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    if not text or not text.strip():
        return []

    pieces: List[str] = []
    for m in _SENTENCE_RE.finditer(text):
        piece = m.group(0).strip()
        if piece:
            pieces.append(piece)

    chunks: List[str] = []
    for piece in pieces:
        if len(piece) <= max_chars:
            chunks.append(piece)
            continue
        rest = piece
        while len(rest) > max_chars:
            cut = -1
            for brk in _SOFT_BREAK:
                cut = max(cut, rest.rfind(brk, 1, max_chars))
            if cut <= 0:
                cut = max_chars
            else:
                cut += 1  # keep the break character with the leading chunk
            head = rest[:cut].strip()
            if head:
                chunks.append(head)
            rest = rest[cut:].strip()
        if rest:
            chunks.append(rest)

    return [Chunk(index=i, text=c) for i, c in enumerate(chunks) if c]


def join_chunks(chunks: List[Chunk], separator: str = "") -> str:
    """Inverse of `split_script` for round-trip verification."""
    return separator.join(c.text for c in chunks)
