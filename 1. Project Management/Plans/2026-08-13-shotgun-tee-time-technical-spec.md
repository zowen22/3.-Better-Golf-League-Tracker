# Technical Spec: Shotgun-Start Tee Time Templates

*Status: `Built & shipped` — 2026-08-13. Owner: @claude. Originated from the "Shot-gun start scheduling" finding in the 2026-08-08 GLT Workflow Parity pass (`7. GLT Feature Parity.md`, "New Gaps Found" table, item #5), re-assessed same day once @user supplied GLT's actual Tee Times page content, scoped further in a follow-up round of questions, then built and validated against real Postgres same day. No current league runs shotgun format — built ahead of demand, per @user's explicit go-ahead.*

**Built as specced**, with one real bug caught by end-to-end testing: `admin.py`'s `edit_week()` called `_shotgun_enabled()` in an `if` condition without importing it first (the import was accidentally scoped inside that same `if` block's body, so it never ran before the condition needed it) — a `NameError` on every week-editor page load once Shotgun Start was turned on. Fixed by moving the import above the condition. Everything else — auto-seeding, front/back-9 hole resolution, Default/Custom detection, Reapply Defaults, additive-only Sync Slot Count, A/B shared-hole slots, and a full non-shotgun regression check — validated correctly on the first pass against a real ephemeral Postgres instance. See Session Log for the full test list.

**Deferred, not built in this pass:** the season-rollover clone list now carries the `shotgun_start_enabled` flag forward, but the actual slot template rows (hole assignments) are *not* cloned to a new season — a fresh season starts with the toggle in whatever state it was, but an empty/re-seeded template. Revisit if a real shotgun league actually rolls over between seasons and this turns out to matter.

## Goal

Let an admin turn on **Shotgun Start** for a season and set up a reusable, season-long default: one shared tee time for every group, plus a starting hole per group (a front-9 hole and a back-9 hole, since this is a 9-hole league playing front-then-back). A week's schedule then auto-populates from that default instead of being re-entered from scratch every week, a specific week can still be hand-overridden, and a summary view shows at a glance which weeks are using the default vs. a custom setup. This is GLT's `set-tee-times`/`shotgun-start` feature (`league/tee-times`), reference page supplied 2026-08-13.

**What BGLT already has, confirmed via code read (Session Log, 2026-08-13):** per-matchup `tee_time`/`starting_hole` columns (`schema_postgres.sql:348-349`), a real working admin editor (`admin.py`'s `edit_week()` POST handler, `admin/edit_week.html`) that sets both per matchup for a given week, and a client-side "Apply to All" shortcut that already covers "same tee time for every group." **What's missing** — and all this spec builds — is: an explicit on/off mode, the season-long default template itself, auto-provisioning the right number of groups, and the front/back-9 pairing per group.

## The two modes, precisely

This is the conceptual distinction @user clarified — it's not just "is a template configured," it changes what the schedule *means*:

- **Shotgun off (today's only mode, unchanged):** every group can have its own staggered tee time, all starting on the same hole (in practice hole 1) — sequential tee-off. This is exactly BGLT's current behavior; nothing about it changes.
- **Shotgun on:** every group starts at the *same* tee time, but at *different* holes around the course. One shared time, many starting positions — the opposite shape from today's mode.

A season is one or the other, not a mix — hence a real per-season toggle (see below), not an inferred one.

## Data model

```sql
-- league_settings: one new column, same convention as every other
-- boolean setting in this table (INTEGER 0/1, not a real BOOLEAN type)
ALTER TABLE league_settings ADD COLUMN shotgun_start_enabled INTEGER NOT NULL DEFAULT 0;

-- matchups: one new nullable column
ALTER TABLE matchups ADD COLUMN slot_number INTEGER;

CREATE TABLE shotgun_slot_templates (
    template_id     SERIAL PRIMARY KEY,
    season_id       INTEGER NOT NULL REFERENCES seasons(season_id),
    slot_number     INTEGER NOT NULL,   -- 1, 2, 3... -- physical position, not a specific team
    slot_label      TEXT,               -- optional, e.g. "1A"/"1B" for two groups sharing a hole
    tee_time        TEXT,               -- same free-text convention as matchups.tee_time
    front_nine_hole INTEGER,            -- 1-9
    back_nine_hole  INTEGER,            -- 10-18
    UNIQUE (season_id, slot_number, slot_label)
);
```

**"Group 1" is a physical starting position, not a fixed team pairing.** BGLT's round-robin schedule rotates which two teams play each other week to week — there's no persistent "Team A always plays in Group 1" concept, and this spec doesn't invent one. A slot is just "whichever matchup ends up assigned to position 1 this week starts at this hole." Confirmed by @user's answer on slot assignment (below) — this reading is correct.

**Number of slots is derived, not a separate setting.** GLT drives group count from a "Number of Players" setting; BGLT already knows team count for a season (that's what `generate_round_robin`, `schedule.py:43`, uses to build the schedule in the first place), and matchup count per week follows directly from it. So: **no new "number of groups" setting** — when Shotgun Start is turned on for a season, the template management page auto-seeds one `shotgun_slot_templates` row per matchup-slot the schedule actually needs (team count ÷ 2, accounting for a bye if odd), and the admin fills in hole assignments for the already-created rows rather than clicking "Add Slot" repeatedly. If team count changes later (a player added mid-season, etc.), a "Sync Slot Count" action reconciles the row count — additive only (adds missing rows), never auto-deletes a row an admin has already filled in.

**A/B same-hole sharing needs no special flag.** Two rows can simply share the same `front_nine_hole`/`back_nine_hole` value — nothing stops that, no uniqueness constraint on the hole columns themselves, only on `(season_id, slot_number, slot_label)`. `slot_label` exists purely so the UI can show "1A"/"1B" as two distinct, addressable slots that happen to share a hole. **Deliberately not the same concept as the already-removed `ab_designation_method`** (`app/migrations/drop_ab_designation_method.sql`) — that was individual player role assignment within a team pairing for handicap stroke allocation, unrelated to which physical hole a group starts on.

**No "is this the default or a custom override" flag anywhere.** Computed at display time: look up the matchup's `slot_number` in `shotgun_slot_templates`, resolve the correct hole (front or back, based on whichever nine that week uses), compare against the matchup's actual stored `tee_time`/`starting_hole`. Match → "Default." Differ → "Custom." Can't drift out of sync the way a stored flag could.

## Where this plugs into existing code

- **Turning Shotgun Start on** (in League Settings) auto-seeds `shotgun_slot_templates` rows for the current season, per the derived-count rule above. Turning it back off does **not** delete the template or touch `matchups.slot_number` — just stops the auto-population/UI from engaging, so re-enabling later picks up right where it left off.
- **`schedule.generate()`** (`schedule.py`) — when `shotgun_start_enabled` is on and template rows exist, assign `slot_number` in matchup-creation order and set `tee_time`/`starting_hole` from the matching template row + that week's nine. When Shotgun is off (the default for every league today), this is a complete no-op — zero behavior change.
- **`schedule.add_week()`** — same auto-population, for a week added after initial generation.
- **New "Reapply Defaults" bulk action**, scoped to not-yet-completed weeks only (never touches a played/locked week) — for when the template is set up or changed after a schedule already exists.
- **`admin/edit_week.html`** — when Shotgun is on for the season, the per-matchup tee-time inputs collapse toward "one shared time" (still individually editable, since GLT's own table technically allows per-group times too, but the "Apply to All" shortcut becomes the expected path rather than an optional convenience) and the starting-hole input shows the template default as placeholder text next to the editable field.

## Routes / UI

- **Settings**: one checkbox, "Shotgun Start," in the existing League Settings page (`admin/settings.html`, same pattern as every other boolean toggle there).
- **New admin page**: `GET/POST /admin/season/<id>/tee-time-template` — auto-seeded list of slot rows (slot_number, label, tee_time, front hole, back hole), "Reapply Defaults" and "Sync Slot Count" actions. Only reachable/relevant when Shotgun Start is on for the season. Linked from the Admin Panel's League Settings tab, next to where Shotgun Start itself is toggled.
- **Summary view**: a per-week Default/Custom column on the Schedule index page, visible only when Shotgun is on for the season — mirrors GLT's "Tee Time Summary For All Rounds" table.

## Resolved open questions (2026-08-13)

1. **Slot auto-assignment order** — matchup creation/schedule order. Confirmed by @user.
2. **Does a slot ever need to skip a nine entirely?** — not confirmed as a real scenario either way; the schema keeps `front_nine_hole`/`back_nine_hole` nullable regardless (no extra cost to staying flexible), but the UI will default to expecting both filled in for every slot.
3. **Explicit setting, not inferred** — @user: add a real Shotgun Start on/off toggle, not "presence of a template implies it's on." This also resolves *why* a toggle is needed beyond just gating the template UI — it changes what the per-week tee-time/hole fields actually mean (see "The two modes" above), which an inferred state couldn't cleanly represent.
4. **Build now** — green-lit 2026-08-13, ahead of any specific league asking for it.

## Effort

**M.** One migration (2 columns + 1 table, registered in `init_db.py`'s additive list) + `schema_postgres.sql` update, one new settings checkbox, one new admin CRUD page with auto-seeding logic, schedule-generation-time integration in two existing functions, edits to the existing week editor template, and a new summary view. No changes to scoring/handicap logic — purely schedule metadata, same "sits alongside, doesn't touch the engine" shape as the points-override feature.

## Testing plan

Validate against real dev Postgres per this project's standing convention: turn Shotgun Start on for a season with N teams, confirm the template auto-seeds N/2 slot rows; fill in hole assignments (including two slots sharing a hole via `slot_label`) and generate a new week's schedule, confirm `tee_time`/`starting_hole`/`slot_number` auto-populate correctly for both a front-9 week and a back-9 week; hand-edit one week's values and confirm the summary view flags it "Custom" while untouched weeks still show "Default"; change the template afterward and confirm "Reapply Defaults" only touches not-yet-completed weeks; add a team mid-season and confirm "Sync Slot Count" adds exactly the new rows needed without touching existing ones; confirm a season with Shotgun off behaves identically to today in every respect (no `slot_number` ever set, no UI changes visible, existing per-matchup tee_time/starting_hole entry unchanged).

## Next step

Build it. See Work Packages / Session Log for progress.
