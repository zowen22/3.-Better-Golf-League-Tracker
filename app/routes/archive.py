"""
Archive blueprint — browse past seasons, control member visibility.
/archive/                              list accessible seasons
/archive/<season_id>                   archived season summary
/archive/<season_id>/settings          admin: toggle visible_to_members + locked (POST)
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required

bp = Blueprint('archive', __name__, url_prefix='/archive')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_archive_settings(db, season_id, league_id):
    """Return archive_settings row (or None) for a season."""
    return db.execute(
        "SELECT * FROM archive_settings WHERE season_id = ? AND league_id = ?",
        (season_id, league_id)
    ).fetchone()


def _upsert_archive_settings(db, season_id, league_id, visible_to_members, locked):
    """Insert or update archive_settings row."""
    existing = _get_archive_settings(db, season_id, league_id)
    if existing:
        db.execute(
            """UPDATE archive_settings
               SET visible_to_members = ?, locked = ?
               WHERE season_id = ? AND league_id = ?""",
            (visible_to_members, locked, season_id, league_id)
        )
    else:
        db.execute(
            """INSERT INTO archive_settings (league_id, season_id, visible_to_members, locked)
               VALUES (?, ?, ?, ?)""",
            (league_id, season_id, visible_to_members, locked)
        )
    db.commit()


def _season_stats(db, season_id):
    """Return a dict with high-level stats for a season."""
    rounds_played = db.execute(
        """SELECT COUNT(*) as cnt FROM matchups
           WHERE season_id = ? AND status = 'completed' AND (is_bye IS NULL OR is_bye = 0)""",
        (season_id,)
    ).fetchone()['cnt']

    teams_count = db.execute(
        "SELECT COUNT(*) as cnt FROM teams WHERE season_id = ?",
        (season_id,)
    ).fetchone()['cnt']

    # Top team by total points from match_results
    top_team = db.execute(
        """SELECT t.team_name,
                  COALESCE(p1.first_name || ' ' || p1.last_name, '') AS p1_name,
                  COALESCE(p2.first_name || ' ' || p2.last_name, '') AS p2_name,
                  SUM(mr.total_points) AS total_pts
           FROM match_results mr
           JOIN teams t ON mr.team_id = t.team_id
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE m.season_id = ?
           GROUP BY mr.team_id
           ORDER BY total_pts DESC
           LIMIT 1""",
        (season_id,)
    ).fetchone()

    return {
        'rounds_played': rounds_played,
        'teams_count': teams_count,
        'top_team': top_team,
    }


def _final_standings(db, season_id):
    """Return standings rows for archived season view."""
    rows = db.execute(
        """SELECT t.team_id, t.team_name, t.division_name,
                  COALESCE(p1.first_name || ' ' || p1.last_name, 'TBD') AS p1_name,
                  COALESCE(p2.first_name || ' ' || p2.last_name, 'TBD') AS p2_name,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts,
                  COUNT(DISTINCT CASE WHEN mr.total_points > 0 THEN m.matchup_id END) AS rounds_with_pts
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           LEFT JOIN match_results mr ON mr.team_id = t.team_id
           LEFT JOIN matchups m ON mr.matchup_id = m.matchup_id AND m.season_id = ?
           WHERE t.season_id = ?
           GROUP BY t.team_id
           ORDER BY total_pts DESC""",
        (season_id, season_id)
    ).fetchall()
    return rows


# ---------------------------------------------------------------------------
# Archive list — accessible seasons
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def index():
    db = get_db()
    league_id = session['league_id']
    is_admin = session.get('role') == 'league_admin'

    all_seasons = db.execute(
        "SELECT * FROM seasons WHERE league_id = ? ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()

    # Build enriched list with archive settings attached
    result = []
    for s in all_seasons:
        arc = _get_archive_settings(db, s['season_id'], league_id)
        visible = arc['visible_to_members'] if arc else 0
        locked  = arc['locked']             if arc else 0
        archived = arc is not None

        # Members only see archived + visible seasons
        if not is_admin and not (archived and visible):
            continue

        stats = _season_stats(db, s['season_id'])
        result.append({
            'season_id':   s['season_id'],
            'season_name': s['season_name'],
            'start_date':  s['start_date'],
            'end_date':    s['end_date'],
            'archived':    archived,
            'visible':     visible,
            'locked':      locked,
            'rounds_played': stats['rounds_played'],
            'teams_count':   stats['teams_count'],
            'top_team':      stats['top_team'],
        })

    return render_template('archive/list.html',
                           seasons=result, is_admin=is_admin)


# ---------------------------------------------------------------------------
# Archived season summary
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>')
@login_required
def season_detail(season_id):
    db = get_db()
    league_id = session['league_id']
    is_admin = session.get('role') == 'league_admin'

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = ? AND league_id = ?",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('archive.index'))

    arc = _get_archive_settings(db, season_id, league_id)

    # Members can only view seasons that are archived + visible
    if not is_admin:
        if not arc or not arc['visible_to_members']:
            flash('This season is not available for viewing.', 'error')
            return redirect(url_for('archive.index'))

    stats = _season_stats(db, season_id)
    standings = _final_standings(db, season_id)

    visible = arc['visible_to_members'] if arc else 0
    locked  = arc['locked']             if arc else 0
    archived = arc is not None

    return render_template('archive/season.html',
                           season=season,
                           archived=archived,
                           visible=visible,
                           locked=locked,
                           stats=stats,
                           standings=standings,
                           is_admin=is_admin)


# ---------------------------------------------------------------------------
# Admin: update archive settings for a season
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/settings', methods=['POST'])
@admin_required
def update_settings(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT season_id FROM seasons WHERE season_id = ? AND league_id = ?",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('archive.index'))

    action = request.form.get('action', '')

    if action == 'archive':
        visible = 1 if request.form.get('visible_to_members') == '1' else 0
        locked  = 1 if request.form.get('locked') == '1' else 0
        _upsert_archive_settings(db, season_id, league_id, visible, locked)
        flash('Archive settings saved.', 'success')

    elif action == 'unarchive':
        db.execute(
            "DELETE FROM archive_settings WHERE season_id = ? AND league_id = ?",
            (season_id, league_id)
        )
        db.commit()
        flash('Season removed from archive.', 'success')

    elif action == 'toggle_visible':
        arc = _get_archive_settings(db, season_id, league_id)
        if arc:
            new_val = 0 if arc['visible_to_members'] else 1
            locked = arc['locked']
        else:
            new_val = 1
            locked = 1
        _upsert_archive_settings(db, season_id, league_id, new_val, locked)
        state = 'visible to members' if new_val else 'hidden from members'
        flash(f'Season is now {state}.', 'success')

    elif action == 'toggle_locked':
        arc = _get_archive_settings(db, season_id, league_id)
        if arc:
            new_val = 0 if arc['locked'] else 1
            visible = arc['visible_to_members']
        else:
            new_val = 1
            visible = 1
        _upsert_archive_settings(db, season_id, league_id, visible, new_val)
        state = 'locked' if new_val else 'unlocked'
        flash(f'Season is now {state}.', 'success')

    # Redirect back: prefer coming from archive detail, fall back to index
    next_url = request.form.get('next') or url_for('archive.index')
    return redirect(next_url)
