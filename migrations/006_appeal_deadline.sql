-- Migration 006: Add appeal_deadline to courses
-- Time limit for girl to press the appeal button after removal

-- Must drop view first (view depends on courses table)
DROP VIEW IF EXISTS public.courses;

ALTER TABLE kok.courses ADD COLUMN appeal_deadline timestamptz DEFAULT NULL;

-- Recreate public view
CREATE VIEW public.courses AS SELECT * FROM kok.courses;
GRANT SELECT, INSERT, UPDATE ON public.courses TO anon, authenticated, service_role;
