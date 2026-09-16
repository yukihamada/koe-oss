# Roadmap

Honest about what is blocking what.

## Done

- Voice enrolment, consent gate, revocation that deletes the recording
- Reading correction (word → reading) with an audit trail
- Long-form synthesis with resume
- Speech-to-text (`koeoss transcribe`, `POST /transcribe`)
- CLI, local HTTP API, macOS desktop app
- Homebrew cask

## Next

1. **Sign the macOS app** — blocked.
   A Developer ID Application certificate exists on the Apple account
   (serial `1806962DB8525717`), but its private key is not on the build
   machine. Creating a new one requires the Account Holder
   (`403 FORBIDDEN_ERROR`), and Apple never returns private keys.
   *Unblocked by:* exporting the existing certificate as a `.p12` from the Mac
   that created it, then `./scripts/sign.sh sign`.

2. **Pairing over LAN** — partially done.
   `core/pairing.py` is implemented and tested, and `koeoss serve --lan` now
   provides the route to it. What is not verified: pairing from a real iPhone.
   *Unblocked by:* testing on a device.

3. **Measure the 1.7B model.** Only 0.6B has been measured. Larger is likely
   better quality; nobody has checked.

4. **Quality metrics.** There is no measure of how similar the output sounds to
   the reference voice. `docs/STATUS.md` concludes that automated ASR checking
   of kana is unreliable, so this needs a different approach.

## Considering

- Windows and Linux. Untested; the engine is Apple Silicon only today.
- Streaming synthesis. Currently blocking and returns a whole file.
- Prosody controls (speed, pitch). Not exposed by the engine yet.
- A Python API (`from koe_oss import speak`) rather than CLI-only.

## Not planned

- A hosted service. The point is that nothing leaves the machine.
- Bundling model weights. They are large; download on first use.
