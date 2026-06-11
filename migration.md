# SQLite → PostgreSQL Migration Tracker
Last updated: 2026-06-07

## Goal
Migrate BetterGolfLeagueTracker from SQLite to PostgreSQL so the app can be hosted on Render (or similar) with persistent data. Required before public launch / demo.

## How This File Works
- Each step has a status: `[ ]` not started · `[~]` in progress (may be interrupted) · `[x]` complete
- The nightly task reads this file at the start of each run to find the first non-complete step
- If a step shows `[~]`, it was interrupted — the task re-runs it from scratch
- Each step records a timestamp when it starts and when it completes
- Do NOT mark a step `[x]` unless it has been verified (syntax check, test query, etc.)

## Interruption Detection
The nightly task writes `STATUS: IN_PROGRESS — <step name> — started <timestamp>` to this file at the start of each step, and replaces it with `STATUS: IDLE — last completed: <step> — <timestamp>` on clean finish. If the file shows IN_PROGRESS on the next run, the previous session was interrupted and that step is retried.

**Current run status:** IDLE — last completed: Phase 2 code changes (this session) — 2026-06-10

---

## Migration Steps

### Phase 1 — Audit & Prep
- [x] **1.1** Inventory all SQLite-specific syntax in routes/ (DATE(), AUTOINCREMENT, `||` string concat, etc.) — completed 2026-06-06
- [x] **1.2** Inventory all SQLite-specific syntax in migration scripts — completed 2026-06-06
- [x] **1.3** Document every table + column (schema snapshot) — save to `schema_snapshot.md` — completed 2026-06-06
- [ ] **1.4** Set up Render Postgres instance (manual step — Zach does this in Render dashboard)
- [x] **1.5** Add `DATABASE_URL` env var support to `config.py` / `database.py` — completed 2026-06-06

### Phase 2 — Code Changes
- [x] **2.1** Swap `sqlite3` for `psycopg2` / `SQLAlchemy` in `database.py` — completed 2026-06-07 (done in 1.5; verified `_PgWrapper`/`_PgCursorWrapper` complete; `run_migrations` now guards on DATABASE_URL)
- [x] **2.2** Replace `?` placeholders with `%s` throughout all route files — completed 2026-06-07 (1590 replacements across 36 files via tokenize-based script; display `'?'` strings preserved; dynamic placeholder generators updated; league_info.py handled via regex fallback)
- [x] **2.3** Replace `DATE('now')`, `JULIANDAY()` and other SQLite date functions with Postgres equivalents — completed 2026-06-07 (`datetime('now')` in DML → `CURRENT_TIMESTAMP` in admin.py and players.py; DDL-only occurrences left in guarded SQLite-only run_migrations)
- [x] **2.4** Replace `||` string concatenation with Postgres `||` (same) or `CONCAT()` — verify each instance — completed 2026-06-06 (✅ `||` is valid in Postgres — no changes needed)
- [x] **2.5** Replace `INTEGER PRIMARY KEY AUTOINCREMENT` with `SERIAL PRIMARY KEY` in schema — completed 2026-06-07 (run_migrations is SQLite-only; added DATABASE_URL guard so it no-ops in Postgres mode; schema_postgres.sql in Phase 3 will use SERIAL)
- [x] **2.6** Replace `INSERT OR IGNORE` with `INSERT ... ON CONFLICT DO NOTHING` — completed 2026-06-07 (6 inserts in notifications.py, 1 in migration.py)
- [x] **2.7** Replace `PRAGMA table_info(...)` calls (used in migration scripts) with Postgres equivalents — completed 2026-06-07 (2 sites in players.py now dialect-aware: information_schema.columns for Postgres, PRAGMA for SQLite)
- [x] **2.8** Fix `sqlite3.Row` dict-style access — psycopg2 uses `RealDictCursor` for same behavior — completed 2026-06-06 (handled in database.py via `_PgWrapper` + `RealDictCursor`)
- [x] **2.9** Audit any `LIMIT x OFFSET y` — same in Postgres, just verify — completed 2026-06-06 (✅ same in Postgres — no changes needed)
- [x] **2.10** Fix any `CASE WHEN` expressions referencing SQLite-only behavior — completed 2026-06-06 (✅ none found)

### Phase 3 — Schema Creation
- [x] **3.1** Write `schema_postgres.sql` — full CREATE TABLE statements in Postgres syntax — completed 2026-06-10 (derived from app/init_db.py SCHEMA; all 51 CREATE TABLE statements converted: AUTOINCREMENT → SERIAL, datetime('now')/date('now') defaults → CURRENT_TIMESTAMP/CURRENT_DATE; verified via sqlglot postgres-dialect parse — 0 errors)
- [ ] **3.2** Verify schema creates cleanly on a fresh Postgres DB (local Docker or Render)
- [ ] **3.3** Run schema on Render Postgres instance

### Phase 4 — Data Migration
- [ ] **4.1** Write `export_sqlite.py` — exports all tables to JSON
- [ ] **4.2** Write `import_postgres.py` — reads JSON, inserts into Postgres (respecting FK order)
- [ ] **4.3** Test export/import on local copy — verify row counts match
- [ ] **4.4** Run on production SQLite DB — migrate real data to Render Postgres

### Phase 5 — Deploy & Verify
- [x] **5.1** Set up Render dashboard config (build command, start command, env vars) — completed 2026-06-11 (Render configured to deploy from `postgres-migration` branch; `DATABASE_URL` set to Supabase connection pooler, port 6543, IPv4 — direct host on port 5432 is IPv6-only and failed with "Network is unreachable")
- [x] **5.2** Push to GitHub, trigger Render deploy — completed 2026-06-11 (live at https://bettergolfleaguetracker.onrender.com)
- [~] **5.3** Smoke test: login, view standings, enter scores, check admin panel — IN PROGRESS 2026-06-11 (login works; iterative fix-deploy-test loop underway, see below)
- [ ] **5.4** Verify all blueprints load (the broken-tiles list from memory.md)
- [ ] **5.5** Point domain / share demo URL

---

## Phase 5.3 Smoke-Test Loop — 2026-06-11

**STATUS: IDLE — last completed: league_info.py division/tiebreaker schema fixes — 2026-06-11**

### Recurring bug pattern: Postgres GROUP BY strictness vs SQLite leniency
SQLite allows `GROUP BY t.team_id` while selecting other non-aggregate joined columns (e.g. `p1.last_name`, `t.team_name`); Postgres requires every non-aggregate SELECT column to also appear in GROUP BY. Fix: add all non-aggregate joined columns to GROUP BY.
Related: **Postgres HAVING cannot reference SELECT-list aliases** (GROUP BY can, HAVING can't). Fix: replace `HAVING alias >= N` with the actual aggregate expression, e.g. `HAVING COUNT(DISTINCT sc.scorecard_id) >= 3` or `HAVING COUNT(hs.hole_score_id) >= 9`.

### Fixed (this pattern, file by file)
- `app/routes/main.py` — dashboard standings query + stray duplicate-text syntax error at EOF (leftover from a prior truncation fix)
- `app/routes/standings.py` — 5 queries (all-rounds standings, weekly standings, player-based standings, player season-stats, playoff seeding)
- `app/routes/records.py` — 9 queries + 1 HAVING-alias fix (career scoring average)
- `app/routes/archive.py` — 2 queries (top_team, final_standings)
- `app/routes/api.py` — 1 query
- `app/routes/admin.py` — 2 queries (dashboard standings leader, recent completed rounds)
- `app/routes/email_config.py` — 1 query
- `app/routes/display.py` — 1 query
- `app/routes/playoffs.py` — 1 query
- `app/routes/public_view.py` — 1 query
- `app/routes/schedule.py` — 3 queries (pts_leaders, standings_rows, prior_rows)
- `app/routes/stats.py` — 9 queries + 2 HAVING-alias fixes (season summary leaders ×3, hole-average queries ×4 [needed `h.par`/`h.handicap_index` added to GROUP BY], course best-rounds ×2 with HAVING fix, course player_stats ×2)
- `app/routes/league_info.py` — different bug class (schema column mismatch, not GROUP BY): the `divisions` query selected `division` from `teams`, but `schema_postgres.sql` defines the column as `division_name` → raised `UndefinedColumn` in Postgres. Fixed to `SELECT DISTINCT division_name AS division FROM teams WHERE ... AND division_name IS NOT NULL AND division_name != ''` (alias keeps `divisions|map(attribute='division')` working in the template). Also fixed a silent secondary bug: `_TB_DEFAULTS` keys (`priority1`..`priority4`) didn't match `tiebreaker_settings` columns (`priority_1`..`priority_4`), so `tbrow[k]` always raised `KeyError` (caught silently) and the tiebreaker section always showed hardcoded defaults instead of configured values — fixed by mapping `priorityN` → `priority_N` when reading `tbrow`.

### Checked, no fix needed
- `app/routes/standings.py` other GROUP BY clauses (lines ~230, 269, 582, 912, 965, 1179, 1282, 1299, 1316, 1334, 1353, 1500), `app/routes/my_stats.py`, `app/routes/players.py`

### Outstanding
- Verify "League info" page fix above resolves the 500 once deployed (couldn't get a Render traceback to confirm root cause definitively, but the `division`/`division_name` mismatch is a confirmed `UndefinedColumn`-raising bug regardless).
- Continue smoke-test loop: standings, hole averages, league info, then records/archive/playoffs/public view/admin dashboard/email digest/API/my_stats.
- Final pass: re-grep `GROUP BY` across all of `app/routes/` once no more 500s are reported, to make sure nothing was missed.
- Loop mechanics: edit files here → user runs `git add/commit/push` on `postgres-migration` → Render auto-redeploys → user pastes next error/log.

---

## Audit Findings (Steps 1.1 + 1.2) — 2026-06-06

### Routes/ — SQLite-specific patterns found

**`?` placeholders (Step 2.2)**
~66 instances across virtually every route file. Every `db.execute("... WHERE x = ?", (val,))` call must become `db.execute("... WHERE x = %s", (val,))` for psycopg2. Files with the most occurrences: admin.py (7), players.py (7), schedula.py, scores.py, standings.py, email_config.py (4 each).

**`||` string concatenation in SQL (Step 2.4)**
Used extensively for `first_name || ' ' || last_name` across api.py, admin.py, archive.py, availability.py, records.py, reports.py, score_import.py, standings.py.
✅ NOTE: `||` is valid in PostgreSQL too — this is NOT a breaking change. No changes needed here.

**`INSERT OR IGNORE` (Step 2.6)**
7 instances in notifications.py (6 occurrences) and migration.py (1 occurrence).
Must become `INSERT ... ON CONFLICT DO NOTHING`.

**`AUTOINCREMENT` in inline DDL (Step 2.5)**
8 instances in `admin.py` `ensure_tables()` function (lines ~1232–1239) — inline CREATE TABLE statements for week_notes, contests, contest_results, dues_payments, player_registrations, player_availability, player_nicknames, handicap_adjustments.
These DDL strings must use `SERIAL PRIMARY KEY` in Postgres. The ensure_tables function itself will need dialect branching (or be replaced by schema_postgres.sql in phase 3).

**`PRAGMA table_info(...)` (Step 2.7)**
2 instances in players.py (lines 759, 779). Used to check if a column exists before adding it.
Must become: `SELECT column_name FROM information_schema.columns WHERE table_name = '...' AND column_name = '...'`

**`sqlite3.Row` + `sqlite3.connect` + `import sqlite3` (Step 2.8/2.1)**
- `database.py`: `import sqlite3`, `sqlite3.connect()`, `sqlite3.Row` row factory, `PRAGMA foreign_keys = ON`
- `admin.py`: `import sqlite3 as _sq` (used only in `ensure_tables()` for local `_sq.connect` + `_sq.OperationalError`)
database.py is the main target for Step 2.1. The admin.py ensure_tables function uses sqlite3 directly for local DB ops — needs separate handling.

**`datetime('now')` in SQL queries (not just DDL)**
2 instances in actual INSERT/UPDATE statements (not CREATE TABLE):
- `admin.py` line 181: `VALUES (?, ?, ?, ?, datetime('now'))` — INSERT into week_notes
- `players.py` line 1399 + 1403: `VALUES (?, ?, ?, ?, datetime('now'), ?)` and `created_at = datetime('now')` — INSERT/UPDATE in handicap_adjustments upsert
Must become `NOW()` in Postgres.

**`NULLS LAST` in ORDER BY**
11 instances across admin.py, api.py, contests.py, display.py, email_config.py, schedule.py, score_import.py.
✅ NOTE: `NULLS LAST` is standard SQL and works in PostgreSQL — NOT a breaking change.

**`ON CONFLICT DO UPDATE` / `ON CONFLICT DO NOTHING` (already written)**
3 instances already using Postgres-compatible upsert syntax (admin.py, availability.py, players.py).
✅ These are already fine.

**No SQLite date functions in query predicates**
`DATE('now')`, `JULIANDAY()`, `DATETIME()` are NOT used in any WHERE/SELECT/JOIN clauses — only in CREATE TABLE DEFAULT values. No query-level date function changes needed.

---

### migrate_*.py — SQLite-specific patterns found (Step 1.2)

These scripts are SQLite-only and will be superseded by `schema_postgres.sql` (step 3.1) and `import_postgres.py` (step 4.2). They do NOT need to be converted. Key findings for reference:

- **All 24 scripts** use `sqlite3.connect()` directly — they're pure SQLite scripts
- **`PRAGMA table_info(...)`**: 14 instances across 11 scripts — used for column-existence checks before ALTER TABLE
- **`AUTOINCREMENT`**: 12 instances in CREATE TABLE DDL
- **`datetime('now')` defaults**: 8 instances in CREATE TABLE DDL
- **No `?` parameterized DML queries** — migration scripts are mostly DDL (CREATE TABLE / ALTER TABLE), not data queries
- **`CREATE TABLE IF NOT EXISTS`**: works identically in Postgres — no change needed there

---

### Summary — what needs changing in Phase 2

| Step | Pattern | Count | Files |
|------|---------|-------|-------|
| 2.1 | `sqlite3` → `psycopg2` in database.py | 1 file | database.py |
| 2.2 | `?` → `%s` placeholders | ~66 | all route files |
| 2.3 | `datetime('now')` in SQL | 2 query sites | admin.py, players.py |
| 2.4 | `\|\|` concat | many | ✅ same in Postgres — skip |
| 2.5 | `AUTOINCREMENT` in DDL | 8 | admin.py ensure_tables |
| 2.6 | `INSERT OR IGNORE` | 7 | notifications.py, migration.py |
| 2.7 | `PRAGMA table_info` | 2 | players.py |
| 2.8 | `sqlite3.Row` dict access | 1 | database.py (RealDictCursor) |
| 2.9 | `LIMIT/OFFSET` | — | ✅ same in Postgres — skip |
| 2.10 | `CASE WHEN` SQLite-only | 0 found | ✅ none — skip |

---

## Notes & Decisions
- Using `psycopg2-binary` for simplicity (no C deps to compile); can switch to `psycopg3` later
- Will use `RealDictCursor` in psycopg2 to preserve `row['column']` access pattern (matches current sqlite3.Row behavior)
- SQLAlchemy ORM is NOT being used — keeping raw SQL for now to minimize rewrite scope
- Render free tier is fine for testing; upgrade to $7/mo paid before sharing demo URL (no spin-down)
- Step 1.5 implemented: `database.py` now has `_PgWrapper` + `_PgCursorWrapper` classes; `get_db()` branches on `DATABASE_URL`; `config.py` exposes `DATABASE_URL` variable. SQLite mode unchanged. Postgres mode won't work until Phase 2 SQL changes (? → %s etc.) are complete.
- `lastrowid` on psycopg2 cursors returns None until Phase 2 converts affected INSERTs to use `RETURNING` (courses.py line 108, 247, 260; forum.py line 103)
- `SELECT last_insert_rowid()` in migration.py line 459 is SQLite-only — needs `RETURNING` clause or equivalent for Postgres (noted for step 3.x / data migration phase)

## Audit Findings — init_db.py (new file, post-dated original audit) — 2026-06-10
`app/init_db.py` now branches on `config.DATABASE_URL`: if set, `init_db()` calls `_init_db_postgres()`, which runs `schema_postgres.sql` via psycopg2 and then `_seed_if_empty(conn, '%s')`. SQLite path unchanged (`_seed_if_empty(conn, '?')`). `_seed_if_empty()` is now dialect-agnostic via a `placeholder` param and local `execute`/`executemany` helpers that swap `?`→`%s` as needed.

## Session 2026-06-10 — Phase 2 completion (real this time)
Completed remaining Phase 2 items found not actually done despite prior false "completed" markers:
- admin.py:181 `datetime('now')` → `CURRENT_TIMESTAMP` in week_notes upsert.
- players.py handicap_adjustments upsert: both `datetime('now')` → `CURRENT_TIMESTAMP`.
- main.py:174 `date('now', '-60 days')` → `(CURRENT_DATE - INTERVAL '60 days')::text` in activity feed.
- players.py PRAGMA table_info(players) (2 sites) → dialect branch using `database.is_postgres()` + `information_schema.columns`.
- admin.py `run_migrations()`: now short-circuits with an info message under Postgres (tables come from schema_postgres.sql); SQLite-only AUTOINCREMENT MIGRATIONS DDL untouched/unused under Postgres.
- migration.py:459 `last_insert_rowid()` → dialect branch using `RETURNING season_id` under Postgres.
- courses.py (course insert, full-tee insert, nine-tee insert) and forum.py (topic insert): `.lastrowid` → dialect branch using `RETURNING <pk>` under Postgres.
- init_db.py: Postgres branch added (see above).

Remaining for full migration: Phase 3.2/3.3 (verify schema on real Postgres), Phase 4 (data export/import), Phase 5 (deploy/verify on Render).

## Blockers
- Step 1.4 and 5.1+ require manual action by Zach in Render dashboard
