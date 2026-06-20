"""Add default_tee_id column to courses table."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import get_db
from app import create_app

app = create_app()
with app.app_context():
    db = get_db()
    db.execute(
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS default_tee_id INTEGER REFERENCES tees(tee_id)"
    )
    db.commit()
    print("Done: courses.default_tee_id added.")
