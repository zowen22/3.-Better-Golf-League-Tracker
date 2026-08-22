"""Site-admin 'view as league' impersonation.

Lets a platform operator (a `users.is_site_admin` account) temporarily act
as a league's admin -- e.g. to help with a support request -- without
knowing that league's actual admin password. This deliberately breaks the
Site Admin dashboard's original "read-only, no cross-league editing" rule
(see site_admin.py's module docstring), so it exists ONLY behind this
module: every entry, exit, and individual request made while impersonating
is written to `site_admin_audit_log`. See Technical Reference "Site Admin
Impersonation" for the full design.
"""
from datetime import datetime, timezone, timedelta
from flask import request, session
from database import get_db

MAX_DURATION_MINUTES = 30

_EXCLUDED_PREFIXES = ('/static/',)
_EXCLUDED_PATHS = ('/health', '/sw.js', '/offline', '/favicon.ico', '/manifest.json')


def is_impersonating():
    return bool(session.get('impersonating'))


def start(db, site_admin_user_id, league_id, league_name):
    """Begins an impersonation session: writes the audit start row, then
    stamps session state so the rest of the app treats this request (and
    every request until end()/timeout) as that league's admin. Deliberately
    does NOT clear session['user_id']/['is_site_admin'] -- that's what lets
    end() hand the operator back their own Site Admin session afterward."""
    row = db.execute(
        "INSERT INTO site_admin_audit_log (site_admin_user_id, league_id, action) "
        "VALUES (%s, %s, 'impersonation_start') RETURNING audit_id",
        (site_admin_user_id, league_id)
    ).fetchone()
    db.commit()

    session['impersonating'] = True
    session['impersonation_audit_id'] = row['audit_id']
    session['impersonation_site_admin_id'] = site_admin_user_id
    session['impersonation_started_at'] = datetime.now(timezone.utc).isoformat()
    session['league_id'] = league_id
    session['league_name'] = league_name
    session['role'] = 'league_admin'
    session['player_id'] = None
    session.pop('current_season_id', None)


def end(db, reason='manual'):
    """Ends the current impersonation session (manual exit or timeout),
    writes the paired audit end row, and clears the league-scoped session
    keys back to a bare (still logged-in) Site Admin state."""
    if not is_impersonating():
        return
    audit_id = session.get('impersonation_audit_id')
    league_id = session.get('league_id')
    site_admin_id = session.get('impersonation_site_admin_id')
    try:
        db.execute(
            "INSERT INTO site_admin_audit_log (site_admin_user_id, league_id, action, detail, ref_id) "
            "VALUES (%s, %s, 'impersonation_end', %s, %s)",
            (site_admin_id, league_id, reason, audit_id)
        )
        db.commit()
    except Exception:
        pass

    for key in ('impersonating', 'impersonation_audit_id', 'impersonation_site_admin_id',
                'impersonation_started_at', 'league_id', 'league_name', 'role',
                'player_id', 'current_season_id'):
        session.pop(key, None)


def check_expiry(db):
    """Called at the start of every request (app.py before_request). Force-
    ends the session if it's run past MAX_DURATION_MINUTES, so a forgotten
    tab can't leave an operator silently able to act as a league forever.
    Returns True if it just force-ended the session."""
    if not is_impersonating():
        return False
    started_raw = session.get('impersonation_started_at')
    if not started_raw:
        end(db, reason='timeout (missing start time)')
        return True
    started = datetime.fromisoformat(started_raw)
    if datetime.now(timezone.utc) - started > timedelta(minutes=MAX_DURATION_MINUTES):
        end(db, reason='timeout')
        return True
    return False


def _is_trackable(path):
    if path in _EXCLUDED_PATHS:
        return False
    return not any(path.startswith(p) for p in _EXCLUDED_PREFIXES)


def record_request(db, status_code):
    """Logs one request made while impersonating -- method, path, status --
    against the session's audit_id. Called from app.py's after_request.
    Never raises: a logging failure must not break the page."""
    if not is_impersonating():
        return
    if not _is_trackable(request.path):
        return
    try:
        db.execute(
            "INSERT INTO site_admin_audit_log "
            "(site_admin_user_id, league_id, action, method, path, status_code, ref_id) "
            "VALUES (%s, %s, 'request', %s, %s, %s, %s)",
            (
                session.get('impersonation_site_admin_id'), session.get('league_id'),
                request.method, request.path, status_code,
                session.get('impersonation_audit_id'),
            )
        )
        db.commit()
    except Exception:
        pass
