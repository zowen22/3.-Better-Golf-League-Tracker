-- schema_postgres.sql
-- PostgreSQL equivalent of init_db.py's SQLite SCHEMA.
-- Conversions applied:
--   INTEGER PRIMARY KEY AUTOINCREMENT  -> SERIAL PRIMARY KEY
--   DEFAULT (datetime('now'))          -> DEFAULT CURRENT_TIMESTAMP
--   DEFAULT (date('now'))              -> DEFAULT CURRENT_DATE
-- Everything else (TEXT, REAL, INTEGER, UNIQUE, FOREIGN KEY, ON DELETE CASCADE)
-- is valid as-is in Postgres.

CREATE TABLE IF NOT EXISTS absent_player_policies (
    policy_id SERIAL PRIMARY KEY,
    policy_name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS leagues (
    league_id SERIAL PRIMARY KEY,
    league_name TEXT NOT NULL,
    created_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_by_user_id INTEGER,
    admin_password_hash TEXT,
    member_password_hash TEXT,
    email_enabled INTEGER DEFAULT 0,
    smtp_host TEXT DEFAULT NULL,
    smtp_port INTEGER DEFAULT 587,
    smtp_user TEXT DEFAULT NULL,
    smtp_password TEXT DEFAULT NULL,
    smtp_from_email TEXT DEFAULT NULL,
    smtp_from_name TEXT DEFAULT NULL,
    smtp_use_tls INTEGER DEFAULT 1,
    email_on_announcement INTEGER DEFAULT 1,
    email_on_round_posted INTEGER DEFAULT 1,
    email_on_sub_assigned INTEGER DEFAULT 0,
    public_enabled INTEGER DEFAULT 0,
    public_slug TEXT DEFAULT NULL,
    reg_enabled INTEGER DEFAULT 0,
    reg_welcome_msg TEXT DEFAULT NULL,
    api_key TEXT DEFAULT NULL,
    login_code TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS roles (
    role_id SERIAL PRIMARY KEY,
    role_name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS permissions (
    permission_id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL,
    resource TEXT NOT NULL,
    can_read INTEGER NOT NULL DEFAULT 0,
    can_write INTEGER NOT NULL DEFAULT 0,
    can_delete INTEGER NOT NULL DEFAULT 0,
    scope TEXT NOT NULL DEFAULT 'own_league',
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE IF NOT EXISTS user_league_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE IF NOT EXISTS platform_settings (
    setting_id SERIAL PRIMARY KEY,
    allow_gross_net_toggle INTEGER NOT NULL DEFAULT 1,
    allow_holes_setting INTEGER NOT NULL DEFAULT 1,
    allow_handicap_percent_change INTEGER NOT NULL DEFAULT 1,
    allow_negative_handicaps INTEGER NOT NULL DEFAULT 1,
    max_handicap_index_ceiling REAL NOT NULL DEFAULT 54.0,
    allow_playoff_config INTEGER NOT NULL DEFAULT 1,
    allow_finals_weeks_config INTEGER NOT NULL DEFAULT 1,
    max_playoff_teams_allowed INTEGER NOT NULL DEFAULT 8,
    allow_skins_config INTEGER NOT NULL DEFAULT 1,
    allow_absent_player_config INTEGER NOT NULL DEFAULT 1,
    allow_custom_points INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS seasons (
    season_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS league_settings (
    setting_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    holes_per_round INTEGER NOT NULL DEFAULT 9,
    scoring_type TEXT NOT NULL DEFAULT 'net',
    match_play_points_per_hole INTEGER NOT NULL DEFAULT 1,
    match_play_overall_point INTEGER NOT NULL DEFAULT 1,
    ab_designation_method TEXT NOT NULL DEFAULT 'weekly',
    absent_player_policy_id INTEGER,
    playoff_teams INTEGER NOT NULL DEFAULT 4,
    finals_weeks INTEGER NOT NULL DEFAULT 2,
    min_rounds_for_handicap INTEGER NOT NULL DEFAULT 2,
    rounds_to_average INTEGER NOT NULL DEFAULT 4,
    high_scores_to_drop INTEGER NOT NULL DEFAULT 1,
    handicap_percent REAL NOT NULL DEFAULT 90.0,
    max_handicap_index REAL NOT NULL DEFAULT 18.0,
    max_score_over_handicap INTEGER NOT NULL DEFAULT 18,
    negative_handicap_allowed INTEGER NOT NULL DEFAULT 1,
    carry_scores_across_seasons INTEGER NOT NULL DEFAULT 1,
    skins_default_gross_net TEXT NOT NULL DEFAULT 'gross',
    skins_default_amount REAL,
    self_reporting_enabled INTEGER NOT NULL DEFAULT 0,
    self_reporting_requires_approval INTEGER NOT NULL DEFAULT 1,
    skins_self_optin_enabled INTEGER NOT NULL DEFAULT 0,
    diff_calculation_type TEXT NOT NULL DEFAULT 'par',
    max_score_per_hole INTEGER,
    max_score_action TEXT NOT NULL DEFAULT 'warn',
    max_score_message TEXT,
    padding_score_count INTEGER NOT NULL DEFAULT 0,
    low_scores_to_drop INTEGER NOT NULL DEFAULT 0,
    segment_start_week INTEGER DEFAULT NULL,
    segment_end_week INTEGER DEFAULT NULL,
    dues_amount REAL DEFAULT NULL,
    dues_due_date TEXT DEFAULT NULL,
    show_dues_shame_widget INTEGER NOT NULL DEFAULT 0,
    scoring_mode TEXT NOT NULL DEFAULT 'match_play',
    multi_course INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS league_nav_settings (
    nav_setting_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    page_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    display_order INTEGER,
    display_name TEXT,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS courses (
    course_id SERIAL PRIMARY KEY,
    league_id INTEGER,
    course_name TEXT NOT NULL,
    city TEXT,
    state TEXT,
    num_holes INTEGER NOT NULL DEFAULT 18,
    website TEXT,
    notes TEXT,
    is_master_record INTEGER NOT NULL DEFAULT 0,
    created_by_user_id INTEGER,
    created_date TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    default_tee_id INTEGER,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id),
    FOREIGN KEY (default_tee_id) REFERENCES tees(tee_id)
);

CREATE TABLE IF NOT EXISTS tees (
    tee_id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL,
    tee_name TEXT NOT NULL,
    tee_color TEXT,
    nine TEXT NOT NULL DEFAULT 'full',
    slope REAL,
    rating REAL,
    par_total INTEGER NOT NULL,
    gender TEXT NOT NULL DEFAULT 'M',
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);

CREATE TABLE IF NOT EXISTS holes (
    hole_id SERIAL PRIMARY KEY,
    tee_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    par INTEGER NOT NULL,
    handicap_index INTEGER,
    distance_yards INTEGER,
    FOREIGN KEY (tee_id) REFERENCES tees(tee_id)
);

CREATE TABLE IF NOT EXISTS players (
    player_id SERIAL PRIMARY KEY,
    player_code TEXT UNIQUE,
    user_id INTEGER,
    league_id INTEGER NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_date TEXT NOT NULL,
    starting_handicap REAL,
    oldest_score_date TEXT,
    notes TEXT DEFAULT NULL,
    email_opt_out INTEGER DEFAULT 0,
    email_opt_out_round_results INTEGER DEFAULT 0,
    email_opt_out_reminders INTEGER DEFAULT 0,
    preferred_tee_name TEXT DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS player_nicknames (
    nickname_id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    nickname TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, league_id, nickname)
);

CREATE TABLE IF NOT EXISTS apns_tokens (
    token_id   SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS handicap_history (
    handicap_id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL,
    handicap_index REAL NOT NULL,
    calculated_date TEXT NOT NULL,
    round1_id INTEGER,
    round2_id INTEGER,
    round3_id INTEGER,
    round4_id INTEGER,
    differentials_used TEXT,
    differential_dropped REAL,
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS handicap_adjustments (
    adj_id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    adjustment REAL NOT NULL DEFAULT 0,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by_user_id INTEGER,
    UNIQUE(player_id, league_id)
);

CREATE TABLE IF NOT EXISTS teams (
    team_id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    player1_id INTEGER,
    player2_id INTEGER,
    division_name TEXT DEFAULT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (player1_id) REFERENCES players(player_id),
    FOREIGN KEY (player2_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS matchups (
    matchup_id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    scheduled_date TEXT,
    team1_id INTEGER,
    team2_id INTEGER,
    course_id INTEGER,
    tee_id INTEGER,
    course_confirmed INTEGER NOT NULL DEFAULT 0,
    is_bye INTEGER NOT NULL DEFAULT 0,
    bye_team_id INTEGER,
    status TEXT NOT NULL DEFAULT 'scheduled',
    notes TEXT,
    tee_time TEXT,
    starting_hole INTEGER NOT NULL DEFAULT 1,
    week_type TEXT NOT NULL DEFAULT 'Normal',
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (team1_id) REFERENCES teams(team_id),
    FOREIGN KEY (team2_id) REFERENCES teams(team_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id),
    FOREIGN KEY (tee_id) REFERENCES tees(tee_id)
);

CREATE TABLE IF NOT EXISTS rounds (
    round_id SERIAL PRIMARY KEY,
    matchup_id INTEGER UNIQUE,
    season_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    tee_id INTEGER NOT NULL,
    round_date TEXT NOT NULL,
    round_number INTEGER,
    notes TEXT,
    entered_by_user_id INTEGER,
    FOREIGN KEY (matchup_id) REFERENCES matchups(matchup_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id),
    FOREIGN KEY (tee_id) REFERENCES tees(tee_id),
    FOREIGN KEY (entered_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS scorecards (
    scorecard_id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    team_id INTEGER,
    handicap_at_time_of_play REAL,
    is_sub INTEGER NOT NULL DEFAULT 0,
    sub_for_player_id INTEGER,
    self_reported INTEGER NOT NULL DEFAULT 0,
    approved INTEGER NOT NULL DEFAULT 0,
    approved_by_user_id INTEGER,
    tee_id INTEGER REFERENCES tees(tee_id),
    is_absent INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id),
    FOREIGN KEY (sub_for_player_id) REFERENCES players(player_id),
    FOREIGN KEY (approved_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS hole_scores (
    hole_score_id SERIAL PRIMARY KEY,
    scorecard_id INTEGER NOT NULL,
    hole_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    gross_score INTEGER NOT NULL,
    net_score REAL,
    score_differential INTEGER,
    FOREIGN KEY (scorecard_id) REFERENCES scorecards(scorecard_id),
    FOREIGN KEY (hole_id) REFERENCES holes(hole_id)
);

CREATE TABLE IF NOT EXISTS match_results (
    match_result_id SERIAL PRIMARY KEY,
    matchup_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    hole_points_won REAL,
    overall_point_won REAL,
    total_points REAL,
    opponent_player_id INTEGER,
    FOREIGN KEY (matchup_id) REFERENCES matchups(matchup_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (opponent_player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS season_standings (
    standing_id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    matches_played INTEGER NOT NULL DEFAULT 0,
    total_points REAL NOT NULL DEFAULT 0,
    points_against REAL NOT NULL DEFAULT 0,
    points_percentage REAL,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    ties INTEGER NOT NULL DEFAULT 0,
    bye_weeks INTEGER NOT NULL DEFAULT 0,
    head_to_head_record TEXT,
    last_3_form TEXT,
    playoff_seed INTEGER,
    playoff_qualified INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS schedule_settings (
    setting_id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL,
    schedule_type TEXT NOT NULL DEFAULT 'round_robin',
    avoid_rematches INTEGER NOT NULL DEFAULT 1,
    bye_point_policy TEXT NOT NULL DEFAULT 'none',
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS tiebreaker_settings (
    setting_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    priority_1 TEXT NOT NULL DEFAULT 'head_to_head',
    priority_2 TEXT NOT NULL DEFAULT 'points_percentage',
    priority_3 TEXT NOT NULL DEFAULT 'all_play_record',
    priority_4 TEXT NOT NULL DEFAULT 'scoring_average',
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS skins_config (
    config_id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    default_amount REAL,
    default_gross_net TEXT NOT NULL DEFAULT 'gross',
    handicap_percent REAL NOT NULL DEFAULT 90.0,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS skins_results (
    skin_id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    winner_player_id INTEGER,
    skins_won INTEGER,
    payout REAL,
    carried_over INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (winner_player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS round_skins_settings (
    setting_id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL,
    amount_override REAL,
    gross_net_override TEXT,
    carried_over_amount REAL NOT NULL DEFAULT 0,
    notes TEXT,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id)
);

CREATE TABLE IF NOT EXISTS round_skins_participants (
    participant_id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    paid_in INTEGER NOT NULL DEFAULT 0,
    amount_paid REAL,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS player_absences (
    absence_id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    sub_player_id INTEGER,
    reason TEXT,
    excused INTEGER NOT NULL DEFAULT 0,
    matchup_id INTEGER REFERENCES matchups(matchup_id),
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (sub_player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS sub_requests (
    request_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    matchup_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    sub_player_id INTEGER,
    admin_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (matchup_id) REFERENCES matchups(matchup_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (sub_player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_date TEXT NOT NULL,
    display_until TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS notification_reads (
    read_id SERIAL PRIMARY KEY,
    notification_id INTEGER NOT NULL,
    user_id INTEGER,
    session_key TEXT,
    read_at TEXT NOT NULL,
    UNIQUE(notification_id, user_id)
);

CREATE TABLE IF NOT EXISTS notification_settings (
    setting_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    delivery_method TEXT NOT NULL DEFAULT 'in_app',
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS league_events (
    event_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_id INTEGER,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    ref_id INTEGER
);

CREATE TABLE IF NOT EXISTS archive_settings (
    archive_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    visible_to_members INTEGER NOT NULL DEFAULT 1,
    locked INTEGER NOT NULL DEFAULT 1,
    unlocked_by_user_id INTEGER,
    unlock_date TEXT,
    unlock_reason TEXT,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (unlocked_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS playoff_brackets (
    bracket_id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    total_teams INTEGER NOT NULL,
    current_round INTEGER NOT NULL DEFAULT 1,
    created_date TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS playoff_matchups (
    matchup_id SERIAL PRIMARY KEY,
    bracket_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    team1_id INTEGER,
    team2_id INTEGER,
    team1_points REAL,
    team2_points REAL,
    winner_team_id INTEGER,
    is_finals INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (bracket_id) REFERENCES playoff_brackets(bracket_id),
    FOREIGN KEY (team1_id) REFERENCES teams(team_id),
    FOREIGN KEY (team2_id) REFERENCES teams(team_id),
    FOREIGN KEY (winner_team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS contests (
    contest_id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    week_num INTEGER,
    contest_type TEXT DEFAULT 'other',
    created_date TEXT DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS contest_results (
    result_id SERIAL PRIMARY KEY,
    contest_id INTEGER NOT NULL REFERENCES contests(contest_id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL,
    value_text TEXT,
    value_num REAL,
    hole_number INTEGER,
    notes TEXT,
    created_date TEXT DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS dues_payments (
    payment_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    paid_date TEXT,
    method TEXT,
    notes TEXT,
    created_date TEXT DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS forum_topics (
    topic_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    author_id INTEGER,
    author_name TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0,
    reply_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS forum_replies (
    reply_id SERIAL PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES forum_topics(topic_id) ON DELETE CASCADE,
    league_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    author_id INTEGER,
    author_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS score_submissions (
    submission_id SERIAL PRIMARY KEY,
    matchup_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    submitter_name TEXT,
    course_id INTEGER,
    tee_id INTEGER,
    round_date TEXT,
    submitted_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    admin_note TEXT,
    reviewed_at TEXT,
    FOREIGN KEY (matchup_id) REFERENCES matchups(matchup_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS score_submission_details (
    detail_id SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    gross_score INTEGER NOT NULL,
    FOREIGN KEY (submission_id) REFERENCES score_submissions(submission_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS report_templates (
    template_id SERIAL PRIMARY KEY,
    report_name TEXT NOT NULL,
    description TEXT,
    report_type TEXT NOT NULL,
    is_site_default INTEGER NOT NULL DEFAULT 0,
    league_id INTEGER,
    created_by_user_id INTEGER,
    created_date TEXT NOT NULL,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS report_parameters (
    parameter_id SERIAL PRIMARY KEY,
    template_id INTEGER NOT NULL,
    parameter_name TEXT NOT NULL,
    parameter_type TEXT NOT NULL,
    default_value TEXT,
    required INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (template_id) REFERENCES report_templates(template_id)
);

CREATE TABLE IF NOT EXISTS player_registrations (
    reg_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    starting_handicap REAL DEFAULT 18.0,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,
    reviewed_by_user_id INTEGER,
    player_id INTEGER
);

CREATE TABLE IF NOT EXISTS player_availability (
    avail_id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    available INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, league_id, season_id, week_number)
);

CREATE TABLE IF NOT EXISTS week_notes (
    note_id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(league_id, season_id, week_number)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_matchups_season_status_bye ON matchups(season_id, status, is_bye);
CREATE INDEX IF NOT EXISTS idx_match_results_matchup_team ON match_results(matchup_id, team_id);
CREATE INDEX IF NOT EXISTS idx_scorecards_round_player    ON scorecards(round_id, player_id);
CREATE INDEX IF NOT EXISTS idx_hole_scores_scorecard      ON hole_scores(scorecard_id);
CREATE INDEX IF NOT EXISTS idx_rounds_matchup_season      ON rounds(matchup_id, season_id);
CREATE INDEX IF NOT EXISTS idx_players_league             ON players(league_id);
CREATE INDEX IF NOT EXISTS idx_teams_season_league        ON teams(season_id, league_id);
CREATE INDEX IF NOT EXISTS idx_handicap_history_player    ON handicap_history(player_id, calculated_date DESC, handicap_id DESC);
CREATE INDEX IF NOT EXISTS idx_seasons_league             ON seasons(league_id);
CREATE INDEX IF NOT EXISTS idx_league_settings_season     ON league_settings(season_id, league_id);

-- ── API infrastructure ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS course_api_cache (
    api_course_id  INTEGER PRIMARY KEY,
    response_json  TEXT    NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_request_log (
    log_id        SERIAL PRIMARY KEY,
    endpoint      TEXT    NOT NULL,
    league_id     INTEGER,
    user_id       INTEGER,
    response_code INTEGER,
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_request_log_month        ON api_request_log (DATE_TRUNC('month', requested_at));
CREATE INDEX IF NOT EXISTS idx_api_request_log_league_month ON api_request_log (league_id, DATE_TRUNC('month', requested_at));
CREATE INDEX IF NOT EXISTS idx_api_request_log_league_time  ON api_request_log (league_id, requested_at DESC);
