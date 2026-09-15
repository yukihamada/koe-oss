"""Long-form synthesis: split a script, synthesize each chunk, keep progress.

Why this is a separate module
-----------------------------
Existing local studios lose work on long text: a chapter runs past a compute
limit and the whole thing is abandoned. This pipeline exists so that never
happens:

- the chunk list is computed up front (so progress is knowable before we start),
- each finished chunk is written to its own file immediately,
- a failure mid-run leaves every completed chunk on disk,
- re-running resumes from the first chunk that has no audio yet.

Concatenation is done by ffmpeg concat rather than in Python, to avoid
re-encoding and to keep memory flat regardless of script length.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from ..core.jobs import Job, QUEUED, PREPARING, GENERATING, CHECKING, COMPLETED, FAILED
from ..core.readings import ReadingDictionary
from ..core.script import split_script
from ..core.voices import Voice
from ..engines.base import SynthEngine, SynthRequest

__all__ = ["LongformResult", "synthesize_longform"]


@dataclass
class LongformResult:
    job: Job
    chunk_paths: List[str] = field(default_factory=list)
    merged_path: Optional[str] = None
    resumed: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.job.state == COMPLETED and not self.errors


def _chunk_path(workdir: Path, index: int) -> Path:
    return workdir / f"chunk_{index:05d}.wav"


def _concat(paths: List[Path], out: Path) -> None:
    """Join wavs without re-encoding.

    Done in Python rather than shelling out to ffmpeg: ffmpeg is not installed
    everywhere (CI being the obvious case), and concatenating wavs is just
    writing one header followed by the existing PCM frames. No external
    process, no transcode, no quality loss.
    """
    if not paths:
        raise ValueError("nothing to concatenate")
    if len(paths) == 1:
        out.write_bytes(paths[0].read_bytes())
        return

    import wave

    params = None
    frames = []
    for p in paths:
        with wave.open(str(p), "rb") as w:
            if params is None:
                params = w.getparams()
            elif (
                w.getframerate() != params.framerate
                or w.getsampwidth() != params.sampwidth
                or w.getnchannels() != params.nchannels
            ):
                raise ValueError(f"incompatible audio format: {p}")
            frames.append(w.readframes(w.getnframes()))

    with wave.open(str(out), "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        for f in frames:
            w.writeframes(f)


def synthesize_longform(
    engine: SynthEngine,
    voice: Voice,
    text: str,
    workdir: str | Path,
    lang: Optional[str] = None,
    dictionary: Optional[ReadingDictionary] = None,
    max_chars: int = 80,
    job: Optional[Job] = None,
    on_progress: Optional[Callable[[Job], None]] = None,
) -> LongformResult:
    """Synthesize a long script chunk by chunk, resumably.

    Existing audio in `workdir` is reused, so calling this again after a crash
    resumes rather than starting over.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    job = job or Job(id=workdir.name, voice_id=voice.handle, lang=lang or voice.lang)
    result = LongformResult(job=job)

    # Resolve language once, before spending GPU time on 40 chunks.
    from ..core.capabilities import resolve_language

    resolved = resolve_language(lang, voice, engine.capabilities())

    job.transition(PREPARING)
    chunks = split_script(text, max_chars=max_chars)
    job.set_total_chunks(len(chunks))
    if on_progress:
        on_progress(job)

    if not chunks:
        job.transition(FAILED, "script produced no chunks")
        result.errors.append("script produced no chunks")
        return result

    job.transition(GENERATING)

    dct = dictionary or ReadingDictionary(lang=voice.lang)
    paths: List[Path] = []

    for chunk in chunks:
        target = _chunk_path(workdir, chunk.index)

        # Resume: an existing non-trivial file counts as done.
        if target.exists() and target.stat().st_size > 1000:
            result.resumed += 1
            job.mark_chunk_done(chunk.index)
            paths.append(target)
            if on_progress:
                on_progress(job)
            continue

        if job.cancel_requested:
            job.transition(FAILED, "cancelled")
            result.errors.append("cancelled")
            return result

        spoken = dct.apply(chunk.text)
        try:
            engine.synthesize(SynthRequest(
                text=spoken,
                lang=resolved,
                ref_audio=voice.ref_audio,
                ref_text=voice.ref_text,
                out_path=str(target),
            ))
        except Exception as e:  # keep completed chunks; that is the whole point
            job.transition(FAILED, f"chunk {chunk.index}: {e}")
            result.errors.append(f"chunk {chunk.index}: {e}")
            return result

        job.mark_chunk_done(chunk.index)
        paths.append(target)
        if on_progress:
            on_progress(job)

    job.transition(CHECKING)
    merged = workdir / "merged.wav"
    try:
        _concat(paths, merged)
    except Exception as e:
        job.transition(FAILED, f"concat: {e}")
        result.errors.append(f"concat: {e}")
        return result

    job.transition(COMPLETED)
    result.chunk_paths = [str(p) for p in paths]
    result.merged_path = str(merged)
    (workdir / "manifest.json").write_text(
        json.dumps({
            "voice": voice.handle,
            "lang": resolved,
            "chunks": len(paths),
            "resumed": result.resumed,
            "merged": str(merged),
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    if on_progress:
        on_progress(job)
    return result
