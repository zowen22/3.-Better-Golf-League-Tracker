"""
Bulk Score CSV Import
Routes:
  GET  /admin/import/season/<id>           → upload form + matchup reference table
  GET  /admin/import/season/<id>/template  → download blank CSV template
  POST /admin/import/season/<id>           → parse upload, process, show results

CSV format — one row per player (4 rows per matchup):
  matchup_id, round_date, course_name, tee_name,
  player_first, player_last, h1, h2, h3, h4, h5, h6, h7, h8, h9

  matchup_id  : integer — see the reference table on the upload page
  round_date  : YYYY-MM-DD (blank = uses matchup scheduled_date)
  course_name : partial match OK; blank = uses matchup's assigned course
  tee_name    : partial match OK; blank = uses matchup's assigned tee
  player_first: first name (case-insensitive)
  player_last : last name  (case-insensitive)
  h1–h9       : integer gross score per hole

Each group of 4 rows with the same matchup_id forms one complete round.
Players must belong to one of the two teams in that matchup.
Match-play points are computed automatically from net hole scores.
Handicaps are recalculated for all affected players after import.
"""

import csv
import io
from collections import defaultdict

from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, Response)
from database import get_db
from routes.auth import admin_required
from routes.scores import (get_player_handicap, strokes_on_hole,
                           calc_match_play, get_league_settings, diff_match_hole_points)
from routes.handicap import recalc_handicap_for_player

bp = Blueprint('score_import', __name__, url_prefix='/admin/import')

CSV_HEADER = [
    'matchup_id', 'round_date', 'course_name', 'tee_name',
    'player_first', 'player_last',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7', 'h8', 'h9',
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_season(db, season_id, league_id):
    return db.execute(
        "SELECT * FROM seasons WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()


def _matchup_list(db, season_id):
    """Return all non-bye matchups with team labels for the reference table."""
    rows = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.status,
                  m.course_id, m.tee_id,
                  m.team1_id AS t1_id, m.team2_id AS t2_id,
                  COALESCE(t1.team_name, p1a.last_name||' / '||p1b.last_name) AS t1_label,
                  COALESCE(t2.team_name, p2a.last_name||' / '||p2b.last_name) AS t2_label,
                  t1.player1_id AS t1_p1, t1.player2_id AS t1_p2,
                  t2.player1_id AS t2_p1, t2.player2_id AS t2_p2,
                  p1a.first_name AS t1_p1_first, p1a.last_name AS t1_p1_last,
                  p1b.first_name AS t1_p2_first, p1b.last_name AS t1_p2_last,
                  p2a.first_name AS t2_p1_first, p2a.last_name AS t2_p1_last,
                  p2b.first_name AS t2_p2_first, p2b.last_name AS t2_p2_last
           FROM matchups m
           JOIN teams t1 ON m.team1_id = t1.team_id
           JOIN teams t2 ON m.team2_id = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           WHERE m.season_id=%s AND m.is_bye=0
           ORDER BY m.week_number, m.matchup_id""",
        (season_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def _resolve_course_tee(db, course_name, tee_name, league_id, fallback_course_id, fallback_tee_id):
    """Return (course_id, tee_id, holes_list) using CSV hints then matchup fallbacks."""
    course_id = None
    if course_name:
        row = db.execute(
            """SELECT course_id FROM courses
               WHERE course_name LIKE %s AND (league_id=%s OR is_master_record=1 OR league_id IS NULL)
               ORDER BY league_id DESC NULLS LAST LIMIT 1""",
            ('%' + course_name.strip() + '%', league_id)
        ).fetchone()
        if row:
            course_id = row['course_id']
    if not course_id:
        course_id = fallback_course_id

    tee_id = None
    if course_id:
        if tee_name:
            row = db.execute(
                "SELECT tee_id FROM tees WHERE course_id=%s AND tee_name LIKE %s LIMIT 1",
                (course_id, '%' + tee_name.strip() + '%')
            ).fetchone()
            if row:
                tee_id = row['tee_id']
        if not tee_id:
            if fallback_tee_id:
                row = db.execute(
                    "SELECT tee_id FROM tees WHERE tee_id=%s AND course_id=%s",
                    (fallback_tee_id, course_id)
                ).fetchone()
                if row:
                    tee_id = fallback_tee_id
            if not tee_id:
                row = db.execute(
                    "SELECT tee_id FROM tees WHERE course_id=%s LIMIT 1", (course_id,)
                ).fetchone()
                if row:
                    tee_id = row['tee_id']

    holes = []
    if tee_id:
        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id=%s ORDER BY hole_number", (tee_id,)
        ).fetchall()

    return course_id, tee_id, [dict(h) for h in holes]


def _resolve_player_in_matchup(db, first, last, matchup_info, league_id):
    """
    Find player_id and (team_id, role) by name within a matchup.
    Returns (player_id, team_id, role) or (None, None, None).
    """
    f, l = first.strip().lower(), last.strip().lower()
    candidates = [
        (matchup_info['t1_p1'], matchup_info['t1_id'], 'A',
         (matchup_info.get('t1_p1_first') or '').lower(),
         (matchup_info.get('t1_p1_last') or '').lower()),
        (matchup_info['t1_p2'], matchup_info['t1_id'], 'B',
         (matchup_info.get('t1_p2_first') or '').lower(),
         (matchup_info.get('t1_p2_last') or '').lower()),
        (matchup_info['t2_p1'], matchup_info['t2_id'], 'A',
         (matchup_info.get('t2_p1_first') or '').lower(),
         (matchup_info.get('t2_p1_last') or '').lower()),
        (matchup_info['t2_p2'], matchup_info['t2_id'], 'B',
         (matchup_info.get('t2_p2_first') or '').lower(),
         (matchup_info.get('t2_p2_last') or '').lower()),
    ]
    for pid, tid, role, cfirst, clast in candidates:
        if pid and cfirst == f and clast == l:
            return pid, tid, role
    # Fallback: last-name only match
    for pid, tid, role, cfirst, clast in candidates:
        if pid and clast == l:
            return pid, tid, role
    return None, None, None


def _parse_csv_upload(file_bytes):
    """Parse raw CSV bytes into list of row dicts. Returns (rows, hard_error)."""
    try:
        text = file_bytes.decode('utf-8-sig')
    except Exception:
        return [], 'Could not decode file as UTF-8. Save your spreadsheet as CSV (UTF-8) and try again.'

    reader = csv.reader(io.StringIO(text))
    rows = []
    for i, line in enumerate(reader, start=1):
        # Skip blank rows and header row (first cell is non-numeric)
        stripped = [c.strip() for c in line]
        if not any(stripped):
            continue
        if i == 1 and stripped and not stripped[0].lstrip('-').isdigit():
            continue
        rows.append({'line_num': i, 'raw': stripped})
    return rows, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route('/season/<int:season_id>', methods=['GET'])
@admin_required
def upload_form(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))
    matchups = _matchup_list(db, season_id)
    return render_template('admin/score_import.html',
                           season=season, matchups=matchups, results=None)


@bp.route('/season/<int:season_id>/template')
@admin_required
def download_template(season_id):
    """Return a pre-filled CSV template with one sample row per uncompleted matchup."""
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    matchups = _matchup_list(db, season_id)
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(CSV_HEADER)

    for m in matchups:
        if m['status'] == 'completed':
            continue
        date_str = m['scheduled_date'] or ''
        for pid_key, fname_key, lname_key in [
            ('t1_p1', 't1_p1_first', 't1_p1_last'),
            ('t1_p2', 't1_p2_first', 't1_p2_last'),
            ('t2_p1', 't2_p1_first', 't2_p1_last'),
            ('t2_p2', 't2_p2_first', 't2_p2_last'),
        ]:
            if not m.get(pid_key):
                continue
            w.writerow([
                m['matchup_id'], date_str, '', '',
                m.get(fname_key) or '', m.get(lname_key) or '',
                '', '', '', '', '', '', '', '', '',
            ])

    content = output.getvalue()
    season_slug = (season['season_name'] or 'season').replace(' ', '_').lower()
    filename = f'scores_import_{season_slug}.csv'
    return Response(
        content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@bp.route('/season/<int:season_id>', methods=['POST'])
@admin_required
def process_upload(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    matchups_ref = _matchup_list(db, season_id)

    uploaded = request.files.get('csv_file')
    if not uploaded or not uploaded.filename:
        flash('No file selected.', 'error')
        return render_template('admin/score_import.html',
                               season=season, matchups=matchups_ref, results=None)

    file_bytes = uploaded.read()
    raw_rows, hard_err = _parse_csv_upload(file_bytes)
    if hard_err:
        flash(hard_err, 'error')
        return render_template('admin/score_import.html',
                               season=season, matchups=matchups_ref, results=None)

    # ── Validate & group rows by matchup_id ──────────────────────────────
    grouped = defaultdict(list)  # matchup_id -> list of player dicts
    row_errors = []

    for row in raw_rows:
        cols = row['raw']
        ln = row['line_num']
        if len(cols) < 15:
            row_errors.append(f'Line {ln}: expected 15 columns, got {len(cols)} — skipped.')
            continue
        try:
            mid = int(cols[0])
        except ValueError:
            row_errors.append(f'Line {ln}: matchup_id "{cols[0]}" is not an integer — skipped.')
            continue

        holes_raw = cols[6:15]
        gross = []
        valid_scores = True
        for idx, h in enumerate(holes_raw, start=1):
            if not h.strip():
                gross.append(None)
            else:
                try:
                    v = int(h)
                    if v < 1 or v > 20:
                        row_errors.append(f'Line {ln}: hole {idx} score {v} is out of range (1–20) — skipped.')
                        valid_scores = False
                        break
                    gross.append(v)
                except ValueError:
                    row_errors.append(f'Line {ln}: hole {idx} score "{h}" is not a number — skipped.')
                    valid_scores = False
                    break
        if not valid_scores:
            continue

        grouped[mid].append({
            'line_num': ln,
            'date': cols[1].strip(),
            'course_name': cols[2].strip(),
            'tee_name': cols[3].strip(),
            'first': cols[4].strip(),
            'last': cols[5].strip(),
            'gross': gross,
        })

    # ── Load league settings for handicap calc ───────────────────────────
    settings = get_league_settings(db, season_id, league_id)
    handicap_pct = float((settings['handicap_percent'] if settings else None) or 100)
    max_hcp = float((settings['max_handicap'] if settings else None) or 36)

    # Build matchup_id → matchup_info lookup
    matchup_map = {m['matchup_id']: m for m in matchups_ref}

    # ── Process each matchup group ────────────────────────────────────────
    results = {
        'imported': [],    # list of success dicts
        'skipped': [],     # list of (matchup_id, reason)
        'row_errors': row_errors,
        'total_imported': 0,
        'handicaps_recalced': 0,
    }

    affected_players = set()

    for mid, player_rows in sorted(grouped.items()):
        matchup_info = matchup_map.get(mid)
        if not matchup_info:
            results['skipped'].append((mid, f'Matchup {mid} not found in this season.'))
            continue
        if matchup_info['status'] == 'completed':
            results['skipped'].append((mid, f'Week {matchup_info["week_number"]} matchup {mid} is already completed — skipped.'))
            continue
        if len(player_rows) != 4:
            results['skipped'].append((mid, f'Matchup {mid} has {len(player_rows)} player row(s); expected exactly 4.'))
            continue

        # Resolve players
        resolved = []
        player_errors = []
        for pr in player_rows:
            pid, tid, role = _resolve_player_in_matchup(db, pr['first'], pr['last'], matchup_info, league_id)
            if not pid:
                player_errors.append(f'Player "{pr["first"]} {pr["last"]}" not found in matchup {mid}.')
            else:
                resolved.append({'player_id': pid, 'team_id': tid, 'role': role,
                                  'gross': pr['gross'], 'date': pr['date'],
                                  'course_name': pr['course_name'], 'tee_name': pr['tee_name']})

        if player_errors:
            results['skipped'].append((mid, ' | '.join(player_errors)))
            continue

        # Check for duplicate player IDs
        pids_in_group = [r['player_id'] for r in resolved]
        if len(set(pids_in_group)) != 4:
            results['skipped'].append((mid, f'Matchup {mid} has duplicate player entries.'))
            continue

        # Use first row's date/course/tee info (they should all match)
        first_row = player_rows[0]
        round_date = first_row['date'] or matchup_info['scheduled_date'] or None
        course_id, tee_id, holes = _resolve_course_tee(
            db, first_row['course_name'], first_row['tee_name'],
            league_id, matchup_info['course_id'], matchup_info['tee_id']
        )

        # Build hole lookup: hole_number -> {par, handicap_index, hole_id}
        hole_map = {h['hole_number']: h for h in holes} if holes else {}

        # Get handicaps and compute net scores
        # Identify the 4 players: team1_A, team1_B, team2_A, team2_B
        t1_id = matchup_info['t1_id']
        t2_id = matchup_info['t2_id']

        t1_players = [r for r in resolved if r['team_id'] == t1_id]
        t2_players = [r for r in resolved if r['team_id'] == t2_id]
        t1_a = next((r for r in t1_players if r['role'] == 'A'), t1_players[0] if t1_players else None)
        t1_b = next((r for r in t1_players if r['role'] == 'B'), t1_players[1] if len(t1_players) > 1 else None)
        t2_a = next((r for r in t2_players if r['role'] == 'A'), t2_players[0] if t2_players else None)
        t2_b = next((r for r in t2_players if r['role'] == 'B'), t2_players[1] if len(t2_players) > 1 else None)

        if not all([t1_a, t1_b, t2_a, t2_b]):
            results['skipped'].append((mid, f'Could not assign all 4 players to A/B roles for matchup {mid}.'))
            continue

        # Build playing handicaps for net scoring
        playing_hcps = {}
        for r in resolved:
            pid = r['player_id']
            raw_hcp = get_player_handicap(db, pid, league_id)
            ph = min(round(raw_hcp * handicap_pct / 100, 1), max_hcp)
            playing_hcps[pid] = ph

        # Compute net scores and hole-by-hole match play
        _hcp_indices = [h['handicap_index'] for h in holes if h.get('handicap_index') is not None] if holes else []

        def net_gross(gross_list, pid, total_holes):
            net = []
            for i, g in enumerate(gross_list):
                h_num = i + 1
                if g is None:
                    net.append(None)
                    continue
                h = hole_map.get(h_num)
                hcp_idx = h['handicap_index'] if h else None
                strokes = strokes_on_hole(playing_hcps[pid], hcp_idx, total_holes,
                                          hcp_indices=_hcp_indices)
                net.append(g - strokes)
            return net

        total_holes = len(holes) if holes else 9
        t1a_net = net_gross(t1_a['gross'], t1_a['player_id'], total_holes)
        t1b_net = net_gross(t1_b['gross'], t1_b['player_id'], total_holes)
        t2a_net = net_gross(t2_a['gross'], t2_a['player_id'], total_holes)
        t2b_net = net_gross(t2_b['gross'], t2_b['player_id'], total_holes)

        # Hole-by-hole + overall: differential stroke allocation (only the
        # higher-handicap player gets strokes, equal to the handicap gap).
        # Net scores stored to hole_scores (t1a_net etc. above) stay absolute.
        aa_pts_1, aa_pts_2, aa_ov_1, aa_ov_2 = diff_match_hole_points(
            t1_a['gross'], t2_a['gross'], holes or [],
            playing_hcps[t1_a['player_id']], playing_hcps[t2_a['player_id']])
        bb_pts_1, bb_pts_2, bb_ov_1, bb_ov_2 = diff_match_hole_points(
            t1_b['gross'], t2_b['gross'], holes or [],
            playing_hcps[t1_b['player_id']], playing_hcps[t2_b['player_id']])

        # ── Write to DB ──────────────────────────────────────────────────
        try:
            matchup_id_val = matchup_info['matchup_id']
            round_num = matchup_info['week_number']

            round_id = db.execute(
                """INSERT INTO rounds (matchup_id, season_id, course_id, tee_id, round_date, round_number)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING round_id""",
                (matchup_id_val, season_id, course_id, tee_id, round_date, round_num)
            ).fetchone()['round_id']

            sc_ids = {}
            for r in [t1_a, t1_b, t2_a, t2_b]:
                pid = r['player_id']
                sc_id = db.execute(
                    """INSERT INTO scorecards
                       (round_id, player_id, team_id, handicap_at_time_of_play, is_sub, approved, tee_id)
                       VALUES (%s,%s,%s,%s,0,1,%s) RETURNING scorecard_id""",
                    (round_id, pid, r['team_id'], playing_hcps[pid], tee_id)
                ).fetchone()['scorecard_id']
                sc_ids[pid] = sc_id

                gross_list = r['gross']
                net_map = {t1_a['player_id']: t1a_net,
                           t1_b['player_id']: t1b_net,
                           t2_a['player_id']: t2a_net,
                           t2_b['player_id']: t2b_net}
                net_list = net_map[pid]

                for i, g in enumerate(gross_list):
                    if g is None:
                        continue
                    h_num = i + 1
                    h = hole_map.get(h_num, {})
                    hole_id = h.get('hole_id')
                    par = h.get('par', 4)
                    net_g = net_list[i] if net_list[i] is not None else g
                    diff = g - par
                    db.execute(
                        """INSERT INTO hole_scores
                           (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (sc_id, hole_id, h_num, g, net_g, diff)
                    )

            # Match results
            result_rows = [
                (t1_a['player_id'], t1_id, 'A', aa_pts_1, aa_ov_1, t2_a['player_id']),
                (t2_a['player_id'], t2_id, 'A', aa_pts_2, aa_ov_2, t1_a['player_id']),
                (t1_b['player_id'], t1_id, 'B', bb_pts_1, bb_ov_1, t2_b['player_id']),
                (t2_b['player_id'], t2_id, 'B', bb_pts_2, bb_ov_2, t1_b['player_id']),
            ]
            for pid, tid, role, hole_pts, ov_pt, opp_pid in result_rows:
                db.execute(
                    """INSERT INTO match_results
                       (matchup_id, team_id, player_id, role,
                        hole_points_won, overall_point_won, total_points, opponent_player_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (matchup_id_val, tid, pid, role, hole_pts, ov_pt,
                     hole_pts + ov_pt, opp_pid)
                )

            # Mark matchup completed
            db.execute(
                "UPDATE matchups SET status='completed', course_id=%s, tee_id=%s WHERE matchup_id=%s",
                (course_id, tee_id, matchup_id_val)
            )
            db.commit()

            for r in resolved:
                affected_players.add(r['player_id'])

            t1_gross = sum(g for g in t1_a['gross'] if g) + sum(g for g in t1_b['gross'] if g)
            t2_gross = sum(g for g in t2_a['gross'] if g) + sum(g for g in t2_b['gross'] if g)
            t1_total = aa_pts_1 + aa_ov_1 + bb_pts_1 + bb_ov_1
            t2_total = aa_pts_2 + aa_ov_2 + bb_pts_2 + bb_ov_2

            results['imported'].append({
                'matchup_id': mid,
                'week': matchup_info['week_number'],
                't1_label': matchup_info['t1_label'],
                't2_label': matchup_info['t2_label'],
                't1_pts': int(t1_total) if t1_total == int(t1_total) else t1_total,
                't2_pts': int(t2_total) if t2_total == int(t2_total) else t2_total,
                't1_gross': t1_gross,
                't2_gross': t2_gross,
            })
            results['total_imported'] += 1

        except Exception as e:
            db.execute("ROLLBACK") if hasattr(db, 'execute') else None
            try:
                db.rollback()
            except Exception:
                pass
            results['skipped'].append((mid, f'Database error: {e}'))
            continue

    # ── Recalculate handicaps for all affected players ────────────────────
    for pid in affected_players:
        try:
            recalc_handicap_for_player(db, pid, season_id, league_id)
            results['handicaps_recalced'] += 1
        except Exception:
            pass
    if affected_players:
        try:
            db.commit()
        except Exception:
            pass

    # Refresh matchup list for the results page
    matchups_ref = _matchup_list(db, season_id)
    return render_template('admin/score_import.html',
                           season=season, matchups=matchups_ref, results=results)
