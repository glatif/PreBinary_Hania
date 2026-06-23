-- =============================================================================
-- migration_add_quiz_proctoring.sql
-- =============================================================================
-- Adds tab-switch / screen-share proctoring support to an existing database
-- (one already created from an earlier version of schema_clean.sql or
-- schema_demo.sql, with data you want to keep). Safe to run once.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_quiz_proctoring.sql
-- =============================================================================

ALTER TABLE practice_quiz_attempts
    ADD COLUMN proctor_session_id VARCHAR(36) NULL AFTER score;

CREATE TABLE quiz_proctor_events (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(36)  NOT NULL,
    user_id       INT          NOT NULL,
    quiz_id       INT          NULL,
    assessment_id INT          NULL,
    event_type    VARCHAR(40)  NOT NULL,
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)                   ON DELETE CASCADE,
    FOREIGN KEY (quiz_id)       REFERENCES practice_quiz_generated(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)             ON DELETE CASCADE,
    INDEX idx_proctor_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
