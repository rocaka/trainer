"""One-time, target-bound authorization for external Skill optimization."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from threading import Lock


TTL = timedelta(minutes=5)
LOCK = Lock()
TOKENS: dict[str, tuple[str, str, datetime]] = {}


def issue(target_type: str, target_id: str) -> str:
    if target_type not in {"pending", "skill"}:
        raise ValueError("Invalid optimization target type.")
    token = secrets.token_urlsafe(32)
    with LOCK:
        TOKENS[token] = (target_type, target_id, datetime.now(timezone.utc) + TTL)
    return token


def consume(token: str, target_type: str, target_id: str) -> None:
    with LOCK:
        stored = TOKENS.pop(token, None)
    if stored is None:
        raise ValueError("Optimization authorization is missing, expired, or already used.")
    stored_type, stored_id, expires_at = stored
    if expires_at < datetime.now(timezone.utc) or stored_type != target_type or stored_id != target_id:
        raise ValueError("Optimization authorization does not match this selected Skill.")

