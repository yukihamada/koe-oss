# KOE OSS

**Your voice. On your device.**

KOE OSS is a local-first, open-source toolkit for speaking text in **your own
voice** — recorded, stored, and synthesized entirely on your machine.

No account. No API key. After the one-time model download, it works offline.

> **Status: early development.** The core logic, the MLX engine, the CLI and the
> local HTTP API all work and are tested end-to-end against real audio. The
> desktop app and cross-platform builds do not exist yet. See
> [docs/STATUS.md](docs/STATUS.md) for exactly what is verified and what is not.

## Quickstart (Apple Silicon)

```bash
pip install -e ".[dev]"
pip install mlx-audio          # the synthesis engine
koe doctor                     # is this machine ready?
```

Register a voice and speak:

```bash
koe enroll yuki ~/my-voice.wav --text "what you said in the recording"
koe consent yuki               # required before any synthesis
koe say yuki "こんにちは、これは私の声です。"
```

Fix a misread once, permanently:

```bash
koe set-reading 弟子屈 テシカガ
koe say yuki "弟子屈は北海道にある静かな村です。"
# -> speaks テシカガは北海道にある静かな村です。
```

Or run the local API (binds to 127.0.0.1 only):

```bash
uvicorn koe_oss.server.api:app --port 8787
```

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
| Desktop app (Tauri) | **not implemented** |
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

## License

- This repository: **AGPL-3.0** (see [LICENSE](LICENSE)).
- Upstream models keep their own licenses (Qwen3-TTS: Apache-2.0, MLX-Audio:
  MIT). See [docs/LICENSES.md](docs/LICENSES.md).

AGPL permits commercial use. It does not impose revenue sharing.
