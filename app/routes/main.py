import datetime
from flask import Blueprint, render_template, session, redirect, url_for
from database import get_db
from routes.auth import login_required
from routes.self_report import pending_count as _pending_count

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    if 'league_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@bp.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    league_id = session['league_id']

    # Get current/latest season
    season = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (league_id,)
    ).fetchone()

    if not season:
        return render_template('dashboard.html',
            season=None,
            recent_rounds=[],
            upcoming=[],
            standings=[],
            hdcp_updates=[],
            announcements=[],
        )

    season_id = season['season_id']

    # ── 1. Recent completed rounds (last 5 non-bye matchups) ─────────────────
    completed = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                  t1.team_name AS team1_name, t1.team_id AS team1_id,
                  t2.team_name AS team2_name, t2.team_id AS team2_id,
                  r.round_id
           FROM matchups m
           JOIN teams  t1 ON m.team1_id    = t1.team_id
           JOIN teams  t2 ON m.team2_id    = t2.team_id
           JOIN rounds r  ON r.matchup_id  = m.matchup_id
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           ORDER BY m.week_number DESC, m.matchup_id DESC
           LIMIT 5""",
        (season_id,)
    ).fetchall()

    recent_rounds = []
    for match in completed:
        pts_rows = db.execute(
            "SELECT team_id, SUM(total_points) AS pts FROM match_results WHERE matchup_id = %s GROUP BY team_id",
            (match['matchup_id'],)
        ).fetchall()
        team_pts = {r['team_id']: (r['pts'] or 0) for r in pts_rows}
        t1_pts = team_pts.get(match['team1_id'], 0)
        t2_pts = team_pts.get(match['team2_id'], 0)

        has_scores = len(pts_rows) > 0
        if t1_pts > t2_pts:
            winner = match['team1_name']
        elif t2_pts > t1_pts:
            winner = match['team2_name']
        else:
            winner = None  # tie (only meaningful when has_scores)

        recent_rounds.append({
            'matchup_id':  match['matchup_id'],
            'round_id':    match['round_id'],
            'week_number': match['week_number'],
            'date':        match['scheduled_date'],
            'team1_name':  match['team1_name'],
            'team2_name':  match['team2_name'],
            't1_pts':      t1_pts,
            't2_pts':      t2_pts,
            'winner':      winner,
            'has_scores':  has_scores,
        })

    # ── 2. Upcoming scheduled matchups (next 3, soonest first) ───────────────
    upcoming_rows = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                  t1.team_name AS team1_name, t2.team_name AS team2_name
           FROM matchups m
           LEFT JOIN teams t1 ON m.team1_id = t1.team_id
           LEFT JOIN teams t2 ON m.team2_id = t2.team_id
           WHERE m.season_id = %s AND m.status = 'scheduled' AND m.is_bye = 0
           ORDER BY m.scheduled_date ASC, m.matchup_id ASC
           LIMIT 3""",
        (season_id,)
    ).fetchall()
    upcoming = [dict(u) for u in upcoming_rows]

    # ── 3. Standings snapshot (all teams, ranked) ─────────────────────────────
    standings_rows = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.last_name AS p1_last, p2.last_name AS p2_last,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts
           FROM teams t
           LEFT JOIN players p1       ON t.player1_id  = p1.player_id
           LEFT JOIN players p2       ON t.player2_id  = p2.player_id
           LEFT JOIN match_results mr ON mr.team_id    = t.team_id
           LEFT JOIN matchups m       ON mr.matchup_id = m.matchup_id
                                     AND m.season_id   = %s
           WHERE t.season_id = %s AND t.league_id = %s
           GROUP BY t.team_id, t.team_name, p1.last_name, p2.last_name
           ORDER BY total_pts DESC""",
        (season_id, season_id, league_id)
    ).fetchall()
    standings = [dict(s) for s in standings_rows]

    # ── 4. Recent handicap updates (most recent per player, up to 6) ──────────
    hdcp_rows = db.execute(
        """SELECT hh.player_id, hh.handicap_index, hh.calculated_date,
                  p.first_name, p.last_name
           FROM handicap_history hh
           JOIN players p ON hh.player_id = p.player_id
           WHERE p.league_id = %s
           ORDER BY hh.calculated_date DESC, hh.handicap_id DESC
           LIMIT 30""",
        (league_id,)
    ).fetchall()
    seen_players = set()
    hdcp_updates = []
    for h in hdcp_rows:
        if h['player_id'] not in seen_players:
            seen_players.add(h['player_id'])
            hdcp_updates.append(dict(h))
        if len(hdcp_updates) >= 6:
            break

    # ── 5. Season stats summary ───────────────────────────────────────────────
    completed_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id = %s AND status = 'completed' AND is_bye = 0",
        (season_id,)
    ).fetchone()['cnt']

    scheduled_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id = %s AND status = 'scheduled' AND is_bye = 0",
        (season_id,)
    ).fetchone()['cnt']

    total_rounds = completed_count + scheduled_count

    pending_submission_count = _pending_count(db, league_id)

    ls = db.execute(
        "SELECT self_reporting_enabled FROM league_settings WHERE league_id = %s",
        (league_id,)
    ).fetchone()
    self_reporting_enabled = bool(ls['self_reporting_enabled']) if ls else False

    # ── 6. Active announcements ───────────────────────────────────────────────
    today = datetime.date.today().isoformat()
    ann_rows = db.execute(
        """SELECT * FROM notifications
           WHERE league_id = %s AND active = 1
             AND (display_until IS NULL OR display_until = '' OR display_until >= %s)
           ORDER BY created_date DESC
           LIMIT 5""",
        (league_id, today)
    ).fetchall()
    announcements = [dict(a) for a in ann_rows]

    # ── 7. Unified activity feed (league_events + recent announcements) ─────────
    from datetime import datetime as _dt, timedelta as _td
    now_utc = _dt.utcnow()

    event_rows = db.execute(
        """SELECT 'event' AS src, event_id AS id, event_type AS type,
                  message, created_at AS ts, ref_id, season_id
           FROM league_events
           WHERE league_id = %s
             AND created_at >= (CURRENT_DATE - INTERVAL '60 days')::text
           ORDER BY created_at DESC
           LIMIT 20""",
        (league_id,)
    ).fetchall()

    ann_rows2 = db.execute(
        """SELECT 'announcement' AS src, notification_id AS id, type,
                  message, created_date AS ts, NULL AS ref_id, NULL AS season_id
           FROM notifications
           WHERE league_id = %s AND active = 1
           ORDER BY created_date DESC
           LIMIT 10""",
        (league_id,)
    ).fetchall()

    EVENT_ICONS = {
        'round_completed': '🏌️',
        'sub_assigned':    '🔄',
        'announcement':    '📢',
        'info':            '📋',
        'alert':           '⚠️',
        'reminder':        '🔔',
        'score':           '⛳',
        'result':          '🏆',
    }
    ANN_ICONS = {
        'info':     '📋',
        'result':   '🏆',
        'reminder': '🔔',
        'alert':    '⚠️',
        'score':    '⛳',
    }

    def _relative_time(ts_str):
        try:
            if not ts_str:
                return ''
            ts = _dt.strptime(ts_str[:19], '%Y-%m-%d %H:%M:%S') if ' ' in ts_str else _dt.strptime(ts_str[:10], '%Y-%m-%d')
            diff = now_utc - ts
            if diff < _td(minutes=1):
                return 'just now'
            if diff < _td(hours=1):
                m = int(diff.total_seconds() // 60)
                return f'{m}m ago'
            if diff < _td(hours=24):
                h = int(diff.total_seconds() // 3600)
                return f'{h}h ago'
            d = diff.days
            if d == 1:
                return 'Yesterday'
            if d < 7:
                return f'{d} days ago'
            if d < 14:
                return '1 week ago'
            if d < 30:
                return f'{d // 7} weeks ago'
            return ts_str[:10]
        except Exception:
            return ts_str[:10] if ts_str else ''

    activity_feed = []
    for r in event_rows:
        activity_feed.append({
            'src':     'event',
            'id':      r['id'],
            'type':    r['type'],
            'icon':    EVENT_ICONS.get(r['type'], '📌'),
            'message': r['message'],
            'ts':      r['ts'],
            'rel_ts':  _relative_time(r['ts']),
            'ref_id':  r['ref_id'],
        })
    for r in ann_rows2:
        activity_feed.append({
            'src':     'announcement',
            'id':      r['id'],
            'type':    r['type'] or 'info',
            'icon':    ANN_ICONS.get(r['type'] or 'info', '📢'),
            'message': r['message'],
            'ts':      r['ts'],
            'rel_ts':  _relative_time(r['ts']),
            'ref_id':  None,
        })

    activity_feed.sort(key=lambda x: x['ts'] or '', reverse=True)
    activity_feed = activity_feed[:15]

    return render_template('dashboard.html',
        season=dict(season),
        recent_rounds=recent_rounds,
        upcoming=upcoming,
        standings=standings,
        hdcp_updates=hdcp_updates,
        completed_count=completed_count,
        total_rounds=total_rounds,
        pending_submission_count=pending_submission_count,
        self_reporting_enabled=self_reporting_enabled,
        announcements=announcements,
        activity_feed=activity_feed,
    )
