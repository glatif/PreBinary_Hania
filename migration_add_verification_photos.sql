-- =============================================================================
-- migration_add_verification_photos.sql
-- =============================================================================
-- Adds columns to verification_attempts to keep the actual ID-card and
-- selfie photos captured during identity verification, not just the OCR/
-- face-match metadata derived from them. Both are nullable so existing rows
-- (captured before this migration) remain valid with no photo on file.
--
-- Run manually against the application database, e.g.:
--   mysql -u streamlit_user -p streamlit_database < migration_add_verification_photos.sql
-- =============================================================================

ALTER TABLE verification_attempts
    ADD COLUMN id_card_image_path VARCHAR(500) NULL AFTER ocr_text,
    ADD COLUMN selfie_image_path  VARCHAR(500) NULL AFTER id_card_image_path;
