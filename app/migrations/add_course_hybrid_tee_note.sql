-- Free-text footnote for courses where a hybrid tee-box arrangement is in
-- play (a group mixing tee colors hole-by-hole, e.g. "Whites on all par 3's
-- and 2,5,8,10,14,18, Black/Blue elsewhere"). This app has no per-hole-
-- per-player tee assignment in the schema (see print_scorecards.html's
-- comment, 2026-07-28) -- building one would touch scoring/handicap math,
-- not just the printout. Deliberately just a persisted note, admin-set per
-- course, shown as-is on that course's printed scorecards -- not computed
-- or enforced.
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE courses ADD COLUMN IF NOT EXISTS hybrid_tee_note TEXT;
