"""
Forum blueprint — league message board.

Routes:
  GET  /forum                     topic list
  GET  /forum/new                 new topic form
  POST /forum/new                 create topic
  GET  /forum/<topic_id>          view topic + replies
  POST /forum/<topic_id>/reply    post a reply
  POST /forum/<topic_id>/delete   admin: delete topic
  POST /forum/<topic_id>/pin      admin: toggle pin
  POST /forum/<topic_id>/lock     admin: toggle lock
  POST /forum/reply/<reply_id>/delete  admin: delete reply
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import database
from database import get_db
from routes.auth import login_required, admin_required
from datetime import datetime, timezone

bp = Blueprint('forum', __name__)

POSTS_PER_PAGE = 20


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _author_name():
    """Return display name for the current session user."""
    name = session.get('user_name') or session.get('display_name') or ''
    if not name:
        # Try to load from users table
        user_id = session.get('user_id')
        if user_id:
            db = get_db()
            u = db.execute("SELECT first_name, last_name FROM users WHERE user_id = %s", (user_id,)).fetchone()
            if u:
                name = f"{u['first_name']} {u['last_name']}".strip()
    return name or 'League Member'


# ── Topic list ────────────────────────────────────────────────────────────────

@bp.route('/forum')
@login_required
def index():
    db = get_db()
    league_id = session['league_id']

    page = max(1, request.args.get('page', 1, type=int))
    offset = (page - 1) * POSTS_PER_PAGE

    total = db.execute(
        "SELECT COUNT(*) FROM forum_topics WHERE league_id = %s", (league_id,)
    ).fetchone()[0]

    topics = db.execute(
        """SELECT t.*,
                  (SELECT body FROM forum_replies r WHERE r.topic_id = t.topic_id ORDER BY r.created_at DESC LIMIT 1) AS last_reply_body,
                  (SELECT author_name FROM forum_replies r WHERE r.topic_id = t.topic_id ORDER BY r.created_at DESC LIMIT 1) AS last_reply_author,
                  (SELECT created_at FROM forum_replies r WHERE r.topic_id = t.topic_id ORDER BY r.created_at DESC LIMIT 1) AS last_reply_at
           FROM forum_topics t
           WHERE t.league_id = %s
           ORDER BY t.pinned DESC, t.updated_at DESC
           LIMIT %s OFFSET %s""",
        (league_id, POSTS_PER_PAGE, offset)
    ).fetchall()

    total_pages = max(1, (total + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE)
    return render_template('forum/index.html',
                           topics=topics,
                           page=page,
                           total_pages=total_pages,
                           total=total)


# ── New topic ─────────────────────────────────────────────────────────────────

@bp.route('/forum/new', methods=['GET', 'POST'])
@login_required
def new_topic():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        body  = request.form.get('body', '').strip()
        if not title or not body:
            flash('Title and message are required.', 'error')
            return render_template('forum/new_topic.html', title=title, body=body)

        db = get_db()
        league_id = session['league_id']
        author_id = session.get('user_id')
        author_name = _author_name()
        now = _now()

        sql = """INSERT INTO forum_topics (league_id, title, body, author_id, author_name, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        params = (league_id, title, body, author_id, author_name, now, now)
        if database.is_postgres():
            new_topic_id = db.execute(sql + " RETURNING topic_id", params).fetchone()[0]
        else:
            new_topic_id = db.execute(sql, params).lastrowid
        db.commit()
        flash('Topic posted!', 'success')
        return redirect(url_for('forum.view_topic', topic_id=new_topic_id))

    return render_template('forum/new_topic.html', title='', body='')


# ── View topic + replies ──────────────────────────────────────────────────────

@bp.route('/forum/<int:topic_id>')
@login_required
def view_topic(topic_id):
    db = get_db()
    league_id = session['league_id']

    topic = db.execute(
        "SELECT * FROM forum_topics WHERE topic_id = %s AND league_id = %s",
        (topic_id, league_id)
    ).fetchone()
    if not topic:
        flash('Topic not found.', 'error')
        return redirect(url_for('forum.index'))

    replies = db.execute(
        "SELECT * FROM forum_replies WHERE topic_id = %s ORDER BY created_at ASC",
        (topic_id,)
    ).fetchall()

    return render_template('forum/topic.html', topic=topic, replies=replies)


# ── Post reply ────────────────────────────────────────────────────────────────

@bp.route('/forum/<int:topic_id>/reply', methods=['POST'])
@login_required
def reply(topic_id):
    db = get_db()
    league_id = session['league_id']

    topic = db.execute(
        "SELECT * FROM forum_topics WHERE topic_id = %s AND league_id = %s",
        (topic_id, league_id)
    ).fetchone()
    if not topic:
        flash('Topic not found.', 'error')
        return redirect(url_for('forum.index'))

    if topic['locked'] and session.get('role') != 'league_admin':
        flash('This topic is locked.', 'error')
        return redirect(url_for('forum.view_topic', topic_id=topic_id))

    body = request.form.get('body', '').strip()
    if not body:
        flash('Reply cannot be empty.', 'error')
        return redirect(url_for('forum.view_topic', topic_id=topic_id))

    author_id = session.get('user_id')
    author_name = _author_name()
    now = _now()

    db.execute(
        "INSERT INTO forum_replies (topic_id, league_id, body, author_id, author_name, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
        (topic_id, league_id, body, author_id, author_name, now)
    )
    db.execute(
        "UPDATE forum_topics SET reply_count = reply_count + 1, updated_at = %s WHERE topic_id = %s",
        (now, topic_id)
    )
    db.commit()
    return redirect(url_for('forum.view_topic', topic_id=topic_id) + '#bottom')


# ── Admin: delete topic ───────────────────────────────────────────────────────

@bp.route('/forum/<int:topic_id>/delete', methods=['POST'])
@admin_required
def delete_topic(topic_id):
    db = get_db()
    league_id = session['league_id']
    db.execute("DELETE FROM forum_topics WHERE topic_id = %s AND league_id = %s", (topic_id, league_id))
    db.commit()
    flash('Topic deleted.', 'success')
    return redirect(url_for('forum.index'))


# ── Admin: toggle pin ─────────────────────────────────────────────────────────

@bp.route('/forum/<int:topic_id>/pin', methods=['POST'])
@admin_required
def toggle_pin(topic_id):
    db = get_db()
    league_id = session['league_id']
    topic = db.execute(
        "SELECT pinned FROM forum_topics WHERE topic_id = %s AND league_id = %s",
        (topic_id, league_id)
    ).fetchone()
    if topic:
        db.execute(
            "UPDATE forum_topics SET pinned = %s WHERE topic_id = %s",
            (0 if topic['pinned'] else 1, topic_id)
        )
        db.commit()
        flash('Topic pinned.' if not topic['pinned'] else 'Topic unpinned.', 'success')
    return redirect(url_for('forum.view_topic', topic_id=topic_id))


# ── Admin: toggle lock ────────────────────────────────────────────────────────

@bp.route('/forum/<int:topic_id>/lock', methods=['POST'])
@admin_required
def toggle_lock(topic_id):
    db = get_db()
    league_id = session['league_id']
    topic = db.execute(
        "SELECT locked FROM forum_topics WHERE topic_id = %s AND league_id = %s",
        (topic_id, league_id)
    ).fetchone()
    if topic:
        db.execute(
            "UPDATE forum_topics SET locked = %s WHERE topic_id = %s",
            (0 if topic['locked'] else 1, topic_id)
        )
        db.commit()
        flash('Topic locked.' if not topic['locked'] else 'Topic unlocked.', 'success')
    return redirect(url_for('forum.view_topic', topic_id=topic_id))


# ── Admin: delete reply ───────────────────────────────────────────────────────

@bp.route('/forum/reply/<int:reply_id>/delete', methods=['POST'])
@admin_required
def delete_reply(reply_id):
    db = get_db()
    league_id = session['league_id']
    r = db.execute(
        "SELECT topic_id FROM forum_replies WHERE reply_id = %s AND league_id = %s",
        (reply_id, league_id)
    ).fetchone()
    if r:
        topic_id = r['topic_id']
        db.execute("DELETE FROM forum_replies WHERE reply_id = %s", (reply_id,))
        db.execute(
            "UPDATE forum_topics SET reply_count = MAX(0, reply_count - 1) WHERE topic_id = %s",
            (topic_id,)
        )
        db.commit()
        flash('Reply deleted.', 'success')
        return redirect(url_for('forum.view_topic', topic_id=topic_id))
    flash('Reply not found.', 'error')
    return redirect(url_for('forum.index'))
