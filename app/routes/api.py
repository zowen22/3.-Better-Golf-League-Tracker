"""
REST API v1 — BetterGolfLeagueTracker
Auth: X-Api-Key header  OR  ?api_key=<key> query param (legacy)
      Authorization: Bearer <JWT>  (mobile endpoints)
All responses: JSON  (Content-Type: application/json)

Endpoints (legacy API-key auth):
  GET /api/v1/leagues/me                            league info
  GET /api/v1/seasons                               list seasons
  GET /api/v1/seasons/<id>/standings                team standings
  GET /api/v1/seasons/<id>/schedule                 full schedule
  GET /api/v1/seasons/<id>/teams                    teams + players
  GET /api/v1/players                               player roster
  GET /api/v1/matchups/<id>/scores                  scorecard detail
  GET /api/v1/seasons/<id>/weeks/<n>/live           live leaderboard
  POST /api/v1/keys/regenerate                      rotate API key (admin)

Endpoints (JWT Bearer auth — mobile app):
  POST /api/v1/auth/login                           obtain JWT
  POST /api/v1/auth/refresh                         refresh JWT
  GET  /api/v1/auth/me                              current user
  GET  /api/v1/schedule                             current season schedule
  GET  /api/v1/schedule/<matchup_id>                matchup detail
  GET  /api/v1/standings                            current season standings
  GET  /api/v1/players/nicknames                    players + OCR nicknames
  GET  /api/v1/scorecards/<round_id>                completed round scorecard
  POST /api/v1/nicknames                            add OCR nickname
  DELETE /api/v1/nicknames/<id>                     remove OCR nickname
  POST /api/v1/scores/submit                        submit scores (admin)
  GET  /api/v1/admin/pending                        pending self-reports (admin)
  POST /api/v1/admin/approve/<submission_id>        approve self-report (admin)
  POST /api/v1/apns/register                        register APNs device token
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
    POST {league_code, password}
    Authenticates against the league's admin_password_hash or member_password_hash.
    Returns {token, league_id, role, display_name, current_season_id}

    Legacy path (kept for future individual accounts):
    POST {email, password, league_code} still works if email is provided.
    """
    data = request.get_json(force=True, silent=True) or {}
    email       = (data.get('email') or '').strip().lower()
    password    = data.get('password', '')
    league_code = (data.get('league_code') or '').strip()

    if not password or not league_code:
        return _err('league_code and password are required.', 400)

    db = get_db()

    # Validate league
    league = db.execute(
        "SELECT * FROM leagues WHERE login_code = %s AND active = 1",
        (league_code,)
    ).fetchone()
    if not league:
        return _err('League not found.', 404)

    if email:
        # --- Individual user auth (legacy / future use) ---
        user = db.execute(
            "SELECT * FROM users WHERE LOWER(email) = %s AND active = 1",
            (email,)
        ).fetchone()
        if not user or not check_password_hash(user['password_hash'] or '', password):
            return _err('Invalid email or password.', 401)

        ulr = db.execute(
            """SELECT ulr.role_id, r.role_name
               FROM user_league_roles ulr
               JOIN roles r ON r.role_id = ulr.role_id
               WHERE ulr.user_id = %s AND ulr.league_id = %s""",
            (user['user_id'], league['league_id'])
        ).fetchone()
        if not ulr:
            return _err('Your account is not a member of this league.', 403)

        player = db.execute(
            "SELECT player_id FROM players WHERE user_id = %s AND league_id = %s",
            (user['user_id'], league['league_id'])
        ).fetchone()
        player_id = player['player_id'] if player else None
        role = ulr['role_name']
        user_id = user['user_id']
        display_name = f"{user['first_name']} {user['last_name']}"
    else:
        # --- League-level auth (primary iOS path) ---
        if check_password_hash(league['admin_password_hash'] or '', password):
            role = 'league_admin'
        elif check_password_hash(league['member_password_hash'] or '', password):
            role = 'member'
        else:
            return _err('Incorrect password.', 401)

        user_id = 0  # No individual user for league-level auth
        player_id = None
        display_name = league['league_name']

    season = _current_season(db, league['league_id'])

    token = create_token(
        user_id=user_id,
        league_id=league['league_id'],
        role=role,
        player_id=player_id,
    )

    return jsonify({
        'token':             token,
        'user_id':           user_id,
        'league_id':         league['league_id'],
        'league_name':       league['league_name'],
        'role':              role,
        'player_id':         player_id,
        'display_name':      display_name,
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
            hh1.handicap_index AS hp1_hcp,
            hp2.player_id AS hp2_id, hp2.first_name AS hp2_first, hp2.last_name AS hp2_last,
            hh2.handicap_index AS hp2_hcp,
            at2.team_id AS away_team_id, at2.team_name AS away_team_name,
            ap1.player_id AS ap1_id, ap1.first_name AS ap1_first, ap1.last_name AS ap1_last,
            hh3.handicap_index AS ap1_hcp,
            ap2.player_id AS ap2_id, ap2.first_name AS ap2_first, ap2.last_name AS ap2_last,
            hh4.handicap_index AS ap2_hcp
        FROM matchups m
        JOIN teams ht  ON ht.team_id  = m.team1_id
        JOIN players hp1 ON hp1.player_id = ht.player1_id
        JOIN players hp2 ON hp2.player_id = ht.player2_id
        JOIN teams at2 ON at2.team_id  = m.team2_id
        JOIN players ap1 ON ap1.player_id = at2.player1_id
        JOIN players ap2 ON ap2.player_id = at2.player2_id
        LEFT JOIN courses c  ON c.course_id = m.course_id
        LEFT JOIN tees te    ON te.tee_id   = m.tee_id
        LEFT JOIN LATERAL (
            SELECT handicap_index FROM handicap_history
            WHERE player_id = hp1.player_id
            ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1
        ) hh1 ON true
        LEFT JOIN LATERAL (
            SELECT handicap_index FROM handicap_history
            WHERE player_id = hp2.player_id
            ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1
        ) hh2 ON true
        LEFT JOIN LATERAL (
            SELECT handicap_index FROM handicap_history
            WHERE player_id = ap1.player_id
            ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1
        ) hh3 ON true
        LEFT JOIN LATERAL (
            SELECT handicap_index FROM handicap_history
            WHERE player_id = ap2.player_id
            ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1
        ) hh4 ON true
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
               hp1.player_id AS hp1_id, hp1.first_name AS hp1_first, hp1.last_name AS hp1_last, hh1.handicap_index AS hp1_hcp,
               hp2.player_id AS hp2_id, hp2.first_name AS hp2_first, hp2.last_name AS hp2_last, hh2.handicap_index AS hp2_hcp,
               at2.team_id AS away_team_id, at2.team_name AS away_team_name,
               ap1.player_id AS ap1_id, ap1.first_name AS ap1_first, ap1.last_name AS ap1_last, hh3.handicap_index AS ap1_hcp,
               ap2.player_id AS ap2_id, ap2.first_name AS ap2_first, ap2.last_name AS ap2_last, hh4.handicap_index AS ap2_hcp
        FROM matchups m
        JOIN seasons s  ON s.season_id   = m.season_id
        JOIN teams ht   ON ht.team_id    = m.team1_id
        JOIN players hp1 ON hp1.player_id = ht.player1_id
        JOIN players hp2 ON hp2.player_id = ht.player2_id
        JOIN teams at2  ON at2.team_id   = m.team2_id
        JOIN players ap1 ON ap1.player_id = at2.player1_id
        JOIN players ap2 ON ap2.player_id = at2.player2_id
        LEFT JOIN courses c  ON c.course_id = m.course_id
        LEFT JOIN tees te    ON te.tee_id   = m.tee_id
        LEFT JOIN LATERAL (
            SELECT handicap_index FROM handicap_history
            WHERE player_id = hp1.player_id
            ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1
        ) hh1 ON true
        LEFT JOIN LATERAL (
            SELECT handicap_index FROM handicap_history
            WHERE player_id = hp2.player_id
            ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1
        ) hh2 ON true
        LEFT JOIN LATERAL (
            SELECT handicap_index FROM handicap_history
            WHERE player_id = ap1.player_id
            ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1
        ) hh3 ON true
        LEFT JOIN LATERAL (
            SELECT handicap_index FROM handicap_history
            WHERE player_id = ap2.player_id
            ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1
        ) hh4 ON true
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


# ---------------------------------------------------------------------------
# WP0.3 — Score Submission + Admin Endpoints
# ---------------------------------------------------------------------------

@bp.route('/scores/submit', methods=['POST'])
@require_jwt_admin
def api_submit_scores():
    """
    POST {matchup_id, tee_id, course_id?, round_date?,
          scores: [{player_id, hole_scores: [int, ...]}],
          player_tees?: [{player_id, tee_id}],
          absences?: [{player_id, sub_player_id?}]}
    → {round_id, match_results: [{player_id, role, hole_points, overall_point, total_points}]}
    """
    from routes.scores import (
        calc_playing_handicap, strokes_on_hole, calc_match_play, calc_stableford,
        get_player_handicap, get_league_settings, _build_player_list, _get_sub_assignments,
    )
    from routes.handicap import recalc_handicap_for_player
    from routes.notifications import create_league_event

    data       = request.get_json(force=True, silent=True) or {}
    league_id  = g.jwt_league_id
    user_id    = g.jwt_user_id
    matchup_id = data.get('matchup_id')
    tee_id     = data.get('tee_id')

    if not matchup_id or not tee_id:
        return _err('matchup_id and tee_id are required.', 400)

    db = get_db()

    # Load and validate matchup
    matchup = db.execute(
        """SELECT m.*, s.season_id, s.league_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = %s AND s.league_id = %s""",
        (matchup_id, league_id)
    ).fetchone()
    if not matchup:
        return _err('Matchup not found.', 404)
    if matchup['status'] == 'completed':
        return _err('Scores for this matchup have already been recorded.', 409)
    if matchup['is_bye']:
        return _err('Bye weeks do not have scores.', 400)

    season_id = matchup['season_id']

    # Resolve course_id from tee if not provided
    tee_row = db.execute(
        "SELECT tee_id, course_id FROM tees WHERE tee_id = %s", (tee_id,)
    ).fetchone()
    if not tee_row:
        return _err('Tee not found.', 404)
    course_id = data.get('course_id') or tee_row['course_id']

    round_date = (data.get('round_date') or '').strip() or datetime.now().strftime('%Y-%m-%d')

    # Load holes for default tee
    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number", (tee_id,)
    ).fetchall()
    if not holes:
        return _err('No hole data for the selected tee.', 400)

    # Load teams
    def _load_team(team_id):
        return db.execute(
            """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                           p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
               FROM teams t
               LEFT JOIN players p1 ON t.player1_id = p1.player_id
               LEFT JOIN players p2 ON t.player2_id = p2.player_id
               WHERE t.team_id = %s""", (team_id,)
        ).fetchone()

    team1 = _load_team(matchup['team1_id'])
    team2 = _load_team(matchup['team2_id'])
    if not team1 or not team2:
        return _err('Teams not found for this matchup.', 400)

    sub_assignments = _get_sub_assignments(db, matchup_id)

    # Apply absences from payload (optional)
    absences = data.get('absences') or []
    for ab in absences:
        ab_pid     = ab.get('player_id')
        sub_pid    = ab.get('sub_player_id')
        if ab_pid:
            existing_ab = db.execute(
                "SELECT absence_id FROM player_absences WHERE matchup_id = %s AND player_id = %s",
                (matchup_id, ab_pid)
            ).fetchone()
            if existing_ab:
                db.execute(
                    "UPDATE player_absences SET sub_player_id = %s WHERE absence_id = %s",
                    (sub_pid, existing_ab['absence_id'])
                )
            else:
                db.execute(
                    "INSERT INTO player_absences (matchup_id, player_id, sub_player_id, excused) VALUES (%s, %s, %s, 0)",
                    (matchup_id, ab_pid, sub_pid)
                )

    # Refresh sub assignments after applying absences
    sub_assignments = _get_sub_assignments(db, matchup_id)
    players = _build_player_list(db, season_id, team1, team2, sub_assignments, league_id=league_id)
    if len(players) < 4:
        return _err('Both teams need 2 players assigned before entering scores.', 400)

    # Per-player tee overrides
    player_tees_input = {pt['player_id']: pt['tee_id'] for pt in (data.get('player_tees') or [])}
    player_tee_ids = {}
    player_holes   = {}
    for p in players:
        pid = p['player_id']
        override_tid = player_tees_input.get(pid)
        if override_tid and override_tid != tee_id:
            # Validate same course
            ot = db.execute("SELECT course_id FROM tees WHERE tee_id = %s", (override_tid,)).fetchone()
            if not ot or ot['course_id'] != course_id:
                return _err(f"Override tee for player {pid} does not belong to the selected course.", 400)
            ph = db.execute("SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number", (override_tid,)).fetchall()
            player_tee_ids[pid] = override_tid
            player_holes[pid]   = ph if ph else holes
        else:
            player_tee_ids[pid] = tee_id
            player_holes[pid]   = holes

    # Parse and validate submitted scores
    scores_input = {s['player_id']: s['hole_scores'] for s in (data.get('scores') or [])}
    gross = {}
    for p in players:
        pid       = p['player_id']
        p_holes   = player_holes[pid]
        submitted = scores_input.get(pid)
        if not submitted:
            return _err(f"Missing scores for player {pid}.", 400)
        if len(submitted) != len(p_holes):
            return _err(f"Expected {len(p_holes)} scores for player {pid}, got {len(submitted)}.", 400)
        for i, s in enumerate(submitted):
            if not isinstance(s, int) or s < 1 or s > 20:
                return _err(f"Score out of range for player {pid} hole {i + 1} (got {s}).", 400)
        gross[pid] = list(submitted)

    # League settings + handicaps
    settings         = get_league_settings(db, season_id, league_id)
    handicap_percent = float(settings['handicap_percent']) if settings else 90.0
    max_handicap     = float(settings['max_handicap_index']) if settings else 18.0
    scoring_mode     = (settings.get('scoring_mode') or 'match_play') if settings else 'match_play'

    playing_hcps = {p['player_id']: calc_playing_handicap(p['handicap'], handicap_percent, max_handicap)
                    for p in players}

    # Net scores
    net = {}
    for p in players:
        pid     = p['player_id']
        ph      = playing_hcps[pid]
        p_holes = player_holes[pid]
        net[pid] = [gross[pid][i] - strokes_on_hole(ph, h['handicap_index'], total_holes=len(p_holes))
                    for i, h in enumerate(p_holes)]

    # A/B designation
    def _designate(team, p_list):
        tp = sorted([p for p in p_list if p['team_id'] == team['team_id']],
                    key=lambda x: playing_hcps[x['player_id']])
        return tp[0]['player_id'], tp[1]['player_id']

    t1_a, t1_b = _designate(team1, players)
    t2_a, t2_b = _designate(team2, players)

    def _match_result(pid_x, pid_y):
        p_holes_x = player_holes[pid_x]
        if scoring_mode == 'stableford':
            sb_x = sum(calc_stableford(net[pid_x][i] - (h['par'] or 4)) for i, h in enumerate(p_holes_x))
            sb_y = sum(calc_stableford(net[pid_y][i] - (h['par'] or 4)) for i, h in enumerate(p_holes_x))
            ov_x, ov_y = calc_match_play(-sb_x, -sb_y)
            return sb_x, sb_y, ov_x, ov_y
        else:
            hp_x, hp_y = 0.0, 0.0
            for i in range(len(p_holes_x)):
                px, py = calc_match_play(net[pid_x][i], net[pid_y][i])
                hp_x += px; hp_y += py
            ov_x, ov_y = calc_match_play(sum(net[pid_x]), sum(net[pid_y]))
            return hp_x, hp_y, ov_x, ov_y

    aa = _match_result(t1_a, t2_a)
    bb = _match_result(t1_b, t2_b)

    # Duplicate guard
    existing = db.execute("SELECT round_id FROM rounds WHERE matchup_id = %s", (matchup_id,)).fetchone()
    if existing:
        return _err('Scores for this matchup have already been recorded.', 409)

    # Save round
    row = db.execute(
        """INSERT INTO rounds (matchup_id, season_id, course_id, tee_id, round_date, round_number, entered_by_user_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING round_id""",
        (matchup_id, season_id, int(course_id), int(tee_id),
         round_date, matchup['round_number'], user_id)
    )
    round_id = row.fetchone()['round_id']

    # Scorecards + hole scores
    for p in players:
        pid         = p['player_id']
        p_holes     = player_holes[pid]
        p_tee_id    = player_tee_ids[pid]
        is_sub_flag = 1 if p.get('is_sub') else 0
        sub_for_pid = p.get('orig_player_id')

        sc_row = db.execute(
            """INSERT INTO scorecards
               (round_id, player_id, team_id, handicap_at_time_of_play,
                is_sub, sub_for_player_id, approved, tee_id)
               VALUES (%s, %s, %s, %s, %s, %s, 1, %s) RETURNING scorecard_id""",
            (round_id, pid, p['team_id'], playing_hcps[pid],
             is_sub_flag, sub_for_pid, p_tee_id)
        )
        sc_id = sc_row.fetchone()['scorecard_id']
        for i, h in enumerate(p_holes):
            db.execute(
                """INSERT INTO hole_scores
                   (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (sc_id, h['hole_id'], h['hole_number'],
                 gross[pid][i], net[pid][i], gross[pid][i] - h['par'])
            )

    # Absence round linkage
    db.execute("UPDATE player_absences SET round_id = %s WHERE matchup_id = %s", (round_id, matchup_id))

    # Match results
    roles = {
        t1_a: ('A', team1['team_id'], t2_a, aa[0], aa[2]),
        t2_a: ('A', team2['team_id'], t1_a, aa[1], aa[3]),
        t1_b: ('B', team1['team_id'], t2_b, bb[0], bb[2]),
        t2_b: ('B', team2['team_id'], t1_b, bb[1], bb[3]),
    }
    for pid, (role, tid, opp, hole_pts, overall_pt) in roles.items():
        db.execute(
            """INSERT INTO match_results
               (matchup_id, team_id, player_id, role,
                hole_points_won, overall_point_won, total_points, opponent_player_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (matchup_id, tid, pid, role, hole_pts, overall_pt, hole_pts + overall_pt, opp)
        )

    db.execute(
        "UPDATE matchups SET status = 'completed', course_id = %s, tee_id = %s WHERE matchup_id = %s",
        (int(course_id), int(tee_id), matchup_id)
    )
    db.commit()

    # Handicap recalc (non-fatal)
    try:
        for p in players:
            recalc_handicap_for_player(db, p['player_id'], season_id, league_id)
        db.commit()
    except Exception:
        pass

    # Notification event
    try:
        t1_name = team1.get('team_name') or f"{team1['p1_last']}/{team1['p2_last']}"
        t2_name = team2.get('team_name') or f"{team2['p1_last']}/{team2['p2_last']}"
        create_league_event(db, league_id, 'round_completed',
                            f"Scores recorded: {t1_name} vs {t2_name} (Week {matchup['week_number']})",
                            season_id=season_id, ref_id=matchup_id)
        db.commit()
    except Exception:
        pass

    return jsonify({
        'round_id': round_id,
        'match_results': [
            {
                'player_id':     pid,
                'role':          role,
                'team_id':       tid,
                'hole_points':   hole_pts,
                'overall_point': overall_pt,
                'total_points':  hole_pts + overall_pt,
            }
            for pid, (role, tid, _, hole_pts, overall_pt) in roles.items()
        ],
    }), 201


@bp.route('/admin/pending')
@require_jwt_admin
def api_admin_pending():
    """Pending self-report submissions for the current league."""
    db  = get_db()
    rows = db.execute(
        """SELECT ss.submission_id, ss.status, ss.submitted_at,
                  m.matchup_id, m.week_number, m.scheduled_date,
                  p.first_name || ' ' || p.last_name AS submitted_by_name,
                  c.course_name, te.tee_name, te.nine,
                  t1.team_name AS team1_name, t2.team_name AS team2_name
           FROM score_submissions ss
           JOIN matchups m  ON ss.matchup_id = m.matchup_id
           JOIN seasons  s  ON m.season_id   = s.season_id
           LEFT JOIN players p  ON ss.player_id  = p.player_id
           LEFT JOIN courses c  ON ss.course_id   = c.course_id
           LEFT JOIN tees    te ON ss.tee_id       = te.tee_id
           LEFT JOIN teams   t1 ON m.team1_id      = t1.team_id
           LEFT JOIN teams   t2 ON m.team2_id      = t2.team_id
           WHERE s.league_id = %s AND ss.status = 'pending'
           ORDER BY ss.submitted_at DESC""",
        (g.jwt_league_id,)
    ).fetchall()

    result = []
    for r in rows:
        # Score summary: count of holes submitted
        detail_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM score_submission_details WHERE submission_id = %s",
            (r['submission_id'],)
        ).fetchone()
        result.append({
            'submission_id':     r['submission_id'],
            'matchup_id':        r['matchup_id'],
            'week_number':       r['week_number'],
            'scheduled_date':    r['scheduled_date'],
            'submitted_by_name': r['submitted_by_name'],
            'submitted_at':      r['submitted_at'],
            'course_name':       r['course_name'],
            'tee_name':          r['tee_name'],
            'nine':              r['nine'],
            'team1_name':        r['team1_name'],
            'team2_name':        r['team2_name'],
            'hole_count':        detail_count['cnt'] if detail_count else 0,
        })

    return jsonify({'pending': result, 'count': len(result)})


@bp.route('/admin/approve/<int:submission_id>', methods=['POST'])
@require_jwt_admin
def api_admin_approve(submission_id):
    """Approve a pending self-report — creates the round and calculates match results."""
    from routes.self_report import approve as web_approve
    # Re-use the approve logic via a shared helper rather than calling the web handler.
    # We call the DB path directly to avoid session/redirect dependencies.
    from routes.scores import (
        calc_playing_handicap, strokes_on_hole, calc_match_play, calc_stableford,
        get_player_handicap, get_league_settings, _build_player_list,
    )
    from routes.handicap import recalc_handicap_for_player
    from routes.notifications import create_league_event

    db         = get_db()
    league_id  = g.jwt_league_id
    user_id    = g.jwt_user_id

    sub = db.execute(
        """SELECT ss.*, m.matchup_id, m.team1_id, m.team2_id, m.status AS matchup_status,
                  m.week_number, m.round_number, s.season_id, s.league_id
           FROM score_submissions ss
           JOIN matchups m ON ss.matchup_id = m.matchup_id
           JOIN seasons  s ON m.season_id   = s.season_id
           WHERE ss.submission_id = %s AND s.league_id = %s""",
        (submission_id, league_id)
    ).fetchone()

    if not sub:
        return _err('Submission not found.', 404)
    if sub['status'] != 'pending':
        return _err('This submission has already been reviewed.', 409)
    if sub['matchup_status'] == 'completed':
        db.execute(
            "UPDATE score_submissions SET status='rejected', admin_note='Matchup already scored', "
            "reviewed_at=%s WHERE submission_id=%s",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), submission_id)
        )
        db.commit()
        return _err('Matchup already has scores entered — submission rejected.', 409)

    details = db.execute(
        "SELECT * FROM score_submission_details WHERE submission_id = %s ORDER BY player_id, hole_number",
        (submission_id,)
    ).fetchall()
    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number", (sub['tee_id'],)
    ).fetchall()
    if not holes:
        return _err('No hole data for the selected tee.', 400)

    def _load_team(team_id):
        return db.execute(
            """SELECT t.*, p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                           p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
               FROM teams t
               LEFT JOIN players p1 ON t.player1_id = p1.player_id
               LEFT JOIN players p2 ON t.player2_id = p2.player_id
               WHERE t.team_id = %s""", (team_id,)
        ).fetchone()

    team1   = _load_team(sub['team1_id'])
    team2   = _load_team(sub['team2_id'])
    players = _build_player_list(db, sub['season_id'], team1, team2, league_id=league_id)

    gross = {}
    for d in details:
        pid = d['player_id']
        gross.setdefault(pid, {})[d['hole_number']] = d['gross_score']

    # Validate completeness + range
    for p in players:
        pid = p['player_id']
        if pid not in gross or len(gross[pid]) != len(holes):
            return _err(f"Submission is missing scores for player {p['first_name']} {p['last_name']}.", 400)
        for hnum, score in gross[pid].items():
            if score is None or score < 1 or score > 20:
                return _err(f"Score out of range for {p['first_name']} {p['last_name']} hole {hnum} (got {score}).", 400)

    # Convert gross to ordered lists
    gross_ordered = {pid: [scores[h['hole_number']] for h in holes] for pid, scores in gross.items()}

    settings         = get_league_settings(db, sub['season_id'], league_id)
    handicap_percent = float(settings['handicap_percent']) if settings else 90.0
    max_handicap     = float(settings['max_handicap_index']) if settings else 18.0
    scoring_mode     = (settings.get('scoring_mode') or 'match_play') if settings else 'match_play'

    playing_hcps = {p['player_id']: calc_playing_handicap(p['handicap'], handicap_percent, max_handicap)
                    for p in players}
    net = {p['player_id']: [gross_ordered[p['player_id']][i] -
                             strokes_on_hole(playing_hcps[p['player_id']], h['handicap_index'], total_holes=len(holes))
                             for i, h in enumerate(holes)]
           for p in players}

    def _designate(team, p_list):
        tp = sorted([p for p in p_list if p['team_id'] == team['team_id']],
                    key=lambda x: playing_hcps[x['player_id']])
        return tp[0]['player_id'], tp[1]['player_id']

    t1_a, t1_b = _designate(team1, players)
    t2_a, t2_b = _designate(team2, players)

    def _match_result(pid_x, pid_y):
        if scoring_mode == 'stableford':
            sb_x = sum(calc_stableford(net[pid_x][i] - (h['par'] or 4)) for i, h in enumerate(holes))
            sb_y = sum(calc_stableford(net[pid_y][i] - (h['par'] or 4)) for i, h in enumerate(holes))
            ov_x, ov_y = calc_match_play(-sb_x, -sb_y)
            return sb_x, sb_y, ov_x, ov_y
        else:
            hp_x, hp_y = 0.0, 0.0
            for i in range(len(holes)):
                px, py = calc_match_play(net[pid_x][i], net[pid_y][i])
                hp_x += px; hp_y += py
            ov_x, ov_y = calc_match_play(sum(net[pid_x]), sum(net[pid_y]))
            return hp_x, hp_y, ov_x, ov_y

    aa = _match_result(t1_a, t2_a)
    bb = _match_result(t1_b, t2_b)

    existing = db.execute("SELECT round_id FROM rounds WHERE matchup_id = %s", (sub['matchup_id'],)).fetchone()
    if existing:
        return _err('Scores for this matchup have already been recorded.', 409)

    row = db.execute(
        """INSERT INTO rounds (matchup_id, season_id, course_id, tee_id, round_date, round_number, entered_by_user_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING round_id""",
        (sub['matchup_id'], sub['season_id'], sub['course_id'], sub['tee_id'],
         sub.get('round_date') or datetime.now().strftime('%Y-%m-%d'),
         sub['round_number'], user_id)
    )
    round_id = row.fetchone()['round_id']

    for p in players:
        pid = p['player_id']
        sc_row = db.execute(
            """INSERT INTO scorecards
               (round_id, player_id, team_id, handicap_at_time_of_play, is_sub, approved, tee_id)
               VALUES (%s, %s, %s, %s, 0, 1, %s) RETURNING scorecard_id""",
            (round_id, pid, p['team_id'], playing_hcps[pid], sub['tee_id'])
        )
        sc_id = sc_row.fetchone()['scorecard_id']
        for i, h in enumerate(holes):
            db.execute(
                """INSERT INTO hole_scores
                   (scorecard_id, hole_id, hole_number, gross_score, net_score, score_differential)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (sc_id, h['hole_id'], h['hole_number'],
                 gross_ordered[pid][i], net[pid][i], gross_ordered[pid][i] - h['par'])
            )

    db.execute("UPDATE player_absences SET round_id = %s WHERE matchup_id = %s",
               (round_id, sub['matchup_id']))

    roles = {
        t1_a: ('A', team1['team_id'], t2_a, aa[0], aa[2]),
        t2_a: ('A', team2['team_id'], t1_a, aa[1], aa[3]),
        t1_b: ('B', team1['team_id'], t2_b, bb[0], bb[2]),
        t2_b: ('B', team2['team_id'], t1_b, bb[1], bb[3]),
    }
    for pid, (role, tid, opp, hole_pts, overall_pt) in roles.items():
        db.execute(
            """INSERT INTO match_results
               (matchup_id, team_id, player_id, role,
                hole_points_won, overall_point_won, total_points, opponent_player_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (sub['matchup_id'], tid, pid, role, hole_pts, overall_pt, hole_pts + overall_pt, opp)
        )

    db.execute("UPDATE matchups SET status = 'completed', course_id = %s, tee_id = %s WHERE matchup_id = %s",
               (sub['course_id'], sub['tee_id'], sub['matchup_id']))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        "UPDATE score_submissions SET status='approved', reviewed_at=%s WHERE submission_id=%s",
        (now_str, submission_id)
    )
    db.commit()

    try:
        for p in players:
            recalc_handicap_for_player(db, p['player_id'], sub['season_id'], league_id)
        db.commit()
    except Exception:
        pass

    try:
        create_league_event(db, league_id, 'round_completed',
                            f"Self-report approved: Week {sub['week_number']}",
                            season_id=sub['season_id'], ref_id=sub['matchup_id'])
        db.commit()
    except Exception:
        pass

    return jsonify({'round_id': round_id, 'submission_id': submission_id, 'status': 'approved'}), 201


# ===========================================================================
# Stats Endpoints  — JWT-protected, current season auto-detected
# ===========================================================================

@bp.route('/stats/leaders')
@require_jwt
def api_stats_leaders():
    """Season leaders: low gross, high points, most wins."""
    db = get_db()
    season = _current_season(db, g.jwt_league_id)
    if not season:
        return jsonify({'season_id': None, 'low_gross': [], 'high_points': [], 'most_wins': []})
    season_id = season['season_id']

    low_gross = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name,
                  SUM(hs.gross_score) AS total_gross,
                  r.round_date, m.week_number
           FROM hole_scores hs
           JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
           JOIN rounds r      ON sc.round_id     = r.round_id
           JOIN matchups m    ON r.matchup_id     = m.matchup_id
           JOIN players p     ON sc.player_id     = p.player_id
           JOIN teams t       ON sc.team_id       = t.team_id
           WHERE m.season_id = %s AND m.is_bye = 0
           GROUP BY sc.scorecard_id, p.first_name, p.last_name, t.team_name, r.round_date, m.week_number
           ORDER BY total_gross ASC LIMIT 5""",
        (season_id,)
    ).fetchall()

    high_pts = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name, mr.total_points, m.week_number, r.round_date
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           JOIN rounds r   ON r.matchup_id  = m.matchup_id
           JOIN players p  ON mr.player_id  = p.player_id
           JOIN teams t    ON mr.team_id    = t.team_id
           WHERE m.season_id = %s
           ORDER BY mr.total_points DESC LIMIT 5""",
        (season_id,)
    ).fetchall()

    most_wins = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name,
                  COUNT(*) AS wins
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           JOIN players p  ON mr.player_id  = p.player_id
           JOIN teams t    ON mr.team_id    = t.team_id
           LEFT JOIN match_results opp ON opp.matchup_id = mr.matchup_id AND opp.player_id != mr.player_id AND opp.team_id != mr.team_id
           WHERE m.season_id = %s AND mr.total_points > opp.total_points
           GROUP BY mr.player_id, p.first_name, p.last_name, t.team_name
           ORDER BY wins DESC LIMIT 5""",
        (season_id,)
    ).fetchall()

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'low_gross':   [dict(r) for r in low_gross],
        'high_points': [dict(r) for r in high_pts],
        'most_wins':   [dict(r) for r in most_wins],
    })


@bp.route('/stats/allplay')
@require_jwt
def api_stats_allplay():
    """All-play standings: each team's record vs every other team each week."""
    db = get_db()
    season = _current_season(db, g.jwt_league_id)
    if not season:
        return jsonify({'season_id': None, 'rows': [], 'completed_weeks': []})
    season_id  = season['season_id']
    league_id  = g.jwt_league_id

    teams = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s ORDER BY t.team_id""",
        (season_id, league_id)
    ).fetchall()

    week_pts_rows = db.execute(
        """SELECT m.week_number, mr.team_id, SUM(mr.total_points) AS team_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           GROUP BY m.week_number, mr.team_id ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    week_data = {}
    for row in week_pts_rows:
        wk = row['week_number']
        week_data.setdefault(wk, {})[row['team_id']] = row['team_pts']

    week_dates = db.execute(
        """SELECT DISTINCT week_number, scheduled_date FROM matchups
           WHERE season_id = %s AND status = 'completed' AND is_bye = 0
           ORDER BY week_number""",
        (season_id,)
    ).fetchall()
    completed_weeks = [{'week_number': r['week_number'], 'scheduled_date': r['scheduled_date']}
                       for r in week_dates]

    team_ids = [t['team_id'] for t in teams]
    records  = {tid: {'w': 0, 'l': 0, 't': 0} for tid in team_ids}

    for wk_info in completed_weeks:
        wk       = wk_info['week_number']
        team_pts = week_data.get(wk, {})
        playing  = list(team_pts.keys())
        for i, ta in enumerate(playing):
            for tb in playing[i + 1:]:
                pts_a, pts_b = team_pts[ta], team_pts[tb]
                if pts_a > pts_b:
                    records[ta]['w'] += 1; records[tb]['l'] += 1
                elif pts_b > pts_a:
                    records[tb]['w'] += 1; records[ta]['l'] += 1
                else:
                    records[ta]['t'] += 1; records[tb]['t'] += 1

    season_pts_rows = db.execute(
        """SELECT mr.team_id, SUM(mr.total_points) AS total_pts
           FROM match_results mr JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.status = 'completed'
           GROUP BY mr.team_id""",
        (season_id,)
    ).fetchall()
    season_pts = {r['team_id']: float(r['total_pts'] or 0) for r in season_pts_rows}

    rows = []
    for t in teams:
        tid = t['team_id']
        rec = records[tid]
        w, l, tv = rec['w'], rec['l'], rec['t']
        total_games = w + l + tv
        pct = round((w + 0.5 * tv) / total_games, 3) if total_games > 0 else 0.0
        rows.append({
            'team_id':    tid,
            'team_name':  t['team_name'] or f"{t['p1_first']} {t['p1_last']} / {t['p2_first']} {t['p2_last']}",
            'p1_name':    f"{t['p1_first']} {t['p1_last']}",
            'p2_name':    f"{t['p2_first']} {t['p2_last']}",
            'w': w, 'l': l, 't': tv, 'pct': pct,
            'season_pts': season_pts.get(tid, 0.0),
        })
    rows.sort(key=lambda r: (-r['pct'], -r['season_pts']))
    for i, r in enumerate(rows, 1):
        r['rank'] = i

    return jsonify({
        'season_id':      season_id,
        'season_name':    season['season_name'],
        'rows':           rows,
        'completed_weeks': completed_weeks,
    })


@bp.route('/stats/trend')
@require_jwt
def api_stats_trend():
    """Cumulative points trend per team across completed weeks."""
    db = get_db()
    season = _current_season(db, g.jwt_league_id)
    if not season:
        return jsonify({'season_id': None, 'weeks': [], 'teams': []})
    season_id = season['season_id']
    league_id = g.jwt_league_id

    team_rows = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s ORDER BY t.team_id""",
        (season_id, league_id)
    ).fetchall()

    week_rows = db.execute(
        """SELECT DISTINCT week_number, scheduled_date FROM matchups
           WHERE season_id = %s AND status = 'completed' AND is_bye = 0
           ORDER BY week_number""",
        (season_id,)
    ).fetchall()
    weeks = [{'week_number': r['week_number'], 'scheduled_date': r['scheduled_date']}
             for r in week_rows]

    pts_rows = db.execute(
        """SELECT m.week_number, mr.team_id, SUM(mr.total_points) AS wk_pts
           FROM match_results mr JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           GROUP BY m.week_number, mr.team_id""",
        (season_id,)
    ).fetchall()
    wk_team_pts = {(r['week_number'], r['team_id']): float(r['wk_pts'] or 0) for r in pts_rows}

    week_numbers = [w['week_number'] for w in weeks]
    teams_data = []
    for tr in team_rows:
        tid = tr['team_id']
        cumulative = 0.0
        pts_by_week = []
        for wn in week_numbers:
            cumulative += wk_team_pts.get((wn, tid), 0.0)
            pts_by_week.append(round(cumulative, 1))
        teams_data.append({
            'team_id':   tid,
            'team_name': tr['team_name'] or f"{tr['p1_first']} {tr['p1_last']} / {tr['p2_first']} {tr['p2_last']}",
            'points':    pts_by_week,
            'final_pts': pts_by_week[-1] if pts_by_week else 0.0,
        })
    teams_data.sort(key=lambda x: -x['final_pts'])

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'weeks':       weeks,
        'teams':       teams_data,
    })


@bp.route('/stats/records')
@require_jwt
def api_stats_records():
    """Season records: low gross, high individual pts, high/low team combined pts."""
    db = get_db()
    season = _current_season(db, g.jwt_league_id)
    if not season:
        return jsonify({'season_id': None, 'low_gross': [], 'high_gross': [],
                        'high_indiv_pts': [], 'low_indiv_pts': []})
    season_id = season['season_id']

    def round_records(order):
        return db.execute(
            """SELECT p.first_name || ' ' || p.last_name AS player_name,
                      t.team_name, SUM(hs.gross_score) AS total_gross,
                      r.round_date, m.week_number
               FROM hole_scores hs
               JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id
               JOIN rounds r      ON sc.round_id     = r.round_id
               JOIN matchups m    ON r.matchup_id     = m.matchup_id
               JOIN players p     ON sc.player_id     = p.player_id
               JOIN teams t       ON sc.team_id       = t.team_id
               WHERE m.season_id = %s AND m.is_bye = 0
               GROUP BY sc.scorecard_id, p.first_name, p.last_name, t.team_name, r.round_date, m.week_number
               ORDER BY total_gross """ + order + " LIMIT 5",
            (season_id,)
        ).fetchall()

    high_pts = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name, mr.total_points, m.week_number, r.round_date
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           JOIN rounds r   ON r.matchup_id  = m.matchup_id
           JOIN players p  ON mr.player_id  = p.player_id
           JOIN teams t    ON mr.team_id    = t.team_id
           WHERE m.season_id = %s
           ORDER BY mr.total_points DESC LIMIT 5""",
        (season_id,)
    ).fetchall()

    low_pts = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  t.team_name, mr.total_points, m.week_number, r.round_date
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           JOIN rounds r   ON r.matchup_id  = m.matchup_id
           JOIN players p  ON mr.player_id  = p.player_id
           JOIN teams t    ON mr.team_id    = t.team_id
           WHERE m.season_id = %s
           ORDER BY mr.total_points ASC LIMIT 5""",
        (season_id,)
    ).fetchall()

    return jsonify({
        'season_id':      season_id,
        'season_name':    season['season_name'],
        'low_gross':      [dict(r) for r in round_records('ASC')],
        'high_gross':     [dict(r) for r in round_records('DESC')],
        'high_indiv_pts': [dict(r) for r in high_pts],
        'low_indiv_pts':  [dict(r) for r in low_pts],
    })


@bp.route('/stats/weekly')
@require_jwt
def api_stats_weekly():
    """Per-week scorecards summary — teams, points, scores."""
    db = get_db()
    season = _current_season(db, g.jwt_league_id)
    if not season:
        return jsonify({'season_id': None, 'weeks': []})
    season_id = season['season_id']
    league_id = g.jwt_league_id

    week_rows = db.execute(
        """SELECT DISTINCT m.week_number, m.scheduled_date
           FROM matchups m
           WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()

    weeks_out = []
    for wr in week_rows:
        wk = wr['week_number']
        matchups = db.execute(
            """SELECT m.matchup_id, m.week_number,
                      t1.team_name AS team1_name, t2.team_name AS team2_name,
                      c.course_name, te.tee_name,
                      r.round_id, r.round_date
               FROM matchups m
               JOIN teams t1   ON m.team1_id   = t1.team_id
               JOIN teams t2   ON m.team2_id   = t2.team_id
               LEFT JOIN rounds r  ON r.matchup_id  = m.matchup_id
               LEFT JOIN courses c ON c.course_id = r.course_id
               LEFT JOIN tees te   ON te.tee_id    = r.tee_id
               WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0""",
            (season_id, wk)
        ).fetchall()

        matchups_out = []
        for m in matchups:
            if not m['round_id']:
                continue
            results = db.execute(
                """SELECT p.first_name || ' ' || p.last_name AS player_name,
                          mr.team_id, mr.total_points, mr.hole_points_won, mr.overall_point_won,
                          SUM(hs.gross_score) AS gross_score
                   FROM match_results mr
                   JOIN players p ON mr.player_id = p.player_id
                   JOIN scorecards sc ON sc.player_id = mr.player_id AND sc.round_id = %s
                   JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
                   WHERE mr.matchup_id = %s
                   GROUP BY mr.player_id, p.first_name, p.last_name, mr.team_id,
                            mr.total_points, mr.hole_points_won, mr.overall_point_won
                   ORDER BY mr.team_id""",
                (m['round_id'], m['matchup_id'])
            ).fetchall()

            matchups_out.append({
                'matchup_id':  m['matchup_id'],
                'team1_name':  m['team1_name'],
                'team2_name':  m['team2_name'],
                'course_name': m['course_name'],
                'tee_name':    m['tee_name'],
                'round_id':    m['round_id'],
                'round_date':  m['round_date'],
                'results': [{
                    'player_name':    r['player_name'],
                    'team_id':        r['team_id'],
                    'gross_score':    r['gross_score'],
                    'total_points':   float(r['total_points'] or 0),
                    'hole_points':    float(r['hole_points_won'] or 0),
                    'overall_point':  float(r['overall_point_won'] or 0),
                } for r in results],
            })

        if matchups_out:
            weeks_out.append({
                'week_number':    wk,
                'scheduled_date': wr['scheduled_date'],
                'matchups':       matchups_out,
            })

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'weeks':       weeks_out,
    })


@bp.route('/apns/register', methods=['POST'])
@require_jwt
def api_apns_register():
    """POST {device_token} — upsert APNs device token for the current user."""
    data         = request.get_json(force=True, silent=True) or {}
    device_token = (data.get('device_token') or '').strip()
    if not device_token:
        return _err('device_token is required.', 400)

    db      = get_db()
    user_id = g.jwt_user_id
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        db.execute(
            """INSERT INTO apns_tokens (user_id, token, updated_at)
               VALUES (%s, %s, %s)
               ON CONFLICT (user_id) DO UPDATE SET token = EXCLUDED.token, updated_at = EXCLUDED.updated_at""",
            (user_id, device_token, now_str)
        )
        db.commit()
    except Exception:
        # Table may not exist yet on older deploys
        return _err('APNs token registration unavailable.', 503)

    return jsonify({'status': 'registered'}), 200
