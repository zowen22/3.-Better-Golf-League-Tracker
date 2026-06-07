# iOS App Plan — BetterGolfLeagueTracker

Created: 2026-06-02

---

## Camera Score Entry — Design Spec

### User Flow

1. **Enter Scores screen** → choice: "Manual" or "Camera"
2. If Camera → **"Who are you uploading for?"** — user selects which players' scores are on this scorecard (multi-select from the matchup's player list)
3. Take photo of scorecard
4. Confirmation screen (see below)

---

### Confirmation Screen Requirements

- Shows parsed hole-by-hole scores assigned to each selected player
- Easy inline editing of any individual hole score
- Software **always calculates totals** (front 9, back 9, total) from the hole scores — never accept the written total on the scorecard as truth
- If the calculated total differs from the OCR-read total, show a notification/warning:
  > "Calculated total (38) differs from scorecard total (37) — please verify"
- User must explicitly confirm before scores are submitted

---

### Nickname / Name Matching

When the OCR-read name on the scorecard is meaningfully different from the player being assigned to that column, prompt:

> "Scorecard shows 'Ziggy' — would you like to save this as a nickname for [Player Name]?"

#### Nickname System Requirements

- **Multiple nicknames per player** (not just one alias)
- Nicknames editable on the player profile page
- Nicknames used for OCR matching in future scans — fuzzy match against all known nicknames
- If nickname already exists in the system, **auto-assign confidently** without prompting

#### OCR Confidence Logic

- Only prompt for nickname assignment if confidence is **below a threshold AND** the name is meaningfully different (not just spacing/capitalization differences)
- High-confidence matches (exact name or known nickname) should silently assign without prompting

---

### Backend Considerations

#### New DB Table: `player_nicknames`

```sql
CREATE TABLE player_nicknames (
    nickname_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    nickname    TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
```

#### OCR Endpoint (Flask backend)

- Accepts: image upload
- Returns: structured JSON
  ```json
  {
    "players": [
      {
        "player_name_read": "Ziggy",
        "confidence": 0.72,
        "hole_scores": [4, 5, 3, 4, 5, 4, 3, 4, 5, 4, 5, 4, 3, 4, 5, 4, 3, 4],
        "totals_read": { "front": 37, "back": 40, "total": 77 }
      }
    ]
  }
  ```

#### Score Submission Endpoint

- Confirmation screen calls a **separate submit endpoint** once user approves
- Keeps the OCR parsing step and the score write step cleanly separated

---

## Other Planned App Features (for reference)

- View schedule, standings, scorecards
- Push notifications for round completions, announcements, sub assignments
- Offline-capable scorecard entry with sync when back on WiFi
- Admin actions: lock/unlock scores, approve self-reports

## Implementation Path Recommendation

1. **PWA first** — lowest lift, works on Safari, no App Store required; quick win
2. **React Native / Expo** — shares JS logic with web app, calls existing Flask API
3. **Native SwiftUI** — best iOS integration (Vision framework for on-device OCR), highest effort; best follow-on after PWA

---

*See also: `memory.md` iOS App TODO item*
