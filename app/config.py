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

# Secret key — falls back to a fixed dev key if not configured.
# Good enough for local use; swap in a real key before exposing publicly.
_raw_key = os.environ.get('FLASK_SECRET_KEY', '')
if _raw_key and _raw_key != 'replace-me-with-a-real-random-key':
    SECRET_KEY = _raw_key
else:
    SECRET_KEY = 'dev-secret-key-local-only'
    print("INFO: FLASK_SECRET_KEY not set — using default dev key (local use only).", file=sys.stderr)

DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

# Session cookie settings
SESSION_COOKIE_SECURE = False          # False so cookies work over plain HTTP locally
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
