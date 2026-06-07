from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required
from datetime import datetime

bp = Blueprint('subs', __name__, url_prefix='/subs')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_sub_assignments(db, matchup_id):
    """Return dict: player_id -> absence record dict (pre-round or round-based)."""
    result = {}
    rows = db.execute(
        "SELECT * FROM player_absences WHERE matchup_id = ?", (matchup_id,)
    ).fetchall()
    for r in rows:
        result[r['player_id']] = {
            'absence_id':    r['absence_id'],
            'sub_player_id': r['sub_player_id'],
            'reason':        r['reason'] or '',
            'excused':       r['excused'],
        }
    round_row = db.execute(
        "SELECT round_id FROM rounds WHERE matchup_id = ?", (matchup_id,)
    ).fetchone()
    if round_row:
        round_rows = db.execute(
            "SELECT * FROM player_absences WHERE round_id = ?",
            (round_row['round_id'],)
        ).fetchall()
        for r in round_rows:
            if r['player_id'] not in result:
                result[r['player_id']] = {
                    'absence_id':    r['absence_id'],
                    'sub_player_id': r['sub_player_id'],
                    'reason':        r['reason'] or '',
                    'excused':       r['excused'],
                }
    return result


def pending_sub_request_count(db, league_id):
    """Return count of open sub requests for admin badge."""
    try:
        row = db.execute(
            "SELECT COUNT(*) AS cnt FROM sub_requests WHERE league_id=? AND status='open'",
            (league_id,)
        ).fetchone()
        return row['cnt'] if row else 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Admin: manage subs for a matchup (existing feature)
# ---------------------------------------------------------------------------

@bp.route('/<int:matchup_id>', methods=['GET', 'POST'])
@admin_required
def manage(matchup_id):
    db = get_db()

    matchup = db.execute(
        """SELECT m.*, s.season_name, s.league_id, s.season_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = ?""",
        (matchup_id,)
    ).fetchone()

    if not matchup or matchup['league_id'] != session['league_id']:
        flash('Matchup not found.', 'error')
        return redirect(url_for('schedule.index', season_id=session.get('current_season_id', 1)))

    if matchup['is_bye']:
        flash('Bye weeks do not have player assignments.', 'error')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

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

    all_players = db.execute(
        """SELECT player_id, first_name, last_name FROM players
           WHERE league_id = ? AND active = 1
           ORDER BY last_name, first_name""",
        (session['league_id'],)
    ).fetchall()

    matchup_player_ids = set()
    for team in [team1, team2]:
        if team['p1_id']:
            matchup_player_ids.add(team['p1_id'])
        if team['p2_id']:
            matchup_player_ids.add(team['p2_id'])

    current_subs = _get_sub_assignments(db, matchup_id)

    if request.method == 'POST':
        players_in_matchup = []
        for team in [team1, team2]:
            for pid_key in ['p1_id', 'p2_id']:
                if team[pid_key]:
                    players_in_matchup.append(team[pid_key])

        for pid in players_in_matchup:
            is_absent  = request.form.get(f'absent_{pid}') == '1'
            sub_pid    = request.form.get(f'sub_{pid}', '').strip()
            reason     = request.form.get(f'reason_{pid}', '').strip()
            excused    = 1 if request.form.get(f'excused_{pid}') == '1' else 0
            sub_pid_val = int(sub_pid) if sub_pid else None
            existing   = current_subs.get(pid)

            if is_absent:
                if existing:
                    db.execute(
                        """UPDATE player_absences
                           SET sub_player_id=?, reason=?, excused=?
                           WHERE absence_id=?""",
                        (sub_pid_val, reason or None, excused, existing['absence_id'])
                    )
                else:
                    db.execute(
                        """INSERT INTO player_absences
                           (round_id, matchup_id, player_id, sub_player_id, reason, excused)
                           VALUES (NULL, ?, ?, ?, ?, ?)""",
                        (matchup_id, pid, sub_pid_val, reason or None, excused)
                    )
            else:
                if existing:
                    db.execute(
                        "DELETE FROM player_absences WHERE absence_id=?",
                        (existing['absence_id'],)
                    )

        db.commit()
        flash('Sub assignments saved.', 'success')
        return redirect(url_for('subs.manage', matchup_id=matchup_id))

    player_rows = []
    for team, team_num in [(team1, 1), (team2, 2)]:
        for pid_key, fname_key, lname_key in [('p1_id', 'p1_first', 'p1_last'),
                                               ('p2_id', 'p2_first', 'p2_last')]:
            pid = team[pid_key]
            if pid:
                sub_info = current_subs.get(pid, {})
                sub_pid  = sub_info.get('sub_player_id')
                sub_name = None
                if sub_pid:
                    sp = db.execute(
                        "SELECT first_name, last_name FROM players WHERE player_id=?",
                        (sub_pid,)
                    ).fetchone()
                    if sp:
                        sub_name = f"{sp['first_name']} {sp['last_name']}"
                player_rows.append({
                    'player_id':     pid,
                    'first_name':    team[fname_key],
                    'last_name':     team[lname_key],
                    'team_num':      team_num,
                    'team_name':     (team['team_name'] or
                                      f"{team['p1_last'] or '?'} / {team['p2_last'] or '?'}"),
                    'is_absent':     pid in current_subs,
                    'sub_player_id': sub_pid,
                    'sub_name':      sub_name,
                    'reason':        sub_info.get('reason', ''),
                    'excused':       sub_info.get('excused', 0),
                })

    return render_template('subs/manage.html',
                           matchup=matchup,
                           team1=team1, team2=team2,
                           player_rows=player_rows,
                           all_players=all_players,
                           matchup_player_ids=matchup_player_ids)


# ---------------------------------------------------------------------------
# Player: request a sub for an upcoming matchup
# ---------------------------------------------------------------------------

@bp.route('/request/<int:matchup_id>', methods=['GET', 'POST'])
@login_required
def request_sub(matchup_id):
    db = get_db()
    player_id = session.get('player_id')

    if not player_id:
        flash('Your account is not linked to a player. Ask your admin to link your account.', 'error')
        return redirect(url_for('main.dashboard'))

    matchup = db.execute(
        """SELECT m.*, s.season_name, s.league_id, s.season_id,
                  w.week_date, w.week_num
           FROM matchups m
           JOIN seasons s ON m.season_id = s.season_id
           LEFT JOIN schedule_weeks w ON m.week_id = w.week_id
           WHERE m.matchup_id = ?""",
        (matchup_id,)
    ).fetchone()

    if not matchup or matchup['league_id'] != session['league_id']:
        flash('Matchup not found.', 'error')
        return redirect(url_for('main.dashboard'))

    if matchup['is_bye']:
        flash('Bye weeks do not have sub requests.', 'error')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

    # Verify this player is actually in this matchup
    team_check = db.execute(
        """SELECT t.team_id FROM teams t
           JOIN matchups m ON (m.team1_id = t.team_id OR m.team2_id = t.team_id)
           WHERE m.matchup_id = ?
             AND (t.player1_id = ? OR t.player2_id = ?)""",
        (matchup_id, player_id, player_id)
    ).fetchone()

    if not team_check:
        flash('You are not scheduled to play in this matchup.', 'error')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

    # Check for existing open request
    existing = db.execute(
        "SELECT * FROM sub_requests WHERE matchup_id=? AND player_id=? AND status='open'",
        (matchup_id, player_id)
    ).fetchone()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'cancel' and existing:
            db.execute(
                "UPDATE sub_requests SET status='cancelled', updated_at=? WHERE request_id=?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), existing['request_id'])
            )
            db.commit()
            flash('Sub request cancelled.', 'success')
            return redirect(url_for('subs.my_requests'))

        if not existing:
            notes = request.form.get('notes', '').strip()
            db.execute(
                """INSERT INTO sub_requests
                   (league_id, season_id, matchup_id, player_id, notes, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'open', ?)""",
                (session['league_id'], matchup['season_id'], matchup_id,
                 player_id, notes or None,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            db.commit()
            flash('Sub request submitted. Your admin will be notified.', 'success')
            return redirect(url_for('subs.my_requests'))

    # Load matchup info for display
    teams = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.team_id IN (
               SELECT team1_id FROM matchups WHERE matchup_id=?
               UNION
               SELECT team2_id FROM matchups WHERE matchup_id=?
           )""",
        (matchup_id, matchup_id)
    ).fetchall()

    return render_template('subs/request.html',
                           matchup=matchup,
                           teams=teams,
                           existing=existing,
                           player_id=player_id)


# ---------------------------------------------------------------------------
# Player: my sub requests
# ---------------------------------------------------------------------------

@bp.route('/my-requests')
@login_required
def my_requests():
    db = get_db()
    player_id = session.get('player_id')

    if not player_id:
        flash('Your account is not linked to a player.', 'error')
        return redirect(url_for('main.dashboard'))

    requests_rows = db.execute(
        """SELECT sr.*,
                  s.season_name,
                  w.week_num, w.week_date,
                  sub.first_name AS sub_first, sub.last_name AS sub_last
           FROM sub_requests sr
           JOIN seasons s ON sr.season_id = s.season_id
           LEFT JOIN matchups m ON sr.matchup_id = m.matchup_id
           LEFT JOIN schedule_weeks w ON m.week_id = w.week_id
           LEFT JOIN players sub ON sr.sub_player_id = sub.player_id
           WHERE sr.player_id = ? AND sr.league_id = ?
           ORDER BY sr.created_at DESC""",
        (player_id, session['league_id'])
    ).fetchall()

    return render_template('subs/my_requests.html', requests=requests_rows)


# ---------------------------------------------------------------------------
# Admin: sub request queue
# ---------------------------------------------------------------------------

@bp.route('/admin/requests')
@admin_required
def admin_requests():
    db = get_db()
    league_id = session['league_id']

    open_requests = db.execute(
        """SELECT sr.*,
                  p.first_name AS player_first, p.last_name AS player_last,
                  s.season_name,
                  w.week_num, w.week_date,
                  t1p1.first_name AS t1p1_first, t1p1.last_name AS t1p1_last,
                  t1p2.first_name AS t1p2_first, t1p2.last_name AS t1p2_last,
                  t2p1.first_name AS t2p1_first, t2p1.last_name AS t2p1_last,
                  t2p2.first_name AS t2p2_first, t2p2.last_name AS t2p2_last,
                  tm1.team_name AS team1_name, tm2.team_name AS team2_name
           FROM sub_requests sr
           JOIN players p  ON sr.player_id = p.player_id
           JOIN seasons s  ON sr.season_id = s.season_id
           LEFT JOIN matchups m  ON sr.matchup_id = m.matchup_id
           LEFT JOIN schedule_weeks w ON m.week_id = w.week_id
           LEFT JOIN teams tm1 ON m.team1_id = tm1.team_id
           LEFT JOIN teams tm2 ON m.team2_id = tm2.team_id
           LEFT JOIN players t1p1 ON tm1.player1_id = t1p1.player_id
           LEFT JOIN players t1p2 ON tm1.player2_id = t1p2.player_id
           LEFT JOIN players t2p1 ON tm2.player1_id = t2p1.player_id
           LEFT JOIN players t2p2 ON tm2.player2_id = t2p2.player_id
           WHERE sr.league_id = ? AND sr.status = 'open'
           ORDER BY w.week_date ASC, sr.created_at ASC""",
        (league_id,)
    ).fetchall()

    recent_resolved = db.execute(
        """SELECT sr.*,
                  p.first_name AS player_first, p.last_name AS player_last,
                  sub.first_name AS sub_first, sub.last_name AS sub_last,
                  s.season_name,
                  w.week_num, w.week_date
           FROM sub_requests sr
           JOIN players p ON sr.player_id = p.player_id
           JOIN seasons s ON sr.season_id = s.season_id
           LEFT JOIN matchups m  ON sr.matchup_id = m.matchup_id
           LEFT JOIN schedule_weeks w ON m.week_id = w.week_id
           LEFT JOIN players sub ON sr.sub_player_id = sub.player_id
           WHERE sr.league_id = ? AND sr.status != 'open'
           ORDER BY sr.updated_at DESC
           LIMIT 20""",
        (league_id,)
    ).fetchall()

    all_players = db.execute(
        """SELECT player_id, first_name, last_name FROM players
           WHERE league_id = ? AND active = 1
           ORDER BY last_name, first_name""",
        (league_id,)
    ).fetchall()

    return render_template('subs/admin_requests.html',
                           open_requests=open_requests,
                           recent_resolved=recent_resolved,
                           all_players=all_players)


# ---------------------------------------------------------------------------
# Admin: assign a sub to a request
# ---------------------------------------------------------------------------

@bp.route('/admin/requests/<int:request_id>/assign', methods=['POST'])
@admin_required
def admin_assign(request_id):
    db = get_db()

    req = db.execute(
        "SELECT * FROM sub_requests WHERE request_id=? AND league_id=?",
        (request_id, session['league_id'])
    ).fetchone()

    if not req:
        flash('Request not found.', 'error')
        return redirect(url_for('subs.admin_requests'))

    sub_pid_str  = request.form.get('sub_player_id', '').strip()
    admin_notes  = request.form.get('admin_notes', '').strip()
    sub_pid      = int(sub_pid_str) if sub_pid_str else None

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Mark request as filled
    db.execute(
        """UPDATE sub_requests
           SET status='filled', sub_player_id=?, admin_notes=?, updated_at=?
           WHERE request_id=?""",
        (sub_pid, admin_notes or None, now, request_id)
    )

    # Also create/update the player_absences record so score entry picks it up
    existing_absence = db.execute(
        "SELECT absence_id FROM player_absences WHERE matchup_id=? AND player_id=?",
        (req['matchup_id'], req['player_id'])
    ).fetchone()

    reason_text = req['notes'] or 'Player sub request'
    if existing_absence:
        db.execute(
            """UPDATE player_absences
               SET sub_player_id=?, reason=?, excused=1
               WHERE absence_id=?""",
            (sub_pid, reason_text, existing_absence['absence_id'])
        )
    else:
        db.execute(
            """INSERT INTO player_absences
               (round_id, matchup_id, player_id, sub_player_id, reason, excused)
               VALUES (NULL, ?, ?, ?, ?, 1)""",
            (req['matchup_id'], req['player_id'], sub_pid, reason_text)
        )

    db.commit()
    flash('Sub assigned and absence record created.', 'success')
    return redirect(url_for('subs.admin_requests'))


# ---------------------------------------------------------------------------
# Admin: dismiss / cancel a request without assigning
# ---------------------------------------------------------------------------

@bp.route('/admin/requests/<int:request_id>/dismiss', methods=['POST'])
@admin_required
def admin_dismiss(request_id):
    db = get_db()
    req = db.execute(
        "SELECT * FROM sub_requests WHERE request_id=? AND league_id=?",
        (request_id, session['league_id'])
    ).fetchone()
    if not req:
        flash('Request not found.', 'error')
        return redirect(url_for('subs.admin_requests'))

    admin_notes = request.form.get('admin_notes', '').strip()
    db.execute(
        """UPDATE sub_requests SET status='dismissed', admin_notes=?, updated_at=?
           WHERE request_id=?""",
        (admin_notes or None, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), request_id)
    )
    db.commit()
    flash('Request dismissed.', 'success')
    return redirect(url_for('subs.admin_requests'))
