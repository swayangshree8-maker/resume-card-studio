"""AWS Lambda Function URL backend for the Studio control panel."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs

import boto3
from boto3.dynamodb.conditions import Key

TABLE = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
ALLOWED_ORIGIN = "https://swayangshree8-maker.github.io"
PAGES = {"home", "resume", "cards", "rent", "login"}
TOKEN_SECONDS = 6 * 60 * 60
FAILURE_SECONDS = 15 * 60
FAILURE_LIMIT = 5


def response(status: int, data=None):
    body = "" if data is None else json.dumps(data, separators=(",", ":"))
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        },
        "body": body,
    }


def body_json(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    if len(raw) > 16384:
        raise ValueError("Request too large")
    return json.loads(raw)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def client_ip(event) -> str:
    return str(event.get("requestContext", {}).get("http", {}).get("sourceIp", "unknown"))[:80]


def query_count(pk: str, now: int) -> int:
    result = TABLE.query(
        KeyConditionExpression=Key("pk").eq(pk),
        Select="COUNT",
        FilterExpression="#expiry > :now",
        ExpressionAttributeNames={"#expiry": "expires_at"},
        ExpressionAttributeValues={":now": now},
    )
    return int(result.get("Count", 0))


def rate_limit(ip_hash: str, now: int) -> bool:
    minute = now // 60
    result = TABLE.update_item(
        Key={"pk": f"RATE#{minute}#{ip_hash}", "sk": "REQUESTS"},
        UpdateExpression="SET expires_at = :ttl ADD #count :one",
        ExpressionAttributeNames={"#count": "request_count"},
        ExpressionAttributeValues={":ttl": minute * 60 + 120, ":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(result["Attributes"].get("request_count", 0)) > 300


def record_failure(ip_hash: str, user_hash: str, now: int):
    stamp = f"{now:010d}#{secrets.token_hex(6)}"
    expiry = now + FAILURE_SECONDS
    for pk in (f"FAIL#IP#{ip_hash}", f"FAIL#USER#{user_hash}"):
        TABLE.put_item(Item={"pk": pk, "sk": stamp, "expires_at": expiry})


def validate_session(event, now: int) -> bool:
    auth = str(event.get("headers", {}).get("authorization", ""))
    if not auth.startswith("Bearer "):
        return False
    token_hash = digest(auth[7:].strip())
    result = TABLE.get_item(Key={"pk": f"SESSION#{token_hash}", "sk": "TOKEN"})
    item = result.get("Item")
    return bool(item and int(item.get("expires_at", 0)) > now)


def get_setting(name: str, default: str = "") -> str:
    result = TABLE.get_item(Key={"pk": f"SETTING#{name}", "sk": "VALUE"})
    return str(result.get("Item", {}).get("value", default))


def put_settings(values: dict):
    for name, value in values.items():
        TABLE.put_item(Item={"pk": f"SETTING#{name}", "sk": "VALUE", "value": value})


def admin_login(event, now: int):
    payload = body_json(event)
    user = str(payload.get("username", ""))[:100].strip().lower()
    password = str(payload.get("password", ""))[:512]
    ip_hash, user_hash = digest(client_ip(event)), digest(user)
    if max(query_count(f"FAIL#IP#{ip_hash}", now), query_count(f"FAIL#USER#{user_hash}", now)) >= FAILURE_LIMIT:
        return response(429, {"error": "Too many sign-in attempts", "retry_after": FAILURE_SECONDS})
    expected_user = os.environ.get("ADMIN_USERNAME", "sway").strip().lower()
    expected_password = os.environ.get("ADMIN_PASSWORD", "")
    if not expected_password:
        return response(503, {"error": "Admin password is not configured on the server"})
    if not (hmac.compare_digest(user, expected_user) and hmac.compare_digest(password, expected_password)):
        record_failure(ip_hash, user_hash, now)
        return response(401, {"error": "Username or password is incorrect"})
    token = secrets.token_urlsafe(32)
    TABLE.put_item(Item={
        "pk": f"SESSION#{digest(token)}", "sk": "TOKEN", "user": expected_user,
        "expires_at": now + TOKEN_SECONDS,
    })
    return response(200, {"token": token, "expires_in": TOKEN_SECONDS})


def admin_analytics(query: dict, now: int):
    try:
        days = max(1, min(int((query.get("days") or [30])[0]), 90))
    except (TypeError, ValueError):
        days = 30
    by_page = {page: 0 for page in PAGES}
    daily = []
    total = 0
    today = datetime.fromtimestamp(now, timezone.utc).date()
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        result = TABLE.query(
            KeyConditionExpression=Key("pk").eq(f"SUMMARY#{day}"),
            ConsistentRead=False,
        )
        count = 0
        for item in result.get("Items", []):
            page = item.get("page")
            views = int(item.get("views", 0))
            count += views
            if page in by_page:
                by_page[page] += views
        total += count
        if count:
            daily.append({"day": day, "views": count})
    return response(200, {
        "days": days, "total_views": total, "by_page": by_page, "daily": daily,
        "privacy": "Anonymous page totals only; no names, emails, or resume contents are collected.",
    })


def lambda_handler(event, context):
    method = str(event.get("requestContext", {}).get("http", {}).get("method", "GET")).upper()
    path = str(event.get("rawPath", "/"))
    headers = {str(k).lower(): str(v) for k, v in event.get("headers", {}).items()}
    origin = headers.get("origin", "").rstrip("/")
    if origin and origin != ALLOWED_ORIGIN:
        return response(403, {"error": "Origin not allowed"})
    if method == "OPTIONS":
        return response(204)
    if len(str(event.get("rawQueryString", ""))) > 1024:
        return response(414, {"error": "Request too large"})
    if method == "POST" and (origin != ALLOWED_ORIGIN or "application/json" not in headers.get("content-type", "")):
        return response(403, {"error": "Allowed site origin and JSON required"})
    routes = {
        ("GET", "/api/health"), ("GET", "/api/settings"),
        ("POST", "/api/analytics/event"), ("POST", "/api/admin/login"),
        ("GET", "/api/admin/settings"), ("POST", "/api/admin/settings"),
        ("GET", "/api/admin/analytics"),
    }
    if (method, path) not in routes:
        return response(404, {"error": "Not found"})
    now = int(time.time())
    if rate_limit(digest(client_ip(event)), now):
        return response(429, {"error": "Request rate limit reached"})
    if method == "GET" and path == "/api/health":
        return response(200, {"ok": True, "configured": bool(os.environ.get("ADMIN_PASSWORD"))})
    if method == "POST" and path == "/api/admin/login":
        try:
            return admin_login(event, now)
        except (ValueError, json.JSONDecodeError):
            return response(400, {"error": "Invalid JSON"})
    if path.startswith("/api/admin/") and not validate_session(event, now):
        return response(401, {"error": "Sign in required"})
    if method == "GET" and path == "/api/settings":
        return response(200, {
            "site_title": get_setting("site_title", "Resume & Card Studio"),
            "announcement": get_setting("announcement", "") if get_setting("announcement_enabled") == "true" else "",
        })
    if method == "POST" and path == "/api/analytics/event":
        try:
            page = body_json(event).get("page")
        except (ValueError, json.JSONDecodeError):
            return response(400, {"error": "Invalid JSON"})
        if page not in PAGES:
            return response(400, {"error": "Unknown page"})
        day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
        TABLE.update_item(
            Key={"pk": f"SUMMARY#{day}", "sk": f"PAGE#{page}"},
            UpdateExpression="SET #page = :page, expires_at = :ttl ADD #views :one",
            ExpressionAttributeNames={"#page": "page", "#views": "views"},
            ExpressionAttributeValues={":page": page, ":ttl": now + 400 * 86400, ":one": 1},
        )
        return response(202, {"ok": True})
    if method == "GET" and path == "/api/admin/settings":
        return response(200, {
            "site_title": get_setting("site_title", "Resume & Card Studio"),
            "announcement": get_setting("announcement"),
            "announcement_enabled": get_setting("announcement_enabled") == "true",
        })
    if method == "POST" and path == "/api/admin/settings":
        try:
            data = body_json(event)
        except (ValueError, json.JSONDecodeError):
            return response(400, {"error": "Invalid JSON"})
        title = str(data.get("site_title", "Resume & Card Studio")).strip()
        announcement = str(data.get("announcement", "")).strip()
        enabled = bool(data.get("announcement_enabled", False))
        if not title or len(title) > 80 or len(announcement) > 240:
            return response(400, {"error": "Title max 80 chars; announcement max 240 chars"})
        put_settings({"site_title": title, "announcement": announcement,
                      "announcement_enabled": "true" if enabled else "false"})
        return response(200, {"ok": True})
    if method == "GET" and path == "/api/admin/analytics":
        return admin_analytics(parse_qs(str(event.get("rawQueryString", ""))), now)
    return response(404, {"error": "Not found"})
