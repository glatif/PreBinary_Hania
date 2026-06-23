# =============================================================================
# quiz_generator_feature.py — Practice Quiz Feature
# =============================================================================
# Provides the full Practice Quiz UI and all supporting database operations.
#
# Feature overview:
#   Students upload study materials, configure a quiz (question counts, difficulty,
#   topic focus, model), take the generated quiz interactively, and receive
#   immediate scored feedback. All attempts are persisted to the database so
#   students can review their history and teachers can monitor engagement.
#
# Database integration:
#   - Source files uploaded by the user are saved to disk under the
#     practice_quiz subdirectory for the current assessment and recorded in
#     the files table with feature_name='practice_quiz'. Saved files can be
#     reused across generation runs. The Manage Saved Files section (visible
#     to instructors only) allows deletion of individual files.
#   - After a successful quiz generation, the full question set is saved to
#     practice_quiz_generated and the resulting row id is stored in session
#     state (quiz_current_db_id) so the subsequent attempt can reference it.
#   - When a student submits their answers, the attempt (answers + score) is
#     saved to practice_quiz_attempts, linked to both the quiz row and the
#     current assessment.
#   - The History tab shows a student only their own attempts for the current
#     assessment. Teachers and admins see an additional Instructor View tab
#     showing all student attempts for the assessment.
#
# Course/assessment context:
#   This feature is always rendered inside a specific assessment. The selected
#   course and assessment are read from session state using the tab-namespaced
#   keys set by app.py's navigation system:
#     st.session_state["practice_quiz_selected_course"]     -> {"id": int, "name": str}
#     st.session_state["practice_quiz_selected_assessment"] -> {"id": int, "title": str}
# =============================================================================

import streamlit as st
import json
import io
from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy import text

from db import get_connection, get_engine
from auth import save_uploaded_file, delete_physical_file

from src.utils.llm_utils import stream_llm, MODELS, MODEL_PROVIDERS
from src.features.quiz_generator.document_processor import (
    process_uploaded_files,
    combine_extracted_texts,
    validate_extracted_content,
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_pptx,
    extract_text_from_txt,
)
from src.features.quiz_generator.quiz_generator import (
    generate_quiz_questions,
    generate_multiple_question_types,
    validate_quiz_data,
    create_word_document_questions_only,
    create_word_document_with_answers,
)
from src.features.exam_verification.exam_verification_feature import verify_student_identity
from src.features.proctoring.proctoring_feature import (
    render_proctor_monitor,
    get_proctor_summary,
    get_proctor_frames,
)


# =============================================================================
# DATABASE WRITE OPERATIONS
# =============================================================================

def save_generated_quiz(
    user_id: int,
    assessment_id: int,
    quiz_data: dict,
    source_filenames: list = None,
) -> int:
    """
    Persist a generated quiz to the practice_quiz_generated table.

    Stores the full question set as a JSON blob alongside the metadata
    fields (counts, difficulty, topic focus, model used) so the quiz can
    be reconstructed and displayed in the history tab without re-querying
    the LLM.

    source_filenames is a list of the original uploaded filenames used to
    generate the quiz (e.g. ["lecture1.pdf", "notes.docx"]). Stored as a
    JSON array so the history tab can display which materials were used.

    Returns the new row's primary key, which is stored in session state
    as quiz_current_db_id and used when saving the student's attempt.
    """
    metadata = quiz_data.get("metadata", {})
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO practice_quiz_generated
                (user_id, assessment_id, source_filenames, questions_json,
                 mc_count, tf_count, sa_count, difficulty, topic_focus, model_used)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            assessment_id,
            json.dumps(source_filenames) if source_filenames else None,
            json.dumps(quiz_data.get("questions", [])),
            metadata.get("multiple_choice_count", 0),
            metadata.get("true_false_count", 0),
            metadata.get("short_answer_count", 0),
            metadata.get("difficulty"),
            metadata.get("topic_filters"),
            metadata.get("model_used"),
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def save_quiz_attempt(
    user_id: int,
    quiz_id: int,
    assessment_id: int,
    answers: dict,
    score: float,
    proctor_session_id: str = None,
) -> None:
    """
    Persist a student's completed quiz attempt to practice_quiz_attempts.

    answers is the quiz_user_answers dict keyed by question index (int).
    score is the percentage correct for auto-graded questions (MC and T/F),
    or None when the quiz contained only short-answer questions.

    assessment_id is stored directly on the attempt row so that instructor
    queries can filter by assessment without joining to practice_quiz_generated.

    proctor_session_id links this attempt to the tab-switch/screen-share
    monitoring events recorded by proctoring_feature.py while the student was
    taking the quiz (None for non-student preview attempts, which are never
    gated through the proctoring monitor).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO practice_quiz_attempts
                (user_id, quiz_id, assessment_id, answers_json, score, proctor_session_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            quiz_id,
            assessment_id,
            json.dumps({str(k): v for k, v in answers.items()}),
            score,
            proctor_session_id,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_quiz_attempt(attempt_id: int) -> None:
    """
    Permanently delete a single quiz attempt row from practice_quiz_attempts.

    Used by both the student history tab (student deletes their own attempt)
    and the instructor tab (instructor deletes any student's attempt). No
    user_id filter is applied here — access control is enforced at the UI
    layer by only showing delete controls to the attempt owner or an
    instructor.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM practice_quiz_attempts WHERE id = %s",
            (attempt_id,)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# FILE DB OPERATIONS
# =============================================================================

def get_practice_quiz_files(assessment_id: int) -> List[Dict]:
    """
    Return all files saved under the practice_quiz feature for the given assessment.

    Filters by both assessment_id and feature_name so only files uploaded
    through the Practice Quiz feature are returned, not general course files
    or files from other features within the same assessment.

    Ordered newest first so recently uploaded files appear at the top of
    the saved files list.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, file_name, file_path, uploaded_at
            FROM files
            WHERE assessment_id = %s
              AND feature_name  = 'practice_quiz'
            ORDER BY uploaded_at DESC
        """, (assessment_id,))
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def save_practice_quiz_file(
    file_bytes: bytes,
    original_name: str,
    course_id: int,
    course_name: str,
    assessment_id: int,
    assessment_title: str,
    user_id: int,
) -> None:
    """
    Save an uploaded source file to the practice_quiz directory for the
    current assessment and insert a record into the files table.

    Uses the shared save_uploaded_file() helper from auth.py, which handles
    directory creation and UUID-prefixed naming to prevent collisions.
    The feature_name column is set to 'practice_quiz' so the file appears
    only in the Practice Quiz saved files list, not in files from other features.

    Errors are surfaced via st.warning rather than raising, so that a storage
    failure does not block the text extraction workflow from continuing.
    """
    try:
        saved_name, saved_path = save_uploaded_file(
            file_bytes=file_bytes,
            original_name=original_name,
            course_name=course_name,
            assessment_name=assessment_title,
            course_id=course_id,
            feature_name="practice_quiz",
        )
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO files
                    (file_name, file_path, course_id, assessment_id, uploaded_by, feature_name)
                VALUES (:name, :path, :cid, :aid, :uid, :feat)
            """), {
                "name": saved_name,
                "path": saved_path,
                "cid":  course_id,
                "aid":  assessment_id,
                "uid":  user_id,
                "feat": "practice_quiz",
            })
    except Exception as exc:
        st.warning(f"File '{original_name}' could not be saved: {exc}")


def extract_text_from_saved_file(file_path: str, file_name: str) -> str:
    """
    Extract text content from a file that has been saved to disk.

    Reads the file bytes from its stored path and routes to the correct
    extractor based on file extension. Uses io.BytesIO to wrap the raw
    bytes into a file-like object compatible with the document_processor
    extractor functions.

    Returns the extracted text, or an empty string on failure.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            st.warning(f"Saved file '{file_name}' could not be found on disk.")
            return ""

        file_bytes = path.read_bytes()
        ext = path.suffix.lower()
        file_obj = io.BytesIO(file_bytes)

        if ext == ".pdf":
            return extract_text_from_pdf(file_obj)
        elif ext == ".docx":
            return extract_text_from_docx(file_obj)
        elif ext == ".pptx":
            return extract_text_from_pptx(file_obj)
        elif ext == ".txt":
            return file_bytes.decode("utf-8", errors="replace")
        else:
            st.warning(f"Unsupported file type for '{file_name}'.")
            return ""
    except Exception as exc:
        st.warning(f"Could not read '{file_name}': {exc}")
        return ""


# =============================================================================
# DATABASE READ OPERATIONS
# =============================================================================

def get_student_quiz_history(user_id: int, assessment_id: int) -> List[Dict]:
    """
    Return all quiz attempts made by the given student within the given assessment.

    Joins to practice_quiz_generated to include the question counts and
    difficulty metadata needed to display a useful summary in the History tab.
    Ordered newest first.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                a.id,
                a.score,
                a.submitted_at,
                a.answers_json,
                a.proctor_session_id,
                g.mc_count,
                g.tf_count,
                g.sa_count,
                g.difficulty,
                g.topic_focus,
                g.model_used,
                g.source_filenames,
                g.questions_json
            FROM practice_quiz_attempts a
            JOIN practice_quiz_generated g ON a.quiz_id = g.id
            WHERE a.user_id      = %s
              AND a.assessment_id = %s
            ORDER BY a.submitted_at DESC
        """, (user_id, assessment_id))
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def get_latest_generated_quiz(user_id: int, assessment_id: int) -> Dict | None:
    """
    Return the most recently generated practice quiz for this user and
    assessment, reshaped to match the quiz_data dict produced in-memory by
    generate_multiple_question_types() (a "questions" list plus a "metadata"
    dict), so it can be dropped straight into st.session_state.quiz_generated_questions.

    Returns None if this user has never generated a quiz for this assessment.
    Used by quiz_generator_ui() to restore an already-generated quiz when the
    session state is empty (e.g. a new browser session) instead of forcing
    the student to regenerate it from scratch every time.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, questions_json, mc_count, tf_count, sa_count,
                   difficulty, topic_focus, model_used
            FROM practice_quiz_generated
            WHERE user_id = %s AND assessment_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id, assessment_id))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "questions": json.loads(row["questions_json"]),
        "metadata": {
            "multiple_choice_count": row["mc_count"],
            "true_false_count":      row["tf_count"],
            "short_answer_count":    row["sa_count"],
            "difficulty":            row["difficulty"],
            "topic_filters":         row["topic_focus"],
            "model_used":            row["model_used"],
        },
    }


def get_all_attempts_for_assessment(assessment_id: int) -> List[Dict]:
    """
    Return all student attempts for a given assessment.

    Used by the Instructor View tab, which is only rendered for admin and
    teacher roles. Joins to users to include the student's display name and
    to practice_quiz_generated for the quiz metadata summary.
    Ordered newest first.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                a.id,
                a.score,
                a.submitted_at,
                a.answers_json,
                a.proctor_session_id,
                u.username,
                u.first_name,
                u.last_name,
                g.mc_count,
                g.tf_count,
                g.sa_count,
                g.difficulty,
                g.topic_focus,
                g.model_used,
                g.source_filenames,
                g.questions_json
            FROM practice_quiz_attempts a
            JOIN practice_quiz_generated g ON a.quiz_id = g.id
            JOIN users u ON a.user_id = u.id
            WHERE a.assessment_id = %s
            ORDER BY a.submitted_at DESC
        """, (assessment_id,))
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# SESSION STATE INITIALISATION
# =============================================================================

def initialize_quiz_session_state() -> None:
    """
    Initialise all session state keys used by the Practice Quiz feature.

    Called once at the top of quiz_generator_ui() on every render. Keys are
    only set if they do not already exist, so values set during a previous
    render are preserved across Streamlit reruns.

    quiz_current_db_id holds the primary key of the most recently generated
    quiz row in practice_quiz_generated. It is reset to None each time a new
    quiz is generated and is used when saving the student's attempt so the
    attempt is linked to the correct quiz row.
    """
    if "quiz_uploaded_files" not in st.session_state:
        st.session_state.quiz_uploaded_files = []
    if "quiz_extracted_texts" not in st.session_state:
        st.session_state.quiz_extracted_texts = []
    if "quiz_analysis_complete" not in st.session_state:
        st.session_state.quiz_analysis_complete = False
    if "quiz_generated_questions" not in st.session_state:
        st.session_state.quiz_generated_questions = None
    if "quiz_selected_model" not in st.session_state:
        st.session_state.quiz_selected_model = list(MODELS.keys())[0]
    if "quiz_user_answers" not in st.session_state:
        st.session_state.quiz_user_answers = {}
    if "quiz_submitted" not in st.session_state:
        st.session_state.quiz_submitted = False
    # Tracks the DB row id of the quiz that is currently loaded in the Quiz
    # Interface tab. Reset to None whenever a new quiz is generated.
    if "quiz_current_db_id" not in st.session_state:
        st.session_state.quiz_current_db_id = None
    # Guards the attempt save so it fires exactly once per submission,
    # not on every rerender while quiz_submitted remains True.
    if "quiz_attempt_saved" not in st.session_state:
        st.session_state.quiz_attempt_saved = False
    # Tracks which assessment's quiz is currently loaded into the keys above,
    # so quiz_generator_ui() can tell when it needs to (re)load from the DB —
    # either because the session is fresh or because the student switched to
    # a different assessment. See quiz_generator_ui().
    if "quiz_loaded_for_assessment" not in st.session_state:
        st.session_state.quiz_loaded_for_assessment = None


# =============================================================================
# DATA INPUT & ANALYSIS TAB
# =============================================================================

def render_data_input_tab(
    user_id: int,
    assessment_id: int,
    course_id: int,
    course_name: str,
    assessment_title: str,
    is_instructor: bool,
) -> None:
    """
    Render the Data Input & Analysis tab.

    Handles file input (upload new or select from saved), quiz configuration,
    model selection, and quiz generation. After a successful generation the
    quiz is saved to the database and quiz_current_db_id is updated so the
    Quiz Interface tab can link the subsequent attempt to the correct row.

    File input modes:
        Upload new files   — saves each file to the practice_quiz directory
                             for this assessment before extracting text, so
                             the file is available for future runs.
        Use saved files    — multiselect from files already saved under this
                             assessment; text is extracted from disk and
                             combined exactly as the upload mode does.

    The Manage Saved Files expander (instructor-only) lists all saved files
    for this assessment with a delete button per file.

    All parameters are passed explicitly from quiz_generator_ui() so that
    file persistence and DB interactions remain centralised and testable.
    """
    st.header("📚 Data Input & Analysis")
    st.write("Upload your study materials and analyze the content to prepare for quiz generation.")

    # ── File Input ─────────────────────────────────────────────────────────────
    st.subheader("📁 Study Materials")

    input_method = st.radio(
        "How would you like to provide your study materials?",
        ["Upload new files", "Use saved files"],
        key="pq_input_method",
    )

    # extracted_texts holds (filename, text) tuples for the current input,
    # matching the format expected by combine_extracted_texts() and
    # validate_extracted_content().
    extracted_texts = []

    if input_method == "Upload new files":
        # Upload one or more files, save each to the course directory under
        # the practice_quiz subdirectory, then extract and combine text.
        uploaded_files = st.file_uploader(
            "Upload PDFs, Word documents, PowerPoint presentations, or text files:",
            type=["pdf", "docx", "pptx", "txt"],
            accept_multiple_files=True,
            key="quiz_file_uploader",
            help="You can upload multiple files. All content will be analyzed together.",
        )
        if uploaded_files:
            # Guard file persistence with a session state flag keyed on the
            # sorted set of uploaded filenames. Streamlit rerenders this block
            # on every interaction while files are present in the uploader;
            # without this guard each rerender would create duplicate records
            # in the files table and duplicate files on disk.
            current_filenames = tuple(sorted(uf.name for uf in uploaded_files))
            if (
                course_id and assessment_id
                and st.session_state.get("pq_saved_filenames") != current_filenames
            ):
                for uf in uploaded_files:
                    save_practice_quiz_file(
                        file_bytes=uf.getvalue(),
                        original_name=uf.name,
                        course_id=course_id,
                        course_name=course_name,
                        assessment_id=assessment_id,
                        assessment_title=assessment_title,
                        user_id=user_id,
                    )
                st.session_state["pq_saved_filenames"] = current_filenames
            extracted_texts = process_uploaded_files(uploaded_files)

    else:
        # Present all files saved under practice_quiz for this assessment.
        # The user selects one or more; text is extracted from disk and
        # combined in the same way as freshly uploaded files.
        saved_files = get_practice_quiz_files(assessment_id) if assessment_id else []
        if not saved_files:
            st.info("No saved files for this assessment yet. Upload new files to get started.")
        else:
            file_options = {f["file_name"]: f for f in saved_files}
            selected_names = st.multiselect(
                "Select one or more saved files to use:",
                list(file_options.keys()),
                key="pq_saved_select",
                help="All selected files will be combined as study material.",
            )
            if selected_names and st.button("Use selected files", key="pq_use_saved"):
                for name in selected_names:
                    f = file_options[name]
                    text = extract_text_from_saved_file(f["file_path"], f["file_name"])
                    if text:
                        extracted_texts.append((f["file_name"], text))
                if extracted_texts:
                    st.session_state["pq_saved_extracted_texts"] = extracted_texts
                    st.success(
                        f"Text extracted from {len(extracted_texts)} file(s). "
                        "Configure your quiz below and click Generate."
                    )

        # Persist extracted texts in session state so the user can configure
        # and generate without clicking Use selected files again on rerenders.
        if not extracted_texts:
            extracted_texts = st.session_state.get("pq_saved_extracted_texts", [])

    # ── Manage Saved Files (instructors only) ───────────────────────────────
    # Shown below the input section so teachers can delete outdated files
    # without it interfering with the student-facing generation workflow.
    if is_instructor and assessment_id:
        with st.expander("📁 Manage Saved Files", expanded=False):
            saved_files_list = get_practice_quiz_files(assessment_id)
            if not saved_files_list:
                st.info("No files saved for this assessment yet.")
            else:
                for f in saved_files_list:
                    col_name, col_date, col_del = st.columns([4, 2, 1])
                    with col_name:
                        st.markdown(f"`{f['file_name']}`")
                    with col_date:
                        st.caption(str(f["uploaded_at"]))
                    with col_del:
                        if st.button(
                            "Delete",
                            key=f"pq_del_file_{f['id']}",
                            type="primary",
                            width="stretch",
                        ):
                            _dialog_delete_pq_file(f["id"], f["file_name"], f["file_path"])

    # ── Quiz Configuration ──────────────────────────────────────────────────
    st.subheader("🎯 Quiz Configuration")
    st.write("Set the number of questions for each type (0-15 per type):")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**📝 Multiple Choice**")
        mc_count = st.number_input(
            "Number of MC Questions",
            min_value=0, max_value=15, value=5,
            key="quiz_mc_count",
            help="Multiple choice questions with 4 options",
        )
    with col2:
        st.markdown("**✅ True/False**")
        tf_count = st.number_input(
            "Number of T/F Questions",
            min_value=0, max_value=15, value=5,
            key="quiz_tf_count",
            help="True or False questions",
        )
    with col3:
        st.markdown("**✍️ Short Answer**")
        sa_count = st.number_input(
            "Number of SA Questions",
            min_value=0, max_value=15, value=5,
            key="quiz_sa_count",
            help="Questions requiring written responses",
        )

    total_questions = mc_count + tf_count + sa_count
    if total_questions == 0:
        st.error("⚠️ Please select at least one question type with a count greater than 0.")
    else:
        st.info(f"📊 Total Questions: {total_questions} (MC: {mc_count}, T/F: {tf_count}, SA: {sa_count})")

    col4, col5 = st.columns(2)
    with col4:
        difficulty = st.select_slider(
            "Difficulty Level",
            options=["Easy", "Medium", "Hard"],
            value="Medium",
            key="quiz_difficulty",
            help="Easy: Direct recall, Medium: Application, Hard: Analysis",
        )
    with col5:
        topic_filters = st.text_input(
            "Topic Focus (Optional)",
            placeholder="e.g., Biology, History, Math",
            key="quiz_topic_filters",
            help="Comma-separated topics to focus on (leave blank for all topics)",
        )

    # ── Model Selection ─────────────────────────────────────────────────────
    # Uses quiz_selected_model as the initial index so that the user's saved
    # model preference (set by _load_model_preferences() at login) is applied
    # on first render.
    st.subheader("🤖 AI Model Selection")
    model_keys = list(MODELS.keys())
    saved_model = st.session_state.get("quiz_selected_model", model_keys[0])
    if saved_model not in model_keys:
        saved_model = model_keys[0]
    selected_model_key = st.selectbox(
        "Select AI Model for Quiz Generation",
        options=model_keys,
        index=model_keys.index(saved_model),
        key="quiz_model_select",
        help="Choose which AI model to use for generating questions",
    )
    st.session_state.quiz_selected_model = selected_model_key

    selected_model_id = MODELS[selected_model_key]
    model_provider    = MODEL_PROVIDERS.get(selected_model_id, "")

    if model_provider == "groq" and not st.session_state.get("groq_api_key"):
        st.warning("⚠️ Groq API key is required for this model. Please add your API key in your profile settings.")
    if model_provider == "gemini" and not st.session_state.get("gemini_api_key"):
        st.warning("⚠️ Google Gemini API key is required for this model. Please add your API key in your profile settings.")
    if model_provider == "openai" and not st.session_state.get("openai_api_key"):
        st.warning("⚠️ OpenAI API key is required for this model. Please add your API key in your profile settings.")
    if model_provider == "github" and not st.session_state.get("github_token"):
        st.warning("⚠️ GitHub token is required for this model. Please add your GitHub token in your profile settings.")

    # ── Generate ─────────────────────────────────────────────────────────────
    st.markdown("---")
    # The generate button is disabled if there is no extracted content or no
    # question types selected. For "Use saved files" mode, extracted_texts is
    # populated from session state so the button stays enabled across rerenders.
    content_ready = bool(extracted_texts) or bool(
        input_method == "Use saved files"
        and st.session_state.get("pq_saved_extracted_texts")
    )
    analyze_button = st.button(
        "🔍 Analyze Content & Generate Quiz",
        type="primary",
        disabled=not content_ready or total_questions == 0,
        help="Process uploaded files and generate quiz questions",
    )

    if analyze_button and content_ready and total_questions > 0:
        # Resolve the final extracted_texts — either freshly uploaded or
        # retrieved from session state for the saved-file flow.
        if not extracted_texts:
            extracted_texts = st.session_state.get("pq_saved_extracted_texts", [])

        with st.spinner("📖 Analyzing documents and generating quiz questions..."):
            if not validate_extracted_content(extracted_texts):
                st.error("❌ Insufficient content extracted from files. Please check your files and try again.")
                return

            st.session_state.quiz_extracted_texts = extracted_texts
            combined_content = combine_extracted_texts(extracted_texts)

            quiz_data = generate_multiple_question_types(
                content=combined_content,
                mc_count=mc_count,
                tf_count=tf_count,
                sa_count=sa_count,
                difficulty=difficulty,
                topic_filters=topic_filters,
                model_id=selected_model_id,
            )

            if "error" in quiz_data:
                st.error(f"❌ Failed to generate quiz: {quiz_data['error']}")
                return

            if not validate_quiz_data(quiz_data):
                st.error("❌ Generated quiz data is invalid. Please try again.")
                return

            # Store quiz in session state and reset all attempt tracking so a
            # previously submitted attempt is not carried over to the new quiz.
            st.session_state.quiz_generated_questions = quiz_data
            st.session_state.quiz_analysis_complete   = True
            st.session_state.quiz_user_answers        = {}
            st.session_state.quiz_submitted           = False
            st.session_state.quiz_attempt_saved       = False

            # Save the generated quiz to the database and record its id so the
            # subsequent attempt can reference the correct quiz row. The id is
            # reset to None here and set after the DB write to ensure it always
            # reflects the current quiz, never a previous one.
            st.session_state.quiz_current_db_id = None
            if assessment_id:
                try:
                    source_filenames = [
                        fname for fname, _ in st.session_state.quiz_extracted_texts
                    ]
                    quiz_db_id = save_generated_quiz(
                        user_id, assessment_id, quiz_data, source_filenames
                    )
                    st.session_state.quiz_current_db_id = quiz_db_id
                except Exception as exc:
                    st.warning(f"Quiz could not be saved to the database: {exc}")

            st.success(
                f"✅ Successfully generated {len(quiz_data['questions'])} questions! "
                "Go to the 'Quiz Interface' tab to start practicing."
            )

    # Show extracted content preview if a quiz has been generated this session.
    if st.session_state.quiz_analysis_complete and st.session_state.quiz_extracted_texts:
        st.markdown("---")
        with st.expander("📄 View Extracted Content", expanded=False):
            for filename, text in st.session_state.quiz_extracted_texts:
                st.subheader(f"📄 {filename}")
                st.text_area(
                    "Content",
                    text[:1000] + "..." if len(text) > 1000 else text,
                    height=150,
                    key=f"quiz_content_{filename}",
                    disabled=True,
                )


# =============================================================================
# QUIZ INTERFACE TAB
# =============================================================================

def render_quiz_interface_tab() -> None:
    """
    Render the Quiz Interface tab.

    Displays the generated quiz metadata, download options, and the interactive
    question-and-answer form. On submission, display_quiz_results() is called
    which also saves the attempt to the database.

    This function is unchanged from the original session-based implementation
    except that the submit button now triggers display_quiz_results(), which
    handles DB persistence internally via session state keys set during
    generation (quiz_current_db_id, practice_quiz_selected_assessment).
    """
    st.header("🎯 Quiz Interface")

    if not st.session_state.quiz_analysis_complete or not st.session_state.quiz_generated_questions:
        st.warning("⚠️ Please upload and analyze your documents in the 'Data Input & Analysis' tab first.")
        return

    quiz_data = st.session_state.quiz_generated_questions
    questions = quiz_data.get("questions", [])

    if not questions:
        st.error("❌ No questions available. Please regenerate the quiz.")
        return

    # ---- Identity verification gate (students only) ----
    # Instructors previewing their own generated quiz are not gated — only
    # students taking the quiz for an actual attempt must verify. Keyed by
    # quiz_current_db_id (the practice_quiz_generated row for this quiz) so
    # a fresh verification is required if the student generates a new quiz.
    user = st.session_state.get("user", {})
    if user.get("role") == "student":
        quiz_gate_id = st.session_state.get("quiz_current_db_id") or "session"
        gate_key = f"practice_quiz_{quiz_gate_id}"
        if not verify_student_identity(user, gate_key=gate_key):
            return

        # Proctoring starts the instant verification passes, before any quiz
        # content is shown. The returned session_id is stamped onto the
        # attempt row when it is saved in display_quiz_results() below.
        assessment_ctx = st.session_state.get("practice_quiz_selected_assessment") or {}
        st.session_state["quiz_proctor_session_id"] = render_proctor_monitor(
            gate_key=gate_key,
            user=user,
            quiz_id=st.session_state.get("quiz_current_db_id"),
            assessment_id=assessment_ctx.get("id"),
        )

    # Quiz metadata summary
    metadata = quiz_data.get("metadata", {})
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Questions", len(questions))
    with col2:
        mc_count = metadata.get("multiple_choice_count", 0)
        tf_count = metadata.get("true_false_count", 0)
        sa_count = metadata.get("short_answer_count", 0)
        st.metric("Question Types", f"MC:{mc_count} TF:{tf_count} SA:{sa_count}")
    with col3:
        st.metric("Difficulty", metadata.get("difficulty", "N/A"))
    with col4:
        st.metric("Model Used", metadata.get("model_used", "N/A"))

    # Download options for the question set
    st.markdown("---")
    st.subheader("📥 Download Options")
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("📄 Download Questions Only (Word)", key="download_questions_only"):
            try:
                doc_bytes = create_word_document_questions_only(quiz_data)
                st.download_button(
                    label="📥 Download Word File (Questions Only)",
                    data=doc_bytes.getvalue(),
                    file_name="quiz_questions_only.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            except Exception as e:
                st.error(f"Failed to generate Word document: {str(e)}")

    with col2:
        if st.button("📄 Download with Answers (Word)", key="download_with_answers"):
            try:
                doc_bytes = create_word_document_with_answers(quiz_data)
                st.download_button(
                    label="📥 Download Word File (With Answers)",
                    data=doc_bytes.getvalue(),
                    file_name="quiz_with_answers.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            except Exception as e:
                st.error(f"Failed to generate Word document: {str(e)}")

    with col3:
        if st.button("📋 Download JSON", key="download_json"):
            quiz_json = json.dumps(quiz_data, indent=2)
            st.download_button(
                label="📥 Download JSON File",
                data=quiz_json,
                file_name="quiz_data.json",
                mime="application/json",
            )

    st.markdown("---")

    # Interactive question form
    st.subheader("📝 Answer the Questions")

    for i, question in enumerate(questions):
        question_number = i + 1
        question_text   = question.get("question_text", "")
        question_type   = question.get("question_type", "")
        options         = question.get("options", [])
        topic           = question.get("topic", "General")

        with st.container():
            st.markdown(f"### Question {question_number}")
            st.markdown(f"**Topic:** {topic}")
            st.markdown(f"**Question:** {question_text}")

            answer_key = f"quiz_answer_{i}"

            if question_type in ["multiple_choice", "true_false"] and options:
                user_answer = st.radio(
                    "Choose your answer:",
                    options=options,
                    key=answer_key,
                    index=None,
                    help=f"Select the best answer for question {question_number}",
                )
                st.session_state.quiz_user_answers[i] = user_answer

            elif question_type == "short_answer":
                user_answer = st.text_area(
                    "Your answer:",
                    key=answer_key,
                    height=100,
                    placeholder="Enter your answer here...",
                    help=f"Provide a short answer for question {question_number}",
                )
                st.session_state.quiz_user_answers[i] = user_answer

            else:
                st.error(f"Unsupported question type: {question_type}")

            st.markdown("---")

    # Submit button — disabled once the quiz has been submitted.
    # On submit, quiz_submitted is set and the page reruns so the button
    # re-evaluates its disabled state cleanly. Results are then rendered
    # on every subsequent render via the if quiz_submitted block below,
    # keeping them visible across tab switches and other rerenders.
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        submit_button = st.button(
            "📊 Submit Quiz",
            type="primary",
            disabled=st.session_state.quiz_submitted,
            help="Submit your answers to see results",
        )

    if submit_button:
        st.session_state.quiz_submitted     = True
        st.session_state.quiz_attempt_saved = False
        st.rerun()

    if st.session_state.quiz_submitted:
        display_quiz_results(questions)


# =============================================================================
# QUIZ RESULTS AND ATTEMPT PERSISTENCE
# =============================================================================

def display_quiz_results(questions: List[Dict[str, Any]]) -> None:
    """
    Display per-question feedback and the overall score after submission.

    In addition to rendering results, this function saves the attempt to
    practice_quiz_attempts. The quiz row id (quiz_current_db_id) and assessment
    id (from practice_quiz_selected_assessment) are read from session state,
    which were set during generation in render_data_input_tab().

    Score is calculated only from auto-graded question types (MC and T/F).
    Short-answer questions are displayed for self-review but do not contribute
    to the numeric score. If the quiz contains only short-answer questions,
    score is stored as None.
    """
    st.markdown("---")
    st.subheader("📊 Quiz Results")

    correct_count   = 0
    total_questions = len(questions)

    for i, question in enumerate(questions):
        user_answer    = st.session_state.quiz_user_answers.get(i, "")
        correct_answer = question.get("correct_answer", "")
        explanation    = question.get("explanation", "No explanation provided.")
        question_text  = question.get("question_text", "")
        question_type  = question.get("question_type", "")

        is_correct = False
        if question_type in ["multiple_choice", "true_false"]:
            is_correct = user_answer == correct_answer
        elif question_type == "short_answer":
            # Short-answer correctness cannot be determined automatically.
            # Treat as correct for display purposes if the student provided
            # any response; the actual quality is for the student to judge.
            is_correct = bool(user_answer and user_answer.strip())

        if is_correct and question_type != "short_answer":
            correct_count += 1

        if question_type == "short_answer":
            label = "❓ Review"
        elif is_correct:
            label = "✅ Correct"
        else:
            label = "❌ Incorrect"

        with st.expander(f"Question {i + 1}: {label}", expanded=False):
            st.markdown(f"**Question:** {question_text}")
            st.markdown(f"**Your Answer:** {user_answer if user_answer else '*No answer provided*'}")
            st.markdown(f"**Correct Answer:** {correct_answer}")
            st.markdown(f"**Explanation:** {explanation}")

    # Calculate and display the numeric score for auto-graded questions.
    scorable_questions = [q for q in questions if q.get("question_type") in ["multiple_choice", "true_false"]]
    score_percentage   = None

    if scorable_questions:
        score_percentage = (correct_count / len(scorable_questions)) * 100
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Score", f"{correct_count}/{len(scorable_questions)}")
        with col2:
            st.metric("Percentage", f"{score_percentage:.1f}%")
        with col3:
            grade = (
                "A" if score_percentage >= 90 else
                "B" if score_percentage >= 80 else
                "C" if score_percentage >= 70 else
                "D" if score_percentage >= 60 else
                "F"
            )
            st.metric("Grade", grade)

    # Persist the attempt exactly once per submission. quiz_attempt_saved
    # prevents duplicate rows if the page rerenders while quiz_submitted
    # is True (e.g. the student switches tabs before clicking Take Quiz Again).
    quiz_db_id    = st.session_state.get("quiz_current_db_id")
    assessment_id = (
        st.session_state.get("practice_quiz_selected_assessment") or {}
    ).get("id")
    user_id = st.session_state["user"]["id"]

    if quiz_db_id and assessment_id and not st.session_state.get("quiz_attempt_saved"):
        try:
            save_quiz_attempt(
                user_id=user_id,
                quiz_id=quiz_db_id,
                assessment_id=assessment_id,
                answers=st.session_state.quiz_user_answers,
                score=score_percentage,
                proctor_session_id=st.session_state.get("quiz_proctor_session_id"),
            )
            st.session_state.quiz_attempt_saved = True
        except Exception as exc:
            st.warning(f"Attempt could not be saved to the database: {exc}")

    # Reset button — clears answers and submission flag so the student can
    # retake the same quiz. Generates a new attempt row when re-submitted.
    if st.button("🔄 Take Quiz Again", key="quiz_reset"):
        st.session_state.quiz_user_answers  = {}
        st.session_state.quiz_submitted     = False
        st.session_state.quiz_attempt_saved = False
        st.rerun()


# =============================================================================
# HISTORY TAB — STUDENT VIEW
# =============================================================================

def render_student_history_tab(user_id: int, assessment_id: int) -> None:
    """
    Render the student's personal quiz history for the current assessment.

    Shows each attempt as a collapsible expander containing the score,
    difficulty, question counts, a per-question answer review, download
    options for the question set, and a delete button. Only the current
    student's own attempts are shown.
    """
    st.header("🕘 My Quiz History")

    attempts = get_student_quiz_history(user_id, assessment_id)

    if not attempts:
        st.info("You have not completed any quizzes for this assessment yet.")
        return

    for attempt in attempts:
        attempt_id    = attempt["id"]
        score_display = (
            f"{attempt['score']:.1f}%"
            if attempt["score"] is not None
            else "No score (short answer only)"
        )
        label = f"{attempt['submitted_at']} — Score: {score_display}"

        with st.expander(label, expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Difficulty:** {attempt.get('difficulty', 'N/A')}")
            with col2:
                st.write(
                    f"**Questions:** MC: {attempt.get('mc_count', 0)}, "
                    f"T/F: {attempt.get('tf_count', 0)}, "
                    f"SA: {attempt.get('sa_count', 0)}"
                )
            with col3:
                st.write(f"**Score:** {score_display}")

            # Display the source files used to generate this quiz so the
            # student can identify which study materials it was based on.
            try:
                raw_filenames = attempt.get("source_filenames")
                if raw_filenames:
                    filenames = json.loads(raw_filenames)
                    if filenames:
                        st.write(
                            "**Source Files:** " + ", ".join(filenames)
                        )
            except Exception:
                pass

            # Reconstruct the per-question review from stored answers and
            # the original question set saved with the quiz.
            questions = []
            try:
                questions    = json.loads(attempt.get("questions_json", "[]"))
                answers_raw  = json.loads(attempt.get("answers_json", "{}"))
                # answers_json keys are stored as strings; convert to int for lookup.
                answers      = {int(k): v for k, v in answers_raw.items()}

                if questions:
                    st.markdown("**Question Review:**")
                    for i, q in enumerate(questions):
                        user_answer    = answers.get(i, "")
                        correct_answer = q.get("correct_answer", "")
                        question_type  = q.get("question_type", "")

                        if question_type == "short_answer":
                            result = "❓ Review"
                        elif user_answer == correct_answer:
                            result = "✅ Correct"
                        else:
                            result = "❌ Incorrect"

                        with st.expander(f"Q{i + 1}: {result}", expanded=False):
                            st.markdown(f"**Question:** {q.get('question_text', '')}")
                            st.markdown(f"**Your Answer:** {user_answer if user_answer else '*No answer provided*'}")
                            st.markdown(f"**Correct Answer:** {correct_answer}")
                            st.markdown(f"**Explanation:** {q.get('explanation', 'N/A')}")
            except Exception:
                st.caption("Question review unavailable for this attempt.")

            st.markdown("---")

            # Download options — reconstruct the quiz_data dict from stored
            # fields so the Word document generators receive the expected format.
            if questions:
                # Reconstruct quiz_data to match the format produced by
                # generate_multiple_question_types() so the Word document
                # generators produce output identical to the Quiz Interface tab.
                mc = attempt.get("mc_count", 0)
                tf = attempt.get("tf_count", 0)
                sa = attempt.get("sa_count", 0)
                quiz_data_for_export = {
                    "questions": questions,
                    "metadata": {
                        "difficulty":            attempt.get("difficulty"),
                        "total_questions":       len(questions),
                        "multiple_choice_count": mc,
                        "true_false_count":      tf,
                        "short_answer_count":    sa,
                        "topic_filters":         attempt.get("topic_focus"),
                        "model_used":            attempt.get("model_used"),
                        # generation_summary is used by the with-answers Word
                        # document to render the question distribution line.
                        "generation_summary": {
                            "multiple_choice": {"generated": mc},
                            "true_false":      {"generated": tf},
                            "short_answer":    {"generated": sa},
                        },
                    },
                }
                # All actions on one row: three download buttons on the left,
                # delete button on the far right.
                dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)

                with dl_col1:
                    try:
                        doc_bytes = create_word_document_questions_only(quiz_data_for_export)
                        st.download_button(
                            label="📄 Questions Only (Word)",
                            data=doc_bytes.getvalue(),
                            file_name=f"quiz_{attempt_id}_questions.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"hist_dl_qonly_{attempt_id}",
                        )
                    except Exception as e:
                        st.error(f"Failed to generate document: {str(e)}")

                with dl_col2:
                    try:
                        doc_bytes = create_word_document_with_answers(quiz_data_for_export)
                        st.download_button(
                            label="📄 With Answers (Word)",
                            data=doc_bytes.getvalue(),
                            file_name=f"quiz_{attempt_id}_answers.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"hist_dl_qans_{attempt_id}",
                        )
                    except Exception as e:
                        st.error(f"Failed to generate document: {str(e)}")

                with dl_col3:
                    st.download_button(
                        label="📋 Download JSON",
                        data=json.dumps(quiz_data_for_export, indent=2),
                        file_name=f"quiz_{attempt_id}.json",
                        mime="application/json",
                        key=f"hist_dl_json_{attempt_id}",
                    )

                with dl_col4:
                    if st.button(
                        "🗑️ Delete",
                        key=f"hist_del_{attempt_id}",
                        type="primary",
                    ):
                        _dialog_delete_quiz_attempt(attempt_id)
# =============================================================================
# HISTORY TAB — INSTRUCTOR VIEW
# =============================================================================

def render_instructor_attempts_tab(assessment_id: int) -> None:
    """
    Render the instructor's view of all student quiz attempts for the assessment.

    Mirrors the student history tab format — each attempt is a collapsible
    expander with the student's name, score, difficulty, and submission time
    in the title, and a full per-question answer review, download options, and
    a delete button inside. Only rendered for admin and teacher roles.
    """
    st.header("👩\u200d🏫 Student Attempts")

    attempts = get_all_attempts_for_assessment(assessment_id)

    if not attempts:
        st.info("No student attempts yet for this assessment.")
        return

    for attempt in attempts:
        attempt_id = attempt["id"]
        first      = attempt.get("first_name", "") or ""
        last       = attempt.get("last_name", "") or ""
        name       = f"{first} {last}".strip() or attempt.get("username", "")
        score_display = (
            f"{attempt['score']:.1f}%"
            if attempt["score"] is not None
            else "No score (short answer only)"
        )
        label = (
            f"{name} — Score: {score_display} — "
            f"{attempt.get('difficulty', 'N/A')} — {attempt['submitted_at']}"
        )

        with st.expander(label, expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Student:** {name}")
            with col2:
                st.write(f"**Difficulty:** {attempt.get('difficulty', 'N/A')}")
            with col3:
                st.write(f"**Score:** {score_display}")

            st.write(
                f"**Questions:** MC: {attempt.get('mc_count', 0)}, "
                f"T/F: {attempt.get('tf_count', 0)}, "
                f"SA: {attempt.get('sa_count', 0)}"
            )

            # Proctoring summary — tab-switch/focus-loss count and the
            # screen-share permission outcome recorded while this student was
            # taking the quiz. proctor_session_id is None for attempts taken
            # before this feature existed.
            proctor = get_proctor_summary(attempt.get("proctor_session_id"))
            share_label = {
                "granted": "✅ granted",
                "denied":  "❌ denied",
                None:      "— not recorded",
            }[proctor["screen_share"]]
            violation_count = proctor["violation_count"]
            violation_icon  = "🔴" if violation_count else "🟢"
            st.write(
                f"**Monitoring:** {violation_icon} {violation_count} tab-switch/focus "
                f"warning(s) — Screen share: {share_label}"
            )

            # Screen-share snapshots captured while the student had the quiz
            # open, downscaled JPEGs taken every CAPTURE_INTERVAL_MS — see
            # proctoring_feature.py. Not shown at all if sharing was never
            # granted or no frames were captured.
            frames = get_proctor_frames(attempt.get("proctor_session_id"))
            if frames:
                with st.expander(f"📷 Screen Capture Frames ({len(frames)})", expanded=False):
                    frame_cols = st.columns(4)
                    for i, frame in enumerate(frames):
                        with frame_cols[i % 4]:
                            st.image(frame["file_path"], caption=str(frame["captured_at"]))

            # Display the source files used to generate this quiz so the
            # instructor can identify which study materials the student used.
            try:
                raw_filenames = attempt.get("source_filenames")
                if raw_filenames:
                    filenames = json.loads(raw_filenames)
                    if filenames:
                        st.write(
                            "**Source Files:** " + ", ".join(filenames)
                        )
            except Exception:
                pass

            # Reconstruct the per-question review from stored answers and
            # the original question set saved with the quiz.
            questions = []
            try:
                questions   = json.loads(attempt.get("questions_json", "[]"))
                answers_raw = json.loads(attempt.get("answers_json", "{}"))
                # answers_json keys are stored as strings; convert to int for lookup.
                answers     = {int(k): v for k, v in answers_raw.items()}

                if questions:
                    st.markdown("**Question Review:**")
                    for i, q in enumerate(questions):
                        user_answer    = answers.get(i, "")
                        correct_answer = q.get("correct_answer", "")
                        question_type  = q.get("question_type", "")

                        if question_type == "short_answer":
                            result = "❓ Review"
                        elif user_answer == correct_answer:
                            result = "✅ Correct"
                        else:
                            result = "❌ Incorrect"

                        with st.expander(f"Q{i + 1}: {result}", expanded=False):
                            st.markdown(f"**Question:** {q.get('question_text', '')}")
                            st.markdown(
                                f"**Student's Answer:** "
                                f"{user_answer if user_answer else '*No answer provided*'}"
                            )
                            st.markdown(f"**Correct Answer:** {correct_answer}")
                            st.markdown(f"**Explanation:** {q.get('explanation', 'N/A')}")
            except Exception:
                st.caption("Question review unavailable for this attempt.")

            st.markdown("---")

            # Download options — reconstruct the quiz_data dict from stored
            # fields so the Word document generators receive the expected format.
            if questions:
                # Reconstruct quiz_data to match the format produced by
                # generate_multiple_question_types() so the Word document
                # generators produce output identical to the Quiz Interface tab.
                mc = attempt.get("mc_count", 0)
                tf = attempt.get("tf_count", 0)
                sa = attempt.get("sa_count", 0)
                quiz_data_for_export = {
                    "questions": questions,
                    "metadata": {
                        "difficulty":            attempt.get("difficulty"),
                        "total_questions":       len(questions),
                        "multiple_choice_count": mc,
                        "true_false_count":      tf,
                        "short_answer_count":    sa,
                        "topic_filters":         attempt.get("topic_focus"),
                        "model_used":            attempt.get("model_used"),
                        # generation_summary is used by the with-answers Word
                        # document to render the question distribution line.
                        "generation_summary": {
                            "multiple_choice": {"generated": mc},
                            "true_false":      {"generated": tf},
                            "short_answer":    {"generated": sa},
                        },
                    },
                }
                # All actions on one row: three download buttons on the left,
                # delete button on the far right.
                dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)

                with dl_col1:
                    try:
                        doc_bytes = create_word_document_questions_only(quiz_data_for_export)
                        st.download_button(
                            label="📄 Questions Only (Word)",
                            data=doc_bytes.getvalue(),
                            file_name=f"quiz_{attempt_id}_questions.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"inst_dl_qonly_{attempt_id}",
                        )
                    except Exception as e:
                        st.error(f"Failed to generate document: {str(e)}")

                with dl_col2:
                    try:
                        doc_bytes = create_word_document_with_answers(quiz_data_for_export)
                        st.download_button(
                            label="📄 With Answers (Word)",
                            data=doc_bytes.getvalue(),
                            file_name=f"quiz_{attempt_id}_answers.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"inst_dl_qans_{attempt_id}",
                        )
                    except Exception as e:
                        st.error(f"Failed to generate document: {str(e)}")

                with dl_col3:
                    st.download_button(
                        label="📋 Download JSON",
                        data=json.dumps(quiz_data_for_export, indent=2),
                        file_name=f"quiz_{attempt_id}.json",
                        mime="application/json",
                        key=f"inst_dl_json_{attempt_id}",
                    )

                with dl_col4:
                    if st.button(
                        "🗑️ Delete",
                        key=f"inst_del_{attempt_id}",
                        type="primary",
                    ):
                        _dialog_delete_quiz_attempt(attempt_id)
# =============================================================================
# MAIN UI ENTRY POINT
# =============================================================================

@st.dialog("Delete File")
def _dialog_delete_pq_file(file_id: int, file_name: str, file_path: str) -> None:
    """
    Confirmation modal for permanently deleting a saved practice quiz source file.

    Removes the database record and the physical file from disk. Only rendered
    for instructor roles — students cannot delete saved files.
    """
    st.warning(
        f"Are you sure you want to delete **{file_name}**? "
        "This cannot be undone."
    )
    col1, col2 = st.columns(2)
    if col1.button("Delete", type="primary", key="pq_file_dialog_confirm"):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM files WHERE id = %s", (file_id,))
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        delete_physical_file(file_path)
        st.toast("File deleted.")
        st.rerun()
    if col2.button("Cancel", key="pq_file_dialog_cancel"):
        st.rerun()


@st.dialog("Delete Attempt")
def _dialog_delete_quiz_attempt(attempt_id: int) -> None:
    """
    Confirmation modal for permanently deleting a practice quiz attempt.

    Used by both the student history tab (student deletes their own attempt)
    and the instructor tab (instructor deletes any student's attempt).
    """
    st.warning("Are you sure you want to delete this attempt? This cannot be undone.")
    col1, col2 = st.columns(2)
    if col1.button("Delete", type="primary", key="quiz_dialog_confirm_delete"):
        delete_quiz_attempt(attempt_id)
        st.toast("Attempt deleted.")
        st.rerun()
    if col2.button("Cancel", key="quiz_dialog_cancel_delete"):
        st.rerun()


def quiz_generator_ui() -> None:
    """
    Main entry point for the Practice Quiz feature.

    Reads the course/assessment context from session state, initialises session
    state, determines the user's role to control tab visibility, and renders
    the appropriate tab set.

    Tab structure:
        Data Input & Analysis  -- upload files, configure and generate a quiz.
        Quiz Interface         -- take the quiz and receive scored feedback.
        My History             -- view past attempts for this assessment (all roles).
        Student Attempts       -- instructor summary of all student attempts
                                  (admin and teacher roles only).
    """
    initialize_quiz_session_state()

    # Read course and assessment context set by app.py's navigation.
    # course_id, course_name, and assessment_title are needed for saving
    # uploaded files to the correct directory in the files table.
    _course       = st.session_state.get("practice_quiz_selected_course", {}) or {}
    _assessment   = st.session_state.get("practice_quiz_selected_assessment", {}) or {}
    course_id        = _course.get("id")
    course_name      = _course.get("name", "")
    assessment_id    = _assessment.get("id")
    assessment_title = _assessment.get("title", "")
    user_id          = st.session_state["user"]["id"]
    user_role        = st.session_state["user"].get("role", "")
    is_instructor    = user_role in ("admin", "teacher")

    # Restore an already-generated quiz for this assessment instead of
    # forcing a fresh upload-and-generate cycle every time. quiz_generated_questions
    # otherwise lives only in session state, which is empty at the start of
    # every new browser session even though the quiz itself is already saved
    # in practice_quiz_generated. Re-checked whenever the selected assessment
    # changes so a stale quiz from a different assessment is never shown.
    if assessment_id and st.session_state.quiz_loaded_for_assessment != assessment_id:
        st.session_state.quiz_generated_questions = None
        st.session_state.quiz_analysis_complete   = False
        st.session_state.quiz_current_db_id       = None
        st.session_state.quiz_user_answers        = {}
        st.session_state.quiz_submitted           = False
        st.session_state.quiz_attempt_saved       = False

        existing_quiz = get_latest_generated_quiz(user_id, assessment_id)
        if existing_quiz:
            st.session_state.quiz_generated_questions = existing_quiz
            st.session_state.quiz_analysis_complete   = True
            st.session_state.quiz_current_db_id       = existing_quiz["id"]

        st.session_state.quiz_loaded_for_assessment = assessment_id

    st.markdown('<h2 class="feature-header">🧠 Quiz Generator</h2>', unsafe_allow_html=True)
    st.write(
        "Upload your study materials and generate personalized quiz questions "
        "to test your knowledge and improve learning outcomes."
    )

    # Build the tab list based on role. Students see three tabs; instructors
    # see a fourth tab that surfaces all student attempts for the assessment.
    if is_instructor:
        tabs = st.tabs([
            "📚 Data Input & Analysis",
            "🎯 Quiz Interface",
            "🕘 My History",
            "👩‍🏫 Student Attempts",
        ])
    else:
        tabs = st.tabs([
            "📚 Data Input & Analysis",
            "🎯 Quiz Interface",
            "🕘 My History",
        ])

    with tabs[0]:
        render_data_input_tab(
            user_id=user_id,
            assessment_id=assessment_id,
            course_id=course_id,
            course_name=course_name,
            assessment_title=assessment_title,
            is_instructor=is_instructor,
        )

    with tabs[1]:
        render_quiz_interface_tab()

    with tabs[2]:
        render_student_history_tab(user_id, assessment_id)

    if is_instructor:
        with tabs[3]:
            render_instructor_attempts_tab(assessment_id)