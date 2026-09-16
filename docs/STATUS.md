# Status — what actually works

Last verified: 2026-09-16, Apple M5 Max (arm64), macOS 26.4.1.

Everything below was run on this machine. Nothing is inherited from a
description of someone else's run.

## Verified working

| Claim | Evidence |
|---|---|
| Core logic is correct and deterministic | `172 passed` (`pytest`) |
| On-device voice cloning produces audio | Measurements below |
| Reading dictionary changes what is spoken | Reading correction below |
| Full path works end-to-end with the real engine | `tools/e2e_real_engine.py` → `E2E OK` |
| CLI works against real audio | `koeoss say` produced a 3.20 s / 24 kHz wav |
| Desktop app launches and brings up the API | `KOE.app` started from a clean state served `/health` on 8807 |
| DMG contains a working app | mounted, `KOE.app/Contents/MacOS/koe-oss` present, 1.6 MB |
| UI drives real synthesis | `tools/check_ui.py` 8/8 pass |
| Capability gate refuses instead of substituting | `tests/test_capabilities.py` |
| Job state machine keeps partial progress on failure | `tests/test_jobs.py` |
| State survives a restart | `tests/test_store.py`, `tests/test_api.py` |

## Not implemented

- **Signed and notarized release.** `KOE.app` and a DMG build locally, but
  neither is signed or notarized, so macOS will refuse to open them on someone
  else's machine. This is the main blocker to actually shipping.
- **Windows and Linux.** Untested. Core logic is platform-independent; the MLX
  engine is Apple-Silicon-only by nature. No non-macOS run has been made.
- **NVIDIA / CUDA backend.** The fast decoder in the hosted KOE service is
  CUDA-specific and has not been ported here.
- **Long-form pipeline** (multi-voice, chapters, dubbing). Splitting exists;
  the orchestration on top does not.
- **Windows / Linux builds.** The Tauri config is macOS-only today.
- **Streaming synthesis.** Generation is blocking and returns a whole file.

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

## End-to-end run

`tools/e2e_real_engine.py` drives the real engine through the HTTP API:

```
1. voice registered: yuki
2. consent gate blocks synthesis: ok
3. synthesized: .../out.wav   duration: 3.52 sec   gen: 1.92 sec
   corrected: True -> テシカガは北海道にある静かな村です。
4. ffprobe: sample_rate 24000, channels 1, duration 3.520000
5. state reloaded from disk: ok
E2E OK
```

## Reading correction — what we actually learned

We transcribed our own output with Whisper (`large-v3-turbo`).

| input | heard (no dictionary) |
|---|---|
| 弟子屈は北海道に… | 弟子**靴**は北海道に… |
| 焚き火を囲んで… | 焚火を囲んで… |
| 市場で買い物を… | 市場で買い物を… |
| 毎月一日に支払います | 毎月**1日**に支払います |

Applying the dictionary changed the output:

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

This is why readings are **proposed**, then **confirmed by a human** — not
auto-applied on a checker's word. The checker narrows the search; it does not
close it.

## Known limitations

- `mlx_audio` emits an unrelated transformers warning on load. Harmless.
- Only `ja` was measured end-to-end. Other languages are declared but untested.
- Only the 0.6B model was measured. 1.7B is untested.
- Whisper transcription of numbers is unreliable (毎月一日 → 毎月1日), so
  number readings are marked unverifiable rather than pass/fail.
- `/synth` is synchronous. A long script blocks the request.
