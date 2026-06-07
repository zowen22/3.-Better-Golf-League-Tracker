from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import login_required, admin_required
from datetime import date
from routes.notifications import create_league_event

bp = Blueprint('announcements', __name__, url_prefix='/announcements')

NOTIFICATION_TYPES = [
    ('general',   'General'),
    ('schedule',  'Schedule'),
    ('weather',   'Weather / Cancellation'),
    ('results',   'Results'),
    ('reminder',  'Reminder'),
    ('important', 'Important'),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_announcements(db, league_id):
    """Return all currently-active announcements for a league."""
    today = date.today().isoformat()
    return db.execute(
        """SELECT * FROM notifications
           WHERE league_id = ? AND active = 1
             AND (display_until IS NULL OR display_until = '' OR display_until >= ?)
           ORDER BY created_date DESC""",
        (league_id, today)
    ).fetchall()


# ---------------------------------------------------------------------------
# Member view: /announcements/
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def index():
    db = get_db()
    league_id = session['league_id']
    today = date.today().isoformat()

    active = db.execute(
        """SELECT * FROM notifications
           WHERE league_id = ? AND active = 1
             AND (display_until IS NULL OR display_until = '' OR display_until >= ?)
           ORDER BY created_date DESC""",
        (league_id, today)
    ).fetchall()

    expired = db.execute(
        """SELECT * FROM notifications
           WHERE league_id = ? AND active = 1
             AND display_until IS NOT NULL AND display_until != '' AND display_until < ?
           ORDER BY display_until DESC
           LIMIT 10""",
        (league_id, today)
    ).fetchall()

    return render_template('announcements/index.html',
        active=active,
        expired=expired,
        notification_types=dict(NOTIFICATION_TYPES),
    )


# ---------------------------------------------------------------------------
# Admin: manage announcements
# ---------------------------------------------------------------------------

@bp.route('/manage')
@admin_required
def manage():
    db = get_db()
    league_id = session['league_id']

    all_notices = db.execute(
        "SELECT * FROM notifications WHERE league_id = ? ORDER BY created_date DESC",
        (league_id,)
    ).fetchall()

    today = date.today().isoformat()

    return render_template('announcements/manage.html',
        all_notices=all_notices,
        notification_types=dict(NOTIFICATION_TYPES),
        notification_type_list=NOTIFICATION_TYPES,
        today=today,
    )


@bp.route('/create', methods=['POST'])
@admin_required
def create():
    db = get_db()
    league_id = session['league_id']

    notif_type   = request.form.get('type', 'general').strip()
    message      = request.form.get('message', '').strip()
    display_until = request.form.get('display_until', '').strip() or None

    if not message:
        flash('Announcement message cannot be empty.', 'error')
        return redirect(url_for('announcements.manage'))

    db.execute(
        """INSERT INTO notifications (league_id, type, message, created_date, display_until, active)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (league_id, notif_type, message, date.today().isoformat(), display_until)
    )
    db.commit()
    # Fire announcement event so it appears in the notification feed
    try:
        preview = message[:80] + ('…' if len(message) > 80 else '')
        create_league_event(db, league_id, 'announcement',
                            f"New announcement: {preview}")
        db.commit()
    except Exception:
        pass
    # Fire email to all players (if configured)
    try:
        from routes.email_config import send_announcement_email
        send_announcement_email(db, league_id, message, notif_type)
    except Exception:
        pass
    flash('Announcement posted.', 'success')
    return redirect(url_for('announcements.manage'))


@bp.route('/<int:notif_id>/toggle', methods=['POST'])
@admin_required
def toggle(notif_id):
    db = get_db()
    league_id = session['league_id']

    row = db.execute(
        "SELECT * FROM notifications WHERE notification_id = ? AND league_id = ?",
        (notif_id, league_id)
    ).fetchone()
    if not row:
        flash('Announcement not found.', 'error')
        return redirect(url_for('announcements.manage'))

    new_active = 0 if row['active'] else 1
    db.execute(
        "UPDATE notifications SET active = ? WHERE notification_id = ?",
        (new_active, notif_id)
    )
    db.commit()
    flash('Announcement updated.', 'success')
    return redirect(url_for('announcements.manage'))


@bp.route('/<int:notif_id>/delete', methods=['POST'])
@admin_required
def delete(notif_id):
    db = get_db()
    league_id = session['league_id']

    row = db.execute(
        "SELECT notification_id FROM notifications WHERE notification_id = ? AND league_id = ?",
        (notif_id, league_id)
    ).fetchone()
    if not row:
        flash('Announcement not found.', 'error')
        return redirect(url_for('announcements.manage'))

    db.execute("DELETE FROM notifications WHERE notification_id = ?", (notif_id,))
    db.commit()
    flash('Announcement deleted.', 'success')
    return redirect(url_for('announcements.manage'))


@bp.route('/<int:notif_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(notif_id):
    db = get_db()
    league_id = session['league_id']

    row = db.execute(
        "SELECT * FROM notifications WHERE notification_id = ? AND league_id = ?",
        (notif_id, league_id)
    ).fetchone()
    if not row:
        flash('Announcement not found.', 'error')
        return redirect(url_for('announcements.manage'))

    if request.method == 'POST':
        notif_type    = request.form.get('type', 'general').strip()
        message       = request.form.get('message', '').strip()
        display_until = request.form.get('display_until', '').strip() or None

        if not message:
            flash('Message cannot be empty.', 'error')
            return redirect(url_for('announcements.edit', notif_id=notif_id))

        db.execute(
            """UPDATE notifications
               SET type = ?, message = ?, display_until = ?
               WHERE notification_id = ?""",
            (notif_type, message, display_until, notif_id)
        )
        db.commit()
        flash('Announcement updated.', 'success')
        return redirect(url_for('announcements.manage'))

    return render_template('announcements/edit.html',
        notice=row,
        notification_type_list=NOTIFICATION_TYPES,
    )
