"""
Week Exclusions — see Plans/2026-09-11-week-exclusions-technical-spec.md.

Lets an admin exclude a specific (season, week) from Player Stats, Handicap
calculation, and Points/standings independently. Week-level, opt-in row (no
row for a (season_id, week_number) means nothing is excluded) — mirrors
routes/archive.py's season-level `locked` flag, just scoped one level
narrower and with three independent booleans instead of one.

One route (`save`) is POSTed to from two different admin surfaces (the
Schedule page and Score Entry's Edit Week Settings panel) via the existing
`return_url` hidden-field convention (see scores.py's reopen_scores/
cancel_edit) — same write, same helper, no duplicated logic either place.
"""
from flask import Blueprint, request, redirect, url_for, session, flash
from database import get_db
from routes.auth import admin_required

bp = Blueprint('week_exclusions', __name__, url_prefix='/week-exclusions')

_KINDS = ('stats', 'handicap', 'points')

# Assumes the query's matchups table is aliased "m" -- true at every call
# site this is used from (stats.py/records.py/players.py/contests.py/
# handicap.py/standings.py all already join matchups as m). One shared
# fragment per kind so every call site pulls from the same string instead
# of hand-typing the subquery at each of the ~70 sites and drifting.
WEEK_EXCLUSION_FILTER = {
    kind: (
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM week_exclusions we WHERE we.season_id = m.season_id "
        f"AND we.week_number = m.week_number AND we.exclude_{kind} = 1)"
    )
    for kind in _KINDS
}


def get_week_exclusion(db, season_id, week_number):
    """Returns the week_exclusions row, or None if the week has never been touched."""
    return db.execute(
        "SELECT * FROM week_exclusions WHERE season_id = %s AND week_number = %s",
        (season_id, week_number)
    ).fetchone()


def is_week_excluded(db, season_id, week_number, kind):
    assert kind in _KINDS
    row = get_week_exclusion(db, season_id, week_number)
    return bool(row and row[f'exclude_{kind}'])


def excluded_kinds_label(row):
    """Badge text for a week_exclusions row, e.g. 'Excluded from Points' or
    'Excluded from Stats, Handicap' -- None if nothing's actually excluded
    (a row can exist with all three flags cleared, after an admin unchecks
    everything without deleting the row)."""
    if not row:
        return None
    labels = {'stats': 'Stats', 'handicap': 'Handicap', 'points': 'Points'}
    on = [labels[k] for k in _KINDS if row[f'exclude_{k}']]
    if not on:
        return None
    return 'Excluded from ' + ', '.join(on)


def set_week_exclusion(db, season_id, week_number, *, exclude_stats, exclude_handicap,
                        exclude_points, reason, user_id):
    """Upsert -- one row per (season_id, week_number), matching the UNIQUE constraint."""
    db.execute("""
        INSERT INTO week_exclusions
            (season_id, week_number, exclude_stats, exclude_handicap, exclude_points,
             reason, updated_by_user_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (season_id, week_number) DO UPDATE SET
            exclude_stats = EXCLUDED.exclude_stats,
            exclude_handicap = EXCLUDED.exclude_handicap,
            exclude_points = EXCLUDED.exclude_points,
            reason = EXCLUDED.reason,
            updated_by_user_id = EXCLUDED.updated_by_user_id,
            updated_at = CURRENT_TIMESTAMP
    """, (season_id, week_number, int(bool(exclude_stats)), int(bool(exclude_handicap)),
          int(bool(exclude_points)), reason, user_id))


@bp.route('/<int:season_id>/<int:week_num>', methods=['POST'])
@admin_required
def save(season_id, week_num):
    """Shared write target for both the Schedule page and Score Entry's Edit
    Week Settings panel. Checkbox inputs only appear in the form when
    checked, so absence means unchecked -- same convention every other
    checkbox in this app already follows (see e.g. league_settings' own
    hidden-before-checkbox history in Technical Reference)."""
    db = get_db()
    season = db.execute(
        "SELECT season_id, league_id FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    from routes.archive import block_if_locked
    blocked = block_if_locked(db, season_id, session['league_id'], 'schedule.index', season_id=season_id)
    if blocked:
        return blocked

    exclude_handicap = bool(request.form.get('exclude_handicap'))
    was_excluded_handicap = is_week_excluded(db, season_id, week_num, 'handicap')

    set_week_exclusion(
        db, season_id, week_num,
        exclude_stats=bool(request.form.get('exclude_stats')),
        exclude_handicap=exclude_handicap,
        exclude_points=bool(request.form.get('exclude_points')),
        reason=request.form.get('reason', '').strip() or None,
        user_id=session.get('user_id'),
    )
    db.commit()

    # Handicap history is a materialized rebuild output (unlike Stats/Points,
    # both fully live) -- a toggle has no visible effect until a rebuild
    # runs. Silent auto-trigger, matching this app's 3 existing precedents
    # for handicap-affecting admin edits (matrix_update,
    # clear_scorecard_overrides, clear_handicap_override) -- see spec's
    # "Handicap rebuild on toggle" decision.
    if exclude_handicap != was_excluded_handicap:
        from routes.handicap import rebuild_league_handicaps_and_scores
        rebuild_league_handicaps_and_scores(db, session['league_id'])
        db.commit()

    flash(f'Week {week_num} exclusions saved.', 'success')
    return_url = request.form.get('return_url', '').strip()
    if return_url:
        return redirect(return_url)
    return redirect(url_for('schedule.index', season_id=season_id))
