# Status — what actually works

Last verified: 2026-09-15, Apple M5 Max (arm64), macOS 26.4.1.

This file exists so nobody has to guess. Everything below was run on this
machine; nothing here is inherited from a description of someone else's run.

## Verified working

| Claim | Evidence |
|---|---|
| Core logic is correct and deterministic | `92 passed` (`pytest`) |
| On-device voice cloning produces audio | see Measurements below |
| Reading dictionary changes what is spoken | see Reading correction below |
| Capability gate refuses instead of substituting | `tests/test_capabilities.py`, `tests/test_api.py` |
| Job state machine keeps partial progress on failure | `tests/test_jobs.py::test_partial_progress_survives_failure` |

## Not implemented

- **Desktop app (Tauri).** No UI exists. The HTTP API is the only interface.
- **Synthesis engine inside `koe_oss`.** `koe_oss/engines/base.py` defines the
  interface only. The measurements below were produced by scripts in `tools/`
  that call MLX-Audio directly; they are not wired into the API yet.
- **Persistence.** Voices, dictionary and jobs live in process memory. A
  restart clears them.
- **Installer / signed build / release artifacts.** None.
- **Windows and Linux.** Untested. The core logic is platform-independent, but
  no non-macOS run has been made.

## Measurements

Model: `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16`
Reference: an 8.26 s, 24 kHz recording of one speaker.

| text (chars) | audio | generation | realtime factor |
|---|---|---|---|
| 15 | 1.76 s | 3.30 s | 1.88 |
| 17 | 3.44 s | 0.93 s | 0.27 |
| 21 | 3.52 s | 0.92 s | 0.26 |

- Model load: **18.97 s** (first run; includes tokenizer init).
- Peak memory: **6.6 GB**.
- The 1.88× first row is warm-up, not steady state. Rows 2–3 (~0.26×) are the
  meaningful number, but they come from three consecutive short runs and are
  **not** a sustained-throughput measurement.

Reproduce: `python tools/measure_local.py`

## Reading correction — what we actually learned

We transcribed our own output with Whisper (`large-v3-turbo`) to see what the
model really said.

| input | heard (no dictionary) |
|---|---|
| 弟子屈は北海道に… | 弟子**靴**は北海道に… |
| 焚き火を囲んで… | 焚火を囲んで… |
| 市場で買い物を… | 市場で買い物を… |
| 毎月一日に支払います | 毎月**1日**に支払います |

So the misreads are real. Applying the dictionary changed the output:

| rule | heard (with dictionary) |
|---|---|
| 弟子屈 → テシカガ | テシカ**川**北海道に… |
| 焚き火 → タキビ | 焚火を囲んで… |

Two honest conclusions:

1. **The dictionary demonstrably changes what is spoken.** 弟子靴 became
   テシカ川 — wrong in a *different* way, but proof the correction reaches the
   model rather than being discarded.
2. **Automated ASR verification of kana readings is not reliable.** Whisper
   normalises kana back to kanji (タキビ → 焚火) and confuses ガ with 川. A
   green/red verdict from this pipeline would be noise.

This is why the design says readings are **proposed**, then **confirmed by a
human** — not auto-applied on a checker's word. The checker narrows the search;
it does not close it.

## Known limitations

- `mlx_audio` emits an unrelated transformers warning on load. Harmless.
- Only `ja` was measured. Other languages are untested.
- Only the 0.6B model was measured. 1.7B is untested.
- Whisper transcription of numbers is unreliable (毎月一日 → 毎月1日), so
  number readings are marked unverifiable rather than pass/fail.
