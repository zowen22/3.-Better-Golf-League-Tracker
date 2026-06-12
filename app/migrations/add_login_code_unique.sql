-- Add UNIQUE constraint to login_code column
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query → paste → Run
-- Ensure no duplicate login_codes exist before running (there shouldn't be any in a fresh DB)

ALTER TABLE leagues ADD CONSTRAINT leagues_login_code_unique UNIQUE (login_code);
