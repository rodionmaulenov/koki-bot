-- Migration 004: Add role column to managers
-- Date: 2026-02-18 (APPLIED)
-- Existing managers get default 'manager' role

ALTER TABLE public.managers ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'manager';
