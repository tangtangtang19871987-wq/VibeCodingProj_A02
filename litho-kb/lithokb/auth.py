"""Users, roles and stateless signed login tokens (stdlib only: pbkdf2 + HMAC)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from .store import KB, LOCK, atomic_write, now

ROLES = ("reader", "reviewer", "admin")
RANK = {"anonymous": 0, "reader": 1, "reviewer": 2, "admin": 3}
TOKEN_TTL = 7 * 24 * 3600


class AuthError(Exception):
    pass


def _hash(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def _check(pw: str, stored: str) -> bool:
    try:
        _, s, d = stored.split("$")
        salt = base64.b64decode(s)
    except ValueError:
        return False
    return hmac.compare_digest(_hash(pw, salt), stored)


def load_users(kb: KB) -> dict:
    p = kb.root / "users.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _save(kb: KB, users: dict) -> None:
    atomic_write(kb.root / "users.json", json.dumps(users, ensure_ascii=False, indent=2))


def public(u: dict) -> dict:
    return {k: v for k, v in u.items() if k != "pw"}


def add_user(kb: KB, actor: str, name: str, password: str, role: str = "reader", display: str = "") -> dict:
    if role not in ROLES:
        raise AuthError(f"unknown role {role}")
    if not name or not name.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise AuthError("username: letters, digits, - _ . only")
    with LOCK:
        users = load_users(kb)
        if name in users:
            raise AuthError(f"user {name} exists")
        users[name] = {"name": name, "display": display or name, "role": role, "active": True,
                       "created": now(), "pw": _hash(password)}
        _save(kb, users)
    kb.event(actor, "user.add", name, role=role)
    return public(users[name])


def update_user(kb: KB, actor: str, name: str, role: str | None = None, active: bool | None = None,
                password: str | None = None, display: str | None = None) -> dict:
    with LOCK:
        users = load_users(kb)
        if name not in users:
            raise AuthError(f"no user {name}")
        u = users[name]
        changes = {}
        if role is not None:
            if role not in ROLES:
                raise AuthError(f"unknown role {role}")
            u["role"] = changes["role"] = role
        if active is not None:
            u["active"] = changes["active"] = bool(active)
        if display is not None:
            u["display"] = changes["display"] = display
        if password:
            u["pw"] = _hash(password)
            changes["password"] = "changed"
        if not any(x["role"] == "admin" and x.get("active") for x in users.values()):
            raise AuthError("refusing: at least one active admin must remain")
        _save(kb, users)
    kb.event(actor, "user.update", name, **changes)
    return public(u)


def login(kb: KB, name: str, password: str) -> str:
    u = load_users(kb).get(name)
    if not u or not u.get("active") or not _check(password, u["pw"]):
        raise AuthError("invalid credentials")
    kb.event(name, "user.login", name)
    return make_token(kb, name)


def make_token(kb: KB, name: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"u": name, "exp": int(time.time()) + TOKEN_TTL}).encode()).decode()
    sig = hmac.new(kb.secret(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + sig


def verify_token(kb: KB, token: str | None) -> dict | None:
    """Return the *current* user record (role read live, so demotion/disable is immediate)."""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    good = hmac.new(kb.secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
    if data.get("exp", 0) < time.time():
        return None
    u = load_users(kb).get(data.get("u"))
    return public(u) if u and u.get("active") else None


def require(user: dict | None, role: str) -> None:
    have = RANK[user["role"]] if user else 0
    if have < RANK[role]:
        raise PermissionError(f"requires role {role}")
