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
    ph = round(handicap_index * (handicap_percent / 100), 1)
    return min(ph, max_handicap)


def strokes_on_hole(playing_handicap, hole_hcp_index, total_holes=9):
    if hole_hcp_index is None:
        return 0
    ph = playing_handicap
    strokes = 0
    if ph >= hole_hcp_index:
        strokes += 1
    if ph >= total_holes + hole_hcp_index:
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

    if matchup['status'] == 'completed':
        if request.method == 'POST':
            flash('Scores for this matchup have already been recorded by another admin.', 'warning')
        return redirect(url_for('scores.view', matchup_id=matchup_id))

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
    holes = []
    all_tee_hcp = {}   # {tee_id: [hcp_index_per_hole, ...]} for JS live calc
    if selected_course_id:
        tees = db.execute(
            """SELECT tee_id, tee_name, nine, gender, par_total, slope, rating
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
        nine_options = list(seen_nines.values())

        # Pre-load all tees' hole HCP data for per-player tee support
        for t in tees:
            th = db.execute(
                "SELECT hole_number, handicap_index FROM holes WHERE tee_id = %s ORDER BY hole_number",
                (t['tee_id'],)
            ).fetchall()
            all_tee_hcp[t['tee_id']] = [row['handicap_index'] for row in th]
    if selected_tee_id:
        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (int(selected_tee_id),)
        ).fetchall()
        # P2-2: warn if any hole is missing a handicap index (breaks stroke allocation)
        null_hcp_holes = [h['hole_number'] for h in holes if h['handicap_index'] is None]
        if null_hcp_holes:
            flash(f"Tee is missing handicap index on hole(s) {', '.join(str(n) for n in null_hcp_holes)} — stroke allocation will be incorrect until course data is fixed.", 'warning')

    # All active players for sub dropdown
    all_players = db.execute(
        """SELECT player_id, first_name, last_name FROM players
           WHERE league_id = %s AND active = 1
           ORDER BY last_name, first_name""",
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
        if settings:
            try:
                enter_scoring_mode = settings['scoring_mode'] or 'match_play'
            except (IndexError, KeyError):
                enter_scoring_mode = 'match_play'
        for p in players:
            p['playing_hcp'] = calc_playing_handicap(p['handicap'], hpct, hmax)
        for team_num in [1, 2]:
            tp = sorted([p for p in players if p['team_num'] == team_num],
                        key=lambda x: x['playing_hcp'])
            for i, p in enumerate(tp):
                p['role'] = 'A' if i == 0 else 'B'
        def sort_key(p):
            return (p['team_num'], p.get('role', 'Z'))
        players.sort(key=sort_key)

    # Warn if any player has no handicap history AND no starting_handicap — they'll
    # silently play as scratch (get_player_handicap returns 0).
    scratch_names = []
    for p in players:
        if p['handicap'] == 0:
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

    # ── Per-player tee pre-selection (hierarchy: league default < player preferred) ──
    # Resolve each player's starting tee using their preferred_tee_name, falling back
    # to the matchup default. For 9-hole leagues, the nine (front/back) is inherited
    # from the matchup tee so the player preference only needs to store the color name.
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

        # Fetch preferred_tee_name for all players in this matchup
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

        default_tid = int(selected_tee_id)
        for p in players:
            pid = p['player_id']
            pref = pref_map.get(pid)
            if pref and pref in tee_name_to_id:
                player_default_tees[pid] = tee_name_to_id[pref]
            else:
                player_default_tees[pid] = default_tid

    return render_template('scores/enter.html',
                           matchup=matchup, team1=team1, team2=team2,
                           players=players, courses=courses, tees=tees, nine_options=nine_options if selected_course_id else [], holes=holes,
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
                sub_name = None
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
        sub_pid_val = int(sub_pid) if sub_pid else None

        if is_absent:
            if pid in existing:
                db.execute(
                    """UPDATE player_absences
                       SET sub_player_id=%s, reason=%s, excused=%s
                       WHERE absence_id=%s""",
                    (sub_pid_val, reason or None, excused, existing[pid])
                )
            else:
                db.execute(
                    """INSERT INTO player_absences
                       (matchup_id, player_id, sub_player_id, reason, excused)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (matchup_id, pid, sub_pid_val, reason or None, excused)
                )
        else:
            if pid in existing:
                db.execute(
                    "DELETE FROM player_absences WHERE absence_id=%s",
                    (existing[pid],)
                )

    db.commit()
    flash('Absence/sub assignments saved.', 'success')


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
                    'handicap':       hcp,
                    'is_sub':         sub_info is not None,
                    'orig_player_id': orig_pid if sub_info else None,
                    'orig_first':     team[fname_key] if sub_info else None,
                    'orig_last':      team[lname_key] if sub_info else None,
                })
    return players


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
        pid   = p['player_id']
        ptee  = form.get(f'player_tee_{pid}', '').strip()
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

    # Parse gross scores
    gross = {}
    for p in players:
        pid = p['player_id']
        p_holes = player_holes[pid]
        player_scores = []
        valid = True
        for h in p_holes:
            key = f"score_{pid}_{h['hole_number']}"
            val = form.get(key, '').strip()
            if not val:
                flash(f"Missing score for {p['first_name']} {p['last_name']}, hole {h['hole_number']}.", 'error')
                valid = False
                break
            try:
                player_scores.append(int(val))
            except ValueError:
                flash(f"Invalid score for {p['first_name']} {p['last_name']}, hole {h['hole_number']}.", 'error')
                valid = False
                break
        if not valid:
            return redirect(url_for('scores.enter', matchup_id=matchup['matchup_id']))
        gross[pid] = player_scores

    # League settings
    settings = get_league_settings(db, season_id, league_id)
    handicap_percent = float(settings['handicap_percent']) if settings else 90.0
    max_handicap     = float(settings['max_handicap_index']) if settings else 18.0
    scoring_mode     = 'match_play'
    if settings:
        try:
            scoring_mode = settings['scoring_mode'] or 'match_play'
        except (IndexError, KeyError):
            scoring_mode = 'match_play'

    # P2-1: Enforce max_score_per_hole if set in league settings
    max_per_hole   = int(settings['max_score_per_hole']) if settings and settings.get('max_score_per_hole') else None
    score_action   = (settings.get('max_score_action') or 'warn') if settings else 'warn'
    if max_per_hole:
        violations = []
        for p in players:
            pid = p['player_id']
            p_holes = player_holes[pid]
            for i, h in enumerate(p_holes):
                s = gross[pid][i]
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
        playing_hcps[pid] = calc_playing_handicap(p['handicap'], handicap_percent, max_handicap)

    # Net scores per hole using per-player tee's hole HCP indexes
    net = {}
    for p in players:
        pid    = p['player_id']
        ph     = playing_hcps[pid]
        p_holes = player_holes[pid]
        net[pid] = []
        for i, h in enumerate(p_holes):
            s = strokes_on_hole(ph, h['handicap_index'], total_holes=len(p_holes))
            net[pid].append(gross[pid][i] - s)

    # A/B designation — within each team, lower handicap = A
    def designate(team, p_list):
        tp = [p for p in p_list if p['team_id'] == team['team_id']]
        tp_sorted = sorted(tp, key=lambda x: playing_hcps[x['player_id']])
        return tp_sorted[0]['player_id'], tp_sorted[1]['player_id']

    t1_a, t1_b = designate(team1, players)
    t2_a, t2_b = designate(team2, players)

    # Match play or Stableford: A vs A, B vs B hole by hole + overall
    def match_result(pid_x, pid_y):
        p_holes_x = player_holes[pid_x]
        if scoring_mode == 'stableford':
            # Each player accumulates Stableford pts per hole; compare totals
            sb_x, sb_y = 0.0, 0.0
            for i, h in enumerate(p_holes_x):
                par = h['par'] if h['par'] else 4
                sb_x += calc_stableford(net[pid_x][i] - par)
                sb_y += calc_stableford(net[pid_y][i] - par)
            # Higher Stableford total wins (negate so calc_match_play's lower=better logic works)
            overall_x, overall_y = calc_match_play(-sb_x, -sb_y)
            # Store stableford totals as hole_points_won; overall = comparison bonus
            return sb_x, sb_y, overall_x, overall_y
        else:
            # Standard match play
            hole_pts_x, hole_pts_y = 0.0, 0.0
            for i in range(len(p_holes_x)):
                px, py = calc_match_play(net[pid_x][i], net[pid_y][i])
                hole_pts_x += px
                hole_pts_y += py
            total_net_x = sum(net[pid_x])
            total_net_y = sum(net[pid_y])
            overall_x, overall_y = calc_match_play(total_net_x, total_net_y)
            return hole_pts_x, hole_pts_y, overall_x, overall_y

    aa = match_result(t1_a, t2_a)
    bb = match_result(t1_b, t2_b)

    # --- Save to db ---
    # P1-2: guard against duplicate submission (race condition / double-click)
    existing = db.execute(
        "SELECT round_id FROM rounds WHERE matchup_id = %s", (matchup['matchup_id'],)
    ).fetchone()
    if existing:
        flash('Scores for this matchup have already been recorded.', 'info')
        return redirect(url_for('scores.view', matchup_id=matchup['matchup_id']))

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

        sc_row = db.execute(
            """INSERT INTO scorecards
               (round_id, player_id, team_id, handicap_at_time_of_play,
                is_sub, sub_for_player_id, approved, tee_id)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s) RETURNING scorecard_id""",
            (round_id, pid, p['team_id'], playing_hcps[pid],
             is_sub_flag, sub_for_pid, p_tee_id)
        )
        sc_id = sc_row.fetchone()['scorecard_id']
        for i, h in enumerate(p_holes):
            diff = gross[pid][i] - h['par']
            db.execute(
                """INSERT INTO hole_scores
                   (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (sc_id, h['hole_id'], h['hole_number'],
                 gross[pid][i], net[pid][i], diff)
            )

    # Link absence records to this round (P1-3: same transaction as round creation)
    db.execute(
        "UPDATE player_absences SET round_id = %s WHERE matchup_id = %s",
        (round_id, matchup['matchup_id'])
    )

    # Match results
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

    # Mark matchup completed
    db.execute(
        "UPDATE matchups SET status = 'completed', course_id = %s, tee_id = %s WHERE matchup_id = %s",
        (int(course_id), int(default_tee_id), matchup['matchup_id'])
    )

    db.commit()

    # P1-1: Handicap recalc runs after round data is committed.
    # Wrapped so a recalc failure surfaces as a warning without rolling back scores.
    try:
        for p in players:
            recalc_handicap_for_player(db, p['player_id'], season_id, league_id)
        db.commit()
    except Exception as hcap_err:
        import logging
        logging.getLogger(__name__).error('Handicap recalc failed after round commit: %s', hcap_err)
        flash('Scores saved, but handicap recalculation failed — recalculate manually from the standings page.', 'warning')

    # Fire round-completed notification
    try:
        t1_name = team1.get('team_name') or f"{team1['p1_last']}/{team1['p2_last']}"
        t2_name = team2.get('team_name') or f"{team2['p1_last']}/{team2['p2_last']}"
        msg = f"Scores recorded: {t1_name} vs {t2_name} (Week {matchup['week_number']})"
        create_league_event(db, league_id, 'round_completed', msg,
                            season_id=season_id, ref_id=matchup['matchup_id'])
        db.commit()
    except Exception:
        pass

    # Fire round-posted email (if configured)
    try:
        from routes.email_config import send_round_posted_email, send_player_scorecard_emails
        week_label = f"Week {matchup['week_number']}"
        send_round_posted_email(db, league_id, season_id, week_label)

        # Build per-player summaries for personalized scorecard emails
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
                'gross_total': sum(gross.get(_pid, [])),
                'net_total':   sum(net.get(_pid, [])),
                'total_pts':   _total_pts,
                'opp_name':    _name_map.get(_opp_pid, 'Opponent'),
                'opp_gross':   sum(gross.get(_opp_pid, [])),
                'opp_net':     sum(net.get(_opp_pid, [])),
                'opp_pts':     _opp_pts,
                'role':        _role,
            })
        _sc_url = url_for('scores.view', matchup_id=matchup['matchup_id'], _external=True)
        send_player_scorecard_emails(db, league_id, week_label, _player_summaries, scorecard_url=_sc_url)
    except Exception:
        pass

    # Push notification: scores posted
    try:
        from push import send_to_league
        t1_label = team1.get('team_name') or f"{team1.get('p1_last','')}/{team1.get('p2_last','')}"
        t2_label = team2.get('team_name') or f"{team2.get('p1_last','')}/{team2.get('p2_last','')}"
        send_to_league(db, league_id,
                       title=f"Week {matchup['week_number']} Scores Posted",
                       body=f"{t1_label} vs {t2_label}",
                       data={'deep_link': 'score_approved'})
    except Exception:
        pass

    flash('Scores saved!', 'success')
    return redirect(url_for('scores.view', matchup_id=matchup['matchup_id']))


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

    extra_tee_ids = set()
    for raw in request.args.get('extra_tees', '').split(','):
        try:
            extra_tee_ids.add(int(raw.strip()))
        except ValueError:
            pass

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
            'player_id':   pid,
            'name':        last or first or 'Player',
            'full_name':   f"{first} {last}".strip(),
            'playing_hcp': ph,
            'hcp_display': ph_display,
            'dots':        {},
        }

    def apply_dots(player, opponent_ph, mhcp_map, total_holes):
        # Dots show where THIS player receives strokes from their opponent.
        # Strokes = differential (this player's ph minus opponent's ph), allocated
        # to the hardest holes first via the M handicap index column.
        diff = player['playing_hcp'] - opponent_ph
        player['dots'] = {
            hn: strokes_on_hole(diff, hidx, total_holes) > 0
            for hn, hidx in mhcp_map.items()
        } if diff > 0 else {hn: False for hn in mhcp_map}

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
        course_tee_id_set = {t['tee_id'] for t in all_tees}

        # Auto-detect: matchup's default tee
        auto_ids = set()
        if m['tee_id']:
            auto_ids.add(m['tee_id'])

        # Display tees = auto + extra, filtered to this course
        display_ids = (auto_ids | extra_tee_ids) & course_tee_id_set
        if not display_ids and all_tees:
            display_ids = {all_tees[0]['tee_id']}

        # Load holes for each display tee, primary tee first
        ordered_ids = [m['tee_id']] if m['tee_id'] and m['tee_id'] in display_ids else []
        for tid in display_ids:
            if tid not in ordered_ids:
                ordered_ids.append(tid)

        tees_info  = []
        par_map    = {}   # hole_number → par
        mhcp_map   = {}   # hole_number → M handicap_index
        whcp_map   = {}   # hole_number → W handicap_index

        for tee_id in ordered_ids:
            meta = next((t for t in all_tees if t['tee_id'] == tee_id), None)
            if not meta:
                continue
            holes = db.execute(
                "SELECT hole_number, par, handicap_index, distance_yards FROM holes WHERE tee_id = %s ORDER BY hole_number",
                (tee_id,)
            ).fetchall()
            if not holes:
                continue

            total_yds = sum(h['distance_yards'] or 0 for h in holes)
            label     = meta['tee_color'] or meta['tee_name']

            tees_info.append({
                'tee_id':     tee_id,
                'label':      label,
                'gender':     meta['gender'],
                'holes':      [dict(h) for h in holes],
                'total_yards': total_yds if total_yds else None,
                'par_total':  meta['par_total'],
                'is_auto':    tee_id in auto_ids,
            })

            g = (meta['gender'] or 'M').upper()
            if not par_map:
                par_map  = {h['hole_number']: h['par']            for h in holes}
            if g == 'M' and not mhcp_map:
                mhcp_map = {h['hole_number']: h['handicap_index'] for h in holes}
            if g in ('F', 'W') and not whcp_map:
                whcp_map = {h['hole_number']: h['handicap_index'] for h in holes}

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
        apply_dots(p1, p3['playing_hcp'], mhcp_map, total_holes)
        apply_dots(p3, p1['playing_hcp'], mhcp_map, total_holes)
        apply_dots(p2, p4['playing_hcp'], mhcp_map, total_holes)
        apply_dots(p4, p2['playing_hcp'], mhcp_map, total_holes)

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
            'tees_info':     tees_info,
            'all_tees':      [dict(t) for t in all_tees],
            'auto_tee_ids':  list(auto_ids),
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

    return render_template('scores/print_scorecards.html',
        matchups        = matchups_data,
        week_number     = week_number,
        scheduled_date  = scheduled_date,
        season_id       = season_id,
        available_weeks = [dict(w) for w in available_weeks],
        display_format  = display_format,
        extra_tee_ids   = list(extra_tee_ids),
        extra_tees_param= request.args.get('extra_tees', ''),
        league_name     = league_name,
    )


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

    round_row = db.execute(
        "SELECT * FROM rounds WHERE matchup_id = %s", (matchup_id,)
    ).fetchone()

    if not round_row:
        flash('Score data not found for this matchup.', 'error')
        return redirect(url_for('seasons.index'))

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
    ).fetchall() if round_row else []

    tee    = db.execute("SELECT * FROM tees    WHERE tee_id    = %s", (round_row['tee_id'],)).fetchone()    if round_row else None
    course = db.execute("SELECT * FROM courses WHERE course_id = %s", (round_row['course_id'],)).fetchone() if round_row else None

    opp_map = {}
    role_map = {}
    pts_map  = {}
    tid_map  = {}
    for r in results:
        opp_map[r['player_id']]  = r['opponent_player_id']
        role_map[r['player_id']] = r['role']
        pts_map[r['player_id']]  = r['total_points']
        tid_map[r['player_id']]  = r['team_id']

    # Get scoring mode for view
    view_settings = get_league_settings(db, matchup['season_id'], matchup['league_id'])
    view_scoring_mode = 'match_play'
    if view_settings:
        try:
            view_scoring_mode = view_settings['scoring_mode'] or 'match_play'
        except (IndexError, KeyError):
            view_scoring_mode = 'match_play'

    view_hole_pts = {}
    for pid, opp_id in opp_map.items():
        pts = []
        my_hs  = {h['hole_number']: h for h in hole_scores.get(pid, [])}
        opp_hs = {h['hole_number']: h for h in hole_scores.get(opp_id, [])}
        for h in holes:
            n_mine = my_hs.get(h['hole_number'])
            n_opp  = opp_hs.get(h['hole_number'])
            if view_scoring_mode == 'stableford':
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

    # Build sub info from scorecards table (is_sub / sub_for_player_id)
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

    # Fall back to player_absences if scorecards don't have sub info yet
    if not sub_info_by_sub_pid:
        try:
            absence_rows = []
            if round_row:
                absence_rows = db.execute(
                    "SELECT * FROM player_absences WHERE round_id = %s AND sub_player_id IS NOT NULL",
                    (round_row['round_id'],)
                ).fetchall()
            if not absence_rows:
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

    t1_id = matchup['team1_id']
    t2_id = matchup['team2_id']

    def build_team_group(team_id):
        scs = [sc for sc in scorecards if sc['team_id'] == team_id]
        scs.sort(key=lambda x: role_map.get(x['player_id'], 'Z'))
        group = []
        for sc in scs:
            pid = sc['player_id']
            hs  = hole_scores.get(pid, [])
            # Resolve per-player tee name if different from round tee
            sc_tee_name = None
            sc_tee_id = sc['tee_id'] if sc['tee_id'] else None
            if sc_tee_id and round_row and sc_tee_id != round_row['tee_id']:
                tee_row = db.execute(
                    "SELECT tee_name, nine FROM tees WHERE tee_id = %s", (sc_tee_id,)
                ).fetchone()
                if tee_row:
                    sc_tee_name = f"{tee_row['tee_name']} ({tee_row['nine']})"
            ph = sc['handicap_at_time_of_play'] or 0
            n_holes = len(holes) or 9
            stroke_dots = [strokes_on_hole(ph, h['handicap_index'], n_holes) for h in holes]
            group.append({
                              'pid':          pid,
                'name':         f"{sc['first_name']} {sc['last_name']}",
                'role':         role_map.get(pid, '?'),
                'hcp':          sc['handicap_at_time_of_play'],
                'gross_scores': [h['gross_score'] for h in hs],
                'net_scores':   [h['net_score']   for h in hs],
                'total_gross':  sum(h['gross_score'] for h in hs) if hs else 0,
                'total_net':    sum(h['net_score']   for h in hs) if hs else 0,
                'hole_pts':     view_hole_pts.get(pid, []),
                'total_pts':    pts_map.get(pid, 0),
                'team_label':   f"{sc['t_p1_last'] or '?'} / {sc['t_p2_last'] or '?'}",
                'sub_for':      sub_info_by_sub_pid.get(pid),
                'is_sub':       bool(sc['is_sub']),
                'tee_name':     sc_tee_name,
                'stroke_dots':  stroke_dots,
            })
        return group

    view_groups = [build_team_group(t1_id), build_team_group(t2_id)]
    all_view_pids = [g['pid'] for grp in view_groups for g in grp]
    view_nickname_map = _get_nickname_map(db, all_view_pids)
    # Attach nickname to each group entry
    for grp in view_groups:
        for g in grp:
            g['nickname'] = view_nickname_map.get(g['pid'])

    return render_template('scores/view.html',
                           matchup=matchup, round_row=round_row,
                           holes=holes, view_groups=view_groups,
                           tee=tee, course=course,
                           scoring_mode=view_scoring_mode)
