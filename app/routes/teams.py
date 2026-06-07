from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required

bp = Blueprint('teams', __name__, url_prefix='/teams')


def _get_season_or_404(db, season_id):
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = ? AND league_id = ?",
        (season_id, session['league_id'])
    ).fetchone()
    return season


def _available_players(db, season_id, exclude_team_id=None):
    """Players not already assigned to two teams this season."""
    rows = db.execute(
        """SELECT player1_id, player2_id FROM teams
           WHERE season_id = ? AND league_id = ?""",
        (season_id, session['league_id'])
    ).fetchall()

    used = set()
    for r in rows:
        if exclude_team_id is None:
            if r['player1_id']: used.add(r['player1_id'])
            if r['player2_id']: used.add(r['player2_id'])

    if exclude_team_id:
        current = db.execute(
            "SELECT player1_id, player2_id FROM teams WHERE team_id = ?",
            (exclude_team_id,)
        ).fetchone()
        for r in rows:
            if r['player1_id'] and r['player1_id'] != (current['player1_id'] or -1) \
               and r['player1_id'] != (current['player2_id'] or -1):
                used.add(r['player1_id'])
            if r['player2_id'] and r['player2_id'] != (current['player1_id'] or -1) \
               and r['player2_id'] != (current['player2_id'] or -1):
                used.add(r['player2_id'])

    all_players = db.execute(
        "SELECT player_id, first_name, last_name FROM players WHERE league_id = ? ORDER BY last_name, first_name",
        (session['league_id'],)
    ).fetchall()

    return [p for p in all_players if p['player_id'] not in used]


def _get_divisions(db, season_id, league_id):
    """Get distinct division names already used in this season (for datalist)."""
    rows = db.execute(
        """SELECT DISTINCT division_name FROM teams
           WHERE season_id = ? AND league_id = ? AND division_name IS NOT NULL AND division_name != ''
           ORDER BY division_name""",
        (season_id, league_id)
    ).fetchall()
    return [r['division_name'] for r in rows]


@bp.route('/add/<int:season_id>', methods=['GET', 'POST'])
@admin_required
def add(season_id):
    db = get_db()
    season = _get_season_or_404(db, season_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    if request.method == 'POST':
        team_name     = request.form.get('team_name', '').strip()
        player1_id    = request.form.get('player1_id', '').strip() or None
        player2_id    = request.form.get('player2_id', '').strip() or None
        division_name = request.form.get('division_name', '').strip() or None

        errors = []
        if not team_name:
            errors.append('Team name is required.')
        if player1_id and player2_id and player1_id == player2_id:
            errors.append('Player 1 and Player 2 must be different.')

        if errors:
            for e in errors:
                flash(e, 'error')
            players   = _available_players(db, season_id)
            divisions = _get_divisions(db, season_id, session['league_id'])
            return render_template('teams/add.html', season=season, players=players,
                                   team_name=team_name, player1_id=player1_id,
                                   player2_id=player2_id, division_name=division_name or '',
                                   divisions=divisions)

        db.execute(
            """INSERT INTO teams (season_id, league_id, team_name, player1_id, player2_id, division_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (season_id, session['league_id'], team_name,
             int(player1_id) if player1_id else None,
             int(player2_id) if player2_id else None,
             division_name)
        )
        db.commit()
        flash(f'Team "{team_name}" added.', 'success')
        return redirect(url_for('seasons.detail', season_id=season_id))

    players   = _available_players(db, season_id)
    divisions = _get_divisions(db, season_id, session['league_id'])
    return render_template('teams/add.html', season=season, players=players,
                           team_name='', player1_id='', player2_id='',
                           division_name='', divisions=divisions)


@bp.route('/<int:team_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(team_id):
    db = get_db()
    team = db.execute(
        "SELECT * FROM teams WHERE team_id = ? AND league_id = ?",
        (team_id, session['league_id'])
    ).fetchone()
    if not team:
        flash('Team not found.', 'error')
        return redirect(url_for('seasons.index'))

    season = _get_season_or_404(db, team['season_id'])

    if request.method == 'POST':
        team_name     = request.form.get('team_name', '').strip()
        player1_id    = request.form.get('player1_id', '').strip() or None
        player2_id    = request.form.get('player2_id', '').strip() or None
        division_name = request.form.get('division_name', '').strip() or None

        errors = []
        if not team_name:
            errors.append('Team name is required.')
        if player1_id and player2_id and player1_id == player2_id:
            errors.append('Player 1 and Player 2 must be different.')

        if errors:
            for e in errors:
                flash(e, 'error')
            players   = _available_players(db, team['season_id'], exclude_team_id=team_id)
            divisions = _get_divisions(db, team['season_id'], session['league_id'])
            return render_template('teams/edit.html', season=season, team=team, players=players,
                                   team_name=team_name, player1_id=player1_id,
                                   player2_id=player2_id, division_name=division_name or '',
                                   divisions=divisions)

        db.execute(
            """UPDATE teams SET team_name = ?, player1_id = ?, player2_id = ?, division_name = ?
               WHERE team_id = ?""",
            (team_name,
             int(player1_id) if player1_id else None,
             int(player2_id) if player2_id else None,
             division_name, team_id)
        )
        db.commit()
        flash(f'Team "{team_name}" updated.', 'success')
        return redirect(url_for('seasons.detail', season_id=team['season_id']))

    players   = _available_players(db, team['season_id'], exclude_team_id=team_id)
    divisions = _get_divisions(db, team['season_id'], session['league_id'])
    # Safe column access — division_name may not exist in DB yet if migration hasn't run
    try:
        div_val = team['division_name'] or ''
    except (IndexError, KeyError):
        div_val = ''

    return render_template('teams/edit.html', season=season, team=team, players=players,
                           team_name=team['team_name'],
                           player1_id=str(team['player1_id']) if team['player1_id'] else '',
                           player2_id=str(team['player2_id']) if team['player2_id'] else '',
                           division_name=div_val, divisions=divisions)


@bp.route('/<int:team_id>')
@login_required
def profile(team_id):
    """Team profile page: season record, matchup history, player stats, H2H."""
    db  = get_db()
    lid = session['league_id']

    # ── Team info ────────────────────────────────────────────────────────────
    team = db.execute(
        """SELECT t.*,
                  p1.first_name AS p1_first, p1.last_name AS p1_last, p1.player_id AS p1_id,
                  p2.first_name AS p2_first, p2.last_name AS p2_last, p2.player_id AS p2_id,
                  s.season_name, s.season_id
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           JOIN seasons s ON t.season_id = s.season_id
           WHERE t.team_id = ? AND t.league_id = ?""",
        (team_id, lid)
    ).fetchone()
    if not team:
        flash('Team not found.', 'error')
        return redirect(url_for('main.dashboard'))

    season_id  = team['season_id']
    team_label = team['team_name'] or f"{team['p1_last'] or '?'} / {team['p2_last'] or '?'}"

    # ── Season standings position ─────────────────────────────────────────────
    all_teams = db.execute(
        """SELECT t2.team_id,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts
           FROM teams t2
           LEFT JOIN match_results mr ON mr.team_id = t2.team_id
           LEFT JOIN matchups m ON mr.matchup_id = m.matchup_id AND m.season_id = ?
           WHERE t2.season_id = ? AND t2.league_id = ?
           GROUP BY t2.team_id
           ORDER BY total_pts DESC""",
        (season_id, season_id, lid)
    ).fetchall()

    team_total_pts = 0
    standings_pos  = None
    for i, row in enumerate(all_teams, 1):
        if row['team_id'] == team_id:
            standings_pos = i
            team_total_pts = row['total_pts']
            break

    # ── Match-by-match results ────────────────────────────────────────────────
    matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.status,
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
           WHERE m.season_id = ? AND (m.team1_id = ? OR m.team2_id = ?) AND m.is_bye = 0
           ORDER BY m.week_number""",
        (season_id, team_id, team_id)
    ).fetchall()

    # Per-matchup pts for both teams
    matchup_ids = [m['matchup_id'] for m in matchups]
    pts_by_matchup = {}
    if matchup_ids:
        placeholders = ','.join('?' * len(matchup_ids))
        results = db.execute(
            f"""SELECT mr.matchup_id, mr.team_id, SUM(mr.total_points) AS pts
                FROM match_results mr
                WHERE mr.matchup_id IN ({placeholders})
                GROUP BY mr.matchup_id, mr.team_id""",
            matchup_ids
        ).fetchall()
        for r in results:
            pts_by_matchup.setdefault(r['matchup_id'], {})[r['team_id']] = r['pts']

    match_results = []
    wins = ties = losses = 0
    for m in matchups:
        mid      = m['matchup_id']
        opp_id   = m['team2_id'] if m['team1_id'] == team_id else m['team1_id']
        opp_nick = m['t2_nick'] or f"{m['t2_p1_last'] or '?'} / {m['t2_p2_last'] or '?'}" \
                   if m['team1_id'] == team_id else \
                   m['t1_nick'] or f"{m['t1_p1_last'] or '?'} / {m['t1_p2_last'] or '?'}"
        our_pts  = pts_by_matchup.get(mid, {}).get(team_id, None)
        opp_pts  = pts_by_matchup.get(mid, {}).get(opp_id, None)

        outcome = None
        if m['status'] == 'completed' and our_pts is not None and opp_pts is not None:
            if our_pts > opp_pts:
                outcome = 'W'; wins += 1
            elif opp_pts > our_pts:
                outcome = 'L'; losses += 1
            else:
                outcome = 'T'; ties += 1

        match_results.append({
            'week_number': m['week_number'],
            'date':        m['round_date'] or m['scheduled_date'] or '',
            'course':      m['course_name'] or '',
            'matchup_id':  mid,
            'opp_id':      opp_id,
            'opp_label':   opp_nick,
            'our_pts':     our_pts,
            'opp_pts':     opp_pts,
            'status':      m['status'],
            'outcome':     outcome,
        })

    total_matches = wins + ties + losses

    # ── H2H breakdown per opponent ────────────────────────────────────────────
    h2h = {}
    for mr in match_results:
        if mr['status'] != 'completed' or mr['outcome'] is None:
            continue
        opp = mr['opp_label']
        if opp not in h2h:
            h2h[opp] = {'opp_label': opp, 'opp_id': mr['opp_id'], 'w': 0, 't': 0, 'l': 0, 'pts_for': 0, 'pts_against': 0}
        h2h[opp]['pts_for']     += (mr['our_pts'] or 0)
        h2h[opp]['pts_against'] += (mr['opp_pts'] or 0)
        if mr['outcome'] == 'W':   h2h[opp]['w'] += 1
        elif mr['outcome'] == 'T': h2h[opp]['t'] += 1
        else:                      h2h[opp]['l'] += 1
    h2h_list = sorted(h2h.values(), key=lambda x: -(x['w'] * 2 + x['t']))

    # ── Per-player stats this season ─────────────────────────────────────────
    player_ids = [pid for pid in [team['p1_id'], team['p2_id']] if pid]
    player_stats = []
    for pid in player_ids:
        # Match record
        mr_rows = db.execute(
            """SELECT mr.total_points, mr.overall_point_won
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               WHERE mr.player_id = ? AND m.season_id = ?""",
            (pid, season_id)
        ).fetchall()
        total_pts  = sum(r['total_points'] for r in mr_rows)
        p_wins     = sum(1 for r in mr_rows if r['overall_point_won'] == 1.0)
        p_ties     = sum(1 for r in mr_rows if r['overall_point_won'] == 0.5)
        p_losses   = sum(1 for r in mr_rows if r['overall_point_won'] == 0.0)

        # Scoring stats
        sc_rows = db.execute(
            """SELECT sc.scorecard_id FROM scorecards sc
               JOIN rounds rnd ON sc.round_id = rnd.round_id
               JOIN matchups m ON rnd.matchup_id = m.matchup_id
               WHERE sc.player_id = ? AND m.season_id = ? AND sc.is_sub = 0""",
            (pid, season_id)
        ).fetchall()
        gross_totals = []
        birdie_count = eagle_count = 0
        for sc in sc_rows:
            hs_agg = db.execute(
                """SELECT SUM(gross_score) AS gtot,
                          SUM(CASE WHEN score_differential = -1 THEN 1 ELSE 0 END) AS birdies,
                          SUM(CASE WHEN score_differential <= -2 THEN 1 ELSE 0 END) AS eagles
                   FROM hole_scores WHERE scorecard_id = ?""",
                (sc['scorecard_id'],)
            ).fetchone()
            if hs_agg and hs_agg['gtot'] is not None:
                gross_totals.append(hs_agg['gtot'])
                birdie_count += (hs_agg['birdies'] or 0)
                eagle_count  += (hs_agg['eagles']  or 0)

        fname = team['p1_first'] if pid == team['p1_id'] else team['p2_first']
        lname = team['p1_last']  if pid == team['p1_id'] else team['p2_last']
        player_stats.append({
            'player_id':   pid,
            'name':        f"{fname} {lname}",
            'rounds':      len(gross_totals),
            'total_pts':   total_pts,
            'avg_gross':   round(sum(gross_totals) / len(gross_totals), 1) if gross_totals else None,
            'best_gross':  min(gross_totals) if gross_totals else None,
            'wins':        p_wins,
            'ties':        p_ties,
            'losses':      p_losses,
            'birdies':     birdie_count,
            'eagles':      eagle_count,
        })

    # ── Recent form (last 5 completed matches) ────────────────────────────────
    completed_matches = [mr for mr in match_results if mr['outcome']]
    recent_form = [mr['outcome'] for mr in completed_matches[-5:]]

    return render_template(
        'teams/profile.html',
        team=team,
        team_label=team_label,
        season_id=season_id,
        standings_pos=standings_pos,
        team_total_pts=team_total_pts,
        total_teams=len(all_teams),
        match_results=match_results,
        wins=wins, ties=ties, losses=losses,
        total_matches=total_matches,
        h2h_list=h2h_list,
        player_stats=player_stats,
        recent_form=recent_form,
    )
