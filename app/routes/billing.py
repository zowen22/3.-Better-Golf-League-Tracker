"""Stripe billing -- one recurring annual subscription per league.

Web-only by design: the iOS app never sells anything and has no purchase
UI, so it never needs StoreKit (Apple App Store Review Guideline 3.1.3(b)
explicitly allows a companion app to access a subscription bought on the
web, as long as the app itself has no purchase button/external checkout
link -- verified against Apple's current guideline text 2026-07-15).

Free usage model: no Stripe-side trial (`trial_period_days`) -- a new
league gets FREE_ROUNDS rounds of full access before enforcement kicks
in (see `get_lockout_status()` and app.py's `_enforce_lockout` before_
request hook). This is a usage-based trial, not a calendar one, so it
lives entirely on our side rather than Stripe's Checkout trial UI.
"""
import config
from flask import Blueprint, render_template, redirect, url_for, session, flash, request, current_app
from database import get_db
from routes.auth import admin_required

bp = Blueprint('billing', __name__, url_prefix='/billing')

FREE_ROUNDS = 6


def _stripe():
    """Lazily import + configure the stripe client. Raises if not configured
    rather than silently no-op'ing -- a misconfigured billing route should
    fail loudly, not pretend to succeed."""
    if not config.STRIPE_SECRET_KEY:
        raise RuntimeError('STRIPE_SECRET_KEY not configured on this server.')
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    return stripe


def has_active_subscription(db, league_id):
    """True if this league is entitled: a real Stripe subscription that's
    `active`/`trialing`, or a manually-`comped` free league (no Stripe
    customer behind it at all -- see the comped-row convention below)."""
    row = db.execute(
        "SELECT status FROM subscriptions WHERE league_id = %s",
        (league_id,)
    ).fetchone()
    return bool(row and row['status'] in ('active', 'trialing', 'comped'))


def _league_round_count(db, league_id):
    """Total rounds ever recorded for this league, across all seasons --
    this is a one-time lifetime allowance, not something that resets each
    season. `rounds.season_id` links directly to `seasons.league_id`, no
    need to go through `matchups`."""
    row = db.execute(
        "SELECT COUNT(*) AS n FROM rounds r JOIN seasons s ON r.season_id = s.season_id "
        "WHERE s.league_id = %s",
        (league_id,)
    ).fetchone()
    return row['n'] if row else 0


def get_lockout_status(db, league_id):
    """Whether this league is currently locked out of everything except
    score entry. A subscribed/comped league is never locked, regardless of
    round count -- round counting only matters for the free-usage window."""
    if has_active_subscription(db, league_id):
        return {'locked': False, 'round_count': None, 'rounds_remaining': None}
    count = _league_round_count(db, league_id)
    return {
        'locked': count >= FREE_ROUNDS,
        'round_count': count,
        'rounds_remaining': max(0, FREE_ROUNDS - count),
    }


def _log_subscription_event(db, league_id, event_type):
    db.execute(
        "INSERT INTO subscription_events (league_id, event_type) VALUES (%s, %s)",
        (league_id, event_type)
    )
    db.commit()


def record_lockout_started(db, league_id):
    """Idempotent -- a league should only ever cross into lockout once in
    its lifetime (barring a cancellation putting it back into the free
    window, which the `has_active_subscription` short-circuit above
    already prevents from happening more than once per subscribe/cancel
    cycle anyway). Guarded so the before_request hook can call this on
    every blocked request without spamming the event log."""
    row = db.execute(
        "SELECT 1 FROM subscription_events WHERE league_id = %s AND event_type = 'lockout_started'",
        (league_id,)
    ).fetchone()
    if not row:
        _log_subscription_event(db, league_id, 'lockout_started')


STATUS_LABELS = {
    'trialing':  'Free trial',
    'active':    'Active',
    'comped':    'Complimentary (free)',
    'past_due':  'Payment failed',
    'canceled':  'Canceled',
    'incomplete': 'Incomplete',
}


def _format_epoch(ts_str):
    """Stripe timestamps are mirrored into `subscriptions` as raw Unix-epoch
    seconds (via str(int)) -- this is the one place that turns that back
    into something a person can read, rather than storing a second,
    display-only date format alongside the source-of-truth one."""
    if not ts_str:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(ts_str), tz=timezone.utc).strftime('%b %-d, %Y')
    except (ValueError, OSError):
        return ts_str


@bp.route('/')
@admin_required
def index():
    db = get_db()
    league_id = session['league_id']
    sub = db.execute(
        "SELECT * FROM subscriptions WHERE league_id = %s",
        (league_id,)
    ).fetchone()
    subscription = dict(sub) if sub else None
    if subscription:
        subscription['status_label'] = STATUS_LABELS.get(subscription['status'], subscription['status'])
        subscription['trial_end_display'] = _format_epoch(subscription['trial_end'])
        subscription['current_period_end_display'] = _format_epoch(subscription['current_period_end'])
        if subscription['cancel_at_period_end']:
            subscription['period_end_label'] = 'Cancels on'
        elif subscription['status'] == 'past_due':
            subscription['period_end_label'] = 'Current period ends'
        else:
            subscription['period_end_label'] = 'Renews on'
    lockout = get_lockout_status(db, league_id)
    return render_template('billing/index.html',
        subscription=subscription,
        lockout=lockout,
        free_rounds=FREE_ROUNDS,
        stripe_configured=bool(config.STRIPE_SECRET_KEY and config.STRIPE_PRICE_ID_ANNUAL),
    )


@bp.route('/checkout', methods=['POST'])
@admin_required
def checkout():
    if not config.STRIPE_PRICE_ID_ANNUAL:
        flash('Billing is not configured on this server yet.', 'error')
        return redirect(url_for('billing.index'))

    stripe = _stripe()
    db = get_db()
    league_id = session['league_id']

    existing = db.execute(
        "SELECT stripe_customer_id FROM subscriptions WHERE league_id = %s",
        (league_id,)
    ).fetchone()

    checkout_session = stripe.checkout.Session.create(
        mode='subscription',
        line_items=[{'price': config.STRIPE_PRICE_ID_ANNUAL, 'quantity': 1}],
        client_reference_id=str(league_id),
        customer=existing['stripe_customer_id'] if existing else None,
        success_url=url_for('billing.success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('billing.index', _external=True),
    )
    return redirect(checkout_session.url, code=303)


@bp.route('/success')
@admin_required
def success():
    return render_template('billing/success.html')


@bp.route('/portal', methods=['POST'])
@admin_required
def portal():
    db = get_db()
    row = db.execute(
        "SELECT stripe_customer_id, status FROM subscriptions WHERE league_id = %s",
        (session['league_id'],)
    ).fetchone()
    if not row:
        flash('No billing account on file yet.', 'error')
        return redirect(url_for('billing.index'))
    if row['status'] == 'comped':
        flash('This league has complimentary access — there is no billing account to manage.', 'info')
        return redirect(url_for('billing.index'))

    stripe = _stripe()
    portal_session = stripe.billing_portal.Session.create(
        customer=row['stripe_customer_id'],
        return_url=url_for('billing.index', _external=True),
    )
    return redirect(portal_session.url, code=303)


def _upsert_subscription(db, league_id, customer_id, sub_obj):
    """Mirror a Stripe subscription object into our `subscriptions` row.
    `sub_obj` is a stripe.Subscription (dict-like) -- reads its fields
    directly rather than re-deriving anything, per this table's own
    docstring ("mirrors Stripe, doesn't compute anything independently").

    Also logs a `converted` event to `subscription_events` the moment this
    league's status newly becomes active/trialing (whether that's a first
    subscribe, a resubscribe after canceling, or a locked league finally
    paying) -- read alongside the `lockout_started` events already logged
    by `record_lockout_started()`, this is what a trial-conversion-rate
    metric is computed from."""
    prior = db.execute(
        "SELECT status FROM subscriptions WHERE league_id = %s", (league_id,)
    ).fetchone()
    prior_status = prior['status'] if prior else None
    new_status = sub_obj.get('status')

    trial_end = sub_obj.get('trial_end')
    period_end = sub_obj.get('current_period_end')
    db.execute(
        """INSERT INTO subscriptions
               (league_id, stripe_customer_id, stripe_subscription_id, status,
                price_id, trial_end, current_period_end, cancel_at_period_end, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
           ON CONFLICT (league_id) DO UPDATE SET
               stripe_customer_id = EXCLUDED.stripe_customer_id,
               stripe_subscription_id = EXCLUDED.stripe_subscription_id,
               status = EXCLUDED.status,
               price_id = EXCLUDED.price_id,
               trial_end = EXCLUDED.trial_end,
               current_period_end = EXCLUDED.current_period_end,
               cancel_at_period_end = EXCLUDED.cancel_at_period_end,
               updated_at = CURRENT_TIMESTAMP""",
        (league_id, customer_id, sub_obj.get('id'), sub_obj.get('status'),
         sub_obj['items']['data'][0]['price']['id'] if sub_obj.get('items', {}).get('data') else None,
         str(trial_end) if trial_end else None,
         str(period_end) if period_end else None,
         1 if sub_obj.get('cancel_at_period_end') else 0)
    )
    db.commit()

    entitled_statuses = ('active', 'trialing')
    if new_status in entitled_statuses and prior_status not in entitled_statuses:
        _log_subscription_event(db, league_id, 'converted')


@bp.route('/webhook', methods=['POST'])
def webhook():
    stripe = _stripe()
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', '')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, config.STRIPE_WEBHOOK_SECRET)
    except (ValueError, Exception) as e:
        current_app.logger.warning(f'Stripe webhook signature/parse failure: {e}')
        return '', 400

    db = get_db()
    obj = event['data']['object']

    if event['type'] == 'checkout.session.completed':
        league_id = obj.get('client_reference_id')
        sub_id = obj.get('subscription')
        customer_id = obj.get('customer')
        if league_id and sub_id and customer_id:
            sub_obj = stripe.Subscription.retrieve(sub_id)
            _upsert_subscription(db, int(league_id), customer_id, sub_obj)

    elif event['type'] in ('customer.subscription.updated', 'customer.subscription.created'):
        row = db.execute(
            "SELECT league_id FROM subscriptions WHERE stripe_customer_id = %s",
            (obj.get('customer'),)
        ).fetchone()
        if row:
            _upsert_subscription(db, row['league_id'], obj.get('customer'), obj)

    elif event['type'] == 'customer.subscription.deleted':
        row = db.execute(
            "SELECT league_id FROM subscriptions WHERE stripe_subscription_id = %s",
            (obj.get('id'),)
        ).fetchone()
        db.execute(
            "UPDATE subscriptions SET status = 'canceled', updated_at = CURRENT_TIMESTAMP "
            "WHERE stripe_subscription_id = %s",
            (obj.get('id'),)
        )
        db.commit()
        if row:
            _log_subscription_event(db, row['league_id'], 'canceled')

    elif event['type'] == 'invoice.payment_failed':
        sub_id = obj.get('subscription')
        if sub_id:
            db.execute(
                "UPDATE subscriptions SET status = 'past_due', updated_at = CURRENT_TIMESTAMP "
                "WHERE stripe_subscription_id = %s",
                (sub_id,)
            )
            db.commit()

    return '', 200
