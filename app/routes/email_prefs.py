"""
Email Notification Preferences — player-facing settings page.

Routes:
  GET  /account/email-preferences     — show current prefs
  POST /account/email-preferences     — save prefs
  POST /admin/players/<id>/email-prefs — admin toggle for any player
"""
import logging
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, g
from routes.auth import login_required, admin_required

bp = Blueprint('email_prefs', __name__)
log = logging.getLogger(__name__)


def _get_db():
    return g.db


def _get_player_prefs(db, player_id):
    """Return dict of email pref columns for a player. Defaults all False if columns absent."""
    try:
        row = db.execute(
            """SELECT COALESCE(email_opt_out, 0)               AS email_opt_out,
                      COALESCE(email_opt_out_round_results, 0) AS email_opt_out_round_results,
                      COALESCE(email_opt_out_reminders, 0)     AS email_opt_out_reminders,
                      email
               FROM players WHERE player_id = ?""",
            (player_id,)
        ).fetchone()
        if not row:
            return {}
        return dict(row)
    except Exception:
        return {}


# ── Player self-service page ─────────────────────────────────────────────────

@bp.route('/account/email-preferences', methods=['GET', 'POST'])
@login_required
def my_prefs():
    db = _get_db()
    league_id = session.get('league_id')
    player_id = session.get('player_id')

    # Page requires the account to be linked to a player
    if not player_id:
        flash('Your account is not linked to a player. Contact your commissioner.', 'warning')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        # Checkboxes are absent from form data when unchecked — treat missing as 0
        opt_out_all     = 1 if request.form.get('email_opt_out')               else 0
        opt_out_results = 1 if request.form.get('email_opt_out_round_results') else 0
        opt_out_remind  = 1 if request.form.get('email_opt_out_reminders')     else 0

        try:
            db.execute(
                """UPDATE players
                   SET email_opt_out = ?,
                       email_opt_out_round_results = ?,
                       email_opt_out_reminders = ?
                   WHERE player_id = ? AND league_id = ?""",
                (opt_out_all, opt_out_results, opt_out_remind, player_id, league_id)
            )
            db.commit()
            flash('Email preferences saved.', 'success')
        except Exception as e:
            log.error('email_prefs save failed: %s', e)
            flash('Could not save preferences. The migration may not have been run yet.', 'danger')

        return redirect(url_for('email_prefs.my_prefs'))

    prefs = _get_player_prefs(db, player_id)
    # Check if SMTP is configured (so we can warn if email isn't set up)
    email_enabled = False
    try:
        cfg = db.execute(
            "SELECT email_enabled FROM leagues WHERE league_id = ?", (league_id,)
        ).fetchone()
        email_enabled = bool(cfg and cfg['email_enabled'])
    except Exception:
        pass

    return render_template(
        'email_prefs/index.html',
        prefs=prefs,
        email_enabled=email_enabled,
    )


# ── Admin override for any player ───────────────────────────────────────────

@bp.route('/admin/players/<int:player_id>/email-prefs', methods=['POST'])
@admin_required
def admin_set_prefs(player_id):
    db = _get_db()
    league_id = session.get('league_id')

    opt_out_all     = 1 if request.form.get('email_opt_out')               else 0
    opt_out_results = 1 if request.form.get('email_opt_out_round_results') else 0
    opt_out_remind  = 1 if request.form.get('email_opt_out_reminders')     else 0

    try:
        db.execute(
            """UPDATE players
               SET email_opt_out = ?,
                   email_opt_out_round_results = ?,
                   email_opt_out_reminders = ?
               WHERE player_id = ? AND league_id = ?""",
            (opt_out_all, opt_out_results, opt_out_remind, player_id, league_id)
        )
        db.commit()
        flash('Email preferences updated for player.', 'success')
    except Exception as e:
        log.error('admin_set_prefs failed: %s', e)
        flash('Could not save. Run migrate_email_prefs.py first.', 'danger')

    return redirect(url_for('players.profile', player_id=player_id))
