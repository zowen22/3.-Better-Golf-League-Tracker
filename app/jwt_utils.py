"""
JWT utilities for the mobile API.
Tokens carry: sub (user_id), league_id, role, player_id, exp, iat.
"""
import functools
import logging
import jwt
from datetime import datetime, timedelta, timezone
from flask import current_app, request, g, jsonify

log = logging.getLogger(__name__)


TOKEN_TTL_HOURS   = 24
REFRESH_GRACE_DAYS = 7


def create_token(user_id, league_id, role, player_id=None):
    """Return a signed JWT string."""
    now = datetime.now(timezone.utc)
    payload = {
        'sub':       str(user_id),
        'league_id': league_id,
        'role':      role,
        'player_id': player_id,
        'iat':       now,
        'exp':       now + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def decode_token(token, allow_expired=False):
    """Decode and verify a JWT. Returns payload dict or raises jwt.PyJWTError."""
    options = {'verify_exp': not allow_expired}
    return jwt.decode(
        token,
        current_app.config['SECRET_KEY'],
        algorithms=['HS256'],
        options=options,
    )


def require_jwt(f):
    """Decorator: validate JWT from Authorization: Bearer header; populate g.jwt_*."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header.'}), 401
        token = auth[len('Bearer '):]
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired.'}), 401
        except jwt.PyJWTError as e:
            log.warning('JWT decode failed [%s]: %s', type(e).__name__, e)
            return jsonify({'error': 'Invalid token.'}), 401
        g.jwt_user_id   = int(payload['sub'])
        g.jwt_league_id = payload['league_id']
        g.jwt_role      = payload.get('role')
        g.jwt_player_id = payload.get('player_id')
        return f(*args, **kwargs)
    return wrapper


def require_jwt_admin(f):
    """Decorator: require JWT + admin role."""
    @functools.wraps(f)
    @require_jwt
    def wrapper(*args, **kwargs):
        if g.jwt_role not in ('admin', 'league_admin'):
            return jsonify({'error': 'Admin access required.'}), 403
        return f(*args, **kwargs)
    return wrapper
