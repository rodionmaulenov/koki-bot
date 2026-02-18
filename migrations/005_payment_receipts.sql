-- Migration 005: Create payment_receipts table
-- Date: 2026-02-18
-- Description: Track accountant payment receipts per course

SET ROLE postgres;

CREATE TABLE kok.payment_receipts (
    id              serial PRIMARY KEY,
    course_id       integer NOT NULL UNIQUE REFERENCES kok.courses(id),
    accountant_id   integer NOT NULL REFERENCES public.managers(id),
    receipt_file_id text NOT NULL,
    amount          integer,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_payment_receipts_course ON kok.payment_receipts (course_id);
CREATE INDEX idx_payment_receipts_accountant ON kok.payment_receipts (accountant_id);

GRANT ALL ON kok.payment_receipts TO anon, authenticated, service_role;
GRANT ALL ON SEQUENCE kok.payment_receipts_id_seq TO anon, authenticated, service_role;
