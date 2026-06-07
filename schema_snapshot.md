# Schema Snapshot — BetterGolfLeagueTracker
Captured: 2026-06-06 from `D:\GolfLeague\Database\golf_league.db`
Total tables: 47 (including `sqlite_sequence`)

---

## Table List

absent_player_policies, archive_settings, contest_results, contests, courses,
dues_payments, forum_replies, forum_topics, handicap_history, hole_scores,
holes, league_events, league_nav_settings, league_settings, leagues,
match_results, matchups, notification_reads, notification_settings, notifications,
permissions, platform_settings, player_absences, players, playoff_brackets,
playoff_matchups, report_parameters, report_templates, roles,
round_skins_participants, round_skins_settings, rounds, schedule_settings,
score_submission_details, score_submissions, scorecards, season_standings,
seasons, skins_config, skins_results, sub_requests, teams, tees,
tiebreaker_settings, user_league_roles, users

---

## CREATE TABLE Statements (SQLite syntax)

```sql
CREATE TABLE absent_player_policies (
    policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE archive_settings (
    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE contest_results (
    result_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id  INTEGER NOT NULL REFERENCES contests(contest_id) ON DELETE CASCADE,
    player_id   INTEGER NOT NULL,
    value_text  TEXT,
    value_num   REAL,
    hole_number INTEGER,
    notes       TEXT,
    created_date TEXT DEFAULT (date('now'))
);

CREATE TABLE contests (
    contest_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id    INTEGER NOT NULL,
    league_id    INTEGER NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT,
    week_num     INTEGER,
    contest_type TEXT DEFAULT 'other',
    created_date TEXT DEFAULT (date('now'))
);

CREATE TABLE courses (
    course_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE dues_payments (
    payment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id    INTEGER NOT NULL,
    season_id    INTEGER NOT NULL,
    player_id    INTEGER NOT NULL,
    amount       REAL NOT NULL DEFAULT 0,
    paid_date    TEXT,
    method       TEXT,
    notes        TEXT,
    created_date TEXT DEFAULT (date('now'))
);

CREATE TABLE forum_replies (
    reply_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id   INTEGER NOT NULL REFERENCES forum_topics(topic_id) ON DELETE CASCADE,
    league_id  INTEGER NOT NULL,
    body       TEXT NOT NULL,
    author_id  INTEGER,
    author_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE forum_topics (
    topic_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id  INTEGER NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    author_id  INTEGER,
    author_name TEXT NOT NULL,
    pinned     INTEGER NOT NULL DEFAULT 0,
    locked     INTEGER NOT NULL DEFAULT 0,
    reply_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE handicap_history (
    handicap_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE hole_scores (
    hole_score_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scorecard_id INTEGER NOT NULL,
    hole_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    gross_score INTEGER NOT NULL,
    net_score REAL,
    score_differential INTEGER,
    FOREIGN KEY (scorecard_id) REFERENCES scorecards(scorecard_id),
    FOREIGN KEY (hole_id) REFERENCES holes(hole_id)
);

CREATE TABLE holes (
    hole_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tee_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    par INTEGER NOT NULL,
    handicap_index INTEGER,
    distance_yards INTEGER,
    FOREIGN KEY (tee_id) REFERENCES tees(tee_id)
);

CREATE TABLE league_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    season_id INTEGER,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    ref_id INTEGER
);

CREATE TABLE league_nav_settings (
    nav_setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    page_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    display_order INTEGER,
    display_name TEXT,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE league_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE leagues (
    league_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    login_code TEXT
);

CREATE TABLE match_results (
    match_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE matchups (
    matchup_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE notification_reads (
    read_id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id INTEGER NOT NULL,
    user_id INTEGER,
    session_key TEXT,
    read_at TEXT NOT NULL,
    UNIQUE(notification_id, user_id)
);

CREATE TABLE notification_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    delivery_method TEXT NOT NULL DEFAULT 'in_app',
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_date TEXT NOT NULL,
    display_until TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE permissions (
    permission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    resource TEXT NOT NULL,
    can_read INTEGER NOT NULL DEFAULT 0,
    can_write INTEGER NOT NULL DEFAULT 0,
    can_delete INTEGER NOT NULL DEFAULT 0,
    scope TEXT NOT NULL DEFAULT 'own_league',
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE platform_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE player_absences (
    absence_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE players (
    player_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE playoff_brackets (
    bracket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    total_teams INTEGER NOT NULL,
    current_round INTEGER NOT NULL DEFAULT 1,
    created_date TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE playoff_matchups (
    matchup_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE report_parameters (
    parameter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    parameter_name TEXT NOT NULL,
    parameter_type TEXT NOT NULL,
    default_value TEXT,
    required INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (template_id) REFERENCES report_templates(template_id)
);

CREATE TABLE report_templates (
    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE roles (
    role_id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE round_skins_participants (
    participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    paid_in INTEGER NOT NULL DEFAULT 0,
    amount_paid REAL,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE round_skins_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    amount_override REAL,
    gross_net_override TEXT,
    carried_over_amount REAL NOT NULL DEFAULT 0,
    notes TEXT,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id)
);

CREATE TABLE rounds (
    round_id INTEGER PRIMARY KEY AUTOINCREMENT,
    matchup_id INTEGER,
    season_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    tee_id INTEGER NOT NULL,
    round_date TEXT NOT NULL,
    round_number INTEGER,
    notes TEXT,
    FOREIGN KEY (matchup_id) REFERENCES matchups(matchup_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id),
    FOREIGN KEY (tee_id) REFERENCES tees(tee_id)
);

CREATE TABLE schedule_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    schedule_type TEXT NOT NULL DEFAULT 'round_robin',
    avoid_rematches INTEGER NOT NULL DEFAULT 1,
    bye_point_policy TEXT NOT NULL DEFAULT 'none',
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE score_submission_details (
    detail_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    player_id     INTEGER NOT NULL,
    hole_number   INTEGER NOT NULL,
    gross_score   INTEGER NOT NULL,
    FOREIGN KEY (submission_id) REFERENCES score_submissions(submission_id),
    FOREIGN KEY (player_id)     REFERENCES players(player_id)
);

CREATE TABLE score_submissions (
    submission_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    matchup_id     INTEGER NOT NULL,
    season_id      INTEGER NOT NULL,
    submitter_name TEXT,
    course_id      INTEGER,
    tee_id         INTEGER,
    round_date     TEXT,
    submitted_at   TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    admin_note     TEXT,
    reviewed_at    TEXT,
    FOREIGN KEY (matchup_id) REFERENCES matchups(matchup_id),
    FOREIGN KEY (season_id)  REFERENCES seasons(season_id)
);

CREATE TABLE scorecards (
    scorecard_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id),
    FOREIGN KEY (sub_for_player_id) REFERENCES players(player_id),
    FOREIGN KEY (approved_by_user_id) REFERENCES users(user_id)
);

CREATE TABLE season_standings (
    standing_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE seasons (
    season_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    season_name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE skins_config (
    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    default_amount REAL,
    default_gross_net TEXT NOT NULL DEFAULT 'gross',
    handicap_percent REAL NOT NULL DEFAULT 90.0,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE skins_results (
    skin_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    winner_player_id INTEGER,
    skins_won INTEGER,
    payout REAL,
    carried_over INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (winner_player_id) REFERENCES players(player_id)
);

CREATE TABLE sub_requests (
    request_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id      INTEGER NOT NULL,
    season_id      INTEGER NOT NULL,
    matchup_id     INTEGER NOT NULL,
    player_id      INTEGER NOT NULL,
    notes          TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    sub_player_id  INTEGER,
    admin_notes    TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    FOREIGN KEY (matchup_id)    REFERENCES matchups(matchup_id),
    FOREIGN KEY (player_id)     REFERENCES players(player_id),
    FOREIGN KEY (sub_player_id) REFERENCES players(player_id)
);

CREATE TABLE teams (
    team_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE tees (
    tee_id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE tiebreaker_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    priority_1 TEXT NOT NULL DEFAULT 'head_to_head',
    priority_2 TEXT NOT NULL DEFAULT 'points_percentage',
    priority_3 TEXT NOT NULL DEFAULT 'all_play_record',
    priority_4 TEXT NOT NULL DEFAULT 'scoring_average',
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE user_league_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
```

---

## Notes for Postgres Schema (step 3.1)

- All `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
- All `TEXT` columns that store dates/timestamps → `TEXT` is fine (app stores as ISO strings) OR convert to `TIMESTAMP`/`DATE` (simpler to keep as TEXT for now)
- `DEFAULT (datetime('now'))` → `DEFAULT NOW()`
- `DEFAULT (date('now'))` → `DEFAULT CURRENT_DATE`
- `BOOLEAN` columns stored as INTEGER (0/1) → can keep as `INTEGER` or convert to `BOOLEAN`
- `REAL` → `REAL` or `DOUBLE PRECISION` in Postgres (both work)
- Tables NOT in the live DB yet (created by migrate scripts not yet run):
  - `handicap_adjustments` (migrate_handicap_adjustments.py — needs manual run)
  - `player_availability` (migrate_player_availability.py — needs manual run)
  - `player_nicknames` (migrate_player_nicknames.py — needs manual run)
  - `player_registrations` (already applied per memory.md)
  - `week_notes` (applied per run #6)
  - `forum_topics`, `forum_replies` (applied per run #6)
  - `dues_payments` (applied per run #6)
  - `sub_requests` (applied per run #6)
  - `contests`, `contest_results` (applied per run #6)
