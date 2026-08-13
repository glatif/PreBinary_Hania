# =============================================================================
# plagiarism.py — AI-based plagiarism / similarity scoring
# =============================================================================
# Computes pairwise similarity between students' submissions on the same
# assessment using the app's existing local sentence-embedding model
# (embedding_wrapper.py, already used by the RAG feature) — no paid API key
# required. Pairs above SIMILARITY_FLAG_THRESHOLD get one additional LLM
# call each to produce a short explanation of the overlap. Results are
# upserted into plagiarism_results, keyed by (assessment_id, feature_name,
# student_a_id, student_b_id) with student_a_id always the smaller ID.
#
# Run on-demand from Admin Panel -> Maintenance -> "Run Plagiarism Scan",
# not automatically per-submission, to control cost/latency as class size
# grows — mirrors the existing "Run Proctoring Analysis Now" pattern.
# =============================================================================

import json
from itertools import combinations
from typing import Dict, List

import numpy as np

from db import get_connection
from src.utils.embedding_wrapper import get_embedding_model
from src.utils.llm_utils import generate_llm_response, MODELS

SIMILARITY_FLAG_THRESHOLD = 0.85

_embedding_model = None


def _model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = get_embedding_model()
    return _embedding_model


def compute_similarity(text_a: str, text_b: str) -> float:
    """
    Return cosine similarity between two texts' embeddings, in [0, 1].
    Uses the app's local sentence-embedding model — no external API call.
    """
    if not text_a.strip() or not text_b.strip():
        return 0.0
    vectors = _model().encode([text_a, text_b])
    a, b = np.asarray(vectors[0]), np.asarray(vectors[1])
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.clip(np.dot(a, b) / denom, 0.0, 1.0))


def _get_exam_grading_texts(assessment_id: int) -> Dict[int, str]:
    """{student_id: extracted submission text} from uploaded exam_grading_submission files."""
    from src.features.exam_grading.exam_grading_feature import (
        get_student_exam_submissions,
        extract_text_from_file,
    )
    texts = {}
    for row in get_student_exam_submissions(assessment_id):
        try:
            texts[row["uploaded_by"]] = extract_text_from_file(row["file_path"])
        except Exception:
            continue
    return texts


def _get_oral_exam_texts(assessment_id: int) -> Dict[int, str]:
    """{student_id: concatenated answer transcripts} for an oral exam assessment."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT student_id, transcript FROM oral_exam_responses
            WHERE assessment_id = %s AND skipped = 0 AND transcript IS NOT NULL
            ORDER BY student_id, question_number
            """,
            (assessment_id,),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    texts: Dict[int, List[str]] = {}
    for r in rows:
        texts.setdefault(r["student_id"], []).append(r["transcript"] or "")
    return {sid: "\n".join(parts) for sid, parts in texts.items()}


def _get_practice_quiz_texts(assessment_id: int) -> Dict[int, str]:
    """{student_id: concatenated short-answer text} for the practice quiz feature."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT a.user_id, a.answers_json, g.questions_json
            FROM practice_quiz_attempts a
            JOIN practice_quiz_generated g ON a.quiz_id = g.id
            WHERE a.assessment_id = %s
            """,
            (assessment_id,),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    texts = {}
    for r in rows:
        try:
            questions = json.loads(r["questions_json"] or "[]")
            answers   = {int(k): v for k, v in json.loads(r["answers_json"] or "{}").items()}
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        parts = [
            str(answers[i]) for i, q in enumerate(questions)
            if q.get("question_type") == "short_answer" and i in answers and answers[i]
        ]
        if parts:
            texts[r["user_id"]] = "\n".join(parts)
    return texts


_TEXT_GETTERS = {
    "exam_grading": _get_exam_grading_texts,
    "oral_exam": _get_oral_exam_texts,
    "practice_quiz": _get_practice_quiz_texts,
}


def _explain_similarity(text_a: str, text_b: str) -> str:
    """One short LLM call explaining why two flagged submissions overlap."""
    prompt = (
        "Two students' exam answers were flagged as highly similar by an "
        "automated similarity check. In 2-3 sentences, describe what "
        "specifically overlaps between them (phrasing, structure, specific "
        "claims) — be factual and concise, not accusatory; the instructor "
        "will make the final judgment.\n\n"
        f"--- Submission A ---\n{text_a[:3000]}\n\n"
        f"--- Submission B ---\n{text_b[:3000]}"
    )
    try:
        model = next(iter(MODELS.values()))
        return generate_llm_response(prompt, model, force_json=False).strip()
    except Exception as exc:
        return f"(Explanation unavailable: {exc})"


def run_plagiarism_scan(assessment_id: int, feature_name: str) -> Dict[str, int]:
    """
    Compute pairwise similarity across every pair of students' submissions
    for one assessment/feature, upsert results into plagiarism_results, and
    return {"pairs_checked": n, "pairs_flagged": n}.
    """
    getter = _TEXT_GETTERS.get(feature_name)
    if getter is None:
        raise ValueError(f"Unknown feature_name for plagiarism scan: {feature_name!r}")

    texts = {sid: t for sid, t in getter(assessment_id).items() if t and t.strip()}
    student_ids = sorted(texts.keys())

    pairs_checked = 0
    pairs_flagged = 0
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        for sid_a, sid_b in combinations(student_ids, 2):
            similarity = compute_similarity(texts[sid_a], texts[sid_b])
            pairs_checked += 1
            explanation = None
            if similarity >= SIMILARITY_FLAG_THRESHOLD:
                pairs_flagged += 1
                explanation = _explain_similarity(texts[sid_a], texts[sid_b])

            cursor.execute(
                """
                INSERT INTO plagiarism_results
                    (assessment_id, feature_name, student_a_id, student_b_id, similarity_score, llm_explanation)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    similarity_score = VALUES(similarity_score),
                    llm_explanation  = VALUES(llm_explanation)
                """,
                (assessment_id, feature_name, sid_a, sid_b, similarity, explanation),
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {"pairs_checked": pairs_checked, "pairs_flagged": pairs_flagged}


def get_plagiarism_results(assessment_id: int, feature_name: str) -> List[Dict]:
    """Return flagged pairs (similarity_score >= threshold) with student names, highest first."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                p.similarity_score, p.llm_explanation, p.computed_at,
                ua.first_name AS a_first, ua.last_name AS a_last,
                ub.first_name AS b_first, ub.last_name AS b_last
            FROM plagiarism_results p
            JOIN users ua ON ua.id = p.student_a_id
            JOIN users ub ON ub.id = p.student_b_id
            WHERE p.assessment_id = %s AND p.feature_name = %s AND p.similarity_score >= %s
            ORDER BY p.similarity_score DESC
            """,
            (assessment_id, feature_name, SIMILARITY_FLAG_THRESHOLD),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
