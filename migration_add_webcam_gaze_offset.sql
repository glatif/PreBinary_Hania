-- =============================================================================
-- migration_add_webcam_gaze_offset.sql
-- =============================================================================
-- Extends quiz_proctor_webcam_frames (added by
-- migration_add_webcam_proctoring.sql) with iris-offset gaze tracking.
--
-- The original looking_away signal relied solely on solvePnP head-pose
-- estimation against an uncalibrated camera matrix, which significantly
-- underestimates real head rotation (verified in testing: a student looking
-- at a phone in their lap for 15+ seconds only produced ~8-10 degrees of
-- estimated yaw/pitch). gaze_offset_x/gaze_offset_y store the new,
-- calibration-free iris-position signal (see _estimate_gaze_offset() in
-- proctoring_feature.py) that looking_away now also considers.
--
-- Safe to run once, on a database that already has
-- quiz_proctor_webcam_frames.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_webcam_gaze_offset.sql
-- =============================================================================

ALTER TABLE quiz_proctor_webcam_frames
    ADD COLUMN gaze_offset_x FLOAT NULL AFTER pitch_deg,
    ADD COLUMN gaze_offset_y FLOAT NULL AFTER gaze_offset_x;
