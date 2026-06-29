from flask import Blueprint, session, request, redirect, url_for, flash
from database import get_db
from routes.auth import login_required

bp = Blueprint('reflections', __name__)


@bp.route('/reflections/<int:season_id>/<int:week_number>/odds-and-ends', methods=['POST'])
@login_required
def save_odds_and_ends(season_id, week_number):
    if session.get('role') != 'league_admin':
        flash('Unauthorized', 'error')
        return redirect(url_for('main.dashboard'))

    league_id = session['league_id']
    text = request.form.get('odds_and_ends', '').strip() or None

    db = get_db()
    db.execute(
        """INSERT INTO round_reflections (league_id, season_id, week_number, odds_and_ends, updated_at)
           VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (league_id, season_id, week_number)
           DO UPDATE SET odds_and_ends = EXCLUDED.odds_and_ends, updated_at = CURRENT_TIMESTAMP""",
        (league_id, season_id, week_number, text)
    )
    return redirect(url_for('main.dashboard'))
