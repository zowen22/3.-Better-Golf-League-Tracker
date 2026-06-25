from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
from datetime import datetime
import functools

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


# --- Create league ---

@bp.route('/create-league', methods=['GET', 'POST'])
def create_league():
    if request.method == 'POST':
        import re
        league_name     = request.form.get('league_name', '').strip()
        login_code      = request.form.get('login_code', '').strip().lower()
        admin_password  = request.form.get('admin_password', '')
        admin_confirm   = request.form.get('admin_confirm', '')
        member_password = request.form.get('member_password', '')
        member_confirm  = request.form.get('member_confirm', '')

        errors = []
        if not league_name:
            errors.append('League name is required.')
        if not login_code:
            errors.append('League login code is required.')
        elif not re.match(r'^[a-z0-9_-]+$', login_code):
            errors.append('Login code may only contain letters, numbers, hyphens, and underscores.')
        elif len(login_code) < 3 or len(login_code) > 50:
            errors.append('Login code must be between 3 and 50 characters.')
        if not admin_password:
            errors.append('Admin password is required.')
        if admin_password != admin_confirm:
            errors.append('Admin passwords do not match.')
        if not member_password:
            errors.append('Member password is required.')
        if member_password != member_confirm:
            errors.append('Member passwords do not match.')
        if admin_password == member_password:
            errors.append('Admin and member passwords must be different.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('create_league.html', league_name=league_name, login_code=login_code)

        db = get_db()
        if db.execute(
            "SELECT league_id FROM leagues WHERE LOWER(league_name) = LOWER(%s)",
            (league_name,)
        ).fetchone():
            flash('A league with that name already exists.', 'error')
            return render_template('create_league.html', league_name=league_name, login_code=login_code)

        if db.execute(
            "SELECT league_id FROM leagues WHERE login_code = %s",
            (login_code,)
        ).fetchone():
            flash('That login code is already taken. Please choose a different one.', 'error')
            return render_template('create_league.html', league_name=league_name, login_code=login_code)

        admin_hash  = generate_password_hash(admin_password)
        member_hash = generate_password_hash(member_password)
        created     = datetime.now().strftime('%Y-%m-%d')

        db.execute(
            """INSERT INTO leagues (league_name, login_code, created_date, active, admin_password_hash, member_password_hash)
               VALUES (%s, %s, %s, 1, %s, %s)""",
            (league_name, login_code, created, admin_hash, member_hash)
        )
        db.commit()

        flash(f'League created! Your login code is <strong>{login_code}</strong>. Members use this to find your league at login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('create_league.html', league_name='', login_code='')


# --- Login (supports both league-password and user-account login) ---

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

            # Get league role
            ulr = db.execute(
                """SELECT ulr.league_id, ulr.role_id, r.role_name, l.league_name
                   FROM user_league_roles ulr
                   JOIN roles r ON r.role_id = ulr.role_id
                   JOIN leagues l ON l.league_id = ulr.league_id
                   WHERE ulr.user_id = %s AND l.active = 1
                   LIMIT 1""",
                (user['user_id'],)
            ).fetchone()

            if not ulr:
                flash('Your account is not linked to any active league. Contact your league admin.', 'error')
                return render_template('login.html', active_tab='user', email=email)

            # Get linked player
            player = db.execute(
                "SELECT player_id FROM players WHERE user_id = %s AND league_id = %s",
                (user['user_id'], ulr['league_id'])
            ).fetchone()

            session.clear()
            session['league_id']          = ulr['league_id']
            session['league_name']        = ulr['league_name']
            session['role']               = ulr['role_name']
            session['user_id']            = user['user_id']
            session['user_display_name']  = f"{user['first_name']} {user['last_name']}"
            session['player_id']          = player['player_id'] if player else None
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
                session['league_id']   = league['league_id']
                session['league_name'] = league['league_name']
                session['role']        = 'league_admin'
                return redirect(url_for('admin.landing'))

            if check_password_hash(league['member_password_hash'] or '', password):
                session.clear()
                session['league_id']   = league['league_id']
                session['league_name'] = league['league_name']
                session['role']        = 'member'
                return redirect(url_for('main.dashboard'))

            flash('Incorrect password.', 'error')
            return render_template('login.html', active_tab='league', league_id=league_id)

    return render_template('login.html', active_tab='league', league_id='', email='')


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
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
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

        # Get role_id
        role_row = db.execute("SELECT role_id FROM roles WHERE role_name = %s", (role_name,)).fetchone()
        db.execute(
            "INSERT INTO user_league_roles (user_id, league_id, role_id) VALUES (%s, %s, %s)",
            (user_id, league_id, role_row['role_id'])
        )
        db.commit()

        flash('Account created! You can now sign in with your email and password.', 'success')
        return redirect(url_for('auth.login', tab='user'))

    return render_template('auth/register.html',
                           league_id='', first_name='', last_name='', email='')


# --- Logout ---

@bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
