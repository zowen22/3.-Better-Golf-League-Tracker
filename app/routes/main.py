import datetime
from flask import Blueprint, render_template, session, redirect, url_for
from database import get_db, load_nicknames, player_display_name, get_current_season_id
from routes.auth import login_required
from routes.self_report import pending_count as _pending_count
from routes.seasons import season_is_over

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

    # Get current season (the one the user has switched to)
    season_id = get_current_season_id(db, league_id)
    season = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone() if season_id else None

    if not season:
        return render_template('dashboard.html',
            season=None,
            recent_rounds=[],
            upcoming=[],
            standings=[],
            hdcp_updates=[],
            announcements=[],
            recap_week=None,
            medalists=[],
            net_lows=[],
            odds_and_ends=None,
            show_start_next_cta=False,
            show_announcements_widget=True,
            show_round_recap_widget=True,
            show_activity_feed_widget=True,
            show_league_activity_widget=True,
        )

    season_id = season['season_id']

    # "Start Another Season" CTA: admin-only, shown once the current season
    # has concluded. One extra query, computed here (not in the template).
    show_start_next_cta = (session.get('role') == 'league_admin'
                            and season_is_over(db, season_id))

    today_str = datetime.date.today().isoformat()

    # ── 1. Most recent fully-complete week ────────────────────────────────────
    # A week is "complete" when every non-bye matchup in it has status='completed'.
    last_complete_week = db.execute(
        """SELECT week_number
           FROM matchups
           WHERE season_id = %s AND is_bye = 0
           GROUP BY week_number
           HAVING COUNT(*) > 0
              AND COUNT(*) = SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)
           ORDER BY week_number DESC
           LIMIT 1""",
        (season_id,)
    ).fetchone()

    recent_rounds = []
    if last_complete_week:
        completed = db.execute(
            """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                      t1.team_id AS team1_id, t2.team_id AS team2_id,
                      COALESCE(NULLIF(t1.team_name,''), p1a.last_name || ' & ' || p2a.last_name) AS team1_name,
                      COALESCE(NULLIF(t2.team_name,''), p1b.last_name || ' & ' || p2b.last_name) AS team2_name,
                      r.round_id
               FROM matchups m
               JOIN teams   t1  ON m.team1_id   = t1.team_id
               JOIN teams   t2  ON m.team2_id   = t2.team_id
               LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
               LEFT JOIN players p2a ON t1.player2_id = p2a.player_id
               LEFT JOIN players p1b ON t2.player1_id = p1b.player_id
               LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
               JOIN rounds r    ON r.matchup_id = m.matchup_id
               WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
               ORDER BY m.matchup_id ASC""",
            (season_id, last_complete_week['week_number'])
        ).fetchall()

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
                winner = None
            recent_rounds.append({
                'matchup_id':  match['matchup_id'],
                'round_id':    match['round_id'],
                'week_number': match['week_number'],
                'season_id':   season_id,
                'date':        match['scheduled_date'],
                'team1_name':  match['team1_name'],
                'team2_name':  match['team2_name'],
                't1_pts':      t1_pts,
                't2_pts':      t2_pts,
                'winner':      winner,
                'has_scores':  has_scores,
            })

    # Detect a pending week: past its scheduled date but not fully entered
    pending_week_row = db.execute(
        """SELECT week_number
           FROM matchups
           WHERE season_id = %s AND is_bye = 0
             AND scheduled_date IS NOT NULL AND scheduled_date <= %s
           GROUP BY week_number
           HAVING COUNT(*) > SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)
           ORDER BY week_number DESC
           LIMIT 1""",
        (season_id, today_str)
    ).fetchone()
    pending_week = pending_week_row['week_number'] if pending_week_row else None

    # ── 2. Up Next: next week chronologically by date relative to today ───────
    next_week_row = db.execute(
        """SELECT week_number, MIN(scheduled_date) AS week_date
           FROM matchups
           WHERE season_id = %s AND is_bye = 0
             AND scheduled_date IS NOT NULL AND scheduled_date >= %s
           GROUP BY week_number
           ORDER BY week_date ASC, week_number ASC
           LIMIT 1""",
        (season_id, today_str)
    ).fetchone()

    upcoming = []
    if next_week_row:
        upcoming_rows = db.execute(
            """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                      COALESCE(NULLIF(t1.team_name,''), p1a.last_name || ' & ' || p2a.last_name) AS team1_name,
                      COALESCE(NULLIF(t2.team_name,''), p1b.last_name || ' & ' || p2b.last_name) AS team2_name
               FROM matchups m
               LEFT JOIN teams   t1  ON m.team1_id   = t1.team_id
               LEFT JOIN teams   t2  ON m.team2_id   = t2.team_id
               LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
               LEFT JOIN players p2a ON t1.player2_id = p2a.player_id
               LEFT JOIN players p1b ON t2.player1_id = p1b.player_id
               LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
               WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
               ORDER BY m.matchup_id ASC""",
            (season_id, next_week_row['week_number'])
        ).fetchall()
        upcoming = [dict(u) for u in upcoming_rows]

    # ── 3. Standings snapshot (all teams, ranked) ─────────────────────────────
    standings_rows = db.execute(
        """SELECT t.team_id,
                  COALESCE(NULLIF(t.team_name,''), p1.last_name || ' & ' || p2.last_name) AS team_name,
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
    from routes.handicap import PRE_ELIGIBILITY_MARKER_PREFIX
    hdcp_rows = db.execute(
        """SELECT hh.player_id, hh.handicap_index, hh.calculated_date, hh.override_reason,
                  p.first_name, p.last_name
           FROM handicap_history hh
           JOIN players p ON hh.player_id = p.player_id
           WHERE p.league_id = %s
           ORDER BY hh.calculated_date DESC, hh.handicap_id DESC
           LIMIT 30""",
        (league_id,)
    ).fetchall()
    from routes.scores import get_league_settings, calc_playing_handicap
    _settings = get_league_settings(db, season_id, league_id)
    _hpct = float(_settings['handicap_percent']) if _settings else 90.0
    _hmax = float(_settings['max_handicap_index']) if _settings else 18.0

    seen_players = set()
    hdcp_updates = []
    for h in hdcp_rows:
        if h['player_id'] not in seen_players:
            seen_players.add(h['player_id'])
            row = dict(h)
            row['is_provisional'] = bool(h['override_reason'] and
                                          h['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))
            # Provisional rows already store a final playing handicap.
            row['playing_hcp'] = (row['handicap_index'] if row['is_provisional']
                                   else calc_playing_handicap(row['handicap_index'], _hpct, _hmax))
            hdcp_updates.append(row)
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
        "SELECT self_reporting_enabled, show_dues_shame_widget, "
        "show_announcements_widget, show_round_recap_widget, "
        "show_activity_feed_widget, show_league_activity_widget "
        "FROM league_settings WHERE league_id = %s AND season_id = %s",
        (league_id, season_id)
    ).fetchone()
    self_reporting_enabled = bool(ls['self_reporting_enabled']) if ls else False

    # Member-dashboard widget visibility (admin-controlled). Columns are NOT NULL
    # DEFAULT 1, so a real settings row always yields 0/1; when no row exists yet
    # (brand-new league) default to visible. These gate the MEMBER view only —
    # admins always see all widgets (see dashboard.html).
    show_announcements_widget   = bool(ls['show_announcements_widget'])   if ls else True
    show_round_recap_widget     = bool(ls['show_round_recap_widget'])     if ls else True
    show_activity_feed_widget   = bool(ls['show_activity_feed_widget'])   if ls else True
    show_league_activity_widget = bool(ls['show_league_activity_widget']) if ls else True

    # ── Dues shame widget ─────────────────────────────────────────────────────
    dues_shame_data = None
    if ls and ls['show_dues_shame_widget']:
        all_players_in_season = db.execute(
            """SELECT DISTINCT p.player_id, p.first_name, p.last_name
               FROM players p
               JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
               WHERE t.season_id = %s AND t.league_id = %s AND p.active = 1
               ORDER BY p.last_name, p.first_name""",
            (season_id, league_id)
        ).fetchall()
        paid_ids = set(r['player_id'] for r in db.execute(
            "SELECT DISTINCT player_id FROM dues_payments WHERE season_id = %s AND league_id = %s",
            (season_id, league_id)
        ).fetchall())
        dues_shame_data = {
            'players': [
                {**dict(p), 'paid': p['player_id'] in paid_ids}
                for p in all_players_in_season
            ],
            'paid_count': sum(1 for p in all_players_in_season if p['player_id'] in paid_ids),
            'total_count': len(all_players_in_season),
        }

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

    # ── 8. Round recap widgets (medalist, net lows, odds & ends) ─────────────
    recap_week = last_complete_week['week_number'] if last_complete_week else None
    medalists = []
    net_lows = []
    odds_and_ends = None

    if recap_week is not None:
        nicknames = load_nicknames(db, league_id)

        medalist_rows = db.execute(
            """SELECT p.player_id, p.first_name, p.last_name,
                      SUM(hs.gross_score) AS total_gross
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id = r.round_id
               JOIN matchups m    ON r.matchup_id = m.matchup_id
               JOIN players p     ON sc.player_id = p.player_id
               WHERE m.season_id = %s AND m.week_number = %s
                 AND m.is_bye = 0 AND sc.is_absent = 0
               GROUP BY p.player_id, p.first_name, p.last_name
               ORDER BY total_gross ASC
               LIMIT 5""",
            (season_id, recap_week)
        ).fetchall()
        for r in medalist_rows:
            row = dict(r)
            row['display_name'] = player_display_name(
                row['player_id'], row['first_name'], row['last_name'], nicknames
            )
            medalists.append(row)

        net_rows = db.execute(
            """SELECT p.player_id, p.first_name, p.last_name,
                      SUM(hs.net_score) AS total_net
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id = r.round_id
               JOIN matchups m    ON r.matchup_id = m.matchup_id
               JOIN players p     ON sc.player_id = p.player_id
               WHERE m.season_id = %s AND m.week_number = %s
                 AND m.is_bye = 0 AND sc.is_absent = 0
                 AND hs.net_score IS NOT NULL
               GROUP BY p.player_id, p.first_name, p.last_name
               HAVING SUM(hs.net_score) IS NOT NULL
               ORDER BY total_net ASC
               LIMIT 5""",
            (season_id, recap_week)
        ).fetchall()
        for r in net_rows:
            row = dict(r)
            row['display_name'] = player_display_name(
                row['player_id'], row['first_name'], row['last_name'], nicknames
            )
            row['total_net_int'] = round(row['total_net'])
            net_lows.append(row)

        reflection_row = db.execute(
            """SELECT odds_and_ends FROM round_reflections
               WHERE league_id = %s AND season_id = %s AND week_number = %s""",
            (league_id, season_id, recap_week)
        ).fetchone()
        if reflection_row:
            odds_and_ends = reflection_row['odds_and_ends']

    return render_template('dashboard.html',
        season=dict(season),
        recent_rounds=recent_rounds,
        upcoming=upcoming,
        pending_week=pending_week,
        standings=standings,
        hdcp_updates=hdcp_updates,
        completed_count=completed_count,
        total_rounds=total_rounds,
        pending_submission_count=pending_submission_count,
        self_reporting_enabled=self_reporting_enabled,
        announcements=announcements,
        activity_feed=activity_feed,
        dues_shame_data=dues_shame_data,
        recap_week=recap_week,
        medalists=medalists,
        net_lows=net_lows,
        odds_and_ends=odds_and_ends,
        show_start_next_cta=show_start_next_cta,
        show_announcements_widget=show_announcements_widget,
        show_round_recap_widget=show_round_recap_widget,
        show_activity_feed_widget=show_activity_feed_widget,
        show_league_activity_widget=show_league_activity_widget,
    )
