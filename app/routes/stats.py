from flask import Blueprint, render_template, redirect, url_for, session, request
from database import get_db
from routes.auth import login_required

bp = Blueprint('stats', __name__, url_prefix='/stats')


# ---------------------------------------------------------------------------
# Season Comparison Stats
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def compare():
    db = get_db()
    league_id = session['league_id']

    seasons = db.execute(
        "SELECT season_id, season_name, start_date, end_date FROM seasons WHERE league_id = %s ORDER BY season_id ASC",
        (league_id,)
    ).fetchall()

    if not seasons:
        return render_template('stats/compare.html', seasons=[], season_rows=[])

    season_rows = []

    for s in seasons:
        sid = s['season_id']
        row = {
            'season_id':   sid,
            'season_name': s['season_name'],
            'start_date':  s['start_date'],
            'end_date':    s['end_date'],
        }

        t = db.execute(
            "SELECT COUNT(*) AS cnt FROM teams WHERE season_id = %s AND league_id = %s",
            (sid, league_id)
        ).fetchone()
        row['num_teams'] = t['cnt'] if t else 0

        played = db.execute(
            """SELECT COUNT(DISTINCT r.round_id) AS cnt
               FROM rounds r
               JOIN matchups m ON r.matchup_id = m.matchup_id
               WHERE m.season_id = %s AND m.is_bye = 0""",
            (sid,)
        ).fetchone()
        scheduled = db.execute(
            "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id = %s AND is_bye = 0",
            (sid,)
        ).fetchone()
        row['rounds_played']    = played['cnt'] if played else 0
        row['rounds_scheduled'] = scheduled['cnt'] if scheduled else 0

        if row['rounds_played'] == 0:
            row['avg_gross']        = None
            row['low_gross']        = None
            row['pts_leader_name']  = None
            row['pts_leader_pts']   = None
            row['wins_leader_name'] = None
            row['wins_leader_wins'] = None
            row['standings_leader'] = None
            row['standings_pts']    = None
            row['total_pts_scored'] = None
            row['all_win_counts']   = []
            season_rows.append(row)
            continue

        ag = db.execute(
            """SELECT AVG(scorecard_gross) AS avg_gross, MIN(scorecard_gross) AS low_gross
               FROM (
                   SELECT sc.scorecard_id, SUM(hs.gross_score) AS scorecard_gross
                   FROM hole_scores hs
                   JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
                   JOIN rounds r      ON sc.round_id = r.round_id
                   JOIN matchups m    ON r.matchup_id = m.matchup_id
                   WHERE m.season_id = %s AND m.is_bye = 0
                   GROUP BY sc.scorecard_id
               )""",
            (sid,)
        ).fetchone()
        row['avg_gross'] = round(ag['avg_gross'], 1) if ag and ag['avg_gross'] is not None else None
        row['low_gross'] = ag['low_gross'] if ag else None

        lg = db.execute(
            """SELECT p.first_name || ' ' || p.last_name AS player_name,
                      SUM(hs.gross_score) AS scorecard_gross
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id = r.round_id
               JOIN matchups m    ON r.matchup_id = m.matchup_id
               JOIN players p     ON sc.player_id = p.player_id
               WHERE m.season_id = %s AND m.is_bye = 0
               GROUP BY sc.scorecard_id, p.first_name, p.last_name
               ORDER BY scorecard_gross ASC
               LIMIT 1""",
            (sid,)
        ).fetchone()
        row['low_gross_player'] = lg['player_name'] if lg else None

        pl = db.execute(
            """SELECT p.first_name || ' ' || p.last_name AS player_name,
                      SUM(mr.total_points) AS season_pts
               FROM match_results mr
               JOIN matchups m  ON mr.matchup_id = m.matchup_id
               JOIN players p   ON mr.player_id  = p.player_id
               WHERE m.season_id = %s AND m.is_bye = 0
               GROUP BY mr.player_id, p.first_name, p.last_name
               ORDER BY season_pts DESC
               LIMIT 1""",
            (sid,)
        ).fetchone()
        row['pts_leader_name'] = pl['player_name'] if pl else None
        row['pts_leader_pts']  = pl['season_pts']  if pl else None

        sl = db.execute(
            """SELECT t.team_name, SUM(mr.total_points) AS team_pts
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               JOIN teams t    ON mr.team_id    = t.team_id
               WHERE m.season_id = %s AND m.is_bye = 0
               GROUP BY mr.team_id, t.team_name
               ORDER BY team_pts DESC
               LIMIT 1""",
            (sid,)
        ).fetchone()
        row['standings_leader'] = sl['team_name'] if sl else None
        row['standings_pts']    = sl['team_pts']  if sl else None

        matchup_results = db.execute(
            """SELECT mr.matchup_id, mr.team_id, t.team_name,
                      SUM(mr.total_points) AS team_pts
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               JOIN teams t    ON mr.team_id    = t.team_id
               WHERE m.season_id = %s AND m.is_bye = 0
               GROUP BY mr.matchup_id, mr.team_id, t.team_name
               ORDER BY mr.matchup_id""",
            (sid,)
        ).fetchall()

        matchup_dict = {}
        for r in matchup_results:
            mid = r['matchup_id']
            if mid not in matchup_dict:
                matchup_dict[mid] = []
            matchup_dict[mid].append({'team_id': r['team_id'], 'team_name': r['team_name'], 'pts': r['team_pts']})

        win_counts = {}
        for mid, teams in matchup_dict.items():
            if len(teams) < 2:
                continue
            a, b = teams[0], teams[1]
            for tid, tname in [(a['team_id'], a['team_name']), (b['team_id'], b['team_name'])]:
                win_counts.setdefault(tid, {'name': tname, 'wins': 0, 'losses': 0, 'ties': 0})
            if a['pts'] > b['pts']:
                win_counts[a['team_id']]['wins']   += 1
                win_counts[b['team_id']]['losses'] += 1
            elif b['pts'] > a['pts']:
                win_counts[b['team_id']]['wins']   += 1
                win_counts[a['team_id']]['losses'] += 1
            else:
                win_counts[a['team_id']]['ties'] += 1
                win_counts[b['team_id']]['ties'] += 1

        if win_counts:
            best_team_id = max(win_counts, key=lambda tid: (win_counts[tid]['wins'], -win_counts[tid]['losses']))
            row['wins_leader_name']   = win_counts[best_team_id]['name']
            row['wins_leader_wins']   = win_counts[best_team_id]['wins']
            row['wins_leader_losses'] = win_counts[best_team_id]['losses']
            row['wins_leader_ties']   = win_counts[best_team_id]['ties']
            row['all_win_counts']     = sorted(win_counts.values(), key=lambda x: (-x['wins'], x['losses']))
        else:
            row['wins_leader_name']   = None
            row['wins_leader_wins']   = None
            row['wins_leader_losses'] = None
            row['wins_leader_ties']   = None
            row['all_win_counts']     = []

        tp = db.execute(
            """SELECT SUM(mr.total_points) AS total
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               WHERE m.season_id = %s AND m.is_bye = 0""",
            (sid,)
        ).fetchone()
        row['total_pts_scored'] = tp['total'] if tp else 0

        season_rows.append(row)

    return render_template('stats/compare.html', seasons=seasons, season_rows=season_rows)


# ---------------------------------------------------------------------------
# Per-hole scoring averages — #23
# ---------------------------------------------------------------------------

@bp.route('/hole-averages')
@login_required
def hole_averages():
    db = get_db()
    league_id = session['league_id']

    # Season list
    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()
    if not all_seasons:
        return render_template('stats/hole_averages.html',
                               all_seasons=[], season=None, players=[],
                               player=None, player_holes=[], course_holes=[],
                               has_par=False)

    # Selected season
    season_id = request.args.get('season_id', type=int)
    if not season_id:
        # Default to current session season or most recent
        season_id = session.get('current_season_id') or all_seasons[0]['season_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        season_id = all_seasons[0]['season_id']
        season = db.execute("SELECT * FROM seasons WHERE season_id = %s", (season_id,)).fetchone()

    # Players who played in this season
    players = db.execute(
        """SELECT DISTINCT p.player_id, p.first_name || ' ' || p.last_name AS player_name,
                  p.last_name, p.first_name
           FROM scorecards sc
           JOIN rounds r   ON sc.round_id = r.round_id
           JOIN matchups m ON r.matchup_id = m.matchup_id
           JOIN players p  ON sc.player_id = p.player_id
           WHERE m.season_id = %s AND m.is_bye = 0
           ORDER BY p.last_name, p.first_name""",
        (season_id,)
    ).fetchall()

    # Selected player
    player_id = request.args.get('player_id', type=int)
    player = None
    player_holes = []

    if player_id:
        player = db.execute(
            "SELECT player_id, first_name || ' ' || last_name AS player_name FROM players WHERE player_id = %s",
            (player_id,)
        ).fetchone()

    if player:
        # Per-hole stats for this player in the selected season
        # Includes holes with par data (via hole_id join) and those without
        player_holes_raw = db.execute(
            """SELECT
                   hs.hole_number,
                   h.par,
                   COUNT(*)                                                                          AS rounds,
                   ROUND(AVG(hs.gross_score), 2)                                                    AS avg_score,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score <= h.par - 2 THEN 1 ELSE 0 END) AS eagles,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par - 1 THEN 1 ELSE 0 END) AS birdies,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par     THEN 1 ELSE 0 END) AS pars,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par + 1 THEN 1 ELSE 0 END) AS bogeys,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score >= h.par + 2 THEN 1 ELSE 0 END) AS doubles_plus,
                   AVG(CASE WHEN h.par IS NOT NULL THEN hs.gross_score - h.par ELSE NULL END)       AS avg_vs_par
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id = r.round_id
               JOIN matchups m    ON r.matchup_id = m.matchup_id
               LEFT JOIN holes h  ON hs.hole_id = h.hole_id
               WHERE m.season_id = %s AND m.is_bye = 0 AND sc.player_id = %s
               GROUP BY hs.hole_number, h.par
               ORDER BY hs.hole_number""",
            (season_id, player_id)
        ).fetchall()

        for row in player_holes_raw:
            r = dict(row)
            rounds = r['rounds'] or 0
            r['eagle_pct']  = round(100 * r['eagles']  / rounds, 1) if rounds else 0
            r['birdie_pct'] = round(100 * r['birdies'] / rounds, 1) if rounds else 0
            r['par_pct']    = round(100 * r['pars']    / rounds, 1) if rounds else 0
            r['bogey_pct']  = round(100 * r['bogeys']  / rounds, 1) if rounds else 0
            r['double_pct'] = round(100 * r['doubles_plus'] / rounds, 1) if rounds else 0
            r['avg_vs_par_fmt'] = (
                ('+' if r['avg_vs_par'] > 0 else '') + f"{r['avg_vs_par']:.2f}"
                if r['avg_vs_par'] is not None else '—'
            )
            player_holes.append(r)

    # ── Course difficulty: all players, per hole (season-wide) ──────────────
    course_holes_raw = db.execute(
        """SELECT
               hs.hole_number,
               h.par,
               COUNT(*)                                                                          AS rounds,
               ROUND(AVG(hs.gross_score), 2)                                                    AS avg_score,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score <= h.par - 2 THEN 1 ELSE 0 END) AS eagles,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par - 1 THEN 1 ELSE 0 END) AS birdies,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par     THEN 1 ELSE 0 END) AS pars,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par + 1 THEN 1 ELSE 0 END) AS bogeys,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score >= h.par + 2 THEN 1 ELSE 0 END) AS doubles_plus,
               AVG(CASE WHEN h.par IS NOT NULL THEN hs.gross_score - h.par ELSE NULL END)       AS avg_vs_par
           FROM hole_scores hs
           JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
           JOIN rounds r      ON sc.round_id = r.round_id
           JOIN matchups m    ON r.matchup_id = m.matchup_id
           LEFT JOIN holes h  ON hs.hole_id = h.hole_id
           WHERE m.season_id = %s AND m.is_bye = 0
           GROUP BY hs.hole_number, h.par
           ORDER BY hs.hole_number""",
        (season_id,)
    ).fetchall()

    course_holes = []
    has_par = False
    for row in course_holes_raw:
        r = dict(row)
        if r['par'] is not None:
            has_par = True
        rounds = r['rounds'] or 0
        r['birdie_pct'] = round(100 * r['birdies'] / rounds, 1) if rounds else 0
        r['par_pct']    = round(100 * r['pars']    / rounds, 1) if rounds else 0
        r['bogey_pct']  = round(100 * r['bogeys']  / rounds, 1) if rounds else 0
        r['avg_vs_par_fmt'] = (
            ('+' if r['avg_vs_par'] > 0 else '') + f"{r['avg_vs_par']:.2f}"
            if r['avg_vs_par'] is not None else '—'
        )
        course_holes.append(r)

    # Difficulty rank: sort by avg_vs_par desc (hardest first) for holes that have par
    holes_with_par = [h for h in course_holes if h['avg_vs_par'] is not None]
    ranked = sorted(holes_with_par, key=lambda h: -(h['avg_vs_par'] or 0))
    for rank, h in enumerate(ranked, 1):
        h['difficulty_rank'] = rank

    return render_template('stats/hole_averages.html',
                           all_seasons=all_seasons,
                           season=season,
                           players=players,
                           player=player,
                           player_holes=player_holes,
                           course_holes=course_holes,
                           has_par=has_par)


# ---------------------------------------------------------------------------
# Course Statistics — #30
# ---------------------------------------------------------------------------

@bp.route('/course/<int:course_id>')
@login_required
def course_stats(course_id):
    db = get_db()
    league_id = session['league_id']

    # Verify course belongs to this league (or is a shared master record)
    course = db.execute(
        """SELECT c.*, 
                  (SELECT COUNT(*) FROM tees WHERE course_id = c.course_id) AS tee_count
           FROM courses c
           WHERE c.course_id = %s AND (c.league_id = %s OR c.is_master_record = 1)""",
        (course_id, league_id)
    ).fetchone()
    if not course:
        from flask import abort
        abort(404)

    # All seasons for this league
    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()

    # Optional season filter
    season_id = request.args.get('season_id', type=int)

    # Build the matchup filter clause
    # Rounds at this course = matchups where rounds exist with scorecards that have hole_scores
    # tied to holes in this course's tees
    if season_id:
        season_filter = "AND m.season_id = %s"
        params_base = (course_id, season_id, league_id)
        params_league = (course_id, league_id, season_id, league_id)
    else:
        season_filter = ""
        params_base = (course_id, league_id)
        params_league = (course_id, league_id, league_id)

    # ── Per-hole stats ────────────────────────────────────────────────────
    if season_id:
        hole_rows = db.execute(
            """SELECT
                   hs.hole_number,
                   h.par,
                   h.handicap_index                                                                      AS hcp_index,
                   COUNT(*)                                                                              AS rounds,
                   ROUND(AVG(hs.gross_score), 2)                                                        AS avg_score,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score <= h.par - 2 THEN 1 ELSE 0 END)   AS eagles,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par - 1 THEN 1 ELSE 0 END)   AS birdies,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par     THEN 1 ELSE 0 END)   AS pars,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par + 1 THEN 1 ELSE 0 END)   AS bogeys,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score >= h.par + 2 THEN 1 ELSE 0 END)   AS doubles_plus,
                   AVG(CASE WHEN h.par IS NOT NULL THEN CAST(hs.gross_score - h.par AS REAL) ELSE NULL END) AS avg_vs_par
               FROM hole_scores hs
               JOIN holes h         ON hs.hole_id   = h.hole_id
               JOIN tees t          ON h.tee_id     = t.tee_id
               JOIN scorecards sc   ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r        ON sc.round_id  = r.round_id
               JOIN matchups m      ON r.matchup_id = m.matchup_id
               WHERE t.course_id = %s AND m.season_id = %s AND m.is_bye = 0
               GROUP BY hs.hole_number, h.par, h.handicap_index
               ORDER BY hs.hole_number""",
            (course_id, season_id)
        ).fetchall()
    else:
        hole_rows = db.execute(
            """SELECT
                   hs.hole_number,
                   h.par,
                   h.handicap_index                                                                      AS hcp_index,
                   COUNT(*)                                                                              AS rounds,
                   ROUND(AVG(hs.gross_score), 2)                                                        AS avg_score,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score <= h.par - 2 THEN 1 ELSE 0 END)   AS eagles,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par - 1 THEN 1 ELSE 0 END)   AS birdies,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par     THEN 1 ELSE 0 END)   AS pars,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score  = h.par + 1 THEN 1 ELSE 0 END)   AS bogeys,
                   SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score >= h.par + 2 THEN 1 ELSE 0 END)   AS doubles_plus,
                   AVG(CASE WHEN h.par IS NOT NULL THEN CAST(hs.gross_score - h.par AS REAL) ELSE NULL END) AS avg_vs_par
               FROM hole_scores hs
               JOIN holes h         ON hs.hole_id   = h.hole_id
               JOIN tees t          ON h.tee_id     = t.tee_id
               JOIN scorecards sc   ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r        ON sc.round_id  = r.round_id
               JOIN matchups m      ON r.matchup_id = m.matchup_id
               JOIN seasons _ls     ON m.season_id  = _ls.season_id AND _ls.league_id = %s
               WHERE t.course_id = %s AND m.is_bye = 0
               GROUP BY hs.hole_number, h.par, h.handicap_index
               ORDER BY hs.hole_number""",
            (league_id, course_id)
        ).fetchall()

    has_par = False
    hole_stats = []
    for row in hole_rows:
        r = dict(row)
        n = r['rounds'] or 0
        if r['par'] is not None:
            has_par = True
        r['birdie_pct'] = round(100 * r['birdies'] / n, 1) if n else 0
        r['eagle_pct']  = round(100 * r['eagles']  / n, 1) if n else 0
        r['par_pct']    = round(100 * r['pars']    / n, 1) if n else 0
        r['bogey_pct']  = round(100 * r['bogeys']  / n, 1) if n else 0
        r['double_pct'] = round(100 * r['doubles_plus'] / n, 1) if n else 0
        r['avg_vs_par_fmt'] = (
            ('+' if r['avg_vs_par'] > 0 else '') + f"{r['avg_vs_par']:.2f}"
            if r['avg_vs_par'] is not None else '—'
        )
        hole_stats.append(r)

    # Difficulty rank (hardest = highest avg_vs_par)
    holes_with_par = [h for h in hole_stats if h['avg_vs_par'] is not None]
    for rank, h in enumerate(sorted(holes_with_par, key=lambda x: -(x['avg_vs_par'] or 0)), 1):
        h['difficulty_rank'] = rank

    # ── Best rounds (lowest gross total) ─────────────────────────────────
    if season_id:
        best_rounds = db.execute(
            """SELECT
                   p.first_name || ' ' || p.last_name AS player_name,
                   p.player_id,
                   SUM(hs.gross_score)  AS gross_total,
                   COUNT(hs.hole_score_id) AS holes_played,
                   r.round_id,
                   m.week_number,
                   se.season_name,
                   m.match_date
               FROM hole_scores hs
               JOIN holes h       ON hs.hole_id      = h.hole_id
               JOIN tees t        ON h.tee_id        = t.tee_id
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id     = r.round_id
               JOIN matchups m    ON r.matchup_id    = m.matchup_id
               JOIN seasons se    ON m.season_id     = se.season_id
               JOIN players p     ON sc.player_id    = p.player_id
               WHERE t.course_id = %s AND m.season_id = %s AND m.is_bye = 0
               GROUP BY sc.scorecard_id, p.first_name, p.last_name, p.player_id, r.round_id, m.week_number, se.season_name, m.match_date
               HAVING COUNT(hs.hole_score_id) >= 9
               ORDER BY gross_total ASC
               LIMIT 10""",
            (course_id, season_id)
        ).fetchall()
    else:
        best_rounds = db.execute(
            """SELECT
                   p.first_name || ' ' || p.last_name AS player_name,
                   p.player_id,
                   SUM(hs.gross_score)  AS gross_total,
                   COUNT(hs.hole_score_id) AS holes_played,
                   r.round_id,
                   m.week_number,
                   se.season_name,
                   m.match_date
               FROM hole_scores hs
               JOIN holes h       ON hs.hole_id      = h.hole_id
               JOIN tees t        ON h.tee_id        = t.tee_id
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id     = r.round_id
               JOIN matchups m    ON r.matchup_id    = m.matchup_id
               JOIN seasons se    ON m.season_id     = se.season_id AND se.league_id = %s
               JOIN players p     ON sc.player_id    = p.player_id
               WHERE t.course_id = %s AND m.is_bye = 0
               GROUP BY sc.scorecard_id, p.first_name, p.last_name, p.player_id, r.round_id, m.week_number, se.season_name, m.match_date
               HAVING COUNT(hs.hole_score_id) >= 9
               ORDER BY gross_total ASC
               LIMIT 10""",
            (league_id, course_id)
        ).fetchall()

    # ── Player stats: rounds + avg gross ─────────────────────────────────
    if season_id:
        player_stats = db.execute(
            """SELECT
                   p.first_name || ' ' || p.last_name AS player_name,
                   p.player_id,
                   COUNT(DISTINCT sc.scorecard_id)          AS rounds_played,
                   ROUND(AVG(scorecard_totals.gross), 2)    AS avg_gross,
                   MIN(scorecard_totals.gross)              AS low_gross
               FROM scorecards sc
               JOIN players p ON sc.player_id = p.player_id
               JOIN rounds r  ON sc.round_id  = r.round_id
               JOIN matchups m ON r.matchup_id = m.matchup_id
               JOIN (
                   SELECT hs2.scorecard_id, SUM(hs2.gross_score) AS gross
                   FROM hole_scores hs2
                   JOIN holes h2 ON hs2.hole_id = h2.hole_id
                   JOIN tees t2  ON h2.tee_id   = t2.tee_id
                   WHERE t2.course_id = %s
                   GROUP BY hs2.scorecard_id
               ) AS scorecard_totals ON scorecard_totals.scorecard_id = sc.scorecard_id
               WHERE m.season_id = %s AND m.is_bye = 0
               GROUP BY sc.player_id, p.first_name, p.last_name, p.player_id
               ORDER BY rounds_played DESC, avg_gross ASC
               LIMIT 20""",
            (course_id, season_id)
        ).fetchall()
    else:
        player_stats = db.execute(
            """SELECT
                   p.first_name || ' ' || p.last_name AS player_name,
                   p.player_id,
                   COUNT(DISTINCT sc.scorecard_id)          AS rounds_played,
                   ROUND(AVG(scorecard_totals.gross), 2)    AS avg_gross,
                   MIN(scorecard_totals.gross)              AS low_gross
               FROM scorecards sc
               JOIN players p ON sc.player_id = p.player_id
               JOIN rounds r  ON sc.round_id  = r.round_id
               JOIN matchups m ON r.matchup_id = m.matchup_id
               JOIN (
                   SELECT hs2.scorecard_id, SUM(hs2.gross_score) AS gross
                   FROM hole_scores hs2
                   JOIN holes h2 ON hs2.hole_id = h2.hole_id
                   JOIN tees t2  ON h2.tee_id   = t2.tee_id
                   WHERE t2.course_id = %s
                   GROUP BY hs2.scorecard_id
               ) AS scorecard_totals ON scorecard_totals.scorecard_id = sc.scorecard_id
               JOIN seasons _ls2 ON m.season_id = _ls2.season_id AND _ls2.league_id = %s
               WHERE m.is_bye = 0
               GROUP BY sc.player_id, p.first_name, p.last_name, p.player_id
               ORDER BY rounds_played DESC, avg_gross ASC
               LIMIT 20""",
            (course_id, league_id)
        ).fetchall()

    # ── Summary stats ─────────────────────────────────────────────────────
    total_rounds_played = sum(p['rounds_played'] for p in player_stats)
    total_eagle = sum(h['eagles'] for h in hole_stats)
    total_birdie = sum(h['birdies'] for h in hole_stats)

    selected_season = None
    if season_id:
        selected_season = db.execute(
            "SELECT season_id, season_name FROM seasons WHERE season_id = %s AND league_id = %s",
            (season_id, league_id)
        ).fetchone()

    return render_template('stats/course_stats.html',
                           course=course,
                           all_seasons=all_seasons,
                           selected_season=selected_season,
                           hole_stats=hole_stats,
                           has_par=has_par,
                           best_rounds=best_rounds,
                           player_stats=player_stats,
                           total_rounds_played=total_rounds_played,
                           total_eagle=total_eagle,
                           total_birdie=total_birdie)
