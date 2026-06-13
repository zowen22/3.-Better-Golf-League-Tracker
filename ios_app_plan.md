# iOS App — Development Plan
**Platform:** SwiftUI (iOS 17+) · **Backend:** Flask + PostgreSQL (existing)
**Created:** 2026-06-02 · **Updated:** 2026-06-13

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   SwiftUI iOS App                        │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Auth/JWT   │  │ Networking   │  │  Core Data     │  │
│  │  Keychain   │  │ (URLSession) │  │  (offline)     │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
│  ┌──────────────────────────────────────────────────┐    │
│  │          Feature Modules (MVVM)                  │    │
│  │  Schedule · Standings · Score Entry · Admin      │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌─────────────────────┐                                  │
│  │  Vision Framework   │  (on-device OCR — no server)    │
│  │  AVFoundation       │                                  │
│  └─────────────────────┘                                  │
└─────────────────────────────────────────────────────────┘
                          │  JWT Bearer tokens
                          ▼
┌─────────────────────────────────────────────────────────┐
│          Flask REST API  /api/v1/                        │
│  Auth · Schedule · Standings · Scores · Admin · APNs    │
└─────────────────────────────────────────────────────────┘
```

**Key decisions:**
- Apple Vision on-device OCR — no image upload endpoint needed; all parsing runs client-side
- Separate `/api/v1/` Flask blueprint — existing web routes unchanged
- JWT Bearer tokens (PyJWT) for stateless mobile auth alongside existing session cookies
- MVVM throughout SwiftUI; `@Observable` (Swift 5.9) for view models
- Core Data for offline scorecard draft storage and sync queue
- APNs for native push notifications

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | SwiftUI (iOS 17+), `NavigationStack`, tab bar |
| Architecture | MVVM, `@Observable` macros |
| Networking | `URLSession` + `async/await`, `Codable` models |
| Auth | JWT (PyJWT on Flask), `Security.framework` Keychain storage |
| OCR | `Vision.framework` `VNRecognizeTextRequest` |
| Camera | `AVFoundation` capture session |
| Offline | Core Data, `NSPersistentCloudKitContainer` optional |
| Push | Apple Push Notification service (APNs), `UserNotifications` |
| Backend additions | PyJWT, `flask-apns2` or direct `httpx` APNs sender |

---

## Backend Changes Required

All mobile-facing endpoints live in a new `app/routes/api.py` blueprint, registered at `/api/v1/`. Existing web routes are untouched.

### New Flask files
| File | Purpose |
|------|---------|
| `app/routes/api.py` | New blueprint: all `/api/v1/` routes |
| `app/utils/jwt_utils.py` | `create_token()`, `decode_token()`, `require_jwt` decorator |
| `app/schema_migrations/add_player_nicknames.sql` | `player_nicknames` table |
| `app/schema_migrations/add_apns_tokens.sql` | `apns_tokens` table |
| `app/utils/push.py` | APNs sender utility |

### New DB tables

```sql
-- Migration: add_player_nicknames.sql
CREATE TABLE player_nicknames (
    nickname_id  SERIAL PRIMARY KEY,
    player_id    INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    nickname     TEXT    NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX ON player_nicknames (player_id, lower(nickname));

-- Migration: add_apns_tokens.sql
CREATE TABLE apns_tokens (
    token_id   SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token      TEXT    NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id)
);
```

---

## Phase 0: Backend Prep *(prerequisite for all app phases)*

### WP0.1 — JWT Auth Endpoints
**@claude**

| Task | Detail |
|------|--------|
| Add PyJWT to `requirements.txt` | `PyJWT>=2.8.0` |
| Create `app/utils/jwt_utils.py` | `create_token(user_id, league_id, role)` → signed JWT (24h expiry); `decode_token(token)` → payload or raises; `require_jwt` decorator wraps API route functions — reads `Authorization: Bearer <token>`, injects `g.jwt_user` |
| `POST /api/v1/auth/login` | Accepts `{email, password, league_code}`; validates against existing `users` + `league_members` tables; returns `{token, user_id, league_id, role, display_name}` |
| `POST /api/v1/auth/refresh` | Accepts expiring token within 7-day grace window; returns fresh token; rejects if older than 7 days |
| `GET /api/v1/auth/me` | Returns current user profile from JWT payload (no DB hit) |

**Acceptance:** Postman/curl: POST login with valid creds → 200 + JWT; invalid creds → 401; expired token on protected route → 401.

---

### WP0.2 — Core Read Endpoints
**@claude**

All routes require `@require_jwt`. Return `application/json`.

| Endpoint | Response shape |
|----------|---------------|
| `GET /api/v1/schedule` | `[{matchup_id, week_number, scheduled_date, tee_time, starting_hole, status, course_name, tee_name, team1: {team_id, name, players: [{player_id, display_name, handicap}]}, team2: {...}}]` for current season |
| `GET /api/v1/schedule/<matchup_id>` | Single matchup + players + any existing round/scorecard data |
| `GET /api/v1/standings` | `[{team_id, team_name, points, wins, losses, ties, rank}]` |
| `GET /api/v1/players/nicknames` | `[{player_id, display_name, nicknames: ["Ziggy", ...]}]` — used client-side for OCR matching |
| `GET /api/v1/scorecards/<round_id>` | Hole-by-hole scores + match results for a completed round |

**Acceptance:** Each endpoint returns well-formed JSON with correct league scoping (JWT league_id filters all queries).

---

### WP0.3 — Score Submission + Admin Endpoints
**@claude**

| Endpoint | Detail |
|----------|--------|
| `POST /api/v1/scores/submit` | Accepts `{matchup_id, tee_id, scores: [{player_id, hole_scores: [int×9or18]}], absences: [{player_id, sub_player_id?}]}`; calls existing `_process_scores()` logic (refactor to be callable without Flask request context); returns `{round_id, match_results}` |
| `GET /api/v1/admin/pending` | `[{self_report_id, player_name, matchup_week, submitted_at, scores_summary}]` — admin-only (role check in JWT) |
| `POST /api/v1/admin/approve/<self_report_id>` | Approves self-report, creates round; returns `{round_id}` |
| `POST /api/v1/admin/lock/<matchup_id>` | Sets `rounds.locked = true` |
| `POST /api/v1/nicknames` | `{player_id, nickname}` → inserts into `player_nicknames`; 409 if duplicate |
| `DELETE /api/v1/nicknames/<nickname_id>` | Deletes nickname (player owner or admin only) |
| `POST /api/v1/apns/register` | `{device_token}` → upserts into `apns_tokens` for current JWT user |

**Note on score submission:** `_process_scores()` currently reads directly from `flask.request.form`. Refactor its internals into `_process_scores_data(db, matchup_id, tee_id, scores_dict, absences_list)` that accepts plain Python dicts — call it from both the web route and the API route.

**Acceptance:** POST /api/v1/scores/submit with valid payload → round created, returns match_results; re-submit same matchup_id → 409 (honoring P1-2 unique constraint once that's added).

---

## Phase 1: App Foundation

### WP1.1 — Xcode Project Setup
**@user**

| Task | Detail |
|------|--------|
| Create new Xcode project | SwiftUI App template, iOS 17 deployment target, bundle ID `com.yourname.golfleaguetracker` |
| Swift Package dependencies | None required initially (all frameworks are system) |
| Folder structure | `App/`, `Features/Auth/`, `Features/Schedule/`, `Features/Standings/`, `Features/ScoreEntry/`, `Features/Admin/`, `Features/Profile/`, `Core/Networking/`, `Core/Persistence/`, `Core/Push/`, `Shared/Models/`, `Shared/Components/` |
| Environment config | `Config.swift` with `baseURL` (debug = `http://localhost:5000`, release = Render URL); loaded from xcconfig |
| App entry point | `BetterGolfTrackerApp.swift` — inject `AuthViewModel` as environment object |

---

### WP1.2 — Networking Layer
**@claude**

| File | Purpose |
|------|---------|
| `Core/Networking/APIClient.swift` | `actor APIClient` — `func request<T: Decodable>(_ endpoint: Endpoint) async throws -> T`; attaches JWT from Keychain; handles 401 → trigger re-auth |
| `Core/Networking/Endpoint.swift` | Enum of all API endpoints with path, method, body; each case produces `URLRequest` |
| `Core/Networking/APIError.swift` | `enum APIError: Error` — unauthorized, serverError(Int), decodingError, noNetwork |
| `Core/Auth/KeychainStore.swift` | `save(token:)`, `loadToken() -> String?`, `deleteToken()` using `Security.framework` |
| `Shared/Models/` | Codable structs mirroring API response shapes: `Matchup`, `Team`, `Player`, `Standing`, `Scorecard`, `HoleScore`, `MatchResult` |

**Acceptance:** Unit test: `APIClient` with mock `URLProtocol` — valid response decodes; 401 response triggers auth callback; network error surfaces as `APIError.noNetwork`.

---

### WP1.3 — Auth Flow
**@claude**

| File | Purpose |
|------|---------|
| `Features/Auth/AuthViewModel.swift` | `@Observable` — `login(email:password:leagueCode:)` async; stores JWT in Keychain; publishes `isAuthenticated`, `currentUser`; `logout()` clears Keychain |
| `Features/Auth/LoginView.swift` | League code field, email, password; "Sign In" button calls `authVM.login()`; shows inline error on 401 |
| `App/RootView.swift` | Reads `authVM.isAuthenticated`; shows `LoginView` or `MainTabView` |
| `App/MainTabView.swift` | 4 tabs: Schedule (calendar icon), Standings (chart), Score Entry (golf flag), Admin (gear — hidden if `role != "admin"`) |

**Acceptance:** Cold launch → LoginView; valid login → MainTabView persists across app restarts; logout clears token and returns to LoginView.

---

## Phase 2: Read Views

### WP2.1 — Schedule View
**@claude**

| File | Purpose |
|------|---------|
| `Features/Schedule/ScheduleViewModel.swift` | Fetches `/api/v1/schedule`; groups matchups by week; `@Observable` |
| `Features/Schedule/ScheduleView.swift` | `List` with section headers per week; each row: teams vs teams, date, status badge (Upcoming/Completed/In Progress) |
| `Features/Schedule/MatchupDetailView.swift` | Shows course, tee, tee time, team roster with handicaps; "Enter Scores" button (admin only, visible if matchup is schedulable); "View Scorecard" if completed |

**Acceptance:** Schedule loads and displays; tapping matchup opens detail; completed matchup shows "View Scorecard" CTA; non-admin sees read-only view.

---

### WP2.2 — Standings View
**@claude**

| File | Purpose |
|------|---------|
| `Features/Standings/StandingsViewModel.swift` | Fetches `/api/v1/standings` |
| `Features/Standings/StandingsView.swift` | Ranked table: position, team name, record (W-L-T), points; pull-to-refresh |

---

### WP2.3 — Scorecard History View
**@claude**

| File | Purpose |
|------|---------|
| `Features/Schedule/ScorecardView.swift` | Grid of 9 or 18 holes; per-player net scores; point totals per hole; match result summary at bottom |

Reachable from MatchupDetailView when `matchup.status == "completed"`.

---

## Phase 3: Manual Score Entry

### WP3.1 — Scorecard Grid Entry
**@claude**

| File | Purpose |
|------|---------|
| `Features/ScoreEntry/ScoreEntryViewModel.swift` | Holds per-player, per-hole score state; validates completeness; computes live points via `ScoreCalculator.swift` |
| `Features/ScoreEntry/ScoreEntryView.swift` | "Manual" / "Camera" choice at top; manual path: player rows × hole columns grid; numeric keyboard; auto-advance to next cell on entry; inline live point calculation |
| `Features/ScoreEntry/ScoreCalculator.swift` | Pure functions: `netScore(gross:handicapStrokes:)`, `matchPlayPoints(net1:net2:)`, `stablefordPoints(net:par:)` — mirrors server logic, used for live display |
| `Features/ScoreEntry/AbsenceSheet.swift` | Bottom sheet: mark absent players, optionally assign sub from matchup's league roster |

**Acceptance:** All 18 hole scores entered → Save button enables; submit → API call; success → MatchupDetailView updated with scorecard.

---

## Phase 4: Camera Score Entry *(priority feature)*

### WP4.1 — Camera Capture
**@claude**

| File | Purpose |
|------|---------|
| `Features/ScoreEntry/CameraView.swift` | `UIViewControllerRepresentable` wrapping `AVCaptureSession`; live preview with crop-guide overlay ("Align scorecard within frame"); shutter button; flash toggle; also supports photo library selection |
| `Features/ScoreEntry/PhotoReviewView.swift` | Shows captured image; "Use This Photo" / "Retake"; passes `UIImage` to OCR pipeline |

**Acceptance:** Camera opens; image captured and passed downstream; photo library fallback works.

---

### WP4.2 — Vision OCR Pipeline
**@claude**

| File | Purpose |
|------|---------|
| `Features/ScoreEntry/OCRService.swift` | `actor OCRService` — `func recognizeScorecard(_ image: UIImage) async throws -> OCRRawResult`; runs `VNRecognizeTextRequest` with `recognitionLevel: .accurate`, `usesLanguageCorrection: false` (numbers shouldn't be language-corrected); returns array of `{text: String, boundingBox: CGRect, confidence: Float}` observations |
| `Features/ScoreEntry/ScorecardParser.swift` | Stateless struct — `parse(observations: [OCRObservation], expectedPlayers: [Player]) -> ParsedScorecard`; layout logic: identify row containing hole numbers (1–18 as anchor), extract columns, assign numeric cells to holes; handles 9-hole rows (front/back split) |

**Parsing strategy:**
1. Find the "hole number row" — the row whose cells most closely match [1..9] or [10..18] in sequence
2. All rows below/above with 9–18 numeric cells are candidate score rows
3. Name extraction: leftmost non-numeric text per candidate row is the player name
4. Total validation: sum extracted hole scores; compare to any cell that matches sum (scorecard-printed total); flag mismatch

**Acceptance:** Unit tests with fixture images of common scorecard layouts (handwritten and printed); parser correctly extracts hole scores with ≥80% accuracy on clean printed scorecards.

---

### WP4.3 — Nickname Matching
**@claude**

| File | Purpose |
|------|---------|
| `Features/ScoreEntry/NicknameMatchService.swift` | `func match(ocrName: String, candidates: [Player]) -> MatchResult`; `MatchResult` is `.confident(Player)`, `.prompt(ocrName: String, suggestedPlayer: Player, confidence: Float)`, or `.unmatched`; algorithm: exact match → confident; case/whitespace normalized match → confident; known nickname match (from pre-fetched `/api/v1/players/nicknames`) → confident; Jaro-Winkler similarity ≥ 0.85 → prompt; below threshold → unmatched |
| `Features/ScoreEntry/NicknamePromptView.swift` | Alert-style sheet: "Scorecard shows '\(ocrName)' — assign to \(suggestedPlayer.name)?" + "Save as nickname" checkbox; or player picker if unmatched |

**Acceptance:** Known nickname "Ziggy" for player "Robert Smith" → silent auto-assign; unknown name "Zigster" → prompt with Jaro-Winkler match; completely unrecognized name → unmatched picker.

---

### WP4.4 — Confirmation + Edit Screen
**@claude**

| File | Purpose |
|------|---------|
| `Features/ScoreEntry/OCRConfirmationView.swift` | Full scorecard grid pre-filled from OCR results; each cell editable inline; totals row auto-calculated; mismatch warning banner: "Calculated total (38) ≠ scorecard total (37) — please verify"; per-player confidence indicator (green/yellow/red dot); "Confirm & Submit" button disabled until all mismatches resolved or explicitly dismissed |
| `Features/ScoreEntry/OCRResultModel.swift` | `struct OCRResultModel` — per player: `ocrName`, `assignedPlayer`, `holeScores: [Int?]`, `totalsRead`, `calculatedTotal`, `confidence` |

**Acceptance:** Mismatch → banner visible, Submit disabled; user edits cell → totals recalculate live; all mismatches resolved → Submit enables.

---

### WP4.5 — Full Camera Entry Integration
**@claude**

Wire the pipeline in `ScoreEntryViewModel`:
1. Camera captures image
2. `OCRService.recognizeScorecard()` → raw observations
3. `ScorecardParser.parse()` → `ParsedScorecard`
4. `NicknameMatchService.match()` for each detected player name
5. Show `NicknamePromptView` for any `.prompt` results (sequential, one per unmatched name)
6. Build `OCRResultModel` and push `OCRConfirmationView`
7. Confirmation "Submit" → same `POST /api/v1/scores/submit` as manual entry

**Error states:** OCR fails to find any score rows → "Couldn't read this scorecard — try Manual entry" with retry; partial parse (some holes missing) → confirmation screen with missing cells highlighted red.

---

## Phase 5: Admin Actions

### WP5.1 — Self-Report Approval
**@claude**

| File | Purpose |
|------|---------|
| `Features/Admin/AdminViewModel.swift` | Fetches `/api/v1/admin/pending`; `approve(selfReportId:)` and `lock(matchupId:)` |
| `Features/Admin/AdminView.swift` | Tab visible only when `role == "admin"`; list of pending self-reports; each row: player name, week, submitted date; swipe-to-approve; detail view shows hole scores before approving |
| `Features/Admin/PendingReportDetailView.swift` | Hole-by-hole scorecard from self-report; "Approve" and "Reject" buttons |

---

### WP5.2 — Score Lock / Unlock
**@claude**

Add to `MatchupDetailView` (admin only): Lock/Unlock toggle button → calls `POST /api/v1/admin/lock/<matchup_id>`; locked rounds show lock icon in schedule list.

---

## Phase 6: Push Notifications

### WP6.1 — APNs Backend Setup
**@user + @claude**

| Task | Owner |
|------|-------|
| Create APNs key in Apple Developer portal (`.p8` file, Key ID, Team ID) | @user |
| Add APNs credentials to Render environment vars: `APNS_KEY_PATH`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID` | @user |
| Create `app/utils/push.py`: async APNs HTTP/2 sender using `httpx` with JWT signing | @claude |
| `POST /api/v1/apns/register` route to store device token | @claude |
| Add push sends to key backend events (see WP6.3) | @claude |

---

### WP6.2 — iOS Notification Registration
**@claude**

| File | Purpose |
|------|---------|
| `Core/Push/PushManager.swift` | Requests `UNUserNotificationCenter` authorization on first login; registers with APNs; sends device token to `/api/v1/apns/register` |
| Notification categories | Define `UNNotificationCategory` for actionable notifications (e.g., approve self-report directly from notification) |

---

### WP6.3 — Notification Event Triggers
**@claude**

| Event | Trigger point in Flask | Notification copy |
|-------|----------------------|------------------|
| Round submitted | After `_process_scores()` completes | "Week \(N) scores are in — view the results" → all league members |
| Self-report submitted | `self_report.py` submit handler | "New score submission from \(player_name) — Week \(N)" → admins only |
| Sub request | Existing sub request handler | "Sub request for Week \(N) — can you play?" → targeted sub |
| Announcement | Existing announcements route | Subject line → all league members |

---

## Phase 7: Offline Support

### WP7.1 — Core Data Model
**@claude**

Entities: `CDMatchup`, `CDScoreEntry` (draft in-progress scorecard with hole scores), `CDABSence`.
`CDScoreEntry` has `syncStatus: String` — `draft`, `pending`, `synced`.

---

### WP7.2 — Offline Scorecard Entry + Sync
**@claude**

| File | Purpose |
|------|---------|
| `Core/Persistence/PersistenceController.swift` | `NSPersistentContainer` setup; `NSPersistentCloudKitContainer` optional for iCloud backup |
| `Core/Persistence/SyncQueue.swift` | On network restore (`NWPathMonitor`), drain any `pending` `CDScoreEntry` records by submitting to `/api/v1/scores/submit`; mark `synced` on 200; surface error for 409 (duplicate) |
| `ScoreEntryViewModel` update | Save to Core Data first; if network available, submit immediately + mark synced; if offline, mark pending and show "Saved offline — will sync when connected" banner |

---

## Development Sequence & Sprint Planning

Sprint order reflects dependencies and delivers highest-value features first:

| Sprint | Phases | Deliverable |
|--------|--------|-------------|
| 1 | WP0.1 + WP0.2 | JWT auth + read API endpoints live on Render |
| 2 | WP1.1 + WP1.2 + WP1.3 | iOS app shell: login → tab bar → schedule/standings visible |
| 3 | WP2.1 + WP2.2 + WP2.3 | Full read-only views (schedule, standings, scorecard history) |
| 4 | WP0.3 (partial) + WP3.1 | Manual score entry: end-to-end submit from phone |
| 5 | WP4.1 + WP4.2 + WP4.3 | Camera capture + OCR pipeline (unit tested, no UI yet) |
| 6 | WP4.4 + WP4.5 | Confirmation screen + full camera entry flow wired |
| 7 | WP5.1 + WP5.2 | Admin: approve self-reports, lock scores |
| 8 | WP6.1 + WP6.2 + WP6.3 | Push notifications |
| 9 | WP7.1 + WP7.2 | Offline support + sync |

**Minimum shippable build (Sprints 1–4):** Auth + read views + manual score entry. Covers ~80% of in-round admin usage without camera.
**Camera milestone (Sprints 1–6):** Full camera entry pipeline live — the primary differentiator.

---

## Decisions Log

| # | Question | Decision | Notes |
|---|----------|----------|-------|
| Q1 | App Store vs TestFlight? | **TestFlight for v1** | No App Store review delay; upgrade path open when going public/SaaS |
| Q2 | Single-league or multi-league auth? | **Single-league v1** (re-login to switch) | JWT already carries `league_id`; in-app league switcher is additive later — no architectural blocker |
| Q3 | Member self-report in app? | **Deferred post-v1** | Admin score entry + read-only views first |
| Q4 | Scoring mode? | **Both match play + Stableford** | Stableford may be used; web app logic already exists (`calc_stableford()`). Blocked on P2-4 audit fix: verify `scoring_mode` column exists in `league_settings`, add migration if missing. iOS `ScoreCalculator.swift` must handle both modes. |

### Auth architecture note (Q2)
Email + password → JWT is safe for monetization. Email/password alone does not trigger Apple's "Sign in with Apple" requirement. That requirement only kicks in when you add any third-party OAuth (Google, Facebook, etc.). If a future SaaS pivot adds social login, adding Sign in with Apple at that point is straightforward — it's purely additive and doesn't change the existing email/password flow.

### Scoring mode note (Q4)
Before Sprint 4 (score submission), resolve web audit P2-4: confirm `scoring_mode` column exists in `league_settings`, add migration `add_scoring_mode.sql` if not. The iOS `ScoreCalculator.swift` should accept a `scoringMode: ScoringMode` parameter (`.matchPlay` / `.stableford`) and branch accordingly — same logic as `scores.py:calc_match_play()` and `calc_stableford()`.

---

*Original camera score entry design spec preserved in commit history. Supersedes `Implementation Path Recommendation` section — SwiftUI confirmed 2026-06-13.*
