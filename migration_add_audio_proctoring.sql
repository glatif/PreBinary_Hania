-- =============================================================================
-- migration_add_audio_proctoring.sql
-- =============================================================================
-- Adds audio-based proctoring to an existing database (one already created
-- from an earlier version of schema_clean.sql or schema_demo.sql, with data
-- you want to keep). Safe to run once.
--
-- quiz_proctor_audio_clips stores only the audio clips in which
-- proctoring_feature.py's analyze_audio_clip() (a Silero VAD voice-activity
-- model) detected human speech during a monitored quiz/exam session — clips
-- with no detected speech are discarded right after analysis and never
-- written here or to disk, keeping storage bounded and the retained audio
-- limited to segments actually worth an instructor's review.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_audio_proctoring.sql
-- =============================================================================

CREATE TABLE quiz_proctor_audio_clips (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    session_id          VARCHAR(36)  NOT NULL,
    user_id             INT          NOT NULL,
    quiz_id             INT          NULL,
    assessment_id       INT          NULL,
    file_path           VARCHAR(500) NOT NULL,
    speech_duration_sec FLOAT        NOT NULL,
    clip_duration_sec   FLOAT        NOT NULL,
    captured_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)                   ON DELETE CASCADE,
    FOREIGN KEY (quiz_id)       REFERENCES practice_quiz_generated(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)             ON DELETE CASCADE,
    INDEX idx_proctor_audio_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
