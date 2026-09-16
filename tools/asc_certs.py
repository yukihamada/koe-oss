"""Query the App Store Connect API for code-signing certificates.

Read-only. Prints what certificates exist on the account so we can tell, from
the CLI, whether a Developer ID Application certificate is even available —
and if not, what is.

Measured on this account: a DEVELOPER_ID_APPLICATION certificate DOES exist
("Developer ID Application: Yuki Hamada", serial 1806962DB8525717, valid to
2027-02-01). Its private key is not on this machine. Creating a *new* one from
the CLI returns 403: "This operation can only be performed by the Account
Holder" — the API key here has developer, not Account Holder, scope. So the
certificate exists but cannot be brought here without a .p12 export.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import jwt

BASE = "https://api.appstoreconnect.apple.com/v1"


def token() -> str:
    cfg = json.loads(Path.home().joinpath(".appstoreconnect/api_key.json").read_text())
    key = Path.home() / f"private_keys/AuthKey_{cfg['key_id']}.p8"
    return jwt.encode(
        {
            "iss": cfg["issuer_id"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 1200,
            "aud": "appstoreconnect-v1",
        },
        key.read_text(),
        algorithm="ES256",
        headers={"kid": cfg["key_id"]},
    )


def get(path: str) -> dict:
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": f"Bearer {token()}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        print(f"HTTP {e.code}: {body}")
        raise SystemExit(1)


def main() -> int:
    cfg = json.loads(Path.home().joinpath(".appstoreconnect/api_key.json").read_text())
    print(f"key_id    : {cfg['key_id']}")
    print(f"issuer_id : {cfg['issuer_id']}")
    print()

    data = get("/certificates")
    certs = data.get("data", [])
    print(f"certificates on account: {len(certs)}")
    print()
    for c in certs:
        a = c["attributes"]
        print(f"  {a.get('certificateType')}")
        print(f"    name       : {a.get('name')}")
        print(f"    serial     : {a.get('serialNumber')}")
        print(f"    expires    : {a.get('expirationDate')}")
        print(f"    displayName: {a.get('displayName')}")
        print()

    dev_id = [c for c in certs
              if c["attributes"].get("certificateType") == "DEVELOPER_ID_APPLICATION"]
    if dev_id:
        a = dev_id[0]["attributes"]
        print("FOUND: Developer ID Application exists on the Apple account:")
        print(f"  name    : {a.get('name')}")
        print(f"  serial  : {a.get('serialNumber')}")
        print(f"  expires : {a.get('expirationDate')}")
        print()
        print("But it is NOT on this machine. The private key lives in the")
        print("keychain of whichever Mac created it, and the API cannot return")
        print("a private key. Creating a fresh certificate from the CLI is")
        print("refused (403: Account Holder only).")
        print()
        print("To bring it here: on the Mac that has it, Keychain Access ->")
        print("export the certificate WITH its private key as .p12, then:")
        print("  security import cert.p12 -P <pass> -T /usr/bin/codesign")
        return 1

    print("No DEVELOPER_ID_APPLICATION certificate on this account.")
    print("It must be created at:")
    print("  https://developer.apple.com/account/resources/certificates/add")
    return 1


if __name__ == "__main__":
    sys.exit(main())
