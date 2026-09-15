"""Check our contract against the real hosted service's own records.

`koe-edge/src/consent.js` is the authoritative consent implementation for the
hosted KOE service. This script feeds its CONSENT_VERSION and record shape
through koe_oss.core.interop and reports whether they agree.

It reads the file, it does not import it (that file is ESM for Workers).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from koe_oss.core.interop import CONSENT_VERSION, consent_state, parse_consent  # noqa: E402

EDGE_CONSENT = Path.home() / "workspace/koe-edge/src/consent.js"


def main() -> int:
    if not EDGE_CONSENT.exists():
        print(f"SKIP: {EDGE_CONSENT} not found")
        return 0

    src = EDGE_CONSENT.read_text(encoding="utf-8")
    m = re.search(r'export const CONSENT_VERSION\s*=\s*"([^"]+)"', src)
    if not m:
        print("FAIL: could not read CONSENT_VERSION from consent.js")
        return 1
    edge_version = m.group(1)

    print(f"koe-edge CONSENT_VERSION : {edge_version}")
    print(f"koe-oss  CONSENT_VERSION : {CONSENT_VERSION}")
    agree = edge_version == CONSENT_VERSION
    print(f"{'MATCH' if agree else 'DRIFT'}")

    # Field names the hosted implementation writes.
    fields = sorted(set(re.findall(r"rec\.(\w+)\s*=", src)))
    print(f"hosted consent fields    : {fields}")

    # A record shaped exactly like the hosted one must parse and be 'current'.
    hosted = {
        "consent_version": edge_version,
        "consent_at": 1757900000.0,
        "age_ok": True,
        "consent_by": "self",
    }
    parsed = parse_consent(hosted)
    state = consent_state(hosted)
    print(f"parse hosted record      : {'ok' if parsed else 'FAILED'}")
    print(f"state with matching ver  : {state}")

    ok = agree and parsed is not None and state == "current"
    print("\nOK" if ok else "\nDRIFT — the two implementations disagree")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
