# =============================================================================
# access_gate.py — per-exam access code gate
# =============================================================================
# Renders an access-code prompt that a student must clear before reaching
# identity verification / proctoring / the assessment itself. Mirrors the
# session-state caching pattern used by verify_student_identity() in
# exam_verification_feature.py so the two gates can be chained: access code
# first, then identity verification, at each of the three assessment
# entry points (exam_grading_feature.py, quiz_generator_feature.py,
# oral_examination_feature.py).
# =============================================================================

import streamlit as st


def verify_access_code(required_code: str, gate_key: str) -> bool:
    """
    Render an access-code prompt and return True once the student has
    entered the matching code — or immediately if no code is required.

    Args:
        required_code: The code set by the instructor for this quiz/exam/
            oral exam, or None/blank if no code is required.
        gate_key: Namespaces session state and widget keys so multiple gates
            (e.g. one per assessment) can be active on the same page without
            colliding — pass the same gate_key used for verify_student_identity()
            at the same call site.

    Returns:
        True if no code is required, or the student has already entered the
        correct code this session. False otherwise (renders the prompt).
    """
    if not required_code or not str(required_code).strip():
        return True

    state_key = f"code_ok_{gate_key}"
    if st.session_state.get(state_key):
        return True

    st.warning("This assessment requires an access code from your instructor.")
    entered = st.text_input("Access code", type="password", key=f"{gate_key}_access_code_input")
    if st.button("Submit Code", key=f"{gate_key}_access_code_submit"):
        if entered.strip() == str(required_code).strip():
            st.session_state[state_key] = True
            st.rerun()
        else:
            st.error("Incorrect access code.")

    return False
