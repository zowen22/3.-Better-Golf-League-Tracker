"""Site Admin Dashboard v1 — read-only platform health overview.

A single logged-in-as-individual-account site admin (platform operator, not
a league admin) can view aggregate counts across ALL leagues: how many
leagues exist, how many are active, and Golf Course API usage/status.

Deliberately read-only and aggregate-only — no editing, no cross-league
impersonation, no session-model change. See:
  1. Project Management/Audits/2026-07-04-site-admin-dashboard-investigation.md
  1. Project Management/Handoffs/2026-07-06-site-admin-dashboard-v1.md
"""
from flask import Blueprint, render_template
from database import get_db
from routes.auth import site_admin_required

bp = Blueprint('site_admin', __name__, url_prefix='/site-admin')


def _monthly_platform_request_count(db):
    """Count Golf Course API calls this calendar month, across all leagues.

    Same query shape as courses.py's _monthly_request_count, with the
    league_id filter dropped (platform-wide instead of per-league).
    """
    try:
        row = db.execute(
            "SELECT COUNT(*) AS n FROM api_request_log "
            "WHERE DATE_TRUNC('month', requested_at) = DATE_TRUNC('month', NOW())"
        ).fetchone()
        return row['n'] if row else 0
    except Exception:
        return 0


def _monthly_status_breakdown(db):
    """2xx-vs-error breakdown of this month's API calls, platform-wide."""
    try:
        row = db.execute(
            "SELECT "
            "  COUNT(*) FILTER (WHERE response_code >= 200 AND response_code < 300) AS success, "
            "  COUNT(*) FILTER (WHERE response_code IS NULL OR response_code < 200 OR response_code >= 300) AS error "
            "FROM api_request_log "
            "WHERE DATE_TRUNC('month', requested_at) = DATE_TRUNC('month', NOW())"
        ).fetchone()
        if not row:
            return {'success': 0, 'error': 0}
        return {'success': row['success'] or 0, 'error': row['error'] or 0}
    except Exception:
        return {'success': 0, 'error': 0}


def _per_league_monthly_usage(db):
    """Per-league breakdown of this month's API call counts, active leagues first."""
    try:
        return db.execute(
            "SELECT l.league_id, l.league_name, l.active, "
            "       COUNT(a.log_id) AS call_count "
            "FROM leagues l "
            "LEFT JOIN api_request_log a ON a.league_id = l.league_id "
            "  AND DATE_TRUNC('month', a.requested_at) = DATE_TRUNC('month', NOW()) "
            "GROUP BY l.league_id, l.league_name, l.active "
            "ORDER BY call_count DESC, l.league_name"
        ).fetchall()
    except Exception:
        return []


def _recent_api_errors(db, limit=10):
    """Most recent non-2xx API responses, platform-wide."""
    try:
        return db.execute(
            "SELECT a.log_id, a.endpoint, a.league_id, l.league_name, "
            "       a.response_code, a.requested_at "
            "FROM api_request_log a "
            "LEFT JOIN leagues l ON l.league_id = a.league_id "
            "WHERE a.response_code IS NULL OR a.response_code < 200 OR a.response_code >= 300 "
            "ORDER BY a.requested_at DESC "
            "LIMIT %s",
            (limit,)
        ).fetchall()
    except Exception:
        return []


def _recent_leagues(db, limit=5):
    """Most-recently-created leagues (onboarding-funnel visibility)."""
    return db.execute(
        "SELECT league_id, league_name, created_date, active "
        "FROM leagues ORDER BY created_date DESC, league_id DESC LIMIT %s",
        (limit,)
    ).fetchall()


@bp.route('/')
@site_admin_required
def dashboard():
    db = get_db()

    total_leagues = db.execute("SELECT COUNT(*) AS n FROM leagues").fetchone()['n']
    active_leagues = db.execute("SELECT COUNT(*) AS n FROM leagues WHERE active = 1").fetchone()['n']
    inactive_leagues = total_leagues - active_leagues

    total_players = db.execute("SELECT COUNT(*) AS n FROM players").fetchone()['n']
    total_teams = db.execute("SELECT COUNT(*) AS n FROM teams").fetchone()['n']
    total_seasons = db.execute("SELECT COUNT(*) AS n FROM seasons").fetchone()['n']

    monthly_api_calls = _monthly_platform_request_count(db)
    status_breakdown = _monthly_status_breakdown(db)
    per_league_usage = _per_league_monthly_usage(db)
    recent_errors = _recent_api_errors(db)
    recent_leagues = _recent_leagues(db)

    return render_template(
        'site_admin/dashboard.html',
        total_leagues=total_leagues,
        active_leagues=active_leagues,
        inactive_leagues=inactive_leagues,
        total_players=total_players,
        total_teams=total_teams,
        total_seasons=total_seasons,
        monthly_api_calls=monthly_api_calls,
        status_breakdown=status_breakdown,
        per_league_usage=per_league_usage,
        recent_errors=recent_errors,
        recent_leagues=recent_leagues,
    )
