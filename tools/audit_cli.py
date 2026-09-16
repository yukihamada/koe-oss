"""Exercise every CLI subcommand end to end and fail on any regression.

This is the release gate for the command line. It runs the real commands as a
user would (subprocess, not in-process), in a throwaway data directory, and
checks both output and exit codes.

    python tools/audit_cli.py            # full audit (synthesizes audio)
    python tools/audit_cli.py --no-synth # skip the slow synthesis steps
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
REF = Path.home() / "voice-clone/ref_yuki.wav"
REF_TEXT = "こんばんは、はまだゆうきです。今日は録音ボタンを押して収録しています。"

results: list[tuple[str, bool, str]] = []


def run(args: list[str], data_dir: Path, timeout: int = 300):
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
        "HOME": str(Path.home()),
        "KOE_DATA_DIR": str(data_dir),
        "PYTHONPATH": str(ROOT),
    }
    return subprocess.run(
        [PY, "-m", "koe_oss.cli", *args],
        capture_output=True, text=True, env=env, timeout=timeout, cwd=str(ROOT),
    )


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def main() -> int:
    do_synth = "--no-synth" not in sys.argv
    if not REF.exists():
        print(f"SKIP: reference audio missing at {REF}")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="koe-audit-"))
    try:
        # --- help
        r = run(["--help"], tmp)
        check("help lists subcommands", r.returncode == 0 and "doctor" in r.stdout)
        for sub in ["doctor", "voices", "enroll", "consent", "say",
                    "speak-file", "readings", "set-reading", "serve"]:
            check(f"help mentions {sub}", sub in r.stdout)

        # --- doctor
        r = run(["doctor"], tmp)
        check("doctor rc=0", r.returncode == 0, r.stdout[:60])
        check("doctor reports engine", "engine" in r.stdout.lower())

        # --- empty states
        r = run(["voices"], tmp)
        check("voices empty rc=0", r.returncode == 0 and "no voices" in r.stdout)
        r = run(["readings"], tmp)
        check("readings empty rc=0", r.returncode == 0 and "no reading" in r.stdout)

        # --- enroll
        r = run(["enroll", "yuki", str(REF), "--text", REF_TEXT], tmp)
        check("enroll rc=0", r.returncode == 0, r.stdout[:60])
        check("enroll prints consent hint", "consent" in r.stdout.lower())

        r = run(["enroll", "yuki", str(REF)], tmp)
        check("duplicate enroll rc=1", r.returncode == 1, r.stderr[:60])

        r = run(["enroll", "!!!", str(REF)], tmp)
        check("bad handle rc=1", r.returncode == 1)

        r = run(["enroll", "ghost", "/tmp/definitely-missing.wav"], tmp)
        check("missing file rc=1", r.returncode == 1)

        # --- consent gate
        r = run(["say", "yuki", "こんにちは"], tmp, timeout=60)
        check("say before consent rc=1", r.returncode == 1, r.stderr[:80])
        check("say before consent explains", "consent" in r.stderr.lower())

        r = run(["consent", "yuki"], tmp)
        check("consent rc=0", r.returncode == 0, r.stdout[:60])
        check("consent reports current", "current" in r.stdout)

        r = run(["consent", "ghost"], tmp)
        check("consent unknown voice rc=1", r.returncode == 1)

        # --- readings
        r = run(["set-reading", "弟子屈", "テシカガ"], tmp)
        check("set-reading rc=0", r.returncode == 0)
        r = run(["readings"], tmp)
        check("readings lists rule", "弟子屈" in r.stdout and "テシカガ" in r.stdout)

        # --- voices listing
        r = run(["voices"], tmp)
        check("voices lists yuki", "yuki" in r.stdout, r.stdout[:60])
        check("voices shows consent state", "current" in r.stdout)

        # --- synthesis
        if do_synth:
            out = tmp / "say.wav"
            r = run(["say", "yuki", "弟子屈は静かな村です。", "--out", str(out)],
                    tmp, timeout=600)
            check("say rc=0", r.returncode == 0, r.stderr[:80])
            check("say writes wav", out.exists() and out.stat().st_size > 1000,
                  f"{out.stat().st_size if out.exists() else 0}B")
            check("say applies reading", "テシカガ" in r.stdout, r.stdout[:80])

            # --- long form
            book = tmp / "book.txt"
            book.write_text("一です。二です。三です。\n四です。五です。\n", encoding="utf-8")
            outdir = tmp / "book"
            r = run(["speak-file", "yuki", str(book), "--out", str(outdir)],
                    tmp, timeout=900)
            check("speak-file rc=0", r.returncode == 0, r.stderr[:80])
            check("speak-file merges", (outdir / "merged.wav").exists())

            # resume: second run should reuse everything
            r = run(["speak-file", "yuki", str(book), "--out", str(outdir)],
                    tmp, timeout=900)
            check("speak-file resumes", "resumed 5" in r.stdout, r.stdout[:80])
        else:
            print("SKIP synthesis (--no-synth)")

        # --- unknown voice paths
        r = run(["say", "ghost", "hi"], tmp, timeout=60)
        check("say unknown voice rc=1", r.returncode == 1)

        # --- serve (starts a server; verify it answers, then stop it)
        import time

        import httpx

        # Pick a free port: a fixed one eventually collides with something
        # already running on this machine, which looks like a product bug.
        import socket

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        log_path = str(tmp / "serve.log")
        proc = subprocess.Popen(
            [PY, "-m", "koe_oss.cli", "serve", "--port", str(port)],
            cwd=str(ROOT),
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
                 "HOME": str(Path.home()), "KOE_DATA_DIR": str(tmp),
                 "PYTHONPATH": str(ROOT)},
            stdout=subprocess.DEVNULL, stderr=open(log_path, "w"), text=True,
        )
        try:
            up = False
            for _ in range(60):
                try:
                    r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
                    up = r.status_code == 200 and r.json().get("ok") is True
                    if up:
                        break
                except Exception:
                    time.sleep(0.5)
            if not up:
                try:
                    err = Path(log_path).read_text()[-300:]
                except OSError:
                    err = "no log"
                check("serve answers /health", False, f"port {port}: {err}")
            else:
                check("serve answers /health", True, f"port {port}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} passed")
    if bad:
        print("FAILED: " + ", ".join(bad))
        return 1
    print("CLI AUDIT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
