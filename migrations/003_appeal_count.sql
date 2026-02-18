-- Migration 003: Replace appeal_used (boolean) with appeal_count (integer)
-- This supports up to 2 appeal attempts per course

-- Must drop view first (view depends on appeal_used column)
DROP VIEW IF EXISTS public.courses;

-- Drop the old boolean column and add integer counter
ALTER TABLE kok.courses DROP COLUMN appeal_used;
ALTER TABLE kok.courses ADD COLUMN appeal_count integer NOT NULL DEFAULT 0;

-- Recreate public view
CREATE VIEW public.courses AS SELECT * FROM kok.courses;
GRANT SELECT, INSERT, UPDATE ON public.courses TO anon, authenticated, service_role;
