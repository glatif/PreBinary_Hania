# =============================================================================
# exam_verification_feature.py
# =============================================================================
# Identity verification gate for exam/quiz submission.
#
# At submission time the student shows an ID document to the camera and
# takes a live selfie. The document is OCR'd (EasyOCR) to read the printed
# name, which is checked against the student's profile record
# (users.first_name / last_name). The selfie and the photo on the document
# are then compared with DeepFace's face verification model. The text match
# and the face match must both pass before the gate opens.
#
# Multiple BC/Canada document types are accepted, auto-detected from
# keywords in the OCR text (see detect_document_type):
#   student_card              Institution-issued student ID card. The only
#                              type that carries a roll number, so it's the
#                              only type the roll number check applies to.
#   bc_drivers_licence         BC driver's licence (issued by ICBC).
#   bc_services_card_or_bcid   BC Services Card or non-driver BCID — same
#                              card layout family.
#   other_gov_id                Any other Canadian government photo ID
#                              (passport, another province's licence, etc.)
#                              — looser, name-only matching.
# Government-issued types (everything but student_card) also get an expiry
# check: if an EXP date is found on the card and it's in the past, the
# attempt fails. A missing/unparseable date is treated as inconclusive
# rather than a failure, since OCR misreads on small printed dates are
# common and shouldn't lock a student out.
#
# DeepFace and EasyOCR are imported lazily inside the functions that need
# them, not at module load time — both trigger TensorFlow / model loading
# that is too expensive to pay on every Streamlit rerun of pages that never
# reach this feature.
# =============================================================================

import re
import difflib
from datetime import date

import numpy as np
import streamlit as st
from PIL import Image

from db import get_connection


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
# DOCUMENT TYPE — which kind of ID card was shown
# =============================================================================

DOCUMENT_TYPE_LABELS = {
    "student_card": "Institution Student ID Card",
    "bc_drivers_licence": "BC Driver's Licence",
    "bc_services_card_or_bcid": "BC Services Card / BCID",
    "other_gov_id": "Other Canadian Government ID",
}

# Document types that carry a government-printed expiry date worth checking.
_EXPIRING_DOCUMENT_TYPES = {"bc_drivers_licence", "bc_services_card_or_bcid", "other_gov_id"}


def detect_document_type(ocr_text: str) -> str:
    """
    Guess which kind of ID document was scanned, from keywords commonly
    printed on the front of each card type.

    BC-specific types are checked before the generic "other_gov_id" bucket
    so a BC driver's licence (which also prints "CANADA") doesn't get
    miscategorized as a passport/out-of-province licence. Falls back to
    "student_card" when nothing matches, so plain institution cards (which
    don't carry any of these keywords) keep working exactly as before.
    """
    norm = _normalize(ocr_text)

    if _fuzzy_contains(norm, _normalize("BRITISH COLUMBIA")) and (
        _fuzzy_contains(norm, _normalize("DRIVER"))
        or _fuzzy_contains(norm, _normalize("ICBC"))
    ):
        return "bc_drivers_licence"

    if _fuzzy_contains(norm, _normalize("BRITISH COLUMBIA")) and (
        _fuzzy_contains(norm, _normalize("SERVICES CARD"))
        or _fuzzy_contains(norm, _normalize("IDENTIFICATION CARD"))
    ):
        return "bc_services_card_or_bcid"

    if _fuzzy_contains(norm, _normalize("CANADA")) and (
        _fuzzy_contains(norm, _normalize("PASSPORT"))
        or _fuzzy_contains(norm, _normalize("DRIVER"))
        or _fuzzy_contains(norm, _normalize("LICENCE"))
        or _fuzzy_contains(norm, _normalize("LICENSE"))
    ):
        return "other_gov_id"

    return "student_card"


# Matches an EXP/EXPIRY label followed by a date in either YYYY/MM/DD
# (numeric month) or YYYY/MMM/DD (3-letter month abbreviation) form — the
# two formats ICBC/BC government cards print expiry and birth dates in.
_EXPIRY_PATTERN = re.compile(
    r"EXP[A-Z]*[.:\s]+(\d{4})[/\-\s]([A-Z]{3}|\d{1,2})[/\-\s](\d{1,2})"
)

_MONTH_ABBREVIATIONS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _extract_expiry_date(ocr_text: str):
    """
    Look for an expiry date next to an EXP/EXPIRY label in the OCR text.

    Returns a date, or None when no recognisable date is found — e.g. on a
    student card (which has no expiry field) or when OCR failed to read a
    small printed date cleanly. Callers treat None as inconclusive, not as
    a failure.
    """
    match = _EXPIRY_PATTERN.search(ocr_text.upper())
    if not match:
        return None
    year_str, month_str, day_str = match.groups()
    month = _MONTH_ABBREVIATIONS.get(month_str)
    if month is None:
        try:
            month = int(month_str)
        except ValueError:
            return None
    try:
        return date(int(year_str), month, int(day_str))
    except ValueError:
        return None


def check_expiry(ocr_text: str) -> dict:
    """
    Return {"expiry_date": date|None, "expired": bool|None}.

    expired is None (inconclusive) when no expiry date could be parsed out
    of the OCR text, rather than defaulting to True/False — an unreadable
    date shouldn't silently pass or silently lock a student out.
    """
    expiry_date = _extract_expiry_date(ocr_text)
    if expiry_date is None:
        return {"expiry_date": None, "expired": None}
    return {"expiry_date": expiry_date, "expired": expiry_date < date.today()}


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
# AUDIT LOG — one row per verification attempt, pass or fail
# =============================================================================

def _log_verification_attempt(
    student: dict,
    gate_key: str,
    document_type: str,
    text_result: dict,
    expiry_result: dict,
    face_result: dict,
    roll_check_applies: bool,
    passed: bool,
) -> None:
    """Persist this attempt to verification_attempts so every check on a
    student's identity (document type, name read off the card, roll/T-ID
    read off the card, expiry, and whether the face matched) is auditable
    after the fact."""
    expected_name = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO verification_attempts
                (user_id, gate_key, document_type, expected_name, expected_roll_no,
                 ocr_text, name_matched, roll_matched, expiry_date, expired,
                 face_matched, face_distance, face_threshold, face_error, passed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                student.get("id"),
                gate_key,
                document_type,
                expected_name,
                student.get("roll_no") or None,
                text_result.get("ocr_text"),
                text_result["name_ok"],
                text_result["roll_ok"] if roll_check_applies else None,
                expiry_result.get("expiry_date"),
                expiry_result.get("expired"),
                face_result.get("verified", False),
                face_result.get("distance"),
                face_result.get("threshold"),
                face_result.get("error"),
                passed,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


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
        "Show an ID document to the camera — your institution student card, "
        "a BC driver's licence, a BC Services Card / BCID, or another "
        "Canadian government photo ID — then take a clear selfie. Both will "
        "be checked against your profile before the exam unlocks."
    )

    col1, col2 = st.columns(2)
    with col1:
        id_card_shot = st.camera_input("Step 1 — ID Document", key=f"{gate_key}_id_card")
    with col2:
        selfie_shot = st.camera_input("Step 2 — Your Face", key=f"{gate_key}_selfie")

    if not st.button("Verify Identity", key=f"{gate_key}_verify_btn", type="primary"):
        return False

    if not id_card_shot or not selfie_shot:
        st.error("Please capture both your ID document and a selfie before verifying.")
        return False

    id_card_image = Image.open(id_card_shot)
    selfie_image  = Image.open(selfie_shot)

    with st.spinner("Reading ID document..."):
        ocr_text      = _extract_id_card_text(id_card_image)
        document_type = detect_document_type(ocr_text)
        text_result   = check_id_card_text(
            ocr_text,
            student.get("first_name") or "",
            student.get("last_name") or "",
            student.get("roll_no") or "",
        )
        expiry_result = (
            check_expiry(ocr_text)
            if document_type in _EXPIRING_DOCUMENT_TYPES
            else {"expiry_date": None, "expired": None}
        )

    with st.spinner("Comparing faces..."):
        face_result = check_face_match(id_card_image, selfie_image)

    # A roll number is only ever printed on the institution's own student
    # card — government IDs have no reason to carry it, so don't penalize
    # those for lacking one.
    roll_check_applies = document_type == "student_card" and bool(student.get("roll_no"))

    # ---- Show what was checked, regardless of outcome ----
    name_label = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
    st.markdown("**Verification results:**")
    st.write(f"📄 Document type detected: {DOCUMENT_TYPE_LABELS[document_type]}")
    st.write(f"{'✅' if text_result['name_ok'] else '❌'} Name on ID matches profile ({name_label})")
    if roll_check_applies:
        st.write(
            f"{'✅' if text_result['roll_ok'] else '❌'} "
            f"Roll number on ID matches profile ({student['roll_no']})"
        )
    elif document_type == "student_card":
        st.caption("No roll number on file for this account — skipping roll number check.")

    if expiry_result["expiry_date"] is not None:
        if expiry_result["expired"]:
            st.write(f"❌ Document expired on {expiry_result['expiry_date'].isoformat()}")
        else:
            st.write(f"✅ Document valid until {expiry_result['expiry_date'].isoformat()}")
    elif document_type in _EXPIRING_DOCUMENT_TYPES:
        st.caption("Could not read an expiry date off this document — skipping expiry check.")

    if "error" in face_result:
        st.write(f"❌ Face match: {face_result['error']}")
    else:
        st.write(f"{'✅' if face_result['verified'] else '❌'} Face on ID matches your live photo")

    # Roll number is optional on the profile — only enforce it when the
    # student actually has one on file and the document type carries one.
    roll_required_ok = text_result["roll_ok"] if roll_check_applies else True
    expiry_ok = not expiry_result["expired"]  # None (inconclusive) or False both pass
    passed = (
        text_result["name_ok"]
        and roll_required_ok
        and expiry_ok
        and face_result.get("verified", False)
    )

    _log_verification_attempt(
        student, gate_key, document_type, text_result, expiry_result,
        face_result, roll_check_applies, passed,
    )

    if passed:
        st.session_state[state_key] = True
        st.success("Identity verified. Loading exam...")
        st.rerun()
        return True

    st.error("Verification failed. Please retake the photos and try again.")
    with st.expander("Raw text detected on ID card (for troubleshooting)"):
        st.code(ocr_text or "(no text detected)")
    return False
