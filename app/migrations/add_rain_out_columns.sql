-- Rain out / makeup week columns on matchups. Historically applied to
-- production only via the standalone migrate_rain_outs.py script, which
-- left fresh databases without these columns (admin panel 500s) — the
-- documented "three-part checklist" failure class.
ALTER TABLE matchups ADD COLUMN IF NOT EXISTS week_label TEXT DEFAULT NULL;
ALTER TABLE matchups ADD COLUMN IF NOT EXISTS makeup_for_week INTEGER DEFAULT NULL;
