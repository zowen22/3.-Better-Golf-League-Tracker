"""
Hall of Fame — admin-curated, cross-season custom awards (GLT #5).

Fixed-slot version per @user's 2026-07-10 decision: a small enum of award
slots, not fully custom award types. Distinct from standings.py's /awards
page, which auto-computes current-season-only leaderboards.

Routes:
  GET  /hall-of-fame                                  member view: every winner, every season
  GET  /admin/season/<id>/hall-of-fame                admin: list + add form
  POST /admin/season/<id>/hall-of-fame/add            admin: add a winner
  POST /admin/hall-of-fame/<winner_id>/delete         admin: remove a winner
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required

bp = Blueprint('hall_of_fame', __name__)

HALL_OF_FAME_SLOTS = [
    ('rookie_of_year',        'Rookie of the Year'),
    ('sportsmanship',         'Sportsmanship Award'),
    ('commissioners_choice',  "Commissioner's Choice"),
    ('other',                 'Other (custom)'),
]


def _winner_display_name(row):
    if row['p_first'] or row['p_last']:
        return f"{row['p_first'] or ''} {row['p_last'] or ''}".strip()
    if row['team_name']:
        return row['team_name']
    return row['winner_name'] or '—'


def _fetch_winners(db, league_id):
    rows = db.execute(
        """SELECT hfw.*, s.season_name,
                  p.first_name AS p_first, p.last_name AS p_last,
                  t.team_name
             FROM hall_of_fame_winners hfw
             JOIN seasons s ON hfw.season_id = s.season_id
             LEFT JOIN players p ON hfw.player_id = p.player_id
             LEFT JOIN teams t   ON hfw.team_id   = t.team_id
            WHERE hfw.league_id = %s
            ORDER BY hfw.season_id DESC, hfw.winner_id DESC""",
        (league_id,)
    ).fetchall()
    slot_labels = dict(HALL_OF_FAME_SLOTS)
    return [{
        'winner_id': r['winner_id'],
        'season_name': r['season_name'],
        'season_id': r['season_id'],
        'award_label': r['award_label'] if r['award_slot'] == 'other' and r['award_label'] else slot_labels.get(r['award_slot'], r['award_slot']),
        'winner_display_name': _winner_display_name(r),
        'notes': r['notes'],
    } for r in rows]


@bp.route('/hall-of-fame')
@login_required
def index():
    db = get_db()
    league_id = session['league_id']
    winners = _fetch_winners(db, league_id)
    return render_template('hall_of_fame/index.html', winners=winners)


@bp.route('/admin/season/<int:season_id>/hall-of-fame')
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
        return redirect(url_for('main.dashboard'))

    players = db.execute(
        "SELECT player_id, first_name || ' ' || last_name AS name FROM players "
        "WHERE league_id = %s ORDER BY last_name, first_name",
        (league_id,)
    ).fetchall()
    teams = db.execute(
        "SELECT team_id, team_name FROM teams WHERE season_id = %s AND league_id = %s ORDER BY team_name",
        (season_id, league_id)
    ).fetchall()

    winners = _fetch_winners(db, league_id)

    return render_template('hall_of_fame/admin_list.html',
                           season=season, players=players, teams=teams,
                           winners=winners, slots=HALL_OF_FAME_SLOTS)


@bp.route('/admin/season/<int:season_id>/hall-of-fame/add', methods=['POST'])
@admin_required
def admin_add(season_id):
    db = get_db()
    league_id = session['league_id']

    award_slot = request.form.get('award_slot', '').strip()
    award_label = request.form.get('award_label', '').strip() or None
    player_id = request.form.get('player_id', '').strip() or None
    team_id = request.form.get('team_id', '').strip() or None
    winner_name = request.form.get('winner_name', '').strip() or None
    notes = request.form.get('notes', '').strip() or None

    valid_slots = {s[0] for s in HALL_OF_FAME_SLOTS}
    if award_slot not in valid_slots:
        flash('Invalid award type.', 'error')
        return redirect(url_for('hall_of_fame.admin_list', season_id=season_id))
    if not (player_id or team_id or winner_name):
        flash('Pick a player or team, or enter a winner name.', 'error')
        return redirect(url_for('hall_of_fame.admin_list', season_id=season_id))

    db.execute(
        """INSERT INTO hall_of_fame_winners
           (league_id, season_id, award_slot, award_label, player_id, team_id, winner_name, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (league_id, season_id, award_slot, award_label,
         int(player_id) if player_id else None,
         int(team_id) if team_id else None,
         winner_name, notes)
    )
    db.commit()
    flash('Winner added.', 'success')
    return redirect(url_for('hall_of_fame.admin_list', season_id=season_id))


@bp.route('/admin/hall-of-fame/<int:winner_id>/delete', methods=['POST'])
@admin_required
def admin_delete(winner_id):
    db = get_db()
    league_id = session['league_id']

    row = db.execute(
        "SELECT season_id FROM hall_of_fame_winners WHERE winner_id = %s AND league_id = %s",
        (winner_id, league_id)
    ).fetchone()
    if not row:
        flash('Winner not found.', 'error')
        return redirect(url_for('main.dashboard'))

    db.execute("DELETE FROM hall_of_fame_winners WHERE winner_id = %s AND league_id = %s", (winner_id, league_id))
    db.commit()
    flash('Winner removed.', 'success')
    return redirect(url_for('hall_of_fame.admin_list', season_id=row['season_id']))
