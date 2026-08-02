-- =============================================================================
-- migration_add_oral_exam_skip.sql
-- =============================================================================
-- Lets a student skip an oral exam question entirely (no recording made at
-- all) rather than being forced to submit at least a few seconds of audio
-- to advance. audio_file_path/transcript become nullable to support a
-- skipped row with no answer, and a `skipped` flag distinguishes "skipped"
-- from "answered but transcription failed" (which already stores an
-- "Error: ..." transcript with real audio on disk).
--
-- Run manually against the application database, e.g.:
--   mysql -u streamlit_user -p streamlit_database < migration_add_oral_exam_skip.sql
-- =============================================================================

ALTER TABLE oral_exam_responses
    MODIFY COLUMN audio_file_path VARCHAR(500) NULL,
    ADD COLUMN skipped TINYINT(1) NOT NULL DEFAULT 0 AFTER transcript;
