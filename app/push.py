"""
APNs push notification sender.

Reads credentials from environment:
  APNS_KEY_PATH   — path to .p8 private key file
  APNS_KEY_ID     — 10-char key ID from Apple Developer portal
  APNS_TEAM_ID    — 10-char team ID
  APNS_BUNDLE_ID  — app bundle ID (e.g. owen.BetterGolfTracker)
  APNS_SANDBOX    — "true" for dev/TestFlight, "false" for production

All functions are fire-and-forget: they log errors but never raise,
so a push failure never breaks the main request flow.
"""

import os
import time
import logging
import jwt as pyjwt

log = logging.getLogger(__name__)

_APNS_PROD    = "https://api.push.apple.com"
_APNS_SANDBOX = "https://api.sandbox.push.apple.com"

_cached_client = None   # httpx.Client (reused across requests for connection pooling)
_token_cache   = {}     # {key_id: (token_str, generated_at)}


def _apns_base_url():
    sandbox = os.environ.get("APNS_SANDBOX", "true").lower() == "true"
    return _APNS_SANDBOX if sandbox else _APNS_PROD


def _bearer_token():
    key_id   = os.environ.get("APNS_KEY_ID")
    team_id  = os.environ.get("APNS_TEAM_ID")
    key_path = os.environ.get("APNS_KEY_PATH")
    if not all([key_id, team_id, key_path]):
        return None

    # Reuse token for up to 55 minutes (APNs tokens expire after 60 min)
    cached = _token_cache.get(key_id)
    if cached and (time.time() - cached[1]) < 55 * 60:
        return cached[0]

    try:
        with open(key_path, "r") as f:
            private_key = f.read()
        token = pyjwt.encode(
            {"iss": team_id, "iat": int(time.time())},
            private_key,
            algorithm="ES256",
            headers={"kid": key_id},
        )
        _token_cache[key_id] = (token, time.time())
        return token
    except Exception as e:
        log.warning("APNs token generation failed: %s", e)
        return None


def _get_client():
    global _cached_client
    try:
        import httpx
        if _cached_client is None:
            _cached_client = httpx.Client(http2=True, timeout=10.0)
        return _cached_client
    except ImportError:
        return None


def send_push(device_token: str, title: str, body: str, data: dict = None) -> bool:
    """Send a single push notification. Returns True on success."""
    token = _bearer_token()
    bundle_id = os.environ.get("APNS_BUNDLE_ID")
    client = _get_client()

    if not all([token, bundle_id, client, device_token]):
        log.debug("APNs not configured — skipping push")
        return False

    payload = {
        "aps": {"alert": {"title": title, "body": body}, "sound": "default"}
    }
    if data:
        payload.update(data)

    url = f"{_apns_base_url()}/3/device/{device_token}"
    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": bundle_id,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }
    try:
        import httpx
        r = client.post(url, json=payload, headers=headers)
        if r.status_code == 200:
            return True
        log.warning("APNs push failed: %s %s", r.status_code, r.text)
        return False
    except Exception as e:
        log.warning("APNs send error: %s", e)
        return False


def send_to_league(db, league_id: int, title: str, body: str, data: dict = None):
    """Send push to all registered devices for a league."""
    try:
        rows = db.execute(
            """SELECT at.token FROM apns_tokens at
               JOIN users u ON u.user_id = at.user_id
               JOIN league_members lm ON lm.user_id = u.user_id
               WHERE lm.league_id = %s""",
            (league_id,)
        ).fetchall()
        for row in rows:
            send_push(row["token"], title, body, data)
    except Exception as e:
        log.warning("send_to_league error: %s", e)


def send_to_admins(db, league_id: int, title: str, body: str, data: dict = None):
    """Send push only to admin users of a league."""
    try:
        rows = db.execute(
            """SELECT at.token FROM apns_tokens at
               JOIN users u ON u.user_id = at.user_id
               JOIN league_members lm ON lm.user_id = u.user_id
               WHERE lm.league_id = %s AND lm.role IN ('admin', 'league_admin')""",
            (league_id,)
        ).fetchall()
        for row in rows:
            send_push(row["token"], title, body, data)
    except Exception as e:
        log.warning("send_to_admins error: %s", e)
