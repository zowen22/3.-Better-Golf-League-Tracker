"""
REST API v1 — BetterGolfLeagueTracker
Auth: X-Api-Key header  OR  ?api_key=<key> query param
All responses: JSON  (Content-Type: application/json)

Endpoints:
  GET /api/v1/leagues/me                            league info
  GET /api/v1/seasons                               list seasons
  GET /api/v1/seasons/<id>/standings                team standings
  GET /api/v1/seasons/<id>/schedule                 full schedule
  GET /api/v1/seasons/<id>/teams                    teams + players
  GET /api/v1/players                               player roster
  GET /api/v1/matchups/<id>/scores                  scorecard detail
  GET /api/v1/seasons/<id>/weeks/<n>/live           live leaderboard
  POST /api/v1/keys/regenerate                      rotate API key (admin)
"""
import secrets
import functools
from flask import Blueprint, jsonify, request, g
from werkzeug.security import check_password_hash
from database import get_db
from jwt_utils import create_token, decode_token, require_jwt, require_jwt_admin
import jwt as pyjwt
from datetime import datetime, timezone, timedelta

bp = Blueprint('api', __name__, url_prefix='/api/v1')


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_api_key():
    """Extract API key from header or query string."""
    key = request.headers.get('X-Api-Key') or request.args.get('api_key')
    return (key or '').strip()


def _resolve_league(db, api_key):
    """Return the league row that owns this api_key, or None."""
    if not api_key:
        return None
    return db.execute(
        "SELECT * FROM leagues WHERE api_key = %s AND active = 1",
        (api_key,)
    ).fetchone()


def _err(msg, code=400):
    return jsonify({'error': msg}), code


def api_key_required(f):
    """Decorator: resolve league from API key; store as g.api_league."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        db = get_db()
        key = _get_api_key()
        league = _resolve_league(db, key)
        if not league:
            return _err('Invalid or missing API key.', 401)
        g.api_league = league
        g.api_league_id = league['league_id']
        return f(*args, **kwargs)
    return wrapper


def _season_for_league(db, season_id, league_id):
    return db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()


# ---------------------------------------------------------------------------
# /leagues/me
# ---------------------------------------------------------------------------

@bp.route('/leagues/me')
@api_key_required
def league_me():
    league = g.api_league
    db = get_db()
    seasons = db.execute(
        "SELECT season_id, season_name, start_date, end_date FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (g.api_league_id,)
    ).fetchall()
    return jsonify({
        'league_id':   league['league_id'],
        'league_name': league['league_name'],
        'seasons':     [dict(s) for s in seasons],
    })


# ---------------------------------------------------------------------------
# /seasons
# ---------------------------------------------------------------------------

@bp.route('/seasons')
@api_key_required
def seasons_list():
    db = get_db()
    rows = db.execute(
        "SELECT season_id, season_name, start_date, end_date FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (g.api_league_id,)
    ).fetchall()
    return jsonify({'seasons': [dict(r) for r in rows]})


# ---------------------------------------------------------------------------
# /seasons/<id>/standings
# ---------------------------------------------------------------------------

@bp.route('/seasons/<int:season_id>/standings')
@api_key_required
def season_standings(season_id):
    db = get_db()
    season = _season_for_league(db, season_id, g.api_league_id)
    if not season:
        return _err('Season not found.', 404)

    rows = db.execute(
        """
        SELECT
            t.team_id,
            t.team_name,
            p1.first_name || ' ' || p1.last_name AS p1_name,
            p2.first_name || ' ' || p2.last_name AS p2_name,
            COALESCE(SUM(mr.total_points), 0) AS total_points,
            COUNT(DISTINCT mr.matchup_id) AS rounds_played
        FROM teams t
        JOIN players p1 ON p1.player_id = t.player1_id
        JOIN players p2 ON p2.player_id = t.player2_id
        LEFT JOIN match_results mr ON mr.team_id = t.team_id AND mr.season_id = %s
        WHERE t.season_id = %s
        GROUP BY t.team_id
        ORDER BY total_points DESC, rounds_played ASC
        """,
        (season_id, season_id)
    ).fetchall()

    standings = []
    for i, r in enumerate(rows, 1):
        team_label = r['team_name'] if r['team_name'] else f"{r['p1_name']} / {r['p2_name']}"
        standings.append({
            'rank':          i,
            'team_id':       r['team_id'],
            'team_label':    team_label,
            'p1_name':       r['p1_name'],
            'p2_name':       r['p2_name'],
            'total_points':  round(float(r['total_points']), 1),
            'rounds_played': r['rounds_played'],
        })

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'standings':   standings,
    })


# ---------------------------------------------------------------------------
# /seasons/<id>/schedule
# ---------------------------------------------------------------------------

@bp.route('/seasons/<int:season_id>/schedule')
@api_key_required
def season_schedule(season_id):
    db = get_db()
    season = _season_for_league(db, season_id, g.api_league_id)
    if not season:
        return _err('Season not found.', 404)

    matchups = db.execute(
        """
        SELECT
            m.matchup_id, m.week_number, m.scheduled_date, m.status,
            m.tee_time, m.starting_hole, m.week_type,
            c.course_name,
            ht.team_name AS home_team_name,
            hp1.first_name || ' ' || hp1.last_name AS home_p1,
            hp2.first_name || ' ' || hp2.last_name AS home_p2,
            at2.team_name AS away_team_name,
            ap1.first_name || ' ' || ap1.last_name AS away_p1,
            ap2.first_name || ' ' || ap2.last_name AS away_p2,
            ht.team_id AS home_team_id,
            at2.team_id AS away_team_id
        FROM matchups m
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN players hp1 ON hp1.player_id = ht.player1_id
        JOIN players hp2 ON hp2.player_id = ht.player2_id
        JOIN teams at2 ON at2.team_id = m.away_team_id
        JOIN players ap1 ON ap1.player_id = at2.player1_id
        JOIN players ap2 ON ap2.player_id = at2.player2_id
        LEFT JOIN courses c ON c.course_id = m.course_id
        WHERE m.season_id = %s
        ORDER BY m.week_number, m.tee_time NULLS LAST, m.matchup_id
        """,
        (season_id,)
    ).fetchall()

    # Group by week
    weeks = {}
    for r in matchups:
        wn = r['week_number']
        if wn not in weeks:
            weeks[wn] = {
                'week_number':    wn,
                'scheduled_date': r['scheduled_date'],
                'week_type':      r['week_type'] or 'Normal',
                'course_name':    r['course_name'],
                'matchups':       [],
            }
        home_label = r['home_team_name'] or f"{r['home_p1']} / {r['home_p2']}"
        away_label = r['away_team_name'] or f"{r['away_p1']} / {r['away_p2']}"
        weeks[wn]['matchups'].append({
            'matchup_id':  r['matchup_id'],
            'status':      r['status'],
            'tee_time':    r['tee_time'],
            'starting_hole': r['starting_hole'],
            'home_team_id':    r['home_team_id'],
            'home_team_label': home_label,
            'away_team_id':    r['away_team_id'],
            'away_team_label': away_label,
        })

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'weeks':       list(weeks.values()),
    })


# ---------------------------------------------------------------------------
# /seasons/<id>/teams
# ---------------------------------------------------------------------------

@bp.route('/seasons/<int:season_id>/teams')
@api_key_required
def season_teams(season_id):
    db = get_db()
    season = _season_for_league(db, season_id, g.api_league_id)
    if not season:
        return _err('Season not found.', 404)

    rows = db.execute(
        """
        SELECT
            t.team_id, t.team_name, t.division_name,
            p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
            p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
        FROM teams t
        JOIN players p1 ON p1.player_id = t.player1_id
        JOIN players p2 ON p2.player_id = t.player2_id
        WHERE t.season_id = %s
        ORDER BY t.team_id
        """,
        (season_id,)
    ).fetchall()

    teams = []
    for r in rows:
        teams.append({
            'team_id':    r['team_id'],
            'team_name':  r['team_name'],
            'division':   r['division_name'],
            'players': [
                {'player_id': r['p1_id'], 'name': f"{r['p1_first']} {r['p1_last']}"},
                {'player_id': r['p2_id'], 'name': f"{r['p2_first']} {r['p2_last']}"},
            ],
        })

    return jsonify({'season_id': season_id, 'teams': teams})


# ---------------------------------------------------------------------------
# /players
# ---------------------------------------------------------------------------

@bp.route('/players')
@api_key_required
def players_list():
    db = get_db()
    rows = db.execute(
        """SELECT player_id, first_name, last_name, email, active,
                  handicap_index, starting_handicap
           FROM players WHERE league_id = %s
           ORDER BY last_name, first_name""",
        (g.api_league_id,)
    ).fetchall()

    players = []
    for r in rows:
        players.append({
            'player_id':         r['player_id'],
            'name':              f"{r['first_name']} {r['last_name']}",
            'first_name':        r['first_name'],
            'last_name':         r['last_name'],
            'email':             r['email'],
            'active':            bool(r['active']),
            'handicap_index':    r['handicap_index'],
            'starting_handicap': r['starting_handicap'],
        })

    return jsonify({'players': players})


# ---------------------------------------------------------------------------
# /matchups/<id>/scores
# ---------------------------------------------------------------------------

@bp.route('/matchups/<int:matchup_id>/scores')
@api_key_required
def matchup_scores(matchup_id):
    db = get_db()
    matchup = db.execute(
        """SELECT m.*, s.season_id,
                  c.course_name,
                  ht.team_name AS home_name,
                  at2.team_name AS away_name
           FROM matchups m
           JOIN seasons s ON s.season_id = m.season_id
           LEFT JOIN courses c ON c.course_id = m.course_id
           JOIN teams ht ON ht.team_id = m.home_team_id
           JOIN teams at2 ON at2.team_id = m.away_team_id
           WHERE m.matchup_id = %s AND s.league_id = %s""",
        (matchup_id, g.api_league_id)
    ).fetchone()
    if not matchup:
        return _err('Matchup not found.', 404)

    scorecards = db.execute(
        """SELECT sc.scorecard_id, sc.player_id, sc.team_id, sc.is_sub,
                  p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name
           FROM scorecards sc
           JOIN players p ON p.player_id = sc.player_id
           JOIN teams t ON t.team_id = sc.team_id
           WHERE sc.matchup_id = %s
           ORDER BY sc.team_id, sc.player_id""",
        (matchup_id,)
    ).fetchall()

    players_data = []
    for sc in scorecards:
        holes = db.execute(
            """SELECT hs.hole_number, hs.gross_score, hs.net_score,
                      hs.score_differential, hs.hole_points_won,
                      h.par
               FROM hole_scores hs
               LEFT JOIN holes h ON h.hole_id = hs.hole_id
               WHERE hs.scorecard_id = %s
               ORDER BY hs.hole_number""",
            (sc['scorecard_id'],)
        ).fetchall()

        mr = db.execute(
            """SELECT total_points, overall_point_won, hole_points_won
               FROM match_results WHERE scorecard_id = %s""",
            (sc['scorecard_id'],)
        ).fetchone()

        players_data.append({
            'player_id':    sc['player_id'],
            'player_name':  sc['player_name'],
            'team_id':      sc['team_id'],
            'team_name':    sc['team_name'],
            'is_sub':       bool(sc['is_sub']),
            'total_points': float(mr['total_points']) if mr else None,
            'overall_point_won': float(mr['overall_point_won']) if mr else None,
            'holes': [
                {
                    'hole_number':       h['hole_number'],
                    'par':               h['par'],
                    'gross_score':       h['gross_score'],
                    'net_score':         h['net_score'],
                    'score_differential':h['score_differential'],
                    'hole_points_won':   float(h['hole_points_won']) if h['hole_points_won'] is not None else None,
                }
                for h in holes
            ],
        })

    return jsonify({
        'matchup_id':     matchup_id,
        'week_number':    matchup['week_number'],
        'scheduled_date': matchup['scheduled_date'],
        'status':         matchup['status'],
        'course_name':    matchup['course_name'],
        'players':        players_data,
    })


# ---------------------------------------------------------------------------
# /seasons/<id>/weeks/<n>/live
# ---------------------------------------------------------------------------

@bp.route('/seasons/<int:season_id>/weeks/<int:week_num>/live')
@api_key_required
def week_live(season_id, week_num):
    db = get_db()
    season = _season_for_league(db, season_id, g.api_league_id)
    if not season:
        return _err('Season not found.', 404)

    matchups = db.execute(
        """
        SELECT m.matchup_id, m.status, m.tee_time, m.starting_hole,
               ht.team_id AS home_team_id, ht.team_name AS home_name,
               hp1.first_name || ' ' || hp1.last_name AS home_p1,
               hp2.first_name || ' ' || hp2.last_name AS home_p2,
               at2.team_id AS away_team_id, at2.team_name AS away_name,
               ap1.first_name || ' ' || ap1.last_name AS away_p1,
               ap2.first_name || ' ' || ap2.last_name AS away_p2
        FROM matchups m
        JOIN teams ht ON ht.team_id = m.home_team_id
        JOIN players hp1 ON hp1.player_id = ht.player1_id
        JOIN players hp2 ON hp2.player_id = ht.player2_id
        JOIN teams at2 ON at2.team_id = m.away_team_id
        JOIN players ap1 ON ap1.player_id = at2.player1_id
        JOIN players ap2 ON ap2.player_id = at2.player2_id
        WHERE m.season_id = %s AND m.week_number = %s
        ORDER BY m.tee_time NULLS LAST, m.matchup_id
        """,
        (season_id, week_num)
    ).fetchall()

    result_matchups = []
    for m in matchups:
        pts = db.execute(
            """SELECT sc.team_id, SUM(mr.total_points) AS pts
               FROM match_results mr JOIN scorecards sc ON sc.scorecard_id = mr.scorecard_id
               WHERE sc.matchup_id = %s GROUP BY sc.team_id""",
            (m['matchup_id'],)
        ).fetchall()
        pts_map = {r['team_id']: float(r['pts']) for r in pts}

        home_label = m['home_name'] or f"{m['home_p1']} / {m['home_p2']}"
        away_label = m['away_name'] or f"{m['away_p1']} / {m['away_p2']}"

        result_matchups.append({
            'matchup_id':   m['matchup_id'],
            'status':       m['status'],
            'tee_time':     m['tee_time'],
            'starting_hole':m['starting_hole'],
            'home_team_id':    m['home_team_id'],
            'home_team_label': home_label,
            'home_pts':        pts_map.get(m['home_team_id']),
            'away_team_id':    m['away_team_id'],
            'away_team_label': away_label,
            'away_pts':        pts_map.get(m['away_team_id']),
        })

    all_complete = all(m['status'] == 'completed' for m in matchups) if matchups else False

    return jsonify({
        'season_id':    season_id,
        'week_number':  week_num,
        'all_complete': all_complete,
        'matchups':     result_matchups,
    })


# ---------------------------------------------------------------------------
# /keys/regenerate  (POST — admin action)
# ---------------------------------------------------------------------------

@bp.route('/keys/regenerate', methods=['POST'])
@api_key_required
def regenerate_key():
    """Generate a new API key for this league. Old key immediately invalidated."""
    new_key = 'bglk_' + secrets.token_urlsafe(32)
    db = get_db()
    db.execute("UPDATE leagues SET api_key = %s WHERE league_id = %s",
               (new_key, g.api_league_id))
    db.commit()
    return jsonify({'api_key': new_key, 'message': 'API key rotated. Update your integrations.'})


# ===========================================================================
# JWT Auth Endpoints  (WP0.1)
# ===========================================================================

def _current_season(db, league_id):
    """Return the most recent active season for a league, or None."""
    return db.execute(
        """SELECT season_id, season_name FROM seasons
           WHERE league_id = %s ORDER BY season_id DESC LIMIT 1""",
        (league_id,)
    ).fetchone()


@bp.route('/auth/login', methods=['POST'])
def auth_login():
    """
    POST {email, password, league_code}
    Returns {token, user_id, league_id, role, player_id, display_name, current_season_id}
    """
    data = request.get_json(force=True, silent=True) or {}
    email       = (data.get('email') or '').strip().lower()
    password    = data.get('password', '')
    league_code = (data.get('league_code') or '').strip()

    if not email or not password or not league_code:
        return _err('email, password, and league_code are required.', 400)

    db = get_db()

    # Validate league
    league = db.execute(
        "SELECT league_id, league_name FROM leagues WHERE login_code = %s AND active = 1",
        (league_code,)
    ).fetchone()
    if not league:
        return _err('League not found.', 404)

    # Validate user
    user = db.execute(
        "SELECT * FROM users WHERE LOWER(email) = %s AND active = 1",
        (email,)
    ).fetchone()
    if not user or not check_password_hash(user['password_hash'] or '', password):
        return _err('Invalid email or password.', 401)

    # Validate user has a role in this league
    ulr = db.execute(
        """SELECT ulr.role_id, r.role_name
           FROM user_league_roles ulr
           JOIN roles r ON r.role_id = ulr.role_id
           WHERE ulr.user_id = %s AND ulr.league_id = %s""",
        (user['user_id'], league['league_id'])
    ).fetchone()
    if not ulr:
        return _err('Your account is not a member of this league.', 403)

    # Get linked player (optional)
    player = db.execute(
        "SELECT player_id FROM players WHERE user_id = %s AND league_id = %s",
        (user['user_id'], league['league_id'])
    ).fetchone()
    player_id = player['player_id'] if player else None

    season = _current_season(db, league['league_id'])

    token = create_token(
        user_id=user['user_id'],
        league_id=league['league_id'],
        role=ulr['role_name'],
        player_id=player_id,
    )

    return jsonify({
        'token':             token,
        'user_id':           user['user_id'],
        'league_id':         league['league_id'],
        'league_name':       league['league_name'],
        'role':              ulr['role_name'],
        'player_id':         player_id,
        'display_name':      f"{user['first_name']} {user['last_name']}",
        'current_season_id': season['season_id'] if season else None,
    })


@bp.route('/auth/refresh', methods=['POST'])
def auth_refresh():
    """
    POST Authorization: Bearer <expiring-token>
    Accepts tokens expired within the 7-day grace window; returns a fresh token.
    """
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return _err('Missing Authorization header.', 401)
    token = auth[len('Bearer '):]
    try:
        payload = decode_token(token, allow_expired=True)
    except pyjwt.PyJWTError:
        return _err('Invalid token.', 401)

    # Enforce 7-day grace window
    exp = payload.get('exp', 0)
    grace_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    if datetime.fromtimestamp(exp, tz=timezone.utc) < grace_cutoff:
        return _err('Token too old to refresh. Please log in again.', 401)

    new_token = create_token(
        user_id=payload['sub'],
        league_id=payload['league_id'],
        role=payload.get('role'),
        player_id=payload.get('player_id'),
    )
    return jsonify({'token': new_token})


@bp.route('/auth/me')
@require_jwt
def auth_me():
    """GET — returns current user profile from JWT (no DB hit)."""
    return jsonify({
        'user_id':   g.jwt_user_id,
        'league_id': g.jwt_league_id,
        'role':      g.jwt_role,
        'player_id': g.jwt_player_id,
    })


# ===========================================================================
# iOS Read Endpoints  (WP0.2) — JWT-protected, "current season" auto-detected
# ===========================================================================

@bp.route('/schedule')
@require_jwt
def mobile_schedule():
    """Current season schedule for the JWT's league."""
    db = get_db()
    season = _current_season(db, g.jwt_league_id)
    if not season:
        return jsonify({'weeks': [], 'season_id': None})

    season_id = season['season_id']
    matchups = db.execute(
        """
        SELECT
            m.matchup_id, m.week_number, m.scheduled_date, m.status,
            m.tee_time, m.starting_hole, m.week_type, m.is_bye,
            m.course_id, m.tee_id,
            c.course_name,
            te.tee_name,
            ht.team_id AS home_team_id, ht.team_name AS home_team_name,
            hp1.player_id AS hp1_id, hp1.first_name AS hp1_first, hp1.last_name AS hp1_last,
            hp1.handicap_index AS hp1_hcp,
            hp2.player_id AS hp2_id, hp2.first_name AS hp2_first, hp2.last_name AS hp2_last,
            hp2.handicap_index AS hp2_hcp,
            at2.team_id AS away_team_id, at2.team_name AS away_team_name,
            ap1.player_id AS ap1_id, ap1.first_name AS ap1_first, ap1.last_name AS ap1_last,
            ap1.handicap_index AS ap1_hcp,
            ap2.player_id AS ap2_id, ap2.first_name AS ap2_first, ap2.last_name AS ap2_last,
            ap2.handicap_index AS ap2_hcp
        FROM matchups m
        JOIN teams ht  ON ht.team_id  = m.home_team_id
        JOIN players hp1 ON hp1.player_id = ht.player1_id
        JOIN players hp2 ON hp2.player_id = ht.player2_id
        JOIN teams at2 ON at2.team_id  = m.away_team_id
        JOIN players ap1 ON ap1.player_id = at2.player1_id
        JOIN players ap2 ON ap2.player_id = at2.player2_id
        LEFT JOIN courses c  ON c.course_id = m.course_id
        LEFT JOIN tees te    ON te.tee_id   = m.tee_id
        WHERE m.season_id = %s
        ORDER BY m.week_number, m.tee_time NULLS LAST, m.matchup_id
        """,
        (season_id,)
    ).fetchall()

    weeks = {}
    for r in matchups:
        wn = r['week_number']
        if wn not in weeks:
            weeks[wn] = {
                'week_number':    wn,
                'scheduled_date': r['scheduled_date'],
                'week_type':      r['week_type'] or 'Normal',
                'course_name':    r['course_name'],
                'tee_name':       r['tee_name'],
                'matchups':       [],
            }
        weeks[wn]['matchups'].append({
            'matchup_id':    r['matchup_id'],
            'status':        r['status'],
            'is_bye':        bool(r['is_bye']),
            'tee_time':      r['tee_time'],
            'starting_hole': r['starting_hole'],
            'course_id':     r['course_id'],
            'tee_id':        r['tee_id'],
            'team1': {
                'team_id':   r['home_team_id'],
                'name':      r['home_team_name'] or f"{r['hp1_first']} {r['hp1_last']} / {r['hp2_first']} {r['hp2_last']}",
                'players': [
                    {'player_id': r['hp1_id'], 'display_name': f"{r['hp1_first']} {r['hp1_last']}", 'handicap': r['hp1_hcp']},
                    {'player_id': r['hp2_id'], 'display_name': f"{r['hp2_first']} {r['hp2_last']}", 'handicap': r['hp2_hcp']},
                ],
            },
            'team2': {
                'team_id':   r['away_team_id'],
                'name':      r['away_team_name'] or f"{r['ap1_first']} {r['ap1_last']} / {r['ap2_first']} {r['ap2_last']}",
                'players': [
                    {'player_id': r['ap1_id'], 'display_name': f"{r['ap1_first']} {r['ap1_last']}", 'handicap': r['ap1_hcp']},
                    {'player_id': r['ap2_id'], 'display_name': f"{r['ap2_first']} {r['ap2_last']}", 'handicap': r['ap2_hcp']},
                ],
            },
        })

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'weeks':       list(weeks.values()),
    })


@bp.route('/schedule/<int:matchup_id>')
@require_jwt
def mobile_matchup_detail(matchup_id):
    """Single matchup detail including any existing round data."""
    db = get_db()
    matchup = db.execute(
        """
        SELECT m.*, s.season_name,
               c.course_name, te.tee_name,
               ht.team_id AS home_team_id, ht.team_name AS home_team_name,
               hp1.player_id AS hp1_id, hp1.first_name AS hp1_first, hp1.last_name AS hp1_last, hp1.handicap_index AS hp1_hcp,
               hp2.player_id AS hp2_id, hp2.first_name AS hp2_first, hp2.last_name AS hp2_last, hp2.handicap_index AS hp2_hcp,
               at2.team_id AS away_team_id, at2.team_name AS away_team_name,
               ap1.player_id AS ap1_id, ap1.first_name AS ap1_first, ap1.last_name AS ap1_last, ap1.handicap_index AS ap1_hcp,
               ap2.player_id AS ap2_id, ap2.first_name AS ap2_first, ap2.last_name AS ap2_last, ap2.handicap_index AS ap2_hcp
        FROM matchups m
        JOIN seasons s  ON s.season_id   = m.season_id
        JOIN teams ht   ON ht.team_id    = m.home_team_id
        JOIN players hp1 ON hp1.player_id = ht.player1_id
        JOIN players hp2 ON hp2.player_id = ht.player2_id
        JOIN teams at2  ON at2.team_id   = m.away_team_id
        JOIN players ap1 ON ap1.player_id = at2.player1_id
        JOIN players ap2 ON ap2.player_id = at2.player2_id
        LEFT JOIN courses c  ON c.course_id = m.course_id
        LEFT JOIN tees te    ON te.tee_id   = m.tee_id
        WHERE m.matchup_id = %s AND s.league_id = %s
        """,
        (matchup_id, g.jwt_league_id)
    ).fetchone()
    if not matchup:
        return _err('Matchup not found.', 404)

    round_row = db.execute(
        "SELECT round_id FROM rounds WHERE matchup_id = %s", (matchup_id,)
    ).fetchone()

    return jsonify({
        'matchup_id':    matchup_id,
        'week_number':   matchup['week_number'],
        'scheduled_date': matchup['scheduled_date'],
        'status':        matchup['status'],
        'tee_time':      matchup['tee_time'],
        'starting_hole': matchup['starting_hole'],
        'course_id':     matchup['course_id'],
        'course_name':   matchup['course_name'],
        'tee_id':        matchup['tee_id'],
        'tee_name':      matchup['tee_name'],
        'round_id':      round_row['round_id'] if round_row else None,
        'team1': {
            'team_id': matchup['home_team_id'],
            'name':    matchup['home_team_name'] or f"{matchup['hp1_first']} / {matchup['hp2_first']}",
            'players': [
                {'player_id': matchup['hp1_id'], 'display_name': f"{matchup['hp1_first']} {matchup['hp1_last']}", 'handicap': matchup['hp1_hcp']},
                {'player_id': matchup['hp2_id'], 'display_name': f"{matchup['hp2_first']} {matchup['hp2_last']}", 'handicap': matchup['hp2_hcp']},
            ],
        },
        'team2': {
            'team_id': matchup['away_team_id'],
            'name':    matchup['away_team_name'] or f"{matchup['ap1_first']} / {matchup['ap2_first']}",
            'players': [
                {'player_id': matchup['ap1_id'], 'display_name': f"{matchup['ap1_first']} {matchup['ap1_last']}", 'handicap': matchup['ap1_hcp']},
                {'player_id': matchup['ap2_id'], 'display_name': f"{matchup['ap2_first']} {matchup['ap2_last']}", 'handicap': matchup['ap2_hcp']},
            ],
        },
    })


@bp.route('/standings')
@require_jwt
def mobile_standings():
    """Current season standings for the JWT's league."""
    db = get_db()
    season = _current_season(db, g.jwt_league_id)
    if not season:
        return jsonify({'standings': [], 'season_id': None})

    season_id = season['season_id']
    rows = db.execute(
        """
        SELECT
            t.team_id, t.team_name,
            p1.first_name || ' ' || p1.last_name AS p1_name,
            p2.first_name || ' ' || p2.last_name AS p2_name,
            COALESCE(SUM(mr.total_points), 0)            AS total_points,
            COUNT(DISTINCT CASE WHEN mr.total_points IS NOT NULL THEN mr.matchup_id END) AS rounds_played,
            COALESCE(SUM(CASE WHEN mr.total_points > opp.total_points THEN 1 ELSE 0 END), 0) AS wins,
            COALESCE(SUM(CASE WHEN mr.total_points < opp.total_points THEN 1 ELSE 0 END), 0) AS losses,
            COALESCE(SUM(CASE WHEN mr.total_points = opp.total_points AND mr.total_points IS NOT NULL THEN 1 ELSE 0 END), 0) AS ties
        FROM teams t
        JOIN players p1 ON p1.player_id = t.player1_id
        JOIN players p2 ON p2.player_id = t.player2_id
        LEFT JOIN match_results mr ON mr.team_id = t.team_id AND mr.matchup_id IN (
            SELECT matchup_id FROM matchups WHERE season_id = %s
        )
        LEFT JOIN match_results opp ON opp.matchup_id = mr.matchup_id AND opp.team_id != t.team_id
        WHERE t.season_id = %s
        GROUP BY t.team_id, t.team_name, p1_name, p2_name
        ORDER BY total_points DESC
        """,
        (season_id, season_id)
    ).fetchall()

    standings = []
    for i, r in enumerate(rows, 1):
        standings.append({
            'rank':         i,
            'team_id':      r['team_id'],
            'team_name':    r['team_name'] or f"{r['p1_name']} / {r['p2_name']}",
            'p1_name':      r['p1_name'],
            'p2_name':      r['p2_name'],
            'total_points': round(float(r['total_points']), 1),
            'rounds_played': r['rounds_played'],
            'wins':         r['wins'],
            'losses':       r['losses'],
            'ties':         r['ties'],
        })

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'standings':   standings,
    })


@bp.route('/players/nicknames')
@require_jwt
def mobile_player_nicknames():
    """All players with their nicknames — used client-side for OCR name matching."""
    db = get_db()

    players = db.execute(
        """SELECT player_id, first_name, last_name FROM players
           WHERE league_id = %s AND active = 1
           ORDER BY last_name, first_name""",
        (g.jwt_league_id,)
    ).fetchall()

    # Load nicknames if table exists
    nicknames_map = {}
    try:
        rows = db.execute(
            "SELECT player_id, nickname FROM player_nicknames WHERE league_id = %s",
            (g.jwt_league_id,)
        ).fetchall()
        for r in rows:
            nicknames_map.setdefault(r['player_id'], []).append(r['nickname'])
    except Exception:
        pass  # table may not exist yet on older deploys

    result = []
    for p in players:
        result.append({
            'player_id':    p['player_id'],
            'display_name': f"{p['first_name']} {p['last_name']}",
            'first_name':   p['first_name'],
            'last_name':    p['last_name'],
            'nicknames':    nicknames_map.get(p['player_id'], []),
        })

    return jsonify({'players': result})


@bp.route('/scorecards/<int:round_id>')
@require_jwt
def mobile_scorecard(round_id):
    """Hole-by-hole scores + match results for a completed round."""
    db = get_db()

    # Verify round belongs to this league
    round_row = db.execute(
        """SELECT r.*, m.week_number, s.league_id
           FROM rounds r
           JOIN matchups m ON m.matchup_id = r.matchup_id
           JOIN seasons s  ON s.season_id  = r.season_id
           WHERE r.round_id = %s AND s.league_id = %s""",
        (round_id, g.jwt_league_id)
    ).fetchone()
    if not round_row:
        return _err('Round not found.', 404)

    scorecards = db.execute(
        """SELECT sc.scorecard_id, sc.player_id, sc.team_id, sc.is_sub,
                  sc.handicap_at_time_of_play,
                  p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name
           FROM scorecards sc
           JOIN players p ON p.player_id = sc.player_id
           JOIN teams   t ON t.team_id   = sc.team_id
           WHERE sc.round_id = %s
           ORDER BY sc.team_id, sc.player_id""",
        (round_id,)
    ).fetchall()

    players_data = []
    for sc in scorecards:
        holes = db.execute(
            """SELECT hs.hole_number, hs.gross_score, hs.net_score,
                      hs.score_differential, h.par
               FROM hole_scores hs
               LEFT JOIN holes h ON h.hole_id = hs.hole_id
               WHERE hs.scorecard_id = %s
               ORDER BY hs.hole_number""",
            (sc['scorecard_id'],)
        ).fetchall()

        mr = db.execute(
            """SELECT hole_points_won, overall_point_won, total_points, role
               FROM match_results
               WHERE matchup_id = %s AND player_id = %s""",
            (round_row['matchup_id'], sc['player_id'])
        ).fetchone()

        players_data.append({
            'player_id':               sc['player_id'],
            'player_name':             sc['player_name'],
            'team_id':                 sc['team_id'],
            'team_name':               sc['team_name'],
            'is_sub':                  bool(sc['is_sub']),
            'handicap_at_time_of_play': sc['handicap_at_time_of_play'],
            'role':                    mr['role'] if mr else None,
            'hole_points_won':         float(mr['hole_points_won'])   if mr and mr['hole_points_won']   is not None else None,
            'overall_point_won':       float(mr['overall_point_won']) if mr and mr['overall_point_won'] is not None else None,
            'total_points':            float(mr['total_points'])      if mr and mr['total_points']      is not None else None,
            'holes': [
                {
                    'hole_number':        h['hole_number'],
                    'par':                h['par'],
                    'gross_score':        h['gross_score'],
                    'net_score':          h['net_score'],
                    'score_differential': h['score_differential'],
                }
                for h in holes
            ],
        })

    return jsonify({
        'round_id':       round_id,
        'matchup_id':     round_row['matchup_id'],
        'week_number':    round_row['week_number'],
        'round_date':     round_row['round_date'],
        'players':        players_data,
    })


@bp.route('/nicknames', methods=['POST'])
@require_jwt
def add_nickname():
    """POST {player_id, nickname} — save OCR nickname for a player."""
    data      = request.get_json(force=True, silent=True) or {}
    player_id = data.get('player_id')
    nickname  = (data.get('nickname') or '').strip()
    if not player_id or not nickname:
        return _err('player_id and nickname are required.', 400)

    db = get_db()
    # Verify player belongs to this league
    player = db.execute(
        "SELECT player_id FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, g.jwt_league_id)
    ).fetchone()
    if not player:
        return _err('Player not found.', 404)

    try:
        db.execute(
            "INSERT INTO player_nicknames (player_id, league_id, nickname) VALUES (%s, %s, %s)",
            (player_id, g.jwt_league_id, nickname)
        )
        db.commit()
    except Exception:
        return _err('Nickname already exists for this player.', 409)

    return jsonify({'status': 'created', 'player_id': player_id, 'nickname': nickname}), 201


@bp.route('/nicknames/<int:nickname_id>', methods=['DELETE'])
@require_jwt
def delete_nickname(nickname_id):
    """DELETE — remove a nickname (player owner or admin)."""
    db = get_db()
    row = db.execute(
        """SELECT pn.nickname_id, pn.player_id, p.user_id
           FROM player_nicknames pn
           JOIN players p ON p.player_id = pn.player_id
           WHERE pn.nickname_id = %s AND p.league_id = %s""",
        (nickname_id, g.jwt_league_id)
    ).fetchone()
    if not row:
        return _err('Nickname not found.', 404)

    is_owner = (row['user_id'] == g.jwt_user_id)
    is_admin = g.jwt_role in ('admin', 'league_admin')
    if not is_owner and not is_admin:
        return _err('Permission denied.', 403)

    db.execute("DELETE FROM player_nicknames WHERE nickname_id = %s", (nickname_id,))
    db.commit()
    return jsonify({'status': 'deleted'})
