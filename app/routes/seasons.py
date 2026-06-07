from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required

bp = Blueprint('seasons', __name__, url_prefix='/seasons')


@bp.route('/')
@login_required
def index():
    db = get_db()
    seasons = db.execute(
        """SELECT s.season_id, s.season_name, s.start_date, s.end_date,
                  COUNT(DISTINCT t.team_id) as team_count
           FROM seasons s
           LEFT JOIN teams t ON t.season_id = s.season_id
           WHERE s.league_id = ?
           GROUP BY s.season_id
           ORDER BY s.start_date DESC, s.season_id DESC""",
        (session['league_id'],)
    ).fetchall()
    return render_template('seasons/index.html', seasons=seasons)


@bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create():
    if request.method == 'POST':
        season_name = request.form.get('season_name', '').strip()
        start_date  = request.form.get('start_date', '').strip() or None
        end_date    = request.form.get('end_date', '').strip() or None

        if not season_name:
            flash('Season name is required.', 'error')
            return render_template('seasons/create.html',
                                   season_name=season_name, start_date=start_date or '', end_date=end_date or '')

        db = get_db()
        existing = db.execute(
            "SELECT season_id FROM seasons WHERE league_id = ? AND LOWER(season_name) = LOWER(?)",
            (session['league_id'], season_name)
        ).fetchone()
        if existing:
            flash('A season with that name already exists.', 'error')
            return render_template('seasons/create.html',
                                   season_name=season_name, start_date=start_date or '', end_date=end_date or '')

        db.execute(
            "INSERT INTO seasons (league_id, season_name, start_date, end_date) VALUES (?, ?, ?, ?)",
            (session['league_id'], season_name, start_date, end_date)
        )
        db.commit()
        flash(f'Season "{season_name}" created.', 'success')
        return redirect(url_for('seasons.index'))

    return render_template('seasons/create.html', season_name='', start_date='', end_date='')


@bp.route('/<int:season_id>')
@login_required
def detail(season_id):
    db = get_db()
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = ? AND league_id = ?",
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    teams = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.last_name AS player1_last, p2.last_name AS player2_last,
                  p1.first_name AS player1_first, p2.first_name AS player2_first
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = ? AND t.league_id = ?
           ORDER BY p1.last_name, p2.last_name""",
        (season_id, session['league_id'])
    ).fetchall()

    return render_template('seasons/detail.html', season=season, teams=teams)
