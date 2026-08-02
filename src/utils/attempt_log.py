# =============================================================================
# attempt_log.py — cross-feature assessment attempt activity log
# =============================================================================
# Records the full lifecycle of a student's attempt at an assessment
# (Oral Examination or Practice Quiz) — started, question reached, timed
# out, answer submitted, completed — not just the pass/fail identity check
# already covered by verification_attempts (exam_verification_feature.py).
#
# The point is to make abandoned attempts visible: previously, if a student
# opened an oral exam or quiz and never finished, nothing was written to the
# database at all, so a teacher had no way to tell "never started" apart
# from "started but gave up". get_incomplete_attempts() answers that by
# finding every (user, assessment, feature) with a 'started' event but no
# terminal event.
# =============================================================================

from typing import List, Dict

from db import get_connection

# Event types that mark an attempt as finished — anything with a 'started'
# event but none of these is surfaced by get_incomplete_attempts().
_TERMINAL_EVENT_TYPES = ("completed", "submitted")


def log_attempt_event(
    user_id: int,
    assessment_id: int,
    feature_name: str,
    event_type: str,
    session_id: str = None,
    question_number: int = None,
    detail: str = None,
) -> None:
    """
    Append one row to assessment_attempt_log. Never raises — a logging
    failure must not block the student's actual exam/quiz flow, so any DB
    error here is swallowed silently (mirrors the "errors surfaced via
    st.warning, not raised" convention used for non-critical writes
    elsewhere, e.g. save_practice_quiz_file() in quiz_generator_feature.py).
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO assessment_attempt_log
                    (user_id, assessment_id, feature_name, session_id, event_type, question_number, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, assessment_id, feature_name, session_id, event_type, question_number, detail),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    except Exception:
        pass


def get_incomplete_attempts(assessment_id: int, feature_name: str) -> List[Dict]:
    """
    Return one row per student who has a 'started' event for this
    assessment/feature but no terminal ('completed' or 'submitted') event —
    i.e. they opened it and never finished. Includes the last question
    number reached and the timestamp of their most recent activity, so a
    teacher can see how far they got and how long ago.
    """
    # Expanded to individual placeholders rather than passing
    # _TERMINAL_EVENT_TYPES as a single tuple param — mysql-connector's C
    # extension (unlike its pure-Python fallback) does not support expanding
    # a tuple param into an IN (...) list and raises
    # "Python type tuple cannot be converted" if you try.
    placeholders = ", ".join(["%s"] * len(_TERMINAL_EVENT_TYPES))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT
                l.user_id,
                u.first_name,
                u.last_name,
                u.roll_no,
                MAX(l.created_at) AS last_activity,
                MAX(CASE WHEN l.question_number IS NOT NULL THEN l.question_number END) AS last_question_reached
            FROM assessment_attempt_log l
            JOIN users u ON u.id = l.user_id
            WHERE l.assessment_id = %s
              AND l.feature_name  = %s
            GROUP BY l.user_id, u.first_name, u.last_name, u.roll_no
            HAVING SUM(l.event_type IN ({placeholders})) = 0
            ORDER BY last_activity DESC
            """,
            (assessment_id, feature_name, *_TERMINAL_EVENT_TYPES),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()
