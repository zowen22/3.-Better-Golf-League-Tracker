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


def _subscription_status_counts(db):
    """Count of leagues per Stripe subscription status, plus leagues with
    no subscription row at all (never started checkout). Wrapped in
    try/except like the API-usage queries above since `subscriptions`
    won't exist on a production DB until that migration is run there."""
    try:
        rows = db.execute(
            "SELECT status, COUNT(*) AS n FROM subscriptions GROUP BY status"
        ).fetchall()
        counts = {r['status']: r['n'] for r in rows}
        subscribed_leagues = db.execute("SELECT COUNT(*) AS n FROM subscriptions").fetchone()['n']
        total_leagues = db.execute("SELECT COUNT(*) AS n FROM leagues").fetchone()['n']
        counts['none'] = total_leagues - subscribed_leagues
        return counts
    except Exception:
        return {}


def _trial_funnel(db):
    """Free-usage-trial funnel: how many leagues are currently using their
    free rounds, how many have used them all without converting, and the
    conversion rate among leagues that ever hit that point. Computed from
    `subscription_events` (append-only) rather than `subscriptions` (current
    state only, overwritten on every webhook) -- that table can't answer
    "did this league convert AFTER its trial ended" on its own."""
    from routes.billing import get_lockout_status
    try:
        leagues = db.execute("SELECT league_id FROM leagues").fetchall()
        in_free_window = 0
        locked_unconverted = 0
        for row in leagues:
            status = get_lockout_status(db, row['league_id'])
            if status['locked']:
                locked_unconverted += 1
            elif status['round_count'] is not None:
                in_free_window += 1

        funnel_row = db.execute(
            """SELECT
                   COUNT(DISTINCT le.league_id) AS trials_ended,
                   COUNT(DISTINCT CASE WHEN conv.league_id IS NOT NULL THEN le.league_id END) AS converted
               FROM subscription_events le
               LEFT JOIN subscription_events conv
                   ON conv.league_id = le.league_id AND conv.event_type = 'converted'
                   AND conv.created_at > le.created_at
               WHERE le.event_type = 'lockout_started'"""
        ).fetchone()
        trials_ended = funnel_row['trials_ended'] or 0
        converted = funnel_row['converted'] or 0
        conversion_rate = round(100 * converted / trials_ended) if trials_ended else None

        return {
            'in_free_window': in_free_window,
            'locked_unconverted': locked_unconverted,
            'trials_ended': trials_ended,
            'converted': converted,
            'conversion_rate': conversion_rate,
        }
    except Exception:
        return None


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
    subscription_counts = _subscription_status_counts(db)
    trial_funnel = _trial_funnel(db)

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
        subscription_counts=subscription_counts,
        trial_funnel=trial_funnel,
    )
