"""
Handicap calculation engine.

Design:
  - Par-based differential: gross_total - par_total  (diff_calculation_type='par')
  - Pool of rounds: last (rounds_to_average + high_scores_to_drop + low_scores_to_drop)
    real rounds + optional padding zeros, capped to that window size
  - Drop the N highest diffs and N lowest diffs from the pool
  - Average the remainder × handicap_percent / 100
  - Cap at max_handicap_index; optionally floor at 0
  - Minimum min_rounds_for_handicap real rounds required to issue a handicap

Call recalc_handicap_for_player() after every round is saved.
Call recalc_all_for_season()    from the admin "Recalculate All" button.
"""

import json
from datetime import datetime

from flask import Blueprint, redirect, url_for, session, flash
from database import get_db
from routes.auth import admin_required

bp = Blueprint('handicap', __name__, url_prefix='/handicap')


# ---------------------------------------------------------------------------
# Core calculation (no Flask context needed — pass db directly)
# ---------------------------------------------------------------------------

def _get_settings(db, season_id, league_id):
    """Return settings dict with safe defaults."""
    row = db.execute(
        "SELECT * FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()

    defaults = dict(
        min_rounds_for_handicap=2,
        rounds_to_average=4,
        high_scores_to_drop=1,
        low_scores_to_drop=0,
        padding_score_count=0,
        handicap_percent=90.0,
        max_handicap_index=18.0,
        negative_handicap_allowed=1,
        carry_scores_across_seasons=1,
        diff_calculation_type='par',
    )
    if row is None:
        return defaults
    # Merge row over defaults so any missing column still has a value
    merged = dict(defaults)
    for key in defaults:
        if row[key] is not None:
            merged[key] = row[key]
    return merged


def recalc_handicap_for_player(db, player_id, season_id, league_id):
    """
    Recalculate the handicap index for one player.

    Returns the new handicap_index (float) if successful, or None if the
    player doesn't have enough rounds yet. A new handicap_history row is
    inserted on success.
    """
    s = _get_settings(db, season_id, league_id)

    min_rounds    = int(s['min_rounds_for_handicap'])
    rounds_to_avg = int(s['rounds_to_average'])
    high_drop     = int(s['high_scores_to_drop'])
    low_drop      = int(s['low_scores_to_drop'])
    padding       = int(s['padding_score_count'])
    hcp_pct       = float(s['handicap_percent'])
    max_hcp       = float(s['max_handicap_index'])
    neg_allowed   = bool(s['negative_handicap_allowed'])
    carry_across  = bool(s['carry_scores_across_seasons'])

    # Player's personal oldest-score cutoff
    player_row = db.execute(
        "SELECT oldest_score_date FROM players WHERE player_id = %s",
        (player_id,)
    ).fetchone()
    oldest_date = player_row['oldest_score_date'] if player_row else None

    # ------------------------------------------------------------------
    # Fetch completed rounds for this player, ordered oldest → newest
    # ------------------------------------------------------------------
    query = """
        SELECT r.round_id,
               r.round_date,
               r.season_id,
               SUM(hs.gross_score) AS total_gross,
               t.par_total
          FROM scorecards sc
          JOIN rounds        r  ON sc.round_id      = r.round_id
          JOIN tees          t  ON r.tee_id          = t.tee_id
          JOIN hole_scores   hs ON hs.scorecard_id   = sc.scorecard_id
          JOIN seasons       s  ON r.season_id        = s.season_id
         WHERE sc.player_id = %s
           AND s.league_id  = %s
    """
    params = [player_id, league_id]

    if not carry_across:
        query += " AND r.season_id = %s"
        params.append(season_id)

    if oldest_date:
        query += " AND r.round_date >= %s"
        params.append(oldest_date)

    query += " GROUP BY sc.scorecard_id ORDER BY r.round_date ASC, r.round_id ASC"

    rounds = db.execute(query, params).fetchall()
    real_count = len(rounds)

    if real_count < min_rounds:
        return None   # Not enough data — leave handicap unchanged

    # ------------------------------------------------------------------
    # Build differentials (oldest → newest)
    # ------------------------------------------------------------------
    real_diffs    = []
    real_round_ids = []
    for row in rounds:
        diff = float(row['total_gross']) - float(row['par_total'])
        real_diffs.append(diff)
        real_round_ids.append(row['round_id'])

    # ------------------------------------------------------------------
    # Window: how many rounds to consider
    # ------------------------------------------------------------------
    window = rounds_to_avg + high_drop + low_drop

    # Take the most recent `window` real rounds
    recent_diffs    = real_diffs[-window:]
    recent_round_ids = real_round_ids[-window:]

    # Pad from the front with zeros (padding rounds represent scratch play)
    if padding > 0:
        slots_for_padding = max(0, window - len(recent_diffs))
        pads_to_add = min(padding, slots_for_padding)
        recent_diffs     = [0.0] * pads_to_add + recent_diffs
        # round IDs for padding are None
        recent_round_ids = [None] * pads_to_add + recent_round_ids

    # ------------------------------------------------------------------
    # Drop extremes and average
    # ------------------------------------------------------------------
    sorted_diffs = sorted(recent_diffs)

    # Drop best (lowest) first, then worst (highest)
    if low_drop > 0:
        sorted_diffs = sorted_diffs[low_drop:]
    if high_drop > 0:
        sorted_diffs = sorted_diffs[:-high_drop]

    if not sorted_diffs:
        return None

    avg_diff = sum(sorted_diffs) / len(sorted_diffs)

    # ------------------------------------------------------------------
    # Apply league modifiers
    # ------------------------------------------------------------------
    hcp_index = round(avg_diff * (hcp_pct / 100.0), 1)
    hcp_index = min(hcp_index, max_hcp)
    if not neg_allowed:
        hcp_index = max(hcp_index, 0.0)

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    today = datetime.now().strftime('%Y-%m-%d')
    db.execute(
        """INSERT INTO handicap_history
               (player_id, handicap_index, calculated_date,
                differentials_used)
           VALUES (%s, %s, %s, %s)""",
        (player_id, hcp_index, today, json.dumps(sorted_diffs))
    )

    return hcp_index


def recalc_all_for_season(db, season_id, league_id):
    """
    Recalculate handicaps for every active player in a season.
    Returns dict {player_id: new_index or None}.
    """
    players = db.execute(
        """SELECT DISTINCT p.player_id
             FROM players p
             JOIN teams t  ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
            WHERE t.season_id = %s AND p.league_id = %s AND p.active = 1""",
        (season_id, league_id)
    ).fetchall()

    results = {}
    for row in players:
        pid = row['player_id']
        results[pid] = recalc_handicap_for_player(db, pid, season_id, league_id)
    return results


# ---------------------------------------------------------------------------
# Admin route — manual "Recalculate All" trigger
# ---------------------------------------------------------------------------

@bp.route('/recalc/<int:season_id>', methods=['POST'])
@admin_required
def recalc_season(season_id):
    db = get_db()

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()

    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    results = recalc_all_for_season(db, season_id, session['league_id'])
    db.commit()

    updated = sum(1 for v in results.values() if v is not None)
    skipped = len(results) - updated
    msg = f"Handicaps recalculated: {updated} updated"
    if skipped:
        msg += f", {skipped} skipped (not enough rounds)"
    flash(msg, 'success')

    return redirect(url_for('seasons.detail', season_id=season_id))
