"""Create a Developer ID Application certificate from the CLI and import it.

The account already has a Developer ID Application certificate, but its private
key is not on this machine (it lives in the keychain of whichever Mac created
it). A certificate without its key cannot sign anything.

Apple's API cannot hand back an existing private key, so this generates a new
key pair here, submits a CSR, and imports the returned certificate next to our
own key.

MEASURED: this is refused. The API returns

  403 FORBIDDEN_ERROR "This operation can only be performed by the Account
  Holder."

so creating a Developer ID certificate needs the Apple ID that owns the
account, not an API key with developer scope. The script is kept because it
reports that outcome precisely, and will work unchanged for an Account Holder
key.

The key is written to ~/.config/koe-oss/certs (outside the repo, 0700).
"""

from __future__ import annotations

import base64
import json
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.appstoreconnect.apple.com/v1"
CERT_DIR = Path.home() / ".config/koe-oss/certs"
TEAM = "5BV85JW8US"
CN = f"Developer ID Application: Yuki Hamada ({TEAM})"
SUBJ = f"/C=US/O=Yuki Hamada/OU={TEAM}/CN={CN}"


def token() -> str:
    import jwt

    cfg = json.loads((Path.home() / ".appstoreconnect/api_key.json").read_text())
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


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:600]}")
        raise SystemExit(1)


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"failed: {' '.join(cmd)}\n{p.stderr}")
        raise SystemExit(1)
    return p.stdout


def identity_present() -> bool:
    p = subprocess.run(
        ["security", "find-identity", "-v", "-p", "codesigning"],
        capture_output=True,
        text=True,
    )
    return "Developer ID Application" in p.stdout


def main() -> int:
    if identity_present():
        print("Developer ID Application identity already present.")
        return 0

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    CERT_DIR.chmod(stat.S_IRWXU)
    key = CERT_DIR / "developer_id.key"
    csr_pem = CERT_DIR / "developer_id.csr"
    csr_der = CERT_DIR / "developer_id.csr.der"
    cert = CERT_DIR / "developer_id.pem"
    p12 = CERT_DIR / "developer_id.p12"

    print(f"generating key pair in {CERT_DIR}")
    run([
        "openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(csr_pem), "-subj", SUBJ,
    ])
    run(["openssl", "req", "-in", str(csr_pem), "-outform", "DER",
         "-out", str(csr_der)])
    key.chmod(stat.S_IRUSR | stat.S_IWUSR)

    csr_b64 = base64.b64encode(csr_der.read_bytes()).decode()
    print("submitting CSR for DEVELOPER_ID_APPLICATION")
    try:
        data = post("/certificates", {
            "data": {
                "type": "certificates",
                "attributes": {
                    "certificateType": "DEVELOPER_ID_APPLICATION",
                    "csrContent": csr_b64,
                },
            }
        })
    except SystemExit:
        print()
        print("Cannot create a Developer ID certificate with this API key.")
        print("Apple requires the Account Holder. Two ways forward:")
        print()
        print("  1. Export the existing certificate (it already exists on the")
        print("     account, serial 1806962DB8525717) as a .p12 WITH its private")
        print("     key from the Mac that created it, then:")
        print("       security import cert.p12 -P <pass> -T /usr/bin/codesign")
        print()
        print("  2. Sign in as Account Holder at")
        print("     https://developer.apple.com/account/resources/certificates/add")
        raise

    a = data["data"]["attributes"]
    print(f"  id      : {data['data']['id']}")
    print(f"  name    : {a.get('name')}")
    print(f"  expires : {a.get('expirationDate')}")
    cert.write_bytes(base64.b64decode(a["certificateContent"]))
    print(f"  wrote   : {cert}")

    print("importing into keychain")
    run(["openssl", "pkcs12", "-export", "-legacy",
         "-inkey", str(key), "-in", str(cert),
         "-out", str(p12), "-passout", "pass:koe"]) if False else None
    p = subprocess.run(
        ["openssl", "pkcs12", "-export", "-legacy",
         "-inkey", str(key), "-in", str(cert),
         "-out", str(p12), "-passout", "pass:koe"],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        print("legacy p12 failed, retrying without -legacy")
        run(["openssl", "pkcs12", "-export",
             "-inkey", str(key), "-in", str(cert),
             "-out", str(p12), "-passout", "pass:koe"])

    run(["security", "import", str(p12), "-P", "koe",
         "-T", "/usr/bin/codesign", "-A"])

    if not identity_present():
        print("import reported success but no identity appeared")
        return 1

    print()
    print("OK: Developer ID Application identity available")
    run(["security", "find-identity", "-v", "-p", "codesigning"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
