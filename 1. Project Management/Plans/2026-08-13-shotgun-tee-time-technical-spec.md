# Technical Spec: Shotgun-Start Tee Time Templates

*Status: `Evaluating` — Owner: @claude. Requested by @user 2026-08-13, following up on the "Shot-gun start scheduling" finding from the 2026-08-08 GLT Workflow Parity pass (`7. GLT Feature Parity.md`, "New Gaps Found" table, item #5), re-assessed same day once @user supplied GLT's actual Tee Times page content. No current league runs shotgun format — this is a spec to have ready, not a build-now request.*

## Goal

Let an admin set up a reusable, season-long **default** tee time + starting hole per physical group ("Group 1 starts on hole 3"), so a shotgun-format week's schedule auto-populates from that default instead of being re-entered from scratch every week — while still allowing a specific week to be hand-overridden, and showing at a glance which weeks are using the default vs. a custom setup. This is GLT's `set-tee-times`/`shotgun-start` feature (`league/tee-times`), reference page supplied 2026-08-13.

**What BGLT already has, confirmed via code read (`Session Log`, 2026-08-13):** per-matchup `tee_time`/`starting_hole` columns (`schema_postgres.sql:348-349`), a real working admin editor (`admin.py`'s `edit_week()` POST handler, `admin/edit_week.html`) that sets both per matchup for a given week, and a client-side "Apply to All" shortcut (`edit_week.html:60-68`/184-190) that already covers "same tee time for every group." **What's missing** is everything about persistence across weeks and the front/back-9 pairing — this spec covers only that gap, not a rebuild of the existing per-week editor.

## Data model

One new table. No changes to `matchups.tee_time`/`starting_hole` themselves — this sits alongside them, the same relationship the points-override feature has to `match_results`.

```sql
CREATE TABLE shotgun_slot_templates (
    template_id   SERIAL PRIMARY KEY,
    season_id     INTEGER NOT NULL REFERENCES seasons(season_id),
    slot_number   INTEGER NOT NULL,        -- 1, 2, 3... — physical position, not a specific team
    slot_label    TEXT,                    -- optional, e.g. "1A"/"1B" for two groups sharing a hole
    tee_time      TEXT,                    -- same free-text convention as matchups.tee_time
    front_nine_hole INTEGER,                -- 1-9, nullable (a slot might only ever play back-9 weeks)
    back_nine_hole  INTEGER,                -- 10-18, nullable
    UNIQUE (season_id, slot_number, slot_label)
);
```

**"Group 1" is a physical starting position, not a fixed team pairing.** BGLT's round-robin schedule rotates which two teams play each other week to week — there's no persistent "Team A always plays in Group 1" concept, and this spec doesn't invent one. A slot is just "whichever matchup ends up assigned to position 1 this week starts at this hole/time." This matches how GLT's own numbering plausibly works (the sample page has no team names attached to Group 1/2/3, just hole assignments) — flagged as an assumption, not confirmed against GLT's live behavior.

**A/B same-hole sharing needs no special flag.** Two rows can simply share the same `front_nine_hole`/`back_nine_hole` value — nothing stops that today, no uniqueness constraint on the hole columns themselves, only on `(season_id, slot_number, slot_label)`. `slot_label` exists purely so the UI can show "1A" and "1B" as two distinct, addressable slots that happen to share a hole. **Deliberately not the same concept as the already-removed `ab_designation_method`** (`app/migrations/drop_ab_designation_method.sql`) — that was individual player role assignment within a team pairing for handicap stroke allocation, unrelated to which physical hole a group starts on. Don't let the shared "A/B" letters suggest these were ever the same feature.

**`matchups` gets one new column:**

```sql
ALTER TABLE matchups ADD COLUMN slot_number INTEGER;
```

Nullable, unused by leagues that don't touch this feature (the overwhelming majority today) — `NULL` means "not part of a shotgun template," identical to today's behavior. Assigned automatically when a week's schedule is generated (see below), editable by an admin afterward if the auto-assignment doesn't match how they actually want groups laid out.

**No "is this the default or a custom override" flag anywhere.** Computed at display time instead: look up the matchup's `slot_number` in `shotgun_slot_templates` for that season, resolve the correct hole (front or back, based on whichever nine that week is using — already tracked, see `schedule.py`'s `bulk_edit` "which nine" toggle), and compare against the matchup's actual stored `tee_time`/`starting_hole`. Match → "Default." Differ → "Custom." This can't drift out of sync the way a separate boolean flag could, and it's exactly the comparison GLT's own summary table implies it's doing.

## Where this plugs into existing code

- **`schedule.generate()`** (`schedule.py`) — after creating a week's matchups, if `shotgun_slot_templates` has rows for the season, assign `slot_number` in schedule order (matchup creation order, or `team1_id` ascending — pick one, doesn't need to be configurable) and set `tee_time`/`starting_hole` from the matching template row + that week's nine. If no template rows exist for the season, this whole step is a no-op — zero behavior change for every league not using the feature.
- **`schedule.add_week()`** — same auto-population, for a week added after initial generation.
- **New: "Reapply Defaults" bulk action**, scoped to not-yet-completed weeks only (never touches a played/locked week) — for when the template is set up or changed *after* a schedule already exists. Explicit admin action, not automatic, matching the points-override spec's "never silently clobber a value the admin might have hand-set" precedent.
- **`admin/edit_week.html`** gains one more piece of context per matchup row: if a template exists for that slot, show what the default *would* be next to the actual editable fields (small muted text, same pattern as a placeholder), so an admin editing a specific week can see at a glance whether they're about to diverge from the default.

## Routes / UI

- **New admin page**: `GET/POST /admin/season/<id>/tee-time-template` — simple CRUD list of slot rows (slot_number, label, tee_time, front hole, back hole), plus "Reapply Defaults" and "Add Slot" actions. Linked from the Admin Panel's Scheduling area (wherever `schedule.generate`'s entry point already lives).
- **Summary view**: a per-week Default/Custom column, either as a new small section on the Schedule index page or folded into the existing week list — mirrors GLT's "Tee Time Summary For All Rounds" table. Computed live per the comparison above, not stored.

## Open questions for @user (not decided here)

1. **Slot auto-assignment order** — recommend matchup creation order (stable, simple) with the week editor allowed to override for a specific week if needed. Confirm this is good enough, or is a more deliberate "assign teams to slots" step wanted?
2. **Does a slot ever need to skip a nine entirely** (e.g. a par-3 hole that can't host a shotgun group on the back-9 layout)? The nullable `front_nine_hole`/`back_nine_hole` columns already support "this slot has no back-9 assignment," just confirming that's a real scenario worth designing for rather than assumed.
3. **Should this feature require any per-league setting to enable/appear**, or is "presence of template rows = shotgun mode in use" sufficient (this spec's current assumption, avoids one more settings toggle to maintain)?
4. **Build now, or wait for a real shotgun league?** No current league (Root Beer, Buckeye) uses this format. Recommend: keep this spec on file, don't build until a real need shows up — same call already made for GLT's field-position Stroke Play (#30/#31, declined for the same "no signal of real demand" reason).

## Effort

**M.** One new table + migration (registered in `init_db.py`'s additive list — this project's own repeatedly-learned lesson about forgotten registrations), one new admin CRUD page, schedule-generation-time integration in two existing functions, a small addition to the existing week editor template, and a new summary view. No changes to scoring/handicap logic at all — this is purely schedule metadata, same "sits alongside, doesn't touch the engine" shape as the points-override feature.

## Testing plan

Validate against real dev Postgres per this project's standing convention: create a season's slot template (including two slots sharing a hole via `slot_label`), generate a new week's schedule and confirm `tee_time`/`starting_hole`/`slot_number` auto-populate correctly for both front-9 and back-9 weeks; hand-edit one week's values via the existing editor and confirm the summary view correctly flags it "Custom" while untouched weeks still show "Default"; change the template afterward and confirm "Reapply Defaults" only touches not-yet-completed weeks; confirm a season with zero template rows behaves identically to today (no `slot_number` ever set, no UI changes visible).

## Next step

Spec only — not built. Revisit if a real league asks for shotgun-format scheduling; until then this stays `Evaluating` as a ready-to-build reference rather than active work.
