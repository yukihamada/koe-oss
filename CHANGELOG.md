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

## Unreleased

### Distribution workaround

No Developer ID certificate is available on the build machine, so the app
cannot be signed for distribution and Gatekeeper blocks it. The block is the
`com.apple.quarantine` attribute, not the signature: removing it lets the app
run. `scripts/install.sh` copies the app to /Applications and clears that
attribute. Verified: the app launches and serves /health.

This is a workaround, not a fix. Proper distribution still needs a Developer
ID certificate and `scripts/sign.sh sign`.

### Fixed: the app could not start after a clean install

The bundled app reported "no python with koe_oss found" even with a venv
inside it. Two separate causes:

1. `cargo tauri build` wipes Contents/Resources, so the venv created before
   the build was gone by the time the DMG was made. `scripts/sign.sh build`
   now runs `scripts/setup-python.sh` after the build, not before.
2. `find_python()` only looked for `<ancestor>/venv/bin/python`. A bundled .app
   keeps resources in Contents/Resources, so a venv there was never found.
   It now also checks `Resources/venv/bin/python`.

Also: the error message pointed at `scripts/setup-python.sh`, which did not
exist. It does now, and it has a `--check` mode.

Verified: uninstall, `brew install yukihamada/koe/koe-oss`, launch, /health
answers on 8807 with data_dir ~/.local/share/koe-oss.

### Added: speech-to-text

`koeoss transcribe <audio>` and `POST /transcribe`, both on-device via
mlx-whisper (whisper-large-v3-turbo).

Measured on ref_yuki.wav (8.26s): 3.6s, "こんばんは濱田裕樹です。今日は録音ボタンを押して収録しています。"

Kept separate from synthesis on purpose — transcription has no voice, no
enrolment and no consent, so it does not belong in that lifecycle. `/transcribe`
rejects paths outside the data dir, same as `/audio`.

Bundling note: mlx-whisper declares torch but never imports it (verified).
Removing it took the app from 1.2GB to 654MB, and the DMG to 292MB.

### Fixed after a 10-persona review

- **The shipped app could not synthesize.** `scripts/setup-python.sh` only
  installed mlx-audio behind `KOE_WITH_MLX=1`, which `sign.sh` never set, so
  the bundled venv had transcription but no TTS. Now installed by default.
  Verified: `import mlx_audio, soundfile` succeeds in the installed app, and
  /synth produced a 2.08s wav in 0.6s through the running app.
- **Revoking consent did not delete the recording.** `core/voices.py` says
  callers must delete derived data; the API returned the targets and deleted
  nothing. Worse, `ref_audio` kept the caller's external path, so the recording
  was never ours to delete. Enrollment now copies it into the data dir, and
  revoke deletes it. Verified: `removed: ['ref/yuki.wav']`.
- **Stored XSS in the UI.** Reading rules and audio paths went into innerHTML
  unescaped. Rebuilt with textContent/createElement.
- **Focus was invisible** (`outline: none`) and synthesis progress had no
  aria-live. Fixed both.
- **The README claimed 弟子屈 → テシカガ.** The measured result was テシカ川 —
  wrong in a different way. Rewritten to say what actually happens.
- Removed `tools/find_p12_password.py` and `tools/find_devid_key.sh`:
  password-guessing scripts with hardcoded personal paths, in a public repo.
- Added `--version`. Fixed `koe doctor` → `koeoss doctor` in error messages.
- `docs/STATUS.md` said 114 tests; it is 172.

### Completed the remaining review findings

- **brew install now works for everyone.** The tap was never pushed, so the
  README's install command only worked on this machine. Pushed to
  github.com/yukihamada/homebrew-koe. Verified by untapping, re-tapping from
  the remote, and installing clean.
- **LAN access is real now.** `core/pairing.py` existed and the README
  advertised iPhone access, but nothing ever bound outside loopback, so the
  feature was unreachable. Added `koeoss serve --lan`, opt-in, which prints a
  warning. Documented a threat model with no implementation behind it is worse
  than not documenting it.
- **`/synth` accepted an arbitrary `out_path`.** `/audio` and `/transcribe`
  restricted paths but synthesis did not, so an unauthenticated caller could
  write a wav anywhere. Now checked the same way. Verified: 403.
- **Pairing codes were not spent.** The docstring said "one code, one token,
  then it is spent"; the implementation returned the same pairing forever until
  it expired. Now cleared on redeem. Verified: second redeem returns None.
- **iOS provenance was undocumented.** 41 vendored Swift files with no license
  statement. The upstream had none, so LICENSES.md now states they are
  published here under AGPL-3.0 by the copyright holder, with a removal path.
- Added SECURITY.md (threat model, reporting address) and
  CODE_OF_CONDUCT.md, the latter including a clause specific to voice cloning.
- Added ROADMAP.md stating what is blocked and by what, rather than a list of
  wishes.
- pyproject.toml had no license, authors, urls, classifiers, keywords or
  readme — it could not have been published to PyPI as-is. Added, plus an
  `apple` extra so `pip install "koe-oss[apple]"` is one command.

## 0.1.1 — 2026-09-17

**The macOS app is now signed and notarized.**

```
spctl: accepted
source=Notarized Developer ID
origin=Developer ID Application: Yuki Hamada (5BV85JW8US)
```

A Developer ID Application certificate was created through the Apple
Developer site and imported with its private key. No longer blocked by
Gatekeeper on other people's Macs.

Three things had to be fixed to get notarization to pass:

- `codesign --deep` does not sign every Mach-O binary. The notary rejected
  unsigned `.so` files inside the bundled venv. Now every Mach-O file in the
  bundle is signed explicitly.
- The venv's `python` was a symlink chain out to the Homebrew prefix
  (`venv/bin/python` → `python3.12` → `/opt/homebrew/...`). Inside a bundle
  that points at a path the recipient does not have, and Gatekeeper rejected
  it as an "invalid destination for symbolic link". The links are now resolved
  to real files at build time. `readlink` alone was not enough — the chain
  needed `readlink -f`.
- The first notarization attempt returned `Invalid`; the log named the exact
  unsigned binaries.

The cask no longer needs to clear `com.apple.quarantine`, but it still does so
for anyone who installed an earlier build.
