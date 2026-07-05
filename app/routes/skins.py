from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db, load_nicknames, player_display_name, get_current_season_id
from routes.auth import login_required, admin_required

bp = Blueprint('skins', __name__, url_prefix='/skins')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_league_season(db, season_id):
    """Return season row, verifying it belongs to the logged-in league."""
    return db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()


def _get_skins_config(db, season_id):
    return db.execute(
        "SELECT * FROM skins_config WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()


def _get_round_skins_settings(db, round_id):
    return db.execute(
        "SELECT * FROM round_skins_settings WHERE round_id = %s", (round_id,)
    ).fetchone()


def _calculate_skins(participants_pids, hole_scores_by_pid, holes, gross_net,
                     total_pot, carried_over_in):
    """
    Run skins algorithm. Returns (results_list, leftover_amount).

    results_list entries:
        hole_number, winner_player_id (or None), skins_won, payout, carried_over (0/1)
    leftover_amount: unawarded pot dollars to carry to next round.
    """
    total_available = total_pot + carried_over_in
    if not holes or not participants_pids:
        return [], total_available

    # unit value per skin = total_pot / num_holes
    num_holes = len(holes)
    unit = total_available / num_holes if num_holes else 0.0

    results = []
    running_carryover = 0  # accumulated skins (count) not yet awarded

    for idx, hole in enumerate(holes):
        hole_num = hole['hole_number']
        key = 'net_score' if gross_net == 'net' else 'gross_score'

        scores = {}
        for pid in participants_pids:
            hs_list = hole_scores_by_pid.get(pid, [])
            if idx < len(hs_list):
                scores[pid] = hs_list[idx][key]

        if not scores:
            results.append({
                'hole_number': hole_num,
                'winner_player_id': None,
                'skins_won': 0,
                'payout': 0.0,
                'carried_over': 1,
            })
            running_carryover += 1
            continue

        min_score = min(scores.values())
        winners = [pid for pid, s in scores.items() if s == min_score]
        skins_on_table = running_carryover + 1

        if len(winners) == 1:
            payout = round(skins_on_table * unit, 2)
            results.append({
                'hole_number': hole_num,
                'winner_player_id': winners[0],
                'skins_won': skins_on_table,
                'payout': payout,
                'carried_over': 0,
            })
            running_carryover = 0
        else:
            results.append({
                'hole_number': hole_num,
                'winner_player_id': None,
                'skins_won': 0,
                'payout': 0.0,
                'carried_over': 1,
            })
            running_carryover = skins_on_table

    leftover_amount = round(running_carryover * unit, 2)
    return results, leftover_amount


# ---------------------------------------------------------------------------
# Skins Flights — handicap-tiered skins pots
#
# Config lives on skins_config.flights_enabled / .skins_flight_thresholds (see
# migrations/add_skins_flights.sql — verified as the table the live round_view
# /calculate path below actually reads; league_settings.skins_default_* is a
# separate, unrelated dead column set as far as skins.py is concerned).
#
# Thresholds are stored as a single ordered ascending list ("9,18" -> 3
# flights: <=9, <=18, >18) rather than named columns, so 2-5 flights (1-4
# thresholds) is just "however many values are in the list" — nothing in the
# calc/results/carryover/display code below is hardcoded to a flight count.
# ---------------------------------------------------------------------------

def _parse_flight_thresholds(raw):
    """Parse a stored 'skins_flight_thresholds' string ("9,18") into an
    ascending list of floats. Returns [] for blank/unset/unparseable input
    (which callers treat as "flights effectively collapse to 1 flight")."""
    if not raw:
        return []
    out = []
    for part in str(raw).split(','):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            continue
    return sorted(out)


def _assign_flight(playing_handicap, thresholds):
    """Assign a flight number (1 = lowest handicap) from an ascending list of
    handicap thresholds. len(thresholds) + 1 total flights; a handicap goes to
    the first flight whose threshold it's <= to, else the last (highest)
    flight. Pure function — unit-testable by inspection."""
    hcp = playing_handicap if playing_handicap is not None else 0
    for i, t in enumerate(thresholds):
        if hcp <= t:
            return i + 1
    return len(thresholds) + 1


def _flight_label(flight_num, num_flights):
    """Human-readable flight label. Endpoints get Low/High tags; the single
    middle flight in a 3-flight setup gets Mid; anything else is a plain
    'Flight N' (no attempt to name every tier in a 4-5 flight setup)."""
    if not num_flights or num_flights <= 1:
        return f"Flight {flight_num}"
    if flight_num == 1:
        tag = "Low"
    elif flight_num == num_flights:
        tag = "High"
    elif num_flights == 3 and flight_num == 2:
        tag = "Mid"
    else:
        tag = None
    return f"Flight {flight_num} ({tag})" if tag else f"Flight {flight_num}"


# ---------------------------------------------------------------------------
# Current redirect
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def current():
    db = get_db()
    season_id = get_current_season_id(db, session['league_id'])
    if not season_id:
        flash('No seasons found.', 'error')
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('skins.index', season_id=season_id))


# ---------------------------------------------------------------------------
# Season overview  /skins/<season_id>
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>')
@login_required
def index(season_id):
    db = get_db()
    season = _get_league_season(db, season_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    seasons = db.execute(
        "SELECT * FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (session['league_id'],)
    ).fetchall()

    skins_cfg = _get_skins_config(db, season_id)
    nicknames = load_nicknames(db, session['league_id'])

    # All completed rounds for this season
    rounds = db.execute(
        """SELECT r.*, m.week_number, m.matchup_id,
                  t1.team_id AS team1_id,
                  p1a.last_name AS t1p1_last, p1b.last_name AS t1p2_last,
                  t2.team_id AS team2_id,
                  p2a.last_name AS t2p1_last, p2b.last_name AS t2p2_last,
                  c.course_name, te.tee_name, te.nine
           FROM rounds r
           JOIN matchups m ON r.matchup_id = m.matchup_id
           JOIN teams t1 ON m.team1_id = t1.team_id
           JOIN teams t2 ON m.team2_id = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           LEFT JOIN courses c ON r.course_id = c.course_id
           LEFT JOIN tees te ON r.tee_id = te.tee_id
           WHERE r.season_id = %s
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    round_summaries = []
    for rnd in rounds:
        rss = _get_round_skins_settings(db, rnd['round_id'])
        participants = db.execute(
            """SELECT rsp.*, p.first_name, p.last_name
               FROM round_skins_participants rsp
               JOIN players p ON rsp.player_id = p.player_id
               WHERE rsp.round_id = %s""",
            (rnd['round_id'],)
        ).fetchall()
        results = db.execute(
            """SELECT sr.*, p.first_name, p.last_name
               FROM skins_results sr
               LEFT JOIN players p ON sr.winner_player_id = p.player_id
               WHERE sr.round_id = %s
               ORDER BY sr.hole_number""",
            (rnd['round_id'],)
        ).fetchall()

        total_pot = 0.0
        if rss:
            carried_in = rss['carried_over_amount'] or 0
            amt = rss['amount_override'] or (skins_cfg['default_amount'] if skins_cfg else 0) or 0
            total_pot = len(participants) * amt + carried_in

        round_flight_nums = [r['flight'] for r in results if r['flight'] is not None]
        num_flights_for_label = max(round_flight_nums) if round_flight_nums else 0

        winners_summary = []
        for r in results:
            if r['winner_player_id']:
                name = player_display_name(r['winner_player_id'], r['first_name'], r['last_name'], nicknames)
                entry = f"{name} (H{r['hole_number']}: ${r['payout']:.2f})"
                if r['flight'] is not None:
                    entry = f"{_flight_label(r['flight'], num_flights_for_label)} · {entry}"
                winners_summary.append(entry)

        round_summaries.append({
            'round': rnd,
            'settings': rss,
            'participant_count': len(participants),
            'total_pot': total_pot,
            'calculated': len(results) > 0,
            'winners_summary': winners_summary,
            'leftover': rss['carried_over_amount'] if rss else 0,
        })

    # Flight threshold inputs for the settings form (up to 4 -> 5 flights max).
    stored_thresholds = _parse_flight_thresholds(
        skins_cfg['skins_flight_thresholds'] if skins_cfg else None)
    flight_threshold_display = (stored_thresholds + [None, None, None, None])[:4]

    return render_template('skins/index.html',
                           season=season, seasons=seasons,
                           skins_cfg=skins_cfg,
                           round_summaries=round_summaries,
                           flight_threshold_display=flight_threshold_display)


# ---------------------------------------------------------------------------
# Skins Flights settings  /skins/<season_id>/flights-settings
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/flights-settings', methods=['POST'])
@admin_required
def save_flights_settings(season_id):
    db = get_db()
    season = _get_league_season(db, season_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    flights_enabled = 1 if request.form.get('flights_enabled') == '1' else 0

    raw_values = []
    for i in range(1, 5):  # threshold_1..threshold_4 -> cap at 4 thresholds (5 flights)
        v = request.form.get(f'threshold_{i}', '').strip()
        if not v:
            continue
        try:
            raw_values.append(float(v))
        except ValueError:
            flash(f'Threshold {i} must be a number.', 'error')
            return redirect(url_for('skins.index', season_id=season_id))

    # Dedupe and enforce strictly ascending (sorted() already gives ascending order).
    thresholds = []
    for t in sorted(raw_values):
        if not thresholds or t > thresholds[-1]:
            thresholds.append(t)

    if flights_enabled and not thresholds:
        thresholds = [9.0, 18.0]  # locked-decision default when first enabled

    thresholds_str = ','.join(str(t) for t in thresholds) if thresholds else None

    existing = _get_skins_config(db, season_id)
    if existing:
        db.execute(
            """UPDATE skins_config SET
               flights_enabled = %s, skins_flight_thresholds = %s
               WHERE season_id = %s AND league_id = %s""",
            (flights_enabled, thresholds_str, season_id, session['league_id'])
        )
    else:
        db.execute(
            """INSERT INTO skins_config
               (season_id, league_id, default_amount, default_gross_net,
                flights_enabled, skins_flight_thresholds)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (season_id, session['league_id'], None, 'gross',
             flights_enabled, thresholds_str)
        )
    db.commit()
    flash('Skins flights settings saved.', 'success')
    return redirect(url_for('skins.index', season_id=season_id))


# ---------------------------------------------------------------------------
# Round skins  /skins/round/<round_id>
# ---------------------------------------------------------------------------

@bp.route('/round/<int:round_id>', methods=['GET', 'POST'])
@admin_required
def round_view(round_id):
    db = get_db()

    round_row = db.execute(
        """SELECT r.*, m.week_number, m.matchup_id, m.team1_id, m.team2_id,
                  s.season_id, s.league_id, s.season_name,
                  c.course_name, te.tee_name, te.nine
           FROM rounds r
           JOIN matchups m ON r.matchup_id = m.matchup_id
           JOIN seasons s ON r.season_id = s.season_id
           LEFT JOIN courses c ON r.course_id = c.course_id
           LEFT JOIN tees te ON r.tee_id = te.tee_id
           WHERE r.round_id = %s""",
        (round_id,)
    ).fetchone()

    if not round_row or round_row['league_id'] != session['league_id']:
        flash('Round not found.', 'error')
        return redirect(url_for('skins.current'))

    season_id = round_row['season_id']
    skins_cfg = _get_skins_config(db, season_id)
    rss = _get_round_skins_settings(db, round_id)
    nicknames = load_nicknames(db, session['league_id'])

    # All players who played in this round (from scorecards)
    scorecards = db.execute(
        """SELECT sc.player_id, p.first_name, p.last_name, t.team_id
           FROM scorecards sc
           JOIN players p ON sc.player_id = p.player_id
           JOIN teams t ON sc.team_id = t.team_id
           WHERE sc.round_id = %s
           ORDER BY p.last_name""",
        (round_id,)
    ).fetchall()

    current_participants = db.execute(
        "SELECT player_id, paid_in, amount_paid FROM round_skins_participants WHERE round_id = %s",
        (round_id,)
    ).fetchall()
    participant_map = {r['player_id']: r for r in current_participants}

    results = db.execute(
        """SELECT sr.*, p.first_name, p.last_name
           FROM skins_results sr
           LEFT JOIN players p ON sr.winner_player_id = p.player_id
           WHERE sr.round_id = %s
           ORDER BY sr.hole_number""",
        (round_id,)
    ).fetchall()

    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
        (round_row['tee_id'],)
    ).fetchall()

    # GET: just display
    if request.method == 'GET':
        # Build score table for display if results exist
        if results:
            score_table = _build_score_table(db, round_id, current_participants, holes,
                                             rss, skins_cfg, nicknames)
        else:
            score_table = None

        default_amount = (skins_cfg['default_amount'] if skins_cfg else None) or 2.0
        default_gn = (skins_cfg['default_gross_net'] if skins_cfg else None) or 'gross'

        # Pre-resolve winner display names using nicknames
        results_display = []
        for r in results:
            rd = dict(r)
            if r['winner_player_id']:
                rd['winner_display'] = player_display_name(
                    r['winner_player_id'], r['first_name'], r['last_name'], nicknames)
            else:
                rd['winner_display'] = None
            results_display.append(rd)

        # Skins Flights: config-driven flag (drives setup-form/calculate-button UI,
        # i.e. what will happen on the *next* calculate) vs. data-driven flag (drives
        # display of *already-calculated* results — based on the stored flight column,
        # not current config, so a stale display never claims a role config doesn't
        # currently support).
        flights_enabled = bool(skins_cfg and skins_cfg['flights_enabled'])
        results_are_flighted = any(r['flight'] is not None for r in results_display) if results_display else False

        flights_view = []
        if results_are_flighted and score_table:
            thresholds = _parse_flight_thresholds(
                skins_cfg['skins_flight_thresholds'] if skins_cfg else None)
            flight_numbers = sorted(set(rd['flight'] for rd in results_display if rd['flight'] is not None))
            num_flights_for_label = max(flight_numbers)

            for fn in flight_numbers:
                fn_rows = [row for row in score_table['rows']
                           if _assign_flight(row['hcp'], thresholds) == fn]
                fn_pids = {row['pid'] for row in fn_rows}
                fn_score_table = {'rows': fn_rows, 'gross_net': score_table['gross_net']}

                fn_results = [rd for rd in results_display if rd['flight'] == fn]

                fn_carry_row = db.execute(
                    "SELECT carried_over_amount FROM round_skins_flight_carryover "
                    "WHERE round_id = %s AND flight = %s",
                    (round_id, fn)
                ).fetchone()
                fn_carryover = fn_carry_row['carried_over_amount'] if fn_carry_row else 0

                winner_totals = {}
                for rd in fn_results:
                    if rd['winner_player_id']:
                        wt = winner_totals.setdefault(rd['winner_player_id'], {
                            'name': rd['winner_display'] or (rd['first_name'] + ' ' + rd['last_name']),
                            'skins': 0, 'payout': 0.0,
                        })
                        wt['skins'] += rd['skins_won']
                        wt['payout'] += rd['payout']

                total_won = sum(rd['payout'] for rd in fn_results if rd['winner_player_id'])

                flights_view.append({
                    'flight': fn,
                    'label': _flight_label(fn, num_flights_for_label),
                    'participant_count': len(fn_pids),
                    'total_won': total_won,
                    'carryover': fn_carryover,
                    'score_table': fn_score_table,
                    'results': fn_results,
                    'winner_totals': winner_totals,
                })

        return render_template('skins/round.html',
                               round_row=round_row,
                               season_id=season_id,
                               skins_cfg=skins_cfg,
                               rss=rss,
                               scorecards=scorecards,
                               participant_map=participant_map,
                               results=results_display,
                               holes=holes,
                               score_table=score_table,
                               default_amount=default_amount,
                               default_gn=default_gn,
                               flights_enabled=flights_enabled,
                               results_are_flighted=results_are_flighted,
                               flights_view=flights_view)

    # POST: save setup (participants, amount, gross/net)
    action = request.form.get('action', '')

    if action == 'save_setup':
        amount = request.form.get('amount', '').strip()
        gross_net = request.form.get('gross_net', 'gross')
        carried_over = request.form.get('carried_over_amount', '0').strip() or '0'
        opted_in_pids = request.form.getlist('opted_in')  # list of player_id strings
        paid_in_pids = request.form.getlist('paid_in')

        try:
            amount_val = float(amount) if amount else 0.0
            carried_val = float(carried_over)
        except ValueError:
            flash('Invalid amount value.', 'error')
            return redirect(url_for('skins.round_view', round_id=round_id))

        # Upsert round_skins_settings
        if rss:
            db.execute(
                """UPDATE round_skins_settings
                   SET amount_override = %s, gross_net_override = %s, carried_over_amount = %s
                   WHERE round_id = %s""",
                (amount_val, gross_net, carried_val, round_id)
            )
        else:
            db.execute(
                """INSERT INTO round_skins_settings
                   (round_id, amount_override, gross_net_override, carried_over_amount)
                   VALUES (%s, %s, %s, %s)""",
                (round_id, amount_val, gross_net, carried_val)
            )

        # Clear existing participants, re-insert opted-in ones
        db.execute("DELETE FROM round_skins_participants WHERE round_id = %s", (round_id,))
        for pid_str in opted_in_pids:
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            paid = 1 if pid_str in paid_in_pids else 0
            db.execute(
                """INSERT INTO round_skins_participants
                   (round_id, player_id, paid_in, amount_paid)
                   VALUES (%s, %s, %s, %s)""",
                (round_id, pid, paid, amount_val if paid else 0.0)
            )

        # Clear any existing results if settings changed
        db.execute("DELETE FROM skins_results WHERE round_id = %s", (round_id,))
        db.commit()
        flash('Skins setup saved.', 'success')
        return redirect(url_for('skins.round_view', round_id=round_id))

    if action == 'calculate':
        if not rss:
            flash('Set up skins first.', 'error')
            return redirect(url_for('skins.round_view', round_id=round_id))

        rss = _get_round_skins_settings(db, round_id)  # re-fetch after possible update
        participants = db.execute(
            "SELECT player_id, amount_paid FROM round_skins_participants WHERE round_id = %s",
            (round_id,)
        ).fetchall()

        if len(participants) < 2:
            flash('Need at least 2 participants to calculate skins.', 'error')
            return redirect(url_for('skins.round_view', round_id=round_id))

        gross_net = rss['gross_net_override'] or (skins_cfg['default_gross_net'] if skins_cfg else 'gross')
        amount = rss['amount_override'] or (skins_cfg['default_amount'] if skins_cfg else 0) or 0
        carried_in = rss['carried_over_amount'] or 0

        participant_pids = [p['player_id'] for p in participants]
        amount_paid_by_pid = {p['player_id']: (p['amount_paid'] or amount) for p in participants}

        # Load hole scores (and, for flighting, playing handicap) for participants
        hole_scores_by_pid = {}
        handicap_by_pid = {}
        for pid in participant_pids:
            sc_row = db.execute(
                "SELECT scorecard_id, handicap_at_time_of_play FROM scorecards "
                "WHERE round_id = %s AND player_id = %s",
                (round_id, pid)
            ).fetchone()
            if sc_row:
                handicap_by_pid[pid] = sc_row['handicap_at_time_of_play']
                hs = db.execute(
                    "SELECT hole_number, gross_score, net_score FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
                    (sc_row['scorecard_id'],)
                ).fetchall()
                hole_scores_by_pid[pid] = list(hs)

        flights_enabled = bool(skins_cfg and skins_cfg['flights_enabled'])

        db.execute("DELETE FROM skins_results WHERE round_id = %s", (round_id,))

        if not flights_enabled:
            # --- Single-pot path (unchanged from pre-flights behavior) ---
            total_pot = sum(p['amount_paid'] or amount for p in participants) + carried_in

            results_data, leftover = _calculate_skins(
                participant_pids, hole_scores_by_pid, list(holes), gross_net,
                total_pot, 0  # carried_in already included in total_pot
            )

            for row in results_data:
                db.execute(
                    """INSERT INTO skins_results
                       (round_id, hole_number, winner_player_id, skins_won, payout, carried_over)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (round_id, row['hole_number'], row['winner_player_id'],
                     row['skins_won'], row['payout'], row['carried_over'])
                )

            # Update leftover carryover amount on this round's settings
            db.execute(
                "UPDATE round_skins_settings SET carried_over_amount = %s WHERE round_id = %s",
                (leftover, round_id)
            )

            db.commit()
            flash(f'Skins calculated! Pot: ${total_pot:.2f}. Leftover carryover: ${leftover:.2f}', 'success')
            return redirect(url_for('skins.round_view', round_id=round_id))

        # --- Flighted path: run _calculate_skins once per flight, independently ---
        thresholds = _parse_flight_thresholds(skins_cfg['skins_flight_thresholds'])
        num_flights_for_label = len(thresholds) + 1
        flight_by_pid = {pid: _assign_flight(handicap_by_pid.get(pid), thresholds)
                         for pid in participant_pids}
        flight_numbers = sorted(set(flight_by_pid.values()))

        summary_parts = []
        skipped_labels = []
        for flight_num in flight_numbers:
            flight_pids = [pid for pid in participant_pids if flight_by_pid[pid] == flight_num]
            if len(flight_pids) < 2:
                # Mirrors the round-level "need >= 2 to calculate" rule, per-flight.
                skipped_labels.append(_flight_label(flight_num, num_flights_for_label))
                continue

            flight_pot_buyins = sum(amount_paid_by_pid[pid] for pid in flight_pids)
            flight_carry_row = db.execute(
                "SELECT carried_over_amount FROM round_skins_flight_carryover "
                "WHERE round_id = %s AND flight = %s",
                (round_id, flight_num)
            ).fetchone()
            flight_carry_in = flight_carry_row['carried_over_amount'] if flight_carry_row else 0
            flight_total_pot = flight_pot_buyins + flight_carry_in

            flight_hole_scores = {pid: hole_scores_by_pid.get(pid, []) for pid in flight_pids}

            results_data, leftover = _calculate_skins(
                flight_pids, flight_hole_scores, list(holes), gross_net,
                flight_total_pot, 0  # carry-in already included in flight_total_pot
            )

            for row in results_data:
                db.execute(
                    """INSERT INTO skins_results
                       (round_id, hole_number, winner_player_id, skins_won, payout, carried_over, flight)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (round_id, row['hole_number'], row['winner_player_id'],
                     row['skins_won'], row['payout'], row['carried_over'], flight_num)
                )

            if flight_carry_row:
                db.execute(
                    "UPDATE round_skins_flight_carryover SET carried_over_amount = %s "
                    "WHERE round_id = %s AND flight = %s",
                    (leftover, round_id, flight_num)
                )
            else:
                db.execute(
                    """INSERT INTO round_skins_flight_carryover (round_id, flight, carried_over_amount)
                       VALUES (%s, %s, %s)""",
                    (round_id, flight_num, leftover)
                )

            summary_parts.append(
                f"{_flight_label(flight_num, num_flights_for_label)}: "
                f"pot ${flight_total_pot:.2f}, carryover ${leftover:.2f}"
            )

        db.commit()

        if not summary_parts:
            flash('No flight had at least 2 opted-in participants — nothing calculated.', 'error')
        else:
            msg = 'Skins calculated per flight! ' + '; '.join(summary_parts)
            if skipped_labels:
                msg += '. Skipped (fewer than 2 participants): ' + ', '.join(skipped_labels)
            flash(msg, 'success')
        return redirect(url_for('skins.round_view', round_id=round_id))

    flash('Unknown action.', 'error')
    return redirect(url_for('skins.round_view', round_id=round_id))


def _build_score_table(db, round_id, participants, holes, rss, skins_cfg, nicknames=None):
    """Build data structure for score display table in round view."""
    gross_net = (rss['gross_net_override'] if rss else None) or \
                (skins_cfg['default_gross_net'] if skins_cfg else 'gross')

    rows = []
    for p in participants:
        pid = p['player_id']
        sc_row = db.execute(
            """SELECT sc.scorecard_id, sc.handicap_at_time_of_play,
                      pl.first_name, pl.last_name
               FROM scorecards sc JOIN players pl ON sc.player_id = pl.player_id
               WHERE sc.round_id = %s AND sc.player_id = %s""",
            (round_id, pid)
        ).fetchone()
        if not sc_row:
            continue
        hs = db.execute(
            "SELECT hole_number, gross_score, net_score FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
            (sc_row['scorecard_id'],)
        ).fetchall()
        scores_by_hole = {h['hole_number']: h for h in hs}
        row_scores = []
        for hole in holes:
            hn = hole['hole_number']
            hs_row = scores_by_hole.get(hn)
            if hs_row:
                val = hs_row['net_score'] if gross_net == 'net' else hs_row['gross_score']
                row_scores.append(val)
            else:
                row_scores.append(None)

        rows.append({
            'pid': pid,
            'name': player_display_name(pid, sc_row['first_name'], sc_row['last_name'], nicknames),
            'hcp': sc_row['handicap_at_time_of_play'],
            'scores': row_scores,
        })

    return {'rows': rows, 'gross_net': gross_net}
