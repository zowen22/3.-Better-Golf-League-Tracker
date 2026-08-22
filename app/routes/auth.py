from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import database
from database import get_db
import traffic
from datetime import datetime, timedelta
import functools
import secrets
import hashlib

bp = Blueprint('auth', __name__)


# --- Auth decorators ---

def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if 'league_id' not in session:
            flash('Please log in to continue.', 'info')
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if 'league_id' not in session:
            flash('Please log in to continue.', 'info')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'league_admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('main.dashboard'))
        return view(**kwargs)
    return wrapped


def account_required(view):
    """Gate for individual-account pages (My Leagues, Add League, switching
    leagues) that must work even when no league is currently active in
    session -- unlike login_required, which requires session['league_id'].
    A multi-league account can legitimately have zero leagues linked (just
    removed its last one, or never added one after registering) and still
    needs to reach these pages. Shared league-password sessions (no
    user_id) are locked out, same reasoning as site_admin_required below.
    """
    @functools.wraps(view)
    def wrapped(**kwargs):
        if not session.get('user_id'):
            flash('Please log in with your individual account to continue.', 'info')
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped


def site_admin_required(view):
    """Gate for the platform-wide (cross-league) site-admin dashboard.

    Deliberately separate from `admin_required`, which is league-scoped and
    would let any league admin in. Site-admin status is a platform-level
    flag on `users.is_site_admin` keyed off `session['user_id']` — so it
    requires the individual-account login flow (the shared league-password
    login never sets `user_id`, correctly locking that flow out).
    """
    @functools.wraps(view)
    def wrapped(**kwargs):
        if not session.get('user_id'):
            flash('Please log in with your individual account to continue.', 'info')
            return redirect(url_for('auth.login'))
        db = get_db()
        row = db.execute(
            "SELECT is_site_admin FROM users WHERE user_id = %s",
            (session['user_id'],)
        ).fetchone()
        if not row or not row['is_site_admin']:
            flash('Site admin access required.', 'error')
            return redirect(url_for('main.dashboard'))
        return view(**kwargs)
    return wrapped


# --- Create league ---

@bp.route('/create-league', methods=['GET', 'POST'])
def create_league():
    if request.method == 'POST':
        import re
        league_name     = request.form.get('league_name', '').strip()
        login_code      = request.form.get('login_code', '').strip().upper()
        admin_email     = request.form.get('admin_email', '').strip().lower()
        admin_password  = request.form.get('admin_password', '')
        admin_confirm   = request.form.get('admin_confirm', '')
        member_password = request.form.get('member_password', '')
        member_confirm  = request.form.get('member_confirm', '')
        league_type     = request.form.get('league_type', 'league').strip()
        if league_type not in ('league', 'event'):
            league_type = 'league'

        errors = []
        if not league_name:
            errors.append('League name is required.')
        if not login_code:
            errors.append('League login code is required.')
        elif not re.match(r'^[A-Z0-9_-]+$', login_code):
            errors.append('Login code may only contain letters, numbers, hyphens, and underscores.')
        elif len(login_code) < 3 or len(login_code) > 50:
            errors.append('Login code must be between 3 and 50 characters.')
        if not admin_email or '@' not in admin_email:
            errors.append('A valid admin email is required.')
        if not admin_password:
            errors.append('Admin password is required.')
        elif len(admin_password) < 4:
            errors.append('Admin password must be at least 4 characters.')
        if admin_password != admin_confirm:
            errors.append('Admin passwords do not match.')
        if not member_password:
            errors.append('Member password is required.')
        elif len(member_password) < 4:
            errors.append('Member password must be at least 4 characters.')
        if member_password != member_confirm:
            errors.append('Member passwords do not match.')
        if admin_password == member_password:
            errors.append('Admin and member passwords must be different.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('create_league.html', league_name=league_name, login_code=login_code, admin_email=admin_email, league_type=league_type)

        db = get_db()
        ph = '%s' if database.is_postgres() else '?'
        if db.execute(
            f"SELECT league_id FROM leagues WHERE LOWER(league_name) = LOWER({ph})",
            (league_name,)
        ).fetchone():
            flash('A league with that name already exists.', 'error')
            return render_template('create_league.html', league_name=league_name, login_code=login_code, admin_email=admin_email, league_type=league_type)

        if db.execute(
            f"SELECT league_id FROM leagues WHERE login_code = {ph}",
            (login_code,)
        ).fetchone():
            flash('That login code is already taken. Please choose a different one.', 'error')
            return render_template('create_league.html', league_name=league_name, login_code=login_code, admin_email=admin_email, league_type=league_type)

        admin_hash  = generate_password_hash(admin_password)
        member_hash = generate_password_hash(member_password)
        created     = datetime.now().strftime('%Y-%m-%d')

        if database.is_postgres():
            league_id = db.execute(
                """INSERT INTO leagues (league_name, login_code, created_date, active, admin_password_hash, member_password_hash, admin_email, league_type)
                   VALUES (%s, %s, %s, 1, %s, %s, %s, %s) RETURNING league_id""",
                (league_name, login_code, created, admin_hash, member_hash, admin_email, league_type)
            ).fetchone()[0]
            db.commit()
        else:
            db.execute(
                """INSERT INTO leagues (league_name, login_code, created_date, active, admin_password_hash, member_password_hash, admin_email, league_type)
                   VALUES (?, ?, ?, 1, ?, ?, ?, ?)""",
                (league_name, login_code, created, admin_hash, member_hash, admin_email, league_type)
            )
            db.commit()
            league_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        traffic.record_conversion(db, 'league_created', ref_id=league_id)

        # Log the new admin straight in -- they just typed these credentials,
        # making them do it again at a separate login screen was pure friction.
        session.clear()
        session.permanent       = True
        session['league_id']   = league_id
        session['league_name'] = league_name
        session['role']        = 'league_admin'

        flash(f'League created! Your login code is <strong>{login_code}</strong>. Members use this to find your league at login.', 'success')
        return redirect(url_for('seasons.create'))

    return render_template('create_league.html', league_name='', login_code='', admin_email='', league_type='league')


# --- Forgot password / forgot League ID (admin password reset via email) ---

RESET_TOKEN_TTL_HOURS = 1


def _hash_reset_token(raw_token):
    return hashlib.sha256(raw_token.encode()).hexdigest()


@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        league_id = request.form.get('league_id', '').strip().lower()
        admin_email = request.form.get('admin_email', '').strip().lower()

        if league_id and admin_email:
            db = get_db()
            league = db.execute(
                "SELECT * FROM leagues WHERE LOWER(login_code) = %s AND active = 1",
                (league_id,)
            ).fetchone()
            # Only send if the League ID *and* email match what's on file --
            # but the flash message is identical either way (below), so a
            # wrong guess can't be used to enumerate valid League IDs/emails.
            if league and league['admin_email'] and league['admin_email'].strip().lower() == admin_email:
                raw_token = secrets.token_urlsafe(32)
                now = datetime.now()
                db.execute(
                    "INSERT INTO password_reset_tokens (league_id, token_hash, created_at, expires_at) VALUES (%s, %s, %s, %s)",
                    (league['league_id'], _hash_reset_token(raw_token), now.isoformat(),
                     (now + timedelta(hours=RESET_TOKEN_TTL_HOURS)).isoformat())
                )
                db.commit()
                from routes.email_config import send_platform_email
                reset_url = url_for('auth.reset_password', token=raw_token, _external=True)
                send_platform_email(
                    admin_email,
                    'Reset your league admin password',
                    f'<p>Someone (hopefully you) requested a password reset for League ID '
                    f'<strong>{league["login_code"]}</strong>.</p>'
                    f'<p><a href="{reset_url}">Click here to set a new password</a>. '
                    f'This link expires in {RESET_TOKEN_TTL_HOURS} hour.</p>'
                    f'<p>If you didn\'t request this, you can ignore this email.</p>'
                )

        flash('If that League ID and email match our records, a reset link is on its way.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    db = get_db()
    row = db.execute(
        "SELECT * FROM password_reset_tokens WHERE token_hash = %s",
        (_hash_reset_token(token),)
    ).fetchone()
    valid = bool(row) and not row['used'] and datetime.fromisoformat(row['expires_at']) > datetime.now()

    if not valid:
        flash('This reset link is invalid or has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))

    is_account_reset = bool(row['user_id'])

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        if len(password) < 4:
            flash('Password must be at least 4 characters.', 'error')
            return render_template('auth/reset_password.html', token=token, is_account_reset=is_account_reset)
        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token, is_account_reset=is_account_reset)

        if is_account_reset:
            db.execute(
                "UPDATE users SET password_hash = %s WHERE user_id = %s",
                (generate_password_hash(password), row['user_id'])
            )
        else:
            db.execute(
                "UPDATE leagues SET admin_password_hash = %s WHERE league_id = %s",
                (generate_password_hash(password), row['league_id'])
            )
        db.execute("UPDATE password_reset_tokens SET used = 1 WHERE token_id = %s", (row['token_id'],))
        db.commit()
        flash('Password updated! You can now sign in.', 'success')
        return redirect(url_for('auth.account_login') if is_account_reset else url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token, is_account_reset=is_account_reset)


@bp.route('/forgot-account-password', methods=['GET', 'POST'])
def forgot_account_password():
    """Self-serve reset for an individual account (users.password_hash) --
    separate from forgot_password() above, which only ever resets the
    shared league admin password. See Work Packages backlog: "Individual
    accounts have no self-serve password reset" (found 2026-08-11)."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if email:
            db = get_db()
            user = db.execute(
                "SELECT * FROM users WHERE LOWER(email) = %s AND active = 1",
                (email,)
            ).fetchone()
            # Same non-enumerating flash regardless of match -- see forgot_password() above.
            if user:
                raw_token = secrets.token_urlsafe(32)
                now = datetime.now()
                db.execute(
                    "INSERT INTO password_reset_tokens (user_id, token_hash, created_at, expires_at) VALUES (%s, %s, %s, %s)",
                    (user['user_id'], _hash_reset_token(raw_token), now.isoformat(),
                     (now + timedelta(hours=RESET_TOKEN_TTL_HOURS)).isoformat())
                )
                db.commit()
                from routes.email_config import send_platform_email
                reset_url = url_for('auth.reset_password', token=raw_token, _external=True)
                send_platform_email(
                    email,
                    'Reset your BGLT account password',
                    f'<p>Someone (hopefully you) requested a password reset for the individual '
                    f'account tied to <strong>{email}</strong>.</p>'
                    f'<p><a href="{reset_url}">Click here to set a new password</a>. '
                    f'This link expires in {RESET_TOKEN_TTL_HOURS} hour.</p>'
                    f'<p>If you didn\'t request this, you can ignore this email.</p>'
                )

        flash('If that email matches an account on file, a reset link is on its way.', 'success')
        return redirect(url_for('auth.login', tab='user'))

    return render_template('auth/forgot_account_password.html')


@bp.route('/forgot-league-id', methods=['GET', 'POST'])
def forgot_league_id():
    if request.method == 'POST':
        admin_email = request.form.get('admin_email', '').strip().lower()
        if admin_email:
            db = get_db()
            leagues = db.execute(
                "SELECT login_code FROM leagues WHERE LOWER(admin_email) = %s AND active = 1",
                (admin_email,)
            ).fetchall()
            if leagues:
                from routes.email_config import send_platform_email
                codes = ', '.join(f'<strong>{r["login_code"]}</strong>' for r in leagues)
                send_platform_email(
                    admin_email,
                    'Your League ID',
                    f'<p>Here\'s the League ID on file for this email: {codes}</p>'
                )
        flash('If that email matches a league on file, the League ID has been sent.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_league_id.html')


# --- Login (supports both league-password and user-account login) ---

@bp.route('/account-login')
def account_login():
    """Bookmarkable entry point for individual-account (email + password)
    login -- equivalent to /login?tab=user, which is what the visible
    Individual Account tab on the login page itself links to."""
    return render_template('login.html', active_tab='user', league_id='', email='')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'league')

        if login_type == 'user':
            # ── User-account login (email + password) ──
            email    = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')

            if not email or not password:
                flash('Email and password are required.', 'error')
                return render_template('login.html', active_tab='user', email=email)

            db = get_db()
            user = db.execute(
                "SELECT * FROM users WHERE LOWER(email) = %s AND active = 1",
                (email,)
            ).fetchone()

            if not user or not check_password_hash(user['password_hash'] or '', password):
                flash('Invalid email or password.', 'error')
                return render_template('login.html', active_tab='user', email=email)

            # Get a league role to land in by default -- an account can now
            # legitimately have zero (see account_required/My Leagues), in
            # which case login still succeeds at the account level, it just
            # doesn't set a league_id.
            ulr = db.execute(
                """SELECT ulr.league_id, ulr.role_id, r.role_name, l.league_name
                   FROM user_league_roles ulr
                   JOIN roles r ON r.role_id = ulr.role_id
                   JOIN leagues l ON l.league_id = ulr.league_id
                   WHERE ulr.user_id = %s AND l.active = 1
                   ORDER BY ulr.id
                   LIMIT 1""",
                (user['user_id'],)
            ).fetchone()

            session.clear()
            session.permanent             = True
            session['user_id']            = user['user_id']
            session['user_display_name']  = f"{user['first_name']} {user['last_name']}"
            session['is_site_admin']      = bool(user['is_site_admin'])

            if not ulr:
                flash('Add a league to get started.', 'info')
                return redirect(url_for('users.my_leagues'))

            # Get linked player
            player = db.execute(
                "SELECT player_id FROM players WHERE user_id = %s AND league_id = %s",
                (user['user_id'], ulr['league_id'])
            ).fetchone()

            session['league_id']   = ulr['league_id']
            session['league_name'] = ulr['league_name']
            session['role']        = ulr['role_name']
            session['player_id']   = player['player_id'] if player else None
            if ulr['role_name'] == 'league_admin':
                return redirect(url_for('admin.landing'))
            return redirect(url_for('main.dashboard'))

        else:
            # ── League-password login (League ID + shared password) ──
            league_id = request.form.get('league_id', '').strip().lower()
            password  = request.form.get('password', '')

            if not league_id or not password:
                flash('League ID and password are required.', 'error')
                return render_template('login.html', active_tab='league', league_id=league_id)

            db = get_db()
            league = db.execute(
                "SELECT * FROM leagues WHERE LOWER(login_code) = %s AND active = 1",
                (league_id,)
            ).fetchone()

            if not league:
                flash('League ID not found.', 'error')
                return render_template('login.html', active_tab='league', league_id=league_id)

            if check_password_hash(league['admin_password_hash'] or '', password):
                session.clear()
                session.permanent       = True
                session['league_id']   = league['league_id']
                session['league_name'] = league['league_name']
                session['role']        = 'league_admin'
                return redirect(url_for('admin.landing'))

            if check_password_hash(league['member_password_hash'] or '', password):
                session.clear()
                session.permanent       = True
                session['league_id']   = league['league_id']
                session['league_name'] = league['league_name']
                session['role']        = 'member'
                return redirect(url_for('main.dashboard'))

            flash('Incorrect password.', 'error')
            return render_template('login.html', active_tab='league', league_id=league_id)

    default_tab = 'user' if request.args.get('tab') == 'user' else 'league'
    return render_template('login.html', active_tab=default_tab, league_id='', email='')


# --- Register user account ---

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        league_id        = request.form.get('league_id', '').strip().lower()
        league_password  = request.form.get('league_password', '')
        first_name       = request.form.get('first_name', '').strip()
        last_name        = request.form.get('last_name', '').strip()
        email            = request.form.get('email', '').strip().lower()
        password         = request.form.get('password', '')
        confirm          = request.form.get('confirm', '')

        form_data = dict(league_id=league_id, first_name=first_name,
                         last_name=last_name, email=email)

        errors = []
        if not league_id:
            errors.append('League ID is required.')
        if not league_password:
            errors.append('League password is required.')
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if not email or '@' not in email:
            errors.append('A valid email address is required.')
        if not password:
            errors.append('Password is required.')
        if len(password) < 4:
            errors.append('Password must be at least 4 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('auth/register.html', **form_data)

        db = get_db()

        # Verify league exists
        league = db.execute(
            "SELECT * FROM leagues WHERE LOWER(login_code) = %s AND active = 1",
            (league_id,)
        ).fetchone()

        if not league:
            flash('League ID not found.', 'error')
            return render_template('auth/register.html', **form_data)

        # Determine role from league password
        role_name = None
        if check_password_hash(league['admin_password_hash'] or '', league_password):
            role_name = 'league_admin'
        elif check_password_hash(league['member_password_hash'] or '', league_password):
            role_name = 'member'
        else:
            flash('Incorrect league password.', 'error')
            return render_template('auth/register.html', **form_data)

        # Check email not already taken
        existing = db.execute(
            "SELECT user_id FROM users WHERE LOWER(email) = %s",
            (email,)
        ).fetchone()
        if existing:
            flash('An account with that email already exists. Try logging in.', 'error')
            return render_template('auth/register.html', **form_data)

        # Create user
        today = datetime.now().strftime('%Y-%m-%d')
        pw_hash = generate_password_hash(password)
        row = db.execute(
            "INSERT INTO users (first_name, last_name, email, password_hash, created_date, active) VALUES (%s, %s, %s, %s, %s, 1) RETURNING user_id",
            (first_name, last_name, email, pw_hash, today)
        ).fetchone()
        user_id = row['user_id']

        # Get role_id -- self-healing get-or-create, since `roles` is a small
        # fixed lookup table with no seed step anywhere in schema/init, and a
        # missing row here would otherwise crash registration outright.
        role_row = db.execute("SELECT role_id FROM roles WHERE role_name = %s", (role_name,)).fetchone()
        if not role_row:
            role_row = db.execute(
                "INSERT INTO roles (role_name) VALUES (%s) RETURNING role_id",
                (role_name,)
            ).fetchone()
        db.execute(
            "INSERT INTO user_league_roles (user_id, league_id, role_id) VALUES (%s, %s, %s)",
            (user_id, league['league_id'], role_row['role_id'])
        )
        db.commit()

        flash('Account created! You can now sign in with your email and password.', 'success')
        return redirect(url_for('auth.account_login'))

    return render_template('auth/register.html',
                           league_id='', first_name='', last_name='', email='')


# --- Logout ---

@bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
