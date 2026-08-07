-- Enable Row Level Security on every public-schema table.
--
-- Context (2026-08-07): Supabase's security advisor flagged all 64 public
-- tables as rls_disabled (critical) — with RLS off, Supabase's
-- auto-generated PostgREST REST API exposes every table to the anon/
-- authenticated roles with no restriction, regardless of whether the app
-- uses that API surface.
--
-- This app never uses Supabase's client SDK or anon key (confirmed via
-- codebase search) — it talks to Postgres directly via the `postgres`
-- role, which has rolbypassrls=true and therefore ignores RLS entirely.
-- So enabling RLS here has zero effect on the running Flask app or any
-- existing/future league's data; it only closes off the unused REST API
-- path. No policies are attached (intentional, full default-deny for a
-- surface nothing should be hitting).
--
-- Applied directly to production via Supabase MCP apply_migration on
-- 2026-08-07; this file exists to keep the change tracked in the repo.

ALTER TABLE public.absent_player_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leagues ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_league_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.platform_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.league_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.league_nav_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.courses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tees ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.holes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.players ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_nicknames ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.handicap_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.handicap_adjustments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.matchups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scorecards ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hole_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.match_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.season_standings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schedule_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiebreaker_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.skins_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.skins_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.round_skins_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.round_skins_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_absences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sub_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_reads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.league_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.archive_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.playoff_brackets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.playoff_matchups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contest_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dues_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.forum_topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.forum_replies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.score_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.score_submission_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_parameters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.week_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.apns_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.course_api_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_request_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.league_announcements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.announcement_reactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.round_reflections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.round_skins_flight_carryover ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hall_of_fame_winners ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscription_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.password_reset_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.matchup_tee_overrides ENABLE ROW LEVEL SECURITY;
