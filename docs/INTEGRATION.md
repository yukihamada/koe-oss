# KOE OSS and the rest of KOE

How this project relates to the hosted KOE service (`koe-edge`, koe.live) and
the Koe iOS app.

## The three pieces

| Piece | Where | Role |
|---|---|---|
| **KOE OSS** (this repo) | your Mac | owns the voice: recording, consent, dictionary, synthesis |
| **koe-edge** | Cloudflare Workers | hosted service: koe.live, voice messages, MCP |
| **Koe iOS** | `ios/` | phone client; can now use the Mac's local voice |

They are different things on purpose. The OSS piece exists so the voice can
stay on your device; the hosted piece exists for sharing it with other people.

## Shared data contract

`koe_oss/core/interop.py` is the single definition of the voice, consent and
reading shapes. Both sides import it so they cannot drift.

Hosted layout (R2), which the contract mirrors exactly:

```
voiceprint/<handle>.wav   reference audio
consent/<handle>          consent record
profile/<handle>.json     display name
speakervec/<handle>.json  speaker embedding (separate from the TTS reference)
```

Check for drift at any time:

```bash
python tools/check_interop.py
```

It reads `koe-edge/src/consent.js` and compares. **It found a real drift on
first run**: this repo used consent version `2026-09-15` while the service used
`2026-09-10`, which would have made every already-registered voice read as
"stale". Versions are now aligned at `2026-09-10`.

Consent field names match the hosted implementation (`consent_version`,
`consent_at`, `age_ok`, `consent_by`, `consent_operator`), and `parse_consent`
accepts both spellings so old records are read rather than dropped.

## Using the Mac voice from iOS

The model and the recording live on the Mac. Rather than upload a recording of
your voice to a server so your phone can hear it, the Mac synthesizes locally
and sends back the audio over your own network.

```
Mac:  koe-oss running, POST /pair/start -> shows a 6-character code
iOS:  enter the code -> exchanged for a token (stored in Keychain)
iOS:  POST /remote/synth with the token -> wav
```

```bash
# on the Mac
curl -X POST http://127.0.0.1:8807/pair/start -d '{"label":"iphone"}'
```

`ios/LocalVoiceClient.swift` implements the phone side.

### Threat model, stated plainly

- This exposes your voice on your LAN. **Only pair on a network you trust.**
- Traffic is plain HTTP. Do not pair over public wifi.
- The token is random, expires (15 minutes by default), and is revocable:
  `POST /pair/revoke` or `POST /pair/revoke-all`.
- It does **not** authenticate *who* holds the phone. Anyone on the LAN with
  the code has access until it expires or is revoked.
- Pairing is **off by default** — `/pair/active` returns empty until you start
  one. There is a test asserting this.
- Audio is generated on your Mac and sent to the phone. It goes nowhere else,
  but once it is on the phone we cannot recall it.

## Vendored iOS sources

`ios/Sources` and `ios/Shared` are mirrored from `~/workspace/koe-ios` by
`tools/sync_ios.py`, which records file hashes and fails on drift:

```bash
python tools/sync_ios.py check   # CI runs this
python tools/sync_ios.py sync    # re-copy and rewrite the manifest
```

A copy that silently goes stale is worse than no copy, so drift is a build
failure rather than a warning.

**`Secrets.swift` is never vendored.** Upstream it holds a personal API token
and is gitignored. Copy `Sources/Secrets.template.swift` to build locally, and
never commit the result. The check fails if a `Secrets.swift` ever appears.

## What is NOT unified

- **Accounts.** The hosted service has users and billing; this does not.
- **Revenue sharing.** A hosted-service concern, not part of the local tool.
- **The model.** Both use Qwen3-TTS, but nothing forces them to stay in step.
- **Signing.** The iOS app is signed with an Apple Distribution certificate
  that exists on this machine. The macOS app has **no** Developer ID
  certificate, so it cannot be distributed outside this Mac yet.
