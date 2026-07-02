"""
init_db.py — Creates all database tables if they don't exist.
Called automatically at app startup so the app works on a fresh deployment
(e.g. Render free tier where the filesystem resets on redeploy).
"""
import os
import sqlite3

import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS absent_player_policies (
    policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS leagues (
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

CREATE TABLE IF NOT EXISTS roles (
    role_id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS permissions (
    permission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    resource TEXT NOT NULL,
    can_read INTEGER NOT NULL DEFAULT 0,
    can_write INTEGER NOT NULL DEFAULT 0,
    can_delete INTEGER NOT NULL DEFAULT 0,
    scope TEXT NOT NULL DEFAULT 'own_league',
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE IF NOT EXISTS user_league_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (role_id) REFERENCES roles(role_id)
);

CREATE TABLE IF NOT EXISTS platform_settings (
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

CREATE TABLE IF NOT EXISTS seasons (
    season_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    season_name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS league_settings (
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
    absence_overall_point_policy TEXT NOT NULL DEFAULT 'excused_only',
    temp_handicap_percent_member REAL NOT NULL DEFAULT 90.0,
    temp_handicap_percent_sub REAL NOT NULL DEFAULT 90.0,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS league_nav_settings (
    nav_setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    page_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    display_order INTEGER,
    display_name TEXT,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS courses (
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

CREATE TABLE IF NOT EXISTS tees (
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

CREATE TABLE IF NOT EXISTS holes (
    hole_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tee_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    par INTEGER NOT NULL,
    handicap_index INTEGER,
    distance_yards INTEGER,
    FOREIGN KEY (tee_id) REFERENCES tees(tee_id)
);

CREATE TABLE IF NOT EXISTS players (
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
    preferred_tee_name TEXT DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS player_nicknames (
    nickname_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    nickname TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_id, league_id, nickname)
);

CREATE TABLE IF NOT EXISTS handicap_history (
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

CREATE TABLE IF NOT EXISTS handicap_adjustments (
    adj_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    adjustment REAL NOT NULL DEFAULT 0,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by_user_id INTEGER,
    UNIQUE(player_id, league_id)
);

CREATE TABLE IF NOT EXISTS teams (
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

CREATE TABLE IF NOT EXISTS matchups (
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

CREATE TABLE IF NOT EXISTS rounds (
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

CREATE TABLE IF NOT EXISTS scorecards (
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

CREATE TABLE IF NOT EXISTS hole_scores (
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

CREATE TABLE IF NOT EXISTS match_results (
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

CREATE TABLE IF NOT EXISTS season_standings (
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

CREATE TABLE IF NOT EXISTS schedule_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    schedule_type TEXT NOT NULL DEFAULT 'round_robin',
    avoid_rematches INTEGER NOT NULL DEFAULT 1,
    bye_point_policy TEXT NOT NULL DEFAULT 'none',
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS tiebreaker_settings (
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

CREATE TABLE IF NOT EXISTS skins_config (
    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    default_amount REAL,
    default_gross_net TEXT NOT NULL DEFAULT 'gross',
    handicap_percent REAL NOT NULL DEFAULT 90.0,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS skins_results (
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

CREATE TABLE IF NOT EXISTS round_skins_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    amount_override REAL,
    gross_net_override TEXT,
    carried_over_amount REAL NOT NULL DEFAULT 0,
    notes TEXT,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id)
);

CREATE TABLE IF NOT EXISTS round_skins_participants (
    participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    paid_in INTEGER NOT NULL DEFAULT 0,
    amount_paid REAL,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS player_absences (
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

CREATE TABLE IF NOT EXISTS sub_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_date TEXT NOT NULL,
    display_until TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS notification_reads (
    read_id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id INTEGER NOT NULL,
    user_id INTEGER,
    session_key TEXT,
    read_at TEXT NOT NULL,
    UNIQUE(notification_id, user_id)
);

CREATE TABLE IF NOT EXISTS notification_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    delivery_method TEXT NOT NULL DEFAULT 'in_app',
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS league_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    season_id INTEGER,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    ref_id INTEGER
);

CREATE TABLE IF NOT EXISTS archive_settings (
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

CREATE TABLE IF NOT EXISTS playoff_brackets (
    bracket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    total_teams INTEGER NOT NULL,
    current_round INTEGER NOT NULL DEFAULT 1,
    created_date TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)
);

CREATE TABLE IF NOT EXISTS playoff_matchups (
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

CREATE TABLE IF NOT EXISTS contests (
    contest_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    week_num INTEGER,
    contest_type TEXT DEFAULT 'other',
    created_date TEXT DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS contest_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER NOT NULL REFERENCES contests(contest_id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL,
    value_text TEXT,
    value_num REAL,
    hole_number INTEGER,
    notes TEXT,
    created_date TEXT DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS dues_payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    paid_date TEXT,
    method TEXT,
    notes TEXT,
    created_date TEXT DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS forum_topics (
    topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    author_id INTEGER,
    author_name TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0,
    reply_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS forum_replies (
    reply_id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES forum_topics(topic_id) ON DELETE CASCADE,
    league_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    author_id INTEGER,
    author_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS score_submissions (
    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    hole_number INTEGER NOT NULL,
    gross_score INTEGER NOT NULL,
    FOREIGN KEY (submission_id) REFERENCES score_submissions(submission_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS report_templates (
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

CREATE TABLE IF NOT EXISTS report_parameters (
    parameter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    parameter_name TEXT NOT NULL,
    parameter_type TEXT NOT NULL,
    default_value TEXT,
    required INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (template_id) REFERENCES report_templates(template_id)
);

CREATE TABLE IF NOT EXISTS player_registrations (
    reg_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    starting_handicap REAL DEFAULT 18.0,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at TEXT,
    reviewed_by_user_id INTEGER,
    player_id INTEGER
);

CREATE TABLE IF NOT EXISTS player_availability (
    avail_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    available INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_id, league_id, season_id, week_number)
);

CREATE TABLE IF NOT EXISTS week_notes (
    note_id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(league_id, season_id, week_number)
);
"""


def init_db(db_path):
    """Create all tables if they don't exist. Safe to call on every startup."""
    if config.DATABASE_URL:
        return _init_db_postgres(config.DATABASE_URL)

    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        _seed_if_empty(conn, '?')
        conn.commit()
    finally:
        conn.close()


def _init_db_postgres(database_url):
    """Create all tables (via schema_postgres.sql) and seed demo data on Postgres."""
    import psycopg2
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema_postgres.sql')
    with open(schema_path) as f:
        schema_sql = f.read()

    conn = psycopg2.connect(database_url)
    try:
        cur = conn.cursor()
        cur.execute(schema_sql)
        conn.commit()
        _apply_additive_migrations_postgres(cur)
        conn.commit()
        _seed_if_empty(conn, '%s')
        conn.commit()
        _reset_sequences_postgres(conn)
        conn.commit()
    finally:
        conn.close()


def _apply_additive_migrations_postgres(cur):
    """Run migrations that add tables/columns not in the base schema. Safe to re-run (IF NOT EXISTS)."""
    migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')
    additive = [
        'add_course_api_cache.sql',
        'add_league_board.sql',
    ]
    for fname in additive:
        path = os.path.join(migrations_dir, fname)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            sql = f.read()
        try:
            cur.execute(sql)
        except Exception as e:
            print(f"[init_db] Migration {fname} skipped or failed: {e}")


def _reset_sequences_postgres(conn):
    """Sync all SERIAL sequences to the max existing id so new inserts don't collide with seed data."""
    tables = [
        ('leagues',          'league_id'),
        ('users',            'user_id'),
        ('seasons',          'season_id'),
        ('courses',          'course_id'),
        ('tees',             'tee_id'),
        ('holes',            'hole_id'),
        ('players',          'player_id'),
        ('teams',            'team_id'),
        ('matchups',         'matchup_id'),
        ('rounds',           'round_id'),
        ('scores',           'score_id'),
        ('match_results',    'result_id'),
        ('league_members',   'member_id'),
        ('score_submissions','submission_id'),
        ('apns_tokens',      'token_id'),
        ('handicap_history', 'handicap_id'),
        ('skins_results',    'skin_id'),
        ('forum_threads',    'thread_id'),
        ('forum_posts',      'post_id'),
        ('notifications',    'notification_id'),
    ]
    cur = conn.cursor()
    for table, col in tables:
        try:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                f"COALESCE(MAX({col}), 1)) FROM {table}"
            )
        except Exception:
            conn.rollback()
            cur = conn.cursor()


def _seed_if_empty(conn, placeholder='?'):
    """Seed the Shankapotamus demo league if no leagues exist yet.

    `placeholder` is '?' for sqlite3 connections and '%s' for psycopg2
    connections (passed in from init_db / _init_db_postgres).
    """
    cur = conn.cursor() if hasattr(conn, 'cursor') and placeholder == '%s' else conn

    def execute(sql, params=None):
        sql = sql.replace('?', placeholder)
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)

    def executemany(sql, seq):
        sql = sql.replace('?', placeholder)
        cur.executemany(sql, seq)

    cur.execute("SELECT COUNT(*) FROM leagues")
    if cur.fetchone()[0] > 0:
        return  # already has data, skip

    # League
    execute("""
        INSERT INTO leagues (league_id, league_name, created_date, active, login_code,
            admin_password_hash, member_password_hash)
        VALUES (1, 'Shankapotamus Golf League', '2026-06-05', 1, '1',
            'scrypt:32768:8:1$YAfx6BBBzQ7EwHRH$200125d7fe99698f43f7a41ba6a36a43427b86a9e63760fb980f7e552aac34ad560de777a3759ed5eadad7f742abb943f0edf799007f8871da420cc50022d1de',
            'scrypt:32768:8:1$gOSlIl9DbfHHJeLA$7010b7f26910f9d24376f87ddaeb33531d1f767bf1fbf127f9c63c3e3d69af519cde3f7c0157f3bbcb9498d0929254630a26933e78b3f1519823acb379ce749f')
    """)

    # Season
    execute("""
        INSERT INTO seasons (season_id, league_id, season_name, start_date, end_date)
        VALUES (1, 1, '2026 Summer Season', '2026-05-01', '2026-09-30')
    """)

    # Course
    execute("""
        INSERT INTO courses (course_id, league_id, course_name, city, state, num_holes, created_date)
        VALUES (1, 1, 'Goat Pasture Golf Club', 'Birdsburg', 'OH', 18, '2026-06-05')
    """)

    # Tee
    execute("""
        INSERT INTO tees (tee_id, course_id, tee_name, tee_color, nine, slope, rating, par_total, gender)
        VALUES (1, 1, 'White', 'white', 'full', 113.0, 34.5, 36, 'M')
    """)

    # Players (20 players, IDs 1-20)
    players = [
        (1,  'Bogey',    'McFadden'),
        (2,  'Chip',     'Yippsalot'),
        (3,  'Sandy',    'Trapper'),
        (4,  'Mulligan', 'Jones'),
        (5,  'Divot',    'Thunderclap'),
        (6,  'Birdie',   'Shankowski'),
        (7,  'Par',      'Excellence'),
        (8,  'Fore',     'Warning'),
        (9,  'Grip',     'Slipperton'),
        (10, 'Hosel',    'Rocket'),
        (11, 'Wedge',    'Snorkelson'),
        (12, 'Loft',     'Mangum'),
        (13, 'Eagle',    'Flapjack'),
        (14, 'Bunker',   'Hilton'),
        (15, 'Wrist',    'Flipper'),
        (16, 'Turbo',    'Chunkins'),
        (17, 'Ace',      'Clanksworth'),
        (18, 'Lag',      'Putterly'),
        (19, 'Shank',    'Nasty'),
        (20, 'Dimple',   'McSpin'),
    ]
    executemany("""
        INSERT INTO players (player_id, league_id, first_name, last_name, active, created_date)
        VALUES (?, 1, ?, ?, 1, '2026-06-05')
    """, players)

    # Teams (10 teams)
    teams = [
        (1,  'The Duffers',          15, 10),
        (2,  'Fairway Felons',        1, 12),
        (3,  'Bogey Bros',           16, 18),
        (4,  'Sand Trap Survivors',   9,  2),
        (5,  'The Mulligan Men',     11,  4),
        (6,  'Chunk & Pray',          5,  7),
        (7,  'Cart Path Warriors',   20, 14),
        (8,  'Lost Ball Club',       13,  8),
        (9,  'The Wrist Flippers',   17, 19),
        (10, 'Par-Ish Activity',      3,  6),
    ]
    executemany("""
        INSERT INTO teams (team_id, season_id, league_id, team_name, player1_id, player2_id)
        VALUES (?, 1, 1, ?, ?, ?)
    """, teams)

    # Schedule (18 rounds, 5 matchups each = 90 matchups)
    # Re-mapped from original team_ids 14-23 → 1-10
    matchups = [
        # Week 1
        (1,1,1,'2026-05-01',5,6),(2,1,1,'2026-05-01',1,3),(3,1,1,'2026-05-01',4,7),
        (4,1,1,'2026-05-01',2,9),(5,1,1,'2026-05-01',8,10),
        # Week 2
        (6,2,2,'2026-05-08',2,7),(7,2,2,'2026-05-08',3,5),(8,2,2,'2026-05-08',1,6),
        (9,2,2,'2026-05-08',4,8),(10,2,2,'2026-05-08',9,10),
        # Week 3
        (11,3,3,'2026-05-15',2,5),(12,3,3,'2026-05-15',3,10),(13,3,3,'2026-05-15',7,9),
        (14,3,3,'2026-05-15',1,4),(15,3,3,'2026-05-15',6,8),
        # Week 4
        (16,4,4,'2026-05-22',5,10),(17,4,4,'2026-05-22',2,4),(18,4,4,'2026-05-22',3,8),
        (19,4,4,'2026-05-22',1,9),(20,4,4,'2026-05-22',6,7),
        # Week 5
        (21,5,5,'2026-05-29',2,3),(22,5,5,'2026-05-29',4,9),(23,5,5,'2026-05-29',1,8),
        (24,5,5,'2026-05-29',5,7),(25,5,5,'2026-05-29',6,10),
        # Week 6
        (26,6,6,'2026-06-05',3,9),(27,6,6,'2026-06-05',4,10),(28,6,6,'2026-06-05',1,2),
        (29,6,6,'2026-06-05',7,8),(30,6,6,'2026-06-05',5,6),
        # Week 7
        (31,7,7,'2026-06-12',8,9),(32,7,7,'2026-06-12',3,6),(33,7,7,'2026-06-12',4,5),
        (34,7,7,'2026-06-12',7,10),(35,7,7,'2026-06-12',1,2),
        # Week 8
        (36,8,8,'2026-06-19',4,6),(37,8,8,'2026-06-19',3,7),(38,8,8,'2026-06-19',5,9),
        (39,8,8,'2026-06-19',2,8),(40,8,8,'2026-06-19',1,10),
        # Week 9
        (41,9,9,'2026-06-26',3,4),(42,9,9,'2026-06-26',6,9),(43,9,9,'2026-06-26',5,8),
        (44,9,9,'2026-06-26',2,10),(45,9,9,'2026-06-26',1,7),
        # Week 10
        (46,10,10,'2026-07-03',2,6),(47,10,10,'2026-07-03',1,5),(48,10,10,'2026-07-03',4,7),
        (49,10,10,'2026-07-03',3,10),(50,10,10,'2026-07-03',8,9),
        # Week 11
        (51,11,11,'2026-07-10',1,3),(52,11,11,'2026-07-10',2,7),(53,11,11,'2026-07-10',5,10),
        (54,11,11,'2026-07-10',4,8),(55,11,11,'2026-07-10',6,9),
        # Week 12
        (56,12,12,'2026-07-17',3,5),(57,12,12,'2026-07-17',1,6),(58,12,12,'2026-07-17',2,9),
        (59,12,12,'2026-07-17',8,10),(60,12,12,'2026-07-17',4,7),
        # Week 13
        (61,13,13,'2026-07-24',2,5),(62,13,13,'2026-07-24',7,9),(63,13,13,'2026-07-24',1,4),
        (64,13,13,'2026-07-24',3,8),(65,13,13,'2026-07-24',6,10),
        # Week 14
        (66,14,14,'2026-07-31',2,4),(67,14,14,'2026-07-31',1,9),(68,14,14,'2026-07-31',6,7),
        (69,14,14,'2026-07-31',5,8),(70,14,14,'2026-07-31',3,10),
        # Week 15
        (71,15,15,'2026-08-07',2,3),(72,15,15,'2026-08-07',4,9),(73,15,15,'2026-08-07',1,8),
        (74,15,15,'2026-08-07',5,7),(75,15,15,'2026-08-07',6,10),
        # Week 16
        (76,16,16,'2026-08-14',9,10),(77,16,16,'2026-08-14',3,6),(78,16,16,'2026-08-14',7,8),
        (79,16,16,'2026-08-14',4,5),(80,16,16,'2026-08-14',1,2),
        # Week 17
        (81,17,17,'2026-08-21',3,9),(82,17,17,'2026-08-21',4,10),(83,17,17,'2026-08-21',2,8),
        (84,17,17,'2026-08-21',1,5),(85,17,17,'2026-08-21',6,7),
        # Week 18
        (86,18,18,'2026-08-28',4,6),(87,18,18,'2026-08-28',3,7),(88,18,18,'2026-08-28',5,9),
        (89,18,18,'2026-08-28',2,10),(90,18,18,'2026-08-28',1,8),
    ]
    executemany("""
        INSERT INTO matchups (matchup_id, season_id, round_number, week_number, scheduled_date,
            team1_id, team2_id, status, starting_hole, week_type)
        VALUES (?, 1, ?, ?, ?, ?, ?, 'scheduled', 1, 'Normal')
    """, matchups)
