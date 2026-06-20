-- =============================================================================
-- schema_clean.sql — Prebinary × UReap Integration
-- =============================================================================
-- Full database schema. Run this file to drop and recreate the database from
-- scratch, including the application user, all tables, indexes, and the seed
-- admin account.
--
-- Table structure overview:
--   users            Core user accounts with profile, address, API key, and
--                    per-feature model preference fields.
--   courses          Courses created by instructors or admins. (Deferred sprint.)
--   assessments      Assessments belonging to a course. (Deferred sprint.)
--   files            Files uploaded to a specific assessment. (Deferred sprint.)
--   course_access    Access control records for courses. (Deferred sprint.)
--   quizzes          Instructor-published quizzes. (Deferred sprint — ai_output_id
--                    column removed; table retained for future use.)
--   quiz_questions   Questions belonging to a quiz. (Deferred sprint.)
--   quiz_submissions Student quiz submissions. (Deferred sprint.)
--   quiz_answers     Per-question answers within a submission. (Deferred sprint.)
--
--   ── UReap feature tables (this sprint) ─────────────────────────────────────
--   rag_indexes           Per-user FAISS index directory tracking.
--   rag_query_history     Per-user RAG query and response history.
--   exam_grading_results  Per-student AI grading output, grouped by session.
--   exam_creation_questions  Generated exam questions from both creation modes.
--   advisor_chat_history  Per-user Advisor AI conversation turns.
--   wellness_chat_history Per-user Wellness Assistant conversation turns.
--   practice_quiz_generated  Self-service generated practice quizzes per user.
--   practice_quiz_attempts   Student attempts against a generated practice quiz.
--
-- All tables use InnoDB for foreign key support and utf8mb4 for full Unicode.
--
-- Cascade behaviour:
--   Deleting a user cascades to all UReap feature rows owned by that user.
--   Deferred-sprint tables retain their own cascade rules unchanged.
-- =============================================================================


-- =============================================================================
-- 1. DATABASE
-- =============================================================================

DROP DATABASE IF EXISTS streamlit_database;
CREATE DATABASE streamlit_database;
USE streamlit_database;


-- =============================================================================
-- 2. USERS
-- =============================================================================
-- Stores all user accounts regardless of role. The role column determines what
-- a logged-in user can see and do. The status column controls whether a user
-- can log in at all; new self-registered accounts default to 'inactive' and
-- must be activated by an admin.
--
-- API key columns store user-supplied credentials for external AI services.
-- They are nullable so users who have not configured a key return NULL rather
-- than an empty string, making the "not set" check unambiguous in app.py.
--
-- UReap uses the following session state key names for API keys:
--   openai_api_key  → loaded from chatgpt_api_key at login
--   gemini_api_key  → loaded from gemini_api_key at login
--   groq_api_key    → loaded from groq_api_key at login
--   github_token    → loaded from github_token at login
-- ElevenLabs and Cartesia keys are stored here for the Narrated Slideshow
-- feature (future sprint) but are not surfaced in the UI this sprint.
--
-- pref_model_* columns store each user's preferred LLM for each UReap feature.
-- NULL means no preference set; the application falls back to the first model
-- in llm_utils.MODELS. Values are model ID strings (e.g. 'gemini-2.5-flash'),
-- not display names.
--
-- pref_model_video_lectures is stored in the same column family and is loaded
-- into the slideshow_selected_model session state key at login via
-- _load_model_preferences() in app.py.
--
-- phone is VARCHAR(20) — accommodates the full range of international phone
-- number formats. The column size matches the 20-character maximum enforced
-- by validate_phone() in validators.py.

CREATE TABLE users (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(255)                                 NOT NULL UNIQUE,
    email          VARCHAR(255)                                 NOT NULL UNIQUE,
    password       VARCHAR(255)                                 NOT NULL,
    first_name     VARCHAR(50),
    last_name      VARCHAR(50),
    phone          VARCHAR(20),
    street_address VARCHAR(255),
    city           VARCHAR(100),
    state_province VARCHAR(100),
    postal_code    VARCHAR(20),
    country        VARCHAR(100),

    -- Student roll/registration number, shown on the institution-issued ID
    -- card and checked against that card at exam-submission identity
    -- verification time. NULL for non-student roles.
    roll_no        VARCHAR(50)  NULL UNIQUE,

    -- AI provider API keys. chatgpt_api_key doubles as the OpenAI key for UReap
    -- (UReap reads st.session_state.openai_api_key, loaded from this column).
    chatgpt_api_key    VARCHAR(255)  NULL,
    gemini_api_key     VARCHAR(255)  NULL,
    groq_api_key       VARCHAR(255)  NULL,
    github_token       VARCHAR(255)  NULL,
    elevenlabs_api_key VARCHAR(255)  NULL,
    cartesia_api_key   VARCHAR(255)  NULL,

    -- Per-feature preferred model IDs for UReap features.
    -- NULL means "use application default" (first entry in llm_utils.MODELS).
    pref_model_rag           VARCHAR(100)  NULL,
    pref_model_exam_grading  VARCHAR(100)  NULL,
    pref_model_exam_creation VARCHAR(100)  NULL,
    pref_model_advisor_ai    VARCHAR(100)  NULL,
    pref_model_wellness      VARCHAR(100)  NULL,
    pref_model_quiz_generator VARCHAR(100) NULL,
    pref_model_video_lectures VARCHAR(100)  NULL,

    role       ENUM('user', 'admin', 'teacher', 'student')  DEFAULT 'user',
    status     ENUM('active', 'inactive')                   DEFAULT 'inactive',
    created_at TIMESTAMP                                     DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_username (username),
    INDEX idx_email    (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 3. DATABASE USER
-- =============================================================================
-- Application-level database user with access limited to streamlit_database.
-- Credentials must match the DB_CONFIG values in db.py.

CREATE USER IF NOT EXISTS 'streamlit_user'@'localhost' IDENTIFIED BY 'streamlit_pass';
GRANT ALL PRIVILEGES ON streamlit_database.* TO 'streamlit_user'@'localhost';
FLUSH PRIVILEGES;


-- =============================================================================
-- 4. SEED ADMIN ACCOUNT
-- =============================================================================
-- Default admin account created at schema initialisation time. The password
-- hash corresponds to 'admin' (bcrypt, cost factor 12). Change this
-- password immediately after first login in any non-development environment.

INSERT INTO users (
    username, email, password,
    first_name, last_name, phone,
    street_address, city, state_province, postal_code, country,
    role, status
)
VALUES (
    'admin', 'admin@example.com',
    '$2b$12$IrvZB71wdGRlkf8ME9onD.7IpTuQlxB7HW/haydXXike0qxVSLGBm',
    'System', 'Admin', '111-111-1111',
    '-', '-', '-', '11111', '-',
    'admin', 'active'
);


-- =============================================================================
-- 5. COURSES  (deferred sprint — unchanged from original)
-- =============================================================================
-- A course belongs to an instructor (instructor_id FK → users). The instructor
-- is also stored as a display name string (instructor_name) so the name shown
-- on cards does not change if the instructor's user account is later renamed.
--
-- ON DELETE CASCADE on instructor_id means deleting a user who owns courses
-- will also delete those courses and everything beneath them. This is
-- intentional — courses without an owner are not meaningful in this system.

CREATE TABLE courses (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    course_code     VARCHAR(20)                                  NOT NULL UNIQUE,
    course_name     VARCHAR(255)                                 NOT NULL,
    credit_hours    INT                                          NOT NULL,
    year            INT                                          NOT NULL,
    semester        ENUM('Winter', 'Spring', 'Summer', 'Fall')  NOT NULL,
    description     TEXT,
    instructor_id   INT                                          NOT NULL,
    instructor_name VARCHAR(255)                                 NOT NULL,
    status          ENUM('active', 'inactive')                   DEFAULT 'active',
    created_at      TIMESTAMP                                    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (instructor_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 6. ASSESSMENTS  (deferred sprint — unchanged from original)
-- =============================================================================
-- Each assessment belongs to exactly one course. Deleting a course removes all
-- its assessments via cascade, which in turn cascades to files.

CREATE TABLE assessments (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    course_id       INT                                                     NOT NULL,
    title           VARCHAR(255)                                            NOT NULL,
    description     TEXT,
    created_at      TIMESTAMP                                               DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 7. FILES  (deferred sprint — unchanged from original)
-- =============================================================================
-- Stores metadata for files uploaded to a specific assessment. The actual file
-- bytes are stored on disk under the uploads/ directory; file_path holds the
-- relative path from the project root so the application remains portable.
--
-- assessment_id is nullable to allow course-level file uploads if that feature
-- is added in the future, but in current usage all files belong to an assessment.

CREATE TABLE files (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    file_name     VARCHAR(255) NOT NULL,
    file_path     VARCHAR(255) NOT NULL,
    course_id     INT          NOT NULL,
    assessment_id INT          NULL,
    uploaded_by   INT          NOT NULL,
    -- feature_name identifies which feature uploaded this file, allowing each
    -- feature to list and manage only its own files within an assessment.
    -- Values: 'general' (course files view), 'exam_creation', 'practice_quiz',
    -- 'exam_grading_submission' (student's own verified exam upload).
    -- NULL means the file predates this column and belongs to the general view.
    feature_name  VARCHAR(50)  NULL,
    uploaded_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (course_id)     REFERENCES courses(id)     ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by)   REFERENCES users(id)       ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 8. COURSE ACCESS  (deferred sprint — unchanged from original)
-- =============================================================================
-- Controls which teachers and students have access to which courses.
--
-- Status values:
--   pending  — access requested but not yet reviewed (reserved for future use).
--   approved — user can see and interact with the course.
--   revoked  — access removed; row is retained for audit purposes.
--
-- The composite unique key (course_id, user_id, access_role) prevents a user
-- from having duplicate access records of the same role for the same course.
-- It also supports the ON DUPLICATE KEY UPDATE pattern used in grant_course_access()
-- in auth.py, which resets a revoked record to approved without creating a
-- second row.
--
-- updated_at uses ON UPDATE CURRENT_TIMESTAMP so the access audit trail
-- records when a status change occurred without requiring an explicit write.

CREATE TABLE course_access (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    course_id   INT                                        NOT NULL,
    user_id     INT                                        NOT NULL,
    access_role ENUM('teacher', 'student')                NOT NULL,
    status      ENUM('pending', 'approved', 'revoked')    NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_course_user_role (course_id, user_id, access_role),

    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)   REFERENCES users(id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 9. QUIZZES  (deferred sprint — ai_output_id column removed)
-- =============================================================================
-- Stores instructor-published quizzes linked to a course assessment.
-- The ai_output_id column that previously linked quizzes to the retired AI
-- prompt feature (ai_outputs table) has been removed. The table is retained
-- for the course management sprint where quizzes will be generated and
-- published through the integrated UReap quiz pipeline.
--
-- published       — controls whether quiz questions are visible to students.
-- grades_visible  — controls whether students can see their score after
--                   submitting, independently of question visibility.
-- grading_mode    — 'auto': True/False and MCQ graded at submission time;
--                   'manual': instructor enters scores per submission;
--                   'ai': instructor triggers an AI grading pass.

CREATE TABLE IF NOT EXISTS quizzes (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    assessment_id  INT          NOT NULL,
    title          VARCHAR(255) NOT NULL,
    published      TINYINT(1)   NOT NULL DEFAULT 0,
    grades_visible TINYINT(1)   NOT NULL DEFAULT 0,
    grading_mode   ENUM('auto', 'manual', 'ai') NOT NULL DEFAULT 'auto',
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 10. QUIZ QUESTIONS  (deferred sprint — unchanged from original)
-- =============================================================================
-- Stores individual questions belonging to a quiz. The question_type column
-- drives how the question is rendered and graded:
--
--   true_false    — two options ("True" / "False"); correct_answer is "True"
--                   or "False".
--   mcq           — multiple choice; options_json is a JSON array of choice
--                   strings; correct_answer is one of those strings.
--   short_answer  — free-text response; correct_answer holds the model answer
--                   used for display-only reference.
--
-- question_order controls rendering order within the quiz.

CREATE TABLE IF NOT EXISTS quiz_questions (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    quiz_id         INT                                          NOT NULL,
    question_text   TEXT                                         NOT NULL,
    question_type   ENUM('true_false', 'mcq', 'short_answer')   NOT NULL,
    options_json    TEXT                                         NULL,
    correct_answer  TEXT                                         NULL,
    question_order  INT                                          NOT NULL DEFAULT 0,

    FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 11. QUIZ SUBMISSIONS  (deferred sprint — unchanged from original)
-- =============================================================================
-- One submission record per student per quiz attempt. A student can only have
-- one submission per quiz (UNIQUE constraint on quiz_id, student_id).
--
-- manual_score   — overrides the auto-calculated score when the instructor
--                  grades manually or confirms an AI grading result.
-- grading_notes  — free-text feedback per submission from instructor or AI.

CREATE TABLE IF NOT EXISTS quiz_submissions (
    id            INT   AUTO_INCREMENT PRIMARY KEY,
    quiz_id       INT   NOT NULL,
    student_id    INT   NOT NULL,
    score         FLOAT NULL,
    manual_score  FLOAT NULL,
    grading_notes TEXT  NULL,
    submitted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_quiz_student (quiz_id, student_id),

    FOREIGN KEY (quiz_id)    REFERENCES quizzes(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 12. QUIZ ANSWERS  (deferred sprint — unchanged from original)
-- =============================================================================
-- Stores the student's response to each question in a submission. For
-- auto-graded question types (true_false, mcq), is_correct is set at
-- submission time. Short-answer questions leave is_correct as NULL.

CREATE TABLE IF NOT EXISTS quiz_answers (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    submission_id  INT  NOT NULL,
    question_id    INT  NOT NULL,
    answer_text    TEXT NULL,
    is_correct     TINYINT(1) NULL,

    FOREIGN KEY (submission_id) REFERENCES quiz_submissions(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id)   REFERENCES quiz_questions(id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 13. RAG INDEXES
-- =============================================================================
-- Tracks the on-disk FAISS index directory for each user's RAG document set.
-- One row per user — re-indexing overwrites via ON DUPLICATE KEY UPDATE.
--
-- The three FAISS binary files are derived from index_dir_path as:
--   {index_dir_path}/embeddings.npy
--   {index_dir_path}/faiss_index.index
--   {index_dir_path}/chunks.json
--
-- indexed_filenames_json holds a JSON array of the filenames included in the
-- current index (e.g. '["lecture1.pdf", "notes.docx"]'). This is required so
-- the Document Management UI can list previously indexed files per user without
-- reading from disk.
--
-- active_chat_session_id tracks which chat session snapshot is currently loaded
-- as the active index. When the user indexes new documents this is set to NULL.
-- When a past chat session is loaded via the History tab, this is set to that
-- session's UUID so the query tab knows which session is active without
-- comparing directory paths directly.

CREATE TABLE rag_indexes (
    id                       INT AUTO_INCREMENT PRIMARY KEY,
    user_id                  INT          NOT NULL,
    index_dir_path           VARCHAR(500) NOT NULL,
    indexed_filenames_json   TEXT         NULL,
    document_count           INT          NOT NULL DEFAULT 0,
    chunk_count              INT          NOT NULL DEFAULT 0,
    active_chat_session_id   VARCHAR(36)  NULL,
    created_at               TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_user_index (user_id),

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 14. RAG QUERY HISTORY
-- =============================================================================
-- Stores one row per conversation turn (user message or assistant response) in
-- the RAG chat feature. Turns belonging to the same conversation are grouped by
-- chat_session_id (a UUID generated when the first message of a new conversation
-- is sent).
--
-- Each chat session has a corresponding FAISS index snapshot saved on disk at
-- data/rag/{user_id}/{chat_session_id}/, which allows any past conversation to
-- be loaded and continued against the exact document set used at the time,
-- regardless of whether the user has re-indexed since then.
--
-- model_provider, model_name, and language are populated on assistant-role rows
-- only. They are NULL on user-role rows since those fields describe the model
-- that generated a response, not the user's input.

CREATE TABLE rag_query_history (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    chat_session_id  VARCHAR(36)              NOT NULL,
    user_id          INT                      NOT NULL,
    role             ENUM('user','assistant') NOT NULL,
    message_text     TEXT                     NOT NULL,
    model_provider   VARCHAR(100)             NULL,
    model_name       VARCHAR(100)             NULL,
    language         VARCHAR(20)              NULL,
    created_at       TIMESTAMP                DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 15. EXAM GRADING RESULTS
-- =============================================================================
-- Stores one row per graded student submission produced by the Exam Grading
-- feature. All rows from a single batch run share the same grading_session_id
-- (a UUID generated once per run) so the History tab can group and display
-- results by session without relying on text matching.
--
-- student_name and student_id_parsed are extracted from submission filenames
-- using the Name_ID.pdf convention. student_id_parsed is a raw string from
-- the filename, not a FK to users.id, as no user account linkage is performed
-- at this stage.
--
-- The questions_text, rubric, and sub_rubric used for a grading session are
-- stored redundantly per row to maintain a complete audit record for each
-- individual result independent of session state.

CREATE TABLE exam_grading_results (
    id                  INT  AUTO_INCREMENT PRIMARY KEY,
    grading_session_id  VARCHAR(36)  NOT NULL,
    graded_by           INT          NOT NULL,
    -- assessment_id links each grading session to the specific assessment it
    -- was run against, enabling the History tab to filter by assessment.
    -- CASCADE on delete removes all grading results when the assessment is
    -- deleted, ensuring no orphaned records remain.
    assessment_id       INT          NULL,
    student_name        VARCHAR(255),
    student_id_parsed   VARCHAR(100),
    questions_text      TEXT,
    rubric              TEXT,
    sub_rubric          TEXT,
    score               FLOAT,
    max_points          INT,
    feedback            TEXT,
    detailed_explanation TEXT,
    model_provider      VARCHAR(100),
    model_name          VARCHAR(100),
    graded_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (graded_by)     REFERENCES users(id)       ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 15B. EXAM SETUPS
-- =============================================================================
-- The canonical, persisted exam questions for an assessment, saved explicitly
-- by the teacher from the Setup Exam tab ("Save Exam Setup" button) so that
-- students can read the questions in their Submit My Exam view. Without this
-- table the questions only ever existed in the teacher's own browser session
-- state, invisible to students in their own separate session.
--
-- rubric/sub_rubric are stored here too (read by the grading pipeline) but
-- are never shown to students — only `questions` and `max_points` are
-- displayed in the student-facing view, since the rubric is the grading key.
--
-- One row per assessment (UNIQUE), upserted on every save.

CREATE TABLE exam_setups (
    id            INT  AUTO_INCREMENT PRIMARY KEY,
    assessment_id INT  NOT NULL UNIQUE,
    questions     TEXT NOT NULL,
    rubric        TEXT,
    sub_rubric    TEXT,
    max_points    INT  DEFAULT 100,
    set_by        INT  NOT NULL,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY (set_by)        REFERENCES users(id)       ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 16. EXAM CREATION QUESTIONS
-- =============================================================================
-- Stores questions generated by the Exam Creation feature in both modes:
--   variation   — generates variations of existing questions. Each row holds
--                 one variation; original_question_text holds the source.
--   from_topics — generates new questions from lecture content. Each row holds
--                 one question; original_question_text is NULL.
--
-- All questions from a single LLM call share a creation_session_id (UUID)
-- so the History tab can display and reload them as a grouped session.
--
-- question_type accommodates the from-topics output values: 'multiple-choice',
-- 'short-answer', 'problem-solving'. It is NULL for variation-mode rows
-- because the LLM output for variations does not include question_type.

CREATE TABLE exam_creation_questions (
    id                     INT  AUTO_INCREMENT PRIMARY KEY,
    creation_session_id    VARCHAR(36)  NOT NULL,
    user_id                INT          NOT NULL,
    -- assessment_id links generated question sets to the assessment they were
    -- created for. CASCADE on delete removes all generated questions when the
    -- assessment is deleted, ensuring no orphaned records remain.
    assessment_id          INT          NULL,
    creation_mode          ENUM('variation', 'from_topics') NOT NULL,
    original_question_text TEXT         NULL,
    question_text          TEXT         NOT NULL,
    question_type          VARCHAR(50)  NULL,
    topic                  VARCHAR(255) NULL,
    difficulty             VARCHAR(50)  NULL,
    answer_guidance        TEXT         NULL,
    created_at             TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)       ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 17. ADVISOR CHAT HISTORY
-- =============================================================================
-- Stores each conversation turn (user message or assistant response) for the
-- Advisor AI feature. Each logical conversation is identified by a
-- chat_session_id (UUID generated when a new conversation begins). The History
-- tab groups rows by chat_session_id to display and reload past sessions.
--
-- model_provider and model_name are populated on assistant-role rows only;
-- they are NULL on user-role rows.

CREATE TABLE advisor_chat_history (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    chat_session_id  VARCHAR(36)  NOT NULL,
    user_id          INT          NOT NULL,
    role             ENUM('user', 'assistant') NOT NULL,
    message_text     TEXT         NOT NULL,
    model_provider   VARCHAR(100) NULL,
    model_name       VARCHAR(100) NULL,
    language         VARCHAR(20)  NULL,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 18. WELLNESS CHAT HISTORY
-- =============================================================================
-- Stores each conversation turn for the Wellness Assistant chatbot. Structure
-- mirrors advisor_chat_history. The static Services Information tab is
-- stateless and has no corresponding table.

CREATE TABLE wellness_chat_history (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    chat_session_id  VARCHAR(36)  NOT NULL,
    user_id          INT          NOT NULL,
    role             ENUM('user', 'assistant') NOT NULL,
    message_text     TEXT         NOT NULL,
    model_provider   VARCHAR(100) NULL,
    model_name       VARCHAR(100) NULL,
    language         VARCHAR(20)  NULL,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 19. PRACTICE QUIZ GENERATED
-- =============================================================================
-- Stores one row per quiz generated through the Practice Quiz (Quiz Generator)
-- feature. Each row holds the complete question set as a JSON array so the
-- quiz can be re-displayed and re-attempted without re-querying the LLM.
--
-- questions_json contains an array of question objects, each with:
--   question_text, question_type, options, correct_answer, explanation,
--   topic, difficulty.
--
-- A generated quiz is private to the user who created it — always filter
-- queries by user_id. model_used stores the model ID string (not display name).

CREATE TABLE practice_quiz_generated (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT          NOT NULL,
    -- assessment_id links a generated quiz to the assessment the student was
    -- working under when they created it. Used to scope the instructor view
    -- and the student history tab to the current assessment.
    -- CASCADE on delete removes all generated quizzes when the assessment is
    -- deleted. This in turn cascade-deletes all practice_quiz_attempts rows
    -- via the quiz_id FK on that table.
    assessment_id  INT          NULL,
    -- source_filenames stores a JSON array of the original uploaded filenames
    -- used to generate this quiz (e.g. ["lecture1.pdf", "notes.docx"]).
    -- Displayed in the history tab so the student can identify which materials
    -- a quiz was generated from.
    source_filenames TEXT        NULL,
    questions_json LONGTEXT     NOT NULL,
    mc_count       INT          NOT NULL DEFAULT 0,
    tf_count       INT          NOT NULL DEFAULT 0,
    sa_count       INT          NOT NULL DEFAULT 0,
    difficulty     VARCHAR(50),
    topic_focus    VARCHAR(255) NULL,
    model_used     VARCHAR(100),
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)       ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- 20. PRACTICE QUIZ ATTEMPTS
-- =============================================================================
-- Stores each attempt a user makes on a generated practice quiz. Multiple
-- attempts per quiz are permitted — there is no UNIQUE constraint on
-- (user_id, quiz_id). The user_id column here is intentionally redundant with
-- practice_quiz_generated.user_id to allow direct ON DELETE CASCADE from users
-- and to support efficient per-user queries without a join.
--
-- answers_json is a JSON object keyed by question index (0-based string key),
-- e.g. {"0": "True", "1": "B", "2": "free text answer"}.
--
-- score is the percentage correct for auto-graded questions only (MCQ and
-- True/False). It is NULL when the quiz contained only short-answer questions,
-- as those have no machine-verifiable correct answer.

CREATE TABLE practice_quiz_attempts (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT    NOT NULL,
    quiz_id      INT    NOT NULL,
    -- assessment_id is stored directly on the attempt row (in addition to
    -- practice_quiz_generated) to allow direct per-assessment queries on
    -- attempts without a join to the generated quiz table. CASCADE on delete
    -- ensures attempts are removed when the assessment is deleted, consistent
    -- with the cascade on practice_quiz_generated.assessment_id above.
    assessment_id INT   NULL,
    answers_json LONGTEXT NOT NULL,
    score        FLOAT  NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)       REFERENCES users(id)                   ON DELETE CASCADE,
    FOREIGN KEY (quiz_id)       REFERENCES practice_quiz_generated(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id) REFERENCES assessments(id)             ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- DEMO DATA
-- =============================================================================
-- Seed data for client demonstrations. Provides two active teacher accounts
-- and one active student account, two courses (one per teacher), two
-- assessments per course, and course access records granting the student
-- access to both courses.
--
-- Insertion order respects all foreign key constraints:
--   1. Users       — no FK dependencies
--   2. Courses     — FK: instructor_id → users.id
--   3. Assessments — FK: course_id → courses.id
--   4. Course access — FK: course_id → courses.id, user_id → users.id
--
-- Passwords match the account username (e.g. teacher1 / teacher1).
-- Hashes are bcrypt cost factor 12, generated by generate_hashes.py.
-- No API keys are stored — all key columns are left as NULL.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Demo Users
-- -----------------------------------------------------------------------------

INSERT INTO users (
    username, email, password,
    first_name, last_name, phone,
    street_address, city, state_province, postal_code, country,
    role, status
)
VALUES
    (
        'teacher1', 'smitchell@tru.ca',
        '$2b$12$/rS1UN.VnqyrHe9zr9HZauoRCz1T/uNYpb/yFJbyHr0QRo3Bqbgf6',
        'Sarah', 'Mitchell', '250-371-5001',
        '900 McGill Road', 'Kamloops', 'British Columbia', 'V2C 0C8', 'Canada',
        'teacher', 'active'
    ),
    (
        'teacher2', 'jokafor@tru.ca',
        '$2b$12$btqmZNYTMcx4hVaOSzvmkuVU/khliK3j5ztSKtA0rEVLgYw0z9Lay',
        'James', 'Okafor', '250-371-5002',
        '900 McGill Road', 'Kamloops', 'British Columbia', 'V2C 0C8', 'Canada',
        'teacher', 'active'
    ),
    (
        'student1', 'echen@mytru.ca',
        '$2b$12$EGcfBRVat07osK2LnRzRG.YSkqkMiQ6LvKUIORa70krcyz4D3oZuu',
        'Emily', 'Chen', '250-371-5003',
        '900 McGill Road', 'Kamloops', 'British Columbia', 'V2C 0C8', 'Canada',
        'student', 'active'
    );


-- -----------------------------------------------------------------------------
-- Demo Courses
-- -----------------------------------------------------------------------------
-- instructor_id values reference the auto-incremented IDs assigned to the demo
-- users above. The admin account is always id=1, so teacher1=2, teacher2=3.

INSERT INTO courses (
    course_code, course_name, credit_hours, year, semester,
    description, instructor_id, instructor_name, status
)
VALUES
    (
        'COMP3710',
        'Applied Artificial Intelligence',
        3, 2025, 'Fall',
        'An introduction to classical and modern AI techniques including '
        'machine learning, neural networks, and practical LLM integration.',
        2, 'Sarah Mitchell',
        'active'
    ),
    (
        'COMP3610',
        'Database Systems',
        3, 2025, 'Fall',
        'Relational database design, SQL, normalisation, and an introduction '
        'to database-backed application development.',
        3, 'James Okafor',
        'active'
    );


-- -----------------------------------------------------------------------------
-- Demo Assessments
-- -----------------------------------------------------------------------------
-- course_id values reference the auto-incremented IDs assigned to the courses
-- above. COMP3710=1, COMP3610=2.

INSERT INTO assessments (course_id, title, description)
VALUES
    (1, 'Midterm Exam',  'Covers AI fundamentals, search algorithms, and machine learning basics.'),
    (1, 'Final Exam',    'Comprehensive exam covering all course material including LLMs and neural networks.'),
    (2, 'Midterm Quiz',  'Tests understanding of relational model, ER diagrams, and basic SQL.'),
    (2, 'Final Exam',    'Comprehensive exam covering normalisation, transactions, and database design.');


-- -----------------------------------------------------------------------------
-- Demo Course Access
-- -----------------------------------------------------------------------------
-- Grant student1 (id=4) approved student access to both courses so they appear
-- in the student's course list immediately on login.

INSERT INTO course_access (course_id, user_id, access_role, status)
VALUES
    -- Teacher access: each teacher must have an approved course_access record
    -- for their own course. The application fetches visible courses via a JOIN
    -- on course_access, so instructor_id ownership alone is not sufficient.
    (1, 2, 'teacher', 'approved'),   -- teacher1 (Sarah Mitchell) → COMP3710
    (2, 3, 'teacher', 'approved'),   -- teacher2 (James Okafor)   → COMP3610
    -- Student access: student1 (Emily Chen) granted access to both courses.
    (1, 4, 'student', 'approved'),   -- student1 → COMP3710
    (2, 4, 'student', 'approved');   -- student1 → COMP3610