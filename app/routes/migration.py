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
    _update_import(key, data)
    return key


def _update_import(key: str, data: dict):
    """Overwrite an existing import's stashed state in place (used while
    stepping through the column-mapping pages one file type at a time)."""
    _ensure_tmp()
    path = os.path.join(_TMP_DIR, f'{key}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


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


def _insert_returning_id(db, insert_sql, params, pk_col):
    """Execute an INSERT and return the new row's primary key, on either
    Postgres (RETURNING) or SQLite (last_insert_rowid()). insert_sql must
    not already include a RETURNING clause."""
    if database.is_postgres():
        new_id = db.execute(f"{insert_sql} RETURNING {pk_col}", params).fetchone()[0]
        db.commit()
    else:
        db.execute(insert_sql, params)
        db.commit()
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    return new_id


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


def _read_csv_headers_and_rows(b: bytes) -> tuple[list[str], list[list[str]]]:
    """Positional (not dict) read -- duplicate header text shouldn't
    silently collide/lose a column the way DictReader would."""
    text = b.decode('utf-8-sig', errors='replace')
    rows_raw = list(csv.reader(io.StringIO(text)))
    if not rows_raw:
        return [], []
    headers = [h.strip() for h in rows_raw[0]]
    ncols = len(headers)
    rows = []
    for r in rows_raw[1:]:
        if not any(c.strip() for c in r):
            continue  # fully blank row
        padded = (r + [''] * ncols)[:ncols]
        rows.append([c.strip() for c in padded])
    return headers, rows


def _xlsx_cell_str(v) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d')
    return str(v).strip() if isinstance(v, str) else str(v)


def _read_xlsx_headers_and_rows(b: bytes) -> tuple[list[str], list[list[str]]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    first = next(it, None)
    if not first:
        return [], []
    headers = [(str(h).strip() if h is not None else '') for h in first]
    ncols = len(headers)
    rows = []
    for r in it:
        if r is None or all(v is None for v in r):
            continue
        rows.append([_xlsx_cell_str(r[i]) if i < len(r) else '' for i in range(ncols)])
    return headers, rows


def _read_uploaded_bytes(filename: str, b: bytes) -> tuple[list[str], list[list[str]]]:
    """Read a CSV or XLSX file's raw headers + rows (positional lists),
    regardless of format -- callers don't need to know which one it was."""
    if filename.lower().endswith('.xlsx'):
        return _read_xlsx_headers_and_rows(b)
    return _read_csv_headers_and_rows(b)


# ── Column-mapping preview step ──────────────────────────────────────────────
#
# Upload no longer parses straight to final fields -- it reads the raw grid,
# suggests a mapping (alias match, falling back to this type's template
# column order by position), and lets the admin confirm/adjust it (map
# columns to fields, drop columns, exclude rows) before anything is parsed
# for real. The actual per-type validation/normalization in _parse_players()
# etc. below is unchanged and reused as-is -- the mapping step's only job is
# to turn the raw grid + admin's choices into the same {field: value} row
# dicts those functions already expect (keyed by canonical field name
# directly, which every alias map already resolves to itself via its
# identity fallback in _map_headers()).

FIELD_OPTIONS = {
    'players': [
        ('', 'Ignore this column'),
        ('first_name', 'First Name'),
        ('last_name', 'Last Name'),
        ('email', 'Email'),
        ('handicap', 'Handicap'),
    ],
    'teams': [
        ('', 'Ignore this column'),
        ('team_name', 'Team Name'),
        ('player1', 'Player 1'),
        ('player2', 'Player 2'),
    ],
    'schedule': [
        ('', 'Ignore this column'),
        ('week', 'Week'),
        ('date', 'Date'),
        ('home_team', 'Home Team'),
        ('away_team', 'Away Team'),
        ('course', 'Course'),
    ],
    'scores': [
        ('', 'Ignore this column'),
        ('date', 'Date'),
        ('player', 'Player'),
        ('team', 'Team'),
        ('course', 'Course'),
    ] + [(f'hole_{n}', f'Hole {n}') for n in range(1, 19)],
}

# Human labels for the import-type headings on the mapping page.
IMPORT_TYPE_LABELS = {
    'players': 'Players', 'teams': 'Teams', 'schedule': 'Schedule', 'scores': 'Scores',
}


def _norm_to_field(header: str, import_type: str) -> str:
    """Resolve a raw header to one of this import type's known field names
    via the same alias maps _parse_*() itself uses, so the suggested
    mapping and the actual parser can never disagree about what a header
    means. Returns '' (ignore) if nothing matches."""
    n = _norm(header)
    alias_map = {
        'players': _PLAYER_ALIASES, 'teams': _TEAM_ALIASES, 'schedule': _SCHED_ALIASES,
    }.get(import_type)
    if alias_map is not None:
        field = alias_map.get(n, n)
        valid = {v for v, _ in FIELD_OPTIONS[import_type]}
        return field if field in valid else ''

    if import_type == 'scores':
        if n in ('player', 'player_name', 'name', 'golfer'):
            return 'player'
        if n in ('date', 'round_date', 'game_date', 'matchdate'):
            return 'date'
        if n in ('team', 'team_name'):
            return 'team'
        if n in ('course', 'course_name', 'coursename'):
            return 'course'
        for prefix in ('hole_', 'hole', 'h', ''):
            if n.startswith(prefix):
                suffix = n[len(prefix):]
                if suffix.isdigit() and 1 <= int(suffix) <= 18:
                    return f'hole_{int(suffix)}'
        return ''
    return ''


def _suggest_mapping(headers: list[str], import_type: str) -> list[str]:
    """Per-column suggested field: alias match first, then positional
    fallback to this type's template column order (see _TEMPLATES), then
    '' (ignore) if the column runs past the template's own length."""
    template_order = _TEMPLATES.get(import_type, ([], [], []))[0]
    suggested = []
    for i, h in enumerate(headers):
        field = _norm_to_field(h, import_type)
        if not field and i < len(template_order):
            field = template_order[i]
        suggested.append(field)
    return suggested


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

def _extract_files(request_files) -> dict[str, tuple[str, bytes]]:
    """Return dict: csv_type → (filename, bytes). Handles individual
    CSV/XLSX files and a ZIP bundling either format."""
    result = {}
    known = ('players', 'teams', 'schedule', 'scores')

    # Handle individual named file inputs
    for key in known:
        f = request_files.get(key)
        if f and f.filename:
            result[key] = (f.filename, f.read())

    # Handle ZIP upload
    zip_file = request_files.get('zip_file')
    if zip_file and zip_file.filename:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_file.read())) as zf:
                for name in zf.namelist():
                    base = os.path.basename(name).lower()
                    for key in known:
                        if key in result:
                            continue
                        if base.startswith(key) and (base.endswith('.csv') or base.endswith('.xlsx')):
                            result[key] = (name, zf.read(name))
                            break
        except zipfile.BadZipFile:
            pass

    return result


# ── Template downloads ────────────────────────────────────────────────────────

# Each template has two example rows: one fully filled in (shows the
# expected format), one with optional columns left blank (shows they're
# safe to skip). Column names themselves are never annotated (e.g. "email
# (optional)") -- _map_headers()/_norm() match on exact/aliased header
# text, so any change there would break re-uploading the template as-is.
# Notes live in a labeled "Notes" column past the real headers (see
# _build_template_csv()) rather than on the upload page -- keeps the page
# clean and puts the instructions in the file someone's actually looking
# at when they need them, without a '#' comment convention Excel/Sheets
# users won't recognize.
_TEMPLATES = {
    'players': (
        ['first_name', 'last_name', 'email', 'handicap'],
        [
            ['Jane', 'Doe', 'jane@example.com', '12.4'],
            ['John', 'Smith', '', ''],  # email/handicap are optional
            ['Mike', 'Johnson', 'mike@example.com', '9.1'],
        ],
        [
            "Column headers are case-insensitive; common aliases are recognized "
            "(e.g. \"name\" instead of first_name/last_name, \"handicap_index\" instead of handicap).",
            "email and handicap are optional.",
            "Players already on your roster (matched by first + last name) will be linked, not duplicated.",
        ],
    ),
    'teams': (
        ['team_name', 'player1', 'player2'],
        [
            ['The Duffers', 'Jane Doe', 'John Smith'],
            ['Solo Team', 'Bob Jones', ''],  # player2 is optional
        ],
        [
            "player1/player2 must match a \"First Last\" name from players.csv.",
            "player2 is optional (for a solo/bye team).",
        ],
    ),
    'schedule': (
        ['week', 'date', 'home_team', 'away_team'],
        [
            ['1', '2026-04-07', 'The Duffers', 'Sand Trappers'],
            ['', '', 'Sand Trappers', 'The Duffers'],  # week/date are optional
        ],
        [
            "week and date are optional -- week auto-numbers from row order if blank.",
            "date format: YYYY-MM-DD or MM/DD/YYYY.",
        ],
    ),
    'scores': (
        ['date', 'player', 'hole_1', 'hole_2', 'hole_3', 'hole_4', 'hole_5',
         'hole_6', 'hole_7', 'hole_8', 'hole_9'],
        [
            ['2026-04-07', 'Jane Doe', '4', '5', '3', '4', '4', '5', '3', '4', '5'],
            ['', 'John Smith', '5', '4', '4', '3', '5', '4', '4', '5', '3'],  # date is optional
        ],
        [
            "date is optional.",
            "Also accepts H1..H18 or Hole1..Hole18 as column headers instead of hole_1..hole_9.",
        ],
    ),
}


def _build_template_csv(headers, example_rows, notes):
    """Real columns start at A1, untouched. Notes sit in their own
    labeled column past a blank spacer, one per row -- '#' comment lines
    read as a wall of text to anyone opening this in Excel/Sheets (no
    native comment concept in plain CSV), and real cell formatting
    (colored/bordered note callout) isn't something a .csv file can carry
    at all -- that needs an actual spreadsheet file format (.xlsx), which
    would mean generating binary files and teaching every parser to
    accept them, not just this template."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(list(headers) + ['', 'Notes'])
    row_count = max(len(example_rows), len(notes))
    for i in range(row_count):
        data = list(example_rows[i]) if i < len(example_rows) else [''] * len(headers)
        note = notes[i] if i < len(notes) else ''
        writer.writerow(data + ['', note])
    return buf.getvalue()


@bp.route('/template/<name>', methods=['GET'])
@admin_required
def template(name):
    spec = _TEMPLATES.get(name)
    if not spec:
        flash('Unknown template.', 'error')
        return redirect(url_for('migration.index'))
    headers, rows, notes = spec
    return Response(
        _build_template_csv(headers, rows, notes),
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
        flash('Please upload at least one CSV/XLSX (players, teams, schedule, or scores) or a ZIP file.', 'error')
        return redirect(url_for('migration.index'))

    raw = {}
    for key, (filename, b) in files.items():
        try:
            headers, rows = _read_uploaded_bytes(filename, b)
        except Exception:
            flash(f'Could not read "{filename}" — is it a valid CSV or XLSX file?', 'error')
            return redirect(url_for('migration.index'))
        if not headers:
            continue
        raw[key] = {
            'headers': headers,
            'rows': rows,
            'suggested_mapping': _suggest_mapping(headers, key),
        }

    if not raw:
        flash('No data could be read from the uploaded files. Check the file format.', 'error')
        return redirect(url_for('migration.index'))

    # 'pending' drives the column-mapping walkthrough below: one page per
    # uploaded file type, in this fixed order, popped off as each is
    # confirmed. The remaining keys match confirm()'s expected shape
    # exactly, so preview()/confirm() need no changes at all once mapping
    # is done -- they just see the same {type: [...], 'errors': [...]}
    # dict this route used to hand them directly.
    state = {
        'raw': raw,
        'pending': [k for k in ('players', 'teams', 'schedule', 'scores') if k in raw],
        'players': [], 'teams': [], 'schedule': [], 'scores': [], 'errors': [],
    }
    key = _save_import(state)
    session['migration_key'] = key
    return redirect(url_for('migration.map_columns'))


# Cap how many rows render as individually-checkable in the mapping grid --
# an 18-hole season's worth of scores can be thousands of rows, and a page
# with that many checkboxes would be both slow to render and useless to
# scroll through by hand. Rows past the cap are still imported (just not
# individually excludable here); the cap only limits what's interactively
# editable, never what's read from the file.
_MAP_PREVIEW_ROW_CAP = 300


@bp.route('/map', methods=['GET', 'POST'])
@admin_required
def map_columns():
    key = session.get('migration_key')
    state = _load_import(key)
    if not state or not state.get('pending'):
        flash('No import data found. Please upload files again.', 'error')
        return redirect(url_for('migration.index'))

    current_type = state['pending'][0]
    raw = state['raw'][current_type]

    if request.method == 'POST':
        n_cols = len(raw['headers'])
        col_fields = [request.form.get(f'col_field_{i}', '') for i in range(n_cols)]

        shown_rows = raw['rows'][:_MAP_PREVIEW_ROW_CAP]
        row_included = [
            request.form.get(f'row_included_{i}') == '1' if i < len(shown_rows) else True
            for i in range(len(raw['rows']))
        ]

        dict_rows = []
        for i, row_vals in enumerate(raw['rows']):
            if not row_included[i]:
                continue
            d = {}
            for ci, field in enumerate(col_fields):
                if not field or ci >= len(row_vals):
                    continue
                d[field] = row_vals[ci]
            dict_rows.append(d)

        parser = {
            'players': _parse_players, 'teams': _parse_teams,
            'schedule': _parse_schedule, 'scores': _parse_scores,
        }[current_type]
        parsed_rows, errors = parser(dict_rows)
        state[current_type] = parsed_rows
        state['errors'] += errors
        state['pending'].pop(0)
        _update_import(key, state)

        if state['pending']:
            return redirect(url_for('migration.map_columns'))
        return redirect(url_for('migration.preview'))

    total_rows = len(raw['rows'])
    return render_template('migration/map_columns.html',
        import_type=current_type,
        import_type_label=IMPORT_TYPE_LABELS[current_type],
        headers=raw['headers'],
        rows=raw['rows'][:_MAP_PREVIEW_ROW_CAP],
        rows_truncated=total_rows > _MAP_PREVIEW_ROW_CAP,
        total_rows=total_rows,
        suggested_mapping=raw['suggested_mapping'],
        field_options=FIELD_OPTIONS[current_type],
        step_number=len(state['raw']) - len(state['pending']) + 1,
        step_total=len(state['raw']),
        remaining_types=[IMPORT_TYPE_LABELS[t] for t in state['pending'][1:]],
    )


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
                pid = _insert_returning_id(
                    db,
                    """INSERT INTO players (league_id, first_name, last_name, email, starting_handicap, active, created_date)
                       VALUES (%s,%s,%s,%s,%s,1,%s)""",
                    (league_id, fn, ln, p['email'], p['handicap'], today),
                    'player_id'
                )
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
            tid = _insert_returning_id(
                db,
                "INSERT INTO teams (season_id, league_id, team_name, player1_id, player2_id) VALUES (%s,%s,%s,%s,%s)",
                (season_id, league_id, t['team_name'], p1_id, p2_id),
                'team_id'
            )
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
            mid = _insert_returning_id(
                db,
                """INSERT INTO matchups
                   (season_id, round_number, week_number, scheduled_date, team1_id, team2_id,
                    course_id, tee_id, status, starting_hole)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'scheduled',1)""",
                (season_id, s['week'], s['week'], sched_date, home_id, away_id, course_id, tee_id),
                'matchup_id'
            )
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

        # hole_scores.hole_id is NOT NULL -- a hole number with no matching
        # row in `holes` (no tee selected, or the selected tee doesn't have
        # that many holes configured) can't be inserted at all, not just
        # inserted with a null hole_id. Skipped once as a single summary
        # count rather than per hole/player, which would be extremely noisy
        # on an 18-hole import with no tee selected.
        skipped_holes_no_tee_match = 0

        for round_date, sc_rows in sorted(by_date_player.items()):
            # Create a round record
            round_id = _insert_returning_id(
                db,
                """INSERT INTO rounds (season_id, course_id, tee_id, round_date, round_number)
                   VALUES (%s,%s,%s,%s,1)""",
                (season_id, int(target_course_id) if target_course_id else None,
                 int(target_tee_id) if target_tee_id else None, round_date or today),
                'round_id'
            )
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

                sc_id = _insert_returning_id(
                    db,
                    """INSERT INTO scorecards
                       (round_id, player_id, team_id, handicap_at_time_of_play, is_sub, approved)
                       VALUES (%s,%s,%s,%s,0,1)""",
                    (round_id, player_id, team_id, hcp),
                    'scorecard_id'
                )

                # Insert hole scores
                for (hole_num, gross) in sc['holes']:
                    if gross is None:
                        continue
                    hole_row = holes_info.get(hole_num)
                    if not hole_row:
                        skipped_holes_no_tee_match += 1
                        continue
                    hole_id = hole_row['hole_id']
                    par = hole_row['par']
                    diff = gross - par
                    db.execute(
                        """INSERT INTO hole_scores
                           (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (sc_id, hole_id, hole_num, gross, gross - hcp, diff)
                    )
                db.commit()

        if skipped_holes_no_tee_match:
            stats['errors'].append(
                f"{skipped_holes_no_tee_match} hole score(s) skipped: no matching hole data for the "
                f"selected course/tee. Pick a course and tee with holes already configured (Courses → "
                f"manage holes) before importing scores, or these holes have no home to attach to."
            )

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
