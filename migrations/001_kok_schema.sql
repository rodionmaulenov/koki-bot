-- Migration: Create kok schema, move KOK tables, create new tables
-- Date: 2026-02-07 (APPLIED)
-- Description: Organize KOK-specific tables into separate schema
-- Code uses schema("kok").table() explicitly, no views needed.

BEGIN;

-- ============================================================
-- 1. Create kok schema + permissions
-- ============================================================

CREATE SCHEMA IF NOT EXISTS kok;

GRANT USAGE ON SCHEMA kok TO postgres, anon, authenticated, service_role;

-- ============================================================
-- 2. Move KOK tables from public to kok
-- ============================================================

-- Order matters: intake_logs depends on courses, courses depends on users
ALTER TABLE public.intake_logs SET SCHEMA kok;
ALTER TABLE public.courses SET SCHEMA kok;
ALTER TABLE public.users SET SCHEMA kok;

-- ============================================================
-- 3. Delete stats_messages (dashboard removed)
-- ============================================================

DROP TABLE IF EXISTS public.stats_messages;

-- ============================================================
-- 5. Create new tables in kok
-- ============================================================

CREATE TABLE kok.documents (
    id serial PRIMARY KEY,
    user_id integer NOT NULL UNIQUE REFERENCES kok.users(id) ON DELETE CASCADE,
    manager_id integer NOT NULL REFERENCES public.managers(id),
    passport_file_id text,
    receipt_file_id text,
    receipt_price integer,
    card_file_id text,
    card_number text,
    card_holder_name text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE kok.private_messages (
    id serial PRIMARY KEY,
    user_id integer NOT NULL REFERENCES kok.users(id) ON DELETE CASCADE,
    message_id integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- 6. Add new columns to courses
-- ============================================================

ALTER TABLE kok.courses ADD COLUMN extended boolean NOT NULL DEFAULT false;
ALTER TABLE kok.courses ADD COLUMN appeal_used boolean NOT NULL DEFAULT false;
ALTER TABLE kok.courses ADD COLUMN appeal_video text;
ALTER TABLE kok.courses ADD COLUMN appeal_text text;
ALTER TABLE kok.courses ADD COLUMN late_dates jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE kok.courses ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

-- Auto-update updated_at on every UPDATE
CREATE OR REPLACE FUNCTION kok.set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
CREATE TRIGGER trg_courses_updated_at
    BEFORE UPDATE ON kok.courses
    FOR EACH ROW EXECUTE FUNCTION kok.set_updated_at();

-- ============================================================
-- 7. Drop unused columns
-- ============================================================

ALTER TABLE kok.courses DROP COLUMN IF EXISTS transfer_code;
ALTER TABLE kok.courses DROP COLUMN IF EXISTS allow_video;
ALTER TABLE kok.courses DROP COLUMN IF EXISTS completed_days;

-- ============================================================
-- 8. Add new columns to intake_logs
-- ============================================================

ALTER TABLE kok.intake_logs ADD COLUMN review_started_at timestamptz;
ALTER TABLE kok.intake_logs ADD COLUMN reshoot_deadline timestamptz;

-- ============================================================
-- 9. Update CHECK constraints
-- ============================================================

ALTER TABLE kok.courses DROP CONSTRAINT IF EXISTS valid_status;
ALTER TABLE kok.courses ADD CONSTRAINT valid_status
    CHECK (status = ANY(ARRAY['setup', 'active', 'completed', 'refused', 'expired', 'appeal']));

ALTER TABLE kok.intake_logs DROP CONSTRAINT IF EXISTS valid_log_status;
ALTER TABLE kok.intake_logs ADD CONSTRAINT valid_log_status
    CHECK (status = ANY(ARRAY['pending', 'taken', 'late', 'missed', 'pending_review', 'rejected', 'reshoot']));

ALTER TABLE kok.intake_logs DROP CONSTRAINT IF EXISTS valid_day;
ALTER TABLE kok.intake_logs ADD CONSTRAINT valid_day
    CHECK (day >= 1 AND day <= 42);

-- ============================================================
-- 10. Create indexes
-- ============================================================

-- Partial indexes for workers
CREATE INDEX idx_courses_active ON kok.courses (id) WHERE status = 'active';
CREATE INDEX idx_courses_appeal ON kok.courses (id) WHERE status = 'appeal';
CREATE INDEX idx_intake_logs_pending_review ON kok.intake_logs (review_started_at) WHERE status = 'pending_review';
CREATE INDEX idx_intake_logs_reshoot ON kok.intake_logs (reshoot_deadline) WHERE status = 'reshoot';

-- Composite index for fast day lookup
CREATE INDEX idx_intake_logs_course_day ON kok.intake_logs (course_id, day);

-- BRIN indexes for time-series queries
CREATE INDEX idx_courses_created_brin ON kok.courses USING brin (created_at);
CREATE INDEX idx_intake_logs_created_brin ON kok.intake_logs USING brin (created_at);

-- Indexes for new tables
CREATE INDEX idx_documents_user ON kok.documents (user_id);
CREATE INDEX idx_documents_manager ON kok.documents (manager_id);
CREATE INDEX idx_private_messages_user ON kok.private_messages (user_id);

-- ============================================================
-- 12. Cleanup + permissions
-- ============================================================

DROP INDEX IF EXISTS kok.idx_courses_transfer_code;

GRANT ALL ON ALL TABLES IN SCHEMA kok TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA kok TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA kok GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA kok GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;

COMMIT;
