"""
Playoffs blueprint — single-elimination bracket management.
/playoffs/                              redirect to latest season
/playoffs/<season_id>                   bracket overview + visualization
/playoffs/<season_id>/generate          POST: generate bracket from standings
/playoffs/<season_id>/matchup/<id>      POST: save result for a playoff matchup
/playoffs/<season_id>/reset             POST: delete bracket (admin only)
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required
import math
from datetime import date

bp = Blueprint('playoffs', __name__, url_prefix='/playoffs')


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


def _get_settings(db, season_id, league_id):
    row = db.execute(
        "SELECT playoff_teams, finals_weeks FROM league_settings WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if row:
        return {'playoff_teams': row['playoff_teams'] or 4, 'finals_weeks': row['finals_weeks'] or 2}
    return {'playoff_teams': 4, 'finals_weeks': 2}


def _get_team_label(team):
    """Build a display label for a team row (dict-like)."""
    if not team:
        return 'TBD'
    nickname = team['nickname'] if team['nickname'] else None
    if nickname:
        return nickname
    p1 = team['p1_last'] or ''
    p2 = team['p2_last'] or ''
    if p2:
        return f"{p1} / {p2}"
    return p1 or f"Team {team['team_id']}"


def _load_teams(db, season_id, league_id):
    """Return {team_id: team_row} for the season."""
    rows = db.execute(
        """SELECT t.team_id, t.team_name AS nickname,
                  p1.last_name AS p1_last, p1.first_name AS p1_first,
                  p2.last_name AS p2_last, p2.first_name AS p2_first
           FROM teams t
           JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s""",
        (season_id, league_id)
    ).fetchall()
    return {r['team_id']: r for r in rows}


def _standings_ordered(db, season_id, league_id):
    """Return teams ordered by total points DESC for seeding."""
    rows = db.execute(
        """SELECT t.team_id,
                  t.team_name AS nickname,
                  p1.last_name AS p1_last, p1.first_name AS p1_first,
                  p2.last_name AS p2_last, p2.first_name AS p2_first,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts
           FROM teams t
           JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           LEFT JOIN match_results mr ON mr.team_id = t.team_id
           LEFT JOIN matchups m ON mr.matchup_id = m.matchup_id AND m.season_id = %s
           WHERE t.season_id = %s AND t.league_id = %s
           GROUP BY t.team_id
           ORDER BY total_pts DESC""",
        (season_id, season_id, league_id)
    ).fetchall()
    return rows


def _build_bracket_data(db, bracket, teams_map):
    """
    Return bracket rounds as a list of round dicts:
    [
      {
        'round_number': 1,
        'label': 'Semifinals',
        'matchups': [
          {
            'matchup_id': ...,
            'team1': team_row or None,
            'team2': team_row or None,
            'team1_points': ...,
            'team2_points': ...,
            'winner_team_id': ...,
            'is_finals': ...,
            'week_number': ...,
          },
          ...
        ]
      },
      ...
    ]
    """
    bracket_id = bracket['bracket_id']
    total_teams = bracket['total_teams']
    num_rounds = int(math.log2(total_teams))

    raw = db.execute(
        """SELECT * FROM playoff_matchups
           WHERE bracket_id = %s
           ORDER BY round_number, matchup_id""",
        (bracket_id,)
    ).fetchall()

    rounds = []
    for rnum in range(1, num_rounds + 1):
        matchups_in_round = [m for m in raw if m['round_number'] == rnum]
        label = _round_label(rnum, num_rounds)
        matchup_dicts = []
        for m in matchups_in_round:
            matchup_dicts.append({
                'matchup_id':    m['matchup_id'],
                'team1':         teams_map.get(m['team1_id']) if m['team1_id'] else None,
                'team2':         teams_map.get(m['team2_id']) if m['team2_id'] else None,
                'team1_id':      m['team1_id'],
                'team2_id':      m['team2_id'],
                'team1_points':  m['team1_points'],
                'team2_points':  m['team2_points'],
                'winner_team_id': m['winner_team_id'],
                'is_finals':     m['is_finals'],
                'week_number':   m['week_number'],
            })
        rounds.append({
            'round_number': rnum,
            'label': label,
            'matchups': matchup_dicts,
        })
    return rounds


def _round_label(round_num, total_rounds):
    if round_num == total_rounds:
        return 'Championship'
    elif round_num == total_rounds - 1:
        return 'Semifinals'
    elif round_num == total_rounds - 2:
        return 'Quarterfinals'
    else:
        return f'Round {round_num}'


def _generate_bracket(db, season_id, league_id, bracket_id, total_teams):
    """
    Seed teams from standings and create Round 1 matchups.
    Creates placeholder rows for subsequent rounds (team_id = NULL).
    Standard bracket seeding: 1v(n), 2v(n-1), ...
    """
    seeds = _standings_ordered(db, season_id, league_id)
    num_rounds = int(math.log2(total_teams))

    # Pair seeds for round 1: 1v(n), 2v(n-1), ...
    pairs = []
    for i in range(total_teams // 2):
        t1 = seeds[i] if i < len(seeds) else None
        t2 = seeds[total_teams - 1 - i] if (total_teams - 1 - i) < len(seeds) else None
        pairs.append((
            t1['team_id'] if t1 else None,
            t2['team_id'] if t2 else None,
        ))

    # Insert round 1 matchups
    for wk, (t1_id, t2_id) in enumerate(pairs, start=1):
        db.execute(
            """INSERT INTO playoff_matchups
               (bracket_id, round_number, week_number, team1_id, team2_id, is_finals)
               VALUES (%s, 1, %s, %s, %s, 0)""",
            (bracket_id, wk, t1_id, t2_id)
        )

    # Insert placeholder matchups for subsequent rounds
    for rnum in range(2, num_rounds + 1):
        matchups_in_round = total_teams // (2 ** rnum)
        is_finals = 1 if rnum == num_rounds else 0
        for wk in range(1, matchups_in_round + 1):
            db.execute(
                """INSERT INTO playoff_matchups
                   (bracket_id, round_number, week_number, team1_id, team2_id, is_finals)
                   VALUES (%s, %s, %s, NULL, NULL, %s)""",
                (bracket_id, rnum, wk, is_finals)
            )

    db.commit()


def _advance_winner(db, bracket, won_matchup):
    """
    After a round 1 (or mid-round) matchup completes, place the winner
    into the correct slot of the next round.
    """
    bracket_id = bracket['bracket_id']
    total_teams = bracket['total_teams']
    num_rounds = int(math.log2(total_teams))

    round_num = won_matchup['round_number']
    if round_num >= num_rounds:
        # Finals completed — update bracket current_round to signal done
        db.execute(
            "UPDATE playoff_brackets SET current_round=%s WHERE bracket_id=%s",
            (round_num + 1, bracket_id)
        )
        db.commit()
        return

    # Figure out which next-round matchup this winner feeds into
    # Round 1 matchup week_number -> next round matchup week_number = ceil(week_number / 2)
    current_wk = won_matchup['week_number']
    next_wk = math.ceil(current_wk / 2)

    next_matchup = db.execute(
        """SELECT * FROM playoff_matchups
           WHERE bracket_id=%s AND round_number=%s AND week_number=%s""",
        (bracket_id, round_num + 1, next_wk)
    ).fetchone()

    if not next_matchup:
        return

    winner_id = won_matchup['winner_team_id']
    # Odd week_number -> team1 slot; even -> team2 slot
    if current_wk % 2 == 1:
        db.execute(
            "UPDATE playoff_matchups SET team1_id=%s WHERE matchup_id=%s",
            (winner_id, next_matchup['matchup_id'])
        )
    else:
        db.execute(
            "UPDATE playoff_matchups SET team2_id=%s WHERE matchup_id=%s",
            (winner_id, next_matchup['matchup_id'])
        )

    # Check if all matchups in current round are done; advance bracket round
    round_matchups = db.execute(
        "SELECT * FROM playoff_matchups WHERE bracket_id=%s AND round_number=%s",
        (bracket_id, round_num)
    ).fetchall()
    all_done = all(m['winner_team_id'] is not None for m in round_matchups)
    if all_done:
        db.execute(
            "UPDATE playoff_brackets SET current_round=%s WHERE bracket_id=%s",
            (round_num + 1, bracket_id)
        )
    db.commit()


# ---------------------------------------------------------------------------
# Landing — redirect to latest season
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def current():
    db = get_db()
    season = db.execute(
        "SELECT season_id FROM seasons WHERE league_id=%s ORDER BY season_id DESC LIMIT 1",
        (session['league_id'],)
    ).fetchone()
    if season:
        return redirect(url_for('playoffs.index', season_id=season['season_id']))
    flash('No seasons found.', 'error')
    return redirect(url_for('seasons.index'))


# ---------------------------------------------------------------------------
# Bracket overview  /playoffs/<season_id>
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>')
@login_required
def index(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    seasons = _all_seasons(db, league_id)
    settings = _get_settings(db, season_id, league_id)
    teams_map = _load_teams(db, season_id, league_id)
    standings = _standings_ordered(db, season_id, league_id)

    bracket = db.execute(
        "SELECT * FROM playoff_brackets WHERE season_id=%s AND league_id=%s ORDER BY bracket_id DESC LIMIT 1",
        (season_id, league_id)
    ).fetchone()

    rounds = []
    champion = None
    if bracket:
        rounds = _build_bracket_data(db, bracket, teams_map)
        # Find champion: winner of last round's only matchup
        if rounds:
            last_round = rounds[-1]
            if last_round['matchups'] and last_round['matchups'][0]['winner_team_id']:
                champ_id = last_round['matchups'][0]['winner_team_id']
                champion = teams_map.get(champ_id)

    return render_template('playoffs/index.html',
                           season=season, seasons=seasons,
                           bracket=bracket, rounds=rounds,
                           teams_map=teams_map, standings=standings,
                           settings=settings, champion=champion,
                           get_team_label=_get_team_label)


# ---------------------------------------------------------------------------
# Generate bracket  POST /playoffs/<season_id>/generate
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/generate', methods=['POST'])
@admin_required
def generate(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    # Check if bracket already exists
    existing = db.execute(
        "SELECT bracket_id FROM playoff_brackets WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if existing:
        flash('A bracket already exists for this season. Reset it first to regenerate.', 'error')
        return redirect(url_for('playoffs.index', season_id=season_id))

    settings = _get_settings(db, season_id, league_id)
    try:
        playoff_teams = int(request.form.get('playoff_teams', settings['playoff_teams']))
    except (ValueError, TypeError):
        playoff_teams = int(settings['playoff_teams'])

    # Must be power of 2
    if playoff_teams < 2 or (playoff_teams & (playoff_teams - 1)) != 0:
        flash('Number of playoff teams must be 2, 4, or 8.', 'error')
        return redirect(url_for('playoffs.index', season_id=season_id))

    # Check we have enough teams
    teams = _standings_ordered(db, season_id, league_id)
    if len(teams) < playoff_teams:
        flash(f'Not enough teams. Need {playoff_teams}, have {len(teams)}.', 'error')
        return redirect(url_for('playoffs.index', season_id=season_id))

    # Create bracket
    db.execute(
        """INSERT INTO playoff_brackets (season_id, league_id, total_teams, current_round, created_date)
           VALUES (%s, %s, %s, 1, %s)""",
        (season_id, league_id, playoff_teams, date.today().isoformat())
    )
    bracket_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()['id']

    _generate_bracket(db, season_id, league_id, bracket_id, playoff_teams)

    flash(f'Playoff bracket generated with {playoff_teams} teams!', 'success')
    return redirect(url_for('playoffs.index', season_id=season_id))


# ---------------------------------------------------------------------------
# Save matchup result  POST /playoffs/<season_id>/matchup/<matchup_id>
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/matchup/<int:matchup_id>', methods=['POST'])
@admin_required
def save_result(season_id, matchup_id):
    db = get_db()
    league_id = session['league_id']

    # Validate bracket belongs to this league/season
    matchup = db.execute(
        """SELECT pm.*, pb.league_id, pb.total_teams
           FROM playoff_matchups pm
           JOIN playoff_brackets pb ON pm.bracket_id = pb.bracket_id
           WHERE pm.matchup_id = %s AND pb.season_id = %s AND pb.league_id = %s""",
        (matchup_id, season_id, league_id)
    ).fetchone()

    if not matchup:
        flash('Matchup not found.', 'error')
        return redirect(url_for('playoffs.index', season_id=season_id))

    try:
        t1_pts = float(request.form.get('team1_points', 0) or 0)
        t2_pts = float(request.form.get('team2_points', 0) or 0)
    except ValueError:
        flash('Invalid points values.', 'error')
        return redirect(url_for('playoffs.index', season_id=season_id))

    # Determine winner (higher pts wins; ties require a designated winner)
    winner_id_form = request.form.get('winner_team_id')
    if t1_pts > t2_pts:
        winner_id = matchup['team1_id']
    elif t2_pts > t1_pts:
        winner_id = matchup['team2_id']
    elif winner_id_form:
        try:
            winner_id = int(winner_id_form)
        except ValueError:
            winner_id = matchup['team1_id']
    else:
        flash('Scores are tied — please select a winner.', 'error')
        return redirect(url_for('playoffs.index', season_id=season_id))

    db.execute(
        """UPDATE playoff_matchups
           SET team1_points=%s, team2_points=%s, winner_team_id=%s
           WHERE matchup_id=%s""",
        (t1_pts, t2_pts, winner_id, matchup_id)
    )
    db.commit()

    # Re-fetch updated matchup for advancement logic
    updated = db.execute("SELECT * FROM playoff_matchups WHERE matchup_id=%s", (matchup_id,)).fetchone()
    bracket = db.execute("SELECT * FROM playoff_brackets WHERE bracket_id=%s", (updated['bracket_id'],)).fetchone()
    _advance_winner(db, bracket, updated)

    flash('Result saved and bracket updated.', 'success')
    return redirect(url_for('playoffs.index', season_id=season_id))


# ---------------------------------------------------------------------------
# Reset bracket  POST /playoffs/<season_id>/reset
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/reset', methods=['POST'])
@admin_required
def reset(season_id):
    db = get_db()
    league_id = session['league_id']

    bracket = db.execute(
        "SELECT bracket_id FROM playoff_brackets WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if bracket:
        db.execute("DELETE FROM playoff_matchups WHERE bracket_id=%s", (bracket['bracket_id'],))
        db.execute("DELETE FROM playoff_brackets WHERE bracket_id=%s", (bracket['bracket_id'],))
        db.commit()
        flash('Playoff bracket has been reset.', 'success')
    else:
        flash('No bracket to reset.', 'error')
    return redirect(url_for('playoffs.index', season_id=season_id))
