-- =============================================================================
-- migration_add_assessment_attempt_log.sql
-- =============================================================================
-- Adds a cross-feature activity log covering Oral Examination and Practice
-- Quiz attempts end-to-end (started, question reached, timed out, submitted/
-- completed) — not just identity verification (see verification_attempts).
-- This lets a teacher see students who opened an assessment but never
-- finished it, which previously left no trace at all.
--
-- Run manually against the application database, e.g.:
--   mysql -u streamlit_user -p streamlit_database < migration_add_assessment_attempt_log.sql
-- =============================================================================

CREATE TABLE assessment_attempt_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          NOT NULL,
    assessment_id   INT          NOT NULL,
    feature_name    VARCHAR(50)  NOT NULL,
    session_id      VARCHAR(36)  NULL,
    event_type      VARCHAR(50)  NOT NULL,
    question_number INT          NULL,
    detail          TEXT         NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)       ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    INDEX idx_attempt_log_lookup (assessment_id, feature_name, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
