-- Performance indexes for BetterGolfLeagueTracker
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run
-- Safe to run multiple times (IF NOT EXISTS is idempotent, no read locks)

-- Core joins hit on every page load
CREATE INDEX IF NOT EXISTS idx_matchups_season_status_bye ON matchups(season_id, status, is_bye);
CREATE INDEX IF NOT EXISTS idx_match_results_matchup_team ON match_results(matchup_id, team_id);
CREATE INDEX IF NOT EXISTS idx_scorecards_round_player    ON scorecards(round_id, player_id);
CREATE INDEX IF NOT EXISTS idx_hole_scores_scorecard      ON hole_scores(scorecard_id);

-- Secondary joins
CREATE INDEX IF NOT EXISTS idx_rounds_matchup_season      ON rounds(matchup_id, season_id);
CREATE INDEX IF NOT EXISTS idx_players_league             ON players(league_id);
CREATE INDEX IF NOT EXISTS idx_teams_season_league        ON teams(season_id, league_id);
CREATE INDEX IF NOT EXISTS idx_handicap_history_player    ON handicap_history(player_id, calculated_date DESC, handicap_id DESC);
CREATE INDEX IF NOT EXISTS idx_seasons_league             ON seasons(league_id);
CREATE INDEX IF NOT EXISTS idx_league_settings_season     ON league_settings(season_id, league_id);
