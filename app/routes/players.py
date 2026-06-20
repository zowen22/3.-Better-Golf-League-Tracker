from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import database
from database import get_db, table_exists
from routes.auth import login_required, admin_required
from datetime import datetime
import csv
import io

bp = Blueprint('players', __name__, url_prefix='/players')


@bp.route('/')
@login_required
def roster():
    db = get_db()
    league_id = session['league_id']

    players = db.execute(
        """SELECT player_id, first_name, last_name, email, starting_handicap, active
           FROM players
           WHERE league_id = %s
           ORDER BY last_name, first_name""",
        (league_id,)
    ).fetchall()

    # Load primary nicknames for roster display
    tbl_check = table_exists(db, 'player_nicknames')
    roster_nicknames = {}
    if tbl_check:
        nick_rows = db.execute(
            """SELECT player_id, nickname FROM player_nicknames
               WHERE league_id = %s AND is_primary = 1""",
            (league_id,)
        ).fetchall()
        for nr in nick_rows:
            roster_nicknames[nr['player_id']] = nr['nickname']

    # "Next step" prompt: show link to add teams if active players exist but latest season has none
    add_teams_url = None
    active_count = sum(1 for p in players if p['active'])
    if active_count >= 2 and session.get('role') == 'league_admin':
        season = db.execute(
            "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
            (league_id,)
        ).fetchone()
        if season:
            team_count = db.execute(
                "SELECT COUNT(*) AS cnt FROM teams WHERE season_id = %s AND league_id = %s",
                (season['season_id'], league_id)
            ).fetchone()
            if not team_count or team_count['cnt'] == 0:
                add_teams_url = url_for('teams.add', season_id=season['season_id'])

    return render_template('players/roster.html', players=players,
                           roster_nicknames=roster_nicknames, add_teams_url=add_teams_url)


@bp.route('/<int:player_id>')
@login_required
def profile(player_id):
    db = get_db()
    league_id = session['league_id']

    player = db.execute(
        "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    # --- Current handicap ---
    current_hcp_row = db.execute(
        """SELECT handicap_index FROM handicap_history
           WHERE player_id = %s
           ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1""",
        (player_id,)
    ).fetchone()
    if current_hcp_row:
        current_handicap = current_hcp_row['handicap_index']
    else:
        current_handicap = player['starting_handicap']

    # --- Handicap history for trend chart ---
    hcp_history = db.execute(
        """SELECT handicap_index, calculated_date
           FROM handicap_history
           WHERE player_id = %s
           ORDER BY calculated_date ASC, handicap_id ASC""",
        (player_id,)
    ).fetchall()

    # Build sparkline points (normalised 0..1 within [min,max])
    sparkline_pts = []
    if hcp_history:
        vals = [float(h['handicap_index']) for h in hcp_history]
        lo, hi = min(vals), max(vals)
        spread = hi - lo if hi != lo else 1.0
        w, h_px = 320, 80
        for i, v in enumerate(vals):
            x = round(i / max(len(vals) - 1, 1) * w, 1)
            y = round(h_px - (v - lo) / spread * (h_px - 8), 1)
            sparkline_pts.append((x, y))

    # --- Round history ---
    round_rows = db.execute(
        """SELECT
               r.round_id,
               r.round_date,
               r.round_number,
               m.matchup_id,
               m.week_number,
               m.season_id,
               s.season_name,
               sc.scorecard_id,
               sc.handicap_at_time_of_play AS hcp_used,
               c.course_name,
               te.tee_name,
               te.nine,
               COALESCE(mr.total_points,       0) AS total_pts,
               COALESCE(mr.hole_points_won,    0) AS hole_pts,
               COALESCE(mr.overall_point_won,  0) AS overall_pts,
               mr.role
           FROM scorecards sc
           JOIN rounds    r   ON sc.round_id   = r.round_id
           JOIN matchups  m   ON r.matchup_id  = m.matchup_id
           JOIN seasons   s   ON m.season_id   = s.season_id
           LEFT JOIN courses  c   ON r.course_id  = c.course_id
           LEFT JOIN tees     te  ON r.tee_id     = te.tee_id
           LEFT JOIN match_results mr
               ON mr.player_id  = sc.player_id
              AND mr.matchup_id = m.matchup_id
           WHERE sc.player_id = %s AND s.league_id = %s
             AND m.status = 'completed'
           ORDER BY r.round_date DESC, r.round_id DESC""",
        (player_id, league_id)
    ).fetchall()

    # Gross / net totals from hole_scores
    round_data = []
    for rd in round_rows:
        scores = db.execute(
            """SELECT gross_score, net_score FROM hole_scores
               WHERE scorecard_id = %s ORDER BY hole_number""",
            (rd['scorecard_id'],)
        ).fetchall()
        gross_list = [h['gross_score'] for h in scores if h['gross_score'] is not None]
        net_list   = [h['net_score']   for h in scores if h['net_score']   is not None]
        gross_total = sum(gross_list) if gross_list else None
        net_total   = int(sum(float(x) for x in net_list)) if net_list else None

        round_data.append({
            'round_date':  rd['round_date'],
            'season_name': rd['season_name'],
            'season_id':   rd['season_id'],
            'week_number': rd['week_number'],
            'course_name': rd['course_name'] or '—',
            'nine':        rd['nine'] or '—',
            'gross_total': gross_total,
            'net_total':   net_total,
            'hcp_used':    rd['hcp_used'],
            'total_pts':   rd['total_pts'],
            'role':        rd['role'] or '—',
            'matchup_id':  rd['matchup_id'],
        })

    # --- Career stats ---
    played_rounds     = len(round_data)
    all_gross         = [r['gross_total'] for r in round_data if r['gross_total'] is not None]
    best_gross        = min(all_gross) if all_gross else None
    avg_gross         = round(sum(all_gross) / len(all_gross), 1) if all_gross else None
    total_pts_career  = sum(r['total_pts'] for r in round_data)
    avg_pts           = round(total_pts_career / played_rounds, 1) if played_rounds else None

    # --- Season breakdown ---
    season_map = {}
    for r in round_data:
        sid = r['season_id']
        if sid not in season_map:
            season_map[sid] = {
                'season_name': r['season_name'],
                'rounds':      0,
                'total_pts':   0.0,
                'gross':       [],
            }
        season_map[sid]['rounds']    += 1
        season_map[sid]['total_pts'] += r['total_pts'] or 0
        if r['gross_total'] is not None:
            season_map[sid]['gross'].append(r['gross_total'])

    season_list = []
    for ss in season_map.values():
        gs = ss['gross']
        season_list.append({
            'season_name': ss['season_name'],
            'rounds':      ss['rounds'],
            'total_pts':   int(ss['total_pts']),
            'avg_gross':   round(sum(gs) / len(gs), 1) if gs else None,
            'best_gross':  min(gs) if gs else None,
        })

    # --- Hole-by-hole scoring history ---
    hole_rows = db.execute(
        """SELECT r.round_id, r.round_date, m.week_number, m.season_id, s.season_name,
                   hs.hole_number, hs.gross_score, h.par
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r ON sc.round_id = r.round_id
               JOIN matchups m ON r.matchup_id = m.matchup_id
               JOIN seasons s ON m.season_id = s.season_id
               LEFT JOIN holes h ON hs.hole_id = h.hole_id
               WHERE sc.player_id = %s AND s.league_id = %s AND m.status = 'completed'
                 AND hs.gross_score IS NOT NULL
               ORDER BY r.round_date DESC, r.round_id DESC, hs.hole_number ASC""",
        (player_id, league_id)
    ).fetchall()

    # Group by round
    rounds_by_id = {}
    round_order = []
    for hr in hole_rows:
        rid = hr['round_id']
        if rid not in rounds_by_id:
            rounds_by_id[rid] = {
                'round_id': rid,
                'round_date': hr['round_date'],
                'week_number': hr['week_number'],
                'season_name': hr['season_name'],
                'holes': {}
            }
            round_order.append(rid)
        rounds_by_id[rid]['holes'][hr['hole_number']] = {
            'gross': hr['gross_score'],
            'par': hr['par']
        }

    hole_rounds = [rounds_by_id[rid] for rid in round_order]

    # Determine hole numbers present across all rounds
    all_hole_nums = set()
    for rd in hole_rounds:
        all_hole_nums.update(rd['holes'].keys())
    hole_columns = sorted(all_hole_nums) if all_hole_nums else list(range(1, 10))

    # Per-hole averages + score distribution
    hole_avg_data = {}
    for hnum in hole_columns:
        scores = [rd['holes'][hnum]['gross'] for rd in hole_rounds if hnum in rd['holes'] and rd['holes'][hnum]['gross'] is not None]
        pars   = [rd['holes'][hnum]['par']   for rd in hole_rounds if hnum in rd['holes'] and rd['holes'][hnum]['par']   is not None]
        if not scores:
            hole_avg_data[hnum] = None
            continue
        avg = round(sum(scores) / len(scores), 2)
        par_val = pars[0] if pars else None
        eagle = birdie = par_cnt = bogey = double = 0
        for s, p in [(rd['holes'][hnum]['gross'], rd['holes'][hnum]['par']) for rd in hole_rounds if hnum in rd['holes']]:
            if s is None:
                continue
            if p is None:
                continue
            diff = s - p
            if diff <= -2:
                eagle += 1
            elif diff == -1:
                birdie += 1
            elif diff == 0:
                par_cnt += 1
            elif diff == 1:
                bogey += 1
            else:
                double += 1
        hole_avg_data[hnum] = {
            'avg': avg,
            'par': par_val,
            'count': len(scores),
            'eagle': eagle,
            'birdie': birdie,
            'par_cnt': par_cnt,
            'bogey': bogey,
            'double': double,
        }

    has_hole_history = bool(hole_rounds)

    # --- Nicknames ---
    # Check if table exists first (graceful if migration not yet run)
    tbl_check = table_exists(db, 'player_nicknames')
    if tbl_check:
        nicknames = db.execute(
            """SELECT nickname_id, nickname, is_primary
               FROM player_nicknames
               WHERE player_id = %s
               ORDER BY is_primary DESC, nickname_id ASC""",
            (player_id,)
        ).fetchall()
    else:
        nicknames = []

    primary_nickname = next((n['nickname'] for n in nicknames if n['is_primary']), None)

    # --- Committee adjustment ---
    committee_adjustment = None
    try:
        adj_row = db.execute(
            "SELECT adjustment, reason, created_at FROM handicap_adjustments WHERE player_id = %s AND league_id = %s",
            (player_id, league_id)
        ).fetchone()
        if adj_row:
            committee_adjustment = {
                'adjustment': adj_row['adjustment'],
                'reason':     adj_row['reason'],
                'created_at': adj_row['created_at'],
            }
    except Exception:
        pass  # Table not yet migrated

    return render_template('players/profile.html',
                           player=player,
                           current_handicap=current_handicap,
                           hcp_history=hcp_history,
                           sparkline_pts=sparkline_pts,
                           round_data=round_data,
                           played_rounds=played_rounds,
                           best_gross=best_gross,
                           avg_gross=avg_gross,
                           total_pts_career=int(total_pts_career),
                           avg_pts=avg_pts,
                           season_list=season_list,
                           hole_rounds=hole_rounds,
                           hole_columns=hole_columns,
                           hole_avg_data=hole_avg_data,
                           has_hole_history=has_hole_history,
                           nicknames=nicknames,
                           primary_nickname=primary_nickname,
                           committee_adjustment=committee_adjustment)


@bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add():
    if request.method == 'POST':
        first_name        = request.form.get('first_name', '').strip()
        last_name         = request.form.get('last_name', '').strip()
        email             = request.form.get('email', '').strip() or None
        starting_handicap = request.form.get('starting_handicap', '').strip() or None

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if starting_handicap is not None:
            try:
                starting_handicap = float(starting_handicap)
            except ValueError:
                errors.append('Starting handicap must be a number.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('players/add.html',
                                   first_name=first_name,
                                   last_name=last_name,
                                   email=email or '',
                                   starting_handicap=request.form.get('starting_handicap', ''))

        db = get_db()

        existing = db.execute(
            """SELECT player_id FROM players
               WHERE league_id = %s AND LOWER(first_name) = LOWER(%s) AND LOWER(last_name) = LOWER(%s)""",
            (session['league_id'], first_name, last_name)
        ).fetchone()
        if existing:
            flash(f'{first_name} {last_name} is already on the roster.', 'error')
            return render_template('players/add.html',
                                   first_name=first_name, last_name=last_name,
                                   email=email or '', starting_handicap=request.form.get('starting_handicap', ''))

        db.execute(
            """INSERT INTO players (league_id, first_name, last_name, email, starting_handicap, active, created_date)
               VALUES (%s, %s, %s, %s, %s, 1, %s)""",
            (session['league_id'], first_name, last_name, email, starting_handicap,
             datetime.now().strftime('%Y-%m-%d'))
        )
        db.commit()

        flash(f'{first_name} {last_name} added.', 'success')
        return redirect(url_for('players.add'))

    return render_template('players/add.html',
                           first_name='', last_name='', email='', starting_handicap='')


@bp.route('/import', methods=['GET', 'POST'])
@admin_required
def import_csv():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename:
            flash('Please select a CSV file to upload.', 'error')
            return redirect(url_for('players.import_csv'))

        if not file.filename.lower().endswith('.csv'):
            flash('File must be a .csv file.', 'error')
            return redirect(url_for('players.import_csv'))

        try:
            content = file.read().decode('utf-8-sig')  # strip BOM if present
        except UnicodeDecodeError:
            flash('Could not read file. Make sure it is a UTF-8 encoded CSV.', 'error')
            return redirect(url_for('players.import_csv'))

        reader = csv.DictReader(io.StringIO(content))

        # Normalize headers: lowercase, strip whitespace
        if reader.fieldnames is None:
            flash('CSV file appears to be empty.', 'error')
            return redirect(url_for('players.import_csv'))

        normalized = {h.strip().lower(): h for h in reader.fieldnames}

        required = {'first_name', 'last_name'}
        missing = required - set(normalized.keys())
        if missing:
            flash(f'CSV is missing required columns: {", ".join(sorted(missing))}. '
                  f'Expected: first_name, last_name (optional: email, starting_handicap)', 'error')
            return redirect(url_for('players.import_csv'))

        db = get_db()
        league_id = session['league_id']
        today = datetime.now().strftime('%Y-%m-%d')

        added = []
        skipped = []
        errors_list = []

        for row_num, row in enumerate(reader, start=2):
            # Re-key using normalized header map
            norm_row = {k.strip().lower(): (v.strip() if v else '') for k, v in row.items()}

            first_name = norm_row.get('first_name', '').strip()
            last_name  = norm_row.get('last_name', '').strip()
            email      = norm_row.get('email', '').strip() or None
            hdcp_raw   = norm_row.get('starting_handicap', '').strip()

            if not first_name or not last_name:
                errors_list.append(f'Row {row_num}: missing first or last name — skipped.')
                continue

            starting_handicap = None
            if hdcp_raw:
                try:
                    starting_handicap = float(hdcp_raw)
                except ValueError:
                    errors_list.append(f'Row {row_num}: invalid handicap "{hdcp_raw}" for {first_name} {last_name} — skipped.')
                    continue

            existing = db.execute(
                """SELECT player_id FROM players
                   WHERE league_id = %s AND LOWER(first_name) = LOWER(%s) AND LOWER(last_name) = LOWER(%s)""",
                (league_id, first_name, last_name)
            ).fetchone()

            if existing:
                skipped.append(f'{first_name} {last_name} (already exists)')
                continue

            db.execute(
                """INSERT INTO players (league_id, first_name, last_name, email, starting_handicap, active, created_date)
                   VALUES (%s, %s, %s, %s, %s, 1, %s)""",
                (league_id, first_name, last_name, email, starting_handicap, today)
            )
            added.append(f'{first_name} {last_name}')

        db.commit()

        return render_template('players/import_result.html',
                               added=added,
                               skipped=skipped,
                               errors_list=errors_list)

    return render_template('players/import.html')


@bp.route('/<int:player_id>/deactivate', methods=['POST'])
@admin_required
def deactivate(player_id):
    db = get_db()
    player = db.execute(
        "SELECT first_name, last_name FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, session['league_id'])
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    db.execute("UPDATE players SET active = 0 WHERE player_id = %s", (player_id,))
    db.commit()
    flash(f'{player["first_name"]} {player["last_name"]} deactivated.', 'success')
    return redirect(url_for('players.roster'))


@bp.route('/<int:player_id>/reactivate', methods=['POST'])
@admin_required
def reactivate(player_id):
    db = get_db()
    player = db.execute(
        "SELECT first_name, last_name FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, session['league_id'])
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    db.execute("UPDATE players SET active = 1 WHERE player_id = %s", (player_id,))
    db.commit()
    flash(f'{player["first_name"]} {player["last_name"]} reactivated.', 'success')
    return redirect(url_for('players.roster'))


@bp.route('/<int:player_id>/delete', methods=['POST'])
@admin_required
def delete(player_id):
    db = get_db()
    league_id = session['league_id']

    player = db.execute(
        "SELECT first_name, last_name FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    name = f'{player["first_name"]} {player["last_name"]}'

    # Safety check 1: player has any scorecards (recorded scores)
    has_scores = db.execute(
        "SELECT 1 FROM scorecards WHERE player_id = %s LIMIT 1",
        (player_id,)
    ).fetchone()
    if has_scores:
        flash(
            f'Cannot delete {name} — they have recorded scores. '
            'Deactivate them instead to hide from active rosters.',
            'error'
        )
        return redirect(url_for('players.roster'))

    # Safety check 2: player is on any team
    on_team = db.execute(
        "SELECT 1 FROM team_members WHERE player_id = %s LIMIT 1",
        (player_id,)
    ).fetchone()
    if on_team:
        flash(
            f'Cannot delete {name} — they are assigned to a team. '
            'Remove them from the team first, or deactivate instead.',
            'error'
        )
        return redirect(url_for('players.roster'))

    # Safety check 3: player has match results
    has_results = db.execute(
        "SELECT 1 FROM match_results WHERE player_id = %s LIMIT 1",
        (player_id,)
    ).fetchone()
    if has_results:
        flash(
            f'Cannot delete {name} — they have match result records. '
            'Deactivate them instead.',
            'error'
        )
        return redirect(url_for('players.roster'))

    # Safe to delete — remove handicap history first, then player
    db.execute("DELETE FROM handicap_history WHERE player_id = %s", (player_id,))
    db.execute("DELETE FROM players WHERE player_id = %s AND league_id = %s", (player_id, league_id))
    db.commit()

    flash(f'{name} has been permanently deleted.', 'success')
    return redirect(url_for('players.roster'))


@bp.route('/<int:player_id>/hole-history')
@login_required
def hole_history(player_id):
    db = get_db()
    league_id = session['league_id']

    player = db.execute(
        "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    # Available seasons (for filter dropdown)
    seasons = db.execute(
        """SELECT s.season_id, s.season_name
           FROM seasons s
           JOIN matchups m ON m.season_id = s.season_id
           JOIN rounds r ON r.matchup_id = m.matchup_id
           JOIN scorecards sc ON sc.round_id = r.round_id
           WHERE sc.player_id = %s AND s.league_id = %s AND m.status = 'completed'
           GROUP BY s.season_id ORDER BY s.season_id DESC""",
        (player_id, league_id)
    ).fetchall()

    selected_season_id = request.args.get('season_id', type=int)

    # Per-hole aggregation
    base_where = "sc.player_id = %s AND s.league_id = %s AND m.status = 'completed' AND hs.gross_score IS NOT NULL"
    params = [player_id, league_id]
    if selected_season_id:
        base_where += " AND m.season_id = %s"
        params.append(selected_season_id)

    hole_rows = db.execute(
        f"""SELECT
               hs.hole_number,
               h.par,
               COUNT(hs.gross_score) AS rounds_played,
               ROUND(AVG(CAST(hs.gross_score AS REAL)), 2) AS avg_gross,
               CASE WHEN h.par IS NOT NULL
                    THEN ROUND(AVG(CAST(hs.gross_score AS REAL)) - h.par, 2)
                    ELSE NULL END AS avg_vs_par,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score <= h.par - 2 THEN 1 ELSE 0 END) AS eagles,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score = h.par - 1 THEN 1 ELSE 0 END) AS birdies,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score = h.par     THEN 1 ELSE 0 END) AS pars,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score = h.par + 1 THEN 1 ELSE 0 END) AS bogeys,
               SUM(CASE WHEN h.par IS NOT NULL AND hs.gross_score >= h.par + 2 THEN 1 ELSE 0 END) AS doubles_plus
           FROM hole_scores hs
           JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
           JOIN rounds r ON r.round_id = sc.round_id
           JOIN matchups m ON m.matchup_id = r.matchup_id
           JOIN seasons s ON s.season_id = m.season_id
           LEFT JOIN holes h ON hs.hole_id = h.hole_id
           WHERE {base_where}
           GROUP BY hs.hole_number
           ORDER BY hs.hole_number""",
        params
    ).fetchall()

    # Build display rows with % values
    has_par = any(r['par'] is not None for r in hole_rows)
    hole_data = []
    total_rounds = total_gross = 0
    total_eagles = total_birdies = total_pars = total_bogeys = total_doubles = 0

    for r in hole_rows:
        rp = r['rounds_played']
        total_rounds += rp
        gross_sum = round(r['avg_gross'] * rp) if r['avg_gross'] is not None else 0
        total_gross += gross_sum

        def pct(count):
            return round(count * 100 / rp, 1) if rp else 0

        avg_vp = r['avg_vs_par']
        if avg_vp is not None:
            sign = '+' if avg_vp > 0 else ('' if avg_vp == 0 else '')
            avg_vs_par_fmt = f"{sign}{avg_vp:+.2f}".replace('+', '+') if avg_vp != 0 else 'E'
            # simpler
            if avg_vp > 0:
                avg_vs_par_fmt = f"+{avg_vp:.2f}"
            elif avg_vp < 0:
                avg_vs_par_fmt = f"{avg_vp:.2f}"
            else:
                avg_vs_par_fmt = 'E'
        else:
            avg_vs_par_fmt = None

        eagles = r['eagles']
        birdies = r['birdies']
        pars_c = r['pars']
        bogeys = r['bogeys']
        doubles = r['doubles_plus']
        total_eagles += eagles; total_birdies += birdies
        total_pars += pars_c; total_bogeys += bogeys; total_doubles += doubles

        hole_data.append({
            'hole_number':   r['hole_number'],
            'par':           r['par'],
            'rounds_played': rp,
            'avg_gross':     r['avg_gross'],
            'avg_vs_par':    avg_vp,
            'avg_vs_par_fmt': avg_vs_par_fmt,
            'eagles':        eagles,
            'eagles_pct':    pct(eagles),
            'birdies':       birdies,
            'birdies_pct':   pct(birdies),
            'pars':          pars_c,
            'pars_pct':      pct(pars_c),
            'bogeys':        bogeys,
            'bogeys_pct':    pct(bogeys),
            'doubles_plus':  doubles,
            'doubles_pct':   pct(doubles),
        })

    return render_template('players/hole_history.html',
                           player=player,
                           seasons=seasons,
                           selected_season_id=selected_season_id,
                           hole_data=hole_data,
                           has_par=has_par,
                           total_rounds=total_rounds,
                           total_gross=total_gross,
                           total_eagles=total_eagles,
                           total_birdies=total_birdies,
                           total_pars=total_pars,
                           total_bogeys=total_bogeys,
                           total_doubles=total_doubles)


@bp.route('/<int:player_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(player_id):
    db = get_db()
    league_id = session['league_id']

    player = db.execute(
        "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        email      = request.form.get('email', '').strip() or None
        starting_handicap_raw = request.form.get('starting_handicap', '').strip()
        notes      = request.form.get('notes', '').strip() or None

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')

        starting_handicap = None
        if starting_handicap_raw:
            try:
                starting_handicap = float(starting_handicap_raw)
            except ValueError:
                errors.append('Starting handicap must be a number.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('players/edit.html', player=player,
                                   first_name=first_name, last_name=last_name,
                                   email=email or '', starting_handicap=starting_handicap_raw,
                                   notes=notes or '')

        # Check for duplicate name (excluding self)
        dup = db.execute(
            """SELECT player_id FROM players
               WHERE league_id = %s AND LOWER(first_name) = LOWER(%s) AND LOWER(last_name) = LOWER(%s)
                 AND player_id != %s""",
            (league_id, first_name, last_name, player_id)
        ).fetchone()
        if dup:
            flash(f'A player named {first_name} {last_name} already exists.', 'error')
            return render_template('players/edit.html', player=player,
                                   first_name=first_name, last_name=last_name,
                                   email=email or '', starting_handicap=starting_handicap_raw,
                                   notes=notes or '')

        # Check if notes column exists
        if database.is_postgres():
            cols = [row[0] for row in db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='players'"
            ).fetchall()]
        else:
            cols = [row[1] for row in db.execute("PRAGMA table_info(players)").fetchall()]
        has_notes = 'notes' in cols

        if has_notes:
            db.execute(
                """UPDATE players SET first_name=%s, last_name=%s, email=%s, starting_handicap=%s, notes=%s
                   WHERE player_id=%s AND league_id=%s""",
                (first_name, last_name, email, starting_handicap, notes, player_id, league_id)
            )
        else:
            db.execute(
                """UPDATE players SET first_name=%s, last_name=%s, email=%s, starting_handicap=%s
                   WHERE player_id=%s AND league_id=%s""",
                (first_name, last_name, email, starting_handicap, player_id, league_id)
            )
        db.commit()
        flash(f'{first_name} {last_name} updated successfully.', 'success')
        return redirect(url_for('players.profile', player_id=player_id))

    # GET — check for notes column
    if database.is_postgres():
        cols = [row[0] for row in db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='players'"
        ).fetchall()]
    else:
        cols = [row[1] for row in db.execute("PRAGMA table_info(players)").fetchall()]
    has_notes = 'notes' in cols
    notes_val = player['notes'] if has_notes and 'notes' in player.keys() else ''

    return render_template('players/edit.html', player=player,
                           first_name=player['first_name'],
                           last_name=player['last_name'],
                           email=player['email'] or '',
                           starting_handicap=player['starting_handicap'] if player['starting_handicap'] is not None else '',
                           notes=notes_val or '')


# ---------------------------------------------------------------------------
# Player comparison
# ---------------------------------------------------------------------------

def _get_player_compare_stats(db, player_id, league_id):
    """Return a dict of career + scoring stats for one player."""
    player = db.execute(
        "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        return None

    # Current handicap
    hcp_row = db.execute(
        """SELECT handicap_index FROM handicap_history
           WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1""",
        (player_id,)
    ).fetchone()
    current_hcp = hcp_row['handicap_index'] if hcp_row else player['starting_handicap']

    # Handicap history (for mini sparkline)
    hcp_hist = db.execute(
        """SELECT handicap_index, calculated_date
           FROM handicap_history WHERE player_id = %s
           ORDER BY calculated_date ASC, handicap_id ASC""",
        (player_id,)
    ).fetchall()

    sparkline_pts = []
    if hcp_hist:
        vals = [float(r['handicap_index']) for r in hcp_hist]
        lo, hi = min(vals), max(vals)
        spread = hi - lo if hi != lo else 1.0
        W, H = 200, 50
        for i, v in enumerate(vals):
            x = round(i / max(len(vals) - 1, 1) * W, 1)
            y = round(H - (v - lo) / spread * (H - 6), 1)
            sparkline_pts.append((x, y))

    # Match results
    results = db.execute(
        """SELECT mr.total_points, mr.hole_points_won, mr.overall_point_won
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           JOIN seasons s ON m.season_id = s.season_id
           WHERE mr.player_id = %s AND s.league_id = %s AND m.status = 'completed'""",
        (player_id, league_id)
    ).fetchall()

    total_pts = sum(r['total_points'] for r in results)
    rounds = len(results)
    wins = sum(1 for r in results if r['overall_point_won'] == 1.0)
    ties = sum(1 for r in results if r['overall_point_won'] == 0.5)
    losses = sum(1 for r in results if r['overall_point_won'] == 0.0)

    # Scoring stats from hole_scores
    scoring = db.execute(
        """SELECT hs.gross_score, hs.score_differential, h.par, hs.hole_id
           FROM hole_scores hs
           JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
           JOIN rounds r ON sc.round_id = r.round_id
           JOIN matchups m ON r.matchup_id = m.matchup_id
           JOIN seasons s ON m.season_id = s.season_id
           LEFT JOIN holes h ON hs.hole_id = h.hole_id
           WHERE sc.player_id = %s AND s.league_id = %s AND m.status = 'completed'
             AND hs.gross_score IS NOT NULL""",
        (player_id, league_id)
    ).fetchall()

    gross_scores = [r['gross_score'] for r in scoring]
    diffs = [r['score_differential'] for r in scoring if r['score_differential'] is not None]
    eagles  = sum(1 for d in diffs if d <= -2)
    birdies = sum(1 for d in diffs if d == -1)
    pars    = sum(1 for d in diffs if d == 0)
    bogeys  = sum(1 for d in diffs if d == 1)
    doubles = sum(1 for d in diffs if d >= 2)

    # Group gross by round (scorecard_id) to get round totals
    sc_gross = {}
    sc_rows = db.execute(
        """SELECT sc.scorecard_id, SUM(hs.gross_score) AS gross_total,
                  COUNT(hs.hole_score_id) AS holes_played
           FROM hole_scores hs
           JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
           JOIN rounds r ON sc.round_id = r.round_id
           JOIN matchups m ON r.matchup_id = m.matchup_id
           JOIN seasons s ON m.season_id = s.season_id
           WHERE sc.player_id = %s AND s.league_id = %s AND m.status = 'completed'
             AND hs.gross_score IS NOT NULL
           GROUP BY sc.scorecard_id
           HAVING holes_played >= 7""",
        (player_id, league_id)
    ).fetchall()
    round_grosses = [r['gross_total'] for r in sc_rows if r['gross_total'] is not None]

    best_gross = min(round_grosses) if round_grosses else None
    avg_gross  = round(sum(round_grosses) / len(round_grosses), 1) if round_grosses else None
    avg_pts    = round(total_pts / rounds, 1) if rounds else None

    return {
        'player':        player,
        'current_hcp':   current_hcp,
        'sparkline_pts': sparkline_pts,
        'hcp_hist':      hcp_hist,
        'rounds':        rounds,
        'total_pts':     int(total_pts),
        'avg_pts':       avg_pts,
        'wins':          wins,
        'ties':          ties,
        'losses':        losses,
        'best_gross':    best_gross,
        'avg_gross':     avg_gross,
        'eagles':        eagles,
        'birdies':       birdies,
        'pars':          pars,
        'bogeys':        bogeys,
        'doubles':       doubles,
        'total_holes':   len(gross_scores),
    }


def _get_h2h(db, p1_id, p2_id, league_id):
    """Head-to-head matchup history between two players."""
    rows = db.execute(
        """SELECT mr.overall_point_won, mr.total_points, mr.hole_points_won,
                  m.matchup_id, m.week_number, m.season_id, m.scheduled_date,
                  s.season_name
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           JOIN seasons s ON m.season_id = s.season_id
           WHERE mr.player_id = %s AND mr.opponent_player_id = %s
             AND s.league_id = %s AND m.status = 'completed'
           ORDER BY m.scheduled_date DESC, m.matchup_id DESC""",
        (p1_id, p2_id, league_id)
    ).fetchall()

    # For each matchup get opponent's pts too
    h2h = []
    for r in rows:
        opp = db.execute(
            """SELECT total_points FROM match_results
               WHERE matchup_id = %s AND player_id = %s""",
            (r['matchup_id'], p2_id)
        ).fetchone()
        p2_pts = opp['total_points'] if opp else None
        h2h.append({
            'matchup_id':   r['matchup_id'],
            'week_number':  r['week_number'],
            'season_name':  r['season_name'],
            'date':         r['scheduled_date'],
            'p1_pts':       r['total_points'],
            'p2_pts':       p2_pts,
            'p1_result':    r['overall_point_won'],  # 1.0 win / 0.5 tie / 0.0 loss
        })
    return h2h


# ──────────────────────────────────────────────────────────────────────────────
# Nickname management
# ──────────────────────────────────────────────────────────────────────────────

@bp.route('/<int:player_id>/nicknames/add', methods=['POST'])
@admin_required
def add_nickname(player_id):
    db = get_db()
    league_id = session['league_id']
    player = db.execute(
        "SELECT player_id FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    nickname = request.form.get('nickname', '').strip()
    if not nickname:
        flash('Nickname cannot be blank.', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    if len(nickname) > 40:
        flash('Nickname must be 40 characters or fewer.', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    # Check for duplicate (case-insensitive) within this league
    existing = db.execute(
        "SELECT nickname_id FROM player_nicknames WHERE player_id = %s AND LOWER(nickname) = LOWER(%s)",
        (player_id, nickname)
    ).fetchone()
    if existing:
        flash(f'"{nickname}" is already saved for this player.', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    # First nickname auto-becomes primary
    count = db.execute(
        "SELECT COUNT(*) AS n FROM player_nicknames WHERE player_id = %s", (player_id,)
    ).fetchone()['n']
    is_primary = 1 if count == 0 else 0

    db.execute(
        "INSERT INTO player_nicknames (player_id, league_id, nickname, is_primary) VALUES (%s,%s,%s,%s)",
        (player_id, league_id, nickname, is_primary)
    )
    db.commit()
    flash(f'Nickname "{nickname}" added.', 'success')
    return redirect(url_for('players.profile', player_id=player_id))


@bp.route('/<int:player_id>/nicknames/<int:nickname_id>/delete', methods=['POST'])
@admin_required
def delete_nickname(player_id, nickname_id):
    db = get_db()
    league_id = session['league_id']
    row = db.execute(
        "SELECT * FROM player_nicknames WHERE nickname_id = %s AND player_id = %s AND league_id = %s",
        (nickname_id, player_id, league_id)
    ).fetchone()
    if not row:
        flash('Nickname not found.', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    was_primary = row['is_primary']
    db.execute("DELETE FROM player_nicknames WHERE nickname_id = %s", (nickname_id,))
    db.commit()

    # If deleted nickname was primary, promote the next oldest one
    if was_primary:
        next_nick = db.execute(
            "SELECT nickname_id FROM player_nicknames WHERE player_id = %s ORDER BY nickname_id ASC LIMIT 1",
            (player_id,)
        ).fetchone()
        if next_nick:
            db.execute(
                "UPDATE player_nicknames SET is_primary = 1 WHERE nickname_id = %s",
                (next_nick['nickname_id'],)
            )
            db.commit()

    flash('Nickname removed.', 'success')
    return redirect(url_for('players.profile', player_id=player_id))


@bp.route('/<int:player_id>/nicknames/<int:nickname_id>/set-primary', methods=['POST'])
@admin_required
def set_primary_nickname(player_id, nickname_id):
    db = get_db()
    league_id = session['league_id']
    row = db.execute(
        "SELECT nickname_id FROM player_nicknames WHERE nickname_id = %s AND player_id = %s AND league_id = %s",
        (nickname_id, player_id, league_id)
    ).fetchone()
    if not row:
        flash('Nickname not found.', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    db.execute("UPDATE player_nicknames SET is_primary = 0 WHERE player_id = %s", (player_id,))
    db.execute("UPDATE player_nicknames SET is_primary = 1 WHERE nickname_id = %s", (nickname_id,))
    db.commit()
    flash('Primary nickname updated.', 'success')
    return redirect(url_for('players.profile', player_id=player_id))


# ─────────────────────────────────────────────
#  Player vs Player Comparison
# ─────────────────────────────────────────────

@bp.route('/compare')
@login_required
def compare():
    """Side-by-side comparison of two players."""
    db = get_db()
    league_id = session['league_id']

    # All active players for the selector dropdowns
    all_players = db.execute(
        """SELECT player_id, first_name, last_name
           FROM players WHERE league_id = %s AND active = 1
           ORDER BY last_name, first_name""",
        (league_id,)
    ).fetchall()

    p1_id = request.args.get('p1', type=int)
    p2_id = request.args.get('p2', type=int)

    # Show empty selector if neither chosen
    if not p1_id or not p2_id or p1_id == p2_id:
        return render_template(
            'players/compare.html',
            all_players=all_players,
            p1=None, p2=None,
            p1_id=p1_id, p2_id=p2_id,
            comparison=None
        )

    def _get_player(pid):
        return db.execute(
            "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
            (pid, league_id)
        ).fetchone()

    p1 = _get_player(p1_id)
    p2 = _get_player(p2_id)
    if not p1 or not p2:
        flash('One or both players not found.', 'error')
        return redirect(url_for('players.compare'))

    def _current_hcp(pid):
        row = db.execute(
            """SELECT handicap_index FROM handicap_history
               WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1""",
            (pid,)
        ).fetchone()
        return row['handicap_index'] if row else None

    def _hcp_history(pid):
        rows = db.execute(
            """SELECT handicap_index, calculated_date FROM handicap_history
               WHERE player_id = %s ORDER BY calculated_date ASC, handicap_id ASC""",
            (pid,)
        ).fetchall()
        return [(r['calculated_date'], float(r['handicap_index'])) for r in rows]

    def _season_stats(pid):
        """Per-season: rounds, total_pts, avg_gross."""
        rows = db.execute(
            """SELECT s.season_id, s.season_name,
                      COUNT(DISTINCT r.round_id) AS rounds,
                      SUM(mr.total_points) AS total_pts
               FROM scorecards sc
               JOIN rounds r ON sc.round_id = r.round_id
               JOIN matchups m ON r.matchup_id = m.matchup_id
               JOIN seasons s ON m.season_id = s.season_id
               LEFT JOIN match_results mr ON mr.player_id = sc.player_id AND mr.matchup_id = m.matchup_id
               WHERE sc.player_id = %s AND s.league_id = %s AND m.status = 'completed'
               GROUP BY s.season_id
               ORDER BY s.season_id""",
            (pid, league_id)
        ).fetchall()
        return rows

    def _career_gross(pid):
        """All gross totals per round."""
        rows = db.execute(
            """SELECT r.round_id, SUM(hs.gross_score) AS gross_total
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r ON sc.round_id = r.round_id
               JOIN matchups m ON r.matchup_id = m.matchup_id
               JOIN seasons s ON m.season_id = s.season_id
               WHERE sc.player_id = %s AND s.league_id = %s AND m.status = 'completed'
                 AND hs.gross_score IS NOT NULL
               GROUP BY r.round_id
               HAVING COUNT(hs.gross_score) >= 9""",
            (pid, league_id)
        ).fetchall()
        return [r['gross_total'] for r in rows]

    def _score_distribution(pid):
        """Eagle / Birdie / Par / Bogey / Double+ counts across all career holes."""
        rows = db.execute(
            """SELECT hs.score_differential
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r ON sc.round_id = r.round_id
               JOIN matchups m ON r.matchup_id = m.matchup_id
               JOIN seasons s ON m.season_id = s.season_id
               WHERE sc.player_id = %s AND s.league_id = %s AND m.status = 'completed'
                 AND hs.score_differential IS NOT NULL""",
            (pid, league_id)
        ).fetchall()
        eagle = birdie = par = bogey = double = 0
        for r in rows:
            d = r['score_differential']
            if d <= -2: eagle += 1
            elif d == -1: birdie += 1
            elif d == 0: par += 1
            elif d == 1: bogey += 1
            else: double += 1
        total = eagle + birdie + par + bogey + double
        def pct(n): return round(n / total * 100, 1) if total else 0
        return {
            'eagle': eagle, 'birdie': birdie, 'par': par, 'bogey': bogey, 'double': double,
            'total': total,
            'eagle_pct': pct(eagle), 'birdie_pct': pct(birdie), 'par_pct': pct(par),
            'bogey_pct': pct(bogey), 'double_pct': pct(double),
        }

    def _shared_rounds(pid1, pid2):
        """Matchups where both players played, with pts for each."""
        rows = db.execute(
            """SELECT
                   m.matchup_id, m.week_number, m.scheduled_date, m.season_id,
                   s.season_name,
                   mr1.total_points AS p1_pts, mr1.overall_point_won AS p1_win,
                   mr2.total_points AS p2_pts, mr2.overall_point_won AS p2_win
               FROM matchups m
               JOIN seasons s ON m.season_id = s.season_id
               JOIN match_results mr1 ON mr1.matchup_id = m.matchup_id AND mr1.player_id = %s
               JOIN match_results mr2 ON mr2.matchup_id = m.matchup_id AND mr2.player_id = %s
               WHERE s.league_id = %s AND m.status = 'completed'
                 AND mr1.team_id = mr2.team_id
               ORDER BY m.scheduled_date DESC, m.matchup_id DESC""",
            (pid1, pid2, league_id)
        ).fetchall()
        return rows

    def _h2h_records(pid1, pid2):
        """Direct head-to-head: when they were on OPPOSITE teams in the same matchup."""
        rows = db.execute(
            """SELECT
                   m.matchup_id, m.week_number, m.scheduled_date, m.season_id,
                   s.season_name,
                   mr1.total_points AS p1_pts, mr1.overall_point_won AS p1_win,
                   mr2.total_points AS p2_pts, mr2.overall_point_won AS p2_win,
                   mr1.role AS p1_role, mr2.role AS p2_role
               FROM matchups m
               JOIN seasons s ON m.season_id = s.season_id
               JOIN match_results mr1 ON mr1.matchup_id = m.matchup_id AND mr1.player_id = %s
               JOIN match_results mr2 ON mr2.matchup_id = m.matchup_id AND mr2.player_id = %s
               WHERE s.league_id = %s AND m.status = 'completed'
                 AND mr1.team_id != mr2.team_id
                 AND mr1.role = mr2.role
               ORDER BY m.scheduled_date DESC, m.matchup_id DESC""",
            (pid1, pid2, league_id)
        ).fetchall()
        return rows

    # ── Gather data ──────────────────────────────────────
    p1_hcp      = _current_hcp(p1_id)
    p2_hcp      = _current_hcp(p2_id)
    p1_hcp_hist = _hcp_history(p1_id)
    p2_hcp_hist = _hcp_history(p2_id)
    p1_gross    = _career_gross(p1_id)
    p2_gross    = _career_gross(p2_id)
    p1_dist     = _score_distribution(p1_id)
    p2_dist     = _score_distribution(p2_id)
    p1_seasons  = _season_stats(p1_id)
    p2_seasons  = _season_stats(p2_id)
    h2h_rows    = _h2h_records(p1_id, p2_id)
    partner_rows = _shared_rounds(p1_id, p2_id)

    # H2H summary
    p1_wins = p1_ties = p1_losses = 0
    for row in h2h_rows:
        w = row['p1_win']
        if w == 1.0:   p1_wins += 1
        elif w == 0.5: p1_ties += 1
        else:          p1_losses += 1
    p2_wins = p1_losses
    p2_ties = p1_ties
    p2_losses = p1_wins

    # Career stats summary
    def _stats_from_gross(gross_list, seasons_rows):
        rounds    = len(gross_list)
        avg_gross = round(sum(gross_list) / rounds, 1) if rounds else None
        best      = min(gross_list) if gross_list else None
        total_pts = sum(r['total_pts'] or 0 for r in seasons_rows)
        return {
            'rounds':    rounds,
            'avg_gross': avg_gross,
            'best':      best,
            'total_pts': int(total_pts),
        }

    p1_stats = _stats_from_gross(p1_gross, p1_seasons)
    p2_stats = _stats_from_gross(p2_gross, p2_seasons)

    # Handicap chart data (serialize for JS)
    def _hcp_chart(hist):
        return {
            'labels': [d for d, _ in hist],
            'values': [v for _, v in hist],
        }

    comparison = {
        'p1_hcp': p1_hcp, 'p2_hcp': p2_hcp,
        'p1_stats': p1_stats, 'p2_stats': p2_stats,
        'p1_dist': p1_dist, 'p2_dist': p2_dist,
        'p1_hcp_chart': _hcp_chart(p1_hcp_hist),
        'p2_hcp_chart': _hcp_chart(p2_hcp_hist),
        'h2h_rows': h2h_rows,
        'partner_rows': partner_rows,
        'p1_wins': p1_wins, 'p1_ties': p1_ties, 'p1_losses': p1_losses,
        'p2_wins': p2_wins, 'p2_ties': p2_ties, 'p2_losses': p2_losses,
        'h2h_count': len(h2h_rows),
        'partner_count': len(partner_rows),
    }

    return render_template(
        'players/compare.html',
        all_players=all_players,
        p1=p1, p2=p2,
        p1_id=p1_id, p2_id=p2_id,
        comparison=comparison
    )


# ---------------------------------------------------------------------------
# Email opt-out toggle
# ---------------------------------------------------------------------------

@bp.route('/<int:player_id>/email-opt-out', methods=['POST'])
@login_required
def toggle_email_opt_out(player_id):
    """Allow admin or the linked player themselves to toggle email opt-out."""
    db = get_db()
    league_id = session['league_id']
    is_admin   = session.get('role') == 'league_admin'
    own_pid    = session.get('player_id')          # set for linked user accounts

    # Security: only admin or the player themselves may change this
    if not is_admin and own_pid != player_id:
        flash('You do not have permission to change that setting.', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    player = db.execute(
        "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    # Gracefully handle pre-migration state (column absent)
    try:
        current = player['email_opt_out']
    except IndexError:
        flash('Email preference column not yet migrated. Run migrate_email_opt_out.py.', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    new_val = 0 if current else 1
    db.execute(
        "UPDATE players SET email_opt_out = %s WHERE player_id = %s AND league_id = %s",
        (new_val, player_id, league_id)
    )
    db.commit()

    if new_val:
        flash('Email notifications turned off for this player.', 'success')
    else:
        flash('Email notifications turned back on for this player.', 'success')

    return redirect(url_for('players.profile', player_id=player_id))


# ---------------------------------------------------------------------------
# Handicap Committee Adjustment
# ---------------------------------------------------------------------------

@bp.route('/<int:player_id>/set-adjustment', methods=['POST'])
@login_required
@admin_required
def set_adjustment(player_id):
    """Set (or remove) a committee handicap adjustment for a player."""
    db        = get_db()
    league_id = session['league_id']

    player = db.execute(
        "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    raw_adj = request.form.get('adjustment', '').strip()
    reason  = request.form.get('reason', '').strip()[:200]
    action  = request.form.get('action', 'save')

    if action == 'remove':
        # Delete any existing adjustment for this player
        try:
            db.execute(
                "DELETE FROM handicap_adjustments WHERE player_id = %s AND league_id = %s",
                (player_id, league_id)
            )
            db.commit()
            flash('Committee adjustment removed.', 'success')
        except Exception:
            flash('Could not remove adjustment (run migrate_handicap_adjustments.py first).', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    # Validate adjustment value
    try:
        adjustment = float(raw_adj)
    except (ValueError, TypeError):
        flash('Adjustment must be a number (e.g. 2, -1, 0.5).', 'error')
        return redirect(url_for('players.profile', player_id=player_id))

    if adjustment == 0:
        # Treat 0 as remove
        try:
            db.execute(
                "DELETE FROM handicap_adjustments WHERE player_id = %s AND league_id = %s",
                (player_id, league_id)
            )
            db.commit()
        except Exception:
            pass
        flash('Adjustment set to 0 — committee adjustment cleared.', 'success')
        return redirect(url_for('players.profile', player_id=player_id))

    user_id = session.get('user_id')
    try:
        db.execute(
            """INSERT INTO handicap_adjustments
                   (player_id, league_id, adjustment, reason, created_at, created_by_user_id)
               VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
               ON CONFLICT(player_id, league_id) DO UPDATE SET
                   adjustment         = excluded.adjustment,
                   reason             = excluded.reason,
                   created_at         = CURRENT_TIMESTAMP,
                   created_by_user_id = excluded.created_by_user_id""",
            (player_id, league_id, adjustment, reason or None, user_id)
        )
        db.commit()
        sign = '+' if adjustment > 0 else ''
        flash(f'Committee adjustment set to {sign}{adjustment:.1f} strokes.', 'success')
    except Exception as e:
        if 'no such table' in str(e).lower():
            flash('Run migrate_handicap_adjustments.py to enable this feature.', 'error')
        else:
            flash(f'Error saving adjustment: {e}', 'error')

    return redirect(url_for('players.profile', player_id=player_id))


# ---------------------------------------------------------------------------
# Handicap Calculation Detail  /players/<id>/handicap-detail
# ---------------------------------------------------------------------------

@bp.route('/<int:player_id>/handicap-detail')
@login_required
def handicap_detail(player_id):
    db = get_db()
    league_id = session['league_id']

    player = db.execute(
        "SELECT * FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found.', 'error')
        return redirect(url_for('players.roster'))

    # Use session season_id (or most recent)
    season_id = session.get('season_id')
    if not season_id:
        s_row = db.execute(
            "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
            (league_id,)
        ).fetchone()
        season_id = s_row['season_id'] if s_row else None

    # Settings
    from routes.handicap import _get_settings
    s = _get_settings(db, season_id, league_id) if season_id else {}

    min_rounds    = int(s.get('min_rounds_for_handicap', 2))
    rounds_to_avg = int(s.get('rounds_to_average', 4))
    high_drop     = int(s.get('high_scores_to_drop', 1))
    low_drop      = int(s.get('low_scores_to_drop', 0))
    padding       = int(s.get('padding_score_count', 0))
    hcp_pct       = float(s.get('handicap_percent', 90.0))
    max_hcp       = float(s.get('max_handicap_index', 18.0))
    neg_allowed   = bool(s.get('negative_handicap_allowed', 1))
    carry_across  = bool(s.get('carry_scores_across_seasons', 1))

    window = rounds_to_avg + high_drop + low_drop

    # Player-level cutoff date
    p_row = db.execute("SELECT oldest_score_date FROM players WHERE player_id = %s", (player_id,)).fetchone()
    oldest_date = p_row['oldest_score_date'] if p_row else None

    # Fetch all real rounds oldest→newest (same query as engine)
    q = """
        SELECT r.round_id, r.round_date, r.season_id,
               SUM(hs.gross_score) AS total_gross,
               t.par_total,
               c.course_name, t.tee_name,
               sn.season_name,
               sc.scorecard_id, m.matchup_id, m.week_number
          FROM scorecards sc
          JOIN rounds      r  ON sc.round_id     = r.round_id
          JOIN tees        t  ON r.tee_id         = t.tee_id
          JOIN hole_scores hs ON hs.scorecard_id  = sc.scorecard_id
          JOIN seasons     sn ON r.season_id      = sn.season_id
          JOIN matchups    m  ON r.matchup_id     = m.matchup_id
          LEFT JOIN courses c ON r.course_id      = c.course_id
         WHERE sc.player_id = %s AND sn.league_id = %s
           AND m.status = 'completed'
    """
    params = [player_id, league_id]
    if not carry_across and season_id:
        q += " AND r.season_id = %s"
        params.append(season_id)
    if oldest_date:
        q += " AND r.round_date >= %s"
        params.append(oldest_date)
    q += " GROUP BY sc.scorecard_id, r.round_id, r.round_date, r.season_id, t.par_total, c.course_name, t.tee_name, sn.season_name, m.matchup_id, m.week_number ORDER BY r.round_date ASC, r.round_id ASC"

    all_rounds = db.execute(q, params).fetchall()
    real_count = len(all_rounds)

    # Build dicts with diff, all start as outside
    all_round_data = []
    for rr in all_rounds:
        diff = float(rr['total_gross']) - float(rr['par_total'])
        all_round_data.append({
            'round_id':    rr['round_id'],
            'round_date':  rr['round_date'],
            'season_name': rr['season_name'],
            'week_number': rr['week_number'],
            'course_name': rr['course_name'] or '—',
            'tee_name':    rr['tee_name'] or '—',
            'gross':       int(rr['total_gross']),
            'par':         int(rr['par_total']),
            'diff':        diff,
            'matchup_id':  rr['matchup_id'],
            'in_window':   False,
            'status':      'outside',
        })

    # Mark window rounds (most recent `window`)
    window_start_i = max(0, len(all_round_data) - window)
    for i in range(window_start_i, len(all_round_data)):
        all_round_data[i]['in_window'] = True

    window_rounds = all_round_data[window_start_i:]

    # Padding entries (prepended to window, each diff=0)
    pad_entries = []
    if padding > 0 and len(window_rounds) < window:
        n_pads = min(padding, window - len(window_rounds))
        for _ in range(n_pads):
            pad_entries.append({
                'round_id': None, 'round_date': None, 'season_name': '—',
                'week_number': None, 'course_name': 'Scratch Pad (0 diff)',
                'tee_name': '—', 'gross': 0, 'par': 0, 'diff': 0.0,
                'matchup_id': None, 'in_window': True, 'status': 'padding',
            })

    combined_window = pad_entries + list(window_rounds)

    # Assign dropped/counting status
    if combined_window:
        sorted_idx = sorted(range(len(combined_window)), key=lambda i: combined_window[i]['diff'])
        dropped_idxs = set()
        # Mark low_drop lowest
        for i in range(low_drop):
            if i < len(sorted_idx):
                dropped_idxs.add(sorted_idx[i])
                combined_window[sorted_idx[i]]['status'] = 'dropped_low'
        # Mark high_drop highest
        for i in range(high_drop):
            pos = len(sorted_idx) - 1 - i
            if pos >= 0 and sorted_idx[pos] not in dropped_idxs:
                dropped_idxs.add(sorted_idx[pos])
                combined_window[sorted_idx[pos]]['status'] = 'dropped_high'
        # Remaining → counting
        for entry in combined_window:
            if entry['status'] == 'outside':
                entry['status'] = 'counting'

    # Formula
    counting_diffs = [e['diff'] for e in combined_window if e['status'] == 'counting']
    has_enough = real_count >= min_rounds
    avg_diff = (sum(counting_diffs) / len(counting_diffs)) if counting_diffs else None
    computed_index = None
    if avg_diff is not None and has_enough:
        computed_index = round(avg_diff * (hcp_pct / 100.0), 1)
        computed_index = min(computed_index, max_hcp)
        if not neg_allowed:
            computed_index = max(computed_index, 0.0)

    # Current stored handicap
    ch_row = db.execute(
        "SELECT handicap_index, calculated_date FROM handicap_history "
        "WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1",
        (player_id,)
    ).fetchone()
    current_handicap = ch_row['handicap_index'] if ch_row else player['starting_handicap']
    last_calc_date   = ch_row['calculated_date'] if ch_row else None

    # Committee adjustment
    committee_adjustment = 0.0
    adj_reason = None
    try:
        adj_row = db.execute(
            "SELECT adjustment, reason FROM handicap_adjustments "
            "WHERE player_id = %s AND league_id = %s",
            (player_id, league_id)
        ).fetchone()
        if adj_row:
            committee_adjustment = float(adj_row['adjustment'] or 0)
            adj_reason = adj_row['reason']
    except Exception:
        pass

    # Full handicap history (newest first)
    hcp_history = db.execute(
        "SELECT handicap_index, calculated_date FROM handicap_history "
        "WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC",
        (player_id,)
    ).fetchall()

    return render_template('players/handicap_detail.html',
        player=player,
        current_handicap=current_handicap,
        last_calc_date=last_calc_date,
        committee_adjustment=committee_adjustment,
        adj_reason=adj_reason,
        all_round_data=list(reversed(all_round_data)),
        combined_window=list(reversed(combined_window)),
        real_count=real_count,
        has_enough=has_enough,
        min_rounds=min_rounds,
        rounds_to_avg=rounds_to_avg,
        high_drop=high_drop,
        low_drop=low_drop,
        padding=padding,
        hcp_pct=hcp_pct,
        max_hcp=max_hcp,
        neg_allowed=neg_allowed,
)
