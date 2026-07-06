"""
Debug scorecard page — shows hcp index before/after each round and team
points before/after per week. Admin-only. May become a permanent audit page.
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash
from database import get_db
from routes.auth import login_required
from routes.scores import strokes_on_hole

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
                hcp_delta = round(hcp_after - hcp_before, 2)
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


# ---------------------------------------------------------------------------
# Scoring Debug  /debug/scoring/<season_id>/week/<week_num>
# ---------------------------------------------------------------------------

@bp.route('/scoring/<int:season_id>/week/<int:week_num>')
@login_required
def week_scoring_debug(season_id, week_num):
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

    ls = db.execute(
        "SELECT scoring_mode, match_play_overall_point FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    scoring_mode      = (ls['scoring_mode']             or 'match_play') if ls else 'match_play'
    has_overall_point = bool(ls['match_play_overall_point']) if ls and ls['match_play_overall_point'] is not None else True

    def calc_stableford(net_vs_par):
        if net_vs_par <= -2: return 4
        if net_vs_par == -1: return 3
        if net_vs_par ==  0: return 2
        if net_vs_par ==  1: return 1
        return 0

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
        t1_id, t2_id = m['team1_id'], m['team2_id']

        round_row = db.execute("SELECT * FROM rounds WHERE matchup_id = %s", (matchup_id,)).fetchone()
        if not round_row:
            continue
        round_id = round_row['round_id']

        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (round_row['tee_id'],)
        ).fetchall()

        sc_rows = db.execute(
            """SELECT sc.scorecard_id, sc.player_id, sc.team_id,
                      sc.handicap_at_time_of_play AS hcp, sc.is_absent,
                      p.first_name, p.last_name,
                      mr.role, mr.hole_points_won, mr.overall_point_won,
                      mr.total_points, mr.opponent_player_id
               FROM scorecards sc
               JOIN players p ON sc.player_id = p.player_id
               LEFT JOIN match_results mr ON mr.player_id = sc.player_id
                                         AND mr.matchup_id = %s
               WHERE sc.round_id = %s
               ORDER BY sc.team_id, mr.role""",
            (matchup_id, round_id)
        ).fetchall()

        # Cross-check source: scorecards.is_absent is what actually drives
        # ghost-scoring/stats, but player_absences (a separate event log) can
        # drift out of sync — its writer deletes the row if an admin later
        # unchecks "absent," which doesn't retroactively touch an
        # already-saved round's scorecards.is_absent.
        pa_rows = db.execute(
            """SELECT player_id FROM player_absences
                WHERE matchup_id = %s AND sub_player_id IS NULL""",
            (matchup_id,)
        ).fetchall()
        pa_absent_ids = {r['player_id'] for r in pa_rows}

        player_holes = {}
        for sc in sc_rows:
            hs = db.execute(
                "SELECT * FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
                (sc['scorecard_id'],)
            ).fetchall()
            player_holes[sc['player_id']] = hs

        by_role = {}
        for sc in sc_rows:
            by_role[(sc['team_id'], sc['role'])] = sc

        def _name(sc):
            return f"{sc['first_name']} {sc['last_name']}" if sc else '?'

        def _first(sc):
            return sc['first_name'] if sc else '?'

        def _absence_mismatch_msg(sc):
            if not sc:
                return None
            sc_absent = bool(sc['is_absent'])
            pa_absent = sc['player_id'] in pa_absent_ids
            if sc_absent == pa_absent:
                return None
            if sc_absent:
                return (f"Data mismatch: scorecards.is_absent says {_first(sc)} was absent this round "
                        "(ghost score generated), but no player_absences record exists for them.")
            return (f"Data mismatch: a player_absences record marks {_first(sc)} absent this round, "
                    "but scorecards.is_absent says they were not — their score is treated as real. "
                    "This may be stale data from an edit after the round was completed.")

        def build_pair(sc1, sc2):
            if not sc1 and not sc2:
                return None
            hs1 = player_holes.get(sc1['player_id'] if sc1 else None, [])
            hs2 = player_holes.get(sc2['player_id'] if sc2 else None, [])

            # Hole-by-hole result: differential stroke allocation — only the
            # higher-handicap player receives strokes, equal to the handicap
            # gap. Overall point: absolute net (p1_net_tot/p2_net_tot below),
            # each player's own gross minus their own full playing handicap —
            # matches the corrected match_results engine's split.
            ph1 = (sc1['hcp'] or 0) if sc1 else 0
            ph2 = (sc2['hcp'] or 0) if sc2 else 0
            diff1 = ph1 - ph2
            diff2 = ph2 - ph1
            _hcp_idxs_dbg = [hh['handicap_index'] for hh in holes]
            n_holes_dbg = len(holes) or 9

            hole_rows = []
            p1_gross_tot = p2_gross_tot = 0
            p1_net_tot   = p2_net_tot   = 0
            p1_dnet_tot  = p2_dnet_tot  = 0
            p1_sb_tot    = p2_sb_tot    = 0

            for i, h in enumerate(holes):
                h1 = hs1[i] if i < len(hs1) else None
                h2 = hs2[i] if i < len(hs2) else None
                g1 = h1['gross_score'] if h1 else None
                g2 = h2['gross_score'] if h2 else None
                n1 = h1['net_score']   if h1 else None
                n2 = h2['net_score']   if h2 else None
                s1 = int(g1 - n1) if g1 is not None and n1 is not None else 0
                s2 = int(g2 - n2) if g2 is not None and n2 is not None else 0
                par = h['par']

                if scoring_mode == 'stableford':
                    sb1 = calc_stableford(int(n1) - par) if n1 is not None and par else None
                    sb2 = calc_stableford(int(n2) - par) if n2 is not None and par else None
                    p1_pts, p2_pts, result = sb1, sb2, None
                    if sb1 is not None: p1_sb_tot += sb1
                    if sb2 is not None: p2_sb_tot += sb2
                    dn1 = dn2 = ds1 = ds2 = None
                else:
                    if g1 is not None and g2 is not None:
                        ds1 = strokes_on_hole(diff1, h['handicap_index'], n_holes_dbg,
                                               hcp_indices=_hcp_idxs_dbg) if diff1 > 0 else 0
                        ds2 = strokes_on_hole(diff2, h['handicap_index'], n_holes_dbg,
                                               hcp_indices=_hcp_idxs_dbg) if diff2 > 0 else 0
                        dn1, dn2 = g1 - ds1, g2 - ds2
                        p1_dnet_tot += dn1
                        p2_dnet_tot += dn2
                        if dn1 < dn2:   p1_pts, p2_pts, result = 2, 0, 'p1'
                        elif dn2 < dn1: p1_pts, p2_pts, result = 0, 2, 'p2'
                        else:           p1_pts, p2_pts, result = 1, 1, 'tie'
                    else:
                        dn1 = dn2 = ds1 = ds2 = None
                        p1_pts, p2_pts, result = None, None, None

                if g1 is not None: p1_gross_tot += g1
                if g2 is not None: p2_gross_tot += g2
                if n1 is not None: p1_net_tot += int(n1)
                if n2 is not None: p2_net_tot += int(n2)

                hole_rows.append({
                    'hole_number': h['hole_number'],
                    'par': par,
                    'hcp_idx': h['handicap_index'],
                    'p1_gross': g1, 'p1_net': int(n1) if n1 is not None else None, 'p1_strokes': s1,
                    'p2_gross': g2, 'p2_net': int(n2) if n2 is not None else None, 'p2_strokes': s2,
                    'p1_dnet': dn1, 'p2_dnet': dn2, 'p1_dstrokes': ds1, 'p2_dstrokes': ds2,
                    'p1_pts': p1_pts, 'p2_pts': p2_pts, 'result': result,
                })

            # Overall point
            if scoring_mode == 'stableford':
                if   p1_sb_tot > p2_sb_tot: overall, p1_ov, p2_ov = 'p1', 1, 0
                elif p2_sb_tot > p1_sb_tot: overall, p1_ov, p2_ov = 'p2', 0, 1
                else:                        overall, p1_ov, p2_ov = 'tie', 0.5, 0.5
                overall_desc = f"{_first(sc1)} {p1_sb_tot} SB pts vs {_first(sc2)} {p2_sb_tot} SB pts"
            else:
                # Overall point uses absolute net (each player's own full
                # playing handicap vs par), NOT the differential — a
                # stroke-play-style comparison, unlike the hole-by-hole result.
                if   p1_net_tot < p2_net_tot: overall, p1_ov, p2_ov = 'p1', 1, 0
                elif p2_net_tot < p1_net_tot: overall, p1_ov, p2_ov = 'p2', 0, 1
                else:                          overall, p1_ov, p2_ov = 'tie', 0.5, 0.5
                overall_desc = f"{_first(sc1)} net {p1_net_tot} vs {_first(sc2)} net {p2_net_tot}"

            return {
                'p1_name':   _name(sc1),  'p2_name':   _name(sc2),
                'p1_first':  _first(sc1), 'p2_first':  _first(sc2),
                'p1_hcp': round(sc1['hcp']) if sc1 and sc1['hcp'] is not None else '—',
                'p2_hcp': round(sc2['hcp']) if sc2 and sc2['hcp'] is not None else '—',
                'p1_absent': bool(sc1['is_absent']) if sc1 else False,
                'p2_absent': bool(sc2['is_absent']) if sc2 else False,
                # Cross-check: scorecards.is_absent vs. player_absences (see
                # note above sc_rows). None when the two agree.
                'p1_absence_mismatch_msg': _absence_mismatch_msg(sc1),
                'p2_absence_mismatch_msg': _absence_mismatch_msg(sc2),
                'holes': hole_rows,
                'p1_gross_tot': p1_gross_tot, 'p2_gross_tot': p2_gross_tot,
                'p1_net_tot':   p1_net_tot,   'p2_net_tot':   p2_net_tot,
                'p1_dnet_tot':  p1_dnet_tot,  'p2_dnet_tot':  p2_dnet_tot,
                'p1_sb_tot':    p1_sb_tot,    'p2_sb_tot':    p2_sb_tot,
                'overall': overall, 'overall_desc': overall_desc,
                'p1_ov': p1_ov, 'p2_ov': p2_ov,
                # Stored values from match_results for cross-check
                'p1_stored_hole_pts': float(sc1['hole_points_won'] or 0) if sc1 else None,
                'p2_stored_hole_pts': float(sc2['hole_points_won'] or 0) if sc2 else None,
                'p1_stored_overall':  float(sc1['overall_point_won'] or 0) if sc1 else None,
                'p2_stored_overall':  float(sc2['overall_point_won'] or 0) if sc2 else None,
                'p1_stored_total':    float(sc1['total_points'] or 0) if sc1 else None,
                'p2_stored_total':    float(sc2['total_points'] or 0) if sc2 else None,
            }

        def team_display(team_id):
            t = db.execute(
                """SELECT t.team_name, p1.last_name AS p1_last, p2.last_name AS p2_last
                   FROM teams t
                   LEFT JOIN players p1 ON t.player1_id = p1.player_id
                   LEFT JOIN players p2 ON t.player2_id = p2.player_id
                   WHERE t.team_id = %s""", (team_id,)
            ).fetchone()
            if not t: return f"Team {team_id}"
            if t['team_name']: return t['team_name']
            return ' & '.join(n for n in [t['p1_last'], t['p2_last']] if n) or f"Team {team_id}"

        sc_t1_a = by_role.get((t1_id, 'A'))
        sc_t1_b = by_role.get((t1_id, 'B'))
        sc_t2_a = by_role.get((t2_id, 'A'))
        sc_t2_b = by_role.get((t2_id, 'B'))

        pairs = []
        for label, p1, p2 in [('A', sc_t1_a, sc_t2_a), ('B', sc_t1_b, sc_t2_b)]:
            pd = build_pair(p1, p2)
            if pd:
                pairs.append((label, pd))

        blocks.append({
            'matchup_id': matchup_id, 'round_id': round_id,
            't1_name': team_display(t1_id), 't2_name': team_display(t2_id),
            'pairs': pairs,
            'scoring_mode': scoring_mode,
            'has_overall_point': has_overall_point,
        })

    completed_weeks = db.execute(
        """SELECT DISTINCT week_number, MIN(scheduled_date) AS week_date
           FROM matchups
           WHERE season_id = %s AND status = 'completed' AND is_bye = 0
           GROUP BY week_number ORDER BY week_number ASC""",
        (season_id,)
    ).fetchall()

    week_date = db.execute(
        "SELECT scheduled_date FROM matchups WHERE season_id=%s AND week_number=%s AND is_bye=0 LIMIT 1",
        (season_id, week_num)
    ).fetchone()

    return render_template(
        'debug/scoring.html',
        season=season, season_id=season_id,
        week_num=week_num,
        week_date=week_date['scheduled_date'] if week_date else None,
        blocks=blocks,
        completed_weeks=completed_weeks,
        scoring_mode=scoring_mode,
    )
