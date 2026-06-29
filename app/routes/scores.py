from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db, table_exists
from routes.auth import login_required, admin_required
from datetime import datetime
import math
from routes.handicap import recalc_handicap_for_player
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

        for team_num in [1, 2]:
            tp = sorted([p for p in players if p['team_num'] == team_num],
                        key=lambda x: x['playing_handicap'])
            for i, p in enumerate(tp):
                p['role'] = 'A' if i == 0 else 'B'
        def sort_key(p):
            return (p['team_num'], p.get('role', 'Z'))
        players.sort(key=sort_key)

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


def _recalc_future_rounds(db, player_ids, season_id, league_id, after_round_date):
    """
    After a late score entry, re-derive A/B roles, net scores, and match
    results for all completed rounds played after after_round_date.

    Only runs when the late entry predates existing completed rounds.
    """
    import logging
    log = logging.getLogger(__name__)

    settings = get_league_settings(db, season_id, league_id)
    if not settings:
        return
    handicap_percent = float(settings['handicap_percent'])
    max_handicap     = float(settings['max_handicap_index'])
    scoring_mode     = _settings_scoring_mode(settings)

    # Find every completed matchup in this season played after the late entry
    # where at least one of the affected players participated.
    if not player_ids:
        return
    placeholders = ','.join(['%s'] * len(player_ids))
    future_matchup_ids = db.execute(
        f"""SELECT DISTINCT r.matchup_id
              FROM rounds r
              JOIN scorecards sc ON sc.round_id = r.round_id
             WHERE r.season_id = %s
               AND r.round_date > %s
               AND sc.player_id IN ({placeholders})
               AND r.matchup_id IS NOT NULL
             ORDER BY r.round_date ASC""",
        [season_id, after_round_date] + list(player_ids)
    ).fetchall()

    for row in future_matchup_ids:
        mid = row['matchup_id']
        try:
            _recalc_single_round(db, mid, season_id, league_id,
                                 handicap_percent, max_handicap, scoring_mode)
        except Exception as e:
            log.error('Late-entry cascade failed for matchup %s: %s', mid, e)


def _recalc_single_round(db, matchup_id, season_id, league_id,
                         handicap_percent, max_handicap, scoring_mode,
                         use_existing_hcp=False):
    """Re-score one completed round with current handicaps and re-write results."""
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

    # Current handicap for each player (latest handicap_history entry)
    def current_handicap(pid):
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
        if use_existing_hcp and sc['handicap_at_time_of_play'] is not None:
            playing_hcps[pid] = int(round(float(sc['handicap_at_time_of_play'])))
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
            hx, hy = 0.0, 0.0
            for i in range(len(p_holes_x)):
                px, py = calc_match_play(net[pid_x][i], net[pid_y][i])
                hx += px; hy += py
            gx = sum(g for g in gross[pid_x] if g is not None)
            gy = sum(g for g in gross[pid_y] if g is not None)
            ox, oy = calc_match_play(gx, gy)
            return hx, hy, ox, oy

    def _apply_absent_forfeit_recalc(result, pid_x, pid_y):
        hx, hy, ox, oy = result
        if pid_x in absent_sc and not absent_sc[pid_x]:
            ox, oy = 0, 1
        elif pid_y in absent_sc and not absent_sc[pid_y]:
            ox, oy = 1, 0
        return hx, hy, ox, oy

    aa = _apply_absent_forfeit_recalc(match_result(t1_a, t2_a), t1_a, t2_a)
    bb = _apply_absent_forfeit_recalc(match_result(t1_b, t2_b), t1_b, t2_b)

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
            if pid in gross and all(g is None for g in gross[pid]):
                absent_player_pids_raw[pid] = row['excused'] or 0
    except Exception as _ab_err:
        import logging
        logging.getLogger(__name__).error('Absence detection failed for matchup %s: %s', matchup['matchup_id'], _ab_err)

    # League settings
    settings = get_league_settings(db, season_id, league_id)
    handicap_percent = float(settings['handicap_percent']) if settings else 90.0
    max_handicap     = float(settings['max_handicap_index']) if settings else 18.0
    scoring_mode = _settings_scoring_mode(settings)

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
                if s is None:
                    continue  # absent player — ghost scores not yet synthesized
                if s > max_per_hole:
                    violations.append(f"{p['first_name']} {p['last_name']} hole {h['hole_number']} ({s} > max {max_per_hole})")
        if violations:
            msg = 'Score exceeds league max per hole: ' + '; '.join(violations)
            if score_action == 'block':
                flash(msg, 'error')
                return redirect(url_for('scores.enter', matchup_id=matchup['matchup_id']))
            else:
                flash(msg, 'warning')

    # Playing handicaps
    playing_hcps = {}
    for p in players:
        pid = p['player_id']
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
            # Hole-by-hole: net comparison
            hole_pts_x, hole_pts_y = 0.0, 0.0
            for i in range(len(p_holes_x)):
                nx, ny = net[pid_x][i], net[pid_y][i]
                if nx is None or ny is None:
                    continue
                px, py = calc_match_play(nx, ny)
                hole_pts_x += px
                hole_pts_y += py
            # Overall: gross comparison (matches frontend display)
            gross_x = [g for g in gross[pid_x] if g is not None]
            gross_y = [g for g in gross[pid_y] if g is not None]
            if gross_x and gross_y:
                overall_x, overall_y = calc_match_play(sum(gross_x), sum(gross_y))
            else:
                overall_x, overall_y = 0, 0
            return hole_pts_x, hole_pts_y, overall_x, overall_y

    def _apply_absent_forfeit(result, pid_x, pid_y):
        """Unexcused absent player forfeits the overall point to their opponent."""
        hx, hy, ox, oy = result
        if pid_x in absent_players and not absent_players[pid_x]:
            ox, oy = 0, 1
        elif pid_y in absent_players and not absent_players[pid_y]:
            ox, oy = 1, 0
        return hx, hy, ox, oy

    aa = _apply_absent_forfeit(match_result(t1_a, t2_a), t1_a, t2_a)
    bb = _apply_absent_forfeit(match_result(t1_b, t2_b), t1_b, t2_b)

    # --- Save to db ---
    # Guard against duplicate submission; allow re-save of in-progress rounds
    existing = db.execute(
        "SELECT round_id FROM rounds WHERE matchup_id = %s", (matchup['matchup_id'],)
    ).fetchone()
    if existing:
        # Wipe previous data (in_progress or completed) before re-saving
        old_rid = existing['round_id']
        # Capture any manually-overridden playing handicaps before deleting scorecards
        _hcp_overrides = {
            row['player_id']: row['handicap_at_time_of_play']
            for row in db.execute(
                "SELECT player_id, handicap_at_time_of_play FROM scorecards WHERE round_id = %s AND hcp_manually_overridden = 1",
                (old_rid,)
            ).fetchall()
        }
        db.execute("DELETE FROM hole_scores WHERE scorecard_id IN "
                   "(SELECT scorecard_id FROM scorecards WHERE round_id = %s)", (old_rid,))
        db.execute("DELETE FROM scorecards WHERE round_id = %s", (old_rid,))
        db.execute("DELETE FROM match_results WHERE matchup_id = %s", (matchup['matchup_id'],))
        db.execute("UPDATE player_absences SET round_id = NULL WHERE round_id = %s", (old_rid,))
        db.execute("UPDATE handicap_history SET trigger_round_id = NULL WHERE trigger_round_id = %s", (old_rid,))
        db.execute("DELETE FROM rounds WHERE round_id = %s", (old_rid,))
    else:
        _hcp_overrides = {}

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
        sc_row = db.execute(
            """INSERT INTO scorecards
               (round_id, player_id, team_id, handicap_at_time_of_play,
                is_sub, sub_for_player_id, approved, tee_id, is_absent)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s) RETURNING scorecard_id""",
            (round_id, pid, p['team_id'], playing_hcps[pid],
             is_sub_flag, sub_for_pid, p_tee_id, is_absent_flag)
        )
        sc_id = sc_row.fetchone()['scorecard_id']
        # Restore manual playing handicap override if one existed for this player
        if pid in _hcp_overrides:
            db.execute(
                "UPDATE scorecards SET handicap_at_time_of_play = %s, hcp_manually_overridden = 1 WHERE scorecard_id = %s",
                (_hcp_overrides[pid], sc_id)
            )
            playing_hcps[pid] = _hcp_overrides[pid]  # keep net score calc consistent
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

        # Handicap recalc
        try:
            for p in players:
                recalc_handicap_for_player(db, p['player_id'], season_id, league_id,
                                            trigger_round_id=round_id)
            db.commit()
        except Exception as hcap_err:
            import logging
            logging.getLogger(__name__).error('Handicap recalc failed: %s', hcap_err)
            flash('Scores saved, but handicap recalculation failed — recalculate manually.', 'warning')

        # Late-entry cascade: if this round predates existing completed rounds,
        # re-score those future rounds with updated handicaps and A/B roles.
        try:
            _recalc_future_rounds(
                db,
                player_ids=[p['player_id'] for p in players],
                season_id=season_id,
                league_id=league_id,
                after_round_date=round_date,
            )
            db.commit()
        except Exception as cascade_err:
            import logging
            logging.getLogger(__name__).error('Late-entry cascade failed: %s', cascade_err)
            flash('Scores saved. Retroactive re-scoring of future rounds failed — recalculate manually.', 'warning')

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
    db.execute("DELETE FROM match_results WHERE matchup_id = %s", (matchup_id,))
    db.execute("UPDATE matchups SET status = 'in_progress' WHERE matchup_id = %s", (matchup_id,))
    db.commit()
    return_url = request.form.get('return_url', '').strip()
    if return_url:
        return redirect(return_url + f'#ew-block-{matchup_id}')
    return redirect(url_for('scores.enter', matchup_id=matchup_id))


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

    view_hole_pts = {}
    for pid, opp_id in opp_map.items():
        pts = []
        my_hs  = {h['hole_number']: h for h in hole_scores.get(pid, [])}
        opp_hs = {h['hole_number']: h for h in hole_scores.get(opp_id, [])}
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
                elif n_mine['net_score'] < n_opp['net_score']:
                    pts.append(2)
                elif n_opp['net_score'] < n_mine['net_score']:
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

            for team_num in [1, 2]:
                tp = sorted([p for p in players if p['team_num'] == team_num], key=lambda x: x['playing_handicap'])
                for i, p in enumerate(tp):
                    p['role'] = 'A' if i == 0 else 'B'
            players.sort(key=lambda p: (p['team_num'], p.get('role', 'Z')))

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
