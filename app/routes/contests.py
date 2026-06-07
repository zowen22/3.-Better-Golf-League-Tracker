"""
Contests blueprint — track league contests (long drive, closest to pin, etc.)

Routes:
  GET  /contests/season/<id>                     member view: season contest list
  GET  /admin/season/<id>/contests               admin: list + create form
  POST /admin/season/<id>/contests/add            admin: create contest
  GET  /admin/contests/<contest_id>/edit          admin: edit + manage results
  POST /admin/contests/<contest_id>/edit          admin: save contest details
  POST /admin/contests/<contest_id>/results/save  admin: save results for a contest
  POST /admin/contests/<contest_id>/delete        admin: delete contest
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required

bp = Blueprint('contests', __name__)

CONTEST_TYPES = [
    ('long_drive',       'Long Drive'),
    ('closest_to_pin',   'Closest to Pin'),
    ('low_gross',        'Low Gross'),
    ('low_net',          'Low Net'),
    ('most_birdies',     'Most Birdies'),
    ('custom',           'Custom'),
]

# ── Member view ──────────────────────────────────────────────────────────────

@bp.route('/contests/season/<int:season_id>')
@login_required
def season_view(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = ? AND league_id = ?",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    contests = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM contest_results cr WHERE cr.contest_id = c.contest_id) AS result_count
           FROM contests c
           WHERE c.season_id = ? AND c.league_id = ?
           ORDER BY c.week_num ASC NULLS LAST, c.contest_id ASC""",
        (season_id, league_id)
    ).fetchall()

    # For each contest, load results with player names
    contest_data = []
    for c in contests:
        results = db.execute(
            """SELECT cr.*, p.first_name, p.last_name
               FROM contest_results cr
               JOIN players p ON p.player_id = cr.player_id
               WHERE cr.contest_id = ?
               ORDER BY cr.rank ASC, cr.result_id ASC""",
            (c['contest_id'],)
        ).fetchall()
        contest_data.append({'contest': c, 'results': results})

    type_labels = dict(CONTEST_TYPES)
    return render_template('contests/season.html',
                           season=season, contest_data=contest_data,
                           type_labels=type_labels)


# ── Admin: list + create ─────────────────────────────────────────────────────

@bp.route('/admin/season/<int:season_id>/contests')
@admin_required
def admin_list(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = ? AND league_id = ?",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('admin.landing'))

    contests = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM contest_results cr WHERE cr.contest_id = c.contest_id) AS result_count
           FROM contests c
           WHERE c.season_id = ? AND c.league_id = ?
           ORDER BY c.week_num ASC NULLS LAST, c.contest_id ASC""",
        (season_id, league_id)
    ).fetchall()

    # Weeks for dropdown
    weeks = db.execute(
        """SELECT DISTINCT week_num FROM matchups WHERE season_id = ? ORDER BY week_num""",
        (season_id,)
    ).fetchall()

    type_labels = dict(CONTEST_TYPES)
    return render_template('contests/admin_list.html',
                           season=season, contests=contests,
                           weeks=weeks, contest_types=CONTEST_TYPES,
                           type_labels=type_labels)


@bp.route('/admin/season/<int:season_id>/contests/add', methods=['POST'])
@admin_required
def admin_add(season_id):
    db = get_db()
    league_id = session['league_id']

    name         = request.form.get('name', '').strip()
    contest_type = request.form.get('contest_type', 'custom')
    week_num     = request.form.get('week_num') or None
    description  = request.form.get('description', '').strip() or None

    if not name:
        flash('Contest name is required.', 'error')
        return redirect(url_for('contests.admin_list', season_id=season_id))

    if week_num:
        try:
            week_num = int(week_num)
        except ValueError:
            week_num = None

    db.execute(
        """INSERT INTO contests (league_id, season_id, name, contest_type, week_num, description)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (league_id, season_id, name, contest_type, week_num, description)
    )
    db.commit()
    flash(f'Contest "{name}" created.', 'success')
    return redirect(url_for('contests.admin_list', season_id=season_id))


# ── Admin: edit contest + manage results ────────────────────────────────────

@bp.route('/admin/contests/<int:contest_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit(contest_id):
    db = get_db()
    league_id = session['league_id']

    contest = db.execute(
        "SELECT * FROM contests WHERE contest_id = ? AND league_id = ?",
        (contest_id, league_id)
    ).fetchone()
    if not contest:
        flash('Contest not found.', 'error')
        return redirect(url_for('admin.landing'))

    if request.method == 'POST':
        name         = request.form.get('name', '').strip()
        contest_type = request.form.get('contest_type', 'custom')
        week_num     = request.form.get('week_num') or None
        description  = request.form.get('description', '').strip() or None

        if not name:
            flash('Name is required.', 'error')
        else:
            if week_num:
                try:
                    week_num = int(week_num)
                except ValueError:
                    week_num = None
            db.execute(
                """UPDATE contests SET name=?, contest_type=?, week_num=?, description=?
                   WHERE contest_id=?""",
                (name, contest_type, week_num, description, contest_id)
            )
            db.commit()
            flash('Contest updated.', 'success')
            return redirect(url_for('contests.admin_edit', contest_id=contest_id))

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = ?", (contest['season_id'],)
    ).fetchone()

    # Current results
    results = db.execute(
        """SELECT cr.*, p.first_name, p.last_name
           FROM contest_results cr
           JOIN players p ON p.player_id = cr.player_id
           WHERE cr.contest_id = ?
           ORDER BY cr.rank ASC, cr.result_id ASC""",
        (contest_id,)
    ).fetchall()

    # All active players for add-result dropdown
    players = db.execute(
        """SELECT player_id, first_name, last_name FROM players
           WHERE league_id = ? AND active = 1
           ORDER BY last_name, first_name""",
        (league_id,)
    ).fetchall()

    weeks = db.execute(
        """SELECT DISTINCT week_num FROM matchups WHERE season_id = ? ORDER BY week_num""",
        (contest['season_id'],)
    ).fetchall()

    return render_template('contests/admin_edit.html',
                           contest=contest, season=season,
                           results=results, players=players,
                           weeks=weeks, contest_types=CONTEST_TYPES)


@bp.route('/admin/contests/<int:contest_id>/results/save', methods=['POST'])
@admin_required
def admin_save_results(contest_id):
    db = get_db()
    league_id = session['league_id']

    contest = db.execute(
        "SELECT * FROM contests WHERE contest_id = ? AND league_id = ?",
        (contest_id, league_id)
    ).fetchone()
    if not contest:
        flash('Contest not found.', 'error')
        return redirect(url_for('admin.landing'))

    action = request.form.get('action', 'add')

    if action == 'add':
        player_id  = request.form.get('player_id')
        value_text = request.form.get('value_text', '').strip() or None
        notes      = request.form.get('notes', '').strip() or None
        rank_str   = request.form.get('rank', '1')
        try:
            rank = int(rank_str)
        except ValueError:
            rank = 1

        if not player_id:
            flash('Select a player.', 'error')
        else:
            db.execute(
                """INSERT INTO contest_results (contest_id, player_id, value_text, notes, rank)
                   VALUES (?, ?, ?, ?, ?)""",
                (contest_id, int(player_id), value_text, notes, rank)
            )
            db.commit()
            flash('Result added.', 'success')

    elif action == 'delete':
        result_id = request.form.get('result_id')
        if result_id:
            db.execute(
                "DELETE FROM contest_results WHERE result_id = ? AND contest_id = ?",
                (int(result_id), contest_id)
            )
            db.commit()
            flash('Result removed.', 'success')

    return redirect(url_for('contests.admin_edit', contest_id=contest_id))


@bp.route('/admin/contests/<int:contest_id>/delete', methods=['POST'])
@admin_required
def admin_delete(contest_id):
    db = get_db()
    league_id = session['league_id']

    contest = db.execute(
        "SELECT * FROM contests WHERE contest_id = ? AND league_id = ?",
        (contest_id, league_id)
    ).fetchone()
    if not contest:
        flash('Contest not found.', 'error')
        return redirect(url_for('admin.landing'))

    season_id = contest['season_id']
    db.execute("DELETE FROM contest_results WHERE contest_id = ?", (contest_id,))
    db.execute("DELETE FROM contests WHERE contest_id = ?", (contest_id,))
    db.commit()
    flash('Contest deleted.', 'success')
    return redirect(url_for('contests.admin_list', season_id=season_id))
