"""Speech-to-text via mlx-whisper, on-device.

Deliberately separate from the synthesis engines: transcription has no voice,
no consent record and no enrolment, so it does not belong in the same
lifecycle. It reads an audio file and returns text.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


class TranscriptionUnavailable(RuntimeError):
    """mlx-whisper is not installed, or the model could not be loaded."""


@dataclass
class Transcription:
    text: str
    language: str | None
    seconds: float
    model: str


def available() -> bool:
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def transcribe(
    path: str | Path,
    model: str = DEFAULT_MODEL,
    language: str | None = None,
) -> Transcription:
    """Transcribe an audio file. Raises TranscriptionUnavailable if unusable."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no such audio file: {path}")

    try:
        import mlx_whisper
    except ImportError as e:
        raise TranscriptionUnavailable(
            "mlx-whisper is not installed. Install it with:\n"
            "  pip install mlx-whisper"
        ) from e

    kwargs: dict = {"path_or_hf_repo": model}
    # Whisper auto-detects language well; only pin it when asked, because a
    # wrong forced language produces confidently wrong text.
    if language:
        kwargs["language"] = language

    start = time.time()
    try:
        result = mlx_whisper.transcribe(str(path), **kwargs)
    except Exception as e:
        raise TranscriptionUnavailable(f"transcription failed: {e}") from e

    return Transcription(
        text=(result.get("text") or "").strip(),
        language=result.get("language"),
        seconds=round(time.time() - start, 2),
        model=model,
    )
