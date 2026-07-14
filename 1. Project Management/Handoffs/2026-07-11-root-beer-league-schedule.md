# Handoff: Populate Root Beer League schedule dates (production Supabase)

*Status: `Open`*
*Created: 2026-07-11 — Planner: this session (Sonnet)*
*Priority: `High` (real league, real people, near-term dates) — Effort: `S`*
*Depends on: Supabase MCP connector must be connected AND enabled in your session (`ListConnectors` should show `Supabase` with `enabledInChat: true`; if not, tell @user before doing anything else — this cannot be done against the local dev DB, the league doesn't exist there).*

-----

## Goal

Update the **Root Beer League**'s schedule on the **production Supabase database** so every week's date is correct going forward from **July 14, 2026** onward. Source of truth for *week numbering* is whatever is already in the site's `matchups` table (do not renumber); source of truth for *dates* is the attached PDF, whose own week numbers do **not** line up with the site's — @user was explicit about this. Match by chronological order/date, not by week-number label.

## Context

@user uploaded `Root Beer League 2026 Schedule.pdf` and said (verbatim): *"I need you to populate the rest of the league schedule - I realize the week numbers don't match exactly, but the dates should - use the site's week numbers as source of truth, and this doc's dates. Only update schedule going forward, dates after 7/14. July 14th. This is for root beer league only."*

Today's date in-session was 2026-07-14, so "after 7/14" means the PDF's **Week 12 (July 17th) onward** — everything from Week 1 through Week 11 (July 10th) is in the past and out of scope, do not touch it.

This session got as far as confirming the league lives on production Supabase (not the local dev Postgres — `SELECT ... FROM leagues WHERE league_name ILIKE '%root beer%'` returns zero rows locally) before the Supabase MCP connection dropped mid-query. **No production data has been read or written yet.** You are starting the investigation from scratch.

## Full PDF content (transcribed, for reference — every week is here, not just the in-scope ones)

```
Root Beer League 2026 Schedule

Week 1 - April 24th
5:30 - Zach/Collin vs Mitchell/Austin
5:37 - Wil/Rosie vs Mike/Kaidan
5:45 - Will/Caden vs Shane/Seth
BYE - Augie/Jake

Week 2 - May 15th
5:30 - Zach/Collin vs Will/Caden
5:37 - Shane/Seth vs Mitchell/Austin
5:45 - Augie/Jake vs Mike/Kaidan
BYE - Wil/Rosie

Week 3 - End of Year
5:30 - Will/Caden vs Mitchell/Austin
5:37 - Wil/Rosie vs Shane/Seth
5:45 - Augie/Jake vs Zach/Collin
BYE - Mike/Kaidan

Week 4 - May 29th
5:30 - Mike/Kaidan vs Will/Caden
5:37 - Zach/Collin vs Shane/Seth
5:45 - Augie/Jake vs Mitchell/Austin
BYE - Wil/Rosie

Week 5 - End of Year
5:30 - Zach/Collin vs Mitchell/Austin
5:37 - Mike/Kaidan vs Will/Caden
5:45 - Wil/Rosie vs Augie/Jake
BYE - Shane/Seth

Week 6 - End of Year
5:30 - Wil/Rosie vs Mitchell/Austin
5:37 - Mike/Kaidan vs Zach/Collin
5:45 - Augie/Jake vs Shane/Seth
BYE - Will/Caden

Week 7 - June 5th
5:30 - Wil/Rosie vs Zach/Collin
5:37 - Mike/Kaidan vs Shane/Seth
5:45 - Augie/Jake vs Will/Caden
BYE - Mitchell/Austin

Week 8 - June 12th
5:30 - Mike/Kaidan vs Mitchell/Austin
5:37 - Wil/Rosie vs Shane/Seth
5:45 - Augie/Jake vs Will/Caden
BYE - Zach/Collin

Week 9 - June 19th
5:30 - Wil/Rosie vs Will/Caden
5:37 - Shane/Seth vs Mitchell/Austin
5:45 - Augie/Jake vs Zach/Collin
BYE - Mike/Kaidan

Week 10 - June 26th
5:30 - Zach/Collin vs Will/Caden
5:37 - Mike/Kaidan vs Shane/Seth
5:45 - Wil/Rosie vs Augie/Jake
BYE - Mitchell/Austin

OFF WEEK - July 3rd
Happy Fourth of July!

Week 11 - July 10th
5:30 - Mike/Kaidan vs Zach/Collin
5:37 - Wil/Rosie vs Mitchell/Austin
5:45 - Will/Caden vs Shane/Seth
BYE - Augie/Jake

=== EVERYTHING BELOW THIS LINE IS IN SCOPE (dates after 7/14) ===

Week 12 - July 17th
5:30 - Will/Caden vs Mitchell/Austin
5:37 - Wil/Rosie vs Zach/Collin
5:45 - Augie/Jake vs Mike/Kaidan
BYE - Shane/Seth

Week 13 - July 24th
5:30 - Wil/Rosie vs Mike/Kaidan
5:37 - Zach/Collin vs Shane/Seth
5:45 - Augie/Jake vs Mitchell/Austin
BYE - Will/Caden

Week 14 - July 31st
5:30 - Mike/Kaidan vs Mitchell/Austin
5:37 - Wil/Rosie vs Will/Caden
5:45 - Augie/Jake vs Shane/Seth
BYE - Zach/Collin

OFF WEEK - August 7th
Tannenhauf is Hosting a Tournament

First Round - August 14th
5:30 - 5th Place vs 4th Place
5:37 - 6th Place vs 3rd Place
5:45 - 7th Place vs 2nd Place
BYE - 1st Place

Semifinals - August 21st
5:30 - Any Two Eliminated Teams
5:37 - Winner of 3/6 vs Winner of 2/7
5:45 - Winner of 4/5 vs 1st Place
BYE - One Eliminated Team

Semifinals - August 28th
5:30 - Any Two Eliminated Teams
5:37 - Same Matchup as Last Week
5:45 - Same Matchup as Last Week
BYE - One Eliminated Team

Finals - September 4th
5:30 - Any Two Eliminated Teams
5:37 - Any Two Eliminated Teams
5:45 - Winner of 2/3/6/7 vs Winner of 1/4/5
BYE - One Eliminated Team

Finals - September 11th
5:30 - Any Two Eliminated Teams
5:37 - Any Two Eliminated Teams
5:45 - Same Matchup as Last Week
BYE - One Eliminated Team

Make-Up Date - September 18th
Push League to This Date for One Rain Out

Make-Up Date - September 25th
Push League to This Date for Two Rain Outs
(If we have three rain outs we will lose a week of play since we have 19 scheduled
weeks, to keep the 18 week requirement)

Make-Up Date - October 1st
Push League to This Date for Four Rain Outs
```

**Important nuance on the playoff weeks (First Round onward):** these don't have real team pairings yet — they're seeded by final standings ("5th Place vs 4th Place") or bracket-winner references ("Winner of 3/6 vs Winner of 2/7"), which can't be resolved to real `team1_id`/`team2_id` until the regular season finishes and playoffs actually progress. Do not invent team assignments for these. See Scope below.

## Data model (schema, not yet queried against prod — verify column names match before writing)

- `leagues.league_name` — find the league (`ILIKE '%root beer%'`).
- `seasons` — find Root Beer League's current/2026 season (`season_id`).
- `matchups` (`app/schema_postgres.sql:314`) — **this is the schedule table**, one row per matchup/BYE slot per week:
  - `week_number INTEGER NOT NULL` — **the site's own numbering. This is the source of truth for numbering — do not change it, do not try to renumber to match the PDF's "Week 12/13/14" labels.**
  - `scheduled_date TEXT` — **this is what needs updating** to the PDF's real dates for in-scope weeks.
  - `team1_id`, `team2_id`, `is_bye`, `bye_team_id` — existing matchups/pairings; leave alone unless a week has no row at all yet (see below).
  - `week_type TEXT DEFAULT 'Normal'`, `week_label TEXT`, `makeup_for_week INTEGER` — likely how "OFF WEEK" / playoff / make-up rows are represented. Inspect actual existing rows for this league to learn the convention already in use before writing anything — don't guess a convention when real examples exist to read.
- `rounds` (`app/schema_postgres.sql:341`) — this is the **played-round** record (created once scores are entered, has `round_date`, links via `matchup_id`). Do not touch this table — it should have no rows yet for future matchups.

## Task

1. **Confirm Supabase MCP access.** Project: `BetterGolfLeagueTracker`, project ref `zwycrzwunwsqeueqlrxg` (found last session via `list_projects`; re-verify it's still current). If the connector isn't `enabledInChat`, stop and tell @user — do not attempt this against the local dev DB.
2. **Read-only investigation first:**
   - Find Root Beer League's `league_id` and its current season's `season_id`.
   - `SELECT * FROM matchups WHERE season_id = <id> ORDER BY week_number;` — see the *complete* existing site schedule: every week_number currently present, its `scheduled_date`, `week_type`, `week_label`, whether teams are already assigned.
   - Identify which of those rows fall **after 2026-07-14** (by their current `scheduled_date`, or by being the tail of the `week_number` sequence if dates are null/placeholder — use judgment, but the site's `week_number` order is authoritative for sequence).
   - Identify whether rows exist for the full remainder of the season (through the make-up dates) or whether some future weeks are simply **missing** and need inserting — this is what "populate the rest" most likely refers to. Don't assume; check.
3. **Build the mapping**: take the site's future matchup rows in `week_number` order, and the PDF's in-scope entries in date order (Week 12 → Week 13 → Week 14 → First Round → Semifinals ×2 → Finals ×2 → the 3 make-up dates), and pair them up **positionally** (1st site row after 7/14 ↔ Week 12/July 17, 2nd ↔ Week 13/July 24, etc.) — **not** by matching "Week 12" to "Week 12," since @user explicitly said the numbering won't match.
   - If the counts don't match (e.g. site has fewer/more remaining weeks than the PDF lists), **stop and ask @user** rather than guessing which entries to drop or double up — this is a real schedule real people will show up for on the wrong day if it's wrong.
   - For the playoff-bracket weeks (First Round / Semifinals / Finals) and the 3 make-up dates: only set `scheduled_date` (and `week_label`/`week_type` if that's the existing convention for non-"Normal" weeks per your investigation in step 2). Do **not** populate `team1_id`/`team2_id` with guessed values for placeholder matchups like "5th Place vs 4th Place" — leave those null/as they currently are unless the site already has a documented convention for representing TBD playoff slots (check for one before deciding).
4. **Before writing anything**, present the exact planned before/after mapping (week_number → old scheduled_date → new scheduled_date, for every row you're about to touch) to @user for a quick sanity check — this is production data for a real league with real games on real evenings, not dev data with a rollback safety net. A one-line "does this look right?" is enough; don't over-block on it, but don't skip it either.
5. **Apply via `execute_sql`** (or `apply_migration` if you decide DDL is needed, which it shouldn't be — this is data-only), scoped strictly to Root Beer League's `season_id`. Update **only `scheduled_date`** (and `week_label`/`week_type` only if needed per step 3) on the identified rows; do not touch any other league or any row dated on/before 2026-07-14.
6. **Verify**: re-`SELECT` the affected rows after the update and confirm every date matches the PDF exactly, and that no row outside Root Beer League / outside the in-scope date range was touched.

## Stop Conditions

- Supabase connector not connected/enabled in your session → stop, tell @user, do not proceed against local dev DB (the league doesn't exist there).
- Site's remaining schedule row count doesn't cleanly match the PDF's in-scope entry count → stop, ask @user how to reconcile rather than guessing.
- No existing convention found for representing OFF WEEK / playoff / make-up rows in `matchups` → stop and ask rather than inventing a new convention unilaterally on production data.
- Anything suggests more than one league/season would be touched by your planned `UPDATE`/`INSERT` → stop immediately.

## Definition of Done

- [ ] Root Beer League's `matchups.scheduled_date` (and `week_label`/`week_type` if applicable) reflects the PDF's dates for every week after 2026-07-14, in the site's own `week_number` order.
- [ ] Every date verified against the PDF by re-querying after write.
- [ ] No changes to any row dated on/before 2026-07-14, and no changes to any other league.
- [ ] No playoff-week team assignments invented/guessed.
- [ ] Execution Report filled in below with the exact before/after values written.

## Critical Files / Facts

| Item | Value |
|---|---|
| Production Supabase project ref | `zwycrzwunwsqeueqlrxg` (name: `BetterGolfLeagueTracker`) — re-verify via `list_projects`, don't hardcode blindly |
| Schedule table | `matchups` (`app/schema_postgres.sql:314`) — NOT `rounds` |
| Local dev DB | Does not contain this league — do not use it for this task |
| Today's date at handoff creation | 2026-07-14 (confirm current date hasn't drifted if this handoff sits unactioned for a while — "after 7/14" is fixed to the PDF's dates, not relative) |

-----

## Execution Report

*(fill in when done)*
