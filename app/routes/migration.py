"""
Migration blueprint — import league data from CSV exports (e.g. golfleaguetracker.com).

Flow:
  GET  /admin/migrate                  Upload page
  POST /admin/migrate/upload           Parse CSVs → temp JSON → redirect to preview
  GET  /admin/migrate/preview          Show summary of what will be imported
  POST /admin/migrate/confirm          Execute import into DB
  POST /admin/migrate/cancel           Clear session state

Expected CSV formats
--------------------
players.csv  : first_name, last_name [, email, handicap]
               OR: name (split on first space), [email, handicap]
teams.csv    : team_name, player1, player2   (player columns = "First Last" strings)
schedule.csv : week, date, home_team, away_team [, course]
scores.csv   : date, player, hole_1..hole_9 [or hole_1..hole_18] [, course]
               OR GLT columns: Date, Player, H1..H9

Column names are normalised (lowercase, strip whitespace, common aliases mapped).
"""

import csv
import io
import json
import os
import uuid
import zipfile
from datetime import datetime

from flask import (Blueprint, Response, flash, redirect, render_template,
                   request, session, url_for)

import database
from database import get_db
from routes.auth import admin_required
from routes.handicap import recalc_all_for_season

bp = Blueprint('migration', __name__, url_prefix='/admin/migrate')

# ── Temp storage dir for parsed import data ──────────────────────────────────
_TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'import_tmp')


def _ensure_tmp():
    os.makedirs(_TMP_DIR, exist_ok=True)


def _save_import(data: dict) -> str:
    _ensure_tmp()
    key = str(uuid.uuid4())
    path = os.path.join(_TMP_DIR, f'{key}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return key


def _load_import(key: str) -> dict | None:
    if not key:
        return None
    path = os.path.join(_TMP_DIR, f'{key}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _delete_import(key: str):
    if not key:
        return
    path = os.path.join(_TMP_DIR, f'{key}.json')
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# ── Column name normalisation helpers ────────────────────────────────────────

_PLAYER_ALIASES = {
    'firstname': 'first_name', 'first': 'first_name',
    'lastname': 'last_name', 'last': 'last_name', 'surname': 'last_name',
    'emailaddress': 'email', 'e-mail': 'email',
    'handicapindex': 'handicap', 'handicap_index': 'handicap',
    'startinghandicap': 'handicap', 'starting_handicap': 'handicap',
    'index': 'handicap', 'hcp': 'handicap',
}

_TEAM_ALIASES = {
    'teamname': 'team_name', 'name': 'team_name', 'team': 'team_name',
    'player1': 'player1', 'player_1': 'player1', 'player 1': 'player1',
    'member1': 'player1', 'member_1': 'player1',
    'player2': 'player2', 'player_2': 'player2', 'player 2': 'player2',
    'member2': 'player2', 'member_2': 'player2',
}

_SCHED_ALIASES = {
    'weeknumber': 'week', 'week_number': 'week', 'round': 'week',
    'roundnumber': 'week', 'round_number': 'week',
    'matchdate': 'date', 'matchup_date': 'date', 'gamedate': 'date',
    'hometeam': 'home_team', 'home': 'home_team',
    'awayteam': 'away_team', 'away': 'away_team', 'visitor': 'away_team',
    'visitingteam': 'away_team',
    'coursename': 'course',
}


def _norm(h: str) -> str:
    return h.strip().lower().replace(' ', '_').replace('-', '_')


def _map_headers(raw_headers, alias_map):
    """Return dict: normalised_key → original_header (for DictReader)."""
    out = {}
    for h in raw_headers:
        n = _norm(h)
        mapped = alias_map.get(n, n)
        out[mapped] = h
    return out


def _read_csv_bytes(b: bytes) -> list[dict]:
    text = b.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


# ── Per-file parsers ──────────────────────────────────────────────────────────

def _parse_players(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Return (players_list, errors)."""
    players, errors = [], []
    if not rows:
        return players, ['Players CSV is empty.']
    raw_h = list(rows[0].keys())
    hmap = _map_headers(raw_h, _PLAYER_ALIASES)

    for i, row in enumerate(rows, 1):
        def g(k):
            orig = hmap.get(k)
            return row.get(orig, '').strip() if orig else ''

        first = g('first_name')
        last = g('last_name')

        # If no separate first/last, try 'name' column
        if not first and not last:
            name_col = hmap.get('name') or next(
                (h for h in raw_h if _norm(h) in ('name', 'player', 'player_name')), None
            )
            full = row.get(name_col, '').strip() if name_col else ''
            if not full:
                errors.append(f'Row {i}: no name found — skipped.')
                continue
            parts = full.split(None, 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ''

        if not first:
            errors.append(f'Row {i}: missing first name — skipped.')
            continue

        try:
            hcp = float(g('handicap')) if g('handicap') else 0.0
        except ValueError:
            hcp = 0.0

        players.append({
            'first_name': first.strip().title(),
            'last_name': last.strip().title(),
            'email': g('email').lower(),
            'handicap': hcp,
        })
    return players, errors


def _parse_teams(rows: list[dict]) -> tuple[list[dict], list[str]]:
    teams, errors = [], []
    if not rows:
        return teams, []
    raw_h = list(rows[0].keys())
    hmap = _map_headers(raw_h, _TEAM_ALIASES)

    for i, row in enumerate(rows, 1):
        def g(k):
            orig = hmap.get(k)
            return row.get(orig, '').strip() if orig else ''

        team_name = g('team_name')
        p1 = g('player1')
        p2 = g('player2')

        if not p1 and not p2 and not team_name:
            continue  # blank row

        if not p1:
            errors.append(f'Teams row {i}: missing player1 — skipped.')
            continue

        teams.append({
            'team_name': team_name,
            'player1': p1,
            'player2': p2,
        })
    return teams, errors


def _parse_schedule(rows: list[dict]) -> tuple[list[dict], list[str]]:
    sched, errors = [], []
    if not rows:
        return sched, []
    raw_h = list(rows[0].keys())
    hmap = _map_headers(raw_h, _SCHED_ALIASES)

    for i, row in enumerate(rows, 1):
        def g(k):
            orig = hmap.get(k)
            return row.get(orig, '').strip() if orig else ''

        home = g('home_team')
        away = g('away_team')
        if not home and not away:
            continue

        try:
            week = int(g('week')) if g('week') else i
        except ValueError:
            week = i

        sched.append({
            'week': week,
            'date': g('date'),
            'home_team': home,
            'away_team': away,
            'course': g('course'),
        })
    return sched, errors


def _parse_scores(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Parse score rows. Detect 9-hole or 18-hole columns dynamically."""
    scores, errors = [], []
    if not rows:
        return scores, []

    raw_h = list(rows[0].keys())
    norm_h = [_norm(h) for h in raw_h]

    # Detect hole columns: hole_1..hole_18 or h1..h18 or 1..18
    hole_cols = []
    for h in raw_h:
        n = _norm(h)
        # Patterns: hole_1, hole1, h1, or just '1'
        for prefix in ('hole_', 'hole', 'h', ''):
            if n.startswith(prefix):
                suffix = n[len(prefix):]
                if suffix.isdigit():
                    hole_num = int(suffix)
                    if 1 <= hole_num <= 18:
                        hole_cols.append((hole_num, h))
                        break
    hole_cols.sort(key=lambda x: x[0])

    if not hole_cols:
        return scores, ['Scores CSV: no hole columns detected (expected hole_1..hole_9 or H1..H18 etc.)']

    # Detect player / date columns
    player_col = next((h for h in raw_h if _norm(h) in ('player', 'player_name', 'name', 'golfer')), None)
    date_col = next((h for h in raw_h if _norm(h) in ('date', 'round_date', 'game_date', 'matchdate')), None)
    team_col = next((h for h in raw_h if _norm(h) in ('team', 'team_name')), None)
    course_col = next((h for h in raw_h if _norm(h) in ('course', 'course_name', 'coursename')), None)

    for i, row in enumerate(rows, 1):
        player_name = row.get(player_col, '').strip() if player_col else ''
        if not player_name:
            continue  # skip header-like blank rows

        holes = []
        for (hole_num, col) in hole_cols:
            val = row.get(col, '').strip()
            try:
                holes.append((hole_num, int(val)))
            except (ValueError, TypeError):
                holes.append((hole_num, None))

        scores.append({
            'date': row.get(date_col, '').strip() if date_col else '',
            'player': player_name,
            'team': row.get(team_col, '').strip() if team_col else '',
            'course': row.get(course_col, '').strip() if course_col else '',
            'holes': holes,  # list of (hole_number, gross_score)
        })
    return scores, errors


# ── File extraction helper ────────────────────────────────────────────────────

def _extract_files(request_files) -> dict[str, bytes]:
    """Return dict: csv_type → bytes. Handles individual CSVs and ZIP."""
    result = {}
    known = {'players': None, 'teams': None, 'schedule': None, 'scores': None}

    # Handle individual named file inputs
    for key in ('players', 'teams', 'schedule', 'scores'):
        f = request_files.get(key)
        if f and f.filename:
            result[key] = f.read()

    # Handle ZIP upload
    zip_file = request_files.get('zip_file')
    if zip_file and zip_file.filename:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_file.read())) as zf:
                for name in zf.namelist():
                    base = os.path.basename(name).lower()
                    for key in known:
                        if base.startswith(key) and base.endswith('.csv'):
                            if key not in result:
                                result[key] = zf.read(name)
                            break
        except zipfile.BadZipFile:
            pass

    return result


# ── Template downloads ────────────────────────────────────────────────────────

_TEMPLATES = {
    'players': (
        ['first_name', 'last_name', 'email', 'handicap'],
        [['Jane', 'Doe', 'jane@example.com', '12.4']],
    ),
    'teams': (
        ['team_name', 'player1', 'player2'],
        [['The Duffers', 'Jane Doe', 'John Smith']],
    ),
    'schedule': (
        ['week', 'date', 'home_team', 'away_team'],
        [['1', '2026-04-07', 'The Duffers', 'Sand Trappers']],
    ),
    'scores': (
        ['date', 'player', 'hole_1', 'hole_2', 'hole_3', 'hole_4', 'hole_5',
         'hole_6', 'hole_7', 'hole_8', 'hole_9'],
        [['2026-04-07', 'Jane Doe', '4', '5', '3', '4', '4', '5', '3', '4', '5']],
    ),
}


@bp.route('/template/<name>', methods=['GET'])
@admin_required
def template(name):
    spec = _TEMPLATES.get(name)
    if not spec:
        flash('Unknown template.', 'error')
        return redirect(url_for('migration.index'))
    headers, rows = spec
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{name}_template.csv"'},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@bp.route('/', methods=['GET'])
@admin_required
def index():
    return render_template('migration/index.html')


@bp.route('/upload', methods=['POST'])
@admin_required
def upload():
    files = _extract_files(request.files)

    if not files:
        flash('Please upload at least a players CSV or a ZIP file.', 'error')
        return redirect(url_for('migration.index'))

    parsed = {'players': [], 'teams': [], 'schedule': [], 'scores': [], 'errors': []}

    if 'players' in files:
        rows = _read_csv_bytes(files['players'])
        p, errs = _parse_players(rows)
        parsed['players'] = p
        parsed['errors'] += errs

    if 'teams' in files:
        rows = _read_csv_bytes(files['teams'])
        t, errs = _parse_teams(rows)
        parsed['teams'] = t
        parsed['errors'] += errs

    if 'schedule' in files:
        rows = _read_csv_bytes(files['schedule'])
        s, errs = _parse_schedule(rows)
        parsed['schedule'] = s
        parsed['errors'] += errs

    if 'scores' in files:
        rows = _read_csv_bytes(files['scores'])
        sc, errs = _parse_scores(rows)
        parsed['scores'] = sc
        parsed['errors'] += errs

    if not parsed['players']:
        flash('No players could be parsed from the uploaded files. Check the CSV format.', 'error')
        return redirect(url_for('migration.index'))

    key = _save_import(parsed)
    session['migration_key'] = key
    return redirect(url_for('migration.preview'))


@bp.route('/preview', methods=['GET'])
@admin_required
def preview():
    key = session.get('migration_key')
    data = _load_import(key)
    if not data:
        flash('No import data found. Please upload files again.', 'error')
        return redirect(url_for('migration.index'))

    db = get_db()
    league_id = session['league_id']

    # Existing players for match preview
    existing = db.execute(
        "SELECT first_name, last_name FROM players WHERE league_id = %s", (league_id,)
    ).fetchall()
    existing_names = {(r['first_name'].lower(), r['last_name'].lower()) for r in existing}

    new_players = [
        p for p in data['players']
        if (p['first_name'].lower(), p['last_name'].lower()) not in existing_names
    ]
    matched_players = [
        p for p in data['players']
        if (p['first_name'].lower(), p['last_name'].lower()) in existing_names
    ]

    # Fetch seasons for the "import into season" dropdown
    seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()

    # Fetch courses for optional course mapping
    courses = db.execute("SELECT course_id, course_name FROM courses WHERE league_id = %s", (league_id,)).fetchall()

    return render_template('migration/preview.html',
        data=data,
        new_players=new_players,
        matched_players=matched_players,
        seasons=seasons,
        courses=courses,
    )


@bp.route('/confirm', methods=['POST'])
@admin_required
def confirm():
    key = session.get('migration_key')
    data = _load_import(key)
    if not data:
        flash('Import session expired. Please upload files again.', 'error')
        return redirect(url_for('migration.index'))

    db = get_db()
    league_id = session['league_id']
    today = datetime.now().strftime('%Y-%m-%d')

    # ── Options from form ────────────────────────────────────────────────────
    import_players = 'import_players' in request.form
    import_teams = 'import_teams' in request.form
    import_schedule = 'import_schedule' in request.form
    import_scores = 'import_scores' in request.form

    target_season_id = request.form.get('season_id') or None
    new_season_name = request.form.get('new_season_name', '').strip()
    target_course_id = request.form.get('course_id') or None
    target_tee_id = request.form.get('tee_id') or None

    stats = {'players_added': 0, 'players_skipped': 0,
             'teams_added': 0, 'matchups_added': 0,
             'rounds_added': 0, 'errors': list(data.get('errors', []))}

    # ── 1. Create season if requested ────────────────────────────────────────
    season_id = None
    if new_season_name and (import_teams or import_schedule or import_scores):
        if database.is_postgres():
            season_id = db.execute(
                "INSERT INTO seasons (league_id, season_name, start_date) VALUES (%s,%s,%s) RETURNING season_id",
                (league_id, new_season_name, today)
            ).fetchone()[0]
            db.commit()
        else:
            db.execute(
                "INSERT INTO seasons (league_id, season_name, start_date) VALUES (%s,%s,%s)",
                (league_id, new_season_name, today)
            )
            db.commit()
            season_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Create default league_settings row for the new season
        db.execute(
            """INSERT INTO league_settings
               (season_id, holes_per_round, handicap_window, handicap_scores_to_drop,
                handicap_percent, max_handicap_index, min_rounds_for_handicap)
               VALUES (%s,9,4,1,90,18.0,2)
               ON CONFLICT DO NOTHING""",
            (season_id,)
        )
        db.commit()
    elif target_season_id:
        season_id = int(target_season_id)

    # ── 2. Import players ────────────────────────────────────────────────────
    name_to_player_id = {}  # "First Last" → player_id

    if import_players:
        for p in data['players']:
            fn, ln = p['first_name'], p['last_name']
            existing = db.execute(
                """SELECT player_id FROM players
                   WHERE league_id = %s AND LOWER(first_name)=LOWER(%s) AND LOWER(last_name)=LOWER(%s)""",
                (league_id, fn, ln)
            ).fetchone()
            if existing:
                name_to_player_id[f"{fn} {ln}"] = existing['player_id']
                stats['players_skipped'] += 1
            else:
                db.execute(
                    """INSERT INTO players (league_id, first_name, last_name, email, starting_handicap, active, created_date)
                       VALUES (%s,%s,%s,%s,%s,1,%s)""",
                    (league_id, fn, ln, p['email'], p['handicap'], today)
                )
                db.commit()
                pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                name_to_player_id[f"{fn} {ln}"] = pid
                stats['players_added'] += 1
    else:
        # Still build the name map from existing players
        rows = db.execute("SELECT player_id, first_name, last_name FROM players WHERE league_id = %s", (league_id,)).fetchall()
        for r in rows:
            name_to_player_id[f"{r['first_name']} {r['last_name']}"] = r['player_id']

    def _resolve_player(name_str):
        """Try to resolve 'First Last' or 'Last, First' to a player_id."""
        if not name_str:
            return None
        # Direct lookup
        pid = name_to_player_id.get(name_str)
        if pid:
            return pid
        # Try "Last, First" → "First Last"
        if ',' in name_str:
            parts = [s.strip() for s in name_str.split(',', 1)]
            alt = f"{parts[1]} {parts[0]}"
            pid = name_to_player_id.get(alt)
            if pid:
                return pid
        # Case-insensitive fallback
        lower = name_str.lower()
        for k, v in name_to_player_id.items():
            if k.lower() == lower:
                return v
        return None

    # ── 3. Import teams ───────────────────────────────────────────────────────
    team_name_to_id = {}  # team_name → team_id

    if import_teams and season_id and data.get('teams'):
        for t in data['teams']:
            p1_id = _resolve_player(t['player1'])
            p2_id = _resolve_player(t['player2'])
            if not p1_id:
                stats['errors'].append(f"Team '{t['team_name']}': player1 '{t['player1']}' not found — skipped.")
                continue
            db.execute(
                "INSERT INTO teams (season_id, league_id, team_name, player1_id, player2_id) VALUES (%s,%s,%s,%s,%s)",
                (season_id, league_id, t['team_name'], p1_id, p2_id)
            )
            db.commit()
            tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            team_name_to_id[t['team_name']] = tid
            if t['player2']:
                p2_name = t['player2']
            stats['teams_added'] += 1

    # Build team-name lookup from existing season teams too
    if season_id:
        existing_teams = db.execute(
            """SELECT t.team_id, t.team_name FROM teams t WHERE t.season_id = %s AND t.league_id = %s""",
            (season_id, league_id)
        ).fetchall()
        for et in existing_teams:
            if et['team_name'] not in team_name_to_id:
                team_name_to_id[et['team_name']] = et['team_id']

    def _resolve_team(name_str):
        if not name_str:
            return None
        tid = team_name_to_id.get(name_str)
        if tid:
            return tid
        lower = name_str.lower()
        for k, v in team_name_to_id.items():
            if k.lower() == lower:
                return v
        return None

    # ── 4. Import schedule ────────────────────────────────────────────────────
    matchup_key_to_id = {}  # (week, home_team_id, away_team_id) → matchup_id

    if import_schedule and season_id and data.get('schedule'):
        for s in data['schedule']:
            home_id = _resolve_team(s['home_team'])
            away_id = _resolve_team(s['away_team'])
            if not home_id or not away_id:
                stats['errors'].append(
                    f"Schedule week {s['week']}: teams not resolved "
                    f"('{s['home_team']}' vs '{s['away_team']}') — skipped."
                )
                continue
            course_id = int(target_course_id) if target_course_id else None
            tee_id = int(target_tee_id) if target_tee_id else None
            sched_date = s['date'] or None
            db.execute(
                """INSERT INTO matchups
                   (season_id, round_number, week_number, scheduled_date, team1_id, team2_id,
                    course_id, tee_id, status, starting_hole)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'scheduled',1)""",
                (season_id, s['week'], s['week'], sched_date, home_id, away_id, course_id, tee_id)
            )
            db.commit()
            mid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            matchup_key_to_id[(s['week'], home_id, away_id)] = mid
            stats['matchups_added'] += 1

    # ── 5. Import scores ──────────────────────────────────────────────────────
    if import_scores and season_id and data.get('scores'):
        # Group by date to batch into rounds
        from collections import defaultdict
        by_date_player = defaultdict(list)
        for sc in data['scores']:
            by_date_player[sc['date']].append(sc)

        # We need holes from a tee if available
        holes_info = {}
        if target_tee_id:
            hole_rows = db.execute(
                "SELECT hole_number, hole_id, par, handicap_index FROM holes WHERE tee_id = %s ORDER BY hole_number",
                (int(target_tee_id),)
            ).fetchall()
            holes_info = {r['hole_number']: r for r in hole_rows}

        for round_date, sc_rows in sorted(by_date_player.items()):
            # Create a round record
            db.execute(
                """INSERT INTO rounds (season_id, course_id, tee_id, round_date, round_number)
                   VALUES (%s,%s,%s,%s,1)""",
                (season_id, int(target_course_id) if target_course_id else None,
                 int(target_tee_id) if target_tee_id else None, round_date or today)
            )
            db.commit()
            round_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            stats['rounds_added'] += 1

            for sc in sc_rows:
                player_id = _resolve_player(sc['player'])
                if not player_id:
                    stats['errors'].append(f"Score row: player '{sc['player']}' not found — skipped.")
                    continue

                # Figure out team_id
                team_id = None
                if sc.get('team'):
                    team_id = _resolve_team(sc['team'])
                if not team_id and season_id:
                    row = db.execute(
                        "SELECT team_id FROM teams WHERE season_id=%s AND (player1_id=%s OR player2_id=%s)",
                        (season_id, player_id, player_id)
                    ).fetchone()
                    if row:
                        team_id = row['team_id']

                # Get handicap
                hcp_row = db.execute(
                    "SELECT handicap_index FROM handicap_history WHERE player_id=%s ORDER BY calculated_date DESC LIMIT 1",
                    (player_id,)
                ).fetchone()
                hcp = hcp_row['handicap_index'] if hcp_row else 0.0

                db.execute(
                    """INSERT INTO scorecards
                       (round_id, player_id, team_id, handicap_at_time_of_play, is_sub, approved)
                       VALUES (%s,%s,%s,%s,0,1)""",
                    (round_id, player_id, team_id, hcp)
                )
                db.commit()
                sc_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

                # Insert hole scores
                for (hole_num, gross) in sc['holes']:
                    if gross is None:
                        continue
                    hole_row = holes_info.get(hole_num)
                    hole_id = hole_row['hole_id'] if hole_row else None
                    par = hole_row['par'] if hole_row else 4
                    diff = gross - par
                    db.execute(
                        """INSERT INTO hole_scores
                           (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (sc_id, hole_id, hole_num, gross, gross - hcp, diff)
                    )
                db.commit()

        # Recalculate handicaps for all imported players
        if import_players or import_scores:
            try:
                recalc_all_for_season(db, season_id, league_id)
            except Exception as e:
                stats['errors'].append(f'Handicap recalc warning: {e}')

    # ── Done ─────────────────────────────────────────────────────────────────
    _delete_import(key)
    session.pop('migration_key', None)

    return render_template('migration/done.html', stats=stats, season_id=season_id)


@bp.route('/cancel', methods=['POST'])
@admin_required
def cancel():
    key = session.pop('migration_key', None)
    _delete_import(key)
    flash('Import cancelled.', 'info')
    return redirect(url_for('migration.index'))
