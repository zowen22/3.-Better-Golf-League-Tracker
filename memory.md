# BetterGolfLeagueTracker — Project Memory
Last updated: 2026-06-07

## Strategic Plan: Hosting + Database
- **GitHub repo:** https://github.com/zowen22/BetterGolfLeagueTracker
- **Hosting plan:** Deploy on **Render** with a **persistent disk** (mounted at `/data`) to keep SQLite across deploys/restarts. ~$7/mo for web service + $0.25/GB/mo for disk.
- **Current database:** SQLite — fine for launch. Small concurrent user base (golf league) means no write-contention issues.
- **Future migration:** Move to Postgres when scaling warrants it. Render offers managed Postgres — same platform, easy transition. Migration groundwork already done in `database.py` (dialect abstraction, `?`→`%s`, etc.). See `migration.md` for details.
- **Key constraint:** Don't use SQLite-specific syntax in new code — avoid `last_insert_rowid()`, `INSERT OR IGNORE`, `PRAGMA`, and SQLite date functions. Use Postgres-compatible equivalents already established in the codebase.

Last updated: 2026-06-05 (automated bugfix run #11)

## Bug Fixes — 2026-06-05 (automated off-peak run #11)

### Fixed: `score_import.py` crashes with `KeyError: 't1_id'` on every CSV import attempt
- **Route:** `POST /admin/import/season/<id>` (and any call to `_resolve_player_in_matchup()`)
- **Root cause:** `_matchup_list()` builds the matchup reference dicts from a SQL query that never selected `t1.team_id AS t1_id` or `t2.team_id AS t2_id`. However, both `_resolve_player_in_matchup()` (lines 139, 142, 145, 148) and `process_upload()` (lines 382–383) directly access `matchup_info['t1_id']` and `matchup_info['t2_id']`. Result: every CSV upload attempt raised `KeyError: 't1_id'` before processing a single row.
- **Fix:** Added `m.team1_id AS t1_id, m.team2_id AS t2_id` to the SELECT clause in `_matchup_list()`.
- **File changed:** `routes/score_import.py` — 1 targeted replacement via Python script.
- **Syntax verified:** `ast.parse()` clean.

### No other critical bugs found this run
Scanned all route files. Other patterns checked:
- `session['league_id']` direct accesses — all are inside `@login_required`/`@admin_required` decorated routes; safe.
- `int()` conversions — all 4 instances already wrapped in `try/except (ValueError, TypeError)`.
- Division by zero — all division sites already guarded with `if list` / `if count > 0` / `if total` checks.
- `matchup['league_id']` accesses — all queries JOIN seasons to fetch `league_id`; no matchups-table column issue.
- New blueprint routes (display, league_info, score_import, email_prefs, availability, my_stats) — all registered in app.py; `url_for` references match blueprint+function names.


## 18-Hole Round Support — BUILT (2026-06-05, automated run #10)

### What was built
Full support for 18-hole rounds throughout the app. Leagues can now create Full 18-hole tees (holes 1–18 in a single tee record), enter scores across 18 holes with live OUT/IN/TOT subtotals, view completed 18-hole scorecards with proper split columns, and print blank 18-hole scorecards.

### Feature details
- **New tee type** `nine='full'` — a single tee record with holes 1–18 (default par=4, total=72)
- **Course Management — Add Tee form** (`add_tee.html`): new "Round Format" radio selection; "Full 18-Hole Round" option creates one tee with 18 holes; "9-Hole" keeps existing front/back checkbox behavior; JS hides checkboxes when Full 18 is selected
- **Course Detail** (`detail.html`): updated table shows Format column (18-Hole badge vs 9-Hole badge), combined Par total for 9-hole pairs, "All 18 ✏" edit link for full tees, proper delete button
- **Edit Holes** (`holes.html`): full18 tees show two separate 9-hole grids (Front/Back) with OUT/IN subtotals; hdcp max raised from 9 to 18 for full18 tees
- **Score Entry** (`enter.html`): detects 18-hole tees (`is_18 = holes|length > 9`); for 18-hole tees shows OUT subtotal column after hole 9, IN + TOT columns at end; `sc_out_{pid}`, `sc_in_{pid}`, `sc_tot_{pid}` DOM IDs; JS `updateAll()` computes front/back subtotals live; mobile shows divider between hole 9 and 10
- **Score View** (`view.html`): same OUT/IN/TOT column split for completed 18-hole scorecards; tee label shows "Full 18" instead of raw `nine` value
- **Blank Scorecard** (`blank_scorecard.html`): 18-hole tees get OUT/IN/Tot columns in both A and B flight tables; stroke-dot cells span front and back halves
- **CSS** (`main.css`): `.sc-col-out`, `.sc-col-tot`, `.sc-subtotal-col` (green tinted background, bold borders), `.tee-format-badge` with `.tee-format-18` / `.tee-format-9` chips, `.holes-section-label`, `.holes-totals-bar`, `.mob-nine-divider`, `.bsc-subtotal-col`
- **Tee label display**: `nine` value `full` → "Full 18" label everywhere (score entry dropdown, score view header, kiosk/display, week preview)
- **No DB schema changes** — `tees.nine` column already accepts any text; storing `'full'` is backward-compatible

### Files changed
- `routes/courses.py` — `_get_tees_grouped()` adds `full` key; `add_tee()` handles `nine_type=full18`; `edit_holes()` passes `is_full18`; `tees_json()` shows proper labels
- `templates/courses/add_tee.html` — Round Format radio + JS toggle
- `templates/courses/detail.html` — Format/Par columns, full18 delete/edit links, tee-format badges
- `templates/courses/holes.html` — Two 9-hole grids for full18 tees; hdcp max 18; OUT/IN totals
- `templates/scores/enter.html` — OUT/IN/TOT columns; `is_18` flag; JS subtotals; mobile divider; nine label fix
- `templates/scores/view.html` — OUT/IN/TOT display for 18-hole scorecards; nine label fix
- `templates/schedule/blank_scorecard.html` — 18-hole OUT/IN/Tot columns in A and B flight tables
- `templates/schedule/week_preview.html` — nine label fix
- `static/css/main.css` — 18-hole CSS classes appended

### Key decisions
- `nine='full'` is a new value for the `tees.nine` column; backward-compatible (existing front/back tees unaffected)
- Detection: `holes|length > 9` in templates — no new DB column needed
- Handicap engine unchanged: `differential = gross − par` works naturally for any hole count
- `_calc_strokes` in schedule.py already used `total_holes=len(holes)`, so stroke dots work for 18 holes automatically
- Duplicate-check in `add_tee()` uses `(tee_name, gender)` key — prevents adding both front/back AND full18 for same name (by design)
- Par default for full18 tee: 72 (18 × par4); admin edits actual values after creation

### No DB migration needed

---

## Bulk Score CSV Import — BUILT (2026-06-05, automated run #9)

### What was built
A complete admin workflow for bulk-importing historical round scores from a CSV file. Commissioners can now upload past season data without entering each round manually.

### Feature details
- **New blueprint** `routes/score_import.py` registered at `/admin/import/`
- **Routes:**
  - `GET /admin/import/season/<id>` → upload form + matchup reference table
  - `GET /admin/import/season/<id>/template` → download pre-filled CSV template (one sample row per uncompleted matchup with player names filled in)
  - `POST /admin/import/season/<id>` → parse, validate, process, show results page
- **CSV format** — one row per player, 4 rows per matchup (15 columns):
  `matchup_id, round_date, course_name, tee_name, player_first, player_last, h1, h2, h3, h4, h5, h6, h7, h8, h9`
- **Validation per row:**
  - `matchup_id` must be integer and exist in this season
  - Scores must be integers 1–20
  - Exactly 4 player rows required per matchup
  - Player names matched case-insensitively against players on the matchup's teams (last-name fallback)
  - Skips already-completed matchups with clear error message
- **Processing:**
  - Resolves course/tee from CSV hints → falls back to matchup's assigned course/tee → first available tee
  - Computes playing handicaps (% of handicap_index, capped at max_handicap from league settings)
  - Computes net scores via `strokes_on_hole()` using hole handicap_index values
  - Computes hole-by-hole match play points via `calc_match_play()`
  - Inserts: `rounds`, `scorecards`, `hole_scores`, `match_results` records
  - Marks matchup `status='completed'`
  - Recalculates handicaps for all imported players via `recalc_handicap_for_player()`
- **Results page:** Shows imported matchups with pts scores + winner, skipped matchups with reasons, row-level errors; "Import Another File" button
- **Template download:** Pre-fills matchup_id, scheduled_date, and all 4 player names — commissioner just fills in the 9 hole scores per player
- **Admin panel button:** "⬆ Import Scores" added to admin quick-actions bar

### Files changed
- `routes/score_import.py` — new blueprint (~310 lines); `upload_form()`, `download_template()`, `process_upload()` routes; `_resolve_course_tee()`, `_resolve_player_in_matchup()`, `_parse_csv_upload()`, `_matchup_list()` helpers
- `templates/admin/score_import.html` — new template; format docs, file upload form, template download, matchup reference table, results display
- `static/css/main.css` — appended `.si-*` styles (~40 lines)
- `app.py` — added `score_import_bp` import + `register_blueprint`; also fixed pre-existing truncation (`if __n` → `if __name__ == '__main__': app.run(debug=True)`)
- `templates/admin/season.html` — added "⬆ Import Scores" btn to quick-actions

### Key decisions
- One-step (no preview): upload → process → results page. Keeps it simple; errors are shown inline per matchup with clear skip reasons.
- 4-row-per-matchup format balances usability (spreadsheet-friendly) vs column explosion (one-row-per-matchup would need 48 cols)
- Player matching: exact case-insensitive first+last, then last-name-only fallback for common nicknames/typos
- Role (A/B) assigned by which team slot the player occupies (player1=A, player2=B) — consistent with rest of app
- Net scoring and match play computed automatically — no need for commissioner to calculate points
- Graceful if no tee/holes set up: imports gross scores with gross-based match play (no net adjustment)
- No DB migration needed — uses existing schema

### No DB migration needed

---

## TV / Kiosk Display Mode — BUILT (2026-06-05, automated run #8)

### What was built
A full-screen, auto-refreshing scoreboard page designed to display on a clubhouse TV during or after a round. No navigation chrome — a dark green theme with large fonts readable from across a room.

### Feature details
- **Routes** (new `routes/display.py` blueprint):
  - `GET /display` → redirect to current season's latest interesting week
  - `GET /display/<season_id>` → redirect to best week for that season
  - `GET /display/<season_id>/week/<n>` → the kiosk view (`kiosk()`)
  - `_current_week()` helper: prefers in-progress/scheduled week, then latest completed, then first scheduled
- **Kiosk view** (`templates/display/kiosk.html`) — standalone HTML (no base.html):
  - Header bar: league name, season name, week number, course/tee, week date
  - Status badge: 🔴 LIVE (blinking dot) / ✅ FINAL / ⏳ UPCOMING with matchup progress count
  - Two-column layout: matchup cards (left, scrollable) + standings (right, fixed sidebar)
  - **Matchup cards** — one per non-bye matchup:
    - Card header: tee time, starting hole, FINAL/LIVE/UPCOMING chip
    - Large score row: team label vs team label with final point totals (winner highlighted in green glow)
    - 🏆 trophy emoji next to winning team
    - Per-player breakdown grid (A/B role chip, name, gross score, pts, win checkmark)
    - "Waiting" message with tee time for unplayed matchups
  - **Standings sidebar**: rank (🥇🥈🥉 medals), team name, total pts, week pts contribution
  - Commissioner note shown on last card (if set)
  - Footer: prev/next week navigation, "✕ Exit Display" back to dashboard, last-updated time
  - **Auto-refresh**: JS countdown timer; reloads every 60 s if any live, every 300 s if all done
- **"📺 Display" button** added to schedule weekly view header alongside 🔴 Live button
- No DB schema changes required

### Files changed
- `routes/display.py` — new blueprint; `current()`, `season_current()`, `kiosk()` routes; `_get_season()`, `_team_label()`, `_standings()`, `_matchup_cards()`, `_current_week()` helpers (~280 lines)
- `templates/display/kiosk.html` — new standalone template; dark green CSS (~310 lines)
- `app.py` — added `from routes.display import bp as display_bp` + `register_blueprint`
- `templates/schedule/index.html` — added "📺 Display" btn-secondary in week header

### Key decisions
- Standalone HTML (no base.html) so there's zero nav chrome — proper full-screen TV experience
- `login_required` — TV at the clubhouse just needs to be logged into the league account; keeps data private
- `_current_week()` intelligently picks the most relevant week to show: live > latest scheduled > latest completed
- Auto-refresh stops at 300 s (5 min) when all matchups are final — avoids hammering the server post-round
- Player breakdown shows gross + points per player in compact rows — readable at TV distance
- CSS uses `clamp()` for all font sizes so it scales gracefully from laptop to 4K TV

### No DB migration needed

---

## Per-Player Email Notification Preferences — BUILT (2026-06-05, automated run #7)

### What was built
Players can now control which league emails they receive. Admins can also manage any player's preferences from the player profile page.

### Feature details
- **DB migration:** `migrate_email_prefs.py` — adds 3 columns to `players`:
  - `email_opt_out INTEGER DEFAULT 0` — blanket opt-out (already referenced by `_get_player_emails()`)
  - `email_opt_out_round_results INTEGER DEFAULT 0` — opt out of personalized round-result scorecard emails
  - `email_opt_out_reminders INTEGER DEFAULT 0` — opt out of pre-round reminder emails
  - **Already applied to DB** (run this session via sandbox /tmp pattern)
- **Player settings page:** `GET/POST /account/email-preferences` in new `routes/email_prefs.py`
  - Shows 3 toggle cards: "Opt out of all emails" (blanket), "Round result emails", "Round reminder emails"
  - Blanket toggle disables the subtype section with JS opacity/pointer-events
  - Fourth card (Announcements & digest) shown as read-only "Managed by commissioner" — those go through `_get_player_emails()` which already checks `email_opt_out`
  - Player's email address shown at bottom for reference
  - Warning banner shown if `email_enabled` is false on the league
- **Admin override:** `POST /admin/players/<id>/email-prefs` in same blueprint — admin can set all 3 flags for any player from their profile page
- **Admin profile section:** "Email Notification Preferences" section added to `templates/players/profile.html` (admin only) — shows current state as 3 stat cards (green=receiving, red=opted out) + a form to override
- **Email enforcement:**
  - `send_player_scorecard_emails()` — updated query now excludes players with `email_opt_out=1` OR `email_opt_out_round_results=1`
  - `send_round_reminder_emails()` — adds per-matchup opt-out lookup; skips players with `email_opt_out=1` OR `email_opt_out_reminders=1`
  - `_get_player_emails()` (blast/digest/announcements) — was already checking `email_opt_out`; now works correctly since column exists
- **Nav link:** 📧 icon added to base.html nav bar (only shown for player-linked accounts)
- **My Stats quick link:** "📧 Email Prefs" added to the Quick Links grid on `/my-stats`

### Files changed
- `migrate_email_prefs.py` — new migration script (already applied to DB)
- `routes/email_prefs.py` — new blueprint; `my_prefs()` GET+POST + `admin_set_prefs()` POST
- `templates/email_prefs/index.html` — new template; toggle cards with JS blanket-disable behavior
- `routes/email_config.py` — updated `send_player_scorecard_emails()` + `send_round_reminder_emails()` to check per-player prefs
- `app.py` — added `email_prefs_bp` import + `register_blueprint`
- `templates/base.html` — added 📧 nav icon link (player-linked accounts only)
- `templates/my_stats/index.html` — added "📧 Email Prefs" quick link
- `templates/players/profile.html` — added "Email Notification Preferences" admin section at bottom
- `static/css/main.css` — appended `.ep-*` toggle styles (~50 lines) + `.ep-admin-*` profile section styles (~15 lines)

### Key decisions
- `email_opt_out` is the blanket flag — all email functions check it; no email is ever sent to an opted-out player
- Granular prefs only suppress their specific email type; blanket opt-out is checked by all senders
- `send_round_reminder_emails` does a per-matchup opt-out query (checking 4 player IDs at once) — efficient single DB call per matchup
- Announcements/digest opt-out is the blanket `email_opt_out` (no separate per-type column for those — they're less frequent and admin-controlled)
- Admin can override any player's prefs (helpful for managing players who don't use the app)
- All DB reads use `COALESCE(email_opt_out, 0)` for graceful pre-migration behavior
- Columns default to 0 (opt-in by default) — existing players keep receiving emails until they change prefs

### DB migration
Already applied to DB. Columns added with DEFAULT 0 — all existing players default to receiving all emails.

---

## Bug Fixes — 2026-06-05 (automated off-peak run #6)

### Fixed: Missing DB tables causing 7 dashboard tiles to crash with OperationalError
- **Root cause:** The SQLite DB did not have the following tables that routes expected: `forum_topics`, `forum_replies`, `sub_requests`, `contests`, `contest_results`, `dues_payments`, `player_registrations`, `handicap_adjustments`, `player_nicknames`, `player_availability`, `week_notes`. All had existing migration scripts but those scripts used `sqlite3.connect(DB_PATH)` directly on the Windows mount, which causes silent write failures from the Linux sandbox.
- **Affected tiles:** Forum, Dues, Contests, Submit Scores (subs), and features: player nicknames, availability, handicap adjustments, commissioner notes.
- **Fix:** Ran all migrations using the correct /tmp copy-and-write-back pattern + `open()+write()+fsync()` for the final write to the Windows mount. All 52 tables now present and verified.
- **Tables created:** `forum_topics`, `forum_replies`, `sub_requests`, `contests`, `contest_results`, `dues_payments`, `player_registrations`, `player_availability`, `player_nicknames`, `handicap_adjustments`, `week_notes`.
- **Columns added:** `leagues.api_key`, `leagues.reg_enabled`, `leagues.reg_welcome_msg` (already existed), `league_settings.dues_amount` (already existed), `league_settings.dues_due_date` (already existed).
- **Note for future migrations:** Always use `open(f,'rb').read()` → modify in /tmp → `open(dst,'wb').write(data); os.fsync()` pattern. `shutil.copy2()` to the Windows mount silently fails; `open()+write()+fsync()` works.

### Fixed: `schedule.index()` crashes on non-numeric `?week=` or `?team=` URL params
- **Route:** `GET /schedule/<season_id>` — unguarded `week_num = int(selected_week)` (line 258) and `tid = int(selected_team)` (line 263). A non-numeric query parameter (e.g. `?week=abc` or a tampered URL) caused a `ValueError` 500.
- **Fix:** Wrapped both in `try/except (ValueError, TypeError)`. Invalid `?week=` falls back to the last week in the schedule; invalid `?team=` is treated as no team filter.
- **File changed:** `routes/schedule.py` — 2 targeted replacements via Python string replace.
- **Syntax verified:** `ast.parse()` clean.

## Bug Fixes — 2026-06-04 (automated off-peak run #5)

### Fixed: `_save_submission()` IndexError on back-9 score entry (self_report.py)
- **Route:** `POST /self-report/<matchup_id>` — submitting self-reported scores for a back-9 tee (holes 10-18) crashed with `IndexError: list index out of range`.
- **Root cause:** `gross[pid]` is built as a 0-indexed list via `player_scores.append(...)`, but the detail-row insert used `gross[pid][h['hole_number'] - 1]` as the index. For front-9 holes (1-9) this gives indices 0-8 — correct. For back-9 holes (10-18) this gives indices 9-17, all out of range on a 9-element list.
- **Fix:** Changed the insert loop from `for h in holes:` to `for i, h in enumerate(holes):` and replaced `gross[pid][h['hole_number'] - 1]` with `gross[pid][i]`, using the enumeration index which is always 0–8 regardless of hole numbering.
- **Note:** The `approve()` path is not affected — it stores `gross[pid]` as a dict keyed by `hole_number`, so `gross[pid][h['hole_number']]` is correct there.
- **Files changed:** `routes/self_report.py` — 1 targeted replacement via Python script.
- **Syntax verified:** `ast.parse()` clean.


## Bug Fixes — 2026-06-04 (automated off-peak run #4)

### Fixed: `course_stats()` crashes on every visit — `matchups` has no `league_id` column (6 queries)
- **Route:** `GET /stats/course/<id>` in `routes/stats.py` — every visit crashed with `OperationalError: table matchups has no column named league_id`.
- **Root cause:** Same bug previously fixed in `standings.py awards()` (run #2) — 6 queries in `course_stats()` used `AND m.league_id = ?` on the `matchups` table alias, which has no `league_id` column.
- **Queries affected:** `hole_rows` (×2), `best_rounds` (×2), `player_stats` (×2) — each with a season-filtered branch and an all-seasons branch.
- **Fix (season-filtered branches):** Removed `AND m.league_id = ?` and its param — `m.season_id = ?` is sufficient since season was already validated against the league at route entry.
- **Fix (all-seasons branches):** Added `JOIN seasons _ls ON m.season_id = _ls.season_id AND _ls.league_id = ?` instead of the invalid `m.league_id = ?` filter — correctly scopes cross-season queries to the current league without relying on the missing column.
- **Files changed:** `routes/stats.py` — 6 targeted replacements via Python script.
- **Syntax verified:** `ast.parse()` clean.

## Handicap Calculation Transparency Page — BUILT (2026-06-04, daytime run #10)

### What was built
A dedicated `/players/<id>/handicap-detail` page giving full transparency into how each player's handicap index was calculated. Players and admins can see exactly which rounds are in the calculation window, which are dropped (highest/lowest), which are counting, the step-by-step formula, and the full index history.

### Feature details
- **Route:** `GET /players/<id>/handicap-detail` appended to `routes/players.py` (`handicap_detail()`); `login_required`
- **Summary cards row**: Current Index (with committee adj badge if active), Rounds Played (vs min required), Calculation Window size, Rounds Averaged, Handicap %
- **Committee adjustment banner**: shown when an active adjustment exists; shows base computed index vs displayed effective index
- **Not-enough-rounds warning**: shown when player hasn't met minimum round threshold
- **Calculation Window table**: all rounds in the last `window` rounds + any padding entries, each row color-coded:
  - 🟢 Counting (green) — included in average
  - 🔴 Dropped High (red) — highest diff(s) dropped per `high_scores_to_drop` setting
  - 🟡 Dropped Low (amber) — lowest diff(s) dropped per `low_scores_to_drop` setting
  - ⬜ Padding (gray) — scratch-play padding rounds (diff=0)
  - Per row: date, season, week, course/tee, gross, par, differential (color-coded +/−)
- **Formula breakdown box**: shows counting diffs sorted, sum, ÷ N, × pct%, rounded = index; committee adj added if active
- **All Rounds (collapsible details element)**: every completed round ever played by the player, with scorecard links, showing their calc role (outside window / counting / dropped / padding)
- **Index History table**: all `handicap_history` rows newest first; shows change (+/−) vs previous computation; current entry highlighted green

### Files changed
- `routes/players.py` — `handicap_detail()` route appended (~130 lines); reuses `_get_settings` from handicap.py; reconstructs window + status assignment in Python
- `templates/players/handicap_detail.html` — new template (~230 lines); summary cards, adj banner, window table with color rows, formula box, all-rounds details, history table
- `templates/players/profile.html` — added "🔢 Handicap Detail" btn in page-header-actions
- `static/css/main.css` — appended `.hd-*` styles (~70 lines)

### Key decisions
- Reconstruction mirrors the exact logic in `recalc_handicap_for_player()` — uses same query, same window/drop/padding logic, so page always matches what the engine actually computed
- Status assignment: sort window by diff, mark low_drop from bottom as dropped_low, high_drop from top as dropped_high, remaining as counting
- Padding entries (diff=0) shown as "Scratch Pad" with `hd-chip-padding` style — labeled clearly so players understand
- Committee adjustment shown transparently: base index vs effective index side by side
- "outside window" rounds shown in the All Rounds collapsible with muted status text (not a chip) to avoid visual clutter
- No DB schema changes required

### No DB migration needed

## League Info / Rules Page — BUILT (2026-06-04, daytime run #9)

### What was built
A member-facing `/league/info` page that reads all league settings and presents them in plain English. Members can always reference scoring rules, handicap methodology, skins details, and playoff format without needing to know the admin panel exists.

### Feature details
- **Route:** `GET /league/info` in new blueprint `routes/league_info.py`; `login_required`; scoped to most recent season
- **Season Overview card**: season name, total weeks, date range, progress bar (completed/total), team count, division names, courses used with color-coded tee badges, holes per round, A/B flight rotation method
- **Scoring Format card**: Match Play vs Stableford badge; net/gross; points per hole; overall match point; max points available per round; Stableford breakdown (eagle/birdie/par/bogey/dbl pts); max score per hole if set
- **Handicap Rules card**: method (par-based vs score-based); rounds used formula (best N of last N+drops); min rounds; handicap percentage; max handicap cap; negative handicap policy; max score per hole for calc purposes; multi-season carry setting
- **Playoff Format card**: teams qualifying, finals weeks, single-elimination description, link to Playoff Picture standings tab
- **Tiebreakers card**: ordered list of priority1–4 from tiebreaker_settings, using human-readable labels; numbered green circles
- **Skins card**: active/not active badge with count, default gross/net, default amount, opt-in policy, carryover description
- **Score Submission card**: self-reporting enabled/disabled, approval requirement, score lock explanation
- **Season Segment card**: shown only if segment_start_week/segment_end_week are configured
- **Dashboard tile**: "📋 League Info" added to the main dashboard grid

### Files changed
- `routes/league_info.py` — new blueprint; single `info()` route; reads league_settings + tiebreaker_settings + matchup counts + course/division info; graceful try/except on all optional tables
- `templates/league_info/index.html` — new template; `.li-grid` responsive 2-col layout; 7–8 cards depending on config
- `app.py` — added `from routes.league_info import bp as league_info_bp` + `register_blueprint`
- `templates/dashboard.html` — added "📋 League Info" dash-card tile
- `static/css/main.css` — appended `.li-*` styles (~90 lines); grid, card, dl, badge, tee-badge, progress bar, tiebreaker list

### Key decisions
- Scoped to most recent season (not season-specific URL) — always shows current rules
- All DB reads graceful (try/except) — works before segment migration, tiebreaker migration, etc.
- No DB schema changes required
- Tee badge color uses the stored `tees.color` field with text-shadow for readability on any background
- Progress bar capped at 100% (integer width) for visual clarity

## Player Availability Tracking — BUILT (2026-06-04, daytime run #8)

### What was built
Players can mark themselves available or unavailable for each round in a season. Admins see a full grid of all players × all rounds with unavailability counts per round and per player.

### Feature details
- **Migration:** `migrate_player_availability.py` — creates `player_availability (avail_id, player_id, league_id, season_id, week_number, available, note, updated_at)` with UNIQUE(player_id, league_id, season_id, week_number). **Needs manual run.**
- **Member page:** `GET/POST /availability/season/<id>` — card grid of all rounds for the season; each card has Available/Unavailable radio toggle (color-coded green/red) and an optional note field (200 char max). POST upserts via ON CONFLICT DO UPDATE. Redirects to same page with flash on success.
- **Admin grid:** `GET /admin/season/<id>/availability` — full player × round matrix; green ✓ / red ✗ cells; amber column header when any player is out that round; hover tooltip shows player note; "Out" count badge per player row; summary bar showing total unavailability flags.
- **"📅 Availability" button** added to admin panel quick-actions bar.
- **"📆 My Availability" button** added to schedule filter bar (only shown when session has player_id, i.e. linked account).
- All DB reads/writes wrapped in try/except or table_exists check — app works before migration is run.

### Files changed
- `migrate_player_availability.py` — new migration script (needs manual run)
- `routes/availability.py` — new blueprint; `my_availability()` GET+POST + `admin_grid()` GET; `_table_exists()`, `_get_season()`, `_get_weeks()`, `_get_avail_map()` helpers
- `templates/availability/my_availability.html` — member card grid with JS color-update on radio change
- `templates/availability/admin_grid.html` — admin read-only matrix with summary bar
- `app.py` — added `from routes.availability import bp as availability_bp` + `register_blueprint`
- `templates/admin/season.html` — added "📅 Availability" quick-action button
- `templates/schedule/index.html` — added "📆 My Availability" btn in filter bar (player-linked accounts only)
- `static/css/main.css` — appended `.avail-*` styles (~70 lines)

### Key decisions
- Availability is self-reported by players; admin view is read-only (no admin override — keeps it simple)
- Default state = available; only explicit unavailable entries are stored (assumed available if no row)
- `_get_weeks()` uses non-bye matchups only — only real playing rounds show up
- Notes visible to admin via hover tooltip; player notes displayed in admin grid cell
- Season switcher on both pages for multi-season leagues
- Table absence is graceful — shows warning banner asking admin to run migration

### DB migration needed
- `migrate_player_availability.py` — run manually: `cd C:\Users\zowen\Documents\Claude\Projects\Golf League WebApp\app && python migrate_player_availability.py`


## Playoff Picture / Clinch Tracker — BUILT (2026-06-04, daytime run #7)

### What was built
A new "Playoff Picture" tab in the standings subnav showing each team's clinch/alive/eliminated status, points behind the cutline, magic (clinch) number, and max possible points for the season.

### Feature details
- **Route:** `GET /standings/<season_id>/playoff-picture` in `routes/standings.py` (`playoff_picture()`); login_required
- **Summary bar**: Playoff Spots, Teams, Cutline pts, Max pts/round, "Season Final" badge when all rounds done
- **Legend**: explains the three status chips (Clinched / Alive / Eliminated)
- **Main table** (sortable by rank):
  - Rank (with medal emojis for top 3), Team, Season Pts, Rounds Played/Total, Rounds Remaining
  - Pts Behind Leader, vs Cutline (+above / −below), Max Possible, Status chip, Clinch Number
  - A dashed cutline divider row separates playoff spots from the bubble
  - Green dot = currently in a playoff spot, gray dot = outside
  - Rows with `status=eliminated` rendered at reduced opacity
- **Points Progress bars**: Visual bar per team showing current pts (green=in, gray=out) vs max possible (light gray) with a red dashed cutline marker; pts shown as current/max
- **Explainer footer**: Describes the logic for Clinched, Eliminated, Max Possible, Clinch Number
- **Playoff logic**:
  - `max_pts_per_round`: empirically computed from actual season data (max sum of all teams' pts in any single matchup)
  - `status=clinched`: team is currently in a playoff spot AND the best challenger's max possible < team's current pts
  - `status=eliminated`: team's max possible pts < current cutline (Nth team's pts where N=playoff_teams setting)
  - `status=alive`: neither clinched nor eliminated
  - `clinch_number` for teams inside cutline: pts needed = challenger_max_possible − current_pts + 1
  - `clinch_number` for teams outside cutline: pts_to_cutline + 0.5 (needs to surpass, not just tie)
  - When season is complete (remaining=0 for all), status is simply rank vs playoff_teams_count
- **Subnav link**: "Playoff Picture" tab added to all 8 standings templates (index, scorecards, weekly, allplay, individual, trend, awards, divisions)

### Files changed
- `routes/standings.py` — appended `playoff_picture()` route (~115 lines)
- `templates/standings/playoff_picture.html` — new template (~165 lines); summary bar, legend, table with cutline divider, progress bars, explainer
- `templates/standings/index.html` — added Playoff Picture subnav link
- `templates/standings/scorecards.html` — added Playoff Picture subnav link
- `templates/standings/weekly.html` — added Playoff Picture subnav link
- `templates/standings/allplay.html` — added Playoff Picture subnav link
- `templates/standings/individual.html` — added Playoff Picture subnav link
- `templates/standings/trend.html` — added Playoff Picture subnav link
- `templates/standings/awards.html` — added Playoff Picture subnav link
- `templates/standings/divisions.html` — added Playoff Picture subnav link
- `static/css/main.css` — appended `.pp-*` styles (~110 lines)

### Key decisions
- No DB schema changes required — uses existing match_results, matchups, teams, league_settings tables
- max_pts_per_round computed empirically (max matchup total from match_results) rather than from settings — handles any scoring configuration automatically; falls back to 20 if no data yet
- Clinch logic uses challenger's max_possible (not just current pts) — correctly handles mid-season scenarios
- Season-complete detection: all teams have remaining=0 → switches to simple rank-based clinch/eliminated
- All DB queries wrapped gracefully; page works even with no completed rounds (shows teams with 0 pts)
- Divisions check is graceful (try/except) so it works before/after that migration

### No DB migration needed

## Commissioner Overview Dashboard — BUILT (2026-06-04, daytime run #6)

### What was built
A dedicated `/admin/overview` page giving commissioners a consolidated at-a-glance view of everything that needs attention and how the season is going.

### Feature details
- **Route:** `GET /admin/overview` in `routes/admin.py` (`overview()`); admin_required
- **Pending Actions Banner** (amber, shown when any pending items exist):
  - Open sub requests count → links to sub requests queue
  - Pending self-report score approvals → links to pending queue
  - Pending player registrations → links to registration queue
  - Total count shown in banner headline
- **Stat Cards Row** (responsive grid, auto-fill):
  - Rounds Played (X / total) with progress bar + % complete
  - Current Standings Leader (team label + pts)
  - Active Players count + user accounts count
  - Dues Paid (X / total) with dues amount + outstanding count; amber outline if any unpaid
  - Unlocked Scorecards count (amber, only shown if > 0)
  - Active Announcements count with manage link
- **Two-column lower section:**
  - Left: Next Round card (week, date, course/tee, tee time, Edit Week + View Schedule btns); Recent Results table (last 8 matchups, pts score, winner bolded, scorecard links)
  - Right: Quick Actions grid (14 links including pending-badge items highlighted amber); Recent Forum Activity (last 3 topics + reply counts); Other Seasons list (if multiple seasons)
- **"📋 Overview" button** added as first item in admin quick-actions bar on `admin/season.html`

### Files changed
- `routes/admin.py` — appended `overview()` route (~160 lines)
- `templates/admin/overview.html` — new template (~160 lines)
- `templates/admin/season.html` — added "📋 Overview" as first quick-action button
- `static/css/main.css` — appended `.ov-*` styles (~100 lines)

### Key decisions
- No DB schema changes — all queries use existing tables with try/except for graceful degradation
- Dues stats computed live from `dues_payments` table (graceful if table absent)
- Unlocked scores detected via `rounds.is_locked=0` on completed matchups (graceful if absent)
- Quick actions grid uses same links as admin panel but with badge counts for pending items
- Page scoped to most recent season by default (not season-specific URL) — always shows current state

## Pre-Round Reminder Emails — BUILT (2026-06-04, daytime run #5)

### What was built
Admin-triggered personalized pre-round reminder emails for any scheduled week. Each player receives their own email showing: date, tee time, starting hole, course/tee, their team name, opponent team name, and flight (A/B).

### Feature details
- **`send_round_reminder_emails(db, league_id, season_id, week_number)`** — new public helper in `routes/email_config.py`; queries all non-bye matchups for the week via JOIN across matchups/teams/players/courses/tees; sends one personalized email per player (skips players without email on file); returns `(sent_count, error_str_or_None)`
- **Route:** `POST /admin/season/<id>/week/<num>/send-reminders` in `routes/admin.py` (`send_week_reminders`); admin_required; calls helper, flashes result, redirects to admin panel
- **edit_week.html:** New "📨 Send Round Reminders" card below the Save form — shows description, confirm dialog, posts to new route
- **schedule/index.html:** "📨 Reminders" button added to the week header — appears alongside "🎯 Preview" when a week has upcoming (non-completed) matchups; visible to admins only (guarded by `session.get('league_admin')`)
- **CSS:** `.ew-reminder-card`, `.ew-reminder-header`, `.ew-reminder-icon`, `.ew-reminder-desc` appended to main.css
- No DB schema changes required

### Files changed
- `routes/email_config.py` — appended `send_round_reminder_emails()` (~90 lines)
- `routes/admin.py` — appended `send_week_reminders()` route (~25 lines)
- `templates/admin/edit_week.html` — added reminder card below form
- `templates/schedule/index.html` — added "📨 Reminders" btn to week header (admin, upcoming weeks only)
- `static/css/main.css` — appended `.ew-reminder-*` styles (~20 lines)

### Key decisions
- Admin-triggered only (no scheduled auto-send) — keeps it simple, admin controls timing
- Fires regardless of `email_on_round_posted` setting — this is a separate admin action
- Requires `email_enabled` in SMTP settings — graceful error if not configured
- Confirm dialog on button click to prevent accidental sends
- Each player gets a personalized email (not a group blast) — their opponent, their tee time, their flight

## "My Stats" Personal Player Page — BUILT (2026-06-04, daytime run #4)

### What was built
A personalized `/my-stats` page for any logged-in user whose account is linked to a player. Shows everything a player wants to know at a glance: handicap with trend sparkline, season points, W-T-L record, avg/best gross, team standing, dues status, upcoming next round, recent 5 rounds, handicap trend mini-chart, unread notification count, and quick navigation links.

### Feature details
- **Route:** `GET /my-stats` in new blueprint `routes/my_stats.py` — requires `login_required`; redirects to dashboard with flash message if `session['player_id']` is not set (not linked to a player)
- **Stat cards row:** Current Handicap (with sparkline), Season Points, Season Record (W-T-L), Avg Gross / Best Gross, Team Standing (rank / total), Dues status (paid ✅ or owed ⚠️)
- **Next Round card:** upcoming matchup week, date, opponent label, course/tee, tee time/starting hole, "View Schedule" + "Blank Card" action buttons
- **My Team card:** team label, partner name (linked to their profile), rank/pts summary, "Team Profile" and "Compare with Partner" buttons
- **Handicap Trend mini-chart:** SVG polyline of last 10 handicap history entries with date axis labels (only shown with ≥2 history entries)
- **Recent Rounds table:** last 5 completed rounds with date, week, gross total, pts, Win/Tie/Loss chip, Scorecard link
- **Notifications shortcut:** unread count badge, link to notification center
- **Quick Links grid:** Standings, Schedule, Individual Stats, Awards, Compare Players, Dashboard
- **Nav link:** "My Stats" link added to main nav — only shown when `session.get('player_id')` is truthy
- **Dashboard tile:** "👤 My Stats" tile added — only shown when `session.get('player_id')` is truthy

### Files changed
- `routes/my_stats.py` — new blueprint; single `index()` route; inline `_get_player_handicap()` helper (with adjustment support)
- `templates/my_stats/index.html` — new template; stat grid, two-column layout (upcoming/team/chart left, rounds/notif/links right)
- `static/css/main.css` — appended `.mys-*` styles (~90 lines); gradient stat cards, sparkline, outcome chips, quick-link grid
- `templates/base.html` — added "My Stats" nav-page-link (guarded by `session.get('player_id')`)
- `templates/dashboard.html` — added "👤 My Stats" dash-card tile (guarded by `session.get('player_id')`)
- `app.py` — added `from routes.my_stats import bp as my_stats_bp` + `app.register_blueprint(my_stats_bp)`

### Key decisions
- Page is entirely read-only; no writes
- All DB queries wrapped in try/except where tables may be absent (dues, handicap_adjustments, notification_reads)
- Graceful fallback: if no season, no team, no rounds — each section shows empty state rather than crashing
- Opponent label for upcoming matchup uses `team_name` with `p1_last / p2_last` fallback
- sparkline_pts built for last 10 HCP history entries — same algorithm as player profile page
- Dues status shows only if `league_settings` has dues_amount configured
- No DB schema changes required

### No DB migration needed

## Player Self-Registration — BUILT (2026-06-04, daytime run #3)

### What was built
Commissioners can enable a public join link for their league. Players visit the link, fill out a signup form, and their request goes into an admin approval queue. Approving a request instantly creates the player record.

### Feature details
- **DB migration:** `migrate_player_registrations.py` — creates `player_registrations` table + adds `reg_enabled` and `reg_welcome_msg` columns to `leagues`. **Already applied to DB.**
- **Public join form:** `GET/POST /join/<league_id>` — standalone HTML page (no base.html, no auth). Shows league name, optional welcome message, fields for first/last name, email, starting handicap, and a message to the commissioner. Returns a "thank you" page on submission.
- **Registration closed / not found:** Graceful standalone pages for unknown league IDs and disabled registration.
- **Admin settings:** `GET/POST /admin/registration-settings` — toggle registration on/off, set welcome message, display shareable join URL with copy button.
- **Admin approval queue:** `GET /admin/registrations` — table of all pending requests (name, email, handicap, message, timestamp) with Approve/Reject actions. Recent reviewed requests shown below.
- **Approve action:** `POST /admin/registrations/<id>/approve` — creates player record in `players` table, links `player_id` back to registration row, sets status=approved.
- **Reject action:** `POST /admin/registrations/<id>/reject` — sets status=rejected.
- **Admin panel badge:** "👋 Registrations" button added to admin quick-actions bar; shows pending count badge when requests are waiting.
- **Context processor:** `pending_reg_count` added to global nav context (graceful, 0 if table absent).

### Files changed
- `migrate_player_registrations.py` — new migration script (already applied to DB)
- `routes/player_reg.py` — new blueprint; `join()`, `reg_settings()`, `admin_queue()`, `approve()`, `reject()` routes; `pending_reg_count()` helper
- `templates/registration/join.html` — standalone public join form
- `templates/registration/submitted.html` — thank-you page after submission
- `templates/registration/closed.html` — shown when registration is disabled
- `templates/registration/not_found.html` — shown for unknown league IDs
- `templates/registration/admin_settings.html` — admin enable/disable + welcome message + join URL card
- `templates/registration/admin_queue.html` — pending + recently reviewed requests table
- `app.py` — added `player_reg_bp` import + registration; `pending_reg_count` added to context processor; also fixed truncation (switch_season + return app + __main__ block restored); fixed email_config.py truncation (except Exception as e completion)
- `templates/admin/season.html` — added "👋 Registrations" button with badge to quick-actions bar
- `static/css/main.css` — appended `.reg-*` styles

### Key decisions
- Join form is fully public (no login, no league password) — low friction for new player signups
- Registration disabled by default (`reg_enabled=0`) — admin must explicitly turn it on
- Approval creates player with `active=1` and `handicap_index = starting_handicap` — ready to be added to a team immediately
- `pending_reg_count()` is graceful (try/except) — admin badge shows 0 if migration not yet run
- No email notification on new request (keep it simple; admin checks the queue)
- Join URL uses league_id directly (not a slug) — always works, even before public page slug is set

### DB migration
Already applied. Schema: `player_registrations (reg_id, league_id, first_name, last_name, email, starting_handicap, message, status, created_at, reviewed_at, reviewed_by_user_id, player_id)`

### Also fixed this session
- `routes/email_config.py` — truncated at line 724 (`except Exce`); completed to `except Exception as e:` + restored closing `except Exception: pass` for outer try block
- `app.py` — truncated at line 270 (missing `switch_season` route + `return app` + `app = create_app()` + `__main__`); restored

## Week Preview Page — BUILT (2026-06-04, daytime run #2)

### What was built
A pre-round information page at `/schedule/<season_id>/week/<n>/preview` giving players and admins a rich look at an upcoming week before teeing off.

### Feature details
- **Route:** `GET /schedule/<season_id>/week/<n>/preview` appended to `routes/schedule.py`
- **Page contents:**
  - Course banner: course name, tee badge (color-coded), slope/rating
  - Par + Handicap Index header rows (same holes table as blank scorecard)
  - Per-matchup cards for every non-bye matchup that week:
    - **Header bar:** Team 1 name+number vs Team 2 name+number, tee time, starting hole
    - **H2H record bar:** season head-to-head W–T–L record between these two teams, or "First meeting this season"
    - **A Flight + B Flight cards** side by side:
      - Player name (linked to profile), handicap badge
      - Recent form dots (last 5 results: W=green, T=amber, L=red)
      - Stroke differential center: "N strokes →" with amber badge showing who gives how many
      - Hole-by-hole stroke allocation table (● = 1 stroke, ●● = 2 strokes, green highlight on holes receiving strokes)
  - **Action bar:** Blank Card and Tee Sheet links per matchup
- **Button:** "🎯 Preview" btn-secondary added to week header in `schedule/index.html` — shown for weeks with any non-completed matchups (alongside Recap/Tee Sheet/Live buttons)

### Files changed
- `routes/schedule.py` — `week_preview()` route appended (~120 lines); uses existing `_build_team_info()`, `_calc_strokes()`, `_get_player_handicap()` helpers; adds `_recent_form()` and `_h2h_record()` inner functions
- `templates/schedule/week_preview.html` — new template (~220 lines)
- `templates/schedule/index.html` — added `week_has_upcoming` check + "🎯 Preview" button in week header
- `static/css/main.css` — appended `.wp-*` styles (~140 lines)

### Key decisions
- Recent form looks back N=5 rounds; `overall_point_won >= 1.5` = Win, `>= 0.9` = Tie, else Loss (same thresholds as rest of app)
- H2H uses matchup-level query: compares total team pts per completed matchup, counts wins/ties/losses
- Stroke diff = int(hdcp_a) – int(hdcp_b); positive = A gives strokes to B; shown in amber badge with arrow direction
- `week_has_upcoming` uses Jinja2's `selectattr('status', 'ne', 'completed')` — Preview shown even for partially-played weeks
- No DB schema changes — pure route + template addition

## Handicap Committee Adjustment — BUILT (2026-06-04, daytime run)

### What was built
Admins can apply a +/− stroke committee adjustment to any player's handicap. The adjustment stacks on top of the computed handicap index and is applied transparently everywhere handicaps are used: score entry, standings scorecards, and the player profile.

### Feature details
- **Migration:** `migrate_handicap_adjustments.py` — creates `handicap_adjustments (adj_id, player_id, league_id, adjustment REAL, reason TEXT, created_at, created_by_user_id)` with `UNIQUE(player_id, league_id)` — one active adjustment per player per league. **Needs manual run.**
- **Route:** `POST /players/<id>/set-adjustment` in `routes/players.py` (admin only)
  - `action=save`: upserts adjustment via `INSERT … ON CONFLICT DO UPDATE`; clears if value=0
  - `action=remove`: deletes the row
  - Graceful: if table not yet migrated, flashes a message to run the migration
- **Player profile GET:** queries `handicap_adjustments` table (graceful try/except if absent); passes `committee_adjustment` dict to template
- **Player profile UI:**
  - "Current Handicap" stat card shows a colored badge (amber +N / blue −N) when adjustment is active; label changes to "w/ committee adj."
  - Admin section "Committee Handicap Adjustment" at bottom of profile:
    - Active adjustment banner (reason, date set, Remove button)
    - Form: adjustment value (step 0.5), reason text (200 chars max), Save button
- **Score entry integration:** `get_player_handicap(db, player_id, league_id=None)` in `scores.py` now adds adjustment; `_build_player_list` signature updated to accept and pass `league_id`; both call sites pass `session.get('league_id')`
- **Standings integration:** `_get_player_handicap(db, player_id, league_id=None)` in `standings.py` updated the same way; both call sites in `divisions()` and `scorecards()` pass `league_id`

### Files changed
- `migrate_handicap_adjustments.py` — new migration script (needs manual run)
- `routes/players.py` — `profile()` queries adjustment + passes to template; `set_adjustment()` route appended
- `routes/scores.py` — `get_player_handicap()` updated with `league_id` param + adjustment lookup; `_build_player_list()` updated; call sites updated
- `routes/standings.py` — `_get_player_handicap()` updated with `league_id` param + adjustment lookup; 2 call sites updated
- `templates/players/profile.html` — stat card shows adjustment badge; admin section added at bottom
- `static/css/main.css` — `.adj-*` styles appended (~65 lines)

### DB migration needed
- `migrate_handicap_adjustments.py` — run manually: `cd C:\Users\zowen\Documents\Claude\Projects\Golf League WebApp\app && python migrate_handicap_adjustments.py`

### Key decisions
- One active adjustment per player per league (UNIQUE constraint) — simplest model, no history needed
- Adjustment is always additive: effective_handicap = computed_index + adjustment (positive = more strokes = higher handicap)
- `try/except` on all DB reads — app works before migration is run (adjustment silently = 0)
- Removing the adjustment deletes the row (no zero-value stale rows)
- Adjustment visible only to admins on the profile; other views just see the effective handicap as normal

## Blank Pre-Round Scorecard + Personalized Score Emails — BUILT (2026-06-04, daytime session)

### Feature 1: Blank Pre-Round Scorecard Print Page

- **Route:** `GET /schedule/<season_id>/week/<n>/matchup/<matchup_id>/blank-scorecard` in `routes/schedule.py`
- **Template:** `templates/schedule/blank_scorecard.html` — standalone print-optimized page (no base.html nav)
- **What it shows:** League name, season, week number, date, course/tee, tee time, starting hole; two separate flight tables (A and B); Par row, Hdcp Index row, Yardage row; one player row per player with handicap number and ● / ●● dots in each score cell corner showing handicap strokes; empty score cells; Total column; signature/attestation area at bottom
- **Graceful:** Works even when no course/tee is assigned (shows warning banner and blank 9-hole grid)
- **Button added:** "🖨 Blank Card" btn-link added to weekly schedule view for non-completed matchups — both admin row (next to Enter Scores) and member row (next to Submit Scores)
- **Helper:** `_calc_strokes(hdcp, holes)` added to schedule.py — wraps `strokes_on_hole` from scores.py
- **Print support:** "🖨 Print" button triggers `window.print()`; nav elements hidden via `@media print`

### Feature 2: Personalized Player Scorecard Emails

- **New function:** `send_player_scorecard_emails(db, league_id, week_label, player_summaries, scorecard_url=None)` appended to `routes/email_config.py`
- **What it sends:** When `email_on_round_posted` is enabled, sends a personalized email to each of the 4 players in the matchup (if they have an email address on file). Shows: gross total, net total, match points, opponent name/gross/pts, WIN/TIE/LOSS result in color, flight (A or B), link to scorecard
- **Subject line:** `[LeagueName] Your Week N Results — WIN (5 pts)` — personalized to each player
- **Triggered from:** `scores.py save()` route — builds `_player_summaries` list from existing `roles`, `gross`, `net`, `_name_map` dicts already available at save time; passes `url_for('scores.view', ..., _external=True)` as scorecard URL
- **Graceful:** entire block wrapped in try/except; skips players without email; no-op if email disabled

### Files changed
- `routes/schedule.py` — appended `_calc_strokes()` helper + `blank_scorecard()` route (~70 lines)
- `templates/schedule/blank_scorecard.html` — new standalone print template (~290 lines)
- `templates/schedule/index.html` — added "🖨 Blank Card" btn-link in both admin and member action rows for non-completed matchups
- `routes/email_config.py` — appended `send_player_scorecard_emails()` function (~65 lines)
- `routes/scores.py` — replaced simple `send_round_posted_email` call with extended block that also builds `_player_summaries` and calls `send_player_scorecard_emails`

### Technical note
- scores.py Linux mount is stale (35986 bytes / 885 lines); Windows file is correct (verified via Read tool). Flask on Windows reads the Windows file directly — no functional impact. Known mount-sync issue.
- No DB schema changes needed for either feature.

Last updated: 2026-06-04 (automated bug fix run #3)

## Bug Fixes — 2026-06-04 (automated off-peak run #3)

### Fixed: `absence_log()` crashes on every visit — 3 bugs in one route
- **Bug 1 (crash):** Query did `LEFT JOIN schedule_weeks w ON m.week_id = w.week_id`. Neither the `schedule_weeks` table nor the `week_id` column on `matchups` exist — every visit to `/admin/season/<id>/absences` crashed with `OperationalError: no such table: schedule_weeks`.
- **Bug 2 (Jinja2 UndefinedError):** Route passed `absences=absences` but template iterates `absence_rows`. Would have caused `UndefinedError` even if the SQL ran.
- **Bug 3 (wrong column names):** Route selected `p.first_name AS player_first` but template uses `row['absent_first']`/`row['absent_last']`. Also template used `row['round_date']`/`row['round_number']` which weren't selected at all. Template also uses `all_seasons` for the season switcher dropdown — not passed.
- **Fix:** Rewrote the query to JOIN `rounds` instead of `schedule_weeks`; use `m.week_number` and `m.scheduled_date` from `matchups` directly; alias `p.first_name AS absent_first`, `p.last_name AS absent_last`; SELECT `r.round_number`, `r.round_date`; order by `m.week_number DESC NULLS LAST`. Added `all_seasons` query and passed `absence_rows` + `all_seasons` to template.

### Fixed: Unguarded `int()` in `playoffs.py generate_bracket()`
- `int(request.form.get('playoff_teams', settings['playoff_teams']))` had no try/except. A non-numeric form value would crash with ValueError when generating a bracket.
- **Fix:** Wrapped in try/except ValueError/TypeError, falls back to `int(settings['playoff_teams'])`.

### Fixed: Unguarded `int()` in `email_config.py save()`
- `int(request.form.get('smtp_port') or 587)` had no try/except. A non-numeric SMTP port entry would crash with ValueError when saving email settings.
- **Fix:** Wrapped in try/except ValueError/TypeError, defaults to 587.

### Files changed
- `routes/admin.py` — rewrote `absence_log()` query + return (schedule_weeks → matchups/rounds; column aliases fixed; all_seasons added)
- `routes/playoffs.py` — wrapped `playoff_teams` int() in try/except
- `routes/email_config.py` — wrapped `smtp_port` int() in try/except

## Bug Fixes — 2026-06-04 (automated off-peak run #2)

### Fixed: `awards()` route crashes on every visit — `matchups` has no `league_id` column
- All 7 SQL queries in `routes/standings.py awards()` used `AND m.league_id=?` where `m` is the `matchups` table. The `matchups` table has no `league_id` column, so every visit to `/standings/<id>/awards` crashed with `OperationalError: table matchups has no column named league_id`.
- **Fix:** Removed `AND m.league_id=?` and its corresponding parameter from all 7 queries. Filtering by `m.season_id=?` is sufficient — the season_id is already validated to belong to the current league at the top of the route.
- **Queries fixed:** pts_rows, eagle_rows, birdie_rows, low_round_rows, record_rows, streak_data, all_sc.

### Fixed: `starting_hole` unguarded `int()` in `schedule.py edit_matchup`
- `int(request.form.get('starting_hole', 1))` in the `edit_matchup()` POST handler had no try/except. A non-numeric form value (e.g., from a bad HTTP request) would crash with `ValueError`.
- **Fix:** Wrapped in try/except, defaults to 1 on invalid input.

### Files changed
- `routes/standings.py` — removed `AND m.league_id=?` + param from 7 queries in `awards()`
- `routes/schedule.py` — wrapped `starting_hole` int conversion in try/except in `edit_matchup()`

## Bug Fixes — 2026-06-04 (automated off-peak run)

### Fixed: `create_league_event` not imported in `routes/scores.py`
- `create_league_event` was called in two places (sub_assigned event, round_completed event) but was never imported — both calls were silently swallowed by `try/except`, so the activity feed never fired for any score-related action.
- **Fix:** Added `from routes.notifications import create_league_event` to the imports in `routes/scores.py`.

### Fixed: `round_row` None crash in `scores.py view()`
- In `view(matchup_id)`, if a matchup is marked `completed` but no matching row exists in the `rounds` table, `round_row` is `None`. Lines 750–751 had correct `if round_row else` guards, but the `scorecards` query on line 727 used `round_row['round_id']` unconditionally — a guaranteed crash in that edge case.
- **Fix:** Added an explicit `if not round_row` guard immediately after the `round_row` fetch, flashing an error and redirecting to seasons index.

### Fixed: `days_between` unguarded `int()` in `schedule.py` generate route
- `int(request.form.get('days_between', 7))` had no try/except. A non-numeric form value would crash with `ValueError`.
- **Fix:** Wrapped in try/except, defaults to 7 on invalid input.

### Files changed
- `routes/scores.py` — added `create_league_event` import; added `round_row` None guard in `view()`
- `routes/schedule.py` — wrapped `days_between` int conversion in try/except

## Season Carry-Over Handicap Seeding — BUILT (2026-06-03, session 36)

### What was built
- **Route:** `GET/POST /admin/season/<id>/seed-handicaps` in `routes/admin.py`
- **GET:** Preview page — table of all players in the season with current starting_handicap, their latest computed handicap_index from any season, whether each will change, and the source date
- **POST:** Applies seeding — updates `players.starting_handicap` for each player who has computed history; skips players with no handicap_history; redirects to season detail with flash summary
- **Template:** `templates/admin/seed_handicaps.html` — explainer card, full player preview table with UPDATE/No change/No history chips, highlighted changed rows, confirm button (only shown if changes exist)
- **"🌱 Seed Handicaps" button** added to `templates/seasons/detail.html` header actions (admin only), alongside the existing "↺ Recalc Handicaps" button
- **CSS:** `.seed-*` styles appended to main.css

### Key decisions
- Seed source: latest `handicap_history` row per player (any season, `ORDER BY calculated_date DESC`) — gives their most recently computed index regardless of when it was calculated
- Falls back gracefully: players with no history show "No history — no change" chip and are skipped
- No DB schema changes — updates existing `players.starting_handicap` column
- Preview-first UX — admin sees exactly what will change before confirming
- Row highlighted amber in preview if the value will actually change (|proposed - current| ≥ 0.05)

### Files changed
- `routes/admin.py` — appended `seed_handicaps()` route (~65 lines)
- `templates/admin/seed_handicaps.html` — new template
- `templates/seasons/detail.html` — added "🌱 Seed Handicaps" button in header actions
- `static/css/main.css` — appended `.seed-*` styles (~45 lines)

### No DB migration needed

## Bulk Tee-Time Setter — BUILT (2026-06-03, session 35)

### What was built
- **Per-matchup tee time + starting hole editor** added to `GET/POST /admin/season/<id>/week/<num>/edit`
- Admin week editor now shows all non-bye matchups for the week in a table with:
  - Tee time text input per matchup (pre-filled from DB)
  - Starting hole dropdown (Hole 1–18) per matchup (pre-filled from DB)
  - **"Apply to All" bar**: type a tee time + select a hole once, click Apply → fills all rows instantly
  - **"Clear All"** button: blanks tee times + resets holes to 1
- Form POSTs per-matchup values as `tee_time_<matchup_id>` and `hole_<matchup_id>`
- Section hidden if week has no non-bye matchups (e.g. all-bye week)
- No new DB schema needed — uses existing `matchups.tee_time` and `matchups.starting_hole`

### Files changed
- `routes/admin.py` — `edit_week()` POST: saves per-matchup tee times + starting holes; GET: queries `week_matchups` with team labels via JOIN on teams/players
- `templates/admin/edit_week.html` — added "Tee Times & Starting Holes" section below commissioner note; Apply to All bar + matchup table; `applyToAll()` + `clearAll()` JS functions
- `static/css/main.css` — appended `.ew-divider`, `.ew-tee-section`, `.ew-tee-heading`, `.ew-apply-all`, `.ew-apply-row`, `.ew-apply-label`, `.ew-bulk-input/select`, `.ew-tee-table`, `.ew-matchup-label`, `.ew-vs`, `.ew-tee-input`, `.ew-hole-select` styles

### Key decisions
- Team labels use `COALESCE(team_name, last_name || ' / ' || last_name)` — consistent with rest of app
- Matchups ordered by tee_time ASC NULLS LAST then matchup_id — matches tee sheet order
- Section uses same single POST form as week-level fields (date, course, etc.) — one Save button does everything
- No redirect to matchup edit needed — full week tee setup in one place

## CSV Data Export — BUILT (2026-06-03, session 34)

### What was built
- **4 CSV download routes** added to `routes/reports.py` (appended, no blueprint changes needed):
  - `GET /reports/<season_id>/export/standings` — team rank, pts, W–T–L, rounds
  - `GET /reports/<season_id>/export/scores` — every round per player: gross, net, pts, handicap, date, course, tee
  - `GET /reports/<season_id>/export/roster` — players with team, role, division, current & starting handicap
  - `GET /reports/<season_id>/export/schedule` — full schedule with scores, winner, and status per matchup
- **Export Data section** added to `templates/reports/index.html` — 4 export cards with icon, description, CSV badge
- **CSS** — `.export-grid`, `.export-card`, `.export-card__*`, `.export-badge`, `.reports-section-subtitle` styles appended to main.css
- **`_csv_response()` helper** — builds `text/csv` Flask Response with `Content-Disposition: attachment` header
- All exports scoped to league_id + season_id — no cross-league data leakage
- No DB schema changes required

### Files changed
- `routes/reports.py` — appended `_csv_response()` helper + 4 export routes (~200 lines); also fixed roster query to use `player_id` for handicap lookup
- `templates/reports/index.html` — added "📥 Export Data" section with 4 export cards before back-link
- `static/css/main.css` — appended `.export-*` and `.reports-section-subtitle` styles (~60 lines)

### Key decisions
- Uses Python stdlib `csv.DictWriter` + `io.StringIO` — no external dependencies
- `
` line terminators (RFC 4180 CSV standard)
- Score history groups by `scorecard_id` using SQL aggregates — one row per player per round
- Roster handicap uses `_get_player_handicap()` which checks handicap_history then falls back to starting_handicap
- Schedule export skips bye weeks (`is_bye` filter)
- Integer points displayed as int (not float) when value is whole number

## Player vs Player Comparison — BUILT (2026-06-03, session 33)

### What was built
- **Route:** `GET /players/compare?p1=<id>&p2=<id>` — side-by-side comparison of any two league players
- **Selector form:** dropdown for each player; redirects to same page with `?p1=&p2=` params
- **Header cards:** name, current handicap, total career rounds + pts for each player
- **H2H record banner:** W–T–L for each player when matched directly against each other (opposite teams, same role A vs A or B vs B)
- **Career Stats comparison rows:** Avg Gross, Best Round, Current HCP, Career Pts, Rounds — green winner highlight on the better value
- **Scoring Distribution:** side-by-side Eagle/Birdie/Par/Bogey/Dbl+ counts + percentages with bar charts (color-coded gold/green/blue/pink/red)
- **Handicap Trend chart:** canvas-based dual line chart (P1=blue, P2=red) with toggle legend — overlays both players' handicap history
- **Direct H2H Matchups table:** all rounds where they faced each other as opponents — pts per player, outcome chip (W/T/L), Scorecard link
- **Rounds as Partners table:** all rounds where they were on the same team — pts each, Scorecard link
- **Compare button** added to player profile page header (pre-fills P1)
- **Compare link** added to roster table admin actions (pre-fills P1)
- **"⚔️ Compare Players" dashboard tile** added to main dashboard

### Files changed
- `routes/players.py` — appended `compare()` route (~180 lines); 6 helper functions: `_get_player`, `_current_hcp`, `_hcp_history`, `_season_stats`, `_career_gross`, `_score_distribution`, `_shared_rounds`, `_h2h_records`, `_stats_from_gross`, `_hcp_chart`
- `templates/players/compare.html` — new template (~280 lines); selector bar, header grid, stat rows, distribution bars, canvas trend chart, H2H table, partners table
- `templates/players/profile.html` — added "⚔️ Compare" button in page-header-actions (pre-fills p1)
- `templates/players/roster.html` — added "Compare" btn-link in admin actions column (pre-fills p1)
- `templates/dashboard.html` — added "⚔️ Compare Players" dash tile
- `static/css/main.css` — appended `.cmp-*`, `.dist-*`, `.outcome-chip`, `.chip-*` styles (~120 lines)

### Key decisions
- H2H defined as: same matchup, opposite teams, same role (A vs A or B vs B) — avoids comparing A-player pts to B-player pts
- Partner rounds: same matchup, same team — useful for evaluating team chemistry
- `score_differential` column used for distribution (eagle/birdie/par/bogey/double) — already stored on hole_scores
- Career gross requires ≥9 holes played in the round (avoids partial rounds skewing avg/best)
- Winner highlighting uses green background on the better stat; lower gross/HCP = better, higher pts/rounds = better
- Canvas chart: both series share the same Y scale (combined min/max), so relative changes are visually comparable
- No DB schema changes needed — pure route + template addition

## Score Entry UX Enhancements — BUILT (2026-06-03, session 32)

### What was built
- **Handicap Stroke Indicators**: Small green dot(s) appear in the top-right corner of each score cell showing how many handicap strokes that player receives on that hole (● = 1 stroke, ●● = 2 strokes). Computed via existing `strokesOnHole()` function. Updates automatically when player tee selection changes. Rendered on page load for all players.
- **Keyboard Auto-Advance (Enter key)**: On desktop score entry, pressing Enter moves focus to the next player's cell on the same hole (column-major order). After the last player on a hole, jumps to the first player on the next hole. This matches natural scorecard filling order (fill all players on hole 1, then hole 2, etc.). Uses `select()` to pre-select the value for easy overwrite.

### Files changed
- `templates/scores/enter.html` — added `<span class="stroke-dot" id="sd_{{pid}}_{{hole}}">` to both team player blocks (replace_all); added `renderStrokeDots()` function + `buildInputOrder()` IIFE for keyboard nav; updated `updatePlayerTeeJS()` to call `renderStrokeDots()` after tee change
- `static/css/main.css` — added `position: relative` to `.sc-score-cell`; added `.stroke-dot` styles (absolute positioning, top-right corner, 6px green dots)

### Key decisions
- Stroke dots use `●` character at 6px / letter-spacing -1px so `●●` fits in a small corner
- Column-major order (all players on hole 1 first) is the natural scorecard entry pattern — matches how a scorer fills a paper card
- `window.renderStrokeDots` guard in `updatePlayerTeeJS` (defined before `renderStrokeDots`) is safe because tee changes only happen after page fully loads
- No backend changes needed — pure JS/CSS/HTML enhancement

## Player Nickname System — BUILT (2026-06-03, session 31)

### What was built
- **Migration:** `migrate_player_nicknames.py` — creates `player_nicknames` table (nickname_id, player_id, league_id, nickname, is_primary, created_at); needs manual run
- **Routes** (all in `routes/players.py`):
  - `POST /players/<id>/nicknames/add` — admin only; validates length (≤40), deduplicates case-insensitive; first nickname auto-becomes primary
  - `POST /players/<id>/nicknames/<nid>/delete` — admin only; if primary deleted, promotes next oldest
  - `POST /players/<id>/nicknames/<nid>/set-primary` — admin only; clears all is_primary then sets selected
- **Player profile** (`templates/players/profile.html`):
  - Primary nickname shown as badge next to player name in page header: `"Ziggy"`
  - "Nicknames & Aliases" section at bottom (admin): list of all nicknames with primary chip, Set Primary button, Remove button, and Add form
  - Members (non-admin): read-only list of nicknames if any exist
- **Roster page** (`templates/players/roster.html`): primary nickname shown inline after player name in the roster table link
- **Score entry** (`templates/scores/enter.html`): nickname badge shown next to player name in desktop header row (×2) and mobile player row (×2)
- **Score view** (`templates/scores/view.html`): nickname badge shown next to player name in scorecard rows
- **Helper** `_get_nickname_map(db, player_ids)` in `routes/scores.py` — graceful (returns all None if table absent); used in enter + view routes
- **Profile GET** updated: queries nicknames, passes `nicknames` list + `primary_nickname` str to template
- **Roster GET** updated: queries primary nicknames per player, passes `roster_nicknames` dict to template

### Files changed
- `routes/players.py` — roster() updated; profile() updated; 3 new routes appended (add_nickname, delete_nickname, set_primary_nickname)
- `routes/scores.py` — `_get_nickname_map()` helper added; enter() passes `nickname_map`; view() attaches `nickname` to each group entry
- `templates/players/profile.html` — nickname badge in header; full Nicknames section at bottom
- `templates/players/roster.html` — primary nickname badge inline in roster name link
- `templates/scores/enter.html` — nickname badge in 2 desktop + 2 mobile player name spots
- `templates/scores/view.html` — nickname badge in player scorecard row
- `static/css/main.css` — `.nick-display-badge`, `.nick-section-hint`, `.nick-list`, `.nick-item`, `.nick-item--primary`, `.nick-label`, `.nick-primary-chip`, `.nick-actions`, `.nick-btn`, `.nick-add-form`, `.nick-input`, `.nick-empty`, `.nick-score-badge` styles (~90 lines)
- `migrate_player_nicknames.py` — migration script (needs manual run)

### Key decisions
- First nickname added auto-becomes primary — no extra click needed for single-nickname case
- Deleting the primary auto-promotes next oldest — list never has no primary when nicknames exist
- Table absence handled gracefully (sqlite_master check) so app works before migration is run
- `_get_nickname_map` is in scores.py (not a shared util) to keep dependency simple
- Nicknames visible to all users (read-only for non-admins) — transparency about who goes by what

### DB migration needed
- `migrate_player_nicknames.py` — run manually: `cd C:\Users\zowen\Documents\Claude\Projects\Golf League WebApp\app && python migrate_player_nicknames.py`

## REST API Layer — BUILT (2026-06-03, session 30)

### What was built
- **Blueprint:** `routes/api.py` — registered at `/api/v1/`
- **Auth:** `X-Api-Key` header or `?api_key=` query param; key stored as `leagues.api_key` (plaintext, prefixed `bglk_`)
- **Endpoints:**
  - `GET /api/v1/leagues/me` — league info + season list
  - `GET /api/v1/seasons` — all seasons for the league
  - `GET /api/v1/seasons/<id>/standings` — team standings (rank, pts, rounds played)
  - `GET /api/v1/seasons/<id>/schedule` — full schedule grouped by week with matchup details
  - `GET /api/v1/seasons/<id>/teams` — teams + player names + division
  - `GET /api/v1/players` — full roster (name, email, handicap, active)
  - `GET /api/v1/matchups/<id>/scores` — scorecard with per-hole gross/net/pts
  - `GET /api/v1/seasons/<id>/weeks/<n>/live` — live leaderboard data (same data as session 29 JSON endpoint)
  - `POST /api/v1/keys/regenerate` — rotate API key via API itself
- **Admin UI:** `GET/POST /admin/api-settings` — generate/regenerate/revoke key; quick-start curl examples; endpoints reference table
- **"🔌 API Settings" button** added to Admin Panel quick-actions bar
- **Migration:** `migrate_api_key.py` — adds `api_key TEXT DEFAULT NULL` to `leagues`; **needs to be run manually**

### Files changed
- `routes/api.py` — new blueprint (~220 lines)
- `routes/admin.py` — appended `api_settings()` route (~55 lines)
- `templates/admin/api_settings.html` — new template; key display + copy btn + generate/revoke forms + endpoints table + curl examples
- `templates/admin/season.html` — added "🔌 API Settings" to quick-actions
- `static/css/main.css` — appended `.api-settings-*`, `.api-key-*`, `.api-endpoints-table`, `.api-method-chip` styles (~50 lines)
- `app.py` — added `from routes.api import bp as api_bp` + `register_blueprint(api_bp)`
- `migrate_api_key.py` — migration script (needs manual run)

### Key decisions
- API key prefixed with `bglk_` for easy identification in logs/secrets managers
- `api_key_required` decorator uses `g.api_league` / `g.api_league_id` — clean, no session dependency
- All endpoints scope data to the authenticated league — no cross-league data leakage possible
- `POST /api/v1/keys/regenerate` also requires a valid (current) API key to rotate — prevents unauthenticated rotation
- CSRF exemption not needed — API routes use no CSRF token (JSON API, no session cookies required)
- Live week endpoint returns same data shape as the existing live_leaderboard_data JSON route — mobile app can use either

### DB migration needed
- `migrate_api_key.py` — run manually: `cd C:\Users\zowen\Documents\Claude\Projects\Golf League WebApp\app && python migrate_api_key.py`

## Live Leaderboard — BUILT (2026-06-03, session 29)

### What was built
- **Route:** `GET /schedule/<season_id>/week/<week_num>/live` — full live leaderboard page
- **JSON API:** `GET /schedule/<season_id>/week/<week_num>/live-data` — AJAX data endpoint (returns same dict as `_build_live_matchup_data`)
- **Page features:**
  - 🔴 LIVE / ✅ Final / ⏳ Waiting badge in header based on completion state
  - Progress bar (X / N matchups complete)
  - Matchup cards: team names, tee time, starting hole, status chip, Scorecard/Enter Scores link
  - Completed matchups: per-player pts (color-coded high/mid/low), gross score, win/loss score display with green winner highlighting
  - Incomplete matchups: show team names and "vs" placeholder
  - Running standings table (prior weeks + this week's pts as they complete)
  - Auto-refresh countdown bar: refreshes every 60s if any matchup still pending; stops when all done
  - Manual "↻ Refresh" button + "Full Week Recap" link
- **`_build_live_matchup_data()`** helper: builds all data server-side; SQL uses `NULLS LAST` for tee_time ordering; pulls gross totals via JOIN from hole_scores

### Files changed
- `routes/schedule.py` — appended `_build_live_matchup_data()`, `live_leaderboard()`, `live_leaderboard_data()` (~150 lines)
- `templates/schedule/live_leaderboard.html` — new template; two-column grid layout (matchups left, standings + refresh right)
- `templates/schedule/index.html` — added "🔴 Live" button to weekly schedule header (always visible, not just for completed weeks)
- `static/css/main.css` — appended `.live-*`, `.score-win/loss/tie`, `.pts-high/mid/low`, `.live-leaderboard-btn` styles (~120 lines)

### Key decisions
- Auto-refresh uses `requestAnimationFrame` countdown + `fetch` to JSON endpoint; full page reload on response (simpler than DOM-diffing matchup cards)
- Refresh stops (refresh_secs=0) when all matchups are completed — no wasted polling
- "🔴 Live" button visible on all weeks (not just current) — useful for reviewing as a replay too
- `jsonify` imported inline in the data route (avoids adding to top-level import line)

## PWA — Progressive Web App — BUILT (2026-06-03, session 28)

### What was built
- **manifest.json** at `/static/manifest.json` — app name, short_name, theme color (#2d6a4f), standalone display, icons, shortcuts (Schedule + Standings)
- **App icons** — 192×192, 512×512 PNGs + 180×180 apple-touch-icon in `/static/icons/`; dark-green background with white golf flag emblem
- **Service worker** at `/static/sw.js` (served via `/sw.js` route with `Service-Worker-Allowed: /` header):
  - Pre-caches static assets (CSS, JS, manifest, icons, offline page) on install
  - Cache-first for `/static/` assets
  - Network-first for `/schedule`, `/standings`, `/players` pages — caches successful responses for offline use
  - Falls back to `/offline` page when network fails and page not cached
  - Skips caching admin, score-entry, auth routes (always need fresh data)
  - Cleans up old caches on activate
- **Offline fallback page** at `/offline` route + `templates/offline.html` — standalone (no base.html); shows cached page links (Schedule/Standings/Players), auto-redirects to `/` when connection restored
- **base.html** updated with: `<link rel="manifest">`, `theme-color` meta, Apple PWA meta tags (`apple-mobile-web-app-capable`, status bar, title), `apple-touch-icon` link, SW registration script

### Also fixed in this session
- **app.py was truncated** (pre-existing) — completed the truncated `inject_nav_context` return dict + `switch_season` route + `return app` + `app = create_app()` + `__main__` block

### Files changed
- `static/manifest.json` — new PWA manifest
- `static/sw.js` — new service worker
- `static/icons/icon-192.png` — new app icon
- `static/icons/icon-512.png` — new app icon
- `static/icons/apple-touch-icon.png` — new Apple touch icon
- `templates/offline.html` — new offline fallback page (standalone, no base.html)
- `templates/base.html` — added manifest link, PWA meta tags, SW registration script
- `app.py` — added `/offline` + `/sw.js` routes; fixed truncation; added `render_template`, `make_response`, `send_from_directory` to Flask import

### Key decisions
- SW served from `/sw.js` (not `/static/sw.js`) so its scope is `/` — service workers can only control pages within their scope
- `Cache-Control: no-cache` on `/sw.js` so browsers always check for SW updates
- Score entry, admin, auth routes explicitly excluded from SW caching — stale data there would be harmful
- Offline page auto-detects `online` event and redirects to `/` when connection restored
- PWA shortcuts point to `/schedule` and `/standings` — the two most-visited pages

## Public League Page — BUILT (2026-06-02, session 27)

### What was built
- Route: `GET /public/<slug>` — no auth required; looks up league by `public_slug` and `public_enabled=1`
- Admin settings: `GET/POST /admin/public-page` — toggle enabled, set slug, show embed code
- **Public page shows** (standalone HTML, no base.html):
  - Current season standings: position, team label, total points, rounds played
  - Most recent completed week's results: team vs team, pts each, winner bolded
  - Upcoming 3 weeks of schedule: week number, date, matchups, tee times
- **Admin page** (extends base.html):
  - Enable/disable toggle with current live URL displayed
  - Slug input with auto-slugify on save; uniqueness check across leagues
  - "What's shown" explainer + privacy note (no player names/handicaps shown publicly)
  - Embed iframe snippet (click-to-select) when enabled
- "🌐 Public Page" quick-action button added to Admin Panel

### DB migration
- `migrate_public_page.py` — adds `public_enabled INTEGER DEFAULT 0` and `public_slug TEXT DEFAULT NULL` to `leagues`
- Migration already applied to current DB

### Files changed
- `routes/public_view.py` — new blueprint; `public_page()`, `admin_settings()` routes; `_slugify()`, `_get_league_by_slug()`, `_current_season()`, `_standings()`, `_upcoming_weeks()`, `_recent_results()` helpers
- `templates/public/index.html` — standalone public page (no base.html); standings table, recent results, upcoming schedule; fully self-contained CSS
- `templates/public/admin_settings.html` — admin config page; extends base.html
- `templates/public/not_found.html` — standalone 404 page for unknown/disabled slugs
- `app.py` — added import + `register_blueprint(public_view_bp)`
- `templates/admin/season.html` — added "🌐 Public Page" to quick-actions bar
- `migrate_public_page.py` — migration script (already applied)

### Key decisions
- Public page is fully standalone HTML (no base.html, no nav, no login walls) — safe for iframe embedding
- Individual player names are NOT exposed on the public page — only team labels (nickname or "LastName / LastName")
- Recent results computed via per-matchup `SUM(total_points)` from `match_results` — same source as standings
- Slug uniqueness enforced per league at save time; auto-generated from league name if blank
- `public_enabled=0` by default — admin must explicitly enable

## Season Awards Page — BUILT (2026-06-02, session 26)

### What was built
- Route: `GET /standings/<season_id>/awards` in `routes/standings.py`
- Template: `templates/standings/awards.html`
- **7 auto-computed award categories** (no DB schema change):
  - 🏆 Points Leader — SUM(total_points) from match_results
  - 🐦 Birdie Machine — COUNT birdies (score_differential = -1) from hole_scores
  - 🦅 Eagle Eye — COUNT eagles (score_differential <= -2) from hole_scores
  - 💪 Best Match Record — W–T–L from overall_point_won in match_results
  - ⛳ Low Round — lowest single gross SUM(gross_score) from hole_scores, min 9 holes
  - 🔥 Hot Streak — longest consecutive wins computed in Python from ordered match_results
  - 📈 Most Improved — first vs last handicap_at_time_of_play in season (min 3 rounds)
- Top 5 shown per award with medal emoji (🥇🥈🥉) and colored left border
- Each name links to player profile page
- **Awards tab added to all 7 standings subnavs** (index, scorecards, weekly, allplay, divisions, individual, trend)
- Score entry UX: added `inputmode="numeric"` + `autocomplete="off"` to desktop score inputs (was already on mobile)

### Files changed
- `routes/standings.py` — appended `awards()` route (~120 lines)
- `templates/standings/awards.html` — new template
- `templates/standings/index.html` — added Awards tab
- `templates/standings/scorecards.html` — added Awards tab
- `templates/standings/weekly.html` — added Awards tab
- `templates/standings/allplay.html` — added Awards tab
- `templates/standings/divisions.html` — added Awards tab
- `templates/standings/individual.html` — added Awards tab
- `templates/standings/trend.html` — added Awards tab
- `templates/scores/enter.html` — desktop score inputs now have `inputmode="numeric"`
- `static/css/main.css` — appended `.awards-*`, `.award-*` styles (~65 lines)

### Key decisions
- All 7 award categories computed from existing tables — zero schema changes
- Hot Streak uses Python defaultdict + sequential scan of results ordered by week_number
- Most Improved requires ≥3 rounds to filter noise; compares first vs last handicap_at_time_of_play
- Low Round min 9 holes played to filter partial/incomplete rounds
- Best Record min 3 rounds to exclude single-round outliers
- Award card grid uses CSS `auto-fill minmax(340px, 1fr)` — responsive 1–3 columns

## Team Profile Page + Schedule Fixes — BUILT (2026-06-01, session 25)

### What was fixed
- **Truncated yearly schedule template** (`templates/schedule/index.html` was cut off mid-tbody at line 211) — rewrote the complete yearly view with proper tbody rows, type badges, group columns, and Detail/Recap action links per row
- **Truncated schedule.py** — `week_summary` route's `render_template` call was cut off at line 914; completed missing args: `standings`, `week_pts_map`, `prev_week`, `next_week`, `season_id`
- **`_build_yearly_rows`** — added `has_completed` flag to each row so the template can conditionally show the Recap link

### Team Profile Page — new feature
- Route: `GET /teams/<team_id>` in `routes/teams.py`
- Template: `templates/teams/profile.html`
- **Summary bar**: total matches, W–T–L record, total points, standings position (with medal for top 3), recent form dots (last 5 matches, color-coded W/T/L)
- **Players card**: per-player stats — rounds, W–T–L, avg gross, best round, birdies, eagles; linked to player profile
- **H2H breakdown table**: vs each opponent — W–T–L, pts for, pts against; color-coded record
- **Match Results table**: every matchup this season — week, date, opponent (linked), score, outcome badge, Scorecard link
- **Links added**: standings/index.html team names → team profile; seasons/detail.html team names → team profile

### Files changed
- `routes/teams.py` — appended `profile()` route (~150 lines)
- `templates/teams/profile.html` — new template
- `templates/schedule/index.html` — rewrote (fixed truncation + added Recap links in yearly view)
- `routes/schedule.py` — fixed `_build_yearly_rows` (added `has_completed`); completed truncated `week_summary` render_template call
- `templates/standings/index.html` — team name now a link to team profile
- `templates/seasons/detail.html` — team name now a link to team profile
- `static/css/main.css` — appended `.tp-*` styles (~70 lines) + `.team-profile-link`

### Key decisions
- No new DB schema — all data from existing `match_results`, `scorecards`, `hole_scores`, `matchups`
- H2H aggregated in Python from match_results loop (no extra SQL)
- `has_completed` in yearly rows checked against matchup `status` field already in the query
- Team label = `team_name` OR `p1_last / p2_last` fallback (consistent with rest of app)

## League Forum / Message Board — BUILT (2026-06-01, session 24)

Full member-facing discussion forum for the league, with admin moderation.

### What it does
- Topic list at `/forum` — paginated (20/page), pinned topics float to top, locked topics shown with 🔒
- Each row shows: title, author, date, last reply info, reply count
- New topic form at `/forum/new` — title + body; author name pulled from session user
- Topic view at `/forum/<id>` — shows original post + all replies chronologically; reply form at bottom
- Reply posting: `POST /forum/<id>/reply` — locked topics reject non-admin replies
- Admin controls on topic view: Pin/Unpin, Lock/Unlock, Delete topic (with confirm dialog)
- Admin can delete individual replies via 🗑 button inline on each reply
- "Forum" link added to main nav and "💬 Forum" dashboard tile added

### DB schema
- `forum_topics`: topic_id, league_id, title, body, author_id, author_name, pinned, locked, reply_count, created_at, updated_at
- `forum_replies`: reply_id, topic_id, league_id, body, author_id, author_name, created_at; ON DELETE CASCADE from topic

### Files changed
- `routes/forum.py` — new blueprint; 9 routes (index, new_topic, view_topic, reply, delete_topic, toggle_pin, toggle_lock, delete_reply)
- `templates/forum/index.html` — topic list with pinned styling, reply counts, pagination
- `templates/forum/new_topic.html` — create topic form
- `templates/forum/topic.html` — full thread view + reply form + admin controls
- `app.py` — registered `forum_bp` (import + register_blueprint)
- `templates/base.html` — added "Forum" to nav-links
- `templates/dashboard.html` — added "💬 Forum" dash tile
- `static/css/main.css` — appended `.forum-*` styles (~50 lines)
- `migrate_forum.py` — migration script (already applied to DB)

### Key decisions
- `_author_name()` helper: checks session for user_name/display_name, falls back to users table lookup, then "League Member"
- `reply_count` denormalized on topic for fast list display; decrements on reply delete with `MAX(0,...)`
- Pinned rows get subtle yellow background (`--pin-bg`); locked topics shown with opacity
- Admin moderation available to `league_admin` role only
- No new DB migration needed at runtime — tables created via migrate_forum.py (already run)

## Dashboard League Activity Feed — BUILT (2026-06-01, session 23)

Unified chronological activity timeline on the dashboard showing league events + announcements.

### What it does
- New "League Activity" section on the dashboard (below existing activity columns)
- Pulls from `league_events` table (round_completed, sub_assigned, etc.) and `notifications` (announcements)
- Merges and sorts by timestamp descending; shows most recent 15 items
- Each item shows: type icon (🏌️ round, 📢 announcement, 🔄 sub, etc.), message, type chip (color-coded), relative timestamp ("2h ago", "Yesterday", "3 days ago"), and "View →" link when applicable
- round_completed events link to the scorecard (`scores.view`)
- announcement items link to the announcements page
- Empty state shown when no activity yet ("📭 No recent league activity...")
- "View Notifications →" link in header goes to full notifications feed
- `league_events` table and `create_league_event()` already in place (fires on score save + announcements); feed will auto-populate as league plays rounds

### Files changed
- `routes/main.py` — added `activity_feed` query (league_events + notifications JOIN), `_relative_time()` helper, `EVENT_ICONS`/`ANN_ICONS` dicts; passes `activity_feed` to template
- `templates/dashboard.html` — added `.league-activity-section` block after activity columns
- `static/css/main.css` — appended `.league-activity-*`, `.laf-*` styles (~75 lines)

### Key decisions
- `_relative_time()` uses UTC timestamps; shows "just now / Xm ago / Xh ago / Yesterday / X days ago / X weeks ago" 
- Activity feed merges two sources in Python (not SQL UNION) for flexibility  
- event_type → icon mapping covers all current event types; unknown types get 📌
- Type chips get colored backgrounds per event type (green=round, blue=announcement, yellow=sub, red=alert)
- No new DB schema needed — pure route + template addition

## Week Summary / Recap Page — BUILT (2026-06-01, session 22)

Complete per-week recap page showing all matchup results, weekly leaders, skins summary, and standings snapshot.

### What it does
- Route: `GET /schedule/<season_id>/week/<week_num>/summary`
- Week header: season name, date, course, week type chip
- Prev/Next week navigation buttons (only completed weeks)
- Match Results section: one card per matchup — team names, point totals, winner badge, per-player breakdown table (hole pts + overall + total for each player), "View Scorecard →" link
- Weekly Leaders column: Eagles, Birdies, Low Gross (top 5), Match Points (top 5)
- Skins Winners card (only shown if skins results exist for that week)
- Standings Through Week N: cumulative pts per team + that week's pts contribution highlighted green
- "📋 Week Recap" button added to completed weeks in weekly schedule view (next to Tee Sheet btn)

### Files changed
- `routes/schedule.py` — appended `week_summary()` route (~160 lines)
- `templates/schedule/week_summary.html` — new template
- `templates/schedule/index.html` — added "📋 Week Recap" btn to completed week header
- `static/css/main.css` — appended `.ws-*` styles (~65 lines)

### Key decisions
- Standings query uses `week_number <= ?` so the table reflects cumulative standings through that week (not current)
- `week_pts_map` computed separately and merged in Python for the "Wk N" column
- Per-player breakdown uses `selectattr('team_id', 'equalto', ...)` in Jinja2 to split players by team
- Eagles query uses `score_differential <= -2` (catches albatross etc.)
- Navigation only links to completed weeks (queries `status='completed'`)
- No new DB schema needed — pure route + template addition

## Points Trend Chart — BUILT (2026-05-31, session 21)

New "Trend" tab added to all standings subnavs showing a visual line chart of each team's cumulative points by week.

### What it does
- Route: `GET /standings/<season_id>/trend` — new route in standings.py
- Route: `GET /standings/trend` — redirects to current season's trend
- Canvas-based line chart (pure JS, no external libs): one line per team, color-coded, with end labels
- Legend with team checkboxes — clicking a team toggles its line and table row on/off
- Season progress bar showing completed vs total rounds
- Summary table below chart: per-week points earned + cumulative in parens; bold total column
- "Trend" tab link added to all 6 standings templates (index, scorecards, weekly, allplay, divisions, individual)

### Files changed
- `routes/standings.py` — appended `trend()` and `trend_current()` routes (~95 lines)
- `templates/standings/trend.html` — new template; canvas chart + legend + data table
- `templates/standings/index.html` — added Trend tab
- `templates/standings/scorecards.html` — added Trend tab
- `templates/standings/weekly.html` — added Trend tab
- `templates/standings/allplay.html` — added Trend tab
- `templates/standings/divisions.html` — added Trend tab
- `templates/standings/individual.html` — added Trend tab
- `static/css/main.css` — appended `.trend-*` styles

### Key decisions
- Pure JS canvas chart — no Chart.js dependency needed; fully responsive with `devicePixelRatio` support
- Data computed server-side: one query for weekly pts per team, accumulated in Python
- Team colors assigned from 15-color palette by index (deterministic across page loads)
- Empty state shown when no completed rounds exist yet (no crash)
- `trend_current()` shortcut route for linking from dashboard or nav

## Individual Player Standings — BUILT (2026-05-31, session 20)

New "Individual" tab added to the standings subnav showing per-player stats for the season.

### What it does
- Route: `GET /standings/<season_id>/individual`
- Leader card bar at top: Points Leader, Scoring Leader, Birdie Leader, Eagle Leader
- Full player table sorted by total points with rank + medal emojis for top 3
- Columns: Rank, Player (linked to profile), Team, Role (A/B chip), Rounds, Total Pts, Pts/Round, W–T–L, Score Avg, Best Round, Eagles, Birdies, Pars, Bogeys, Dbl+
- W–T–L derived from `match_results.overall_point_won` (1.0=win, 0.5=tie, 0.0=loss)
- Scoring avg / best round / birdie/eagle counts from `hole_scores` (subs excluded)
- "Individual" tab link added to all 5 existing standings subnavs (index, scorecards, weekly, allplay, divisions)

### Files changed
- `routes/standings.py` — appended `individual()` route (~80 lines)
- `templates/standings/individual.html` — new template with leader cards + full stats table
- `templates/standings/index.html` — added Individual tab to subnav
- `templates/standings/scorecards.html` — added Individual tab to subnav
- `templates/standings/weekly.html` — added Individual tab to subnav
- `templates/standings/allplay.html` — added Individual tab to subnav
- `templates/standings/divisions.html` — added Individual tab to subnav
- `static/css/main.css` — appended `.indiv-*`, `.ilc-*`, `.wlt-*`, `.role-chip`, `.score-avg-pill`, `.best-round-pill` styles

### Key decisions
- Scoring query filters `m.season_id = ?` (not `m.league_id` — matchups table has no league_id column)
- Sub appearances excluded from scoring stats (`sc.is_sub = 0`)
- Two separate queries (match_results + hole_scores) merged in Python by player_id
- No new DB schema needed — pure route + template addition

## Weekly Email Digest — BUILT (2026-05-31, session 19)

Admin can send a formatted HTML "weekly digest" email to all league players with email addresses.

### What it does
- Route: `POST /admin/email/digest` — triggered manually from Admin → Email Settings
- Season selector: choose which season to summarize (defaults to current session season)
- Optional app URL field: adds a "View full league →" footer link
- Email contains 3 sections:
  1. **Current Standings** — all teams ranked by total points, with rounds played column (top 10 shown)
  2. **Recent Results** — most recently completed week's matchups with point scores (e.g. "15 – 5")
  3. **Upcoming Schedule** — next unplayed week's matchups with tee times if set
- Sends to all active players with email on file; reports count on success
- Uses existing `send_league_email()` + `_build_html_email()` infrastructure
- "📰 Weekly Digest" card added to Email Settings sidebar (below existing manual blast card)

### Files changed
- `routes/email_config.py` — appended `_build_digest_data()`, `_build_digest_html()`, `send_digest()` route; updated `settings()` to pass `seasons` + `current_season_id`
- `templates/admin/email_settings.html` — added "📰 Weekly Digest" card in sidebar column

### Key decisions
- Digest data is built fresh at send time from live DB queries (no caching)
- Results use `match_results` table totals per team per matchup — same source as standings
- `recent_week_label` = highest `week_number` WHERE `status='completed'`
- `upcoming_label` = lowest `week_number` WHERE `status != 'completed'`
- No new DB schema needed — pure route + template addition

Gap analysis: see `gap_analysis.md` in same folder (refreshed 2026-05-29)

## StatusReport — Dispatch Reporting

After every session where meaningful work is completed, update `StatusReport.md` in the project root. This file is read by the Dispatch Control System (your project manager) and should always reflect current reality.

Update rules:
- **Current Stage**: update whenever the project phase changes
- **Recent Wins**: prepend the most recently completed item; trim to last 3–5
- **Next Actions**: reflect the actual next 1–3 things to do; remove anything completed
- **Blockers**: add any blockers immediately; clear them when resolved
- **Last updated**: always update the date

Do not let StatusReport.md go stale. If you finish a session and haven't updated it, do it before closing.

## What this is
Self-hosted multi-tenant golf league tracker. Local PC → home NAS (Cloudflare Tunnel) → paid SaaS.
Stack: Python/Flask 3.1 · SQLite · Jinja2 · vanilla JS/CSS

## Key paths
| What | Where |
|---|---|
| App code | `C:\Users\zowen\OneDrive\Documents\Claude\Projects\3. BetterGolfLeagueTracker\GolfLeague\app\` |
| Database | `C:\Users\zowen\Documents\Claude\Projects\Golf League WebApp\Database\golf_league.db` |
| Run app | `cd C:\Users\zowen\OneDrive\...\GolfLeague\app && python app.py` → http://127.0.0.1:5000 |
| Memory | `C:\Users\zowen\OneDrive\Documents\Claude\Projects\3. BetterGolfLeagueTracker\memory.md` |
| Build log | same folder → `build-log.md` |
| Sandbox mounts | `/sessions/.../mnt/GolfLeague/` (DB only) and `/sessions/.../mnt/3. BetterGolfLeagueTracker/` (app + docs) |
| Git repo | `C:\Users\zowen\OneDrive\Documents\Claude\Projects\3. BetterGolfLeagueTracker\GolfLeague\` |

## Critical technical gotchas
1. **Python files on Windows mount** — Edit tool adds null bytes. Always write .py files via `bash cat > file << 'EOF'` heredoc. Fix existing: `python3 -c "data=open(f,'rb').read(); open(f,'wb').write(data.replace(b'\x00',b''))"`
2. **SQLite on Windows mount** — Cannot write DB directly from Linux sandbox. Always: `cp db /tmp/x.db` → modify `/tmp/x.db` → `cp /tmp/x.db` back.
3. **sqlite3.Row** — No `.get()` support. Use bracket access `row['key']` with explicit None guards.
4. **Jinja2 enumerate** — Registered as both global and filter in `create_app()` in app.py.
5. **HTML/template files** — Safe to write with Write/Edit tool directly on Windows mount.

## Blueprints registered in app.py
main, auth, players, seasons, teams, schedule, scores, standings, handicap, admin, skins, courses, playoffs, archive, records, stats, reports, self_report, subs, users, announcements, notifications, migration, contests, dues, email_config, forum, public_view, api

## Feature inventory (all built ✅)
- **Auth**: League ID + shared password login; individual user accounts (email+pw); registration; admin user management
- **Players**: Add/edit/deactivate/reactivate/delete (hard delete with safety checks); bulk CSV import; player profile page
- **Seasons + Teams**: Create seasons, pair players into teams, optional nickname, division/group assignment
- **Schedule**: Round-robin generator; per-matchup edit; week date/type edit; tee sheet columns (tee_time, starting_hole)
- **Score Entry**: Flipped layout (holes→columns, players→rows); live JS match pts; mobile card-by-card UX; substitute player support
- **Score View**: Same flipped layout; gross+pts stacked per hole cell; admin Edit Scores button
- **Standings**: 5 tabs — Summary · Team Scorecards · Weekly Scorecards · Al
## Broken Tiles — TODO
Navigating to these dashboard tiles throws errors (needs investigation):
- Schedule, Standings, Forum, Submit Scores, League Info, Dues, Contests, Score Entry, Admin Panel
- Likely: missing blueprints, unregistered routes, or templates referencing undefined variables from recent sessions.

## iOS App — Future Build (App Store target)
- Goal: native iOS companion app, distributed via Apple App Store
- Framework recommendation: **React Native** (faster dev, reuse JS logic, one codebase for iOS+Android later) OR **SwiftUI** (best iOS feel, required for some App Store features like widgets/live activities)
- **App Store requirements to plan around:**
  - Apple Developer Account required ($99/year) — enroll at developer.apple.com
  - App must pass App Store Review (Apple reviews every submission, ~1-3 days)
  - Requires privacy policy URL — must describe what data is collected
  - Login/auth: Apple requires "Sign in with Apple" option if you support any third-party login (we may be exempt if league-ID login is proprietary)
  - No direct payment outside IAP — if we ever charge for the app or features, must use Apple's In-App Purchase (30% cut)
  - App must work on recent iOS versions (target iOS 16+)
  - Screenshots + app metadata required for App Store listing
  - TestFlight available for beta testing before public release

- **Pre-build prep needed:**
  - [ ] Enroll in Apple Developer Program ($99/yr) at developer.apple.com
  - [ ] Define REST API layer — Flask has no JSON API yet; need endpoints for: standings, schedule, scores, players, handicaps, announcements
  - [ ] Auth strategy — JWT tokens recommended for mobile (stateless, no session cookies); add `/api/login` → returns token; token sent as Authorization header
  - [ ] Scope MVP — view schedule, view standings, view scores, submit scores via self-report flow; notifications for new rounds posted
  - [ ] Decide framework: SwiftUI (native, best UX) vs React Native (faster, cross-platform later)
  - [ ] Privacy policy page — needed before App Store submission
  - [ ] App icon set (1024×1024 master + all required sizes)
  - [ ] TestFlight beta test with league members before public release
  - [ ] Review self_report flow as the model for member-facing score submission
  - [ ] Consider: is the app free? Per-league subscription? Affects IAP/pricing setup

- **Payment architecture (dual-system, unified access) — PLANNED:**
  - Goal: Apple IAP for in-app purchases + separate web payment (e.g. Stripe) for desktop — both grant identical access, no account segregation
  - This is feasible and common (Spotify model). Key design principle: payments write to a shared `subscriptions` or `league_access` table in the backend; the app and web both check the same entitlement, regardless of how it was paid for
  - **Apple IAP rules to know:**
    - Apple takes 30% (15% for small developers under $1M/yr via App Store Small Business Program)
    - You CANNOT link to or mention your cheaper web payment option from within the iOS app — Apple will reject the app. You can have both, just can't cross-promote inside the app.
    - Apple calls this the "reader app" rule — apps that give access to content paid for outside the app are allowed, but can't have a "buy here" button pointing to web
    - Receipt validation: when a user pays via IAP, Apple sends a receipt — your backend must validate it with Apple's servers and then grant access in your DB
  - **Recommended backend entitlement model:**
    - Add `subscriptions` table: `user_id, league_id, plan, status, payment_source (apple|stripe|manual), expires_at, apple_receipt, stripe_subscription_id`
    - Both IAP and Stripe webhooks write to this table → app and web check same `status`
    - User logs in once (via JWT on mobile, session on web) — same account, same access
  - **To-do for this feature:**
    - [ ] Design `subscriptions` table schema
    - [ ] Integrate Stripe for web payments (Stripe Checkout is simplest)
    - [ ] Build Apple IAP receipt validation endpoint (`POST /api/iap/validate`)
    - [ ] Enroll in Apple Small Business Program if revenue < $1M/yr (saves 15%)
    - [ ] Decide pricing model: per-league flat fee? monthly per-user? commissioner pays, members free?

## GLT reference
Site: golfleaguetracker.com — login: league "Buckeye", password "SkyPilot"

## Score Entry UX — TODO
Notes from session, to be built:

1. ✅ **Auto-advance cursor after single digit** — DONE. Checkbox "Allow double-digit scores" added; JS auto-advances after single-digit entry.

2. ✅ **Course & Tee selector — hide "Nine" column** — DONE (automated run #13, 2026-06-06). Main "Side" dropdown now shows nine value in label (e.g. "Blue (Front) — par 36") to distinguish front/back. Per-player tee dropdowns now filter to same nine as main selection and show just tee name (e.g. "Blue" not "Blue (Front)") — no redundant nine suffix.

3. **Score entry discoverability / flow** — "Enter Scores" is a small button buried in the schedule table, must be clicked per group. Ideas:
   - Dedicated score entry hub page: select week, then flows through each group in sequence
   - Keep week-selection UI (liked by Zach)
   - Make the entry point more obvious for admins — consider a prominent "Enter Scores" tile or banner when a week is current/upcoming
   - Just noted for now — no implementation yet

## Known Visual Bugs — TODO
None outstanding.

## Score Entry UX — TODO
Notes from session, to be built:

1. ✅ **Auto-advance cursor after single digit** — DONE.
2. ✅ **Course & Tee selector — hide "Nine" column** — DONE (automated run #13).
3. ✅ **Score entry discoverability** — DONE (automated run #14). "🎯 Enter Scores" button added to Next Round card in admin/overview.html, linking directly to the schedule page filtered to that week.

## Recent automated fixes

### 2026-06-07 (automated run #15) — Playoff bracket print view
- **What:** Added "🖨 Print Bracket" button to the playoff bracket page header (only shown when bracket exists). Added `@media print` CSS block to hide nav, admin controls, forms, and page action buttons; sets landscape `@page`; preserves champion banner + bracket visualization with clean black-on-white print styling; winner names bold green, loser names struck through.
- **Files changed:** `templates/playoffs/index.html` — print button in header-actions (conditional on `bracket`); `static/css/main.css` — `.bracket-print-btn` class + `@media print` block (~90 lines appended).
- **Note:** Git commits skipped — `.git/config.lock` still stuck from OneDrive sync (0-byte lock file, cannot delete from Linux sandbox).

### 2026-06-06 (automated run #14) — Score entry discoverability + admin overview truncation fix
- **What:** Added prominent "🎯 Enter Scores" button to the Next Round card in `admin/overview.html`, linking to `schedule.index?week=N` for one-click access to score entry. Also fixed a pre-existing truncation in the same template (Other Seasons card was cut off mid-tag; completed the season switcher link using `url_for('switch_season', season_id=...)` and closed all open blocks).
- **Files changed:** `templates/admin/overview.html` — Enter Scores button + truncation fix; `static/css/main.css` — `.ov-nr-enter` styles (2 lines).
- **Note:** Git commits skipped — `.git/config.lock` still stuck from OneDrive sync.

### 2026-06-06 (automated run #13) — Score entry tee selector UX cleanup
- **What:** Per-player tee dropdowns on score entry now only show tees matching the same nine as the main selected tee, and drop the "(Front)"/"(Back)" suffix (since all options are the same nine). Main "Side" dropdown now includes the nine value in the label (e.g. "Blue (Front) — par 36") so front/back variants are distinguishable.
- **Files changed:** `templates/scores/enter.html` — added `sel_nine`/`player_tees` Jinja2 variables; updated 2 per-player dropdown loops to use `player_tees` with plain tee name; updated main tee dropdown label to include nine suffix.
- **Note:** Git commits skipped — `.git/config.lock` still stuck from OneDrive sync.

### 2026-06-06 (automated run #12) — Fixed standings page visual bug (rank-leader CSS conflict)
- **Root cause:** `.rank-leader` CSS class (line 441, main.css) defines `display: inline-block` for a circular badge element. The same class name was applied to `<tr>` elements in 5 templates to highlight the leader row. This caused `display: inline-block` to be applied to `<tr>` tags, collapsing rows and producing the jumbled Pos/Team column layout and wrapping team names.
- **Fix:** Changed all 5 `<tr class="rank-leader">` usages to `<tr class="standings-row--leader">` — the correct existing row-highlight class (`.standings-row--leader td { background: #f0faf2; }` was already defined). Also updated `.standings-summary-table .rank-leader td` → `.standings-summary-table .standings-row--leader td` in CSS.
- **Files changed:**
  - `templates/standings/index.html` — 2 occurrences
  - `templates/standings/allplay.html` — 1 occurrence
  - `templates/standings/divisions.html` — 1 occurrence
  - `templates/archive/season.html` — 1 occurrence
  - `static/css/main.css` — 1 occurrence (line 1172)
- **Known Visual Bugs — TODO:** standings rank-leader conflict ✅ FIXED; no other known visual bugs remain
- **Note:** Git pre/post-run commits skipped — .git/config.lock stuck from OneDrive sync; cannot write git config from Linux sandbox. Zach may need to manually clear `.git/config.lock` in the repo.
