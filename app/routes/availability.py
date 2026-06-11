"""
Player Availability Tracking
  - Members:  GET/POST /availability/season/<id>   -- mark yourself available/unavailable per week
  - Admin:    GET /admin/season/<id>/availability  -- full grid of all players x all weeks
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db, table_exists
from routes.auth import login_required, admin_required
from datetime import datetime

bp = Blueprint('availability', __name__)


# ── helpers ─────────────────────────────────────────────────────────────────

def _table_exists(db):
    return table_exists(db, 'player_availability')


def _get_season(db, season_id, league_id):
    return db.execute(
        "SELECT * FROM seasons WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()


def _get_weeks(db, season_id):
    """Return list of (week_number, scheduled_date) for all non-bye weeks in order."""
    rows = db.execute(
        """SELECT DISTINCT m.week_number, MIN(m.scheduled_date) AS scheduled_date
           FROM matchups m
           WHERE m.season_id=%s AND (m.is_bye IS NULL OR m.is_bye=0)
           GROUP BY m.week_number
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()
    return rows


def _get_avail_map(db, season_id, league_id, player_ids=None):
    """Return dict: (player_id, week_number) -> {available, note}."""
    if player_ids is not None and len(player_ids) == 0:
        return {}
    if player_ids is not None:
        placeholders = ','.join(['%s'] * len(player_ids))
        rows = db.execute(
            f"""SELECT player_id, week_number, available, note
                FROM player_availability
                WHERE season_id=%s AND league_id=%s AND player_id IN ({placeholders})""",
            [season_id, league_id] + list(player_ids)
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT player_id, week_number, available, note
               FROM player_availability
               WHERE season_id=%s AND league_id=%s""",
            (season_id, league_id)
        ).fetchall()
    return {(r['player_id'], r['week_number']): {'available': r['available'], 'note': r['note'] or ''} for r in rows}


# ── Member: my availability ──────────────────────────────────────────────────

@bp.route('/availability/season/<int:season_id>', methods=['GET', 'POST'])
@login_required
def my_availability(season_id):
    db = get_db()
    league_id  = session['league_id']
    player_id  = session.get('player_id')

    if not player_id:
        flash('Your account is not linked to a player. Ask your admin to link it.', 'error')
        return redirect(url_for('main.dashboard'))

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    weeks = _get_weeks(db, season_id)

    if request.method == 'POST':
        if not _table_exists(db):
            flash('Availability table not yet created. Ask admin to run migrate_player_availability.py.', 'error')
            return redirect(request.url)

        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        for week_row in weeks:
            wk = week_row['week_number']
            avail_val = 1 if request.form.get(f'avail_{wk}') == '1' else 0
            note_val  = (request.form.get(f'note_{wk}') or '').strip()[:200]
            db.execute(
                """INSERT INTO player_availability
                     (player_id, league_id, season_id, week_number, available, note, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT(player_id, league_id, season_id, week_number)
                   DO UPDATE SET available=excluded.available, note=excluded.note, updated_at=excluded.updated_at""",
                (player_id, league_id, season_id, wk, avail_val, note_val, now)
            )
        db.commit()
        flash('Availability saved!', 'success')
        return redirect(url_for('availability.my_availability', season_id=season_id))

    # GET
    avail_map = {}
    if _table_exists(db):
        avail_map = _get_avail_map(db, season_id, league_id, player_ids=[player_id])

    # Build week rows for display
    week_rows = []
    for w in weeks:
        wk   = w['week_number']
        key  = (player_id, wk)
        info = avail_map.get(key, {'available': 1, 'note': ''})
        week_rows.append({
            'week_number': wk,
            'date':        w['scheduled_date'] or '',
            'available':   info['available'],
            'note':        info['note'],
        })

    # Seasons for switcher
    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id=%s ORDER BY start_date DESC",
        (league_id,)
    ).fetchall()

    return render_template('availability/my_availability.html',
                           season=season, all_seasons=all_seasons,
                           week_rows=week_rows, table_exists=_table_exists(db))


# ── Admin: full grid ─────────────────────────────────────────────────────────

@bp.route('/admin/season/<int:season_id>/availability')
@admin_required
def admin_grid(season_id):
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    weeks = _get_weeks(db, season_id)

    # All players in this season (via teams)
    players = db.execute(
        """SELECT DISTINCT p.player_id, p.first_name, p.last_name,
                  t.team_id,
                  COALESCE(t.team_name, tp1.last_name || ' / ' || tp2.last_name) AS team_label,
                  ROW_NUMBER() OVER (ORDER BY t.team_id) AS team_num
           FROM teams t
           JOIN players p  ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
           LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
           WHERE t.season_id=%s AND t.league_id=%s
           ORDER BY t.team_id, p.player_id""",
        (season_id, league_id)
    ).fetchall()

    avail_map = {}
    if _table_exists(db):
        player_ids = [p['player_id'] for p in players]
        avail_map  = _get_avail_map(db, season_id, league_id, player_ids=player_ids)

    # Build player rows
    player_rows = []
    week_numbers = [w['week_number'] for w in weeks]
    for p in players:
        pid   = p['player_id']
        cells = []
        unavail_count = 0
        for wk in week_numbers:
            info = avail_map.get((pid, wk), {'available': 1, 'note': ''})
            cells.append({'available': info['available'], 'note': info['note']})
            if not info['available']:
                unavail_count += 1
        player_rows.append({
            'player_id':     pid,
            'name':          f"{p['first_name']} {p['last_name']}",
            'team_label':    p['team_label'],
            'team_num':      p['team_num'],
            'cells':         cells,
            'unavail_count': unavail_count,
        })

    # Per-week summary: how many players marked unavailable
    week_unavail = {}
    for wk in week_numbers:
        count = sum(
            1 for p in players
            if avail_map.get((p['player_id'], wk), {'available': 1})['available'] == 0
        )
        week_unavail[wk] = count

    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id=%s ORDER BY start_date DESC",
        (league_id,)
    ).fetchall()

    return render_template('availability/admin_grid.html',
                           season=season, all_seasons=all_seasons,
                           weeks=weeks, week_numbers=week_numbers,
                           player_rows=player_rows, week_unavail=week_unavail,
                           table_exists=_table_exists(db))
