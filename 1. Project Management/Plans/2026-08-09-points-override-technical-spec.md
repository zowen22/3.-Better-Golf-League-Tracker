# Technical Spec: Manual Points Override

*Status: `Built & shipped` — 2026-08-09, per @user's go-ahead on this spec's own recommendations. Owner: @claude. Requested by @user 2026-08-09, following up on the "No points-override capability" finding from the 2026-08-08 GLT Workflow Parity pass (`7. GLT Feature Parity.md`, "New Gaps Found" table, item #2; also `3. Work Packages.md` WP3.1).*

**Built as specced, with one correction found during implementation**: grepping every `match_results` write path more carefully (by `INSERT`, not just `DELETE`) turned up **9 real call sites across 8 functions in 6 files** — 3 more than this spec's original count of 6/7 (`api.py`'s two iOS-API score paths, `self_report.py`'s web approval flow, and `score_import.py`'s CSV/Excel import were all missed by the original DELETE-only grep). All 9 are now wired to `apply_point_overrides()` (one, `cancel_edit`'s session-backup restore, deliberately isn't — see Technical Reference for why). This is itself a small confirmation of the spec's own thesis: even a careful review missed real write sites on the first pass, which is exactly why a single shared choke-point function beats hand-preserving state at every call site.

## Goal

Let an admin manually adjust a player's awarded points for a specific matchup, for special-rule situations the scoring engine doesn't (and shouldn't) model in code — e.g. a league-specific bonus, a penalty, or a one-off ruling. GLT has this (`recording-points` how-to article — "Save and Override Points" opens an editable points screen). @user asked for a design that is **cleaner than GLT's and prioritizes traceability**. Two concrete GLT flaws to deliberately not repeat (both confirmed by reading their actual how-to article, not assumed):

1. **GLT silently wipes the override.** Re-recording points for a scorecard recalculates from current settings and erases any manual edit, with no warning in the flow itself.
2. **GLT doesn't show it anywhere.** Their own Detailed Points Scoresheet report doesn't display which points were overridden — no visual trace at the point of use, only (maybe) in whatever screen you happened to set it from.

## Why this needs its own table, not just new columns on `match_results`

`match_results` is not an update-in-place table — it's deleted and fully re-inserted on every recompute. Grepped every write path; there are **6 distinct functions, 7 call sites** that do `DELETE FROM match_results WHERE matchup_id = ...` then re-`INSERT`:

| # | Function | File:line | When it runs |
|---|---|---|---|
| 1 | `_process_scores()` | `scores.py:1395` (fires at both `:1556` and `:1714`, two scoring-mode branches) | Normal score entry save — the everyday path |
| 2 | `reopen_scores()` | `scores.py:1922` | Admin reopens a completed matchup for editing |
| 3 | `clear_scores()` | `scores.py:2114` | Admin clears a matchup's scores entirely |
| 4 | `_recalc_single_round()` | `scores.py:1163` | Admin's "Recalc Points" action |
| 5 | `compute_classical_stroke_play_points()` | `scores.py:304` (bulk, `IN (...)`) | Classical Stroke Play's weekly bulk points pass |
| 6 | `_save_edited_scores()` | `admin.py:757` | Admin directly editing an already-completed matchup's scores |

If an override lived as columns on `match_results` itself, every one of these 7 call sites would need its own bespoke "preserve the override across the delete" logic — exactly the failure-prone shape GLT's own bug has, and exactly the kind of "one call site got missed" bug class this project has hit before for unrelated reasons (e.g. WP3.17's unregistered migration, or the `oldest_score_date` field with no UI). Missing even one call site silently reintroduces GLT's flaw.

**Instead:** overrides live in their own append-only table, independent of `match_results`' churn, and get *reapplied* through one shared function called at the end of each of the 6 functions above. One choke point instead of seven bespoke ones.

## Data model

```sql
CREATE TABLE point_overrides (
    override_id SERIAL PRIMARY KEY,
    matchup_id INTEGER NOT NULL REFERENCES matchups(matchup_id),
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    team_id INTEGER,                    -- snapshot at override time, display convenience only
    field TEXT NOT NULL,                -- 'total_points' or 'overall_point_won' — see Scope below
    original_value REAL NOT NULL,       -- the computed value at the moment of override, snapshotted
    override_value REAL NOT NULL,
    reason TEXT NOT NULL,               -- required — GLT's own flow has no reason field at all
    created_by_user_id INTEGER NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    active INTEGER NOT NULL DEFAULT 1,  -- cleared overrides are marked inactive, never deleted
    cleared_by_user_id INTEGER REFERENCES users(user_id),
    cleared_at TIMESTAMPTZ,
    cleared_reason TEXT
);

CREATE UNIQUE INDEX point_overrides_active_uniq
    ON point_overrides(matchup_id, player_id, field)
    WHERE active = 1;
```

This mirrors the existing `handicap_history` pattern (`is_manual_override`/`override_reason`/`override_by_user_id`/`override_at`/`pre_override_index`) already established in this codebase for exactly this kind of "value was computed, then a human overrode it" situation — same shape, same traceability guarantees, applied to a different table because `match_results`' delete-and-reinsert lifecycle doesn't fit `handicap_history`'s append-a-new-snapshot-per-calculation model.

**Every override is a new row, never an in-place edit** — re-overriding a value doesn't lose the prior one, it marks it `active=0` and inserts a fresh row. Full history survives forever: what it was, what it became, who did it, when, and why, for every override that's ever existed on a matchup — not just the current one.

## Central helper — the one choke point

```python
# scores.py or a small new module, e.g. point_overrides.py
_OVERRIDABLE_FIELDS = {'total_points', 'overall_point_won'}  # allowlist — see Security note

def apply_point_overrides(db, matchup_id):
    """Re-applies any active point overrides onto match_results for this
    matchup. Call this immediately after any DELETE+INSERT of match_results
    rows for a matchup, so overrides survive every recompute instead of
    silently vanishing — the exact GLT flaw this feature exists to avoid."""
    overrides = db.execute(
        "SELECT * FROM point_overrides WHERE matchup_id = %s AND active = 1",
        (matchup_id,)
    ).fetchall()
    for o in overrides:
        field = o['field']
        if field not in _OVERRIDABLE_FIELDS:
            continue  # defense in depth, should be unreachable given the write path below
        db.execute(
            f"UPDATE match_results SET {field} = %s WHERE matchup_id = %s AND player_id = %s",
            (o['override_value'], matchup_id, o['player_id'])
        )
```

**Security note:** `field` gets interpolated into the SQL string because column names can't be parameterized — it's checked against `_OVERRIDABLE_FIELDS` first (data originates from our own DB, not user input directly, but the allowlist check is cheap defense in depth and should stay even though the write path below never lets an arbitrary string reach this table in the first place).

**Wiring:** add one call — `apply_point_overrides(db, matchup_id)` — right before `db.commit()` at the end of each of the 6 functions listed above. For the bulk classical-stroke-play path, call it once per `matchup_id` inside its existing loop, after that matchup's own INSERTs land.

## Scope: which fields are overridable

`total_points` is what every standings/leaderboard query actually sums (`SUM(mr.total_points)` — confirmed the primary driver everywhere in `standings.py`), and is the direct equivalent of what GLT's own override screen edits. `overall_point_won` separately drives W-L-T record classification (`standings.py`'s win/loss/tie `CASE` logic). These are kept as two independently-overridable fields (both rows in the same table, different `field` value) rather than coupled, so an admin can adjust the points total without necessarily forcing a W-L-T reclassification, or vice versa — **this is a judgment call, flagging for @user rather than assuming**: an alternative is to always require both together so they can't drift into an inconsistent state (e.g. `total_points` says a big win but `overall_point_won` still says a loss). Recommend starting with `total_points` only in the UI (the actual GLT-equivalent use case) and treating `overall_point_won` as an advanced/secondary option, not defaulting to exposing both — cuts surface area for the common case.

`hole_points_won` is deliberately **not** overridable — GLT's own feature operates at the round/scorecard total level, not hole-by-hole, and there's no stated use case for it.

## Routes

New, admin-only, season-lock-gated (via the existing `block_if_locked()` helper from `routes.archive` — already the standard gate on every other route that can rewrite historical points/handicaps; must be added here too, easy to forget):

- **`GET/POST /admin/matchup/<matchup_id>/override-points`** — GET renders every `match_results` row for the matchup (player, team, current `total_points`, an "advanced" collapsible field for `overall_point_won`) plus a required reason textarea. POST: for each field that actually changed, mark any existing active override for that `(matchup_id, player_id, field)` as superseded (`active=0`), insert the new override row, call `apply_point_overrides()`, commit.
- **`POST /admin/matchup/<matchup_id>/clear-point-override/<player_id>/<field>`** — marks the specific active override row inactive (`cleared_by_user_id`, `cleared_at`, `cleared_reason` — reason required here too), then re-runs the matchup's normal points computation (reuse `_recalc_single_round()`) so the value reverts to whatever the engine actually computes today. Explicit, traceable, and — unlike GLT — something the admin does on purpose rather than something that happens to them by accident the next time points get re-recorded.

## UI

- **Extend the existing Scoring Debug page** (`debug_scores.py` → `debug/scoring.html`) rather than building a new page — it already shows `p1_stored_total`/`p2_stored_total` per matchup per player (the exact values this feature edits), so it's the natural home for an "Override" action next to each.
- **Visual marker wherever an overridden value is displayed**, not just on the debug page — mirror the existing `hcp_marker`/`data-prov-type` badge convention already used for handicap-override provenance on the score-entry pages (`enter.html`, `enter_week.html`). This is the direct fix for GLT's "Detailed Points Scoresheet doesn't show overridden points" flaw — an override should never be invisible at the point where the number is actually shown to a player.
- **Override history stays visible, not just the current state** — fold a simple chronological list (all `point_overrides` rows for the matchup, active and cleared, with who/when/why) into the same Scoring Debug page rather than building a separate audit page for MVP. Revisit as its own page only if it turns out to get used heavily.

## Interaction with season locking

Must be added to the same locked-route enforcement already wired into every other points/handicap-rewriting route (2026-07-27 work — see Session Log) — both new routes need the `block_if_locked()` check. Flagging explicitly since it's easy to ship a new mutating route and forget this, exactly the kind of thing this project has already caught itself missing once before.

## Open questions for @user (not decided here)

1. **`total_points`-only in the UI, or expose `overall_point_won` too from the start?** Recommend `total_points`-only for v1 (matches GLT's actual scope), `overall_point_won` as a fast-follow if a real need shows up.
2. **Should overriding `total_points` alone ever auto-adjust `overall_point_won`** (e.g. to keep W-L-T consistent with a big point swing), or is it correct to let them diverge and trust the admin to override both when that matters? Leaning toward "let them diverge, trust the admin, but the UI should note this coupling exists" rather than building implicit logic that guesses at the admin's intent.
3. **Any per-league setting to gate this feature on/off**, matching this codebase's general settings-driven convention? Leaning no — this is a narrow, occasional admin escape hatch, not something that needs a league-level toggle — but flagging since it's a real pattern elsewhere in the app.

## Effort

**S–M.** One new table + one migration (registered in `init_db.py`'s additive list, per this project's own repeatedly-learned lesson about forgotten migration registrations), one small shared helper wired into 6 existing functions (mechanical, low-risk — each site gets one added line), two new routes, and additions to one existing template rather than a new page. No changes to the scoring engine itself — this sits entirely alongside it.

## Testing plan

Validate against real dev Postgres (per this project's standing convention): create an override, confirm it lands in `match_results` immediately; re-trigger each of the 6 recompute paths in turn and confirm the override survives every one of them (this is the actual point of the design — needs to be checked per-path, not assumed from the shared-helper wiring alone); clear an override and confirm it correctly reverts to the freshly-computed value; confirm a locked season blocks both new routes; confirm the visual marker appears wherever `total_points` is rendered for an overridden row.

## Next step

Built. Open questions resolved per @user's "go ahead with your recommendations": `total_points`-only in the UI for v1 (schema/helper support `overall_point_won` too, just not exposed yet), no auto-sync between the two fields, no per-league settings gate. See Technical Reference's new "Manual Points Override" section for the shipped shape, including the corrected 9-call-site list.
