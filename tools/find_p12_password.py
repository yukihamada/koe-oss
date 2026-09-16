#!/usr/bin/env python3
"""Try to open a password-protected .p12 by harvesting candidate passwords.

Written for iCloud's 証明書.p12, which is the only file on this machine that
might contain the Developer ID Application private key.

Two things had to be worked out first:

1. The file is PKCS#12 in the OLD format — `pbeWithSHA1And40BitRC2-CBC`.
   OpenSSL 3.x refuses it outright with "Algorithm (RC2-40-CBC): unsupported".
   It needs `-legacy` AND `-provider legacy -provider default`. Without both
   you get "unsupported", never "wrong password", so it looks like the file is
   unreadable when it is only missing a flag.

2. `-nomacver` skips the MAC check, so a wrong password surfaces as a decrypt
   error rather than a MAC error — which is the signal we actually want.

Harvesting: any token appearing on a history line or config line that mentions
p12 / pkcs12 / Developer ID / 証明書, plus name and date combinations.

Result: not found. 270 candidates tried, none open it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

P12 = "/Users/yukihamada/Library/Mobile Documents/com~apple~CloudDocs/Documents/証明書.p12"

HISTORIES = [
    "~/.zsh_history",
    "~/.bash_history",
    "~/.config/fish/fish_history",
    "~/.local/share/fish/fish_history",
    "~/.python_history",
]

SCAN_ROOTS = ["~", "~/Desktop", "~/Downloads", "~/Documents", "~/workspace"]
SKIP_DIRS = {"node_modules", ".git", ".venv", "target", ".build", "venv",
             "Library", "Applications", ".cargo"}
EXTS = (".sh", ".py", ".yml", ".yaml", ".env", ".fish", ".md", ".txt",
        ".json", ".conf", ".rb")

TOKEN = re.compile(r"[\w\-./@#$%^&*!?]{3,40}")
ASSIGN = re.compile(
    r"(?:PASS|PASSWORD|pass|password|pw|secret)\s*[=:]\s*['\"]?([^\s'\"]{1,40})")
PASSIN = re.compile(r"-pass(?:in|out)?[ =]+(?:pass:)?(\S+)")
MENTION = re.compile(r"p12|pkcs12|Developer ID|証明書", re.I)


def harvest() -> set[str]:
    cands: set[str] = set()

    def add(x: str) -> None:
        x = str(x).strip().strip("\"'").strip()
        if 0 < len(x) < 64:
            cands.add(x)

    for h in HISTORIES:
        p = os.path.expanduser(h)
        if not os.path.exists(p):
            continue
        try:
            lines = open(p, errors="ignore").read().splitlines()
        except OSError:
            continue
        for line in lines:
            if MENTION.search(line):
                for m in TOKEN.finditer(line):
                    add(m.group(0))

    for r in SCAN_ROOTS:
        r = os.path.expanduser(r)
        if not os.path.isdir(r):
            continue
        for dp, dn, fn in os.walk(r):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for f in fn:
                if not f.endswith(EXTS):
                    continue
                path = os.path.join(dp, f)
                try:
                    text = open(path, errors="ignore").read()
                except OSError:
                    continue
                if not MENTION.search(text):
                    continue
                for line in text.splitlines():
                    for m in ASSIGN.finditer(line):
                        add(m.group(1))
                    for m in PASSIN.finditer(line):
                        add(m.group(1))

    for x in ["", "password", "1234", "123456", "koe", "yuki", "hamada",
              "yukihamada", "apple", "Apple", "mac", "Mac", "cert", "p12",
              "export", "import", "Yuki", "Hamada", "koeoss", "KOE", "0000",
              "1111", "8888", "6666", "sente", "Sente", "enabler", "Enabler",
              "jiuflow", "JiuFlow", "mu", "MU", "developer", "Developer",
              "dev", "Dev", "dist", "Dist", "keychain", "Keychain", "secret",
              "Secret", "test", "Test", "temp", "Temp", "1", "12", "123",
              "12345", "1234567", "12345678", "123456789", "1234567890",
              "qwerty", "abc123", "letmein", "welcome", "admin", "root",
              "user", "pass", "apple123", "Apple123", "Yuki123", "yuki123",
              "hamada123", "Hamada123", "iphone", "iPhone", "ios", "iOS",
              "xcode", "Xcode"]:
        add(x)

    for p1 in ["yuki", "hamada", "yukihamada", "Yuki", "Hamada", "YukiHamada"]:
        for p2 in ["", "1", "12", "123", "1234", "0520", "0907", "2026",
                   "2025", "!", "!!", "123!"]:
            add(p1 + p2)

    return cands


def try_open(pw: str) -> str | None:
    # -legacy + -provider legacy are both required for RC2-40-CBC.
    # -nomacver makes a wrong password fail at decrypt, which is the
    # signal we test for.
    r = subprocess.run(
        ["openssl", "pkcs12", "-in", P12, "-legacy", "-nomacver", "-nokeys",
         "-passin", f"pass:{pw}", "-provider", "legacy", "-provider", "default"],
        capture_output=True, text=True,
    )
    return r.stdout if r.returncode == 0 and "subject" in r.stdout else None


def main() -> int:
    if not os.path.exists(P12):
        print("p12 not present")
        return 1
    cands = harvest()
    print(f"candidates: {len(cands)}", flush=True)
    for pw in sorted(cands, key=lambda s: (len(s), s)):
        out = try_open(pw)
        if out:
            path = "/tmp/p12pass"
            open(path, "w").write(pw)
            os.chmod(path, 0o600)
            print(f"FOUND (length {len(pw)}); written to {path} (0600)")
            for line in out.splitlines():
                if any(k in line for k in ("subject", "friendlyName", "issuer")):
                    print("  " + line.strip())
            return 0
    print("NOT FOUND")
    return 1


if __name__ == "__main__":
    sys.exit(main())
