-- =============================================================================
-- migration_add_verification_document_type.sql
-- =============================================================================
-- Extends verification_attempts (added by
-- migration_add_verification_attempts.sql) with multi-document-type support:
-- BC driver's licence, BC Services Card / BCID, and other Canadian
-- government photo ID, in addition to the original institution student
-- card. Adds the auto-detected document_type plus an expiry_date/expired
-- pair used for the expiry check on government-issued documents.
--
-- Safe to run once, on a database that already has verification_attempts.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_verification_document_type.sql
-- =============================================================================

ALTER TABLE verification_attempts
    ADD COLUMN document_type VARCHAR(40) NOT NULL DEFAULT 'student_card' AFTER gate_key,
    ADD COLUMN expiry_date   DATE        NULL AFTER roll_matched,
    ADD COLUMN expired       TINYINT(1)  NULL AFTER expiry_date;
