# =============================================================================
# proctoring_feature.py
# =============================================================================
# Lightweight, always-on tab-switch / window-focus-loss monitoring and
# keystroke logging, plus optional screen-share and webcam permission prompts
# that — once granted — periodically capture a downscaled JPEG snapshot of
# the shared screen / the student's face and save it to disk, for the active
# quiz attempt that begins immediately after a student clears the identity
# verification gate (see exam_verification_feature.py).
#
# Browser security constraints shape this design — they cannot be worked
# around from application code:
#   - document visibilitychange and window blur/focus events, and keydown
#     events, fire with no permission prompt, so that part of the monitor
#     starts automatically and silently the instant the quiz screen renders.
#   - navigator.mediaDevices.getDisplayMedia()/getUserMedia() can only be
#     invoked from a real user gesture (a click) and always raise the
#     browser's own native permission dialog ("Share your screen" /
#     "Use your camera") — there is no way to start either capture without
#     that one click, and getDisplayMedia does not exist on most mobile
#     browsers. The buttons below request permission once right after
#     verification; whatever the outcome (granted, denied, unsupported), the
#     quiz is never blocked on it — only the outcome (and any captured
#     frames) are logged for instructor review.
#   - There is no media server in this app, so both captures take periodic
#     still frames rather than continuous video — a JPEG snapshot is drawn
#     from the stream onto a canvas at a fixed interval and sent back to
#     Python as a base64 data URL via setTriggerValue(), the same channel
#     used for tab-switch events. Continuous video recording/upload would
#     need a dedicated media pipeline (MediaRecorder + chunked upload + a
#     storage backend) and is a meaningfully bigger feature than what is
#     built here.
#
# Capture cadence is intentionally conservative to keep storage and bandwidth
# bounded: one frame every CAPTURE_INTERVAL_MS (screen) /
# CAMERA_CAPTURE_INTERVAL_MS (webcam), downscaled to at most
# MAX_FRAME_DIMENSION_PX / MAX_CAMERA_FRAME_DIMENSION_PX px on the long edge,
# capped at MAX_FRAMES_PER_SESSION / MAX_CAMERA_FRAMES_PER_SESSION total
# frames per session. Tune the constants below if you need a different
# tradeoff.
#
# Each webcam frame is additionally run through analyze_webcam_frame():
# mediapipe's FaceMesh detects how many faces are in frame (flagging
# no_face/multiple_faces), and when exactly one face is found, a solvePnP
# head-pose estimate over that face's landmarks yields a yaw/pitch angle used
# to flag looking_away. These are logged silently alongside the frame for
# instructor review, the same as the screen-share path — there is no live
# on-screen warning for them (unlike the tab-switch monitor below), since a
# single misread frame (camera angle, glasses glare, partial OCR-style
# misdetection) is too noisy a signal to interrupt a student over in the
# moment.
#
# Keystrokes are handled the same way the tab-switch monitor's events are,
# except batched rather than streamed: every keydown on the page is buffered
# client-side and the whole buffer is flushed to Python every
# KEYSTROKE_FLUSH_INTERVAL_MS (or sooner if MAX_KEYS_PER_BATCH is hit).
# Sending each keypress individually — like the tab monitor does for
# visibility/focus events — would mean a full Streamlit rerun per key, which
# would make typing into any quiz text field visibly lag; batching avoids
# that while still capturing every key. Any unflushed keys still in the
# buffer when the tab is closed are lost — there is no reliable way to flush
# a Streamlit component trigger value during page unload.
#
# Implementation note: this uses st.components.v2.component(), which mounts
# inline JS directly into the app's own DOM (no iframe), so document/window
# in the JS below refer to the real top-level page.
#
# All events, frames, and keystroke batches are written to
# quiz_proctor_events / quiz_proctor_frames / quiz_proctor_webcam_frames /
# quiz_proctor_keystrokes, keyed by a per-attempt session_id (a UUID minted
# the first time the monitor renders for a given quiz gate). The same
# session_id is stamped onto the practice_quiz_attempts row at submission
# time (quiz_generator_feature.py) so instructors can review the two
# together. Frame image files are written to disk under
# uploads/proctor_frames/ (screen) and uploads/proctor_webcam_frames/
# (webcam) — see save_proctor_frame()/save_proctor_webcam_frame().
#
# This data is meant to be short-lived: cleanup_old_proctor_data() deletes
# events/frames/keystrokes (and frame files on disk) past a retention window,
# and is exposed as an on-demand "Run Proctoring Data Cleanup" button in the
# Admin Panel's Maintenance tab (app.py) rather than running on its own — this
# app has no background worker/cron, so nothing deletes data unless an admin
# (or an external scheduler calling the same function) actually triggers it.
# =============================================================================

import base64
import json
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

# ---- Keystroke-batch cadence/limits — tune to taste ----
KEYSTROKE_FLUSH_INTERVAL_MS = 15_000   # flush the buffered keys every 15 seconds
MAX_KEYS_PER_BATCH          = 500      # flush early if the buffer hits this size

# ---- Webcam-capture cadence/limits — tune to taste ----
CAMERA_CAPTURE_INTERVAL_MS    = 20_000   # one frame every 20 seconds
MAX_CAMERA_FRAME_DIMENSION_PX = 480      # smaller than screen frames — just needs to be big enough for face detection
CAMERA_JPEG_QUALITY            = 0.6
MAX_CAMERA_FRAMES_PER_SESSION  = 120     # hard cap (~40 minutes at the interval above)

# ---- "Looking away" head-pose thresholds — tune to taste ----
# A face turned/tilted further than these angles (degrees) from facing the
# camera straight-on is flagged as looking away. Generous on purpose: webcams
# are usually off to one side of the screen, so some natural yaw/pitch while
# reading the screen is expected.
LOOKING_AWAY_YAW_THRESHOLD_DEG   = 30
LOOKING_AWAY_PITCH_THRESHOLD_DEG = 25

_PROCTOR_FRAMES_DIR        = Path("uploads") / "proctor_frames"
_PROCTOR_WEBCAM_FRAMES_DIR = Path("uploads") / "proctor_webcam_frames"

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

_KEYSTROKE_JS = f"""
export default function(component) {{
    const {{ setTriggerValue }} = component;

    const FLUSH_INTERVAL_MS = {KEYSTROKE_FLUSH_INTERVAL_MS};
    const MAX_KEYS_PER_BATCH = {MAX_KEYS_PER_BATCH};

    let buffer = [];

    const flush = () => {{
        if (buffer.length === 0) return;
        const batch = buffer;
        buffer = [];
        setTriggerValue("keystrokes", {{ keys: batch }});
    }};

    const onKeyDown = (e) => {{
        buffer.push({{
            key: e.key,
            ctrl: e.ctrlKey,
            shift: e.shiftKey,
            alt: e.altKey,
            meta: e.metaKey,
            t: Date.now(),
        }});
        if (buffer.length >= MAX_KEYS_PER_BATCH) flush();
    }};

    document.addEventListener("keydown", onKeyDown);
    const intervalHandle = setInterval(flush, FLUSH_INTERVAL_MS);

    return () => {{
        document.removeEventListener("keydown", onKeyDown);
        clearInterval(intervalHandle);
    }};
}}
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

_WEBCAM_MONITOR_JS = f"""
export default function(component) {{
    const {{ setTriggerValue, parentElement }} = component;

    const CAPTURE_INTERVAL_MS    = {CAMERA_CAPTURE_INTERVAL_MS};
    const MAX_FRAME_DIMENSION_PX = {MAX_CAMERA_FRAME_DIMENSION_PX};
    const JPEG_QUALITY            = {CAMERA_JPEG_QUALITY};
    const MAX_FRAMES              = {MAX_CAMERA_FRAMES_PER_SESSION};

    const btn = document.createElement("button");
    btn.textContent = "Enable Camera Monitoring";
    btn.style.cssText =
        "padding:0.5em 1.1em;font-size:0.95rem;cursor:pointer;border-radius:6px;" +
        "border:1px solid #cc0000;background:#ffecec;color:#900;margin-left:0.5em;";

    btn.onclick = async () => {{
        btn.disabled = true;
        btn.textContent = "Requesting permission...";

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
            setTriggerValue("webcam", {{ granted: false, reason: "unsupported" }});
            return;
        }}
        try {{
            const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});

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
                btn.textContent = "Camera monitoring stopped";
                setTriggerValue("webcam", {{ granted: true, reason: "stopped" }});
            }});

            btn.textContent = "🔴 Camera monitoring active";
            setTriggerValue("webcam", {{ granted: true, reason: "active" }});
        }} catch (err) {{
            setTriggerValue("webcam", {{ granted: false, reason: "denied" }});
            btn.disabled = false;
            btn.textContent = "Enable Camera Monitoring";
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
_keystroke_monitor    = st.components.v2.component("quiz_keystroke_monitor", js=_KEYSTROKE_JS)
_screen_share_button  = st.components.v2.component("quiz_screen_share_button", js=_SCREEN_SHARE_JS)
_webcam_monitor_button = st.components.v2.component("quiz_webcam_monitor_button", js=_WEBCAM_MONITOR_JS)


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


def save_proctor_keystrokes(
    session_id: str,
    user_id: int,
    quiz_id,
    assessment_id,
    keys: list,
) -> None:
    """
    Insert one batch of keystrokes (as flushed by _KEYSTROKE_JS) into
    quiz_proctor_keystrokes as a single JSON-encoded row. Silently does
    nothing for an empty batch — a missed flush should never break the quiz
    for the student.
    """
    if not keys:
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO quiz_proctor_keystrokes
                (session_id, user_id, quiz_id, assessment_id, keys_json)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, user_id, quiz_id, assessment_id, json.dumps(keys)),
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


# =============================================================================
# FACE/GAZE ANALYSIS — suspicious-movement detection on webcam frames
# =============================================================================

@st.cache_resource(show_spinner=False)
def _get_face_mesh():
    """Build (once per process) the mediapipe FaceMesh detector used to find
    faces and facial landmarks in webcam frames."""
    import mediapipe as mp
    return mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=3,
        refine_landmarks=False,
        min_detection_confidence=0.5,
    )


# Six FaceMesh landmark indices with stable, well-separated positions on the
# face, paired with a generic 3D face model (in arbitrary millimeter units)
# for the same six points — the standard solvePnP head-pose estimation setup.
# This gives an approximate yaw/pitch, not a precise gaze direction (it reads
# head orientation, not eye/iris position), which is the tradeoff for not
# needing iris landmarks (refine_landmarks=True, slower) or a calibrated
# camera intrinsics matrix.
_HEAD_POSE_LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]  # nose tip, chin, left/right eye corners, left/right mouth corners
_HEAD_POSE_MODEL_POINTS_3D = [
    (0.0, 0.0, 0.0),          # nose tip
    (0.0, -330.0, -65.0),     # chin
    (-225.0, 170.0, -135.0),  # left eye, left corner
    (225.0, 170.0, -135.0),   # right eye, right corner
    (-150.0, -150.0, -125.0), # left mouth corner
    (150.0, -150.0, -125.0),  # right mouth corner
]


def _estimate_head_pose(landmarks, image_w: int, image_h: int):
    """
    Estimate (yaw_deg, pitch_deg) from one face's FaceMesh landmarks via
    solvePnP against a generic 3D face model, using image dimensions to
    build an approximate camera matrix (no real camera calibration
    available). Returns (None, None) if solvePnP fails to converge.
    """
    import cv2
    import numpy as np

    image_points = np.array(
        [
            (landmarks[idx].x * image_w, landmarks[idx].y * image_h)
            for idx in _HEAD_POSE_LANDMARK_INDICES
        ],
        dtype=np.float64,
    )
    model_points = np.array(_HEAD_POSE_MODEL_POINTS_3D, dtype=np.float64)

    focal_length = image_w
    center = (image_w / 2, image_h / 2)
    camera_matrix = np.array(
        [
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((4, 1))

    success, rotation_vector, _ = cv2.solvePnP(
        model_points, image_points, camera_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success:
        return None, None

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    sy = (rotation_matrix[0, 0] ** 2 + rotation_matrix[1, 0] ** 2) ** 0.5
    pitch = np.degrees(np.arctan2(-rotation_matrix[2, 0], sy))
    yaw   = np.degrees(np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0]))
    return float(yaw), float(pitch)


def analyze_webcam_frame(image_bytes: bytes) -> dict:
    """
    Run one webcam JPEG frame through face detection and (when exactly one
    face is found) head-pose estimation.

    Returns {"face_count": int, "no_face": bool, "multiple_faces": bool,
    "looking_away": bool|None, "yaw_deg": float|None, "pitch_deg": float|None}.
    looking_away/yaw_deg/pitch_deg stay None whenever face_count != 1 — head
    pose is meaningless with zero or multiple faces in frame.
    """
    import cv2
    import numpy as np

    np_arr = np.frombuffer(image_bytes, np.uint8)
    image_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        return {
            "face_count": 0, "no_face": True, "multiple_faces": False,
            "looking_away": None, "yaw_deg": None, "pitch_deg": None,
        }

    face_mesh = _get_face_mesh()
    results = face_mesh.process(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    faces = results.multi_face_landmarks or []
    face_count = len(faces)

    yaw = pitch = looking_away = None
    if face_count == 1:
        h, w, _ = image_bgr.shape
        yaw, pitch = _estimate_head_pose(faces[0].landmark, w, h)
        if yaw is not None:
            looking_away = (
                abs(yaw) > LOOKING_AWAY_YAW_THRESHOLD_DEG
                or abs(pitch) > LOOKING_AWAY_PITCH_THRESHOLD_DEG
            )

    return {
        "face_count": face_count,
        "no_face": face_count == 0,
        "multiple_faces": face_count > 1,
        "looking_away": looking_away,
        "yaw_deg": yaw,
        "pitch_deg": pitch,
    }


def save_proctor_webcam_frame(
    session_id: str,
    user_id: int,
    quiz_id,
    assessment_id,
    data_url: str,
) -> None:
    """
    Decode one base64 JPEG data URL captured by _WEBCAM_MONITOR_JS, run it
    through analyze_webcam_frame(), and write both the image (to disk under
    uploads/proctor_webcam_frames/) and the analysis result (to
    quiz_proctor_webcam_frames) for instructor review. Silently does nothing
    if data_url is malformed — a single dropped frame should never break the
    quiz for the student.
    """
    if not data_url or "," not in data_url:
        return
    try:
        image_bytes = base64.b64decode(data_url.split(",", 1)[1])
    except Exception:
        return

    analysis = analyze_webcam_frame(image_bytes)

    frame_dir = (
        _PROCTOR_WEBCAM_FRAMES_DIR
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
            INSERT INTO quiz_proctor_webcam_frames
                (session_id, user_id, quiz_id, assessment_id, file_path,
                 face_count, no_face, multiple_faces, looking_away,
                 yaw_deg, pitch_deg)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id, user_id, quiz_id, assessment_id, str(file_path),
                analysis["face_count"], analysis["no_face"], analysis["multiple_faces"],
                analysis["looking_away"], analysis["yaw_deg"], analysis["pitch_deg"],
            ),
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


def _webcam_summary_from_rows(rows: list[dict], webcam_counts: dict) -> dict:
    """Shared aggregation for get_proctor_webcam_summary() and its
    by-user-assessment counterpart, given quiz_proctor_events rows (for the
    webcam_granted/denied outcome) and pre-counted quiz_proctor_webcam_frames
    flag totals."""
    counts = {row["event_type"]: row["n"] for row in rows}
    webcam = None
    if counts.get("webcam_granted"):
        webcam = "granted"
    elif counts.get("webcam_denied"):
        webcam = "denied"

    return {
        "webcam": webcam,
        "no_face_count": webcam_counts.get("no_face_count", 0),
        "multiple_faces_count": webcam_counts.get("multiple_faces_count", 0),
        "looking_away_count": webcam_counts.get("looking_away_count", 0),
    }


def get_proctor_webcam_summary(session_id: str) -> dict:
    """
    Return a per-session rollup of webcam monitoring for instructor review:
      {"webcam": "granted" | "denied" | None,
       "no_face_count": int, "multiple_faces_count": int, "looking_away_count": int}
    """
    if not session_id:
        return {"webcam": None, "no_face_count": 0, "multiple_faces_count": 0, "looking_away_count": 0}

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
        event_rows = cursor.fetchall() or []

        cursor.execute(
            """
            SELECT
                SUM(no_face)        AS no_face_count,
                SUM(multiple_faces) AS multiple_faces_count,
                SUM(looking_away)   AS looking_away_count
            FROM quiz_proctor_webcam_frames
            WHERE session_id = %s
            """,
            (session_id,),
        )
        webcam_counts = cursor.fetchone() or {}
    finally:
        cursor.close()
        conn.close()

    return _webcam_summary_from_rows(event_rows, {
        "no_face_count": webcam_counts.get("no_face_count") or 0,
        "multiple_faces_count": webcam_counts.get("multiple_faces_count") or 0,
        "looking_away_count": webcam_counts.get("looking_away_count") or 0,
    })


def get_proctor_webcam_summary_by_user_assessment(user_id: int, assessment_id) -> dict:
    """Same shape as get_proctor_webcam_summary(), aggregated across every
    proctoring session this user has had for the given assessment — see
    get_proctor_summary_by_user_assessment() for why this exists."""
    if not assessment_id:
        return {"webcam": None, "no_face_count": 0, "multiple_faces_count": 0, "looking_away_count": 0}

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
        event_rows = cursor.fetchall() or []

        cursor.execute(
            """
            SELECT
                SUM(no_face)        AS no_face_count,
                SUM(multiple_faces) AS multiple_faces_count,
                SUM(looking_away)   AS looking_away_count
            FROM quiz_proctor_webcam_frames
            WHERE user_id = %s AND assessment_id = %s
            """,
            (user_id, assessment_id),
        )
        webcam_counts = cursor.fetchone() or {}
    finally:
        cursor.close()
        conn.close()

    return _webcam_summary_from_rows(event_rows, {
        "no_face_count": webcam_counts.get("no_face_count") or 0,
        "multiple_faces_count": webcam_counts.get("multiple_faces_count") or 0,
        "looking_away_count": webcam_counts.get("looking_away_count") or 0,
    })


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


def get_proctor_webcam_frames(session_id: str, limit: int = 200) -> list[dict]:
    """Return captured webcam frames (with analysis flags) for one
    proctoring session, newest first."""
    if not session_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path, face_count, no_face, multiple_faces,
                   looking_away, yaw_deg, pitch_deg, captured_at
            FROM quiz_proctor_webcam_frames
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


def get_proctor_webcam_frames_by_user_assessment(user_id: int, assessment_id, limit: int = 200) -> list[dict]:
    """Same as get_proctor_webcam_frames(), aggregated across every
    proctoring session this user has had for the given assessment — see
    get_proctor_summary_by_user_assessment() for why this exists."""
    if not assessment_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path, face_count, no_face, multiple_faces,
                   looking_away, yaw_deg, pitch_deg, captured_at
            FROM quiz_proctor_webcam_frames
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


def get_proctor_keystrokes(session_id: str, limit: int = 200) -> list[dict]:
    """
    Return captured keystroke batches for one proctoring session, oldest
    first, with each row's keys_json decoded back into a list of
    {"key", "ctrl", "shift", "alt", "meta", "t"} dicts.
    """
    if not session_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT keys_json, captured_at
            FROM quiz_proctor_keystrokes
            WHERE session_id = %s
            ORDER BY captured_at ASC
            LIMIT %s
            """,
            (session_id, limit),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()

    return _decode_keystroke_rows(rows)


def get_proctor_keystrokes_by_user_assessment(user_id: int, assessment_id, limit: int = 200) -> list[dict]:
    """
    Same as get_proctor_keystrokes(), aggregated across every proctoring
    session this user has had for the given assessment — see
    get_proctor_summary_by_user_assessment() for why this exists.
    """
    if not assessment_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT keys_json, captured_at
            FROM quiz_proctor_keystrokes
            WHERE user_id = %s AND assessment_id = %s
            ORDER BY captured_at ASC
            LIMIT %s
            """,
            (user_id, assessment_id, limit),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()

    return _decode_keystroke_rows(rows)


def _decode_keystroke_rows(rows: list[dict]) -> list[dict]:
    """Flatten a list of {"keys_json", "captured_at"} batch rows into one
    list of individual keystroke dicts, dropping any batch that fails to
    decode rather than failing the whole review page."""
    keystrokes = []
    for row in rows:
        try:
            keystrokes.extend(json.loads(row["keys_json"]))
        except Exception:
            continue
    return keystrokes


_KEY_NAME_OVERRIDES = {" ": "Space"}


def format_keystrokes_for_display(keystrokes: list[dict]) -> str:
    """
    Render a flat list of keystroke dicts (as returned by
    get_proctor_keystrokes()/get_proctor_keystrokes_by_user_assessment()) as
    one space-separated line of key names for instructor review, e.g.
    "h e l l o Ctrl+c Ctrl+v Enter". Held modifiers are folded into a
    "Mod+key" label rather than shown as separate keydown events, since the
    modifier key's own keydown (e.g. "Control") is otherwise indistinguishable
    noise next to the key it was held with.
    """
    parts = []
    for entry in keystrokes:
        key = entry.get("key", "")
        if key in ("Control", "Shift", "Alt", "Meta"):
            continue
        label = _KEY_NAME_OVERRIDES.get(key, key)
        mods = [
            mod for mod, held in (
                ("Ctrl", entry.get("ctrl")),
                ("Alt", entry.get("alt")),
                ("Meta", entry.get("meta")),
                ("Shift", entry.get("shift")),
            )
            if held
        ]
        parts.append("+".join(mods + [label]) if mods else label)
    return " ".join(parts)


def delete_proctor_session(session_id: str) -> dict:
    """
    Permanently delete every event, frame (including its image file on
    disk), and keystroke batch recorded under one proctoring session_id.

    Lets an instructor discard the monitoring data for a single quiz
    attempt from the review UI, as opposed to cleanup_old_proctor_data()'s
    age-based bulk purge. The practice_quiz_attempts row that referenced
    this session_id is left in place — the attempt itself isn't deleted,
    only the monitoring data attached to it; get_proctor_summary() and
    get_proctor_frames()/get_proctor_webcam_frames()/get_proctor_keystrokes()
    simply return empty results for this session_id afterwards.

    Returns {"events_deleted": int, "frames_deleted": int,
    "webcam_frames_deleted": int, "files_removed": int,
    "keystrokes_deleted": int}.
    """
    empty = {
        "events_deleted": 0, "frames_deleted": 0, "webcam_frames_deleted": 0,
        "files_removed": 0, "keystrokes_deleted": 0,
    }
    if not session_id:
        return empty

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT file_path FROM quiz_proctor_frames WHERE session_id = %s",
            (session_id,),
        )
        frames = cursor.fetchall() or []

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_webcam_frames WHERE session_id = %s",
            (session_id,),
        )
        webcam_frames = cursor.fetchall() or []
    finally:
        cursor.close()

    files_removed = 0
    for row in frames + webcam_frames:
        try:
            path = Path(row["file_path"])
            if path.exists():
                path.unlink()
                files_removed += 1
        except Exception:
            pass

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM quiz_proctor_frames WHERE session_id = %s", (session_id,))
        frames_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_webcam_frames WHERE session_id = %s", (session_id,))
        webcam_frames_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_events WHERE session_id = %s", (session_id,))
        events_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_keystrokes WHERE session_id = %s", (session_id,))
        keystrokes_deleted = cursor.rowcount

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "events_deleted": events_deleted,
        "frames_deleted": frames_deleted,
        "webcam_frames_deleted": webcam_frames_deleted,
        "files_removed": files_removed,
        "keystrokes_deleted": keystrokes_deleted,
    }


def delete_proctor_data_for_user_assessment(user_id: int, assessment_id) -> dict:
    """
    Permanently delete every event, frame (including its image file on
    disk), and keystroke batch recorded for one student across every
    proctoring session tied to one assessment.

    Used by the Exam Grading "Submit My Exam" review, where individual
    uploaded files aren't pinned to a single session_id in the first place
    (see get_proctor_summary_by_user_assessment() for why — a student may
    have re-opened the upload page, and so started a new monitoring
    session, more than once before finally submitting). That means this is
    the finest-grained delete available there: "this student's entire
    proctoring history for this assessment," not a single attempt.

    Returns {"events_deleted": int, "frames_deleted": int,
    "webcam_frames_deleted": int, "files_removed": int,
    "keystrokes_deleted": int}.
    """
    empty = {
        "events_deleted": 0, "frames_deleted": 0, "webcam_frames_deleted": 0,
        "files_removed": 0, "keystrokes_deleted": 0,
    }
    if not assessment_id:
        return empty

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT file_path FROM quiz_proctor_frames WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        frames = cursor.fetchall() or []

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_webcam_frames WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        webcam_frames = cursor.fetchall() or []
    finally:
        cursor.close()

    files_removed = 0
    for row in frames + webcam_frames:
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
            "DELETE FROM quiz_proctor_frames WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        frames_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM quiz_proctor_webcam_frames WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        webcam_frames_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM quiz_proctor_events WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        events_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM quiz_proctor_keystrokes WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        keystrokes_deleted = cursor.rowcount

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "events_deleted": events_deleted,
        "frames_deleted": frames_deleted,
        "webcam_frames_deleted": webcam_frames_deleted,
        "files_removed": files_removed,
        "keystrokes_deleted": keystrokes_deleted,
    }


def cleanup_old_proctor_data(retention_days: int = 7) -> dict:
    """
    Permanently delete proctoring events, screen-capture frames, webcam
    frames, and keystroke batches older than retention_days, removing each
    frame's image file from disk before its quiz_proctor_frames /
    quiz_proctor_webcam_frames row is deleted.

    This data is meant to be short-lived (see module docstring) — anything
    still within the retention window is left untouched; everything older is
    purged outright, with no soft-delete or archive step. Intended to be
    triggered on demand (e.g. the Admin Panel Maintenance tab) or from an
    external scheduler calling this function directly; nothing in this app
    calls it automatically.

    Returns {"events_deleted": int, "frames_deleted": int,
    "webcam_frames_deleted": int, "files_removed": int,
    "keystrokes_deleted": int}. files_removed may be lower than
    frames_deleted + webcam_frames_deleted if some files were already missing
    from disk (e.g. removed manually) — that is not an error here.
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

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_webcam_frames "
            "WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        old_webcam_frames = cursor.fetchall() or []
    finally:
        cursor.close()

    files_removed = 0
    for row in old_frames + old_webcam_frames:
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
            "DELETE FROM quiz_proctor_webcam_frames WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        webcam_frames_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM quiz_proctor_events WHERE created_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        events_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM quiz_proctor_keystrokes WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        keystrokes_deleted = cursor.rowcount

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {
        "events_deleted": events_deleted,
        "frames_deleted": frames_deleted,
        "webcam_frames_deleted": webcam_frames_deleted,
        "files_removed": files_removed,
        "keystrokes_deleted": keystrokes_deleted,
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
    webcam_key = f"proctor_webcam_status_{gate_key}"

    if share_key not in st.session_state:
        st.info(
            "This quiz is monitored for academic integrity. Tab switches, "
            "window focus changes, and keys you press on this page are "
            "recorded automatically. You'll also be asked to share your "
            "screen and enable your camera below — your browser will show "
            "its own permission dialog for each. Once granted, periodic "
            "snapshots of your screen and your face are saved for "
            "instructor review; the webcam snapshots are also checked for "
            "your face being absent, more than one face in frame, or "
            "looking away from the screen for an extended period."
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

    # Same always-mounted pattern as the screen-share button above, for the
    # webcam permission prompt and its periodic frame captures.
    webcam_result = _webcam_monitor_button(
        key=f"proctor_webcam_{session_id}",
        on_webcam_change=lambda: None,
        on_frame_change=lambda: None,
    )

    if webcam_result.webcam is not None and webcam_key not in st.session_state:
        outcome = webcam_result.webcam
        granted = bool(outcome.get("granted"))
        st.session_state[webcam_key] = "granted" if granted else "denied"
        save_proctor_event(
            session_id, user_id, quiz_id, assessment_id,
            "webcam_granted" if granted else "webcam_denied",
        )

    if webcam_result.frame is not None:
        save_proctor_webcam_frame(session_id, user_id, quiz_id, assessment_id, webcam_result.frame.get("data"))

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

    # ---- Always-on keystroke logger ----
    # Mounted on every rerun, same as the tab monitor — it must stay mounted
    # to keep receiving periodic "keystrokes" batches for as long as the quiz
    # page is open.
    keystroke_result = _keystroke_monitor(
        key=f"proctor_keystrokes_{session_id}",
        on_keystrokes_change=lambda: None,
    )
    if keystroke_result.keystrokes is not None:
        save_proctor_keystrokes(
            session_id, user_id, quiz_id, assessment_id,
            keystroke_result.keystrokes.get("keys", []),
        )

    # Webcam face/gaze flags (no_face/multiple_faces/looking_away) are
    # intentionally not surfaced here or as a live st.warning() the way
    # tab-switch/focus-loss is above — a single misread frame is too noisy a
    # signal to interrupt a student over, so they're only ever visible to an
    # instructor reviewing this session afterwards (see get_proctor_webcam_summary()).
    if st.session_state[count_key]:
        st.caption(
            f"🔴 Monitoring active — {st.session_state[count_key]} "
            "tab-switch/focus warning(s) recorded this session."
        )
    else:
        st.caption(
            "🟢 Monitoring active — tab switches, focus loss, keystrokes, "
            "and (once enabled) your camera are being recorded."
        )

    return session_id
