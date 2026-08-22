"""Site Admin Dashboard v1 — read-only platform health overview.

A single logged-in-as-individual-account site admin (platform operator, not
a league admin) can view aggregate counts across ALL leagues: how many
leagues exist, how many are active, and Golf Course API usage/status.

Deliberately read-only and aggregate-only — no editing, no cross-league
impersonation, no session-model change. See:
  1. Project Management/Audits/2026-07-04-site-admin-dashboard-investigation.md
  1. Project Management/Handoffs/2026-07-06-site-admin-dashboard-v1.md
"""
from flask import Blueprint, render_template, redirect, url_for, flash, session
from database import get_db
from routes.auth import site_admin_required
import impersonation

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


def _all_leagues_status(db):
    """Every league with its effective billing-pill status: subscription
    status if one exists (active/trialing/comped/past_due/canceled), else
    derived from the free-round usage window (get_lockout_status) since a
    league with no subscription row has never started checkout at all.

    Returns a list of dicts (not raw rows) -- pill_label/pill_class are
    precomputed here rather than in the template, since the logic branches
    on two different sources (subscriptions table vs. lockout status)."""
    from routes.billing import get_lockout_status, STATUS_LABELS, FREE_ROUNDS

    leagues = db.execute(
        "SELECT league_id, league_name, created_date, active, is_test "
        "FROM leagues ORDER BY created_date DESC, league_id DESC"
    ).fetchall()

    try:
        sub_rows = db.execute("SELECT league_id, status FROM subscriptions").fetchall()
        sub_by_league = {r['league_id']: r['status'] for r in sub_rows}
    except Exception:
        sub_by_league = {}

    PILL_CLASS = {
        'active':   'profile-badge--active',
        'trialing': 'profile-badge--trial',
        'comped':   'profile-badge--comped',
        'past_due': 'profile-badge--past-due',
        'canceled': 'profile-badge--canceled',
    }

    result = []
    for row in leagues:
        league = dict(row)
        status = sub_by_league.get(league['league_id'])
        if status:
            league['pill_label'] = STATUS_LABELS.get(status, status)
            league['pill_class'] = PILL_CLASS.get(status, 'profile-badge--comped')
        else:
            lockout = get_lockout_status(db, league['league_id'])
            if lockout['locked']:
                league['pill_label'] = 'Trial ended'
                league['pill_class'] = 'profile-badge--past-due'
            else:
                league['pill_label'] = f"Free — {lockout['round_count']}/{FREE_ROUNDS} rounds used"
                league['pill_class'] = 'profile-badge--trial'
        result.append(league)
    return result


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
    subscription_counts = _subscription_status_counts(db)
    trial_funnel = _trial_funnel(db)
    all_leagues = _all_leagues_status(db)

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
        subscription_counts=subscription_counts,
        trial_funnel=trial_funnel,
        all_leagues=all_leagues,
        feedback_count=_feedback_count(db),
    )


def _feedback_count(db):
    try:
        return db.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()['n']
    except Exception:
        return 0


@bp.route('/feedback')
@site_admin_required
def feedback():
    db = get_db()
    rows = db.execute(
        """SELECT f.feedback_id, f.message, f.page_url, f.submitted_at,
                  l.league_name, u.email AS user_email
           FROM feedback f
           LEFT JOIN leagues l ON l.league_id = f.league_id
           LEFT JOIN users u ON u.user_id = f.user_id
           ORDER BY f.submitted_at DESC"""
    ).fetchall()
    return render_template('site_admin/feedback.html', items=rows)


def _traffic_summary(db, days=14):
    """Landing count, conversion count, conversion rate, and device mix
    (of landings) over the window."""
    try:
        row = db.execute(
            """SELECT
                   COUNT(DISTINCT visitor_id) FILTER (WHERE event_type = 'pageview' AND is_landing = 1) AS landings,
                   COUNT(DISTINCT visitor_id) FILTER (WHERE event_type = 'conversion') AS conversions
               FROM traffic_events
               WHERE ts >= NOW() - INTERVAL '1 day' * %s""",
            (days,)
        ).fetchone()
        landings = row['landings'] or 0
        conversions = row['conversions'] or 0

        device_rows = db.execute(
            """SELECT COALESCE(device_type, 'unknown') AS device_type, COUNT(*) AS n
               FROM traffic_events
               WHERE event_type = 'pageview' AND is_landing = 1
                 AND ts >= NOW() - INTERVAL '1 day' * %s
               GROUP BY COALESCE(device_type, 'unknown')""",
            (days,)
        ).fetchall()
        device_mix = {r['device_type']: r['n'] for r in device_rows}

        return {
            'landings': landings,
            'conversions': conversions,
            'conversion_rate': round(100 * conversions / landings) if landings else None,
            'device_mix': device_mix,
        }
    except Exception:
        return {'landings': 0, 'conversions': 0, 'conversion_rate': None, 'device_mix': {}}


def _traffic_landings(db, days=14, limit=50):
    """Each ad/utm-tagged landing in the window, with that visitor's full
    subsequent navigation path and whether they ever converted."""
    try:
        landings = db.execute(
            """SELECT event_id, visitor_id, ts, referrer, utm_source, utm_medium,
                      utm_campaign, gclid, gbraid, gad_campaignid, device_type
               FROM traffic_events
               WHERE event_type = 'pageview' AND is_landing = 1
                 AND ts >= NOW() - INTERVAL '1 day' * %s
               ORDER BY ts DESC
               LIMIT %s""",
            (days, limit)
        ).fetchall()
    except Exception:
        return []

    result = []
    for land in landings:
        try:
            nav = db.execute(
                """SELECT path, ts, event_type, ref_id, device_type
                   FROM traffic_events
                   WHERE visitor_id = %s AND ts >= %s
                   ORDER BY ts""",
                (land['visitor_id'], land['ts'])
            ).fetchall()
        except Exception:
            nav = []
        conversion = next((n for n in nav if n['event_type'] == 'conversion'), None)
        result.append({
            'landing': land,
            'nav': nav,
            'conversion': conversion,
        })
    return result


@bp.route('/traffic')
@site_admin_required
def traffic():
    db = get_db()
    days = 14
    return render_template(
        'site_admin/traffic.html',
        days=days,
        summary=_traffic_summary(db, days=days),
        landings=_traffic_landings(db, days=days),
    )


# ---------------------------------------------------------------------------
# "View as league" impersonation — see app/impersonation.py for the design.
# ---------------------------------------------------------------------------

@bp.route('/impersonate/<int:league_id>', methods=['POST'])
@site_admin_required
def impersonate_start(league_id):
    db = get_db()
    league = db.execute(
        "SELECT league_id, league_name, active FROM leagues WHERE league_id = %s",
        (league_id,)
    ).fetchone()
    if not league:
        flash('League not found.', 'error')
        return redirect(url_for('site_admin.dashboard'))

    impersonation.start(db, session['user_id'], league['league_id'], league['league_name'])
    flash(
        f"Now viewing as {league['league_name']} — every action is logged. "
        f"Ends automatically in {impersonation.MAX_DURATION_MINUTES} minutes, or click Exit any time.",
        'info'
    )
    return redirect(url_for('admin.landing'))


@bp.route('/impersonate/end', methods=['POST'])
def impersonate_end():
    if not session.get('impersonating'):
        return redirect(url_for('site_admin.dashboard'))
    db = get_db()
    impersonation.end(db, reason='manual')
    flash('Exited "view as league" — back to your Site Admin session.', 'success')
    return redirect(url_for('site_admin.dashboard'))


def _impersonation_sessions(db, days=30, limit=50):
    """Every impersonation session in the window, paired with its end row
    (if any) and the full list of requests made during it -- the audit
    trail view. Wrapped in try/except like the rest of this dashboard's
    aggregate queries (Postgres-only)."""
    try:
        starts = db.execute(
            """SELECT a.audit_id, a.site_admin_user_id, a.league_id, a.ts,
                      u.email AS site_admin_email, l.league_name
               FROM site_admin_audit_log a
               LEFT JOIN users u ON u.user_id = a.site_admin_user_id
               LEFT JOIN leagues l ON l.league_id = a.league_id
               WHERE a.action = 'impersonation_start'
                 AND a.ts >= NOW() - INTERVAL '1 day' * %s
               ORDER BY a.ts DESC
               LIMIT %s""",
            (days, limit)
        ).fetchall()
    except Exception:
        return []

    result = []
    for s in starts:
        try:
            end_row = db.execute(
                "SELECT ts, detail FROM site_admin_audit_log "
                "WHERE ref_id = %s AND action = 'impersonation_end'",
                (s['audit_id'],)
            ).fetchone()
            reqs = db.execute(
                "SELECT method, path, status_code, ts FROM site_admin_audit_log "
                "WHERE ref_id = %s AND action = 'request' ORDER BY ts",
                (s['audit_id'],)
            ).fetchall()
        except Exception:
            end_row, reqs = None, []
        result.append({'start': s, 'end': end_row, 'requests': reqs})
    return result


@bp.route('/audit')
@site_admin_required
def audit():
    db = get_db()
    return render_template(
        'site_admin/audit.html',
        sessions=_impersonation_sessions(db),
    )
