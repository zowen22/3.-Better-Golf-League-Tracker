"""
Migration: add forum_topics and forum_replies tables.
Run from: D:\GolfLeague\app\  =>  python migrate_forum.py
"""
import sqlite3, os, shutil, time

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'Database', 'golf_league.db')
DB_PATH = os.path.abspath(DB_PATH)
TMP_PATH = '/tmp/golf_forum_mig.db'

print(f"Source DB: {DB_PATH}")
shutil.copy2(DB_PATH, TMP_PATH)

conn = sqlite3.connect(TMP_PATH)
c = conn.cursor()

# Check if tables already exist
tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

if 'forum_topics' not in tables:
    c.execute("""
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
        )
    """)
    print("Created forum_topics")
else:
    print("forum_topics already exists")

if 'forum_replies' not in tables:
    c.execute("""
        CREATE TABLE forum_replies (
            reply_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id   INTEGER NOT NULL REFERENCES forum_topics(topic_id) ON DELETE CASCADE,
            league_id  INTEGER NOT NULL,
            body       TEXT NOT NULL,
            author_id  INTEGER,
            author_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_forum_replies_topic ON forum_replies(topic_id)")
    print("Created forum_replies")
else:
    print("forum_replies already exists")

conn.commit()
conn.close()

shutil.copy2(TMP_PATH, DB_PATH)
print("Migration complete — DB written back.")
