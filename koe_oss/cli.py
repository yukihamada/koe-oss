"""Command line interface.

    koeoss doctor                     is this machine able to run KOE?
    koeoss voices                     list registered voices
    koeoss enroll <handle> <wav>      register a voice from a recording
    koeoss consent <handle>           grant consent (required before synthesis)
    koeoss say <handle> <text>        synthesize text to a wav
    koeoss speak-file <handle> <file> synthesize a whole file, resumably
    koeoss readings                   list reading rules
    koeoss set-reading <word> <kana>  add a reading rule
    koeoss serve                      run the local API

The command is `koeoss`, not `koe`: `koe` is already taken by Sente on this
machine, and silently overwriting an existing command would be hostile.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Set before any model library is imported: without this, huggingface_hub
# writes progress bars and transformers writes load warnings straight to the
# terminal, which makes the CLI output unusable in scripts and pipes.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BAR", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# huggingface_hub writes download progress bars to stderr. HF_HUB_DISABLE_
# PROGRESS_BAR is not honoured by every version (1.31 ignores it), and there is
# no public API to turn them off, so we filter them at the stream level while
# a model is loading. User-facing output goes to stdout and is untouched.
class _Quiet:
    """Suppress library noise while a model loads.

    Model libraries print progress bars and load notices to both stdout and
    stderr, which makes `koeoss say` unusable in a pipe. We wrap both streams
    during synthesis only; our own output is printed outside that window.
    """

    def __init__(self, stream):
        self._stream = stream

    def __getattr__(self, name):
        return getattr(self._stream, name)

    _NOISE = (
        "it/s]", "s/it]", "B/s]", "\r",
        "Initialized encoder codebooks",
        "Loaded speech tokenizer from",
        "You are using a model of type",
        "clean_up_tokenization_spaces",
    )

    def write(self, s):
        if any(n in s for n in self._NOISE):
            return len(s)
        # Swallowing noise leaves behind the blank lines it would have printed.
        if s.strip() == "":
            return len(s)
        return self._stream.write(s)

    def flush(self):
        return self._stream.flush()


def _quiet(on: bool) -> None:
    if on:
        if not isinstance(sys.stderr, _Quiet):
            sys.stderr = _Quiet(sys.stderr)
        if not isinstance(sys.stdout, _Quiet):
            sys.stdout = _Quiet(sys.stdout)
    else:
        if isinstance(sys.stderr, _Quiet):
            sys.stderr = sys.stderr._stream
        if isinstance(sys.stdout, _Quiet):
            sys.stdout = sys.stdout._stream

from koe_oss.core.store import Store
from koe_oss.core.voices import Voice, normalize_handle


def _engine():
    """Pick the best available engine, or None."""
    try:
        from koe_oss.engines.mlx_qwen import MlxQwenEngine

        e = MlxQwenEngine()
        return e if e.is_available() else None
    except ImportError:
        return None


def cmd_doctor(args) -> int:
    import platform

    print(f"platform : {platform.platform()}")
    print(f"python   : {sys.version.split()[0]}")
    e = _engine()
    if e is None:
        print("engine   : NONE — install mlx-audio (Apple Silicon) to synthesize")
        print("           pip install mlx-audio")
        return 1
    caps = e.capabilities()
    print(f"engine   : {caps.name}")
    print(f"languages: {', '.join(sorted(caps.languages))}")
    print(f"clone    : {'yes' if caps.supports_clone else 'no'}")
    return 0


def cmd_voices(args) -> int:
    reg = Store().load_voices()
    if not len(reg):
        print("no voices registered")
        return 0
    for v in reg.all():
        print(f"{v.handle:20s} {v.consent_state:8s} {v.lang}  {v.ref_audio}")
    return 0


def cmd_enroll(args) -> int:
    handle = normalize_handle(args.handle)
    if not handle:
        print("invalid handle", file=sys.stderr)
        return 1
    ref = Path(args.wav).expanduser()
    if not ref.exists():
        print(f"not found: {ref}", file=sys.stderr)
        return 1
    store = Store()
    reg = store.load_voices()
    if handle in reg:
        print(f"voice already exists: {handle}", file=sys.stderr)
        return 1
    v = Voice(handle=handle, ref_audio=str(ref), ref_text=args.text or "", lang=args.lang)
    reg.add(v)
    store.save_voices(reg)
    print(f"registered {handle}")
    print("grant consent before synthesizing:")
    print(f"  koeoss consent {handle}")
    return 0


def cmd_consent(args) -> int:
    store = Store()
    reg = store.load_voices()
    try:
        v = reg.grant_consent(args.handle, age_ok=True, consented_by="self")
    except KeyError:
        print(f"unknown voice: {args.handle}", file=sys.stderr)
        return 1
    store.save_voices(reg)
    print(f"consent granted for {v.handle} ({v.consent_state})")
    return 0


def cmd_say(args) -> int:
    e = _engine()
    if e is None:
        print("no synthesis engine available — run: koe doctor", file=sys.stderr)
        return 1
    store = Store()
    reg = store.load_voices()
    v = reg.get(args.handle)
    if v is None:
        print(f"unknown voice: {args.handle}", file=sys.stderr)
        return 1

    from koe_oss.core.capabilities import CapabilityError, check_can_synthesize

    try:
        lang = check_can_synthesize(v, e.capabilities(), args.text, args.lang)
    except CapabilityError as exc:
        print(f"cannot synthesize: {exc.message}", file=sys.stderr)
        return 1

    spoken = store.load_readings().apply(args.text)
    out = Path(args.out).expanduser() if args.out else (
        store.dir / "audio" / v.handle / "out.wav")
    out.parent.mkdir(parents=True, exist_ok=True)

    from koe_oss.engines.base import SynthRequest

    print(f"speaking ({lang}): {spoken}")
    _quiet(True)
    try:
        result = e.synthesize(SynthRequest(
            text=spoken, lang=lang, ref_audio=v.ref_audio,
            ref_text=v.ref_text, out_path=str(out)))
    finally:
        _quiet(False)
    print(f"wrote {result.audio_path}  {result.duration_sec:.2f}s  ({result.gen_sec:.2f}s)")
    return 0


def cmd_speak_file(args) -> int:
    """Synthesize a whole text file, resumably."""
    e = _engine()
    if e is None:
        print("no synthesis engine available — run: koe doctor", file=sys.stderr)
        return 1
    src = Path(args.file).expanduser()
    if not src.exists():
        print(f"not found: {src}", file=sys.stderr)
        return 1
    store = Store()
    reg = store.load_voices()
    v = reg.get(args.handle)
    if v is None:
        print(f"unknown voice: {args.handle}", file=sys.stderr)
        return 1

    from koe_oss.core.longform import synthesize_longform

    workdir = Path(args.out).expanduser() if args.out else (
        store.dir / "books" / Path(args.file).stem)
    text = src.read_text(encoding="utf-8")
    r = synthesize_longform(
        e, v, text, workdir,
        dictionary=store.load_readings(),
        max_chars=args.max_chars,
    )
    print(f"chunks   : {len(r.chunk_paths)} (resumed {r.resumed})")
    print(f"state    : {r.job.state}")
    if r.merged_path:
        print(f"merged   : {r.merged_path}")
    for err in r.errors:
        print(f"error    : {err}", file=sys.stderr)
    return 0 if r.ok else 1


def cmd_serve(args) -> int:
    """Run the local API. Binds to loopback only."""
    import uvicorn

    uvicorn.run(
        "koe_oss.server.api:app",
        host="127.0.0.1",
        port=args.port,
        log_level=args.log_level,
    )
    return 0


def cmd_readings(args) -> int:
    d = Store().load_readings()
    applied = d.applied_entries()
    proposed = d.proposed_entries()
    if not applied and not proposed:
        print("no reading rules")
        return 0
    for e in applied:
        print(f"  {e.word} -> {e.reading}")
    for e in proposed:
        print(f"? {e.word} -> {e.reading}  (proposed, not applied)")
    return 0


def cmd_set_reading(args) -> int:
    store = Store()
    d = store.load_readings()
    d.set_reading(args.word, args.reading)
    store.save_readings(d)
    print(f"{args.word} -> {args.reading}")
    return 0


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="koeoss", description="KOE OSS command line")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("voices").set_defaults(fn=cmd_voices)

    e = sub.add_parser("enroll")
    e.add_argument("handle")
    e.add_argument("wav")
    e.add_argument("--text", default="", help="transcript of the recording")
    e.add_argument("--lang", default="ja")
    e.set_defaults(fn=cmd_enroll)

    c = sub.add_parser("consent")
    c.add_argument("handle")
    c.set_defaults(fn=cmd_consent)

    s = sub.add_parser("say")
    s.add_argument("handle")
    s.add_argument("text")
    s.add_argument("--lang", default=None)
    s.add_argument("--out", default=None)
    s.set_defaults(fn=cmd_say)

    sf = sub.add_parser("speak-file")
    sf.add_argument("handle")
    sf.add_argument("file")
    sf.add_argument("--out", default=None, help="output directory")
    sf.add_argument("--max-chars", type=int, default=80)
    sf.set_defaults(fn=cmd_speak_file)

    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8807)
    sv.add_argument("--log-level", default="info")
    sv.set_defaults(fn=cmd_serve)

    sub.add_parser("readings").set_defaults(fn=cmd_readings)

    r = sub.add_parser("set-reading")
    r.add_argument("word")
    r.add_argument("reading")
    r.set_defaults(fn=cmd_set_reading)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
