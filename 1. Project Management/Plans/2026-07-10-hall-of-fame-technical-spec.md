# Technical Spec: Hall of Fame (Fixed-Slot Admin-Curated Awards)

*Status: `Ready to build` — @user 2026-07-10: simplified fixed-slot version (Approach B from the decision doc).*
*Decision doc this spec implements: `Plans/2026-07-09-hall-of-fame.md`*

-----

## Goal

A small admin-curated, cross-season awards log — distinct from `standings.py`'s existing `/awards` page, which auto-computes current-season-only leaderboards (Points Leader, Eagle Eye, Best Match Record, Low Round, Hot Streak, **Most Improved Handicap**, etc.). Hall of Fame is the opposite shape: an admin manually types in who won what, persisted across every season the league has run, not recomputed from scorecard data.

Per @user's decision, this is the fixed-slot version (Approach B), not fully custom award types — smaller schema, smaller admin UI, no per-league award-type management screen.

## Important naming conflict to avoid

`standings.py`'s `/awards` page already has a real, precisely-computed **"Most Improved"** award (biggest handicap index drop that season — `standings.py:1454`, `standings.py:1490`). A Hall of Fame fixed slot should **not** reuse this name — it would look like a duplicate/competing feature when it's actually a completely different thing (auto-computed-per-season vs. hand-typed-across-seasons). Recommend fixed slots that have no BGLT auto-computed equivalent at all: **Rookie of the Year**, **Sportsmanship Award**, **Commissioner's Choice**, plus one **free-text "Other"** slot for anything else — 4 fixed slots total. This list is a starting proposal, not a hard requirement; easy to add/rename slots later since they're just enum values, not a schema migration each time (see below).

## Schema

```sql
CREATE TABLE IF NOT EXISTS hall_of_fame_winners (
    winner_id    SERIAL PRIMARY KEY,
    league_id    INTEGER NOT NULL REFERENCES leagues(league_id),
    season_id    INTEGER NOT NULL REFERENCES seasons(season_id),
    award_slot   TEXT NOT NULL,   -- 'rookie_of_year' | 'sportsmanship' | 'commissioners_choice' | 'other'
    award_label  TEXT,            -- only used when award_slot = 'other' (free-text award name)
    player_id    INTEGER REFERENCES players(player_id),   -- nullable: team award or non-player honoree
    team_id      INTEGER REFERENCES teams(team_id),
    winner_name  TEXT,            -- free-text fallback if not tied to an existing player/team record
    notes        TEXT,
    created_date TEXT DEFAULT CURRENT_DATE
);
```

`award_slot` as a plain TEXT enum (validated in the route, no DB CHECK constraint) rather than a separate `award_types` table — matches the "fixed slots, not fully custom types" decision. `player_id`/`team_id`/`winner_name` are all nullable and not mutually exclusive at the DB level (route-level validation: pick exactly one) since GLT's own winners aren't always tied to a roster record (a "Commissioner's Choice" might go to a non-playing member, a rules-committee volunteer, etc.).

One admin-facing constant list drives the dropdown and stays in one place:

```python
HALL_OF_FAME_SLOTS = [
    ('rookie_of_year',        'Rookie of the Year'),
    ('sportsmanship',         'Sportsmanship Award'),
    ('commissioners_choice',  "Commissioner's Choice"),
    ('other',                 'Other (custom)'),
]
```

## Routes

- `GET /admin/season/<season_id>/hall-of-fame` — admin list + add form (mirrors `contests.py`'s `admin_list`/`admin_add` pattern: one form to add a winner for the current season, table of all winners across every season below it).
- `POST /admin/season/<season_id>/hall-of-fame/add` — insert one row.
- `POST /admin/hall-of-fame/<winner_id>/delete` — remove a winner (mistakes happen; no edit-in-place needed at this size, delete + re-add is fine).
- `GET /hall-of-fame` — member-facing read-only view: every winner, every season, grouped by season (most recent first) or by award slot — grouping choice left to whichever renders cleaner once there's real data; not a decision worth blocking the build on.

## Effort: S. One new table, one new blueprint (or a small addition to `contests.py`/`standings.py` if a whole new file feels like overkill for 4 routes — lean toward a new small `hall_of_fame.py` blueprint since the concept is genuinely distinct from both), two templates (admin + member view).

## Testing plan

Standard for this project: validate against real dev Postgres — add a winner for an existing season, confirm it persists and displays correctly cross-season, confirm delete removes only the intended row, confirm the "Other" slot's free-text label actually renders instead of a blank/placeholder.

## Next step

Ready to build — no remaining open questions. The 4-slot list above is a proposal; flag if you want different/more slots before or during the build (cheap to change, it's just the constant list + dropdown, not a migration).
