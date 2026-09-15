"""Keep the vendored iOS app in sync with its upstream checkout.

Why a sync script instead of copying once
-----------------------------------------
The iOS app lives in ~/workspace/koe-ios, which is part of the big `workspace`
repo. We vendor a copy here so koe-oss is self-contained, but a copy that
silently drifts is worse than no copy — you would ship an old app believing it
is current.

So: `sync` copies the sources and records a manifest of file hashes; `check`
verifies the vendored copy still matches upstream and reports drift.

Secrets.swift is never copied. It holds a personal token and is gitignored
upstream; it must stay out of this public repository.

    python tools/sync_ios.py check   # report drift (CI uses this)
    python tools/sync_ios.py sync    # re-copy and rewrite the manifest
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / "ios"
MANIFEST = ROOT / "ios" / "UPSTREAM.json"

UPSTREAM = Path.home() / "workspace" / "koe-ios"

# Directories and files mirrored from upstream.
MIRROR = ["Sources", "Shared", "project.yml", "README.md"]

# Never copy these, for any reason.
# Never copy these, for any reason. Secrets.template.swift is a safe
# placeholder; Secrets.swift holds a real token.
EXCLUDE = {"Secrets.swift"}
SECRET_FILES = {"Secrets.swift"}

# Files we add ourselves; the manifest records them but does not expect them
# to exist upstream.
LOCAL_ONLY = {"LocalVoiceClient.swift", "UPSTREAM.json",
              "Sources/Secrets.template.swift"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan(base: Path) -> dict:
    out = {}
    if not base.exists():
        return out
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if p.name in EXCLUDE:
            continue
        rel = p.relative_to(base).as_posix()
        out[rel] = sha256(p)
    return out


def upstream_files() -> dict:
    """Hash the upstream files we mirror, keyed by their vendored path."""
    out = {}
    for item in MIRROR:
        src = UPSTREAM / item
        if src.is_dir():
            for p in sorted(src.rglob("*")):
                if not p.is_file() or p.name in EXCLUDE:
                    continue
                rel = p.relative_to(UPSTREAM).as_posix()
                out[rel] = sha256(p)
        elif src.is_file() and src.name not in EXCLUDE:
            out[item] = sha256(src)
    return out


def cmd_sync() -> int:
    if not UPSTREAM.exists():
        print(f"SKIP: upstream not found at {UPSTREAM}")
        return 0

    for item in MIRROR:
        src = UPSTREAM / item
        dst = IOS / item
        if not src.exists():
            print(f"warn: missing upstream {item}")
            continue
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(
                src, dst,
                ignore=shutil.ignore_patterns(*EXCLUDE),
            )
        else:
            shutil.copy2(src, dst)

    # Remove anything excluded that may have been copied by an older run.
    for p in IOS.rglob("*"):
        if p.is_file() and p.name in EXCLUDE:
            p.unlink()

    manifest = {
        "upstream": str(UPSTREAM),
        "files": scan(IOS),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(f"synced {len(manifest['files'])} files from {UPSTREAM}")
    return 0


def cmd_check() -> int:
    if not MANIFEST.exists():
        print("FAIL: no UPSTREAM.json manifest; run `sync`")
        return 1
    if not UPSTREAM.exists():
        print(f"SKIP: upstream not found at {UPSTREAM}")
        return 0

    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    current = scan(IOS)
    upstream = upstream_files()

    problems = []

    for rel, want in upstream.items():
        got = current.get(rel)
        if got is None:
            problems.append(f"missing: {rel}")
        elif got != want:
            problems.append(f"drift:   {rel} (vendored copy differs from upstream)")
        if recorded.get(rel) not in (None, want):
            problems.append(f"stale:   {rel} (manifest hash differs)")

    for name in SECRET_FILES:
        if any(p.name == name for p in IOS.rglob("*")):
            problems.append(f"SECRET:  {name} must never be vendored")

    local = sorted(set(current) - set(upstream) - LOCAL_ONLY)
    if local:
        problems.append("unexpected extra files: " + ", ".join(local))

    if problems:
        for p in problems:
            print("FAIL " + p)
        return 1

    print(f"OK: {len(upstream)} files match upstream, no secrets vendored")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "sync":
        return cmd_sync()
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())
