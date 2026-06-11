from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required

bp = Blueprint('reports', __name__, url_prefix='/reports')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_season(db, season_id, league_id):
    return db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()


def _all_seasons(db, league_id):
    return db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()


def _get_standings(db, season_id, league_id):
    """Return list of (team_label, total_pts) ordered by pts desc."""
    rows = db.execute(
        """SELECT t.team_id,
                  p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.first_name AS p2_first, p2.last_name AS p2_last,
                  t.team_name AS nickname,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts
           FROM teams t
           LEFT JOIN players p1       ON t.player1_id  = p1.player_id
           LEFT JOIN players p2       ON t.player2_id  = p2.player_id
           LEFT JOIN match_results mr ON mr.team_id    = t.team_id
           LEFT JOIN matchups m       ON mr.matchup_id = m.matchup_id
                                     AND m.season_id   = %s
           WHERE t.season_id = %s AND t.league_id = %s
           GROUP BY t.team_id, p1.first_name, p1.last_name, p2.first_name, p2.last_name, t.team_name
           ORDER BY total_pts DESC""",
        (season_id, season_id, league_id)
    ).fetchall()
    return rows


def _get_player_handicap(db, player_id):
    row = db.execute(
        "SELECT handicap_index FROM handicap_history WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1",
        (player_id,)
    ).fetchone()
    if row:
        return row['handicap_index']
    row = db.execute("SELECT starting_handicap FROM players WHERE player_id = %s", (player_id,)).fetchone()
    return (row['starting_handicap'] or 0) if row else 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def current():
    """Redirect to the latest season's reports index."""
    db = get_db()
    seasons = _all_seasons(db, session['league_id'])
    if not seasons:
        flash('No seasons found.', 'error')
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('reports.index', season_id=seasons[0]['season_id']))


@bp.route('/<int:season_id>')
@login_required
def index(season_id):
    """Reports landing page: list of available report types for this season."""
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    all_seasons = _all_seasons(db, league_id)

    # Completed matchups with their round info
    matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                  t1.team_id AS t1_id, t2.team_id AS t2_id,
                  p1a.last_name AS t1_p1_last, p1b.last_name AS t1_p2_last,
                  p2a.last_name AS t2_p1_last, p2b.last_name AS t2_p2_last,
                  r.round_id, r.round_date,
                  c.course_name
           FROM matchups m
           JOIN teams t1 ON m.team1_id = t1.team_id
           JOIN teams t2 ON m.team2_id = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           LEFT JOIN rounds r ON r.matchup_id = m.matchup_id
           LEFT JOIN courses c ON r.course_id = c.course_id
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    completed_count = len(matchups)

    return render_template('reports/index.html',
                           season=season,
                           all_seasons=all_seasons,
                           matchups=matchups,
                           completed_count=completed_count)


@bp.route('/<int:season_id>/scorecard/<int:matchup_id>')
@login_required
def scorecard(season_id, matchup_id):
    """Printable single-matchup scorecard."""
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    matchup = db.execute(
        """SELECT m.*, s.season_name, s.league_id, s.season_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = %s AND m.season_id = %s""",
        (matchup_id, season_id)
    ).fetchone()

    if not matchup or matchup['league_id'] != league_id:
        flash('Matchup not found.', 'error')
        return redirect(url_for('reports.index', season_id=season_id))

    if matchup['status'] != 'completed':
        flash('Scores not yet entered for this matchup.', 'error')
        return redirect(url_for('reports.index', season_id=season_id))

    round_row = db.execute(
        "SELECT * FROM rounds WHERE matchup_id = %s", (matchup_id,)
    ).fetchone()

    if not round_row:
        flash('No round data found.', 'error')
        return redirect(url_for('reports.index', season_id=season_id))

    scorecards = db.execute(
        """SELECT sc.*, p.first_name, p.last_name, p.player_id,
                  t.team_id, t.team_name AS team_nickname,
                  tp1.last_name AS t_p1_last, tp2.last_name AS t_p2_last
           FROM scorecards sc
           JOIN players p ON sc.player_id = p.player_id
           JOIN teams t ON sc.team_id = t.team_id
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           WHERE sc.round_id = %s
           ORDER BY sc.team_id, sc.player_id""",
        (round_row['round_id'],)
    ).fetchall()

    hole_scores = {}
    for sc in scorecards:
        hs = db.execute(
            "SELECT * FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
            (sc['scorecard_id'],)
        ).fetchall()
        hole_scores[sc['player_id']] = hs

    results = db.execute(
        """SELECT mr.*, p.first_name, p.last_name
           FROM match_results mr JOIN players p ON mr.player_id = p.player_id
           WHERE mr.matchup_id = %s""",
        (matchup_id,)
    ).fetchall()

    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
        (round_row['tee_id'],)
    ).fetchall()

    tee    = db.execute("SELECT * FROM tees    WHERE tee_id    = %s", (round_row['tee_id'],)).fetchone()
    course = db.execute("SELECT * FROM courses WHERE course_id = %s", (round_row['course_id'],)).fetchone()

    # Build role/pts/opp maps
    opp_map  = {}
    role_map = {}
    pts_map  = {}
    for r in results:
        opp_map[r['player_id']]  = r['opponent_player_id']
        role_map[r['player_id']] = r['role']
        pts_map[r['player_id']]  = r['total_points']

    # Per-hole match pts
    view_hole_pts = {}
    for pid, opp_id in opp_map.items():
        pts = []
        my_hs  = {h['hole_number']: h for h in hole_scores.get(pid, [])}
        opp_hs = {h['hole_number']: h for h in hole_scores.get(opp_id, [])}
        for h in holes:
            n_mine = my_hs.get(h['hole_number'])
            n_opp  = opp_hs.get(h['hole_number'])
            if n_mine is None or n_opp is None:
                pts.append(None)
            elif n_mine['net_score'] < n_opp['net_score']:
                pts.append(2)
            elif n_opp['net_score'] < n_mine['net_score']:
                pts.append(0)
            else:
                pts.append(1)
        view_hole_pts[pid] = pts

    t1_id = matchup['team1_id']
    t2_id = matchup['team2_id']

    def build_team_group(team_id):
        scs = [sc for sc in scorecards if sc['team_id'] == team_id]
        scs.sort(key=lambda x: role_map.get(x['player_id'], 'Z'))
        group = []
        for sc in scs:
            pid = sc['player_id']
            hs  = hole_scores.get(pid, [])
            group.append({
                'pid':         pid,
                'name':        f"{sc['first_name']} {sc['last_name']}",
                'role':        role_map.get(pid, '?'),
                'hcp':         sc['handicap_at_time_of_play'],
                'gross_scores':[h['gross_score'] for h in hs],
                'net_scores':  [h['net_score']   for h in hs],
                'total_gross': sum(h['gross_score'] for h in hs) if hs else 0,
                'total_net':   sum(h['net_score']   for h in hs) if hs else 0,
                'hole_pts':    view_hole_pts.get(pid, []),
                'total_pts':   pts_map.get(pid, 0),
                'team_label':  f"{sc['t_p1_last'] or '?'} / {sc['t_p2_last'] or '?'}",
            })
        return group

    view_groups = [build_team_group(t1_id), build_team_group(t2_id)]

    # Team totals for the header summary
    team_pts = {}
    for grp in view_groups:
        if grp:
            team_pts[grp[0]['team_label']] = sum(p['total_pts'] for p in grp)

    return render_template('reports/scorecard.html',
                           season=season,
                           matchup=matchup,
                           round_row=round_row,
                           holes=holes,
                           view_groups=view_groups,
                           team_pts=team_pts,
                           tee=tee,
                           course=course)


@bp.route('/<int:season_id>/summary')
@login_required
def summary(season_id):
    """Full printable season summary: standings + results + player stats."""
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    all_seasons = _all_seasons(db, league_id)

    # ── Standings ──────────────────────────────────────────────────────────
    standings_rows = _get_standings(db, season_id, league_id)

    # Assign positions (tied teams share rank)
    standings = []
    pos = 0
    prev_pts = None
    for i, row in enumerate(standings_rows):
        if row['total_pts'] != prev_pts:
            pos = i + 1
            prev_pts = row['total_pts']
        t_label = row['nickname'] or f"{row['p1_last'] or '?'} / {row['p2_last'] or '?'}"
        standings.append({
            'pos':       pos,
            'team_id':   row['team_id'],
            'label':     t_label,
            'total_pts': row['total_pts'],
        })

    # ── Completed weeks with per-team pts ─────────────────────────────────
    completed_matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                  m.team1_id, m.team2_id,
                  t1.team_name AS t1_nick,
                  p1a.last_name AS t1_p1_last, p1b.last_name AS t1_p2_last,
                  t2.team_name AS t2_nick,
                  p2a.last_name AS t2_p1_last, p2b.last_name AS t2_p2_last,
                  r.round_date, c.course_name
           FROM matchups m
           JOIN teams t1 ON m.team1_id = t1.team_id
           JOIN teams t2 ON m.team2_id = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           LEFT JOIN rounds r ON r.matchup_id = m.matchup_id
           LEFT JOIN courses c ON r.course_id = c.course_id
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    # Per-matchup team point totals
    results_per_matchup = {}
    all_results = db.execute(
        """SELECT mr.matchup_id, mr.team_id, SUM(mr.total_points) AS team_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s
           GROUP BY mr.matchup_id, mr.team_id""",
        (season_id,)
    ).fetchall()
    for r in all_results:
        mid = r['matchup_id']
        if mid not in results_per_matchup:
            results_per_matchup[mid] = {}
        results_per_matchup[mid][r['team_id']] = r['team_pts']

    week_results = []
    for m in completed_matchups:
        mid = m['matchup_id']
        t1_label = m['t1_nick'] or f"{m['t1_p1_last'] or '?'} / {m['t1_p2_last'] or '?'}"
        t2_label = m['t2_nick'] or f"{m['t2_p1_last'] or '?'} / {m['t2_p2_last'] or '?'}"
        t1_pts   = results_per_matchup.get(mid, {}).get(m['team1_id'], 0)
        t2_pts   = results_per_matchup.get(mid, {}).get(m['team2_id'], 0)
        t1_pts_d = int(t1_pts) if t1_pts == int(t1_pts) else t1_pts
        t2_pts_d = int(t2_pts) if t2_pts == int(t2_pts) else t2_pts
        if t1_pts > t2_pts:
            winner = t1_label
        elif t2_pts > t1_pts:
            winner = t2_label
        else:
            winner = 'Tie'
        week_results.append({
            'week_number': m['week_number'],
            'date':        m['round_date'] or m['scheduled_date'] or '',
            'course_name': m['course_name'] or '',
            'matchup_id':  mid,
            't1_label':    t1_label,
            't2_label':    t2_label,
            't1_pts':      t1_pts_d,
            't2_pts':      t2_pts_d,
            'winner':      winner,
        })

    # ── Player individual stats ────────────────────────────────────────────
    # Rounds played, avg gross, best (lowest) gross total, current handicap
    team_players = db.execute(
        """SELECT t.team_id,
                  t.team_name AS t_nick,
                  p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last,
                  tp1.last_name AS t_p1_last, tp2.last_name AS t_p2_last
           FROM teams t
           LEFT JOIN players p1  ON t.player1_id = p1.player_id
           LEFT JOIN players p2  ON t.player2_id = p2.player_id
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY t.team_id""",
        (season_id, league_id)
    ).fetchall()

    player_stats = []
    seen_pids = set()
    for row in team_players:
        for pid_key, fn_key, ln_key in [('p1_id', 'p1_first', 'p1_last'),
                                         ('p2_id', 'p2_first', 'p2_last')]:
            pid = row[pid_key]
            if not pid or pid in seen_pids:
                continue
            seen_pids.add(pid)

            # Gross scores per round this season (via scorecards + hole_scores + rounds)
            sc_rows = db.execute(
                """SELECT sc.scorecard_id, sc.handicap_at_time_of_play
                   FROM scorecards sc
                   JOIN rounds r ON sc.round_id = r.round_id
                   JOIN matchups m ON r.matchup_id = m.matchup_id
                   WHERE sc.player_id = %s AND m.season_id = %s
                   ORDER BY r.round_date""",
                (pid, season_id)
            ).fetchall()

            rounds_played = len(sc_rows)
            gross_totals  = []
            for sc in sc_rows:
                hs = db.execute(
                    "SELECT SUM(gross_score) AS gtot FROM hole_scores WHERE scorecard_id = %s",
                    (sc['scorecard_id'],)
                ).fetchone()
                if hs and hs['gtot'] is not None:
                    gross_totals.append(hs['gtot'])

            avg_gross  = round(sum(gross_totals) / len(gross_totals), 1) if gross_totals else None
            best_gross = min(gross_totals) if gross_totals else None
            cur_hcp    = _get_player_handicap(db, pid)

            t_label = row['t_nick'] or f"{row['t_p1_last'] or '?'} / {row['t_p2_last'] or '?'}"
            player_stats.append({
                'name':         f"{row[fn_key]} {row[ln_key]}",
                'team_label':   t_label,
                'rounds':       rounds_played,
                'avg_gross':    avg_gross,
                'best_gross':   best_gross,
                'handicap':     cur_hcp,
            })

    # Sort by rounds desc, then avg gross asc
    player_stats.sort(key=lambda x: (-x['rounds'], x['avg_gross'] or 999))

    total_rounds = db.execute(
        "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id = %s AND is_bye = 0",
        (season_id,)
    ).fetchone()['cnt']

    completed_count = len(completed_matchups)

    return render_template('reports/summary.html',
                           season=season,
                           all_seasons=all_seasons,
                           standings=standings,
                           week_results=week_results,
                           player_stats=player_stats,
                           completed_count=completed_count,
                           total_rounds=total_rounds)


# ---------------------------------------------------------------------------
# CSV / Data Export routes
# ---------------------------------------------------------------------------
import csv
import io
from flask import Response

def _csv_response(rows, fieldnames, filename):
    """Build a CSV download response from a list of dicts."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore',
                       lineterminator='\r\n')
    w.writeheader()
    w.writerows(rows)
    output = buf.getvalue()
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@bp.route('/<int:season_id>/export/standings')
@login_required
def export_standings(season_id):
    """CSV download: team standings for a season."""
    db        = get_db()
    league_id = session['league_id']
    season    = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    rows = _get_standings(db, season_id, league_id)

    pos = 0
    prev_pts = None
    out = []
    for i, row in enumerate(rows):
        if row['total_pts'] != prev_pts:
            pos = i + 1
            prev_pts = row['total_pts']
        t_label = row['nickname'] or f"{row['p1_last'] or '?'} / {row['p2_last'] or '?'}"
        # W-T-L from match_results
        wl = db.execute(
            """SELECT
               SUM(CASE WHEN overall_point_won = 1.0 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN overall_point_won = 0.5 THEN 1 ELSE 0 END) AS ties,
               SUM(CASE WHEN overall_point_won = 0.0 THEN 1 ELSE 0 END) AS losses,
               COUNT(*) AS rounds
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               WHERE mr.team_id = %s AND m.season_id = %s""",
            (row['team_id'], season_id)
        ).fetchone()
        out.append({
            'Rank':        pos,
            'Team':        t_label,
            'Player 1':    row['p1_last'] or '',
            'Player 2':    row['p2_last'] or '',
            'Total Pts':   row['total_pts'],
            'Rounds':      wl['rounds'] if wl else 0,
            'Wins':        wl['wins']   if wl else 0,
            'Ties':        wl['ties']   if wl else 0,
            'Losses':      wl['losses'] if wl else 0,
        })

    season_slug = season['season_name'].replace(' ', '_')
    return _csv_response(out,
        ['Rank', 'Team', 'Player 1', 'Player 2', 'Total Pts', 'Rounds', 'Wins', 'Ties', 'Losses'],
        f'standings_{season_slug}.csv')


@bp.route('/<int:season_id>/export/scores')
@login_required
def export_scores(season_id):
    """CSV download: all round scores (per player per matchup) for a season."""
    db        = get_db()
    league_id = session['league_id']
    season    = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    score_rows = db.execute(
        """SELECT m.week_number, m.scheduled_date,
                  r.round_date, c.course_name, te.tee_name,
                  p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name AS team_nickname,
                  tp1.last_name AS t_p1_last, tp2.last_name AS t_p2_last,
                  sc.handicap_at_time_of_play AS handicap,
                  SUM(hs.gross_score) AS gross_total,
                  SUM(hs.net_score)   AS net_total,
                  SUM(mr.total_points) AS pts
           FROM scorecards sc
           JOIN players p   ON sc.player_id   = p.player_id
           JOIN teams t     ON sc.team_id     = t.team_id
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           JOIN rounds r    ON sc.round_id    = r.round_id
           JOIN matchups m  ON r.matchup_id   = m.matchup_id
           LEFT JOIN courses c ON r.course_id = c.course_id
           LEFT JOIN tees te   ON r.tee_id    = te.tee_id
           LEFT JOIN match_results mr ON mr.player_id  = sc.player_id
                                     AND mr.matchup_id = m.matchup_id
           JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
           WHERE m.season_id = %s AND m.status = 'completed'
           GROUP BY sc.scorecard_id, m.week_number, m.scheduled_date, r.round_date, c.course_name, te.tee_name,
                    p.first_name, p.last_name, t.team_name, tp1.last_name, tp2.last_name
           ORDER BY m.week_number, sc.team_id, p.last_name""",
        (season_id,)
    ).fetchall()

    out = []
    for row in score_rows:
        t_label = row['team_nickname'] or f"{row['t_p1_last'] or '?'} / {row['t_p2_last'] or '?'}"
        out.append({
            'Week':        row['week_number'],
            'Date':        row['round_date'] or row['scheduled_date'] or '',
            'Course':      row['course_name'] or '',
            'Tee':         row['tee_name'] or '',
            'Player':      row['player_name'],
            'Team':        t_label,
            'Handicap':    row['handicap'] if row['handicap'] is not None else '',
            'Gross Total': row['gross_total'] if row['gross_total'] is not None else '',
            'Net Total':   row['net_total']   if row['net_total']   is not None else '',
            'Points':      row['pts']         if row['pts']         is not None else '',
        })

    season_slug = season['season_name'].replace(' ', '_')
    return _csv_response(out,
        ['Week', 'Date', 'Course', 'Tee', 'Player', 'Team', 'Handicap', 'Gross Total', 'Net Total', 'Points'],
        f'scores_{season_slug}.csv')


@bp.route('/<int:season_id>/export/roster')
@login_required
def export_roster(season_id):
    """CSV download: player roster with handicaps for a season."""
    db        = get_db()
    league_id = session['league_id']
    season    = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    players = db.execute(
        """SELECT p.player_id, p.first_name, p.last_name, p.email,
                  p.starting_handicap,
                  t.team_name AS team_nickname,
                  tp1.last_name AS t_p1_last, tp2.last_name AS t_p2_last,
                  CASE WHEN t.player1_id = p.player_id THEN 'A' ELSE 'B' END AS role,
                  t.division
           FROM players p
           JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY p.last_name, p.first_name""",
        (season_id, league_id)
    ).fetchall()

    out = []
    for row in players:
        t_label = row['team_nickname'] or f"{row['t_p1_last'] or '?'} / {row['t_p2_last'] or '?'}"
        cur_hcp = _get_player_handicap(db, row['player_id'])
        cur_hcp = round(cur_hcp, 1) if cur_hcp is not None else (row['starting_handicap'] or '')
        out.append({
            'First Name':        row['first_name'],
            'Last Name':         row['last_name'],
            'Email':             row['email'] or '',
            'Team':              t_label,
            'Role':              row['role'],
            'Division':          row['division'] or '',
            'Current Handicap':  cur_hcp,
            'Starting Handicap': row['starting_handicap'] if row['starting_handicap'] is not None else '',
        })

    season_slug = season['season_name'].replace(' ', '_')
    return _csv_response(out,
        ['First Name', 'Last Name', 'Email', 'Team', 'Role', 'Division', 'Current Handicap', 'Starting Handicap'],
        f'roster_{season_slug}.csv')


@bp.route('/<int:season_id>/export/schedule')
@login_required
def export_schedule(season_id):
    """CSV download: full season schedule with results."""
    db        = get_db()
    league_id = session['league_id']
    season    = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    matchups = db.execute(
        """SELECT m.week_number, m.scheduled_date, m.week_type,
                  m.status, m.is_bye,
                  t1.team_name AS t1_nick,
                  p1a.last_name AS t1_p1_last, p1b.last_name AS t1_p2_last,
                  t2.team_name AS t2_nick,
                  p2a.last_name AS t2_p1_last, p2b.last_name AS t2_p2_last,
                  r.round_date, c.course_name,
                  m.matchup_id, m.team1_id, m.team2_id
           FROM matchups m
           JOIN teams t1 ON m.team1_id = t1.team_id
           LEFT JOIN teams t2 ON m.team2_id = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           LEFT JOIN rounds r ON r.matchup_id = m.matchup_id
           LEFT JOIN courses c ON r.course_id = c.course_id
           WHERE m.season_id = %s
           ORDER BY m.week_number, m.matchup_id""",
        (season_id,)
    ).fetchall()

    # Get per-matchup point totals
    pts_by_matchup = {}
    all_pts = db.execute(
        """SELECT mr.matchup_id, mr.team_id, SUM(mr.total_points) AS team_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s
           GROUP BY mr.matchup_id, mr.team_id""",
        (season_id,)
    ).fetchall()
    for r in all_pts:
        mid = r['matchup_id']
        if mid not in pts_by_matchup:
            pts_by_matchup[mid] = {}
        pts_by_matchup[mid][r['team_id']] = r['team_pts']

    out = []
    for m in matchups:
        if m['is_bye']:
            continue
        t1_label = m['t1_nick'] or f"{m['t1_p1_last'] or '?'} / {m['t1_p2_last'] or '?'}"
        t2_label = m['t2_nick'] or f"{m['t2_p1_last'] or '?'} / {m['t2_p2_last'] or '?'}" if m['team2_id'] else 'BYE'
        mid      = m['matchup_id']
        t1_pts   = pts_by_matchup.get(mid, {}).get(m['team1_id'], '')
        t2_pts   = pts_by_matchup.get(mid, {}).get(m['team2_id'], '') if m['team2_id'] else ''
        t1_pts_d = int(t1_pts) if isinstance(t1_pts, float) and t1_pts == int(t1_pts) else t1_pts
        t2_pts_d = int(t2_pts) if isinstance(t2_pts, float) and t2_pts == int(t2_pts) else t2_pts
        if t1_pts != '' and t2_pts != '':
            if t1_pts > t2_pts:
                winner = t1_label
            elif t2_pts > t1_pts:
                winner = t2_label
            else:
                winner = 'Tie'
        else:
            winner = ''
        out.append({
            'Week':        m['week_number'],
            'Date':        m['round_date'] or m['scheduled_date'] or '',
            'Week Type':   m['week_type'] or 'Normal',
            'Status':      m['status'].capitalize() if m['status'] else '',
            'Course':      m['course_name'] or '',
            'Team 1':      t1_label,
            'Team 1 Pts':  t1_pts_d,
            'Team 2':      t2_label,
            'Team 2 Pts':  t2_pts_d,
            'Winner':      winner,
        })

    season_slug = season['season_name'].replace(' ', '_')
    return _csv_response(out,
        ['Week', 'Date', 'Week Type', 'Status', 'Course', 'Team 1', 'Team 1 Pts', 'Team 2', 'Team 2 Pts', 'Winner'],
        f'schedule_{season_slug}.csv')
