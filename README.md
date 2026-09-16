# KOE OSS

**Your voice. On your device.**

KOE OSS is a local-first, open-source toolkit for speaking text in **your own
voice** — recorded, stored, and synthesized entirely on your machine.

No account. No API key. After the one-time model download, it works offline.

> **Status: early development.** The core logic, the MLX engine, the CLI, the
> local HTTP API and a macOS desktop app all work and are tested against real
> audio. **The app is not signed or notarized**, so it only opens on the machine
> that built it. Windows and Linux are untested. See
> [docs/STATUS.md](docs/STATUS.md) for exactly what is verified and what is not.

## Quickstart (Apple Silicon)

```bash
pip install -e ".[dev]"
pip install mlx-audio          # the synthesis engine
koeoss doctor                  # is this machine ready?
```

Register a voice and speak:

```bash
koeoss enroll yuki ~/my-voice.wav --text "what you said in the recording"
koeoss consent yuki            # required before any synthesis
koeoss say yuki "こんにちは、これは私の声です。"
```

Fix a misread once, permanently:

```bash
koeoss set-reading 弟子屈 テシカガ
koeoss say yuki "弟子屈は北海道にある静かな村です。"
# -> speaks テシカガは北海道にある静かな村です。
```

Synthesize a whole file, resumably:

```bash
koeoss speak-file yuki book.txt --out ./book
```

Or run the local API (binds to 127.0.0.1 only):

```bash
koeoss serve                   # or: uvicorn koe_oss.server.api:app
```

> The command is **`koeoss`**, not `koe`. `koe` is already used by Sente on this
> machine, and overwriting an existing command would be hostile.

## Why this exists

Most voice-cloning tools optimize for breadth: hundreds of languages, dozens of
engines. KOE OSS optimizes for something narrower — **your voice stays yours,
and it reads what you actually wrote.**

1. **Local by default.** Recordings, scripts, dictionary and generated audio
   live on your device.
2. **Correctable readings.** When a word is misread you fix it once and it
   stays fixed. Corrections are explicit and reviewable, never silent.
3. **Honest failures.** If a voice or language is unsupported, KOE says so. It
   never silently substitutes a different voice.

## What works today

| Area | State |
|---|---|
| Reading dictionary (overrides + audit trail) | done |
| Script splitting (deterministic, resumable) | done |
| Voice registry + versioned consent, revocation | done |
| Job lifecycle with partial progress on failure | done |
| Capability gating (refuse, never substitute) | done |
| JSON persistence (atomic writes) | done |
| MLX / Qwen3-TTS engine (Apple Silicon) | done |
| CLI (`koe doctor/enroll/say/...`) | done |
| Local HTTP API (FastAPI) | done |
| Desktop app (Tauri, macOS) | done — unsigned |
| Shared contract with the hosted KOE service | done |
| LAN pairing (use the Mac voice from iOS) | done |
| Windows / Linux / NVIDIA | **not implemented** |

## Measured on Apple M5 Max

Model load 18.97 s · peak memory 6.6 GB · realtime factor ~0.26 on short
sentences. Full numbers and the commands that produced them are in
[docs/STATUS.md](docs/STATUS.md).

## Repository layout

```
koe_oss/
  core/       pure logic — no network, no GPU, fully unit-tested
  server/     local HTTP API (FastAPI)
  engines/    synthesis backends (MLX/Qwen3-TTS today)
  cli.py      command line interface
tools/        measurement and verification scripts
tests/        pytest suite (114 tests)
docs/         status, licenses
```

## Language support

The CLI and API are designed for **ja** and **en** from the start. Synthesis
language support depends on the engine; KOE reports engine capabilities rather
than guessing. Only Japanese has been measured end-to-end.

## Related

How this fits with the hosted service and the iOS app — shared data contract,
LAN pairing, and what is deliberately *not* unified:
[docs/INTEGRATION.md](docs/INTEGRATION.md).

## License

- This repository: **AGPL-3.0** (see [LICENSE](LICENSE)).
- Upstream models keep their own licenses (Qwen3-TTS: Apache-2.0, MLX-Audio:
  MIT). See [docs/LICENSES.md](docs/LICENSES.md).

AGPL permits commercial use. It does not impose revenue sharing.

## Desktop app (macOS, Apple Silicon)

```bash
python3 -m venv venv && ./venv/bin/pip install -e . && ./venv/bin/pip install mlx-audio
cargo install tauri-cli --version "^2"
cd app/src-tauri && cargo tauri build --bundles app
open target/release/bundle/macos/KOE.app
```

The app finds a Python that can import `koe_oss`, starts the API on
`127.0.0.1:8807`, and stops it when the window closes. Override the interpreter
with `KOE_PYTHON` and the port with `KOE_API_PORT`.

**The build is unsigned and not notarized.** macOS will block it on any machine
other than the one that built it. Signing requires an Apple Developer
certificate and is not set up here.
