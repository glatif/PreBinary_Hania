-- =============================================================================
-- migration_widen_exam_grading_text_columns.sql
-- =============================================================================
-- Widens exam_grading_results' TEXT columns to MEDIUMTEXT.
--
-- TEXT caps at 65,535 bytes. GitHub Models' max_tokens is set to 16384
-- specifically so multi-question grading responses aren't truncated (see the
-- comment in llm_utils.py's stream_github_llm()/generate_github_response()),
-- which means detailed_explanation (which stores the model's raw response
-- in the JSON-parse-failure fallback path) can legitimately exceed 65,535
-- bytes for a long, multi-question exam. When that INSERT throws
-- "Data too long for column", it was an uncaught exception inside
-- save_exam_grading_result() that the grading loop's outer except swallowed
-- — the student was graded and shown live, but never persisted, so they
-- silently vanished from the History tab. MEDIUMTEXT (16,777,215 bytes) has
-- enough headroom that this shouldn't recur in practice.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_widen_exam_grading_text_columns.sql
-- =============================================================================

ALTER TABLE exam_grading_results
    MODIFY COLUMN questions_text       MEDIUMTEXT,
    MODIFY COLUMN rubric               MEDIUMTEXT,
    MODIFY COLUMN sub_rubric           MEDIUMTEXT,
    MODIFY COLUMN feedback             MEDIUMTEXT,
    MODIFY COLUMN detailed_explanation MEDIUMTEXT;
