-- =============================================================================
-- migration_add_oral_examination.sql
-- =============================================================================
-- Adds the Oral Examination feature: teacher-defined question sets generated
-- by an LLM, per-question spoken student responses (audio + transcript), and
-- LLM-graded results. Proctoring (screen-share, webcam/gaze, keystrokes,
-- mouse) is captured by the existing quiz_proctor_* tables via
-- render_proctor_monitor() and is not duplicated here.
--
-- Run manually against the application database, e.g.:
--   mysql -u streamlit_user -p streamlit_database < migration_add_oral_examination.sql
-- =============================================================================

CREATE TABLE oral_exam_setups (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    assessment_id           INT NOT NULL UNIQUE,
    questions                TEXT NOT NULL,
    rubric                  TEXT,
    max_points_per_question INT NOT NULL DEFAULT 10,
    set_by                  INT NOT NULL,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY (set_by)        REFERENCES users(id)       ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE oral_exam_responses (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    session_id      VARCHAR(36)  NOT NULL,
    assessment_id   INT          NOT NULL,
    student_id      INT          NOT NULL,
    question_number INT          NOT NULL,
    question_text   TEXT         NOT NULL,
    audio_file_path VARCHAR(500) NOT NULL,
    transcript      TEXT,
    answered_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id)    REFERENCES users(id)       ON DELETE CASCADE,
    INDEX idx_oral_response_session (session_id),
    -- One response per student per question: guards against a double-submit
    -- (double-click, or a resubmit before the page rerenders) inserting two
    -- rows for the same question, which would otherwise let a single answer
    -- be graded twice and inflate the student's total score.
    UNIQUE KEY uq_oral_response_question (assessment_id, student_id, question_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE oral_exam_grading_results (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    grading_session_id    VARCHAR(36)  NOT NULL,
    graded_by             INT          NOT NULL,
    assessment_id         INT          NOT NULL,
    student_id            INT          NOT NULL,
    student_name          VARCHAR(255),
    question_number       INT          NOT NULL,
    question_text         TEXT         NOT NULL,
    transcript             TEXT,
    score                 FLOAT        NOT NULL,
    max_points            INT          NOT NULL,
    feedback              TEXT,
    detailed_explanation  TEXT,
    model_provider          VARCHAR(50),
    model_name             VARCHAR(100),
    graded_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (graded_by)     REFERENCES users(id)       ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id)    REFERENCES users(id)       ON DELETE CASCADE,
    INDEX idx_oral_grading_session (grading_session_id),
    INDEX idx_oral_grading_student_assessment (student_id, assessment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
