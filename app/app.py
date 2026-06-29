import os
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timezone

from flask import Flask, session, redirect, url_for, request, flash, jsonify, render_template, make_response, send_from_directory
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
import database

csrf = CSRFProtect()

# ── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60 per minute"],
    storage_uri="memory://",
)

from routes.main import bp as main_bp
from routes.auth import bp as auth_bp, login_required
from routes.players import bp as players_bp
from routes.seasons import bp as seasons_bp
from routes.teams import bp as teams_bp
from routes.schedule import bp as schedule_bp
from routes.scores import bp as scores_bp
from routes.standings import bp as standings_bp
from routes.handicap import bp as handicap_bp
from routes.admin import bp as admin_bp
from routes.skins import bp as skins_bp
from routes.courses import bp as courses_bp
from routes.playoffs import bp as playoffs_bp
from routes.archive import bp as archive_bp
from routes.records import bp as records_bp
from routes.stats import bp as stats_bp
from routes.reports import bp as reports_bp
from routes.self_report import bp as self_report_bp
from routes.users import bp as users_bp
from routes.announcements import bp as announcements_bp
from routes.subs import bp as subs_bp
from routes.notifications import bp as notifications_bp
from routes.migration import bp as migration_bp
from routes.contests import bp as contests_bp
from routes.dues import bp as dues_bp
from routes.email_config import bp as email_config_bp
from routes.forum import bp as forum_bp
from routes.board import bp as board_bp
from routes.public_view import bp as public_view_bp
from routes.api import bp as api_bp
from routes.player_reg import bp as player_reg_bp
from routes.my_stats import bp as my_stats_bp
from routes.availability import bp as availability_bp
from routes.league_info import bp as league_info_bp
from routes.email_prefs import bp as email_prefs_bp
from routes.display import bp as display_bp
from routes.score_import import bp as score_import_bp
from routes.reflections import bp as reflections_bp


def _setup_access_log(app):
    """Set up a rotating access log at ../logs/access.log (relative to app/)."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'access.log')

    handler = TimedRotatingFileHandler(
        log_path,
        when='D',
        interval=1,
        backupCount=7,
        encoding='utf-8',
        delay=False,
    )
    # Also cap at ~5 MB by subclassing — simplest approach: use RotatingFileHandler
    # We'll use a combo: rotating by size, with 7 backups
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=7,
        encoding='utf-8',
    )
    handler.setFormatter(logging.Formatter('%(message)s'))

    access_logger = logging.getLogger('golf_league.access')
    access_logger.setLevel(logging.INFO)
    access_logger.addHandler(handler)
    access_logger.propagate = False
    return access_logger


def create_app():
    app = Flask(__name__)

    # Load config
    app.config['DATABASE'] = config.DATABASE
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['DEBUG'] = config.DEBUG
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour token lifetime

    # Session security
    app.config['SESSION_COOKIE_SECURE'] = config.SESSION_COOKIE_SECURE
    app.config['SESSION_COOKIE_HTTPONLY'] = config.SESSION_COOKIE_HTTPONLY
    app.config['SESSION_COOKIE_SAMESITE'] = config.SESSION_COOKIE_SAMESITE
    app.config['PERMANENT_SESSION_LIFETIME'] = config.PERMANENT_SESSION_LIFETIME

    # CSRF protection (requires SECRET_KEY to be set)
    csrf.init_app(app)

    # Rate limiter
    limiter.init_app(app)

    # Initialize database (creates tables if DB doesn't exist — safe on every startup)
    from init_db import init_db
    init_db(app.config['DATABASE'])

    # Register database
    database.init_app(app)

    # ── Access log setup ──────────────────────────────────────────────────────
    access_logger = _setup_access_log(app)

    @app.after_request
    def log_request(response):
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        access_logger.info(
            '%s %s "%s %s" %d',
            ts, ip, request.method, request.path, response.status_code
        )
        return response

    # ── Health check endpoint ─────────────────────────────────────────────────
    @app.route('/health')
    @limiter.exempt
    def health():
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        return jsonify(status='ok', timestamp=ts), 200

    # Exempt health from CSRF
    csrf.exempt(health)

    # ── PWA routes ────────────────────────────────────────────────────────────
    @app.route('/offline')
    @limiter.exempt
    def offline():
        return render_template('offline.html'), 200

    @app.route('/sw.js')
    @limiter.exempt
    def service_worker():
        response = make_response(
            send_from_directory(app.static_folder, 'sw.js')
        )
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Service-Worker-Allowed'] = '/'
        response.headers['Cache-Control'] = 'no-cache'
        return response

    csrf.exempt(offline)
    csrf.exempt(service_worker)
    csrf.exempt(api_bp)

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(players_bp)
    app.register_blueprint(seasons_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(scores_bp)
    app.register_blueprint(standings_bp)
    app.register_blueprint(handicap_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(skins_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(playoffs_bp)
    app.register_blueprint(archive_bp)
    app.register_blueprint(records_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(self_report_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(announcements_bp)
    app.register_blueprint(subs_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(migration_bp)
    app.register_blueprint(contests_bp)
    app.register_blueprint(dues_bp)
    app.register_blueprint(email_config_bp)
    app.register_blueprint(forum_bp)
    app.register_blueprint(board_bp)
    app.register_blueprint(public_view_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(player_reg_bp)
    app.register_blueprint(my_stats_bp)
    app.register_blueprint(availability_bp)
    app.register_blueprint(league_info_bp)
    app.register_blueprint(email_prefs_bp)
    app.register_blueprint(display_bp)
    app.register_blueprint(score_import_bp)
    app.register_blueprint(reflections_bp)

    # Apply stricter rate limit to login endpoint
    limiter.limit("20 per minute")(auth_bp)

    # Jinja globals + filters
    app.jinja_env.globals['enumerate'] = enumerate
    app.jinja_env.filters['enumerate'] = enumerate
    app.jinja_env.filters['zip'] = zip

    # ── Season-aware nav context processor ──────────────────────────────────
    @app.context_processor
    def inject_nav_context():
        if not session.get('league_id'):
            return {
                'nav_seasons': [],
                'nav_season_id': None,
                'user_display_name': None,
                'session_user_id': None,
                'pending_submission_count': 0,
                'active_announcement_count': 0,
                'unread_notif_count': 0,
            }
        db = database.get_db()
        seasons = db.execute(
            "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
            (session['league_id'],)
        ).fetchall()
        current_sid = session.get('current_season_id')
        if not current_sid and seasons:
            current_sid = seasons[0]['season_id']
            session['current_season_id'] = current_sid

        # Pending submission count (safe for pre-migration)
        pending_count = 0
        try:
            row = db.execute(
                "SELECT COUNT(*) FROM score_submissions WHERE season_id IN "
                "(SELECT season_id FROM seasons WHERE league_id = %s) AND status = 'pending'",
                (session['league_id'],)
            ).fetchone()
            pending_count = row[0] if row else 0
        except Exception:
            pending_count = 0

        # Active announcement count
        from datetime import date
        today = date.today().isoformat()
        ann_count = 0
        try:
            row = db.execute(
                """SELECT COUNT(*) FROM notifications
                   WHERE league_id = %s AND active = 1
                     AND (display_until IS NULL OR display_until = '' OR display_until >= %s)""",
                (session['league_id'], today)
            ).fetchone()
            ann_count = row[0] if row else 0
        except Exception:
            ann_count = 0

        # Unread notification count (announcements + events)
        unread_notif_count = 0
        try:
            from routes.notifications import get_unread_count
            unread_notif_count = get_unread_count(db, session['league_id'])
        except Exception:
            unread_notif_count = 0

        # Pending player registrations (admin badge)
        pending_reg_count = 0
        try:
            from routes.player_reg import pending_reg_count as _prc
            pending_reg_count = _prc(db, session['league_id'])
        except Exception:
            pass

        return {
            'nav_seasons':              [dict(s) for s in seasons],
            'nav_season_id':            current_sid,
            'user_display_name':        session.get('user_display_name'),
            'session_user_id':          session.get('user_id'),
            'pending_submission_count': pending_count,
            'active_announcement_count': ann_count,
            'unread_notif_count':       unread_notif_count,
            'pending_reg_count':        pending_reg_count,
        }

    # ── Switch season route ──────────────────

    @app.route('/switch-season/<int:season_id>')
    @login_required
    def switch_season(season_id):
        session['current_season_id'] = season_id
        referrer = request.referrer or '/'
        return redirect(referrer)

    return app


app = create_app()

if __name__ == '__main__':
    try:
        app.run(debug=True)
    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        input("\nPress Enter to exit...")
