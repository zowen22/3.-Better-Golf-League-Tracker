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


def _get_week_settings(db, season_id, week_number):
    return db.execute(
        "SELECT * FROM round_skins_settings WHERE season_id = %s AND week_number = %s",
        (season_id, week_number)
    ).fetchone()


def _resolve_week_tee(db, season_id, week_number):
    """Return (tee_id, round_ids) for the tee most matchups that week are
    on. In practice a league only ever runs one tee per week (verified
    against Buckeye's actual production data, 2026-08-17) -- picking the
    majority here is just a safety rail for a week that somehow isn't
    uniform, not a supported/UI-surfaced feature (per @user: "no need to
    support" mixed courses/tees within a week)."""
    rows = db.execute(
        """SELECT r.round_id, r.tee_id
           FROM rounds r JOIN matchups m ON r.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.week_number = %s""",
        (season_id, week_number)
    ).fetchall()
    if not rows:
        return None, []
    tee_counts = {}
    for r in rows:
        tee_counts[r['tee_id']] = tee_counts.get(r['tee_id'], 0) + 1
    resolved_tee = max(tee_counts, key=tee_counts.get)
    round_ids = [r['round_id'] for r in rows if r['tee_id'] == resolved_tee]
    return resolved_tee, round_ids


def _get_week_scorecards(db, round_ids):
    """All players (with scorecard_id + handicap already attached) across
    every round in `round_ids` -- i.e. the whole week's field at the
    resolved tee. See _resolve_week_tee()."""
    if not round_ids:
        return []
    placeholders = ','.join(['%s'] * len(round_ids))
    return db.execute(
        f"""SELECT sc.scorecard_id, sc.player_id, sc.handicap_at_time_of_play, sc.round_id,
                   p.first_name, p.last_name, t.team_id
            FROM scorecards sc
            JOIN players p ON sc.player_id = p.player_id
            JOIN teams t ON sc.team_id = t.team_id
            WHERE sc.round_id IN ({placeholders})
            ORDER BY p.last_name""",
        tuple(round_ids)
    ).fetchall()


def _get_week_display_info(db, season_id, week_number):
    """Season/date/course context for a week's skins page header -- pulled
    from any one of that week's rounds (they should all share the same
    course/tee; see _resolve_week_tee). Returns None if the week doesn't
    exist at all."""
    row = db.execute(
        """SELECT s.season_id, s.season_name, s.league_id,
                  r.round_date, c.course_name, te.tee_name, te.nine
           FROM matchups m
           JOIN seasons s ON s.season_id = m.season_id
           JOIN rounds r ON r.matchup_id = m.matchup_id
           LEFT JOIN courses c ON r.course_id = c.course_id
           LEFT JOIN tees te ON r.tee_id = te.tee_id
           WHERE m.season_id = %s AND m.week_number = %s
           ORDER BY r.round_id LIMIT 1""",
        (season_id, week_number)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d['week_number'] = week_number
    return d


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
# migrations/add_skins_flights.sql — verified as the table the live week_view
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
# Season overview  /skins/<season_id> — one row per week
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

    weeks = db.execute(
        """SELECT DISTINCT m.week_number
           FROM matchups m
           WHERE m.season_id = %s AND m.is_bye = 0
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    week_summaries = []
    for wk_row in weeks:
        wk = wk_row['week_number']
        info = _get_week_display_info(db, season_id, wk)
        rss = _get_week_settings(db, season_id, wk)

        participants = db.execute(
            """SELECT rsp.*, p.first_name, p.last_name
               FROM round_skins_participants rsp
               JOIN players p ON rsp.player_id = p.player_id
               WHERE rsp.season_id = %s AND rsp.week_number = %s""",
            (season_id, wk)
        ).fetchall()
        results = db.execute(
            """SELECT sr.*, p.first_name, p.last_name
               FROM skins_results sr
               LEFT JOIN players p ON sr.winner_player_id = p.player_id
               WHERE sr.season_id = %s AND sr.week_number = %s
               ORDER BY sr.hole_number""",
            (season_id, wk)
        ).fetchall()

        total_pot = 0.0
        if rss:
            carried_in = rss['carried_over_amount'] or 0
            amt = rss['amount_override'] or (skins_cfg['default_amount'] if skins_cfg else 0) or 0
            total_pot = len(participants) * amt + carried_in

        week_flight_nums = [r['flight'] for r in results if r['flight'] is not None]
        num_flights_for_label = max(week_flight_nums) if week_flight_nums else 0

        winners_summary = []
        for r in results:
            if r['winner_player_id']:
                name = player_display_name(r['winner_player_id'], r['first_name'], r['last_name'], nicknames)
                entry = f"{name} (H{r['hole_number']}: ${r['payout']:.2f})"
                if r['flight'] is not None:
                    entry = f"{_flight_label(r['flight'], num_flights_for_label)} · {entry}"
                winners_summary.append(entry)

        week_summaries.append({
            'week_number': wk,
            'info': info,
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
                           week_summaries=week_summaries,
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
# Week skins  /skins/week/<season_id>/<week_number>
#
# One skins pot/winner set spans every matchup sharing that (season, week) —
# the whole field playing that week — not just one foursome's own round.
# See migrations/add_week_scoped_skins.sql for the prior per-round shape
# this replaced.
# ---------------------------------------------------------------------------

@bp.route('/week/<int:season_id>/<int:week_number>', methods=['GET', 'POST'])
@admin_required
def week_view(season_id, week_number):
    db = get_db()

    week_info = _get_week_display_info(db, season_id, week_number)
    if not week_info or week_info['league_id'] != session['league_id']:
        flash('Week not found.', 'error')
        return redirect(url_for('skins.current'))

    # GET: just display — via the same context builder the League Standings
    # embed uses (see get_week_page_context()'s docstring), so the two
    # pages can never show different data or markup for the same week.
    if request.method == 'GET':
        return render_template('skins/week.html', **get_week_page_context(db, season_id, week_number))

    # POST: save setup (participants, amount, gross/net) or calculate
    skins_cfg = _get_skins_config(db, season_id)
    rss = _get_week_settings(db, season_id, week_number)

    resolved_tee_id, round_ids = _resolve_week_tee(db, season_id, week_number)
    week_scorecards = _get_week_scorecards(db, round_ids)

    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
        (resolved_tee_id,)
    ).fetchall() if resolved_tee_id else []

    action = request.form.get('action', '')

    if action == 'save_setup':
        amount = request.form.get('amount', '').strip()
        gross_net = request.form.get('gross_net', 'gross')
        carried_over = request.form.get('carried_over_amount', '0').strip() or '0'
        opted_in_pids = request.form.getlist('opted_in')  # list of player_id strings
        paid_in_pids = request.form.getlist('paid_in')
        flights_enabled_val = 1 if request.form.get('flights_enabled') == '1' else 0
        flight_threshold_raw = request.form.get('flight_threshold', '').strip()

        try:
            # Buy-in rounds to a whole dollar (per @user) -- even if a
            # decimal sneaks in via a non-JS form submission.
            amount_val = round(float(amount)) if amount else 0.0
            carried_val = float(carried_over)
            flight_threshold_val = float(flight_threshold_raw) if flight_threshold_raw else None
        except ValueError:
            flash('Invalid amount value.', 'error')
            return redirect(url_for('skins.week_view', season_id=season_id, week_number=week_number))

        if flights_enabled_val and flight_threshold_val is None:
            flight_threshold_val = 9.0  # sensible default when first enabled, same as the old season-level default

        db.execute(
            """INSERT INTO round_skins_settings
               (season_id, week_number, amount_override, gross_net_override, carried_over_amount,
                flights_enabled, flight_threshold)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (season_id, week_number) DO UPDATE SET
                 amount_override = EXCLUDED.amount_override,
                 gross_net_override = EXCLUDED.gross_net_override,
                 carried_over_amount = EXCLUDED.carried_over_amount,
                 flights_enabled = EXCLUDED.flights_enabled,
                 flight_threshold = EXCLUDED.flight_threshold""",
            (season_id, week_number, amount_val, gross_net, carried_val,
             flights_enabled_val, flight_threshold_val)
        )

        # Clear existing participants, re-insert opted-in ones
        db.execute("DELETE FROM round_skins_participants WHERE season_id = %s AND week_number = %s",
                  (season_id, week_number))
        for pid_str in opted_in_pids:
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            paid = 1 if pid_str in paid_in_pids else 0
            db.execute(
                """INSERT INTO round_skins_participants
                   (season_id, week_number, player_id, paid_in, amount_paid)
                   VALUES (%s, %s, %s, %s, %s)""",
                (season_id, week_number, pid, paid, amount_val if paid else 0.0)
            )

        # Clear any existing results if settings changed
        db.execute("DELETE FROM skins_results WHERE season_id = %s AND week_number = %s",
                  (season_id, week_number))
        db.commit()
        flash('Skins setup saved.', 'success')
        return redirect(url_for('skins.week_view', season_id=season_id, week_number=week_number))

    if action == 'calculate':
        if not rss:
            flash('Set up skins first.', 'error')
            return redirect(url_for('skins.week_view', season_id=season_id, week_number=week_number))

        rss = _get_week_settings(db, season_id, week_number)  # re-fetch after possible update
        participants = db.execute(
            "SELECT player_id, amount_paid FROM round_skins_participants "
            "WHERE season_id = %s AND week_number = %s",
            (season_id, week_number)
        ).fetchall()

        if len(participants) < 2:
            flash('Need at least 2 participants to calculate skins.', 'error')
            return redirect(url_for('skins.week_view', season_id=season_id, week_number=week_number))

        gross_net = rss['gross_net_override'] or (skins_cfg['default_gross_net'] if skins_cfg else 'gross')
        amount = rss['amount_override'] or (skins_cfg['default_amount'] if skins_cfg else 0) or 0
        carried_in = rss['carried_over_amount'] or 0

        participant_pids = [p['player_id'] for p in participants]
        amount_paid_by_pid = {p['player_id']: (p['amount_paid'] or amount) for p in participants}

        # Load hole scores (and, for flighting, playing handicap) for participants
        scorecard_by_pid = {sc['player_id']: sc for sc in week_scorecards}
        hole_scores_by_pid = {}
        handicap_by_pid = {}
        for pid in participant_pids:
            sc = scorecard_by_pid.get(pid)
            if sc:
                handicap_by_pid[pid] = sc['handicap_at_time_of_play']
                hs = db.execute(
                    "SELECT hole_number, gross_score, net_score FROM hole_scores "
                    "WHERE scorecard_id = %s ORDER BY hole_number",
                    (sc['scorecard_id'],)
                ).fetchall()
                hole_scores_by_pid[pid] = list(hs)

        # Flights are set per week (per @user 2026-08-18), not read from the
        # season-wide skins_config.
        flights_enabled = bool(rss['flights_enabled'])

        db.execute("DELETE FROM skins_results WHERE season_id = %s AND week_number = %s",
                  (season_id, week_number))

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
                       (season_id, week_number, hole_number, winner_player_id, skins_won, payout, carried_over)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (season_id, week_number, row['hole_number'], row['winner_player_id'],
                     row['skins_won'], row['payout'], row['carried_over'])
                )

            # Update leftover carryover amount on this week's settings
            db.execute(
                "UPDATE round_skins_settings SET carried_over_amount = %s "
                "WHERE season_id = %s AND week_number = %s",
                (leftover, season_id, week_number)
            )

            db.commit()
            flash(f'Skins calculated! Pot: ${total_pot:.2f}. Leftover carryover: ${leftover:.2f}', 'success')
            return redirect(url_for('skins.week_view', season_id=season_id, week_number=week_number))

        # --- Flighted path: run _calculate_skins once per flight, independently ---
        # Single weekly threshold -> 2 flights (Low/High). The underlying
        # engine still supports an ordered list of several thresholds (see
        # _parse_flight_thresholds/_assign_flight) -- this form just only
        # ever produces a 1-element one for now.
        thresholds = [rss['flight_threshold']] if rss['flight_threshold'] is not None else []
        num_flights_for_label = len(thresholds) + 1
        flight_by_pid = {pid: _assign_flight(handicap_by_pid.get(pid), thresholds)
                         for pid in participant_pids}
        flight_numbers = sorted(set(flight_by_pid.values()))

        summary_parts = []
        skipped_labels = []
        for flight_num in flight_numbers:
            flight_pids = [pid for pid in participant_pids if flight_by_pid[pid] == flight_num]
            if len(flight_pids) < 2:
                # Mirrors the week-level "need >= 2 to calculate" rule, per-flight.
                skipped_labels.append(_flight_label(flight_num, num_flights_for_label))
                continue

            flight_pot_buyins = sum(amount_paid_by_pid[pid] for pid in flight_pids)
            flight_carry_row = db.execute(
                "SELECT carried_over_amount FROM round_skins_flight_carryover "
                "WHERE season_id = %s AND week_number = %s AND flight = %s",
                (season_id, week_number, flight_num)
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
                       (season_id, week_number, hole_number, winner_player_id, skins_won, payout, carried_over, flight)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (season_id, week_number, row['hole_number'], row['winner_player_id'],
                     row['skins_won'], row['payout'], row['carried_over'], flight_num)
                )

            db.execute(
                """INSERT INTO round_skins_flight_carryover (season_id, week_number, flight, carried_over_amount)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (season_id, week_number, flight) DO UPDATE SET
                     carried_over_amount = EXCLUDED.carried_over_amount""",
                (season_id, week_number, flight_num, leftover)
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
        return redirect(url_for('skins.week_view', season_id=season_id, week_number=week_number))

    flash('Unknown action.', 'error')
    return redirect(url_for('skins.week_view', season_id=season_id, week_number=week_number))


def _build_calculated_context(db, season_id, week_number):
    """Everything needed to render an already-calculated week's skins: pot
    summary, per-hole blocks (possibly per-flight), and the combined
    full-field scorecard grid. Returns None if nothing's been calculated
    yet for this week. Standalone — usable both by week_view()'s GET path
    and get_weekly_winners_context() (the Standings mirror) without either
    depending on the other."""
    results = db.execute(
        """SELECT sr.*, p.first_name, p.last_name
           FROM skins_results sr
           LEFT JOIN players p ON sr.winner_player_id = p.player_id
           WHERE sr.season_id = %s AND sr.week_number = %s
           ORDER BY sr.hole_number""",
        (season_id, week_number)
    ).fetchall()
    if not results:
        return None

    season_row = db.execute(
        "SELECT league_id FROM seasons WHERE season_id = %s", (season_id,)
    ).fetchone()
    league_id = season_row['league_id'] if season_row else None

    skins_cfg = _get_skins_config_by_league(db, season_id, league_id)
    rss = _get_week_settings(db, season_id, week_number)
    nicknames = load_nicknames(db, league_id)

    resolved_tee_id, round_ids = _resolve_week_tee(db, season_id, week_number)
    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
        (resolved_tee_id,)
    ).fetchall() if resolved_tee_id else []

    participants = db.execute(
        "SELECT player_id, paid_in, amount_paid FROM round_skins_participants "
        "WHERE season_id = %s AND week_number = %s",
        (season_id, week_number)
    ).fetchall()

    week_scorecards = _get_week_scorecards(db, round_ids)
    scorecard_by_pid = {sc['player_id']: sc for sc in week_scorecards}
    participant_rows = [scorecard_by_pid[p['player_id']] for p in participants
                        if p['player_id'] in scorecard_by_pid]

    score_table = _build_score_table(db, participant_rows, holes, rss, skins_cfg, nicknames)

    default_amount = (skins_cfg['default_amount'] if skins_cfg else None) or 2.0
    default_gn = (skins_cfg['default_gross_net'] if skins_cfg else None) or 'gross'

    results_display = []
    for r in results:
        rd = dict(r)
        rd['winner_display'] = (
            player_display_name(r['winner_player_id'], r['first_name'], r['last_name'], nicknames)
            if r['winner_player_id'] else None
        )
        results_display.append(rd)

    def _totals(rows):
        wt = {}
        for rd in rows:
            if rd['winner_player_id']:
                entry = wt.setdefault(rd['winner_player_id'], {
                    'name': rd['winner_display'] or (rd['first_name'] + ' ' + rd['last_name']),
                    'skins': 0, 'payout': 0.0,
                })
                entry['skins'] += rd['skins_won']
                entry['payout'] += rd['payout']
        return wt

    # Flights are set per week (per @user 2026-08-18), not read from the
    # season-wide skins_config.
    flights_enabled = bool(rss and rss['flights_enabled'])
    results_are_flighted = any(r['flight'] is not None for r in results_display)

    flights_view = []
    if results_are_flighted and score_table:
        thresholds = [rss['flight_threshold']] if rss and rss['flight_threshold'] is not None else []
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
                "WHERE season_id = %s AND week_number = %s AND flight = %s",
                (season_id, week_number, fn)
            ).fetchone()
            fn_carryover = fn_carry_row['carried_over_amount'] if fn_carry_row else 0

            flights_view.append({
                'flight': fn,
                'label': _flight_label(fn, num_flights_for_label),
                'participant_count': len(fn_pids),
                'total_won': sum(rd['payout'] for rd in fn_results if rd['winner_player_id']),
                'carryover': fn_carryover,
                'score_table': fn_score_table,
                'results': fn_results,
                'winner_totals': _totals(fn_results),
            })

    blocks = _build_display_blocks(
        holes, score_table=score_table, winner_totals=_totals(results_display),
        flights_view=flights_view if results_are_flighted else None)
    winners_table = _build_winners_summary_table(blocks)

    return {
        'rss': rss,
        'skins_cfg': skins_cfg,
        'results': results_display,
        'score_table': score_table,
        'default_amount': default_amount,
        'default_gn': default_gn,
        'flights_enabled': flights_enabled,
        'results_are_flighted': results_are_flighted,
        'flights_view': flights_view,
        'winner_totals': _totals(results_display),
        'total_won': sum(rd['payout'] for rd in results_display if rd['winner_player_id']),
        'participant_count': len(participants),
        'blocks': blocks,
        'winners_table': winners_table,
        'full_scorecard': _build_full_scorecard_grid(score_table, holes),
        'holes': holes,
    }


def _get_skins_config_by_league(db, season_id, league_id):
    """Same query as _get_skins_config(), but takes an explicit league_id
    instead of reading session['league_id'] — needed by
    _build_calculated_context(), which must stay usable outside a request
    where the target season is already known to be the caller's own (e.g.
    called from get_weekly_winners_context() for the Standings mirror,
    which already validated the season against session['league_id'] before
    ever reaching here)."""
    return db.execute(
        "SELECT * FROM skins_config WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()


def get_week_skins_display(db, season_id, week_number):
    """The single source of truth for the read-only Skins display of a
    (season, week): either the calculated Winners of the Week (pot summary,
    player totals, per-hole/per-flight results) if skins have been
    calculated, or a live no-purse preview if not — plus the combined
    full-field scorecard grid either way. Returns None only if the week
    doesn't exist at all (no matchups).

    Used by get_week_page_context() (the full-page context both week_view()
    and the League Standings embed render from — see its docstring) as the
    read-only half of the page. Change the display here (or in
    _build_calculated_context() / _build_display_blocks() /
    _build_full_scorecard_grid(), which this calls), not by re-deriving it
    elsewhere."""
    week_info = _get_week_display_info(db, season_id, week_number)
    if not week_info:
        return None

    base = {'week_info': week_info, 'season_id': season_id, 'week_number': week_number}

    calc_ctx = _build_calculated_context(db, season_id, week_number)
    if calc_ctx:
        return {**base, **calc_ctx, 'has_results': True}

    # No skins calculated yet -- same live preview week_view() shows.
    skins_cfg = _get_skins_config_by_league(db, season_id, week_info['league_id'])
    rss = _get_week_settings(db, season_id, week_number)
    nicknames = load_nicknames(db, week_info['league_id'])
    resolved_tee_id, round_ids = _resolve_week_tee(db, season_id, week_number)
    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number", (resolved_tee_id,)
    ).fetchall() if resolved_tee_id else []
    week_scorecards = _get_week_scorecards(db, round_ids)

    blocks, full_scorecard, winners_table = [], None, {'headers': [], 'rows': []}
    if week_scorecards and len(week_scorecards) >= 2 and holes:
        score_table = _build_score_table(db, week_scorecards, holes, rss, skins_cfg, nicknames)
        blocks = _build_display_blocks(holes, score_table=score_table)
        full_scorecard = _build_full_scorecard_grid(score_table, holes)
        winners_table = _build_winners_summary_table(blocks)

    return {**base, 'has_results': False, 'blocks': blocks, 'full_scorecard': full_scorecard,
            'winners_table': winners_table}


def get_week_page_context(db, season_id, week_number):
    """Every variable templates/skins/_week_page_body.html needs: header
    info, setup-form data (the week's full field for the opt-in table,
    current participants, buy-in defaults), and the read-only display (see
    get_week_skins_display()). Returns None if the week doesn't exist.

    This is the single source of truth for the whole Skins week page body.
    week_view() (GET) and standings.index() (the League Standings
    admin-only embed) both call this exact function and both `{% include
    'skins/_week_page_body.html' %}` on the result — literally the same
    template, same data, in both places. Per @user 2026-08-18: "one-for-one
    pull... ensure there's no divergence." Don't add a second way to
    render this page; if it needs to change, change it (or the partial)
    here, once."""
    week_info = _get_week_display_info(db, season_id, week_number)
    if not week_info:
        return None

    skins_cfg = _get_skins_config_by_league(db, season_id, week_info['league_id'])
    rss = _get_week_settings(db, season_id, week_number)

    resolved_tee_id, round_ids = _resolve_week_tee(db, season_id, week_number)
    week_scorecards = _get_week_scorecards(db, round_ids)

    current_participants = db.execute(
        "SELECT player_id, paid_in, amount_paid FROM round_skins_participants "
        "WHERE season_id = %s AND week_number = %s",
        (season_id, week_number)
    ).fetchall()
    participant_map = {r['player_id']: r for r in current_participants}

    results = db.execute(
        """SELECT sr.*, p.first_name, p.last_name
           FROM skins_results sr
           LEFT JOIN players p ON sr.winner_player_id = p.player_id
           WHERE sr.season_id = %s AND sr.week_number = %s
           ORDER BY sr.hole_number""",
        (season_id, week_number)
    ).fetchall()

    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
        (resolved_tee_id,)
    ).fetchall() if resolved_tee_id else []

    return {
        'week_info': week_info,
        'season_id': season_id,
        'week_number': week_number,
        'skins_cfg': skins_cfg,
        'rss': rss,
        'scorecards': week_scorecards,
        'participant_map': participant_map,
        'results': results,
        'holes': holes,
        'default_amount': (skins_cfg['default_amount'] if skins_cfg else None) or 2.0,
        'default_gn': (skins_cfg['default_gross_net'] if skins_cfg else None) or 'gross',
        'flights_enabled': bool(rss and rss['flights_enabled']),
        'display': get_week_skins_display(db, season_id, week_number),
    }


def _build_score_table(db, participant_rows, holes, rss, skins_cfg, nicknames=None):
    """Build data structure for score display table. `participant_rows`
    must already carry scorecard_id, handicap_at_time_of_play, first_name,
    last_name, player_id (i.e. rows from _get_week_scorecards(), possibly
    filtered down to opted-in participants) — each player's specific round
    within the week is already resolved via their scorecard_id, so no
    round_id lookup happens here."""
    gross_net = (rss['gross_net_override'] if rss else None) or \
                (skins_cfg['default_gross_net'] if skins_cfg else 'gross')

    rows = []
    for p in participant_rows:
        hs = db.execute(
            "SELECT hole_number, gross_score, net_score FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
            (p['scorecard_id'],)
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
            'pid': p['player_id'],
            'name': player_display_name(p['player_id'], p['first_name'], p['last_name'], nicknames),
            'first_name': p['first_name'],
            'hcp': p['handicap_at_time_of_play'],
            'scores': row_scores,
        })

    return {'rows': rows, 'gross_net': gross_net}


# ---------------------------------------------------------------------------
# Hole-by-hole "Result" display — descriptive (Birdie/Par/Bogey/... + first
# name(s)), independent of the skins pot/payout math. See render_winners()
# in templates/skins/_winners_display.html for how these render.
# ---------------------------------------------------------------------------

def _score_category(diff):
    """diff = score - par. Returns (singular, plural) category labels."""
    if diff <= -2:
        return 'Eagle', 'Eagles'
    if diff == -1:
        return 'Birdie', 'Birdies'
    if diff == 0:
        return 'Par', 'Pars'
    if diff == 1:
        return 'Bogey', 'Bogeys'
    return 'Double Bogey', 'Double Bogeys'


def _hole_result_rows(score_table, holes):
    """One entry per hole: {hole_number, text, highlight, winner_pid, winner_name}.

    text is the category name (singular for a solo winner, plural for a
    tie) followed by first name(s) per the tie-count rule: solo winner ->
    "Birdie Sam"; 2-way tie -> "Pars Sam & Alex"; 3-way tie -> "Bogeys Sam,
    Alex, Jo"; 4+-way tie -> just the plural category, no names.
    highlight is True only for a solo (non-tied) winner. winner_pid/
    winner_name are set only for a solo winner (None on any tie) — used by
    _simple_winner_counts() to tally holes won per player."""
    rows = score_table['rows'] if score_table else []
    out = []
    for idx, hole in enumerate(holes):
        par = hole['par']
        scored = [(p, p['scores'][idx]) for p in rows
                  if idx < len(p['scores']) and p['scores'][idx] is not None]
        if not scored or par is None:
            out.append({'hole_number': hole['hole_number'], 'text': '—', 'highlight': False,
                        'winner_pid': None, 'winner_name': None})
            continue

        best = min(s for _, s in scored)
        tied = [p for p, s in scored if s == best]
        singular, plural = _score_category(best - par)
        names = [p['first_name'] or p['name'] for p in tied]
        winner_pid = winner_name = None

        if len(tied) == 1:
            text, highlight = f"{names[0]} - {singular}", True
            winner_pid, winner_name = tied[0]['pid'], names[0]
        elif len(tied) == 2:
            text, highlight = f"{plural} - {names[0]} & {names[1]}", False
        elif len(tied) == 3:
            text, highlight = f"{plural} - {', '.join(names)}", False
        else:
            text, highlight = plural, False

        out.append({'hole_number': hole['hole_number'], 'text': text, 'highlight': highlight,
                    'winner_pid': winner_pid, 'winner_name': winner_name})
    return out


def _simple_winner_counts(hole_rows, winner_totals=None):
    """Compact 'who won how many holes' tally — name + count, plus payout
    when one exists — derived primarily from solo (non-tied) hole winners
    (so the count works identically whether or not a real skins pot
    exists), with payout merged in by pid from `winner_totals` (the same
    per-flight or whole-block totals `render_winners()`'s detailed table
    already uses). payout is None (blank in the template) whenever there's
    no real pot yet — e.g. the no-purse preview. Sorted by wins descending,
    ties broken by first appearance."""
    winner_totals = winner_totals or {}
    counts, order = {}, []
    for hr in hole_rows:
        pid = hr['winner_pid']
        if pid is None:
            continue
        if pid not in counts:
            counts[pid] = {'pid': pid, 'name': hr['winner_name'], 'wins': 0,
                           'payout': winner_totals[pid]['payout'] if pid in winner_totals else None}
            order.append(pid)
        counts[pid]['wins'] += 1
    return sorted((counts[pid] for pid in order), key=lambda e: -e['wins'])


def _build_display_blocks(holes, score_table=None, winner_totals=None, flights_view=None):
    """Build the block list render_winners() renders: one block per flight
    (label + hole_rows + simple_winners + winner_totals), or a single
    unlabeled block for a non-flighted week. Each flight's simple_winners
    is merged against that same flight's own winner_totals (not the whole
    week's), so payout stays correct per flight."""
    if flights_view:
        blocks = []
        for fv in flights_view:
            hole_rows = _hole_result_rows(fv['score_table'], holes)
            blocks.append({
                'label': fv['label'],
                'hole_rows': hole_rows,
                'simple_winners': _simple_winner_counts(hole_rows, fv['winner_totals']),
                'winner_totals': fv['winner_totals'],
            })
        return blocks
    hole_rows = _hole_result_rows(score_table, holes)
    return [{
        'label': None,
        'hole_rows': hole_rows,
        'simple_winners': _simple_winner_counts(hole_rows, winner_totals),
        'winner_totals': winner_totals or {},
    }]


def _build_winners_summary_table(blocks):
    """Combine every block's simple_winners into ONE table — one column
    per block (flight, or the single block), one row per rank position
    across whichever block has the most winners, cell = that flight's
    Nth-ranked winner as one descriptive string (blank if that flight has
    fewer winners than the tallest column). Replaces what used to be a
    separate stacked table per flight (2026-08-19, per @user — those, plus
    the old bottom per-flight $ totals tables, read as duplicates of each
    other)."""
    headers = [b['label'] or 'Result' for b in blocks]
    max_len = max((len(b['simple_winners']) for b in blocks), default=0)
    rows = []
    for i in range(max_len):
        row = []
        for b in blocks:
            sw = b['simple_winners']
            if i < len(sw):
                w = sw[i]
                text = f"{w['name']} - {w['wins']} skin{'s' if w['wins'] != 1 else ''}"
                if w['payout'] is not None:
                    text += f" (${w['payout']:.2f})"
                row.append(text)
            else:
                row.append(None)
        rows.append(row)
    return {'headers': headers, 'rows': rows}


def _build_full_scorecard_grid(score_table, holes):
    """One combined scorecard for the whole week's field, independent of
    any flight split — every participant x every hole, with each hole's
    outright (non-tied) winner cell flagged for highlighting. Per @user,
    2026-08-17: "a single large scorecard... just highlight the winner
    holes"."""
    hole_rows = _hole_result_rows(score_table, holes)
    winner_by_idx = [hr['winner_pid'] for hr in hole_rows]
    rows = []
    for p in (score_table['rows'] if score_table else []):
        cells, total = [], 0
        for idx, val in enumerate(p['scores']):
            cells.append({'value': val, 'is_winner': val is not None and p['pid'] == winner_by_idx[idx]})
            if val is not None:
                total += val
        rows.append({'name': p['name'], 'hcp': p['hcp'], 'cells': cells, 'total': total})
    return {'holes': holes, 'rows': rows, 'gross_net': score_table['gross_net'] if score_table else 'gross'}
