-- =============================================================================
-- migration_add_video_proctoring.sql
-- =============================================================================
-- Adds continuous screen/webcam video recording to an existing database (one
-- already created from an earlier version of schema_clean.sql or
-- schema_demo.sql, with data you want to keep). Safe to run once.
--
-- quiz_proctor_video_segments stores one row per recorded segment (see
-- save_proctor_video_segment() / VIDEO_SEGMENT_INTERVAL_MS in
-- proctoring_feature.py) — kind distinguishes the screen recording from the
-- webcam(+microphone) recording. get_or_build_proctor_video() stitches a
-- session's segments together into one playable video on demand; this table
-- only tracks the raw per-segment files, not the stitched output.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_video_proctoring.sql
-- =============================================================================

CREATE TABLE quiz_proctor_video_segments (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(36)  NOT NULL,
    user_id       INT          NOT NULL,
    quiz_id       INT          NULL,
    assessment_id INT          NULL,
    kind          ENUM('screen', 'webcam') NOT NULL,
    seq           INT          NOT NULL,
    file_path     VARCHAR(500) NOT NULL,
    captured_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)                   ON DELETE CASCADE,
    FOREIGN KEY (quiz_id)       REFERENCES practice_quiz_generated(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)             ON DELETE CASCADE,
    INDEX idx_proctor_video_segments_session (session_id, kind, seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
