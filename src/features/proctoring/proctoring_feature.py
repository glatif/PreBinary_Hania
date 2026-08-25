# =============================================================================
# proctoring_feature.py
# =============================================================================
# Lightweight, always-on tab-switch / window-focus-loss monitoring,
# keystroke logging, and mouse-activity logging, plus optional screen-share,
# webcam, and microphone permission prompts
# that — once granted — periodically capture a downscaled JPEG snapshot of
# the shared screen / the student's face, continuously record a downscaled
# ("480p") video of each (the webcam recording carries the microphone's
# audio track), and continuously listen for human speech, saving all of it
# to disk, for the active quiz attempt that begins immediately after a
# student clears the identity verification gate (see
# exam_verification_feature.py).
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
#     frames/video) are logged for instructor review.
#   - There is no media server in this app, so continuous video recording is
#     built the same way the still frames and microphone segments already
#     are: MediaRecorder records fixed-length segments off the same
#     getDisplayMedia/getUserMedia stream already granted for the still
#     frames (no extra permission prompt beyond a second, separate
#     getUserMedia({audio:true}) call for the webcam recording's audio
#     track, so a denied/missing mic degrades to a silent webcam video
#     rather than losing the video entirely), each uploaded as its own
#     base64 chunk via setTriggerValue() the same channel used for
#     tab-switch events, and stitched into one playable video per session on
#     demand by get_or_build_proctor_video() (ffmpeg concat, cached by
#     segment count). See VIDEO_SEGMENT_INTERVAL_MS /
#     MAX_VIDEO_SEGMENTS_PER_SESSION / VIDEO_QUALITY_PRESETS below.
#
# Capture cadence is intentionally conservative to keep storage and bandwidth
# bounded: one frame every CAPTURE_INTERVAL_MS (screen) /
# CAMERA_CAPTURE_INTERVAL_MS (webcam), downscaled to at most
# MAX_FRAME_DIMENSION_PX / MAX_CAMERA_FRAME_DIMENSION_PX px on the long edge,
# capped at MAX_FRAMES_PER_SESSION / MAX_CAMERA_FRAMES_PER_SESSION total
# frames per session. Tune the constants below if you need a different
# tradeoff.
#
# Each webcam frame is eventually run through analyze_webcam_frame():
# mediapipe's FaceMesh detects how many faces are in frame (flagging
# no_face/multiple_faces), and when exactly one face is found, a solvePnP
# head-pose estimate over that face's landmarks yields a yaw/pitch angle used
# to flag looking_away. This analysis is NOT run at capture time — it's real
# per-frame CPU work (mediapipe inference) that would otherwise compete with
# the live parts of a proctored session, so save_proctor_webcam_frame() only
# writes the raw frame with analysis_status = 'pending', and
# process_pending_proctor_webcam_frames() fills in the real flags afterward
# (see that function, and the Admin Panel's "Run Proctoring Analysis"
# button). Once analyzed, these are logged silently alongside the frame for
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
# Mouse activity follows the exact same buffered-batch pattern as keystrokes
# (MOUSE_FLUSH_INTERVAL_MS / MAX_MOUSE_EVENTS_PER_BATCH), capturing clicks
# one-for-one plus throttled movement samples (at most one every
# MOUSE_MOVE_SAMPLE_MS — raw mousemove fires far too often to log every
# event) and cursor leave/re-enter of the browser window.
#
# The microphone works differently from the screen/webcam snapshots: once
# granted, the mic stays continuously live for the whole session (no polling
# gaps) — it's still recorded in fixed-length segments
# (AUDIO_SEGMENT_INTERVAL_MS), but only so each segment is a complete,
# decodable audio file to analyze, not to save battery/bandwidth the way the
# still-frame interval does. Every segment is saved to disk with
# analysis_status = 'pending' as soon as it's recorded — analyze_audio_clip()
# (ffmpeg decode + a Silero VAD voice-activity model) is deliberately NOT run
# at capture time, for the same CPU-contention reason described above for
# webcam frames, and instead runs later in
# process_pending_proctor_audio_clips(). That's also where the "keep only
# speech" decision now happens: segments with no detected speech are deleted
# (row + file) at that point instead of being discarded immediately after
# capture, so once processed, quiz_proctor_audio_clips is still a record of
# "when speech was heard," not a full audio timeline — just filled in later
# rather than in real time.
#
# Implementation note: this uses st.components.v2.component(), which mounts
# inline JS directly into the app's own DOM (no iframe), so document/window
# in the JS below refer to the real top-level page.
#
# All events, frames, keystroke/mouse batches, audio clips, and video
# segments are written to quiz_proctor_events / quiz_proctor_frames /
# quiz_proctor_webcam_frames / quiz_proctor_keystrokes /
# quiz_proctor_mouse_events / quiz_proctor_audio_clips /
# quiz_proctor_video_segments, keyed by a per-attempt session_id (a UUID
# minted the first time the monitor renders for a given quiz gate). The same
# session_id is stamped onto the practice_quiz_attempts row at submission
# time (quiz_generator_feature.py) so instructors can review the two
# together. Frame/clip/segment files are written to disk under
# uploads/proctor_frames/ (screen), uploads/proctor_webcam_frames/
# (webcam), uploads/proctor_audio_clips/ (every captured audio segment,
# until process_pending_proctor_audio_clips() deletes the ones with no
# detected speech), and uploads/proctor_video_segments/{screen,webcam}/ (raw
# video segments) — see save_proctor_frame()/save_proctor_webcam_frame()/
# save_proctor_audio_clip()/save_proctor_video_segment(). Stitched final
# videos live separately under uploads/proctor_video_final/, built on demand
# by get_or_build_proctor_video() rather than at capture time. The
# webcam/audio analysis itself is likewise deferred — see
# process_pending_proctor_webcam_frames()/process_pending_proctor_audio_clips()
# below the capture functions.
#
# This data is meant to be short-lived: cleanup_old_proctor_data() deletes
# events/frames/keystrokes/mouse-events/audio-clips/video-segments (and
# their files, plus any stitched final video, on disk) past a retention
# window,
# and is exposed as an on-demand "Run Proctoring Data Cleanup" button in the
# Admin Panel's Maintenance tab (app.py) rather than running on its own — this
# app has no background worker/cron, so nothing deletes data unless an admin
# (or an external scheduler calling the same function) actually triggers it.
# =============================================================================

import base64
import json
import threading
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

# ---- Mouse-activity batch cadence/limits — tune to taste ----
# Clicks are captured one-for-one, the same as keydowns above. Raw mousemove
# fires far too often to log every event, so movement is sampled at most once
# per MOUSE_MOVE_SAMPLE_MS — enough to reconstruct general activity level/
# idle gaps without flooding the batch.
MOUSE_FLUSH_INTERVAL_MS    = 15_000   # flush the buffered mouse events every 15 seconds
MAX_MOUSE_EVENTS_PER_BATCH = 500      # flush early if the buffer hits this size
MOUSE_MOVE_SAMPLE_MS       = 250      # minimum gap between recorded "move" samples

# ---- Webcam-capture cadence/limits — tune to taste ----
CAMERA_CAPTURE_INTERVAL_MS    = 20_000   # one frame every 20 seconds
MAX_CAMERA_FRAME_DIMENSION_PX = 480      # smaller than screen frames — just needs to be big enough for face detection
CAMERA_JPEG_QUALITY            = 0.6
MAX_CAMERA_FRAMES_PER_SESSION  = 120     # hard cap (~40 minutes at the interval above)

# ---- "Looking away" thresholds — tune to taste ----
# Two independent signals feed looking_away (see analyze_webcam_frame()):
#
# Head pose (yaw/pitch, degrees) from solvePnP against an uncalibrated,
# approximate camera matrix (focal_length = image width — there is no real
# per-device calibration available). That approximation systematically
# *underestimates* real rotation: in testing, a face turned/tilted enough to
# clearly be looking at a phone in the lap for 15+ seconds only produced
# ~8-10 degrees of estimated yaw/pitch — well under a 30/25 threshold, which
# is why it originally failed to flag anything. Thresholds below are lowered
# accordingly, but treat this signal as a coarse secondary check, not a
# precise angle.
#
# Gaze offset (see _estimate_gaze_offset()) measures how far the iris has
# drifted from the center of the eye socket, as a ratio of eye width/height.
# This is scale- and calibration-free (a ratio within the same eye, not an
# absolute angle), so it doesn't share the head-pose signal's underestimation
# problem, and it also catches glances where the head barely moves but the
# eyes do — the primary signal; head pose is the fallback for cases where iris
# landmarks are unreliable (glasses glare, partial occlusion).
LOOKING_AWAY_YAW_THRESHOLD_DEG   = 18
LOOKING_AWAY_PITCH_THRESHOLD_DEG = 15
GAZE_OFFSET_THRESHOLD            = 0.20

# ---- Audio-capture cadence/limits — tune to taste ----
# The microphone itself is granted once and stays live for the whole
# session (see _AUDIO_MONITOR_JS) — unlike the screen/webcam snapshots
# above, there's no polling gap where nothing is being heard. It's still
# recorded in fixed-length segments, purely because each segment needs to be
# a complete, decodable audio file to run through analyze_audio_clip().
AUDIO_SEGMENT_INTERVAL_MS       = 10_000  # length of each analyzable segment
MAX_AUDIO_SEGMENTS_PER_SESSION  = 240     # hard cap (~40 minutes at the interval above)

# Speech segments shorter than this (a cough, a chair creak misclassified by
# the VAD model) are ignored when deciding whether a clip contains speech —
# see analyze_audio_clip().
MIN_SPEECH_DURATION_SEC = 0.3

# ---- Video-recording cadence/limits — tune to taste ----
# Continuous screen and webcam video, recorded off the same
# getDisplayMedia/getUserMedia streams already granted for the still-frame
# capture above (see _SCREEN_SHARE_JS/_WEBCAM_MONITOR_JS) — no extra
# permission prompt. Recorded in fixed-length segments for the same reason
# audio is: a single long-running MediaRecorder only produces a decodable
# file from its first chunk, so each segment tears down and recreates the
# recorder, the same trick _AUDIO_MONITOR_JS uses. Segments are stitched
# into one final video per session on demand — see
# get_or_build_proctor_video().
VIDEO_SEGMENT_INTERVAL_MS      = 30_000  # length of each recorded segment
MAX_VIDEO_SEGMENTS_PER_SESSION = 240     # hard cap (~2 hours at the interval above)
VIDEO_CAPTURE_FPS              = 15      # frames/sec drawn onto the recording canvas

# Resolution ("long edge" downscale target) + bitrate are admin-configurable
# (Admin Panel -> Maintenance -> Video Recording Quality), stored in the
# single-row proctor_settings table (see get_proctor_video_quality()/
# set_proctor_video_quality() below) rather than fixed constants. The chosen
# tier is looked up once per render_proctor_monitor() call and handed to the
# _SCREEN_SHARE_JS/_WEBCAM_MONITOR_JS components via their `data` prop, so a
# tier change takes effect for the next proctoring session that starts, not
# retroactively for one already recording. "medium" reproduces the original
# fixed values this used to be hardcoded to ("480p"/400kbps).
VIDEO_QUALITY_PRESETS = {
    "low":    {"max_dimension_px": 360, "bits_per_second": 250_000},
    "medium": {"max_dimension_px": 480, "bits_per_second": 400_000},
    "high":   {"max_dimension_px": 720, "bits_per_second": 800_000},
}
DEFAULT_VIDEO_QUALITY = "medium"

# ---- Combined (screen + webcam-PiP + audio) review recording ----
# get_or_build_combined_proctor_video() composites the already-stitched
# screen and webcam recordings above into one file via ffmpeg — not
# captured directly, so these only control the compositing, not capture.
COMBINED_PIP_SCALE     = 0.28  # webcam PiP width, as a fraction of the screen recording's width
COMBINED_PIP_MARGIN_PX = 12    # gap (px) between the PiP overlay and the screen recording's edges

_PROCTOR_FRAMES_DIR         = Path("uploads") / "proctor_frames"
_PROCTOR_WEBCAM_FRAMES_DIR  = Path("uploads") / "proctor_webcam_frames"
_PROCTOR_AUDIO_CLIPS_DIR    = Path("uploads") / "proctor_audio_clips"
_PROCTOR_VIDEO_SEGMENTS_DIR = Path("uploads") / "proctor_video_segments"
_PROCTOR_VIDEO_FINAL_DIR    = Path("uploads") / "proctor_video_final"

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

_MOUSE_JS = f"""
export default function(component) {{
    const {{ setTriggerValue }} = component;

    const FLUSH_INTERVAL_MS = {MOUSE_FLUSH_INTERVAL_MS};
    const MAX_EVENTS_PER_BATCH = {MAX_MOUSE_EVENTS_PER_BATCH};
    const MOVE_SAMPLE_MS = {MOUSE_MOVE_SAMPLE_MS};

    let buffer = [];
    let lastMoveT = 0;

    const flush = () => {{
        if (buffer.length === 0) return;
        const batch = buffer;
        buffer = [];
        setTriggerValue("mouse_events", {{ events: batch }});
    }};

    const push = (entry) => {{
        buffer.push(entry);
        if (buffer.length >= MAX_EVENTS_PER_BATCH) flush();
    }};

    const BUTTON_NAMES = {{ 0: "left", 1: "middle", 2: "right" }};

    const onMouseMove = (e) => {{
        const now = Date.now();
        if (now - lastMoveT < MOVE_SAMPLE_MS) return;
        lastMoveT = now;
        push({{ type: "move", x: e.clientX, y: e.clientY, t: now }});
    }};

    const onMouseDown = (e) => {{
        push({{
            type: "click",
            button: BUTTON_NAMES[e.button] ?? "other",
            x: e.clientX,
            y: e.clientY,
            t: Date.now(),
        }});
    }};

    const onMouseLeave = () => push({{ type: "leave_window", t: Date.now() }});
    const onMouseEnter = () => push({{ type: "enter_window", t: Date.now() }});

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("mouseleave", onMouseLeave);
    document.addEventListener("mouseenter", onMouseEnter);
    const intervalHandle = setInterval(flush, FLUSH_INTERVAL_MS);

    return () => {{
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mousedown", onMouseDown);
        document.removeEventListener("mouseleave", onMouseLeave);
        document.removeEventListener("mouseenter", onMouseEnter);
        clearInterval(intervalHandle);
    }};
}}
"""

_SCREEN_SHARE_JS = f"""
export default function(component) {{
    const {{ setTriggerValue, parentElement, data }} = component;

    const CAPTURE_INTERVAL_MS    = {CAPTURE_INTERVAL_MS};
    const MAX_FRAME_DIMENSION_PX = {MAX_FRAME_DIMENSION_PX};
    const JPEG_QUALITY            = {JPEG_QUALITY};
    const MAX_FRAMES              = {MAX_FRAMES_PER_SESSION};

    // Resolution/bitrate come from the admin-configurable quality tier (see
    // VIDEO_QUALITY_PRESETS in proctoring_feature.py), passed in via `data`
    // on every render_proctor_monitor() call. The literal fallbacks below
    // (the "medium" preset) only matter if this ever mounts before `data`
    // is populated.
    const VIDEO_SEGMENT_INTERVAL_MS = {VIDEO_SEGMENT_INTERVAL_MS};
    const MAX_VIDEO_SEGMENTS        = {MAX_VIDEO_SEGMENTS_PER_SESSION};
    const VIDEO_MAX_DIMENSION_PX    = (data && data.video_max_dimension_px) || {VIDEO_QUALITY_PRESETS[DEFAULT_VIDEO_QUALITY]["max_dimension_px"]};
    const VIDEO_CAPTURE_FPS         = {VIDEO_CAPTURE_FPS};
    const VIDEO_BITS_PER_SECOND     = (data && data.video_bits_per_second) || {VIDEO_QUALITY_PRESETS[DEFAULT_VIDEO_QUALITY]["bits_per_second"]};
    const VIDEO_MIME_CANDIDATES     = ["video/webm;codecs=vp8", "video/webm;codecs=vp9", "video/webm"];

    const btn = document.createElement("button");
    btn.textContent = "Enable Screen Monitoring";
    btn.style.cssText =
        "padding:0.5em 1.1em;font-size:0.95rem;cursor:pointer;border-radius:6px;" +
        "border:1px solid #cc0000;background:#ffecec;color:#900;";

    // Hoisted so the component-unmount cleanup below can stop an in-flight
    // recording even if the stream's "ended" event never fires (e.g. the
    // quiz page navigates away while still sharing).
    let recDrawHandle = null;
    let videoStopped = true;

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

            // ---- Continuous downscaled screen-recording, off the same stream ----
            // A second, independent canvas (sized for VIDEO_MAX_DIMENSION_PX
            // rather than MAX_FRAME_DIMENSION_PX) is continuously redrawn and fed
            // to MediaRecorder via canvas.captureStream() — recording directly
            // from the raw display-media track can't be reliably downscaled
            // cross-browser. Recorded in fixed-length segments for the same
            // reason _AUDIO_MONITOR_JS is: a single long-running MediaRecorder
            // only produces a decodable file from its first chunk, so each
            // segment tears down and recreates the recorder. Wrapped in its
            // own try/catch (distinct from the outer one) so a failure here
            // degrades to "no video recording" rather than being mistaken
            // for the whole screen-share permission being denied — the
            // still-frame capture above must keep working either way.
            try {{
                const recCanvas = document.createElement("canvas");
                const recCtx = recCanvas.getContext("2d");
                let videoSegmentCount = 0;
                videoStopped = false;
                const videoMimeType = VIDEO_MIME_CANDIDATES.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";

                const drawRecFrame = () => {{
                    const vw = videoEl.videoWidth;
                    const vh = videoEl.videoHeight;
                    if (!vw || !vh) return;
                    const scale = Math.min(1, VIDEO_MAX_DIMENSION_PX / Math.max(vw, vh));
                    const w = Math.max(1, Math.round(vw * scale));
                    const h = Math.max(1, Math.round(vh * scale));
                    if (recCanvas.width !== w) recCanvas.width = w;
                    if (recCanvas.height !== h) recCanvas.height = h;
                    recCtx.drawImage(videoEl, 0, 0, w, h);
                }};

                if (window.MediaRecorder) {{
                    recDrawHandle = setInterval(drawRecFrame, Math.round(1000 / VIDEO_CAPTURE_FPS));
                    const recStream = recCanvas.captureStream(VIDEO_CAPTURE_FPS);

                    const recordSegment = () => {{
                        if (videoStopped || videoSegmentCount >= MAX_VIDEO_SEGMENTS) return;

                        const opts = {{ videoBitsPerSecond: VIDEO_BITS_PER_SECOND }};
                        if (videoMimeType) opts.mimeType = videoMimeType;
                        const recorder = new MediaRecorder(recStream, opts);
                        const chunks = [];
                        recorder.ondataavailable = (e) => {{ if (e.data && e.data.size > 0) chunks.push(e.data); }};
                        recorder.onstop = () => {{
                            videoSegmentCount += 1;
                            const blob = new Blob(chunks, {{ type: videoMimeType || "video/webm" }});
                            const reader = new FileReader();
                            reader.onloadend = () => {{
                                setTriggerValue("video_chunk", {{ kind: "screen", data: reader.result, seq: videoSegmentCount }});
                            }};
                            reader.readAsDataURL(blob);

                            if (!videoStopped && videoSegmentCount < MAX_VIDEO_SEGMENTS) recordSegment();
                        }};
                        recorder.start();
                        setTimeout(() => {{ if (recorder.state !== "inactive") recorder.stop(); }}, VIDEO_SEGMENT_INTERVAL_MS);
                    }};
                    recordSegment();
                }}
            }} catch (recErr) {{
                if (recDrawHandle) clearInterval(recDrawHandle);
                videoStopped = true;
            }}

            stream.getVideoTracks()[0].addEventListener("ended", () => {{
                if (intervalHandle) clearInterval(intervalHandle);
                if (recDrawHandle) clearInterval(recDrawHandle);
                videoStopped = true;
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
    return () => {{
        videoStopped = true;
        if (recDrawHandle) clearInterval(recDrawHandle);
        parentElement.removeChild(btn);
    }};
}}
"""

_WEBCAM_MONITOR_JS = f"""
export default function(component) {{
    const {{ setTriggerValue, parentElement, data }} = component;

    const CAPTURE_INTERVAL_MS    = {CAMERA_CAPTURE_INTERVAL_MS};
    const MAX_FRAME_DIMENSION_PX = {MAX_CAMERA_FRAME_DIMENSION_PX};
    const JPEG_QUALITY            = {CAMERA_JPEG_QUALITY};
    const MAX_FRAMES              = {MAX_CAMERA_FRAMES_PER_SESSION};

    // See _SCREEN_SHARE_JS for why these come from `data` instead of being
    // fixed constants.
    const VIDEO_SEGMENT_INTERVAL_MS = {VIDEO_SEGMENT_INTERVAL_MS};
    const MAX_VIDEO_SEGMENTS        = {MAX_VIDEO_SEGMENTS_PER_SESSION};
    const VIDEO_MAX_DIMENSION_PX    = (data && data.video_max_dimension_px) || {VIDEO_QUALITY_PRESETS[DEFAULT_VIDEO_QUALITY]["max_dimension_px"]};
    const VIDEO_CAPTURE_FPS         = {VIDEO_CAPTURE_FPS};
    const VIDEO_BITS_PER_SECOND     = (data && data.video_bits_per_second) || {VIDEO_QUALITY_PRESETS[DEFAULT_VIDEO_QUALITY]["bits_per_second"]};

    const btn = document.createElement("button");
    btn.textContent = "Enable Camera Monitoring";
    btn.style.cssText =
        "padding:0.5em 1.1em;font-size:0.95rem;cursor:pointer;border-radius:6px;" +
        "border:1px solid #cc0000;background:#ffecec;color:#900;margin-left:0.5em;";

    // Hoisted so the component-unmount cleanup below can stop an in-flight
    // recording even if the stream's "ended" event never fires.
    let recDrawHandle = null;
    let videoStopped = true;

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

            // ---- Continuous downscaled webcam recording, off the same stream ----
            // Same canvas-relay + fixed-length-segment approach as
            // _SCREEN_SHARE_JS's recorder. The microphone is requested
            // separately (rather than via {{video:true, audio:true}} on the
            // getUserMedia call above) so that a student who denies/lacks a
            // microphone still gets webcam monitoring + video, just without an
            // audio track — denying/lacking a mic must not break the camera
            // the way a single combined request could. Wrapped in its own
            // try/catch (distinct from the outer one) so a failure here
            // degrades to "no video recording" rather than being mistaken
            // for the whole webcam permission being denied — still frames
            // and gaze analysis must keep working either way.
            try {{
                const recCanvas = document.createElement("canvas");
                const recCtx = recCanvas.getContext("2d");
                let videoSegmentCount = 0;
                videoStopped = false;

                const drawRecFrame = () => {{
                    const vw = videoEl.videoWidth;
                    const vh = videoEl.videoHeight;
                    if (!vw || !vh) return;
                    const scale = Math.min(1, VIDEO_MAX_DIMENSION_PX / Math.max(vw, vh));
                    const w = Math.max(1, Math.round(vw * scale));
                    const h = Math.max(1, Math.round(vh * scale));
                    if (recCanvas.width !== w) recCanvas.width = w;
                    if (recCanvas.height !== h) recCanvas.height = h;
                    recCtx.drawImage(videoEl, 0, 0, w, h);
                }};

                if (window.MediaRecorder) {{
                    let audioTrack = null;
                    try {{
                        const audioStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
                        audioTrack = audioStream.getAudioTracks()[0] || null;
                    }} catch (audioErr) {{
                        audioTrack = null;
                    }}

                    // Codec candidates depend on whether an audio track ended
                    // up in the recorded stream — requesting an opus codec
                    // for a stream with no audio track is invalid in some
                    // browsers and can throw when constructing MediaRecorder.
                    const mimeCandidates = audioTrack
                        ? ["video/webm;codecs=vp8,opus", "video/webm;codecs=vp9,opus", "video/webm"]
                        : ["video/webm;codecs=vp8", "video/webm;codecs=vp9", "video/webm"];
                    const videoMimeType = mimeCandidates.find((t) => MediaRecorder.isTypeSupported(t)) || "";

                    recDrawHandle = setInterval(drawRecFrame, Math.round(1000 / VIDEO_CAPTURE_FPS));
                    const recVideoTrack = recCanvas.captureStream(VIDEO_CAPTURE_FPS).getVideoTracks()[0];
                    const recStream = audioTrack
                        ? new MediaStream([recVideoTrack, audioTrack])
                        : new MediaStream([recVideoTrack]);

                    const recordSegment = () => {{
                        if (videoStopped || videoSegmentCount >= MAX_VIDEO_SEGMENTS) return;

                        const opts = {{ videoBitsPerSecond: VIDEO_BITS_PER_SECOND }};
                        if (videoMimeType) opts.mimeType = videoMimeType;
                        const recorder = new MediaRecorder(recStream, opts);
                        const chunks = [];
                        recorder.ondataavailable = (e) => {{ if (e.data && e.data.size > 0) chunks.push(e.data); }};
                        recorder.onstop = () => {{
                            videoSegmentCount += 1;
                            const blob = new Blob(chunks, {{ type: videoMimeType || "video/webm" }});
                            const reader = new FileReader();
                            reader.onloadend = () => {{
                                setTriggerValue("video_chunk", {{ kind: "webcam", data: reader.result, seq: videoSegmentCount }});
                            }};
                            reader.readAsDataURL(blob);

                            if (!videoStopped && videoSegmentCount < MAX_VIDEO_SEGMENTS) recordSegment();
                        }};
                        recorder.start();
                        setTimeout(() => {{ if (recorder.state !== "inactive") recorder.stop(); }}, VIDEO_SEGMENT_INTERVAL_MS);
                    }};
                    recordSegment();
                }}
            }} catch (recErr) {{
                if (recDrawHandle) clearInterval(recDrawHandle);
                videoStopped = true;
            }}

            stream.getVideoTracks()[0].addEventListener("ended", () => {{
                if (intervalHandle) clearInterval(intervalHandle);
                if (recDrawHandle) clearInterval(recDrawHandle);
                videoStopped = true;
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
    return () => {{
        videoStopped = true;
        if (recDrawHandle) clearInterval(recDrawHandle);
        parentElement.removeChild(btn);
    }};
}}
"""

_AUDIO_MONITOR_JS = f"""
export default function(component) {{
    const {{ setTriggerValue, parentElement }} = component;

    const SEGMENT_INTERVAL_MS = {AUDIO_SEGMENT_INTERVAL_MS};
    const MAX_SEGMENTS        = {MAX_AUDIO_SEGMENTS_PER_SESSION};
    const MIME_CANDIDATES     = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

    const btn = document.createElement("button");
    btn.textContent = "Enable Microphone Monitoring";
    btn.style.cssText =
        "padding:0.5em 1.1em;font-size:0.95rem;cursor:pointer;border-radius:6px;" +
        "border:1px solid #cc0000;background:#ffecec;color:#900;margin-left:0.5em;";

    btn.onclick = async () => {{
        btn.disabled = true;
        btn.textContent = "Requesting permission...";

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {{
            setTriggerValue("audio", {{ granted: false, reason: "unsupported" }});
            return;
        }}
        try {{
            const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
            const mimeType = MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) || "";

            let segmentCount = 0;
            let stopped = false;

            // The microphone track (and the browser's own recording indicator)
            // stays live for the whole session — only the MediaRecorder wrapping
            // it is torn down and recreated every SEGMENT_INTERVAL_MS, purely so
            // each segment is a complete, self-contained audio file: a single
            // MediaRecorder run with a `timeslice` instead emits a valid header
            // only in its first chunk, and later chunks aren't independently
            // decodable, which analyze_audio_clip() needs. The gap between one
            // recorder's stop() and the next one's start() is sub-frame JS
            // scheduling overhead, not a pause in listening.
            const recordSegment = () => {{
                if (stopped || segmentCount >= MAX_SEGMENTS) return;

                const recorder = mimeType ? new MediaRecorder(stream, {{ mimeType }}) : new MediaRecorder(stream);
                const chunks = [];
                recorder.ondataavailable = (e) => {{ if (e.data && e.data.size > 0) chunks.push(e.data); }};
                recorder.onstop = () => {{
                    segmentCount += 1;
                    const blob = new Blob(chunks, {{ type: mimeType || "audio/webm" }});
                    const reader = new FileReader();
                    reader.onloadend = () => {{
                        setTriggerValue("clip", {{ data: reader.result, seq: segmentCount }});
                    }};
                    reader.readAsDataURL(blob);

                    if (!stopped && segmentCount < MAX_SEGMENTS) recordSegment();
                }};
                recorder.start();
                setTimeout(() => {{ if (recorder.state !== "inactive") recorder.stop(); }}, SEGMENT_INTERVAL_MS);
            }};

            recordSegment();

            stream.getAudioTracks()[0].addEventListener("ended", () => {{
                stopped = true;
                btn.textContent = "Microphone monitoring stopped";
                setTriggerValue("audio", {{ granted: true, reason: "stopped" }});
            }});

            btn.textContent = "🔴 Microphone monitoring active";
            setTriggerValue("audio", {{ granted: true, reason: "active" }});
        }} catch (err) {{
            setTriggerValue("audio", {{ granted: false, reason: "denied" }});
            btn.disabled = false;
            btn.textContent = "Enable Microphone Monitoring";
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
_mouse_monitor        = st.components.v2.component("quiz_mouse_monitor", js=_MOUSE_JS)
_screen_share_button  = st.components.v2.component("quiz_screen_share_button", js=_SCREEN_SHARE_JS)
_webcam_monitor_button = st.components.v2.component("quiz_webcam_monitor_button", js=_WEBCAM_MONITOR_JS)
_audio_monitor_button  = st.components.v2.component("quiz_audio_monitor_button", js=_AUDIO_MONITOR_JS)


def get_proctor_video_quality() -> str:
    """
    Return the currently configured proctoring video-recording quality tier
    ("low" | "medium" | "high") from the single row in proctor_settings.

    Falls back to DEFAULT_VIDEO_QUALITY if the row is missing (e.g. the
    migration/schema hasn't been applied yet) rather than raising, since a
    missing setting should degrade to the original fixed behavior, not break
    proctoring.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT video_quality FROM proctor_settings WHERE id = 1")
        row = cursor.fetchone()
        return row[0] if row else DEFAULT_VIDEO_QUALITY
    except Exception:
        return DEFAULT_VIDEO_QUALITY
    finally:
        cursor.close()
        conn.close()


def set_proctor_video_quality(quality: str) -> None:
    """
    Persist the admin-selected proctoring video-recording quality tier.

    Only affects proctoring sessions whose screen/webcam recording starts
    after this call — see VIDEO_QUALITY_PRESETS above.
    """
    if quality not in VIDEO_QUALITY_PRESETS:
        raise ValueError(f"Unknown video quality tier: {quality!r}")
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO proctor_settings (id, video_quality) VALUES (1, %s)
            ON DUPLICATE KEY UPDATE video_quality = VALUES(video_quality)
            """,
            (quality,),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_record_webcam_video() -> bool:
    """
    Return whether the webcam camera stream (continuous video recording,
    periodic frame snapshots, and face/gaze analysis) should be captured at
    all during a proctored session. When False, only screen recording plus
    tab/keystroke/mouse monitoring run — the browser is never asked for
    camera permission. Microphone recording is independent of this setting.

    Falls back to True (today's always-on behavior) if the row/column is
    missing, e.g. the migration hasn't been applied yet.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT record_webcam_video FROM proctor_settings WHERE id = 1")
        row = cursor.fetchone()
        return bool(row[0]) if row else True
    except Exception:
        return True
    finally:
        cursor.close()
        conn.close()


def set_record_webcam_video(enabled: bool) -> None:
    """Persist the admin-selected webcam-recording on/off setting."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO proctor_settings (id, record_webcam_video) VALUES (1, %s)
            ON DUPLICATE KEY UPDATE record_webcam_video = VALUES(record_webcam_video)
            """,
            (int(enabled),),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_proctoring_admin_lock() -> bool:
    """
    Return whether instructors are allowed to enable proctoring at all for
    their own exams/quizzes/oral exams (allow_instructor_proctoring_toggle
    in app_settings). Falls back to True (today's behavior) if the row/
    column is missing, e.g. the migration hasn't been applied yet.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT allow_instructor_proctoring_toggle FROM app_settings WHERE id = 1")
        row = cursor.fetchone()
        return bool(row[0]) if row else True
    except Exception:
        return True
    finally:
        cursor.close()
        conn.close()


def set_proctoring_admin_lock(enabled: bool) -> None:
    """Persist whether instructors are allowed to enable proctoring at all."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO app_settings (id, allow_instructor_proctoring_toggle) VALUES (1, %s)
            ON DUPLICATE KEY UPDATE allow_instructor_proctoring_toggle = VALUES(allow_instructor_proctoring_toggle)
            """,
            (int(enabled),),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def effective_enable_proctoring(per_exam_enable_proctoring: bool) -> bool:
    """
    Resolve whether proctoring should actually run, combining the
    instructor's per-exam choice with the admin-level permission lock. An
    admin lock always wins — see get_proctoring_admin_lock() above.
    """
    return bool(per_exam_enable_proctoring) and get_proctoring_admin_lock()


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


def save_proctor_mouse_events(
    session_id: str,
    user_id: int,
    quiz_id,
    assessment_id,
    events: list,
) -> None:
    """
    Insert one batch of mouse events (as flushed by _MOUSE_JS — "move",
    "click", "leave_window", "enter_window" entries) into
    quiz_proctor_mouse_events as a single JSON-encoded row. Mirrors
    save_proctor_keystrokes(); silently does nothing for an empty batch.
    """
    if not events:
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO quiz_proctor_mouse_events
                (session_id, user_id, quiz_id, assessment_id, events_json)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, user_id, quiz_id, assessment_id, json.dumps(events)),
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
    # Split on the literal "base64," marker, not the first comma — a comma
    # can legitimately appear earlier, inside the MIME type itself (e.g. a
    # multi-codec "video/webm;codecs=vp8,opus" from a combined video+audio
    # recording), in which case splitting on the first comma leaves a
    # fragment of the MIME string glued onto the front of the "payload".
    # base64.b64decode() doesn't raise on that — it silently discards
    # non-base64 characters and decodes the rest anyway, byte-shifted and
    # corrupt, which only shows up much later as an undecodable file. This
    # capture path doesn't hit that today (JPEG data URLs have no codecs
    # list), but see save_proctor_video_segment() below, which did.
    if not data_url or "base64," not in data_url:
        return
    try:
        image_bytes = base64.b64decode(data_url.partition("base64,")[2])
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
    faces and facial landmarks in webcam frames. refine_landmarks=True adds
    the iris landmarks (indices 468-477) used by _estimate_gaze_offset()."""
    import mediapipe as mp
    return mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=3,
        refine_landmarks=True,
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


# solvePnP occasionally converges to a flipped/degenerate solution (observed
# in testing: yaw values around 167-175 degrees, which is not a physically
# plausible pose for a face FaceMesh still detected as front-facing) — a
# known failure mode of 6-point PnP when the landmarks are slightly noisy or
# nearly coplanar. Angles beyond this are treated as a failed estimate.
_HEAD_POSE_MAX_PLAUSIBLE_DEG = 90


def _estimate_head_pose(landmarks, image_w: int, image_h: int):
    """
    Estimate (yaw_deg, pitch_deg) from one face's FaceMesh landmarks via
    solvePnP against a generic 3D face model, using image dimensions to
    build an approximate camera matrix (no real camera calibration
    available). Returns (None, None) if solvePnP fails to converge, or if it
    converges to an implausible angle (see _HEAD_POSE_MAX_PLAUSIBLE_DEG).
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

    if abs(yaw) > _HEAD_POSE_MAX_PLAUSIBLE_DEG or abs(pitch) > _HEAD_POSE_MAX_PLAUSIBLE_DEG:
        return None, None

    return float(yaw), float(pitch)


# Eye-corner / eyelid / iris-center landmark indices from mediapipe's
# refine_landmarks=True FaceMesh output, used by _estimate_gaze_offset() to
# measure how far each iris has drifted from the center of its eye socket.
_LEFT_EYE_H_CORNERS  = (33, 133)    # outer, inner corner
_LEFT_EYE_V_LIDS     = (159, 145)   # upper, lower lid
_LEFT_IRIS_CENTER    = 468
_RIGHT_EYE_H_CORNERS = (362, 263)   # inner, outer corner
_RIGHT_EYE_V_LIDS    = (386, 374)   # upper, lower lid
_RIGHT_IRIS_CENTER   = 473


# Minimum eye width/height (as a fraction of the whole image — these are
# normalized 0-1 FaceMesh coordinates) below which _eye_offset_ratio()
# refuses to compute a ratio. Without this, a near-closed eye (a blink
# caught mid-frame, or just landmark noise on a small/blurry crop) makes the
# denominator tiny and the resulting ratio explode to nonsense values —
# observed in testing as gaze_offset_y readings of -1 to -6 (the valid range
# is roughly +/-0.5) on otherwise unremarkable frames.
_MIN_EYE_DIMENSION = 0.008


def _eye_offset_ratio(landmarks, h_corners, v_lids, iris_center):
    """
    Return (horizontal_ratio, vertical_ratio) describing how far one eye's
    iris has drifted from that eye's center, as a fraction of its own
    width/height — 0.0 means centered, roughly +/-0.5 means at the eye's
    edge. Being a ratio within the same eye rather than an absolute angle,
    this needs no camera calibration and stays comparable across different
    webcams/distances, unlike _estimate_head_pose(). Returns (0.0, 0.0) —
    treated as centered/inconclusive rather than a measurement — if the eye
    is too small in frame to divide by reliably (see _MIN_EYE_DIMENSION).
    """
    left, right = landmarks[h_corners[0]], landmarks[h_corners[1]]
    top, bottom = landmarks[v_lids[0]], landmarks[v_lids[1]]
    iris = landmarks[iris_center]

    eye_width = right.x - left.x
    eye_height = bottom.y - top.y
    h_ratio = (
        (iris.x - min(left.x, right.x)) / abs(eye_width) - 0.5
        if abs(eye_width) >= _MIN_EYE_DIMENSION else 0.0
    )
    v_ratio = (
        (iris.y - min(top.y, bottom.y)) / abs(eye_height) - 0.5
        if abs(eye_height) >= _MIN_EYE_DIMENSION else 0.0
    )
    return h_ratio, v_ratio


def _estimate_gaze_offset(landmarks):
    """Average the horizontal/vertical iris-offset ratio (see
    _eye_offset_ratio()) across both eyes."""
    lh, lv = _eye_offset_ratio(landmarks, _LEFT_EYE_H_CORNERS, _LEFT_EYE_V_LIDS, _LEFT_IRIS_CENTER)
    rh, rv = _eye_offset_ratio(landmarks, _RIGHT_EYE_H_CORNERS, _RIGHT_EYE_V_LIDS, _RIGHT_IRIS_CENTER)
    return (lh + rh) / 2, (lv + rv) / 2


def analyze_webcam_frame(image_bytes: bytes) -> dict:
    """
    Run one webcam JPEG frame through face detection and (when exactly one
    face is found) head-pose estimation plus iris-offset gaze estimation.

    looking_away is flagged if *either* signal crosses its threshold: a head
    pose beyond LOOKING_AWAY_YAW/PITCH_THRESHOLD_DEG, or an iris-offset ratio
    beyond GAZE_OFFSET_THRESHOLD in either eye (see module constants above
    for why both exist — head pose alone undershoots real rotation, and gaze
    offset alone can miss a full head turn if the face detector loses the
    iris landmarks).

    Returns {"face_count": int, "no_face": bool, "multiple_faces": bool,
    "looking_away": bool|None, "yaw_deg": float|None, "pitch_deg": float|None,
    "gaze_offset_x": float|None, "gaze_offset_y": float|None}. All of the
    per-face fields stay None whenever face_count != 1 — they're meaningless
    with zero or multiple faces in frame.
    """
    import cv2
    import numpy as np

    np_arr = np.frombuffer(image_bytes, np.uint8)
    image_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        return {
            "face_count": 0, "no_face": True, "multiple_faces": False,
            "looking_away": None, "yaw_deg": None, "pitch_deg": None,
            "gaze_offset_x": None, "gaze_offset_y": None,
        }

    face_mesh = _get_face_mesh()
    results = face_mesh.process(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    faces = results.multi_face_landmarks or []
    face_count = len(faces)

    yaw = pitch = gaze_x = gaze_y = looking_away = None
    if face_count == 1:
        h, w, _ = image_bgr.shape
        landmarks = faces[0].landmark
        yaw, pitch = _estimate_head_pose(landmarks, w, h)
        gaze_x, gaze_y = _estimate_gaze_offset(landmarks)

        head_turned = yaw is not None and (
            abs(yaw) > LOOKING_AWAY_YAW_THRESHOLD_DEG
            or abs(pitch) > LOOKING_AWAY_PITCH_THRESHOLD_DEG
        )
        eyes_off_center = (
            abs(gaze_x) > GAZE_OFFSET_THRESHOLD
            or abs(gaze_y) > GAZE_OFFSET_THRESHOLD
        )
        looking_away = head_turned or eyes_off_center

    return {
        "face_count": face_count,
        "no_face": face_count == 0,
        "multiple_faces": face_count > 1,
        "looking_away": looking_away,
        "yaw_deg": yaw,
        "pitch_deg": pitch,
        "gaze_offset_x": gaze_x,
        "gaze_offset_y": gaze_y,
    }


def save_proctor_webcam_frame(
    session_id: str,
    user_id: int,
    quiz_id,
    assessment_id,
    data_url: str,
) -> None:
    """
    Decode one base64 JPEG data URL captured by _WEBCAM_MONITOR_JS and write
    the image to disk under uploads/proctor_webcam_frames/, logging it to
    quiz_proctor_webcam_frames with analysis_status = 'pending'. Silently
    does nothing if data_url is malformed — a single dropped frame should
    never break the quiz for the student.

    analyze_webcam_frame() (mediapipe FaceMesh + head-pose/gaze estimation)
    is deliberately NOT run here — it's real per-frame CPU work that would
    otherwise compete with the live parts of a proctored session (keystroke/
    mouse logging, tab-switch monitoring, video capture) on every one of a
    student's frames throughout the exam. It's deferred to
    process_pending_proctor_webcam_frames(), run after the exam/session is
    over — see that function and the Admin Panel's "Run Proctoring
    Analysis" button.
    """
    # See save_proctor_frame()'s comment for why this splits on "base64,"
    # rather than the first comma.
    if not data_url or "base64," not in data_url:
        return
    try:
        image_bytes = base64.b64decode(data_url.partition("base64,")[2])
    except Exception:
        return

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
                 yaw_deg, pitch_deg, gaze_offset_x, gaze_offset_y,
                 analysis_status)
            VALUES (%s, %s, %s, %s, %s, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'pending')
            """,
            (session_id, user_id, quiz_id, assessment_id, str(file_path)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# AUDIO ANALYSIS — voice-activity (human speech) detection on recorded clips
# =============================================================================

@st.cache_resource(show_spinner=False)
def _get_speech_model():
    """Build (once per process) the Silero VAD model used to detect human
    speech in recorded audio segments. Loaded from the model file bundled
    inside the silero-vad pip package (onnx=False selects the torch-jit
    variant, reusing the torch runtime already pinned for the RAG/embeddings
    features rather than adding a second DL framework) — no network access,
    no torch.hub download."""
    from silero_vad import load_silero_vad
    return load_silero_vad(onnx=False)


def analyze_audio_clip(audio_bytes: bytes) -> dict:
    """
    Decode one recorded audio segment (webm/opus, or audio/mp4 on browsers
    that don't support webm recording — see MIME_CANDIDATES in
    _AUDIO_MONITOR_JS) and run it through Silero VAD to detect human speech.

    Decoding goes through pydub/ffmpeg (the same audio pipeline already used
    by narrated_slideshow) rather than silero-vad's own torchaudio-based
    read_audio(), so no separate audio backend needs configuring. The
    decoded waveform is resampled to mono 16kHz — the sample rate Silero VAD
    is trained for — before being handed to get_speech_timestamps().

    Returns {"speech_present": bool, "speech_duration_sec": float,
    "clip_duration_sec": float}. speech_present is False (with both
    durations 0.0) if the clip fails to decode or is empty — a single
    dropped/corrupt segment should never break the quiz for the student.
    """
    from io import BytesIO

    import imageio_ffmpeg
    import numpy as np
    import torch
    from pydub import AudioSegment
    from silero_vad import get_speech_timestamps

    empty = {"speech_present": False, "speech_duration_sec": 0.0, "clip_duration_sec": 0.0}

    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        segment = AudioSegment.from_file(BytesIO(audio_bytes))
    except Exception:
        return empty

    segment = segment.set_channels(1).set_frame_rate(16000)
    samples = np.array(segment.get_array_of_samples())
    if samples.size == 0:
        return empty

    max_amplitude = float(1 << (8 * segment.sample_width - 1))
    waveform = torch.from_numpy(samples.astype(np.float32) / max_amplitude)

    speech_segments = get_speech_timestamps(
        waveform, _get_speech_model(), sampling_rate=16000,
        min_speech_duration_ms=int(MIN_SPEECH_DURATION_SEC * 1000),
        return_seconds=True,
    )

    speech_duration = sum(seg["end"] - seg["start"] for seg in speech_segments)
    return {
        "speech_present": speech_duration > 0,
        "speech_duration_sec": speech_duration,
        "clip_duration_sec": segment.duration_seconds,
    }


def save_proctor_audio_clip(
    session_id: str,
    user_id: int,
    quiz_id,
    assessment_id,
    data_url: str,
) -> None:
    """
    Decode one base64 audio data URL captured by _AUDIO_MONITOR_JS and write
    it to disk (under uploads/proctor_audio_clips/), logging it to
    quiz_proctor_audio_clips with analysis_status = 'pending' and placeholder
    0.0 durations. Silently does nothing if data_url is malformed — a single
    dropped segment should never break the quiz for the student.

    analyze_audio_clip() (ffmpeg decode + a Silero VAD model pass) is
    deliberately NOT run here — every 10-second segment doing that inline
    would compete for CPU with the live parts of a proctored session the
    same way analyze_webcam_frame() would (see save_proctor_webcam_frame()).
    It's deferred to process_pending_proctor_audio_clips(), which is also
    where the original "discard segments with no detected speech" decision
    now happens — every segment is saved here unconditionally, and only
    speech-positive ones survive that later pass (see the module docstring
    and the Admin Panel's "Run Proctoring Analysis" button).
    """
    # See save_proctor_frame()'s comment for why this splits on "base64,"
    # rather than the first comma (audio/webm;codecs=opus has none today,
    # but the header is also used below for the mp4/webm extension check,
    # so it must stay intact up to the real payload regardless).
    if not data_url or "base64," not in data_url:
        return
    header, _, encoded = data_url.partition("base64,")
    try:
        audio_bytes = base64.b64decode(encoded)
    except Exception:
        return

    clip_dir = (
        _PROCTOR_AUDIO_CLIPS_DIR
        / f"assessment_{assessment_id or 'none'}"
        / f"user_{user_id}"
        / session_id
    )
    clip_dir.mkdir(parents=True, exist_ok=True)
    ext = "mp4" if "audio/mp4" in header else "webm"
    file_path = clip_dir / f"clip_{int(time.time() * 1000)}.{ext}"
    file_path.write_bytes(audio_bytes)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO quiz_proctor_audio_clips
                (session_id, user_id, quiz_id, assessment_id, file_path,
                 speech_duration_sec, clip_duration_sec, analysis_status)
            VALUES (%s, %s, %s, %s, %s, 0.0, 0.0, 'pending')
            """,
            (session_id, user_id, quiz_id, assessment_id, str(file_path)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# DEFERRED ANALYSIS — batch processing after capture
# =============================================================================
# save_proctor_webcam_frame() / save_proctor_audio_clip() above only capture
# and save raw data (analysis_status = 'pending'); the CPU-heavy analysis
# (mediapipe FaceMesh + head-pose/gaze, ffmpeg decode + Silero VAD) runs here
# instead, on whatever schedule the caller chooses — see
# process_pending_proctor_analysis().

def process_pending_proctor_webcam_frames(
    session_id: str = None,
    user_id: int = None,
    assessment_id=None,
    limit: int = 1000,
) -> dict:
    """
    Run analyze_webcam_frame() over webcam frames still awaiting analysis
    (analysis_status = 'pending'), deferred from capture time by
    save_proctor_webcam_frame() — see its docstring for why. Each pending row
    is updated in place with the real face_count/no_face/multiple_faces/
    looking_away/yaw_deg/pitch_deg/gaze_offset_x/gaze_offset_y and
    analysis_status = 'analyzed'. A row whose file is missing from disk is
    deleted outright rather than left permanently pending.

    Scoped by session_id, or by (user_id, assessment_id), or — if none of
    those are given — processed globally, oldest first, up to `limit` rows
    (the mode used by the Admin Panel's "Run Proctoring Analysis" button).

    Returns {"analyzed": int, "missing_file": int}.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if session_id:
            cursor.execute(
                "SELECT id, file_path FROM quiz_proctor_webcam_frames "
                "WHERE analysis_status = 'pending' AND session_id = %s",
                (session_id,),
            )
        elif user_id and assessment_id:
            cursor.execute(
                "SELECT id, file_path FROM quiz_proctor_webcam_frames "
                "WHERE analysis_status = 'pending' AND user_id = %s AND assessment_id = %s",
                (user_id, assessment_id),
            )
        else:
            cursor.execute(
                "SELECT id, file_path FROM quiz_proctor_webcam_frames "
                "WHERE analysis_status = 'pending' ORDER BY captured_at ASC LIMIT %s",
                (limit,),
            )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()

    analyzed = missing_file = 0
    write_cursor = conn.cursor()
    try:
        for row in rows:
            path = Path(row["file_path"])
            if not path.exists():
                write_cursor.execute(
                    "DELETE FROM quiz_proctor_webcam_frames WHERE id = %s", (row["id"],)
                )
                missing_file += 1
                continue

            analysis = analyze_webcam_frame(path.read_bytes())
            write_cursor.execute(
                """
                UPDATE quiz_proctor_webcam_frames
                SET face_count = %s, no_face = %s, multiple_faces = %s,
                    looking_away = %s, yaw_deg = %s, pitch_deg = %s,
                    gaze_offset_x = %s, gaze_offset_y = %s, analysis_status = 'analyzed'
                WHERE id = %s
                """,
                (
                    analysis["face_count"], analysis["no_face"], analysis["multiple_faces"],
                    analysis["looking_away"], analysis["yaw_deg"], analysis["pitch_deg"],
                    analysis["gaze_offset_x"], analysis["gaze_offset_y"], row["id"],
                ),
            )
            analyzed += 1
        conn.commit()
    finally:
        write_cursor.close()
        conn.close()

    return {"analyzed": analyzed, "missing_file": missing_file}


def process_pending_proctor_audio_clips(
    session_id: str = None,
    user_id: int = None,
    assessment_id=None,
    limit: int = 1000,
) -> dict:
    """
    Run analyze_audio_clip() (Silero VAD) over audio clips still awaiting
    analysis (analysis_status = 'pending'), deferred from capture time by
    save_proctor_audio_clip() — see its docstring for why. This is also
    where the original "keep only clips with detected speech" decision now
    happens: a clip found to contain no speech is deleted (row + file on
    disk) exactly as it would have been discarded at capture time before;
    a clip with detected speech is updated in place with its real
    speech_duration_sec/clip_duration_sec and analysis_status = 'analyzed'.
    A row whose file is missing from disk is deleted outright rather than
    left permanently pending.

    Scoped the same way as process_pending_proctor_webcam_frames() — by
    session_id, by (user_id, assessment_id), or globally up to `limit` rows.

    Returns {"analyzed": int, "discarded": int, "missing_file": int}.
    analyzed counts clips kept because speech was detected; discarded counts
    clips deleted because no speech was found.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if session_id:
            cursor.execute(
                "SELECT id, file_path FROM quiz_proctor_audio_clips "
                "WHERE analysis_status = 'pending' AND session_id = %s",
                (session_id,),
            )
        elif user_id and assessment_id:
            cursor.execute(
                "SELECT id, file_path FROM quiz_proctor_audio_clips "
                "WHERE analysis_status = 'pending' AND user_id = %s AND assessment_id = %s",
                (user_id, assessment_id),
            )
        else:
            cursor.execute(
                "SELECT id, file_path FROM quiz_proctor_audio_clips "
                "WHERE analysis_status = 'pending' ORDER BY captured_at ASC LIMIT %s",
                (limit,),
            )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()

    analyzed = discarded = missing_file = 0
    write_cursor = conn.cursor()
    try:
        for row in rows:
            path = Path(row["file_path"])
            if not path.exists():
                write_cursor.execute(
                    "DELETE FROM quiz_proctor_audio_clips WHERE id = %s", (row["id"],)
                )
                missing_file += 1
                continue

            analysis = analyze_audio_clip(path.read_bytes())
            if analysis["speech_present"]:
                write_cursor.execute(
                    """
                    UPDATE quiz_proctor_audio_clips
                    SET speech_duration_sec = %s, clip_duration_sec = %s, analysis_status = 'analyzed'
                    WHERE id = %s
                    """,
                    (analysis["speech_duration_sec"], analysis["clip_duration_sec"], row["id"]),
                )
                analyzed += 1
            else:
                path.unlink(missing_ok=True)
                write_cursor.execute(
                    "DELETE FROM quiz_proctor_audio_clips WHERE id = %s", (row["id"],)
                )
                discarded += 1
        conn.commit()
    finally:
        write_cursor.close()
        conn.close()

    return {"analyzed": analyzed, "discarded": discarded, "missing_file": missing_file}


def process_pending_proctor_analysis(
    session_id: str = None,
    user_id: int = None,
    assessment_id=None,
    limit: int = 1000,
) -> dict:
    """
    Run both deferred analysis passes — see
    process_pending_proctor_webcam_frames() and
    process_pending_proctor_audio_clips() — over whatever is still
    analysis_status = 'pending'.

    Scoped by session_id, by (user_id, assessment_id), or left unscoped to
    sweep globally up to `limit` oldest-pending rows of each kind. Called
    automatically every PROCTOR_ANALYSIS_SWEEP_INTERVAL_SECONDS by the
    background thread started via start_proctor_analysis_scheduler() (see
    below) — an admin no longer has to trigger this for results to be ready;
    the Admin Panel's "Run Proctoring Analysis" button still calls this too,
    for an immediate on-demand run instead of waiting for the next sweep.

    Returns {"webcam_frames_analyzed": int, "webcam_frames_missing_file": int,
    "audio_clips_analyzed": int, "audio_clips_discarded": int,
    "audio_clips_missing_file": int}.
    """
    webcam_result = process_pending_proctor_webcam_frames(session_id, user_id, assessment_id, limit)
    audio_result = process_pending_proctor_audio_clips(session_id, user_id, assessment_id, limit)
    return {
        "webcam_frames_analyzed": webcam_result["analyzed"],
        "webcam_frames_missing_file": webcam_result["missing_file"],
        "audio_clips_analyzed": audio_result["analyzed"],
        "audio_clips_discarded": audio_result["discarded"],
        "audio_clips_missing_file": audio_result["missing_file"],
    }


# =============================================================================
# BACKGROUND SCHEDULER — automatic periodic analysis sweep
# =============================================================================
# Streamlit apps have no built-in background worker/cron process — every
# other on-demand action in this app (cleanup_old_proctor_data(),
# process_pending_proctor_analysis() above) was therefore designed to be
# triggered manually (an admin clicking a button) or by an external scheduler
# calling the function directly.
#
# This section adds a real "automatic" option: a daemon thread, started once
# per server process, that calls process_pending_proctor_analysis() every
# PROCTOR_ANALYSIS_SWEEP_INTERVAL_SECONDS for as long as the process is
# running — so pending webcam/audio analysis gets done on its own schedule,
# and an admin logging in later simply finds finished results waiting,
# without having to click anything first.
#
# start_proctor_analysis_scheduler() is decorated with @st.cache_resource,
# which Streamlit caches globally across every user session on this server
# process (not per-session, unlike st.session_state) — the decorated body,
# and the thread it starts, therefore only ever runs once no matter how many
# times it's called or how many students/admins are using the app
# concurrently. Call it once from app.py at startup.
#
# This does NOT require (or preclude) a real OS-level scheduler — if this
# app is ever run across multiple server processes/replicas behind a load
# balancer, each process starts its own thread, and more than one could pick
# up the same pending rows in the small window before analysis_status flips
# to 'analyzed'; that's wasted duplicate work, not corruption (both
# analyze_webcam_frame() and analyze_audio_clip() are pure functions of the
# same file, safe to run twice), but if that scenario applies, prefer a
# single external cron/task calling process_pending_proctor_analysis()
# instead of relying on this in-process thread.

PROCTOR_ANALYSIS_SWEEP_INTERVAL_SECONDS = 15 * 60  # 15 minutes — tune to taste


def _proctor_analysis_background_loop() -> None:
    """
    Runs forever in a daemon thread (started by
    start_proctor_analysis_scheduler()), sleeping
    PROCTOR_ANALYSIS_SWEEP_INTERVAL_SECONDS between sweeps. A failed sweep
    (e.g. a transient DB hiccup) is swallowed rather than left to kill the
    thread — there's always another attempt one interval later.
    """
    while True:
        time.sleep(PROCTOR_ANALYSIS_SWEEP_INTERVAL_SECONDS)
        try:
            process_pending_proctor_analysis()
        except Exception:
            pass


@st.cache_resource(show_spinner=False)
def start_proctor_analysis_scheduler() -> bool:
    """
    Start the background proctoring-analysis sweep thread exactly once per
    server process — see the module section comment above for why
    st.cache_resource is what makes "exactly once" true here. Call this once
    from app.py at startup; calling it again (from any session, on any
    rerun) is safe and a no-op, since st.cache_resource simply returns the
    already-cached True without re-running the function body.

    Returns True — the value itself isn't meaningful, only that this ran.
    """
    thread = threading.Thread(target=_proctor_analysis_background_loop, daemon=True)
    thread.start()
    return True


# =============================================================================
# FULL-SESSION VIDEO — continuous screen/webcam recording, stitched on demand
# =============================================================================

def save_proctor_video_segment(
    session_id: str,
    user_id: int,
    quiz_id,
    assessment_id,
    kind: str,
    seq: int,
    data_url: str,
) -> None:
    """
    Decode one base64 webm video segment captured by _SCREEN_SHARE_JS or
    _WEBCAM_MONITOR_JS's recorder (kind is "screen" or "webcam") and write it
    to disk under uploads/proctor_video_segments/{kind}/, recording its path
    in quiz_proctor_video_segments. These raw segments are stitched into one
    playable video per session on demand by get_or_build_proctor_video() —
    saving here never blocks on that. Silently does nothing if data_url is
    malformed — a single dropped segment should never break the quiz for the
    student, and just leaves a gap in the final stitched video.
    """
    # Split on the literal "base64," marker, not the first comma. The
    # webcam recorder's video+audio MIME type is
    # "video/webm;codecs=vp8,opus" — note the comma inside the codecs list
    # itself, before the real "base64," marker. Splitting on the first comma
    # (as this used to) cut the string there instead, leaving "opus;base64,"
    # glued onto the front of what got base64-decoded; b64decode() doesn't
    # raise on the stray "opusbase64" prefix (it silently drops the invalid
    # ';' and ',' characters and decodes the rest of the valid-looking
    # alphabet anyway), it just shifts every following byte's alignment,
    # corrupting the whole segment — every webcam *video* segment recorded
    # with an audio track was affected; screen segments (no audio track, so
    # no comma in the MIME type) were never hit by this.
    if not data_url or "base64," not in data_url:
        return
    try:
        video_bytes = base64.b64decode(data_url.partition("base64,")[2])
    except Exception:
        return

    segment_dir = (
        _PROCTOR_VIDEO_SEGMENTS_DIR
        / kind
        / f"assessment_{assessment_id or 'none'}"
        / f"user_{user_id}"
        / session_id
    )
    segment_dir.mkdir(parents=True, exist_ok=True)
    file_path = segment_dir / f"segment_{seq:05d}.webm"
    file_path.write_bytes(video_bytes)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO quiz_proctor_video_segments
                (session_id, user_id, quiz_id, assessment_id, kind, seq, file_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (session_id, user_id, quiz_id, assessment_id, kind, seq, str(file_path)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _stitch_video_segments(segment_paths: list, final_dir: Path):
    """
    Shared ffmpeg concat-demuxer logic for get_or_build_proctor_video() and
    get_or_build_proctor_video_by_user_assessment(). The stitched output's
    filename encodes how many segments went into it (final_{count}.webm) so
    this doubles as a cache key: a later call after more segments have
    landed sees a different count and rebuilds, while a repeat call reuses
    the existing file instead of re-invoking ffmpeg every time an instructor
    opens the review page. Returns None if there are no segments or ffmpeg
    fails.
    """
    if not segment_paths:
        return None

    final_path = final_dir / f"final_{len(segment_paths)}.webm"
    if final_path.exists():
        return final_path

    final_dir.mkdir(parents=True, exist_ok=True)
    for stale in final_dir.glob("final_*.webm"):
        stale.unlink(missing_ok=True)

    import subprocess

    import imageio_ffmpeg

    filelist_path = final_dir / "_filelist.txt"
    filelist_path.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in segment_paths),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(filelist_path),
                "-c", "copy",
                str(final_path),
            ],
            check=True,
            capture_output=True,
        )
    except Exception:
        final_path.unlink(missing_ok=True)
        return None
    finally:
        filelist_path.unlink(missing_ok=True)

    return final_path if final_path.exists() else None


def _video_segment_paths(session_id: str, kind: str) -> list:
    """Shared lookup for get_or_build_proctor_video()/
    get_or_build_combined_proctor_video(): every existing segment file for
    one session_id + kind ("screen" or "webcam"), in capture order."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path FROM quiz_proctor_video_segments
            WHERE session_id = %s AND kind = %s
            ORDER BY seq
            """,
            (session_id, kind),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()

    return [Path(row["file_path"]) for row in rows if Path(row["file_path"]).exists()]


def get_or_build_proctor_video(session_id: str, kind: str):
    """
    Return the Path to one playable video covering the whole session for
    the given kind ("screen" or "webcam"), stitching the raw segments
    written by save_proctor_video_segment() together with ffmpeg the first
    time this is called, or None if no segments were ever recorded.
    """
    if not session_id:
        return None

    segment_paths = _video_segment_paths(session_id, kind)
    return _stitch_video_segments(segment_paths, _PROCTOR_VIDEO_FINAL_DIR / kind / session_id)


def get_or_build_combined_proctor_video(session_id: str):
    """
    Return the Path to one review video for the session: the full-session
    screen recording as the base, with the full-session webcam recording
    composited on top as a small picture-in-picture overlay in the
    bottom-right corner, carrying whatever audio the webcam recording has
    (silent if the student never granted microphone access, or webcam-only
    audio if they did — the screen recording never has an audio track, see
    _SCREEN_SHARE_JS). One file for an instructor to play instead of the
    separate screen/webcam players from get_or_build_proctor_video().

    Screen and webcam are captured off two independent MediaRecorder
    pipelines with no shared clock (see _SCREEN_SHARE_JS/_WEBCAM_MONITOR_JS)
    — each starts recording whenever its own permission button is clicked,
    typically seconds apart — so this overlays both from t=0 of their own
    stitched files rather than guaranteeing frame-accurate sync. That's
    fine for instructor review (spotting behavior) but not forensic-grade
    alignment.

    Falls back to whichever single recording exists if only screen or only
    webcam was ever captured, and returns None if neither was. Cached
    under uploads/proctor_video_final/combined/{session_id}/, keyed (like
    _stitch_video_segments) by how many segments went into each input, so a
    later call after more segments land rebuilds automatically.
    """
    if not session_id:
        return None

    screen_segments = _video_segment_paths(session_id, "screen")
    webcam_segments = _video_segment_paths(session_id, "webcam")

    if not screen_segments and not webcam_segments:
        return None
    if not webcam_segments:
        return _stitch_video_segments(screen_segments, _PROCTOR_VIDEO_FINAL_DIR / "screen" / session_id)
    if not screen_segments:
        return _stitch_video_segments(webcam_segments, _PROCTOR_VIDEO_FINAL_DIR / "webcam" / session_id)

    screen_path = _stitch_video_segments(screen_segments, _PROCTOR_VIDEO_FINAL_DIR / "screen" / session_id)
    webcam_path = _stitch_video_segments(webcam_segments, _PROCTOR_VIDEO_FINAL_DIR / "webcam" / session_id)
    if not screen_path or not webcam_path:
        return screen_path or webcam_path

    final_dir = _PROCTOR_VIDEO_FINAL_DIR / "combined" / session_id
    final_path = final_dir / f"final_{len(screen_segments)}_{len(webcam_segments)}.webm"
    if final_path.exists():
        return final_path

    final_dir.mkdir(parents=True, exist_ok=True)
    for stale in final_dir.glob("final_*.webm"):
        stale.unlink(missing_ok=True)

    if not _compose_pip_video(screen_path, webcam_path, final_path):
        return None
    return final_path if final_path.exists() else None


def _compose_pip_video(screen_path: Path, webcam_path: Path, final_path: Path) -> bool:
    """
    Shared ffmpeg filter_complex logic for get_or_build_combined_proctor_video()
    and its by-user-assessment counterpart below: overlay webcam_path onto
    screen_path as a bottom-right picture-in-picture, carrying webcam_path's
    audio track if it has one. Returns whether final_path was produced.

    screen_path/webcam_path are themselves concat-demuxer stitches (see
    _stitch_video_segments()) of many independently-recorded MediaRecorder
    segments, each with its own real-world capture jitter (canvas redraws
    driven by setInterval, browser encoder buffering) rather than a clean
    constant frame rate — concatenation preserves that raw timing. Feeding
    that directly into overlay left the picture-in-picture frozen on a
    single frame (overlay's frame-hold logic comparing two independently
    jittery PTS streams) and produced crackling audio on re-encode (opus
    decode/resample stumbling on the same irregular timestamps) even though
    each stitched file played back fine on its own — plain playback/stream
    copy tolerates ragged timestamps; filtering and re-encoding does not.
    setpts=PTS-STARTPTS + fps=<capture fps> forces both video streams to a
    clean constant frame rate before overlay so it always has a fresh frame
    to composite, and aresample=async=1 lets the audio resampler absorb the
    same irregularity instead of glitching on it.
    """
    import subprocess

    import imageio_ffmpeg

    # "1:a?" (trailing "?") maps the webcam's audio stream only if one
    # exists, rather than failing the whole ffmpeg invocation when the
    # student never granted microphone access and the webcam recording is
    # video-only. "-af aresample=async=1" is likewise harmless when no
    # audio stream ended up mapped — ffmpeg simply has no audio output
    # stream to apply it to.
    filter_complex = (
        f"[0:v]setpts=PTS-STARTPTS,fps={VIDEO_CAPTURE_FPS}[base];"
        f"[1:v]setpts=PTS-STARTPTS,fps={VIDEO_CAPTURE_FPS},scale=iw*{COMBINED_PIP_SCALE}:-2[pip];"
        f"[base][pip]overlay=W-w-{COMBINED_PIP_MARGIN_PX}:H-h-{COMBINED_PIP_MARGIN_PX}:shortest=1[outv]"
    )
    try:
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-i", str(screen_path),
                "-i", str(webcam_path),
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "1:a?",
                "-af", "aresample=async=1",
                "-c:v", "libvpx",
                "-b:v", "1M",
                "-c:a", "libopus",
                str(final_path),
            ],
            check=True,
            capture_output=True,
        )
    except Exception:
        final_path.unlink(missing_ok=True)
        return False

    return final_path.exists()


def _video_segments_by_user_assessment(user_id: int, assessment_id, kind: str) -> list:
    """Shared lookup for get_or_build_proctor_video_by_user_assessment()/
    get_or_build_combined_proctor_video_by_user_assessment(): every existing
    segment file across every proctoring session this user has had for this
    assessment, ordered chronologically (captured_at) rather than by
    session/seq, since a student may have started more than one session for
    this assessment and the combined recording should play back in the
    order it was actually captured."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path FROM quiz_proctor_video_segments
            WHERE user_id = %s AND assessment_id = %s AND kind = %s
            ORDER BY captured_at
            """,
            (user_id, assessment_id, kind),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()

    return [Path(row["file_path"]) for row in rows if Path(row["file_path"]).exists()]


def get_or_build_proctor_video_by_user_assessment(user_id: int, assessment_id, kind: str):
    """
    Same idea as get_or_build_proctor_video(), aggregated across every
    proctoring session this user has had for the given assessment — see
    get_proctor_summary_by_user_assessment() for why this exists (flows
    like the Exam Grading "Submit My Exam" upload gate have no single
    attempt row to pin one session_id to).
    """
    if not assessment_id:
        return None

    segment_paths = _video_segments_by_user_assessment(user_id, assessment_id, kind)
    final_dir = _PROCTOR_VIDEO_FINAL_DIR / kind / f"user_{user_id}_assessment_{assessment_id}"
    return _stitch_video_segments(segment_paths, final_dir)


def get_or_build_combined_proctor_video_by_user_assessment(user_id: int, assessment_id):
    """
    Same idea as get_or_build_combined_proctor_video() (screen base +
    webcam picture-in-picture + webcam's audio), aggregated across every
    proctoring session this user has had for the given assessment — see
    get_or_build_proctor_video_by_user_assessment() for why this variant
    exists. Falls back to whichever single recording exists if only screen
    or only webcam was ever captured, and returns None if neither was.
    """
    if not assessment_id:
        return None

    screen_segments = _video_segments_by_user_assessment(user_id, assessment_id, "screen")
    webcam_segments = _video_segments_by_user_assessment(user_id, assessment_id, "webcam")

    if not screen_segments and not webcam_segments:
        return None

    screen_final_dir = _PROCTOR_VIDEO_FINAL_DIR / "screen" / f"user_{user_id}_assessment_{assessment_id}"
    webcam_final_dir = _PROCTOR_VIDEO_FINAL_DIR / "webcam" / f"user_{user_id}_assessment_{assessment_id}"

    if not webcam_segments:
        return _stitch_video_segments(screen_segments, screen_final_dir)
    if not screen_segments:
        return _stitch_video_segments(webcam_segments, webcam_final_dir)

    screen_path = _stitch_video_segments(screen_segments, screen_final_dir)
    webcam_path = _stitch_video_segments(webcam_segments, webcam_final_dir)
    if not screen_path or not webcam_path:
        return screen_path or webcam_path

    final_dir = _PROCTOR_VIDEO_FINAL_DIR / "combined" / f"user_{user_id}_assessment_{assessment_id}"
    final_path = final_dir / f"final_{len(screen_segments)}_{len(webcam_segments)}.webm"
    if final_path.exists():
        return final_path

    final_dir.mkdir(parents=True, exist_ok=True)
    for stale in final_dir.glob("final_*.webm"):
        stale.unlink(missing_ok=True)

    if not _compose_pip_video(screen_path, webcam_path, final_path):
        return None
    return final_path if final_path.exists() else None


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
        "pending_count": webcam_counts.get("pending_count", 0),
    }


# Shared by get_proctor_webcam_summary()/get_proctor_webcam_summary_by_user_assessment().
# The CASE guards restrict the face/gaze flag totals to frames that have
# actually been analyzed (analysis_status = 'analyzed') — frames still
# awaiting process_pending_proctor_webcam_frames() have meaningless
# zeroed/NULL flag columns (see save_proctor_webcam_frame()) and must not be
# silently counted as "clean". pending_count reports how many are still
# outstanding so instructor review can show that explicitly.
_WEBCAM_FLAG_COUNTS_SQL = """
    SELECT
        SUM(CASE WHEN analysis_status = 'analyzed' THEN no_face        ELSE 0 END) AS no_face_count,
        SUM(CASE WHEN analysis_status = 'analyzed' THEN multiple_faces ELSE 0 END) AS multiple_faces_count,
        SUM(CASE WHEN analysis_status = 'analyzed' THEN looking_away   ELSE 0 END) AS looking_away_count,
        SUM(CASE WHEN analysis_status = 'pending'  THEN 1              ELSE 0 END) AS pending_count
    FROM quiz_proctor_webcam_frames
    WHERE {where}
"""


def get_proctor_webcam_summary(session_id: str) -> dict:
    """
    Return a per-session rollup of webcam monitoring for instructor review:
      {"webcam": "granted" | "denied" | None,
       "no_face_count": int, "multiple_faces_count": int,
       "looking_away_count": int, "pending_count": int}

    pending_count is how many captured frames are still awaiting
    process_pending_proctor_webcam_frames() — the other three counts only
    reflect frames already analyzed.
    """
    if not session_id:
        return {"webcam": None, "no_face_count": 0, "multiple_faces_count": 0,
                "looking_away_count": 0, "pending_count": 0}

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
            _WEBCAM_FLAG_COUNTS_SQL.format(where="session_id = %s"),
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
        "pending_count": webcam_counts.get("pending_count") or 0,
    })


def get_proctor_webcam_summary_by_user_assessment(user_id: int, assessment_id) -> dict:
    """Same shape as get_proctor_webcam_summary(), aggregated across every
    proctoring session this user has had for the given assessment — see
    get_proctor_summary_by_user_assessment() for why this exists."""
    if not assessment_id:
        return {"webcam": None, "no_face_count": 0, "multiple_faces_count": 0,
                "looking_away_count": 0, "pending_count": 0}

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
            _WEBCAM_FLAG_COUNTS_SQL.format(where="user_id = %s AND assessment_id = %s"),
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
        "pending_count": webcam_counts.get("pending_count") or 0,
    })


def get_proctor_audio_summary(session_id: str) -> dict:
    """
    Return a per-session rollup of audio monitoring for instructor review:
      {"clip_count": int, "speech_duration_sec": float, "pending_count": int}

    clip_count/speech_duration_sec only reflect clips already run through
    process_pending_proctor_audio_clips() and confirmed to contain speech
    (analysis_status = 'analyzed') — see save_proctor_audio_clip() for why
    every captured segment is stored first and analyzed later. pending_count
    is how many captured segments are still awaiting that pass; some of
    those will turn out to contain no speech and be discarded then, exactly
    as they always would have been, just not yet.
    """
    if not session_id:
        return {"clip_count": 0, "speech_duration_sec": 0.0, "pending_count": 0}

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN analysis_status = 'analyzed' THEN 1 ELSE 0 END) AS clip_count,
                SUM(CASE WHEN analysis_status = 'analyzed' THEN speech_duration_sec ELSE 0 END) AS speech_duration_sec,
                SUM(CASE WHEN analysis_status = 'pending' THEN 1 ELSE 0 END) AS pending_count
            FROM quiz_proctor_audio_clips
            WHERE session_id = %s
            """,
            (session_id,),
        )
        row = cursor.fetchone() or {}
    finally:
        cursor.close()
        conn.close()

    return {
        "clip_count": row.get("clip_count") or 0,
        "speech_duration_sec": float(row.get("speech_duration_sec") or 0.0),
        "pending_count": row.get("pending_count") or 0,
    }


def get_proctor_audio_summary_by_user_assessment(user_id: int, assessment_id) -> dict:
    """Same shape as get_proctor_audio_summary(), aggregated across every
    proctoring session this user has had for the given assessment — see
    get_proctor_summary_by_user_assessment() for why this exists."""
    if not assessment_id:
        return {"clip_count": 0, "speech_duration_sec": 0.0, "pending_count": 0}

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN analysis_status = 'analyzed' THEN 1 ELSE 0 END) AS clip_count,
                SUM(CASE WHEN analysis_status = 'analyzed' THEN speech_duration_sec ELSE 0 END) AS speech_duration_sec,
                SUM(CASE WHEN analysis_status = 'pending' THEN 1 ELSE 0 END) AS pending_count
            FROM quiz_proctor_audio_clips
            WHERE user_id = %s AND assessment_id = %s
            """,
            (user_id, assessment_id),
        )
        row = cursor.fetchone() or {}
    finally:
        cursor.close()
        conn.close()

    return {
        "clip_count": row.get("clip_count") or 0,
        "speech_duration_sec": float(row.get("speech_duration_sec") or 0.0),
        "pending_count": row.get("pending_count") or 0,
    }


def get_proctor_audio_clips(session_id: str, limit: int = 200) -> list[dict]:
    """Return logged speech-positive audio clips for one proctoring session
    (analysis_status = 'analyzed' — see save_proctor_audio_clip()/
    get_proctor_audio_summary()), newest first — parallel to
    get_proctor_webcam_frames()."""
    if not session_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path, speech_duration_sec, clip_duration_sec, captured_at
            FROM quiz_proctor_audio_clips
            WHERE session_id = %s AND analysis_status = 'analyzed'
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def get_proctor_audio_clips_by_user_assessment(user_id: int, assessment_id, limit: int = 200) -> list[dict]:
    """Same shape as get_proctor_audio_clips(), aggregated across every
    proctoring session this user has had for the given assessment — see
    get_proctor_summary_by_user_assessment() for why this exists."""
    if not assessment_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path, speech_duration_sec, clip_duration_sec, captured_at
            FROM quiz_proctor_audio_clips
            WHERE user_id = %s AND assessment_id = %s AND analysis_status = 'analyzed'
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (user_id, assessment_id, limit),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


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
    """Return captured webcam frames (with analysis flags, plus
    analysis_status — 'pending' rows have meaningless/zeroed flags, not yet
    filled in by process_pending_proctor_webcam_frames()) for one proctoring
    session, newest first."""
    if not session_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT file_path, face_count, no_face, multiple_faces,
                   looking_away, yaw_deg, pitch_deg, gaze_offset_x,
                   gaze_offset_y, analysis_status, captured_at
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
                   looking_away, yaw_deg, pitch_deg, gaze_offset_x,
                   gaze_offset_y, analysis_status, captured_at
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


def get_proctor_mouse_events(session_id: str, limit: int = 200) -> list[dict]:
    """
    Return captured mouse-event batches for one proctoring session, oldest
    first, with each row's events_json decoded back into a list of
    {"type", "x", "y", "button", "t"} dicts. Mirrors get_proctor_keystrokes().
    """
    if not session_id:
        return []

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT events_json, captured_at
            FROM quiz_proctor_mouse_events
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

    return _decode_mouse_event_rows(rows)


def get_proctor_mouse_events_by_user_assessment(user_id: int, assessment_id, limit: int = 200) -> list[dict]:
    """
    Same as get_proctor_mouse_events(), aggregated across every proctoring
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
            SELECT events_json, captured_at
            FROM quiz_proctor_mouse_events
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

    return _decode_mouse_event_rows(rows)


def _decode_mouse_event_rows(rows: list[dict]) -> list[dict]:
    """Flatten a list of {"events_json", "captured_at"} batch rows into one
    list of individual mouse-event dicts, dropping any batch that fails to
    decode rather than failing the whole review page."""
    events = []
    for row in rows:
        try:
            events.extend(json.loads(row["events_json"]))
        except Exception:
            continue
    return events


def format_mouse_events_for_display(events: list[dict]) -> str:
    """
    Summarize a flat list of mouse-event dicts (as returned by
    get_proctor_mouse_events()/get_proctor_mouse_events_by_user_assessment())
    for instructor review. Unlike format_keystrokes_for_display(), this
    doesn't print a literal stream — raw coordinates aren't meaningful to
    read at a glance — instead it reports activity counts: clicks (by
    button), movement samples, and how many times the cursor left/re-entered
    the browser window (a coarse signal for switching to another monitor or
    device).
    """
    clicks_by_button: dict[str, int] = {}
    move_count = 0
    leave_count = 0
    enter_count = 0

    for entry in events:
        kind = entry.get("type")
        if kind == "click":
            button = entry.get("button", "other")
            clicks_by_button[button] = clicks_by_button.get(button, 0) + 1
        elif kind == "move":
            move_count += 1
        elif kind == "leave_window":
            leave_count += 1
        elif kind == "enter_window":
            enter_count += 1

    total_clicks = sum(clicks_by_button.values())
    click_breakdown = ", ".join(
        f"{count} {button}" for button, count in sorted(clicks_by_button.items())
    )
    lines = [
        f"{total_clicks} click(s)" + (f" ({click_breakdown})" if click_breakdown else ""),
        f"{move_count} movement sample(s)",
        f"{leave_count} window-leave / {enter_count} window-re-enter event(s)",
    ]
    return "\n".join(lines)


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
    disk), keystroke batch, and speech-positive audio clip (including its
    audio file on disk) recorded under one proctoring session_id.

    Lets an instructor discard the monitoring data for a single quiz
    attempt from the review UI, as opposed to cleanup_old_proctor_data()'s
    age-based bulk purge. The practice_quiz_attempts row that referenced
    this session_id is left in place — the attempt itself isn't deleted,
    only the monitoring data attached to it; get_proctor_summary() and
    get_proctor_frames()/get_proctor_webcam_frames()/get_proctor_keystrokes()/
    get_proctor_audio_clips() simply return empty results for this
    session_id afterwards.

    Also removes any recorded screen/webcam video segments and their
    stitched final_*.webm output (see save_proctor_video_segment() /
    get_or_build_proctor_video()).

    Returns {"events_deleted": int, "frames_deleted": int,
    "webcam_frames_deleted": int, "files_removed": int,
    "keystrokes_deleted": int, "mouse_events_deleted": int,
    "audio_clips_deleted": int, "video_segments_deleted": int}.
    """
    import shutil

    empty = {
        "events_deleted": 0, "frames_deleted": 0, "webcam_frames_deleted": 0,
        "files_removed": 0, "keystrokes_deleted": 0, "mouse_events_deleted": 0,
        "audio_clips_deleted": 0, "video_segments_deleted": 0,
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

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_audio_clips WHERE session_id = %s",
            (session_id,),
        )
        audio_clips = cursor.fetchall() or []

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_video_segments WHERE session_id = %s",
            (session_id,),
        )
        video_segments = cursor.fetchall() or []
    finally:
        cursor.close()

    files_removed = 0
    for row in frames + webcam_frames + audio_clips + video_segments:
        try:
            path = Path(row["file_path"])
            if path.exists():
                path.unlink()
                files_removed += 1
        except Exception:
            pass

    for kind in ("screen", "webcam", "combined"):
        shutil.rmtree(_PROCTOR_VIDEO_FINAL_DIR / kind / session_id, ignore_errors=True)

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM quiz_proctor_frames WHERE session_id = %s", (session_id,))
        frames_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_webcam_frames WHERE session_id = %s", (session_id,))
        webcam_frames_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_audio_clips WHERE session_id = %s", (session_id,))
        audio_clips_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_video_segments WHERE session_id = %s", (session_id,))
        video_segments_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_events WHERE session_id = %s", (session_id,))
        events_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_keystrokes WHERE session_id = %s", (session_id,))
        keystrokes_deleted = cursor.rowcount

        cursor.execute("DELETE FROM quiz_proctor_mouse_events WHERE session_id = %s", (session_id,))
        mouse_events_deleted = cursor.rowcount

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
        "mouse_events_deleted": mouse_events_deleted,
        "audio_clips_deleted": audio_clips_deleted,
        "video_segments_deleted": video_segments_deleted,
    }


def delete_proctor_data_for_user_assessment(user_id: int, assessment_id) -> dict:
    """
    Permanently delete every event, frame (including its image file on
    disk), keystroke batch, and speech-positive audio clip (including its
    audio file on disk) recorded for one student across every proctoring
    session tied to one assessment.

    Used by the Exam Grading "Submit My Exam" review, where individual
    uploaded files aren't pinned to a single session_id in the first place
    (see get_proctor_summary_by_user_assessment() for why — a student may
    have re-opened the upload page, and so started a new monitoring
    session, more than once before finally submitting). That means this is
    the finest-grained delete available there: "this student's entire
    proctoring history for this assessment," not a single attempt.

    Also removes any recorded screen/webcam video segments and their
    stitched final_*.webm output across every session tied to this
    student/assessment (see save_proctor_video_segment() /
    get_or_build_proctor_video()).

    Returns {"events_deleted": int, "frames_deleted": int,
    "webcam_frames_deleted": int, "files_removed": int,
    "keystrokes_deleted": int, "mouse_events_deleted": int,
    "audio_clips_deleted": int, "video_segments_deleted": int}.
    """
    import shutil

    empty = {
        "events_deleted": 0, "frames_deleted": 0, "webcam_frames_deleted": 0,
        "files_removed": 0, "keystrokes_deleted": 0, "mouse_events_deleted": 0,
        "audio_clips_deleted": 0, "video_segments_deleted": 0,
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

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_audio_clips WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        audio_clips = cursor.fetchall() or []

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_video_segments WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        video_segments = cursor.fetchall() or []

        cursor.execute(
            "SELECT DISTINCT session_id FROM quiz_proctor_video_segments WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        video_session_ids = [row["session_id"] for row in (cursor.fetchall() or [])]
    finally:
        cursor.close()

    files_removed = 0
    for row in frames + webcam_frames + audio_clips + video_segments:
        try:
            path = Path(row["file_path"])
            if path.exists():
                path.unlink()
                files_removed += 1
        except Exception:
            pass

    for sid in video_session_ids:
        for kind in ("screen", "webcam", "combined"):
            shutil.rmtree(_PROCTOR_VIDEO_FINAL_DIR / kind / sid, ignore_errors=True)
    for kind in ("screen", "webcam", "combined"):
        shutil.rmtree(
            _PROCTOR_VIDEO_FINAL_DIR / kind / f"user_{user_id}_assessment_{assessment_id}",
            ignore_errors=True,
        )

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
            "DELETE FROM quiz_proctor_audio_clips WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        audio_clips_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM quiz_proctor_video_segments WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        video_segments_deleted = cursor.rowcount

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

        cursor.execute(
            "DELETE FROM quiz_proctor_mouse_events WHERE user_id = %s AND assessment_id = %s",
            (user_id, assessment_id),
        )
        mouse_events_deleted = cursor.rowcount

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
        "mouse_events_deleted": mouse_events_deleted,
        "audio_clips_deleted": audio_clips_deleted,
        "video_segments_deleted": video_segments_deleted,
    }


def cleanup_old_proctor_data(retention_days: int = 7) -> dict:
    """
    Permanently delete proctoring events, screen-capture frames, webcam
    frames, keystroke batches, and speech-positive audio clips older than
    retention_days, removing each frame's/clip's file from disk before its
    quiz_proctor_frames / quiz_proctor_webcam_frames /
    quiz_proctor_audio_clips row is deleted.

    This data is meant to be short-lived (see module docstring) — anything
    still within the retention window is left untouched; everything older is
    purged outright, with no soft-delete or archive step. Intended to be
    triggered on demand (e.g. the Admin Panel Maintenance tab) or from an
    external scheduler calling this function directly; nothing in this app
    calls it automatically.

    Also purges video segments (and their stitched final_*.webm output —
    see save_proctor_video_segment() / get_or_build_proctor_video()) whose
    session is entirely older than retention_days.

    Returns {"events_deleted": int, "frames_deleted": int,
    "webcam_frames_deleted": int, "files_removed": int,
    "keystrokes_deleted": int, "mouse_events_deleted": int,
    "audio_clips_deleted": int, "video_segments_deleted": int}.
    files_removed may be lower than frames_deleted + webcam_frames_deleted +
    audio_clips_deleted + video_segments_deleted if some files were already
    missing from disk (e.g. removed manually) — that is not an error here.
    """
    import shutil

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

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_audio_clips "
            "WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        old_audio_clips = cursor.fetchall() or []

        cursor.execute(
            "SELECT file_path FROM quiz_proctor_video_segments "
            "WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        old_video_segments = cursor.fetchall() or []

        cursor.execute(
            "SELECT DISTINCT session_id FROM quiz_proctor_video_segments "
            "WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        old_video_session_ids = [row["session_id"] for row in (cursor.fetchall() or [])]
    finally:
        cursor.close()

    files_removed = 0
    for row in old_frames + old_webcam_frames + old_audio_clips + old_video_segments:
        try:
            path = Path(row["file_path"])
            if path.exists():
                path.unlink()
                files_removed += 1
        except Exception:
            pass

    for sid in old_video_session_ids:
        for kind in ("screen", "webcam", "combined"):
            shutil.rmtree(_PROCTOR_VIDEO_FINAL_DIR / kind / sid, ignore_errors=True)

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
            "DELETE FROM quiz_proctor_audio_clips WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        audio_clips_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM quiz_proctor_video_segments WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        video_segments_deleted = cursor.rowcount

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

        cursor.execute(
            "DELETE FROM quiz_proctor_mouse_events WHERE captured_at < (NOW() - INTERVAL %s DAY)",
            (retention_days,),
        )
        mouse_events_deleted = cursor.rowcount

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
        "mouse_events_deleted": mouse_events_deleted,
        "audio_clips_deleted": audio_clips_deleted,
        "video_segments_deleted": video_segments_deleted,
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
    audio_key = f"proctor_audio_status_{gate_key}"

    # Fetched once per session rather than on every rerun (this function is
    # called on every rerun for as long as the quiz is open) — the admin's
    # quality tier only ever needs to apply from the moment recording starts,
    # so there's no benefit to re-reading it mid-session, only extra DB load.
    quality_key = f"proctor_video_quality_{gate_key}"
    if quality_key not in st.session_state:
        st.session_state[quality_key] = get_proctor_video_quality()
    video_quality_preset = VIDEO_QUALITY_PRESETS.get(
        st.session_state[quality_key], VIDEO_QUALITY_PRESETS[DEFAULT_VIDEO_QUALITY]
    )
    video_quality_data = {
        "video_max_dimension_px": video_quality_preset["max_dimension_px"],
        "video_bits_per_second": video_quality_preset["bits_per_second"],
    }

    # Same once-per-session fetch pattern as the quality tier above — an
    # admin toggling this mid-session shouldn't tear down a webcam stream
    # already in progress. When False, the webcam component below is never
    # mounted at all, so the browser is never asked for camera permission.
    webcam_key_setting = f"proctor_record_webcam_{gate_key}"
    if webcam_key_setting not in st.session_state:
        st.session_state[webcam_key_setting] = get_record_webcam_video()
    webcam_recording_enabled = st.session_state[webcam_key_setting]

    if share_key not in st.session_state:
        if webcam_recording_enabled:
            st.info(
                "This quiz is monitored for academic integrity. Tab switches, "
                "window focus changes, keys you press, and mouse activity on "
                "this page are recorded automatically. You'll also be asked to "
                "share your screen, enable your camera, and enable your "
                "microphone below — your browser will show its own permission "
                "dialog for each. Once granted, a continuous recording of your "
                "screen and a continuous recording of your webcam (with audio "
                "from your microphone) are saved for instructor review, "
                "alongside periodic snapshots checked for your face being "
                "absent, more than one face in frame, or looking away from the "
                "screen for an extended period. Your microphone also stays on "
                "for the whole quiz and is checked for human speech."
            )
        else:
            st.info(
                "This quiz is monitored for academic integrity. Tab switches, "
                "window focus changes, keys you press, and mouse activity on "
                "this page are recorded automatically. You'll also be asked to "
                "share your screen and enable your microphone below — your "
                "browser will show its own permission dialog for each. Once "
                "granted, a continuous recording of your screen is saved for "
                "instructor review. Your microphone also stays on for the "
                "whole quiz and is checked for human speech."
            )

    # Mounted on every rerun, not just before the permission outcome is known
    # — it must stay mounted to keep receiving periodic "frame" trigger values
    # for as long as screen sharing is active, which can be long after the
    # initial granted/denied outcome was already recorded below.
    share_result = _screen_share_button(
        key=f"proctor_share_{session_id}",
        data=video_quality_data,
        on_screen_share_change=lambda: None,
        on_frame_change=lambda: None,
        on_video_chunk_change=lambda: None,
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

    if share_result.video_chunk is not None:
        chunk = share_result.video_chunk
        save_proctor_video_segment(
            session_id, user_id, quiz_id, assessment_id,
            chunk.get("kind"), chunk.get("seq"), chunk.get("data"),
        )

    # Same always-mounted pattern as the screen-share button above, for the
    # webcam permission prompt and its periodic frame captures — only when
    # the admin has webcam recording enabled (see webcam_recording_enabled
    # above). When disabled, this component is never mounted, so the browser
    # never prompts for camera permission and no frames/video/face-gaze
    # analysis are produced for this session.
    if webcam_recording_enabled:
        webcam_result = _webcam_monitor_button(
            key=f"proctor_webcam_{session_id}",
            data=video_quality_data,
            on_webcam_change=lambda: None,
            on_frame_change=lambda: None,
            on_video_chunk_change=lambda: None,
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

        if webcam_result.video_chunk is not None:
            chunk = webcam_result.video_chunk
            save_proctor_video_segment(
                session_id, user_id, quiz_id, assessment_id,
                chunk.get("kind"), chunk.get("seq"), chunk.get("data"),
            )

    # Same always-mounted pattern as the screen-share/webcam buttons above,
    # for the microphone permission prompt and its continuous recording (see
    # _AUDIO_MONITOR_JS — the mic itself never stops for the session; "clip"
    # trigger values arrive one per fixed-length segment).
    audio_result = _audio_monitor_button(
        key=f"proctor_audio_{session_id}",
        on_audio_change=lambda: None,
        on_clip_change=lambda: None,
    )

    if audio_result.audio is not None and audio_key not in st.session_state:
        outcome = audio_result.audio
        granted = bool(outcome.get("granted"))
        st.session_state[audio_key] = "granted" if granted else "denied"
        save_proctor_event(
            session_id, user_id, quiz_id, assessment_id,
            "audio_granted" if granted else "audio_denied",
        )

    if audio_result.clip is not None:
        save_proctor_audio_clip(session_id, user_id, quiz_id, assessment_id, audio_result.clip.get("data"))

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

    # ---- Always-on mouse-activity logger ----
    # Same always-mounted, buffered-batch pattern as the keystroke logger
    # above — clicks, throttled movement samples, and cursor leave/re-enter
    # of the browser window.
    mouse_result = _mouse_monitor(
        key=f"proctor_mouse_{session_id}",
        on_mouse_events_change=lambda: None,
    )
    if mouse_result.mouse_events is not None:
        save_proctor_mouse_events(
            session_id, user_id, quiz_id, assessment_id,
            mouse_result.mouse_events.get("events", []),
        )

    # Webcam face/gaze flags (no_face/multiple_faces/looking_away) and
    # detected-speech audio clips are intentionally not surfaced here or as a
    # live st.warning() the way tab-switch/focus-loss is above — a single
    # misread frame, or a moment of ambient noise picked up as speech, is too
    # noisy a signal to interrupt a student over, so they're only ever
    # visible to an instructor reviewing this session afterwards (see
    # get_proctor_webcam_summary() / get_proctor_audio_summary()).
    if st.session_state[count_key]:
        st.caption(
            f"🔴 Monitoring active — {st.session_state[count_key]} "
            "tab-switch/focus warning(s) recorded this session."
        )
    elif webcam_recording_enabled:
        st.caption(
            "🟢 Monitoring active — tab switches, focus loss, keystrokes, "
            "mouse activity, and (once enabled) your camera and microphone "
            "are being recorded."
        )
    else:
        st.caption(
            "🟢 Monitoring active — tab switches, focus loss, keystrokes, "
            "mouse activity, and (once enabled) your microphone are being "
            "recorded."
        )

    return session_id
