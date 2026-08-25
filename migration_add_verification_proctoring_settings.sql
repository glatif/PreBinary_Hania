-- =============================================================================
-- migration_add_verification_proctoring_settings.sql
-- =============================================================================
-- Adds the following to an existing database (one already created from an
-- earlier version of schema_clean.sql or schema_demo.sql, with data you want
-- to keep). Safe to run once.
--
--   * app_settings: admin toggles for whether verification photos (ID card /
--     selfie) are saved to disk, and admin locks on whether instructors are
--     allowed to require verification / enable proctoring at all — see
--     get_verification_admin_settings()/set_verification_admin_settings() in
--     exam_verification_feature.py.
--   * proctor_settings: admin toggle for whether webcam video (recording,
--     periodic frames, face/gaze analysis) is captured during proctoring, or
--     screen-only — see get_record_webcam_video()/set_record_webcam_video()
--     in proctoring_feature.py.
--   * exam_setups / oral_exam_setups: per-exam instructor toggles for
--     identity verification / proctoring, set alongside access_code in each
--     feature's Setup tab.
--   * quiz_generator_settings (new table): the same two per-assessment
--     toggles for the Practice Quiz feature, which has no other instructor
--     setup step to attach them to.
--
-- All new TINYINT(1) columns default to 1 (enabled) so every existing exam,
-- quiz, and oral exam keeps behaving exactly as it did before this
-- migration — nothing changes until an admin or instructor explicitly
-- unchecks something.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_verification_proctoring_settings.sql
-- =============================================================================

ALTER TABLE app_settings
    ADD COLUMN save_id_card_photo TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN save_selfie_photo  TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN allow_instructor_verification_toggle TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN allow_instructor_proctoring_toggle    TINYINT(1) NOT NULL DEFAULT 1;

ALTER TABLE proctor_settings
    ADD COLUMN record_webcam_video TINYINT(1) NOT NULL DEFAULT 1;

ALTER TABLE exam_setups
    ADD COLUMN require_verification TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN enable_proctoring    TINYINT(1) NOT NULL DEFAULT 1;

ALTER TABLE oral_exam_setups
    ADD COLUMN require_verification TINYINT(1) NOT NULL DEFAULT 1,
    ADD COLUMN enable_proctoring    TINYINT(1) NOT NULL DEFAULT 1;

CREATE TABLE quiz_generator_settings (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    assessment_id         INT NOT NULL UNIQUE,
    require_verification  TINYINT(1) NOT NULL DEFAULT 1,
    enable_proctoring     TINYINT(1) NOT NULL DEFAULT 1,
    set_by                INT NOT NULL,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY (set_by)        REFERENCES users(id)       ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
