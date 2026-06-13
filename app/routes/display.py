"""
TV / Kiosk Display Mode
-----------------------
A full-screen, navigation-free scoreboard page designed for displaying
on a clubhouse TV during or after a round. Auto-refreshes every 60 s
while any matchup is still in progress, every 5 min once all are done.

Routes
  GET /display                          → redirect to current season/week
  GET /display/<season_id>              → redirect to latest interesting week
  GET /display/<season_id>/week/<n>     → kiosk view
"""

from flask import Blueprint, render_template, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required

bp = Blueprint('display', __name__, url_prefix='/display')


# ── helpers ─────────────────────────────────────────────────────────────────

def _get_season(db, season_id, league_id):
    return db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()


def _team_label(name, la, lb):
    if name:
        return name
    parts = [x for x in [la, lb] if x]
    return ' / '.join(parts) if parts else '—'


def _standings(db, season_id, week_num):
    """Cumulative standings through the given week."""
    rows = db.execute(
        """SELECT t.team_id, t.team_name,
                  COALESCE(p1.last_name, '') AS p1_last,
                  COALESCE(p2.last_name, '') AS p2_last,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts,
                  COUNT(DISTINCT CASE WHEN m.status='completed' THEN m.matchup_id END) AS rounds_played
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           LEFT JOIN matchups m  ON (m.team1_id = t.team_id OR m.team2_id = t.team_id)
               AND m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
               AND m.week_number <= %s
           LEFT JOIN match_results mr ON mr.matchup_id = m.matchup_id AND mr.team_id = t.team_id
           WHERE t.season_id = %s
           GROUP BY t.team_id
           ORDER BY total_pts DESC, t.team_name""",
        (season_id, week_num, season_id)
    ).fetchall()

    # This week's contribution per team
    week_pts_rows = db.execute(
        """SELECT mr.team_id, SUM(mr.total_points) AS week_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.week_number = %s
           GROUP BY mr.team_id""",
        (season_id, week_num)
    ).fetchall()
    wpm = {r['team_id']: (r['week_pts'] or 0) for r in week_pts_rows}

    result = []
    for i, t in enumerate(rows, 1):
        label = _team_label(t['team_name'], t['p1_last'], t['p2_last'])
        result.append({
            'rank':         i,
            'team_id':      t['team_id'],
            'label':        label,
            'total_pts':    int(t['total_pts']) if t['total_pts'] == int(t['total_pts']) else t['total_pts'],
            'week_pts':     wpm.get(t['team_id'], 0),
            'rounds_played': t['rounds_played'],
        })
    return result


def _matchup_cards(db, season_id, week_num):
    """Build per-matchup data for display cards."""
    rows = db.execute(
        """SELECT m.matchup_id, m.status, m.tee_time, m.starting_hole, m.week_type,
                  m.team1_id, m.team2_id,
                  t1.team_name AS t1_name,
                  t2.team_name AS t2_name,
                  p1a.last_name AS t1_p1_last, p1b.last_name AS t1_p2_last,
                  p1a.first_name AS t1_p1_first, p1b.first_name AS t1_p2_first,
                  p2a.last_name AS t2_p1_last, p2b.last_name AS t2_p2_last,
                  p2a.first_name AS t2_p1_first, p2b.first_name AS t2_p2_first,
                  c.course_name, te.tee_name, COALESCE(te.tee_color, te.tee_name) AS tee_color,
                  m.scheduled_date
           FROM matchups m
           LEFT JOIN teams   t1  ON m.team1_id   = t1.team_id
           LEFT JOIN teams   t2  ON m.team2_id   = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           LEFT JOIN courses c   ON m.course_id   = c.course_id
           LEFT JOIN tees    te  ON m.tee_id       = te.tee_id
           WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
           ORDER BY m.tee_time ASC NULLS LAST, m.matchup_id ASC""",
        (season_id, week_num)
    ).fetchall()

    cards = []
    for m in rows:
        card = {
            'matchup_id':    m['matchup_id'],
            'status':        m['status'],
            'tee_time':      m['tee_time'],
            'starting_hole': m['starting_hole'],
            'week_type':     m['week_type'],
            'course_name':   m['course_name'],
            'tee_name':      m['tee_name'],
            'tee_color':     m['tee_color'],
            'scheduled_date': m['scheduled_date'],
            'team1_label':   _team_label(m['t1_name'], m['t1_p1_last'], m['t1_p2_last']),
            'team2_label':   _team_label(m['t2_name'], m['t2_p1_last'], m['t2_p2_last']),
            't1_pts': None, 't2_pts': None, 'winner': None,
            'players': [],
        }

        # Player display names (First + Last initial)
        def pname(first, last):
            if first and last:
                return f"{first} {last}"
            return last or first or '?'

        card['t1_players'] = []
        card['t2_players'] = []
        if m['t1_p1_last']:
            card['t1_players'].append(pname(m['t1_p1_first'], m['t1_p1_last']))
        if m['t1_p2_last']:
            card['t1_players'].append(pname(m['t1_p2_first'], m['t1_p2_last']))
        if m['t2_p1_last']:
            card['t2_players'].append(pname(m['t2_p1_first'], m['t2_p1_last']))
        if m['t2_p2_last']:
            card['t2_players'].append(pname(m['t2_p2_first'], m['t2_p2_last']))

        if m['status'] == 'completed':
            pts_rows = db.execute(
                "SELECT team_id, SUM(total_points) AS pts FROM match_results WHERE matchup_id = %s GROUP BY team_id",
                (m['matchup_id'],)
            ).fetchall()
            team_pts = {r['team_id']: (r['pts'] or 0) for r in pts_rows}
            t1p = team_pts.get(m['team1_id'], 0)
            t2p = team_pts.get(m['team2_id'], 0)
            card['t1_pts'] = t1p
            card['t2_pts'] = t2p
            card['winner'] = 'team1' if t1p > t2p else ('team2' if t2p > t1p else 'tie')

            # Per-player line (role, pts, gross)
            round_row = db.execute(
                "SELECT round_id FROM rounds WHERE matchup_id = %s", (m['matchup_id'],)
            ).fetchone()
            gross_map = {}
            if round_row:
                sc_rows = db.execute(
                    """SELECT sc.player_id, SUM(hs.gross_score) AS total_gross
                       FROM scorecards sc
                       JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
                       WHERE sc.round_id = %s
                       GROUP BY sc.player_id""",
                    (round_row['round_id'],)
                ).fetchall()
                for sc in sc_rows:
                    gross_map[sc['player_id']] = sc['total_gross']

            mr_rows = db.execute(
                """SELECT mr.player_id, mr.team_id, mr.role,
                          mr.total_points, mr.overall_point_won,
                          p.first_name, p.last_name
                   FROM match_results mr
                   JOIN players p ON mr.player_id = p.player_id
                   WHERE mr.matchup_id = %s
                   ORDER BY mr.team_id, mr.role""",
                (m['matchup_id'],)
            ).fetchall()
            card['players'] = [
                {
                    'team_id':   r['team_id'],
                    'role':      r['role'],
                    'name':      pname(r['first_name'], r['last_name']),
                    'pts':       r['total_points'],
                    'gross':     gross_map.get(r['player_id']),
                    'win':       r['overall_point_won'] >= 1.5,
                    'tie':       0.9 <= r['overall_point_won'] < 1.5,
                }
                for r in mr_rows
            ]

        cards.append(card)

    return cards


def _current_week(db, season_id):
    """Determine the best week to show: live > latest completed > first scheduled."""
    # First, look for any in-progress or scheduled matchup from the most recent played week
    live = db.execute(
        """SELECT week_number FROM matchups
           WHERE season_id = %s AND is_bye = 0 AND status IN ('in_progress','scheduled')
           ORDER BY week_number ASC LIMIT 1""",
        (season_id,)
    ).fetchone()
    if live:
        return live['week_number']

    completed = db.execute(
        """SELECT week_number FROM matchups
           WHERE season_id = %s AND is_bye = 0 AND status = 'completed'
           ORDER BY week_number DESC LIMIT 1""",
        (season_id,)
    ).fetchone()
    if completed:
        return completed['week_number']

    # Fallback: first scheduled week
    first = db.execute(
        "SELECT week_number FROM matchups WHERE season_id = %s ORDER BY week_number LIMIT 1",
        (season_id,)
    ).fetchone()
    return first['week_number'] if first else 1


# ── routes ──────────────────────────────────────────────────────────────────

@bp.route('/')
@login_required
def current():
    db = get_db()
    league_id = session['league_id']
    row = db.execute(
        "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (league_id,)
    ).fetchone()
    if not row:
        flash('No season found.', 'warning')
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('display.season_current', season_id=row['season_id']))


@bp.route('/<int:season_id>')
@login_required
def season_current(season_id):
    db = get_db()
    league_id = session['league_id']
    season = _get_season(db, season_id, league_id)
    if not season:
        return redirect(url_for('display.current'))
    week_num = _current_week(db, season_id)
    return redirect(url_for('display.kiosk', season_id=season_id, week_num=week_num))


@bp.route('/<int:season_id>/week/<int:week_num>')
@login_required
def kiosk(season_id, week_num):
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        return redirect(url_for('display.current'))

    league = db.execute(
        "SELECT * FROM leagues WHERE league_id = %s", (league_id,)
    ).fetchone()

    # Week meta
    week_row = db.execute(
        """SELECT m.scheduled_date, m.week_type, c.course_name, te.tee_name, COALESCE(te.tee_color, te.tee_name) AS tee_color
           FROM matchups m
           LEFT JOIN courses c ON m.course_id = c.course_id
           LEFT JOIN tees    te ON m.tee_id   = te.tee_id
           WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
           ORDER BY m.matchup_id LIMIT 1""",
        (season_id, week_num)
    ).fetchone()

    week_date    = week_row['scheduled_date'] if week_row else None
    week_type    = week_row['week_type']      if week_row else None
    course_name  = week_row['course_name']    if week_row else None
    tee_name     = week_row['tee_name']       if week_row else None
    tee_color    = week_row['tee_color']      if week_row else None

    cards = _matchup_cards(db, season_id, week_num)
    standings = _standings(db, season_id, week_num)

    completed  = sum(1 for c in cards if c['status'] == 'completed')
    total      = len(cards)
    all_done   = (completed == total and total > 0)
    any_live   = any(c['status'] in ('in_progress', 'scheduled') for c in cards)

    # Commissioner note
    commissioner_note = ''
    try:
        note_row = db.execute(
            "SELECT notes FROM week_notes WHERE league_id=%s AND season_id=%s AND week_number=%s",
            (league_id, season_id, week_num)
        ).fetchone()
        if note_row:
            commissioner_note = note_row['notes']
    except Exception:
        pass

    # Prev / next week navigation
    all_weeks = db.execute(
        "SELECT DISTINCT week_number FROM matchups WHERE season_id = %s ORDER BY week_number",
        (season_id,)
    ).fetchall()
    week_nums = [r['week_number'] for r in all_weeks]
    idx       = week_nums.index(week_num) if week_num in week_nums else -1
    prev_week = week_nums[idx - 1] if idx > 0 else None
    next_week = week_nums[idx + 1] if idx >= 0 and idx < len(week_nums) - 1 else None

    # Refresh interval: 60 s if live, 300 s if all done
    refresh_secs = 60 if any_live else (300 if not all_done else 300)

    return render_template(
        'display/kiosk.html',
        league=league,
        season=season,
        week_num=week_num,
        week_date=week_date,
        week_type=week_type,
        course_name=course_name,
        tee_name=tee_name,
        tee_color=tee_color,
        cards=cards,
        standings=standings,
        completed=completed,
        total=total,
        all_done=all_done,
        any_live=any_live,
        commissioner_note=commissioner_note,
        prev_week=prev_week,
        next_week=next_week,
        refresh_secs=refresh_secs,
        season_id=season_id,
    )
