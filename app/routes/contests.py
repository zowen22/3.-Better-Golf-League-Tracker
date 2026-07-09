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
    ('team_low_net',     'Team Low Net'),
    ('custom',           'Custom'),
]

# Contest types where a result is a team, not a player, and can be
# auto-calculated from scorecard data rather than hand-entered.
TEAM_CONTEST_TYPES = {'team_low_net'}

# ── Member view ──────────────────────────────────────────────────────────────

@bp.route('/contests/season/<int:season_id>')
@login_required
def season_view(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    contests = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM contest_results cr WHERE cr.contest_id = c.contest_id) AS result_count
           FROM contests c
           WHERE c.season_id = %s AND c.league_id = %s
           ORDER BY c.week_num ASC NULLS LAST, c.contest_id ASC""",
        (season_id, league_id)
    ).fetchall()

    # For each contest, load results with player/team names
    contest_data = []
    for c in contests:
        results = db.execute(
            """SELECT cr.*, p.first_name, p.last_name,
                      t.team_name, tp1.first_name AS t_p1_first, tp1.last_name AS t_p1_last,
                      tp2.first_name AS t_p2_first, tp2.last_name AS t_p2_last
               FROM contest_results cr
               LEFT JOIN players p ON p.player_id = cr.player_id
               LEFT JOIN teams t ON t.team_id = cr.team_id
               LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
               LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
               WHERE cr.contest_id = %s
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
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('admin.landing'))

    contests = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM contest_results cr WHERE cr.contest_id = c.contest_id) AS result_count
           FROM contests c
           WHERE c.season_id = %s AND c.league_id = %s
           ORDER BY c.week_num ASC NULLS LAST, c.contest_id ASC""",
        (season_id, league_id)
    ).fetchall()

    # Weeks for dropdown
    weeks = db.execute(
        """SELECT DISTINCT week_number AS week_num FROM matchups WHERE season_id = %s ORDER BY week_number""",
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

    if contest_type in TEAM_CONTEST_TYPES and week_num is None:
        flash('Team Low Net requires a specific week — pick one before saving.', 'error')
        return redirect(url_for('contests.admin_list', season_id=season_id))

    db.execute(
        """INSERT INTO contests (league_id, season_id, name, contest_type, week_num, description)
           VALUES (%s, %s, %s, %s, %s, %s)""",
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
        "SELECT * FROM contests WHERE contest_id = %s AND league_id = %s",
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
        elif contest_type in TEAM_CONTEST_TYPES and not week_num:
            flash('Team Low Net requires a specific week — pick one before saving.', 'error')
        else:
            if week_num:
                try:
                    week_num = int(week_num)
                except ValueError:
                    week_num = None
            db.execute(
                """UPDATE contests SET name=%s, contest_type=%s, week_num=%s, description=%s
                   WHERE contest_id=%s""",
                (name, contest_type, week_num, description, contest_id)
            )
            db.commit()
            flash('Contest updated.', 'success')
            return redirect(url_for('contests.admin_edit', contest_id=contest_id))

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s", (contest['season_id'],)
    ).fetchone()

    # Current results
    results = db.execute(
        """SELECT cr.*, p.first_name, p.last_name,
                  t.team_name, tp1.first_name AS t_p1_first, tp1.last_name AS t_p1_last,
                  tp2.first_name AS t_p2_first, tp2.last_name AS t_p2_last
           FROM contest_results cr
           LEFT JOIN players p ON p.player_id = cr.player_id
           LEFT JOIN teams t ON t.team_id = cr.team_id
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           WHERE cr.contest_id = %s
           ORDER BY cr.rank ASC, cr.result_id ASC""",
        (contest_id,)
    ).fetchall()

    # All active players for add-result dropdown
    players = db.execute(
        """SELECT player_id, first_name, last_name FROM players
           WHERE league_id = %s AND active = 1
           ORDER BY last_name, first_name""",
        (league_id,)
    ).fetchall()

    weeks = db.execute(
        """SELECT DISTINCT week_number AS week_num FROM matchups WHERE season_id = %s ORDER BY week_number""",
        (contest['season_id'],)
    ).fetchall()

    return render_template('contests/admin_edit.html',
                           contest=contest, season=season,
                           results=results, players=players,
                           weeks=weeks, contest_types=CONTEST_TYPES,
                           team_contest_types=TEAM_CONTEST_TYPES)


@bp.route('/admin/contests/<int:contest_id>/calculate', methods=['POST'])
@admin_required
def admin_calculate(contest_id):
    """Auto-calculate results for a computed team contest type (currently
    just Team Low Net) from scorecard/hole_score data. Replaces any
    previously-computed team results for this contest; manual (player-scoped)
    entries on the same contest are left untouched."""
    db = get_db()
    league_id = session['league_id']

    contest = db.execute(
        "SELECT * FROM contests WHERE contest_id = %s AND league_id = %s",
        (contest_id, league_id)
    ).fetchone()
    if not contest:
        flash('Contest not found.', 'error')
        return redirect(url_for('admin.landing'))

    if contest['contest_type'] not in TEAM_CONTEST_TYPES:
        flash('This contest type is not auto-calculated.', 'error')
        return redirect(url_for('contests.admin_edit', contest_id=contest_id))

    if not contest['week_num']:
        flash('This contest has no week set — cannot calculate.', 'error')
        return redirect(url_for('contests.admin_edit', contest_id=contest_id))

    if contest['contest_type'] == 'team_low_net':
        # Sum each team's players' full-round net totals for the contest's
        # week. Only teams where BOTH scorecards are non-absent (a real sub
        # counts fine — their scorecard is is_absent=0 like anyone else's;
        # a true ghost-scored absence excludes the team) are eligible.
        team_totals = db.execute(
            """SELECT sc.team_id, SUM(hs.net_score) AS total_net
               FROM matchups m
               JOIN rounds r ON r.matchup_id = m.matchup_id
               JOIN scorecards sc ON sc.round_id = r.round_id
               JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
               WHERE m.season_id = %s AND m.week_number = %s
                 AND m.status = 'completed' AND m.is_bye = 0
                 AND sc.is_absent = 0
               GROUP BY sc.team_id
               HAVING COUNT(DISTINCT sc.scorecard_id) = 2""",
            (contest['season_id'], contest['week_num'])
        ).fetchall()

        if not team_totals:
            flash('No completed team rounds (with both players present) found for that week yet.', 'error')
            return redirect(url_for('contests.admin_edit', contest_id=contest_id))

        # Standard competition ranking: ties share a rank, next rank skips.
        ranked = sorted(team_totals, key=lambda t: t['total_net'])
        rows = []
        prev_total, prev_rank = None, 0
        for i, t in enumerate(ranked, start=1):
            total_net = round(float(t['total_net']), 1)
            rank = prev_rank if total_net == prev_total else i
            prev_total, prev_rank = total_net, rank
            rows.append((t['team_id'], total_net, rank))

        db.execute(
            "DELETE FROM contest_results WHERE contest_id = %s AND team_id IS NOT NULL",
            (contest_id,)
        )
        for team_id, total_net, rank in rows:
            db.execute(
                """INSERT INTO contest_results (contest_id, team_id, value_num, value_text, rank)
                   VALUES (%s, %s, %s, %s, %s)""",
                (contest_id, team_id, total_net, f'{total_net:g} net', rank)
            )
        db.commit()
        flash(f'Calculated {len(rows)} team result(s).', 'success')

    return redirect(url_for('contests.admin_edit', contest_id=contest_id))


@bp.route('/admin/contests/<int:contest_id>/results/save', methods=['POST'])
@admin_required
def admin_save_results(contest_id):
    db = get_db()
    league_id = session['league_id']

    contest = db.execute(
        "SELECT * FROM contests WHERE contest_id = %s AND league_id = %s",
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
                   VALUES (%s, %s, %s, %s, %s)""",
                (contest_id, int(player_id), value_text, notes, rank)
            )
            db.commit()
            flash('Result added.', 'success')

    elif action == 'delete':
        result_id = request.form.get('result_id')
        if result_id:
            db.execute(
                "DELETE FROM contest_results WHERE result_id = %s AND contest_id = %s",
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
        "SELECT * FROM contests WHERE contest_id = %s AND league_id = %s",
        (contest_id, league_id)
    ).fetchone()
    if not contest:
        flash('Contest not found.', 'error')
        return redirect(url_for('admin.landing'))

    season_id = contest['season_id']
    db.execute("DELETE FROM contest_results WHERE contest_id = %s", (contest_id,))
    db.execute("DELETE FROM contests WHERE contest_id = %s", (contest_id,))
    db.commit()
    flash('Contest deleted.', 'success')
    return redirect(url_for('contests.admin_list', season_id=season_id))
