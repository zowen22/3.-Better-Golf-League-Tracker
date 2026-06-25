"""
Dues blueprint — track league dues payments per season.

Routes:
  GET  /dues/season/<id>                     member: own payment status
  GET  /admin/season/<id>/dues               admin: all-player status table
  POST /admin/season/<id>/dues/pay           admin: record a payment
  POST /admin/season/<id>/dues/delete/<pid>  admin: delete a payment
  POST /admin/season/<id>/dues/settings      admin: update dues_amount / dues_due_date
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db
from routes.auth import login_required, admin_required

bp = Blueprint('dues', __name__)

PAYMENT_METHODS = ['Cash', 'Venmo', 'PayPal', 'Check', 'Zelle', 'Other']

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_dues_settings(db, league_id, season_id):
    row = db.execute(
        "SELECT dues_amount, dues_due_date, show_dues_shame_widget FROM league_settings WHERE league_id=%s AND season_id=%s",
        (league_id, season_id)
    ).fetchone()
    if row is None:
        return None, None, 0
    return row['dues_amount'], row['dues_due_date'], row['show_dues_shame_widget'] or 0


def _get_season(db, season_id, league_id):
    return db.execute(
        "SELECT * FROM seasons WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()


# ── Member view ──────────────────────────────────────────────────────────────

@bp.route('/dues/season/<int:season_id>')
@login_required
def member_view(season_id):
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.dashboard'))

    dues_amount, dues_due_date, show_dues_shame_widget = _get_dues_settings(db, league_id, season_id)

    # Get active players in this season via teams
    players = db.execute(
        """SELECT DISTINCT p.player_id, p.first_name, p.last_name
           FROM players p
           JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           WHERE t.season_id = %s AND t.league_id = %s AND p.active = 1
           ORDER BY p.last_name, p.first_name""",
        (season_id, league_id)
    ).fetchall()

    # Payments for this season
    payments = db.execute(
        """SELECT dp.*, p.first_name, p.last_name
           FROM dues_payments dp
           JOIN players p ON p.player_id = dp.player_id
           WHERE dp.season_id = %s AND dp.league_id = %s
           ORDER BY dp.paid_date DESC""",
        (season_id, league_id)
    ).fetchall()

    paid_player_ids = set(r['player_id'] for r in payments)

    # Current logged-in user's player_id (if individual account)
    user_id = session.get('user_id')
    my_player_id = None
    if user_id:
        urow = db.execute("SELECT player_id FROM users WHERE user_id=%s", (user_id,)).fetchone()
        if urow:
            my_player_id = urow['player_id']

    # Build per-player payment summary for the logged-in player only (if linked)
    my_payments = []
    if my_player_id:
        my_payments = [r for r in payments if r['player_id'] == my_player_id]

    paid_count = len(paid_player_ids)
    total_count = len(players)

    return render_template(
        'dues/member.html',
        season=season,
        players=players,
        payments=payments,
        paid_player_ids=paid_player_ids,
        my_player_id=my_player_id,
        my_payments=my_payments,
        dues_amount=dues_amount,
        dues_due_date=dues_due_date,
        paid_count=paid_count,
        total_count=total_count,
    )


# ── Admin: full dues management ───────────────────────────────────────────────

@bp.route('/admin/season/<int:season_id>/dues')
@admin_required
def admin_dues(season_id):
    db = get_db()
    league_id = session['league_id']

    season = _get_season(db, season_id, league_id)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('admin.index'))

    dues_amount, dues_due_date, show_dues_shame_widget = _get_dues_settings(db, league_id, season_id)

    # All active players in this season
    players = db.execute(
        """SELECT DISTINCT p.player_id, p.first_name, p.last_name
           FROM players p
           JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           WHERE t.season_id = %s AND t.league_id = %s AND p.active = 1
           ORDER BY p.last_name, p.first_name""",
        (season_id, league_id)
    ).fetchall()

    # All payments for this season
    payments = db.execute(
        """SELECT dp.*, p.first_name, p.last_name
           FROM dues_payments dp
           JOIN players p ON p.player_id = dp.player_id
           WHERE dp.season_id = %s AND dp.league_id = %s
           ORDER BY dp.paid_date DESC, dp.payment_id DESC""",
        (season_id, league_id)
    ).fetchall()

    # Build paid_map: player_id -> list of payments
    paid_map = {}
    for row in payments:
        pid = row['player_id']
        if pid not in paid_map:
            paid_map[pid] = []
        paid_map[pid].append(row)

    paid_count = len(paid_map)
    total_collected = sum(r['amount'] for r in payments)
    total_expected = (dues_amount or 0) * len(players) if dues_amount else None

    return render_template(
        'dues/admin.html',
        season=season,
        players=players,
        payments=payments,
        paid_map=paid_map,
        dues_amount=dues_amount,
        dues_due_date=dues_due_date,
        show_dues_shame_widget=show_dues_shame_widget,
        paid_count=paid_count,
        total_count=len(players),
        total_collected=total_collected,
        total_expected=total_expected,
        payment_methods=PAYMENT_METHODS,
    )


@bp.route('/admin/season/<int:season_id>/dues/settings', methods=['POST'])
@admin_required
def admin_dues_settings(season_id):
    db = get_db()
    league_id = session['league_id']

    dues_amount_str = request.form.get('dues_amount', '').strip()
    dues_due_date = request.form.get('dues_due_date', '').strip() or None
    show_dues_shame_widget = 1 if request.form.get('show_dues_shame_widget') else 0

    dues_amount = None
    if dues_amount_str:
        try:
            dues_amount = float(dues_amount_str)
        except ValueError:
            flash('Invalid dues amount.', 'error')
            return redirect(url_for('dues.admin_dues', season_id=season_id))

    db.execute(
        """UPDATE league_settings
           SET dues_amount=%s, dues_due_date=%s, show_dues_shame_widget=%s
           WHERE league_id=%s AND season_id=%s""",
        (dues_amount, dues_due_date, show_dues_shame_widget, league_id, season_id)
    )
    db.commit()
    flash('Dues settings updated.', 'success')
    return redirect(url_for('dues.admin_dues', season_id=season_id))


@bp.route('/admin/season/<int:season_id>/dues/pay', methods=['POST'])
@admin_required
def admin_record_payment(season_id):
    db = get_db()
    league_id = session['league_id']

    player_id = request.form.get('player_id', type=int)
    amount_str = request.form.get('amount', '').strip()
    paid_date = request.form.get('paid_date', '').strip()
    method = request.form.get('method', '').strip() or None
    notes = request.form.get('notes', '').strip() or None

    if not player_id or not amount_str or not paid_date:
        flash('Player, amount, and date are required.', 'error')
        return redirect(url_for('dues.admin_dues', season_id=season_id))

    try:
        amount = float(amount_str)
    except ValueError:
        flash('Invalid amount.', 'error')
        return redirect(url_for('dues.admin_dues', season_id=season_id))

    # Verify player belongs to this season/league
    player = db.execute(
        """SELECT p.player_id FROM players p
           JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           WHERE p.player_id = %s AND t.season_id = %s AND t.league_id = %s""",
        (player_id, season_id, league_id)
    ).fetchone()
    if not player:
        flash('Player not found in this season.', 'error')
        return redirect(url_for('dues.admin_dues', season_id=season_id))

    db.execute(
        """INSERT INTO dues_payments (league_id, season_id, player_id, amount, paid_date, method, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (league_id, season_id, player_id, amount, paid_date, method, notes)
    )
    db.commit()
    flash('Payment recorded.', 'success')
    return redirect(url_for('dues.admin_dues', season_id=season_id))


@bp.route('/admin/season/<int:season_id>/dues/delete/<int:payment_id>', methods=['POST'])
@admin_required
def admin_delete_payment(season_id, payment_id):
    db = get_db()
    league_id = session['league_id']

    db.execute(
        "DELETE FROM dues_payments WHERE payment_id=%s AND league_id=%s AND season_id=%s",
        (payment_id, league_id, season_id)
    )
    db.commit()
    flash('Payment deleted.', 'success')
    return redirect(url_for('dues.admin_dues', season_id=season_id))
