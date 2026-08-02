-- =============================================================================
-- migration_add_proctor_analysis_status.sql
-- =============================================================================
-- Defers the CPU-heavy part of webcam/audio proctoring analysis (mediapipe
-- FaceMesh + head-pose/gaze for frames, Silero VAD for audio) out of the
-- live capture path so it no longer competes for CPU with the real-time
-- parts of a proctored session (keystroke/mouse logging, tab-switch
-- monitoring, and screen/webcam video capture itself) while an exam is in
-- progress.
--
-- Adds analysis_status to both tables. Rows are inserted as 'pending' at
-- capture time (no analysis run yet) and flipped to 'analyzed' later by
-- process_pending_proctor_webcam_frames() / process_pending_proctor_audio_clips()
-- in proctoring_feature.py, triggered on demand via the Admin Panel's
-- Maintenance tab "Run Proctoring Analysis" button (parallel to the
-- existing "Run Proctoring Data Cleanup" button) or an external scheduler
-- calling the same functions — this app has no background worker/cron, the
-- same constraint documented for cleanup_old_proctor_data().
--
-- quiz_proctor_audio_clips previously only ever stored clips where speech
-- had already been detected (silent segments were discarded immediately
-- after analysis and never written). With analysis deferred, every captured
-- segment is now saved as 'pending' with placeholder 0.0 durations; the
-- discard-if-silent decision now happens during batch processing instead,
-- deleting the row/file at that point rather than at capture time.
--
-- Safe to run once, on a database that already has quiz_proctor_webcam_frames
-- (migration_add_webcam_proctoring.sql) and quiz_proctor_audio_clips
-- (migration_add_audio_proctoring.sql).
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_proctor_analysis_status.sql
-- =============================================================================

ALTER TABLE quiz_proctor_webcam_frames
    ADD COLUMN analysis_status ENUM('pending', 'analyzed') NOT NULL DEFAULT 'analyzed' AFTER gaze_offset_y;

ALTER TABLE quiz_proctor_audio_clips
    ADD COLUMN analysis_status ENUM('pending', 'analyzed') NOT NULL DEFAULT 'analyzed' AFTER clip_duration_sec;
