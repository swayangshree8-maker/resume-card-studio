"""Small Flask backend for remote site settings and anonymous usage totals.

The app never receives or stores resume/card contents. Secrets are supplied only
through environment variables; this module is safe to keep in a public repo.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, make_response, request


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", ROOT / "data" / "control.sqlite3"))
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin").strip().lower()
ADMIN_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
TOKEN_SECRET = os.environ.get("TOKEN_SECRET", "")
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "CORS_ALLOW_ORIGIN", "https://swayangshree8-maker.github.io"
    ).split(",")
    if origin.strip()
}
TOKEN_LIFETIME = 6 * 60 * 60
LOGIN_WINDOW = 15 * 60
LOGIN_MAX_FAILURES = 5
ANALYTICS_LIMIT = 240
PAGE_NAMES = {"home", "resume", "cards", "rent", "login"}
DB_LOCK = Lock()
EVENT_LOCK = Lock()
EVENT_BUCKETS: dict[str, list[int]] = {}
REQUEST_LOCK = Lock()
REQUEST_BUCKETS: dict[str, list[int]] = {}
ROUTE_METHODS = {
    ("GET", "/api/health"),
    ("GET", "/api/settings"),
    ("POST", "/api/analytics/event"),
    ("POST", "/api/admin/login"),
    ("GET", "/api/admin/settings"),
    ("POST", "/api/admin/settings"),
    ("GET", "/api/admin/analytics"),
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


@contextmanager
def database():
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with DB_LOCK, database() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                page TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_created_at ON events(created_at);
            CREATE TABLE IF NOT EXISTS login_failures (
                ip_digest TEXT NOT NULL,
                account_digest TEXT NOT NULL,
                failed_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS login_failures_time ON login_failures(failed_at);
            """
        )
        login_columns = {row["name"] for row in db.execute("PRAGMA table_info(login_failures)")}
        if "account_digest" not in login_columns:
            db.execute("ALTER TABLE login_failures ADD COLUMN account_digest TEXT NOT NULL DEFAULT ''")
        defaults = {
            "announcement": "",
            "announcement_enabled": "false",
            "site_title": "Resume & Card Studio",
        }
        for key, value in defaults.items():
            db.execute("INSERT OR IGNORE INTO settings(name,value) VALUES(?,?)", (key, value))


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def token_for(user: str) -> str:
    now = int(time.time())
    payload = b64url(json.dumps({"u": user, "iat": now, "exp": now + TOKEN_LIFETIME,
                                  "n": secrets.token_urlsafe(12)}, separators=(",", ":")).encode())
    signature = hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return payload + "." + b64url(signature)


def authorized() -> bool:
    if not TOKEN_SECRET or not ADMIN_HASH:
        return False
    token = request.headers.get("Authorization", "")
    if not token.startswith("Bearer "):
        return False
    try:
        payload, signature = token[7:].split(".", 1)
        expected = b64url(hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        claims = json.loads(raw)
        return claims.get("u") == ADMIN_USER and int(claims.get("exp", 0)) > int(time.time())
    except (ValueError, TypeError, json.JSONDecodeError):
        return False


def password_matches(password: str) -> bool:
    try:
        scheme, rounds, salt, expected = ADMIN_HASH.split("$", 3)
        if scheme != "pbkdf2_sha256" or not 200_000 <= int(rounds) <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds))
        return hmac.compare_digest(base64.b64encode(actual).decode(), expected)
    except (ValueError, TypeError):
        return False


def ip_digest() -> str:
    # A keyed, one-way digest is used only for short-lived login throttling.
    return hmac.new(TOKEN_SECRET.encode(), (request.remote_addr or "unknown").encode(), hashlib.sha256).hexdigest()


def analytics_is_limited() -> bool:
    now = int(time.time())
    key = request.remote_addr or "unknown"
    with EVENT_LOCK:
        bucket = [stamp for stamp in EVENT_BUCKETS.get(key, []) if stamp > now - 60]
        if len(bucket) >= ANALYTICS_LIMIT:
            EVENT_BUCKETS[key] = bucket
            return True
        bucket.append(now)
        EVENT_BUCKETS[key] = bucket
        if len(EVENT_BUCKETS) > 5000:
            for old_key in list(EVENT_BUCKETS)[:1000]:
                EVENT_BUCKETS.pop(old_key, None)
        return False


def login_is_limited(username: str) -> tuple[bool, int]:
    now = int(time.time())
    account = hmac.new(TOKEN_SECRET.encode(), username.encode(), hashlib.sha256).hexdigest()
    with DB_LOCK, database() as db:
        db.execute("DELETE FROM login_failures WHERE failed_at < ?", (now - LOGIN_WINDOW,))
        row = db.execute(
            "SELECT COUNT(*) AS n, MIN(failed_at) AS first FROM login_failures WHERE ip_digest=? OR account_digest=?",
            (ip_digest(), account),
        ).fetchone()
    if row["n"] >= LOGIN_MAX_FAILURES:
        remaining = max(1, LOGIN_WINDOW - (now - row["first"]))
        return True, remaining
    return False, 0


def record_login_failure(username: str) -> None:
    account = hmac.new(TOKEN_SECRET.encode(), username.encode(), hashlib.sha256).hexdigest()
    with DB_LOCK, database() as db:
        db.execute("INSERT INTO login_failures(ip_digest,account_digest,failed_at) VALUES(?,?,?)",
                   (ip_digest(), account, int(time.time())))


@app.before_request
def enforce_origin():
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") not in ALLOWED_ORIGINS:
        return jsonify(error="Origin not allowed"), 403
    if request.method == "OPTIONS":
        if request.path not in {path for _, path in ROUTE_METHODS}:
            return jsonify(error="Route not allowed"), 404
        requested_method = request.headers.get("Access-Control-Request-Method", "").upper()
        if requested_method and (requested_method, request.path) not in ROUTE_METHODS:
            return jsonify(error="Method not allowed"), 405
        return make_response("", 204)
    if request.path not in {path for _, path in ROUTE_METHODS}:
        return jsonify(error="Not found"), 404
    if (request.method, request.path) not in ROUTE_METHODS:
        return jsonify(error="Method not allowed"), 405
    if request.method == "POST" and request.mimetype != "application/json":
        return jsonify(error="JSON required"), 415
    if len(request.query_string) > 1024:
        return jsonify(error="Request too large"), 414
    if request.method == "POST" and (not origin or origin.rstrip("/") not in ALLOWED_ORIGINS):
        return jsonify(error="Site origin required"), 403
    # In-memory request firewall. No client address is written to disk.
    now = int(time.time())
    key = hmac.new(TOKEN_SECRET.encode(), (request.remote_addr or "unknown").encode(), hashlib.sha256).hexdigest()
    with REQUEST_LOCK:
        bucket = [stamp for stamp in REQUEST_BUCKETS.get(key, []) if stamp > now - 60]
        if len(bucket) >= 300:
            REQUEST_BUCKETS[key] = bucket
            return jsonify(error="Request rate limit reached"), 429
        bucket.append(now)
        REQUEST_BUCKETS[key] = bucket
        if len(REQUEST_BUCKETS) > 5000:
            for old_key in list(REQUEST_BUCKETS)[:1000]:
                REQUEST_BUCKETS.pop(old_key, None)
    return None


@app.after_request
def security_headers(response):
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.get("/api/health")
def health():
    return jsonify(ok=True, configured=bool(TOKEN_SECRET and ADMIN_HASH))


@app.get("/api/settings")
def public_settings():
    init_db()
    with database() as db:
        values = {row["name"]: row["value"] for row in db.execute("SELECT name,value FROM settings")}
    return jsonify(
        site_title=values.get("site_title", "Resume & Card Studio"),
        announcement=values.get("announcement", "") if values.get("announcement_enabled") == "true" else "",
    )


@app.post("/api/analytics/event")
def analytics_event():
    init_db()
    if analytics_is_limited():
        return jsonify(error="Analytics rate limit reached"), 429
    payload = request.get_json(silent=True) or {}
    page = payload.get("page")
    if page not in PAGE_NAMES:
        return jsonify(error="Unknown page"), 400
    now = int(time.time())
    with DB_LOCK, database() as db:
        db.execute("INSERT INTO events(page,created_at) VALUES(?,?)", (page, now))
        db.execute("DELETE FROM events WHERE created_at < ?", (now - 400 * 86400,))
    return jsonify(ok=True), 202


@app.post("/api/admin/login")
def admin_login():
    init_db()
    payload = request.get_json(silent=True) or {}
    user = str(payload.get("username", ""))[:100].strip().lower()
    password = str(payload.get("password", ""))[:512]
    limited, remaining = login_is_limited(user)
    if limited:
        return jsonify(error="Too many sign-in attempts", retry_after=remaining), 429
    if not TOKEN_SECRET or not ADMIN_HASH:
        return jsonify(error="Admin is not configured on the server"), 503
    valid_user = hmac.compare_digest(user, ADMIN_USER)
    valid_password = password_matches(password)
    if not (valid_user and valid_password):
        record_login_failure(user)
        return jsonify(error="Username or password is incorrect"), 401
    return jsonify(token=token_for(ADMIN_USER), expires_in=TOKEN_LIFETIME)


@app.get("/api/admin/settings")
def admin_settings():
    if not authorized():
        return jsonify(error="Sign in required"), 401
    init_db()
    with database() as db:
        values = {row["name"]: row["value"] for row in db.execute("SELECT name,value FROM settings")}
    return jsonify(
        site_title=values.get("site_title", "Resume & Card Studio"),
        announcement=values.get("announcement", ""),
        announcement_enabled=values.get("announcement_enabled") == "true",
    )


@app.post("/api/admin/settings")
def update_settings():
    if not authorized():
        return jsonify(error="Sign in required"), 401
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("site_title", "Resume & Card Studio")).strip()
    announcement = str(payload.get("announcement", "")).strip()
    enabled = bool(payload.get("announcement_enabled", False))
    if not title or len(title) > 80 or len(announcement) > 240:
        return jsonify(error="Title must be 1–80 chars; announcement max is 240 chars"), 400
    values = {
        "site_title": title,
        "announcement": announcement,
        "announcement_enabled": "true" if enabled else "false",
    }
    init_db()
    with DB_LOCK, database() as db:
        db.executemany("INSERT INTO settings(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                       values.items())
    return jsonify(ok=True)


@app.get("/api/admin/analytics")
def analytics_summary():
    if not authorized():
        return jsonify(error="Sign in required"), 401
    days = request.args.get("days", default=30, type=int)
    days = max(1, min(days or 30, 90))
    init_db()
    since = int(time.time()) - days * 86400
    with database() as db:
        total = db.execute("SELECT COUNT(*) AS n FROM events WHERE created_at>=?", (since,)).fetchone()["n"]
        by_page = {row["page"]: row["n"] for row in db.execute(
            "SELECT page,COUNT(*) AS n FROM events WHERE created_at>=? GROUP BY page", (since,)
        )}
        daily = [dict(day=row["day"], views=row["views"]) for row in db.execute(
            "SELECT date(created_at,'unixepoch') AS day,COUNT(*) AS views FROM events WHERE created_at>=? GROUP BY day ORDER BY day",
            (since,),
        )]
    return jsonify(days=days, total_views=total, by_page=by_page, daily=daily,
                   privacy="Anonymous page totals only; no names, emails, or resume contents are collected.")


def make_password_hash(password: str) -> str:
    salt = secrets.token_urlsafe(18)
    rounds = 600_000
    result = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${base64.b64encode(result).decode()}"


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "hash-password":
    secret = input("Choose an admin password (minimum 14 characters): ")
    if len(secret) < 14:
        raise SystemExit("Password must be at least 14 characters.")
    print(make_password_hash(secret))
elif __name__ == "__main__":
    init_db()
    if not TOKEN_SECRET or not ADMIN_HASH:
        raise SystemExit("Set TOKEN_SECRET and ADMIN_PASSWORD_HASH before starting the server.")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), debug=False)
