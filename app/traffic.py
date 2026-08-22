"""Lightweight first-party traffic capture: where anonymous visitors land
(ad click / referrer / utm params) and which pages they visit before either
converting (creating a league) or leaving.

Only tracks pre-login traffic -- once a session is tied to a league or
user, the funnel is already answered by the leagues/subscriptions tables,
so capture stops. This exists so ad performance (Google Ads etc.) can be
checked from our own data instead of digging through Render's raw request
logs each time -- see site_admin.py's /site-admin/traffic view.
"""
import secrets
from flask import request, session, g
from database import get_db, is_postgres

VISITOR_COOKIE = 'vid'
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

_EXCLUDED_PREFIXES = ('/static/', '/api/')
_EXCLUDED_PATHS = ('/health', '/sw.js', '/offline', '/favicon.ico', '/manifest.json')

_UTM_PARAMS = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content')
_AD_PARAMS = ('gclid', 'gbraid', 'wbraid', 'gad_campaignid')


def _is_trackable(path):
    if path in _EXCLUDED_PATHS:
        return False
    return not any(path.startswith(p) for p in _EXCLUDED_PREFIXES)


def ensure_visitor_cookie(response):
    """Assigns a first-party visitor id cookie if the browser doesn't have
    one yet. Runs on every response (even excluded paths) so it's set as
    early as possible in the visit and survives through to any conversion."""
    vid = request.cookies.get(VISITOR_COOKIE)
    if not vid:
        vid = secrets.token_urlsafe(16)
        response.set_cookie(
            VISITOR_COOKIE, vid, max_age=COOKIE_MAX_AGE,
            httponly=True, samesite='Lax',
        )
    g.visitor_id = vid
    return response


def _is_authenticated():
    return bool(session.get('league_id') or session.get('user_id'))


def record_pageview():
    """Logs one anonymous, pre-login pageview -- landing source (referrer +
    ad/utm params) plus the path, so the funnel from ad click through
    sign-up can be reconstructed later. Never raises: a logging failure
    must not break the page for a real visitor."""
    if request.method != 'GET' or _is_authenticated():
        return
    path = request.path
    if not _is_trackable(path):
        return

    try:
        vid = getattr(g, 'visitor_id', None) or request.cookies.get(VISITOR_COOKIE)
        if not vid:
            return
        db = get_db()
        args = request.args
        ad = {k: args.get(k) for k in _AD_PARAMS}
        utm = {k: args.get(k) for k in _UTM_PARAMS}
        is_landing = any(ad.values()) or bool(utm['utm_source'])

        ph = '%s' if is_postgres() else '?'
        db.execute(
            f"""INSERT INTO traffic_events
                (visitor_id, event_type, path, is_landing, referrer,
                 utm_source, utm_medium, utm_campaign, utm_term, utm_content,
                 gclid, gbraid, wbraid, gad_campaignid, user_agent, ip)
                VALUES ({ph},'pageview',{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (
                vid, path, 1 if is_landing else 0, request.referrer,
                utm['utm_source'], utm['utm_medium'], utm['utm_campaign'],
                utm['utm_term'], utm['utm_content'],
                ad['gclid'], ad['gbraid'], ad['wbraid'], ad['gad_campaignid'],
                (request.headers.get('User-Agent') or '')[:500],
                request.headers.get('X-Forwarded-For', request.remote_addr),
            )
        )
        db.commit()
    except Exception:
        pass


def record_conversion(db, event_name, ref_id=None):
    """Stamps a terminal conversion event (e.g. 'league_created') against
    the current visitor cookie, so the site-admin Traffic view can join it
    back to that visitor's landing source and navigation path. Call from
    the route handling the conversion, before the response is sent."""
    try:
        vid = getattr(g, 'visitor_id', None) or request.cookies.get(VISITOR_COOKIE)
        if not vid:
            return
        ph = '%s' if is_postgres() else '?'
        db.execute(
            f"INSERT INTO traffic_events (visitor_id, event_type, path, ref_id) "
            f"VALUES ({ph}, 'conversion', {ph}, {ph})",
            (vid, event_name, ref_id)
        )
        db.commit()
    except Exception:
        pass
