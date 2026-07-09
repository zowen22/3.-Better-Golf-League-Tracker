"""
Public League Page — no authentication required.
Leagues can enable a public URL at /public/<slug> to show standings + schedule.
Admin settings at /admin/public-page.
"""
import re
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required

bp = Blueprint('public_view', __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text):
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def _get_league_by_slug(db, slug):
    return db.execute(
        "SELECT * FROM leagues WHERE public_slug = %s AND public_enabled = 1",
        (slug,)
    ).fetchone()


def _current_season(db, league_id):
    return db.execute(
        """SELECT * FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1""",
        (league_id,)
    ).fetchone()


def _standings(db, season_id, league_id):
    rows = db.execute(
        """SELECT t.team_id,
                  p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.first_name AS p2_first, p2.last_name AS p2_last,
                  t.team_name AS nickname,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts,
                  COUNT(DISTINCT CASE WHEN m.status='completed' AND (m.is_bye IS NULL OR m.is_bye=0) THEN m.matchup_id END) AS rounds_played
           FROM teams t
           LEFT JOIN players p1       ON t.player1_id  = p1.player_id
           LEFT JOIN players p2       ON t.player2_id  = p2.player_id
           LEFT JOIN match_results mr ON mr.team_id    = t.team_id
           LEFT JOIN matchups m       ON mr.matchup_id = m.matchup_id
                                     AND m.season_id   = %s
           WHERE t.season_id = %s AND t.league_id = %s
           GROUP BY t.team_id, t.team_name, p1.first_name, p1.last_name, p2.first_name, p2.last_name
           ORDER BY total_pts DESC""",
        (season_id, season_id, league_id)
    ).fetchall()
    standings = []
    prev_pts, pos = None, 0
    for i, r in enumerate(rows):
        if r['total_pts'] != prev_pts:
            pos = i + 1
            prev_pts = r['total_pts']
        label = r['nickname'] or f"{r['p1_last'] or '?'} / {r['p2_last'] or '?'}"
        standings.append({'pos': pos, 'label': label, 'total_pts': r['total_pts'], 'rounds': r['rounds_played']})
    return standings


def _upcoming_weeks(db, season_id, league_id, limit=3):
    """Return the next N unplayed weeks with their matchups."""
    weeks_raw = db.execute(
        """SELECT DISTINCT m.week_number, m.scheduled_date, m.week_type
           FROM matchups m
           WHERE m.season_id = %s AND m.status != 'completed'
             AND (m.is_bye IS NULL OR m.is_bye = 0)
           ORDER BY m.week_number
           LIMIT %s""",
        (season_id, limit)
    ).fetchall()

    result = []
    for wk in weeks_raw:
        matchups = db.execute(
            """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                      m.tee_time, m.starting_hole, m.week_type,
                      t1.team_id AS t1_id, t2.team_id AS t2_id,
                      p1a.last_name AS t1_p1_last, p1b.last_name AS t1_p2_last,
                      t1.team_name AS t1_nick,
                      p2a.last_name AS t2_p1_last, p2b.last_name AS t2_p2_last,
                      t2.team_name AS t2_nick,
                      m.is_bye, m.bye_team_id
               FROM matchups m
               LEFT JOIN teams t1   ON m.team1_id = t1.team_id
               LEFT JOIN teams t2   ON m.team2_id = t2.team_id
               LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
               LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
               LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
               LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
               WHERE m.season_id = %s AND m.week_number = %s
               ORDER BY m.matchup_id""",
            (season_id, wk['week_number'])
        ).fetchall()

        week_matchups = []
        for mu in matchups:
            if mu['is_bye']:
                continue
            t1 = mu['t1_nick'] or f"{mu['t1_p1_last'] or '?'} / {mu['t1_p2_last'] or '?'}"
            t2 = mu['t2_nick'] or f"{mu['t2_p1_last'] or '?'} / {mu['t2_p2_last'] or '?'}"
            week_matchups.append({'home': t1, 'away': t2, 'tee_time': mu['tee_time']})

        result.append({
            'week_number': wk['week_number'],
            'scheduled_date': wk['scheduled_date'],
            'week_type': wk['week_type'] or 'Normal',
            'matchups': week_matchups,
        })
    return result


def _recent_results(db, season_id, league_id):
    """Return the most recently completed week's matchup results."""
    last_week = db.execute(
        """SELECT MAX(week_number) AS wk FROM matchups
           WHERE season_id = %s AND status = 'completed'""",
        (season_id,)
    ).fetchone()
    if not last_week or not last_week['wk']:
        return None, []

    wk = last_week['wk']
    week_info = db.execute(
        "SELECT scheduled_date, week_type FROM matchups WHERE season_id = %s AND week_number = %s LIMIT 1",
        (season_id, wk)
    ).fetchone()

    matchups = db.execute(
        """SELECT m.matchup_id,
                  t1.team_id AS t1_id, t2.team_id AS t2_id,
                  p1a.last_name AS t1_p1_last, p1b.last_name AS t1_p2_last,
                  t1.team_name AS t1_nick,
                  p2a.last_name AS t2_p1_last, p2b.last_name AS t2_p2_last,
                  t2.team_name AS t2_nick,
                  COALESCE(mr1.total_points, 0) AS t1_pts,
                  COALESCE(mr2.total_points, 0) AS t2_pts
           FROM matchups m
           LEFT JOIN teams t1   ON m.team1_id = t1.team_id
           LEFT JOIN teams t2   ON m.team2_id = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           LEFT JOIN (SELECT matchup_id, SUM(total_points) AS total_points
                      FROM match_results GROUP BY matchup_id) mr1
                  ON m.matchup_id = mr1.matchup_id AND m.team1_id = (
                      SELECT team_id FROM match_results WHERE matchup_id = m.matchup_id LIMIT 1)
           LEFT JOIN (SELECT matchup_id, SUM(total_points) AS total_points, team_id
                      FROM match_results GROUP BY matchup_id) mr2
                  ON m.matchup_id = mr2.matchup_id AND m.team2_id = mr2.team_id
           WHERE m.season_id = %s AND m.week_number = %s AND m.status = 'completed'
             AND (m.is_bye IS NULL OR m.is_bye = 0)
           ORDER BY m.matchup_id""",
        (season_id, wk)
    ).fetchall()

    # Simpler approach: get pts per team per matchup from match_results directly
    matchup_ids = db.execute(
        "SELECT matchup_id, team1_id, team2_id FROM matchups WHERE season_id=%s AND week_number=%s AND status='completed' AND (is_bye IS NULL OR is_bye=0)",
        (season_id, wk)
    ).fetchall()

    results = []
    for mu in matchup_ids:
        t1_row = db.execute("SELECT * FROM teams WHERE team_id=%s", (mu['team1_id'],)).fetchone()
        t2_row = db.execute("SELECT * FROM teams WHERE team_id=%s", (mu['team2_id'],)).fetchone()
        if not t1_row or not t2_row:
            continue

        def team_label(t):
            if t['team_name']:
                return t['team_name']
            p1 = db.execute("SELECT last_name FROM players WHERE player_id=%s", (t['player1_id'],)).fetchone()
            p2 = db.execute("SELECT last_name FROM players WHERE player_id=%s", (t['player2_id'],)).fetchone() if t['player2_id'] else None
            return f"{p1['last_name'] if p1 else '?'} / {p2['last_name'] if p2 else '?'}"

        t1_pts_row = db.execute(
            "SELECT COALESCE(SUM(total_points),0) AS pts FROM match_results WHERE matchup_id=%s AND team_id=%s",
            (mu['matchup_id'], mu['team1_id'])
        ).fetchone()
        t2_pts_row = db.execute(
            "SELECT COALESCE(SUM(total_points),0) AS pts FROM match_results WHERE matchup_id=%s AND team_id=%s",
            (mu['matchup_id'], mu['team2_id'])
        ).fetchone()

        t1_pts = float(t1_pts_row['pts']) if t1_pts_row else 0
        t2_pts = float(t2_pts_row['pts']) if t2_pts_row else 0

        results.append({
            'home': team_label(t1_row),
            'away': team_label(t2_row),
            't1_pts': t1_pts,
            't2_pts': t2_pts,
            'winner': 'home' if t1_pts > t2_pts else ('away' if t2_pts > t1_pts else 'tie'),
        })

    return {'week_number': wk, 'date': week_info['scheduled_date'] if week_info else None}, results


# ---------------------------------------------------------------------------
# Public page
# ---------------------------------------------------------------------------

@bp.route('/public/<slug>')
def public_page(slug):
    db = get_db()
    league = _get_league_by_slug(db, slug)
    if not league:
        return render_template('public/not_found.html'), 404

    league_id = league['league_id']
    season = _current_season(db, league_id)
    if not season:
        return render_template('public/not_found.html'), 404

    season_id = season['season_id']
    standings = _standings(db, season_id, league_id)
    upcoming  = _upcoming_weeks(db, season_id, league_id)
    recent_wk, recent_results = _recent_results(db, season_id, league_id)

    return render_template('public/index.html',
                           league=league,
                           season=season,
                           standings=standings,
                           upcoming=upcoming,
                           recent_wk=recent_wk,
                           recent_results=recent_results)


# ---------------------------------------------------------------------------
# Admin: Public Page settings
# ---------------------------------------------------------------------------

@bp.route('/admin/public-page', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    db = get_db()
    league_id = session['league_id']
    league = db.execute("SELECT * FROM leagues WHERE league_id=%s", (league_id,)).fetchone()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save':
            enabled = 1 if request.form.get('public_enabled') else 0
            slug = request.form.get('public_slug', '').strip()
            # Auto-slugify
            slug = _slugify(slug) if slug else _slugify(league['league_name'])
            # Ensure uniqueness (allow same league to keep its own slug)
            conflict = db.execute(
                "SELECT league_id FROM leagues WHERE public_slug=%s AND league_id!=%s",
                (slug, league_id)
            ).fetchone()
            if conflict:
                flash('That URL slug is already taken by another league. Please choose a different one.', 'error')
            else:
                db.execute(
                    "UPDATE leagues SET public_enabled=%s, public_slug=%s WHERE league_id=%s",
                    (enabled, slug, league_id)
                )
                db.commit()
                flash('Public page settings saved.', 'success')
                return redirect(url_for('public_view.admin_settings'))
        elif action == 'disable':
            db.execute("UPDATE leagues SET public_enabled=0 WHERE league_id=%s", (league_id,))
            db.commit()
            flash('Public page disabled.', 'success')
            return redirect(url_for('public_view.admin_settings'))

    # Reload after possible commit
    league = db.execute("SELECT * FROM leagues WHERE league_id=%s", (league_id,)).fetchone()
    base_url = request.host_url.rstrip('/')
    public_url = f"{base_url}/public/{league['public_slug']}" if league['public_slug'] else None

    return render_template('public/admin_settings.html',
                           league=league,
                           public_url=public_url,
                           base_url=base_url)
