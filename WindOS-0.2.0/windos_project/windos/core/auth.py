"""Authentication helpers shared by the desktop and web front ends."""
import secrets
from . import engine


def authenticate(username: str, password: str):
    users = engine.jload(engine.USERS_F, {})
    record = users.get(username)
    if not record:
        return None
    try:
        candidate = engine.hash_pw(password, record["salt"])[1]
    except (KeyError, TypeError, ValueError):
        return None
    if not secrets.compare_digest(candidate, record.get("hash", "")):
        engine.log_auth(f"login FAILED: {username}")
        return None
    engine.log_auth(f"login ok: {username}")
    return {"name": username, **record}
