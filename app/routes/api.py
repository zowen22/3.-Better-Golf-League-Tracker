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
  GET  /api/v1/contests/winners                     contest winners (detail/summary/low_score/skins)
  GET  /api/v1/dues                                 dues status + my payments
  GET  /api/v1/announcements                         active + expired announcements
  POST /api/v1/subs/request                          request a sub for a matchup
  POST /api/v1/subs/<request_id>/cancel               cancel my sub request
  GET  /api/v1/subs/mine                              my sub requests
  GET  /api/v1/availability                           my availability for a season
  POST /api/v1/availability                           upsert my availability for one week
  GET  /api/v1/playoffs                                bracket for a season
  POST /api/v1/admin/playoffs/matchup/<id>/result       save playoff matchup result (admin)
  GET  /api/v1/matchups/<id>/overrides                  active point overrides for a matchup
  POST /api/v1/admin/matchups/<id>/override-points       set a points override (admin)
  POST /api/v1/admin/matchups/<id>/override-points/<pid>/clear  clear a points override (admin)
  POST /api/v1/admin/week-exclusions/<season_id>/<week>  save week exclusion flags (admin)
  GET  /api/v1/admin/handicap/matrix                     handicap matrix (admin)
  POST /api/v1/admin/handicap/rebuild                    preview/commit handicap rebuild (admin)
  POST /api/v1/admin/handicap/history/<id>/override      override a handicap index (admin)
  POST /api/v1/admin/handicap/history/<id>/clear         clear a handicap override (admin)
  GET/POST/PUT/DELETE /api/v1/admin/contests[/<id>]       contests CRUD (admin)
  POST /api/v1/admin/contests/<id>/calculate[-all]        calculate contest results (admin)
  GET/POST/PUT/DELETE /api/v1/admin/announcements[/<id>]  announcements CRUD (admin)
  POST /api/v1/admin/announcements/<id>/toggle            toggle announcement active (admin)
  GET  /api/v1/admin/subs/pending                         pending sub requests (admin)
  POST /api/v1/admin/subs/<id>/assign                     assign a sub (admin)
  POST /api/v1/admin/subs/<id>/dismiss                    dismiss a sub request (admin)
"""
import secrets
import functools
from flask import Blueprint, jsonify, request, g
from werkzeug.security import check_password_hash
from database import get_db
from jwt_utils import create_token, decode_token, require_jwt, require_jwt_admin
import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from routes.scores import apply_point_overrides

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
            'team_name':  r['team_name'] or f"{r['p1_last']} & {r['p2_last']}",
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
    """GET — returns current user profile."""
    db = get_db()
    user = db.execute(
        'SELECT first_name, last_name, email FROM users WHERE user_id = %s',
        (g.jwt_user_id,)
    ).fetchone()
    league = db.execute(
        'SELECT league_name FROM leagues WHERE league_id = %s',
        (g.jwt_league_id,)
    ).fetchone()
    display_name = ''
    if user and user['first_name']:
        display_name = f"{user['first_name']} {user['last_name']}".strip()

    # Current handicap index for linked player
    from routes.handicap import PRE_ELIGIBILITY_MARKER_PREFIX
    handicap_index = None
    handicap_index_provisional = False
    hcp_history = []
    if g.jwt_player_id:
        hcp_row = db.execute(
            "SELECT handicap_index, override_reason FROM handicap_history "
            "WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1",
            (g.jwt_player_id,)
        ).fetchone()
        if hcp_row:
            handicap_index = float(hcp_row['handicap_index'])
            handicap_index_provisional = bool(
                hcp_row['override_reason'] and
                hcp_row['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))
        else:
            p_row = db.execute(
                "SELECT starting_handicap FROM players WHERE player_id = %s",
                (g.jwt_player_id,)
            ).fetchone()
            if p_row and p_row['starting_handicap'] is not None:
                handicap_index = float(p_row['starting_handicap'])

        hist = db.execute(
            "SELECT handicap_index, calculated_date FROM handicap_history "
            "WHERE player_id = %s ORDER BY calculated_date ASC, handicap_id ASC LIMIT 20",
            (g.jwt_player_id,)
        ).fetchall()
        hcp_history = [
            {'index': float(h['handicap_index']), 'date': str(h['calculated_date'])}
            for h in hist
        ]

    # Current season info
    season = _current_season(db, g.jwt_league_id)

    return jsonify({
        'user_id':        g.jwt_user_id,
        'league_id':      g.jwt_league_id,
        'role':           g.jwt_role,
        'player_id':      g.jwt_player_id,
        'display_name':   display_name,
        'email':          user['email'] if user else '',
        'league_name':    league['league_name'] if league else '',
        'handicap_index': handicap_index,
        'handicap_index_provisional': handicap_index_provisional,
        'hcp_history':    hcp_history,
        'season_id':      season['season_id']   if season else None,
        'season_name':    season['season_name'] if season else None,
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
            te.tee_name, te.nine AS tee_nine,
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
                'tee_nine':       r['tee_nine'],
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
            'tee_nine':      r['tee_nine'],
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

    # Per-week exclusion flags (Stats/Handicap/Points), member-visible
    # transparency — mirrors week_exclusions.get_week_exclusion() exactly,
    # one query per week already present in the schedule (no new week set).
    from routes.week_exclusions import get_week_exclusion
    for wn, week in weeks.items():
        wx = get_week_exclusion(db, season_id, wn)
        week['week_exclusion'] = {
            'exclude_stats':    bool(wx['exclude_stats']),
            'exclude_handicap': bool(wx['exclude_handicap']),
            'exclude_points':   bool(wx['exclude_points']),
            'reason':           wx['reason'],
        } if wx else None

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
               c.course_name, te.tee_name, te.nine AS tee_nine,
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
        "SELECT round_id, locked FROM rounds WHERE matchup_id = %s", (matchup_id,)
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
        'tee_nine':      matchup['tee_nine'],
        'round_id':      round_row['round_id'] if round_row else None,
        'is_locked':     bool(round_row['locked']) if round_row else False,
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


@bp.route('/seasons/list')
@require_jwt
def mobile_seasons_list():
    """All seasons for the JWT's league, newest first."""
    db = get_db()
    rows = db.execute(
        "SELECT season_id, season_name, start_date, end_date FROM seasons "
        "WHERE league_id = %s ORDER BY season_id DESC",
        (g.jwt_league_id,)
    ).fetchall()
    current = _current_season(db, g.jwt_league_id)
    return jsonify({
        'current_season_id': current['season_id'] if current else None,
        'seasons': [
            {
                'season_id':   r['season_id'],
                'season_name': r['season_name'],
                'start_date':  str(r['start_date']) if r['start_date'] else None,
                'end_date':    str(r['end_date'])   if r['end_date']   else None,
            }
            for r in rows
        ],
    })


@bp.route('/seasons/<int:season_id>/standings/mobile')
@require_jwt
def mobile_season_standings(season_id):
    """Standings for a specific season (JWT-protected)."""
    db = get_db()
    league_id = g.jwt_league_id
    season = _season_for_league(db, season_id, league_id)
    if not season:
        return _err('Season not found.', 404)

    rows = db.execute(
        """
        SELECT t.team_id, t.team_name,
               p1.first_name || ' ' || p1.last_name AS p1_name,
               p2.first_name || ' ' || p2.last_name AS p2_name,
               COALESCE(SUM(mr.total_points), 0) AS total_points,
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
            'rank':          i,
            'team_id':       r['team_id'],
            'team_name':     r['team_name'] or f"{r['p1_name']} / {r['p2_name']}",
            'p1_name':       r['p1_name'],
            'p2_name':       r['p2_name'],
            'total_points':  round(float(r['total_points']), 1),
            'rounds_played': r['rounds_played'],
            'wins':          r['wins'],
            'losses':        r['losses'],
            'ties':          r['ties'],
        })

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'standings':   standings,
    })


@bp.route('/standings/podium')
@require_jwt
def mobile_podium():
    """Top 3 teams for the current season — used for the shareable podium graphic."""
    db = get_db()
    season = _current_season(db, g.jwt_league_id)
    if not season:
        return jsonify({'podium': [], 'season_id': None})

    season_id = season['season_id']

    league = db.execute(
        'SELECT league_name FROM leagues WHERE league_id = %s', (g.jwt_league_id,)
    ).fetchone()

    rows = db.execute(
        """
        SELECT
            t.team_id, t.team_name,
            p1.last_name AS p1_last,
            p2.last_name AS p2_last,
            COALESCE(SUM(mr.total_points), 0) AS total_points,
            COALESCE(SUM(CASE WHEN mr.overall_point_won >= 1.0 THEN 1 ELSE 0 END), 0) AS wins,
            COALESCE(SUM(CASE WHEN mr.overall_point_won  = 0.0 THEN 1 ELSE 0 END), 0) AS losses,
            COALESCE(SUM(CASE WHEN mr.overall_point_won  > 0.0
                               AND mr.overall_point_won  < 1.0 THEN 1 ELSE 0 END), 0) AS ties
        FROM teams t
        JOIN players p1 ON p1.player_id = t.player1_id
        JOIN players p2 ON p2.player_id = t.player2_id
        LEFT JOIN match_results mr ON mr.team_id = t.team_id AND mr.matchup_id IN (
            SELECT matchup_id FROM matchups WHERE season_id = %s
        )
        WHERE t.season_id = %s
        GROUP BY t.team_id, t.team_name, p1.last_name, p2.last_name
        ORDER BY total_points DESC
        LIMIT 10
        """,
        (season_id, season_id)
    ).fetchall()

    podium = []
    prev_pts, pos = None, 0
    for i, r in enumerate(rows):
        if r['total_points'] != prev_pts:
            pos = i + 1
            prev_pts = r['total_points']
        name_parts = [n for n in [r['p1_last'], r['p2_last']] if n]
        podium.append({
            'position':     pos,
            'team_label':   r['team_name'] or ' / '.join(name_parts),
            'total_points': round(float(r['total_points']), 1),
            'wins':         r['wins'],
            'losses':       r['losses'],
            'ties':         r['ties'],
        })

    return jsonify({
        'season_id':   season_id,
        'season_name': season['season_name'],
        'league_name': league['league_name'] if league else '',
        'podium':      podium,
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
                  COALESCE(NULLIF(t.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name
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
                      hs.score_differential, h.par, h.handicap_index
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

        ph = sc['handicap_at_time_of_play'] or 0
        total_holes = len(holes) or 9

        _hole_hcp_idxs = [h['handicap_index'] for h in holes]

        def _strokes_on_hole(hole_hcp_index):
            return strokes_on_hole(ph, hole_hcp_index, total_holes,
                                   hcp_indices=_hole_hcp_idxs)

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
                    'strokes_received':   _strokes_on_hole(h['handicap_index']),
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
        diff_match_hole_points,
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
        p_hcp_idxs = [h['handicap_index'] for h in p_holes]
        net[pid] = [gross[pid][i] - strokes_on_hole(ph, h['handicap_index'], total_holes=len(p_holes),
                                                     hcp_indices=p_hcp_idxs)
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
            # Hole-by-hole: differential stroke allocation (only the higher-
            # handicap player gets strokes). Overall: absolute net (net[]).
            return diff_match_hole_points(gross[pid_x], gross[pid_y], p_holes_x,
                                           playing_hcps[pid_x], playing_hcps[pid_y],
                                           net[pid_x], net[pid_y])

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
    apply_point_overrides(db, matchup_id)

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

    try:
        from push import send_to_league
        wk = matchup['week_number']
        send_to_league(db, league_id,
                       title=f"Week {wk} Scores Are In",
                       body="Tap to view the latest results.",
                       data={"matchup_id": matchup_id})
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


@bp.route('/courses')
@require_jwt
def api_courses():
    """GET /api/v1/courses — courses with tees grouped by color.

    Each tee_color entry has a 'tees' dict keyed by nine ('front'/'back'/'full'),
    so the iOS app can show one picker entry per color and resolve to the correct
    tee_id using matchup.tee_nine at submission time.

    Dedup rule (mirrors web score entry): one entry per unique color per course,
    M gender tee preferred as representative when M and W share a color.
    """
    db = get_db()
    courses = db.execute(
        "SELECT course_id, course_name FROM courses ORDER BY course_name"
    ).fetchall()

    result = []
    for c in courses:
        tees = db.execute(
            """SELECT tee_id, tee_name, tee_color, nine, gender
               FROM tees WHERE course_id = %s ORDER BY gender, tee_name, nine""",
            (c['course_id'],)
        ).fetchall()

        # Load holes for every tee upfront
        holes_by_tee = {}
        for t in tees:
            rows = db.execute(
                "SELECT hole_number, par, handicap_index FROM holes WHERE tee_id = %s ORDER BY hole_number",
                (t['tee_id'],)
            ).fetchall()
            if rows:
                holes_by_tee[t['tee_id']] = [
                    {'hole_number': h['hole_number'], 'par': h['par'], 'hcp_index': h['handicap_index']}
                    for h in rows
                ]

        # Group by color; prefer M representative per color per nine
        # color_map: color → nine → best tee row
        color_map = {}   # color → {nine → tee row}
        color_order = [] # preserve first-seen order
        for t in tees:
            if t['tee_id'] not in holes_by_tee:
                continue  # skip tees with no hole data
            color = (t['tee_color'] or t['tee_name'] or '').strip()
            if not color:
                continue
            nine = t['nine'] or 'full'
            if color not in color_map:
                color_map[color] = {}
                color_order.append(color)
            existing = color_map[color].get(nine)
            if existing is None:
                color_map[color][nine] = t
            elif (t['gender'] or 'M').upper() == 'M' and (existing['gender'] or 'M').upper() != 'M':
                color_map[color][nine] = t  # promote M over W

        flat_tees = []
        for color in color_order:
            for nine, t in color_map[color].items():
                flat_tees.append({
                    'tee_id':   t['tee_id'],
                    'tee_name': color,
                    'nine':     nine if nine != 'full' else None,
                    'holes':    holes_by_tee[t['tee_id']],
                })

        if flat_tees:
            result.append({
                'course_id':   c['course_id'],
                'course_name': c['course_name'],
                'tees':        flat_tees,
            })

    return jsonify({'courses': result})


@bp.route('/self-report/submit', methods=['POST'])
@require_jwt
def api_self_report_submit():
    """
    POST {matchup_id, tee_id, round_date?,
          scores: [{player_id, hole_scores: [int, ...]}]}
    → {submission_id, status}
    Creates a pending score submission for admin review.
    """
    from datetime import datetime as _dt
    data       = request.get_json(force=True, silent=True) or {}
    league_id  = g.jwt_league_id
    user_id    = g.jwt_user_id
    matchup_id = data.get('matchup_id')
    tee_id     = data.get('tee_id')

    if not matchup_id or not tee_id:
        return _err('matchup_id and tee_id are required.', 400)

    db = get_db()

    matchup = db.execute(
        """SELECT m.*, s.season_id FROM matchups m
           JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = %s AND s.league_id = %s""",
        (matchup_id, league_id)
    ).fetchone()
    if not matchup:
        return _err('Matchup not found.', 404)
    if matchup['status'] == 'completed':
        return _err('Scores for this matchup have already been recorded.', 409)

    tee_row = db.execute("SELECT course_id FROM tees WHERE tee_id = %s", (tee_id,)).fetchone()
    if not tee_row:
        return _err('Tee not found.', 404)

    season_id  = matchup['season_id']
    round_date = (data.get('round_date') or '').strip() or _dt.now().strftime('%Y-%m-%d')
    now_str    = _dt.now().strftime('%Y-%m-%d %H:%M:%S')

    # Resolve submitter name from user_id
    submitter_row = db.execute(
        "SELECT first_name || ' ' || last_name AS name FROM players WHERE user_id = %s AND league_id = %s",
        (user_id, league_id)
    ).fetchone()
    submitter = submitter_row['name'] if submitter_row else f"User {user_id}"

    sub_id = db.execute(
        """INSERT INTO score_submissions
           (matchup_id, season_id, player_id, submitter_name, course_id, tee_id, round_date, submitted_at, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
           RETURNING submission_id""",
        (matchup_id, season_id, None, submitter, tee_row['course_id'], tee_id, round_date, now_str)
    ).fetchone()['submission_id']

    for entry in (data.get('scores') or []):
        pid    = entry.get('player_id')
        holes  = entry.get('hole_scores') or []
        for i, gross in enumerate(holes):
            db.execute(
                """INSERT INTO score_submission_details
                   (submission_id, player_id, hole_number, gross_score)
                   VALUES (%s, %s, %s, %s)""",
                (sub_id, pid, i + 1, int(gross))
            )

    db.commit()

    try:
        from push import send_to_admins
        wk = matchup['week_number']
        send_to_admins(db, league_id,
                       title="New Score Submission",
                       body=f"{submitter} submitted scores for Week {wk} — tap to review.")
    except Exception:
        pass

    return jsonify({'submission_id': sub_id, 'status': 'pending'}), 201


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
                  COALESCE(NULLIF(t1.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t1.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t1.player2_id)) AS team1_name,
                  COALESCE(NULLIF(t2.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t2.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t2.player2_id)) AS team2_name
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
        diff_match_hole_points,
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
    _hcp_idxs_api = [h['handicap_index'] for h in holes]
    net = {p['player_id']: [gross_ordered[p['player_id']][i] -
                             strokes_on_hole(playing_hcps[p['player_id']], h['handicap_index'],
                                            total_holes=len(holes), hcp_indices=_hcp_idxs_api)
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
            # Hole-by-hole: differential stroke allocation (only the higher-
            # handicap player gets strokes). Overall: absolute net (net[]).
            return diff_match_hole_points(gross_ordered[pid_x], gross_ordered[pid_y], holes,
                                           playing_hcps[pid_x], playing_hcps[pid_y],
                                           net[pid_x], net[pid_y])

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
    apply_point_overrides(db, sub['matchup_id'])

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

    try:
        from push import send_to_league
        wk = sub['week_number']
        send_to_league(db, league_id,
                       title=f"Week {wk} Scores Are In",
                       body="Tap to view the latest results.",
                       data={"matchup_id": sub['matchup_id']})
    except Exception:
        pass

    return jsonify({'round_id': round_id, 'submission_id': submission_id, 'status': 'approved'}), 201


@bp.route('/admin/lock/<int:matchup_id>', methods=['POST'])
@require_jwt_admin
def api_admin_lock(matchup_id):
    """POST — toggle lock on a completed round. Returns {locked: bool}."""
    db = get_db()
    league_id = g.jwt_league_id
    round_row = db.execute(
        """SELECT r.round_id, r.locked
           FROM rounds r
           JOIN matchups m ON r.matchup_id = m.matchup_id
           JOIN seasons  s ON m.season_id   = s.season_id
           WHERE r.matchup_id = %s AND s.league_id = %s""",
        (matchup_id, league_id)
    ).fetchone()
    if not round_row:
        return _err('No completed round found for this matchup.', 404)
    new_locked = not bool(round_row['locked'])
    db.execute("UPDATE rounds SET locked = %s WHERE round_id = %s",
               (new_locked, round_row['round_id']))
    db.commit()
    return jsonify({'round_id': round_row['round_id'], 'locked': new_locked})


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
                  COALESCE(NULLIF(t.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                  vrg.total_gross, vrg.scheduled_date AS round_date, vrg.week_number
           FROM valid_round_gross vrg
           JOIN players p ON vrg.player_id = p.player_id
           JOIN teams t   ON vrg.team_id   = t.team_id
           WHERE vrg.season_id = %s
           ORDER BY vrg.total_gross ASC LIMIT 5""",
        (season_id,)
    ).fetchall()

    high_pts = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  COALESCE(NULLIF(t.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                  mr.total_points, m.week_number, r.round_date
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
                  COALESCE(NULLIF(t.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                  COUNT(*) AS wins
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           JOIN players p  ON mr.player_id  = p.player_id
           JOIN teams t    ON mr.team_id    = t.team_id
           LEFT JOIN match_results opp ON opp.matchup_id = mr.matchup_id AND opp.player_id != mr.player_id AND opp.team_id != mr.team_id
           WHERE m.season_id = %s AND mr.total_points > opp.total_points
           GROUP BY mr.player_id, p.first_name, p.last_name, t.team_name, t.player1_id, t.player2_id
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
                      COALESCE(NULLIF(t.team_name, ''),
                          (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                          (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                      vrg.total_gross, vrg.scheduled_date AS round_date, vrg.week_number
               FROM valid_round_gross vrg
               JOIN players p ON vrg.player_id = p.player_id
               JOIN teams t   ON vrg.team_id   = t.team_id
               WHERE vrg.season_id = %s
               ORDER BY vrg.total_gross """ + order + " LIMIT 5",
            (season_id,)
        ).fetchall()

    high_pts = db.execute(
        """SELECT p.first_name || ' ' || p.last_name AS player_name,
                  COALESCE(NULLIF(t.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                  mr.total_points, m.week_number, r.round_date
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
                  COALESCE(NULLIF(t.team_name, ''),
                      (SELECT last_name FROM players WHERE player_id = t.player1_id) || ' & ' ||
                      (SELECT last_name FROM players WHERE player_id = t.player2_id)) AS team_name,
                  mr.total_points, m.week_number, r.round_date
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
                      COALESCE(NULLIF(t1.team_name, ''),
                          (SELECT last_name FROM players WHERE player_id = t1.player1_id) || ' & ' ||
                          (SELECT last_name FROM players WHERE player_id = t1.player2_id)) AS team1_name,
                      COALESCE(NULLIF(t2.team_name, ''),
                          (SELECT last_name FROM players WHERE player_id = t2.player1_id) || ' & ' ||
                          (SELECT last_name FROM players WHERE player_id = t2.player2_id)) AS team2_name,
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


# ---------------------------------------------------------------------------
# Handicap detail  (all authenticated users)
# ---------------------------------------------------------------------------

@bp.route('/players/league')
@require_jwt
def mobile_league_players():
    """All active players in the league with current handicap index."""
    db = get_db()
    rows = db.execute(
        """SELECT p.player_id, p.first_name, p.last_name,
                  COALESCE(hh.handicap_index, p.starting_handicap) AS handicap_index
           FROM players p
           LEFT JOIN LATERAL (
               SELECT handicap_index FROM handicap_history
               WHERE player_id = p.player_id
               ORDER BY calculated_date DESC, handicap_id DESC
               LIMIT 1
           ) hh ON true
           WHERE p.league_id = %s AND p.active = 1
           ORDER BY p.last_name, p.first_name""",
        (g.jwt_league_id,)
    ).fetchall()

    players = [
        {
            'player_id':      r['player_id'],
            'display_name':   f"{r['first_name']} {r['last_name']}",
            'first_name':     r['first_name'],
            'last_name':      r['last_name'],
            'handicap_index': float(r['handicap_index']) if r['handicap_index'] is not None else None,
        }
        for r in rows
    ]
    return jsonify({'players': players})


@bp.route('/players/<int:player_id>/handicap-detail')
@require_jwt
def mobile_handicap_detail(player_id):
    """Full handicap calculation breakdown for one player."""
    db = get_db()
    league_id = g.jwt_league_id

    player = db.execute(
        "SELECT player_id, first_name, last_name, starting_handicap, oldest_score_date "
        "FROM players WHERE player_id = %s AND league_id = %s",
        (player_id, league_id)
    ).fetchone()
    if not player:
        return _err('Player not found.', 404)

    season = _current_season(db, league_id)
    season_id = season['season_id'] if season else None

    from routes.handicap import _get_settings
    s = _get_settings(db, season_id, league_id) if season_id else {}

    min_rounds    = int(s.get('min_rounds_for_handicap', 2))
    rounds_to_avg = int(s.get('rounds_to_average', 4))
    high_drop     = int(s.get('high_scores_to_drop', 1))
    low_drop      = int(s.get('low_scores_to_drop', 0))
    padding       = int(s.get('padding_score_count', 0))
    hcp_pct       = float(s.get('handicap_percent', 90.0))
    max_hcp       = float(s.get('max_handicap_index', 18.0))
    neg_allowed   = bool(s.get('negative_handicap_allowed', 1))
    carry_across  = bool(s.get('carry_scores_across_seasons', 1))

    window = rounds_to_avg + high_drop + low_drop
    oldest_date = player['oldest_score_date']

    q = """
        SELECT r.round_id, r.round_date, r.season_id,
               SUM(hs.gross_score) AS total_gross,
               t.par_total,
               c.course_name, t.tee_name,
               sn.season_name,
               m.week_number
          FROM scorecards sc
          JOIN rounds      r  ON sc.round_id     = r.round_id
          JOIN tees        t  ON r.tee_id         = t.tee_id
          JOIN hole_scores hs ON hs.scorecard_id  = sc.scorecard_id
          JOIN seasons     sn ON r.season_id      = sn.season_id
          JOIN matchups    m  ON r.matchup_id     = m.matchup_id
          LEFT JOIN courses c ON r.course_id      = c.course_id
         WHERE sc.player_id = %s AND sn.league_id = %s
           AND m.status = 'completed'
           AND sc.is_absent = 0
    """
    params = [player_id, league_id]
    if not carry_across and season_id:
        q += " AND r.season_id = %s"
        params.append(season_id)
    if oldest_date:
        q += " AND r.round_date >= %s"
        params.append(oldest_date)
    q += " GROUP BY sc.scorecard_id ORDER BY r.round_date ASC, r.round_id ASC"

    all_rounds = db.execute(q, params).fetchall()
    real_count = len(all_rounds)

    all_round_data = []
    for rr in all_rounds:
        diff = float(rr['total_gross']) - float(rr['par_total'])
        all_round_data.append({
            'round_id':    rr['round_id'],
            'round_date':  str(rr['round_date']) if rr['round_date'] else None,
            'season_name': rr['season_name'],
            'week_number': rr['week_number'],
            'course_name': rr['course_name'] or '—',
            'tee_name':    rr['tee_name'] or '—',
            'gross':       int(rr['total_gross']),
            'par':         int(rr['par_total']),
            'diff':        round(diff, 1),
            'in_window':   False,
            'status':      'outside',
        })

    window_start_i = max(0, len(all_round_data) - window)
    for i in range(window_start_i, len(all_round_data)):
        all_round_data[i]['in_window'] = True

    window_rounds = all_round_data[window_start_i:]

    pad_entries = []
    if padding > 0 and len(window_rounds) < window:
        n_pads = min(padding, window - len(window_rounds))
        for _ in range(n_pads):
            pad_entries.append({
                'round_id': None, 'round_date': None, 'season_name': '—',
                'week_number': None, 'course_name': 'Scratch Pad',
                'tee_name': '—', 'gross': 0, 'par': 0, 'diff': 0.0,
                'in_window': True, 'status': 'padding',
            })

    combined_window = pad_entries + list(window_rounds)

    if combined_window:
        sorted_idx = sorted(range(len(combined_window)), key=lambda i: combined_window[i]['diff'])
        dropped = set()
        for i in range(low_drop):
            if i < len(sorted_idx):
                dropped.add(sorted_idx[i])
                combined_window[sorted_idx[i]]['status'] = 'dropped_low'
        for i in range(high_drop):
            pos = len(sorted_idx) - 1 - i
            if pos >= 0 and sorted_idx[pos] not in dropped:
                dropped.add(sorted_idx[pos])
                combined_window[sorted_idx[pos]]['status'] = 'dropped_high'
        for e in combined_window:
            if e['status'] == 'outside':
                e['status'] = 'counting'

    counting_diffs = [e['diff'] for e in combined_window if e['status'] == 'counting']
    has_enough = real_count >= min_rounds
    avg_diff = (sum(counting_diffs) / len(counting_diffs)) if counting_diffs else None
    # Handicap Index is the raw average of counting differentials.
    # handicap_percent and max_handicap_index are NOT applied here; they're
    # applied once, downstream, when converting Index -> Playing Handicap
    # (see calc_playing_handicap in scores.py).
    computed_index = None
    if avg_diff is not None and has_enough:
        computed_index = avg_diff
        if not neg_allowed:
            computed_index = max(computed_index, 0.0)

    from routes.handicap import PRE_ELIGIBILITY_MARKER_PREFIX

    ch_row = db.execute(
        "SELECT handicap_index, calculated_date, override_reason FROM handicap_history "
        "WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1",
        (player_id,)
    ).fetchone()
    current_handicap  = float(ch_row['handicap_index']) if ch_row else (
        float(player['starting_handicap']) if player['starting_handicap'] is not None else None
    )
    last_calc_date = str(ch_row['calculated_date']) if ch_row else None
    current_is_provisional = bool(ch_row and ch_row['override_reason'] and
                                   ch_row['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))

    committee_adjustment = 0.0
    adj_reason = None
    try:
        adj_row = db.execute(
            "SELECT adjustment, reason FROM handicap_adjustments "
            "WHERE player_id = %s AND league_id = %s",
            (player_id, league_id)
        ).fetchone()
        if adj_row:
            committee_adjustment = float(adj_row['adjustment'] or 0)
            adj_reason = adj_row['reason']
    except Exception:
        pass

    hcp_history = db.execute(
        "SELECT handicap_index, calculated_date, override_reason FROM handicap_history "
        "WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 20",
        (player_id,)
    ).fetchall()

    # Effective Index (stored index + committee adjustment) and the Playing
    # Handicap derived from it — mirrors get_player_handicap() +
    # calc_playing_handicap() in scores.py exactly, so this is the same
    # number actually used to score this player's rounds. Provisional
    # pre-eligibility rows already store a final playing handicap — do NOT
    # run them through calc_playing_handicap again.
    from routes.scores import calc_playing_handicap
    if current_is_provisional:
        effective_index = current_handicap
        playing_handicap = current_handicap
    else:
        effective_index = (current_handicap or 0) + committee_adjustment
        playing_handicap = calc_playing_handicap(effective_index, hcp_pct, max_hcp) \
            if current_handicap is not None else None

    return jsonify({
        'player_id':            player_id,
        'display_name':         f"{player['first_name']} {player['last_name']}",
        'current_handicap':     current_handicap,
        'current_is_provisional': current_is_provisional,
        'last_calc_date':       last_calc_date,
        'computed_index':       computed_index,
        'committee_adjustment': committee_adjustment,
        'adj_reason':           adj_reason,
        'effective_index':      effective_index,
        'playing_handicap':     playing_handicap,
        'real_count':           real_count,
        'has_enough':           has_enough,
        'settings': {
            'min_rounds':    min_rounds,
            'rounds_to_avg': rounds_to_avg,
            'high_drop':     high_drop,
            'low_drop':      low_drop,
            'padding':       padding,
            'hcp_pct':       hcp_pct,
            'max_hcp':       max_hcp,
            'window':        window,
        },
        'rounds':           list(reversed(all_round_data)),
        'combined_window':  list(reversed(combined_window)),
        'hcp_history':      [
            {'index': float(h['handicap_index']), 'date': str(h['calculated_date']),
             'is_provisional': bool(h['override_reason'] and
                                     h['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))}
            for h in hcp_history
        ],
    })


# ---------------------------------------------------------------------------
# Skins  GET /api/v1/skins
# ---------------------------------------------------------------------------

@bp.route('/skins', methods=['GET'])
@require_jwt
def mobile_skins():
    """Season skins results — grouped by week."""
    db = get_db()

    season = db.execute(
        "SELECT * FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (g.jwt_league_id,)
    ).fetchone()
    if not season:
        return _err('No season found.', 404)

    from database import load_nicknames, player_display_name
    nicknames = load_nicknames(db, g.jwt_league_id)

    # Skins are whole-week (per @user 2026-08-17) -- skins_results carries
    # season_id/week_number directly, no round/matchup join needed for that
    # part. (This endpoint previously selected sr.pot_amount/carry_in_amount/
    # is_carryover, which were never real columns on skins_results -- fixed
    # here to the columns that actually exist, payout/carried_over; a
    # pre-existing bug unrelated to the whole-week change, not something the
    # old per-round shape ever made work either.)
    results = db.execute(
        """SELECT sr.hole_number, sr.payout, sr.carried_over,
                  sr.winner_player_id, sr.week_number,
                  p.first_name, p.last_name
           FROM skins_results sr
           LEFT JOIN players p ON p.player_id = sr.winner_player_id
           WHERE sr.season_id = %s
           ORDER BY sr.week_number, sr.hole_number""",
        (season['season_id'],)
    ).fetchall()

    # Course/date context per week, for display -- any one round from that
    # week (they should all share the same course/tee).
    week_info_rows = db.execute(
        """SELECT DISTINCT ON (m.week_number) m.week_number, r.round_date, c.course_name, te.tee_name
           FROM matchups m
           JOIN rounds r ON r.matchup_id = m.matchup_id
           LEFT JOIN courses c ON c.course_id = r.course_id
           LEFT JOIN tees te ON te.tee_id = r.tee_id
           WHERE m.season_id = %s
           ORDER BY m.week_number, r.round_id""",
        (season['season_id'],)
    ).fetchall()
    info_by_week = {row['week_number']: row for row in week_info_rows}

    # Group by week
    from collections import defaultdict
    weeks = defaultdict(list)
    for row in results:
        weeks[row['week_number']].append({
            'hole':          row['hole_number'],
            'payout':        float(row['payout'] or 0),
            'is_carryover':  bool(row['carried_over']),
            'winner_id':     row['winner_player_id'],
            'winner_name':   player_display_name(
                                 row['winner_player_id'],
                                 row['first_name'], row['last_name'],
                                 nicknames) if row['winner_player_id'] else None,
        })

    week_list = []
    for wk, skins in sorted(weeks.items()):
        info = info_by_week.get(wk)
        week_list.append({
            'week': wk,
            'round_date': str(info['round_date']) if info and info['round_date'] else None,
            'course_name': info['course_name'] if info else None,
            'tee_name': info['tee_name'] if info else None,
            'skins': skins,
        })

    return jsonify({'season_name': season['season_name'], 'weeks': week_list})


# ---------------------------------------------------------------------------
# League Board  GET/POST /api/v1/board  POST /api/v1/board/<id>/react
# ---------------------------------------------------------------------------

@bp.route('/board', methods=['GET'])
@require_jwt
def mobile_board_list():
    """Fetch league announcements newest-first, with reaction counts."""
    db = get_db()
    posts = db.execute(
        """SELECT a.announcement_id, a.body, a.created_at, a.is_pinned,
                  u.display_name AS author_name
           FROM league_announcements a
           JOIN users u ON u.user_id = a.author_user_id
           WHERE a.league_id = %s
           ORDER BY a.is_pinned DESC, a.created_at DESC
           LIMIT 50""",
        (g.jwt_league_id,)
    ).fetchall()

    result = []
    for p in posts:
        reactions = db.execute(
            """SELECT emoji, COUNT(*) AS cnt,
                      bool_or(user_id = %s) AS i_reacted
               FROM announcement_reactions
               WHERE announcement_id = %s
               GROUP BY emoji""",
            (g.jwt_user_id, p['announcement_id'])
        ).fetchall()
        result.append({
            'id':          p['announcement_id'],
            'body':        p['body'],
            'created_at':  str(p['created_at']),
            'is_pinned':   bool(p['is_pinned']),
            'author_name': p['author_name'],
            'reactions':   [{'emoji': r['emoji'], 'count': r['cnt'], 'i_reacted': bool(r['i_reacted'])} for r in reactions],
        })

    return jsonify({'posts': result})


@bp.route('/board', methods=['POST'])
@require_jwt_admin
def mobile_board_post():
    """Admin creates a new announcement."""
    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return _err('body required', 400)
    is_pinned = bool(data.get('is_pinned', False))
    db = get_db()
    db.execute(
        """INSERT INTO league_announcements (league_id, author_user_id, body, is_pinned)
           VALUES (%s, %s, %s, %s)""",
        (g.jwt_league_id, g.jwt_user_id, body, is_pinned)
    )
    db.connection.commit()
    return jsonify({'ok': True}), 201


@bp.route('/board/<int:post_id>/react', methods=['POST'])
@require_jwt
def mobile_board_react(post_id):
    """Toggle an emoji reaction on an announcement."""
    data = request.get_json(silent=True) or {}
    emoji = (data.get('emoji') or '').strip()
    if not emoji:
        return _err('emoji required', 400)
    db = get_db()
    existing = db.execute(
        "SELECT reaction_id FROM announcement_reactions WHERE announcement_id = %s AND user_id = %s AND emoji = %s",
        (post_id, g.jwt_user_id, emoji)
    ).fetchone()
    if existing:
        db.execute("DELETE FROM announcement_reactions WHERE reaction_id = %s", (existing['reaction_id'],))
    else:
        db.execute(
            "INSERT INTO announcement_reactions (announcement_id, user_id, emoji) VALUES (%s, %s, %s)",
            (post_id, g.jwt_user_id, emoji)
        )
    db.connection.commit()
    return jsonify({'ok': True})


# ===========================================================================
# Mobile: Contests Winners  GET /api/v1/contests/winners
# Mirrors routes/contests.py's winners_detail() / winners_summary() /
# winners_low_score() / winners_skins(), dispatched on ?type=.
# ===========================================================================

@bp.route('/contests/winners')
@require_jwt
def api_contests_winners():
    from routes.contests import CONTEST_TYPES

    db = get_db()
    league_id = g.jwt_league_id
    win_type = (request.args.get('type') or 'detail').strip()
    season_id = request.args.get('season_id', type=int)

    if win_type == 'detail':
        contest_type = request.args.get('contest_type', '').strip() or None
        week_num = request.args.get('week_num', type=int)
        player_id = request.args.get('player_id', type=int)
        team_id = request.args.get('team_id', type=int)

        where = ["c.league_id = %(league_id)s"]
        params = {'league_id': league_id}
        if season_id:
            where.append("c.season_id = %(season_id)s")
            params['season_id'] = season_id
        if contest_type:
            where.append("c.contest_type = %(contest_type)s")
            params['contest_type'] = contest_type
        if week_num is not None:
            where.append("cr.week_num = %(week_num)s")
            params['week_num'] = week_num
        if player_id:
            where.append("cr.player_id = %(player_id)s")
            params['player_id'] = player_id
        if team_id:
            where.append("cr.team_id = %(team_id)s")
            params['team_id'] = team_id

        rows = db.execute(
            f"""SELECT c.name AS contest_name, c.contest_type, c.season_id, s.season_name,
                       cr.week_num, cr.hole_number, cr.distance, cr.amount_won, cr.notes, cr.value_text,
                       p.first_name, p.last_name,
                       COALESCE(NULLIF(t.team_name, ''), tp1.last_name || ' & ' || tp2.last_name) AS team_name,
                       tp1.first_name AS t_p1_first, tp1.last_name AS t_p1_last,
                       tp2.first_name AS t_p2_first, tp2.last_name AS t_p2_last
                  FROM contest_results cr
                  JOIN contests c ON cr.contest_id = c.contest_id
                  JOIN seasons  s ON c.season_id   = s.season_id
                  LEFT JOIN players p   ON p.player_id = cr.player_id
                  LEFT JOIN teams t     ON t.team_id   = cr.team_id
                  LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
                  LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
                 WHERE {' AND '.join(where)}
                 ORDER BY s.season_id DESC, cr.week_num ASC NULLS FIRST, c.contest_id""",
            params
        ).fetchall()

        # Week -> {date, course_name}, same derivation as season_view().
        season_ids = {r['season_id'] for r in rows}
        week_course_map = {}
        for sid in season_ids:
            week_rows = db.execute(
                """SELECT DISTINCT ON (m.week_number) m.week_number, m.scheduled_date, c.course_name
                     FROM matchups m
                     LEFT JOIN courses c ON c.course_id = m.course_id
                    WHERE m.season_id = %s AND m.is_bye = 0
                    ORDER BY m.week_number, m.matchup_id""",
                (sid,)
            ).fetchall()
            for w in week_rows:
                week_course_map[(sid, w['week_number'])] = {'date': w['scheduled_date'], 'course_name': w['course_name']}

        winners = []
        for r in rows:
            wc = week_course_map.get((r['season_id'], r['week_num']))
            player_name = f"{r['first_name']} {r['last_name']}" if r['first_name'] else None
            winners.append({
                'contest_name':  r['contest_name'],
                'contest_type':  r['contest_type'],
                'contest_type_label': dict(CONTEST_TYPES).get(r['contest_type'], r['contest_type']),
                'season_id':     r['season_id'],
                'season_name':   r['season_name'],
                'week_num':      r['week_num'],
                'hole_number':   r['hole_number'],
                'distance':      r['distance'],
                'amount_won':    float(r['amount_won']) if r['amount_won'] is not None else None,
                'notes':         r['notes'],
                'value_text':    r['value_text'],
                'player_name':   player_name,
                'team_name':     r['team_name'],
                'round_date':    str(wc['date']) if wc and wc['date'] else None,
                'course_name':   wc['course_name'] if wc else None,
            })
        return jsonify({'winners': winners})

    elif win_type == 'summary':
        where = ["c.league_id = %(league_id)s", "cr.amount_won IS NOT NULL"]
        params = {'league_id': league_id}
        if season_id:
            where.append("c.season_id = %(season_id)s")
            params['season_id'] = season_id

        rows = db.execute(
            f"""SELECT p.player_id, p.first_name, p.last_name, SUM(cr.amount_won) AS total_won
                  FROM contest_results cr
                  JOIN contests c ON cr.contest_id = c.contest_id
                  JOIN players  p ON p.player_id   = cr.player_id
                 WHERE {' AND '.join(where)}
                 GROUP BY p.player_id, p.first_name, p.last_name
                 ORDER BY total_won DESC""",
            params
        ).fetchall()

        return jsonify({'winners': [
            {
                'player_id': r['player_id'],
                'name':      f"{r['first_name']} {r['last_name']}",
                'total_won': float(r['total_won']),
            }
            for r in rows
        ]})

    elif win_type == 'low_score':
        from routes.email_config import _top_n_with_ties
        from routes.week_exclusions import WEEK_EXCLUSION_FILTER
        wx_stats = WEEK_EXCLUSION_FILTER['stats']

        seasons = db.execute(
            "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
            (league_id,)
        ).fetchall()
        season_ids = [season_id] if season_id else [s['season_id'] for s in seasons]

        weeks = []
        for sid in season_ids:
            week_rows = db.execute(
                ("""SELECT DISTINCT m.week_number, s.season_name
                     FROM matchups m JOIN seasons s ON m.season_id = s.season_id
                    WHERE m.season_id = %s AND m.is_bye = 0 AND m.status = 'completed'
                    """ + wx_stats + """
                    ORDER BY m.week_number"""),
                (sid,)
            ).fetchall()
            for wr in week_rows:
                week_player_rows = db.execute(
                    """SELECT p.first_name, p.last_name, sc.handicap_at_time_of_play,
                              SUM(hs.gross_score) AS total_gross
                         FROM scorecards sc
                         JOIN rounds r ON sc.round_id = r.round_id
                         JOIN matchups m ON r.matchup_id = m.matchup_id
                         JOIN players p ON sc.player_id = p.player_id
                         JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
                        WHERE m.season_id = %s AND m.week_number = %s AND sc.is_absent = 0
                        GROUP BY sc.scorecard_id, p.first_name, p.last_name, sc.handicap_at_time_of_play""",
                    (sid, wr['week_number'])
                ).fetchall()
                players_week = []
                for r in week_player_rows:
                    hcp = int(round(float(r['handicap_at_time_of_play']))) if r['handicap_at_time_of_play'] is not None else 0
                    total_gross = r['total_gross']
                    players_week.append({
                        'name': f"{r['first_name']} {r['last_name']}",
                        'gross': total_gross,
                        'hcp': hcp,
                        'net': total_gross - hcp,
                    })
                if not players_week:
                    continue
                weeks.append({
                    'season_name': wr['season_name'],
                    'week_number': wr['week_number'],
                    'low_gross': _top_n_with_ties(players_week, 'gross', n=1),
                    'low_net': _top_n_with_ties(players_week, 'net', n=1),
                })

        weeks.sort(key=lambda w: (w['season_name'], w['week_number']), reverse=True)
        return jsonify({'weeks': weeks})

    elif win_type == 'skins':
        where = ["s.league_id = %(league_id)s", "sr.winner_player_id IS NOT NULL"]
        params = {'league_id': league_id}
        if season_id:
            where.append("sr.season_id = %(season_id)s")
            params['season_id'] = season_id

        rows = db.execute(
            f"""SELECT sr.winner_player_id, p.first_name, p.last_name,
                       COUNT(*) AS skins_won, SUM(sr.payout) AS total_won
                  FROM skins_results sr
                  JOIN seasons  s ON sr.season_id = s.season_id
                  JOIN players  p ON sr.winner_player_id = p.player_id
                 WHERE {' AND '.join(where)}
                 GROUP BY sr.winner_player_id, p.first_name, p.last_name
                 ORDER BY skins_won DESC""",
            params
        ).fetchall()

        using_default = False
        if not rows:
            from routes.skins import compute_default_skins_totals
            rows = compute_default_skins_totals(db, league_id, season_id)
            using_default = bool(rows)

        return jsonify({
            'winners': [
                {
                    'winner_player_id': r['winner_player_id'],
                    'name':             f"{r['first_name']} {r['last_name']}",
                    'skins_won':        r['skins_won'],
                    'total_won':        float(r['total_won'] or 0),
                }
                for r in rows
            ],
            'using_default': using_default,
        })

    else:
        return _err('Invalid type. Use detail, summary, low_score, or skins.', 400)


# ===========================================================================
# Mobile: Dues  GET /api/v1/dues
# Mirrors routes/dues.py's member_view().
# ===========================================================================

@bp.route('/dues')
@require_jwt
def api_dues():
    db = get_db()
    league_id = g.jwt_league_id
    player_id = g.jwt_player_id

    season_id = request.args.get('season_id', type=int)
    if season_id:
        season = _season_for_league(db, season_id, league_id)
    else:
        season = _current_season(db, league_id)
    if not season:
        return _err('Season not found.', 404)
    season_id = season['season_id']

    settings_row = db.execute(
        "SELECT dues_amount, dues_due_date FROM league_settings WHERE league_id=%s AND season_id=%s",
        (league_id, season_id)
    ).fetchone()
    dues_amount = settings_row['dues_amount'] if settings_row else None
    dues_due_date = settings_row['dues_due_date'] if settings_row else None

    # Active players in this season via teams (for paid/total counts)
    players = db.execute(
        """SELECT DISTINCT p.player_id
           FROM players p
           JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           WHERE t.season_id = %s AND t.league_id = %s AND p.active = 1""",
        (season_id, league_id)
    ).fetchall()

    payments_all = db.execute(
        "SELECT DISTINCT player_id FROM dues_payments WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchall()

    my_payments = []
    if player_id:
        my_payments = db.execute(
            """SELECT payment_id, amount, paid_date, method, notes
               FROM dues_payments
               WHERE season_id = %s AND league_id = %s AND player_id = %s
               ORDER BY paid_date DESC""",
            (season_id, league_id, player_id)
        ).fetchall()

    return jsonify({
        'season_id':     season_id,
        'dues_amount':   float(dues_amount) if dues_amount is not None else None,
        'dues_due_date': str(dues_due_date) if dues_due_date else None,
        'my_paid':       len(my_payments) > 0,
        'my_payments': [
            {
                'payment_id': p['payment_id'],
                'amount':     float(p['amount']),
                'paid_date':  str(p['paid_date']) if p['paid_date'] else None,
                'method':     p['method'],
                'notes':      p['notes'],
            }
            for p in my_payments
        ],
        'paid_count':  len(payments_all),
        'total_count': len(players),
    })


# ===========================================================================
# Mobile: Announcements  GET /api/v1/announcements
# Mirrors routes/announcements.py's index().
# ===========================================================================

@bp.route('/announcements')
@require_jwt
def api_announcements():
    from datetime import date as _date

    db = get_db()
    league_id = g.jwt_league_id
    today = _date.today().isoformat()

    active = db.execute(
        """SELECT * FROM notifications
           WHERE league_id = %s AND active = 1
             AND (display_until IS NULL OR display_until = '' OR display_until >= %s)
           ORDER BY created_date DESC""",
        (league_id, today)
    ).fetchall()

    expired = db.execute(
        """SELECT * FROM notifications
           WHERE league_id = %s AND active = 1
             AND display_until IS NOT NULL AND display_until != '' AND display_until < %s
           ORDER BY display_until DESC
           LIMIT 10""",
        (league_id, today)
    ).fetchall()

    def _notif_json(n):
        return {
            'notification_id': n['notification_id'],
            'type':             n['type'],
            'message':          n['message'],
            'created_date':     str(n['created_date']) if n['created_date'] else None,
            'display_until':    n['display_until'],
        }

    return jsonify({
        'active':  [_notif_json(n) for n in active],
        'expired': [_notif_json(n) for n in expired],
    })


# ===========================================================================
# Mobile: Subs  POST /api/v1/subs/request, POST /api/v1/subs/<id>/cancel,
# GET /api/v1/subs/mine
# Mirrors routes/subs.py's request_sub() and my_requests().
# ===========================================================================

@bp.route('/subs/request', methods=['POST'])
@require_jwt
def api_subs_request():
    db = get_db()
    league_id = g.jwt_league_id
    player_id = g.jwt_player_id

    if not player_id:
        return _err('Your account is not linked to a player.', 403)

    data = request.get_json(force=True, silent=True) or {}
    matchup_id = data.get('matchup_id')
    notes = (data.get('notes') or '').strip()

    if not matchup_id:
        return _err('matchup_id is required.', 400)

    matchup = db.execute(
        """SELECT m.*, s.league_id, s.season_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = %s""",
        (matchup_id,)
    ).fetchone()
    if not matchup or matchup['league_id'] != league_id:
        return _err('Matchup not found.', 404)

    if matchup['is_bye']:
        return _err('Bye weeks do not have sub requests.', 400)

    # Verify this player is actually in this matchup
    team_check = db.execute(
        """SELECT t.team_id FROM teams t
           JOIN matchups m ON (m.team1_id = t.team_id OR m.team2_id = t.team_id)
           WHERE m.matchup_id = %s
             AND (t.player1_id = %s OR t.player2_id = %s)""",
        (matchup_id, player_id, player_id)
    ).fetchone()
    if not team_check:
        return _err('You are not scheduled to play in this matchup.', 400)

    existing = db.execute(
        "SELECT * FROM sub_requests WHERE matchup_id=%s AND player_id=%s AND status='open'",
        (matchup_id, player_id)
    ).fetchone()
    if existing:
        return _err('You already have an open sub request for this matchup.', 409)

    cur = db.execute(
        """INSERT INTO sub_requests
           (league_id, season_id, matchup_id, player_id, notes, status, created_at)
           VALUES (%s, %s, %s, %s, %s, 'open', %s)
           RETURNING request_id, league_id, season_id, matchup_id, player_id, notes, status, created_at""",
        (league_id, matchup['season_id'], matchup_id, player_id, notes or None,
         datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    row = cur.fetchone()
    db.commit()

    return jsonify({'request': {
        'request_id': row['request_id'],
        'matchup_id': row['matchup_id'],
        'season_id':  row['season_id'],
        'notes':      row['notes'],
        'status':     row['status'],
        'created_at': str(row['created_at']) if row['created_at'] else None,
    }}), 201


@bp.route('/subs/<int:request_id>/cancel', methods=['POST'])
@require_jwt
def api_subs_cancel(request_id):
    db = get_db()
    player_id = g.jwt_player_id

    req = db.execute(
        "SELECT * FROM sub_requests WHERE request_id=%s AND league_id=%s AND player_id=%s",
        (request_id, g.jwt_league_id, player_id)
    ).fetchone()
    if not req:
        return _err('Sub request not found.', 404)

    if req['status'] != 'open':
        return _err('Only open requests can be cancelled.', 400)

    db.execute(
        "UPDATE sub_requests SET status='cancelled', updated_at=%s WHERE request_id=%s",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), request_id)
    )
    db.commit()
    return jsonify({'status': 'cancelled'})


@bp.route('/subs/mine')
@require_jwt
def api_subs_mine():
    db = get_db()
    player_id = g.jwt_player_id

    if not player_id:
        return jsonify({'requests': []})

    rows = db.execute(
        """SELECT sr.*,
                  s.season_name,
                  m.week_number, m.scheduled_date,
                  sub.first_name AS sub_first, sub.last_name AS sub_last
           FROM sub_requests sr
           JOIN seasons s ON sr.season_id = s.season_id
           LEFT JOIN matchups m ON sr.matchup_id = m.matchup_id
           LEFT JOIN players sub ON sr.sub_player_id = sub.player_id
           WHERE sr.player_id = %s AND sr.league_id = %s
           ORDER BY sr.created_at DESC""",
        (player_id, g.jwt_league_id)
    ).fetchall()

    requests_json = []
    for r in rows:
        sub_name = f"{r['sub_first']} {r['sub_last']}" if r['sub_first'] else None
        requests_json.append({
            'request_id':      r['request_id'],
            'matchup_id':      r['matchup_id'],
            'week_number':     r['week_number'],
            'status':          r['status'],
            'notes':           r['notes'],
            'sub_player_name': sub_name,
            'admin_notes':     r['admin_notes'],
            'created_at':      str(r['created_at']) if r['created_at'] else None,
        })

    return jsonify({'requests': requests_json})


# ===========================================================================
# Mobile: Availability / RSVP  GET/POST /api/v1/availability
# Mirrors routes/availability.py's my_availability() upsert logic, but one
# week per call instead of a whole-season form POST.
# ===========================================================================

@bp.route('/availability')
@require_jwt
def api_availability_list():
    db = get_db()
    player_id = g.jwt_player_id

    if not player_id:
        return _err('Your account is not linked to a player.', 403)

    season_id = request.args.get('season_id', type=int)
    if not season_id:
        return _err('season_id is required.', 400)

    rows = db.execute(
        """SELECT week_number, available, note FROM player_availability
           WHERE player_id = %s AND league_id = %s AND season_id = %s
           ORDER BY week_number""",
        (player_id, g.jwt_league_id, season_id)
    ).fetchall()

    return jsonify({'availability': [
        {
            'week_number': r['week_number'],
            'available':   bool(r['available']),
            'note':        r['note'] or '',
        }
        for r in rows
    ]})


@bp.route('/availability', methods=['POST'])
@require_jwt
def api_availability_upsert():
    db = get_db()
    player_id = g.jwt_player_id

    if not player_id:
        return _err('Your account is not linked to a player.', 403)

    data = request.get_json(force=True, silent=True) or {}
    season_id = data.get('season_id')
    week_number = data.get('week_number')
    if not season_id or week_number is None:
        return _err('season_id and week_number are required.', 400)

    available = 1 if data.get('available') else 0
    note = (data.get('note') or '').strip()[:200]
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    db.execute(
        """INSERT INTO player_availability
             (player_id, league_id, season_id, week_number, available, note, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT(player_id, league_id, season_id, week_number)
           DO UPDATE SET available=excluded.available, note=excluded.note, updated_at=excluded.updated_at""",
        (player_id, g.jwt_league_id, season_id, week_number, available, note, now)
    )
    db.commit()

    return jsonify({
        'status':      'saved',
        'week_number': week_number,
        'available':   bool(available),
        'note':        note,
    })


# ===========================================================================
# Tier-2 admin/secondary endpoints (Playoffs, Points Override, Week
# Exclusions, Handicap Admin, Contests/Announcements/Subs admin CRUD) —
# mirror the equivalent web routes' business logic exactly. See each web
# module (routes/playoffs.py, routes/scores.py, routes/week_exclusions.py,
# routes/handicap.py, routes/contests.py, routes/announcements.py,
# routes/subs.py) for the source of truth being mirrored here.
# ===========================================================================


# ---------------------------------------------------------------------------
# Playoffs
# ---------------------------------------------------------------------------

@bp.route('/playoffs')
@require_jwt
def mobile_playoffs():
    """Playoff bracket for a season — mirrors playoffs._build_bracket_data().
    Public to any authenticated role, matching the web bracket page."""
    db = get_db()
    league_id = g.jwt_league_id
    season_id = request.args.get('season_id', type=int)
    if not season_id:
        season = _current_season(db, league_id)
        season_id = season['season_id'] if season else None
    if not season_id:
        return jsonify({'rounds': [], 'champion': None})

    from routes.playoffs import _build_bracket_data, _load_teams, _get_team_label

    bracket = db.execute(
        "SELECT * FROM playoff_brackets WHERE season_id = %s AND league_id = %s "
        "ORDER BY bracket_id DESC LIMIT 1",
        (season_id, league_id)
    ).fetchone()
    if not bracket:
        return jsonify({'rounds': [], 'champion': None})

    teams_map = _load_teams(db, season_id, league_id)
    rounds = _build_bracket_data(db, bracket, teams_map)

    def _team_json(team):
        if not team:
            return None
        return {'team_id': team['team_id'], 'label': _get_team_label(team)}

    out_rounds = []
    for rnd in rounds:
        out_rounds.append({
            'round_number': rnd['round_number'],
            'label':        rnd['label'],
            'matchups': [
                {
                    'matchup_id':     m['matchup_id'],
                    'team1':          _team_json(m['team1']),
                    'team2':          _team_json(m['team2']),
                    'team1_points':   m['team1_points'],
                    'team2_points':   m['team2_points'],
                    'winner_team_id': m['winner_team_id'],
                    'is_finals':      bool(m['is_finals']),
                    'week_number':    m['week_number'],
                }
                for m in rnd['matchups']
            ],
        })

    champion = None
    if out_rounds:
        last_round = out_rounds[-1]
        if last_round['matchups'] and last_round['matchups'][0]['winner_team_id']:
            champ_id = last_round['matchups'][0]['winner_team_id']
            champion = _team_json(teams_map.get(champ_id))

    return jsonify({'rounds': out_rounds, 'champion': champion})


@bp.route('/admin/playoffs/matchup/<int:matchup_id>/result', methods=['POST'])
@require_jwt_admin
def mobile_playoff_result(matchup_id):
    """Save a playoff matchup result — mirrors playoffs.save_result() exactly:
    winner = higher points; a tie requires an explicit winner_team_id; then
    the same _advance_winner() bracket-progression logic."""
    db = get_db()
    league_id = g.jwt_league_id

    matchup = db.execute(
        """SELECT pm.*, pb.league_id, pb.total_teams
           FROM playoff_matchups pm
           JOIN playoff_brackets pb ON pm.bracket_id = pb.bracket_id
           WHERE pm.matchup_id = %s AND pb.league_id = %s""",
        (matchup_id, league_id)
    ).fetchone()
    if not matchup:
        return _err('Matchup not found.', 404)

    data = request.get_json(silent=True) or {}
    try:
        t1_pts = float(data.get('team1_points', 0) or 0)
        t2_pts = float(data.get('team2_points', 0) or 0)
    except (TypeError, ValueError):
        return _err('Invalid points values.', 400)

    winner_id_raw = data.get('winner_team_id')
    if t1_pts > t2_pts:
        winner_id = matchup['team1_id']
    elif t2_pts > t1_pts:
        winner_id = matchup['team2_id']
    elif winner_id_raw is not None:
        try:
            winner_id = int(winner_id_raw)
        except (TypeError, ValueError):
            winner_id = matchup['team1_id']
    else:
        return _err('Scores are tied — winner_team_id is required.', 400)

    db.execute(
        """UPDATE playoff_matchups
           SET team1_points=%s, team2_points=%s, winner_team_id=%s
           WHERE matchup_id=%s""",
        (t1_pts, t2_pts, winner_id, matchup_id)
    )
    db.commit()

    from routes.playoffs import _advance_winner
    updated = db.execute("SELECT * FROM playoff_matchups WHERE matchup_id=%s", (matchup_id,)).fetchone()
    bracket = db.execute("SELECT * FROM playoff_brackets WHERE bracket_id=%s", (updated['bracket_id'],)).fetchone()
    _advance_winner(db, bracket, updated)

    return jsonify({
        'matchup_id':     matchup_id,
        'team1_points':   t1_pts,
        'team2_points':   t2_pts,
        'winner_team_id': winner_id,
    })


# ---------------------------------------------------------------------------
# Points Override
# ---------------------------------------------------------------------------

@bp.route('/matchups/<int:matchup_id>/overrides')
@require_jwt
def mobile_matchup_overrides(matchup_id):
    """Active total_points overrides for a matchup — member-visible
    transparency, mirrors scores.get_point_overrides_for_matchup(active_only=True)."""
    db = get_db()
    matchup = db.execute(
        "SELECT m.matchup_id FROM matchups m JOIN seasons s ON m.season_id = s.season_id"
        " WHERE m.matchup_id = %s AND s.league_id = %s",
        (matchup_id, g.jwt_league_id)
    ).fetchone()
    if not matchup:
        return _err('Matchup not found.', 404)

    from routes.scores import get_point_overrides_for_matchup
    overrides = get_point_overrides_for_matchup(db, matchup_id, active_only=True)
    return jsonify({
        'overrides': [
            {
                'player_id':      o['player_id'],
                'override_value': o['override_value'],
                'original_value': o['original_value'],
                'reason':         o['reason'],
                'active':         bool(o['active']),
            }
            for o in overrides if o['field'] == 'total_points'
        ]
    })


@bp.route('/admin/matchups/<int:matchup_id>/override-points', methods=['POST'])
@require_jwt_admin
def mobile_override_points(matchup_id):
    """Set manual point overrides for a matchup — mirrors scores.override_points()
    exactly (v1 scope: total_points only, same as the web route)."""
    db = get_db()
    league_id = g.jwt_league_id

    matchup = db.execute(
        "SELECT m.*, s.season_id FROM matchups m JOIN seasons s ON m.season_id = s.season_id"
        " WHERE m.matchup_id = %s AND s.league_id = %s",
        (matchup_id, league_id)
    ).fetchone()
    if not matchup:
        return _err('Matchup not found.', 404)

    from routes.archive import season_is_locked
    if season_is_locked(db, matchup['season_id'], league_id):
        return _err('This season is locked (Archive Settings) — unlock it first.', 423)

    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip()
    values = data.get('values') or []

    rows = db.execute(
        "SELECT player_id, total_points FROM match_results WHERE matchup_id = %s",
        (matchup_id,)
    ).fetchall()
    current_by_player = {r['player_id']: float(r['total_points'] or 0) for r in rows}

    from routes.scores import record_point_override
    changes = []
    for v in values:
        pid = v.get('player_id')
        if pid not in current_by_player:
            continue
        try:
            new_val = float(v.get('total_points'))
        except (TypeError, ValueError):
            return _err(f'Invalid points value for player {pid}.', 400)
        current = current_by_player[pid]
        if abs(new_val - current) > 1e-9:
            changes.append((pid, new_val))

    if changes and not reason:
        return _err('A reason is required to override points.', 400)

    # created_by_user_id has a real FK to users(user_id) — league-level JWT
    # auth (no individual account) carries user_id=0 as a sentinel (see
    # auth_login()), which violates that FK; None is the web session's own
    # equivalent (session.get('user_id') is unset, not 0, for that login path).
    for pid, new_val in changes:
        record_point_override(db, matchup_id, pid, 'total_points', new_val,
                               reason, g.jwt_user_id or None)
    if changes:
        apply_point_overrides(db, matchup_id)
        db.commit()

    return jsonify({'changed': len(changes), 'players': [pid for pid, _ in changes]})


@bp.route('/admin/matchups/<int:matchup_id>/override-points/<int:player_id>/clear', methods=['POST'])
@require_jwt_admin
def mobile_clear_point_override(matchup_id, player_id):
    """Clear a player's active total_points override — mirrors
    scores.clear_point_override_route(), including the completed-matchup
    re-recalc-via-_recalc_single_round() step so the value actually reverts."""
    db = get_db()
    league_id = g.jwt_league_id

    matchup = db.execute(
        "SELECT m.*, s.season_id FROM matchups m JOIN seasons s ON m.season_id = s.season_id"
        " WHERE m.matchup_id = %s AND s.league_id = %s",
        (matchup_id, league_id)
    ).fetchone()
    if not matchup:
        return _err('Matchup not found.', 404)

    from routes.archive import season_is_locked
    if season_is_locked(db, matchup['season_id'], league_id):
        return _err('This season is locked (Archive Settings) — unlock it first.', 423)

    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip() or 'Cleared, reverted to computed value'

    from routes.scores import (clear_point_override, get_league_settings,
                                _recalc_single_round, _settings_scoring_mode,
                                _settings_absence_policy)
    clear_point_override(db, matchup_id, player_id, 'total_points', reason, g.jwt_user_id or None)

    settings = get_league_settings(db, matchup['season_id'], league_id)
    if settings and matchup['status'] == 'completed':
        hpct    = float(settings['handicap_percent'])
        hmax    = float(settings['max_handicap_index'])
        smode   = _settings_scoring_mode(settings)
        apolicy = _settings_absence_policy(settings)
        _recalc_single_round(db, matchup_id, matchup['season_id'], league_id,
                             hpct, hmax, smode, use_existing_hcp=True, absence_policy=apolicy)
    db.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Week Exclusions
# ---------------------------------------------------------------------------

@bp.route('/admin/week-exclusions/<int:season_id>/<int:week_num>', methods=['POST'])
@require_jwt_admin
def mobile_save_week_exclusion(season_id, week_num):
    """Save week exclusion flags — mirrors week_exclusions.save(): season-locked
    block, plus the silent handicap-rebuild-on-change side effect when the
    handicap flag actually flips."""
    db = get_db()
    league_id = g.jwt_league_id

    season = db.execute(
        "SELECT season_id, league_id FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        return _err('Season not found.', 404)

    from routes.archive import season_is_locked
    if season_is_locked(db, season_id, league_id):
        return _err('This season is locked (Archive Settings) — unlock it first.', 423)

    data = request.get_json(silent=True) or {}

    from routes.week_exclusions import set_week_exclusion, is_week_excluded
    exclude_handicap = bool(data.get('exclude_handicap'))
    was_excluded_handicap = is_week_excluded(db, season_id, week_num, 'handicap')

    set_week_exclusion(
        db, season_id, week_num,
        exclude_stats=bool(data.get('exclude_stats')),
        exclude_handicap=exclude_handicap,
        exclude_points=bool(data.get('exclude_points')),
        reason=(data.get('reason') or '').strip() or None,
        # updated_by_user_id FKs to users(user_id) — league-level JWT auth's
        # user_id=0 sentinel would violate it (see the override-points route
        # above for the same fix / rationale).
        user_id=g.jwt_user_id or None,
    )
    db.commit()

    if exclude_handicap != was_excluded_handicap:
        from routes.handicap import rebuild_league_handicaps_and_scores
        rebuild_league_handicaps_and_scores(db, league_id)
        db.commit()

    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Handicap Admin
# ---------------------------------------------------------------------------

@bp.route('/admin/handicap/matrix')
@require_jwt_admin
def mobile_handicap_matrix():
    """Trimmed handicap matrix — mirrors handicap.get_handicap_matrix_context(),
    dropping rank/type/team columns (desktop-only noise)."""
    db = get_db()
    league_id = g.jwt_league_id
    season_id = request.args.get('season_id', type=int)
    if not season_id:
        season = _current_season(db, league_id)
        season_id = season['season_id'] if season else None
    if not season_id:
        return jsonify({'rounds': [], 'matrix': []})

    from routes.handicap import get_handicap_matrix_context
    ctx = get_handicap_matrix_context(db, season_id, league_id)

    rounds = [
        {'round_date': str(r['round_date']), 'week_number': r['week_number']}
        for r in ctx['rounds']
    ]
    matrix = [
        {
            'player_id':   row['player_id'],
            'name':        row['name'],
            'current_hcp': row['current_hcp'],
            'round_cells': [
                {'hcp': c['hcp'], 'overridden': bool(c['overridden'])} if c else None
                for c in row['round_cells']
            ],
            'avg': row['avg'],
        }
        for row in ctx['matrix']
    ]
    return jsonify({'rounds': rounds, 'matrix': matrix})


@bp.route('/admin/handicap/rebuild', methods=['POST'])
@require_jwt_admin
def mobile_handicap_rebuild():
    """Preview (?preview=true) or commit a full chronological handicap
    rebuild — mirrors handicap.rebuild_timeline()'s GET-preview/POST-commit
    split, using db.rollback() for preview instead of a separate GET route
    (one call site either way, so preview == commit's actual computation)."""
    db = get_db()
    league_id = g.jwt_league_id
    preview = request.args.get('preview', '').lower() == 'true'

    from routes.archive import locked_season_names
    from routes.handicap import rebuild_league_handicaps_and_scores
    locked = locked_season_names(db, league_id)

    if not preview and locked:
        db.rollback()
        return _err(
            'This rebuild spans every season in the league, and '
            + (', '.join(locked)) + (' is' if len(locked) == 1 else ' are')
            + ' locked (Archive Settings) — unlock it first.', 423)

    summary = rebuild_league_handicaps_and_scores(db, league_id)

    if preview:
        db.rollback()
    else:
        db.commit()

    return jsonify({'summary': {
        'players_processed': summary['players_processed'],
        'rounds_processed':  summary['rounds_processed'],
        'rounds_changed':    summary['rounds_changed'],
    }})


@bp.route('/admin/handicap/history/<int:handicap_id>/override', methods=['POST'])
@require_jwt_admin
def mobile_override_handicap(handicap_id):
    """Override a handicap_history row's index — mirrors handicap.override_handicap(),
    including the first-time-only pre_override_index/pre_override_reason snapshot."""
    db = get_db()
    league_id = g.jwt_league_id

    hh = db.execute(
        """SELECT hh.*, p.league_id
             FROM handicap_history hh
             JOIN players p ON hh.player_id = p.player_id
            WHERE hh.handicap_id = %s""",
        (handicap_id,)
    ).fetchone()
    if not hh or hh['league_id'] != league_id:
        return _err('Record not found.', 404)

    data = request.get_json(silent=True) or {}
    try:
        new_index = float(data.get('new_index'))
    except (TypeError, ValueError):
        return _err('Invalid handicap index.', 400)
    reason = (data.get('reason') or '').strip()

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    if hh['is_manual_override']:
        db.execute(
            """UPDATE handicap_history
                  SET handicap_index      = %s,
                      override_reason     = %s,
                      override_by_user_id = %s,
                      override_at         = %s
                WHERE handicap_id = %s""",
            (new_index, reason or None, g.jwt_user_id, now, handicap_id)
        )
    else:
        db.execute(
            """UPDATE handicap_history
                  SET handicap_index      = %s,
                      is_manual_override  = 1,
                      override_reason     = %s,
                      override_by_user_id = %s,
                      override_at         = %s,
                      pre_override_index  = %s,
                      pre_override_reason = %s
                WHERE handicap_id = %s""",
            (new_index, reason or None, g.jwt_user_id, now,
             hh['handicap_index'], hh['override_reason'], handicap_id)
        )
    db.commit()
    return jsonify({'handicap_id': handicap_id, 'handicap_index': new_index})


@bp.route('/admin/handicap/history/<int:handicap_id>/clear', methods=['POST'])
@require_jwt_admin
def mobile_clear_handicap_override(handicap_id):
    """Clear a manual handicap override and rebuild — mirrors
    handicap.clear_handicap_override() (delete the anchor row, then rebuild
    to regenerate an auto row for it; commit only after the rebuild succeeds)."""
    db = get_db()
    league_id = g.jwt_league_id

    hh = db.execute(
        """SELECT hh.*, p.league_id, p.player_id AS pid
             FROM handicap_history hh
             JOIN players p ON hh.player_id = p.player_id
            WHERE hh.handicap_id = %s""",
        (handicap_id,)
    ).fetchone()
    if not hh or hh['league_id'] != league_id:
        return _err('Record not found.', 404)

    db.execute("DELETE FROM handicap_history WHERE handicap_id = %s", (handicap_id,))

    from routes.handicap import rebuild_league_handicaps_and_scores
    try:
        rebuild_league_handicaps_and_scores(db, league_id)
        db.commit()
    except Exception as e:
        db.rollback()
        return _err(f'Failed to clear override — nothing was changed. Error: {e}', 500)

    return jsonify({'ok': True, 'player_id': hh['pid']})


# ---------------------------------------------------------------------------
# Admin: Contests CRUD
# ---------------------------------------------------------------------------

@bp.route('/admin/contests', methods=['GET', 'POST'])
@require_jwt_admin
def mobile_admin_contests():
    db = get_db()
    league_id = g.jwt_league_id
    from routes.contests import CONTEST_TYPES, TEAM_CONTEST_TYPES

    if request.method == 'GET':
        season_id = request.args.get('season_id', type=int)
        if not season_id:
            return _err('season_id is required.', 400)
        contests = db.execute(
            """SELECT c.*,
                      (SELECT COUNT(*) FROM contest_results cr WHERE cr.contest_id = c.contest_id) AS result_count
               FROM contests c
               WHERE c.season_id = %s AND c.league_id = %s
               ORDER BY c.week_num ASC NULLS LAST, c.contest_id ASC""",
            (season_id, league_id)
        ).fetchall()
        return jsonify({'contests': [dict(c) for c in contests]})

    # POST — create, mirrors contests.admin_add()
    data = request.get_json(silent=True) or {}
    season_id = data.get('season_id')
    if not season_id:
        return _err('season_id is required.', 400)
    contest_type = data.get('contest_type', 'custom')
    week_num     = data.get('week_num')
    description  = (data.get('description') or '').strip() or None
    is_recurring = 1 if data.get('is_recurring') else 0
    name = dict(CONTEST_TYPES).get(contest_type, contest_type)

    if is_recurring:
        week_num = None
    elif week_num is not None:
        try:
            week_num = int(week_num)
        except (TypeError, ValueError):
            week_num = None

    if not is_recurring and contest_type in TEAM_CONTEST_TYPES and week_num is None:
        return _err('Team Low Net requires a specific week — pick one, or set '
                     'is_recurring to run it week-by-week.', 400)

    contest_id = db.execute(
        """INSERT INTO contests (league_id, season_id, name, contest_type, week_num, description, is_recurring)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING contest_id""",
        (league_id, season_id, name, contest_type, week_num, description, is_recurring)
    ).fetchone()['contest_id']
    db.commit()
    return jsonify({'contest_id': contest_id, 'name': name}), 201


@bp.route('/admin/contests/<int:contest_id>', methods=['GET', 'PUT', 'DELETE'])
@require_jwt_admin
def mobile_admin_contest_detail(contest_id):
    db = get_db()
    league_id = g.jwt_league_id
    from routes.contests import CONTEST_TYPES, TEAM_CONTEST_TYPES

    contest = db.execute(
        "SELECT * FROM contests WHERE contest_id = %s AND league_id = %s",
        (contest_id, league_id)
    ).fetchone()
    if not contest:
        return _err('Contest not found.', 404)

    if request.method == 'GET':
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
               ORDER BY cr.week_num ASC NULLS FIRST, cr.rank ASC, cr.result_id ASC""",
            (contest_id,)
        ).fetchall()
        return jsonify({'contest': dict(contest), 'results': [dict(r) for r in results]})

    if request.method == 'DELETE':
        scope = request.args.get('scope', 'all')
        if scope == 'week' and contest['is_recurring']:
            week_num = request.args.get('week_num', type=int)
            if week_num is None:
                return _err('week_num is required when scope=week.', 400)
            db.execute(
                "DELETE FROM contest_results WHERE contest_id = %s AND week_num = %s",
                (contest_id, week_num)
            )
            db.commit()
            return jsonify({'ok': True, 'scope': 'week', 'week_num': week_num})

        db.execute("DELETE FROM contest_results WHERE contest_id = %s", (contest_id,))
        db.execute("DELETE FROM contests WHERE contest_id = %s", (contest_id,))
        db.commit()
        return jsonify({'ok': True, 'scope': 'all'})

    # PUT — mirrors contests.admin_edit() POST branch
    data = request.get_json(silent=True) or {}
    contest_type = data.get('contest_type', 'custom')
    week_num     = data.get('week_num')
    description  = (data.get('description') or '').strip() or None
    is_recurring = 1 if data.get('is_recurring') else 0
    name = dict(CONTEST_TYPES).get(contest_type, contest_type)

    if is_recurring:
        week_num = None
    elif week_num is not None:
        try:
            week_num = int(week_num)
        except (TypeError, ValueError):
            week_num = None

    if not is_recurring and contest_type in TEAM_CONTEST_TYPES and not week_num:
        return _err('Team Low Net requires a specific week — pick one, or set '
                     'is_recurring to run it week-by-week.', 400)

    db.execute(
        """UPDATE contests SET name=%s, contest_type=%s, week_num=%s, description=%s, is_recurring=%s
           WHERE contest_id=%s""",
        (name, contest_type, week_num, description, is_recurring, contest_id)
    )
    db.commit()
    return jsonify({'ok': True})


@bp.route('/admin/contests/<int:contest_id>/calculate', methods=['POST'])
@require_jwt_admin
def mobile_admin_contest_calculate(contest_id):
    """Auto-calculate results for a computed team contest type — mirrors
    contests.admin_calculate()."""
    db = get_db()
    league_id = g.jwt_league_id

    contest = db.execute(
        "SELECT * FROM contests WHERE contest_id = %s AND league_id = %s",
        (contest_id, league_id)
    ).fetchone()
    if not contest:
        return _err('Contest not found.', 404)

    from routes.contests import TEAM_CONTEST_TYPES, _calculate_team_low_net_week
    if contest['contest_type'] not in TEAM_CONTEST_TYPES:
        return _err('This contest type is not auto-calculated.', 400)

    data = request.get_json(silent=True) or {}
    if contest['is_recurring']:
        week_num = data.get('week_num')
        try:
            week_num = int(week_num)
        except (TypeError, ValueError):
            return _err('week_num is required to calculate a recurring contest.', 400)
    else:
        week_num = contest['week_num']
        if not week_num:
            return _err('This contest has no week set — cannot calculate.', 400)

    n = 0
    if contest['contest_type'] == 'team_low_net':
        n = _calculate_team_low_net_week(db, contest, week_num)
        if not n:
            return _err(f'No completed team rounds (with both players present) found for week {week_num} yet.', 400)
        db.commit()

    return jsonify({'week_num': week_num, 'results': n})


@bp.route('/admin/contests/<int:contest_id>/calculate-all', methods=['POST'])
@require_jwt_admin
def mobile_admin_contest_calculate_all(contest_id):
    """Loops every completed week of the season — mirrors
    contests.admin_calculate_all()."""
    db = get_db()
    league_id = g.jwt_league_id

    contest = db.execute(
        "SELECT * FROM contests WHERE contest_id = %s AND league_id = %s",
        (contest_id, league_id)
    ).fetchone()
    if not contest:
        return _err('Contest not found.', 404)

    from routes.contests import TEAM_CONTEST_TYPES, _calculate_team_low_net_week
    if contest['contest_type'] not in TEAM_CONTEST_TYPES:
        return _err('This contest type is not auto-calculated.', 400)
    if not contest['is_recurring']:
        return _err('This contest only has one week — use /calculate instead.', 400)

    week_rows = db.execute(
        """SELECT DISTINCT week_number FROM matchups
           WHERE season_id = %s AND status = 'completed' AND is_bye = 0
           ORDER BY week_number""",
        (contest['season_id'],)
    ).fetchall()

    weeks_done, weeks_skipped, total_results = 0, 0, 0
    for w in week_rows:
        n = _calculate_team_low_net_week(db, contest, w['week_number'])
        if n:
            weeks_done += 1
            total_results += n
        else:
            weeks_skipped += 1
    db.commit()

    return jsonify({
        'weeks_calculated': weeks_done,
        'weeks_skipped':    weeks_skipped,
        'total_results':    total_results,
    })


# ---------------------------------------------------------------------------
# Admin: Announcements CRUD
# ---------------------------------------------------------------------------

@bp.route('/admin/announcements', methods=['GET', 'POST'])
@require_jwt_admin
def mobile_admin_announcements():
    """Manages routes.announcements' `notifications` table (the league
    announcement feed) — distinct from this API's own /board endpoints,
    which are a separate reaction-enabled announcement table."""
    db = get_db()
    league_id = g.jwt_league_id

    if request.method == 'GET':
        rows = db.execute(
            "SELECT * FROM notifications WHERE league_id = %s ORDER BY created_date DESC",
            (league_id,)
        ).fetchall()
        return jsonify({'announcements': [dict(r) for r in rows]})

    # POST — create, mirrors announcements.create()
    data = request.get_json(silent=True) or {}
    notif_type    = (data.get('type') or 'general').strip()
    message       = (data.get('message') or '').strip()
    display_until = (data.get('display_until') or '').strip() or None

    if not message:
        return _err('Announcement message cannot be empty.', 400)

    from datetime import date
    notification_id = db.execute(
        """INSERT INTO notifications (league_id, type, message, created_date, display_until, active)
           VALUES (%s, %s, %s, %s, %s, 1) RETURNING notification_id""",
        (league_id, notif_type, message, date.today().isoformat(), display_until)
    ).fetchone()['notification_id']
    db.commit()

    try:
        from routes.notifications import create_league_event
        preview = message[:80] + ('…' if len(message) > 80 else '')
        create_league_event(db, league_id, 'announcement', f"New announcement: {preview}")
        db.commit()
    except Exception:
        pass
    try:
        from routes.email_config import send_announcement_email
        send_announcement_email(db, league_id, message, notif_type)
    except Exception:
        pass

    return jsonify({'notification_id': notification_id}), 201


@bp.route('/admin/announcements/<int:notif_id>', methods=['PUT', 'DELETE'])
@require_jwt_admin
def mobile_admin_announcement_detail(notif_id):
    db = get_db()
    league_id = g.jwt_league_id

    row = db.execute(
        "SELECT * FROM notifications WHERE notification_id = %s AND league_id = %s",
        (notif_id, league_id)
    ).fetchone()
    if not row:
        return _err('Announcement not found.', 404)

    if request.method == 'DELETE':
        db.execute("DELETE FROM notifications WHERE notification_id = %s", (notif_id,))
        db.commit()
        return jsonify({'ok': True})

    # PUT — mirrors announcements.edit() POST branch
    data = request.get_json(silent=True) or {}
    notif_type    = (data.get('type') or 'general').strip()
    message       = (data.get('message') or '').strip()
    display_until = (data.get('display_until') or '').strip() or None

    if not message:
        return _err('Message cannot be empty.', 400)

    db.execute(
        """UPDATE notifications
           SET type = %s, message = %s, display_until = %s
           WHERE notification_id = %s""",
        (notif_type, message, display_until, notif_id)
    )
    db.commit()
    return jsonify({'ok': True})


@bp.route('/admin/announcements/<int:notif_id>/toggle', methods=['POST'])
@require_jwt_admin
def mobile_admin_announcement_toggle(notif_id):
    db = get_db()
    league_id = g.jwt_league_id

    row = db.execute(
        "SELECT * FROM notifications WHERE notification_id = %s AND league_id = %s",
        (notif_id, league_id)
    ).fetchone()
    if not row:
        return _err('Announcement not found.', 404)

    new_active = 0 if row['active'] else 1
    db.execute(
        "UPDATE notifications SET active = %s WHERE notification_id = %s",
        (new_active, notif_id)
    )
    db.commit()
    return jsonify({'ok': True, 'active': bool(new_active)})


# ---------------------------------------------------------------------------
# Admin: Subs management
# ---------------------------------------------------------------------------

@bp.route('/admin/subs/pending')
@require_jwt_admin
def mobile_admin_subs_pending():
    """Open sub requests — mirrors subs.admin_requests()'s open_requests query.
    Deviation from the web source: that query LEFT JOINs a `schedule_weeks`
    table (`m.week_id = w.week_id`) that does not exist anywhere in
    schema_postgres.sql — matchups carries week_number/scheduled_date
    directly, with no separate weeks table or week_id column. This appears
    to be a pre-existing dead-code bug in routes/subs.py itself (confirmed
    live: 500 UndefinedTable when exercised against the real dev DB), not
    something to faithfully reproduce here. Uses matchups' own columns
    instead so this endpoint actually returns data."""
    db = get_db()
    league_id = g.jwt_league_id

    open_requests = db.execute(
        """SELECT sr.*,
                  p.first_name AS player_first, p.last_name AS player_last,
                  s.season_name,
                  m.week_number AS week_num, m.scheduled_date AS week_date,
                  t1p1.first_name AS t1p1_first, t1p1.last_name AS t1p1_last,
                  t1p2.first_name AS t1p2_first, t1p2.last_name AS t1p2_last,
                  t2p1.first_name AS t2p1_first, t2p1.last_name AS t2p1_last,
                  t2p2.first_name AS t2p2_first, t2p2.last_name AS t2p2_last,
                  tm1.team_name AS team1_name, tm2.team_name AS team2_name
           FROM sub_requests sr
           JOIN players p  ON sr.player_id = p.player_id
           JOIN seasons s  ON sr.season_id = s.season_id
           LEFT JOIN matchups m  ON sr.matchup_id = m.matchup_id
           LEFT JOIN teams tm1 ON m.team1_id = tm1.team_id
           LEFT JOIN teams tm2 ON m.team2_id = tm2.team_id
           LEFT JOIN players t1p1 ON tm1.player1_id = t1p1.player_id
           LEFT JOIN players t1p2 ON tm1.player2_id = t1p2.player_id
           LEFT JOIN players t2p1 ON tm2.player1_id = t2p1.player_id
           LEFT JOIN players t2p2 ON tm2.player2_id = t2p2.player_id
           WHERE sr.league_id = %s AND sr.status = 'open'
           ORDER BY m.scheduled_date ASC, sr.created_at ASC""",
        (league_id,)
    ).fetchall()

    return jsonify({'requests': [dict(r) for r in open_requests]})


@bp.route('/admin/subs/<int:request_id>/assign', methods=['POST'])
@require_jwt_admin
def mobile_admin_subs_assign(request_id):
    """Assign a sub to an open request — mirrors subs.admin_assign() exactly,
    including the player_absences upsert so score entry picks it up."""
    db = get_db()
    league_id = g.jwt_league_id

    req = db.execute(
        "SELECT * FROM sub_requests WHERE request_id=%s AND league_id=%s",
        (request_id, league_id)
    ).fetchone()
    if not req:
        return _err('Request not found.', 404)

    data = request.get_json(silent=True) or {}
    sub_pid      = data.get('sub_player_id')
    admin_notes  = (data.get('admin_notes') or '').strip()

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    db.execute(
        """UPDATE sub_requests
           SET status='filled', sub_player_id=%s, admin_notes=%s, updated_at=%s
           WHERE request_id=%s""",
        (sub_pid, admin_notes or None, now, request_id)
    )

    existing_absence = db.execute(
        "SELECT absence_id FROM player_absences WHERE matchup_id=%s AND player_id=%s",
        (req['matchup_id'], req['player_id'])
    ).fetchone()

    reason_text = req['notes'] or 'Player sub request'
    if existing_absence:
        db.execute(
            """UPDATE player_absences
               SET sub_player_id=%s, reason=%s, excused=1
               WHERE absence_id=%s""",
            (sub_pid, reason_text, existing_absence['absence_id'])
        )
    else:
        db.execute(
            """INSERT INTO player_absences
               (round_id, matchup_id, player_id, sub_player_id, reason, excused)
               VALUES (NULL, %s, %s, %s, %s, 1)""",
            (req['matchup_id'], req['player_id'], sub_pid, reason_text)
        )

    db.commit()
    return jsonify({'ok': True, 'request_id': request_id, 'status': 'filled'})


@bp.route('/admin/subs/<int:request_id>/dismiss', methods=['POST'])
@require_jwt_admin
def mobile_admin_subs_dismiss(request_id):
    """Dismiss a sub request without assigning — mirrors subs.admin_dismiss()."""
    db = get_db()
    league_id = g.jwt_league_id

    req = db.execute(
        "SELECT * FROM sub_requests WHERE request_id=%s AND league_id=%s",
        (request_id, league_id)
    ).fetchone()
    if not req:
        return _err('Request not found.', 404)

    data = request.get_json(silent=True) or {}
    admin_notes = (data.get('admin_notes') or '').strip()
    db.execute(
        """UPDATE sub_requests SET status='dismissed', admin_notes=%s, updated_at=%s
           WHERE request_id=%s""",
        (admin_notes or None, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), request_id)
    )
    db.commit()
    return jsonify({'ok': True, 'request_id': request_id, 'status': 'dismissed'})
