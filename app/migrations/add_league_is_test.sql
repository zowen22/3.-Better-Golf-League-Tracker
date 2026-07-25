-- Marks a league as scratch/test data (e.g. Shankapotamus, Site_Admin) so
-- the Site Admin dashboard can flag it distinctly from real customer
-- leagues in the All Leagues list, without excluding it from any counts.
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run

ALTER TABLE leagues ADD COLUMN IF NOT EXISTS is_test INTEGER NOT NULL DEFAULT 0;
