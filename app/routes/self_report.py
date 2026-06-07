"""
Self-Report blueprint — players submit scores; admins approve/reject.

Routes
------
GET  /self-report/<matchup_id>          Member score submission form
POST /self-report/<matchup_id>          Save a pending submission
GET  /self-report/pending               Admin queue of pending submissions
GET  /self-report/view/<submission_id>  Admin detail view of a submission
POST /self-report/<submission_id>/approve  Admin approves → writes real scores
POST /self-report/<submission_id>/reject   Admin rejects with optional note
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required
from routes.scores import (
    get_league_settings, get_player_handicap, calc_playing_handicap,
    strokes_on_hole, calc_match_play, _build_player_list
)
from routes.handicap import recalc_handicap_for_player
from datetime import datetime

bp = Blueprint('self_report', __name__, url_prefix='/self-report')


# ---------------------------------------------------------------------------
# Helper: count pending submissions for the current league
# ---------------------------------------------------------------------------

def pending_count(db, league_id):
    row = db.execute(
        """SELECT COUNT(*) AS cnt
           FROM score_submissions ss
           JOIN matchups m ON ss.matchup_id = m.matchup_id
           JOIN seasons s  ON m.season_id   = s.season_id
           WHERE s.league_id = ? AND ss.status = 'pending'""",
        (league_id,)
    ).fetchone()
    return row['cnt'] if row else 0


# ---------------------------------------------------------------------------
# Member: submission form
# ---------------------------------------------------------------------------

@bp.route('/<int:matchup_id>', methods=['GET', 'POST'])
@login_required
def submit(matchup_id):
    db = get_db()

    matchup = db.execute(
        """SELECT m.*, s.season_name, s.league_id, s.season_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = ?""",
        (matchup_id,)
    ).fetchone()

    if not matchup or matchup['league_id'] != session['league_id']:
        flash('Matchup not found.', 'error')
        return redirect(url_for('schedule.index', season_id=0))

    if matchup['is_bye']:
        flash('Bye weeks do not have scores.', 'error')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

    if matchup['status'] == 'completed':
        flash('Scores for this matchup have already been entered.', 'info')
        return redirect(url_for('scores.view', matchup_id=matchup_id))

    # Check for an already-pending submission from this session
    existing = db.execute(
        "SELECT submission_id, status FROM score_submissions WHERE matchup_id = ? AND status = 'pending'",
        (matchup_id,)
    ).fetchone()

    # Teams + players
    team1 = db.execute(
        """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                       p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.team_id = ?""", (matchup['team1_id'],)
    ).fetchone()

    team2 = db.execute(
        """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                       p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.team_id = ?""", (matchup['team2_id'],)
    ).fetchone()

    if not team1 or not team2:
        flash('Teams not found for this matchup.', 'error')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

    # Courses + tees
    courses = db.execute(
        "SELECT course_id, course_name FROM courses WHERE league_id = ? OR league_id IS NULL ORDER BY course_name",
        (session['league_id'],)
    ).fetchall()

    selected_course_id = request.form.get('course_id') or matchup['course_id']
    selected_tee_id    = request.form.get('tee_id')    or matchup['tee_id']

    tees  = []
    holes = []
    if selected_course_id:
        tees = db.execute(
            """SELECT tee_id, tee_name, nine, gender, par_total, slope, rating
               FROM tees WHERE course_id = ? ORDER BY gender, tee_name, nine""",
            (int(selected_course_id),)
        ).fetchall()
    if selected_tee_id:
        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = ? ORDER BY hole_number",
            (int(selected_tee_id),)
        ).fetchall()

    if request.method == 'POST' and request.form.get('action') == 'submit_scores':
        return _save_submission(db, matchup, team1, team2, holes, request.form)

    players = _build_player_list(db, matchup['season_id'], team1, team2)
    if holes:
        settings = get_league_settings(db, matchup['season_id'], session['league_id'])
        hpct = float(settings['handicap_percent']) if settings else 90.0
        hmax = float(settings['max_handicap_index']) if settings else 18.0
        for p in players:
            p['playing_hcp'] = calc_playing_handicap(p['handicap'], hpct, hmax)
        for team_num in [1, 2]:
            tp = sorted([p for p in players if p['team_num'] == team_num],
                        key=lambda x: x['playing_hcp'])
            for i, p in enumerate(tp):
                p['role'] = 'A' if i == 0 else 'B'
        players.sort(key=lambda p: (p['team_num'], p.get('role', 'Z')))

    return render_template(
        'self_report/submit.html',
        matchup=matchup, team1=team1, team2=team2,
        players=players, courses=courses, tees=tees, holes=holes,
        selected_course_id=str(selected_course_id or ''),
        selected_tee_id=str(selected_tee_id or ''),
        existing_pending=existing,
    )


def _save_submission(db, matchup, team1, team2, holes, form):
    """Validate and persist a pending submission (no scoring logic yet)."""
    season_id  = matchup['season_id']
    league_id  = session['league_id']
    tee_id     = form.get('tee_id', '').strip()
    course_id  = form.get('course_id', '').strip()
    round_date = form.get('round_date', '').strip() or datetime.now().strftime('%Y-%m-%d')
    submitter  = form.get('submitter_name', '').strip() or 'Anonymous'

    if not tee_id or not holes:
        flash('Please select a tee before submitting scores.', 'error')
        return redirect(url_for('self_report.submit', matchup_id=matchup['matchup_id']))

    players = _build_player_list(db, season_id, team1, team2)
    if len(players) < 4:
        flash('Both teams need 2 players assigned before entering scores.', 'error')
        return redirect(url_for('self_report.submit', matchup_id=matchup['matchup_id']))

    # Parse gross scores
    gross = {}
    for p in players:
        pid = p['player_id']
        player_scores = []
        for h in holes:
            key = f"score_{pid}_{h['hole_number']}"
            val = form.get(key, '').strip()
            if not val:
                flash(f"Missing score for {p['first_name']} {p['last_name']}, hole {h['hole_number']}.", 'error')
                return redirect(url_for('self_report.submit', matchup_id=matchup['matchup_id']))
            try:
                s = int(val)
                if s < 1 or s > 15:
                    raise ValueError
                player_scores.append(s)
            except ValueError:
                flash(f"Invalid score for {p['first_name']} {p['last_name']}, hole {h['hole_number']}.", 'error')
                return redirect(url_for('self_report.submit', matchup_id=matchup['matchup_id']))
        gross[pid] = player_scores

    # Delete any prior pending submission for this matchup so we don't stack up duplicates
    db.execute("DELETE FROM score_submission_details WHERE submission_id IN "
               "(SELECT submission_id FROM score_submissions WHERE matchup_id = ? AND status = 'pending')",
               (matchup['matchup_id'],))
    db.execute("DELETE FROM score_submissions WHERE matchup_id = ? AND status = 'pending'",
               (matchup['matchup_id'],))

    # Insert header
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        """INSERT INTO score_submissions
           (matchup_id, season_id, submitter_name, course_id, tee_id, round_date, submitted_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (matchup['matchup_id'], season_id, submitter,
         int(course_id), int(tee_id), round_date, now)
    )
    sub_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()['id']

    # Insert detail rows
    for p in players:
        pid = p['player_id']
        for i, h in enumerate(holes):
            db.execute(
                """INSERT INTO score_submission_details
                   (submission_id, player_id, hole_number, gross_score)
                   VALUES (?, ?, ?, ?)""",
                (sub_id, pid, h['hole_number'], gross[pid][i])
            )

    db.commit()
    flash('Scores submitted! An admin will review and approve them shortly.', 'success')
    return redirect(url_for('schedule.index', season_id=matchup['season_id']))


# ---------------------------------------------------------------------------
# Admin: pending queue
# ---------------------------------------------------------------------------

@bp.route('/pending')
@admin_required
def pending():
    db = get_db()
    rows = db.execute(
        """SELECT ss.*,
                  m.week_number, m.scheduled_date, m.round_number,
                  m.team1_id, m.team2_id,
                  s.season_name,
                  t1p1.last_name AS t1p1_last, t1p2.last_name AS t1p2_last,
                  t2p1.last_name AS t2p1_last, t2p2.last_name AS t2p2_last,
                  c.course_name, te.tee_name, te.nine
           FROM score_submissions ss
           JOIN matchups m  ON ss.matchup_id  = m.matchup_id
           JOIN seasons  s  ON m.season_id    = s.season_id
           JOIN teams    t1 ON m.team1_id     = t1.team_id
           JOIN teams    t2 ON m.team2_id     = t2.team_id
           LEFT JOIN players t1p1 ON t1.player1_id = t1p1.player_id
           LEFT JOIN players t1p2 ON t1.player2_id = t1p2.player_id
           LEFT JOIN players t2p1 ON t2.player1_id = t2p1.player_id
           LEFT JOIN players t2p2 ON t2.player2_id = t2p2.player_id
           LEFT JOIN courses c  ON ss.course_id = c.course_id
           LEFT JOIN tees    te ON ss.tee_id    = te.tee_id
           WHERE s.league_id = ?
           ORDER BY
               CASE ss.status WHEN 'pending' THEN 0 WHEN 'rejected' THEN 1 ELSE 2 END,
               ss.submitted_at DESC""",
        (session['league_id'],)
    ).fetchall()

    return render_template('self_report/pending.html', submissions=rows)


# ---------------------------------------------------------------------------
# Admin: view submission detail
# ---------------------------------------------------------------------------

@bp.route('/view/<int:submission_id>')
@admin_required
def view_submission(submission_id):
    db = get_db()

    sub = db.execute(
        """SELECT ss.*,
                  m.week_number, m.scheduled_date, m.round_number,
                  m.team1_id, m.team2_id, m.matchup_id,
                  s.season_name, s.season_id,
                  c.course_name, te.tee_name, te.nine, te.par_total
           FROM score_submissions ss
           JOIN matchups m ON ss.matchup_id = m.matchup_id
           JOIN seasons  s ON m.season_id   = s.season_id
           LEFT JOIN courses c  ON ss.course_id = c.course_id
           LEFT JOIN tees    te ON ss.tee_id    = te.tee_id
           WHERE ss.submission_id = ? AND s.league_id = ?""",
        (submission_id, session['league_id'])
    ).fetchone()

    if not sub:
        flash('Submission not found.', 'error')
        return redirect(url_for('self_report.pending'))

    # Get holes
    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = ? ORDER BY hole_number",
        (sub['tee_id'],)
    ).fetchall() if sub['tee_id'] else []

    # Get detail rows with player info
    details = db.execute(
        """SELECT ssd.*, p.first_name, p.last_name
           FROM score_submission_details ssd
           JOIN players p ON ssd.player_id = p.player_id
           WHERE ssd.submission_id = ?
           ORDER BY ssd.player_id, ssd.hole_number""",
        (submission_id,)
    ).fetchall()

    # Group by player
    player_scores = {}
    for d in details:
        pid = d['player_id']
        if pid not in player_scores:
            player_scores[pid] = {
                'first_name': d['first_name'],
                'last_name':  d['last_name'],
                'scores': [],
            }
        player_scores[pid]['scores'].append(d['gross_score'])

    # Teams
    team1 = db.execute(
        """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                       p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.team_id = ?""", (sub['team1_id'],)
    ).fetchone()

    team2 = db.execute(
        """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                       p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.team_id = ?""", (sub['team2_id'],)
    ).fetchone()

    return render_template(
        'self_report/view_submission.html',
        sub=sub, holes=holes, player_scores=player_scores,
        team1=team1, team2=team2,
    )


# ---------------------------------------------------------------------------
# Admin: approve
# ---------------------------------------------------------------------------

@bp.route('/<int:submission_id>/approve', methods=['POST'])
@admin_required
def approve(submission_id):
    db = get_db()

    sub = db.execute(
        """SELECT ss.*, m.matchup_id, m.team1_id, m.team2_id, m.status AS matchup_status,
                  m.round_number, s.season_id, s.league_id
           FROM score_submissions ss
           JOIN matchups m ON ss.matchup_id = m.matchup_id
           JOIN seasons  s ON m.season_id   = s.season_id
           WHERE ss.submission_id = ? AND s.league_id = ?""",
        (submission_id, session['league_id'])
    ).fetchone()

    if not sub:
        flash('Submission not found.', 'error')
        return redirect(url_for('self_report.pending'))

    if sub['status'] != 'pending':
        flash('This submission has already been reviewed.', 'info')
        return redirect(url_for('self_report.pending'))

    if sub['matchup_status'] == 'completed':
        flash('This matchup already has scores entered. Rejecting submission.', 'error')
        db.execute(
            "UPDATE score_submissions SET status='rejected', admin_note='Matchup already scored', "
            "reviewed_at=? WHERE submission_id=?",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), submission_id)
        )
        db.commit()
        return redirect(url_for('self_report.pending'))

    # Load detail rows
    details = db.execute(
        "SELECT * FROM score_submission_details WHERE submission_id = ? ORDER BY player_id, hole_number",
        (submission_id,)
    ).fetchall()

    # Load holes
    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = ? ORDER BY hole_number",
        (sub['tee_id'],)
    ).fetchall()

    if not holes:
        flash('Cannot approve: no hole data for the selected tee.', 'error')
        return redirect(url_for('self_report.pending'))

    # Load teams
    def load_team(team_id):
        return db.execute(
            """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                           p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
               FROM teams t
               LEFT JOIN players p1 ON t.player1_id = p1.player_id
               LEFT JOIN players p2 ON t.player2_id = p2.player_id
               WHERE t.team_id = ?""", (team_id,)
        ).fetchone()

    team1 = load_team(sub['team1_id'])
    team2 = load_team(sub['team2_id'])

    players = _build_player_list(db, sub['season_id'], team1, team2)

    # Build gross dict from submission details
    gross = {}
    for d in details:
        pid = d['player_id']
        if pid not in gross:
            gross[pid] = {}
        gross[pid][d['hole_number']] = d['gross_score']

    # Validate all players have all holes
    for p in players:
        pid = p['player_id']
        if pid not in gross or len(gross[pid]) != len(holes):
            flash(f"Submission is missing scores for player {p['first_name']} {p['last_name']}. Cannot approve.", 'error')
            return redirect(url_for('self_report.pending'))

    # League settings
    settings = get_league_settings(db, sub['season_id'], session['league_id'])
    handicap_percent = float(settings['handicap_percent']) if settings else 90.0
    max_handicap     = float(settings['max_handicap_index']) if settings else 18.0

    # Playing handicaps
    playing_hcps = {}
    for p in players:
        pid = p['player_id']
        playing_hcps[pid] = calc_playing_handicap(p['handicap'], handicap_percent, max_handicap)

    # Net scores per hole
    net = {}
    for p in players:
        pid = p['player_id']
        ph  = playing_hcps[pid]
        net[pid] = []
        for h in holes:
            s = strokes_on_hole(ph, h['handicap_index'], total_holes=len(holes))
            net[pid].append(gross[pid][h['hole_number']] - s)

    # A/B designation
    def designate(team):
        tp = [p for p in players if p['team_id'] == team['team_id']]
        tp_sorted = sorted(tp, key=lambda x: playing_hcps[x['player_id']])
        return tp_sorted[0]['player_id'], tp_sorted[1]['player_id']

    t1_a, t1_b = designate(team1)
    t2_a, t2_b = designate(team2)

    def match_result(pid_x, pid_y):
        hole_pts_x, hole_pts_y = 0.0, 0.0
        for i in range(len(holes)):
            px, py = calc_match_play(net[pid_x][i], net[pid_y][i])
            hole_pts_x += px
            hole_pts_y += py
        total_net_x = sum(net[pid_x])
        total_net_y = sum(net[pid_y])
        overall_x, overall_y = calc_match_play(total_net_x, total_net_y)
        return hole_pts_x, hole_pts_y, overall_x, overall_y

    aa = match_result(t1_a, t2_a)
    bb = match_result(t1_b, t2_b)

    matchup_id = sub['matchup_id']

    # Save round
    db.execute(
        """INSERT INTO rounds (matchup_id, season_id, course_id, tee_id, round_date, round_number)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (matchup_id, sub['season_id'], sub['course_id'], sub['tee_id'],
         sub['round_date'] or datetime.now().strftime('%Y-%m-%d'), sub['round_number'])
    )
    round_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()['id']

    # Scorecards + hole scores
    for p in players:
        pid = p['player_id']
        db.execute(
            """INSERT INTO scorecards
               (round_id, player_id, team_id, handicap_at_time_of_play, self_reported, approved, approved_by_user_id)
               VALUES (?, ?, ?, ?, 1, 1, NULL)""",
            (round_id, pid, p['team_id'], playing_hcps[pid])
        )
        sc_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()['id']
        for h in holes:
            diff = gross[pid][h['hole_number']] - h['par']
            net_score = net[pid][holes.index(h)]
            db.execute(
                """INSERT INTO hole_scores
                   (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sc_id, h['hole_id'], h['hole_number'],
                 gross[pid][h['hole_number']], net_score, diff)
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
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (matchup_id, tid, pid, role,
             hole_pts, overall_pt, hole_pts + overall_pt, opp)
        )

    # Mark matchup completed
    db.execute(
        "UPDATE matchups SET status = 'completed', course_id = ?, tee_id = ? WHERE matchup_id = ?",
        (sub['course_id'], sub['tee_id'], matchup_id)
    )

    # Mark submission approved
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        "UPDATE score_submissions SET status='approved', reviewed_at=? WHERE submission_id=?",
        (now, submission_id)
    )

    db.commit()

    # Recalculate handicaps
    for p in players:
        recalc_handicap_for_player(db, p['player_id'], sub['season_id'], session['league_id'])
    db.commit()

    flash('Submission approved and scores saved!', 'success')
    return redirect(url_for('self_report.pending'))


# ---------------------------------------------------------------------------
# Admin: reject
# ---------------------------------------------------------------------------

@bp.route('/<int:submission_id>/reject', methods=['POST'])
@admin_required
def reject(submission_id):
    db = get_db()

    sub = db.execute(
        """SELECT ss.*, s.league_id
           FROM score_submissions ss
           JOIN matchups m ON ss.matchup_id = m.matchup_id
           JOIN seasons  s ON m.season_id   = s.season_id
           WHERE ss.submission_id = ? AND s.league_id = ?""",
        (submission_id, session['league_id'])
    ).fetchone()

    if not sub:
        flash('Submission not found.', 'error')
        return redirect(url_for('self_report.pending'))

    note = request.form.get('admin_note', '').strip()
    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        "UPDATE score_submissions SET status='rejected', admin_note=?, reviewed_at=? WHERE submission_id=?",
        (note or None, now, submission_id)
    )
    db.commit()
    flash('Submission rejected.', 'info')
    return redirect(url_for('self_report.pending'))
