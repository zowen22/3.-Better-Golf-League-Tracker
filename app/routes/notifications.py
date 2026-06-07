"""
Notification center — bell icon + activity feed.

Notifications come from two sources:
  1. `notifications` table  — admin-posted announcements (existing system)
  2. `league_events` table  — auto-created system events (round saved, sub assigned)

Read tracking is per-user via `notification_reads`.
For anonymous / shared-password sessions, we fall back to a session cookie key.
"""

from flask import Blueprint, session, redirect, url_for, request, jsonify, render_template
from datetime import datetime, date
from routes.auth import login_required
from database import get_db

bp = Blueprint('notifications', __name__, url_prefix='/notifications')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_user_id():
    return session.get('user_id')


def _session_key():
    """Stable anonymous identifier stored in session for guests."""
    if 'anon_key' not in session:
        import uuid
        session['anon_key'] = str(uuid.uuid4())
    return session['anon_key']


def create_league_event(db, league_id, event_type, message, season_id=None, ref_id=None):
    """
    Create an automatic league event (round completed, sub assigned, etc.).
    Called from other blueprints after their db.commit().
    """
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    db.execute(
        """INSERT INTO league_events (league_id, season_id, event_type, message, created_at, ref_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (league_id, season_id, event_type, message, now, ref_id)
    )
    # Note: caller is responsible for db.commit()


def get_unread_count(db, league_id):
    """
    Return the number of unread items (announcements + events) for the current user.
    Used by context processor to show badge in nav.
    """
    user_id = _current_user_id()
    today = date.today().isoformat()

    # Count unread announcements
    if user_id:
        unread_ann = db.execute(
            """SELECT COUNT(*) FROM notifications n
               WHERE n.league_id = ?
                 AND n.active = 1
                 AND (n.display_until IS NULL OR n.display_until >= ?)
                 AND NOT EXISTS (
                     SELECT 1 FROM notification_reads nr
                     WHERE nr.notification_id = n.notification_id
                       AND nr.user_id = ?
                 )""",
            (league_id, today, user_id)
        ).fetchone()[0]
    else:
        sk = _session_key()
        unread_ann = db.execute(
            """SELECT COUNT(*) FROM notifications n
               WHERE n.league_id = ?
                 AND n.active = 1
                 AND (n.display_until IS NULL OR n.display_until >= ?)
                 AND NOT EXISTS (
                     SELECT 1 FROM notification_reads nr
                     WHERE nr.notification_id = n.notification_id
                       AND nr.session_key = ?
                 )""",
            (league_id, today, sk)
        ).fetchone()[0]

    # Count unread events (last 30 days)
    if user_id:
        unread_evt = db.execute(
            """SELECT COUNT(*) FROM league_events e
               WHERE e.league_id = ?
                 AND e.created_at >= date('now', '-30 days')
                 AND NOT EXISTS (
                     SELECT 1 FROM notification_reads nr
                     WHERE nr.notification_id = -(e.event_id)
                       AND nr.user_id = ?
                 )""",
            (league_id, user_id)
        ).fetchone()[0]
    else:
        sk = _session_key()
        unread_evt = db.execute(
            """SELECT COUNT(*) FROM league_events e
               WHERE e.league_id = ?
                 AND e.created_at >= date('now', '-30 days')
                 AND NOT EXISTS (
                     SELECT 1 FROM notification_reads nr
                     WHERE nr.notification_id = -(e.event_id)
                       AND nr.session_key = ?
                 )""",
            (league_id, sk)
        ).fetchone()[0]

    return unread_ann + unread_evt


def _mark_read(db, notification_id, user_id, session_key):
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    try:
        if user_id:
            db.execute(
                """INSERT OR IGNORE INTO notification_reads (notification_id, user_id, read_at)
                   VALUES (?, ?, ?)""",
                (notification_id, user_id, now)
            )
        else:
            db.execute(
                """INSERT OR IGNORE INTO notification_reads (notification_id, session_key, read_at)
                   VALUES (?, ?, ?)""",
                (notification_id, session_key, now)
            )
    except Exception:
        pass  # ignore duplicate key errors silently


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def index():
    db = get_db()
    league_id = session['league_id']
    today = date.today().isoformat()
    user_id = _current_user_id()
    sk = _session_key()

    # Fetch active announcements
    announcements = db.execute(
        """SELECT n.notification_id, n.type, n.message, n.created_date, n.display_until,
                  CASE WHEN nr.read_id IS NOT NULL THEN 1 ELSE 0 END AS is_read
           FROM notifications n
           LEFT JOIN notification_reads nr
             ON nr.notification_id = n.notification_id
             AND (nr.user_id = ? OR (? IS NULL AND nr.session_key = ?))
           WHERE n.league_id = ?
             AND n.active = 1
             AND (n.display_until IS NULL OR n.display_until >= ?)
           ORDER BY n.created_date DESC""",
        (user_id, user_id, sk, league_id, today)
    ).fetchall()

    # Fetch recent league events (last 60 days)
    events = db.execute(
        """SELECT e.event_id, e.event_type, e.message, e.created_at, e.season_id, e.ref_id,
                  CASE WHEN nr.read_id IS NOT NULL THEN 1 ELSE 0 END AS is_read
           FROM league_events e
           LEFT JOIN notification_reads nr
             ON nr.notification_id = -(e.event_id)
             AND (nr.user_id = ? OR (? IS NULL AND nr.session_key = ?))
           WHERE e.league_id = ?
             AND e.created_at >= date('now', '-60 days')
           ORDER BY e.created_at DESC""",
        (user_id, user_id, sk, league_id)
    ).fetchall()

    # Auto-mark all as read
    for ann in announcements:
        if not ann['is_read']:
            _mark_read(db, ann['notification_id'], user_id, sk)
    for evt in events:
        if not evt['is_read']:
            _mark_read(db, -(evt['event_id']), user_id, sk)
    db.commit()

    return render_template('notifications/index.html',
                           announcements=announcements,
                           events=events)


@bp.route('/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    db = get_db()
    user_id = _current_user_id()
    sk = _session_key()
    _mark_read(db, notif_id, user_id, sk)
    db.commit()
    return ('', 204)


@bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    db = get_db()
    league_id = session['league_id']
    today = date.today().isoformat()
    user_id = _current_user_id()
    sk = _session_key()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    if user_id:
        # Mark announcements
        db.execute(
            """INSERT OR IGNORE INTO notification_reads (notification_id, user_id, read_at)
               SELECT n.notification_id, ?, ?
               FROM notifications n
               WHERE n.league_id = ? AND n.active = 1
                 AND (n.display_until IS NULL OR n.display_until >= ?)""",
            (user_id, now, league_id, today)
        )
        # Mark events
        db.execute(
            """INSERT OR IGNORE INTO notification_reads (notification_id, user_id, read_at)
               SELECT -(e.event_id), ?, ?
               FROM league_events e
               WHERE e.league_id = ?
                 AND e.created_at >= date('now', '-60 days')""",
            (user_id, now, league_id)
        )
    else:
        db.execute(
            """INSERT OR IGNORE INTO notification_reads (notification_id, session_key, read_at)
               SELECT n.notification_id, ?, ?
               FROM notifications n
               WHERE n.league_id = ? AND n.active = 1
                 AND (n.display_until IS NULL OR n.display_until >= ?)""",
            (sk, now, league_id, today)
        )
        db.execute(
            """INSERT OR IGNORE INTO notification_reads (notification_id, session_key, read_at)
               SELECT -(e.event_id), ?, ?
               FROM league_events e
               WHERE e.league_id = ?
                 AND e.created_at >= date('now', '-60 days')""",
            (sk, now, league_id)
        )
    db.commit()
    return redirect(url_for('notifications.index'))
