"""Site-wide feedback/feature-request footer widget.

Deliberately simple: one table, one submit route, one read-only Site Admin
list. No categorization, no status workflow -- this is a direct line to
@user, not a support ticket system.
"""
from flask import Blueprint, request, redirect, session, flash
from database import get_db

bp = Blueprint('feedback', __name__, url_prefix='/feedback')

MAX_MESSAGE_LENGTH = 5000


@bp.route('/submit', methods=['POST'])
def submit():
    message = (request.form.get('message') or '').strip()
    if not message:
        flash('Feedback can\'t be empty.', 'error')
        return redirect(request.referrer or '/')

    message = message[:MAX_MESSAGE_LENGTH]
    db = get_db()
    db.execute(
        "INSERT INTO feedback (league_id, user_id, message, page_url) VALUES (%s, %s, %s, %s)",
        (session.get('league_id'), session.get('user_id'), message, request.referrer)
    )
    db.commit()
    flash('Thanks — got it!', 'success')
    return redirect(request.referrer or '/')
