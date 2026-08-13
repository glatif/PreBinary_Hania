-- =============================================================================
-- migration_add_course_platform_v2.sql
-- =============================================================================
-- Schema foundation for: email-based student onboarding (roster upload,
-- temp-password emails, forced/self-service password change), per-exam
-- access codes, per-question Exam Grading results, and AI plagiarism
-- scoring. Adds columns/tables to an existing database (one already
-- created from an earlier version of schema_clean.sql or schema_demo.sql,
-- with data you want to keep). Safe to run once.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_course_platform_v2.sql
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Forces the mandatory change-password screen on next login. Set to 1
-- whenever a temp password is generated for the user (roster import,
-- admin-triggered email reset, forgot-password self-service) and cleared
-- back to 0 the moment the user successfully sets their own password.
-- -----------------------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN must_change_password TINYINT(1) NOT NULL DEFAULT 0;

-- -----------------------------------------------------------------------------
-- Optional access codes. NULL/blank means no code is required (backward
-- compatible with every existing quiz/exam/oral exam setup).
-- -----------------------------------------------------------------------------
ALTER TABLE quizzes
    ADD COLUMN access_code VARCHAR(50) NULL;

ALTER TABLE exam_setups
    ADD COLUMN access_code VARCHAR(50) NULL;

ALTER TABLE oral_exam_setups
    ADD COLUMN access_code VARCHAR(50) NULL;

-- -----------------------------------------------------------------------------
-- Single-row table (id is always 1) holding the admin-configurable Gmail
-- SMTP sender credentials used to email temp passwords and forgot-password
-- resets to students — see get_smtp_config()/set_smtp_config() in auth.py.
-- Left blank so the app loads safely with no credentials configured.
-- -----------------------------------------------------------------------------
CREATE TABLE app_settings (
    id                INT PRIMARY KEY DEFAULT 1,
    smtp_sender_email VARCHAR(255) NULL,
    smtp_app_password VARCHAR(255) NULL,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO app_settings (id) VALUES (1);

-- -----------------------------------------------------------------------------
-- One row per student per question per grading run, modeled directly on
-- oral_exam_grading_results. exam_grading_results stays as the
-- aggregate/session-level row per student — its score/max_points become the
-- SUM of this table's rows for the same grading_session_id + student.
-- -----------------------------------------------------------------------------
CREATE TABLE exam_grading_question_results (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    grading_session_id    VARCHAR(36)  NOT NULL,
    graded_by             INT          NOT NULL,
    assessment_id         INT          NOT NULL,
    student_name          VARCHAR(255),
    student_id_parsed     VARCHAR(100),
    question_number       INT          NOT NULL,
    question_text         TEXT         NOT NULL,
    student_answer        MEDIUMTEXT,
    score                 FLOAT        NOT NULL,
    max_points            INT          NOT NULL,
    feedback              TEXT,
    detailed_explanation  MEDIUMTEXT,
    model_provider        VARCHAR(50),
    model_name            VARCHAR(100),
    graded_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (graded_by)     REFERENCES users(id)       ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    INDEX idx_exam_grading_question_session (grading_session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- Pairwise similarity results between two students' submissions on the same
-- assessment, computed on-demand via src/utils/plagiarism.py using the app's
-- existing local sentence-embedding model — no paid API key required.
-- student_a_id is always the smaller of the two user IDs so a re-run
-- upserts the same row instead of duplicating the pair.
-- -----------------------------------------------------------------------------
CREATE TABLE plagiarism_results (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    assessment_id    INT          NOT NULL,
    feature_name     VARCHAR(50)  NOT NULL,
    student_a_id     INT          NOT NULL,
    student_b_id     INT          NOT NULL,
    similarity_score FLOAT        NOT NULL,
    llm_explanation  TEXT         NULL,
    computed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY (student_a_id)  REFERENCES users(id)       ON DELETE CASCADE,
    FOREIGN KEY (student_b_id)  REFERENCES users(id)       ON DELETE CASCADE,
    UNIQUE KEY uq_plagiarism_pair (assessment_id, feature_name, student_a_id, student_b_id),
    INDEX idx_plagiarism_assessment (assessment_id, feature_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
