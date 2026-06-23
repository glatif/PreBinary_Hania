# =============================================================================
# proctoring_feature.py
# =============================================================================
# Lightweight, always-on tab-switch / window-focus-loss monitoring, plus an
# optional screen-share permission prompt that — once granted — periodically
# captures a downscaled JPEG snapshot of the shared screen and saves it to
# disk, for the active quiz attempt that begins immediately after a student
# clears the identity verification gate (see exam_verification_feature.py).
#
# Browser security constraints shape this design — they cannot be worked
# around from application code:
#   - document visibilitychange and window blur/focus events fire with no
#     permission prompt, so that part of the monitor starts automatically and
#     silently the instant the quiz screen renders.
#   - navigator.mediaDevices.getDisplayMedia() can only be invoked from a real
#     user gesture (a click) and always raises the browser's own native
#     "Share your screen" dialog — there is no way to start screen capture
#     without that one click, and the API does not exist on most mobile
#     browsers. The button below requests it once right after verification;
#     whatever the outcome (granted, denied, unsupported), the quiz is never
#     blocked on it — only the outcome (and any captured frames) are logged
#     for instructor review.
#   - There is no media server in this app, so this captures periodic still
#     frames rather than continuous video — a JPEG snapshot is drawn from the
#     shared stream onto a canvas at a fixed interval and sent back to Python
#     as a base64 data URL via setTriggerValue(), the same channel used for
#     tab-switch events. Continuous video recording/upload would need a
#     dedicated media pipeline (MediaRecorder + chunked upload + a storage
#     backend) and is a meaningfully bigger feature than what is built here.
#
# Capture cadence is intentionally conservative to keep storage and bandwidth
# bounded: one frame every CAPTURE_INTERVAL_MS, downscaled to at most
# MAX_FRAME_DIMENSION px on the long edge, capped at MAX_FRAMES_PER_SESSION
# total frames per screen-share session. Tune the constants below if you need
# a different tradeoff.
#
# Implementation note: this uses st.components.v2.component(), which mounts
# inline JS directly into the app's own DOM (no iframe), so document/window
# in the JS below refer to the real top-level page.
#
# All events and frames are written to quiz_proctor_events / quiz_proctor_frames,
# keyed by a per-attempt session_id (a UUID minted the first time the monitor
# renders for a given quiz gate). The same session_id is stamped onto the
# practice_quiz_attempts row at submission time (quiz_generator_feature.py) so
# instructors can review the two together. Frame image files are written to
# disk under uploads/proctor_frames/ — see save_proctor_frame().
#
# This data is meant to be short-lived: cleanup_old_proctor_data() deletes
# events/frames (and their files on disk) past a retention window, and is
# exposed as an on-demand "Run Proctoring Data Cleanup" button in the Admin
# Panel's Maintenance tab (app.py) rather than running on its own — this app
# has no background worker/cron, so nothing deletes data unless an admin (or
# an external scheduler calling the same function) actually triggers it.
# =============================================================================

import base64
import time
import uuid
from pathlib import Path

import streamlit as st

from db import get_connection

# ---- Screen-capture cadence/limits — tune to taste ----
CAPTURE_INTERVAL_MS    = 20_000   # one frame every 20 seconds
MAX_FRAME_DIMENSION_PX = 960      # downscale so the long edge is at most this
JPEG_QUALITY           = 0.5      # 0-1, lower = smaller files
MAX_FRAMES_PER_SESSION = 120      # hard cap (~40 minutes at the interval above)

_PROCTOR_FRAMES_DIR = Path("uploads") / "proctor_frames"

_TAB_MONITOR_JS = r"""
export default function(component) {
    const { setTriggerValue } = component;

    const report = (eventType) => setTriggerValue("violation", { event_type: eventType });

    const onVisibility = () => report(document.visibilityState === "hidden" ? "tab_hidden" : "tab_visible");
    const onBlur  = () => report("window_blur");
    const onFocus = () => report("window_focus");

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);

    return () => {
        document.removeEventListener("visibilitychange", onVisibility);
        window.removeEventListener("blur", onBlur);
        window.removeEventListener("focus", onFocus);
    };
}
"""

_SCREEN_SHARE_JS = f"""
export default function(component) {{
    const {{ setTriggerValue, parentElement }} = component;

    const CAPTURE_INTERVAL_MS    = {CAPTURE_INTERVAL_MS};
    const MAX_FRAME_DIMENSION_PX = {MAX_FRAME_DIMENSION_PX};
    const JPEG_QUALITY            = {JPEG_QUALITY};
    const MAX_FRAMES              = {MAX_FRAMES_PER_SESSION};

    const btn = document.createElement("button");
    btn.textContent = "Enable Screen Monitoring";
    btn.style.cssText =
        "padding:0.5em 1.1em;font-size:0.95rem;cursor:pointer;border-radius:6px;" +
        "border:1px solid #cc0000;background:#ffecec;color:#900;";

    btn.onclick = async () => {{
        btn.disabled = true;
        btn.textContent = "Requesting permission...";

        if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {{
            setTriggerValue("screen_share", {{ granted: false, reason: "unsupported" }});
            return;
        }}
        try {{
            const stream = await navigator.mediaDevices.getDisplayMedia({{ video: true }});

            const videoEl = document.createElement("video");
            videoEl.muted = true;
            videoEl.srcObject = stream;
            await videoEl.play();

            const canvas = document.createElement("canvas");
            const ctx = canvas.getContext("2d");
            let frameCount = 0;
            let intervalHandle = null;

            const captureFrame = () => {{
                const vw = videoEl.videoWidth;
                const vh = videoEl.videoHeight;
                if (!vw || !vh) return;

                const scale = Math.min(1, MAX_FRAME_DIMENSION_PX / Math.max(vw, vh));
                canvas.width  = Math.max(1, Math.round(vw * scale));
                canvas.height = Math.max(1, Math.round(vh * scale));
                ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

                frameCount += 1;
                setTriggerValue("frame", {{
                    data: canvas.toDataURL("image/jpeg", JPEG_QUALITY),
                    seq: frameCount,
                }});

                if (frameCount >= MAX_FRAMES && intervalHandle) {{
                    clearInterval(intervalHandle);
                    intervalHandle = null;
                }}
            }};

            captureFrame();
            intervalHandle = setInterval(captureFrame, CAPTURE_INTERVAL_MS);

            stream.getVideoTracks()[0].addEventListener("ended", () => {{
                if (intervalHandle) clearInterval(intervalHandle);
                btn.textContent = "Screen sharing stopped";
                setTriggerValue("screen_share", {{ granted: true, reason: "stopped" }});
            }});

            btn.textContent = "🔴 Screen monitoring active";
            setTriggerValue("screen_share", {{ granted: true, reason: "active" }});
        }} catch (err) {{
            setTriggerValue("screen_share", {{ granted: false, reason: "denied" }});
            btn.disabled = false;
            btn.textContent = "Enable Screen Monitoring";
        }}
    }};

    parentElement.appendChild(btn);
    return () => {{ parentElement.removeChild(btn); }};
}}
"""

# Registered once when this module is first imported. Each is mounted (called)
# once per rerun from render_proctor_monitor() below — calling the mounting
# command repeatedly is the supported pattern; re-registering the component
# definition itself on every rerun is not, which is why these live at module
# scope rather than inside the function.
_tab_monitor          = st.components.v2.component("quiz_tab_monitor", js=_TAB_MONITOR_JS)
_screen_share_button  = st.components.v2.component("quiz_screen_share_button", js=_SCREEN_SHARE_JS)


def save_proctor_event(
    session_id: str,
    user_id: int,
    quiz_id,
    assessment_id,
    event_type: str,
) -> None:
    """Insert one proctoring event row into quiz_proctor_events."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO quiz_proctor_events
                (session_id, user_id, quiz_id, assessment_id, event_type)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, user_id, quiz_id, assessment_id, event_type),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def save_proctor_frame(
    session_id: str,
    user_id: int,
    quiz_id,
    assessment_id,
    data_url: str,
) -> None:
    """
    Decode one base64 JPEG data URL captured by _SCREEN_SHARE_JS and write it
    to disk under uploads/proctor_frames/, recording its path in
    quiz_proctor_frames. Silently does nothing if data_url is malformed —
    a single dropped frame should never break the quiz for the student.
    """
    if not data_url or "," not in data_url:
        return
    try:
        image_bytes = base64.b64decode(data_url.split(",", 1)[1])
    except Exception:
        return

    frame_dir = (
        _PROCTOR_FRAMES_DIR
        / f"assessment_{assessment_id or 'none'}"
        / f"user_{user_id}"
        / session_id
    )
    frame_dir.mkdir(parents=True, exist_ok=True)
    file_path = frame_dir / f"frame_{int(time.time() * 1000)}.jpg"
    file_path.write_bytes(image_bytes)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO quiz_proctor_frames
                (session_id, user_id, quiz_id, assessment_id, file_path)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, user_id, quiz_id, assessment_id, str(file_path)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_proctor_summary(session_id: str) -> dict:
    """
    Return a per-session rollup for instructor review:
      {"violation_count": int, "screen_share": "granted" | "denied" | None}

    violation_count counts tab_hidden and window_blur events only — the
    tab_visible/window_focus counterparts are stored for the full timeline
    but are not violations themselves.
    """
    if not session_id:
        return {"violation_count": 0, "screen_share": None}

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT event_type, COUNT(*) AS n
            FROM quiz_proctor_events
            WHERE session_id = %s
            GROUP BY event_type
            """,
            (session_id,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()

    counts = {row["event_type"]: row["n"] for row in rows}
    violation_count = counts.get("tab_hidden", 0) + counts.get("window_blur", 0)

    screen_share = None
    if counts.get("screen_share_granted"):
        screen_share = "granted"
    elif counts.get("screen_share_denied"):
        screen_share = "denied"

    return {"violation_count": violation_count, "screen_share": screen_share}


def get_proctor_summary_by_user_assessment(user_id: int, assessment_id) -> dict:
    """
    Same shape as get_proctor_summary(), aggregated across every proctoring
    session this user has had for the given assessment rather than one
    session_id.

    Used by flows like the Exam Grading "Submit My Exam" upload gate, where
    there is no single attempt row to pin one session_id to — a student might
    re-open the upload page (and so start a new monitoring session) more than
    once before finally submitting their file.
    """
    if not assessment_id:
        return {"violation_count": 0, "screen_share": None}

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT event_type, COUNT(*) AS n
            FROM quiz_proctor_events
            WHERE user_id = %s AND assessment_id = %s
            GROUP BY event_type
            """,
            (user_id, assessment_id),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()

    counts = {row["event_type"]: row["n"] for row in rows}
    violation_count = counts.get("tab_hidden", 0) + counts.get("window_blur", 0)

    screen_share = None
    if counts.get("screen_share_granted"):
        screen_share = "granted"
    elif counts.get("screen_share_denied"):
        screen_share = "denied"

    return {"violation_count": violation_count, "screen_share": screen_share}


def get_proctor_frames(session_id: str, limit: int = 200) -> list[dict]:
    """Return captured frames for one proctoring session, newest first."""
    if not session_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path, captured_at
            FROM quiz_proctor_frames
            WHERE session_id = %s
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def get_proctor_frames_by_user_assessment(user_id: int, assessment_id, limit: int = 200) -> list[dict]:
    """
    Same as get_proctor_frames(), aggregated across every proctoring session
    this user has had for the given assessment — see
    get_proctor_summary_by_user_assessment() for why this exists.
    """
    if not assessment_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path, captured_at
            FROM quiz_proctor_frames
            WHERE user_id = %s AND assessment_id = %s
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (user_id, assessment_id, limit),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def cleanup_old_proctor_data(retention_days: int = 7) -> dict:
    """
    Permanently delete proctoring events and screen-capture frames older than
    retention_days, removing each frame's image file from disk before its
    quiz_proctor_frames row is deleted.

    This data is meant to be short-lived (see module docstring) — anything
    still within the retention window is left untouched; everything older is
    purged outright, with no soft-delete or archive step. Intended to be
    triggered on demand (e.g. the Admin Panel Maintenance tab) or from an
    external scheduler calling this function directly; nothing in this app
    calls it automatically.

    Returns {"events_deleted": int, "frames_deleted": int, "files_removed": int}.
    files_removed may be lower than frames_deleted if some files were already
    missing from disk (e.g. removed manually) — that is not an error here.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT file_path FROM quiz_proctor_frames "
            "WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        old_frames = cursor.fetchall() or []
    finally:
        cursor.close()

    files_removed = 0
    for row in old_frames:
        try:
            path = Path(row["file_path"])
            if path.exists():
                path.unlink()
                files_removed += 1
        except Exception:
            pass

    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM quiz_proctor_frames WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        frames_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM quiz_proctor_events WHERE created_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        events_deleted = cursor.rowcount

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "events_deleted": events_deleted,
        "frames_deleted": frames_deleted,
        "files_removed": files_removed,
    }


def render_proctor_monitor(gate_key: str, user: dict, quiz_id, assessment_id) -> str:
    """
    Start (or resume) a proctoring session for the current quiz attempt.

    Call this on every rerun, immediately after the identity-verification
    gate for gate_key has passed and before the quiz questions are rendered.
    Returns the session_id so the caller can stamp it onto the saved attempt
    row in practice_quiz_attempts.
    """
    session_key = f"proctor_session_{gate_key}"
    if session_key not in st.session_state:
        st.session_state[session_key] = str(uuid.uuid4())
    session_id = st.session_state[session_key]
    user_id = int(user["id"])

    count_key = f"proctor_violation_count_{gate_key}"
    st.session_state.setdefault(count_key, 0)
    share_key = f"proctor_share_status_{gate_key}"

    if share_key not in st.session_state:
        st.info(
            "This quiz is monitored for academic integrity. Tab switches and "
            "window focus changes are recorded automatically. You'll also be "
            "asked to share your screen below — your browser will show its "
            "own permission dialog for that. Once granted, periodic snapshots "
            "of your screen are saved for instructor review."
        )

    # Mounted on every rerun, not just before the permission outcome is known
    # — it must stay mounted to keep receiving periodic "frame" trigger values
    # for as long as screen sharing is active, which can be long after the
    # initial granted/denied outcome was already recorded below.
    share_result = _screen_share_button(
        key=f"proctor_share_{session_id}",
        on_screen_share_change=lambda: None,
        on_frame_change=lambda: None,
    )

    if share_result.screen_share is not None and share_key not in st.session_state:
        outcome = share_result.screen_share
        granted = bool(outcome.get("granted"))
        st.session_state[share_key] = "granted" if granted else "denied"
        save_proctor_event(
            session_id, user_id, quiz_id, assessment_id,
            "screen_share_granted" if granted else "screen_share_denied",
        )

    if share_result.frame is not None:
        save_proctor_frame(session_id, user_id, quiz_id, assessment_id, share_result.frame.get("data"))

    # ---- Always-on tab-switch / focus-loss monitor ----
    monitor_result = _tab_monitor(
        key=f"proctor_monitor_{session_id}",
        on_violation_change=lambda: None,
    )
    if monitor_result.violation is not None:
        event_type = monitor_result.violation.get("event_type", "unknown")
        save_proctor_event(session_id, user_id, quiz_id, assessment_id, event_type)
        if event_type in ("tab_hidden", "window_blur"):
            st.session_state[count_key] += 1
            st.warning(
                f"Tab switch / focus loss detected (#{st.session_state[count_key]}) "
                "— this has been recorded for instructor review."
            )

    if st.session_state[count_key]:
        st.caption(
            f"🔴 Monitoring active — {st.session_state[count_key]} "
            "tab-switch/focus warning(s) recorded this session."
        )
    else:
        st.caption("🟢 Monitoring active — tab switches and focus loss are being recorded.")

    return session_id
