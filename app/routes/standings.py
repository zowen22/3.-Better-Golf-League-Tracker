from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db, table_exists, get_current_season_id
from routes.auth import login_required
from routes.scores import strokes_on_hole
from routes.handicap import PRE_ELIGIBILITY_MARKER_PREFIX

bp = Blueprint('standings', __name__, url_prefix='/standings')


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


def _completed_weeks(db, season_id):
    rows = db.execute(
        """SELECT DISTINCT m.week_number, m.scheduled_date
           FROM matchups m
           WHERE m.season_id = %s AND m.status = 'completed'
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()
    return [(r['week_number'], r['scheduled_date']) for r in rows]


def _get_player_handicap(db, player_id, league_id=None):
    """Return (handicap index + any active committee adjustment, is_provisional).

    is_provisional=True means the latest handicap_history row is a
    pre-eligibility temp handicap (see handicap.PRE_ELIGIBILITY_MARKER_PREFIX)
    — callers displaying this to users should mark it (e.g. an asterisk)."""
    if not player_id:
        return None, False
    row = db.execute(
        "SELECT handicap_index, override_reason FROM handicap_history WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1",
        (player_id,)
    ).fetchone()
    is_provisional = False
    if row:
        base = row['handicap_index']
        is_provisional = bool(row['override_reason'] and
                               row['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))
    else:
        row2 = db.execute("SELECT starting_handicap FROM players WHERE player_id = %s", (player_id,)).fetchone()
        base = (row2['starting_handicap'] or 0) if row2 else 0

    adjustment = 0.0
    if league_id is not None:
        try:
            adj_row = db.execute(
                "SELECT adjustment FROM handicap_adjustments WHERE player_id = %s AND league_id = %s",
                (player_id, league_id)
            ).fetchone()
            if adj_row:
                adjustment = float(adj_row['adjustment'] or 0)
        except Exception:
            pass
    return base + adjustment, is_provisional


def _build_tee_header(db, course_id, nine, show_tees='M'):
    """Fetch all tees for a course/nine filtered by gender, with per-hole yardages."""
    if show_tees == 'F':
        gender_cond = "te.gender = 'F'"
    elif show_tees == 'both':
        gender_cond = "(te.gender = 'M' OR te.gender = 'F')"
    else:  # default M
        gender_cond = "te.gender = 'M'"

    raw_tees = db.execute(
        f"""SELECT te.tee_id, te.tee_name, te.tee_color, te.gender,
                   te.slope, te.rating, te.par_total
            FROM tees te
            WHERE te.course_id = %s AND te.nine = %s AND ({gender_cond})
            ORDER BY te.gender ASC, COALESCE(te.rating, 0) DESC""",
        (course_id, nine)
    ).fetchall()

    header_tees = []
    for ht in raw_tees:
        ht_holes = db.execute(
            "SELECT hole_number, distance_yards FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (ht['tee_id'],)
        ).fetchall()
        yardages = [h['distance_yards'] for h in ht_holes]
        total = sum(y for y in yardages if y) if any(yardages) else None
        label = ht['tee_name']
        if ht['slope'] and ht['rating']:
            label += f" {ht['rating']}/{int(ht['slope'])}"
        header_tees.append({
            'name':     label,
            'color':    ht['tee_color'] or '',
            'gender':   ht['gender'],
            'yardages': yardages,
            'total':    total,
        })
    return header_tees


def _standings_rows(db, season_id, league_id, sel_round='all'):
    """Return raw standings rows with division info and W-L-T record."""
    if sel_round == 'all' or not sel_round:
        rows = db.execute(
            """SELECT t.team_id,
                      p1.first_name AS p1_first, p1.last_name AS p1_last,
                      p2.first_name AS p2_first, p2.last_name AS p2_last,
                      t.team_name  AS nickname,
                      '' AS division_name,
                      COALESCE(SUM(mr.total_points), 0) AS total_pts,
                      COALESCE(SUM(CASE WHEN mr.overall_point_won >= 1.0 THEN 1 ELSE 0 END), 0) AS wins,
                      COALESCE(SUM(CASE WHEN mr.overall_point_won  = 0.0 THEN 1 ELSE 0 END), 0) AS losses,
                      COALESCE(SUM(CASE WHEN mr.overall_point_won  > 0.0
                                         AND mr.overall_point_won  < 1.0 THEN 1 ELSE 0 END), 0) AS ties
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
    else:
        wk = int(sel_round)
        rows = db.execute(
            """SELECT t.team_id,
                      p1.first_name AS p1_first, p1.last_name AS p1_last,
                      p2.first_name AS p2_first, p2.last_name AS p2_last,
                      t.team_name  AS nickname,
                      '' AS division_name,
                      COALESCE(SUM(mr.total_points), 0) AS total_pts,
                      COALESCE(SUM(CASE WHEN mr.overall_point_won >= 1.0 THEN 1 ELSE 0 END), 0) AS wins,
                      COALESCE(SUM(CASE WHEN mr.overall_point_won  = 0.0 THEN 1 ELSE 0 END), 0) AS losses,
                      COALESCE(SUM(CASE WHEN mr.overall_point_won  > 0.0
                                         AND mr.overall_point_won  < 1.0 THEN 1 ELSE 0 END), 0) AS ties
               FROM teams t
               LEFT JOIN players p1       ON t.player1_id  = p1.player_id
               LEFT JOIN players p2       ON t.player2_id  = p2.player_id
               LEFT JOIN match_results mr ON mr.team_id    = t.team_id
               LEFT JOIN matchups m       ON mr.matchup_id = m.matchup_id
                                         AND m.season_id   = %s
                                         AND m.week_number = %s
               WHERE t.season_id = %s AND t.league_id = %s
               GROUP BY t.team_id, p1.first_name, p1.last_name, p2.first_name, p2.last_name, t.team_name
               ORDER BY total_pts DESC""",
            (season_id, wk, season_id, league_id)
        ).fetchall()
    return rows



# ---------------------------------------------------------------------------
# Tiebreaker helpers
# ---------------------------------------------------------------------------

TIEBREAKER_LABELS = {
    'head_to_head':      'Head-to-Head',
    'points_percentage': 'Points %',
    'all_play_record':   'All-Play Record',
    'scoring_average':   'Scoring Average',
}
TIEBREAKER_OPTIONS = list(TIEBREAKER_LABELS.keys())
_TB_DEFAULTS = {
    'priority_1': 'head_to_head',
    'priority_2': 'points_percentage',
    'priority_3': 'all_play_record',
    'priority_4': 'scoring_average',
}


def _get_tiebreaker_settings(db, season_id, league_id):
    row = db.execute(
        "SELECT * FROM tiebreaker_settings WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if row:
        return {k: row[k] or v for k, v in _TB_DEFAULTS.items()}
    return dict(_TB_DEFAULTS)


def _tb_head_to_head(db, team_id, opponent_ids, season_id):
    """Points earned by team_id in direct matchups against these opponents."""
    total = 0.0
    for opp in opponent_ids:
        r = db.execute(
            """SELECT COALESCE(SUM(mr.total_points), 0) AS pts
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               WHERE mr.team_id = %s AND m.season_id = %s AND m.status = 'completed'
                 AND ((m.team1_id = %s AND m.team2_id = %s)
                   OR (m.team2_id = %s AND m.team1_id = %s))""",
            (team_id, season_id, team_id, opp, team_id, opp)
        ).fetchone()
        total += float(r['pts']) if r else 0.0
    return total


def _tb_points_pct(db, team_id, season_id):
    """Total points / (rounds_played * 20). Higher is better."""
    cnt = db.execute(
        """SELECT COUNT(*) AS cnt FROM matchups
           WHERE season_id = %s AND status = 'completed'
             AND (is_bye IS NULL OR is_bye = 0)
             AND (team1_id = %s OR team2_id = %s)""",
        (season_id, team_id, team_id)
    ).fetchone()['cnt']
    if cnt == 0:
        return 0.0
    pts = db.execute(
        """SELECT COALESCE(SUM(mr.total_points), 0) AS pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE mr.team_id = %s AND m.season_id = %s""",
        (team_id, season_id)
    ).fetchone()
    return float(pts['pts']) / (cnt * 20.0) if pts else 0.0


def _tb_allplay_pct(db, team_id, season_id):
    """All-play win % — (wins + 0.5*ties) / total comparisons. Higher is better."""
    weeks = db.execute(
        """SELECT DISTINCT week_number FROM matchups
           WHERE season_id = %s AND status = 'completed'
             AND (is_bye IS NULL OR is_bye = 0)""",
        (season_id,)
    ).fetchall()
    wins = ties = losses = 0
    for wk in weeks:
        wk_pts = db.execute(
            """SELECT mr.team_id, SUM(mr.total_points) AS pts
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               WHERE m.season_id = %s AND m.week_number = %s
               GROUP BY mr.team_id""",
            (season_id, wk['week_number'])
        ).fetchall()
        my_pts = next((float(r['pts']) for r in wk_pts if r['team_id'] == team_id), None)
        if my_pts is None:
            continue
        for r in wk_pts:
            if r['team_id'] == team_id:
                continue
            op = float(r['pts'])
            if my_pts > op:
                wins += 1
            elif my_pts == op:
                ties += 1
            else:
                losses += 1
    total = wins + ties + losses
    return (wins + 0.5 * ties) / total if total > 0 else 0.0


def _tb_scoring_avg(db, team_id, season_id):
    """Average gross score per scorecard (lower is better; returns positive value)."""
    team = db.execute(
        "SELECT player1_id, player2_id FROM teams WHERE team_id=%s", (team_id,)
    ).fetchone()
    if not team:
        return 999.0
    pids = [team['player1_id']]
    if team['player2_id']:
        pids.append(team['player2_id'])
    total, count = 0, 0
    for pid in pids:
        rows = db.execute(
            """SELECT SUM(hs.gross_score) AS g
               FROM scorecards sc
               JOIN rounds r   ON sc.round_id   = r.round_id
               JOIN matchups m ON r.matchup_id  = m.matchup_id
               JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
               WHERE sc.player_id = %s AND m.season_id = %s
               GROUP BY sc.scorecard_id""",
            (pid, season_id)
        ).fetchall()
        for row in rows:
            if row['g'] is not None:
                total += row['g']
                count += 1
    return total / count if count > 0 else 999.0


def _apply_tiebreakers(db, rows, season_id, tb):
    """Re-sort rows (already by total_pts DESC) applying tiebreakers within tied groups."""
    if len(rows) <= 1:
        return rows

    priorities = [tb.get('priority_1'), tb.get('priority_2'),
                  tb.get('priority_3'), tb.get('priority_4')]
    priorities = [p for p in priorities if p]

    # Split into tied groups
    groups, cur = [], [rows[0]]
    for r in rows[1:]:
        if float(r['total_pts']) == float(cur[0]['total_pts']):
            cur.append(r)
        else:
            groups.append(cur)
            cur = [r]
    groups.append(cur)

    result = []
    for group in groups:
        if len(group) == 1:
            result.extend(group)
            continue
        team_ids = [r['team_id'] for r in group]

        def sort_key(row, _ids=team_ids):
            key = []
            opp = [t for t in _ids if t != row['team_id']]
            for p in priorities:
                if p == 'head_to_head':
                    key.append(-_tb_head_to_head(db, row['team_id'], opp, season_id))
                elif p == 'points_percentage':
                    key.append(-_tb_points_pct(db, row['team_id'], season_id))
                elif p == 'all_play_record':
                    key.append(-_tb_allplay_pct(db, row['team_id'], season_id))
                elif p == 'scoring_average':
                    key.append(_tb_scoring_avg(db, row['team_id'], season_id))
                else:
                    key.append(0)
            return tuple(key)

        result.extend(sorted(group, key=sort_key))
    return result

# ---------------------------------------------------------------------------
# /standings/current
# ---------------------------------------------------------------------------

@bp.route('/current')
@login_required
def current():
    db = get_db()
    season_id = get_current_season_id(db, session['league_id'])
    if season_id:
        return redirect(url_for('standings.index', season_id=season_id))
    flash('No seasons found.', 'error')
    return redirect(url_for('seasons.index'))


# ---------------------------------------------------------------------------
# League Standings Summary  /standings/<season_id>
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

    seasons    = _all_seasons(db, league_id)
    comp_weeks = _completed_weeks(db, season_id)
    sel_round  = request.args.get('round', 'all')

    rows = _standings_rows(db, season_id, league_id, sel_round)

    # Load tiebreaker settings and apply within tied groups
    tb = _get_tiebreaker_settings(db, season_id, league_id)
    rows = _apply_tiebreakers(db, rows, season_id, tb)

    # Determine if any team has a division assigned
    has_divisions = any(r['division_name'] for r in rows)

    if has_divisions:
        # Group by division, rank within each division
        div_order = []
        div_map   = {}
        for r in rows:
            dname = r['division_name'] or 'Unassigned'
            if dname not in div_map:
                div_map[dname] = []
                div_order.append(dname)
            div_map[dname].append(dict(r))

        # Add position within each division
        for dname, drows in div_map.items():
            prev_pts, pos = None, 0
            for i, dr in enumerate(drows):
                if dr['total_pts'] != prev_pts:
                    pos = i + 1
                    prev_pts = dr['total_pts']
                dr['position'] = pos

        divisions_grouped = [{'name': d, 'rows': div_map[d]} for d in div_order]
        standings = []  # not used in grouped mode
    else:
        divisions_grouped = []
        standings = []
        prev_pts, pos = None, 0
        for i, r in enumerate(rows):
            if r['total_pts'] != prev_pts:
                pos = i + 1
                prev_pts = r['total_pts']
            standings.append({**dict(r), 'position': pos})

    return render_template('standings/index.html',
                           season=season, seasons=seasons,
                           standings=standings,
                           has_divisions=has_divisions,
                           divisions_grouped=divisions_grouped,
                           comp_weeks=comp_weeks, sel_round=sel_round,
                           tb=tb, tiebreaker_labels=TIEBREAKER_LABELS)


# ---------------------------------------------------------------------------
# Points by Division  /standings/<season_id>/divisions
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/divisions')
@login_required
def divisions(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    seasons = _all_seasons(db, league_id)

    # Fetch all players with their team's division, total pts, and handicap
    player_rows = db.execute(
        """SELECT p.player_id, p.first_name, p.last_name,
                  t.team_id, t.team_name AS team_nickname,
                  '' AS division_name,
                  tp1.last_name AS t_p1_last,
                  tp2.last_name AS t_p2_last,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts,
                  ROW_NUMBER() OVER (ORDER BY t.team_id) AS team_num
           FROM players p
           JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           LEFT JOIN match_results mr ON mr.player_id = p.player_id
               LEFT JOIN matchups m ON mr.matchup_id = m.matchup_id AND m.season_id = %s
           WHERE t.season_id = %s AND t.league_id = %s
           GROUP BY p.player_id, p.first_name, p.last_name, t.team_id, t.team_name, tp1.last_name, tp2.last_name
           ORDER BY total_pts DESC""",
        (season_id, season_id, league_id)
    ).fetchall()

    # Group by division
    div_order = []
    div_map   = {}
    for r in player_rows:
        dname = r['division_name'] or 'Unassigned'
        if dname not in div_map:
            div_map[dname] = []
            div_order.append(dname)
        row_dict = dict(r)
        row_dict['hdcp'], row_dict['hdcp_provisional'] = _get_player_handicap(db, r['player_id'], league_id=league_id)
        row_dict['name'] = f"{r['first_name']} {r['last_name']}"
        row_dict['team_label'] = f"#{r['team_num']} {r['t_p1_last'] or '?'}/{r['t_p2_last'] or '?'}"
        div_map[dname].append(row_dict)

    # Rank within each division
    for dname, drows in div_map.items():
        prev_pts, pos = None, 0
        for i, dr in enumerate(drows):
            if dr['total_pts'] != prev_pts:
                pos = i + 1
                prev_pts = dr['total_pts']
            dr['position'] = pos

    divisions_list = [{'name': d, 'players': div_map[d]} for d in div_order]
    has_divisions  = any(d['name'] != 'Unassigned' for d in divisions_list)

    return render_template('standings/divisions.html',
                           season=season, seasons=seasons,
                           divisions_list=divisions_list,
                           has_divisions=has_divisions)


# ---------------------------------------------------------------------------
# Team Scorecards  /standings/<season_id>/scorecards
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Team Scorecards  /standings/<season_id>/scorecards
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/scorecards')
@login_required
def scorecards(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    seasons    = _all_seasons(db, league_id)
    comp_weeks = _completed_weeks(db, season_id)

    as_of_week = request.args.get('as_of',     str(comp_weeks[-1][0]) if comp_weeks else '')
    score_type = request.args.get('score_type', 'gross')
    sort_by    = request.args.get('sort_by',    'pts')
    show_tees  = request.args.get('show_tees',  'M')

    # Fetch hole header from the most recent round in this season
    header_holes = []
    header_tees  = []
    header_course = None
    header_tee    = None
    recent_round = db.execute(
        """SELECT r.tee_id, r.course_id FROM rounds r
           JOIN matchups m ON r.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.status = 'completed'
           ORDER BY r.round_id DESC LIMIT 1""",
        (season_id,)
    ).fetchone()
    if recent_round:
        header_holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (recent_round['tee_id'],)
        ).fetchall()
        header_tee    = db.execute("SELECT * FROM tees    WHERE tee_id    = %s", (recent_round['tee_id'],)).fetchone()
        header_course = db.execute("SELECT * FROM courses WHERE course_id = %s", (recent_round['course_id'],)).fetchone()
        if header_tee and header_course:
            header_tees = _build_tee_header(db, header_course['course_id'], header_tee['nine'], show_tees)

    # Read segment configuration (requires migrate_add_segments.py)
    seg_row = db.execute(
        "SELECT * FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    seg_start = None
    seg_end   = None
    if seg_row:
        try:
            seg_start = seg_row['segment_start_week']
            seg_end   = seg_row['segment_end_week']
        except IndexError:
            pass  # columns not yet migrated
    has_segment = bool(seg_start and seg_end)

    if not comp_weeks:
        return render_template('standings/scorecards.html',
                               season=season, seasons=seasons,
                               player_rows=[], comp_weeks=comp_weeks,
                               as_of_week=as_of_week, score_type=score_type, sort_by=sort_by,
                               show_tees=show_tees,
                               weeks_shown=[],
                               has_segment=has_segment, seg_start=seg_start, seg_end=seg_end,
                               header_holes=header_holes, header_tees=header_tees,
                               header_course=header_course, header_tee=header_tee)

    max_week    = int(as_of_week) if as_of_week else comp_weeks[-1][0]
    weeks_shown = [w for w, _ in comp_weeks if w <= max_week]

    players = db.execute(
        """SELECT p.player_id, p.first_name, p.last_name,
                  t.team_id, t.team_name AS team_nickname,
                  tp1.last_name AS t_p1_last, tp2.last_name AS t_p2_last,
                  ROW_NUMBER() OVER (ORDER BY t.team_id) AS team_num
           FROM players p
           JOIN teams t   ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY t.team_id, p.player_id""",
        (season_id, league_id)
    ).fetchall()

    score_col  = 'hs.gross_score' if score_type == 'gross' else 'hs.net_score'
    score_rows = db.execute(
        f"""SELECT sc.player_id, m.week_number,
                   SUM(CASE WHEN sc.is_absent = 0 THEN {score_col} END) AS week_score,
                   SUM(mr.total_points)   AS week_pts
            FROM scorecards sc
            JOIN rounds        r  ON sc.round_id     = r.round_id
            JOIN matchups      m  ON r.matchup_id    = m.matchup_id
            JOIN hole_scores   hs ON hs.scorecard_id = sc.scorecard_id
            LEFT JOIN match_results mr ON mr.player_id  = sc.player_id
                                      AND mr.matchup_id = m.matchup_id
            WHERE m.season_id = %s AND m.week_number <= %s
            GROUP BY sc.player_id, m.week_number""",
        (season_id, max_week)
    ).fetchall()

    by_player = {}
    for r in score_rows:
        by_player.setdefault(r['player_id'], {})[r['week_number']] = {
            'score': r['week_score'],
            'pts':   r['week_pts'] or 0,
        }

    player_rows = []
    for p in players:
        pid   = p['player_id']
        pdata = by_player.get(pid, {})
        week_scores    = [pdata.get(w, {}).get('score', None) for w in weeks_shown]
        week_pts_list  = [int(pdata.get(w, {}).get('pts',   0))    for w in weeks_shown]
        season_pts     = sum(week_pts_list)
        filled         = [s for s in week_scores if s is not None]
        avg_score      = round(sum(filled) / len(filled), 1) if filled else None

        # Indiv pts = pts earned in the as_of (most recent selected) week only
        indiv_pts = int(pdata.get(max_week, {}).get('pts', 0))

        # Segment pts = pts from weeks within the configured segment window
        if has_segment:
            segment_pts = int(sum(
                pdata.get(w, {}).get('pts', 0)
                for w in weeks_shown
                if seg_start <= w <= seg_end
            ))
        else:
            segment_pts = None

        hdcp, hdcp_provisional = _get_player_handicap(db, pid, league_id=league_id)
        player_rows.append({
            'player_id':    pid,
            'team_id':      p['team_id'],
            'name':         f"{p['first_name']} {p['last_name']}",
            'team_label':   f"#{p['team_num']} {p['t_p1_last'] or '?'}/{p['t_p2_last'] or '?'}",
            'team_num':     p['team_num'],
            'hdcp':         hdcp,
            'hdcp_provisional': hdcp_provisional,
            'week_scores':  week_scores,
            'week_pts_list':week_pts_list,
            'avg_score':    avg_score,
            'indiv_pts':    indiv_pts,
            'segment_pts':  segment_pts,
            'season_pts':   season_pts,
            'total_pts':    season_pts,  # kept for sorting compatibility
        })

    # Build team-level standings position as of max_week (historical)
    team_pts_rows = db.execute(
        """SELECT t.team_id, COALESCE(SUM(mr.total_points), 0) AS team_total
           FROM teams t
           LEFT JOIN match_results mr ON mr.team_id = t.team_id
           LEFT JOIN matchups m ON mr.matchup_id = m.matchup_id
                               AND m.season_id = %s
                               AND m.week_number <= %s
           WHERE t.season_id = %s AND t.league_id = %s
           GROUP BY t.team_id
           ORDER BY team_total DESC""",
        (season_id, max_week, season_id, league_id)
    ).fetchall()
    team_position = {}
    prev_tp, tp = None, 0
    for i, tr in enumerate(team_pts_rows):
        if tr['team_total'] != prev_tp:
            tp = i + 1
            prev_tp = tr['team_total']
        team_position[tr['team_id']] = tp

    if sort_by == 'pts':
        player_rows.sort(key=lambda r: (-r['total_pts'], r['name']))
    elif sort_by == 'hdcp':
        player_rows.sort(key=lambda r: (r['hdcp'] or 99))
    else:
        player_rows.sort(key=lambda r: r['name'])

    for r in player_rows:
        r['pos'] = team_position.get(r['team_id'], '—')

    return render_template('standings/scorecards.html',
                           season=season, seasons=seasons,
                           player_rows=player_rows, comp_weeks=comp_weeks,
                           weeks_shown=weeks_shown,
                           as_of_week=str(max_week), score_type=score_type,
                           sort_by=sort_by, show_tees=show_tees,
                           has_segment=has_segment, seg_start=seg_start, seg_end=seg_end,
                           header_holes=header_holes, header_tees=header_tees,
                           header_course=header_course, header_tee=header_tee)



# ---------------------------------------------------------------------------
# Weekly Scorecards  /standings/<season_id>/weekly[/<week_num>]
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/weekly')
@bp.route('/<int:season_id>/weekly/<int:week_num>')
@login_required
def weekly(season_id, week_num=None):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    seasons    = _all_seasons(db, league_id)
    comp_weeks = _completed_weeks(db, season_id)
    score_type = request.args.get('score_type', 'gross')
    show_tees  = request.args.get('show_tees',  'M')

    if not comp_weeks:
        return render_template('standings/weekly.html',
                               season=season, seasons=seasons,
                               comp_weeks=[], groups=[], holes=[],
                               sel_week=None, score_type=score_type,
                               show_tees=show_tees,
                               all_header_tees=[], all_holes=[])

    if week_num is None:
        week_num = comp_weeks[-1][0]

    matchups = db.execute(
        """SELECT m.* FROM matchups m
           WHERE m.season_id = %s AND m.week_number = %s
             AND m.status = 'completed' AND m.is_bye = 0
           ORDER BY m.matchup_id""",
        (season_id, week_num)
    ).fetchall()

    team_num_rows = db.execute(
        """SELECT team_id, ROW_NUMBER() OVER (ORDER BY team_id) AS team_num
           FROM teams WHERE season_id = %s AND league_id = %s""",
        (season_id, league_id)
    ).fetchall()
    team_nums = {r['team_id']: r['team_num'] for r in team_num_rows}

    groups      = []
    all_holes   = []
    all_header_tees = []

    for g_idx, matchup in enumerate(matchups, start=1):
        round_row = db.execute("SELECT * FROM rounds WHERE matchup_id = %s",
                               (matchup['matchup_id'],)).fetchone()
        if not round_row:
            continue

        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (round_row['tee_id'],)
        ).fetchall()
        if not all_holes:
            all_holes = holes

        tee    = db.execute("SELECT * FROM tees    WHERE tee_id    = %s", (round_row['tee_id'],)).fetchone()
        course = db.execute("SELECT * FROM courses WHERE course_id = %s", (round_row['course_id'],)).fetchone()

        header_tees = []
        if g_idx == 1 and tee and course:
            header_tees = _build_tee_header(db, course['course_id'], tee['nine'], show_tees)
            all_header_tees = header_tees

        sc_rows = db.execute(
            """SELECT sc.scorecard_id, sc.player_id, sc.team_id,
                      sc.handicap_at_time_of_play AS hcp,
                      sc.tee_id AS sc_tee_id,
                      sc.is_sub, sc.sub_for_player_id,
                      p.first_name, p.last_name,
                      mr.role, mr.hole_points_won, mr.overall_point_won,
                      mr.total_points AS indv_pts,
                      mr.opponent_player_id
               FROM scorecards sc
               JOIN players p ON sc.player_id = p.player_id
               LEFT JOIN match_results mr ON mr.player_id  = sc.player_id
                                         AND mr.matchup_id = %s
               WHERE sc.round_id = %s
               ORDER BY sc.team_id, mr.role""",
            (matchup['matchup_id'], round_row['round_id'])
        ).fetchall()

        player_holes = {}
        for sc in sc_rows:
            hs = db.execute(
                "SELECT * FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
                (sc['scorecard_id'],)
            ).fetchall()
            player_holes[sc['player_id']] = hs

        t1 = matchup['team1_id']
        t2 = matchup['team2_id']

        by_role = {}
        for sc in sc_rows:
            key = (sc['team_id'], sc['role'])
            by_role[key] = sc

        pid_t1_a = by_role.get((t1, 'A'))
        pid_t1_b = by_role.get((t1, 'B'))
        pid_t2_a = by_role.get((t2, 'A'))
        pid_t2_b = by_role.get((t2, 'B'))

        def compute_hole_pts(sc_x, sc_y):
            # Differential stroke allocation (only the higher-handicap player
            # gets strokes, equal to the handicap gap), matching match_results.
            # hole_scores.net_score itself stays absolute (unaffected here).
            px_id = sc_x['player_id'] if sc_x is not None else None
            py_id = sc_y['player_id'] if sc_y is not None else None
            hx = player_holes.get(px_id, [])
            hy = player_holes.get(py_id, [])
            ph_x = (sc_x['hcp'] or 0) if sc_x is not None else 0
            ph_y = (sc_y['hcp'] or 0) if sc_y is not None else 0
            diff_x = ph_x - ph_y
            diff_y = ph_y - ph_x
            n_holes_here = len(holes) or 9
            hcp_idxs_here = [h['handicap_index'] for h in holes]
            px_list, py_list = [], []
            for i, h in enumerate(holes):
                gx = hx[i]['gross_score'] if i < len(hx) else None
                gy = hy[i]['gross_score'] if i < len(hy) else None
                if gx is None or gy is None:
                    px_list.append(None); py_list.append(None)
                    continue
                sx = strokes_on_hole(diff_x, h['handicap_index'], n_holes_here,
                                      hcp_indices=hcp_idxs_here) if diff_x > 0 else 0
                sy = strokes_on_hole(diff_y, h['handicap_index'], n_holes_here,
                                      hcp_indices=hcp_idxs_here) if diff_y > 0 else 0
                dnx, dny = gx - sx, gy - sy
                if dnx < dny:
                    px_list.append(2); py_list.append(0)
                elif dny < dnx:
                    px_list.append(0); py_list.append(2)
                else:
                    px_list.append(1); py_list.append(1)
            return px_list, py_list

        aa_pts_1, aa_pts_2 = compute_hole_pts(pid_t1_a, pid_t2_a)
        bb_pts_1, bb_pts_2 = compute_hole_pts(pid_t1_b, pid_t2_b)

        per_hole_pts = {}
        for sc_ref, pts in [(pid_t1_a, aa_pts_1), (pid_t2_a, aa_pts_2),
                             (pid_t1_b, bb_pts_1), (pid_t2_b, bb_pts_2)]:
            if sc_ref is not None:
                per_hole_pts[sc_ref['player_id']] = pts

        # Tee lookup cache for this group
        tee_cache = {}
        def _get_tee(tee_id):
            if tee_id not in tee_cache:
                t = db.execute("SELECT tee_name, tee_color FROM tees WHERE tee_id = %s", (tee_id,)).fetchone()
                tee_cache[tee_id] = t
            return tee_cache[tee_id]

        def make_player_dict(sc):
            if sc is None:
                return None
            pid  = sc['player_id']
            hs   = player_holes.get(pid, [])
            hpts = per_hole_pts.get(pid, [])
            scores    = [h['gross_score'] if score_type == 'gross' else h['net_score']
                         for h in hs]
            total_in  = int(sum(h['gross_score'] if score_type == 'gross' else h['net_score'] for h in hs))
            total_net = int(sum(h['net_score']   for h in hs))
            raw_hcp   = sc['hcp']
            hcp_disp  = int(round(raw_hcp)) if raw_hcp is not None else 0
            player_tee_id = sc['sc_tee_id'] or round_row['tee_id']
            p_tee = _get_tee(player_tee_id)
            tee_nm  = p_tee['tee_name']  if p_tee else None
            tee_clr = p_tee['tee_color'] if p_tee else None
            # Sub indicator
            is_sub_flag = bool(sc['is_sub'])
            sub_for_name = None
            if is_sub_flag and sc['sub_for_player_id']:
                absent_p = db.execute(
                    "SELECT first_name, last_name FROM players WHERE player_id = %s",
                    (sc['sub_for_player_id'],)
                ).fetchone()
                if absent_p:
                    sub_for_name = f"{absent_p['first_name']} {absent_p['last_name']}"
            return {
                'name':      f"{sc['first_name']} {sc['last_name']}",
                'team_num':  team_nums.get(sc['team_id'], '?'),
                'hcp':       hcp_disp,
                'tee_name':  tee_nm,
                'tee_color': tee_clr,
                'scores':    scores,
                'hole_pts':  hpts,
                'total_in':  total_in,
                'total_net': total_net,
                'indv_pts':  int(sc['indv_pts'] or 0),
                'is_sub':    is_sub_flag,
                'sub_for':   sub_for_name,
            }

        pairs = []
        for sc1, sc2 in [(pid_t1_a, pid_t2_a), (pid_t1_b, pid_t2_b)]:
            p1 = make_player_dict(sc1)
            p2 = make_player_dict(sc2)
            players_in_pair = [p for p in [p1, p2] if p is not None]
            if players_in_pair:
                pairs.append({'players': players_in_pair})

        groups.append({
            'group_num':   g_idx,
            'matchup':     matchup,
            'course':      course,
            'tee':         tee,
            'holes':       holes,
            'tee_time':    matchup['tee_time'],
            'pairs':       pairs,
            'header_tees': header_tees,
        })

    return render_template('standings/weekly.html',
                           season=season, seasons=seasons,
                           comp_weeks=comp_weeks,
                           groups=groups,
                           holes=all_holes,
                           all_header_tees=all_header_tees,
                           sel_week=week_num,
                           score_type=score_type,
                           show_tees=show_tees)


# ---------------------------------------------------------------------------
# All-Play Standings  /standings/<season_id>/allplay
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/allplay')
@login_required
def allplay(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    seasons = _all_seasons(db, league_id)

    # All teams for this season
    teams = db.execute(
        """SELECT t.team_id,
                  p1.last_name  AS p1_last,  p2.last_name  AS p2_last,
                  p1.first_name AS p1_first, p2.first_name AS p2_first,
                  t.team_name AS nickname,
                  ROW_NUMBER() OVER (ORDER BY t.team_id) AS team_num
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY t.team_id""",
        (season_id, league_id)
    ).fetchall()

    # Total points per team per week (only completed non-bye matchups)
    week_pts_rows = db.execute(
        """SELECT m.week_number, mr.team_id,
                  SUM(mr.total_points) AS team_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           GROUP BY m.week_number, mr.team_id
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    # Build: week_data[week_number] = {team_id: pts, ...}
    week_data = {}
    for row in week_pts_rows:
        wk = row['week_number']
        if wk not in week_data:
            week_data[wk] = {}
        week_data[wk][row['team_id']] = row['team_pts']

    team_ids = [t['team_id'] for t in teams]
    records  = {tid: {'w': 0, 'l': 0, 't': 0} for tid in team_ids}
    # week_records[week][team_id] = {'w':X,'l':Y,'t':Z}
    week_records = {}

    # Build (week_num, date) tuples for template
    week_dates_rows = db.execute(
        """SELECT DISTINCT m.week_number, m.scheduled_date FROM matchups m
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()
    week_date_map = {r['week_number']: r['scheduled_date'] for r in week_dates_rows}
    completed_weeks = [(wk, week_date_map.get(wk)) for wk in sorted(week_data.keys())]

    for wk, _wdate in completed_weeks:
        team_pts = week_data[wk]
        wk_rec   = {tid: {'w': 0, 'l': 0, 't': 0} for tid in team_ids}
        playing  = list(team_pts.keys())
        for i, ta in enumerate(playing):
            for tb in playing[i + 1:]:
                pts_a = team_pts[ta]
                pts_b = team_pts[tb]
                if pts_a > pts_b:
                    records[ta]['w'] += 1;  wk_rec[ta]['w'] += 1
                    records[tb]['l'] += 1;  wk_rec[tb]['l'] += 1
                elif pts_b > pts_a:
                    records[tb]['w'] += 1;  wk_rec[tb]['w'] += 1
                    records[ta]['l'] += 1;  wk_rec[ta]['l'] += 1
                else:
                    records[ta]['t'] += 1;  wk_rec[ta]['t'] += 1
                    records[tb]['t'] += 1;  wk_rec[tb]['t'] += 1
        week_records[wk] = wk_rec

    # Season pts per team (for reference column)
    sp_rows = db.execute(
        """SELECT mr.team_id, SUM(mr.total_points) AS total_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.status = 'completed'
           GROUP BY mr.team_id""",
        (season_id,)
    ).fetchall()
    season_pts = {r['team_id']: r['total_pts'] for r in sp_rows}

    allplay_rows = []
    for t in teams:
        tid = t['team_id']
        rec = records[tid]
        w, l, tv = rec['w'], rec['l'], rec['t']
        total_games = w + l + tv
        pct = round((w + 0.5 * tv) / total_games, 3) if total_games > 0 else 0.0
        week_recs = [week_records.get(wk, {}).get(tid, {'w': 0, 'l': 0, 't': 0})
                     for wk, _d in completed_weeks]
        allplay_rows.append({
            'team_id':   tid,
            'team_num':  t['team_num'],
            'p1_last':   t['p1_last'],
            'p2_last':   t['p2_last'],
            'nickname':  t['nickname'],
            'w':         w,
            'l':         l,
            't':         tv,
            'pct':       pct,
            'week_recs': week_recs,
            'season_pts': season_pts.get(tid, 0),
        })

    allplay_rows.sort(key=lambda r: (-r['pct'], -(r['w'] + 0.5 * r['t'])))

    return render_template('standings/allplay.html',
                           season=season, seasons=seasons,
                           allplay_rows=allplay_rows,
                           completed_weeks=completed_weeks)


# ---------------------------------------------------------------------------
# Individual Player Standings
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/individual')
@login_required
def individual(season_id):
    league_id = session['league_id']
    db = get_db()

    season  = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))
    seasons = _all_seasons(db, league_id)

    # ── 1. Match-results stats per player ──────────────────────────────────
    mr_rows = db.execute('''
        SELECT
            p.player_id,
            p.first_name || ' ' || p.last_name  AS player_name,
            p.first_name,
            p.last_name,
            t.team_id,
            t.team_name,
            mr.role,
            COUNT(DISTINCT mr.matchup_id)        AS rounds_played,
            ROUND(SUM(mr.total_points)::numeric, 1)       AS total_points,
            ROUND(SUM(mr.hole_points_won)::numeric, 1)    AS hole_pts,
            ROUND(SUM(mr.overall_point_won)::numeric, 1)  AS overall_pts,
            SUM(CASE WHEN mr.overall_point_won >= 1.0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN mr.overall_point_won  = 0.5 THEN 1 ELSE 0 END) AS ties,
            SUM(CASE WHEN mr.overall_point_won  = 0.0 THEN 1 ELSE 0 END) AS losses
        FROM match_results mr
        JOIN teams  t ON mr.team_id  = t.team_id
        JOIN players p ON mr.player_id = p.player_id
        WHERE t.season_id  = %s
          AND t.league_id  = %s
        GROUP BY p.player_id, p.first_name, p.last_name, t.team_id, t.team_name, mr.role
        ORDER BY total_points DESC, rounds_played DESC
    ''', (season_id, league_id)).fetchall()

    # ── 2. Scoring stats per player (from hole_scores) ─────────────────────
    # For each player: avg gross per round, best round gross, birdies, eagles
    scoring_rows = db.execute('''
        SELECT
            sc.player_id,
            SUM(hs.gross_score)                              AS round_gross,
            COUNT(DISTINCT sc.scorecard_id)                  AS scorecards,
            SUM(CASE WHEN hs.score_differential <= -2 THEN 1 ELSE 0 END) AS eagles,
            SUM(CASE WHEN hs.score_differential  = -1 THEN 1 ELSE 0 END) AS birdies,
            SUM(CASE WHEN hs.score_differential  =  0 THEN 1 ELSE 0 END) AS pars,
            SUM(CASE WHEN hs.score_differential  =  1 THEN 1 ELSE 0 END) AS bogeys,
            SUM(CASE WHEN hs.score_differential  >= 2 THEN 1 ELSE 0 END) AS doubles_plus
        FROM scorecards sc
        JOIN rounds r      ON sc.round_id    = r.round_id
        JOIN matchups m    ON r.matchup_id   = m.matchup_id
        JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
        WHERE r.season_id = %s
          AND m.season_id = %s
          AND sc.is_sub   = 0
          AND sc.is_absent = 0
        GROUP BY sc.player_id, sc.scorecard_id
    ''', (season_id, season_id)).fetchall()

    # Aggregate per-player: avg gross, best round, total birdies, total eagles
    from collections import defaultdict
    player_scoring = defaultdict(lambda: {
        'rounds': [], 'eagles': 0, 'birdies': 0, 'pars': 0,
        'bogeys': 0, 'doubles_plus': 0
    })
    for sr in scoring_rows:
        pid = sr['player_id']
        if sr['round_gross'] is not None:
            player_scoring[pid]['rounds'].append(sr['round_gross'])
        player_scoring[pid]['eagles']       += sr['eagles'] or 0
        player_scoring[pid]['birdies']      += sr['birdies'] or 0
        player_scoring[pid]['pars']         += sr['pars'] or 0
        player_scoring[pid]['bogeys']       += sr['bogeys'] or 0
        player_scoring[pid]['doubles_plus'] += sr['doubles_plus'] or 0

    # ── 3. Merge into result rows ───────────────────────────────────────────
    result = []
    for r in mr_rows:
        pid  = r['player_id']
        ps   = player_scoring[pid]
        rds  = ps['rounds']
        rp   = r['rounds_played'] or 0
        tp   = r['total_points'] or 0.0
        result.append({
            'player_id':    pid,
            'player_name':  r['player_name'],
            'first_name':   r['first_name'],
            'last_name':    r['last_name'],
            'team_id':      r['team_id'],
            'team_name':    r['team_name'],
            'role':         r['role'] or '',
            'rounds_played': rp,
            'total_points': tp,
            'pts_per_round': round(tp / rp, 2) if rp > 0 else 0.0,
            'wins':         r['wins'] or 0,
            'ties':         r['ties'] or 0,
            'losses':       r['losses'] or 0,
            'scoring_avg':  round(sum(rds) / len(rds), 1) if rds else None,
            'best_round':   min(rds) if rds else None,
            'eagles':       ps['eagles'],
            'birdies':      ps['birdies'],
            'pars':         ps['pars'],
            'bogeys':       ps['bogeys'],
            'doubles_plus': ps['doubles_plus'],
        })

    # Already sorted by total_points DESC from SQL
    # Add rank (handle ties)
    rank = 1
    for i, row in enumerate(result):
        if i > 0 and row['total_points'] != result[i-1]['total_points']:
            rank = i + 1
        row['rank'] = rank

    has_divisions = db.execute(
        'SELECT 1 FROM teams WHERE season_id=%s AND league_id=%s AND division_name IS NOT NULL LIMIT 1',
        (season_id, league_id)
    ).fetchone() is not None

    return render_template('standings/individual.html',
                           season=season, seasons=seasons,
                           result=result,
                           has_divisions=has_divisions)


# ---------------------------------------------------------------------------
# Points Trend (cumulative team pts by week)
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/trend')
@login_required
def trend(season_id):
    db        = get_db()
    league_id = session['league_id']
    season    = _get_season(db, season_id, league_id)
    if not season:
        return redirect(url_for('standings.current'))
    seasons = _all_seasons(db, league_id)

    # All teams for this season
    team_rows = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY t.team_id""",
        (season_id, league_id)
    ).fetchall()

    # All completed weeks in order
    week_rows = db.execute(
        """SELECT DISTINCT week_number, scheduled_date
           FROM matchups
           WHERE season_id = %s AND status = 'completed' AND is_bye = 0
           ORDER BY week_number""",
        (season_id,)
    ).fetchall()
    weeks = [dict(w) for w in week_rows]

    if not weeks:
        return render_template('standings/trend.html',
            season=dict(season), seasons=seasons,
            chart_data=[], weeks=[], has_divisions=False)

    # Points per team per week (not cumulative yet)
    pts_rows = db.execute(
        """SELECT m.week_number, mr.team_id, SUM(mr.total_points) AS wk_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           GROUP BY m.week_number, mr.team_id""",
        (season_id,)
    ).fetchall()

    # Build lookup: (week_number, team_id) -> pts
    wk_team_pts = {}
    for r in pts_rows:
        wk_team_pts[(r['week_number'], r['team_id'])] = r['wk_pts'] or 0

    # Assign colors deterministically
    palette = [
        '#2ecc71', '#3498db', '#e74c3c', '#f39c12', '#9b59b6',
        '#1abc9c', '#e67e22', '#34495e', '#e91e63', '#00bcd4',
        '#8bc34a', '#ff5722', '#607d8b', '#795548', '#673ab7',
    ]

    chart_data = []
    week_numbers = [w['week_number'] for w in weeks]

    for idx, tr in enumerate(team_rows):
        tid   = tr['team_id']
        color = palette[idx % len(palette)]
        cumulative = 0
        pts_by_week = []
        for wn in week_numbers:
            cumulative += wk_team_pts.get((wn, tid), 0)
            pts_by_week.append(round(cumulative, 1))
        chart_data.append({
            'team_id':   tid,
            'team_name': tr['team_name'],
            'color':     color,
            'points':    pts_by_week,
            'final_pts': pts_by_week[-1] if pts_by_week else 0,
        })

    # Sort by final points descending for legend
    chart_data.sort(key=lambda x: x['final_pts'], reverse=True)

    has_divisions = db.execute(
        'SELECT 1 FROM teams WHERE season_id=%s AND league_id=%s AND division_name IS NOT NULL LIMIT 1',
        (season_id, league_id)
    ).fetchone() is not None

    return render_template('standings/trend.html',
        season=dict(season), seasons=seasons,
        chart_data=chart_data,
        weeks=weeks,
        has_divisions=has_divisions)


@bp.route('/trend')
@login_required
def trend_current():
    db = get_db()
    season_id = get_current_season_id(db, session['league_id'])
    if not season_id:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('standings.trend', season_id=season_id))


# ══════════════════════════════════════════════════════════════
#  SEASON AWARDS
# ══════════════════════════════════════════════════════════════
@bp.route('/<int:season_id>/awards')
@login_required
def awards(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        'SELECT * FROM seasons WHERE season_id=%s AND league_id=%s',
        (season_id, league_id)
    ).fetchone()
    if not season:
        return redirect(url_for('main.dashboard'))

    seasons = db.execute(
        'SELECT season_id, season_name FROM seasons WHERE league_id=%s ORDER BY season_id DESC',
        (league_id,)
    ).fetchall()

    has_divisions = db.execute(
        'SELECT 1 FROM teams WHERE season_id=%s AND league_id=%s AND division_name IS NOT NULL LIMIT 1',
        (season_id, league_id)
    ).fetchone() is not None

    # ── Helper: player name lookup (team name with fallback) ────
    player_names = {}
    for row in db.execute(
        '''SELECT p.player_id, p.first_name, p.last_name,
                  COALESCE(NULLIF(t.team_name, ''),
                           p.last_name || ' & ' || p2.last_name) AS display_name
           FROM players p
           LEFT JOIN teams t ON t.league_id = p.league_id
               AND (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           LEFT JOIN players p2 ON p2.player_id = CASE
               WHEN t.player1_id = p.player_id THEN t.player2_id
               ELSE t.player1_id END
           WHERE p.league_id=%s''',
        (league_id,)
    ):
        player_names[row['player_id']] = row['display_name'] or f"{row['first_name']} {row['last_name']}"

    # ── Points Leader ───────────────────────────────────────────
    pts_rows = db.execute('''
        SELECT mr.player_id, SUM(mr.total_points) AS pts, COUNT(DISTINCT mr.matchup_id) AS rounds
        FROM match_results mr
        JOIN matchups m ON mr.matchup_id = m.matchup_id
        WHERE m.season_id=%s
        GROUP BY mr.player_id
        ORDER BY pts DESC LIMIT 5
    ''', (season_id,)).fetchall()
    points_leaders = [{'player_id': r['player_id'],
                        'name': player_names.get(r['player_id'], '?'),
                        'value': round(r['pts'], 1),
                        'sub': f"{r['rounds']} rounds"} for r in pts_rows]

    # ── Eagle Eye ───────────────────────────────────────────────
    eagle_rows = db.execute('''
        SELECT sc.player_id, COUNT(*) AS cnt
        FROM hole_scores hs
        JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
        JOIN rounds r ON sc.round_id = r.round_id
        JOIN matchups m ON r.matchup_id = m.matchup_id
        WHERE m.season_id=%s AND sc.is_sub=0 AND sc.is_absent=0
          AND hs.score_differential <= -2
        GROUP BY sc.player_id
        ORDER BY cnt DESC LIMIT 5
    ''', (season_id,)).fetchall()
    eagle_leaders = [{'player_id': r['player_id'],
                       'name': player_names.get(r['player_id'], '?'),
                       'value': r['cnt'],
                       'sub': 'eagle' + ('s' if r['cnt'] != 1 else '')} for r in eagle_rows]

    # ── Birdie Machine ──────────────────────────────────────────
    birdie_rows = db.execute('''
        SELECT sc.player_id, COUNT(*) AS cnt
        FROM hole_scores hs
        JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
        JOIN rounds r ON sc.round_id = r.round_id
        JOIN matchups m ON r.matchup_id = m.matchup_id
        WHERE m.season_id=%s AND sc.is_sub=0 AND sc.is_absent=0
          AND hs.score_differential = -1
        GROUP BY sc.player_id
        ORDER BY cnt DESC LIMIT 5
    ''', (season_id,)).fetchall()
    birdie_leaders = [{'player_id': r['player_id'],
                        'name': player_names.get(r['player_id'], '?'),
                        'value': r['cnt'],
                        'sub': 'birdie' + ('s' if r['cnt'] != 1 else '')} for r in birdie_rows]

    # ── Low Round ───────────────────────────────────────────────
    low_round_rows = db.execute('''
        SELECT sc.player_id, sc.scorecard_id, SUM(hs.gross_score) AS gross,
               COUNT(hs.hole_score_id) AS holes, m.week_number,
               r.round_date
        FROM scorecards sc
        JOIN hole_scores hs ON sc.scorecard_id = hs.scorecard_id
        JOIN rounds r ON sc.round_id = r.round_id
        JOIN matchups m ON r.matchup_id = m.matchup_id
        WHERE m.season_id=%s AND sc.is_sub=0 AND sc.is_absent=0
        GROUP BY sc.scorecard_id
        HAVING COUNT(hs.hole_score_id) >= 9
        ORDER BY gross ASC LIMIT 5
    ''', (season_id,)).fetchall()
    low_round_leaders = [{'player_id': r['player_id'],
                           'name': player_names.get(r['player_id'], '?'),
                           'value': r['gross'],
                           'sub': f"Wk {r['week_number']}" + (f" · {r['round_date'][:10]}" if r['round_date'] else '')} for r in low_round_rows]

    # ── Best Record (W-T-L) ─────────────────────────────────────
    record_rows = db.execute('''
        SELECT mr.player_id,
               SUM(CASE WHEN mr.overall_point_won = 1.0 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN mr.overall_point_won = 0.5 THEN 1 ELSE 0 END) AS ties,
               SUM(CASE WHEN mr.overall_point_won = 0.0 THEN 1 ELSE 0 END) AS losses,
               COUNT(*) AS played
        FROM match_results mr
        JOIN matchups m ON mr.matchup_id = m.matchup_id
        WHERE m.season_id=%s
        GROUP BY mr.player_id
        HAVING played >= 3
        ORDER BY wins DESC, ties DESC, losses ASC LIMIT 5
    ''', (season_id,)).fetchall()
    record_leaders = [{'player_id': r['player_id'],
                        'name': player_names.get(r['player_id'], '?'),
                        'value': f"{r['wins']}–{r['ties']}–{r['losses']}",
                        'sub': f"{r['played']} rounds"} for r in record_rows]

    # ── Hot Streak (longest consecutive match wins) ─────────────
    # Fetch all results ordered by week_number per player
    streak_data = db.execute('''
        SELECT mr.player_id, m.week_number, mr.overall_point_won
        FROM match_results mr
        JOIN matchups m ON mr.matchup_id = m.matchup_id
        WHERE m.season_id=%s
        ORDER BY mr.player_id, m.week_number
    ''', (season_id,)).fetchall()

    from collections import defaultdict
    player_results = defaultdict(list)
    for r in streak_data:
        player_results[r['player_id']].append(r['overall_point_won'])

    streak_leaders_raw = []
    for pid, results in player_results.items():
        max_streak = 0
        cur_streak = 0
        for won in results:
            if won == 1.0:
                cur_streak += 1
                max_streak = max(max_streak, cur_streak)
            else:
                cur_streak = 0
        if max_streak >= 2:
            streak_leaders_raw.append({'player_id': pid, 'streak': max_streak})

    streak_leaders_raw.sort(key=lambda x: x['streak'], reverse=True)
    streak_leaders = [{'player_id': r['player_id'],
                        'name': player_names.get(r['player_id'], '?'),
                        'value': r['streak'],
                        'sub': 'consecutive win' + ('s' if r['streak'] != 1 else '')} for r in streak_leaders_raw[:5]]

    # ── Most Improved Handicap ──────────────────────────────────
    # Compare first vs last handicap_at_time_of_play in this season
    all_sc = db.execute('''
        SELECT sc.player_id, sc.handicap_at_time_of_play, m.week_number
        FROM scorecards sc
        JOIN rounds r ON sc.round_id = r.round_id
        JOIN matchups m ON r.matchup_id = m.matchup_id
        WHERE m.season_id=%s AND sc.is_sub=0
        ORDER BY sc.player_id, m.week_number
    ''', (season_id,)).fetchall()

    player_hcp_history = defaultdict(list)
    for r in all_sc:
        if r['handicap_at_time_of_play'] is not None:
            player_hcp_history[r['player_id']].append(r['handicap_at_time_of_play'])

    improved_raw = []
    for pid, hcps in player_hcp_history.items():
        if len(hcps) >= 3:
            improvement = hcps[0] - hcps[-1]
            if improvement > 0:
                improved_raw.append({'player_id': pid, 'improvement': round(improvement, 1),
                                     'start': hcps[0], 'end': hcps[-1]})
    improved_raw.sort(key=lambda x: x['improvement'], reverse=True)
    improved_leaders = [{'player_id': r['player_id'],
                          'name': player_names.get(r['player_id'], '?'),
                          'value': f"–{r['improvement']}",
                          'sub': f"{r['start']} → {r['end']}"} for r in improved_raw[:5]]

    awards = [
        {'key': 'points',   'emoji': '🏆', 'title': 'Points Leader',        'desc': 'Most total match points earned this season', 'leaders': points_leaders,  'unit': 'pts'},
        {'key': 'birdie',   'emoji': '🐦', 'title': 'Birdie Machine',        'desc': 'Most birdies recorded this season',           'leaders': birdie_leaders,  'unit': ''},
        {'key': 'eagle',    'emoji': '🦅', 'title': 'Eagle Eye',             'desc': 'Most eagles (or better) this season',         'leaders': eagle_leaders,   'unit': ''},
        {'key': 'record',   'emoji': '💪', 'title': 'Best Match Record',     'desc': 'Best W–T–L record (min 3 rounds)',            'leaders': record_leaders,  'unit': ''},
        {'key': 'low',      'emoji': '⛳', 'title': 'Low Round',             'desc': 'Lowest single gross score in a round',        'leaders': low_round_leaders,'unit': ''},
        {'key': 'streak',   'emoji': '🔥', 'title': 'Hot Streak',            'desc': 'Longest consecutive match win streak',        'leaders': streak_leaders,  'unit': ''},
        {'key': 'improved', 'emoji': '📈', 'title': 'Most Improved',         'desc': 'Biggest handicap index drop this season',     'leaders': improved_leaders, 'unit': ''},
    ]

    return render_template('standings/awards.html',
        season=dict(season),
        seasons=seasons,
        has_divisions=has_divisions,
        awards=awards,
        player_names=player_names,
    )


# ---------------------------------------------------------------------------
# Playoff Picture  /standings/<season_id>/playoff-picture
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/playoff-picture')
@login_required
def playoff_picture(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    seasons = _all_seasons(db, league_id)

    # ── League settings: playoff_teams ─────────────────────────
    settings_row = db.execute(
        "SELECT * FROM league_settings WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    try:
        playoff_teams_count = int(settings_row['playoff_teams']) if settings_row else 4
    except Exception:
        playoff_teams_count = 4

    # ── Team points + schedule counts ──────────────────────────
    team_rows = db.execute("""
        SELECT t.team_id, t.team_name,
               p1.last_name AS p1_last, p2.last_name AS p2_last,
               COALESCE(SUM(mr.total_points), 0.0) AS season_pts,
               COUNT(DISTINCT CASE WHEN m.status='completed' AND m.is_bye=0
                                   THEN m.matchup_id END) AS rounds_played,
               COUNT(DISTINCT CASE WHEN m.is_bye=0
                                   THEN m.matchup_id END) AS total_rounds
        FROM teams t
        LEFT JOIN players p1 ON p1.player_id = t.player1_id
        LEFT JOIN players p2 ON p2.player_id = t.player2_id
        LEFT JOIN matchups m
               ON (m.team1_id=t.team_id OR m.team2_id=t.team_id)
              AND m.season_id = t.season_id
        LEFT JOIN match_results mr
               ON mr.team_id=t.team_id AND mr.matchup_id=m.matchup_id
              AND m.is_bye=0
        WHERE t.season_id=%s AND t.league_id=%s
        GROUP BY t.team_id
        ORDER BY season_pts DESC, t.team_id
    """, (season_id, league_id)).fetchall()

    # ── Max points available per matchup (empirical) ───────────
    max_pts_row = db.execute("""
        SELECT MAX(matchup_total) AS mx FROM (
            SELECT mr.matchup_id, SUM(mr.total_points) AS matchup_total
            FROM match_results mr
            JOIN matchups m ON mr.matchup_id = m.matchup_id
            WHERE m.season_id=%s AND m.is_bye=0
            GROUP BY mr.matchup_id
        )
    """, (season_id,)).fetchone()
    max_pts_per_round = float(max_pts_row['mx']) if max_pts_row and max_pts_row['mx'] else 20.0

    # ── Build team data ─────────────────────────────────────────
    teams_data = []
    for t in team_rows:
        label = t['team_name'] or f"{t['p1_last'] or '?'} / {t['p2_last'] or '?'}"
        remaining = int(t['total_rounds']) - int(t['rounds_played'])
        max_possible = float(t['season_pts']) + remaining * max_pts_per_round
        teams_data.append({
            'team_id':      t['team_id'],
            'label':        label,
            'season_pts':   float(t['season_pts']),
            'rounds_played':int(t['rounds_played']),
            'total_rounds': int(t['total_rounds']),
            'remaining':    remaining,
            'max_possible': max_possible,
            'status':       None,  # filled below
            'pts_behind_leader': None,
            'pts_to_cutline': None,
            'clinch_number': None,
        })

    # ── Sort by pts descending ──────────────────────────────────
    teams_data.sort(key=lambda x: (-x['season_pts'], x['team_id']))
    for i, t in enumerate(teams_data):
        t['rank'] = i + 1

    leader_pts = teams_data[0]['season_pts'] if teams_data else 0.0
    num_teams   = len(teams_data)

    # Cutline = points of the last team in a playoff spot (index playoff_teams_count - 1)
    if num_teams >= playoff_teams_count:
        cutline_pts = teams_data[playoff_teams_count - 1]['season_pts']
    elif num_teams > 0:
        cutline_pts = teams_data[-1]['season_pts']
    else:
        cutline_pts = 0.0

    season_complete = all(t['remaining'] == 0 for t in teams_data)

    for i, t in enumerate(teams_data):
        t['pts_behind_leader'] = round(leader_pts - t['season_pts'], 1)
        pts_to_cutline = cutline_pts - t['season_pts']
        t['pts_to_cutline'] = round(pts_to_cutline, 1)  # negative = above cutline

        if season_complete:
            # Season over — just show final positions
            if i < playoff_teams_count:
                t['status'] = 'clinched'
            else:
                t['status'] = 'eliminated'
        elif i < playoff_teams_count:
            # Currently in a spot — check if clinched (no team outside can catch them)
            # Clinched if max_possible of the first team outside < this team's pts
            if num_teams > playoff_teams_count:
                challenger_max = max(
                    x['max_possible'] for x in teams_data[playoff_teams_count:]
                )
                t['status'] = 'clinched' if challenger_max < t['season_pts'] else 'alive'
            else:
                # Fewer teams than playoff spots: everyone clinches
                t['status'] = 'clinched'
        else:
            # Currently outside — eliminated if max_possible < cutline_pts
            t['status'] = 'eliminated' if t['max_possible'] < cutline_pts else 'alive'

        # Clinch number: pts needed for this team to guarantee a playoff spot
        # = pts such that even if teams below win everything, they can't pass
        if t['status'] == 'alive' and i < playoff_teams_count:
            # How many more pts does the (playoff_teams+1)th team need to tie?
            if num_teams > playoff_teams_count:
                best_challenger = max(
                    x['season_pts'] for x in teams_data[playoff_teams_count:]
                )
                # We need current_pts + X > best_challenger + challenger_remaining * max_per_round
                # X = best_challenger's max - current_pts + 1
                needed = best_challenger + (
                    max(x['remaining'] for x in teams_data[playoff_teams_count:])
                ) * max_pts_per_round - t['season_pts'] + 1
                t['clinch_number'] = max(0, round(needed, 1))
            else:
                t['clinch_number'] = None
        elif t['status'] == 'alive' and i >= playoff_teams_count:
            # How many pts needed to reach current cutline
            t['clinch_number'] = max(0, round(pts_to_cutline + 0.5, 1))

    has_divisions = False
    try:
        if table_exists(db, 'divisions'):
            div_count = db.execute(
                "SELECT COUNT(DISTINCT division_id) FROM team_divisions WHERE season_id=%s AND league_id=%s",
                (season_id, league_id)
            ).fetchone()[0]
            has_divisions = div_count > 1
    except Exception:
        pass

    return render_template('standings/playoff_picture.html',
        season=season, seasons=seasons,
        teams_data=teams_data,
        playoff_teams_count=playoff_teams_count,
        cutline_pts=cutline_pts,
        leader_pts=leader_pts,
        max_pts_per_round=max_pts_per_round,
        num_teams=num_teams,
        season_complete=season_complete,
        has_divisions=has_divisions,
    )


# ---------------------------------------------------------------------------
# A/B Flight Standings
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/flight')
@login_required
def flight_standings(season_id):
    """Separate A-flight and B-flight player leaderboards for the season."""
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    seasons = _all_seasons(db, league_id)

    # --- Per-player match results this season ---
    mr_rows = db.execute(
        """SELECT mr.player_id, mr.role, mr.total_points, mr.hole_points_won,
                  mr.overall_point_won,
                  m.matchup_id, m.week_number,
                  p.first_name, p.last_name,
                  t.team_id, t.team_name,
                  t.player1_id, t.player2_id
           FROM match_results mr
           JOIN matchups m  ON mr.matchup_id = m.matchup_id
           JOIN players p   ON mr.player_id  = p.player_id
           JOIN teams t     ON mr.team_id    = t.team_id
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    # --- Per-player gross scores this season ---
    gross_rows = db.execute(
        """SELECT sc.player_id, SUM(hs.gross_score) AS gross_total
           FROM hole_scores hs
           JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
           JOIN rounds r      ON sc.round_id = r.round_id
           JOIN matchups m    ON r.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.is_bye = 0 AND sc.is_sub = 0 AND sc.is_absent = 0
           GROUP BY sc.scorecard_id""",
        (season_id,)
    ).fetchall()

    # Build per-player gross list for avg/best
    player_grosses = {}
    for row in gross_rows:
        pid = row['player_id']
        if pid not in player_grosses:
            player_grosses[pid] = []
        player_grosses[pid].append(row['gross_total'])

    # Aggregate match results per player
    player_data = {}
    for row in mr_rows:
        pid  = row['player_id']
        role = row['role'] or ''  # 'A' or 'B'
        if pid not in player_data:
            t_label = row['team_name'] or ''
            if not t_label:
                # derive from team player names via a quick lookup
                t_label = ''
            player_data[pid] = {
                'player_id':   pid,
                'first_name':  row['first_name'],
                'last_name':   row['last_name'],
                'team_id':     row['team_id'],
                'team_label':  row['team_name'] or '',
                'role':        role,
                'pts':         0.0,
                'rounds':      0,
                'wins':        0,
                'ties':        0,
                'losses':      0,
                'hole_pts':    0.0,
                'week_pts':    {},   # week_number -> pts
            }
        pd = player_data[pid]
        pd['pts']       += float(row['total_points'] or 0)
        pd['hole_pts']  += float(row['hole_points_won'] or 0)
        pd['rounds']    += 1
        wk = row['week_number']
        pd['week_pts'][wk] = pd['week_pts'].get(wk, 0) + float(row['total_points'] or 0)
        owp = float(row['overall_point_won'] or 0)
        if owp >= 0.9:
            pd['wins'] += 1
        elif owp >= 0.4:
            pd['ties'] += 1
        else:
            pd['losses'] += 1
        # keep role from most-common appearance
        if role:
            pd['role'] = role

    # Attach current handicap + gross stats
    for pid, pd in player_data.items():
        pd['handicap'], pd['handicap_provisional'] = _get_player_handicap(db, pid, league_id)
        gl = player_grosses.get(pid, [])
        pd['avg_gross']  = round(sum(gl) / len(gl), 1) if gl else None
        pd['best_gross'] = min(gl) if gl else None
        pd['pts_per_round'] = round(pd['pts'] / pd['rounds'], 2) if pd['rounds'] else 0

    # Build team label map (fallback for teams without a nickname)
    team_rows = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.last_name AS p1_last, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s""",
        (season_id, league_id)
    ).fetchall()
    team_labels = {}
    for row in team_rows:
        team_labels[row['team_id']] = (
            row['team_name'] or
            '{} / {}'.format(row['p1_last'] or '?', row['p2_last'] or '?')
        )

    for pid, pd in player_data.items():
        if not pd['team_label']:
            pd['team_label'] = team_labels.get(pd['team_id'], 'Unknown')

    # Split into flights
    a_flight = sorted(
        [p for p in player_data.values() if p['role'] == 'A'],
        key=lambda x: (-x['pts'], -x['wins'], x['avg_gross'] or 999)
    )
    b_flight = sorted(
        [p for p in player_data.values() if p['role'] == 'B'],
        key=lambda x: (-x['pts'], -x['wins'], x['avg_gross'] or 999)
    )

    # Assign ranks (tied players share rank)
    def _rank(lst):
        prev_pts = None
        prev_rank = 0
        for i, row in enumerate(lst):
            if row['pts'] != prev_pts:
                prev_rank = i + 1
                prev_pts = row['pts']
            row['rank'] = prev_rank
        return lst

    a_flight = _rank(a_flight)
    b_flight = _rank(b_flight)

    # Weekly pts for sparklines (list of pts per week in order)
    completed_weeks = sorted({row['week_number'] for row in mr_rows})
    for pd in list(a_flight) + list(b_flight):
        pd['sparkline'] = [pd['week_pts'].get(wk, 0) for wk in completed_weeks]

    # Flight leaders
    a_leader = a_flight[0] if a_flight else None
    b_leader = b_flight[0] if b_flight else None

    return render_template(
        'standings/flight_standings.html',
        season=season,
        seasons=seasons,
        a_flight=a_flight,
        b_flight=b_flight,
        a_leader=a_leader,
        b_leader=b_leader,
        completed_weeks=completed_weeks,
    )


# ---------------------------------------------------------------------------
# Podium graphic
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/podium')
@login_required
def podium(season_id):
    """Shareable podium graphic showing top 3 teams. ?share=1 strips nav for screenshot."""
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    league = db.execute(
        'SELECT league_name FROM leagues WHERE league_id = %s', (league_id,)
    ).fetchone()

    rows = _standings_rows(db, season_id, league_id)
    tb = _get_tiebreaker_settings(db, season_id, league_id)
    rows = _apply_tiebreakers(db, rows, season_id, tb)

    # Build ranked list with W-L-T records
    ranked = []
    prev_pts, pos = None, 0
    for i, r in enumerate(rows):
        if r['total_pts'] != prev_pts:
            pos = i + 1
            prev_pts = r['total_pts']

        # Fetch W-L-T for this team
        wlt = db.execute(
            """SELECT
                 SUM(CASE WHEN mr.overall_point_won >= 1.0 THEN 1 ELSE 0 END) AS wins,
                 SUM(CASE WHEN mr.overall_point_won  = 0.0 THEN 1 ELSE 0 END) AS losses,
                 SUM(CASE WHEN mr.overall_point_won  > 0.0
                           AND mr.overall_point_won  < 1.0 THEN 1 ELSE 0 END) AS ties
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               WHERE mr.team_id = %s AND m.season_id = %s""",
            (r['team_id'], season_id)
        ).fetchone()

        name_parts = [n for n in [r['p1_last'], r['p2_last']] if n]
        team_label = r['nickname'] if r['nickname'] else ' / '.join(name_parts)

        ranked.append({
            'position': pos,
            'team_label': team_label,
            'total_pts': float(r['total_pts']),
            'wins':   wlt['wins']   if wlt else 0,
            'losses': wlt['losses'] if wlt else 0,
            'ties':   wlt['ties']   if wlt else 0,
        })

    podium_teams = ranked[:3]
    # Reorder for podium display: 2nd, 1st, 3rd
    if len(podium_teams) >= 3:
        display_order = [podium_teams[1], podium_teams[0], podium_teams[2]]
    elif len(podium_teams) == 2:
        display_order = [podium_teams[1], podium_teams[0]]
    else:
        display_order = podium_teams

    share_mode = request.args.get('share') == '1'

    return render_template(
        'standings/podium.html',
        season=season,
        league=league,
        display_order=display_order,
        podium_teams=podium_teams,
        share_mode=share_mode,
    )
