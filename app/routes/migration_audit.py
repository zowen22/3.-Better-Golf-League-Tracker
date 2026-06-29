"""
Migration audit page — shows week-by-week cumulative team points and
per-player handicaps used each round. Admin-only. Designed to help
migrate a paper-tracked league and verify score calculation.
"""
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from database import get_db
from routes.auth import login_required

bp = Blueprint('migration_audit', __name__, url_prefix='/admin/migration-audit')


@bp.route('/')
@login_required
def index():
    if session.get('role') != 'league_admin':
        flash('Admin only.', 'error')
        return redirect(url_for('main.dashboard'))

    db = get_db()
    league_id = session['league_id']

    # Season selector
    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()

    season_id = request.args.get('season_id', type=int)
    if not season_id and all_seasons:
        season_id = all_seasons[0]['season_id']

    if not season_id:
        return render_template('debug/migration_audit.html',
            all_seasons=all_seasons, season_id=None,
            weeks=[], teams=[], pts_grid={}, pts_by_week={},
            players=[], hcp_grid={}, scoring_note=None)

    # ── All completed weeks in this season ───────────────────────────────────
    week_rows = db.execute(
        """SELECT DISTINCT m.week_number
           FROM matchups m
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()
    weeks = [r['week_number'] for r in week_rows]

    # ── Teams ─────────────────────────────────────────────────────────────────
    team_rows = db.execute(
        """SELECT t.team_id,
                  COALESCE(NULLIF(t.team_name,''),
                      p1.first_name || ' & ' || p2.first_name) AS team_display
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY t.team_id""",
        (season_id, league_id)
    ).fetchall()
    teams = [dict(r) for r in team_rows]

    # ── Weekly points per team (from match_results) ───────────────────────────
    pts_rows = db.execute(
        """SELECT m.week_number, mr.team_id,
                  COALESCE(SUM(mr.total_points), 0) AS week_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.is_bye = 0
           GROUP BY m.week_number, mr.team_id
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    # Build week_pts[team_id][week] = pts
    week_pts = {}
    for r in pts_rows:
        week_pts.setdefault(r['team_id'], {})[r['week_number']] = float(r['week_pts'])

    # Build cumulative and per-week grids
    pts_grid = {}      # pts_grid[team_id][week] = cumulative
    pts_by_week = {}   # pts_by_week[team_id][week] = this-week only
    for t in teams:
        tid = t['team_id']
        cumul = 0.0
        pts_grid[tid] = {}
        pts_by_week[tid] = {}
        for w in weeks:
            wk = week_pts.get(tid, {}).get(w, None)
            pts_by_week[tid][w] = wk
            if wk is not None:
                cumul += wk
                pts_grid[tid][w] = round(cumul, 1)
            else:
                pts_grid[tid][w] = None   # bye or not played

    # Rank teams at each week by cumulative pts (for display)
    rank_at_week = {}  # rank_at_week[week][team_id] = rank
    for w in weeks:
        scored = [(t['team_id'], pts_grid[t['team_id']].get(w)) for t in teams]
        scored_only = [(tid, pts) for tid, pts in scored if pts is not None]
        scored_only.sort(key=lambda x: -x[1])
        rank_at_week[w] = {tid: i + 1 for i, (tid, _) in enumerate(scored_only)}

    # Final week cumulative for overall rank sort
    last_week = weeks[-1] if weeks else None
    if last_week:
        teams.sort(key=lambda t: -(pts_grid[t['team_id']].get(last_week) or 0))

    # ── Per-player handicaps by week ──────────────────────────────────────────
    hcp_rows = db.execute(
        """SELECT m.week_number,
                  p.player_id,
                  p.first_name || ' ' || p.last_name AS player_name,
                  sc.handicap_at_time_of_play AS playing_hcp,
                  COALESCE(NULLIF(t.team_name,''),
                      tp1.first_name || ' & ' || tp2.first_name) AS team_display
           FROM scorecards sc
           JOIN rounds r   ON sc.round_id    = r.round_id
           JOIN matchups m ON r.matchup_id   = m.matchup_id
           JOIN players p  ON sc.player_id   = p.player_id
           JOIN teams t    ON sc.team_id     = t.team_id
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           WHERE m.season_id = %s AND m.is_bye = 0
           ORDER BY p.last_name, p.first_name, m.week_number""",
        (season_id,)
    ).fetchall()

    # Unique players (ordered by last appearance)
    seen_players = {}
    for r in hcp_rows:
        seen_players[r['player_id']] = {
            'player_id': r['player_id'],
            'player_name': r['player_name'],
            'team_display': r['team_display'],
        }
    players = list(seen_players.values())

    # hcp_grid[player_id][week] = playing_hcp
    hcp_grid = {}
    for r in hcp_rows:
        hcp_grid.setdefault(r['player_id'], {})[r['week_number']] = \
            round(r['playing_hcp']) if r['playing_hcp'] is not None else None

    # ── Scoring mode note ─────────────────────────────────────────────────────
    ls = db.execute(
        "SELECT scoring_mode FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    scoring_note = ls['scoring_mode'] if ls else 'match_play'

    return render_template('debug/migration_audit.html',
        all_seasons=all_seasons,
        season_id=season_id,
        weeks=weeks,
        teams=teams,
        pts_grid=pts_grid,
        pts_by_week=pts_by_week,
        rank_at_week=rank_at_week,
        players=players,
        hcp_grid=hcp_grid,
        scoring_note=scoring_note,
    )
