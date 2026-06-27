-- =============================================================================
-- migration_add_verification_attempts.sql
-- =============================================================================
-- Adds an audit log of identity-verification attempts (exam_verification
-- feature) to an existing database (one already created from an earlier
-- version of schema_clean.sql or schema_demo.sql, with data you want to
-- keep). Safe to run once.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_verification_attempts.sql
-- =============================================================================

CREATE TABLE verification_attempts (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          NOT NULL,
    gate_key        VARCHAR(100) NOT NULL,
    expected_name   VARCHAR(101) NOT NULL,
    expected_roll_no VARCHAR(50) NULL,
    ocr_text        LONGTEXT     NULL,
    name_matched    TINYINT(1)   NOT NULL,
    roll_matched    TINYINT(1)   NULL,
    face_matched    TINYINT(1)   NOT NULL,
    face_distance   FLOAT        NULL,
    face_threshold  FLOAT        NULL,
    face_error      VARCHAR(255) NULL,
    passed          TINYINT(1)   NOT NULL,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_verification_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
