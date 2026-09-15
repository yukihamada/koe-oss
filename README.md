# KOE OSS

**Your voice. On your device.**

KOE OSS is a local-first, open-source toolkit for speaking text in **your own
voice** — recorded, stored, and synthesized entirely on your machine.

No account. No API key. After the one-time model download, it works offline.

> **Status: early development.** The core logic (reading correction, script
> splitting, voice/consent records, job lifecycle) is implemented and tested.
> The desktop app and the on-device synthesis backend are not finished yet.
> See [docs/STATUS.md](docs/STATUS.md) for what works today.

## Why this exists

Most voice-cloning tools optimize for breadth: hundreds of languages, dozens of
engines. KOE OSS optimizes for something narrower and, we think, more
important — **your voice stays yours, and it reads what you actually wrote.**

Three commitments:

1. **Local by default.** Your recordings, your scripts, your dictionary, and
   your generated audio live on your device.
2. **Correctable readings.** When a word is misread, you fix it once and it
   stays fixed. Corrections are explicit and reviewable, never silent.
3. **Honest failures.** If a voice or language is not supported, we say so.
   We never silently substitute a different voice.

## What is implemented today

| Area | State |
|---|---|
| Reading dictionary (per-word reading overrides, audit trail) | done |
| Script splitting (sentence chunking, deterministic) | done |
| Voice registry + consent record (versioned, revocable) | done |
| Job lifecycle (`queued → preparing → generating → checking → completed`) | done |
| Capability gating (refuse unknown voice / unsupported language) | done |
| Local HTTP API (FastAPI) | done |
| On-device synthesis backend (MLX / Qwen3-TTS) | **not implemented** |
| Desktop app (Tauri) | **not implemented** |

See [docs/STATUS.md](docs/STATUS.md) for the exact boundary.

## Quickstart (core logic)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Repository layout

```
koe_oss/
  core/       pure logic — no network, no GPU, fully unit-tested
  server/     local HTTP API (FastAPI)
  engines/    synthesis backends (interface only today)
tests/        pytest suite
docs/         design, status, license notes
```

## Language support

The UI and API messages are designed for **ja** and **en** from the start.
Synthesis language support depends on the engine you install; KOE OSS reports
engine capabilities rather than guessing.

## License

- This repository: **AGPL-3.0** (see [LICENSE](LICENSE)).
- Upstream models and libraries keep their own licenses (Qwen3-TTS: Apache-2.0,
  MLX-Audio: MIT). See [docs/LICENSES.md](docs/LICENSES.md).

AGPL permits commercial use. It does not impose revenue sharing.
