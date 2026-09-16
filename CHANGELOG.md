# Changelog

## 0.1.0 — 2026-09-16

First release. Local-first synthesis in your own voice on Apple Silicon.

### What it does

- **Register a voice** from a recording and its transcript.
- **Consent gate.** A voice cannot be synthesized until consent is recorded,
  and consent can be revoked. Versioned, so an older record reads as "stale"
  rather than as no record at all.
- **Correctable readings.** Add a word → reading rule and it is applied before
  synthesis. Rules are confirmed / proposed / rejected; only confirmed rules
  change output. Every change is recorded in an audit trail.
- **Long-form synthesis** with crash-resume. Each chunk is written as it
  finishes; re-running reuses existing audio. Verified: after deleting 3 of 5
  chunks, only the missing 3 were regenerated.
- **Capability gating.** Unsupported languages and unconsented voices are
  refused with a reason code. Nothing is silently substituted.
- **CLI** (`koeoss`) and a **local HTTP API** on 127.0.0.1.
- **Desktop app** (Tauri, macOS) that starts and owns the API.
- **LAN pairing** so an iPhone can use the Mac's voice without the recording
  being uploaded anywhere.
- **Shared data contract** with the hosted KOE service.

### Measured on Apple M5 Max

| | |
|---|---|
| Model | `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16` |
| Model load | 18.97 s |
| Peak memory | 6.6 GB |
| Realtime factor | ~0.26 on short sentences |

### Known limitations

- **The macOS app is unsigned and notarized-for-nothing.** It opens only on the
  machine that built it. A Developer ID Application certificate is required to
  distribute it, and none exists on this machine yet.
- Apple Silicon only. Intel Macs, Windows and Linux are untested.
- Only Japanese is verified end to end. Other languages are declared by the
  engine but unmeasured.
- Only the 0.6B model is measured; 1.7B is untested.
- Automated read-back of kana is unreliable (Whisper normalises kana back to
  kanji), so readings are proposed and human-confirmed, not auto-applied.
- Synthesis is synchronous; a long script blocks the request.

### Verification

- 172 Python tests pass (Python 3.11 / 3.12 × ubuntu / macos).
- CLI audit: 36/36 checks against real audio.
- iOS contract: 26/26 checks against the live API.
- Interop check against `koe-edge/src/consent.js`: no drift.
