"""
auth.py — session-based multi-user auth for the Music Gateway.

Each user has a gateway account (bcrypt password) that is *linked* to a real
Navidrome account (so Symfonium streaming works with the same credentials).
The gateway is the sole source of truth for passwords — admins manage everyone
here, never directly in Navidrome.

Auth flow:
  • POST /api/auth/login  → bcrypt-check, mint a `secrets.token_hex(32)` session
    token (30-day expiry), return it.
  • Every other /api/* route depends on `get_current_user`, which reads the
    Bearer token, validates the session (refreshing last_seen), returns the
    user dict. `require_admin` layers a role check on top.

The Navidrome password for each user is stored Fernet-encrypted in the DB so
the gateway can build per-user Subsonic auth for playlist operations (radio).
"""

import logging
import os
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException

log = logging.getLogger("auth")

SESSION_TTL_DAYS = 30

# main.py sets this so the dependencies can reach the live Database without a
# circular import (main imports auth, not the other way around).
_db_getter = None


def set_db_getter(fn) -> None:
    global _db_getter
    _db_getter = fn


def _db():
    if _db_getter is None:
        raise HTTPException(503, "Service starting up")
    return _db_getter()


# ── password hashing ───────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), pw_hash.encode())
    except Exception:
        return False


# ── Fernet encryption for stored Navidrome passwords ───────────────────────

def _fernet() -> Fernet:
    key = os.environ.get("GATEWAY_SECRET_KEY", "")
    if not key:
        raise HTTPException(500, "GATEWAY_SECRET_KEY is not configured")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


# ── public user shape (never leak password/hash) ───────────────────────────

def public_user(u: dict) -> dict:
    return {
        "id": u.get("id"),
        "username": u.get("username"),
        "role": u.get("role", "user"),
        "navidrome_id": u.get("navidrome_id"),
        "created_at": u.get("created_at"),
    }


# ── FastAPI dependencies ────────────────────────────────────────────────────

async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Missing or malformed Authorization header")
    db = _db()
    session = await db.get_session(token.strip())
    if not session:
        raise HTTPException(401, "Invalid or expired session")
    user = await db.get_user_by_id(session["user_id"])
    if not user:
        raise HTTPException(401, "User no longer exists")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin privileges required")
    return user


# ── account lifecycle (gateway + Navidrome kept in sync) ────────────────────

async def create_linked_user(db, navidrome, username: str, password: str,
                             role: str = "user") -> dict:
    """
    Atomically create a gateway user backed by a Navidrome account.

    Navidrome is created first; only if that succeeds do we persist the gateway
    row. If Navidrome creation fails, no gateway user is created.
    """
    username = username.strip()
    if not username or not password:
        raise HTTPException(400, "username and password are required")
    if await db.get_user_by_username(username):
        raise HTTPException(409, "Username already taken")
    if role not in ("admin", "user"):
        raise HTTPException(400, "role must be 'admin' or 'user'")

    nav_id = None
    try:
        nav_user = await navidrome.create_nav_user(
            username, password, is_admin=(role == "admin")
        )
        nav_id = nav_user.get("id") if nav_user else None
    except Exception as exc:
        log.error("Navidrome user creation failed for %s: %s", username, exc)
        raise HTTPException(502, f"Could not create Navidrome account: {exc}")

    if not nav_id:
        raise HTTPException(502, "Navidrome did not return a user id")

    user_id = await db.create_user(
        username=username,
        pw_hash=hash_password(password),
        role=role,
        nav_user=username,
        nav_pass_enc=encrypt_secret(password),
        nav_id=nav_id,
    )
    return public_user(await db.get_user_by_id(user_id))


async def create_first_admin(db, username: str, password: str,
                            navidrome=None) -> dict:
    """
    First-run admin creation. Tries to link a Navidrome account, but does not
    hard-fail if Navidrome is unreachable during bootstrap — the admin can
    re-link later. Stores the encrypted Navidrome password regardless.
    """
    username = username.strip()
    if not username or not password:
        raise HTTPException(400, "username and password are required")
    if await db.count_users() > 0:
        raise HTTPException(409, "Setup already completed")

    nav_id = None
    if navidrome is not None:
        try:
            nav_user = await navidrome.create_nav_user(username, password, is_admin=True)
            nav_id = nav_user.get("id") if nav_user else None
        except Exception as exc:
            log.warning("First-run: Navidrome admin link failed (%s); "
                        "creating gateway admin anyway", exc)

    user_id = await db.create_user(
        username=username,
        pw_hash=hash_password(password),
        role="admin",
        nav_user=username,
        nav_pass_enc=encrypt_secret(password),
        nav_id=nav_id,
    )
    return public_user(await db.get_user_by_id(user_id))


async def change_password(db, navidrome, user: dict, new_password: str) -> None:
    """Update the password in both Navidrome and the gateway DB."""
    if navidrome is not None and user.get("navidrome_id"):
        try:
            await navidrome.update_nav_user(user["navidrome_id"], password=new_password)
        except Exception as exc:
            log.error("Navidrome password update failed for %s — gateway updated "
                      "anyway (DESYNC): %s", user.get("username"), exc)
    await db.update_user_password(
        user["id"], hash_password(new_password), encrypt_secret(new_password)
    )


async def delete_linked_user(db, navidrome, user: dict) -> None:
    if navidrome is not None and user.get("navidrome_id"):
        try:
            await navidrome.delete_nav_user(user["navidrome_id"])
        except Exception as exc:
            log.error("Navidrome user deletion failed for %s: %s",
                      user.get("username"), exc)
    await db.delete_user(user["id"])


def user_subsonic_auth(user: dict) -> Optional[dict]:
    """Build Subsonic auth params for a user from their stored Navidrome creds."""
    import hashlib
    import secrets as _secrets

    nav_user = user.get("navidrome_user")
    enc = user.get("navidrome_pass")
    if not nav_user or not enc:
        return None
    try:
        password = decrypt_secret(enc)
    except Exception as exc:
        log.error("Could not decrypt Navidrome password for %s: %s",
                  user.get("username"), exc)
        return None
    salt = _secrets.token_hex(8)
    token = hashlib.md5((password + salt).encode()).hexdigest()
    return {"u": nav_user, "t": token, "s": salt,
            "v": "1.16.1", "c": "musicgateway", "f": "json"}
