-- =============================================================================
-- migration_add_proctor_frames.sql
-- =============================================================================
-- Adds storage for periodic screen-share snapshot frames captured during
-- proctored quizzes/exam submissions, to an existing database that already
-- has quiz_proctor_events (from migration_add_quiz_proctoring.sql).
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_proctor_frames.sql
-- =============================================================================

CREATE TABLE quiz_proctor_frames (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(36)  NOT NULL,
    user_id       INT          NOT NULL,
    quiz_id       INT          NULL,
    assessment_id INT          NULL,
    file_path     VARCHAR(500) NOT NULL,
    captured_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)                   ON DELETE CASCADE,
    FOREIGN KEY (quiz_id)       REFERENCES practice_quiz_generated(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)             ON DELETE CASCADE,
    INDEX idx_proctor_frame_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
