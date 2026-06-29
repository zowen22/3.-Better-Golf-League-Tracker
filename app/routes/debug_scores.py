"""
Debug scorecard page — shows hcp index before/after each round and team
points before/after per week. Admin-only. May become a permanent audit page.
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash
from database import get_db
from routes.auth import login_required

bp = Blueprint('debug_scores', __name__, url_prefix='/debug')


@bp.route('/scorecards/<int:season_id>/week/<int:week_num>')
@login_required
def week_debug(season_id, week_num):
    if session.get('role') != 'league_admin':
        flash('Admin only.', 'error')
        return redirect(url_for('main.dashboard'))

    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    week_matchups = db.execute(
        """SELECT m.matchup_id, m.status, m.is_bye, m.week_number,
                  m.team1_id, m.team2_id, m.scheduled_date
           FROM matchups m
           WHERE m.season_id = %s AND m.week_number = %s
           ORDER BY m.matchup_id ASC""",
        (season_id, week_num)
    ).fetchall()

    blocks = []

    for m in week_matchups:
        if m['is_bye'] or m['status'] != 'completed':
            continue

        matchup_id = m['matchup_id']
        t1_id = m['team1_id']
        t2_id = m['team2_id']

        round_row = db.execute(
            "SELECT * FROM rounds WHERE matchup_id = %s", (matchup_id,)
        ).fetchone()
        if not round_row:
            continue
        round_id = round_row['round_id']

        # ── Team names ────────────────────────────────────────────────────────
        def team_display(team_id):
            t = db.execute(
                """SELECT t.team_name,
                          p1.last_name AS p1_last, p2.last_name AS p2_last
                   FROM teams t
                   LEFT JOIN players p1 ON t.player1_id = p1.player_id
                   LEFT JOIN players p2 ON t.player2_id = p2.player_id
                   WHERE t.team_id = %s""",
                (team_id,)
            ).fetchone()
            if not t:
                return f"Team {team_id}"
            if t['team_name']:
                return t['team_name']
            parts = [n for n in [t['p1_last'], t['p2_last']] if n]
            return ' & '.join(parts) or f"Team {team_id}"

        t1_name = team_display(t1_id)
        t2_name = team_display(t2_id)

        # ── Team points: this round ───────────────────────────────────────────
        def team_pts_round(team_id):
            r = db.execute(
                """SELECT COALESCE(SUM(total_points), 0) AS pts
                   FROM match_results
                   WHERE matchup_id = %s AND team_id = %s""",
                (matchup_id, team_id)
            ).fetchone()
            return float(r['pts']) if r else 0.0

        t1_pts_round = team_pts_round(t1_id)
        t2_pts_round = team_pts_round(t2_id)

        # ── Team points: cumulative after this week ───────────────────────────
        def team_pts_through_week(team_id, through_week):
            r = db.execute(
                """SELECT COALESCE(SUM(mr.total_points), 0) AS pts
                   FROM match_results mr
                   JOIN matchups m2 ON mr.matchup_id = m2.matchup_id
                   WHERE mr.team_id = %s
                     AND m2.season_id = %s
                     AND m2.week_number <= %s""",
                (team_id, season_id, through_week)
            ).fetchone()
            return float(r['pts']) if r else 0.0

        t1_pts_after = team_pts_through_week(t1_id, week_num)
        t2_pts_after = team_pts_through_week(t2_id, week_num)
        t1_pts_before = t1_pts_after - t1_pts_round
        t2_pts_before = t2_pts_after - t2_pts_round

        # ── Per-player HCP audit ──────────────────────────────────────────────
        sc_rows = db.execute(
            """SELECT sc.player_id, sc.handicap_at_time_of_play, sc.is_absent,
                      p.first_name, p.last_name
               FROM scorecards sc
               JOIN players p ON sc.player_id = p.player_id
               WHERE sc.round_id = %s
               ORDER BY sc.team_id, sc.player_id""",
            (round_id,)
        ).fetchall()

        player_debug = []
        for sc in sc_rows:
            pid = sc['player_id']
            playing_hcp = sc['handicap_at_time_of_play']

            # Index that was in effect BEFORE this round triggered a recalc
            before_row = db.execute(
                """SELECT handicap_index FROM handicap_history
                   WHERE player_id = %s
                     AND (trigger_round_id IS NULL OR trigger_round_id < %s)
                   ORDER BY calculated_date DESC, handicap_id DESC
                   LIMIT 1""",
                (pid, round_id)
            ).fetchone()
            hcp_before = before_row['handicap_index'] if before_row else None

            # Index computed BY this round
            after_row = db.execute(
                """SELECT handicap_index FROM handicap_history
                   WHERE player_id = %s AND trigger_round_id = %s
                   ORDER BY handicap_id DESC LIMIT 1""",
                (pid, round_id)
            ).fetchone()
            hcp_after = after_row['handicap_index'] if after_row else None

            if hcp_before is not None and hcp_after is not None:
                hcp_delta = round(hcp_after - hcp_before, 1)
            else:
                hcp_delta = None

            player_debug.append({
                'name':        f"{sc['first_name']} {sc['last_name']}",
                'is_absent':   bool(sc['is_absent']),
                'playing_hcp': round(playing_hcp) if playing_hcp is not None else None,
                'hcp_before':  hcp_before,
                'hcp_after':   hcp_after,
                'hcp_delta':   hcp_delta,
            })

        blocks.append({
            'matchup_id':    matchup_id,
            'round_id':      round_id,
            't1_name':       t1_name,
            't2_name':       t2_name,
            't1_pts_round':  t1_pts_round,
            't2_pts_round':  t2_pts_round,
            't1_pts_before': t1_pts_before,
            't2_pts_before': t2_pts_before,
            't1_pts_after':  t1_pts_after,
            't2_pts_after':  t2_pts_after,
            'players':       player_debug,
        })

    # Week dropdown (all completed weeks)
    completed_weeks = db.execute(
        """SELECT DISTINCT week_number, MIN(scheduled_date) AS week_date
           FROM matchups
           WHERE season_id = %s AND status = 'completed' AND is_bye = 0
           GROUP BY week_number
           ORDER BY week_number ASC""",
        (season_id,)
    ).fetchall()

    week_date = db.execute(
        "SELECT scheduled_date FROM matchups WHERE season_id=%s AND week_number=%s AND is_bye=0 LIMIT 1",
        (season_id, week_num)
    ).fetchone()

    return render_template(
        'debug/scorecards.html',
        season=season,
        season_id=season_id,
        week_num=week_num,
        week_date=week_date['scheduled_date'] if week_date else None,
        blocks=blocks,
        completed_weeks=completed_weeks,
    )
