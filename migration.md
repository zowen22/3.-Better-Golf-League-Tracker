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

**Current run status:** IDLE — last completed: 3.1 schema_postgres.sql — 2026-06-10

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
- [ ] **5.1** Set up `render.yaml` or Render dashboard config (build command, start command, env vars)
- [ ] **5.2** Push to GitHub, trigger Render deploy
- [ ] **5.3** Smoke test: login, view standings, enter scores, check admin panel
- [ ] **5.4** Verify all blueprints load (the broken-tiles list from memory.md)
- [ ] **5.5** Point domain / share demo URL

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
`app/init_db.py` (added after the 2026-06-06/07 audit) contains a SQLite-only `SCHEMA` string (51 CREATE TABLE statements, run via `sqlite3.connect().executescript()`) plus a `_seed_if_empty()` demo-data seeder using `?` placeholders and `executemany`. This file is NOT imported by anything Postgres-aware yet — `app.py` calls `init_db(app.config['DATABASE'])` unconditionally with a sqlite3 connection.

- `schema_postgres.sql` (3.1, done) now covers the CREATE TABLE side for Postgres.
- Still TODO (folded into Phase 3/5): `init_db.py` itself needs a DATABASE_URL branch — when running against Postgres it should execute `schema_postgres.sql` via psycopg2 instead of `sqlite3.connect().executescript(SCHEMA)`. The `_seed_if_empty()` demo-data seeder also needs a Postgres-compatible path (`%s` placeholders, psycopg2 cursor) if the demo seed should run on Render too.
- Two `datetime('now')`/`date('now')` DEFAULT clauses inside `_seed_if_empty()` itself: none found — seed data uses literal date strings ('2026-06-05' etc.), so no conversion needed there.

## Blockers
- Step 1.4 and 5.1+ require manual action by Zach in Render dashboard
