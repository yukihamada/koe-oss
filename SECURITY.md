# Security Policy

## Scope

KOE OSS runs a local HTTP API on `127.0.0.1` and handles voice recordings.
Both are security-relevant, so reports are welcome.

## Reporting

**Please do not open a public issue for a security problem.**

Email: mail@yukihamada.jp

Include what you can: what you did, what happened, what you expected, and the
version (`koeoss --version`). You will get a reply within a few days.

## The threat model this project assumes

- The API binds to `127.0.0.1` by default and has **no authentication**.
  Any process running as your user can call it — including granting consent
  or deleting a voice. This is a deliberate trade-off for a local-first tool,
  not an oversight, but it means: **do not expose this API to a network you do
  not control.**
- `koeoss serve --lan` binds to all interfaces so paired devices can reach the
  voice. It is opt-in and prints a warning. Only use it on a trusted network.
- `/audio`, `/transcribe` and `/synth` refuse paths outside the data directory.
  If you find a way around that, it is a vulnerability — please report it.

## Known limitations

- No authentication on the local API (see above).
- The distributed macOS app is ad-hoc signed, so it is not notarized. Verify
  what you run.
- Consent records are self-asserted. The software cannot verify that the person
  who enrolled a voice is the person it belongs to.

## Supported versions

Only the latest release receives fixes.
