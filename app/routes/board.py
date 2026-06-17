"""
League Board blueprint — commissioner posts + emoji reactions.

Routes:
  GET  /board               view all posts
  POST /board/post          admin: create post
  POST /board/<id>/pin      admin: toggle pin
  POST /board/<id>/delete   admin: delete post
  POST /board/<id>/react    any member: toggle emoji reaction (JSON)
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db
from routes.auth import login_required, admin_required

bp = Blueprint('board', __name__, url_prefix='/board')

QUICK_EMOJIS = ['👍', '🔥', '⛳️', '🏌️', '💪', '😂']


def _current_user_id():
    return session.get('user_id')


# ---------------------------------------------------------------------------
# Member view
# ---------------------------------------------------------------------------

@bp.route('/')
@login_required
def index():
    db = get_db()
    league_id = session['league_id']
    user_id   = _current_user_id()

    posts = db.execute(
        """SELECT a.announcement_id, a.body, a.created_at, a.is_pinned,
                  u.display_name AS author_name
           FROM league_announcements a
           JOIN users u ON u.user_id = a.author_user_id
           WHERE a.league_id = %s
           ORDER BY a.is_pinned DESC, a.created_at DESC
           LIMIT 100""",
        (league_id,)
    ).fetchall()

    # Attach reaction data per post
    enriched = []
    for p in posts:
        reactions = db.execute(
            """SELECT emoji,
                      COUNT(*) AS cnt,
                      bool_or(user_id = %s) AS i_reacted
               FROM announcement_reactions
               WHERE announcement_id = %s
               GROUP BY emoji
               ORDER BY MIN(created_at)""",
            (user_id, p['announcement_id'])
        ).fetchall()
        enriched.append({
            'id':          p['announcement_id'],
            'body':        p['body'],
            'created_at':  p['created_at'],
            'is_pinned':   p['is_pinned'],
            'author_name': p['author_name'],
            'reactions':   [dict(r) for r in reactions],
        })

    return render_template('board/index.html',
        posts=enriched,
        quick_emojis=QUICK_EMOJIS,
    )


# ---------------------------------------------------------------------------
# Admin: create post
# ---------------------------------------------------------------------------

@bp.route('/post', methods=['POST'])
@admin_required
def post():
    db = get_db()
    body      = request.form.get('body', '').strip()
    is_pinned = bool(request.form.get('is_pinned'))

    if not body:
        flash('Post cannot be empty.', 'error')
        return redirect(url_for('board.index'))

    db.execute(
        """INSERT INTO league_announcements (league_id, author_user_id, body, is_pinned)
           VALUES (%s, %s, %s, %s)""",
        (session['league_id'], session['user_id'], body, is_pinned)
    )
    db.commit()
    flash('Posted to League Board.', 'success')
    return redirect(url_for('board.index'))


# ---------------------------------------------------------------------------
# Admin: pin toggle
# ---------------------------------------------------------------------------

@bp.route('/<int:post_id>/pin', methods=['POST'])
@admin_required
def pin(post_id):
    db = get_db()
    row = db.execute(
        "SELECT is_pinned FROM league_announcements WHERE announcement_id = %s AND league_id = %s",
        (post_id, session['league_id'])
    ).fetchone()
    if not row:
        flash('Post not found.', 'error')
        return redirect(url_for('board.index'))
    db.execute(
        "UPDATE league_announcements SET is_pinned = %s WHERE announcement_id = %s",
        (not row['is_pinned'], post_id)
    )
    db.commit()
    return redirect(url_for('board.index'))


# ---------------------------------------------------------------------------
# Admin: delete
# ---------------------------------------------------------------------------

@bp.route('/<int:post_id>/delete', methods=['POST'])
@admin_required
def delete(post_id):
    db = get_db()
    db.execute(
        "DELETE FROM league_announcements WHERE announcement_id = %s AND league_id = %s",
        (post_id, session['league_id'])
    )
    db.commit()
    flash('Post deleted.', 'success')
    return redirect(url_for('board.index'))


# ---------------------------------------------------------------------------
# Any member: emoji reaction toggle (JSON)
# ---------------------------------------------------------------------------

@bp.route('/<int:post_id>/react', methods=['POST'])
@login_required
def react(post_id):
    db = get_db()
    league_id = session['league_id']
    user_id   = _current_user_id()

    # Verify post belongs to this league
    row = db.execute(
        "SELECT announcement_id FROM league_announcements WHERE announcement_id = %s AND league_id = %s",
        (post_id, league_id)
    ).fetchone()
    if not row:
        return jsonify({'ok': False}), 404

    emoji = (request.get_json(silent=True) or {}).get('emoji', '').strip()
    if not emoji:
        return jsonify({'ok': False}), 400

    existing = db.execute(
        "SELECT reaction_id FROM announcement_reactions WHERE announcement_id = %s AND user_id = %s AND emoji = %s",
        (post_id, user_id, emoji)
    ).fetchone()

    if existing:
        db.execute("DELETE FROM announcement_reactions WHERE reaction_id = %s", (existing['reaction_id'],))
        added = False
    else:
        db.execute(
            "INSERT INTO announcement_reactions (announcement_id, user_id, emoji) VALUES (%s, %s, %s)",
            (post_id, user_id, emoji)
        )
        added = True
    db.commit()

    # Return updated counts for this post
    reactions = db.execute(
        """SELECT emoji, COUNT(*) AS cnt, bool_or(user_id = %s) AS i_reacted
           FROM announcement_reactions
           WHERE announcement_id = %s
           GROUP BY emoji
           ORDER BY MIN(created_at)""",
        (user_id, post_id)
    ).fetchall()

    return jsonify({
        'ok': True,
        'added': added,
        'reactions': [{'emoji': r['emoji'], 'count': r['cnt'], 'i_reacted': bool(r['i_reacted'])} for r in reactions],
    })
