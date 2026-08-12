import os
import sys
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, '..', 'Database', 'golf_league.db')

# Try to load .env from the project root (one level up from app/)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(BASE_DIR, '..', '.env')
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv not installed; fall back to env vars or default

# If DATABASE_URL is set (e.g. on Render with a Postgres add-on), the app
# uses Postgres via psycopg2 instead of the local SQLite file. Leave unset
# for local SQLite development.
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip() or None

# Secret key — falls back to a fixed dev key if not configured.
# Good enough for local use; swap in a real key before exposing publicly.
_raw_key = os.environ.get('FLASK_SECRET_KEY', '')
if _raw_key and _raw_key != 'replace-me-with-a-real-random-key':
    SECRET_KEY = _raw_key
else:
    SECRET_KEY = 'dev-secret-key-local-only'
    print("INFO: FLASK_SECRET_KEY not set — using default dev key (local use only).", file=sys.stderr)

DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

# Render sets this automatically on every deploy (no manual config needed) --
# used for a small footer build note so a deploy can be visually confirmed
# instead of guessing whether a push has actually rolled out yet.
_git_commit = os.environ.get('RENDER_GIT_COMMIT', '').strip()
GIT_COMMIT_SHORT = _git_commit[:7] if _git_commit else 'local'

from datetime import datetime, timezone
BOOT_TIME = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

GOLFCOURSE_API_KEY = os.environ.get('GOLFCOURSE_API_KEY', '').strip() or None

# Stripe billing (recurring annual subscription, one per league). All unset
# in dev by design -- billing.py degrades to a "not configured" message
# rather than erroring when these are blank.
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '').strip() or None
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '').strip() or None
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '').strip() or None
STRIPE_PRICE_ID_ANNUAL = os.environ.get('STRIPE_PRICE_ID_ANNUAL', '').strip() or None

# Platform-level SMTP (distinct from each league's own SMTP config in the
# `leagues` table) -- used for account-level emails that can't depend on a
# league's own settings, e.g. password reset: the whole point is reaching
# someone who is currently locked out. All unset in dev by design; the
# sending function degrades to a log line + no-op rather than erroring
# when these are blank.
PLATFORM_SMTP_HOST = os.environ.get('PLATFORM_SMTP_HOST', 'smtp.gmail.com').strip()
PLATFORM_SMTP_PORT = int(os.environ.get('PLATFORM_SMTP_PORT', '587').strip() or 587)
PLATFORM_SMTP_USER = os.environ.get('PLATFORM_SMTP_USER', '').strip() or None
PLATFORM_SMTP_PASSWORD = os.environ.get('PLATFORM_SMTP_PASSWORD', '').strip() or None
PLATFORM_SMTP_FROM_EMAIL = os.environ.get('PLATFORM_SMTP_FROM_EMAIL', '').strip() or PLATFORM_SMTP_USER
PLATFORM_SMTP_FROM_NAME = os.environ.get('PLATFORM_SMTP_FROM_NAME', 'Better Golf League Tracker').strip()

# Session cookie settings
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'  # Set to true in production (HTTPS)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = timedelta(days=180)
