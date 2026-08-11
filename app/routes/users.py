from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
from datetime import datetime
from routes.auth import login_required, admin_required, account_required

bp = Blueprint('users', __name__, url_prefix='/users')


# ── Admin: list all user accounts in this league ──────────────────────────

@bp.route('/')
@admin_required
def list_users():
    db = get_db()
    league_id = session['league_id']

    users = db.execute(
        """SELECT u.user_id, u.first_name, u.last_name, u.email,
                  u.active, u.created_date,
                  r.role_name,
                  p.player_id, p.first_name AS p_first, p.last_name AS p_last
           FROM users u
           JOIN user_league_roles ulr ON ulr.user_id = u.user_id
           JOIN roles r ON r.role_id = ulr.role_id
           LEFT JOIN players p ON p.user_id = u.user_id AND p.league_id = %s
           WHERE ulr.league_id = %s
           ORDER BY u.last_name, u.first_name""",
        (league_id, league_id)
    ).fetchall()

    # Players not yet linked to a user account
    unlinked = db.execute(
        """SELECT player_id, first_name, last_name
           FROM players
           WHERE league_id = %s AND active = 1 AND (user_id IS NULL OR user_id = 0)
           ORDER BY last_name, first_name""",
        (league_id,)
    ).fetchall()

    return render_template('users/list.html',
                           users=users,
                           unlinked=unlinked)


# ── Admin: link / unlink a user to a player ──────────────────────────────

@bp.route('/<int:user_id>/link-player', methods=['POST'])
@admin_required
def link_player(user_id):
    db = get_db()
    league_id  = session['league_id']
    player_id  = request.form.get('player_id', '').strip()

    # Verify user belongs to this league
    ulr = db.execute(
        "SELECT id FROM user_league_roles WHERE user_id = %s AND league_id = %s",
        (user_id, league_id)
    ).fetchone()
    if not ulr:
        flash('User not found in this league.', 'error')
        return redirect(url_for('users.list_users'))

    # Unlink any player currently linked to this user in this league
    db.execute(
        "UPDATE players SET user_id = NULL WHERE user_id = %s AND league_id = %s",
        (user_id, league_id)
    )

    if player_id:
        # Unlink that player from any other user
        db.execute(
            "UPDATE players SET user_id = NULL WHERE player_id = %s AND league_id = %s",
            (player_id, league_id)
        )
        db.execute(
            "UPDATE players SET user_id = %s WHERE player_id = %s AND league_id = %s",
            (user_id, player_id, league_id)
        )
        flash('Player linked to user account.', 'success')
    else:
        flash('Player unlinked from user account.', 'success')

    db.commit()
    return redirect(url_for('users.list_users'))


# ── Admin: change a user's role ──────────────────────────────────────────

@bp.route('/<int:user_id>/set-role', methods=['POST'])
@admin_required
def set_role(user_id):
    db = get_db()
    league_id = session['league_id']
    role_name = request.form.get('role_name', '').strip()

    if role_name not in ('league_admin', 'member'):
        flash('Invalid role.', 'error')
        return redirect(url_for('users.list_users'))

    role_row = db.execute("SELECT role_id FROM roles WHERE role_name = %s", (role_name,)).fetchone()
    if not role_row:
        flash('Role not found.', 'error')
        return redirect(url_for('users.list_users'))

    # Verify user is in this league
    ulr = db.execute(
        "SELECT id FROM user_league_roles WHERE user_id = %s AND league_id = %s",
        (user_id, league_id)
    ).fetchone()
    if not ulr:
        flash('User not found in this league.', 'error')
        return redirect(url_for('users.list_users'))

    db.execute(
        "UPDATE user_league_roles SET role_id = %s WHERE user_id = %s AND league_id = %s",
        (role_row['role_id'], user_id, league_id)
    )
    db.commit()
    flash('Role updated.', 'success')
    return redirect(url_for('users.list_users'))


# ── Admin: activate / deactivate a user ──────────────────────────────────

@bp.route('/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_active(user_id):
    db = get_db()
    league_id = session['league_id']

    # Verify user is in this league
    ulr = db.execute(
        "SELECT id FROM user_league_roles WHERE user_id = %s AND league_id = %s",
        (user_id, league_id)
    ).fetchone()
    if not ulr:
        flash('User not found in this league.', 'error')
        return redirect(url_for('users.list_users'))

    user = db.execute("SELECT active FROM users WHERE user_id = %s", (user_id,)).fetchone()
    new_status = 0 if user['active'] else 1
    db.execute("UPDATE users SET active = %s WHERE user_id = %s", (new_status, user_id))
    db.commit()

    label = 'reactivated' if new_status else 'deactivated'
    flash(f'User account {label}.', 'success')
    return redirect(url_for('users.list_users'))


# ── Admin: reset a user's password ───────────────────────────────────────

@bp.route('/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_password(user_id):
    db = get_db()
    league_id    = session['league_id']
    new_password = request.form.get('new_password', '').strip()

    if len(new_password) < 6:
        flash('New password must be at least 6 characters.', 'error')
        return redirect(url_for('users.list_users'))

    ulr = db.execute(
        "SELECT id FROM user_league_roles WHERE user_id = %s AND league_id = %s",
        (user_id, league_id)
    ).fetchone()
    if not ulr:
        flash('User not found in this league.', 'error')
        return redirect(url_for('users.list_users'))

    db.execute(
        "UPDATE users SET password_hash = %s WHERE user_id = %s",
        (generate_password_hash(new_password), user_id)
    )
    db.commit()
    flash('Password reset successfully.', 'success')
    return redirect(url_for('users.list_users'))


# ── My Leagues (individual accounts -- see Plans/2026-08-11-multi-league- ─
#    individual-accounts-technical-spec.md) ───────────────────────────────

@bp.route('/my-leagues')
@account_required
def my_leagues():
    db = get_db()
    user_id = session['user_id']
    leagues = db.execute(
        """SELECT l.league_id, l.league_name, r.role_name
           FROM user_league_roles ulr
           JOIN leagues l ON l.league_id = ulr.league_id
           JOIN roles r ON r.role_id = ulr.role_id
           WHERE ulr.user_id = %s AND l.active = 1
           ORDER BY l.league_name""",
        (user_id,)
    ).fetchall()
    return render_template(
        'users/my_leagues.html',
        leagues=leagues,
        active_league_id=session.get('league_id'),
    )


@bp.route('/my-leagues/add', methods=['GET', 'POST'])
@account_required
def add_league():
    if request.method == 'POST':
        league_code     = request.form.get('league_id', '').strip().lower()
        league_password = request.form.get('league_password', '')

        if not league_code or not league_password:
            flash('League ID and password are required.', 'error')
            return render_template('users/add_league.html', league_id=league_code)

        db = get_db()
        league = db.execute(
            "SELECT * FROM leagues WHERE LOWER(login_code) = %s AND active = 1",
            (league_code,)
        ).fetchone()
        if not league:
            flash('League ID not found.', 'error')
            return render_template('users/add_league.html', league_id=league_code)

        # Same role-by-password convention as register() -- whichever
        # shared password matches decides the role for this account in
        # this league.
        role_name = None
        if check_password_hash(league['admin_password_hash'] or '', league_password):
            role_name = 'league_admin'
        elif check_password_hash(league['member_password_hash'] or '', league_password):
            role_name = 'member'
        else:
            flash('Incorrect league password.', 'error')
            return render_template('users/add_league.html', league_id=league_code)

        role_row = db.execute("SELECT role_id FROM roles WHERE role_name = %s", (role_name,)).fetchone()
        if not role_row:
            role_row = db.execute(
                "INSERT INTO roles (role_name) VALUES (%s) RETURNING role_id",
                (role_name,)
            ).fetchone()

        user_id = session['user_id']
        existing = db.execute(
            "SELECT id FROM user_league_roles WHERE user_id = %s AND league_id = %s",
            (user_id, league['league_id'])
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE user_league_roles SET role_id = %s WHERE id = %s",
                (role_row['role_id'], existing['id'])
            )
            flash(f"Already linked to {league['league_name']} -- role updated.", 'success')
        else:
            db.execute(
                "INSERT INTO user_league_roles (user_id, league_id, role_id) VALUES (%s, %s, %s)",
                (user_id, league['league_id'], role_row['role_id'])
            )
            flash(f"Added {league['league_name']} to your account.", 'success')
        db.commit()

        return redirect(url_for('switch_league', league_id=league['league_id']))

    return render_template('users/add_league.html', league_id='')


@bp.route('/my-leagues/<int:league_id>/remove', methods=['POST'])
@account_required
def remove_league(league_id):
    db = get_db()
    user_id = session['user_id']

    row = db.execute(
        "SELECT id FROM user_league_roles WHERE user_id = %s AND league_id = %s",
        (user_id, league_id)
    ).fetchone()
    if not row:
        flash('That league is not linked to your account.', 'error')
        return redirect(url_for('users.my_leagues'))

    db.execute("DELETE FROM user_league_roles WHERE id = %s", (row['id'],))
    db.commit()
    flash(
        "Removed from your account. This only removes the connection between "
        "your individual account and that league; nothing was deleted, and "
        "you can still get in anytime with the shared League ID and "
        "password. You can add it back from here later too.",
        'success'
    )

    if session.get('league_id') == league_id:
        remaining = db.execute(
            """SELECT ulr.league_id
               FROM user_league_roles ulr
               JOIN leagues l ON l.league_id = ulr.league_id
               WHERE ulr.user_id = %s AND l.active = 1
               ORDER BY ulr.id
               LIMIT 1""",
            (user_id,)
        ).fetchone()
        if remaining:
            return redirect(url_for('switch_league', league_id=remaining['league_id']))
        # No leagues left on the account -- stay logged in at the account
        # level (account_required still lets My Leagues/Add League
        # through), just clear the now-stale league-scoped session keys.
        for key in ('league_id', 'league_name', 'role', 'player_id', 'current_season_id'):
            session.pop(key, None)

    return redirect(url_for('users.my_leagues'))


# ── My Account (any logged-in user with a user_id in session) ────────────

@bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    user_id = session.get('user_id')
    if not user_id:
        flash('Your session uses a shared league password. Create a personal account to access account settings.', 'info')
        return redirect(url_for('main.dashboard'))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id = %s", (user_id,)).fetchone()
    if not user:
        flash('Account not found.', 'error')
        return redirect(url_for('main.dashboard'))

    # Get linked player
    player = db.execute(
        "SELECT player_id, first_name, last_name FROM players WHERE user_id = %s AND league_id = %s",
        (user_id, session['league_id'])
    ).fetchone()

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'update_info':
            first_name = request.form.get('first_name', '').strip()
            last_name  = request.form.get('last_name', '').strip()
            email      = request.form.get('email', '').strip().lower()

            if not first_name or not last_name:
                flash('First and last name are required.', 'error')
                return render_template('users/account.html', user=user, player=player)
            if not email or '@' not in email:
                flash('A valid email is required.', 'error')
                return render_template('users/account.html', user=user, player=player)

            # Check email not taken by another user
            dupe = db.execute(
                "SELECT user_id FROM users WHERE LOWER(email) = %s AND user_id != %s",
                (email, user_id)
            ).fetchone()
            if dupe:
                flash('That email is already in use by another account.', 'error')
                return render_template('users/account.html', user=user, player=player)

            db.execute(
                "UPDATE users SET first_name = %s, last_name = %s, email = %s WHERE user_id = %s",
                (first_name, last_name, email, user_id)
            )
            db.commit()
            session['user_display_name'] = f"{first_name} {last_name}"
            flash('Profile updated.', 'success')
            return redirect(url_for('users.account'))

        elif action == 'change_password':
            current_pw  = request.form.get('current_password', '')
            new_pw      = request.form.get('new_password', '')
            confirm_pw  = request.form.get('confirm_password', '')

            if not check_password_hash(user['password_hash'] or '', current_pw):
                flash('Current password is incorrect.', 'error')
                return render_template('users/account.html', user=user, player=player)
            if len(new_pw) < 6:
                flash('New password must be at least 6 characters.', 'error')
                return render_template('users/account.html', user=user, player=player)
            if new_pw != confirm_pw:
                flash('New passwords do not match.', 'error')
                return render_template('users/account.html', user=user, player=player)

            db.execute(
                "UPDATE users SET password_hash = %s WHERE user_id = %s",
                (generate_password_hash(new_pw), user_id)
            )
            db.commit()
            flash('Password changed successfully.', 'success')
            return redirect(url_for('users.account'))

    return render_template('users/account.html', user=user, player=player)
