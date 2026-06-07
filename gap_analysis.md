# BetterGolfLeagueTracker — GLT Gap Analysis
Last refreshed: 2026-05-29

Reference: https://www.golfleaguetracker.com (login: league "Buckeye", password "SkyPilot")
GLT version: 8.138 (as of May 2026)

---

## Completed features (all ✅)
See build-log.md for full history. Summary:
- Auth (league + individual user accounts)
- Players (add/edit/deactivate/reactivate/delete/CSV import)
- Seasons + Teams + Divisions
- Schedule (round-robin generator, per-matchup edit, tee times)
- Score Entry (flipped layout, live JS, mobile card UX, sub support)
- Standings (5 tabs: Summary, Team Scorecards, Weekly, All-Play, By Division)
- Handicap engine (par-based, auto-recalc, history)
- Admin Panel + League Settings UI (250+ settings parity)
- Skins (gross/net, carryover, payout)
- Self-Reporting (submission + admin approval queue)
- Announcements (typed, expiry dates, dashboard banner)
- Reports (printable scorecard, season summary)
- Records (season leaders, streaks, H2H matrix, career leaders)
- Stats (season comparison, win records)
- Archive (past season visibility control)
- Playoffs (full bracket UI: generate, visualize, record results)
- Courses (full CRUD: courses, tees, holes)
- Player Profile (handicap trend, round history, career stats)
- Substitute player support (admin-assigned)
- Individual user accounts + Manage Users admin

---

## Current priority list

### Unchecked (next to implement, in order)

- [x] **#19 — Configurable tiebreakers** ✅ BUILT 2026-05-29
  - 4-priority cascade (H2H, Pts%, All-Play, Scoring Avg); admin settings UI; standings tiebreaker bar

- [x] **#20 — Tee sheet / starting times view** ✅ BUILT 2026-05-29
  - Standalone printable page at `/schedule/<id>/week/<num>/tee-sheet`
  - Shows tee times, starting holes, player names + handicaps; print-optimized layout
  - "🖨 Tee Sheet" button added to weekly schedule view header

- [x] **#21 — In-app notification center** ✅ BUILT 2026-05-30
  - Bell icon + unread badge in nav; feed at `/notifications`
  - Auto-events: round_completed, sub_assigned, announcement
  - Per-user read tracking via `notification_reads` table

- [x] **#22 — Score entry: par/birdie/eagle color coding** ✅ BUILT 2026-05-30
  - Pure CSS/JS in `templates/scores/enter.html` — no backend changes
  - Desktop: `.sc-score-cell` td gets class `score-eagle/birdie/par/bogey/double` via `updateAll()`
  - Mobile: `.mob-score-input` colored via `colorMobInput()` in `syncAndCalc()` and `loadHole()`
  - Color legend shown above scorecard; eagle=gold, birdie=green-yellow, bogey=pink, double+=red

---

### New gaps identified (GLT features we still lack)

- [x] **#23 — Per-hole scoring averages / birdie-par-bogey stats** ✅ BUILT 2026-05-30
  - `/stats/hole-averages`: season + player selectors; per-hole avg score, eagle/birdie/par/bogey/double+ counts and %
  - Course difficulty table: all-players per-hole avg + birdie%/par%/bogey%; holes ranked hardest first by avg vs par
  - Dashboard tile "🕳️ Hole Averages" added; linked from Season Stats page
  - Also restored missing `templates/stats/compare.html` (was accidentally deleted)

- [x] **#24 — Custom contests** ✅ BUILT 2026-05-30
  - `routes/contests.py` + 3 templates; admin CRUD + member view at `/contests/season/<id>`
  - Types: Long Drive, Closest to Pin, Low Gross, Low Net, Most Birdies, Custom
  - Results with rank, value text, notes; medal emoji for top 3; dashboard tile + admin panel button

- [x] **#25 — Stableford scoring mode** ✅ BUILT 2026-05-31
  - `scoring_mode` setting in League Settings (Match Play / Stableford)
  - Stableford: Eagle=4, Birdie=3, Par=2, Bogey=1, Double+=0 per hole (net vs par)
  - Score entry: per-hole stableford pts displayed with gold/green/pink color coding; comparison bonus (2/1/0) for winning stableford matchup
  - Score view: same color coding; "SB" column header
  - Standings: no change needed — total_points sum works for both modes
  - DB migration: `migrate_scoring_mode.py` (run manually)

- [x] **#26 — Payment / dues tracking** ✅ BUILT 2026-05-30
  - `dues_payments` table + `dues_amount`/`dues_due_date` in `league_settings`
  - Admin: `/admin/season/<id>/dues` — all-player status, record payment, delete payment, dues settings
  - Member: `/dues/season/<id>` — league-wide paid/unpaid; personal status if linked account
  - Dashboard tile + admin panel quick-action button added

- [x] **#27 — Per-player tee selection in score entry** ✅ BUILT 2026-05-30
  - Dropdown per player row in score entry; JS uses per-player HCP indexes; tee_id saved to scorecards; view shows tee badge

- [x] **#28 — Player-initiated sub requests** ✅ BUILT 2026-05-31
  - `sub_requests` table + migration; routes in subs.py
  - Player "Need a Sub" btn on schedule; `/subs/request/<id>` form; `/subs/my-requests` history
  - Admin queue at `/subs/admin/requests`; assign sub (auto-writes absence record) or dismiss
  - Badge on Admin Panel quick-actions; "My Sub Requests" dashboard tile

- [x] **#29 — Player hole-by-hole scoring history** -- BUILT 2026-05-30
  - GLT: "Hole by Hole Scoring History: View a single player's complete scoring history and averages"
  - Player profile shows round history but not hole-by-hole breakdown with averages
  - Data exists in `hole_scores`; extend player profile or add sub-page

- [x] **#30 — Course statistics** ✅ BUILT 2026-05-31
  - `/stats/course/<id>`: hole breakdown, best rounds, player stats; linked from Course Detail page

- [x] **#32 — Player Edit** ✅ BUILT 2026-05-31
  - `GET/POST /players/<id>/edit`: edit name, email, starting handicap, notes
  - Edit button on roster table (admin only) and player profile page header
  - `notes` column added to players table via `migrate_player_notes.py` (already applied)
  - Duplicate name check; graceful fallback if notes column absent

- [x] **#36 — League Forum / Message Board** ✅ BUILT 2026-06-01
  - `/forum` topic list (paginated, pinned topics float up, locked badge); `/forum/new` create; `/forum/<id>` thread view
  - Members post topics + replies; admin can pin, lock, delete topics, delete replies
  - `forum_topics` + `forum_replies` tables; "Forum" in nav + dashboard tile
  - `routes/forum.py` blueprint; 3 templates; CSS; registered in app.py

- [x] **#35 — Dashboard League Activity Feed** ✅ BUILT 2026-06-01
  - Unified "League Activity" section on dashboard below activity columns
  - Merges `league_events` (round_completed, sub_assigned, etc.) + recent announcements
  - Type icons, color-coded chips, relative timestamps; "View →" links for scorecards/announcements
  - Empty state shown until league plays rounds; `create_league_event()` already fires on score save

- [x] **#34 — Points Trend Chart** ✅ BUILT 2026-05-31
  - New "Trend" tab in standings; canvas line chart of cumulative pts/week per team
  - Team toggle legend, per-week + cumulative data table, 15-color palette
  - `trend()` + `trend_current()` routes in standings.py; trend.html template
  - Trend tab added to all 6 standings subnavs

- [x] **#33 — Individual Player Standings** ✅ BUILT 2026-05-31
  - New "Individual" tab in standings subnav at `/standings/<id>/individual`
  - Leader cards (points, scoring, birdies, eagles), full player table with rank, W–T–L, scoring avg, best round, birdie/eagle/par/bogey counts
  - Tab link added to all 5 standings subnavs

- [x] **#31 — Email notifications** ✅ BUILT 2026-05-31
  - SMTP config columns on `leagues` table; `routes/email_config.py` blueprint
  - Auto-email on announcements + round score posting; manual blast to all players; test send
  - Admin settings at `/admin/email`; "📧 Email Settings" button in Admin Panel

---

- [x] **#37 — Player Nickname System** ✅ BUILT 2026-06-03
  - `player_nicknames` table (nickname_id, player_id, league_id, nickname, is_primary)
  - Admin: add/delete/set-primary nicknames on player profile page
  - Primary nickname shown as badge on: player profile header, roster table, score entry rows, score view rows
  - `_get_nickname_map()` helper gracefully handles pre-migration state
  - `migrate_player_nicknames.py` — run manually

- [x] **#38 — Player vs Player Comparison Page** ✅ BUILT 2026-06-03
  - `GET /players/compare?p1=<id>&p2=<id>` — side-by-side comparison page
  - H2H record (W–T–L when on opposite teams same role), career stats bars (avg gross, best round, HCP, pts, rounds)
  - Scoring distribution: Eagle/Birdie/Par/Bogey/Dbl+ % with horizontal bar charts (color-coded)
  - Handicap trend canvas chart: dual line (P1=blue, P2=red) over full career history
  - Direct H2H matchups table + Rounds as Partners table; Scorecard links on each row
  - "⚔️ Compare" button on player profile (pre-fills P1); "Compare" link in roster admin actions; dashboard tile

## GLT features we intentionally skip (out of scope for self-hosted)
- Android/iOS native apps (we have mobile web)
- Extended League upgrade (200 players/60 rounds) — our app is uncapped
- Image Gallery / Document Library upgrade
- USGA slope/rating handicap (we use par-based by design)
- Multi-league user accounts (future)

---

## Priority reasoning
Order balances user value vs. implementation complexity:
1. Tiebreakers (#19): schema complete, closes a real admin pain point, standings critical path
2. Tee sheet (#20): data complete, simple printable page, popular request
3. Notifications (#21): schema exists, nice UX polish
4. Color coding (#22): pure CSS/JS, zero risk, big visual win
5. Per-hole stats (#23): data exists, extends existing Records/Stats pages naturally
6. Per-player tee in score entry (#27): schema exists, completes partia