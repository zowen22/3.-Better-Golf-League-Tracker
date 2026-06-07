# BetterGolfLeagueTracker — Project Memory
Last updated: 2026-05-28 (session 23)

## What this project is
A self-hosted, multi-tenant golf league tracking web app. Runs locally on PC HDD first, then migrates to home NAS via Cloudflare Tunnel. Long-term goal: paid SaaS platform.

## Tech stack
- Database: SQLite (`D:\GolfLeague\Database\golf_league.db`)
- DB GUI: DB Browser for SQLite
- Backend: Python / Flask 3.1
- Editor: VS Code
- Version Control: Git
- Future hosting: Home NAS → Cloudflare Tunnel
- Future payments: Stripe
- Domain: Cloudflare Registrar

## Folder structure
```
D:\GolfLeague\
    Database\
        golf_league.db   ← built and populated
    app\
        app.py, config.py, database.py, requirements.txt
        routes/
            main.py, auth.py, players.py, seasons.py, teams.py
            schedule.py, scores.py, standings.py, handicap.py, admin.py
        templates/
            base.html, dashboard.html
            admin/season.html, edit_week.html, edit_scores.html, unlock_scores.html
            players/, seasons/, teams/, schedule/, scores/, standings/
        static/css/main.css, js/main.js
    docs/
    migrate_add_passwords.py         (run)
    migrate_add_handicap_columns.py  (run)
    migrate_add_schedule_columns.py  (run)
```

## Run the app
```
cd D:\GolfLeague\app && python app.py → http://127.0.0.1:5000
```

## Current build status (all ✅ unless noted)
- ✅ Schema: 37 tables, Tannenhauf GC test data, default roles/permissions
- ✅ Auth: league creation, login/logout, session (league_id, league_name, role)
- ✅ Players: add, view, deactivate/reactivate
- ✅ Seasons + Teams: create seasons, pair players into teams, optional nickname
- ✅ Schedule: round-robin generator, weekly/biweekly cadence, per-matchup edit, clear
  - Filter bar: Week dropdown + Team dropdown + "Get Schedule"
  - Default lands on closest upcoming week
  - Weekly detail view: Group/Hole/Course/Side/TeeTime/Team#/Player1/Hdcp/Player2/Hdcp
  - Yearly overview (All Dates): Week/Type/Date/Course/Side/Group1/Group2 ("3 v 7" cells)
  - matchups table new columns: tee_time, starting_hole (default 1), week_type (default 'Normal')
- ✅ Score entry: REDESIGNED (session 4)
  - Flipped layout: holes across top, players down side
  - Header rows: Hole#, Par, Hdcp Index
  - Grouped by team: Team1 header → A row → B row → "vs" → Team2 header → A row → B row
  - Live JS: per-hole net calc, per-hole match pts (0/1/2) shown under each input, running totals
  - Summary columns: In / Hdcp / Net / Pts (live)
  - A/B designation shown with role pill on each player row
- ✅ Score view: REDESIGNED (session 4) — same flipped layout, gross+pts stacked per hole cell
- ✅ Match play scoring: FIXED (session 4) — Win=2, Tie=1 each, Loss=0 (was 1/0.5/0)
  - Max individual pts per player: 9 holes × 2 + 2 overall = 20 pts max
- ✅ Standings: 3-page tab structure with season switcher
  - /standings/current → redirects to latest season
  - /standings/<id>  → League Standings Summary: Pos/Division/Team/Total Pts + Choose Rounds filter
  - /standings/<id>/scorecards → Team Scorecards: per-player rows, As of Round / Score Type / Sort By
  - /standings/<id>/weekly[/<week>] → Weekly Scorecards: stacked score+pts per hole, prev/next nav
    - UPDATED (session 4): score+pts now stacked in same hole cell (like GLT reference)
    - Columns: Hdcp | H1..H9 | In | Net | Pts
- ✅ Handicap engine (routes/handicap.py):
  - Par-based differential, configurable window, padding scores, high/low drops
  - Recalculates automatically after every round saved
  - Admin "↺ Recalc Handicaps" button on season detail + admin panel
  - handicap_history table stores each calculation
- ✅ Admin Panel (/admin/):
  - Separate from member dashboard; accessible via "🔧 Admin Panel" tile (admins only)
  - /admin/ → redirects to latest season panel
  - /admin/season/<id> → admin panel with quick actions + embedded editable schedule widget
  - /admin/season/<id>/week/<num>/edit → edit week date + type (applies to all matchups that week)
  - /admin/scores/<id>/unlock → redirects to edit page (no deletion)
  - /admin/scores/<id>/edit → pre-filled score grid, updates hole_scores in place, rebuilds match_results
- ✅ Jinja2: `enumerate` registered as both global and filter (app.py)
- ✅ Dashboard tiles: Seasons, Schedule, Standings, Scores, Players, [Admin Panel], [Skins]

## DB columns added via migrations (all applied)
- leagues: admin_password_hash, member_password_hash
- league_settings: padding_score_count, low_scores_to_drop
- matchups: tee_time, starting_hole (default 1), week_type (default 'Normal')

## Scoring system (session 4 fix)
- Win = 2 pts, Tie = 1 pt each, Loss = 0 pts (per hole AND overall)
- Max pts per player per matchup: 9×2 + 2 = 20 pts
- Affects: calc_match_play() in routes/scores.py and hole_pts() in routes/standings.py
- Existing test data in DB has old 0/0.5/1 values — will be correct for new rounds

## Known bugs — RESOLVED
1. ✅ **Standings tab formatting** — CSS fix confirmed in place (`table-layout: fixed`, column widths, `.center`). Visually verified via code review — structure is correct.
2. ✅ **admin/edit_scores.html** — Already uses the flipped layout (holes across top, players down side). No change needed.

## Skins — BUILT (session 5)
Full skins feature implemented end-to-end:
- `routes/skins.py` — new blueprint registered in app.py
  - `GET /skins/` → redirect to latest season
  - `GET /skins/<season_id>` → season overview: all rounds, pot totals, winners summary
  - `GET/POST /skins/round/<round_id>` → round setup + results view
  - `POST /skins/round/<round_id>` action=calculate → runs skins algorithm, saves results
- `templates/skins/index.html` — season overview with round cards
- `templates/skins/round.html` — setup form (buy-in, gross/net, opt-in players, paid status) + per-hole results table with winning scores highlighted
- `static/css/main.css` — skins styles appended (round cards, result table, winner chips, payout cells, .btn-success)
- `dashboard.html` — Skins tile now links to `url_for('skins.current')`

Skins algorithm:
- Unit value = total_pot / num_holes
- Per hole: lowest score among participants wins. Tie → carries over.
- Carryover skins accumulate until a clean winner. Payout = skins_on_table × unit_value
- End-of-round leftover stored as carried_over_amount in round_skins_settings for next round

## League Settings UI — BUILT (session 6)
Full settings UI implemented end-to-end:
- `routes/admin.py` — new `GET/POST /admin/season/<id>/settings` route added
  - Reads existing `league_settings` row or falls back to `_SETTINGS_DEFAULTS` dict
  - POST: INSERT if no row yet, UPDATE if exists (keyed on season_id + league_id)
  - Handles int/float/bool/str coercion from form POST data
- `templates/admin/settings.html` — full settings form, 6 grouped sections:
  - **Scoring**: holes/round, scoring type (net/gross), match play pts/hole, A/B method
  - **Handicap**: differential method, rounds window, drops, %, max index, ESC, booleans
  - **Max Score Per Hole**: optional cap with warn/cap action and custom message
  - **Playoffs**: team count, finals duration
  - **Skins Defaults**: gross/net, default buy-in, self opt-in flag
  - **Self-Reporting**: enabled toggle + approval required toggle
  - Season switcher dropdown navigates between `/admin/season/<id>/settings`
- `templates/admin/season.html` — "⚙ League Settings" button added to quick-actions bar
- `static/css/main.css` — Settings styles appended (settings-section, settings-grid, checkbox-label, save bar, btn-lg, page-subtitle)

## GLT Feature Gap Analysis — Priority Order
Target: match golfleaguetracker.com (GLT) functionality.
GLT reference login: league "Buckeye", password "SkyPilot"

### HIGH PRIORITY (core gaps vs GLT)

**1. Course Management UI** ← DO NEXT
- Currently: no UI to add/edit courses, tees, or holes. Only Tannenhauf GC exists from manual DB setup.
- Need: `/courses/` list, `/courses/add`, `/courses/<id>/edit`, tee management, hole par/hdcp entry
- Tables: courses, tees, holes (all exist)
- GLT has full course database with tee boxes and hole details

**2. Player Profile Page**
- No individual stats page. Need: handicap trend chart, round-by-round history, pts history, career totals
- Tables: players, hole_scores, scorecards, handicap_history, match_results (all exist)

**3. Playoff Bracket UI**
- Schema fully built (playoff_brackets, playoff_matchups). Zero UI or routes.
- GLT has full bracket view with seeding, matchup results, advancement
- Need: bracket generation from standings, weekly matchup entry, bracket visualization

**4. Division / Group System**
- GLT shows teams grouped by division in standings. We show "—" placeholder.
- "Points by League Group" page on GLT: players sorted by pts within each division
- Need: add division/group assignment to teams (or league_settings), update standings to group by division
- Could be a simple `division_name` column on teams table + standings grouping

**5. Indiv / Segment / Season Points Breakdown**
- GLT's Team Scorecards show: Indiv pts | Segment pts | Season pts columns
- We show only Season pts total
- Segment = a date range within a season (playoff qualifier period). Needs segment_start/end dates.

### MEDIUM PRIORITY

**6. Archive UI**
- Schema: archive_settings (visible_to_members, locked, unlock flow). No routes or UI.
- Members should be able to browse past seasons if admin enables it.

**7. Self-Reporting**
- Schema and admin toggle exist. No player-facing score submission UI.
- Need: `/scores/self-report/<matchup_id>` route, approval queue in admin panel

**8. All-Play Standings**
- GLT shows an "All-Play" record (how you'd do against every other team each week)
- Currently calculated at report time but not implemented anywhere
- Adds richness to standings / tiebreakers

**9. Score history / recent rounds on dashboard**
- GLT dashboard shows recent round summaries. We just show nav tiles.

**10. Reports / Export**
- Schema: report_templates, report_parameters. No generation UI.
- At minimum: printable scorecard PDF, season summary export

### LOW PRIORITY / BACKLOG
- Individual user accounts (currently league-wide passwords)
- Delete players (currently only deactivate/reactivate)
- Bulk player adding (add multiple at once)
- League ID as text slug instead of integer
- Notifications (email/SMS) — schema exists
- USGA course API integration (Stage 3 — far future)

## Next automated session TODO (pick highest unchecked item above)
1. ✅ Course Management UI
2. ✅ Player Profile Page
3. ✅ Playoff Bracket UI
4. ✅ Division / Group System
5. ✅ Indiv / Segment / Season pts breakdown in Team Scorecards
6. ✅ Archive UI
7. ✅ Self-Reporting (player score submission + admin approval queue)
8. ✅ All-Play standings record
9. ✅ Dashboard recent activity feed
10. ✅ Reports / Export (printable scorecard, season summary)
11. ✅ League Records & Statistics page
12. ✅ Player delete functionality (hard delete with safety checks — reassign or block if scores exist)
13. ✅ Bulk player import via CSV (add multiple players at once from spreadsheet)
14. ✅ Mobile-optimized score entry (responsive layout for phone use on course)
15. ✅ Season comparison stats table (side-by-side stats across all seasons)
16. ✅ Individual user accounts (per-player logins, significant schema refactor)
17. ✅ League Announcements / Bulletin Board
18. ✅ Substitute player support (mark player absent, assign sub — player_absences table exists)
19. ✅ Configurable tiebreakers (tiebreaker_settings table exists — wire up to standings)
20. [ ] Tee sheet / starting times view (tee_time + starting_hole already stored; add a printable tee sheet page)
21. [ ] In-app notification center (bell icon in nav showing recent league events — different from announcements)
22. [ ] Score entry enhancement: par/birdie/eagle color coding during live entry (visual feedback while entering scores)
23. [ ] Per-hole scoring averages / birdie-par-bogey stats (data in hole_scores; add player/league stats page)
24. [ ] Custom contests — long drive, closest to pin tracking (new schema needed)
25. [ ] Stableford scoring mode (major engine change; defer)
26. [ ] Payment / dues tracking (new schema needed)
27. [ ] Per-player tee selection in score entry (scorecards.tee_id column exists; UI missing)
28. [ ] Player-initiated sub requests (players self-request via site; we only have admin-assigned)
29. [ ] Player hole-by-hole scoring history (extend player profile with per-hole breakdown)
30. [ ] Course statistics — hole difficulty rankings (data in hole_scores)

## Substitute Player Support — BUILT (session 23)
Full substitute player feature implemented end-to-end. DB migration required (adds `matchup_id` to `player_absences`).

### What it does
Admins can mark players as absent for any upcoming matchup and assign substitute players. Subs are reflected in score entry and score view.

1. **Manage Subs page** (`/subs/<matchup_id>`) — per-matchup page showing all 4 players with:
   - "Mark Absent" checkbox per player
   - Sub dropdown (any active league player; ✦ marks regular team players)
   - Optional reason text field + "Excused" checkbox
   - Status badges: Playing (green) / Absent (red) / Sub: Name (amber) / No Sub (gray)
   - Current assignments shown immediately on page load

2. **Schedule integration** — "Subs" link added to admin table-actions column on all non-completed, non-bye matchups

3. **Score entry integration**:
   - "👤 Manage Subs" button in page-header actions
   - Blue banner shows active substitutions if any are assigned
   - Sub player's name appears in the score grid instead of the absent player
   - Amber "SUB" badge next to sub player names with tooltip "(Substituting for X)"
   - Sub's handicap used for net score calculation

4. **Score view integration** — "SUB" badge + "for Original Player" label shown in completed scorecard

### Migration required
- `app/migrate_add_absence_matchup.py` — ⚠️ **Must be run manually**: `python migrate_add_absence_matchup.py` from `D:\GolfLeague\app\`
  - Adds `matchup_id` column to `player_absences` (allows pre-round sub assignment)
  - Safe to run multiple times (checks if column exists first)

### How data flows
1. Admin opens Schedule → clicks "Subs" on any upcoming matchup
2. Admin marks Player A absent, assigns Player X as sub → saves
3. Absence stored in `player_absences` (matchup_id set, round_id NULL until scored)
4. Admin opens Enter Scores → sees banner + sub names in grid
5. `_get_sub_assignments()` queries `player_absences WHERE matchup_id = ?`
6. `_build_player_list()` uses sub's player_id/name/handicap instead of absent player
7. When scores saved, `UPDATE player_absences SET round_id = ?` links to the created round

### Files changed / created
- `app/migrate_add_absence_matchup.py` — migration script (new)
- `routes/subs.py` — new blueprint (`/subs/`): `manage()` GET/POST
- `app.py` — registered `subs_bp`
- `routes/scores.py` — added `_get_sub_assignments()` helper; updated `_build_player_list()` to accept/apply subs; `enter()` passes `sub_assignments` to template; `_process_scores()` links absences to round_id after save; `view()` loads `sub_info_by_sub_pid` to show "(sub for X)" in scorecard
- `templates/subs/manage.html` — new template
- `templates/scores/enter.html` — header now has "Manage Subs" button + sub banner + SUB badges on player rows
- `templates/scores/view.html` — SUB badge + "for X" label on sub player rows
- `templates/schedule/index.html` — "Subs" link added to admin actions column
- `static/css/main.css` — appended ~130 lines: `.sub-badge`, `.sub-for-label`, `.alert-info`, `.sub-notice`, `.subs-*` page styles

### Key design decisions
- Pre-round subs stored via `matchup_id` on `player_absences` (not `round_id`) — requires migration
- `_get_sub_assignments()` wrapped in try/except — app works pre-migration (subs silently disabled)
- Score entry uses sub's actual handicap for net calculation and A/B designation
- Scores are attributed to the sub player's `player_id` in scorecards/hole_scores/match_results
- When round is saved, `player_absences.round_id` is updated to link the record to the round
- Sub dropdown marks regular team players with ✦ to help admin identify them

## Individual User Accounts — BUILT (session 21)
Full per-player login system implemented end-to-end. No DB migration required (schema already had `users`, `user_league_roles`, and `players.user_id` columns).

### What it does
Adds a complete parallel login system alongside the existing shared-password league login:

1. **Dual login page** — `/login` now has two tabs:
   - "League Login" tab: original League ID + shared password (unchanged, fully backward-compatible)
   - "My Account" tab: email + personal password login

2. **Account registration** — `/register`:
   - Enter League ID + league password (admin or member) to verify membership
   - Enter name, email, personal password
   - Creates `users` row + `user_league_roles` row (role matches which password they used)
   - No player link at registration — admin links them via Manage Users

3. **My Account page** — `/users/account`:
   - Edit first name, last name, email
   - Change password (requires current password)
   - Shows linked player profile (with link) or a warning if unlinked
   - Shows account details: member since, league, role, status

4. **Admin: Manage Users** — `/users/`:
   - Table of all user accounts in the league
   - Per-row: change role (dropdown auto-submits), link to player (dropdown + Save), activate/deactivate, reset password (inline form)
   - "Invite players" info box with step-by-step instructions
   - Shows unlinked players in the link dropdown

5. **Session enrichment** — user-account login additionally sets:
   - `session['user_id']`, `session['user_display_name']`, `session['player_id']`
   - Context processor exposes `session_user_id` and `user_display_name` to all templates

6. **Nav bar** — shows "👤 First Last" link to account page when logged in as user account

### Files changed / created
- `routes/auth.py` — added `register()` route; updated `login()` to handle `login_type=user` (email + password) alongside existing league password flow
- `routes/users.py` — new blueprint (`/users/`): `list_users()`, `link_player()`, `set_role()`, `toggle_active()`, `reset_password()`, `account()`
- `app.py` — registered `users_bp`; updated context processor to expose `user_display_name`, `session_user_id`, kept `pending_submission_count`
- `templates/login.html` — two-tab login UI (League Login / My Account) with JS tab switcher + localStorage persistence
- `templates/auth/register.html` — new registration form (league verification + account creation)
- `templates/users/account.html` — account settings page (profile info + change password + linked player)
- `templates/users/list.html` — admin user management page
- `templates/dashboard.html` — added "👤 My Account" tile (when user_id in session), "🔑 Manage Users" tile (admins only)
- `templates/admin/season.html` — added "🔑 Manage Users" button to quick-actions bar
- `templates/base.html` — shows "👤 Display Name" link in nav bar for user-account sessions
- `static/css/main.css` — appended ~130 lines: login tabs, registration page sections, account page player card, badge variants, data-table, user management styles

### Key design decisions
- **No migration needed** — `users`, `user_league_roles`, `players.user_id` all existed in the original schema
- **Fully backward-compatible** — existing league-password login unchanged; user accounts are additive
- **Role from password** — during registration, admin password → league_admin role; member password → member role
- **Player linking is admin-only** — avoids players claiming someone else's profile; admin links via Manage Users
- **Single-league accounts** — each user account is linked to one league (simplest model; multi-league is a future concern)
- **Session compatibility** — user-account session sets the same `league_id`/`role` keys; all existing decorators (`login_required`, `admin_required`) work unchanged

## Season Comparison Stats — BUILT (session 20)
Full season comparison stats feature implemented end-to-end. No DB migration required.

### What it does
A new `/stats/` route accessible from the dashboard ("📊 Season Stats" tile) that shows:

1. **Overview Cards** (one per season, responsive grid) — each card shows:
   - Season name + date range (header)
   - Teams count, Rounds played / scheduled
   - Average gross score per scorecard
   - Low round (score + player name)
   - Individual points leader (pts + name)
   - Top team in standings (team name)
   - Match wins leader (W-L-T record + name)
   - Links to Standings and Records for that season

2. **Side-by-Side Comparison Table** (only shown when 2+ seasons exist) — metrics as rows, seasons as columns:
   - Teams, Rounds Played, Avg Gross Score, Low Round, Individual Pts Leader, Top Team (highlighted gold row), Match Wins Leader, Total Pts Scored

3. **Per-Season Team Win Records** tables — one per season with data, showing Pos/Team/W/L/T/Pct; top team highlighted gold, podium emojis for top 3

### Files changed / created
- `routes/stats.py` — new blueprint (`/stats/`) registered in app.py
  - `GET /stats/` → `compare()` — queries all seasons in league, builds per-season stats dict
  - All data calculated at render time from: `seasons`, `teams`, `matchups`, `rounds`, `hole_scores`, `scorecards`, `match_results`, `players`
  - Win record calculated by comparing per-team pts per matchup (higher pts = win)
- `templates/stats/compare.html` — full template with overview cards + comparison table + win records tables
  - Empty state when no seasons exist
  - Season links to Standings and Records
  - Comparison table only shown for 2+ seasons (no value showing a 1-column table)
- `app.py` — registered `stats_bp` (import + `app.register_blueprint`)
- `templates/dashboard.html` — RECONSTRUCTED (file was truncated on disk) + added "📊 Season Stats" tile
  - Tile visible to all roles; links to `url_for('stats.compare')`
- `static/css/main.css` — appended ~130 lines of stats styles:
  - `.stats-overview-grid` (responsive auto-fill card grid)
  - `.stats-season-card` with green header, metric rows, footer links
  - `.stats-compare-table` (scrollable, season-per-column comparison)
  - `.stats-winrecord-table` with winner row highlight
  - `.stats-highlight-row` (gold background for Top Team row)
  - Mobile: single-column card layout at ≤600px

### Key design decisions
- All queries are league-scoped via session `league_id`
- Win/Loss/Tie calculated from `match_results` by summing per-team pts per matchup — no separate wins column needed
- `.pct` displayed baseball-style (.667 format) using `('%03d' % (pct * 1000)|int)`
- Comparison table hidden when only 1 season (would be one column, no comparison value)
- dashboard.html was reconstructed from scratch (it was truncated on disk mid-tag) with all original tiles preserved + Stats tile added

## Mobile-Optimized Score Entry — BUILT (session 19)
Full mobile scorecard feature implemented. Zero DB changes required.

### What it does
On screens ≤ 768px, the wide horizontal scorecard table is hidden and replaced with a touch-friendly hole-by-hole card navigator. Desktop users see the original table unchanged.

**Mobile UX flow:**
1. Select course/tee as before (selects now go full-width on mobile, font-size 16p