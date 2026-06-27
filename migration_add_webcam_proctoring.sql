-- =============================================================================
-- migration_add_webcam_proctoring.sql
-- =============================================================================
-- Adds webcam-based proctoring to an existing database (one already created
-- from an earlier version of schema_clean.sql or schema_demo.sql, with data
-- you want to keep). Safe to run once.
--
-- quiz_proctor_webcam_frames stores periodic webcam snapshots (parallel to
-- quiz_proctor_frames, which stores screen-share snapshots) plus, per frame,
-- the result of running it through proctoring_feature.py's face/gaze
-- analysis: how many faces were detected, whether none/multiple were found,
-- and an estimated head-pose-based "looking away from screen" verdict.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_webcam_proctoring.sql
-- =============================================================================

CREATE TABLE quiz_proctor_webcam_frames (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    session_id     VARCHAR(36)  NOT NULL,
    user_id        INT          NOT NULL,
    quiz_id        INT          NULL,
    assessment_id  INT          NULL,
    file_path      VARCHAR(500) NOT NULL,
    face_count     INT          NOT NULL,
    no_face        TINYINT(1)   NOT NULL,
    multiple_faces TINYINT(1)   NOT NULL,
    looking_away   TINYINT(1)   NULL,
    yaw_deg        FLOAT        NULL,
    pitch_deg      FLOAT        NULL,
    captured_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)                   ON DELETE CASCADE,
    FOREIGN KEY (quiz_id)       REFERENCES practice_quiz_generated(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)             ON DELETE CASCADE,
    INDEX idx_proctor_webcam_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
