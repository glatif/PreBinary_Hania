# =============================================================================
# oral_examination_feature.py — Oral Examination Feature
# =============================================================================
# Provides the full Oral Examination UI and all supporting database operations.
#
# Feature overview:
#   Teachers generate a fixed set of open-ended questions from source material
#   using an LLM, save them with a grading rubric, and students answer each
#   question by speaking into their microphone. Answers are recorded as audio,
#   transcribed to text, and the whole session is graded by an LLM in one
#   batch pass once the teacher triggers grading — closely mirroring the
#   Exam Grading feature's setup -> submit -> grade -> history flow, reusing
#   its create_grading_prompt() and the shared proctoring stack unchanged.
#
# Proctoring:
#   Questions are answered under the same render_proctor_monitor() used by
#   Exam Grading — screen-share, webcam (including gaze/head-pose analysis),
#   keystroke, and mouse logging all run for the full duration of the exam,
#   keyed by (session_id, student_id, assessment_id) exactly like the
#   existing quiz_proctor_* tables. No proctoring code is duplicated here;
#   the Grading Results tab surfaces the same summary functions Exam Grading
#   already uses to display it to the teacher.
#
# Course/assessment context:
#   This feature is always rendered inside a specific assessment. The selected
#   course and assessment are read from session state using the tab-namespaced
#   keys set by app.py's navigation system:
#     st.session_state["oral_examination_selected_course"]     -> {"id": int, "name": str}
#     st.session_state["oral_examination_selected_assessment"] -> {"id": int, "title": str}
# =============================================================================

import json
import uuid
import streamlit as st
import pandas as pd
from typing import List, Dict, Any

from db import get_connection
from auth import save_uploaded_file

from src.utils.llm_utils import MODELS, MODEL_PROVIDERS, generate_llm_response, strip_llm_json, transcribe_audio
from src.features.exam_verification.exam_verification_feature import verify_student_identity
from src.features.exam_grading.exam_grading_feature import create_grading_prompt
from src.features.proctoring.proctoring_feature import (
    render_proctor_monitor,
    get_proctor_summary_by_user_assessment,
    get_proctor_webcam_summary_by_user_assessment,
    get_proctor_keystrokes_by_user_assessment,
    format_keystrokes_for_display,
    get_proctor_mouse_events_by_user_assessment,
    format_mouse_events_for_display,
)


# =============================================================================
# LLM PROMPT BUILDER — question generation
# =============================================================================

def create_oral_question_generation_prompt(
    content: str,
    num_questions: int,
    difficulty: str,
    topic_filters: str = "",
) -> str:
    """
    Build the LLM prompt used to generate open-ended oral exam questions.

    Unlike quiz_generator's multiple-choice/true-false/short-answer prompt,
    every question here must be answerable out loud, so the JSON schema has
    no options/correct_answer fields — just a question the student explains
    or justifies verbally.

    Small local models (e.g. Ollama's deepseek-r1:1.5B) tend to stop after
    writing just one question unless the requested count is reinforced
    several times and the model is walked through the list step by step —
    quiz_generator.py's prompt does the same repetition for the same reason.
    The JSON template also shows two example entries (not one) so the model
    has a concrete visual cue that the array should hold more than a single
    item.
    """
    json_template = """
{
  "questions": [
    {
      "question_number": 1,
      "question_text": "An open-ended question the student must answer out loud"
    },
    {
      "question_number": 2,
      "question_text": "A second open-ended question the student must answer out loud"
    }
  ]
}
"""
    topic_filter_text = f"\nFocus specifically on these topics: {topic_filters}" if topic_filters else ""

    return f"""You are an expert educator writing questions for a spoken oral examination.

CONTENT TO ANALYZE:
{content}

REQUIREMENTS:
- Generate exactly {num_questions} open-ended questions a student must answer verbally — no multiple choice, no true/false.
- Difficulty level: {difficulty}
- Each question should require the student to explain, justify, or apply a concept from the content, not just recall a fact.{topic_filter_text}

INSTRUCTIONS:
1. Carefully read and understand the provided content.
2. Write question 1, covering one key concept from the content.
3. Write question 2, covering a different key concept than question 1.
4. Continue this pattern until you have written all {num_questions} questions, each covering a different part of the content for comprehensive coverage — do not stop early.
5. Match the specified difficulty level:
   - Easy: Direct recall of facts
   - Medium: Application of concepts
   - Hard: Analysis and synthesis of information

OUTPUT FORMAT:
Respond with ONLY valid JSON in this exact format (the example below shows 2 entries only to illustrate the shape — your output must contain {num_questions} entries):
{json_template.strip()}

Make sure your response is valid JSON that can be parsed. The "questions" array MUST contain exactly {num_questions} entries, numbered sequentially starting at 1. Do not stop before reaching {num_questions} questions.
"""


# =============================================================================
# DATABASE WRITE OPERATIONS — setup
# =============================================================================

def save_oral_exam_setup(
    assessment_id: int,
    questions: str,
    rubric: str,
    max_points_per_question: int,
    set_by: int,
) -> None:
    """
    Persist the canonical oral exam setup for an assessment. One row per
    assessment — upserted on every save, since a teacher revising the exam
    should replace the prior version rather than accumulate duplicates.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO oral_exam_setups (assessment_id, questions, rubric, max_points_per_question, set_by)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                questions = VALUES(questions),
                rubric = VALUES(rubric),
                max_points_per_question = VALUES(max_points_per_question),
                set_by = VALUES(set_by)
            """,
            (assessment_id, questions, rubric, max_points_per_question, set_by),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_oral_exam_setup(assessment_id: int) -> Dict:
    """Return the saved oral exam setup for an assessment, or None if not yet saved."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT questions, rubric, max_points_per_question, updated_at "
            "FROM oral_exam_setups WHERE assessment_id = %s",
            (assessment_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# DATABASE WRITE OPERATIONS — student responses
# =============================================================================

def save_oral_exam_response(
    session_id: str,
    assessment_id: int,
    student_id: int,
    question_number: int,
    question_text: str,
    audio_file_path: str,
    transcript: str,
) -> None:
    """
    Persist one answered question: the saved audio path and its transcript.

    Upserted on the (assessment_id, student_id, question_number) unique key
    rather than a blind INSERT — a double-click on "Submit Answer" or a
    resubmit before the page rerenders would otherwise race past the
    Streamlit-layer "already answered" check and insert two rows for the same
    question, letting a single answer be graded twice.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO oral_exam_responses
                (session_id, assessment_id, student_id, question_number, question_text, audio_file_path, transcript)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                session_id      = VALUES(session_id),
                question_text   = VALUES(question_text),
                audio_file_path = VALUES(audio_file_path),
                transcript      = VALUES(transcript),
                answered_at     = CURRENT_TIMESTAMP
            """,
            (session_id, assessment_id, student_id, question_number, question_text, audio_file_path, transcript),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_oral_exam_responses(assessment_id: int, student_id: int) -> List[Dict]:
    """Return one student's answered questions for an assessment, in question order."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT question_number, question_text, audio_file_path, transcript, answered_at
            FROM oral_exam_responses
            WHERE assessment_id = %s AND student_id = %s
            ORDER BY question_number ASC
            """,
            (assessment_id, student_id),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def get_oral_exam_responses_for_assessment(assessment_id: int) -> List[Dict]:
    """
    Return every student's answered questions for an assessment in one query,
    used by the Grading Results tab so grading a whole class doesn't issue one
    get_oral_exam_responses() round-trip per student.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT student_id, question_number, question_text, audio_file_path, transcript, answered_at
            FROM oral_exam_responses
            WHERE assessment_id = %s
            ORDER BY student_id ASC, question_number ASC
            """,
            (assessment_id,),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def get_students_with_oral_responses(assessment_id: int) -> List[Dict]:
    """
    Return one row per student who has answered at least one question for this
    assessment, with their answered-question count so the Grading Results tab
    can tell which students have completed every question.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT r.student_id, u.first_name, u.last_name, u.roll_no,
                   COUNT(*) AS answered_count
            FROM oral_exam_responses r
            JOIN users u ON u.id = r.student_id
            WHERE r.assessment_id = %s
            GROUP BY r.student_id, u.first_name, u.last_name, u.roll_no
            ORDER BY u.first_name ASC, u.last_name ASC
            """,
            (assessment_id,),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# DATABASE WRITE OPERATIONS — grading
# =============================================================================

def save_oral_exam_grading_result(
    grading_session_id: str,
    graded_by: int,
    assessment_id: int,
    student_id: int,
    student_name: str,
    question_number: int,
    question_text: str,
    transcript: str,
    score: float,
    max_points: int,
    feedback: str,
    detailed_explanation: str,
    model_name: str,
) -> None:
    """
    Persist one graded question response. One row per (student, question) pair;
    all rows produced by a single grading run share the same
    grading_session_id so the History tab can group and display them as a batch.
    """
    model_provider = MODEL_PROVIDERS.get(model_name)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO oral_exam_grading_results (
                grading_session_id, graded_by, assessment_id, student_id, student_name,
                question_number, question_text, transcript, score, max_points,
                feedback, detailed_explanation, model_provider, model_name
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                grading_session_id, graded_by, assessment_id, student_id, student_name,
                question_number, question_text, transcript, score, max_points,
                feedback, detailed_explanation, model_provider, model_name,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_oral_exam_grading_sessions(user_id: int, assessment_id: int) -> List[Dict]:
    """Return all grading sessions run by the given user within the given assessment."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT grading_session_id, MAX(graded_at) AS graded_at, COUNT(*) AS result_count
            FROM oral_exam_grading_results
            WHERE graded_by = %s AND assessment_id = %s
            GROUP BY grading_session_id
            ORDER BY graded_at DESC
            """,
            (user_id, assessment_id),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def get_oral_exam_grading_session_results(grading_session_id: str, user_id: int) -> List[Dict]:
    """Return all individual question results belonging to a specific grading session."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT student_id, student_name, question_number, question_text, transcript,
                   score, max_points, feedback, detailed_explanation,
                   model_provider, model_name, graded_at
            FROM oral_exam_grading_results
            WHERE grading_session_id = %s AND graded_by = %s
            ORDER BY student_name ASC, question_number ASC
            """,
            (grading_session_id, user_id),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# STUDENT — "Take Oral Exam"
# =============================================================================
# Questions are revealed one at a time and are never shown in advance — a real
# oral exam shouldn't give a student prep time on the next question the way
# Exam Grading's upfront question list does. Once a student has answered
# every question the exam is locked; there is no re-submission, unlike Exam
# Grading's file re-upload allowance, because a spoken exam is a one-attempt
# event by nature.

def _render_student_oral_exam(
    course_id: int,
    course_name: str,
    assessment_id: int,
    assessment_title: str,
) -> None:
    user = st.session_state.user

    st.markdown("### 🎤 Oral Examination")

    if not assessment_id:
        st.warning("Select a course and assessment first.")
        return

    setup = get_oral_exam_setup(assessment_id)
    if not setup or not setup.get("questions"):
        st.info("Your instructor has not published the oral exam questions yet. Check back later.")
        return

    questions = json.loads(setup["questions"])
    total_questions = len(questions)

    existing = get_oral_exam_responses(assessment_id, int(user["id"]))
    if len(existing) >= total_questions:
        st.success(f"You have already completed this oral exam ({len(existing)} question(s) answered).")
        with st.expander("Review your answers", expanded=False):
            for r in existing:
                st.markdown(f"**Q{r['question_number']}. {r['question_text']}**")
                st.caption(r.get("transcript") or "(no transcript)")
        return

    st.caption(
        f"This oral exam has {total_questions} question(s). Questions are revealed "
        "one at a time and are not shown in advance."
    )

    # Spoken answers are transcribed via Groq or OpenAI's Whisper endpoint
    # (see transcribe_audio() in llm_utils.py) — there's no offline/local
    # transcription option. Checked here, before identity verification and
    # recording, so a student finds out up front rather than after already
    # completing the camera verification and recording an answer that can't
    # be transcribed.
    if not st.session_state.get("groq_api_key") and not st.session_state.get("openai_api_key"):
        st.warning(
            "⚠️ This oral exam requires a Groq or OpenAI API key on your account to transcribe "
            "your spoken answers — neither is set. Go to **Profile → AI API Keys**, save a Groq "
            "or OpenAI key, then come back here to start the exam."
        )
        return

    if not verify_student_identity(user, gate_key=f"oral_exam_{assessment_id}"):
        return

    session_key = f"oral_exam_session_id_{assessment_id}"
    if session_key not in st.session_state:
        st.session_state[session_key] = str(uuid.uuid4())
    session_id = st.session_state[session_key]

    render_proctor_monitor(
        gate_key=f"oral_exam_{assessment_id}",
        user=user,
        quiz_id=None,
        assessment_id=assessment_id,
    )

    st.success("Identity verified. Proctoring is active for the remainder of this exam.")

    answered_numbers = {r["question_number"] for r in existing}
    next_question = next(
        (q for q in questions if q["question_number"] not in answered_numbers), None
    )
    if next_question is None:
        st.rerun()
        return

    st.divider()
    st.markdown(f"**Question {next_question['question_number']} of {total_questions}**")
    st.markdown(f"### {next_question['question_text']}")

    audio = st.audio_input(
        "Record your answer",
        key=f"oral_audio_{assessment_id}_{next_question['question_number']}",
    )

    if audio and st.button(
        "Submit Answer",
        type="primary",
        key=f"oral_submit_{assessment_id}_{next_question['question_number']}",
    ):
        audio_bytes = audio.getvalue()
        audio_name = getattr(audio, "name", "answer.wav") or "answer.wav"
        with st.spinner("Saving and transcribing your answer..."):
            try:
                _saved_name, saved_path = save_uploaded_file(
                    file_bytes=audio_bytes,
                    original_name=f"q{next_question['question_number']}_{audio_name}",
                    course_name=course_name,
                    assessment_name=assessment_title,
                    course_id=course_id,
                    feature_name="oral_examination_response",
                )
                transcript = transcribe_audio(audio_bytes, audio_name)
                # transcribe_audio() reports failures as an "Error: ..." string
                # rather than raising (see llm_utils.py), so that it can be
                # displayed directly like generate_llm_response()'s errors. A
                # failed transcript must NOT be saved as the student's answer —
                # it would otherwise be graded as if it were real speech. The
                # audio itself is already safely on disk at saved_path, so the
                # student can simply retry without losing their recording.
                if transcript.startswith("Error:"):
                    st.error(
                        f"Could not transcribe your answer: {transcript} "
                        "Your recording was not lost — please try submitting again."
                    )
                else:
                    save_oral_exam_response(
                        session_id=session_id,
                        assessment_id=assessment_id,
                        student_id=int(user["id"]),
                        question_number=next_question["question_number"],
                        question_text=next_question["question_text"],
                        audio_file_path=saved_path,
                        transcript=transcript,
                    )
                    st.rerun()
            except Exception as exc:
                st.error(f"Could not submit your answer: {exc}")


# =============================================================================
# TEACHER/ADMIN — Setup Exam
# =============================================================================

def _render_oral_exam_setup(assessment_id: int, set_by: int) -> None:
    if not assessment_id:
        st.warning("Select a course and assessment first.")
        return

    with st.expander("How this works", expanded=True):
        st.markdown(
            "**Step 1 — Setup Exam (this tab)**  \n"
            "Paste the topic or source material the questions should cover, choose "
            "how many questions and how hard they should be, then click "
            "**Generate Questions with AI**. Review and edit the generated questions, "
            "add a grading rubric, and save.  \n\n"
            "**Step 2 — Grading Results**  \n"
            "Once students have answered every question, click **Grade All Submissions** "
            "and the AI will score every response against your rubric.  \n\n"
            "**Step 3 — History**  \n"
            "Revisit past grading sessions for this assessment."
        )

    questions_key = f"oral_setup_questions_{assessment_id}"
    content_key = f"oral_setup_content_{assessment_id}"
    rubric_key = f"oral_setup_rubric_{assessment_id}"
    points_key = f"oral_setup_points_{assessment_id}"

    if questions_key not in st.session_state:
        existing_setup = get_oral_exam_setup(assessment_id)
        if existing_setup and existing_setup.get("questions"):
            try:
                st.session_state[questions_key] = json.loads(existing_setup["questions"])
            except (TypeError, json.JSONDecodeError):
                st.session_state[questions_key] = []
            st.session_state[rubric_key] = existing_setup.get("rubric") or ""
            st.session_state[points_key] = existing_setup.get("max_points_per_question") or 10
        else:
            st.session_state[questions_key] = []
            st.session_state[rubric_key] = ""
            st.session_state[points_key] = 10
    st.session_state.setdefault(content_key, "")

    st.session_state[content_key] = st.text_area(
        "Topic or source material for question generation",
        value=st.session_state[content_key],
        height=180,
        key=f"{content_key}_widget",
    )

    gen_col1, gen_col2, gen_col3 = st.columns(3)
    with gen_col1:
        num_questions = st.slider("Number of questions", 1, 15, 5, key=f"oral_num_q_{assessment_id}")
    with gen_col2:
        difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], key=f"oral_difficulty_{assessment_id}")
    with gen_col3:
        model_keys = list(MODELS.keys())
        selected_model_key = st.selectbox("Model", model_keys, key=f"oral_setup_model_{assessment_id}")
        selected_model = MODELS[selected_model_key]

    if st.button("🪄 Generate Questions with AI", key=f"oral_generate_btn_{assessment_id}"):
        if not st.session_state[content_key].strip():
            st.error("Enter a topic or source material before generating questions.")
        else:
            with st.spinner("Generating questions..."):
                prompt = create_oral_question_generation_prompt(
                    content=st.session_state[content_key],
                    num_questions=num_questions,
                    difficulty=difficulty,
                )
                # force_json is intentionally omitted here: per
                # generate_llm_response()'s own docstring, Ollama's JSON mode
                # overrides the prompt's own format instructions and produces
                # garbage/truncated JSON for generation tasks like this one —
                # it's only appropriate for the single-object grading response
                # in _render_oral_exam_grading(). quiz_generator.py's
                # equivalent question-generation call avoids it for the same
                # reason. Passing force_json=True here was the actual cause of
                # only 1 question coming back instead of the requested count
                # on Ollama models.
                #
                # Even without force_json, small local models (e.g.
                # deepseek-r1:1.5B) sometimes still stop early despite the
                # prompt asking for an exact count — a handful of retries
                # resolves this in practice without the user having to notice
                # and manually click Generate again.
                best_questions: List[Dict] = []
                parse_error = False
                for _attempt in range(3):
                    response = generate_llm_response(prompt, selected_model)
                    try:
                        parsed = json.loads(strip_llm_json(response))
                        attempt_questions = parsed.get("questions", [])
                        parse_error = False
                    except Exception:
                        attempt_questions = []
                        parse_error = True
                    if len(attempt_questions) > len(best_questions):
                        best_questions = attempt_questions
                    if len(best_questions) >= num_questions:
                        break

                st.session_state[questions_key] = best_questions
                if len(best_questions) >= num_questions:
                    st.success(f"Generated {len(best_questions)} question(s).")
                elif best_questions:
                    st.warning(
                        f"The model returned only {len(best_questions)} of the {num_questions} "
                        "requested question(s) after several attempts — small local models "
                        "sometimes fall short of an exact count. Review the list below, add more "
                        "manually with \"+ Add Question\", or click Generate again."
                    )
                elif parse_error:
                    st.error("Could not parse the AI's response as valid questions. Please try again.")
                else:
                    st.error("The model did not return any questions. Please try again.")

    if st.session_state[questions_key]:
        st.write("### Questions")
        for i, q in enumerate(st.session_state[questions_key]):
            col_q, col_del = st.columns([6, 1])
            with col_q:
                q["question_text"] = st.text_area(
                    f"Question {q.get('question_number', i + 1)}",
                    value=q.get("question_text", ""),
                    height=80,
                    key=f"oral_q_text_{assessment_id}_{i}",
                )
            with col_del:
                if st.button("🗑️", key=f"oral_q_del_{assessment_id}_{i}"):
                    st.session_state[questions_key].pop(i)
                    st.rerun()
        if st.button("+ Add Question", key=f"oral_q_add_{assessment_id}"):
            next_number = len(st.session_state[questions_key]) + 1
            st.session_state[questions_key].append({"question_number": next_number, "question_text": ""})
            st.rerun()

    st.session_state[rubric_key] = st.text_area(
        "Grading Rubric (never shown to students)",
        value=st.session_state[rubric_key],
        height=140,
        key=f"{rubric_key}_widget",
    )
    st.session_state[points_key] = st.number_input(
        "Maximum points per question",
        min_value=1,
        value=int(st.session_state[points_key]),
        key=f"{points_key}_widget",
    )

    # Students identify "their next question" by matching question_number
    # against the live setup (see _render_student_oral_exam), so editing and
    # re-saving the question list after someone has already started answering
    # silently repoints their already-recorded answers at different question
    # text. There's no versioning to prevent this — surface it instead so the
    # teacher can make an informed call before saving.
    students_in_progress = get_students_with_oral_responses(assessment_id)
    if students_in_progress:
        st.warning(
            f"⚠️ {len(students_in_progress)} student(s) have already answered one or more "
            "questions under the current setup. Saving changes here will not affect their "
            "already-recorded answers, but it will change which question text those answers "
            "are shown and graded against if question numbering shifts (e.g. deleting or "
            "reordering a question). Prefer adding new questions at the end over deleting or "
            "reordering existing ones once students have started."
        )

    if st.session_state[questions_key] and st.button(
        "💾 Save Oral Exam Setup (visible to students)", type="primary", key=f"oral_save_setup_{assessment_id}"
    ):
        # Renumber sequentially on save so gaps left by deleting a question in
        # the middle of the list don't propagate into what the student sees
        # or into the grading records.
        for i, q in enumerate(st.session_state[questions_key], start=1):
            q["question_number"] = i
        save_oral_exam_setup(
            assessment_id=assessment_id,
            questions=json.dumps(st.session_state[questions_key]),
            rubric=st.session_state[rubric_key],
            max_points_per_question=int(st.session_state[points_key]),
            set_by=set_by,
        )
        total_possible = len(st.session_state[questions_key]) * int(st.session_state[points_key])
        st.success(
            "Oral exam setup saved — students can now take the exam. "
            f"Total possible score: {total_possible} points."
        )


# =============================================================================
# TEACHER/ADMIN — Grading Results
# =============================================================================

def _render_oral_exam_grading(assessment_id: int) -> None:
    if not assessment_id:
        st.warning("Select a course and assessment first.")
        return

    st.write("Grade student oral exam responses")

    # Namespaced by assessment_id so switching between assessments within the
    # same browser session doesn't display one assessment's freshly-graded
    # results under a different assessment's Grading Results tab.
    results_key = f"oral_exam_graded_results_{assessment_id}"

    setup = get_oral_exam_setup(assessment_id)
    if not setup or not setup.get("questions"):
        st.warning("Please set up questions and a rubric in the Setup Exam tab first.")
        return

    questions = json.loads(setup["questions"])
    total_questions = len(questions)
    rubric = setup.get("rubric") or ""
    max_points_per_question = setup.get("max_points_per_question") or 10

    students = get_students_with_oral_responses(assessment_id)
    complete_students = [s for s in students if s["answered_count"] >= total_questions]

    if not complete_students:
        st.info("No students have completed all questions for this oral exam yet.")
        return

    st.caption(f"{len(complete_students)} student(s) have completed all {total_questions} question(s).")

    if "oral_exam_selected_model" not in st.session_state:
        st.session_state.oral_exam_selected_model = list(MODELS.keys())[0]
    model_keys = list(MODELS.keys())
    saved_model = st.session_state.get("oral_exam_selected_model", model_keys[0])
    if saved_model not in model_keys:
        saved_model = model_keys[0]
    selected_model_key = st.selectbox(
        "Select the model to use for grading:",
        model_keys,
        index=model_keys.index(saved_model),
        key="oral_exam_model_selectbox",
    )
    st.session_state.oral_exam_selected_model = selected_model_key
    selected_model = MODELS[selected_model_key]

    if selected_model == "llama-3.3-70b-groq" and not st.session_state.get("groq_api_key"):
        st.warning("⚠️ Groq API key is required. Please add your API key in your profile settings.")
    if selected_model == "gemini-2.5-flash" and not st.session_state.get("gemini_api_key"):
        st.warning("⚠️ Gemini API key is required. Please add your API key in your profile settings.")

    if st.button("Grade All Submissions", key="oral_grade_all_btn"):
        grading_session_id = str(uuid.uuid4())
        graded_by = int(st.session_state["user"]["id"])
        graded_results: List[Dict[str, Any]] = []

        progress_bar = st.progress(0)
        status_text = st.empty()
        total_steps = len(complete_students)

        # Fetched once for the whole assessment rather than once per student —
        # grading a class of 30 would otherwise issue 30 separate round-trips
        # for data this single query already returns.
        all_responses = get_oral_exam_responses_for_assessment(assessment_id)
        responses_by_student: Dict[int, List[Dict]] = {}
        for r in all_responses:
            responses_by_student.setdefault(r["student_id"], []).append(r)

        for step, student in enumerate(complete_students):
            student_name = f"{student['first_name']} {student['last_name']}".strip()
            status_text.text(f"Grading {student_name}...")

            responses = responses_by_student.get(student["student_id"], [])
            for response in responses:
                raw_transcript = response.get("transcript") or ""
                # Guard against rows saved before the transcription-error check
                # in _render_student_oral_exam existed — an "Error: ..." string
                # must never be graded as if it were the student's answer.
                if not raw_transcript or raw_transcript.startswith("Error:"):
                    student_answer = "(no transcript — audio could not be transcribed)"
                else:
                    student_answer = raw_transcript
                prompt = create_grading_prompt(
                    question=response["question_text"],
                    rubric=rubric,
                    sub_rubric="",
                    student_answer=student_answer,
                    max_points=max_points_per_question,
                )

                try:
                    llm_response = generate_llm_response(prompt, selected_model, force_json=True)
                    result_json = json.loads(strip_llm_json(llm_response))
                    raw_score = result_json.get("score")
                    try:
                        coerced = int(float(str(raw_score)))
                        result_json["score"] = max(0, min(coerced, max_points_per_question))
                    except (TypeError, ValueError):
                        result_json["score"] = 0
                except Exception as e:
                    result_json = {
                        "score": 0,
                        "feedback": f"Error grading response: {e}",
                        "detailed_explanation": "",
                    }

                feedback = result_json.get("feedback") or "No feedback provided"
                detailed_explanation = result_json.get("detailed_explanation") or ""

                save_oral_exam_grading_result(
                    grading_session_id=grading_session_id,
                    graded_by=graded_by,
                    assessment_id=assessment_id,
                    student_id=student["student_id"],
                    student_name=student_name,
                    question_number=response["question_number"],
                    question_text=response["question_text"],
                    transcript=response.get("transcript") or "",
                    score=result_json["score"],
                    max_points=max_points_per_question,
                    feedback=feedback,
                    detailed_explanation=detailed_explanation,
                    model_name=selected_model,
                )

                graded_results.append({
                    "student_id": student["student_id"],
                    "student_name": student_name,
                    "question_number": response["question_number"],
                    "question_text": response["question_text"],
                    "transcript": response.get("transcript") or "",
                    "score": result_json["score"],
                    "max_points": max_points_per_question,
                    "feedback": feedback,
                    "detailed_explanation": detailed_explanation,
                })

            progress_bar.progress((step + 1) / total_steps)

        status_text.text("Grading completed!")
        st.session_state[results_key] = graded_results
        st.success("All oral exam responses graded successfully!")

    if st.session_state.get(results_key):
        st.write("### Grading Results")

        by_student: Dict[int, List[Dict]] = {}
        for r in st.session_state[results_key]:
            by_student.setdefault(r["student_id"], []).append(r)

        summary_rows = []
        for rows in by_student.values():
            total_score = sum(r["score"] for r in rows)
            total_max = sum(r["max_points"] for r in rows)
            pct = (total_score / total_max * 100) if total_max else 0.0
            summary_rows.append({
                "Student": rows[0]["student_name"],
                "Score": f"{total_score}/{total_max}",
                "Percentage": f"{pct:.1f}%",
            })
        st.table(pd.DataFrame(summary_rows))

        for student_id, rows in by_student.items():
            student_name = rows[0]["student_name"]
            total_score = sum(r["score"] for r in rows)
            total_max = sum(r["max_points"] for r in rows)

            with st.expander(f"{student_name} — {total_score}/{total_max}"):
                for r in sorted(rows, key=lambda x: x["question_number"]):
                    st.markdown(f"**Q{r['question_number']}. {r['question_text']}**")
                    st.caption(f"Transcript: {r['transcript'] or '(none)'}")
                    st.write(f"Score: {r['score']}/{r['max_points']} — {r['feedback']}")
                    with st.expander("Detailed explanation", expanded=False):
                        st.write(r["detailed_explanation"])

                st.markdown("---")
                st.markdown("**Proctoring summary**")

                # Reused unchanged from exam_grading_feature.py's Student
                # Submissions tab — same functions, same display, so eye
                # movement / mouse / keyboard logs look identical whether the
                # exam was written or spoken.
                proctor = get_proctor_summary_by_user_assessment(student_id, assessment_id)
                share_label = {
                    "granted": "✅ granted", "denied": "❌ denied", None: "— not recorded",
                }[proctor["screen_share"]]
                violation_count = proctor["violation_count"]
                violation_icon = "🔴" if violation_count else "🟢"
                st.caption(
                    f"{violation_icon} {violation_count} tab-switch/focus warning(s) — "
                    f"Screen share: {share_label}"
                )

                webcam_proctor = get_proctor_webcam_summary_by_user_assessment(student_id, assessment_id)
                webcam_label = {
                    "granted": "✅ granted", "denied": "❌ denied", None: "— not recorded",
                }[webcam_proctor["webcam"]]
                suspicious_count = (
                    webcam_proctor["no_face_count"]
                    + webcam_proctor["multiple_faces_count"]
                    + webcam_proctor["looking_away_count"]
                )
                suspicious_icon = "🔴" if suspicious_count else "🟢"
                st.caption(
                    f"{suspicious_icon} Camera: {webcam_label} — "
                    f"{webcam_proctor['no_face_count']} no-face, "
                    f"{webcam_proctor['multiple_faces_count']} multiple-faces, "
                    f"{webcam_proctor['looking_away_count']} looking-away (eye movement) frame(s)"
                )

                keystrokes = get_proctor_keystrokes_by_user_assessment(student_id, assessment_id)
                if keystrokes:
                    with st.expander(f"⌨️ Keystrokes Logged ({len(keystrokes)})", expanded=False):
                        st.text(format_keystrokes_for_display(keystrokes))

                mouse_events = get_proctor_mouse_events_by_user_assessment(student_id, assessment_id)
                if mouse_events:
                    with st.expander(f"🖱️ Mouse Activity Logged ({len(mouse_events)})", expanded=False):
                        st.text(format_mouse_events_for_display(mouse_events))


# =============================================================================
# TEACHER/ADMIN — History
# =============================================================================

def _render_oral_exam_history(assessment_id: int) -> None:
    if not assessment_id:
        st.warning("Select a course and assessment first.")
        return

    st.subheader("Grading History")

    user_id = int(st.session_state["user"]["id"])
    sessions = get_oral_exam_grading_sessions(user_id, assessment_id)

    if not sessions:
        st.info("No grading history found for this assessment.")
        return

    for session in sessions:
        grading_session_id = session["grading_session_id"]
        graded_at = session["graded_at"]
        result_count = session["result_count"]

        with st.expander(f"{graded_at} — {result_count} response(s) graded", expanded=False):
            session_results = get_oral_exam_grading_session_results(grading_session_id, user_id)

            by_student: Dict[int, List[Dict]] = {}
            for r in session_results:
                by_student.setdefault(r["student_id"], []).append(r)

            for rows in by_student.values():
                student_name = rows[0]["student_name"]
                total_score = sum(r["score"] for r in rows)
                total_max = sum(r["max_points"] for r in rows)
                with st.expander(f"{student_name} — {total_score}/{total_max}", expanded=False):
                    for r in sorted(rows, key=lambda x: x["question_number"]):
                        st.markdown(f"**Q{r['question_number']}. {r['question_text']}**")
                        st.caption(f"Transcript: {r.get('transcript') or '(none)'}")
                        st.write(f"Score: {r['score']}/{r['max_points']} — {r.get('feedback', '')}")


# =============================================================================
# TOP-LEVEL ENTRY POINT
# =============================================================================

def oral_examination_ui() -> None:
    """
    Render the full Oral Examination feature UI.

    The feature is always opened from within a specific course assessment. The
    current course and assessment are read from tab-namespaced session state
    keys so that responses and grading results are linked to the correct
    assessment in the database.

    Students get a single cut-down view instead of the tabs below: the
    question-by-question spoken response flow (see
    _render_student_oral_exam()). Everything from here down is the
    teacher/admin workflow.
    """
    st.subheader("Oral Examination")

    course = st.session_state.get("oral_examination_selected_course", {}) or {}
    assessment = st.session_state.get("oral_examination_selected_assessment", {}) or {}
    course_id = course.get("id")
    course_name = course.get("name", "")
    assessment_id = assessment.get("id")
    assessment_title = assessment.get("title", "")

    if st.session_state.get("user", {}).get("role") == "student":
        _render_student_oral_exam(course_id, course_name, assessment_id, assessment_title)
        return

    tab1, tab2, tab3 = st.tabs(["📝 Setup Exam", "📊 Grading Results", "🕘 History"])

    with tab1:
        _render_oral_exam_setup(assessment_id, int(st.session_state["user"]["id"]))
    with tab2:
        _render_oral_exam_grading(assessment_id)
    with tab3:
        _render_oral_exam_history(assessment_id)
