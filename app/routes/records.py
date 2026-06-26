from flask import Blueprint, render_template, redirect, url_for, session
from database import get_db
from routes.auth import login_required

bp = Blueprint('records', __name__, url_prefix='/records')


def _all_seasons(db, league_id):
    return db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()


def _get_season(db, season_id, league_id):
    return db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()


# ---------------------------------------------------------------------------
# Redirect helpers
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def current():
    db = get_db()
    league_id = session['league_id']
    row = db.execute(
        "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (league_id,)
    ).fetchone()
    if not row:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('records.index', season_id=row['season_id']))


# ---------------------------------------------------------------------------
# Main records page
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>')
@login_required
def index(season_id):
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        return redirect(url_for('records.current'))

    all_seasons = _all_seasons(db, league_id)

    # ── Individual Season Records ─────────────────────────────────────────
    # Lowest gross round — grouped by player+score, weeks comma-separated
    low_gross_rows = db.execute(
        """SELECT player_id, player_name, team_name, total_gross,
                  STRING_AGG(week_number::TEXT, ', ' ORDER BY week_number) AS weeks
           FROM (
               SELECT p.player_id,
                      p.first_name || ' ' || p.last_name AS player_name,
                      COALESCE(NULLIF(t.team_name, ''),
                          (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                          (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                      SUM(hs.gross_score) AS total_gross,
                      m.week_number
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id = r.round_id
               JOIN matchups m    ON r.matchup_id = m.matchup_id
               JOIN players p     ON sc.player_id = p.player_id
               JOIN teams t       ON sc.team_id   = t.team_id
               WHERE m.season_id = %s AND m.is_bye = false
               GROUP BY sc.scorecard_id, p.player_id, p.first_name, p.last_name,
                        t.team_name, t.player1_id, t.player2_id, m.week_number
           ) sub
           GROUP BY player_id, player_name, team_name, total_gross
           ORDER BY total_gross ASC
           LIMIT 5""",
        (season_id,)
    ).fetchall()
    low_gross = [dict(r) for r in low_gross_rows]

    # Highest gross round — same structure
    high_gross_rows = db.execute(
        """SELECT player_id, player_name, team_name, total_gross,
                  STRING_AGG(week_number::TEXT, ', ' ORDER BY week_number DESC) AS weeks
           FROM (
               SELECT p.player_id,
                      p.first_name || ' ' || p.last_name AS player_name,
                      COALESCE(NULLIF(t.team_name, ''),
                          (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                          (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                      SUM(hs.gross_score) AS total_gross,
                      m.week_number
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id = r.round_id
               JOIN matchups m    ON r.matchup_id = m.matchup_id
               JOIN players p     ON sc.player_id = p.player_id
               JOIN teams t       ON sc.team_id   = t.team_id
               WHERE m.season_id = %s AND m.is_bye = false
               GROUP BY sc.scorecard_id, p.player_id, p.first_name, p.last_name,
                        t.team_name, t.player1_id, t.player2_id, m.week_number
           ) sub
           GROUP BY player_id, player_name, team_name, total_gross
           ORDER BY total_gross DESC
           LIMIT 5""",
        (season_id,)
    ).fetchall()
    high_gross = [dict(r) for r in high_gross_rows]

    # Highest individual points in a single match
    high_indiv_pts_rows = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name,
                  mr.total_points,
                  mr.hole_points_won,
                  mr.overall_point_won,
                  m.week_number,
                  r.round_date
           FROM match_results mr
           JOIN matchups m  ON mr.matchup_id = m.matchup_id
           JOIN rounds r    ON r.matchup_id  = m.matchup_id
           JOIN players p   ON mr.player_id  = p.player_id
           JOIN teams t     ON mr.team_id    = t.team_id
           WHERE m.season_id = %s
           ORDER BY mr.total_points DESC
           LIMIT 5""",
        (season_id,)
    ).fetchall()
    high_indiv_pts = [dict(r) for r in high_indiv_pts_rows]

    # Lowest individual points in a single match (min 1 entry)
    low_indiv_pts_rows = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name,
                  mr.total_points,
                  m.week_number,
                  r.round_date
           FROM match_results mr
           JOIN matchups m  ON mr.matchup_id = m.matchup_id
           JOIN rounds r    ON r.matchup_id  = m.matchup_id
           JOIN players p   ON mr.player_id  = p.player_id
           JOIN teams t     ON mr.team_id    = t.team_id
           WHERE m.season_id = %s
           ORDER BY mr.total_points ASC
           LIMIT 5""",
        (season_id,)
    ).fetchall()
    low_indiv_pts = [dict(r) for r in low_indiv_pts_rows]

    # ── Team Season Records ───────────────────────────────────────────────
    # Largest combined team pts in one match (both teams combined)
    team_pts_rows = db.execute(
        """SELECT m.matchup_id, m.week_number, r.round_date,
                  COALESCE(NULLIF(t1.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t1.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t1.player2_id)) AS team1_name,
                  COALESCE(NULLIF(t2.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t2.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t2.player2_id)) AS team2_name,
                  SUM(mr.total_points) AS combined_pts
           FROM matchups m
           JOIN rounds r        ON r.matchup_id = m.matchup_id
           JOIN teams t1        ON m.team1_id = t1.team_id
           JOIN teams t2        ON m.team2_id = t2.team_id
           JOIN match_results mr ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.is_bye = false
           GROUP BY m.matchup_id, m.week_number, r.round_date,
                    t1.team_name, t1.player1_id, t1.player2_id,
                    t2.team_name, t2.player1_id, t2.player2_id
           ORDER BY combined_pts DESC
           LIMIT 5""",
        (season_id,)
    ).fetchall()
    high_combined_pts = [dict(r) for r in team_pts_rows]

    # Biggest margin of victory (winner pts - loser pts per match)
    margin_rows = db.execute(
        """SELECT m.matchup_id, m.week_number, r.round_date,
                  COALESCE(NULLIF(t1.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t1.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t1.player2_id)) AS team1_name,
                  COALESCE(NULLIF(t2.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t2.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t2.player2_id)) AS team2_name,
                  SUM(CASE WHEN mr.team_id = m.team1_id THEN mr.total_points ELSE 0 END) AS t1_pts,
                  SUM(CASE WHEN mr.team_id = m.team2_id THEN mr.total_points ELSE 0 END) AS t2_pts
           FROM matchups m
           JOIN rounds r         ON r.matchup_id = m.matchup_id
           JOIN teams t1         ON m.team1_id = t1.team_id
           JOIN teams t2         ON m.team2_id = t2.team_id
           JOIN match_results mr ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.is_bye = false
           GROUP BY m.matchup_id, m.week_number, r.round_date,
                    t1.team_name, t1.player1_id, t1.player2_id,
                    t2.team_name, t2.player1_id, t2.player2_id
           ORDER BY ABS(SUM(CASE WHEN mr.team_id = m.team1_id THEN mr.total_points ELSE 0 END) -
                        SUM(CASE WHEN mr.team_id = m.team2_id THEN mr.total_points ELSE 0 END)) DESC
           LIMIT 5""",
        (season_id,)
    ).fetchall()
    big_margins = []
    for r in margin_rows:
        row = dict(r)
        t1 = row['t1_pts'] or 0
        t2 = row['t2_pts'] or 0
        row['margin'] = abs(t1 - t2)
        if t1 > t2:
            row['winner_name'] = row['team1_name']
            row['loser_name']  = row['team2_name']
            row['winner_pts']  = t1
            row['loser_pts']   = t2
        elif t2 > t1:
            row['winner_name'] = row['team2_name']
            row['loser_name']  = row['team1_name']
            row['winner_pts']  = t2
            row['loser_pts']   = t1
        else:
            row['winner_name'] = 'Tie'
            row['loser_name']  = ''
            row['winner_pts']  = t1
            row['loser_pts']   = t2
        big_margins.append(row)

    # ── Season Leaders table ──────────────────────────────────────────────
    season_leaders_rows = db.execute(
        """SELECT p.player_id,
                  p.first_name || ' ' || p.last_name AS player_name,
                  COALESCE(NULLIF(t.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                  COALESCE(SUM(mr.total_points), 0) AS season_pts,
                  COUNT(DISTINCT sc.scorecard_id)   AS rounds_played,
                  COALESCE(SUM(gross_totals.total_gross), 0) AS total_gross,
                  COALESCE(
                      CAST(SUM(gross_totals.total_gross) AS REAL) /
                      NULLIF(COUNT(DISTINCT sc.scorecard_id), 0),
                      0
                  ) AS avg_gross
           FROM players p
           JOIN scorecards sc     ON sc.player_id = p.player_id
           JOIN rounds r          ON sc.round_id  = r.round_id
           JOIN matchups m        ON r.matchup_id  = m.matchup_id
           JOIN teams t           ON sc.team_id    = t.team_id
           LEFT JOIN match_results mr ON mr.player_id = p.player_id AND mr.matchup_id = m.matchup_id
           LEFT JOIN (
               SELECT sc2.scorecard_id, SUM(hs.gross_score) AS total_gross
               FROM hole_scores hs
               JOIN scorecards sc2 ON hs.scorecard_id = sc2.scorecard_id
               GROUP BY sc2.scorecard_id
           ) gross_totals ON gross_totals.scorecard_id = sc.scorecard_id
           WHERE m.season_id = %s AND m.is_bye = false AND t.league_id = %s
           GROUP BY p.player_id, p.first_name, p.last_name, t.team_name, t.player1_id, t.player2_id
           ORDER BY season_pts DESC""",
        (season_id, league_id)
    ).fetchall()
    season_leaders = [dict(r) for r in season_leaders_rows]

    # Rank them properly (ties share rank)
    prev_pts = None
    prev_rank = 0
    for i, row in enumerate(season_leaders):
        if row['season_pts'] != prev_pts:
            prev_rank = i + 1
        row['rank'] = prev_rank
        prev_pts = row['season_pts']

    # ── Career / All-time Leaders ─────────────────────────────────────────
    career_pts_rows = db.execute(
        """SELECT p.player_id,
                  p.first_name || ' ' || p.last_name AS player_name,
                  COALESCE(SUM(mr.total_points), 0) AS career_pts,
                  COUNT(DISTINCT sc.scorecard_id)   AS rounds_played
           FROM players p
           JOIN scorecards sc    ON sc.player_id = p.player_id
           JOIN rounds r         ON sc.round_id  = r.round_id
           JOIN matchups m       ON r.matchup_id  = m.matchup_id
           JOIN seasons s        ON m.season_id   = s.season_id
           LEFT JOIN match_results mr ON mr.player_id = p.player_id AND mr.matchup_id = m.matchup_id
           WHERE s.league_id = %s AND m.is_bye = false
           GROUP BY p.player_id, p.first_name, p.last_name
           ORDER BY career_pts DESC
           LIMIT 10""",
        (league_id,)
    ).fetchall()
    career_pts = [dict(r) for r in career_pts_rows]

    career_avg_rows = db.execute(
        """SELECT p.player_id,
                  p.first_name || ' ' || p.last_name AS player_name,
                  COUNT(DISTINCT sc.scorecard_id) AS rounds_played,
                  COALESCE(
                      CAST(SUM(gross_totals.total_gross) AS REAL) /
                      NULLIF(COUNT(DISTINCT sc.scorecard_id), 0),
                      0
                  ) AS avg_gross
           FROM players p
           JOIN scorecards sc     ON sc.player_id = p.player_id
           JOIN rounds r          ON sc.round_id  = r.round_id
           JOIN matchups m        ON r.matchup_id  = m.matchup_id
           JOIN seasons s         ON m.season_id   = s.season_id
           LEFT JOIN (
               SELECT sc2.scorecard_id, SUM(hs.gross_score) AS total_gross
               FROM hole_scores hs
               JOIN scorecards sc2 ON hs.scorecard_id = sc2.scorecard_id
               GROUP BY sc2.scorecard_id
           ) gross_totals ON gross_totals.scorecard_id = sc.scorecard_id
           WHERE s.league_id = %s AND m.is_bye = false
           GROUP BY p.player_id, p.first_name, p.last_name
           HAVING COUNT(DISTINCT sc.scorecard_id) >= 3
           ORDER BY avg_gross ASC
           LIMIT 10""",
        (league_id,)
    ).fetchall()
    career_avg = [dict(r) for r in career_avg_rows]

    # Lowest handicap ever reached (join through players.league_id — no season_id on handicap_history)
    low_hdcp_rows = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  MIN(hh.handicap_index) AS lowest_hdcp,
                  MIN(hh.calculated_date) AS calculated_date
           FROM handicap_history hh
           JOIN players p ON hh.player_id = p.player_id
           WHERE p.league_id = %s
           GROUP BY hh.player_id, p.first_name, p.last_name
           ORDER BY lowest_hdcp ASC
           LIMIT 10""",
        (league_id,)
    ).fetchall()
    low_hdcp = [dict(r) for r in low_hdcp_rows]

    # ── Head-to-Head Records (current season) ────────────────────────────
    h2h_matchups = db.execute(
        """SELECT m.matchup_id, m.week_number,
                  t1.team_id AS t1_id,
                  COALESCE(NULLIF(t1.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t1.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t1.player2_id)) AS t1_name,
                  t2.team_id AS t2_id,
                  COALESCE(NULLIF(t2.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t2.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t2.player2_id)) AS t2_name,
                  SUM(CASE WHEN mr.team_id = m.team1_id THEN mr.total_points ELSE 0 END) AS t1_pts,
                  SUM(CASE WHEN mr.team_id = m.team2_id THEN mr.total_points ELSE 0 END) AS t2_pts
           FROM matchups m
           JOIN teams t1         ON m.team1_id = t1.team_id
           JOIN teams t2         ON m.team2_id = t2.team_id
           JOIN match_results mr ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.is_bye = false
           GROUP BY m.matchup_id, m.week_number,
                    t1.team_id, t1.team_name, t1.player1_id, t1.player2_id,
                    t2.team_id, t2.team_name, t2.player1_id, t2.player2_id""",
        (season_id,)
    ).fetchall()

    # Build pair dict: key = frozenset of two team_ids
    h2h_data = {}
    for row in h2h_matchups:
        t1_id   = row['t1_id']
        t2_id   = row['t2_id']
        t1_name = row['t1_name']
        t2_name = row['t2_name']
        t1_pts  = row['t1_pts'] or 0
        t2_pts  = row['t2_pts'] or 0

        key = (min(t1_id, t2_id), max(t1_id, t2_id))
        if key not in h2h_data:
            h2h_data[key] = {
                'team_a_id':   min(t1_id, t2_id),
                'team_b_id':   max(t1_id, t2_id),
                'team_a_name': t1_name if t1_id < t2_id else t2_name,
                'team_b_name': t2_name if t1_id < t2_id else t1_name,
                'a_wins': 0, 'b_wins': 0, 'ties': 0, 'matches': 0,
            }
        rec = h2h_data[key]
        rec['matches'] += 1
        a_pts = t1_pts if t1_id == rec['team_a_id'] else t2_pts
        b_pts = t2_pts if t2_id == rec['team_b_id'] else t1_pts
        if a_pts > b_pts:
            rec['a_wins'] += 1
        elif b_pts > a_pts:
            rec['b_wins'] += 1
        else:
            rec['ties'] += 1

    head_to_head = sorted(h2h_data.values(), key=lambda x: (x['team_a_name'], x['team_b_name']))

    # ── Streak data: current win/loss streaks by team ─────────────────────
    all_results = db.execute(
        """SELECT m.matchup_id, m.week_number,
                  t1.team_id AS t1_id,
                  COALESCE(NULLIF(t1.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t1.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t1.player2_id)) AS t1_name,
                  t2.team_id AS t2_id,
                  COALESCE(NULLIF(t2.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t2.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t2.player2_id)) AS t2_name,
                  SUM(CASE WHEN mr.team_id = m.team1_id THEN mr.total_points ELSE 0 END) AS t1_pts,
                  SUM(CASE WHEN mr.team_id = m.team2_id THEN mr.total_points ELSE 0 END) AS t2_pts
           FROM matchups m
           JOIN teams t1         ON m.team1_id = t1.team_id
           JOIN teams t2         ON m.team2_id = t2.team_id
           JOIN match_results mr ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.is_bye = false
           GROUP BY m.matchup_id, m.week_number,
                    t1.team_id, t1.team_name, t1.player1_id, t1.player2_id,
                    t2.team_id, t2.team_name, t2.player1_id, t2.player2_id
           ORDER BY m.week_number ASC""",
        (season_id,)
    ).fetchall()

    # Track streak per team: list of W/L/T outcomes most-recent-last
    team_outcomes = {}
    for row in all_results:
        t1_id  = row['t1_id']
        t2_id  = row['t2_id']
        t1_pts = row['t1_pts'] or 0
        t2_pts = row['t2_pts'] or 0
        for tid in [t1_id, t2_id]:
            if tid not in team_outcomes:
                team_outcomes[tid] = {'name': row['t1_name'] if tid == t1_id else row['t2_name'], 'results': []}
        if t1_pts > t2_pts:
            team_outcomes[t1_id]['results'].append('W')
            team_outcomes[t2_id]['results'].append('L')
        elif t2_pts > t1_pts:
            team_outcomes[t2_id]['results'].append('W')
            team_outcomes[t1_id]['results'].append('L')
        else:
            team_outcomes[t1_id]['results'].append('T')
            team_outcomes[t2_id]['results'].append('T')

    streaks = []
    for tid, data in team_outcomes.items():
        results = data['results']
        if not results:
            continue
        last = results[-1]
        count = 0
        for outcome in reversed(results):
            if outcome == last:
                count += 1
            else:
                break
        streaks.append({
            'team_name':   data['name'],
            'streak_type': last,
            'streak_len':  count,
            'results':     results,
        })
    streaks.sort(key=lambda x: (-x['streak_len'], x['team_name']))

    return render_template(
        'records/index.html',
        season=dict(season),
        all_seasons=[dict(s) for s in all_seasons],
        low_gross=low_gross,
        high_gross=high_gross,
        high_indiv_pts=high_indiv_pts,
        low_indiv_pts=low_indiv_pts,
        high_combined_pts=high_combined_pts,
        big_margins=big_margins,
        season_leaders=season_leaders,
        career_pts=career_pts,
        career_avg=career_avg,
        low_hdcp=low_hdcp,
        head_to_head=head_to_head,
        streaks=streaks,
    )
