# StatusReport — BetterGolfLeagueTracker
_Last updated: 2026-06-06_

## Current Stage
Automated run #15 complete. Playoff bracket print view added.

## Recent Wins
- **Playoff Bracket Print View** — "🖨 Print Bracket" button + `@media print` CSS; landscape layout, clean bracket, winner/loser styling (2026-06-07)
- **Score Entry Discoverability** — "🎯 Enter Scores" button on Next Round card in admin overview (2026-06-06)
- **Score Entry Tee Selector Cleanup** — Per-player tee dropdowns filter to matching nine; main dropdown shows nine in label (2026-06-06)

## Next Actions
1. **Run migrate_week_notes.py** — creates `week_notes` table (manual step)
2. **Run migrate_player_nicknames.py** — creates `player_nicknames` table (manual step)
3. **Run migrate_api_key.py** — adds `api_key` column to leagues (manual step)
4. Next feature candidates: Playoff bracket print view · Season-end awards certificate · Score import CSV for 18-hole rounds

## Blockers
None.
