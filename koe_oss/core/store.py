"""JSON-file persistence for voices, readings and jobs.

Why files and not a database: the data is small, human-readable, and users
should be able to inspect and delete it. Atomic writes (tmp + os.replace) so a
crash mid-write never leaves a truncated store.

Nothing here touches the network.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from ..core.jobs import Job
from ..core.readings import ReadingDictionary
from ..core.voices import Voice, VoiceRegistry

__all__ = ["Store", "default_data_dir"]

VOICES_FILE = "voices.json"
READINGS_FILE = "readings.json"
JOBS_FILE = "jobs.json"


def default_data_dir() -> Path:
    """Per-user data directory. Overridable for tests."""
    override = os.environ.get("KOE_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "koe-oss"


class Store:
    """Loads and saves the three stores under one directory."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.dir = Path(data_dir) if data_dir else default_data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- internals
    def _path(self, name: str) -> Path:
        return self.dir / name

    def _write(self, name: str, payload: dict) -> None:
        """Atomic write: never leave a half-written file behind."""
        target = self._path(name)
        fd, tmp = tempfile.mkstemp(dir=str(self.dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, target)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _read(self, name: str) -> dict:
        p = self._path(name)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Corrupt store: do not crash the app, start clean and keep the
            # bad file for inspection.
            p.rename(p.with_suffix(p.suffix + ".corrupt"))
            return {}

    # ---------------------------------------------------------------- voices
    def load_voices(self) -> VoiceRegistry:
        return VoiceRegistry.from_dict(self._read(VOICES_FILE))

    def save_voices(self, reg: VoiceRegistry) -> None:
        self._write(VOICES_FILE, reg.to_dict())

    # -------------------------------------------------------------- readings
    def load_readings(self, lang: str = "ja") -> ReadingDictionary:
        d = self._read(READINGS_FILE)
        if not d:
            return ReadingDictionary(lang=lang)
        return ReadingDictionary.from_dict(d)

    def save_readings(self, dct: ReadingDictionary) -> None:
        self._write(READINGS_FILE, dct.to_dict())

    # ------------------------------------------------------------------ jobs
    def load_jobs(self) -> dict:
        raw = self._read(JOBS_FILE)
        out = {}
        for jid, d in (raw.get("jobs") or {}).items():
            try:
                out[jid] = Job(**{k: v for k, v in d.items()
                                  if k in Job.__dataclass_fields__})  # type: ignore[attr-defined]
            except TypeError:
                continue  # skip records written by an older shape
        return out

    def save_jobs(self, jobs: dict) -> None:
        self._write(JOBS_FILE, {"jobs": {k: v.to_dict() for k, v in jobs.items()}})

    # ---------------------------------------------------------------- import
    def import_ref_audio(self, handle: str, src: str) -> str:
        """Copy a reference recording into the data dir, return the new path.

        Storing the caller's path would mean revocation cannot delete the
        recording, since it would live outside our data dir. So we own a copy.
        """
        import shutil

        from ..core.voices import normalize_handle

        h = normalize_handle(handle)
        source = Path(src).expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"no such audio file: {source}")

        ref_dir = self.dir / "ref"
        ref_dir.mkdir(parents=True, exist_ok=True)
        dest = ref_dir / f"{h}{source.suffix or '.wav'}"
        shutil.copy2(source, dest)
        return str(dest)

    # --------------------------------------------------------------- deletion
    def delete_voice_data(self, handle: str) -> list:
        """Remove files belonging to a voice. Returns what was removed."""
        from ..core.voices import delete_targets, normalize_handle

        h = normalize_handle(handle)
        removed = []
        for rel in delete_targets(h)["keys"] + [
            f"audio/{h}", f"cache/{h}", f"jobs/{h}"
        ]:
            p = self.dir / rel
            if p.exists():
                if p.is_dir():
                    import shutil

                    shutil.rmtree(p)
                else:
                    p.unlink()
                removed.append(rel)
        return removed
