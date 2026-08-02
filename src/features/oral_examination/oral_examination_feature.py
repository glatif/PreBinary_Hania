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
#   The student side is a real-time spoken conversation, not a form: each
#   question is read aloud (TTS, see _oral_question_audio_data_url()) and the
#   student's answer starts recording automatically the instant that audio
#   finishes, via the always-on mic stream in _render_oral_qa_recorder() (a
#   CCv2 component). The student only clicks once, to grant the microphone at
#   the start, and again per question to end their answer ("Stop & Submit")
#   — never to start recording, and never to see more than the current
#   question. See the "CONVERSATIONAL Q&A RECORDER" section below.
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

import base64
import hashlib
import json
import uuid
from pathlib import Path
import streamlit as st
import pandas as pd
from typing import List, Dict, Any

from db import get_connection
from auth import save_uploaded_file

from src.utils.llm_utils import MODELS, MODEL_PROVIDERS, generate_llm_response, strip_llm_json, transcribe_audio
from src.features.exam_verification.exam_verification_feature import verify_student_identity
from src.features.exam_grading.exam_grading_feature import create_grading_prompt
from src.features.quiz_generator.document_processor import (
    process_uploaded_files,
    combine_extracted_texts,
    validate_extracted_content,
)
from src.utils.attempt_log import log_attempt_event, get_incomplete_attempts
from src.features.proctoring.proctoring_feature import (
    render_proctor_monitor,
    get_proctor_summary_by_user_assessment,
    get_proctor_frames_by_user_assessment,
    get_proctor_webcam_summary_by_user_assessment,
    get_proctor_webcam_frames_by_user_assessment,
    get_proctor_audio_summary_by_user_assessment,
    get_proctor_audio_clips_by_user_assessment,
    get_proctor_keystrokes_by_user_assessment,
    format_keystrokes_for_display,
    get_proctor_mouse_events_by_user_assessment,
    format_mouse_events_for_display,
    get_or_build_proctor_video_by_user_assessment,
    get_or_build_combined_proctor_video_by_user_assessment,
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
    audio_file_path: str = None,
    transcript: str = None,
    skipped: bool = False,
) -> None:
    """
    Persist one answered (or skipped) question.

    audio_file_path/transcript are None when skipped=True — a student who
    skips a question never records anything, unlike a transcription failure
    (which still has real audio on disk and an "Error: ..." transcript).

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
                (session_id, assessment_id, student_id, question_number, question_text, audio_file_path, transcript, skipped)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                session_id      = VALUES(session_id),
                question_text   = VALUES(question_text),
                audio_file_path = VALUES(audio_file_path),
                transcript      = VALUES(transcript),
                skipped         = VALUES(skipped),
                answered_at     = CURRENT_TIMESTAMP
            """,
            (session_id, assessment_id, student_id, question_number, question_text, audio_file_path, transcript, skipped),
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
            SELECT question_number, question_text, audio_file_path, transcript, skipped, answered_at
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
            SELECT student_id, question_number, question_text, audio_file_path, transcript, skipped, answered_at
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
# QUESTION AUDIO — text-to-speech for the spoken-conversation flow
# =============================================================================
# Each question is read aloud (Google TTS — gtts, free, no API key) before the
# student answers, so the exam feels like a real back-and-forth conversation
# rather than a text quiz read silently. Audio is generated once per question
# and cached to disk under _ORAL_QUESTION_AUDIO_DIR, keyed by a hash of the
# question text — every student hearing the same question reuses the same
# file, and editing a question's wording in Setup naturally invalidates the
# cache (new text -> new hash -> a fresh file) without needing to track or
# delete stale ones explicitly.

_ORAL_QUESTION_AUDIO_DIR = Path("data") / "oral_examination" / "question_audio"


def _oral_question_audio_path(assessment_id: int, question_number: int, question_text: str) -> Path:
    """Deterministic on-disk path for one question's TTS audio."""
    content_hash = hashlib.md5(question_text.encode("utf-8")).hexdigest()[:10]
    return (
        _ORAL_QUESTION_AUDIO_DIR
        / f"assessment_{assessment_id}"
        / f"q{question_number}_{content_hash}.mp3"
    )


def _ensure_oral_question_audio(assessment_id: int, question_number: int, question_text: str) -> Path | None:
    """
    Return the Path to this question's TTS audio, generating it with gTTS on
    first use and reusing the cached file afterward. Returns None (rather
    than raising) if generation fails — gTTS needs network access to Google's
    service, so a student on an exam machine with no internet, or any other
    TTS failure, must not block the exam; the caller falls back to
    starting the recording immediately instead of waiting on audio playback.
    """
    path = _oral_question_audio_path(assessment_id, question_number, question_text)
    if path.exists():
        return path
    try:
        from gtts import gTTS
        path.parent.mkdir(parents=True, exist_ok=True)
        gTTS(text=question_text, lang="en", slow=False).save(str(path))
        return path
    except Exception:
        return None


def _oral_question_audio_data_url(assessment_id: int, question_number: int, question_text: str) -> str | None:
    """Base64 data: URL for one question's TTS audio, embeddable directly in
    the recorder component's <audio> element below without a separate static
    file route. Returns None if the audio couldn't be generated/read."""
    path = _ensure_oral_question_audio(assessment_id, question_number, question_text)
    if not path:
        return None
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:audio/mpeg;base64,{encoded}"
    except Exception:
        return None


# =============================================================================
# CONVERSATIONAL Q&A RECORDER — plays the question, then auto-records the answer
# =============================================================================
# One question per screen, question read aloud, and the student answers
# immediately after — no seeing the next question in advance, no access to
# the whole question set at once (see the "Take Oral Exam" section below for
# the one-at-a-time reveal that was already true before this component
# existed). This component adds the "conversation" feel on top of that: the
# mic, once granted, stays live for the whole exam (same approach as
# _AUDIO_MONITOR_JS in proctoring_feature.py) so each new question can start
# recording automatically the instant its audio finishes playing, with no
# extra permission prompt or click between questions — only a manual
# "Stop & Submit" (a plain Streamlit button, wired via the stop_signal data
# field below) ends the recording, since auto-stop-on-silence risks cutting
# a student off mid-thought.
#
# State that must survive across Streamlit reruns (the live mic stream, the
# <audio> element, the in-progress MediaRecorder) is kept in a WeakMap keyed
# by parentElement, exactly as CCv2's own docs recommend for per-instance
# resources — this makes the component correct regardless of exactly how
# often the frontend re-invokes the exported function, since re-invocations
# just reconcile from the same persistent state instead of re-creating it.
_ORAL_QA_RECORDER_JS = """
export default function (component) {
  const { data, parentElement, setStateValue, setTriggerValue } = component

  const STORE = (globalThis.__oral_qa_recorder_store ||= new WeakMap())
  let state = STORE.get(parentElement)
  if (!state) {
    state = {
      micReady: false,
      stream: null,
      audioEl: null,
      recorder: null,
      chunks: [],
      lastQuestionKey: null,
      lastStopSignal: null,
      btn: null,
      statusEl: null,
      timerEl: null,
      countdownInterval: null,
      autoSubmitted: false,
    }
    STORE.set(parentElement, state)
  }

  if (!state.statusEl) {
    state.statusEl = document.createElement("div")
    state.statusEl.style.cssText = "font-size:0.95rem;margin-bottom:0.5em;"
    parentElement.appendChild(state.statusEl)
  }
  if (!state.timerEl) {
    state.timerEl = document.createElement("div")
    state.timerEl.style.cssText = "font-size:1.3rem;font-weight:600;margin-bottom:0.5em;"
    parentElement.appendChild(state.timerEl)
  }

  const setPhase = (phase) => setStateValue("phase", phase)

  const clearCountdown = () => {
    if (state.countdownInterval) {
      clearInterval(state.countdownInterval)
      state.countdownInterval = null
    }
    state.timerEl.textContent = ""
  }

  const startCountdown = () => {
    clearCountdown()
    const limitSeconds = Number(data.time_limit_seconds) || 120
    const deadline = Date.now() + limitSeconds * 1000
    const tick = () => {
      const remainingMs = deadline - Date.now()
      const remaining = Math.max(0, Math.ceil(remainingMs / 1000))
      const mins = String(Math.floor(remaining / 60)).padStart(2, "0")
      const secs = String(remaining % 60).padStart(2, "0")
      state.timerEl.textContent = `⏱️ Time remaining: ${mins}:${secs}`
      state.timerEl.style.color = remaining <= 10 ? "#c00" : ""
      if (remainingMs <= 0) {
        clearCountdown()
        state.autoSubmitted = true
        if (state.recorder && state.recorder.state !== "inactive") {
          state.recorder.stop()
          setPhase("submitting")
          state.statusEl.textContent = "⏰ Time's up — submitting your answer..."
        }
      }
    }
    tick()
    state.countdownInterval = setInterval(tick, 250)
  }

  const startRecording = () => {
    if (!state.stream) return
    state.chunks = []
    state.autoSubmitted = false
    const mimeCandidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
    const mimeType = mimeCandidates.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || ""
    const recorder = mimeType ? new MediaRecorder(state.stream, { mimeType }) : new MediaRecorder(state.stream)
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) state.chunks.push(e.data)
    }
    recorder.onstop = () => {
      clearCountdown()
      const blob = new Blob(state.chunks, { type: mimeType || "audio/webm" })
      const reader = new FileReader()
      reader.onloadend = () => {
        setTriggerValue("answer_audio", {
          data: reader.result,
          question_key: state.lastQuestionKey,
          auto_submitted: state.autoSubmitted,
        })
      }
      reader.readAsDataURL(blob)
    }
    recorder.start()
    state.recorder = recorder
    state.statusEl.textContent = "🎙️ Recording your answer — click \\"Stop & Submit\\" below when you're finished."
    setPhase("recording")
    startCountdown()
  }

  const loadAndPlayQuestion = () => {
    if (!data.audio_data_url) {
      // TTS generation failed server-side — don't block the exam waiting on
      // audio that will never arrive; start recording immediately so the
      // student can still answer the (text-only) question on screen.
      startRecording()
      return
    }
    state.statusEl.textContent = "🔊 Playing question audio — listen carefully..."
    setPhase("playing_question")
    state.audioEl.src = data.audio_data_url
    state.audioEl.onended = () => startRecording()
    state.audioEl.play().catch(() => {
      // Autoplay blocked by the browser for some reason — fall back to
      // recording immediately rather than leaving the student stuck with a
      // silent question and no way to answer.
      startRecording()
    })
  }

  const beginSession = async () => {
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      state.statusEl.textContent = "❌ Microphone permission denied — you cannot proceed without it."
      setPhase("mic_denied")
      return
    }
    state.micReady = true
    state.audioEl = document.createElement("audio")
    state.audioEl.style.display = "none"
    parentElement.appendChild(state.audioEl)
    if (state.btn) {
      state.btn.remove()
      state.btn = null
    }
    // Both baselines must be set here, before the first "mic already
    // granted" render below ever runs its question_key/stop_signal
    // comparisons — otherwise stop_signal's initial value (0 from Python)
    // would never equal the sentinel null it's compared against, and the
    // very first "recording" phase would immediately look like an
    // already-requested stop and cut the student off before they'd said
    // anything.
    state.lastQuestionKey = data.question_key
    state.lastStopSignal = data.stop_signal
    loadAndPlayQuestion()
  }

  if (!state.micReady) {
    if (!state.btn) {
      state.btn = document.createElement("button")
      state.btn.textContent = "🎙️ Enable Microphone & Begin"
      state.btn.style.cssText =
        "padding:0.6em 1.2em;font-size:1rem;cursor:pointer;border-radius:6px;" +
        "border:1px solid #0a7;background:#e8fff5;color:#050;"
      state.btn.onclick = beginSession
      parentElement.appendChild(state.btn)
      state.statusEl.textContent =
        "Click below once you're ready to begin — the question will be read aloud immediately after."
      setPhase("need_mic")
    }
    return
  }

  // Mic already granted and the session is underway: react to either a new
  // question (data.question_key changed) or an external "stop & submit"
  // request from Python (data.stop_signal changed) — never both at once,
  // since a stop_signal bump always arrives for the question that is
  // currently being recorded, before Python advances to the next one.
  if (data.question_key !== state.lastQuestionKey) {
    state.lastQuestionKey = data.question_key
    loadAndPlayQuestion()
  } else if (data.stop_signal !== state.lastStopSignal) {
    state.lastStopSignal = data.stop_signal
    if (state.recorder && state.recorder.state !== "inactive") {
      state.recorder.stop()
      setPhase("submitting")
      state.statusEl.textContent = "⏳ Submitting your answer..."
    }
  }
}
"""

_oral_qa_recorder_component = st.components.v2.component(
    "oral_qa_recorder",
    html="<div></div>",
    js=_ORAL_QA_RECORDER_JS,
)


def _render_oral_qa_recorder(
    question_key: str,
    audio_data_url: str | None,
    stop_signal: int,
    time_limit_seconds: int,
    key: str,
):
    """
    Mount the conversational Q&A recorder for the current question.

    Returns a result object with:
      .phase        -- "need_mic" | "playing_question" | "recording" |
                        "submitting" | "mic_denied" | None (before first mount)
      .answer_audio -- {"data": <base64 data URL>, "question_key": str,
                        "auto_submitted": bool} once recording has stopped
                        and been packaged, else None (this is a trigger — it
                        resets after one rerun, so the caller must persist it
                        if it needs to survive a failed save/transcription
                        attempt). auto_submitted is True when the recorder
                        stopped itself because time_limit_seconds ran out,
                        rather than the student clicking "Stop & Submit".
    """
    return _oral_qa_recorder_component(
        key=key,
        data={
            "question_key": question_key,
            "audio_data_url": audio_data_url,
            "time_limit_seconds": time_limit_seconds,
            "stop_signal": stop_signal,
        },
        on_phase_change=lambda: None,
        on_answer_audio_change=lambda: None,
    )


# =============================================================================
# STUDENT — "Take Oral Exam"
# =============================================================================
# Questions are revealed one at a time and are never shown in advance — a real
# oral exam shouldn't give a student prep time on the next question the way
# Exam Grading's upfront question list does. Once a student has answered
# every question the exam is locked; there is no re-submission, unlike Exam
# Grading's file re-upload allowance, because a spoken exam is a one-attempt
# event by nature.
#
# Each question is read aloud via _render_oral_qa_recorder() (TTS + an
# always-live mic stream) and the answer recording starts automatically the
# moment that audio ends — the student only ever clicks "Stop & Submit" to
# end their answer, never to start it, and never sees a question until it's
# their turn to answer it.

@st.dialog("Submit & Continue?")
def _dialog_confirm_oral_stop(stop_key: str) -> None:
    """
    Confirmation modal shown before ending the current question's recording.

    Questions are answered one at a time with no way back once submitted
    (see the module docstring), so this warns the student before that
    becomes irreversible rather than letting a single click end the
    recording with no chance to reconsider. Only shown for a manual stop —
    the automatic timeout advance below needs no confirmation since it is
    not a student-initiated action.
    """
    st.warning(
        "Once you submit this answer you will move to the next question and "
        "cannot come back to change it. Continue?"
    )
    col1, col2 = st.columns(2)
    if col1.button("Continue", type="primary", key="oral_stop_dialog_confirm"):
        st.session_state[stop_key] += 1
        st.rerun()
    if col2.button("Cancel", key="oral_stop_dialog_cancel"):
        st.rerun()


@st.dialog("Skip This Question?")
def _dialog_confirm_oral_skip(skip_key: str, stop_key: str, question_number: int) -> None:
    """
    Confirmation modal for skipping a question with no answer recorded at
    all — distinct from Stop & Submit, which always submits whatever audio
    has been captured so far.

    Only *requests* the skip here (records which question_number to skip in
    session_state and bumps stop_key) rather than saving immediately —
    saving must wait for a follow-up rerun where the recorder has already
    been remounted with the bumped stop_signal (see the skip_key handling in
    _render_student_oral_exam right after the recorder is mounted). This
    mirrors the exact two-step sequencing _dialog_confirm_oral_stop relies
    on: if a recording was already in progress, the JS component needs one
    full round-trip on the *same* question_key to stop the old
    MediaRecorder before Python advances to a new question_key. Skipping
    that round-trip (e.g. saving and bumping stop_key in the same click)
    would let the still-running old recorder's ondataavailable handler keep
    writing into the next question's (already-reset) chunk buffer,
    corrupting its recording.
    """
    st.warning(
        "Skipping this question means you will not be able to come back and "
        "answer it later. Are you sure you want to skip it?"
    )
    col1, col2 = st.columns(2)
    if col1.button("Skip Question", type="primary", key="oral_skip_dialog_confirm"):
        st.session_state[skip_key] = question_number
        st.session_state[stop_key] += 1
        st.rerun()
    if col2.button("Cancel", key="oral_skip_dialog_cancel"):
        st.rerun()


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
                if r.get("skipped"):
                    st.caption("⏭️ Skipped — no answer provided.")
                else:
                    st.caption(r.get("transcript") or "(no transcript)")
        return

    st.caption(
        f"This oral exam has {total_questions} question(s). Each question is read "
        "aloud, and your answer starts recording automatically as soon as it "
        "finishes — questions are revealed one at a time and are not shown in "
        "advance."
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

    # Logged once per browser session — guarded the same way session_key
    # above is, so a page rerun doesn't write a new 'started' row every time
    # this function re-executes. This is the row that makes an abandoned
    # attempt visible at all: without it, a student who never answers a
    # single question leaves no trace anywhere in the database.
    started_logged_key = f"oral_exam_started_logged_{assessment_id}"
    if not st.session_state.get(started_logged_key):
        log_attempt_event(
            user_id=int(user["id"]),
            assessment_id=assessment_id,
            feature_name="oral_examination",
            event_type="started",
            session_id=session_id,
        )
        st.session_state[started_logged_key] = True

    answered_numbers = {r["question_number"] for r in existing}
    next_question = next(
        (q for q in questions if q["question_number"] not in answered_numbers), None
    )
    if next_question is None:
        st.rerun()
        return

    # Logged once per question the student actually reaches (guarded on the
    # question number so it doesn't re-fire on every rerun while the same
    # question is still on screen).
    reached_logged_key = f"oral_exam_reached_logged_{assessment_id}"
    if st.session_state.get(reached_logged_key) != next_question["question_number"]:
        log_attempt_event(
            user_id=int(user["id"]),
            assessment_id=assessment_id,
            feature_name="oral_examination",
            event_type="question_reached",
            session_id=session_id,
            question_number=next_question["question_number"],
        )
        st.session_state[reached_logged_key] = next_question["question_number"]

    st.divider()
    st.markdown(f"**Question {next_question['question_number']} of {total_questions}**")
    st.markdown(f"### {next_question['question_text']}")

    question_key = f"{assessment_id}_{next_question['question_number']}"
    audio_data_url = _oral_question_audio_data_url(
        assessment_id, next_question["question_number"], next_question["question_text"]
    )
    if audio_data_url is None:
        st.caption(
            "⚠️ Could not generate question audio right now — recording will "
            "start immediately below; answer the question as written above."
        )

    stop_key = f"oral_stop_signal_{assessment_id}"
    st.session_state.setdefault(stop_key, 0)
    skip_key = f"oral_skip_requested_{assessment_id}"
    pending_key = f"oral_pending_answer_{question_key}"

    time_limit_seconds = int(next_question.get("time_limit_seconds", 120))
    recorder_result = _render_oral_qa_recorder(
        question_key=question_key,
        audio_data_url=audio_data_url,
        stop_signal=st.session_state[stop_key],
        time_limit_seconds=time_limit_seconds,
        key=f"oral_qa_recorder_{assessment_id}",
    )

    # A skip requested on the previous rerun is executed here, now that the
    # recorder above has just been remounted with the bumped stop_signal
    # (see _dialog_confirm_oral_skip's docstring for why this can't happen
    # in the same click that requests it) — question_key is still the
    # skipped question at this point, since nothing has been saved yet.
    if st.session_state.get(skip_key) == next_question["question_number"]:
        save_oral_exam_response(
            session_id=session_id,
            assessment_id=assessment_id,
            student_id=int(user["id"]),
            question_number=next_question["question_number"],
            question_text=next_question["question_text"],
            skipped=True,
        )
        log_attempt_event(
            user_id=int(user["id"]),
            assessment_id=assessment_id,
            feature_name="oral_examination",
            event_type="skipped",
            session_id=session_id,
            question_number=next_question["question_number"],
        )
        if len(existing) + 1 >= total_questions:
            log_attempt_event(
                user_id=int(user["id"]),
                assessment_id=assessment_id,
                feature_name="oral_examination",
                event_type="completed",
                session_id=session_id,
            )
        del st.session_state[skip_key]
        st.rerun()

    # Skip is available as soon as the mic session is live (question audio
    # playing or already recording) — unlike Stop & Submit, it needs no
    # recording to exist yet, since it discards rather than submits.
    if recorder_result.phase in ("playing_question", "recording"):
        col_skip, col_stop = st.columns(2)
        with col_skip:
            if st.button(
                "⏭️ Skip Question",
                key=f"oral_skip_btn_{assessment_id}_{next_question['question_number']}",
            ):
                _dialog_confirm_oral_skip(
                    skip_key=skip_key,
                    stop_key=stop_key,
                    question_number=next_question["question_number"],
                )
        if recorder_result.phase == "recording":
            with col_stop:
                if st.button(
                    "⏹️ Stop & Submit Answer",
                    type="primary",
                    key=f"oral_stop_btn_{assessment_id}_{next_question['question_number']}",
                ):
                    _dialog_confirm_oral_stop(stop_key)
    elif recorder_result.phase == "mic_denied":
        st.error(
            "Microphone permission was denied. You must allow microphone "
            "access to answer this oral exam — reload the page and try again."
        )

    # answer_audio is a trigger (resets after one rerun), so the decoded
    # bytes are stashed in session_state under pending_key right away —
    # that way a failed transcription attempt below can be retried from the
    # same recording instead of losing it (mirrors the original st.audio_input
    # flow, where the widget itself held the bytes across a failed retry).
    if (
        recorder_result.answer_audio is not None
        and recorder_result.answer_audio.get("question_key") == question_key
        and pending_key not in st.session_state
    ):
        try:
            # Split on "base64," rather than the first comma — a comma can
            # appear earlier inside the MIME type itself for some codec
            # strings (see the identical fix in proctoring_feature.py's
            # save_proctor_video_segment(), which hit this for real with
            # "video/webm;codecs=vp8,opus"). None of this recorder's audio
            # MIME candidates contain one today, but splitting on the first
            # comma would silently corrupt the recording if that ever changed.
            header, _, encoded = recorder_result.answer_audio.get("data", "").partition("base64,")
            st.session_state[pending_key] = {
                "bytes": base64.b64decode(encoded),
                "ext": "mp4" if "audio/mp4" in header else "webm",
                "auto_submitted": bool(recorder_result.answer_audio.get("auto_submitted")),
            }
        except Exception:
            st.error("Could not read your recording — please try answering again.")

    pending = st.session_state.get(pending_key)
    if pending:
        if pending.get("auto_submitted"):
            st.info("⏰ Time's up — your answer is being submitted automatically.")
        with st.spinner("Saving and transcribing your answer..."):
            try:
                audio_bytes = pending["bytes"]
                audio_name = f"answer.{pending['ext']}"
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
                # audio itself is already safely on disk at saved_path, and
                # the raw bytes are still in pending_key, so the student can
                # retry transcription without re-recording.
                if transcript.startswith("Error:"):
                    st.error(
                        f"Could not transcribe your answer: {transcript} "
                        "Your recording was not lost."
                    )
                    if st.button(
                        "Retry Transcription",
                        key=f"oral_retry_{assessment_id}_{next_question['question_number']}",
                    ):
                        st.rerun()
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
                    log_attempt_event(
                        user_id=int(user["id"]),
                        assessment_id=assessment_id,
                        feature_name="oral_examination",
                        event_type="timed_out" if pending.get("auto_submitted") else "answer_submitted",
                        session_id=session_id,
                        question_number=next_question["question_number"],
                    )
                    # This save is the last question exactly when it brings
                    # the answered count up to total_questions — that's the
                    # terminal event get_incomplete_attempts() looks for, so
                    # a fully-finished attempt stops showing up as abandoned.
                    if len(existing) + 1 >= total_questions:
                        log_attempt_event(
                            user_id=int(user["id"]),
                            assessment_id=assessment_id,
                            feature_name="oral_examination",
                            event_type="completed",
                            session_id=session_id,
                        )
                    del st.session_state[pending_key]
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
            "Paste the topic or source material the questions should cover, or "
            "upload a lecture file (PDF, Word, PowerPoint, or text) to extract it "
            "automatically. Choose how many questions and how hard they should be, "
            "then click **Generate Questions with AI**. Review and edit the "
            "generated questions, add a grading rubric, and save.  \n\n"
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

    source_mode = st.radio(
        "Source material for question generation",
        ["Paste topic or text", "Upload lecture file(s)"],
        key=f"oral_setup_source_mode_{assessment_id}",
        horizontal=True,
    )

    if source_mode == "Upload lecture file(s)":
        uploaded_files = st.file_uploader(
            "Upload PDF, Word, PowerPoint, or text file(s) from the lecture:",
            type=["pdf", "docx", "pptx", "txt"],
            accept_multiple_files=True,
            key=f"oral_lecture_uploader_{assessment_id}",
            help="You can upload multiple files. All content will be extracted and combined.",
        )
        if uploaded_files:
            # Guard extraction with a session-state flag keyed on the sorted
            # filenames — Streamlit reruns this block on every interaction
            # while files remain in the uploader, so without this guard the
            # (potentially slow) extraction would redo on every rerun instead
            # of only when the actual file selection changes.
            extracted_key = f"oral_setup_extracted_filenames_{assessment_id}"
            current_filenames = tuple(sorted(uf.name for uf in uploaded_files))
            if st.session_state.get(extracted_key) != current_filenames:
                with st.spinner("Extracting text from uploaded file(s)..."):
                    extracted_texts = process_uploaded_files(uploaded_files)
                if not validate_extracted_content(extracted_texts):
                    st.error(
                        "Could not extract enough text from the uploaded file(s). "
                        "Try a different file or paste the material below instead."
                    )
                else:
                    st.session_state[content_key] = combine_extracted_texts(extracted_texts)
                    st.session_state[extracted_key] = current_filenames
                    st.success(
                        f"Extracted text from {len(extracted_texts)} file(s). "
                        "Review it below before generating questions."
                    )

    st.session_state[content_key] = st.text_area(
        "Topic or source material for question generation",
        value=st.session_state[content_key],
        height=180,
        key=f"{content_key}_widget",
        help="Edit the extracted or pasted text if needed before generating questions.",
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
            col_q, col_time, col_del = st.columns([5, 2, 1])
            with col_q:
                q["question_text"] = st.text_area(
                    f"Question {q.get('question_number', i + 1)}",
                    value=q.get("question_text", ""),
                    height=80,
                    key=f"oral_q_text_{assessment_id}_{i}",
                )
            with col_time:
                # Per-question spoken-answer time limit — the +/- steppers
                # built into st.number_input satisfy the "+ or - change the
                # time" requirement without a custom widget. Defaults to two
                # minutes; also the fallback read by the student flow for
                # older saved questions that predate this field.
                q["time_limit_seconds"] = st.number_input(
                    "Time limit (seconds)",
                    min_value=30,
                    max_value=1800,
                    step=15,
                    value=int(q.get("time_limit_seconds", 120)),
                    key=f"oral_q_time_{assessment_id}_{i}",
                    help="How long the student has to answer this question before it auto-advances. Default 120s (2 min).",
                )
            with col_del:
                if st.button("🗑️", key=f"oral_q_del_{assessment_id}_{i}"):
                    st.session_state[questions_key].pop(i)
                    st.rerun()
        if st.button("+ Add Question", key=f"oral_q_add_{assessment_id}"):
            next_number = len(st.session_state[questions_key]) + 1
            st.session_state[questions_key].append({
                "question_number": next_number,
                "question_text": "",
                "time_limit_seconds": 120,
            })
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

    # Attempts that were opened but never finished — see attempt_log.py.
    # Shown even when no student has completed the exam yet (an "all
    # abandoned" assessment is exactly the case this is meant to surface),
    # so this renders before the early return below.
    incomplete = get_incomplete_attempts(assessment_id, "oral_examination")
    if incomplete:
        with st.expander(f"⚠️ Started but did not finish ({len(incomplete)})", expanded=False):
            for row in incomplete:
                name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
                last_q = row.get("last_question_reached")
                q_label = f"question {last_q} of {total_questions}" if last_q else "no question reached"
                st.caption(f"**{name}** — last saw {q_label}, last activity {row['last_activity']}")

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

    st.caption(
        "Each answer is graded with one LLM call, one at a time — a full class "
        "can take several minutes, longer on a local/Ollama model or a slow "
        "connection. The status line below updates after every question, not "
        "just every student, so it should keep moving throughout."
    )

    if st.button("Grade All Submissions", key="oral_grade_all_btn"):
        grading_session_id = str(uuid.uuid4())
        graded_by = int(st.session_state["user"]["id"])
        graded_results: List[Dict[str, Any]] = []

        progress_bar = st.progress(0)
        status_text = st.empty()

        # Fetched once for the whole assessment rather than once per student —
        # grading a class of 30 would otherwise issue 30 separate round-trips
        # for data this single query already returns.
        all_responses = get_oral_exam_responses_for_assessment(assessment_id)
        responses_by_student: Dict[int, List[Dict]] = {}
        for r in all_responses:
            responses_by_student.setdefault(r["student_id"], []).append(r)

        # One grading step is one (student, question) pair — each involves its
        # own LLM call (up to LLM_REQUEST_TIMEOUT_SECONDS, currently 120s, if
        # the provider is slow) — so progress must advance per call, not per
        # student. Advancing only per student left the bar and status text
        # frozen on the same message for as long as it took to grade every
        # question that student answered, which looked identical to the whole
        # thing having hung even though it was still working.
        total_steps = sum(
            len(responses_by_student.get(s["student_id"], [])) for s in complete_students
        )
        completed_steps = 0

        if total_steps == 0:
            status_text.text("Nothing to grade.")

        for student in complete_students:
            student_name = f"{student['first_name']} {student['last_name']}".strip()

            responses = responses_by_student.get(student["student_id"], [])
            for response in responses:
                status_text.text(
                    f"Grading {student_name} — question {response['question_number']} "
                    f"of {total_questions}..."
                )
                raw_transcript = response.get("transcript") or ""
                if response.get("skipped"):
                    student_answer = "(student skipped this question — no answer provided)"
                # Guard against rows saved before the transcription-error check
                # in _render_student_oral_exam existed — an "Error: ..." string
                # must never be graded as if it were the student's answer.
                elif not raw_transcript or raw_transcript.startswith("Error:"):
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
                    # st.spinner() shows a continuously-animated icon for as
                    # long as this block runs, unlike the plain text above —
                    # without it, a single slow call (a local/Ollama model in
                    # particular can take 30s+, especially a "thinking" model
                    # like deepseek-r1) has zero visual motion until it
                    # finishes, which looks identical to having hung. This
                    # matters most for a small assessment (few students/
                    # questions), where progress_bar below has little or
                    # nothing to subdivide between calls.
                    with st.spinner(f"Waiting on {selected_model} — this can take a while for local models..."):
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

                completed_steps += 1
                progress_bar.progress(completed_steps / total_steps)

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

                frames = get_proctor_frames_by_user_assessment(student_id, assessment_id)
                if frames:
                    with st.expander(f"📷 Screen Capture Frames ({len(frames)})", expanded=False):
                        frame_cols = st.columns(4)
                        for i, frame in enumerate(frames):
                            with frame_cols[i % 4]:
                                st.image(frame["file_path"], caption=str(frame["captured_at"]))

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
                if webcam_proctor["pending_count"]:
                    st.caption(
                        f"⏳ {webcam_proctor['pending_count']} frame(s) awaiting analysis — "
                        "run \"Run Proctoring Analysis\" in Admin Panel → Maintenance."
                    )

                webcam_frames = get_proctor_webcam_frames_by_user_assessment(student_id, assessment_id)
                if webcam_frames:
                    with st.expander(f"📷 Webcam Capture Frames ({len(webcam_frames)})", expanded=False):
                        webcam_cols = st.columns(4)
                        for i, frame in enumerate(webcam_frames):
                            flags = []
                            if frame["analysis_status"] == "pending":
                                flags.append("analysis pending")
                            else:
                                if frame["no_face"]:
                                    flags.append("no face")
                                if frame["multiple_faces"]:
                                    flags.append(f"{frame['face_count']} faces")
                                if frame["looking_away"]:
                                    flags.append("looking away")
                            caption = str(frame["captured_at"])
                            if flags:
                                caption += " — ⚠️ " + ", ".join(flags)
                            with webcam_cols[i % 4]:
                                st.image(frame["file_path"], caption=caption)

                # Background-microphone clips captured for the whole oral-exam
                # session by the proctoring stack's own separate mic stream
                # (distinct from the student's actual spoken answers, captured
                # by _render_oral_qa_recorder()'s recorder above), kept only for
                # segments where analyze_audio_clip()'s Silero VAD model detected
                # human speech — see save_proctor_audio_clip() in proctoring_feature.py.
                # Analysis is deferred, so clip_count only reflects clips
                # already processed; pending_count is how many captured
                # segments are still waiting.
                audio_proctor = get_proctor_audio_summary_by_user_assessment(student_id, assessment_id)
                audio_icon = "🔴" if audio_proctor["clip_count"] else "🟢"
                st.caption(
                    f"{audio_icon} Microphone: {audio_proctor['clip_count']} clip(s) with "
                    f"detected speech, {audio_proctor['speech_duration_sec']:.1f}s total"
                )
                if audio_proctor["pending_count"]:
                    st.caption(
                        f"⏳ {audio_proctor['pending_count']} segment(s) awaiting analysis — "
                        "run \"Run Proctoring Analysis\" in Admin Panel → Maintenance."
                    )
                audio_clips = get_proctor_audio_clips_by_user_assessment(student_id, assessment_id)
                if audio_clips:
                    with st.expander(f"🎙️ Audio Clips With Detected Speech ({len(audio_clips)})", expanded=False):
                        for clip in audio_clips:
                            st.audio(clip["file_path"])
                            st.caption(
                                f"{clip['captured_at']} — {clip['speech_duration_sec']:.1f}s speech "
                                f"of {clip['clip_duration_sec']:.1f}s segment"
                            )

                # Full-session screen/webcam(+audio) recordings, stitched
                # from segments uploaded across every proctoring session
                # this student had for this assessment — see
                # get_or_build_proctor_video_by_user_assessment() in
                # proctoring_feature.py. Built on request (button click)
                # rather than on every render of this row, cached in
                # session_state so reopening this page doesn't re-invoke
                # ffmpeg.
                # Combined session recording — screen as the base with the
                # webcam composited on top as a small picture-in-picture
                # overlay, carrying the webcam's audio track (see
                # get_or_build_combined_proctor_video_by_user_assessment()
                # in proctoring_feature.py). This is the one file most
                # reviewers want; the separate screen/webcam players below
                # stay available for closer inspection of either feed.
                combined_cache_key = f"proctor_video_combined_user_{student_id}_assessment_{assessment_id}"
                with st.expander("🎬 Combined Session Recording (Screen + Webcam PiP + Audio)", expanded=False):
                    cached_combined = st.session_state.get(combined_cache_key)
                    if cached_combined:
                        st.video(str(cached_combined))
                    elif st.button("Load Combined Recording", key=f"load_{combined_cache_key}"):
                        with st.spinner("Building combined recording..."):
                            built_combined = get_or_build_combined_proctor_video_by_user_assessment(
                                student_id, assessment_id
                            )
                        if built_combined:
                            st.session_state[combined_cache_key] = built_combined
                            st.video(str(built_combined))
                        else:
                            st.caption("No recording available for this student yet.")

                for kind, label, icon in (
                    ("screen", "Full Screen Recording", "🖥️"),
                    ("webcam", "Full Webcam + Audio Recording", "🎥"),
                ):
                    cache_key = f"proctor_video_{kind}_user_{student_id}_assessment_{assessment_id}"
                    with st.expander(f"{icon} {label}", expanded=False):
                        # Only a successful build is cached — a None result
                        # (no segments yet, or a transient ffmpeg failure)
                        # must not get stuck forever with no retry option.
                        cached_path = st.session_state.get(cache_key)
                        if cached_path:
                            st.video(str(cached_path))
                        elif st.button(f"Load {label}", key=f"load_{cache_key}"):
                            with st.spinner(f"Building {label.lower()}..."):
                                built_path = get_or_build_proctor_video_by_user_assessment(
                                    student_id, assessment_id, kind
                                )
                            if built_path:
                                st.session_state[cache_key] = built_path
                                st.video(str(built_path))
                            else:
                                st.caption("No recording available for this student yet.")

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
