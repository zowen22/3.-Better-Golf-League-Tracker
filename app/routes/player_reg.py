"""
Player Self-Registration
 - Public join form at /join/<league_id>
 - Admin approval queue at /admin/registrations
 - Approve / reject actions
"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash)
from database import get_db
from routes.auth import admin_required
from datetime import datetime

bp = Blueprint('player_reg', __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pending_reg_count(db, league_id):
    """Return count of pending registrations for badge display. Graceful."""
    try:
        row = db.execute(
            "SELECT COUNT(*) AS cnt FROM player_registrations "
            "WHERE league_id=%s AND status='pending'",
            (league_id,)
        ).fetchone()
        return row['cnt'] if row else 0
    except Exception:
        return 0


def _get_league(db, league_id):
    return db.execute(
        "SELECT * FROM leagues WHERE league_id=%s AND active=1",
        (league_id,)
    ).fetchone()


# ---------------------------------------------------------------------------
# Public join form
# ---------------------------------------------------------------------------

@bp.route('/join/<league_id>', methods=['GET', 'POST'])
def join(league_id):
    db = get_db()
    league = _get_league(db, league_id)
    if not league:
        return render_template('registration/not_found.html'), 404

    # Check registrations are enabled
    try:
        reg_enabled = league['reg_enabled']
    except (IndexError, KeyError):
        reg_enabled = 0

    if not reg_enabled:
        return render_template('registration/closed.html', league=league), 403

    try:
        welcome_msg = league['reg_welcome_msg'] or ''
    except (IndexError, KeyError):
        welcome_msg = ''

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        email      = request.form.get('email', '').strip().lower()
        try:
            hdcp = float(request.form.get('starting_handicap', '0') or '0')
            hdcp = max(0.0, min(54.0, hdcp))
        except (ValueError, TypeError):
            hdcp = 0.0
        message = request.form.get('message', '').strip()[:500]

        errors = []
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if email and '@' not in email:
            errors.append('Please enter a valid email address.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('registration/join.html',
                                   league=league, welcome_msg=welcome_msg,
                                   first_name=first_name, last_name=last_name,
                                   email=email, starting_handicap=hdcp,
                                   message=message)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            db.execute(
                """INSERT INTO player_registrations
                   (league_id, first_name, last_name, email, starting_handicap, message, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)""",
                (league_id, first_name, last_name, email or None, hdcp, message or None, now)
            )
            db.commit()
        except Exception as e:
            flash('Something went wrong. Please try again.', 'error')
            return render_template('registration/join.html',
                                   league=league, welcome_msg=welcome_msg,
                                   first_name=first_name, last_name=last_name,
                                   email=email, starting_handicap=hdcp,
                                   message=message)

        return render_template('registration/submitted.html', league=league,
                               first_name=first_name, last_name=last_name)

    return render_template('registration/join.html',
                           league=league, welcome_msg=welcome_msg,
                           first_name='', last_name='', email='',
                           starting_handicap=0, message='')


# ---------------------------------------------------------------------------
# Admin: registration settings
# ---------------------------------------------------------------------------

@bp.route('/admin/registration-settings', methods=['GET', 'POST'])
@admin_required
def reg_settings():
    db = get_db()
    league = db.execute(
        "SELECT * FROM leagues WHERE league_id=%s", (session['league_id'],)
    ).fetchone()

    try:
        reg_enabled = league['reg_enabled']
        welcome_msg = league['reg_welcome_msg'] or ''
    except (IndexError, KeyError):
        reg_enabled = 0
        welcome_msg = ''

    if request.method == 'POST':
        enabled = 1 if request.form.get('reg_enabled') else 0
        msg = request.form.get('welcome_msg', '').strip()[:500]
        try:
            db.execute(
                "UPDATE leagues SET reg_enabled=%s, reg_welcome_msg=%s WHERE league_id=%s",
                (enabled, msg or None, session['league_id'])
            )
            db.commit()
            flash('Registration settings saved.', 'success')
        except Exception:
            flash('Error saving settings. Run the migration first.', 'error')
        return redirect(url_for('player_reg.reg_settings'))

    join_url = url_for('player_reg.join', league_id=session['league_id'], _external=True)
    pending_count = pending_reg_count(db, session['league_id'])
    return render_template('registration/admin_settings.html',
                           league=league, reg_enabled=reg_enabled,
                           welcome_msg=welcome_msg, join_url=join_url,
                           pending_count=pending_count)


# ---------------------------------------------------------------------------
# Admin: approval queue
# ---------------------------------------------------------------------------

@bp.route('/admin/registrations')
@admin_required
def admin_queue():
    db = get_db()
    pending = db.execute(
        """SELECT * FROM player_registrations
           WHERE league_id=%s AND status='pending'
           ORDER BY created_at ASC""",
        (session['league_id'],)
    ).fetchall()
    recent = db.execute(
        """SELECT r.*, u.first_name AS reviewer_first, u.last_name AS reviewer_last
           FROM player_registrations r
           LEFT JOIN users u ON r.reviewed_by_user_id = u.user_id
           WHERE r.league_id=%s AND r.status != 'pending'
           ORDER BY r.reviewed_at DESC
           LIMIT 30""",
        (session['league_id'],)
    ).fetchall()
    join_url = url_for('player_reg.join', league_id=session['league_id'], _external=True)
    return render_template('registration/admin_queue.html',
                           pending=pending, recent=recent,
                           join_url=join_url)


# ---------------------------------------------------------------------------
# Admin: approve registration → create player
# ---------------------------------------------------------------------------

@bp.route('/admin/registrations/<int:reg_id>/approve', methods=['POST'])
@admin_required
def approve(reg_id):
    db = get_db()
    reg = db.execute(
        "SELECT * FROM player_registrations WHERE reg_id=%s AND league_id=%s",
        (reg_id, session['league_id'])
    ).fetchone()
    if not reg or reg['status'] != 'pending':
        flash('Registration not found or already reviewed.', 'error')
        return redirect(url_for('player_reg.admin_queue'))

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    today = now[:10]
    user_id = session.get('user_id')

    # Create the player record
    player_id = db.execute(
        """INSERT INTO players
           (league_id, first_name, last_name, email, starting_handicap, handicap_index, active, created_date)
           VALUES (%s, %s, %s, %s, %s, %s, 1, %s) RETURNING player_id""",
        (session['league_id'], reg['first_name'], reg['last_name'],
         reg['email'], reg['starting_handicap'], reg['starting_handicap'], today)
    ).fetchone()['player_id']

    # Update registration record
    db.execute(
        """UPDATE player_registrations
           SET status='approved', reviewed_at=%s, reviewed_by_user_id=%s, player_id=%s
           WHERE reg_id=%s""",
        (now, user_id, player_id, reg_id)
    )
    db.commit()

    flash(f"{reg['first_name']} {reg['last_name']} approved and added as a player.", 'success')
    return redirect(url_for('player_reg.admin_queue'))


# ---------------------------------------------------------------------------
# Admin: reject registration
# ---------------------------------------------------------------------------

@bp.route('/admin/registrations/<int:reg_id>/reject', methods=['POST'])
@admin_required
def reject(reg_id):
    db = get_db()
    reg = db.execute(
        "SELECT * FROM player_registrations WHERE reg_id=%s AND league_id=%s",
        (reg_id, session['league_id'])
    ).fetchone()
    if not reg or reg['status'] != 'pending':
        flash('Registration not found or already reviewed.', 'error')
        return redirect(url_for('player_reg.admin_queue'))

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user_id = session.get('user_id')

    db.execute(
        """UPDATE player_registrations
           SET status='rejected', reviewed_at=%s, reviewed_by_user_id=%s
           WHERE reg_id=%s""",
        (now, user_id, reg_id)
    )
    db.commit()

    flash(f"{reg['first_name']} {reg['last_name']}'s registration rejected.", 'success')
    return redirect(url_for('player_reg.admin_queue'))
