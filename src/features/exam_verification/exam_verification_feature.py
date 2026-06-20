# =============================================================================
# exam_verification_feature.py
# =============================================================================
# Identity verification gate for exam/quiz submission.
#
# At submission time the student shows their institution ID card to the
# camera and takes a live selfie. The ID card is OCR'd (EasyOCR) to read the
# printed name and roll number, which are checked against the student's
# profile record (users.first_name / last_name / roll_no). The selfie and
# the photo on the ID card are then compared with DeepFace's face
# verification model. Both the text match and the face match must pass
# before the gate opens.
#
# DeepFace and EasyOCR are imported lazily inside the functions that need
# them, not at module load time — both trigger TensorFlow / model loading
# that is too expensive to pay on every Streamlit rerun of pages that never
# reach this feature.
# =============================================================================

import re
import difflib

import numpy as np
import streamlit as st
from PIL import Image


# =============================================================================
# OCR — reading the ID card
# =============================================================================

@st.cache_resource(show_spinner=False)
def _get_ocr_reader():
    """Build (once per process) the EasyOCR reader used to read ID cards."""
    import easyocr
    return easyocr.Reader(["en"], gpu=False)


def _normalize(text: str) -> str:
    """Uppercase and strip everything but letters/digits for fuzzy matching."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _extract_id_card_text(image: Image.Image) -> str:
    """Run OCR over the ID card photo and return the concatenated raw text."""
    reader = _get_ocr_reader()
    results = reader.readtext(np.array(image.convert("RGB")))
    return " ".join(text for _, text, _ in results)


def _fuzzy_contains(haystack_norm: str, needle_norm: str, threshold: float = 0.8) -> bool:
    """
    Return True if needle_norm appears in haystack_norm, tolerating OCR noise.

    Tries an exact substring match first (cheap, common case). Falls back to
    a sliding-window similarity ratio so minor OCR misreads (e.g. 0 vs O,
    1 vs I) don't cause a false rejection.
    """
    if not needle_norm:
        return False
    if needle_norm in haystack_norm:
        return True
    window = len(needle_norm)
    if window == 0 or len(haystack_norm) < window:
        return False
    best = 0.0
    step = max(1, window // 4)
    for start in range(0, len(haystack_norm) - window + 1, step):
        chunk = haystack_norm[start:start + window]
        ratio = difflib.SequenceMatcher(None, chunk, needle_norm).ratio()
        best = max(best, ratio)
    return best >= threshold


def check_id_card_text(ocr_text: str, first_name: str, last_name: str, roll_no: str) -> dict:
    """
    Compare OCR'd ID card text against the student's profile fields.

    Returns per-field booleans plus the raw OCR text, so the caller can both
    gate on overall success and show the student exactly what was found.
    """
    norm_text = _normalize(ocr_text)

    name_ok = (
        _fuzzy_contains(norm_text, _normalize(first_name))
        and _fuzzy_contains(norm_text, _normalize(last_name))
    )
    roll_ok = _fuzzy_contains(norm_text, _normalize(roll_no)) if roll_no else False

    return {
        "ocr_text": ocr_text,
        "name_ok": name_ok,
        "roll_ok": roll_ok,
    }


# =============================================================================
# FACE MATCH — ID card photo vs. live selfie
# =============================================================================

def check_face_match(id_card_image: Image.Image, selfie_image: Image.Image) -> dict:
    """
    Compare the face on the ID card photo against the live selfie.

    DeepFace expects BGR arrays (OpenCV convention); PIL decodes to RGB, so
    the channel order is reversed before handing the arrays over.

    Returns 'verified' (bool) and 'distance'/'threshold' on success, or an
    'error' message when DeepFace could not detect a face in either image
    (e.g. card glare, selfie out of frame) — surfaced to the student as a
    retake prompt rather than a crash.
    """
    from deepface import DeepFace

    def _to_bgr(image: Image.Image) -> np.ndarray:
        return np.array(image.convert("RGB"))[:, :, ::-1]

    try:
        result = DeepFace.verify(
            img1_path=_to_bgr(id_card_image),
            img2_path=_to_bgr(selfie_image),
            model_name="VGG-Face",
            enforce_detection=True,
        )
        return {
            "verified": bool(result["verified"]),
            "distance": result["distance"],
            "threshold": result["threshold"],
        }
    except ValueError as exc:
        return {"verified": False, "error": str(exc)}


# =============================================================================
# UI GATE
# =============================================================================

def verify_student_identity(student: dict, gate_key: str) -> bool:
    """
    Render the ID-card + selfie identity check and return True once the
    student has passed both the text match and the face match.

    gate_key namespaces session state and widget keys so multiple gates
    (e.g. one per quiz) can be active on the same page without colliding.
    The verified result is cached in session state under
    f"verified_{gate_key}" so the student is not re-prompted on every
    Streamlit rerun once they have passed.
    """
    state_key = f"verified_{gate_key}"
    if st.session_state.get(state_key):
        return True

    st.warning("Identity verification is required before you can access this exam.")
    st.caption(
        "Show your student ID card to the camera, then take a clear selfie. "
        "Both will be checked against your profile before the exam unlocks."
    )

    col1, col2 = st.columns(2)
    with col1:
        id_card_shot = st.camera_input("Step 1 — ID Card", key=f"{gate_key}_id_card")
    with col2:
        selfie_shot = st.camera_input("Step 2 — Your Face", key=f"{gate_key}_selfie")

    if not st.button("Verify Identity", key=f"{gate_key}_verify_btn", type="primary"):
        return False

    if not id_card_shot or not selfie_shot:
        st.error("Please capture both your ID card and a selfie before verifying.")
        return False

    id_card_image = Image.open(id_card_shot)
    selfie_image  = Image.open(selfie_shot)

    with st.spinner("Reading ID card..."):
        ocr_text    = _extract_id_card_text(id_card_image)
        text_result = check_id_card_text(
            ocr_text,
            student.get("first_name") or "",
            student.get("last_name") or "",
            student.get("roll_no") or "",
        )

    with st.spinner("Comparing faces..."):
        face_result = check_face_match(id_card_image, selfie_image)

    # ---- Show what was checked, regardless of outcome ----
    name_label = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
    st.markdown("**Verification results:**")
    st.write(f"{'✅' if text_result['name_ok'] else '❌'} Name on ID matches profile ({name_label})")
    if student.get("roll_no"):
        st.write(
            f"{'✅' if text_result['roll_ok'] else '❌'} "
            f"Roll number on ID matches profile ({student['roll_no']})"
        )
    else:
        st.caption("No roll number on file for this account — skipping roll number check.")

    if "error" in face_result:
        st.write(f"❌ Face match: {face_result['error']}")
    else:
        st.write(f"{'✅' if face_result['verified'] else '❌'} Face on ID matches your live photo")

    # Roll number is optional on the profile — only enforce it when the
    # student actually has one on file.
    roll_required_ok = text_result["roll_ok"] if student.get("roll_no") else True
    passed = text_result["name_ok"] and roll_required_ok and face_result.get("verified", False)

    if passed:
        st.session_state[state_key] = True
        st.success("Identity verified. Loading exam...")
        st.rerun()
        return True

    st.error("Verification failed. Please retake the photos and try again.")
    with st.expander("Raw text detected on ID card (for troubleshooting)"):
        st.code(ocr_text or "(no text detected)")
    return False
