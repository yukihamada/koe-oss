"""LAN pairing — let a phone use the voice that lives on your computer.

Why
---
The voice is registered and synthesized on the desktop, where the model and the
recording live. But you want to *hear* it on your phone. Uploading the
reference recording to a server to do that defeats the point of keeping it
local, so instead the desktop serves it to devices on your own network.

How it works
------------
1. The desktop prints a one-time pairing code (or you call /pair/start).
2. On the phone you enter that code; it exchanges for a bearer token.
3. The phone calls /remote/synth with the token; audio is generated locally
   and returned.

Threat model, stated plainly
----------------------------
- This exposes your voice over your LAN. Only do it on a network you trust.
- The token is random, time-limited, and revocable; `/pair/revoke` kills it.
- Audio is generated on this machine and sent to the phone. It is not sent
  anywhere else, but once it is on the phone we cannot recall it.
- Nothing here authenticates *who* is on the phone. Anyone on the LAN with the
  code gets access until it expires or is revoked.
"""

from __future__ import annotations

import hmac
import json
import secrets
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

__all__ = ["Pairing", "PairingStore", "DEFAULT_TTL_SEC"]

DEFAULT_TTL_SEC = 15 * 60
CODE_LEN = 6


def _new_code() -> str:
    """Numeric code, no ambiguous characters. Human-typeable from a phone."""
    alphabet = "23456789abcdefghjkmnpqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(CODE_LEN))


@dataclass
class Pairing:
    code: str
    token: str
    created_at: float
    expires_at: float
    label: str = ""
    last_used_at: Optional[float] = None
    use_count: int = 0

    def expired(self, now: Optional[float] = None) -> bool:
        return (now or time.time()) >= self.expires_at

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Pairing":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class PairingStore:
    """Active pairings, persisted so a restart does not silently un-pair."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._items: Dict[str, Pairing] = {}
        self._load()

    # ------------------------------------------------------------------ io
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for d in raw.get("pairings", []):
            try:
                p = Pairing.from_dict(d)
                if not p.expired():
                    self._items[p.token] = p
            except TypeError:
                continue

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"pairings": [p.to_dict() for p in self._items.values()]},
                       ensure_ascii=False, indent=1),
            encoding="utf-8")
        tmp.replace(self.path)

    # ------------------------------------------------------------- lifecycle
    def start(self, label: str = "", ttl: int = DEFAULT_TTL_SEC) -> Pairing:
        self.prune()
        p = Pairing(
            code=_new_code(),
            token=secrets.token_urlsafe(32),
            created_at=time.time(),
            expires_at=time.time() + ttl,
            label=label,
        )
        self._items[p.token] = p
        self._save()
        return p

    def redeem(self, code: str) -> Optional[Pairing]:
        """Exchange a code for its token. One code, one token, then it is spent."""
        self.prune()
        want = (code or "").strip().lower()
        for token, p in list(self._items.items()):
            if hmac.compare_digest(p.code.lower(), want):
                # Spend it. The docstring promised one code, one token; without
                # this the same code worked until it expired.
                p.code = ""
                self._save()
                return p
        return None

    def by_token(self, token: str) -> Optional[Pairing]:
        self.prune()
        p = self._items.get(token or "")
        if p is None or p.expired():
            return None
        return p

    def touch(self, token: str) -> None:
        p = self._items.get(token)
        if p is not None:
            p.last_used_at = time.time()
            p.use_count += 1
            self._save()

    def revoke(self, token: str) -> bool:
        if self._items.pop(token or "", None) is not None:
            self._save()
            return True
        return False

    def revoke_all(self) -> int:
        n = len(self._items)
        self._items.clear()
        self._save()
        return n

    def prune(self) -> int:
        now = time.time()
        gone = [t for t, p in self._items.items() if p.expired(now)]
        for t in gone:
            del self._items[t]
        if gone:
            self._save()
        return len(gone)

    def active(self) -> list:
        self.prune()
        return [p.to_dict() for p in self._items.values()]


def require_token(store: PairingStore, authorization: Optional[str]) -> Pairing:
    """Raise ValueError unless the header carries a live token."""
    if not authorization:
        raise ValueError("missing Authorization header")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise ValueError("expected 'Bearer <token>'")
    p = store.by_token(value)
    if p is None:
        raise ValueError("invalid or expired token")
    return p
