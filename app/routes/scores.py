from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db, table_exists
from routes.auth import login_required, admin_required
from datetime import datetime
import math
from routes.handicap import rebuild_league_handicaps_and_scores, PRE_ELIGIBILITY_MARKER_PREFIX
from routes.notifications import create_league_event

bp = Blueprint('scores', __name__, url_prefix='/scores')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_player_handicap(db, player_id, league_id=None):
    """Return player handicap index + any active committee adjustment."""
    row = db.execute(
        "SELECT handicap_index FROM handicap_history WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1",
        (player_id,)
    ).fetchone()
    if row:
        base = row['handicap_index']
    else:
        row2 = db.execute("SELECT starting_handicap FROM players WHERE player_id = %s", (player_id,)).fetchone()
        base = (row2['starting_handicap'] or 0) if row2 else 0

    # Add committee adjustment if present (graceful if table not yet migrated)
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
    return base + adjustment


def calc_playing_handicap(handicap_index, handicap_percent, max_handicap):
    ph = int(round(handicap_index * (handicap_percent / 100)))
    return min(ph, max_handicap)


def strokes_on_hole(playing_handicap, hole_hcp_index, total_holes=9, hcp_indices=None):
    """Return strokes received on one hole.

    hole_hcp_index is used as a difficulty rank (1 = hardest).  For 9-hole rounds
    taken from an 18-hole layout the raw DB handicap_index values are non-consecutive
    (e.g. 1,3,5,… or 2,4,6,…), so callers must pass hcp_indices (the full list of
    handicap_index values for the holes being played) so this function can compute the
    correct rank instead of treating the raw value as a rank.
    """
    if hole_hcp_index is None:
        return 0
    ph = playing_handicap
    if hcp_indices is not None:
        sorted_idx = sorted(h for h in hcp_indices if h is not None)
        n = len(sorted_idx)
        try:
            rank = sorted_idx.index(hole_hcp_index) + 1
        except ValueError:
            rank = hole_hcp_index
    else:
        rank = hole_hcp_index
        n = total_holes
    strokes = 0
    if ph >= rank:
        strokes += 1
    if ph >= n + rank:
        strokes += 1
    return strokes


def calc_match_play(score_a, score_b):
    if score_a < score_b:
        return 2.0, 0.0
    elif score_b < score_a:
        return 0.0, 2.0
    else:
        return 1.0, 1.0


def diff_match_hole_points(gross_x, gross_y, holes_x, ph_x, ph_y, net_x, net_y):
    """Match-play points for one pair — hole-by-hole and overall use different bases.

    Hole-by-hole win/loss/tie: differential stroke allocation — only the
    higher-handicap player receives strokes, equal to the handicap gap
    between the two players, allocated to the hardest holes by
    handicap_index rank (same convention as real singles match play).

    Overall point: absolute net comparison — each player's own net_x/net_y
    (i.e. hole_scores.net_score: gross minus strokes from their OWN full
    playing handicap against par), summed and compared. This intentionally
    does NOT use the differential — the overall point is a stroke-play-
    style "who shot the better net round" comparison, independent of who
    the opponent happens to be.

    gross_x/gross_y: per-hole gross score lists (None = not yet entered).
    holes_x: hole rows (par/handicap_index) aligned to gross_x/gross_y by index.
    ph_x/ph_y: playing handicaps for the two players (drives hole points).
    net_x/net_y: each player's own absolute per-hole net list (drives overall).
    """
    n = len(holes_x)
    hcp_idxs = [h['handicap_index'] for h in holes_x]
    diff_x = ph_x - ph_y
    diff_y = ph_y - ph_x
    hole_pts_x, hole_pts_y = 0.0, 0.0
    for i, h in enumerate(holes_x):
        gx = gross_x[i] if i < len(gross_x) else None
        gy = gross_y[i] if i < len(gross_y) else None
        if gx is None or gy is None:
            continue
        sx = strokes_on_hole(diff_x, h['handicap_index'], total_holes=n, hcp_indices=hcp_idxs) if diff_x > 0 else 0
        sy = strokes_on_hole(diff_y, h['handicap_index'], total_holes=n, hcp_indices=hcp_idxs) if diff_y > 0 else 0
        dnx, dny = gx - sx, gy - sy
        px, py = calc_match_play(dnx, dny)
        hole_pts_x += px
        hole_pts_y += py

    net_x_valid = [v for v in net_x if v is not None]
    net_y_valid = [v for v in net_y if v is not None]
    if net_x_valid and net_y_valid:
        overall_x, overall_y = calc_match_play(sum(net_x_valid), sum(net_y_valid))
    else:
        overall_x, overall_y = 0, 0
    return hole_pts_x, hole_pts_y, overall_x, overall_y


def calc_stableford(net_vs_par):
    """Stableford points for a hole given net score minus par."""
    if net_vs_par <= -2:
        return 4   # Eagle or better
    elif net_vs_par == -1:
        return 3   # Birdie
    elif net_vs_par == 0:
        return 2   # Par
    elif net_vs_par == 1:
        return 1   # Bogey
    else:
        return 0   # Double bogey or worse

def get_league_settings(db, season_id, league_id):
    row = db.execute(
        "SELECT * FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    return row


def _settings_scoring_mode(settings):
    """Return scoring mode string from a league_settings row.
    Column is 'scoring_type' in the DB; fallback to 'match_play'."""
    if not settings:
        return 'match_play'
    try:
        return settings['scoring_type'] or 'match_play'
    except (ValueError, KeyError, IndexError):
        return 'match_play'


def _settings_absence_policy(settings):
    """Return the league's absence overall-point policy.

    'always'        - an absent player's ghost score can win the overall point
    'never'         - any absence forfeits the overall point to the opponent
    'excused_only'  - only unexcused absences forfeit (legacy/default behavior)

    Falls back to 'excused_only' if unset or the column doesn't exist yet
    (e.g. migration not yet applied against this DB).
    """
    if not settings:
        return 'excused_only'
    try:
        return settings['absence_overall_point_policy'] or 'excused_only'
    except (ValueError, KeyError, IndexError):
        return 'excused_only'


def _apply_absence_overall_policy(result, pid_x, pid_y, absent_map, policy):
    """Apply the league's absence overall-point policy to a match result.

    absent_map: pid -> excused (1) / unexcused (0), present only for absent players.
    Mirrors the elif precedence of the original hardcoded logic (pid_x checked first).
    """
    hx, hy, ox, oy = result
    if policy == 'always':
        return hx, hy, ox, oy
    x_absent = pid_x in absent_map
    y_absent = pid_y in absent_map
    if policy == 'never':
        if x_absent:
            return hx, hy, 0, 1
        if y_absent:
            return hx, hy, 1, 0
        return hx, hy, ox, oy
    # excused_only
    if x_absent and not absent_map[pid_x]:
        return hx, hy, 0, 1
    if y_absent and not absent_map[pid_y]:
        return hx, hy, 1, 0
    return hx, hy, ox, oy


def _get_sub_assignments(db, matchup_id):
    """
    Return dict: regular_player_id -> sub_player info dict.
    Checks matchup-linked (pre-round) absences that have a sub_player_id.
    """
    result = {}
    try:
        rows = db.execute(
            "SELECT * FROM player_absences WHERE matchup_id = %s AND sub_player_id IS NOT NULL",
            (matchup_id,)
        ).fetchall()
        for r in rows:
            if r['sub_player_id']:
                sub = db.execute(
                    "SELECT player_id, first_name, last_name FROM players WHERE player_id = %s",
                    (r['sub_player_id'],)
                ).fetchone()
                if sub:
                    orig = db.execute(
                        "SELECT first_name, last_name FROM players WHERE player_id = %s",
                        (r['player_id'],)
                    ).fetchone()
                    result[r['player_id']] = {
                        'sub_player_id': r['sub_player_id'],
                        'sub_first':     sub['first_name'],
                        'sub_last':      sub['last_name'],
                        'orig_first':    orig['first_name'] if orig else '',
                        'orig_last':     orig['last_name']  if orig else '',
                        'reason':        r['reason'] or '',
                        'excused':       r['excused'],
                        'absence_id':    r['absence_id'],
                    }
    except Exception:
        pass
    return result


def _get_all_absence_records(db, matchup_id):
    """
    Return dict: player_id -> full absence record (including players with no sub).
    Used to pre-populate the inline absence form.
    """
    result = {}
    try:
        rows = db.execute(
            "SELECT * FROM player_absences WHERE matchup_id = %s",
            (matchup_id,)
        ).fetchall()
        for r in rows:
            result[r['player_id']] = {
                'absence_id':    r['absence_id'],
                'sub_player_id': r['sub_player_id'],
                'reason':        r['reason'] or '',
                'excused':       r['excused'] or 0,
            }
    except Exception:
        pass
    return result



def _get_nickname_map(db, player_ids):
    """Return dict: player_id -> primary nickname (str or None). Graceful if table absent."""
    if not player_ids:
        return {}
    try:
        if not table_exists(db, 'player_nicknames'):
            return {pid: None for pid in player_ids}
        placeholders = ','.join(['%s'] * len(player_ids))
        rows = db.execute(
            f"SELECT player_id, nickname FROM player_nicknames WHERE player_id IN ({placeholders}) AND is_primary=1",
            list(player_ids)
        ).fetchall()
        result = {pid: None for pid in player_ids}
        for r in rows:
            result[r['player_id']] = r['nickname']
        return result
    except Exception:
        return {pid: None for pid in player_ids}


def _detect_eligibility_rounds(db, player_ids, league_id, min_rounds):
    """Return {pid: rounds_so_far} for players whose next round is their handicap-eligibility round.

    A player qualifies when they have exactly (min_rounds - 1) completed non-absent
    rounds and no handicap_history row yet — meaning completing this round would be
    the one that makes them handicap-eligible.
    """
    if not player_ids or min_rounds <= 0:
        return {}
    placeholders = ','.join(['%s'] * len(player_ids))
    rc_rows = db.execute(
        f"""SELECT sc.player_id, COUNT(*) AS cnt
              FROM scorecards sc
              JOIN rounds   r ON sc.round_id    = r.round_id
              JOIN matchups m ON r.matchup_id   = m.matchup_id
              JOIN seasons  s ON m.season_id    = s.season_id
             WHERE sc.player_id IN ({placeholders})
               AND s.league_id  = %s
               AND sc.is_absent = 0
               AND m.status     = 'completed'
             GROUP BY sc.player_id""",
        list(player_ids) + [league_id]
    ).fetchall()
    round_counts = {r['player_id']: r['cnt'] for r in rc_rows}

    # Exclude provisional pre-eligibility rows — otherwise a player would
    # look "already has a handicap" the moment their first temp row is
    # written, and this eligibility indicator would never fire again.
    hh_rows = db.execute(
        f"""SELECT DISTINCT player_id FROM handicap_history
             WHERE player_id IN ({placeholders})
               AND (is_manual_override = 1
                    OR override_reason IS NULL
                    OR override_reason NOT LIKE %s)""",
        list(player_ids) + [f'{PRE_ELIGIBILITY_MARKER_PREFIX}%']
    ).fetchall()
    has_hcp = {r['player_id'] for r in hh_rows}

    return {
        pid: round_counts.get(pid, 0)
        for pid in player_ids
        if pid not in has_hcp and round_counts.get(pid, 0) + 1 == min_rounds
    }

# ---------------------------------------------------------------------------
# Score entry
# ---------------------------------------------------------------------------

@bp.route('/enter/<int:matchup_id>', methods=['GET', 'POST'])
@admin_required
def enter(matchup_id):
    db = get_db()

    matchup = db.execute(
        """SELECT m.*, s.season_name, s.league_id, s.season_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = %s""",
        (matchup_id,)
    ).fetchone()

    if not matchup or matchup['league_id'] != session['league_id']:
        flash('Matchup not found.', 'error')
        return redirect(url_for('seasons.index'))

    if matchup['is_bye']:
        flash('Bye weeks do not have scores.', 'error')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

    # Completed matchups are allowed through — admins can clear and re-enter scores

    # Get teams + players
    team1 = db.execute(
        """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                       p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.team_id = %s""", (matchup['team1_id'],)
    ).fetchone()

    team2 = db.execute(
        """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                       p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.team_id = %s""", (matchup['team2_id'],)
    ).fetchone()

    if not team1 or not team2:
        flash('Teams not found for this matchup.', 'error')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

    # Available courses / tees
    courses = db.execute(
        "SELECT course_id, course_name FROM courses WHERE league_id = %s OR league_id IS NULL ORDER BY course_name",
        (session['league_id'],)
    ).fetchall()

    selected_course_id = (request.form.get('course_id') or
                          request.args.get('course_id') or
                          matchup['course_id'])
    selected_tee_id    = (request.form.get('tee_id') or
                          request.args.get('tee_id') or
                          matchup['tee_id'])

    tees = []
    player_tees = []   # deduplicated by color for the per-player tee dropdown
    holes = []
    all_tee_hcp = {}   # {tee_id: [hcp_index_per_hole, ...]} for JS live calc
    if selected_course_id:
        tees = db.execute(
            """SELECT tee_id, tee_name, tee_color, nine, gender, par_total, slope, rating
               FROM tees WHERE course_id = %s ORDER BY gender, tee_name, nine""",
            (int(selected_course_id),)
        ).fetchall()
        # Build nine_options: one entry per unique nine value (front/back/full)
        # Uses the first tee for that nine as the representative tee_id for loading holes
        nine_label_map = {'front': 'Front 9', 'back': 'Back 9', 'full': 'Full 18'}
        seen_nines = {}
        for t in tees:
            n = t['nine'] or 'full'
            if n not in seen_nines:
                seen_nines[n] = {'nine': n, 'label': nine_label_map.get(n, n.title()), 'tee_id': t['tee_id']}
            # Prefer the schedule-assigned tee as representative for its nine
            if selected_tee_id and str(t['tee_id']) == str(selected_tee_id):
                seen_nines[n]['tee_id'] = t['tee_id']
        nine_options = list(seen_nines.values())

        # Pre-load all tees' hole HCP data for per-player tee support
        for t in tees:
            th = db.execute(
                "SELECT hole_number, handicap_index FROM holes WHERE tee_id = %s ORDER BY hole_number",
                (t['tee_id'],)
            ).fetchall()
            all_tee_hcp[t['tee_id']] = [row['handicap_index'] for row in th]

        # Build player_tees: one entry per unique color for the selected nine.
        # Order: M tees first (preferred representative), then W-only tees.
        # This deduplicates the per-player tee dropdown by color.
        _sel_nine = None
        if selected_tee_id:
            _sel_tee_meta = next((t for t in tees if str(t['tee_id']) == str(selected_tee_id)), None)
            if _sel_tee_meta:
                _sel_nine = _sel_tee_meta['nine']
        _pt_seen_colors = {}  # color → representative tee row
        for t in tees:
            if _sel_nine and t['nine'] != _sel_nine:
                continue
            color = (t['tee_color'] or t['tee_name'] or '').strip()
            if not color:
                continue
            if color not in _pt_seen_colors:
                _pt_seen_colors[color] = dict(t)
            elif (t['gender'] or 'M').upper() == 'M' and (_pt_seen_colors[color]['gender'] or 'M').upper() != 'M':
                # Prefer M representative
                _pt_seen_colors[color] = dict(t)
        player_tees = list(_pt_seen_colors.values())

    if selected_tee_id:
        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (int(selected_tee_id),)
        ).fetchall()
        # P2-2: warn if any hole is missing a handicap index (breaks stroke allocation)
        null_hcp_holes = [h['hole_number'] for h in holes if h['handicap_index'] is None]
        if null_hcp_holes:
            flash(f"Tee is missing handicap index on hole(s) {', '.join(str(n) for n in null_hcp_holes)} — stroke allocation will be incorrect until course data is fixed.", 'warning')

    # All active players for sub dropdown (including subs)
    all_players = db.execute(
        """SELECT player_id, first_name, last_name, COALESCE(is_sub, FALSE) AS is_sub FROM players
           WHERE league_id = %s AND active = 1
           ORDER BY is_sub, last_name, first_name""",
        (session['league_id'],)
    ).fetchall()

    # Handle inline absence save (separate action from score submission)
    if request.method == 'POST' and request.form.get('action') == 'save_absences':
        _process_absences(db, matchup_id, team1, team2, request.form)
        # Fire sub_assigned notifications for any player with a sub set
        try:
            _sid = matchup['season_id']
            _lid = matchup['league_id']
            for team in [team1, team2]:
                for pk, spk in [('p1_id', 'p1_last'), ('p2_id', 'p2_last')]:
                    pid = team[pk]
                    if pid and request.form.get(f'absent_{pid}') == '1':
                        sub_pid = request.form.get(f'sub_{pid}', '').strip()
                        if sub_pid:
                            sub_row = db.execute(
                                "SELECT first_name, last_name FROM players WHERE player_id = %s",
                                (int(sub_pid),)
                            ).fetchone()
                            sub_name = f"{sub_row['first_name']} {sub_row['last_name']}" if sub_row else 'sub'
                            msg = f"Sub assigned: {sub_name} will sub for {team[spk]} (Week {matchup['week_number']})"
                            create_league_event(db, _lid, 'sub_assigned', msg, season_id=_sid, ref_id=matchup_id)
            db.commit()
        except Exception:
            pass
        return redirect(url_for('scores.enter', matchup_id=matchup_id,
                                course_id=selected_course_id or '',
                                tee_id=selected_tee_id or ''))

    if request.method == 'POST' and request.form.get('action') == 'submit_scores':
        return _process_scores(db, matchup, team1, team2, holes, request.form)

    # Load sub assignments and absence records for display
    sub_assignments  = _get_sub_assignments(db, matchup['matchup_id'])
    absence_records  = _get_all_absence_records(db, matchup['matchup_id'])

    # Collect player info with handicaps
    players = _build_player_list(db, matchup['season_id'], team1, team2, sub_assignments, league_id=session.get('league_id'))

    enter_scoring_mode = 'match_play'
    if holes:
        settings = get_league_settings(db, matchup['season_id'], session['league_id'])
        hpct = float(settings['handicap_percent']) if settings else 90.0
        hmax = float(settings['max_handicap_index']) if settings else 18.0
        enter_scoring_mode = _settings_scoring_mode(settings)
        for p in players:
            p['playing_handicap'] = calc_playing_handicap(p['handicap_index'], hpct, hmax)

        # For completed scorecards, override playing_handicap with stored value so the
        # edit form shows what was actually used at time of play, not a re-derived value.
        if matchup['status'] == 'completed':
            stored_hcps = db.execute(
                """SELECT sc.player_id, sc.handicap_at_time_of_play
                   FROM scorecards sc
                   JOIN rounds r ON sc.round_id = r.round_id
                   WHERE r.matchup_id = %s AND sc.handicap_at_time_of_play IS NOT NULL""",
                (matchup['matchup_id'],)
            ).fetchall()
            stored_hcp_map = {row['player_id']: int(round(float(row['handicap_at_time_of_play']))) for row in stored_hcps}
            for p in players:
                if p['player_id'] in stored_hcp_map:
                    p['playing_handicap'] = stored_hcp_map[p['player_id']]

        # Flag players whose handicap for THIS round isn't a plain averaged
        # index — either a manual override or a pre-eligibility provisional
        # value — regardless of whether the round is completed yet. A manual
        # override always wins for what's actually used (see _recalc_single_round's
        # playing_hcps priority order), so it takes priority here too even if
        # the player also happens to be pre-eligibility.
        round_row = db.execute(
            "SELECT round_id FROM rounds WHERE matchup_id = %s", (matchup['matchup_id'],)
        ).fetchone()
        if round_row:
            override_rows = db.execute(
                """SELECT player_id FROM scorecards
                    WHERE round_id = %s AND hcp_manually_overridden = 1""",
                (round_row['round_id'],)
            ).fetchall()
            override_ids = {r['player_id'] for r in override_rows}

            prov_rows = db.execute(
                """SELECT player_id FROM handicap_history
                    WHERE trigger_round_id = %s AND override_reason LIKE %s""",
                (round_row['round_id'], f'{PRE_ELIGIBILITY_MARKER_PREFIX}%')
            ).fetchall()
            prov_ids = {r['player_id'] for r in prov_rows}

            for p in players:
                pid = p['player_id']
                if pid in override_ids:
                    p['hcp_marker'] = 'override'
                elif pid in prov_ids:
                    p['hcp_marker'] = 'provisional'

        for team_num in [1, 2]:
            tp = sorted([p for p in players if p['team_num'] == team_num],
                        key=lambda x: x['playing_handicap'])
            for i, p in enumerate(tp):
                p['role'] = 'A' if i == 0 else 'B'
        def sort_key(p):
            return (p['team_num'], p.get('role', 'Z'))
        players.sort(key=sort_key)

        if matchup['status'] != 'completed':
            min_rounds_for_hcp_e = int(settings['min_rounds_for_handicap']) if settings else 2
            _elig_e = _detect_eligibility_rounds(
                db, [p['player_id'] for p in players], session['league_id'], min_rounds_for_hcp_e
            )
            for p in players:
                # A manual override always wins over the eligibility-round
                # notice — the override determines what's actually used for
                # scoring, so show the editable field + override marker
                # instead of hiding it behind the forward-looking ℹ button.
                if p.get('hcp_marker') == 'override':
                    continue
                if p['player_id'] in _elig_e:
                    p['hcp_eligibility_round'] = True
                    p['rounds_so_far'] = _elig_e[p['player_id']]

    # Warn if any player has no handicap history AND no starting_handicap — they'll
    # silently play as scratch (get_player_handicap returns 0).
    scratch_names = []
    for p in players:
        if p['handicap_index'] == 0:
            ph_row = db.execute(
                "SELECT handicap_id FROM handicap_history WHERE player_id = %s LIMIT 1",
                (p['player_id'],)
            ).fetchone()
            if not ph_row:
                sh_row = db.execute(
                    "SELECT starting_handicap FROM players WHERE player_id = %s", (p['player_id'],)
                ).fetchone()
                if sh_row and sh_row['starting_handicap'] is None:
                    scratch_names.append(p.get('name') or f"Player {p['player_id']}")
    if scratch_names:
        names_str = ', '.join(scratch_names)
        flash(
            f"Warning: {names_str} {'has' if len(scratch_names) == 1 else 'have'} no "
            f"starting handicap set and will play as scratch (0). "
            f"Set a starting handicap in Player settings to correct this.",
            'warning'
        )

    # Build raw player list (unmodified by subs) for the absence form
    raw_players = _build_raw_player_list(db, team1, team2, absence_records)

    nickname_map = _get_nickname_map(db, [p['player_id'] for p in players])

    # ── Per-player tee pre-selection ──────────────────────────────────────────
    # Priority (lowest → highest): course default → flight default (TODO: needs
    # flights/divisions schema) → player preferred_tee_name.
    # For 9-hole leagues the nine is inherited from the matchup tee; player
    # preferences only need to store the color name.
    player_default_tees = {}
    if tees and selected_tee_id:
        # Find nine of the currently selected tee
        selected_nine = next(
            (t['nine'] for t in tees if str(t['tee_id']) == str(selected_tee_id)), None
        )
        # Map tee_name → tee_id for that nine (exact match, first found wins)
        tee_name_to_id = {}
        if selected_nine:
            for t in tees:
                if t['nine'] == selected_nine and t['tee_name'] not in tee_name_to_id:
                    tee_name_to_id[t['tee_name']] = t['tee_id']

        # Build color → M-rep tee_id map from player_tees (the deduplicated list).
        # player_default_tees must resolve to one of these tee_ids or the
        # dropdown <option selected> will never match.
        color_to_rep_tid = {}
        for pt in player_tees:
            color = (pt.get('tee_color') or pt.get('tee_name') or '').strip()
            if color:
                color_to_rep_tid[color] = pt['tee_id']

        def _resolve_to_rep(tid):
            """Map any tee_id → its color's M-rep tee_id in player_tees."""
            t = next((x for x in tees if x['tee_id'] == tid), None)
            if not t:
                return tid
            color = (t.get('tee_color') or t.get('tee_name') or '').strip()
            return color_to_rep_tid.get(color, tid)

        # 1) Course default tee (lowest priority)
        course_default_tid = int(selected_tee_id)
        if selected_course_id:
            try:
                crow = db.execute(
                    "SELECT default_tee_id FROM courses WHERE course_id=%s", (selected_course_id,)
                ).fetchone()
                if crow and crow['default_tee_id']:
                    cd_tee = next((t for t in tees if t['tee_id'] == crow['default_tee_id']), None)
                    if cd_tee and cd_tee['nine'] == selected_nine:
                        course_default_tid = _resolve_to_rep(crow['default_tee_id'])
            except Exception:
                pass

        # 2) Fetch player preferred_tee_name (highest priority)
        pids = [p['player_id'] for p in players]
        pref_map = {}
        if pids:
            placeholders = ','.join(['%s'] * len(pids))
            try:
                rows = db.execute(
                    f"SELECT player_id, preferred_tee_name FROM players WHERE player_id IN ({placeholders})",
                    pids
                ).fetchall()
                pref_map = {r['player_id']: r['preferred_tee_name']
                            for r in rows if r['preferred_tee_name']}
            except Exception:
                pass

        for p in players:
            pid = p['player_id']
            pref = pref_map.get(pid)
            if pref and pref in tee_name_to_id:
                player_default_tees[pid] = _resolve_to_rep(tee_name_to_id[pref])
            else:
                player_default_tees[pid] = course_default_tid

    return render_template('scores/enter.html',
                           matchup=matchup, team1=team1, team2=team2,
                           players=players, courses=courses, tees=tees, player_tees=player_tees, nine_options=nine_options if selected_course_id else [], holes=holes,
                           selected_course_id=str(selected_course_id or ''),
                           selected_tee_id=str(selected_tee_id or ''),
                           all_tee_hcp=all_tee_hcp,
                           player_default_tees=player_default_tees,
                           sub_assignments=sub_assignments,
                           absence_records=absence_records,
                           raw_players=raw_players,
                           all_players=all_players,
                           scoring_mode=enter_scoring_mode,
                           nickname_map=nickname_map)


@bp.route('/tees-json/<int:course_id>')
@admin_required
def tees_json(course_id):
    """AJAX endpoint: return nine-options for a course as JSON (used by course dropdown)."""
    db = get_db()
    tees = db.execute(
        "SELECT tee_id, nine FROM tees WHERE course_id = %s ORDER BY nine, tee_id",
        (course_id,)
    ).fetchall()
    nine_label_map = {'front': 'Front 9', 'back': 'Back 9', 'full': 'Full 18'}
    seen = {}
    for t in tees:
        n = t['nine'] or 'full'
        if n not in seen:
            seen[n] = {'tee_id': t['tee_id'], 'label': nine_label_map.get(n, n.title())}
    return jsonify(list(seen.values()))


def _build_raw_player_list(db, team1, team2, absence_records=None):
    """
    Return all 4 matchup players (never substituted) for the absence form.
    """
    if absence_records is None:
        absence_records = {}
    players = []
    for team, team_num in [(team1, 1), (team2, 2)]:
        for pid_key, fname_key, lname_key in [('p1_id', 'p1_first', 'p1_last'),
                                               ('p2_id', 'p2_first', 'p2_last')]:
            pid = team[pid_key]
            if pid:
                ab = absence_records.get(pid, {})
                sub_pid = ab.get('sub_player_id')
                sub_name = ab.get('sub_name') or None
                if sub_pid:
                    sp = db.execute(
                        "SELECT first_name, last_name FROM players WHERE player_id = %s",
                        (sub_pid,)
                    ).fetchone()
                    if sp:
                        sub_name = f"{sp['first_name']} {sp['last_name']}"
                players.append({
                    'player_id':     pid,
                    'first_name':    team[fname_key],
                    'last_name':     team[lname_key],
                    'team_num':      team_num,
                    'is_absent':     pid in absence_records,
                    'sub_player_id': sub_pid,
                    'sub_name':      sub_name,
                    'reason':        ab.get('reason', ''),
                    'excused':       ab.get('excused', 0),
                })
    return players


def _process_absences(db, matchup_id, team1, team2, form):
    """Save inline absence/sub form data to player_absences."""
    players_in_matchup = []
    for team in [team1, team2]:
        for pk in ['p1_id', 'p2_id']:
            if team[pk]:
                players_in_matchup.append(team[pk])

    existing = {}
    try:
        rows = db.execute(
            "SELECT * FROM player_absences WHERE matchup_id = %s", (matchup_id,)
        ).fetchall()
        for r in rows:
            existing[r['player_id']] = r['absence_id']
    except Exception:
        pass

    for pid in players_in_matchup:
        is_absent = form.get(f'absent_{pid}') == '1'
        sub_pid   = form.get(f'sub_{pid}', '').strip()
        reason    = form.get(f'reason_{pid}', '').strip()
        excused   = 1 if form.get(f'excused_{pid}') == '1' else 0
        new_sub_name = form.get(f'sub_new_name_{pid}', '').strip() or None
        sub_pid_val  = int(sub_pid) if sub_pid else None
        # If a free-text new sub name is provided, create a player record and use their id
        if new_sub_name:
            parts = new_sub_name.strip().split(' ', 1)
            first = parts[0]
            last  = parts[1] if len(parts) > 1 else ''
            league_id = session.get('league_id')
            existing_player = db.execute(
                "SELECT player_id FROM players WHERE first_name=%s AND last_name=%s AND league_id=%s",
                (first, last, league_id)
            ).fetchone()
            if existing_player:
                sub_pid_val = existing_player['player_id']
            else:
                row = db.execute(
                    "INSERT INTO players (first_name, last_name, league_id, active, is_sub, created_date) VALUES (%s, %s, %s, 1, TRUE, CURRENT_DATE::TEXT) RETURNING player_id",
                    (first, last, league_id)
                ).fetchone()
                sub_pid_val = row['player_id']
            new_sub_name = None  # stored via player record now

        if is_absent:
            if pid in existing:
                db.execute(
                    """UPDATE player_absences
                       SET sub_player_id=%s, sub_name=%s, reason=%s, excused=%s
                       WHERE absence_id=%s""",
                    (sub_pid_val, new_sub_name, reason or None, excused, existing[pid])
                )
            else:
                db.execute(
                    """INSERT INTO player_absences
                       (matchup_id, player_id, sub_player_id, sub_name, reason, excused)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (matchup_id, pid, sub_pid_val, new_sub_name, reason or None, excused)
                )
        else:
            if pid in existing:
                db.execute(
                    "DELETE FROM player_absences WHERE absence_id=%s",
                    (existing[pid],)
                )

    db.commit()


def _build_player_list(db, season_id, team1, team2, sub_assignments=None, league_id=None):
    """
    Return list of player dicts with handicap info, substituting absent players with their subs.
    """
    if sub_assignments is None:
        sub_assignments = {}
    players = []
    for team, role in [(team1, 1), (team2, 2)]:
        for pid_key, fname_key, lname_key in [('p1_id', 'p1_first', 'p1_last'),
                                               ('p2_id', 'p2_first', 'p2_last')]:
            if team[pid_key]:
                orig_pid = team[pid_key]
                sub_info = sub_assignments.get(orig_pid)
                if sub_info:
                    pid        = sub_info['sub_player_id']
                    first_name = sub_info['sub_first']
                    last_name  = sub_info['sub_last']
                else:
                    pid        = orig_pid
                    first_name = team[fname_key]
                    last_name  = team[lname_key]
                hcp = get_player_handicap(db, pid, league_id=league_id)
                players.append({
                    'player_id':      pid,
                    'first_name':     first_name,
                    'last_name':      last_name,
                    'team_num':       role,
                    'team_id':        team['team_id'],
                    'handicap_index': hcp,
                    'is_sub':         sub_info is not None,
                    'orig_player_id': orig_pid if sub_info else None,
                    'orig_first':     team[fname_key] if sub_info else None,
                    'orig_last':      team[lname_key] if sub_info else None,
                })
    return players


def _recalc_single_round(db, matchup_id, season_id, league_id,
                         handicap_percent, max_handicap, scoring_mode,
                         use_existing_hcp=False, handicap_lookup=None,
                         temp_ph_lookup=None,
                         absence_policy='excused_only'):
    """Re-score one completed round with current handicaps and re-write results.

    handicap_lookup, when given, maps player_id -> raw handicap_index to use
    instead of querying handicap_history for "whatever is latest right now".
    This lets a chronological rebuild (see handicap.rebuild_league_handicaps_and_scores)
    supply each player's point-in-time handicap for this specific round.

    temp_ph_lookup, when given, maps player_id -> an already-final playing
    handicap for a pre-eligibility round (diff × member/sub percent, capped
    — see handicap.rebuild_player_handicap_timeline). Used directly, NOT run
    through calc_playing_handicap() again — that would double-apply a percent.
    """
    round_row = db.execute(
        "SELECT * FROM rounds WHERE matchup_id = %s", (matchup_id,)
    ).fetchone()
    if not round_row:
        return

    matchup = db.execute(
        "SELECT * FROM matchups WHERE matchup_id = %s", (matchup_id,)
    ).fetchone()
    if not matchup:
        return

    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
        (round_row['tee_id'],)
    ).fetchall()
    if not holes:
        return
    n_holes = len(holes)

    scorecards = db.execute(
        """SELECT sc.*, p.first_name, p.last_name
             FROM scorecards sc JOIN players p ON sc.player_id = p.player_id
            WHERE sc.round_id = %s""",
        (round_row['round_id'],)
    ).fetchall()
    if not scorecards:
        return

    # Handicap for each player: point-in-time lookup if supplied, else
    # whatever handicap_history currently considers "latest".
    def current_handicap(pid):
        if handicap_lookup is not None and pid in handicap_lookup:
            return float(handicap_lookup[pid])
        hh = db.execute(
            """SELECT handicap_index FROM handicap_history
                WHERE player_id = %s
                ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1""",
            (pid,)
        ).fetchone()
        if hh:
            return float(hh['handicap_index'])
        row = db.execute("SELECT starting_handicap FROM players WHERE player_id = %s", (pid,)).fetchone()
        return float(row['starting_handicap']) if row and row['starting_handicap'] is not None else 0.0

    playing_hcps = {}
    for sc in scorecards:
        pid = sc['player_id']
        if sc['hcp_manually_overridden'] and sc['handicap_at_time_of_play'] is not None:
            # Per-round manual override always wins, regardless of use_existing_hcp.
            playing_hcps[pid] = int(round(float(sc['handicap_at_time_of_play'])))
        elif use_existing_hcp and sc['handicap_at_time_of_play'] is not None:
            playing_hcps[pid] = int(round(float(sc['handicap_at_time_of_play'])))
        elif temp_ph_lookup and pid in temp_ph_lookup:
            # Pre-eligibility round: value is already the final playing
            # handicap (diff × member/sub percent, capped) — do NOT run it
            # through calc_playing_handicap again.
            playing_hcps[pid] = int(round(float(temp_ph_lookup[pid])))
        else:
            raw_hcp = current_handicap(pid)
            playing_hcps[pid] = calc_playing_handicap(raw_hcp, handicap_percent, max_handicap)

    # Absent players: pid -> excused
    absent_sc = {}
    try:
        abs_rows = db.execute(
            """SELECT pa.player_id, pa.excused
               FROM player_absences pa
               JOIN scorecards sc ON sc.player_id = pa.player_id AND sc.round_id = %s
               WHERE pa.matchup_id = %s AND pa.sub_player_id IS NULL AND sc.is_absent = 1""",
            (round_row['round_id'], matchup_id)
        ).fetchall()
        for r in abs_rows:
            absent_sc[r['player_id']] = r['excused'] or 0
    except Exception:
        pass

    # Gross scores and per-player hole list
    gross = {}
    net   = {}
    sc_holes = {}  # pid -> holes (in case of per-player tee)
    for sc in scorecards:
        pid = sc['player_id']
        p_tee_id = sc['tee_id'] if sc['tee_id'] else round_row['tee_id']
        if p_tee_id != round_row['tee_id']:
            p_holes = db.execute(
                "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number", (p_tee_id,)
            ).fetchall() or holes
        else:
            p_holes = holes
        sc_holes[pid] = p_holes
        ph = playing_hcps[pid]
        n = len(p_holes)
        p_hcp_idxs = [h['handicap_index'] for h in p_holes]
        if pid in absent_sc:
            # Regenerate ghost scores from current handicap
            ghost = [h['par'] + strokes_on_hole(ph, h['handicap_index'], total_holes=n,
                                                 hcp_indices=p_hcp_idxs)
                     for h in p_holes]
            gross[pid] = ghost
            net[pid]   = [h['par'] for h in p_holes]  # ghost always scores par net
        else:
            hs = db.execute(
                "SELECT * FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
                (sc['scorecard_id'],)
            ).fetchall()
            gross[pid] = [h['gross_score'] for h in hs]
            net[pid] = [
                g - strokes_on_hole(ph, p_holes[i]['handicap_index'], total_holes=n,
                                    hcp_indices=p_hcp_idxs)
                for i, g in enumerate(gross[pid])
            ]

    # A/B designation per team — lower playing hcp = A
    team_ids = list({sc['team_id'] for sc in scorecards})
    if len(team_ids) != 2:
        return
    t1_id, t2_id = team_ids[0], team_ids[1]

    def team_ab(team_id):
        pids = [sc['player_id'] for sc in scorecards if sc['team_id'] == team_id]
        pids.sort(key=lambda p: playing_hcps.get(p, 99))
        return (pids[0], pids[1]) if len(pids) >= 2 else (pids[0], pids[0])

    t1_a, t1_b = team_ab(t1_id)
    t2_a, t2_b = team_ab(t2_id)

    def match_result(pid_x, pid_y):
        p_holes_x = sc_holes[pid_x]
        if scoring_mode == 'stableford':
            sb_x, sb_y = 0.0, 0.0
            for i, h in enumerate(p_holes_x):
                nx, ny = net[pid_x][i], net[pid_y][i]
                par = h['par'] if h['par'] else 4
                sb_x += calc_stableford(nx - par)
                sb_y += calc_stableford(ny - par)
            ox, oy = calc_match_play(-sb_x, -sb_y)
            return sb_x, sb_y, ox, oy
        else:
            # Hole-by-hole: differential stroke allocation (only the higher-
            # handicap player gets strokes). Overall: absolute net (net[]).
            return diff_match_hole_points(gross[pid_x], gross[pid_y], p_holes_x,
                                           playing_hcps[pid_x], playing_hcps[pid_y],
                                           net[pid_x], net[pid_y])

    aa = _apply_absence_overall_policy(match_result(t1_a, t2_a), t1_a, t2_a, absent_sc, absence_policy)
    bb = _apply_absence_overall_policy(match_result(t1_b, t2_b), t1_b, t2_b, absent_sc, absence_policy)

    # Update scorecard handicap_at_time_of_play and hole scores
    sc_map = {sc['player_id']: sc for sc in scorecards}
    for pid, sc in sc_map.items():
        if not use_existing_hcp:
            db.execute(
                "UPDATE scorecards SET handicap_at_time_of_play = %s WHERE scorecard_id = %s",
                (playing_hcps[pid], sc['scorecard_id'])
            )
        if pid in absent_sc:
            # Rewrite ghost hole scores with updated handicap
            db.execute("DELETE FROM hole_scores WHERE scorecard_id = %s", (sc['scorecard_id'],))
            ph = playing_hcps[pid]
            p_holes = sc_holes[pid]
            n = len(p_holes)
            for i, h in enumerate(p_holes):
                g = gross[pid][i]
                net_val = net[pid][i]
                db.execute(
                    """INSERT INTO hole_scores
                       (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (sc['scorecard_id'], h['hole_id'], h['hole_number'], g, net_val, g - h['par'])
                )
        else:
            for i, net_val in enumerate(net[pid]):
                db.execute(
                    "UPDATE hole_scores SET net_score = %s WHERE scorecard_id = %s AND hole_number = %s",
                    (net_val, sc['scorecard_id'], sc_holes[pid][i]['hole_number'])
                )

    # Rewrite match_results
    db.execute("DELETE FROM match_results WHERE matchup_id = %s", (matchup_id,))
    roles = {
        t1_a: ('A', t1_id, t2_a, aa[0], aa[2]),
        t2_a: ('A', t2_id, t1_a, aa[1], aa[3]),
        t1_b: ('B', t1_id, t2_b, bb[0], bb[2]),
        t2_b: ('B', t2_id, t1_b, bb[1], bb[3]),
    }
    for pid, (role, tid, opp, hole_pts, overall_pt) in roles.items():
        db.execute(
            """INSERT INTO match_results
               (matchup_id, team_id, player_id, role,
                hole_points_won, overall_point_won, total_points, opponent_player_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (matchup_id, tid, pid, role,
             hole_pts, overall_pt, hole_pts + overall_pt, opp)
        )


def _process_scores(db, matchup, team1, team2, holes, form):
    """Validate, calculate, and save scores + match results."""
    season_id  = matchup['season_id']
    league_id  = session['league_id']
    round_date = form.get('round_date', '').strip() or datetime.now().strftime('%Y-%m-%d')

    default_tee_id = form.get('tee_id', '').strip()
    course_id      = form.get('course_id', '').strip()

    # Process inline absence changes FIRST — before tee validation so absences
    # are always saved even when no tee is selected yet.
    matchup_player_ids = [team[pk] for team in [team1, team2] for pk in ['p1_id', 'p2_id'] if team[pk]]
    has_inline_absences = any(form.get(f'absent_{pid}') is not None for pid in matchup_player_ids)
    if has_inline_absences:
        _process_absences(db, matchup['matchup_id'], team1, team2, form)

    if not default_tee_id or not holes:
        flash('Please select a tee before submitting scores.', 'error')
        return redirect(url_for('scores.enter', matchup_id=matchup['matchup_id']))

    # P3-2: Detect tee change after holes were loaded (sentinel from hidden input)
    loaded_tee_id = form.get('loaded_tee_id', '').strip()
    if loaded_tee_id and loaded_tee_id != default_tee_id:
        import logging
        logging.getLogger(__name__).warning(
            'Tee mismatch on score submit: holes loaded for tee %s but form submitted tee %s (matchup %s, user %s)',
            loaded_tee_id, default_tee_id, matchup['matchup_id'], session.get('user_id')
        )
        flash('Warning: the tee shown on the scorecard did not match the submitted tee. Scores were saved using the submitted tee — verify hole handicaps are correct.', 'warning')

    sub_assignments = _get_sub_assignments(db, matchup['matchup_id'])
    players = _build_player_list(db, season_id, team1, team2, sub_assignments, league_id=session.get('league_id'))
    if len(players) < 4:
        flash('Both teams need 2 players assigned before entering scores.', 'error')
        return redirect(url_for('scores.enter', matchup_id=matchup['matchup_id']))

    # Per-player tee selection (defaults to matchup tee if not set)
    player_tee_ids = {}
    player_holes   = {}
    for p in players:
        pid      = p['player_id']
        orig_pid = p.get('orig_player_id')
        ptee     = form.get(f'player_tee_{pid}', '').strip()
        if not ptee and orig_pid:
            ptee = form.get(f'player_tee_{orig_pid}', '').strip()
        tid   = int(ptee) if ptee else int(default_tee_id)
        player_tee_ids[pid] = tid
        if tid != int(default_tee_id):
            ph = db.execute(
                "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
                (tid,)
            ).fetchall()
            player_holes[pid] = ph if ph else holes
        else:
            player_holes[pid] = holes

    # P1-4: Validate per-player tees belong to the same course as the matchup
    if course_id:
        pid_to_name = {p['player_id']: f"{p['first_name']} {p['last_name']}" for p in players}
        for pid, tid in player_tee_ids.items():
            if tid != int(default_tee_id):
                tee_row = db.execute(
                    "SELECT course_id FROM tees WHERE tee_id = %s", (tid,)
                ).fetchone()
                if not tee_row or tee_row['course_id'] != int(course_id):
                    flash(f"Tee selection for {pid_to_name.get(pid, str(pid))} does not belong to the selected course.", 'error')
                    return redirect(url_for('scores.enter', matchup_id=matchup['matchup_id']))

    # Parse gross scores — allow missing holes (partial save)
    gross = {}
    is_complete = True
    for p in players:
        pid = p['player_id']
        p_holes = player_holes[pid]
        player_scores = []
        orig_pid = p.get('orig_player_id')
        for h in p_holes:
            key = f"score_{pid}_{h['hole_number']}"
            val = form.get(key, '').strip()
            # Sub selected mid-session: form inputs were keyed by orig player id
            if not val and orig_pid:
                val = form.get(f"score_{orig_pid}_{h['hole_number']}", '').strip()
            if not val:
                player_scores.append(None)
                is_complete = False
            else:
                try:
                    player_scores.append(int(val))
                except ValueError:
                    flash(f"Invalid score for {p['first_name']} {p['last_name']}, hole {h['hole_number']}.", 'error')
                    return redirect(url_for('scores.enter', matchup_id=matchup['matchup_id']))
        gross[pid] = player_scores

    # Detect absent-no-sub players (all scores None) and synthesize ghost scores
    # Must happen before playing_hcps is built, so we do a preliminary pass here.
    # We'll fill synthetic gross after playing_hcps is computed below.
    absent_player_pids_raw = {}  # pid -> excused (resolved after playing_hcps)
    try:
        absence_rows = db.execute(
            "SELECT player_id, excused FROM player_absences WHERE matchup_id = %s AND sub_player_id IS NULL",
            (matchup['matchup_id'],)
        ).fetchall()
        for row in absence_rows:
            pid = row['player_id']
            # player_absences is authoritative for this submission (already
            # committed by _process_absences above) — ghost this player even
            # if some real scores slipped through, instead of only when
            # every hole was blank.
            if pid in gross:
                absent_player_pids_raw[pid] = row['excused'] or 0
    except Exception as _ab_err:
        import logging
        logging.getLogger(__name__).error('Absence detection failed for matchup %s: %s', matchup['matchup_id'], _ab_err)

    # League settings
    settings = get_league_settings(db, season_id, league_id)
    handicap_percent = float(settings['handicap_percent']) if settings else 90.0
    max_handicap     = float(settings['max_handicap_index']) if settings else 18.0
    scoring_mode = _settings_scoring_mode(settings)
    absence_policy = _settings_absence_policy(settings)

    # P2-1: Enforce max_score_per_hole if set in league settings
    max_per_hole   = int(settings['max_score_per_hole']) if settings and settings['max_score_per_hole'] else None
    score_action   = (settings['max_score_action'] or 'warn') if settings and settings['max_score_action'] else 'warn'
    if max_per_hole:
        violations = []
        for p in players:
            pid = p['player_id']
            p_holes = player_holes[pid]
            for i, h in enumerate(p_holes):
                s = gross[pid][i]
                if s is None or pid in absent_player_pids_raw:
                    continue  # absent player — real leftover values are discarded before ghosting
                if s > max_per_hole:
                    violations.append(f"{p['first_name']} {p['last_name']} hole {h['hole_number']} ({s} > max {max_per_hole})")
        if violations:
            msg = 'Score exceeds league max per hole: ' + '; '.join(violations)
            if score_action == 'block':
                flash(msg, 'error')
                return redirect(url_for('scores.enter', matchup_id=matchup['matchup_id']))
            else:
                flash(msg, 'warning')

    # Look up any pre-existing round so manually-overridden playing handicaps
    # can be applied BEFORE net scores / A-B roles / match results are computed
    # (must happen before those calculations, not patched in afterward).
    existing = db.execute(
        "SELECT round_id FROM rounds WHERE matchup_id = %s", (matchup['matchup_id'],)
    ).fetchone()
    if existing:
        _hcp_overrides = {
            row['player_id']: row['handicap_at_time_of_play']
            for row in db.execute(
                "SELECT player_id, handicap_at_time_of_play FROM scorecards WHERE round_id = %s AND hcp_manually_overridden = 1",
                (existing['round_id'],)
            ).fetchall()
        }
    else:
        _hcp_overrides = {}

    # Manual playing-handicap override submitted from the score-entry form
    # (the "Hdcp" column input) — same effect as editing a value in the
    # Handicap Matrix. Only treated as an override when it differs from the
    # freshly computed default, so re-saving an untouched field doesn't
    # spuriously flag hcp_manually_overridden; submitting back the computed
    # default clears a pre-existing override.
    for p in players:
        pid = p['player_id']
        orig_pid = p.get('orig_player_id')
        raw_override = form.get(f'hcp_override_{pid}', '').strip()
        if not raw_override and orig_pid:
            raw_override = form.get(f'hcp_override_{orig_pid}', '').strip()
        if not raw_override:
            continue
        try:
            submitted_hcp = int(round(float(raw_override)))
        except ValueError:
            continue
        default_hcp = calc_playing_handicap(p['handicap_index'], handicap_percent, max_handicap)
        if submitted_hcp != default_hcp:
            _hcp_overrides[pid] = submitted_hcp
        elif pid in _hcp_overrides:
            del _hcp_overrides[pid]

    # Playing handicaps (manual overrides take precedence)
    playing_hcps = {}
    for p in players:
        pid = p['player_id']
        if pid in _hcp_overrides:
            playing_hcps[pid] = int(round(float(_hcp_overrides[pid])))
        else:
            playing_hcps[pid] = calc_playing_handicap(p['handicap_index'], handicap_percent, max_handicap)

    # Synthesize ghost gross for absent-no-sub players (par + strokes per hole)
    absent_players = {}  # pid -> excused
    if absent_player_pids_raw:
        import logging as _log
        _log.getLogger(__name__).info('Ghost scoring %d absent player(s) for matchup %s: %s',
                                      len(absent_player_pids_raw), matchup['matchup_id'],
                                      list(absent_player_pids_raw.keys()))
    for pid, excused in absent_player_pids_raw.items():
        p_holes = player_holes[pid]
        ph = playing_hcps[pid]
        n = len(p_holes)
        p_hcp_idxs = [h['handicap_index'] for h in p_holes]
        ghost = [h['par'] + strokes_on_hole(ph, h['handicap_index'], total_holes=n,
                                             hcp_indices=p_hcp_idxs)
                 for h in p_holes]
        gross[pid] = ghost
        absent_players[pid] = excused

    # Recheck completeness after synthesizing absent scores
    is_complete = all(
        all(g is not None for g in gross[p['player_id']])
        for p in players
    )
    if absent_players and not is_complete:
        import logging as _log2
        for p in players:
            pid = p['player_id']
            nones = [i for i, g in enumerate(gross.get(pid, [])) if g is None]
            if nones:
                _log2.getLogger(__name__).warning(
                    'Matchup %s: player %s still has %d None scores after ghost synthesis (holes %s)',
                    matchup['matchup_id'], pid, len(nones), nones[:5]
                )

    # Net scores per hole using per-player tee's hole HCP indexes
    net = {}
    for p in players:
        pid    = p['player_id']
        ph     = playing_hcps[pid]
        p_holes = player_holes[pid]
        p_hcp_idxs = [h['handicap_index'] for h in p_holes]
        net[pid] = []
        for i, h in enumerate(p_holes):
            g = gross[pid][i]
            if g is None:
                net[pid].append(None)
            else:
                s = strokes_on_hole(ph, h['handicap_index'], total_holes=len(p_holes),
                                    hcp_indices=p_hcp_idxs)
                net[pid].append(g - s)

    # A/B designation — within each team, lower handicap = A
    def designate(team, p_list):
        tp = [p for p in p_list if p['team_id'] == team['team_id']]
        tp_sorted = sorted(tp, key=lambda x: playing_hcps[x['player_id']])
        return tp_sorted[0]['player_id'], tp_sorted[1]['player_id']

    t1_a, t1_b = designate(team1, players)
    t2_a, t2_b = designate(team2, players)

    # Match play or Stableford: A vs A, B vs B hole by hole + overall gross
    def match_result(pid_x, pid_y):
        p_holes_x = player_holes[pid_x]
        if scoring_mode == 'stableford':
            sb_x, sb_y = 0.0, 0.0
            for i, h in enumerate(p_holes_x):
                nx, ny = net[pid_x][i], net[pid_y][i]
                if nx is None or ny is None:
                    continue
                par = h['par'] if h['par'] else 4
                sb_x += calc_stableford(nx - par)
                sb_y += calc_stableford(ny - par)
            overall_x, overall_y = calc_match_play(-sb_x, -sb_y)
            return sb_x, sb_y, overall_x, overall_y
        else:
            # Hole-by-hole: differential stroke allocation (only the higher-
            # handicap player gets strokes). Overall: absolute net (net[]).
            return diff_match_hole_points(gross[pid_x], gross[pid_y], p_holes_x,
                                           playing_hcps[pid_x], playing_hcps[pid_y],
                                           net[pid_x], net[pid_y])

    aa = _apply_absence_overall_policy(match_result(t1_a, t2_a), t1_a, t2_a, absent_players, absence_policy)
    bb = _apply_absence_overall_policy(match_result(t1_b, t2_b), t1_b, t2_b, absent_players, absence_policy)

    # --- Save to db ---
    # Guard against duplicate submission; allow re-save of in-progress rounds
    # (existing/_hcp_overrides were already looked up above, before playing_hcps)
    if existing:
        # Wipe previous data (in_progress or completed) before re-saving
        old_rid = existing['round_id']
        db.execute("DELETE FROM hole_scores WHERE scorecard_id IN "
                   "(SELECT scorecard_id FROM scorecards WHERE round_id = %s)", (old_rid,))
        db.execute("DELETE FROM scorecards WHERE round_id = %s", (old_rid,))
        db.execute("DELETE FROM match_results WHERE matchup_id = %s", (matchup['matchup_id'],))
        db.execute("UPDATE player_absences SET round_id = NULL WHERE round_id = %s", (old_rid,))
        db.execute("UPDATE handicap_history SET trigger_round_id = NULL WHERE trigger_round_id = %s", (old_rid,))
        db.execute("DELETE FROM rounds WHERE round_id = %s", (old_rid,))

    row = db.execute(
        """INSERT INTO rounds (matchup_id, season_id, course_id, tee_id, round_date, round_number, entered_by_user_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING round_id""",
        (matchup['matchup_id'], season_id, int(course_id), int(default_tee_id),
         round_date, matchup['round_number'], session.get('user_id'))
    )
    round_id = row.fetchone()['round_id']

    # Scorecards + hole scores
    # Build a lookup: sub_player_id -> orig_player_id from sub_assignments
    sub_to_orig = {info['sub_player_id']: orig_pid
                   for orig_pid, info in sub_assignments.items()}

    for p in players:
        pid = p['player_id']
        is_sub_flag = 1 if p.get('is_sub') else 0
        sub_for_pid = p.get('orig_player_id')  # None if not a sub
        p_holes     = player_holes[pid]
        p_tee_id    = player_tee_ids[pid]

        is_absent_flag = 1 if pid in absent_players else 0
        is_override_flag = 1 if pid in _hcp_overrides else 0
        sc_row = db.execute(
            """INSERT INTO scorecards
               (round_id, player_id, team_id, handicap_at_time_of_play,
                is_sub, sub_for_player_id, approved, tee_id, is_absent, hcp_manually_overridden)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s) RETURNING scorecard_id""",
            (round_id, pid, p['team_id'], playing_hcps[pid],
             is_sub_flag, sub_for_pid, p_tee_id, is_absent_flag, is_override_flag)
        )
        sc_id = sc_row.fetchone()['scorecard_id']
        for i, h in enumerate(p_holes):
            g = gross[pid][i]
            if g is None:
                continue  # skip missing holes
            diff = g - h['par']
            db.execute(
                """INSERT INTO hole_scores
                   (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (sc_id, h['hole_id'], h['hole_number'],
                 g, net[pid][i], diff)
            )

    # Link absence records to this round
    db.execute(
        "UPDATE player_absences SET round_id = %s WHERE matchup_id = %s",
        (round_id, matchup['matchup_id'])
    )

    if is_complete:
        # Match results (only when all scores are present)
        roles = {
            t1_a: ('A', team1['team_id'], t2_a, aa[0], aa[2]),
            t2_a: ('A', team2['team_id'], t1_a, aa[1], aa[3]),
            t1_b: ('B', team1['team_id'], t2_b, bb[0], bb[2]),
            t2_b: ('B', team2['team_id'], t1_b, bb[1], bb[3]),
        }
        for pid, (role, tid, opp, hole_pts, overall_pt) in roles.items():
            db.execute(
                """INSERT INTO match_results
                   (matchup_id, team_id, player_id, role,
                    hole_points_won, overall_point_won, total_points, opponent_player_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (matchup['matchup_id'], tid, pid, role,
                 hole_pts, overall_pt, hole_pts + overall_pt, opp)
            )
        db.execute(
            "UPDATE matchups SET status = 'completed', course_id = %s, tee_id = %s WHERE matchup_id = %s",
            (int(course_id), int(default_tee_id), matchup['matchup_id'])
        )
        db.commit()

        # Handicap + downstream-round rebuild: walks every round chronologically
        # so this save (even a late/backdated entry) correctly ripples forward
        # through every later round's handicap, net scores, and match points.
        try:
            rebuild_league_handicaps_and_scores(db, league_id)
            db.commit()
        except Exception as hcap_err:
            import logging
            logging.getLogger(__name__).error('Handicap timeline rebuild failed: %s', hcap_err)
            flash('Scores saved, but handicap recalculation failed — recalculate manually.', 'warning')

        # Round-completed notification + emails + push
        try:
            t1_name = team1.get('team_name') or f"{team1['p1_last']}/{team1['p2_last']}"
            t2_name = team2.get('team_name') or f"{team2['p1_last']}/{team2['p2_last']}"
            msg = f"Scores recorded: {t1_name} vs {t2_name} (Week {matchup['week_number']})"
            create_league_event(db, league_id, 'round_completed', msg,
                                season_id=season_id, ref_id=matchup['matchup_id'])
            db.commit()
        except Exception:
            pass
        try:
            from routes.email_config import send_round_posted_email, send_player_scorecard_emails
            week_label = f"Week {matchup['week_number']}"
            send_round_posted_email(db, league_id, season_id, week_label)
            _name_map = {
                team1['p1_id']: f"{team1['p1_first'] or ''} {team1['p1_last'] or ''}".strip(),
                team1['p2_id']: f"{team1['p2_first'] or ''} {team1['p2_last'] or ''}".strip(),
                team2['p1_id']: f"{team2['p1_first'] or ''} {team2['p1_last'] or ''}".strip(),
                team2['p2_id']: f"{team2['p2_first'] or ''} {team2['p2_last'] or ''}".strip(),
            }
            _player_summaries = []
            for _pid, (_role, _tid, _opp_pid, _hole_pts, _overall_pt) in roles.items():
                _total_pts = _hole_pts + _overall_pt
                _opp_pts   = sum(v[3] + v[4] for k, v in roles.items() if k == _opp_pid) if _opp_pid else 0
                _player_summaries.append({
                    'player_id':   _pid,
                    'name':        _name_map.get(_pid, 'Player'),
                    'gross_total': sum(g for g in gross.get(_pid, []) if g is not None),
                    'net_total':   sum(n for n in net.get(_pid, []) if n is not None),
                    'total_pts':   _total_pts,
                    'opp_name':    _name_map.get(_opp_pid, 'Opponent'),
                    'opp_gross':   sum(g for g in gross.get(_opp_pid, []) if g is not None),
                    'opp_net':     sum(n for n in net.get(_opp_pid, []) if n is not None),
                    'opp_pts':     _opp_pts,
                    'role':        _role,
                })
            _sc_url = url_for('scores.view', matchup_id=matchup['matchup_id'], _external=True)
            send_player_scorecard_emails(db, league_id, week_label, _player_summaries, scorecard_url=_sc_url)
        except Exception:
            pass
        try:
            from push import send_to_league
            t1_label = team1['team_name'] or f"{team1['p1_last'] or ''}/{team1['p2_last'] or ''}"
            t2_label = team2['team_name'] or f"{team2['p1_last'] or ''}/{team2['p2_last'] or ''}"
            send_to_league(db, league_id,
                           title=f"Week {matchup['week_number']} Scores Posted",
                           body=f"{t1_label} vs {t2_label}",
                           data={'deep_link': 'score_approved'})
        except Exception:
            pass

        flash('Scores saved!', 'success')
        return_url = form.get('return_url', '').strip()
        if return_url:
            return redirect(return_url)
        return redirect(url_for('scores.view', matchup_id=matchup['matchup_id']))

    else:
        # Partial save — only mark in_progress if at least one real score was entered
        has_any_real_score = any(
            g is not None
            for pid, scores in gross.items()
            if pid not in absent_players
            for g in scores
        )
        new_status = 'in_progress' if has_any_real_score else matchup['status']
        db.execute(
            "UPDATE matchups SET status = %s, course_id = %s, tee_id = %s WHERE matchup_id = %s",
            (new_status, int(course_id), int(default_tee_id), matchup['matchup_id'])
        )
        db.commit()
        flash('Scores partially saved — group marked as in progress.', 'info')
        return_url = form.get('return_url', '').strip()
        if return_url:
            return redirect(return_url)
        return redirect(url_for('scores.enter', matchup_id=matchup['matchup_id']))


# ---------------------------------------------------------------------------
# Reopen / clear completed scores
# ---------------------------------------------------------------------------

@bp.route('/reopen/<int:matchup_id>', methods=['POST'])
@admin_required
def reopen_scores(matchup_id):
    """Strip match results and reopen a completed round for editing, keeping hole scores."""
    db = get_db()
    matchup = db.execute(
        "SELECT m.*, s.season_id FROM matchups m JOIN seasons s ON m.season_id = s.season_id WHERE m.matchup_id = %s AND s.league_id = %s",
        (matchup_id, session['league_id'])
    ).fetchone()
    if not matchup:
        flash('Matchup not found.', 'error')
        return redirect(url_for('seasons.index'))
    saved = db.execute(
        "SELECT matchup_id, team_id, player_id, role, hole_points_won, overall_point_won, total_points, opponent_player_id"
        " FROM match_results WHERE matchup_id = %s", (matchup_id,)
    ).fetchall()
    session['mr_backup_' + str(matchup_id)] = [dict(r) for r in saved]
    db.execute("DELETE FROM match_results WHERE matchup_id = %s", (matchup_id,))
    db.execute("UPDATE matchups SET status = 'in_progress' WHERE matchup_id = %s", (matchup_id,))
    db.commit()
    return_url = request.form.get('return_url', '').strip()
    if return_url:
        sep = '&' if '?' in return_url else '?'
        return redirect(f'{return_url}{sep}scroll_to=ew-block-{matchup_id}')
    return redirect(url_for('scores.enter', matchup_id=matchup_id))


@bp.route('/cancel-edit/<int:matchup_id>', methods=['POST'])
@admin_required
def cancel_edit(matchup_id):
    """Discard in-progress edits and restore the matchup to completed state."""
    db = get_db()
    matchup = db.execute(
        "SELECT m.*, s.season_id FROM matchups m JOIN seasons s ON m.season_id = s.season_id"
        " WHERE m.matchup_id = %s AND s.league_id = %s",
        (matchup_id, session['league_id'])
    ).fetchone()
    if not matchup:
        flash('Matchup not found.', 'error')
        return redirect(url_for('seasons.index'))

    backup_key = 'mr_backup_' + str(matchup_id)
    saved = session.pop(backup_key, None)
    if saved:
        for row in saved:
            db.execute(
                "INSERT INTO match_results"
                " (matchup_id, team_id, player_id, role, hole_points_won, overall_point_won, total_points, opponent_player_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (row['matchup_id'], row['team_id'], row['player_id'], row['role'],
                 row['hole_points_won'], row['overall_point_won'], row['total_points'], row['opponent_player_id'])
            )
        db.execute("UPDATE matchups SET status = 'completed' WHERE matchup_id = %s", (matchup_id,))
        db.commit()

    return_url = request.form.get('return_url', '').strip()
    if return_url:
        sep = '&' if '?' in return_url else '?'
        return redirect(f'{return_url}{sep}scroll_to=ew-block-{matchup_id}')
    return redirect(url_for('scores.enter_week',
                            season_id=matchup['season_id'],
                            week_num=matchup['week_number']))


@bp.route('/swap-side/<int:season_id>/<int:week_num>', methods=['POST'])
@admin_required
def swap_side(season_id, week_num):
    """Remap completed hole scores to a different nine, preserving gross scores.

    Position-maps scores: position 0 on old side → position 0 on new side.
    All results are recalculated with existing playing handicaps.
    Course changes are not permitted — only side (nine) swaps within the same course.
    """
    db = get_db()
    league_id = session['league_id']
    new_tee_id = request.form.get('new_tee_id', type=int)

    def _back(msg, level='error'):
        flash(msg, level)
        return redirect(url_for('scores.enter_week', season_id=season_id, week_num=week_num))

    if not new_tee_id:
        return _back('No side selected.')

    new_tee = db.execute("SELECT * FROM tees WHERE tee_id = %s", (new_tee_id,)).fetchone()
    if not new_tee:
        return _back('Invalid tee.')

    new_holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number", (new_tee_id,)
    ).fetchall()
    if not new_holes:
        return _back('No hole data found for the selected side.')

    matchup_rows = db.execute(
        """SELECT matchup_id FROM matchups
           WHERE season_id = %s AND week_number = %s AND status = 'completed' AND is_bye = 0""",
        (season_id, week_num)
    ).fetchall()
    if not matchup_rows:
        return _back('No completed matchups to update.', 'info')

    settings        = get_league_settings(db, season_id, league_id)
    scoring_mode    = _settings_scoring_mode(settings)
    hcp_pct         = float(settings.get('handicap_percent', 100)) / 100
    max_hcp         = float(settings.get('max_handicap', 54))
    absence_policy  = _settings_absence_policy(settings)

    swapped = 0
    warnings = []

    for mr in matchup_rows:
        matchup_id = mr['matchup_id']
        round_row = db.execute("SELECT * FROM rounds WHERE matchup_id = %s", (matchup_id,)).fetchone()
        if not round_row:
            continue

        old_tee = db.execute("SELECT course_id FROM tees WHERE tee_id = %s", (round_row['tee_id'],)).fetchone()
        if not old_tee or old_tee['course_id'] != new_tee['course_id']:
            warnings.append(f'Group {matchup_id}: different course — skipped.')
            continue

        old_holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number", (round_row['tee_id'],)
        ).fetchall()
        if len(old_holes) != len(new_holes):
            warnings.append(f'Group {matchup_id}: hole count mismatch ({len(old_holes)} vs {len(new_holes)}) — skipped.')
            continue

        scorecards = db.execute(
            "SELECT * FROM scorecards WHERE round_id = %s", (round_row['round_id'],)
        ).fetchall()

        for sc in scorecards:
            hs_rows = db.execute(
                "SELECT gross_score FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
                (sc['scorecard_id'],)
            ).fetchall()
            gross_by_pos = [h['gross_score'] for h in hs_rows]
            if not gross_by_pos:
                continue

            db.execute("DELETE FROM hole_scores WHERE scorecard_id = %s", (sc['scorecard_id'],))
            db.execute("UPDATE scorecards SET tee_id = NULL WHERE scorecard_id = %s", (sc['scorecard_id'],))

            for gross, new_hole in zip(gross_by_pos, new_holes):
                db.execute(
                    """INSERT INTO hole_scores
                       (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (sc['scorecard_id'], new_hole['hole_id'], new_hole['hole_number'],
                     gross, 0, gross - new_hole['par'])
                )

        db.execute("UPDATE rounds SET tee_id = %s WHERE round_id = %s", (new_tee_id, round_row['round_id']))

        _recalc_single_round(
            db, matchup_id, season_id, league_id,
            hcp_pct, max_hcp, scoring_mode,
            use_existing_hcp=True,
            absence_policy=absence_policy,
        )
        swapped += 1

    db.commit()

    for w in warnings:
        flash(w, 'warning')
    if swapped:
        flash(f'Side swapped for {swapped} group(s). All results recalculated.', 'success')

    return redirect(url_for('scores.enter_week', season_id=season_id, week_num=week_num,
                            course_id=new_tee['course_id'], tee_id=new_tee_id))


@bp.route('/clear/<int:matchup_id>', methods=['POST'])
@admin_required
def clear_scores(matchup_id):
    """Wipe all scores for a matchup and reset to not_started."""
    db = get_db()
    matchup = db.execute(
        "SELECT m.*, s.season_id FROM matchups m JOIN seasons s ON m.season_id = s.season_id WHERE m.matchup_id = %s AND s.league_id = %s",
        (matchup_id, session['league_id'])
    ).fetchone()
    if not matchup:
        flash('Matchup not found.', 'error')
        return redirect(url_for('seasons.index'))
    existing = db.execute("SELECT round_id FROM rounds WHERE matchup_id = %s", (matchup_id,)).fetchone()
    if existing:
        old_rid = existing['round_id']
        db.execute("DELETE FROM hole_scores WHERE scorecard_id IN (SELECT scorecard_id FROM scorecards WHERE round_id = %s)", (old_rid,))
        db.execute("DELETE FROM scorecards WHERE round_id = %s", (old_rid,))
        db.execute("UPDATE handicap_history SET trigger_round_id = NULL WHERE trigger_round_id = %s", (old_rid,))
        db.execute("DELETE FROM rounds WHERE round_id = %s", (old_rid,))
    db.execute("DELETE FROM match_results WHERE matchup_id = %s", (matchup_id,))
    db.execute("UPDATE matchups SET status = 'scheduled' WHERE matchup_id = %s", (matchup_id,))
    db.commit()
    flash('Scores cleared.', 'info')
    return_url = request.form.get('return_url', '').strip()
    if return_url:
        return redirect(return_url)
    return redirect(url_for('scores.enter_week',
                            season_id=matchup['season_id'],
                            week_num=matchup['week_number']))


# ---------------------------------------------------------------------------
# Print scorecards
# ---------------------------------------------------------------------------

@bp.route('/print-scorecards')
@admin_required
def print_scorecards():
    db         = get_db()
    league_id  = session['league_id']
    league_name = session.get('league_name', '')

    # ── Season ──────────────────────────────────────────────────────────────
    season_id = request.args.get('season_id', type=int)
    if not season_id:
        row = db.execute(
            "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
            (league_id,)
        ).fetchone()
        season_id = row['season_id'] if row else None
    if not season_id:
        flash('No seasons found.', 'error')
        return redirect(url_for('main.dashboard'))

    # ── Week ────────────────────────────────────────────────────────────────
    week_number = request.args.get('week_number', type=int)
    if not week_number:
        row = db.execute(
            """SELECT MIN(week_number) AS wn FROM matchups
               WHERE season_id = %s AND status = 'scheduled' AND is_bye = 0""",
            (season_id,)
        ).fetchone()
        week_number = (row['wn'] if row and row['wn'] else 1)

    available_weeks = db.execute(
        """SELECT DISTINCT week_number, scheduled_date FROM matchups
           WHERE season_id = %s AND is_bye = 0 ORDER BY week_number""",
        (season_id,)
    ).fetchall()

    # ── Options ─────────────────────────────────────────────────────────────
    display_format = request.args.get('format', 'group')
    if display_format not in ('group', 'matchup'):
        display_format = 'group'

    extra_tee_colors = set()
    for raw in request.args.get('extra_tees', '').split(','):
        c = raw.strip()
        if c:
            extra_tee_colors.add(c)

    # ── League settings (for playing handicap calc) ──────────────────────
    settings        = get_league_settings(db, season_id, league_id)
    handicap_pct    = float(settings['handicap_percent'])   if settings else 90.0
    max_hcap        = float(settings['max_handicap_index']) if settings else 18.0

    # ── Matchups for this week ───────────────────────────────────────────
    matchup_rows = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.tee_time,
                  m.starting_hole, m.course_id, m.tee_id, m.status,
                  c.course_name,
                  ht.team_id  AS t1_id,  ht.team_name  AS t1_name,
                  at2.team_id AS t2_id,  at2.team_name AS t2_name,
                  p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last,
                  p3.player_id AS p3_id, p3.first_name AS p3_first, p3.last_name AS p3_last,
                  p4.player_id AS p4_id, p4.first_name AS p4_first, p4.last_name AS p4_last
           FROM matchups m
           JOIN teams  ht  ON ht.team_id  = m.team1_id
           JOIN teams  at2 ON at2.team_id = m.team2_id
           JOIN players p1 ON p1.player_id = ht.player1_id
           JOIN players p2 ON p2.player_id = ht.player2_id
           JOIN players p3 ON p3.player_id = at2.player1_id
           JOIN players p4 ON p4.player_id = at2.player2_id
           LEFT JOIN courses c ON c.course_id = m.course_id
           WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
           ORDER BY m.tee_time NULLS LAST, m.matchup_id""",
        (season_id, week_number)
    ).fetchall()

    # ── Build per-matchup data ──────────────────────────────────────────
    def make_player(pid, first, last):
        hcp = get_player_handicap(db, pid, league_id=league_id)
        ph  = calc_playing_handicap(float(hcp or 0), handicap_pct, max_hcap)
        ph_display = int(ph) if ph == int(ph) else ph
        return {
            'player_id':      pid,
            'name':           first or last or 'Player',
            'full_name':      f"{first} {last}".strip(),
            'playing_handicap': ph,
            'hcp_display':    ph_display,
            'dots':           {},
        }

    def apply_dots(player, opponent_ph, mhcp_map, total_holes):
        # Dots show where THIS player receives strokes from their opponent.
        # Strokes = differential (this player's ph minus opponent's ph), allocated
        # to the hardest holes first via the M handicap index column.
        diff = player['playing_handicap'] - opponent_ph
        if diff > 0:
            hcp_idxs = list(mhcp_map.values())
            player['dots'] = {
                hn: strokes_on_hole(diff, hidx, total_holes, hcp_indices=hcp_idxs) > 0
                for hn, hidx in mhcp_map.items()
            }
        else:
            player['dots'] = {hn: False for hn in mhcp_map}

    matchups_data = []
    for m in matchup_rows:
        course_id = m['course_id']

        # All tees for this course
        all_tees = []
        if course_id:
            all_tees = db.execute(
                """SELECT tee_id, tee_name, tee_color, nine, gender, par_total, slope, rating
                   FROM tees WHERE course_id = %s ORDER BY gender, nine, tee_name""",
                (course_id,)
            ).fetchall()

        # Group tees by color (dedup M/F and front/back per color)
        from collections import defaultdict as _dd
        color_to_tees = _dd(list)
        seen_colors_ord = []
        seen_colors_set = set()
        for t in all_tees:
            color = (t['tee_color'] or t['tee_name'] or '').strip()
            if not color:
                continue
            color_to_tees[color].append(dict(t))
            if color not in seen_colors_set:
                seen_colors_ord.append(color)
                seen_colors_set.add(color)

        # Auto color = color of matchup's default tee; fall back to first course tee
        # so it stays stable when extras are added (prevents the "swap" bug)
        auto_color = None
        auto_nine  = None  # 'Front', 'Back', or None — used to filter tees to correct side
        if m['tee_id']:
            auto_meta = next((t for t in all_tees if t['tee_id'] == m['tee_id']), None)
            if auto_meta:
                auto_color = (auto_meta['tee_color'] or auto_meta['tee_name'] or '').strip()
                auto_nine  = auto_meta['nine']  # e.g. 'Front', 'Back', None
        if not auto_color and seen_colors_ord:
            auto_color = seen_colors_ord[0]

        # Display colors = auto (always present) + any extra colors that exist on this course
        display_colors = set()
        if auto_color:
            display_colors.add(auto_color)
        for ec in extra_tee_colors:
            if ec in color_to_tees:
                display_colors.add(ec)

        # Order: auto first, then others in DB order
        ordered_colors = []
        if auto_color and auto_color in display_colors:
            ordered_colors.append(auto_color)
        for c in seen_colors_ord:
            if c in display_colors and c not in ordered_colors:
                ordered_colors.append(c)

        tees_info  = []
        par_map    = {}   # hole_number → par
        mhcp_map   = {}   # hole_number → M handicap_index
        whcp_map   = {}   # hole_number → W handicap_index

        for color in ordered_colors:
            tee_rows = color_to_tees[color]

            # Filter to the correct nine (Front/Back) when the matchup tee specifies one
            if auto_nine:
                nine_filtered = [t for t in tee_rows if t['nine'] == auto_nine]
                if nine_filtered:
                    tee_rows = nine_filtered

            # Split by gender
            m_tees = [t for t in tee_rows if (t['gender'] or 'M').upper() == 'M']
            f_tees = [t for t in tee_rows if (t['gender'] or '').upper() in ('F', 'W')]
            if not m_tees:
                m_tees = tee_rows  # no gender differentiation — use all

            # Load M holes (yardages + hcp), combining any nines
            m_holes_map = {}
            for t in m_tees:
                holes = db.execute(
                    "SELECT hole_number, par, handicap_index, distance_yards FROM holes WHERE tee_id = %s ORDER BY hole_number",
                    (t['tee_id'],)
                ).fetchall()
                for h in holes:
                    m_holes_map[h['hole_number']] = dict(h)
            if not m_holes_map:
                continue
            m_holes = [m_holes_map[hn] for hn in sorted(m_holes_map.keys())]
            total_yds = sum(h['distance_yards'] or 0 for h in m_holes)

            tees_info.append({
                'label':       color,
                'gender':      None,   # no gender suffix — M/F merged
                'holes':       m_holes,
                'total_yards': total_yds or None,
                'is_auto':     color == auto_color,
            })

            if not par_map:
                par_map  = {h['hole_number']: h['par']            for h in m_holes}
            if not mhcp_map:
                mhcp_map = {h['hole_number']: h['handicap_index'] for h in m_holes}

            # F hcp — combine nines
            if not whcp_map and f_tees:
                f_hcp_map = {}
                for t in f_tees:
                    fh = db.execute(
                        "SELECT hole_number, handicap_index FROM holes WHERE tee_id = %s ORDER BY hole_number",
                        (t['tee_id'],)
                    ).fetchall()
                    for h in fh:
                        f_hcp_map[h['hole_number']] = h['handicap_index']
                if f_hcp_map:
                    whcp_map = f_hcp_map

        # Fallback: if no gendered split, use first tee for both
        if tees_info and not mhcp_map:
            mhcp_map = {h['hole_number']: h['handicap_index'] for h in tees_info[0]['holes']}
        if not par_map and tees_info:
            par_map  = {h['hole_number']: h['par']            for h in tees_info[0]['holes']}

        hole_nums   = sorted(par_map.keys())
        total_holes = len(hole_nums)

        # Split for 18-hole layout
        front_holes = [h for h in hole_nums if h <= 9]
        back_holes  = [h for h in hole_nums if h > 9]
        is_18       = len(hole_nums) > 9

        # Par totals for each half
        par_total_front = sum(par_map.get(h, 0) for h in front_holes) if front_holes else sum(par_map.values())
        par_total_back  = sum(par_map.get(h, 0) for h in back_holes)  if back_holes  else 0

        # Build players without dots first so all playing handicaps are known
        p1 = make_player(m['p1_id'], m['p1_first'], m['p1_last'])
        p2 = make_player(m['p2_id'], m['p2_first'], m['p2_last'])
        p3 = make_player(m['p3_id'], m['p3_first'], m['p3_last'])
        p4 = make_player(m['p4_id'], m['p4_first'], m['p4_last'])

        # Dots = differential strokes vs paired opponent (home.p1 vs away.p1, home.p2 vs away.p2)
        apply_dots(p1, p3['playing_handicap'], mhcp_map, total_holes)
        apply_dots(p3, p1['playing_handicap'], mhcp_map, total_holes)
        apply_dots(p2, p4['playing_handicap'], mhcp_map, total_holes)
        apply_dots(p4, p2['playing_handicap'], mhcp_map, total_holes)

        players = [p1, p2, p3, p4]

        matchups_data.append({
            'matchup_id':    m['matchup_id'],
            'course_name':   m['course_name'] or '—',
            'tee_time':      m['tee_time'],
            'starting_hole': m['starting_hole'] or 1,
            'scheduled_date': m['scheduled_date'],
            'status':        m['status'],
            't1_id':         m['t1_id'],
            't1_name':       m['t1_name'] or f"{m['p1_last']}/{m['p2_last']}",
            't2_id':         m['t2_id'],
            't2_name':       m['t2_name'] or f"{m['p3_last']}/{m['p4_last']}",
            'team1_players': players[:2],
            'team2_players': players[2:],
            'all_players':   players,
            'paired_a':      [p1, p3],
            'paired_b':      [p2, p4],
            'grouped_players': [p1, p3, p2, p4],
            'tees_info':        tees_info,
            'course_tee_colors': seen_colors_ord,
            'hole_nums':     hole_nums,
            'front_holes':   front_holes,
            'back_holes':    back_holes,
            'is_18':         is_18,
            'par_map':       par_map,
            'mhcp_map':      mhcp_map,
            'whcp_map':      whcp_map,
            'has_whcp':      bool(whcp_map),
            'par_total_front': par_total_front,
            'par_total_back':  par_total_back,
        })

    scheduled_date = matchup_rows[0]['scheduled_date'] if matchup_rows else None

    # Unique tee colors across the week (for the Extra Tees checkbox UI)
    all_tee_colors = []
    all_tee_colors_set = set()
    for md in matchups_data:
        for c in md.get('course_tee_colors', []):
            if c not in all_tee_colors_set:
                all_tee_colors.append(c)
                all_tee_colors_set.add(c)
    # Colors already in use as the auto-tee don't need to be in the extras checkbox list
    auto_colors = {md['tees_info'][0]['label'] for md in matchups_data if md['tees_info']}
    extra_only_colors = [c for c in all_tee_colors if c not in auto_colors]

    return render_template('scores/print_scorecards.html',
        matchups          = matchups_data,
        week_number       = week_number,
        scheduled_date    = scheduled_date,
        season_id         = season_id,
        available_weeks   = [dict(w) for w in available_weeks],
        display_format    = display_format,
        extra_tee_colors  = extra_tee_colors,
        all_tee_colors    = extra_only_colors,
        league_name       = league_name,
    )


# ---------------------------------------------------------------------------
# Shared helper: fetch all data needed to render a completed scorecard
# ---------------------------------------------------------------------------

def _load_completed_scorecard(db, matchup_id, scoring_mode=None):
    """Return dict with keys: round_row, holes, tee, course, view_groups, scoring_mode.
    Returns None if the round data doesn't exist."""
    round_row = db.execute(
        "SELECT * FROM rounds WHERE matchup_id = %s", (matchup_id,)
    ).fetchone()
    if not round_row:
        return None

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

    opp_map      = {}
    role_map     = {}
    pts_map      = {}
    overall_map  = {}
    for r in results:
        opp_map[r['player_id']]     = r['opponent_player_id']
        role_map[r['player_id']]    = r['role']
        pts_map[r['player_id']]     = r['total_points']
        overall_map[r['player_id']] = r['overall_point_won']

    hcp_map = {sc['player_id']: (sc['handicap_at_time_of_play'] or 0) for sc in scorecards}
    _hcp_idxs_all = [h['handicap_index'] for h in holes]
    n_holes_all = len(holes) or 9

    view_hole_pts = {}
    for pid, opp_id in opp_map.items():
        pts = []
        my_hs  = {h['hole_number']: h for h in hole_scores.get(pid, [])}
        opp_hs = {h['hole_number']: h for h in hole_scores.get(opp_id, [])}
        if scoring_mode != 'stableford':
            diff_mine = hcp_map.get(pid, 0) - hcp_map.get(opp_id, 0)
            diff_opp  = hcp_map.get(opp_id, 0) - hcp_map.get(pid, 0)
        for h in holes:
            n_mine = my_hs.get(h['hole_number'])
            n_opp  = opp_hs.get(h['hole_number'])
            if scoring_mode == 'stableford':
                if n_mine is None:
                    pts.append(None)
                else:
                    par = h['par'] if h['par'] else 4
                    pts.append(calc_stableford(n_mine['net_score'] - par))
            else:
                if n_mine is None or n_opp is None:
                    pts.append(None)
                else:
                    # Differential stroke allocation: only the higher-handicap
                    # player gets strokes, matching the match_results engine.
                    s_mine = strokes_on_hole(diff_mine, h['handicap_index'], n_holes_all,
                                              hcp_indices=_hcp_idxs_all) if diff_mine > 0 else 0
                    s_opp  = strokes_on_hole(diff_opp, h['handicap_index'], n_holes_all,
                                              hcp_indices=_hcp_idxs_all) if diff_opp > 0 else 0
                    dnet_mine = n_mine['gross_score'] - s_mine
                    dnet_opp  = n_opp['gross_score']  - s_opp
                    if dnet_mine < dnet_opp:
                        pts.append(2)
                    elif dnet_opp < dnet_mine:
                        pts.append(0)
                    else:
                        pts.append(1)
        view_hole_pts[pid] = pts

    sub_info_by_sub_pid = {}
    for sc in scorecards:
        if sc['is_sub'] and sc['sub_for_player_id']:
            absent_p = db.execute(
                "SELECT first_name, last_name FROM players WHERE player_id = %s",
                (sc['sub_for_player_id'],)
            ).fetchone()
            if absent_p:
                sub_info_by_sub_pid[sc['player_id']] = \
                    f"{absent_p['first_name']} {absent_p['last_name']}"
    if not sub_info_by_sub_pid:
        try:
            absence_rows = db.execute(
                "SELECT * FROM player_absences WHERE matchup_id = %s AND sub_player_id IS NOT NULL",
                (matchup_id,)
            ).fetchall()
            for ar in absence_rows:
                absent_p = db.execute(
                    "SELECT first_name, last_name FROM players WHERE player_id = %s",
                    (ar['player_id'],)
                ).fetchone()
                if absent_p:
                    sub_info_by_sub_pid[ar['sub_player_id']] = \
                        f"{absent_p['first_name']} {absent_p['last_name']}"
        except Exception:
            pass

    # Absence info for view display: pid -> excused (None if not absent)
    absence_view = {}
    try:
        for ar in db.execute(
            "SELECT player_id, excused FROM player_absences WHERE matchup_id = %s AND sub_player_id IS NULL",
            (matchup_id,)
        ).fetchall():
            absence_view[ar['player_id']] = ar['excused'] or 0
    except Exception:
        pass

    matchup_row = db.execute("SELECT team1_id, team2_id FROM matchups WHERE matchup_id = %s", (matchup_id,)).fetchone()
    t1_id = matchup_row['team1_id']
    t2_id = matchup_row['team2_id']

    # Why each player's handicap for this round isn't a plain averaged index —
    # a manual override always wins over a pre-eligibility provisional value
    # for what's actually used (see _recalc_single_round's playing_hcps
    # priority order), so it takes priority here too.
    hcp_marker_map = {}
    override_ids = {sc['player_id'] for sc in scorecards if sc['hcp_manually_overridden']}
    prov_rows = db.execute(
        """SELECT player_id FROM handicap_history
            WHERE trigger_round_id = %s AND override_reason LIKE %s""",
        (round_row['round_id'], f'{PRE_ELIGIBILITY_MARKER_PREFIX}%')
    ).fetchall()
    prov_ids = {r['player_id'] for r in prov_rows}
    for sc in scorecards:
        pid = sc['player_id']
        if pid in override_ids:
            hcp_marker_map[pid] = 'override'
        elif pid in prov_ids:
            hcp_marker_map[pid] = 'provisional'

    def build_team_group(team_id):
        scs = [sc for sc in scorecards if sc['team_id'] == team_id]
        scs.sort(key=lambda x: role_map.get(x['player_id'], 'Z'))
        group = []
        for sc in scs:
            pid = sc['player_id']
            hs  = hole_scores.get(pid, [])
            sc_tee_name = None
            if sc['tee_id'] and sc['tee_id'] != round_row['tee_id']:
                tee_row = db.execute(
                    "SELECT tee_name, nine FROM tees WHERE tee_id = %s", (sc['tee_id'],)
                ).fetchone()
                if tee_row:
                    sc_tee_name = f"{tee_row['tee_name']} ({tee_row['nine']})"
            ph = sc['handicap_at_time_of_play'] or 0
            n_holes = len(holes) or 9
            _hcp_idxs = [h['handicap_index'] for h in holes]
            stroke_dots = [strokes_on_hole(ph, h['handicap_index'], n_holes,
                                           hcp_indices=_hcp_idxs) for h in holes]
            group.append({
                'pid':          pid,
                'name':         sc['first_name'],
                'role':         role_map.get(pid, '?'),
                'hcp':          sc['handicap_at_time_of_play'],
                'gross_scores': [h['gross_score'] for h in hs],
                'net_scores':   [h['net_score']   for h in hs],
                'total_gross':  sum(h['gross_score'] for h in hs) if hs else 0,
                'total_net':    sum(h['net_score']   for h in hs) if hs else 0,
                'hole_pts':     view_hole_pts.get(pid, []),
                'total_pts':    pts_map.get(pid, 0),
                'overall_pts':  overall_map.get(pid, None),
                'team_label':   f"{sc['t_p1_last'] or '?'} / {sc['t_p2_last'] or '?'}",
                'sub_for':      sub_info_by_sub_pid.get(pid),
                'is_sub':       bool(sc['is_sub']),
                'tee_name':     sc_tee_name,
                'stroke_dots':  stroke_dots,
                'is_absent':    bool(sc['is_absent'] if 'is_absent' in sc.keys() else 0),
                'is_excused':   absence_view.get(pid, 1),
                'hcp_marker':   hcp_marker_map.get(pid),
            })
        return group

    t1_group = build_team_group(t1_id)
    t2_group = build_team_group(t2_id)
    all_players = t1_group + t2_group
    a_pair = [p for p in all_players if p['role'] == 'A']
    b_pair = [p for p in all_players if p['role'] == 'B']
    view_groups = [a_pair, b_pair]

    # Recalculate stroke_dots using differential vs opponent so only the higher-
    # handicap player receives dots; the lower-handicap player gets none.
    n_holes = len(holes) or 9
    _hcp_idxs = [h['handicap_index'] for h in holes]
    for pair in view_groups:
        if len(pair) == 2:
            ph0 = pair[0]['hcp'] or 0
            ph1 = pair[1]['hcp'] or 0
            diff0 = ph0 - ph1
            diff1 = ph1 - ph0
            pair[0]['stroke_dots'] = [strokes_on_hole(diff0, h['handicap_index'], n_holes,
                                                       hcp_indices=_hcp_idxs) if diff0 > 0 else 0 for h in holes]
            pair[1]['stroke_dots'] = [strokes_on_hole(diff1, h['handicap_index'], n_holes,
                                                       hcp_indices=_hcp_idxs) if diff1 > 0 else 0 for h in holes]

    all_pids = [g['pid'] for grp in view_groups for g in grp]
    nickname_map = _get_nickname_map(db, all_pids)
    for grp in view_groups:
        for g in grp:
            g['nickname'] = nickname_map.get(g['pid'])

    return {
        'round_row':    round_row,
        'holes':        holes,
        'tee':          tee,
        'course':       course,
        'view_groups':  view_groups,
        'scoring_mode': scoring_mode or 'match_play',
    }


# ---------------------------------------------------------------------------
# View completed scorecard
# ---------------------------------------------------------------------------

@bp.route('/view/<int:matchup_id>')
@login_required
def view(matchup_id):
    db = get_db()

    matchup = db.execute(
        """SELECT m.*, s.season_name, s.league_id, s.season_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = %s""",
        (matchup_id,)
    ).fetchone()

    if not matchup or matchup['league_id'] != session['league_id']:
        flash('Matchup not found.', 'error')
        return redirect(url_for('seasons.index'))

    if matchup['status'] != 'completed':
        return redirect(url_for('scores.enter', matchup_id=matchup_id))

    view_settings = get_league_settings(db, matchup['season_id'], matchup['league_id'])
    scoring_mode = _settings_scoring_mode(view_settings)

    sc_data = _load_completed_scorecard(db, matchup_id, scoring_mode)
    if not sc_data:
        flash('Score data not found for this matchup.', 'error')
        return redirect(url_for('seasons.index'))

    return render_template('scores/view.html',
                           matchup=matchup,
                           round_row=sc_data['round_row'],
                           holes=sc_data['holes'],
                           view_groups=sc_data['view_groups'],
                           tee=sc_data['tee'],
                           course=sc_data['course'],
                           scoring_mode=sc_data['scoring_mode'])


# ---------------------------------------------------------------------------
# Week-level score entry (all matchups for a week on one page)
# ---------------------------------------------------------------------------

@bp.route('/enter-week/current')
@admin_required
def enter_week_current():
    """Redirect to week entry for the upcoming (or most recent) week."""
    db = get_db()
    season = db.execute(
        "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (session['league_id'],)
    ).fetchone()
    if not season:
        flash('No seasons found.', 'error')
        return redirect(url_for('seasons.index'))
    season_id = season['season_id']

    # Land on the most recent week by date (scheduled_date <= today).
    # Falls back to the next upcoming week if the season hasn't started yet.
    from datetime import date as _date
    today = _date.today().isoformat()
    row = db.execute(
        """SELECT week_number AS wn FROM matchups
           WHERE season_id = %s AND is_bye = 0
             AND week_type NOT IN ('League Bye')
             AND scheduled_date IS NOT NULL AND scheduled_date <= %s
           ORDER BY scheduled_date DESC LIMIT 1""",
        (season_id, today)
    ).fetchone()
    week_num = row['wn'] if row and row['wn'] else None
    if not week_num:
        # Season hasn't started yet — land on the earliest upcoming week
        row2 = db.execute(
            """SELECT week_number AS wn FROM matchups
               WHERE season_id = %s AND is_bye = 0
               ORDER BY scheduled_date ASC LIMIT 1""",
            (season_id,)
        ).fetchone()
        week_num = row2['wn'] if row2 and row2['wn'] else 1

    return redirect(url_for('scores.enter_week', season_id=season_id, week_num=week_num))


@bp.route('/enter-week/<int:season_id>/<int:week_num>', methods=['GET'])
@admin_required
def enter_week(season_id, week_num):
    """Week-level score entry: all matchups for the week on one page."""
    db = get_db()
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    # All non-bye matchups for this week
    matchup_rows = db.execute(
        """SELECT m.*, s.season_name, s.league_id, s.season_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
           ORDER BY m.tee_time NULLS LAST, m.matchup_id""",
        (season_id, week_num)
    ).fetchall()

    if not matchup_rows:
        flash('No matchups found for this week.', 'info')
        return redirect(url_for('schedule.index', season_id=season_id, week=week_num))

    # Available weeks for the nav dropdown
    week_options = db.execute(
        "SELECT DISTINCT week_number, scheduled_date FROM matchups WHERE season_id = %s AND is_bye = 0 ORDER BY week_number",
        (season_id,)
    ).fetchall()

    # Shared course/tee from query params, then from first matchup with an assignment
    selected_course_id = request.args.get('course_id')
    selected_tee_id    = request.args.get('tee_id')
    if not selected_course_id:
        for mr in matchup_rows:
            if mr['course_id']:
                selected_course_id = str(mr['course_id'])
                break
    if not selected_tee_id and selected_course_id:
        for mr in matchup_rows:
            if mr['tee_id']:
                selected_tee_id = str(mr['tee_id'])
                break
    if not selected_tee_id and selected_course_id:
        crow = db.execute(
            "SELECT default_tee_id FROM courses WHERE course_id = %s", (int(selected_course_id),)
        ).fetchone()
        if crow and crow['default_tee_id']:
            selected_tee_id = str(crow['default_tee_id'])

    courses = db.execute(
        "SELECT course_id, course_name FROM courses WHERE league_id = %s OR league_id IS NULL ORDER BY course_name",
        (session['league_id'],)
    ).fetchall()

    tees = []
    player_tees = []  # deduplicated by color for per-player tee dropdown
    holes = []
    nine_options = []
    all_tee_hcp = {}
    nine_label_map = {'front': 'Front 9', 'back': 'Back 9', 'full': 'Full 18'}
    course_default_tid = None  # resolved M-rep tee_id from course.default_tee_id
    if selected_course_id:
        tees = db.execute(
            """SELECT tee_id, tee_name, tee_color, nine, gender, par_total, slope, rating
               FROM tees WHERE course_id = %s ORDER BY gender, tee_name, nine""",
            (int(selected_course_id),)
        ).fetchall()
        seen_nines = {}
        for t in tees:
            n = t['nine'] or 'full'
            if n not in seen_nines:
                seen_nines[n] = {'nine': n, 'label': nine_label_map.get(n, n.title()), 'tee_id': t['tee_id']}
            if selected_tee_id and str(t['tee_id']) == str(selected_tee_id):
                seen_nines[n]['tee_id'] = t['tee_id']
        nine_options = list(seen_nines.values())
        for t in tees:
            th = db.execute(
                "SELECT hole_number, handicap_index FROM holes WHERE tee_id = %s ORDER BY hole_number",
                (t['tee_id'],)
            ).fetchall()
            all_tee_hcp[t['tee_id']] = [r['handicap_index'] for r in th]

        # Build player_tees: deduplicated by color for the selected nine (mirrors enter() logic)
        if selected_tee_id:
            _sel_nine = next((t['nine'] for t in tees if str(t['tee_id']) == str(selected_tee_id)), None)
            _pt_seen = {}
            for t in tees:
                if _sel_nine and t['nine'] != _sel_nine:
                    continue
                color = (t['tee_color'] or t['tee_name'] or '').strip()
                if not color:
                    continue
                if color not in _pt_seen:
                    _pt_seen[color] = dict(t)
                elif (t['gender'] or 'M').upper() == 'M' and (_pt_seen[color]['gender'] or 'M').upper() != 'M':
                    _pt_seen[color] = dict(t)
            player_tees = list(_pt_seen.values())

            # Resolve course default tee through M-rep map
            color_to_rep = {(pt.get('tee_color') or pt.get('tee_name') or '').strip(): pt['tee_id']
                            for pt in player_tees}
            try:
                crow = db.execute(
                    "SELECT default_tee_id FROM courses WHERE course_id=%s", (selected_course_id,)
                ).fetchone()
                if crow and crow['default_tee_id']:
                    cd = next((t for t in tees if t['tee_id'] == crow['default_tee_id']), None)
                    if cd and cd['nine'] == _sel_nine:
                        c = (cd.get('tee_color') or cd.get('tee_name') or '').strip()
                        course_default_tid = color_to_rep.get(c, crow['default_tee_id'])
            except Exception:
                pass
    if selected_tee_id:
        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (int(selected_tee_id),)
        ).fetchall()

    settings = get_league_settings(db, season_id, session['league_id'])
    hpct = float(settings['handicap_percent']) if settings else 90.0
    hmax = float(settings['max_handicap_index']) if settings else 18.0
    scoring_mode = _settings_scoring_mode(settings)
    min_rounds_for_hcp = int(settings['min_rounds_for_handicap']) if settings else 2

    all_players = db.execute(
        "SELECT player_id, first_name, last_name FROM players WHERE league_id = %s AND active = 1 ORDER BY last_name, first_name",
        (session['league_id'],)
    ).fetchall()

    matchups_data = []
    for mr in matchup_rows:
        if mr['status'] == 'completed':
            sc_data = _load_completed_scorecard(db, mr['matchup_id'], scoring_mode)
            # Build matchup label from view_groups team labels
            if sc_data and sc_data['view_groups']:
                seen_labels = []
                for grp in sc_data['view_groups']:
                    for p in (grp or []):
                        if p['team_label'] not in seen_labels:
                            seen_labels.append(p['team_label'])
                c_matchup_label = ' vs '.join(seen_labels)
            else:
                c_matchup_label = ''
            matchups_data.append({
                'matchup':        dict(mr),
                'completed':      True,
                'sc_data':        sc_data,
                'matchup_label':  c_matchup_label,
            })
            continue

        team1 = db.execute(
            """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                           p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
               FROM teams t LEFT JOIN players p1 ON t.player1_id = p1.player_id
               LEFT JOIN players p2 ON t.player2_id = p2.player_id
               WHERE t.team_id = %s""", (mr['team1_id'],)
        ).fetchone()
        team2 = db.execute(
            """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                           p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
               FROM teams t LEFT JOIN players p1 ON t.player1_id = p1.player_id
               LEFT JOIN players p2 ON t.player2_id = p2.player_id
               WHERE t.team_id = %s""", (mr['team2_id'],)
        ).fetchone()
        if not team1 or not team2:
            continue

        sub_assignments = _get_sub_assignments(db, mr['matchup_id'])
        absence_records = _get_all_absence_records(db, mr['matchup_id'])
        players = _build_player_list(db, season_id, team1, team2, sub_assignments, league_id=session.get('league_id'))
        raw_players = _build_raw_player_list(db, team1, team2, absence_records)
        nickname_map = _get_nickname_map(db, [p['player_id'] for p in players])

        if holes:
            for p in players:
                p['playing_handicap'] = calc_playing_handicap(p['handicap_index'], hpct, hmax)

            # For rounds that already have scorecards (e.g. reopened completed rounds),
            # override playing_handicap with the stored value so the edit form shows
            # what was actually used at time of play.
            _ew_rd = db.execute(
                "SELECT round_id FROM rounds WHERE matchup_id = %s", (mr['matchup_id'],)
            ).fetchone()
            if _ew_rd:
                _ew_sc_hcps = db.execute(
                    """SELECT player_id, handicap_at_time_of_play FROM scorecards
                       WHERE round_id = %s AND handicap_at_time_of_play IS NOT NULL""",
                    (_ew_rd['round_id'],)
                ).fetchall()
                if _ew_sc_hcps:
                    _ew_hcp_map = {row['player_id']: int(round(float(row['handicap_at_time_of_play']))) for row in _ew_sc_hcps}
                    for p in players:
                        if p['player_id'] in _ew_hcp_map:
                            p['playing_handicap'] = _ew_hcp_map[p['player_id']]

            # Flag players whose handicap for THIS round isn't a plain averaged
            # index — either a manual override or a pre-eligibility provisional
            # value. A manual override always wins for what's actually used
            # (see _recalc_single_round's playing_hcps priority order), so it
            # takes priority here too even if the player is also pre-eligibility.
            if _ew_rd:
                _ew_override_rows = db.execute(
                    """SELECT player_id FROM scorecards
                        WHERE round_id = %s AND hcp_manually_overridden = 1""",
                    (_ew_rd['round_id'],)
                ).fetchall()
                _ew_override_ids = {r['player_id'] for r in _ew_override_rows}

                _ew_prov_rows = db.execute(
                    """SELECT player_id FROM handicap_history
                        WHERE trigger_round_id = %s AND override_reason LIKE %s""",
                    (_ew_rd['round_id'], f'{PRE_ELIGIBILITY_MARKER_PREFIX}%')
                ).fetchall()
                _ew_prov_ids = {r['player_id'] for r in _ew_prov_rows}

                for p in players:
                    pid = p['player_id']
                    if pid in _ew_override_ids:
                        p['hcp_marker'] = 'override'
                    elif pid in _ew_prov_ids:
                        p['hcp_marker'] = 'provisional'

            for team_num in [1, 2]:
                tp = sorted([p for p in players if p['team_num'] == team_num], key=lambda x: x['playing_handicap'])
                for i, p in enumerate(tp):
                    p['role'] = 'A' if i == 0 else 'B'
            players.sort(key=lambda p: (p['team_num'], p.get('role', 'Z')))

            # Mark players whose next round is their handicap-eligibility round
            _elig = _detect_eligibility_rounds(
                db, [p['player_id'] for p in players], session['league_id'], min_rounds_for_hcp
            )
            for p in players:
                # A manual override always wins over the eligibility-round
                # notice — show the editable field + override marker instead
                # of hiding it behind the forward-looking ℹ button.
                if p.get('hcp_marker') == 'override':
                    continue
                if p['player_id'] in _elig:
                    p['hcp_eligibility_round'] = True
                    p['rounds_so_far'] = _elig[p['player_id']]

        player_default_tees = {}
        if player_tees and selected_tee_id:
            color_to_rep = {(pt.get('tee_color') or pt.get('tee_name') or '').strip(): pt['tee_id']
                            for pt in player_tees}
            selected_nine = next((t['nine'] for t in tees if str(t['tee_id']) == str(selected_tee_id)), None)
            tee_name_to_id = {}
            if selected_nine:
                for t in tees:
                    if t['nine'] == selected_nine and t['tee_name'] not in tee_name_to_id:
                        tee_name_to_id[t['tee_name']] = t['tee_id']

            def _ew_resolve(tid):
                t = next((x for x in tees if x['tee_id'] == tid), None)
                if not t:
                    return tid
                c = (t.get('tee_color') or t.get('tee_name') or '').strip()
                return color_to_rep.get(c, tid)

            base_tid = _ew_resolve(course_default_tid) if course_default_tid else int(selected_tee_id)
            pids = [p['player_id'] for p in players]
            pref_map = {}
            if pids:
                placeholders = ','.join(['%s'] * len(pids))
                try:
                    rows = db.execute(
                        f"SELECT player_id, preferred_tee_name FROM players WHERE player_id IN ({placeholders})",
                        pids
                    ).fetchall()
                    pref_map = {r['player_id']: r['preferred_tee_name'] for r in rows if r['preferred_tee_name']}
                except Exception:
                    pass
            for p in players:
                pid = p['player_id']
                pref = pref_map.get(pid)
                if pref and pref in tee_name_to_id:
                    player_default_tees[pid] = _ew_resolve(tee_name_to_id[pref])
                else:
                    player_default_tees[pid] = base_tid

        # Load existing hole scores for pre-population (in_progress rounds)
        existing_scores = {}
        ex_round = db.execute("SELECT round_id FROM rounds WHERE matchup_id = %s", (mr['matchup_id'],)).fetchone()
        if ex_round:
            scs = db.execute("SELECT scorecard_id, player_id FROM scorecards WHERE round_id = %s", (ex_round['round_id'],)).fetchall()
            for sc in scs:
                hs = db.execute("SELECT hole_number, gross_score FROM hole_scores WHERE scorecard_id = %s", (sc['scorecard_id'],)).fetchall()
                for h in hs:
                    existing_scores[f"{sc['player_id']}_{h['hole_number']}"] = h['gross_score']

        t1_label = team1['team_name'] or f"{team1['p1_last'] or ''}/{team1['p2_last'] or ''}"
        t2_label = team2['team_name'] or f"{team2['p1_last'] or ''}/{team2['p2_last'] or ''}"
        matchups_data.append({
            'matchup':        dict(mr),
            'team1':          team1,
            'team2':          team2,
            'players':        players,
            'raw_players':    raw_players,
            'nickname_map':   nickname_map,
            'sub_assignments': sub_assignments,
            'absence_records': absence_records,
            'player_default_tees': player_default_tees,
            'existing_scores': existing_scores,
            'completed':      False,
            'matchup_label':  f"{t1_label} vs {t2_label}",
        })

    week_date = None
    for mr in matchup_rows:
        if mr['scheduled_date']:
            week_date = mr['scheduled_date']
            break

    return render_template('scores/enter_week.html',
                           season=season,
                           week_num=week_num,
                           week_date=week_date,
                           week_options=[(r['week_number'], r['scheduled_date']) for r in week_options],
                           matchups_data=matchups_data,
                           courses=courses,
                           tees=tees,
                           player_tees=player_tees,
                           nine_options=nine_options,
                           holes=holes,
                           all_tee_hcp=all_tee_hcp,
                           selected_course_id=str(selected_course_id or ''),
                           selected_tee_id=str(selected_tee_id or ''),
                           scoring_mode=scoring_mode,
                           all_players=all_players)
