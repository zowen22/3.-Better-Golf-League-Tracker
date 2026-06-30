"""
Handicap calculation engine.

Design:
  - Par-based differential: gross_total - par_total  (diff_calculation_type='par')
  - Pool of rounds: last (rounds_to_average + high_scores_to_drop + low_scores_to_drop)
    real rounds + optional padding zeros, capped to that window size
  - Drop the N highest diffs and N lowest diffs from the pool
  - Average the remainder; optionally floor at 0 — this average IS the
    Handicap Index (handicap_history.handicap_index). handicap_percent and
    max_handicap_index are NOT applied here.
  - Minimum min_rounds_for_handicap real rounds required to issue a handicap

  Index → Playing Handicap is a separate, downstream conversion, done once
  by calc_playing_handicap() in scores.py: playing_handicap =
  min(round(index × handicap_percent / 100), max_handicap_index). Every
  caller that needs a number to actually play with (strokes, net scores,
  match points, the matrix's "Current" column) goes through that function.
  Do not re-apply handicap_percent or max_handicap_index when computing or
  displaying handicap_index itself — that double-discounts every player's
  handicap (e.g. 90% × 90% = 81% effective, not the configured 90%).

rebuild_league_handicaps_and_scores() is the primary entry point: it's called
after every round save and every override/matrix edit (see scores._process_scores,
matrix_update, clear_scorecard_overrides, clear_handicap_override). It walks
every completed round in the league chronologically, so corrections to old
rounds correctly ripple forward to every later round's handicap, net scores,
and match points — see "Chronological rebuild" below.

recalc_handicap_for_player() / recalc_all_for_season() are the older,
date-unaware mechanism (always recomputed from "whatever the most recent N
rounds are right now"). They're kept for the few callers that only need a
one-off recalc with no cascade (score_import, self_report, the API score
endpoints, the legacy data-migration script, and the "Recalc Handicaps"
button) — those entry points haven't been migrated to the chronological
rebuild yet.
"""

import json
from datetime import datetime

from flask import Blueprint, redirect, url_for, session, flash, render_template, request, jsonify
from database import get_db
from routes.auth import admin_required, login_required

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


def recalc_handicap_for_player(db, player_id, season_id, league_id, trigger_round_id=None):
    """
    Recalculate the handicap index for one player.

    Returns the new handicap_index (float) if successful, or None if the
    player doesn't have enough rounds yet. A new handicap_history row is
    inserted on success.

    Skips recalc if the player's current handicap is a manual override —
    manual edits take precedence over auto-calculation.
    """
    # Don't overwrite a manual override when re-saving the same round that triggered it
    if trigger_round_id is not None:
        latest = db.execute(
            """SELECT is_manual_override, trigger_round_id FROM handicap_history
                WHERE player_id = %s
                ORDER BY calculated_date DESC, handicap_id DESC
                LIMIT 1""",
            (player_id,)
        ).fetchone()
        if latest and latest['is_manual_override'] and latest['trigger_round_id'] == trigger_round_id:
            return None

    s = _get_settings(db, season_id, league_id)

    min_rounds    = int(s['min_rounds_for_handicap'])
    rounds_to_avg = int(s['rounds_to_average'])
    high_drop     = int(s['high_scores_to_drop'])
    low_drop      = int(s['low_scores_to_drop'])
    padding       = int(s['padding_score_count'])
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
           AND sc.is_absent = 0
    """
    params = [player_id, league_id]

    if not carry_across:
        query += " AND r.season_id = %s"
        params.append(season_id)

    if oldest_date:
        query += " AND r.round_date >= %s"
        params.append(oldest_date)

    query += " GROUP BY sc.scorecard_id, r.round_id, r.round_date, r.season_id, t.par_total ORDER BY r.round_date ASC, r.round_id ASC"

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
    # Handicap Index is the raw average — handicap_percent and
    # max_handicap_index are applied downstream by calc_playing_handicap()
    # when converting this index into a playing handicap, not here.
    # ------------------------------------------------------------------
    hcp_index = round(avg_diff, 1)
    if not neg_allowed:
        hcp_index = max(hcp_index, 0.0)

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    today = datetime.now().strftime('%Y-%m-%d')
    db.execute(
        """INSERT INTO handicap_history
               (player_id, handicap_index, calculated_date,
                differentials_used, trigger_round_id)
           VALUES (%s, %s, %s, %s, %s)""",
        (player_id, hcp_index, today, json.dumps(sorted_diffs), trigger_round_id)
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
# Chronological rebuild — replaces "latest handicap_history row" semantics
# with true point-in-time handicaps, derived by walking every round in date
# order instead of querying "whatever the most recent N rounds are right now".
#
# Two phases:
#   1. rebuild_player_handicap_timeline() — one player's handicap_index
#      progression, one round at a time, oldest to newest.
#   2. rebuild_league_handicaps_and_scores() — re-scores every completed
#      round in the league (net scores, A/B roles, match points) using the
#      point-in-time handicaps from phase 1, instead of "latest".
#
# This is what makes editing an old round correctly ripple forward through
# every later round, rather than flattening all later rounds to today's
# handicap (see recalc_handicap_for_player above, the older mechanism this
# replaces for cascading callers).
# ---------------------------------------------------------------------------

def rebuild_player_handicap_timeline(db, player_id, league_id):
    """
    Rebuild one player's entire handicap_history as a chronological walk
    through every completed round they've played (oldest to newest).

    For round i, the entering handicap (used to score that round) is exactly
    what was computed/anchored after round i-1 — correctly date-bounded
    because rounds are processed strictly in order, not via a "latest as of
    now" query. After round i, a new index is computed from the player's
    windowed/dropped/averaged gross differentials using round i's own season
    settings (window size, drop counts, %, carry-across), mirroring
    recalc_handicap_for_player()'s math exactly.

    Manual overrides (handicap_history.is_manual_override=1, anchored via
    trigger_round_id) are preserved as anchor points: the override value
    becomes the entering handicap for the next round instead of the
    freshly-computed average. Standalone overrides with no trigger_round_id
    are left untouched (not part of the walk).

    Deletes and reinserts every auto-computed handicap_history row for the
    player. Does not commit — caller controls the transaction.

    Returns {round_id: entering_handicap_index} — the raw index in effect
    when each round was/should be scored.
    """
    player_row = db.execute(
        "SELECT starting_handicap, oldest_score_date FROM players WHERE player_id = %s",
        (player_id,)
    ).fetchone()
    starting_hcp = float(player_row['starting_handicap'] or 0) if player_row else 0.0
    oldest_date = player_row['oldest_score_date'] if player_row else None

    rounds = db.execute(
        """SELECT r.round_id, r.round_date, r.season_id,
                  SUM(hs.gross_score) AS total_gross, t.par_total
             FROM scorecards sc
             JOIN rounds      r  ON sc.round_id = r.round_id
             JOIN matchups    m  ON r.matchup_id = m.matchup_id
             JOIN tees        t  ON r.tee_id = t.tee_id
             JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
             JOIN seasons     s  ON r.season_id = s.season_id
            WHERE sc.player_id = %s AND s.league_id = %s
              AND m.status = 'completed' AND m.is_bye = 0
              AND sc.is_absent = 0
         GROUP BY sc.scorecard_id, r.round_id, r.round_date, r.season_id, t.par_total
         ORDER BY r.round_date ASC, r.round_id ASC""",
        (player_id, league_id)
    ).fetchall()

    if not rounds:
        return {}

    # Snapshot manual overrides anchored to a specific round before wiping
    # the auto-computed rows.
    anchor_rows = db.execute(
        """SELECT handicap_id, trigger_round_id, handicap_index,
                  override_reason, override_by_user_id, override_at
             FROM handicap_history
            WHERE player_id = %s AND is_manual_override = 1
              AND trigger_round_id IS NOT NULL""",
        (player_id,)
    ).fetchall()
    anchors = {r['trigger_round_id']: r for r in anchor_rows}

    db.execute(
        """DELETE FROM handicap_history
            WHERE player_id = %s AND (is_manual_override = 0 OR is_manual_override IS NULL)""",
        (player_id,)
    )

    diffs = [float(r['total_gross']) - float(r['par_total']) for r in rounds]

    entering_by_round = {}
    entering = starting_hcp
    settings_cache = {}

    for i, rnd in enumerate(rounds):
        entering_by_round[rnd['round_id']] = entering

        season_id = rnd['season_id']
        if season_id not in settings_cache:
            settings_cache[season_id] = _get_settings(db, season_id, league_id)
        s = settings_cache[season_id]

        min_rounds    = int(s['min_rounds_for_handicap'])
        rounds_to_avg = int(s['rounds_to_average'])
        high_drop     = int(s['high_scores_to_drop'])
        low_drop      = int(s['low_scores_to_drop'])
        padding       = int(s['padding_score_count'])
        neg_allowed   = bool(s['negative_handicap_allowed'])
        carry_across  = bool(s['carry_scores_across_seasons'])

        pool = []
        for j in range(i + 1):
            if not carry_across and rounds[j]['season_id'] != season_id:
                continue
            if oldest_date and rounds[j]['round_date'] < oldest_date:
                continue
            pool.append(diffs[j])

        new_index = None
        sorted_diffs = None
        if len(pool) >= min_rounds:
            window = rounds_to_avg + high_drop + low_drop
            recent = pool[-window:]
            if padding > 0:
                slots = max(0, window - len(recent))
                pads = min(padding, slots)
                recent = [0.0] * pads + recent
            sorted_diffs = sorted(recent)
            if low_drop > 0:
                sorted_diffs = sorted_diffs[low_drop:]
            if high_drop > 0:
                sorted_diffs = sorted_diffs[:-high_drop]
            if sorted_diffs:
                avg = sum(sorted_diffs) / len(sorted_diffs)
                new_index = round(avg, 1)
                if not neg_allowed:
                    new_index = max(new_index, 0.0)

        anchor = anchors.get(rnd['round_id'])
        if anchor is not None:
            db.execute(
                """INSERT INTO handicap_history
                       (player_id, handicap_index, calculated_date,
                        differentials_used, trigger_round_id,
                        is_manual_override, override_reason,
                        override_by_user_id, override_at)
                   VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s)""",
                (player_id, anchor['handicap_index'], rnd['round_date'],
                 json.dumps(sorted_diffs) if sorted_diffs else None, rnd['round_id'],
                 anchor['override_reason'], anchor['override_by_user_id'], anchor['override_at'])
            )
            entering = float(anchor['handicap_index'])
        elif new_index is not None:
            db.execute(
                """INSERT INTO handicap_history
                       (player_id, handicap_index, calculated_date,
                        differentials_used, trigger_round_id)
                   VALUES (%s, %s, %s, %s, %s)""",
                (player_id, new_index, rnd['round_date'], json.dumps(sorted_diffs), rnd['round_id'])
            )
            entering = new_index
        # else: not enough rounds yet — entering handicap carries over unchanged,
        # no row inserted (mirrors recalc_handicap_for_player returning None).

    return entering_by_round


def rebuild_league_handicaps_and_scores(db, league_id):
    """
    The authoritative, date-correct replacement for the
    recalc_handicap_for_player() cascade-after-save mechanism.

    Phase 1: walk every player's round history chronologically and rebuild
    handicap_history with correct point-in-time values and dates.
    Phase 2: re-score every completed round in the league, oldest to newest,
    using each player's entering handicap as of that specific round — so a
    correction to an old round ripples forward correctly through every later
    round's playing handicaps, net scores, and match points, instead of
    flattening every future round to today's handicap.

    Does not commit — caller controls the transaction (so a preview can
    apply this and roll back instead of committing).

    Returns a summary dict: players_processed, rounds_processed, rounds_changed.
    """
    from routes.scores import (get_league_settings, _settings_scoring_mode,
                               _settings_absence_policy, _recalc_single_round)

    players = db.execute(
        "SELECT player_id FROM players WHERE league_id = %s", (league_id,)
    ).fetchall()

    handicap_lookup = {}  # round_id -> {player_id: raw_handicap_index}
    for row in players:
        pid = row['player_id']
        per_round = rebuild_player_handicap_timeline(db, pid, league_id)
        for rid, idx in per_round.items():
            handicap_lookup.setdefault(rid, {})[pid] = idx

    matchups = db.execute(
        """SELECT m.matchup_id, m.season_id, r.round_id
             FROM matchups m
             JOIN rounds  r ON r.matchup_id = m.matchup_id
             JOIN seasons s ON m.season_id  = s.season_id
            WHERE s.league_id = %s AND m.status = 'completed' AND m.is_bye = 0
         ORDER BY r.round_date ASC, r.round_id ASC""",
        (league_id,)
    ).fetchall()

    settings_cache = {}
    rounds_changed = 0
    for row in matchups:
        mid       = row['matchup_id']
        season_id = row['season_id']
        round_id  = row['round_id']

        if season_id not in settings_cache:
            s = get_league_settings(db, season_id, league_id)
            settings_cache[season_id] = None if not s else (
                float(s['handicap_percent']), float(s['max_handicap_index']),
                _settings_scoring_mode(s), _settings_absence_policy(s)
            )
        cached = settings_cache[season_id]
        if cached is None:
            continue
        hpct, hmax, smode, apolicy = cached

        before = {
            r['player_id']: (r['hole_points_won'], r['overall_point_won'])
            for r in db.execute(
                "SELECT player_id, hole_points_won, overall_point_won FROM match_results WHERE matchup_id = %s",
                (mid,)
            ).fetchall()
        }

        _recalc_single_round(db, mid, season_id, league_id, hpct, hmax, smode,
                             handicap_lookup=handicap_lookup.get(round_id, {}),
                             absence_policy=apolicy)

        after = {
            r['player_id']: (r['hole_points_won'], r['overall_point_won'])
            for r in db.execute(
                "SELECT player_id, hole_points_won, overall_point_won FROM match_results WHERE matchup_id = %s",
                (mid,)
            ).fetchall()
        }
        if set(before) != set(after) or any(before.get(pid) != after.get(pid) for pid in after):
            rounds_changed += 1

    return {
        'players_processed': len(players),
        'rounds_processed': len(matchups),
        'rounds_changed': rounds_changed,
    }


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


# ---------------------------------------------------------------------------
# Admin route — full league-wide chronological rebuild (preview + apply)
# ---------------------------------------------------------------------------

@bp.route('/rebuild', methods=['GET', 'POST'])
@admin_required
def rebuild_timeline():
    """
    Preview and apply the full chronological rebuild of every player's
    handicap_history plus every completed round's net scores and match
    points, across every season in the league.

    GET runs the rebuild against the live connection and rolls it back —
    a true preview, not a separate simulation path, so what you see is
    exactly what POST will commit.
    """
    db = get_db()
    league_id = session['league_id']

    summary = rebuild_league_handicaps_and_scores(db, league_id)

    if request.method == 'POST':
        db.commit()
        flash(
            f"Handicap timeline rebuilt: {summary['players_processed']} player(s), "
            f"{summary['rounds_processed']} completed round(s) checked, "
            f"{summary['rounds_changed']} round(s) had corrected handicaps or points.",
            'success'
        )
        return render_template('handicap/rebuild_timeline.html', summary=summary, done=True)

    db.rollback()
    return render_template('handicap/rebuild_timeline.html', summary=summary, done=False)


# ---------------------------------------------------------------------------
# Handicap history — player view
# ---------------------------------------------------------------------------

def _seasons_list(db, league_id):
    return db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()


def _active_players(db, league_id, season_id):
    """All players who played at least one round in the season, or are on a team."""
    return db.execute(
        """SELECT DISTINCT p.player_id, p.first_name, p.last_name,
                  p.first_name || ' ' || p.last_name AS full_name
             FROM players p
        LEFT JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
                          AND t.season_id = %s
        LEFT JOIN scorecards sc ON sc.player_id = p.player_id
        LEFT JOIN rounds r ON sc.round_id = r.round_id
        LEFT JOIN matchups m ON r.matchup_id = m.matchup_id AND m.season_id = %s
            WHERE p.league_id = %s AND p.active = 1
              AND (t.team_id IS NOT NULL OR m.matchup_id IS NOT NULL)
         ORDER BY p.last_name, p.first_name""",
        (season_id, season_id, league_id)
    ).fetchall()


@bp.route('/player')
@login_required
def player_history_redirect():
    db = get_db()
    league_id = session['league_id']
    row = db.execute(
        "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (league_id,)
    ).fetchone()
    if not row:
        flash('No seasons found.', 'error')
        return redirect(url_for('main.index'))
    return redirect(url_for('handicap.player_history', season_id=row['season_id']))


@bp.route('/player/<int:season_id>')
@login_required
def player_history(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.index'))

    player_id = request.args.get('player_id', type=int)
    limit = request.args.get('limit', 10, type=int)
    if limit not in (5, 10, 15, 20, 50, 100):
        limit = 10

    players = _active_players(db, league_id, season_id)
    if not player_id and players:
        player_id = players[0]['player_id']

    history = []
    if player_id:
        # Rounds played this season
        rounds_played = db.execute(
            """SELECT r.round_id, r.round_date,
                      sc.handicap_at_time_of_play,
                      sc.scorecard_id
                 FROM scorecards sc
                 JOIN rounds r    ON sc.round_id   = r.round_id
                 JOIN matchups m  ON r.matchup_id  = m.matchup_id
                WHERE sc.player_id = %s
                  AND m.season_id  = %s
                  AND sc.approved  = 1
             ORDER BY r.round_date ASC, r.round_id ASC""",
            (player_id, season_id)
        ).fetchall()

        # handicap_history entries — join by trigger_round_id when available,
        # fall back to matching by calculated_date for legacy rows
        hh_rows = db.execute(
            """SELECT hh.handicap_id, hh.handicap_index, hh.calculated_date,
                      hh.trigger_round_id, hh.is_manual_override,
                      hh.override_reason, hh.override_at,
                      u.first_name || ' ' || u.last_name AS override_by
                 FROM handicap_history hh
            LEFT JOIN users u ON hh.override_by_user_id = u.user_id
                WHERE hh.player_id = %s
             ORDER BY hh.calculated_date ASC, hh.handicap_id ASC""",
            (player_id,)
        ).fetchall()

        # Index hh by trigger_round_id and by date (fallback)
        hh_by_round = {r['trigger_round_id']: r for r in hh_rows if r['trigger_round_id']}
        hh_by_date  = {}
        for r in hh_rows:
            if r['trigger_round_id'] is None:
                hh_by_date.setdefault(r['calculated_date'], r)

        for i, rnd in enumerate(rounds_played):
            hh = hh_by_round.get(rnd['round_id']) or hh_by_date.get(rnd['round_date'])
            playing = rnd['handicap_at_time_of_play']
            history.append({
                'round_num':   i + 1,
                'round_id':    rnd['round_id'],
                'round_date':  rnd['round_date'],
                'playing_hcp': round(playing) if playing is not None else None,
                'hcp_index':   hh['handicap_index'] if hh else None,
                'handicap_id': hh['handicap_id'] if hh else None,
                'is_override': bool(hh and hh['is_manual_override']),
                'override_reason': hh['override_reason'] if hh else None,
                'override_at':     hh['override_at']     if hh else None,
                'override_by':     hh['override_by']     if hh else None,
            })

        # Most recent first, limited
        history = list(reversed(history))[-limit:]

    return render_template(
        'handicap/player_history.html',
        season=season,
        seasons=_seasons_list(db, league_id),
        players=players,
        selected_player_id=player_id,
        history=history,
        limit=limit,
        is_admin=session.get('is_admin', False),
    )


# ---------------------------------------------------------------------------
# Handicap history — league matrix
# ---------------------------------------------------------------------------

@bp.route('/league')
@login_required
def league_matrix_redirect():
    db = get_db()
    league_id = session['league_id']
    row = db.execute(
        "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (league_id,)
    ).fetchone()
    if not row:
        flash('No seasons found.', 'error')
        return redirect(url_for('main.index'))
    return redirect(url_for('handicap.league_matrix', season_id=row['season_id']))


@bp.route('/league/<int:season_id>')
@login_required
def league_matrix(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('main.index'))

    # All distinct round dates for this season (one column per date, not per round_id)
    _round_rows = db.execute(
        """SELECT r.round_id, r.round_date, m.week_number
             FROM rounds r
             JOIN matchups m ON r.matchup_id = m.matchup_id
            WHERE m.season_id = %s
         ORDER BY r.round_date ASC, r.round_id ASC""",
        (season_id,)
    ).fetchall()
    # Collapse to one entry per date; track all round_ids for that date
    _date_map = {}  # round_date -> {'round_date': ..., 'week_number': ..., 'round_ids': [...]}
    for row in _round_rows:
        d = row['round_date']
        if d not in _date_map:
            _date_map[d] = {'round_date': d, 'week_number': row['week_number'], 'round_ids': []}
        _date_map[d]['round_ids'].append(row['round_id'])
    rounds = list(_date_map.values())  # one entry per unique date, ordered

    # Member player_ids and team info (on a team this season)
    member_ids = set()
    player_team = {}   # player_id -> {team_num, team_name}
    for i, row in enumerate(db.execute(
        "SELECT team_id, player1_id, player2_id, team_name FROM teams WHERE season_id = %s AND league_id = %s ORDER BY team_id",
        (season_id, league_id)
    ).fetchall(), start=1):
        tinfo = {'team_num': i, 'team_name': row['team_name'] or f"Team {i}"}
        if row['player1_id']:
            member_ids.add(row['player1_id'])
            player_team[row['player1_id']] = tinfo
        if row['player2_id']:
            member_ids.add(row['player2_id'])
            player_team[row['player2_id']] = tinfo

    # League settings for playing handicap conversion
    from routes.scores import get_league_settings, calc_playing_handicap
    settings = get_league_settings(db, season_id, league_id)
    hpct = float(settings['handicap_percent']) if settings else 90.0
    hmax = float(settings['max_handicap_index']) if settings else 18.0

    def _playing_hcp(index):
        if index is None:
            return None
        return calc_playing_handicap(index, hpct, hmax)

    # All scorecards for this season: player → round → {hcp, scorecard_id, matchup_id}
    sc_rows = db.execute(
        """SELECT sc.player_id, sc.scorecard_id, r.round_id, r.round_date,
                  m.matchup_id, sc.handicap_at_time_of_play, sc.is_sub,
                  sc.hcp_manually_overridden
             FROM scorecards sc
             JOIN rounds r   ON sc.round_id  = r.round_id
             JOIN matchups m ON r.matchup_id = m.matchup_id
            WHERE m.season_id = %s AND sc.approved = 1""",
        (season_id,)
    ).fetchall()

    # Build lookup: player_id → {round_id: {hcp, scorecard_id, matchup_id}}
    plays = {}
    sub_flags = {}
    for sc in sc_rows:
        pid = sc['player_id']
        plays.setdefault(pid, {})[sc['round_id']] = {
            'hcp':          sc['handicap_at_time_of_play'],
            'scorecard_id': sc['scorecard_id'],
            'matchup_id':   sc['matchup_id'],
            'overridden':   bool(sc['hcp_manually_overridden']),
        }
        if sc['is_sub']:
            sub_flags[pid] = True

    # Current handicap per player (most recent handicap_history entry)
    current_hcps = {}
    for row in db.execute(
        """SELECT DISTINCT ON (hh.player_id) hh.player_id, hh.handicap_index
             FROM handicap_history hh
             JOIN players p ON hh.player_id = p.player_id
            WHERE p.league_id = %s AND p.active = 1
         ORDER BY hh.player_id, hh.calculated_date DESC, hh.handicap_id DESC""",
        (league_id,)
    ).fetchall():
        current_hcps[row['player_id']] = row['handicap_index']

    # All active players who played or are on a team
    all_player_ids = member_ids | set(plays.keys())
    if all_player_ids:
        placeholders = ','.join(['%s'] * len(all_player_ids))
        player_rows = db.execute(
            f"""SELECT player_id, first_name, last_name, starting_handicap
                  FROM players
                 WHERE player_id IN ({placeholders})
                   AND league_id = %s AND active = 1
              ORDER BY last_name, first_name""",
            list(all_player_ids) + [league_id]
        ).fetchall()
    else:
        player_rows = []

    matrix = []
    for p in player_rows:

        pid = p['player_id']
        player_rounds = plays.get(pid, {})
        round_cells = [
            next((player_rounds[rid] for rid in r['round_ids'] if rid in player_rounds), None)
            for r in rounds
        ]
        played_hcps = [c['hcp'] for c in round_cells if c is not None]
        avg = round(sum(played_hcps) / len(played_hcps), 1) if played_hcps else None
        raw_index = current_hcps.get(pid)
        tinfo = player_team.get(pid, {})
        has_cell_override = any(c and c.get('overridden') for c in round_cells)
        matrix.append({
            'player_id':         pid,
            'name':              f"{p['first_name']} {p['last_name']}",
            'type':              'Sub' if (pid not in member_ids and sub_flags.get(pid)) else 'Member',
            'team_num':          tinfo.get('team_num', 9999),
            'team_name':         tinfo.get('team_name', ''),
            'starting_hcp':      p['starting_handicap'],
            'current_hcp':       _playing_hcp(raw_index),
            'rounds_played':     len(played_hcps),
            'round_cells':       round_cells,
            'avg':               avg,
            'has_cell_override': has_cell_override,
        })

    matrix.sort(key=lambda r: (r['team_num'], r['name']))

    return render_template(
        'handicap/league_matrix.html',
        season=season,
        seasons=_seasons_list(db, league_id),
        rounds=rounds,
        matrix=matrix,
    )


@bp.route('/matrix/<int:season_id>/update', methods=['POST'])
@admin_required
def matrix_update(season_id):
    """Bulk-update playing handicaps from the matrix edit mode and re-score affected rounds."""
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        return jsonify({'error': 'Season not found'}), 404

    data = request.get_json(silent=True) or {}
    changes = data.get('changes', [])  # [{scorecard_id, hcp, matchup_id}, ...]

    if not changes:
        return jsonify({'ok': True, 'updated': 0})

    affected_matchup_ids = set()
    updated = 0
    for ch in changes:
        try:
            sc_id      = int(ch['scorecard_id'])
            new_hcp    = int(round(float(ch['hcp'])))
            matchup_id = int(ch['matchup_id'])
        except (KeyError, TypeError, ValueError):
            continue
        # Verify scorecard belongs to this league (admin already verified above)
        ok = db.execute(
            """SELECT sc.scorecard_id FROM scorecards sc
                 JOIN players p ON sc.player_id = p.player_id
                WHERE sc.scorecard_id = %s AND p.league_id = %s""",
            (sc_id, league_id)
        ).fetchone()
        if not ok:
            continue
        db.execute(
            "UPDATE scorecards SET handicap_at_time_of_play = %s, hcp_manually_overridden = 1 WHERE scorecard_id = %s",
            (new_hcp, sc_id)
        )
        affected_matchup_ids.add(matchup_id)
        updated += 1

    db.commit()

    # Rebuild the league timeline: re-applies the overrides just set above
    # (hcp_manually_overridden always wins, see _recalc_single_round) and
    # correctly ripples the change forward through every later round.
    recalc_errors = []
    try:
        rebuild_league_handicaps_and_scores(db, league_id)
        db.commit()
    except Exception as e:
        recalc_errors.append(str(e))

    return jsonify({'ok': True, 'updated': updated, 'recalc_errors': recalc_errors})


@bp.route('/matrix/<int:season_id>/clear-overrides/<int:player_id>', methods=['POST'])
@admin_required
def clear_scorecard_overrides(season_id, player_id):
    """Clear all hcp_manually_overridden flags for a player in a season."""
    db = get_db()
    league_id = session['league_id']
    db.execute(
        """UPDATE scorecards SET hcp_manually_overridden = 0
             FROM rounds r
             JOIN matchups m ON r.matchup_id = m.matchup_id
            WHERE scorecards.round_id = r.round_id
              AND m.season_id = %s
              AND scorecards.player_id = %s
              AND EXISTS (
                  SELECT 1 FROM players p
                  WHERE p.player_id = scorecards.player_id AND p.league_id = %s
              )""",
        (season_id, player_id, league_id)
    )
    db.commit()

    # Rebuild the league timeline now that overrides are cleared; each round
    # will recalculate its playing handicap from the point-in-time index.
    try:
        rebuild_league_handicaps_and_scores(db, league_id)
        db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('clear-overrides cascade failed for player %s', player_id)

    flash('Playing handicap overrides cleared.', 'success')
    return redirect(url_for('handicap.league_matrix', season_id=season_id))


# ---------------------------------------------------------------------------
# Admin — manual override
# ---------------------------------------------------------------------------

@bp.route('/history/<int:handicap_id>/override', methods=['POST'])
@admin_required
def override_handicap(handicap_id):
    db = get_db()
    league_id = session['league_id']

    hh = db.execute(
        """SELECT hh.*, p.league_id
             FROM handicap_history hh
             JOIN players p ON hh.player_id = p.player_id
            WHERE hh.handicap_id = %s""",
        (handicap_id,)
    ).fetchone()
    if not hh or hh['league_id'] != league_id:
        flash('Record not found.', 'error')
        return redirect(request.referrer or url_for('handicap.player_history_redirect'))

    new_index = request.form.get('new_index', type=float)
    reason    = request.form.get('reason', '').strip()
    player_id = request.form.get('player_id', type=int)
    season_id = request.form.get('season_id', type=int)

    if new_index is None:
        flash('Invalid handicap index.', 'error')
        return redirect(request.referrer or url_for('handicap.player_history_redirect'))

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    db.execute(
        """UPDATE handicap_history
              SET handicap_index      = %s,
                  is_manual_override  = 1,
                  override_reason     = %s,
                  override_by_user_id = %s,
                  override_at         = %s
            WHERE handicap_id = %s""",
        (new_index, reason or None, session['user_id'], now, handicap_id)
    )
    db.commit()
    flash(f'Handicap index updated to {new_index}.', 'success')
    return redirect(url_for('handicap.player_history', season_id=season_id,
                            player_id=player_id))


@bp.route('/history/<int:handicap_id>/clear', methods=['POST'])
@admin_required
def clear_handicap_override(handicap_id):
    db = get_db()
    league_id = session['league_id']

    hh = db.execute(
        """SELECT hh.*, p.league_id, p.player_id AS pid
             FROM handicap_history hh
             JOIN players p ON hh.player_id = p.player_id
            WHERE hh.handicap_id = %s""",
        (handicap_id,)
    ).fetchone()
    if not hh or hh['league_id'] != league_id:
        flash('Record not found.', 'error')
        return redirect(request.referrer or url_for('handicap.player_history_redirect'))

    player_id = hh['pid']
    season_id = request.form.get('season_id', type=int)

    # Drop this anchor entirely — the rebuild below regenerates an auto row
    # for this round (and re-derives everything downstream of it) from scratch.
    db.execute("DELETE FROM handicap_history WHERE handicap_id = %s", (handicap_id,))
    db.commit()

    try:
        rebuild_league_handicaps_and_scores(db, league_id)
        db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('clear-override rebuild failed for player %s', player_id)

    flash('Manual override cleared and handicap recalculated.', 'success')
    return redirect(url_for('handicap.player_history', season_id=season_id,
                            player_id=player_id))
