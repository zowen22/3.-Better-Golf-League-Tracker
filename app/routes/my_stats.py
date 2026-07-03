from flask import Blueprint, render_template, session, redirect, url_for, flash
from database import get_db, get_current_season_id
from routes.auth import login_required
from routes.handicap import PRE_ELIGIBILITY_MARKER_PREFIX

bp = Blueprint('my_stats', __name__, url_prefix='/my-stats')


def _get_player_handicap(db, player_id, league_id=None):
    """Return (effective handicap (computed + committee adjustment), is_provisional).

    is_provisional=True means the latest handicap_history row is a
    pre-eligibility temp handicap — its handicap_index is ALREADY a final
    playing-handicap-equivalent value, so callers must NOT run it through
    calc_playing_handicap() again (that would double-apply a percent)."""
    row = db.execute(
        """SELECT handicap_index, override_reason FROM handicap_history
           WHERE player_id = %s
           ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1""",
        (player_id,)
    ).fetchone()
    is_provisional = False
    base = float(row['handicap_index']) if row else None
    if row:
        is_provisional = bool(row['override_reason'] and
                               row['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))
    if base is None:
        pr = db.execute("SELECT starting_handicap FROM players WHERE player_id = %s", (player_id,)).fetchone()
        base = float(pr['starting_handicap']) if pr and pr['starting_handicap'] is not None else 0.0
    if league_id:
        try:
            adj = db.execute(
                "SELECT adjustment FROM handicap_adjustments WHERE player_id = %s AND league_id = %s",
                (player_id, league_id)
            ).fetchone()
            if adj:
                base += float(adj['adjustment'])
        except Exception:
            pass
    return round(base, 1), is_provisional


@bp.route('/')
@login_required
def index():
    player_id = session.get('player_id')
    if not player_id:
        flash('Your account is not linked to a player. Ask your admin to link your account.', 'info')
        return redirect(url_for('main.dashboard'))

    db        = get_db()
    league_id = session['league_id']

    # -- Player info --
    player = db.execute(
        "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player record not found.', 'error')
        return redirect(url_for('main.dashboard'))

    # -- Current season --
    _current_season_id = get_current_season_id(db, league_id)
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (_current_season_id, league_id)
    ).fetchone() if _current_season_id else None

    # -- Current handicap --
    current_hdcp, current_hdcp_provisional = _get_player_handicap(db, player_id, league_id)

    from routes.scores import get_league_settings
    from routes.scores import calc_playing_handicap
    _season_id = season['season_id'] if season else None
    _settings  = get_league_settings(db, _season_id, league_id) if _season_id else None
    _hpct = float(_settings['handicap_percent']) if _settings else 90.0
    _hmax = float(_settings['max_handicap_index']) if _settings else 18.0
    if current_hdcp is not None and not current_hdcp_provisional:
        # A provisional value is already a final playing handicap — running
        # it through calc_playing_handicap again would double-apply a percent.
        current_hdcp = calc_playing_handicap(current_hdcp, _hpct, _hmax)

    # -- Handicap trend (last 10 history entries) --
    hcp_hist = db.execute(
        """SELECT handicap_index, calculated_date, override_reason
           FROM handicap_history WHERE player_id = %s
           ORDER BY calculated_date DESC, handicap_id DESC LIMIT 10""",
        (player_id,)
    ).fetchall()
    hcp_hist = list(reversed(hcp_hist))   # chronological order
    # Convert each entry to playing hcp for display — except provisional
    # entries, whose handicap_index is already a final playing handicap.
    hcp_hist = [
        {'handicap_index': float(h['handicap_index']) if (h['override_reason'] and
             h['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))
             else calc_playing_handicap(float(h['handicap_index']), _hpct, _hmax),
         'calculated_date': h['calculated_date'],
         'is_provisional': bool(h['override_reason'] and
             h['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))}
        for h in hcp_hist
    ]
    sparkline_pts = []
    if len(hcp_hist) >= 2:
        vals  = [float(h['handicap_index']) for h in hcp_hist]
        lo, hi = min(vals), max(vals)
        spread = hi - lo if hi != lo else 1.0
        W, H   = 220, 50
        for i, v in enumerate(vals):
            x = round(i / max(len(vals) - 1, 1) * W, 1)
            y = round(H - (v - lo) / spread * (H - 6), 1)
            sparkline_pts.append((x, y))

    # -- My team this season --
    my_team = None
    teammate = None
    if season:
        team_row = db.execute(
            """SELECT t.*, p1.first_name AS p1_first, p1.last_name AS p1_last,
                      p2.first_name AS p2_first, p2.last_name AS p2_last
               FROM teams t
               LEFT JOIN players p1 ON t.player1_id = p1.player_id
               LEFT JOIN players p2 ON t.player2_id = p2.player_id
               WHERE t.season_id = %s AND t.league_id = %s
                 AND (t.player1_id = %s OR t.player2_id = %s)""",
            (season['season_id'], league_id, player_id, player_id)
        ).fetchone()
        if team_row:
            my_team = dict(team_row)
            partner_id = team_row['player2_id'] if team_row['player1_id'] == player_id else team_row['player1_id']
            if partner_id:
                teammate = db.execute(
                    "SELECT player_id, first_name, last_name FROM players WHERE player_id = %s",
                    (partner_id,)
                ).fetchone()

    # -- Season stats (current season) --
    season_stats = {'rounds': 0, 'total_pts': 0.0, 'wins': 0, 'ties': 0, 'losses': 0,
                    'gross_list': [], 'avg_gross': None, 'best_gross': None}
    team_standing = None

    if season and my_team:
        sid = season['season_id']

        # Match results
        # Simpler: just get totals from match_results + hole_scores separately
        mr_rows = db.execute(
            """SELECT mr.total_points, mr.overall_point_won
               FROM match_results mr
               JOIN matchups m ON m.matchup_id = mr.matchup_id
               WHERE mr.player_id = %s AND m.season_id = %s AND m.status = 'completed'""",
            (player_id, sid)
        ).fetchall()

        gross_rows = db.execute(
            """SELECT SUM(hs.gross_score) AS gross_total
               FROM scorecards sc
               JOIN rounds r   ON sc.round_id   = r.round_id
               JOIN matchups m ON r.matchup_id  = m.matchup_id
               JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
               WHERE sc.player_id = %s AND m.season_id = %s AND m.status = 'completed'
                 AND sc.is_absent = 0
               GROUP BY m.matchup_id""",
            (player_id, sid)
        ).fetchall()

        for r in mr_rows:
            # Points/W-T-L intentionally include ghost matches — governed by
            # the absence_overall_point_policy setting, not a blanket filter.
            season_stats['total_pts']  += float(r['total_points'] or 0)
            owp = float(r['overall_point_won'] or 0)
            if owp >= 1.0:
                season_stats['wins']   += 1
            elif owp >= 0.5:
                season_stats['ties']   += 1
            else:
                season_stats['losses'] += 1

        for g in gross_rows:
            if g['gross_total'] is not None:
                season_stats['gross_list'].append(int(g['gross_total']))

        # "Rounds played" is a gross-score concept — exclude ghosts. gross_rows
        # already filters is_absent = 0 (one row per non-absent round).
        season_stats['rounds'] = len(gross_rows)

        glist = season_stats['gross_list']
        if glist:
            season_stats['avg_gross']  = round(sum(glist) / len(glist), 1)
            season_stats['best_gross'] = min(glist)

        # Team standing
        standings = db.execute(
            """SELECT t.team_id, COALESCE(SUM(mr.total_points), 0) AS pts
               FROM teams t
               LEFT JOIN match_results mr ON mr.team_id = t.team_id
               LEFT JOIN matchups m ON m.matchup_id = mr.matchup_id AND m.season_id = %s
               WHERE t.season_id = %s AND t.league_id = %s
               GROUP BY t.team_id
               ORDER BY pts DESC""",
            (sid, sid, league_id)
        ).fetchall()
        for rank, row in enumerate(standings, 1):
            if row['team_id'] == my_team['team_id']:
                team_standing = {'rank': rank, 'total': len(standings), 'pts': float(row['pts'])}
                break

    # -- Recent 5 rounds (any season) --
    recent_rounds = []
    recent_raw = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.season_id,
                  s.season_name,
                  mr.total_points, mr.overall_point_won, mr.role,
                  sc.scorecard_id,
                  r.round_date
           FROM match_results mr
           JOIN matchups  m  ON m.matchup_id  = mr.matchup_id
           JOIN seasons   s  ON m.season_id   = s.season_id
           JOIN rounds    r  ON r.matchup_id  = m.matchup_id
           JOIN scorecards sc ON sc.player_id = mr.player_id AND sc.round_id = r.round_id
           WHERE mr.player_id = %s AND s.league_id = %s AND m.status = 'completed'
             AND sc.is_absent = 0
           ORDER BY r.round_date DESC, r.round_id DESC
           LIMIT 5""",
        (player_id, league_id)
    ).fetchall()

    for row in recent_raw:
        gross = db.execute(
            "SELECT SUM(gross_score) AS g FROM hole_scores WHERE scorecard_id = %s",
            (row['scorecard_id'],)
        ).fetchone()
        owp = float(row['overall_point_won'] or 0)
        outcome = 'Win' if owp >= 1.0 else ('Tie' if owp >= 0.5 else 'Loss')
        recent_rounds.append({
            'matchup_id':  row['matchup_id'],
            'week_number': row['week_number'],
            'date':        row['round_date'] or row['scheduled_date'],
            'season_name': row['season_name'],
            'gross_total': int(gross['g']) if gross and gross['g'] is not None else None,
            'total_pts':   float(row['total_points'] or 0),
            'role':        row['role'],
            'outcome':     outcome,
        })

    # -- Upcoming round for my team --
    upcoming_matchup = None
    if season and my_team:
        up = db.execute(
            """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.tee_time,
                      m.starting_hole, m.status,
                      t_opp.team_name AS opp_name,
                      p1.last_name AS opp_p1_last, p2.last_name AS opp_p2_last,
                      c.course_name, te.tee_name
               FROM matchups m
               LEFT JOIN teams t_opp ON (m.team1_id = t_opp.team_id OR m.team2_id = t_opp.team_id)
                         AND t_opp.team_id != %s
               LEFT JOIN players p1 ON t_opp.player1_id = p1.player_id
               LEFT JOIN players p2 ON t_opp.player2_id = p2.player_id
               LEFT JOIN courses c  ON m.course_id = c.course_id
               LEFT JOIN tees    te ON m.tee_id    = te.tee_id
               WHERE m.season_id = %s AND m.status = 'scheduled' AND m.is_bye = 0
                 AND (m.team1_id = %s OR m.team2_id = %s)
               ORDER BY m.scheduled_date ASC, m.week_number ASC
               LIMIT 1""",
            (my_team['team_id'], season['season_id'], my_team['team_id'], my_team['team_id'])
        ).fetchone()
        if up:
            opp_label = up['opp_name'] or f"{up['opp_p1_last'] or '?'} / {up['opp_p2_last'] or '?'}"
            upcoming_matchup = {
                'matchup_id':   up['matchup_id'],
                'week_number':  up['week_number'],
                'date':         up['scheduled_date'],
                'tee_time':     up['tee_time'],
                'starting_hole':up['starting_hole'],
                'opp_label':    opp_label,
                'course_name':  up['course_name'],
                'tee_name':     up['tee_name'],
            }

    # -- Dues status --
    dues_status = None
    if season:
        try:
            payment = db.execute(
                "SELECT * FROM dues_payments WHERE player_id = %s AND season_id = %s",
                (player_id, season['season_id'])
            ).fetchone()
            dues_cfg = db.execute(
                "SELECT dues_amount, dues_due_date FROM league_settings WHERE season_id = %s AND league_id = %s",
                (season['season_id'], league_id)
            ).fetchone()
            if dues_cfg:
                dues_status = {
                    'paid':     payment is not None,
                    'amount':   dues_cfg['dues_amount'],
                    'due_date': dues_cfg['dues_due_date'],
                }
        except Exception:
            pass

    # -- Unread notifications count --
    unread_count = 0
    user_id = session.get('user_id')
    if user_id:
        try:
            unread_count = db.execute(
                """SELECT COUNT(*) AS cnt FROM notifications n
                   WHERE n.league_id = %s AND n.active = 1
                     AND n.notification_id NOT IN (
                         SELECT notification_id FROM notification_reads WHERE user_id = %s)""",
                (league_id, user_id)
            ).fetchone()['cnt']
        except Exception:
            pass

    return render_template('my_stats/index.html',
                           player=player,
                           season=season,
                           current_hdcp=current_hdcp,
                           sparkline_pts=sparkline_pts,
                           hcp_hist=hcp_hist,
                           my_team=my_team,
                           teammate=teammate,
                           team_standing=team_standing,
                           season_stats=season_stats,
                           recent_rounds=recent_rounds,
                           upcoming_matchup=upcoming_matchup,
                           dues_status=dues_status,
                           unread_count=unread_count)
