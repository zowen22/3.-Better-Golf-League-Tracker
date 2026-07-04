# Skins Flights — Investigation for Fable

**Type:** Feature Scoping (pre-design investigation, not an implementation plan)
**Status:** Open — findings ready for Fable to plan from
**Prepared by:** Sonnet, 2026-07-04
**Linked WP:** Backlog item "Skins flights: investigate existing skins system..." (`3. Work Packages.md`)

-----

## Ask

Backlog item asked three things before this could be planned: (1) investigate the existing skins system, (2) design a handicap-divided flight system (e.g. low/mid/high handicap tiers get separate skins pots), (3) check whether a `flights` concept already exists in the schema that this could build on. This doc covers (1) and (3) — audit only, no design decisions made, per the standing "audit first, Fable plans" process.

## Finding: a "flight" concept already exists, but it's a false lead

`grep -rln "flight" app/` turns up a real, shipped feature: `/standings/<season_id>/flight` (`standings.py:1675-1835`, `templates/standings/flight_standings.html`). But it is **not** a handicap-tier system — it splits players into "A-flight" and "B-flight" leaderboards based on each player's **A/B role within their own team** (`role == 'A'` vs `role == 'B'`), and that role is assigned by sorting each 2-player team's own two members by handicap (`scores.py:572-577`: lower-handicap teammate becomes "A", the other becomes "B"). This is a **per-team relative split**, not a whole-field handicap-tier split — a low-handicap player can land in "B-flight" if paired with an even-lower-handicap teammate. Confirmed via `schema_postgres.sql` (no `flight`/`flights` table or column anywhere) and via reading the route directly (grouping key is `match_results.role`, not a stored flight assignment).

**Conclusion for Fable: there is nothing to reuse here.** The word "flight" already means something different and shipped in this codebase; a skins-flights feature needs its own concept, ideally named differently in code/UI to avoid confusion with the existing A-flight/B-flight standings view (same underlying word, unrelated mechanism).

## Current skins system — as it actually works (`app/routes/skins.py`, `schema_postgres.sql:437-476`)

- **Schema**: `skins_config` (season-level defaults: `default_amount`, `default_gross_net`, `handicap_percent` — the last one is a **confirmed dead setting**, see `7. GLT Feature Parity.md`'s Dead Settings table, never read anywhere in `skins.py`). `round_skins_settings` (per-round overrides: `amount_override`, `gross_net_override`, `carried_over_amount`, `notes` — one row per round). `round_skins_participants` (**opt-in is already per-player, per-round**: `player_id`, `paid_in`, `amount_paid` — a player can skip skins some weeks and play others). `skins_results` (one row per hole per round: `winner_player_id`, `skins_won`, `payout`, `carried_over`).
- **Calculation** (`_calculate_skins()`, `skins.py:33-99`): takes one flat list of participant player_ids, one flat pot (`sum(amount_paid for participants) + carried_in`), and one holes list. Per hole: lowest score among participants wins outright; ties carry the skin(s) forward (both count and dollar value); unit value = `total_pot / num_holes`. Runs once, across the whole opted-in field, no partitioning of any kind.
- **Display**: `skins/round.html` and `skins/index.html` both assume one pot, one flat results list per round.

## What a flights version would actually require (facts, not a design — Fable's call)

Concrete implementation surface, so Fable can weigh effort against the backlog's stated goal (low/mid/high handicap tiers, separate pots):

1. **Flight assignment mechanism** — doesn't exist. Two real options, each with a real tradeoff: (a) compute flights fresh each round from that week's opted-in participants' current handicaps (robust to week-to-week attendance changes, but a player's flight can shift week to week); (b) fix flight membership for the season up front, e.g. as a player-profile field (stable identity, but breaks down if a player's handicap moves across the boundary mid-season, and needs a manual re-balance point). `scorecards.handicap_at_time_of_play` already exists and would be the natural input for option (a).
2. **Pot allocation across flights** — no existing mechanism to adapt. Two real options: (a) one pot per flight, each independently configured (mirrors `skins_config.default_amount`, just N times); (b) one collected pot, split proportionally by how many participants opted into each flight (uses the existing per-player `amount_paid` tracking naturally — a flight's pot = sum of `amount_paid` for players in that flight — probably the more natural fit given opt-in is already per-player, not a fixed override).
3. **Carryover** — currently one value per round (`round_skins_settings.carried_over_amount`). Flighted skins logically need **per-flight carryover** (a flight with no winner one week should roll its own skins forward, not affect the other flight's pot) — this needs either a new per-flight-per-round table (parallel to `round_skins_settings`) or extending `round_skins_participants`/a new junction with a flight-scoped carryover column.
4. **Results storage** — `skins_results` is currently one row per hole per round, with an implicit assumption of a single winner per hole. Flighted skins need **multiple potential winners per hole** (one per flight) — requires adding a `flight_number` (or similar) column to `skins_results` so a hole can have both a low-flight winner and a high-flight winner recorded simultaneously.
5. **Number of flights** — backlog example says "low/mid/high" (3), but 2 (low/high) is also a reasonable default. Whichever is chosen needs to be a real config value (`skins_config` gains a column), not hardcoded.
6. **Display** — both `skins/round.html` and `skins/index.html` need a per-flight breakdown instead of one flat list; not a large change once the data model supports it, but not zero either.

**Net for Fable**: this is a genuine feature addition, not a settings tweak — touches schema (2-4 new columns/tables), the core `_calculate_skins()` call site (needs to run once per flight instead of once per round), and both skins templates. The two real open design questions (assignment mechanism, pot-allocation method) are exactly the kind of thing that belongs in this handoff's Stop Conditions if Fable doesn't want to decide them outright — recommend surfacing both to @user as an explicit choice before locking in an Implementation Plan, since either direction is defensible and changes the schema shape.
