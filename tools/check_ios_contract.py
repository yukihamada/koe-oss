"""Verify the iOS client's contract against the live API.

The Swift file cannot be compiled into a test here (it needs XCTest and a
device SDK), so instead we assert the HTTP contract it depends on: the exact
paths, headers, status codes and JSON keys LocalVoiceClient.swift parses.

If this passes, the Swift decoder will not silently get nil for a renamed key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8807"


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return cond


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=120)
    ok = True

    # --- /pair/start : Swift decodes code / expires_at / expires_in
    r = c.post("/pair/start", json={"label": "iphone"})
    ok &= check("POST /pair/start 200", r.status_code == 200, str(r.status_code))
    body = r.json()
    ok &= check("pair/start has code", isinstance(body.get("code"), str), body.get("code", ""))
    ok &= check("pair/start has expires_at", "expires_at" in body)
    ok &= check("pair/start has expires_in", "expires_in" in body)

    # --- /pair/redeem : Swift decodes token / expires_at
    r = c.post("/pair/redeem", json={"code": body["code"]})
    ok &= check("POST /pair/redeem 200", r.status_code == 200, str(r.status_code))
    tok = r.json().get("token")
    ok &= check("redeem returns token", isinstance(tok, str) and len(tok) > 20)

    # --- /voices : Swift decodes handle / lang / consent_state
    r = c.get("/voices")
    ok &= check("GET /voices 200", r.status_code == 200)
    vs = r.json().get("voices", [])
    ok &= check("voices non-empty", len(vs) > 0, f"{len(vs)}")
    if vs:
        v = vs[0]
        for k in ("handle", "lang", "consent_state"):
            ok &= check(f"voice has {k}", k in v, k)

    # --- /remote/synth : Swift decodes all CodingKeys
    if vs:
        voice = vs[0]["handle"]
        r = c.post(
            "/remote/synth",
            json={"voice_id": voice, "text": "こんにちは、これはテストです。"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        ok &= check("POST /remote/synth 200", r.status_code == 200, r.text[:120])
        if r.status_code == 200:
            b = r.json()
            for k in ("ok", "audio_path", "duration_sec", "gen_sec",
                      "engine", "lang", "spoken", "corrected"):
                ok &= check(f"synth has {k}", k in b, k)

            # --- /audio : the follow-up fetch the client performs
            r2 = c.get("/audio", params={"path": b["audio_path"]})
            ok &= check("GET /audio 200", r2.status_code == 200, str(r2.status_code))
            ok &= check("audio has bytes", len(r2.content) > 1000, f"{len(r2.content)}B")
            ok &= check("audio is wav", r2.content[:4] == b"RIFF", str(r2.content[:4]))

    # --- 401 paths the client maps to .unauthorized
    r = c.post("/remote/synth", json={"voice_id": "yuki", "text": "x"})
    ok &= check("synth without token 401", r.status_code == 401, str(r.status_code))
    r = c.post("/remote/synth", json={"voice_id": "yuki", "text": "x"},
               headers={"Authorization": "Bearer bogus"})
    ok &= check("synth with bad token 401", r.status_code == 401, str(r.status_code))
    r = c.post("/pair/redeem", json={"code": "zzzzzz"})
    ok &= check("redeem bad code 401", r.status_code == 401, str(r.status_code))

    # --- path traversal guard
    r = c.get("/audio", params={"path": "/etc/passwd"})
    ok &= check("/audio refuses outside paths", r.status_code in (403, 404), str(r.status_code))

    print("\nOK" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
