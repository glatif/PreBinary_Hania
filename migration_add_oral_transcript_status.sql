-- =============================================================================
-- migration_add_oral_transcript_status.sql
-- =============================================================================
-- Moves Oral Examination transcription off the student-facing submit path.
-- Previously, "Stop & Submit" saved the audio AND transcribed it in the same
-- blocking request — a slow or unresponsive Whisper/Gemini call left the
-- student staring at a spinner. Now a submit only saves the raw audio
-- (transcript_status = 'pending'); process_pending_oral_transcriptions() in
-- oral_examination_feature.py transcribes it afterward, either via the
-- background sweep thread (start_oral_transcription_scheduler(), mirroring
-- proctoring's own analysis sweep) or synchronously right before grading, so
-- a transcript is always ready by the time a teacher grades.
--
-- transcript_status values:
--   'not_applicable' -- skipped question, nothing to transcribe
--   'pending'         -- audio saved, transcription not yet attempted
--   'done'            -- transcript column holds a real transcript
--   'failed'          -- transcript column holds an "Error: ..." string
--
-- Existing rows are backfilled based on their current transcript/skipped
-- state so nothing already-transcribed gets re-queued.
--
-- Run manually against the application database, e.g.:
--   mysql -u streamlit_user -p streamlit_database < migration_add_oral_transcript_status.sql
-- =============================================================================

ALTER TABLE oral_exam_responses
    ADD COLUMN transcript_status ENUM('not_applicable', 'pending', 'done', 'failed')
        NOT NULL DEFAULT 'pending' AFTER transcript;

UPDATE oral_exam_responses SET transcript_status = 'not_applicable' WHERE skipped = 1;
UPDATE oral_exam_responses SET transcript_status = 'failed' WHERE skipped = 0 AND transcript LIKE 'Error:%';
UPDATE oral_exam_responses SET transcript_status = 'done' WHERE skipped = 0 AND transcript IS NOT NULL AND transcript NOT LIKE 'Error:%';

CREATE INDEX idx_oral_response_transcript_status ON oral_exam_responses (transcript_status);
