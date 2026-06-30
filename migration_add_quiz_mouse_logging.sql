-- =============================================================================
-- migration_add_quiz_mouse_logging.sql
-- =============================================================================
-- Adds storage for mouse activity (clicks, throttled movement samples, and
-- cursor leave/re-enter of the browser window) captured during proctored
-- quizzes/exam submissions, to an existing database that already has
-- quiz_proctor_keystrokes (from migration_add_quiz_keystroke_logging.sql).
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_quiz_mouse_logging.sql
-- =============================================================================

CREATE TABLE quiz_proctor_mouse_events (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(36)  NOT NULL,
    user_id       INT          NOT NULL,
    quiz_id       INT          NULL,
    assessment_id INT          NULL,
    events_json   LONGTEXT     NOT NULL,
    captured_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)                   ON DELETE CASCADE,
    FOREIGN KEY (quiz_id)       REFERENCES practice_quiz_generated(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)             ON DELETE CASCADE,
    INDEX idx_proctor_mouse_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
