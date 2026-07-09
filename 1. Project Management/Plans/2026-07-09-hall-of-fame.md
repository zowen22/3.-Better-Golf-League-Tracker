# Plan: Hall of Fame — Admin-Curated Cross-Season Awards

*Status: `Evaluating`*
*Opened: 2026-07-09 — from the GLT Stats Feature Parity pass (`7. GLT Feature Parity.md`, item #5)*

-----

## GLT page covered

`halloffame/hall-of-fame-winners` — a cross-season log of admin-defined custom awards (e.g. "Rookie of the Year," "Most Improved") and their winners, one row per (Season, Award, Winner, Comments).

## Current BGLT state

`standings.py`'s `/awards` route computes **auto-derived, current-season-only** leaderboards (Points Leader, Birdie Machine, Eagle Eye, Best Match Record, Low Round, Hot Streak, Most Improved Handicap) — genuinely useful, but architecturally different from what GLT's page does: those are always-computed rankings for the season in progress, not a **persisted, admin-curated history** of custom award types that can span every season the league has ever run.

This is a real, standalone gap — nothing in BGLT lets an admin define an arbitrary award name and record who won it, season after season.

## Decision — is this worth building, and how much admin flexibility does it need?

**Approach A: Fully custom award types** (admin defines the award name/description once, then records a winner per season) — matches GLT exactly.
- *Tradeoffs:* new schema (`award_types`, `award_winners` or similar), full admin CRUD UI. Real effort, but genuinely new capability, not a variant of something that already exists.
- *Effort:* M.

**Approach B: A handful of fixed award slots** (e.g. always exactly "Rookie of the Year" + "Most Improved" + one free-text slot), just recorded per season rather than fully computed.
- *Tradeoffs:* much smaller build, but doesn't match GLT's actual flexibility and would need a schema migration later anyway if @user wants more award types.
- *Effort:* S.

**Recommendation: lean A**, but this is much more of a "does @user actually want this" question than a technical one — it's a genuinely new feature, not a gap-fill of something almost-there.

## Open questions for @user

- Does this league actually give out custom awards worth tracking, or was GLT's Hall of Fame page unused/aspirational for most leagues? Worth confirming real demand before building.
- If yes: roughly how many award types, and are they the same every season or do they change?

## Next step

This is the lowest-priority of the plan docs opened this pass specifically because it's new-feature-shaped rather than gap-fill-shaped — recommend confirming real demand with @user before scoping further.
