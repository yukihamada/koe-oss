# Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Run the API (binds to 127.0.0.1 only):

```bash
uvicorn koe_oss.server.api:app --port 8787
```

## Layout

- `koe_oss/core/` — pure logic. No I/O, no network, no GPU. This is where the
  behaviour that makes KOE KOE lives: reading correction, script splitting,
  consent/voice records, job lifecycle, capability gating.
- `koe_oss/server/` — FastAPI app exposing that logic over localhost.
- `koe_oss/engines/` — synthesis backends. Interface only today.
- `tools/` — measurement and verification scripts. Not part of the package.
- `tests/` — pytest. Core logic and API contract.

## Rules for contributors

1. **Core stays pure.** If a change in `core/` needs I/O, it belongs in
   `server/` or `engines/`.
2. **Never silently substitute.** If a voice or language is unsupported, raise
   `CapabilityError`. A fallback that produces plausible-but-wrong audio is a
   defect, not a convenience.
3. **Every claim needs a measurement.** Performance and quality statements go
   in `docs/STATUS.md` with the command that produced them.
4. **Tests are the spec.** New behaviour lands with a test that fails without
   it.
5. **No competitor naming in public-facing text.** Describe what KOE does, not
   what it replaces.
