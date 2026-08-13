# =============================================================================
# gradebook.py — combined multi-assessment gradebook export
# =============================================================================
# Builds one row per enrolled student (First/Last/ID/email) with one column
# per assessment/feature combination in the course, for a single CSV
# download covering every quiz/exam/oral exam grade at once. Used from the
# course management area in app.py, next to _render_course_access_panel().
#
# The three assessment systems store grades differently, so each is
# collapsed to "one number per student per assessment" independently:
#   - Practice Quiz (practice_quiz_attempts): real student_id FK — takes
#     each student's most recent attempt for that assessment.
#   - Exam Grading (exam_grading_results): students are identified by
#     free-text student_name/student_id_parsed, not a FK (grading can run
#     against a bulk ZIP of files never tied to a login) — matched back to
#     the enrolled roster by roll_no first, then by normalized full name.
#     Unmatched rows are simply omitted from that student's column. Takes
#     the most recent grading session for that assessment.
#   - Oral Examination (oral_exam_grading_results): real student_id FK,
#     stored per-question — summed per student for the most recent grading
#     session for that assessment.
# =============================================================================

import re
from typing import Dict, List

import pandas as pd

from db import get_connection


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _get_roster(course_id: int) -> List[Dict]:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT u.id, u.first_name, u.last_name, u.roll_no, u.email
            FROM course_access ca
            JOIN users u ON u.id = ca.user_id
            WHERE ca.course_id = %s AND ca.access_role = 'student' AND ca.status = 'approved'
            ORDER BY u.last_name, u.first_name
            """,
            (course_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def _get_assessments(course_id: int) -> List[Dict]:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, title FROM assessments WHERE course_id = %s ORDER BY id",
            (course_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def _get_latest_quiz_scores(assessment_id: int) -> Dict[int, float]:
    """{student_id: most recent practice_quiz_attempts.score} for this assessment."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT a.user_id, a.score
            FROM practice_quiz_attempts a
            INNER JOIN (
                SELECT user_id, MAX(submitted_at) AS latest
                FROM practice_quiz_attempts
                WHERE assessment_id = %s
                GROUP BY user_id
            ) latest_a ON latest_a.user_id = a.user_id AND latest_a.latest = a.submitted_at
            WHERE a.assessment_id = %s
            """,
            (assessment_id, assessment_id),
        )
        return {row["user_id"]: row["score"] for row in cursor.fetchall() if row["score"] is not None}
    finally:
        cursor.close()
        conn.close()


def _get_latest_exam_grading_rows(assessment_id: int) -> List[Dict]:
    """Rows (student_name, student_id_parsed, score, max_points) from the most recent grading session."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT grading_session_id FROM exam_grading_results
            WHERE assessment_id = %s ORDER BY graded_at DESC LIMIT 1
            """,
            (assessment_id,),
        )
        latest = cursor.fetchone()
        if not latest:
            return []
        cursor.execute(
            """
            SELECT student_name, student_id_parsed, score, max_points
            FROM exam_grading_results
            WHERE grading_session_id = %s
            """,
            (latest["grading_session_id"],),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def _get_latest_oral_exam_scores(assessment_id: int) -> Dict[int, Dict[str, float]]:
    """{student_id: {"score": total, "max_points": total}} from the most recent grading session."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT grading_session_id FROM oral_exam_grading_results
            WHERE assessment_id = %s ORDER BY graded_at DESC LIMIT 1
            """,
            (assessment_id,),
        )
        latest = cursor.fetchone()
        if not latest:
            return {}
        cursor.execute(
            """
            SELECT student_id, SUM(score) AS total_score, SUM(max_points) AS total_max_points
            FROM oral_exam_grading_results
            WHERE grading_session_id = %s
            GROUP BY student_id
            """,
            (latest["grading_session_id"],),
        )
        return {
            row["student_id"]: {"score": row["total_score"], "max_points": row["total_max_points"]}
            for row in cursor.fetchall()
        }
    finally:
        cursor.close()
        conn.close()


def build_course_gradebook(course_id: int) -> pd.DataFrame:
    """
    Build the combined gradebook for a course: one row per enrolled student,
    one column per assessment/feature combination that has any recorded
    grade. Cells are "score/max_points" strings, blank where a student has
    no recorded grade for that column.
    """
    roster = _get_roster(course_id)
    if not roster:
        return pd.DataFrame(columns=["First Name", "Last Name", "ID Number", "Email"])

    by_roll_no = {r["roll_no"]: r["id"] for r in roster if r["roll_no"]}
    by_name = {_normalize_name(f"{r['first_name']} {r['last_name']}"): r["id"] for r in roster}

    rows = {
        r["id"]: {
            "First Name": r["first_name"] or "",
            "Last Name": r["last_name"] or "",
            "ID Number": r["roll_no"] or "",
            "Email": r["email"] or "",
        }
        for r in roster
    }

    for assessment in _get_assessments(course_id):
        assessment_id = assessment["id"]
        title = assessment["title"]

        quiz_scores = _get_latest_quiz_scores(assessment_id)
        if quiz_scores:
            col = f"{title} — Quiz (%)"
            for student_id, score in quiz_scores.items():
                if student_id in rows:
                    rows[student_id][col] = f"{score:.1f}"

        exam_rows = _get_latest_exam_grading_rows(assessment_id)
        if exam_rows:
            col = f"{title} — Exam"
            for r in exam_rows:
                student_id = by_roll_no.get(r.get("student_id_parsed")) or by_name.get(
                    _normalize_name(r.get("student_name", ""))
                )
                if student_id in rows:
                    rows[student_id][col] = f"{r['score']}/{r['max_points']}"

        oral_scores = _get_latest_oral_exam_scores(assessment_id)
        if oral_scores:
            col = f"{title} — Oral Exam"
            for student_id, totals in oral_scores.items():
                if student_id in rows:
                    rows[student_id][col] = f"{totals['score']}/{totals['max_points']}"

    return pd.DataFrame(list(rows.values())).fillna("")
