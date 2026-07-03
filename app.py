# =============================================================================
# app.py — Prebinary × UReap Integration
# =============================================================================
# Main Streamlit application entry point.
#
# Architecture overview:
#   - All page routing is driven by st.session_state.current_page, which is
#     set by the sidebar navigation rendered on every authenticated view.
#     Valid current_page values: "dashboard", "profile", "admin_panel".
#   - Hierarchical navigation state (view_level, selected_course,
#     selected_assessment) is initialised here and will be used when course
#     management is introduced in a future sprint.
#   - Delete confirmations use @st.dialog modal popups throughout to avoid
#     inline warning clutter.
#   - Bulk data_editor tables are available to admin users in the Admin Panel.
#   - All validation is delegated to validators.py before any database write.
#   - strip() is applied to all text inputs at submission time, never at
#     widget declaration time (which would run on every render). Passwords
#     are never stripped, as leading/trailing whitespace is intentional.
# =============================================================================

# =============================================================================
# TORCH PATCH
# =============================================================================
# PyTorch's torch._classes module triggers a Streamlit file-watcher
# compatibility error on startup. The patch below intercepts attribute access
# on torch._classes before Streamlit's watcher initialises, preventing the
# crash. It must appear before all other imports so it executes first.
#
# This patch is required by the RAG and Advisor AI features, which depend on
# sentence-transformers and FAISS, both of which import PyTorch.

import os
import sys
import types
import importlib.abc

try:
    class _TorchClassesFinder(importlib.abc.MetaPathFinder):
        """
        MetaPathFinder that intercepts imports of torch._classes and its
        submodules, replacing them with a stub module that exposes a no-op
        __path__ attribute. This prevents Streamlit's file watcher from
        raising an AttributeError when it inspects the module's __path__.
        """
        def find_spec(self, fullname, path, target=None):
            if fullname == "torch._classes" or fullname.startswith("torch._classes."):
                class _DummyPath:
                    _path = []

                class _DummyLoader(importlib.abc.Loader):
                    def create_module(self, spec):
                        module = types.ModuleType(fullname)
                        module.__path__ = _DummyPath()
                        return module

                    def exec_module(self, module):
                        pass

                return importlib.machinery.ModuleSpec(
                    name=fullname,
                    loader=_DummyLoader(),
                    is_package=True,
                )
            return None

    sys.meta_path.insert(0, _TorchClassesFinder())

    import torch

    class _DummyPath:
        _path = []

    if hasattr(torch, "_classes"):
        if not hasattr(torch._classes, "__path__"):
            torch._classes.__path__ = _DummyPath()

        _original_getattr = getattr(torch._classes, "__getattr__", None)

        def _safe_getattr(self, name=None):
            if name is None or name == "__path__":
                return _DummyPath()
            if _original_getattr:
                try:
                    return _original_getattr(self, name)
                except Exception:
                    pass
            raise AttributeError(
                f"{self.__class__.__name__} has no attribute '{name}'"
            )

        torch._classes.__getattr__ = _safe_getattr

        if hasattr(torch._C, "_get_custom_class_python_wrapper"):
            _original_wrapper = torch._C._get_custom_class_python_wrapper

            def _safe_wrapper(name=None, attr=None):
                if name is None or attr is None or attr == "__path__":
                    return _DummyPath()
                try:
                    return _original_wrapper(name, attr)
                except Exception:
                    return None

            torch._C._get_custom_class_python_wrapper = _safe_wrapper

except Exception as _torch_patch_error:
    print(f"Warning: torch patch could not be applied: {_torch_patch_error}")


import streamlit as st
import pandas as pd
from sqlalchemy import text

from db import get_engine
from app_validators import (
    validate_user_form,
    validate_email_field,
    validate_password,
    validate_name,
    validate_phone,
    validate_text_field,
    validate_postal_code,
    validate_api_key,
    validate_roll_no,
)
from auth import (
    signup_user,
    login_user,
    update_user_profile,
    change_user_password,
    delete_user_account,
    is_username_unique,
    is_email_unique,
    admin_reset_user_password,
    admin_create_user,
    admin_update_user_full,
    is_phone_unique,
    is_roll_no_unique,
    is_username_unique_for_update,
    is_email_unique_for_update,
    update_user_api_keys,
    update_user_model_prefs,
)
import json
import time as _time

# UReap feature render functions. Each is the top-level entry point for its
# respective tab in the dashboard. All modules live in the UReap src/ directory
# which is placed at the project root unchanged.
from src.features.rag.rag_feature import rag_ui
from src.features.exam_grading.exam_grading_feature import exam_grading_ui
from src.features.exam_creation.exam_creation_feature import exam_creation_ui
from src.features.advisor_ai.advisor_ai_feature import advisor_ai_ui
from src.features.student_wellness.student_wellness_feature import student_wellness_ui
from src.features.quiz_generator.quiz_generator_feature import quiz_generator_ui
from src.features.oral_examination.oral_examination_feature import oral_examination_ui
from src.features.narrated_slideshow.narrated_slideshow_feature import render_narrated_slideshow_feature
from src.features.proctoring.proctoring_feature import cleanup_old_proctor_data

# llm_utils.MODELS is referenced by the profile page to build per-feature model
# preference selectors and to resolve stored model IDs back to display names.
from src.utils.llm_utils import MODELS as LLM_MODELS

# =============================================================================
# DEFERRED SPRINT IMPORTS
# =============================================================================
# The following imports support course management, file handling, and quiz
# pipeline functions whose UI code remains in this file but is not yet wired
# into the active navigation. They will become part of the active import block
# when course management is implemented in a future sprint.
# Do not remove these — the functions below are still defined in this file
# and will raise NameError at runtime if called without these imports.

from app_validators import (
    validate_course_form,
    validate_assessment_form,
    validate_quiz_title,
)
from auth import (
    is_course_code_unique,
    update_course_details,
    update_assessment_details,
    save_uploaded_file,
    delete_physical_file,
    grant_course_access,
    revoke_course_access,
    duplicate_course_for_teacher,
    save_quiz,
    set_quiz_published,
    set_quiz_grades_visible,
    save_quiz_submission,
    save_grade,
)


# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="PreBinary: Redefining Learning with AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject global CSS.
# Prebinary styles: constrains the main content area to a readable max-width
#   while keeping layout="wide". Defines breadcrumb link styling for the course
#   hierarchy (retained for future sprint re-introduction).
# UReap styles: .main-header and .feature-header are used by UReap feature
#   modules via st.markdown('<h2 class="feature-header">...').
st.markdown("""
<style>
/* Constrain main content to a readable max-width while keeping layout="wide" */
.block-container {
    max-width: 1100px;
    padding-top: 2rem;
    padding-bottom: 2rem;
}

/* Breadcrumb: each clickable segment is styled as a compact inline text link.
   The aggressive reset removes all button chrome so only the text is visible.
   This is applied via a wrapper span injected around each st.button call. */
.bc-link button {
    background: none !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 2px !important;
    margin: 0 !important;
    min-height: 0 !important;
    height: auto !important;
    line-height: 1.4 !important;
    font-size: 0.85rem !important;
    color: #0066cc !important;
    text-decoration: underline !important;
    cursor: pointer !important;
    display: inline !important;
}
.bc-link button:hover {
    color: #004499 !important;
}

/* Breadcrumb separator and current page label — small, muted, inline */
.bc-sep, .bc-current {
    font-size: 0.85rem;
    color: #888;
    padding: 0 4px;
}
.bc-current {
    color: #333;
    font-weight: 600;
}

/* UReap feature header classes used by feature modules */
.main-header {
    font-size: 2.5rem;
    margin-bottom: 1rem;
}
.feature-header {
    font-size: 1.8rem;
    margin-top: 1rem;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 2rem;
}
.stTabs [data-baseweb="tab"] {
    height: 4rem;
    white-space: pre-wrap;
    font-size: 1rem;
}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# SESSION STATE INITIALISATION
# =============================================================================
# All session state keys are initialised here at startup so that downstream
# code can read them without KeyError guards.
#
# UReap feature session state keys (slideshow_*, advisor_*, quiz_*, etc.) are
# initialised by their own initialize_*_session_state() functions when each
# feature page first renders. They are not listed here.

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

# current_page drives the sidebar navigation for authenticated users.
# Valid values: "dashboard" | "profile" | "admin_panel"
# "admin_panel" is only reachable by users with role == "admin".
if "current_page" not in st.session_state:
    st.session_state.current_page = "dashboard"

# Hierarchical drill-down state shared across course/assessment/file views.
# Retained here for the course management sprint; unused in the current sprint.
# view_level: "courses" | "assessments" | "files"
if "view_level" not in st.session_state:
    st.session_state.view_level = "courses"
if "selected_course" not in st.session_state:
    st.session_state.selected_course = None
if "selected_assessment" not in st.session_state:
    st.session_state.selected_assessment = None

# Per-tab navigation state for the four course-integrated feature tabs.
# Each tab maintains independent view_level, selected_course, and
# selected_assessment so that navigating into a course under one tab
# does not affect the navigation state of any other tab.
for _tab_prefix in ("exam_grading", "exam_creation", "practice_quiz", "oral_examination"):
    if f"{_tab_prefix}_view_level" not in st.session_state:
        st.session_state[f"{_tab_prefix}_view_level"] = "courses"
    if f"{_tab_prefix}_selected_course" not in st.session_state:
        st.session_state[f"{_tab_prefix}_selected_course"] = None
    if f"{_tab_prefix}_selected_assessment" not in st.session_state:
        st.session_state[f"{_tab_prefix}_selected_assessment"] = None

# Admin Panel Courses tab navigation state. Tracks whether the admin is
# viewing the course list or the assessment list for a selected course.
# Kept separate from all feature-tab and global nav keys.
if "admin_panel_view_level" not in st.session_state:
    st.session_state.admin_panel_view_level = "courses"
if "admin_panel_selected_course" not in st.session_state:
    st.session_state.admin_panel_selected_course = None




# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def logout():
    """Clear all session state and return to the login screen."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def _nav_key(base: str, tab_key: str | None = None) -> str:
    """
    Return a session state or widget key namespaced to the given tab.

    When tab_key is provided (e.g. 'exam_grading'), the returned key is
    '{tab_key}_{base}' (e.g. 'exam_grading_view_level'). This prevents
    DuplicateWidgetID errors when Streamlit renders all four feature tabs
    simultaneously in the DOM.

    When tab_key is None the base key is returned unchanged, preserving
    backwards-compatible behaviour for callers that predate per-tab navigation.
    """
    return f"{tab_key}_{base}" if tab_key else base


def reset_navigation(tab_key=None):
    """
    When tab_key is provided, resets only that tab's three per-tab navigation
    keys (e.g. 'exam_grading_view_level', 'exam_grading_selected_course',
    'exam_grading_selected_assessment'). This allows each of the four feature
    tabs to be independently reset without disturbing the others.

    When tab_key is None, resets the global navigation keys used by the shared
    render_hierarchy_dashboard() entry point. Called with no argument when the
    user navigates to Profile or Admin Panel so the global state is also cleared.
    """
    if tab_key:
        st.session_state[f"{tab_key}_view_level"] = "courses"
        st.session_state[f"{tab_key}_selected_course"] = None
        st.session_state[f"{tab_key}_selected_assessment"] = None
    else:
        st.session_state.view_level = "courses"
        st.session_state.selected_course = None
        st.session_state.selected_assessment = None




def show_errors(errors: list[str]):
    """
    Display a list of validation error strings, one st.error per message.
    Callers pass the list returned by validators.py composite functions.
    """
    for msg in errors:
        st.error(msg)


def render_address_fields(
    key_prefix: str,
    *,
    street_value: str = "",
    city_value: str = "",
    state_value: str = "",
    postal_value: str = "",
    country_value: str = "",
) -> tuple[str, str, str, str, str]:
    """
    Render the standard five-field address block used by signup, profile,
    and admin user forms.

    Widget keys are namespaced via key_prefix to prevent collisions when
    multiple address blocks appear in the same Streamlit session (e.g. the
    profile form and an admin dialog both on the same page load). Each caller
    supplies a unique prefix such as "signup", "profile", or "edit_user".

    This helper may be called inside a st.form() block — all widgets it
    renders participate in the enclosing form's submit cycle normally.

    Returns raw widget values in (street, city, state/province, postal code,
    country) order so callers can apply their own submission-time transforms.
    """
    st.markdown("**Address**")
    street = st.text_input("Street Address", value=street_value, key=f"{key_prefix}_street")
    ad1, ad2 = st.columns(2)
    with ad1:
        city        = st.text_input("City",        value=city_value,   key=f"{key_prefix}_city")
        postal_code = st.text_input("Postal Code", value=postal_value, key=f"{key_prefix}_postal")
    with ad2:
        state_prov = st.text_input("State / Province", value=state_value,   key=f"{key_prefix}_state")
        country    = st.text_input("Country",           value=country_value, key=f"{key_prefix}_country")
    return street, city, state_prov, postal_code, country

def get_course_permission_context(engine, course_id: int) -> dict:
    """
    Resolve the current user's effective permissions for a specific course.

    Permission rules implemented here:

      - Admins can view, edit content, manage sharing, and delete courses.
      - The teacher who created (owns) the course — identified by
        courses.instructor_id — can view the course, create/edit/delete
        assessments, manage course sharing, and delete the course itself.
      - Teachers who have been granted access to a course by an owner or admin
        can view the course and its assessments in read-only mode only. They
        cannot create, modify, or delete assessments, and they cannot open the
        Access management tab. The Duplicate action lets a granted teacher
        produce their own independently-owned copy of the course that they can
        then edit freely.
      - Students with approved student access can view course content only.

    Centralising these checks keeps the course, assessment, file, and sharing
    views consistent and avoids duplicating access logic across the UI.
    """
    user = st.session_state.user
    uid  = int(user["id"])
    role = str(user.get("role") or "")

    course_row = pd.read_sql(
        text("SELECT id, instructor_id FROM courses WHERE id = :cid"),
        engine,
        params={"cid": int(course_id)},
    )
    if course_row.empty:
        return {
            "exists": False,
            "is_admin": False,
            "is_owner": False,
            "has_teacher_access": False,
            "has_student_access": False,
            "can_view": False,
            "can_manage_sharing": False,
            "can_edit_content": False,
            "can_delete_course": False,
            "is_student_read_only": False,
        }

    instructor_id = int(course_row.iloc[0]["instructor_id"])

    is_admin = role == "admin"
    is_owner = role == "teacher" and instructor_id == uid

    access_row = pd.read_sql(
        text("""
            SELECT access_role, status
            FROM course_access
            WHERE course_id = :cid AND user_id = :uid
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        engine,
        params={"cid": int(course_id), "uid": uid},
    )

    has_teacher_access = False
    has_student_access = False

    if not access_row.empty:
        access_role = str(access_row.iloc[0]["access_role"])
        status      = str(access_row.iloc[0]["status"])
        has_teacher_access = access_role == "teacher" and status == "approved"
        has_student_access = access_role == "student" and status == "approved"

    # A granted teacher (has_teacher_access but not is_owner) can view the
    # course but cannot edit its content or manage its sharing. Only the
    # course owner and admins hold those elevated permissions.
    can_view           = is_admin or has_teacher_access or has_student_access
    can_manage_sharing = is_admin or is_owner
    can_edit_content   = is_admin or is_owner
    can_delete_course  = is_admin or is_owner

    # is_student_read_only is True for anyone who can view but cannot edit.
    # This covers granted teachers as well as students, giving all read-only
    # viewers the same informational UI treatment in the assessment and files views.
    is_read_only = can_view and not can_edit_content

    return {
        "exists": True,
        "is_admin": is_admin,
        "is_owner": is_owner,
        "has_teacher_access": has_teacher_access,
        "has_student_access": has_student_access,
        "can_view": can_view,
        "can_manage_sharing": can_manage_sharing,
        "can_edit_content": can_edit_content,
        "can_delete_course": can_delete_course,
        # is_student_read_only now covers granted teachers as well as students
        # so that all read-only viewers receive the same UI treatment.
        "is_student_read_only": is_read_only,
    }


# =============================================================================
# GLOBAL LAYOUT COMPONENTS
# =============================================================================

def render_sidebar():
    """
    Sidebar displayed for all authenticated users.
    Contains the Prebinary Learning Platform heading, page navigation buttons
    and logout at the top, followed by the original UReap informational sidebar
    content: About, Features, Models, Default Model Selection, GitHub link,
    and tagline.
    """
    with st.sidebar:
        user = st.session_state.user

        st.markdown("### Prebinary Learning Platform")
        st.divider()

        # ── Navigation buttons ────────────────────────────────────────────────
        dash_label = "**Dashboard**" if st.session_state.current_page == "dashboard" else "Dashboard"
        if st.button(dash_label, key="nav_dashboard", width="stretch"):
            st.session_state.current_page = "dashboard"
            st.rerun()

        prof_label = "**Profile**" if st.session_state.current_page == "profile" else "Profile"
        if st.button(prof_label, key="nav_profile", width="stretch"):
            st.session_state.current_page = "profile"
            # Reset global nav state, all three per-tab nav states, and the
            # admin panel courses nav so all views return to their course list.
            reset_navigation()
            for _tk in ("exam_grading", "exam_creation", "practice_quiz", "oral_examination"):
                reset_navigation(_tk)
            st.session_state.admin_panel_view_level = "courses"
            st.session_state.admin_panel_selected_course = None
            st.rerun()

        if user.get("role") == "admin":
            admin_label = (
                "**Admin Panel**"
                if st.session_state.current_page == "admin_panel"
                else "Admin Panel"
            )
            if st.button(admin_label, key="nav_admin_panel", width="stretch"):
                st.session_state.current_page = "admin_panel"
                # Reset dashboard nav and admin panel courses nav so both
                # return to their course lists when the page is re-entered.
                reset_navigation()
                for _tk in ("exam_grading", "exam_creation", "practice_quiz", "oral_examination"):
                    reset_navigation(_tk)
                st.session_state.admin_panel_view_level = "courses"
                st.session_state.admin_panel_selected_course = None
                st.rerun()

        st.divider()
        if st.button("Log Out", width="stretch"):
            logout()

        # ── About ─────────────────────────────────────────────────────────────
        st.title("About")
        st.write("This application integrates multiple AI features using local and cloud LLMs.")

        with st.expander("📋 Features"):
            st.markdown("""
            - **RAG System**: Query documents with semantic search
            - **Exam Grading**: Automate grading of student submissions
            - **Exam Creation**: Generate variations of exam questions
            - **Advisor AI**: Query professor and course information
            - **Student Wellness**: Access TRU health and wellness services
            - **Quiz Generator**: Create interactive quizzes from study materials
            - **Narrated Slideshow**: Generate auto-narrated presentations from PDFs/PPTs
            """)

        with st.expander("🤖 Models"):
            st.markdown("""
            This application supports:
            - **Local models** (via Ollama):
              - DeepSeek R1: 1.5B
              - Llama 3.2
            - **Cloud models** (API key required):
              - Groq (Llama 3.3)
              - Google Gemini
              - OpenAI (GPT-4o)
              - GitHub Models (GPT-4o)
            """)

        with st.expander("⚙️ Default Model Selection per Feature"):
            st.write("Set preferences in profile.")

        st.markdown("""
---
🌟 **Explore the Project**:  
[GitHub Repository](https://github.com/glatif/AI_Instructor)  
Dive into the source code and contribute to the project!
""", unsafe_allow_html=True)

        st.caption("AI Instructor: A tool for Instructors 📚, Students 🎓 and Researchers 🔬 ")


def render_breadcrumb(tab_key=None):
    """
    Compact breadcrumb navigation rendered at the top of the assessments
    and files views. Each parent segment is a minimal text-link button that
    navigates back to that level and clears deeper selection state.

    When tab_key is provided (e.g. 'exam_grading'), per-tab session state
    keys are read and written so breadcrumb navigation is isolated to that
    tab and does not affect any other tab's position in the hierarchy.

    When tab_key is None, the global navigation keys are used as before,
    preserving backwards-compatible behaviour for render_hierarchy_dashboard().

    Widget keys include tab_key to prevent DuplicateWidgetID errors when all
    three feature tabs are rendered simultaneously by Streamlit.

    Breadcrumb structure:
      Courses › [Course Name]               (assessments level)
      Courses › [Course Name] › [Title]     (files level)
    """
    # Read navigation state from the correct key set for this tab.
    course     = st.session_state.get(_nav_key("selected_course",     tab_key))
    assessment = st.session_state.get(_nav_key("selected_assessment", tab_key))
    level      = st.session_state.get(_nav_key("view_level",          tab_key), "courses")

    # Build segment list: (label, target_level, is_current)
    # Build the course label as "Name CODE" when a course code is available.
    if course:
        course_label = (
            f"{course['name']} {course['code']}"
            if course.get("code")
            else course["name"]
        )
    else:
        course_label = "Course"

    if level == "assessments":
        segments = [
            ("Courses", "courses", False),
            (course_label, "assessments", True),
        ]
    else:  # files
        segments = [
            ("Courses", "courses", False),
            (course_label, "assessments", False),
            (assessment["title"] if assessment else "Files", "files", True),
        ]

    # Render one column per segment plus a separator column between each pair,
    # then a trailing spacer to fill the row.
    num_segs = len(segments)
    col_spec = []
    for i in range(num_segs):
        col_spec.append(0.14)
        if i < num_segs - 1:
            col_spec.append(0.05)  # separator column
    col_spec.append(max(0.01, 1.0 - sum(col_spec)))  # trailing spacer

    cols    = st.columns(col_spec)
    col_idx = 0

    for i, (label, target_level, is_cur) in enumerate(segments):
        if is_cur:
            cols[col_idx].markdown(
                f'<span class="bc-current">{label}</span>',
                unsafe_allow_html=True,
            )
        else:
            with cols[col_idx]:
                st.markdown('<span class="bc-link">', unsafe_allow_html=True)
                # Widget keys include tab_key to prevent DuplicateWidgetID errors
                # when all three feature tab breadcrumbs render simultaneously.
                btn_key = (
                    f"bc_{tab_key}_{target_level}" if tab_key else f"bc_{target_level}"
                )
                if st.button(label, key=btn_key):
                    # Write navigation state back to the correct key set.
                    st.session_state[_nav_key("view_level", tab_key)] = target_level
                    if target_level == "courses":
                        st.session_state[_nav_key("selected_course",     tab_key)] = None
                        st.session_state[_nav_key("selected_assessment", tab_key)] = None
                    elif target_level == "assessments":
                        st.session_state[_nav_key("selected_assessment", tab_key)] = None
                    st.rerun()
                st.markdown('</span>', unsafe_allow_html=True)
        col_idx += 1
        if i < num_segs - 1:
            cols[col_idx].markdown('<span class="bc-sep">/</span>', unsafe_allow_html=True)
            col_idx += 1

    st.divider()


# =============================================================================
# DIALOG MODALS
# =============================================================================
# All destructive confirmations and the admin user edit form are implemented
# as @st.dialog modals. This keeps the main page clean and makes destructive
# actions unambiguous. Dialogs are defined centrally so they can be triggered
# from any view without duplicating confirmation UI.

@st.dialog("Delete User Account")
def dialog_delete_user(user_id: int, username: str):
    """
    Confirmation modal for permanently deleting a user account.
    Triggered by the Delete button in the admin Users tab.
    """
    st.warning(
        f"You are about to permanently delete the account for **{username}**. "
        "This will remove all associated data and cannot be undone."
    )
    col1, col2 = st.columns(2)
    if col1.button("Delete Permanently", type="primary", width="stretch"):
        delete_user_account(user_id)
        st.toast(f"User '{username}' has been deleted.")
        st.rerun()
    if col2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Edit User")
def dialog_edit_user(user_row):
    """
    Full user edit form presented as a modal dialog.
    Triggered when an admin selects a user row and clicks Edit.
    All field validation and uniqueness checks run before writing.
    Password changes are handled separately via the Reset Password dialog.

    user_row is a pandas Series sourced from the _admin_users_tab() SELECT
    query, which explicitly fetches chatgpt_api_key, gemini_api_key,
    groq_api_key, and github_token. The user_row.get() calls below must
    reference the same column names as that SELECT — they are kept in sync
    intentionally to prevent silent data loss on save.

    The address block is rendered via render_address_fields() using the
    "edit_user" key prefix, which keeps widget keys unique relative to any
    other address block that may be rendered in the same session.
    """
    u_id = int(user_row["id"])
    st.subheader(f"Editing: {user_row['username']}")

    with st.form("dialog_edit_user_form"):
        st.markdown("**Account**")
        a1, a2 = st.columns(2)
        with a1:
            edit_user  = st.text_input("Username", value=user_row.get("username") or "")
            edit_role  = st.selectbox("Role", ["user", "admin", "teacher", "student"],
                                      index=["user", "admin", "teacher", "student"].index(user_row["role"]))
        with a2:
            edit_email_in = st.text_input("Email", value=user_row.get("email") or "")
            edit_status   = st.selectbox("Status", ["active", "inactive"],
                                         index=["active", "inactive"].index(user_row["status"]))

        st.divider()
        st.markdown("**Personal Information**")
        p1, p2 = st.columns(2)
        with p1:
            edit_first = st.text_input("First Name", value=user_row.get("first_name") or "")
            edit_phone = st.text_input("Phone", value=user_row.get("phone") or "")
        with p2:
            edit_last = st.text_input("Last Name", value=user_row.get("last_name") or "")
            edit_roll = st.text_input(
                "Roll Number",
                value=user_row.get("roll_no") or "",
                help="Checked against the student's ID card at exam submission time.",
            )

        st.divider()
        edit_street, edit_city, edit_state, edit_postal, edit_country = render_address_fields(
            "edit_user",
            street_value=user_row.get("street_address") or "",
            city_value=user_row.get("city") or "",
            state_value=user_row.get("state_province") or "",
            postal_value=user_row.get("postal_code") or "",
            country_value=user_row.get("country") or "",
        )

        st.divider()
        st.markdown("**AI API Keys**")
        k1, k2 = st.columns(2)
        with k1:
            edit_chatgpt = st.text_input(
                "ChatGPT / OpenAI Key",
                value=user_row.get("chatgpt_api_key") or "",
                type="password",
                placeholder="Enter API key",
            )
            edit_groq = st.text_input(
                "Groq Key",
                value=user_row.get("groq_api_key") or "",
                type="password",
                placeholder="Enter API key",
            )
        with k2:
            edit_gemini = st.text_input(
                "Gemini Key",
                value=user_row.get("gemini_api_key") or "",
                type="password",
                placeholder="Enter API key",
            )
            edit_github = st.text_input(
                "GitHub Token",
                value=user_row.get("github_token") or "",
                type="password",
                placeholder="Enter API key",
            )

        st.divider()
        st.markdown("**Model Preferences**")
        st.caption(
            "Set the preferred AI model for each feature for this user. "
            "Preferences are applied at the user's next login."
        )

        # Build a reverse lookup from model ID → display name so stored
        # preferences can be pre-selected in each selectbox.
        _model_names   = list(LLM_MODELS.keys())
        _id_to_display = {mid: name for name, mid in LLM_MODELS.items()}

        def _edit_pref_display(col: str) -> str:
            """Return the display name for a stored preference column value."""
            stored = user_row.get(col)
            if stored and stored in _id_to_display:
                return _id_to_display[stored]
            return _model_names[0]

        ep1, ep2 = st.columns(2)
        with ep1:
            edit_pref_rag = st.selectbox(
                "RAG System",
                _model_names,
                index=_model_names.index(_edit_pref_display("pref_model_rag")),
                key="admin_edit_pref_rag",
            )
            edit_pref_exam_grading = st.selectbox(
                "Exam Grading",
                _model_names,
                index=_model_names.index(_edit_pref_display("pref_model_exam_grading")),
                key="admin_edit_pref_exam_grading",
            )
            edit_pref_exam_creation = st.selectbox(
                "Exam Creation",
                _model_names,
                index=_model_names.index(_edit_pref_display("pref_model_exam_creation")),
                key="admin_edit_pref_exam_creation",
            )
        with ep2:
            edit_pref_advisor = st.selectbox(
                "Advisor AI",
                _model_names,
                index=_model_names.index(_edit_pref_display("pref_model_advisor_ai")),
                key="admin_edit_pref_advisor",
            )
            edit_pref_wellness = st.selectbox(
                "Student Wellness",
                _model_names,
                index=_model_names.index(_edit_pref_display("pref_model_wellness")),
                key="admin_edit_pref_wellness",
            )
            edit_pref_quiz = st.selectbox(
                "Practice Quiz",
                _model_names,
                index=_model_names.index(_edit_pref_display("pref_model_quiz_generator")),
                key="admin_edit_pref_quiz",
            )
            edit_pref_video = st.selectbox(
                "Video Lectures",
                _model_names,
                index=_model_names.index(_edit_pref_display("pref_model_video_lectures")),
                key="admin_edit_pref_video",
            )

        save = st.form_submit_button("Save Changes", type="primary")

    if save:
        # Apply strip/title transformations at submission time.
        edit_user     = edit_user.strip()
        edit_email_in = edit_email_in.strip()
        edit_first    = edit_first.strip().title()
        edit_last     = edit_last.strip().title()
        edit_phone    = edit_phone.strip()
        edit_street   = edit_street.strip()
        edit_city     = edit_city.strip()
        edit_state    = edit_state.strip()
        edit_postal   = edit_postal.strip()
        edit_country  = edit_country.strip()
        edit_roll     = edit_roll.strip()    or None
        edit_chatgpt  = edit_chatgpt.strip() or None
        edit_gemini   = edit_gemini.strip()  or None
        edit_groq     = edit_groq.strip()    or None
        edit_github   = edit_github.strip()  or None

        errors = validate_user_form(
            username=edit_user, email=edit_email_in, password=None,
            first_name=edit_first, last_name=edit_last, phone=edit_phone,
            street=edit_street, city=edit_city, state_prov=edit_state,
            postal_code=edit_postal, country=edit_country,
        )
        roll_err = validate_roll_no(edit_roll)
        if roll_err:
            errors.append(roll_err)
        if errors:
            show_errors(errors)
            return

        api_key_errors = [
            validate_api_key(edit_chatgpt, "ChatGPT / OpenAI"),
            validate_api_key(edit_gemini,  "Gemini"),
            validate_api_key(edit_groq,    "Groq"),
            validate_api_key(edit_github,  "GitHub Token"),
        ]
        api_key_errors = [msg for msg in api_key_errors if msg]
        if api_key_errors:
            show_errors(api_key_errors)
            return

        valid_email, _ = validate_email_field(edit_email_in)

        if not is_username_unique_for_update(edit_user, u_id):
            st.error("That username is already taken by another user.")
            return
        if not is_email_unique_for_update(valid_email, u_id):
            st.error("That email address is already used by another user.")
            return
        if edit_phone and not is_phone_unique(edit_phone, exclude_id=u_id):
            st.error("That phone number is already used by another user.")
            return
        if edit_roll and not is_roll_no_unique(edit_roll, exclude_id=u_id):
            st.error("That roll number is already used by another user.")
            return

        try:
            admin_update_user_full(
                user_id=u_id, username=edit_user, email=valid_email,
                first_name=edit_first, last_name=edit_last, phone=edit_phone,
                street=edit_street, city=edit_city, state_prov=edit_state,
                postal_code=edit_postal, country=edit_country,
                role=edit_role, status=edit_status,
                chatgpt_key=edit_chatgpt, gemini_key=edit_gemini,
                groq_key=edit_groq, github_token=edit_github,
                elevenlabs_key=None, cartesia_key=None,
                roll_no=edit_roll,
                pref_rag           = LLM_MODELS[edit_pref_rag],
                pref_exam_grading  = LLM_MODELS[edit_pref_exam_grading],
                pref_exam_creation = LLM_MODELS[edit_pref_exam_creation],
                pref_advisor_ai    = LLM_MODELS[edit_pref_advisor],
                pref_wellness      = LLM_MODELS[edit_pref_wellness],
                pref_quiz_generator= LLM_MODELS[edit_pref_quiz],
                pref_video_lectures= LLM_MODELS[edit_pref_video],
            )
            st.toast("User updated successfully.")
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to update user: {exc}")


@st.dialog("Reset Password")
def dialog_reset_password(user_id: int, username: str):
    """
    Admin password reset form presented as a modal dialog.
    The admin sets a new password directly without requiring the current one.
    Password strength is validated via validators.py before writing.
    """
    st.subheader(f"Reset password for: {username}")
    with st.form("dialog_reset_pwd_form"):
        new_pwd  = st.text_input("New Password", type="password")
        conf_pwd = st.text_input("Confirm New Password", type="password")
        submit   = st.form_submit_button("Update Password", type="primary")

    if submit:
        # Passwords are not stripped — whitespace is intentional.
        pwd_err = validate_password(new_pwd)
        if pwd_err:
            st.error(pwd_err)
        elif new_pwd != conf_pwd:
            st.error("Passwords do not match.")
        else:
            admin_reset_user_password(user_id, new_pwd)
            st.toast(f"Password for '{username}' updated.")
            st.rerun()


@st.dialog("Delete Course")
def dialog_delete_course(engine, course_id: int, course_name: str, tab_key=None):
    """
    Confirmation modal for permanently deleting a course.

    Physical files are removed from disk before the SQL DELETE so that no
    orphaned files are left in the uploads directory. The SQL DELETE then
    removes the course row, which cascade-deletes all linked assessments,
    files table records, course_access records, and feature data via the
    ON DELETE CASCADE constraints defined in schema_clean.sql.

    tab_key is forwarded to reset_navigation() so that after deletion the
    correct tab (or global state when None) returns to its courses list.
    The existing call from _admin_courses_tab passes no tab_key — it resets
    the global state, which is correct for that unrendered context.
    """
    st.warning(
        f"You are about to permanently delete **{course_name}**. "
        "All linked assessments, files, and AI outputs will also be removed. "
        "This cannot be undone."
    )
    col1, col2 = st.columns(2)
    if col1.button("Delete Permanently", type="primary", width="stretch"):
        # Fetch all file paths stored under this course before deleting so
        # the physical files can be removed from disk. The SQL cascade will
        # remove the files table records; this step removes the actual bytes.
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT file_path FROM files WHERE course_id = :cid"),
                {"cid": course_id},
            )
            file_paths = [row.file_path for row in result]

        for file_path in file_paths:
            delete_physical_file(file_path)

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM courses WHERE id = :id"), {"id": course_id})

        st.toast(f"Course '{course_name}' deleted.")
        reset_navigation(tab_key)
        st.rerun()
    if col2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Edit Course")
def dialog_edit_course(engine, course_id: int, row: dict, role: str, tab_key=None):
    """
    Modal edit form for a single course.

    Shown to admin and to the teacher who owns the course (is_owner). All
    editable fields are presented: course code, name, credit hours, year,
    semester, instructor name, description, and status. Validation and
    uniqueness checks mirror those in the Create New Course form.

    tab_key is accepted for signature consistency but is not needed for widget
    keys inside a dialog — dialogs render in an isolated modal context and
    cannot produce DuplicateWidgetID errors against the main page.
    """
    st.subheader(f"Editing: {row['course_name']}")

    with st.form("edit_course_modal_form"):
        ec1, ec2 = st.columns(2)
        with ec1:
            e_code  = st.text_input("Course Code",   value=str(row.get("course_code") or ""))
            e_hours = st.number_input(
                "Credit Hours", min_value=1, max_value=12,
                value=int(row.get("credit_hours") or 3),
            )
            sem_options = ["Winter", "Spring", "Summer", "Fall"]
            current_sem = str(row.get("semester") or "Fall")
            e_sem = st.selectbox(
                "Semester", sem_options,
                index=sem_options.index(current_sem) if current_sem in sem_options else 0,
            )
        with ec2:
            e_name = st.text_input("Course Name",    value=str(row.get("course_name") or ""))
            e_year = st.number_input(
                "Year", min_value=2000, max_value=2100,
                value=int(row.get("year") or 2026),
            )
            # Status is editable by both admin and the owning teacher.
            status_options = ["active", "inactive"]
            current_status = str(row.get("status") or "active")
            e_status = st.selectbox(
                "Status", status_options,
                index=status_options.index(current_status) if current_status in status_options else 0,
            )
        e_inst = st.text_input("Instructor Name", value=str(row.get("instructor_name") or ""))
        e_desc = st.text_area("Description (optional)", value=str(row.get("description") or ""))

        col_save, col_cancel = st.columns(2)
        save   = col_save.form_submit_button("Save",   type="primary",  width="stretch")
        cancel = col_cancel.form_submit_button("Cancel", width="stretch")

    if cancel:
        st.rerun()

    if save:
        e_code   = e_code.strip()
        e_name   = e_name.strip()
        e_inst   = e_inst.strip()
        e_desc   = e_desc.strip()

        course_errors = validate_course_form(
            course_code=e_code, course_name=e_name,
            credit_hours=e_hours, year=e_year, instructor_name=e_inst,
        )
        if course_errors:
            show_errors(course_errors)
            return
        if not is_course_code_unique(e_code, exclude_id=course_id):
            st.error(f"Course code '{e_code}' is already used by another course.")
            return

        try:
            update_course_details(
                course_id,
                e_code.upper(),
                e_name,
                int(e_hours),
                int(e_year),
                e_sem,
                e_desc,
                e_inst,
            )
            # update_course_details does not write status; apply it separately.
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE courses SET status = :s WHERE id = :cid"),
                    {"s": e_status, "cid": course_id},
                )
            st.toast("Course updated.")
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to update course: {exc}")


@st.dialog("Delete Assessment")
def dialog_delete_assessment(engine, assessment_id: int, title: str):
    """
    Confirmation modal for permanently deleting an assessment.

    Physical files are removed from disk before the SQL DELETE so that no
    orphaned files are left in the uploads directory. The SQL DELETE then
    removes the assessment row, which cascade-deletes all linked files table
    records, grading results, generated exam questions, practice quizzes,
    quiz attempts, and published quiz data via the ON DELETE CASCADE constraints
    defined in schema_clean.sql.
    """
    st.warning(
        f"You are about to permanently delete **{title}**. "
        "All linked files, grading history, generated questions, and quiz "
        "records will also be removed. This cannot be undone."
    )
    col1, col2 = st.columns(2)
    if col1.button("Delete Permanently", type="primary", width="stretch"):
        # Fetch all file paths stored under this assessment before deleting so
        # the physical files can be removed from disk. The SQL cascade will
        # remove the files table records; this step removes the actual bytes.
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT file_path FROM files WHERE assessment_id = :aid"),
                {"aid": assessment_id},
            )
            file_paths = [row.file_path for row in result]

        for file_path in file_paths:
            delete_physical_file(file_path)

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM assessments WHERE id = :id"), {"id": assessment_id})

        st.toast(f"Assessment '{title}' deleted.")
        st.rerun()
    if col2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Edit Assessment")
def dialog_edit_assessment(engine, assessment_id: int, row: dict, tab_key=None):
    """
    Modal edit form for a single assessment.

    Shown when can_edit_content is True (admin or course-owning teacher).
    Editable fields are title and description.

    tab_key is accepted for signature consistency; widget keys inside a dialog
    are isolated and do not require namespacing.
    """
    st.subheader(f"Editing: {row['title']}")

    with st.form("edit_assessment_modal_form"):
        e_title = st.text_input("Title", value=str(row.get("title") or ""))
        e_desc  = st.text_area("Description (optional)", value=str(row.get("description") or ""))

        col_save, col_cancel = st.columns(2)
        save   = col_save.form_submit_button("Save",   type="primary",  width="stretch")
        cancel = col_cancel.form_submit_button("Cancel", width="stretch")

    if cancel:
        st.rerun()

    if save:
        e_title = e_title.strip()
        e_desc  = e_desc.strip()

        asm_errors = validate_assessment_form(title=e_title)
        if asm_errors:
            show_errors(asm_errors)
            return

        try:
            update_assessment_details(
                assessment_id,
                e_title,
                e_desc,
            )
            st.toast("Assessment updated.")
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to update assessment: {exc}")


@st.dialog("Delete File")
def dialog_delete_file(engine, file_id: int, file_name: str, file_path: str):
    """
    Confirmation modal for permanently deleting a file record and its
    corresponding file on disk. The DB record is the source of truth for
    listing; failure to delete the physical file is caught silently.
    """
    st.warning(
        f"You are about to permanently delete **{file_name}**. "
        "This cannot be undone."
    )
    col1, col2 = st.columns(2)
    if col1.button("Delete Permanently", type="primary", width="stretch"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM files WHERE id = :id"), {"id": file_id})
        delete_physical_file(file_path)
        st.toast("File deleted.")
        st.rerun()
    if col2.button("Cancel", width="stretch"):
        st.rerun()




@st.dialog("Delete Account")
def dialog_delete_own_account(user_id: int, username: str):
    """
    Confirmation modal for a user permanently deleting their own account.
    On confirmation, the account is deleted and the session is cleared,
    returning the user to the login screen.
    """
    st.warning(
        f"You are about to permanently delete your account **{username}**. "
        "All your data will be removed. This cannot be undone."
    )
    col1, col2 = st.columns(2)
    if col1.button("Delete My Account", type="primary", width="stretch"):
        delete_user_account(user_id)
        logout()
    if col2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Revoke Course Access")
def dialog_revoke_access(engine, course_id: int, user_id: int, username: str, access_role: str):
    """
    Confirmation modal for revoking a user's access to a course.
    Sets course_access.status to 'revoked' rather than deleting the row,
    preserving the audit trail. All users including course creators can
    have their access revoked by an admin.
    """
    st.warning(
        f"Revoke **{access_role}** access for **{username}**? "
        "Their access status will be set to revoked."
    )
    col1, col2 = st.columns(2)
    if col1.button("Revoke Access", type="primary", width="stretch"):
        revoke_course_access(course_id, user_id, access_role)
        st.toast(f"Access revoked for {username}.")
        st.rerun()
    if col2.button("Cancel", width="stretch"):
        st.rerun()


# =============================================================================
# AUTHENTICATION PAGES (unauthenticated view)
# =============================================================================

def auth_page():
    """
    Landing page shown to unauthenticated users.
    Log In and Create Account are presented as tabs within a centred panel.
    No sidebar is shown in this state.
    """
    # Centre the panel using columns — the middle column holds the content.
    _, centre, _ = st.columns([1, 2, 1])
    with centre:
        st.markdown("""<div style="text-align: center;"><h1>Welcome to <a href="https://prebinary.com">PreBinary</a> <br> <span style="font-size:20px; color:gray;">Redefining Learning with AI</span></h1></div>""", unsafe_allow_html=True)
        st.divider()

        login_tab, signup_tab = st.tabs(["Log In", "Create Account"])

        with login_tab:
            _render_login_form()

        with signup_tab:
            _render_signup_form()


def _render_login_form():
    """
    Login form tab content.
    Calls login_user() from auth.py and handles the three possible outcomes:
    successful login, inactive account, and invalid credentials.

    On successful login, session state is populated with all user fields
    returned by login_user() (SELECT * — includes all new API key and
    pref_model_* columns), plus two additional mappings required for
    compatibility between the Prebinary and UReap naming conventions:

      openai_api_key — UReap's llm_utils.py reads this key from session state
                       when calling OpenAI. It is mapped from chatgpt_api_key,
                       which is the column name used in the Prebinary users table.

    Per-feature model preferences are loaded from the pref_model_* columns into
    the internal session state keys that each UReap feature module reads. NULL
    preferences fall back to the first model in llm_utils.MODELS.
    """
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit   = st.form_submit_button("Log In", type="primary", width="stretch")

    if submit:
        # Passwords are not stripped before passing to login_user.
        result = login_user(username.strip(), password)
        if result == "inactive":
            st.error("This account is inactive. Contact an administrator to have it activated.")
        elif result:
            st.session_state.logged_in = True
            st.session_state.user = result

            # Bridge the naming difference between Prebinary's chatgpt_api_key
            # column and UReap's openai_api_key session state key. Both refer
            # to the same OpenAI credential; only the name differs.
            st.session_state["openai_api_key"] = result.get("chatgpt_api_key")

            # Flatten UReap API key session state keys to the root level.
            # llm_utils.py reads these directly from st.session_state (e.g.
            # st.session_state.groq_api_key), not from st.session_state.user,
            # so they must be present at the top level of session state.
            st.session_state["groq_api_key"]       = result.get("groq_api_key")
            st.session_state["gemini_api_key"]      = result.get("gemini_api_key")
            st.session_state["github_token"]        = result.get("github_token")

            # Load per-feature model preferences into each feature's internal
            # session state key. Values are model ID strings (e.g.
            # 'gemini-2.5-flash'). A NULL or unrecognised value falls back to
            # the first entry in LLM_MODELS.
            _load_model_preferences(result)

            st.rerun()
        else:
            st.error("Invalid username or password. Please try again.")


def _load_model_preferences(user: dict) -> None:
    """
    Populate each UReap feature's internal model selection session state key
    from the user's saved pref_model_* preferences.

    Preferences are stored in the DB as model ID strings and must be converted
    to display names before being written to session state, because each feature
    module's selectbox is keyed by display name (a key in llm_utils.MODELS).

    The mapping from DB column → session state key is:
      pref_model_rag            → rag_selected_model
      pref_model_exam_grading   → exam_grading_selected_model
      pref_model_exam_creation  → exam_creation_selected_model
      pref_model_advisor_ai     → advisor_selected_model
      pref_model_wellness       → wellness_selected_model
      pref_model_quiz_generator → quiz_selected_model
      pref_model_video_lectures → slideshow_selected_model

    If a stored model ID is NULL or is no longer present in LLM_MODELS (e.g.
    a model was removed), the key falls back to the first display name in
    LLM_MODELS so the feature always has a usable default.
    """
    # Build a reverse lookup: model_id → display_name
    id_to_display = {model_id: name for name, model_id in LLM_MODELS.items()}
    default_display = list(LLM_MODELS.keys())[0] if LLM_MODELS else None

    def _resolve(pref_col: str) -> str:
        """Return the display name for a stored model ID, or the default."""
        model_id = user.get(pref_col)
        if model_id and model_id in id_to_display:
            return id_to_display[model_id]
        return default_display

    st.session_state["rag_selected_model"]           = _resolve("pref_model_rag")
    st.session_state["exam_grading_selected_model"]  = _resolve("pref_model_exam_grading")
    st.session_state["exam_creation_selected_model"] = _resolve("pref_model_exam_creation")
    st.session_state["advisor_selected_model"]       = _resolve("pref_model_advisor_ai")
    st.session_state["wellness_selected_model"]      = _resolve("pref_model_wellness")
    st.session_state["quiz_selected_model"]          = _resolve("pref_model_quiz_generator")
    st.session_state["slideshow_selected_model"]     = _resolve("pref_model_video_lectures")


def _render_signup_form():
    """
    Account creation form tab content.
    Grouped into three logical sections: Account credentials, Personal details,
    and Address. All validation is performed by validate_user_form() before the
    DB write. New accounts are created with status='inactive' and must be
    activated by an administrator before they can log in.

    The address block is rendered via render_address_fields() using the
    "signup" key prefix to keep widget keys unique across the session.
    """
    with st.form("signup_form", clear_on_submit=False):
        st.markdown("**Account**")
        ac1, ac2 = st.columns(2)
        with ac1:
            uname = st.text_input("Username")
            pwd   = st.text_input("Password", type="password")
        with ac2:
            email_input = st.text_input("Email")
            cpwd        = st.text_input("Confirm Password", type="password")

        st.divider()
        st.markdown("**Personal Details**")
        pd1, pd2 = st.columns(2)
        with pd1:
            f_name = st.text_input("First Name")
            phone  = st.text_input("Phone (optional)")
        with pd2:
            l_name = st.text_input("Last Name")

        st.divider()
        street, city, state_prov, postal_code, country = render_address_fields("signup")

        submit = st.form_submit_button("Create Account", type="primary", width="stretch")

    if submit:
        # Apply strip/title at submission. Passwords are never stripped.
        uname       = uname.strip()
        email_input = email_input.strip()
        f_name      = f_name.strip().title()
        l_name      = l_name.strip().title()
        phone       = phone.strip()
        street      = street.strip()
        city        = city.strip()
        state_prov  = state_prov.strip()
        postal_code = postal_code.strip()
        country     = country.strip()

        errors = validate_user_form(
            username=uname, email=email_input, password=pwd,
            first_name=f_name, last_name=l_name, phone=phone,
            street=street, city=city, state_prov=state_prov,
            postal_code=postal_code, country=country,
        )
        if errors:
            show_errors(errors)
        elif pwd != cpwd:
            st.error("Passwords do not match.")
        elif not is_username_unique(uname):
            st.error("That username is already taken.")
        else:
            valid_email, _ = validate_email_field(email_input)
            if not is_email_unique(valid_email):
                st.error("That email address is already registered.")
            elif phone and not is_phone_unique(phone):
                st.error("That phone number is already registered.")
            else:
                signup_user(uname, valid_email, pwd, f_name, l_name, phone,
                            street, city, state_prov, postal_code, country)
                st.success(
                    "Account created. An administrator must activate it before you can log in."
                )


# =============================================================================
# PROFILE PAGE
# =============================================================================

def profile_page():
    """
    User profile and settings page, accessible from the sidebar navigation.
    Organised into five tabs: Personal Information, API Keys, Model Preferences,
    Change Password, and Delete Account.
    """
    st.title("Profile")
    user = st.session_state.user

    tab_personal, tab_keys, tab_prefs, tab_password, tab_deletion = st.tabs([
        "Personal Information", "API Keys", "Model Preferences",
        "Change Password", "Delete Account",
    ])

    # ------------------------------------------------------------------
    # Tab 1: Personal Information
    # ------------------------------------------------------------------
    with tab_personal:
        st.subheader("Personal Information")
        with st.form("update_profile_form"):
            st.markdown("**Name & Contact**")
            nc1, nc2 = st.columns(2)
            with nc1:
                fn = st.text_input("First Name", value=user.get("first_name") or "")
                ln = st.text_input("Last Name",  value=user.get("last_name") or "")
            with nc2:
                ph = st.text_input("Phone (optional)", value=user.get("phone") or "")

            # Roll number is only meaningful for student accounts — it is the
            # identifier checked against the student's physical ID card during
            # exam-submission identity verification.
            if user.get("role") == "student":
                roll = st.text_input(
                    "Roll Number",
                    value=user.get("roll_no") or "",
                    help="Must match the roll number printed on your ID card — "
                         "this is checked at exam submission time.",
                )
            else:
                roll = user.get("roll_no") or ""

            st.divider()
            strt, cty, stt, zp, cnt = render_address_fields(
                "profile",
                street_value=user.get("street_address") or "",
                city_value=user.get("city") or "",
                state_value=user.get("state_province") or "",
                postal_value=user.get("postal_code") or "",
                country_value=user.get("country") or "",
            )

            submitted = st.form_submit_button("Save Changes", type="primary")

        if submitted:
            # Apply transformations at submission time, not at widget render.
            fn   = fn.strip().title()
            ln   = ln.strip().title()
            ph   = ph.strip()
            strt = strt.strip()
            cty  = cty.strip()
            stt  = stt.strip()
            zp   = zp.strip()
            cnt  = cnt.strip()
            roll = roll.strip() or None

            profile_errors = []
            for err in [
                validate_name(fn, "First name"),
                validate_name(ln, "Last name"),
                validate_phone(ph),
                validate_text_field(strt, "Street address", 255),
                validate_text_field(cty,  "City",           100),
                validate_text_field(stt,  "State/Province", 100),
                validate_postal_code(zp),
                validate_text_field(cnt,  "Country",        100),
                validate_roll_no(roll),
            ]:
                if err:
                    profile_errors.append(err)

            if profile_errors:
                show_errors(profile_errors)
            elif ph and not is_phone_unique(ph, exclude_id=int(user["id"])):
                st.error("That phone number is already used by another user.")
            elif roll and not is_roll_no_unique(roll, exclude_id=int(user["id"])):
                st.error("That roll number is already used by another user.")
            else:
                update_user_profile(user["id"], fn, ln, ph, strt, cty, stt, zp, cnt, roll)
                # Keep session state in sync so the form pre-populates correctly
                # without requiring a full page reload.
                st.session_state.user.update({
                    "first_name": fn, "last_name": ln, "phone": ph,
                    "street_address": strt, "city": cty, "state_province": stt,
                    "postal_code": zp, "country": cnt, "roll_no": roll,
                })
                st.toast("Profile saved.")
                st.rerun()

    # ------------------------------------------------------------------
    # Tab 2: API Keys
    # Each key field shows a saved/not-saved indicator so the user knows
    # whether a key is currently stored without revealing its value.
    # ------------------------------------------------------------------
    with tab_keys:
        st.subheader("AI API Keys")
        st.caption(
            "API keys are stored in your account and used by AI features "
            "throughout the application."
        )

        chatgpt_saved    = bool(user.get("chatgpt_api_key"))
        gemini_saved     = bool(user.get("gemini_api_key"))
        groq_saved       = bool(user.get("groq_api_key"))
        github_saved     = bool(user.get("github_token"))
        elevenlabs_saved = bool(user.get("elevenlabs_api_key"))
        cartesia_saved   = bool(user.get("cartesia_api_key"))

        with st.form("api_keys_form"):
            st.markdown("**LLM Provider Keys**")
            k1, k2 = st.columns(2)
            with k1:
                # chatgpt_api_key doubles as the OpenAI key for UReap.
                # UReap reads st.session_state.openai_api_key at runtime,
                # which is populated from this column at login.
                cgpt = st.text_input(
                    "ChatGPT / OpenAI API Key",
                    value=user.get("chatgpt_api_key") or "",
                    type="password",
                    placeholder="Enter API key",
                )
                groq = st.text_input(
                    "Groq API Key",
                    value=user.get("groq_api_key") or "",
                    type="password",
                    placeholder="Enter API key",
                    help="Used for Llama 3.3-70B via the Groq inference API.",
                )
            with k2:
                gem = st.text_input(
                    "Google Gemini API Key",
                    value=user.get("gemini_api_key") or "",
                    type="password",
                    placeholder="Enter API key",
                )
                github = st.text_input(
                    "GitHub Token",
                    value=user.get("github_token") or "",
                    type="password",
                    placeholder="Enter API key",
                    help="Used for GPT-4o via GitHub Models.",
                )

            st.divider()
            st.markdown("**Text-to-Speech Keys**")
            tts1, tts2 = st.columns(2)
            with tts1:
                elevenlabs = st.text_input(
                    "ElevenLabs API Key",
                    value=user.get("elevenlabs_api_key") or "",
                    type="password",
                    placeholder="Enter API key",
                )
            with tts2:
                cartesia = st.text_input(
                    "Cartesia API Key",
                    value=user.get("cartesia_api_key") or "",
                    type="password",
                    placeholder="Enter API key",
                )

            save_keys = st.form_submit_button("Save API Keys", type="primary")

        if save_keys:
            # Blank strings are stored as None so the not-set indicator works
            # correctly on the next render.
            cgpt       = cgpt.strip()       or None
            gem        = gem.strip()        or None
            groq       = groq.strip()       or None
            github     = github.strip()     or None
            elevenlabs = elevenlabs.strip() or None
            cartesia   = cartesia.strip()   or None

            api_key_errors = [
                validate_api_key(cgpt,       "ChatGPT / OpenAI"),
                validate_api_key(gem,        "Gemini"),
                validate_api_key(groq,       "Groq"),
                validate_api_key(github,     "GitHub Token"),
                validate_api_key(elevenlabs, "ElevenLabs"),
                validate_api_key(cartesia,   "Cartesia"),
            ]
            api_key_errors = [msg for msg in api_key_errors if msg]
            if api_key_errors:
                # Display errors without returning early so all other tabs
                # remain accessible.
                show_errors(api_key_errors)
            else:
                update_user_api_keys(
                    user["id"], cgpt, gem, groq, github, elevenlabs, cartesia
                )
                st.session_state.user.update({
                    "chatgpt_api_key":    cgpt,
                    "gemini_api_key":     gem,
                    "groq_api_key":       groq,
                    "github_token":       github,
                    "elevenlabs_api_key": elevenlabs,
                    "cartesia_api_key":   cartesia,
                })
                # Keep the session state root-level keys in sync so that
                # llm_utils.py, which reads these directly from st.session_state
                # (not from st.session_state.user), picks up the updated values.
                st.session_state["openai_api_key"] = cgpt
                st.session_state["groq_api_key"]   = groq
                st.session_state["gemini_api_key"] = gem
                st.session_state["github_token"]   = github
                st.toast("API keys saved.")
                st.rerun()

        # ── API key links ─────────────────────────────────────────────────────
        st.divider()
        st.write("Enter your API keys to use cloud-based models:")
        st.markdown("""
🔑 Get your API keys:
- [OpenAI API Key](https://platform.openai.com/api-keys)
- [GitHub Token](https://github.com/settings/personal-access-tokens)
- [Gemini API Key](https://aistudio.google.com/apikey)
- [Groq API Key](https://console.groq.com/keys)
""")

    # ------------------------------------------------------------------
    # Tab 3: Model Preferences
    # Allows each user to set a default LLM for each UReap feature so
    # they do not need to re-select on every session. Preferences are
    # stored as model ID strings in the pref_model_* columns and loaded
    # into feature session state keys at login via _load_model_preferences().
    # ------------------------------------------------------------------
    with tab_prefs:
        st.subheader("Model Preferences")
        st.caption(
            "Set your preferred AI model for each feature. Your selection is "
            "saved to your account and applied automatically at login."
        )

        if not LLM_MODELS:
            st.warning("No models are currently available.")
        else:
            model_display_names = list(LLM_MODELS.keys())

            # Build a reverse lookup so current preferences can be pre-selected
            # in each selectbox by display name.
            id_to_display = {mid: name for name, mid in LLM_MODELS.items()}

            def _current_display(pref_col: str) -> str:
                """Return the current display name for a preference column."""
                stored_id = user.get(pref_col)
                if stored_id and stored_id in id_to_display:
                    return id_to_display[stored_id]
                return model_display_names[0]

            with st.form("model_prefs_form"):
                col1, col2 = st.columns(2)

                with col1:
                    sel_rag = st.selectbox(
                        "RAG System",
                        model_display_names,
                        index=model_display_names.index(_current_display("pref_model_rag")),
                        key="pref_sel_rag",
                    )
                    sel_exam_grading = st.selectbox(
                        "Exam Grading",
                        model_display_names,
                        index=model_display_names.index(_current_display("pref_model_exam_grading")),
                        key="pref_sel_exam_grading",
                    )
                    sel_exam_creation = st.selectbox(
                        "Exam Creation",
                        model_display_names,
                        index=model_display_names.index(_current_display("pref_model_exam_creation")),
                        key="pref_sel_exam_creation",
                    )

                with col2:
                    sel_advisor = st.selectbox(
                        "Advisor AI",
                        model_display_names,
                        index=model_display_names.index(_current_display("pref_model_advisor_ai")),
                        key="pref_sel_advisor",
                    )
                    sel_wellness = st.selectbox(
                        "Student Wellness",
                        model_display_names,
                        index=model_display_names.index(_current_display("pref_model_wellness")),
                        key="pref_sel_wellness",
                    )
                    sel_quiz = st.selectbox(
                        "Practice Quiz",
                        model_display_names,
                        index=model_display_names.index(_current_display("pref_model_quiz_generator")),
                        key="pref_sel_quiz",
                    )
                    sel_video_lectures = st.selectbox(
                        "Video Lectures",
                        model_display_names,
                        index=model_display_names.index(_current_display("pref_model_video_lectures")),
                        key="pref_sel_video_lectures",
                    )

                save_prefs = st.form_submit_button("Save Preferences", type="primary")

            if save_prefs:
                # Convert display names back to model IDs for storage.
                update_user_model_prefs(
                    user_id           = user["id"],
                    pref_rag          = LLM_MODELS[sel_rag],
                    pref_exam_grading = LLM_MODELS[sel_exam_grading],
                    pref_exam_creation= LLM_MODELS[sel_exam_creation],
                    pref_advisor_ai   = LLM_MODELS[sel_advisor],
                    pref_wellness     = LLM_MODELS[sel_wellness],
                    pref_quiz_generator=LLM_MODELS[sel_quiz],
                    pref_video_lectures=LLM_MODELS[sel_video_lectures],
                )
                # Update session state user record so profile re-renders with
                # the new values without requiring a full re-login.
                st.session_state.user.update({
                    "pref_model_rag":            LLM_MODELS[sel_rag],
                    "pref_model_exam_grading":   LLM_MODELS[sel_exam_grading],
                    "pref_model_exam_creation":  LLM_MODELS[sel_exam_creation],
                    "pref_model_advisor_ai":     LLM_MODELS[sel_advisor],
                    "pref_model_wellness":       LLM_MODELS[sel_wellness],
                    "pref_model_quiz_generator": LLM_MODELS[sel_quiz],
                    "pref_model_video_lectures": LLM_MODELS[sel_video_lectures],
                })
                # Apply the new preferences to the live feature session state
                # keys immediately so they take effect without re-login.
                _load_model_preferences(st.session_state.user)
                st.toast("Model preferences saved.")
                st.rerun()

    # ------------------------------------------------------------------
    # Tab 4: Change Password
    # Wrapped in st.form to prevent fields from re-rendering on unrelated
    # state changes. The current password is verified via login_user before
    # the change is accepted.
    # ------------------------------------------------------------------
    with tab_password:
        st.subheader("Change Password")
        with st.form("change_password_form"):
            cur_p = st.text_input("Current Password", type="password")
            new_p = st.text_input("New Password",     type="password")
            con_p = st.text_input("Confirm New Password", type="password")
            submit_pwd = st.form_submit_button("Update Password", type="primary")

        if submit_pwd:
            # Passwords are not stripped — whitespace is intentional.
            valid = login_user(user["username"], cur_p)
            if not valid or valid == "inactive":
                st.error("Current password is incorrect.")
            else:
                pwd_err = validate_password(new_p)
                if pwd_err:
                    st.error(pwd_err)
                elif new_p != con_p:
                    st.error("New passwords do not match.")
                else:
                    change_user_password(user["id"], new_p)
                    st.toast("Password updated.")

    # ------------------------------------------------------------------
    # Tab 5: Delete Account
    # Visually separated to make clear this is a destructive, irreversible
    # action. Confirmation is handled by a dialog modal.
    # ------------------------------------------------------------------
    with tab_deletion:
        st.subheader("Delete Account")
        st.markdown(
            "Permanently deleting your account will remove all your data from the system. "
            "This action cannot be reversed."
        )
        st.divider()
        if st.button("Delete My Account", type="primary"):
            dialog_delete_own_account(user["id"], user["username"])


# =============================================================================
# FEATURE TAB WRAPPER FUNCTIONS
# =============================================================================
# Each wrapper drives one of the three course-integrated feature tabs.
# They maintain completely independent per-tab navigation state so that
# navigating into a course under one tab does not affect the others.
#
# Navigation levels:
#   "courses"     → course card grid (render_courses_view)
#   "assessments" → assessments list + access panel (render_assessments_view)
#   "files"       → feature UI entry point (exam_grading_ui / exam_creation_ui /
#                   quiz_generator_ui)
#
# The breadcrumb is rendered at the assessments and files levels only. At the
# files level the feature UI is called directly — it renders exactly as it
# does when called from the original unwired all_tab_defs list.


def _render_exam_grading_tab():
    """
    Entry point for the Exam Grading feature tab.

    Renders the course list at the top level, the assessment list and access
    management panel after a course is selected, and the Exam Grading feature
    UI once an assessment is opened. The breadcrumb provides navigation back
    up the hierarchy within this tab's own navigation state, independent of
    all other tabs.
    """
    tab_key = "exam_grading"
    level = st.session_state[f"{tab_key}_view_level"]

    # Breadcrumb is shown at assessments and files levels only.
    if level in ("assessments", "files"):
        render_breadcrumb(tab_key)

    if level == "courses":
        render_courses_view(get_engine(), tab_key)
    elif level == "assessments":
        render_assessments_view(get_engine(), tab_key)
    elif level == "files":
        # The feature UI renders exactly as it does today when called directly.
        exam_grading_ui()


def _render_exam_creation_tab():
    """
    Entry point for the Exam Creation feature tab.

    Renders the course list at the top level, the assessment list and access
    management panel after a course is selected, and the Exam Creation feature
    UI once an assessment is opened. Navigation state is fully isolated from
    the Exam Grading and Practice Quiz tabs.
    """
    tab_key = "exam_creation"
    level = st.session_state[f"{tab_key}_view_level"]

    if level in ("assessments", "files"):
        render_breadcrumb(tab_key)

    if level == "courses":
        render_courses_view(get_engine(), tab_key)
    elif level == "assessments":
        render_assessments_view(get_engine(), tab_key)
    elif level == "files":
        exam_creation_ui()


def _render_practice_quiz_tab():
    """
    Entry point for the Practice for Exam/Quiz feature tab.

    Renders the course list at the top level (visible to students as well as
    admins and teachers), the assessment list after a course is selected, and
    the Quiz Generator feature UI once an assessment is opened. Navigation
    state is fully isolated from the other two feature tabs.

    Students see this tab and can navigate into courses and assessments in
    read-only mode, but cannot create, edit, or delete content.
    """
    tab_key = "practice_quiz"
    level = st.session_state[f"{tab_key}_view_level"]

    if level in ("assessments", "files"):
        render_breadcrumb(tab_key)

    if level == "courses":
        render_courses_view(get_engine(), tab_key)
    elif level == "assessments":
        render_assessments_view(get_engine(), tab_key)
    elif level == "files":
        quiz_generator_ui()


def _render_oral_examination_tab():
    """
    Entry point for the Oral Examination feature tab.

    Renders the course list at the top level, the assessment list after a
    course is selected, and the Oral Examination feature UI once an
    assessment is opened. Navigation state is fully isolated from the other
    three feature tabs.
    """
    tab_key = "oral_examination"
    level = st.session_state[f"{tab_key}_view_level"]

    if level in ("assessments", "files"):
        render_breadcrumb(tab_key)

    if level == "courses":
        render_courses_view(get_engine(), tab_key)
    elif level == "assessments":
        render_assessments_view(get_engine(), tab_key)
    elif level == "files":
        oral_examination_ui()


def render_dashboard():
    """
    Shared dashboard content rendered for all authenticated roles.

    This function replaces UReap's main() function as the single entry point
    for the feature tab layout. It is called by admin_page(), teacher_page(),
    and student_page() so that all three role entry points share the same tab
    rendering logic.

    Tab visibility is role-based. The tab list is filtered before the call to
    st.tabs() so that excluded tabs are never rendered at all — they do not
    appear greyed-out or disabled, they simply do not exist for that user.

    Role rules (from the integration plan tab visibility table):
      admin / teacher — all nine tabs including Exam Grading, Exam Creation,
                        Oral Examination, and Video Lectures.
      student         — eight tabs; Exam Creation is removed from the list
                        before rendering. Exam Grading and Oral Examination
                        stay visible — each renders a cut-down student view
                        instead of the full teacher/admin workflow.

    The tab-to-function mapping is built as a list of (label, render_fn) tuples
    which is filtered by role, then passed to st.tabs(). Each resulting tab
    object is mapped back to its render function by zipping the filtered
    definition list with the st.tabs() return value. This avoids hardcoded
    index access, which would produce incorrect routing whenever tabs are
    removed for a student.
    """
    role = st.session_state.user.get("role", "")

    st.write("Empowering Students, Educators, and Institutions to Shape the Future of Education.")

    # Full ordered definition list. Each element is (display_label, render_fn).
    # Entries marked "student: hidden" are excluded from the list when role is
    # 'student', before st.tabs() is ever called.
    all_tab_defs = [
        ("📚 RAG System",               rag_ui),
        ("📝 Exam Grading",             _render_exam_grading_tab),      # student: hidden
        ("✨ Exam Creation",            _render_exam_creation_tab),     # student: hidden
        ("🎓 Advisor AI",               advisor_ai_ui),
        ("🌟 Student Wellness",         student_wellness_ui),
        ("🧠 Practice for Exam/Quiz",   _render_practice_quiz_tab),
        ("🎤 Oral Examination",         _render_oral_examination_tab),
        ("🎬 Video Lectures",           render_narrated_slideshow_feature),
        ("➕ More Features Coming Soon", _render_more_features_tab),
    ]

    # Labels excluded for students. Using a set for O(1) membership checks.
    # Exam Grading is shown to students too — exam_grading_ui() renders a
    # different, cut-down view for them (Submit My Exam) than the full
    # teacher/admin setup-and-grade workflow.
    STUDENT_EXCLUDED = {
        "✨ Exam Creation",
    }

    if role == "student":
        tab_defs = [
            (label, fn)
            for label, fn in all_tab_defs
            if label not in STUDENT_EXCLUDED
        ]
    else:
        # Admins and teachers see all tabs.
        tab_defs = all_tab_defs

    tabs = st.tabs([label for label, _ in tab_defs])

    for (label, render_fn), tab in zip(tab_defs, tabs):
        with tab:
            render_fn()


def _render_more_features_tab():
    """
    Content for the 'More Features Coming Soon' tab.

    Preserved verbatim from UReap's original main() implementation. This tab
    is explicitly out of scope for modification this sprint — its content and
    structure must remain exactly as shown here.
    """
    st.subheader("More Features Coming Soon")
    st.write("This tab is reserved for future features. Check back later for updates!")

    st.info("Future features may include:")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("- **Text Summarization**")
        st.markdown("- **Document Translation**")
        st.markdown("- **Content Generation**")
    with col2:
        st.markdown("- **Image Analysis**")
        st.markdown("- **Custom Training**")
        st.markdown("- **API Integrations**")


def admin_panel_page():
    """
    Standalone Admin Panel page, accessible only to admin-role users.

    Organised into four tabs:
      Users           — create, edit, reset password, and delete user accounts.
      Courses         — create, edit, duplicate, delete all courses in the database,
                         and drill into a course to edit or delete its assessments.
      Verification Log — read-only audit trail of identity-verification attempts
                         (exam_verification feature).
    """
    st.title("Admin Panel")
    engine = get_engine()

    tab_users, tab_courses, tab_verification, tab_maintenance = st.tabs(
        ["Users", "Courses", "Verification Log", "Maintenance"]
    )

    with tab_users:
        _admin_users_tab(engine)

    with tab_courses:
        _admin_courses_panel(engine)

    with tab_verification:
        _admin_verification_log_tab(engine)

    with tab_maintenance:
        _admin_maintenance_tab()


def admin_page():
    """
    Entry point for users with the admin role on the Dashboard page.

    Delegates entirely to render_dashboard(), which builds the feature tab list
    dynamically. Admins see all nine tabs. User management has moved to the
    standalone admin_panel_page(), reachable via the Admin Panel sidebar button.
    """
    st.title("Dashboard")
    render_dashboard()


def _admin_verification_log_tab(engine):
    """
    Admin Panel → Verification Log tab.

    Read-only audit trail of every identity-verification attempt (one row
    per attempt, pass or fail) written by verify_student_identity() in
    exam_verification_feature.py. Joined against users so each row shows
    which account attempted verification, which document type was detected
    (institution student card, BC driver's licence, BC Services Card/BCID,
    or other Canadian government ID), the name/roll number read off it,
    its expiry status, and whether the face match succeeded.
    """
    st.subheader("Identity Verification Attempts")
    st.caption(
        "Every time a student goes through the ID document + selfie "
        "verification gate, the result is logged here — regardless of "
        "whether it passed."
    )

    df = pd.read_sql(
        text("""
            SELECT
                va.id, va.user_id, u.username, va.gate_key, va.document_type,
                va.expected_name, va.expected_roll_no, va.ocr_text,
                va.name_matched, va.roll_matched, va.expiry_date, va.expired,
                va.face_matched, va.face_distance, va.face_threshold,
                va.face_error, va.passed, va.created_at
            FROM verification_attempts va
            LEFT JOIN users u ON u.id = va.user_id
            ORDER BY va.created_at DESC
        """),
        engine,
    )

    if df.empty:
        st.info("No verification attempts have been recorded yet.")
        return

    document_type_labels = {
        "student_card": "Institution Student ID Card",
        "bc_drivers_licence": "BC Driver's Licence",
        "bc_services_card_or_bcid": "BC Services Card / BCID",
        "other_gov_id": "Other Canadian Government ID",
    }
    display_df = df.drop(columns=["user_id"]).copy()
    display_df["document_type"] = display_df["document_type"].map(document_type_labels).fillna(display_df["document_type"])
    display_df = display_df.rename(columns={
        "id": "ID",
        "username": "Account",
        "gate_key": "Gate",
        "document_type": "Document Type",
        "expected_name": "Name on File",
        "expected_roll_no": "Roll/T-ID on File",
        "ocr_text": "Text Read From Document",
        "name_matched": "Name Matched",
        "roll_matched": "Roll/T-ID Matched",
        "expiry_date": "Expiry Date",
        "expired": "Expired",
        "face_matched": "Face Matched",
        "face_distance": "Face Distance",
        "face_threshold": "Face Threshold",
        "face_error": "Face Error",
        "passed": "Passed",
        "created_at": "When",
    })
    st.dataframe(display_df, hide_index=True, width="stretch")


def _admin_maintenance_tab():
    """
    Admin Panel → Maintenance tab.

    Currently holds a single on-demand action: purge proctoring data (tab-
    switch/focus-loss events, screen-capture frame files, webcam frame files,
    keystroke logs, and mouse activity logs) older than a chosen retention
    window. This app has no background worker or cron, so nothing deletes
    this data unless an admin clicks the button here — see
    cleanup_old_proctor_data() in proctoring_feature.py for what it does and
    why this data is treated as short-lived in the first place.
    """
    st.subheader("Proctoring Data Cleanup")
    st.write(
        "Tab-switch/focus-loss events, screen-capture frames, webcam frames "
        "(with their face/gaze analysis), keystroke logs, and mouse activity "
        "logs recorded during proctored quizzes and exam submissions. "
        "Deleting them also removes the captured frame images from disk."
    )
    retention_days = st.number_input(
        "Delete proctoring data older than (days)",
        min_value=1, max_value=365, value=7,
        help="Events, frames, keystroke logs, and mouse activity logs older than this many days will be permanently deleted.",
    )
    if st.button("Run Proctoring Data Cleanup", type="primary"):
        with st.spinner("Cleaning up old proctoring data..."):
            result = cleanup_old_proctor_data(retention_days=int(retention_days))
        st.success(
            f"Deleted {result['events_deleted']} event(s), "
            f"{result['frames_deleted']} screen frame record(s), "
            f"{result['webcam_frames_deleted']} webcam frame record(s), "
            f"{result['keystrokes_deleted']} keystroke batch(es), "
            f"{result['mouse_events_deleted']} mouse-event batch(es), and "
            f"removed {result['files_removed']} image file(s) from disk."
        )


def _admin_users_tab(engine):
    """
    Admin Panel → Users tab.
    Provides two capabilities:
      1. Create a new user via an expander form.
      2. Select a user row in a dataframe and open the Edit or Reset Password
         dialog, or trigger the Delete confirmation dialog.
    Role and status changes are made through the Edit User dialog — there is
    no bulk editor.
    """
    # Load all users except the currently logged-in admin to prevent
    # self-modification of role or status. Selects the API key columns
    # that are surfaced in the admin Edit User dialog.
    current_admin_id = int(st.session_state.user["id"])
    df = pd.read_sql(
        text("""
            SELECT id, username, email, first_name, last_name,
                   phone, street_address, city, state_province, postal_code, country,
                   roll_no,
                   chatgpt_api_key, gemini_api_key, groq_api_key, github_token,
                   elevenlabs_api_key, cartesia_api_key, role, status,
                   pref_model_rag, pref_model_exam_grading, pref_model_exam_creation,
                   pref_model_advisor_ai, pref_model_wellness,
                   pref_model_quiz_generator, pref_model_video_lectures
            FROM users
            WHERE id != :aid
            ORDER BY username
        """),
        engine,
        params={"aid": current_admin_id},
    )

    # ---- Section 1: Create New User ----
    st.subheader("Create User")
    with st.expander("Create a New User", expanded=False):
        with st.form("admin_add_user_form"):
            st.markdown("**Account**")
            ac1, ac2 = st.columns(2)
            with ac1:
                new_first    = st.text_input("First Name")
                new_user     = st.text_input("Username")
                new_pwd      = st.text_input("Password", type="password")
            with ac2:
                new_last     = st.text_input("Last Name")
                new_email_in = st.text_input("Email")
                new_status   = st.selectbox("Status", ["active", "inactive"], index=1)
            new_role = st.selectbox("Role", ["user", "admin", "teacher", "student"], index=0)
            new_roll = st.text_input("Roll Number (students only, optional)")

            st.divider()
            st.markdown("**Contact & Address**")
            new_phone = st.text_input("Phone (optional)")
            new_street, new_city, new_state, new_postal, new_country = render_address_fields(
                "create_user"
            )

            st.divider()
            st.markdown("**AI API Keys (optional)**")
            k1, k2 = st.columns(2)
            with k1:
                new_chatgpt = st.text_input("ChatGPT / OpenAI Key", type="password", placeholder="Enter API key")
                new_groq    = st.text_input("Groq Key",             type="password", placeholder="Enter API key")
            with k2:
                new_gemini  = st.text_input("Gemini Key",           type="password", placeholder="Enter API key")
                new_github  = st.text_input("GitHub Token",         type="password", placeholder="Enter API key")

            st.divider()
            st.markdown("**Model Preferences (optional)**")
            st.caption(
                "Set the preferred AI model for each feature for this user. "
                "Defaults to the first available model if left unchanged."
            )

            # Widget keys prefixed admin_new_pref_ to avoid collision with
            # the admin_edit_pref_ keys used in the Edit User dialog.
            _new_model_names = list(LLM_MODELS.keys())
            np1, np2 = st.columns(2)
            with np1:
                new_pref_rag = st.selectbox(
                    "RAG System", _new_model_names, key="admin_new_pref_rag"
                )
                new_pref_exam_grading = st.selectbox(
                    "Exam Grading", _new_model_names, key="admin_new_pref_exam_grading"
                )
                new_pref_exam_creation = st.selectbox(
                    "Exam Creation", _new_model_names, key="admin_new_pref_exam_creation"
                )
            with np2:
                new_pref_advisor = st.selectbox(
                    "Advisor AI", _new_model_names, key="admin_new_pref_advisor"
                )
                new_pref_wellness = st.selectbox(
                    "Student Wellness", _new_model_names, key="admin_new_pref_wellness"
                )
                new_pref_quiz = st.selectbox(
                    "Practice Quiz", _new_model_names, key="admin_new_pref_quiz"
                )
                new_pref_video = st.selectbox(
                    "Video Lectures", _new_model_names, key="admin_new_pref_video"
                )

            submitted = st.form_submit_button("Create User", type="primary")

    if submitted:
        # Apply transformations at submission time.
        new_first    = new_first.strip().title()
        new_last     = new_last.strip().title()
        new_user     = new_user.strip()
        new_email_in = new_email_in.strip()
        new_phone    = new_phone.strip()
        new_street   = new_street.strip()
        new_city     = new_city.strip()
        new_state    = new_state.strip()
        new_postal   = new_postal.strip()
        new_country  = new_country.strip()
        new_chatgpt  = new_chatgpt.strip() or None
        new_gemini   = new_gemini.strip()  or None
        new_groq     = new_groq.strip()    or None
        new_github   = new_github.strip()  or None
        new_roll     = new_roll.strip()    or None

        errors = validate_user_form(
            username=new_user, email=new_email_in, password=new_pwd,
            first_name=new_first, last_name=new_last, phone=new_phone,
            street=new_street, city=new_city, state_prov=new_state,
            postal_code=new_postal, country=new_country,
        )
        roll_err = validate_roll_no(new_roll)
        if roll_err:
            errors.append(roll_err)
        if errors:
            show_errors(errors)
        else:
            api_key_errors = [
                validate_api_key(new_chatgpt, "ChatGPT / OpenAI"),
                validate_api_key(new_gemini,  "Gemini"),
                validate_api_key(new_groq,    "Groq"),
                validate_api_key(new_github,  "GitHub Token"),
            ]
            api_key_errors = [msg for msg in api_key_errors if msg]
            if api_key_errors:
                show_errors(api_key_errors)
            else:
                valid_email, _ = validate_email_field(new_email_in)
                if not is_username_unique(new_user):
                    st.error("That username is already taken.")
                elif not is_email_unique(valid_email):
                    st.error("That email address is already registered.")
                elif new_phone and not is_phone_unique(new_phone):
                    st.error("That phone number is already registered.")
                elif new_roll and not is_roll_no_unique(new_roll):
                    st.error("That roll number is already registered.")
                else:
                    try:
                        admin_create_user(
                            username=new_user, email=valid_email, password=new_pwd,
                            first_name=new_first, last_name=new_last, phone=new_phone,
                            street=new_street, city=new_city, state_prov=new_state,
                            postal_code=new_postal, country=new_country,
                            role=new_role, status=new_status,
                            roll_no=new_roll,
                            chatgpt_key=new_chatgpt, gemini_key=new_gemini,
                            groq_key=new_groq, github_token=new_github,
                            pref_rag           = LLM_MODELS[new_pref_rag],
                            pref_exam_grading  = LLM_MODELS[new_pref_exam_grading],
                            pref_exam_creation = LLM_MODELS[new_pref_exam_creation],
                            pref_advisor_ai    = LLM_MODELS[new_pref_advisor],
                            pref_wellness      = LLM_MODELS[new_pref_wellness],
                            pref_quiz_generator= LLM_MODELS[new_pref_quiz],
                            pref_video_lectures= LLM_MODELS[new_pref_video],
                        )
                        st.toast("User created.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to create user: {exc}")

    st.divider()

    # ---- Section 2: Individual User Management ----
    # Single-row selectable dataframe. The selected row populates the Edit and
    # Reset Password dialogs. Delete requires only the user ID and username.
    st.subheader("Manage Users")

    if df.empty:
        st.info("No other users found.")
    else:
        display_df = df[["id", "username", "first_name", "last_name", "email", "role", "status"]].copy()
        display_df.columns = ["ID", "Username", "First Name", "Last Name", "Email", "Role", "Status"]

        selection = st.dataframe(
            display_df,
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key="user_table_selection",
        )

        selected_rows = selection.selection.rows if selection.selection else []

        if selected_rows:
            row_idx   = selected_rows[0]
            user_row  = df.iloc[row_idx]
            u_id      = int(user_row["id"])
            uname_sel = user_row["username"]

            btn1, btn2, btn3, _ = st.columns([1.5, 1.5, 1.5, 5])
            with btn1:
                if st.button("Edit User", width="stretch"):
                    dialog_edit_user(user_row)
            with btn2:
                if st.button("Reset Password", width="stretch"):
                    dialog_reset_password(u_id, uname_sel)
            with btn3:
                if st.button("Delete User", type="primary", width="stretch"):
                    dialog_delete_user(u_id, uname_sel)
        else:
            st.caption("Select a row to manage a user.")



def _admin_courses_panel(engine):
    """
    Admin Panel → Courses tab.

    Provides a two-level hierarchy:
      courses     — all courses in the database shown as cards with Open,
                    Edit, Duplicate, and Delete actions. A Create New Course
                    form sits above the card list.
      assessments — all assessments for the selected course shown as cards
                    with Edit and Delete actions only (no Open). A breadcrumb
                    links back to the course list.

    Navigation is driven by admin_panel_view_level and
    admin_panel_selected_course in session state, which are independent of
    all feature-tab and global navigation keys.
    """
    level = st.session_state.admin_panel_view_level

    if level == "assessments":
        # ── Breadcrumb ───────────────────────────────────────────────────────
        course = st.session_state.admin_panel_selected_course
        course_name = course["name"] if course else "Course"

        col_spec = [0.14, 0.05, 0.18, max(0.01, 0.63)]
        cols = st.columns(col_spec)

        with cols[0]:
            st.markdown('<span class="bc-link">', unsafe_allow_html=True)
            if st.button("Courses", key="ap_bc_courses"):
                st.session_state.admin_panel_view_level = "courses"
                st.session_state.admin_panel_selected_course = None
                st.rerun()
            st.markdown('</span>', unsafe_allow_html=True)

        cols[1].markdown('<span class="bc-sep">/</span>', unsafe_allow_html=True)
        # Show course name and code together in the breadcrumb label.
        course_code  = course.get("code", "") if course else ""
        course_label = f"{course_name} {course_code}" if course_code else course_name
        cols[2].markdown(
            f'<span class="bc-current">{course_label}</span>',
            unsafe_allow_html=True,
        )
        st.divider()

        # ── Course detail: Assessments and Access sub-tabs ───────────────────
        # Admins have full access to both assessment management and access
        # control for every course. The Access tab uses _render_course_access_panel()
        # which already grants admins full sharing privileges via get_course_permission_context().
        ap_sub_tab_assessments, ap_sub_tab_access = st.tabs(["Assessments", "Access"])

        with ap_sub_tab_assessments:
            _admin_panel_assessments_view(engine, int(course["id"]))

        with ap_sub_tab_access:
            _render_course_access_panel(engine, int(course["id"]))

        return

    # ── Course list level ────────────────────────────────────────────────────
    uid = int(st.session_state.user["id"])

    # ---- Create New Course ----
    with st.expander("Create New Course", expanded=False):
        with st.form("ap_new_course_form", clear_on_submit=True):
            cc1, cc2 = st.columns(2)
            with cc1:
                c_code  = st.text_input("Course Code")
                c_hours = st.number_input("Credit Hours", min_value=1, max_value=12, value=3)
                c_sem   = st.selectbox("Semester", ["Winter", "Spring", "Summer", "Fall"])
            with cc2:
                c_name   = st.text_input("Course Name")
                c_year   = st.number_input("Year", min_value=2000, max_value=2100, value=2026)
                c_status = st.selectbox("Status", ["active", "inactive"], index=0)
            c_inst_name = st.text_input("Instructor Name (optional)")
            c_desc      = st.text_area("Description (optional)")
            create_sub  = st.form_submit_button("Create Course", type="primary")

    if create_sub:
        c_code      = c_code.strip()
        c_name      = c_name.strip()
        c_inst_name = c_inst_name.strip()
        c_desc      = c_desc.strip()

        course_errors = validate_course_form(
            course_code=c_code, course_name=c_name,
            credit_hours=c_hours, year=c_year,
            instructor_name=c_inst_name or "Admin",
        )
        if course_errors:
            show_errors(course_errors)
        elif not is_course_code_unique(c_code):
            st.error(f"Course code '{c_code}' is already in use.")
        else:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO courses
                                (course_code, course_name, credit_hours, year, semester,
                                 description, instructor_id, instructor_name, status)
                            VALUES
                                (:code, :name, :hours, :year, :sem,
                                 :desc, :ins_id, :ins_name, :status)
                        """),
                        {
                            "code":     c_code.upper(),
                            "name":     c_name,
                            "hours":    int(c_hours),
                            "year":     int(c_year),
                            "sem":      c_sem,
                            "desc":     c_desc,
                            "ins_id":   uid,
                            "ins_name": c_inst_name or "Admin",
                            "status":   c_status,
                        },
                    )
                st.toast("Course created.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to create course: {exc}")

    # ---- Manage Courses ----
    st.subheader("Manage Courses")

    df = pd.read_sql(
        "SELECT * FROM courses ORDER BY year DESC, semester, course_name", engine
    )

    if df.empty:
        st.info("No courses have been created yet.")
        return

    for _, row in df.iterrows():
        c_id   = int(row["id"])
        c_name = str(row["course_name"])
        c_code = str(row["course_code"])

        with st.container(border=True):
            col_info, col_actions = st.columns([4, 1])

            with col_info:
                st.markdown(f"**{c_name}**  `{c_code}`")
                st.caption(
                    f"{row['semester']} {row['year']}  ·  "
                    f"{row['credit_hours']} credit hours  ·  "
                    f"Instructor: {row['instructor_name']}  ·  "
                    f"Status: {row['status']}"
                )
                if row.get("description"):
                    st.caption(row["description"])

            with col_actions:
                if st.button("Open", key=f"ap_course_open_{c_id}", width="stretch"):
                    st.session_state.admin_panel_selected_course = {
                        "id": c_id, "name": c_name, "code": c_code,
                    }
                    st.session_state.admin_panel_view_level = "assessments"
                    st.rerun()

                if st.button("Edit", key=f"ap_course_edit_{c_id}", width="stretch"):
                    dialog_edit_course(engine, c_id, row.to_dict(), "admin")

                if st.button("Duplicate", key=f"ap_course_dup_{c_id}", width="stretch"):
                    try:
                        # Duplicate is owned by the logged-in admin.
                        admin_name = (
                            f"{st.session_state.user.get('first_name', '')} "
                            f"{st.session_state.user.get('last_name', '')}"
                        ).strip() or st.session_state.user.get("username", "Admin")

                        duplicate_course_for_teacher(
                            source_course_id=c_id,
                            new_owner_user_id=uid,
                            new_owner_name=admin_name,
                        )
                        st.toast(f"Course '{c_name}' duplicated.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Course duplication failed: {exc}")

                if st.button("Delete", key=f"ap_course_del_{c_id}",
                             width="stretch", type="primary"):
                    dialog_delete_course(engine, c_id, c_name)


def _admin_panel_assessments_view(engine, course_id: int):
    """
    Admin Panel → Courses tab → Assessment list for a selected course.

    Shows all assessments for the course as cards. Each card exposes Edit
    (opens dialog_edit_assessment) and Delete (opens dialog_delete_assessment).
    There is no Open button — this view is for management only.
    """
    df = pd.read_sql(
        text("SELECT * FROM assessments WHERE course_id = :cid ORDER BY created_at, title"),
        engine,
        params={"cid": course_id},
    )

    if df.empty:
        st.info("No assessments have been created for this course yet.")
        return

    st.subheader("Assessments")
    for _, row in df.iterrows():
        a_id    = int(row["id"])
        a_title = str(row["title"])

        with st.container(border=True):
            col_info, col_actions = st.columns([4, 1])

            with col_info:
                st.markdown(f"**{a_title}**")
                st.caption(f"Created: {row['created_at']}")
                if row.get("description"):
                    st.caption(row["description"])

            with col_actions:
                if st.button("Edit", key=f"ap_asm_edit_{a_id}", width="stretch"):
                    dialog_edit_assessment(engine, a_id, row.to_dict())

                if st.button("Delete", key=f"ap_asm_del_{a_id}",
                             width="stretch", type="primary"):
                    dialog_delete_assessment(engine, a_id, a_title)


def _admin_courses_tab(engine):
    """
    Admin → Courses tab.
    Displays all courses as cards. Opening a course card navigates into a
    two-sub-tab view: Assessments (the shared hierarchy dashboard) and Access
    (assign/revoke teachers and students for that specific course). This merges
    the former separate Course Access tab directly into the course card flow,
    so the course is already determined when access management begins.
    """
    st.subheader("Course Management")

    # ---- Create New Course ----
    with st.expander("Create New Course", expanded=False):
        with st.form("admin_new_course_form", clear_on_submit=True):
            cc1, cc2 = st.columns(2)
            with cc1:
                c_code  = st.text_input("Course Code")
                c_hours = st.number_input("Credit Hours", min_value=1, max_value=12, value=3)
                c_sem   = st.selectbox("Semester", ["Winter", "Spring", "Summer", "Fall"])
            with cc2:
                c_name   = st.text_input("Course Name")
                c_year   = st.number_input("Year", min_value=2000, max_value=2100, value=2026)
                c_status = st.selectbox("Status", ["active", "inactive"], index=0)
            c_inst_name = st.text_input("Instructor Display Name (optional)")
            c_desc      = st.text_area("Description (optional)")
            create_submit = st.form_submit_button("Create Course", type="primary")

    if create_submit:
        c_code      = c_code.strip()
        c_name      = c_name.strip()
        c_inst_name = c_inst_name.strip()
        c_desc      = c_desc.strip()

        course_errors = validate_course_form(
            course_code=c_code, course_name=c_name,
            credit_hours=c_hours, year=c_year,
            instructor_name=c_inst_name or "Admin",
        )
        if course_errors:
            show_errors(course_errors)
        elif not is_course_code_unique(c_code):
            st.error(f"Course code '{c_code}' is already in use.")
        else:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO courses
                                (course_code, course_name, credit_hours, year, semester,
                                 description, instructor_id, instructor_name, status)
                            VALUES
                                (:code, :name, :hours, :year, :sem,
                                 :desc, :ins_id, :ins_name, :status)
                        """),
                        {
                            "code":     c_code.upper(),
                            "name":     c_name,
                            "hours":    int(c_hours),
                            "year":     int(c_year),
                            "sem":      c_sem,
                            "desc":     c_desc,
                            "ins_id":   int(st.session_state.user["id"]),
                            "ins_name": c_inst_name or "Admin",
                            "status":   c_status,
                        },
                    )
                st.toast("Course created.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to create course: {exc}")

    # ---- Course Card Grid ----
    df = pd.read_sql("SELECT * FROM courses ORDER BY year DESC, semester, course_name", engine)

    if df.empty:
        st.info("No courses have been created yet.")
        return

    # Each card shows metadata inline and exposes Open and Delete actions.
    # Open navigates into the course detail view with Assessments and Access sub-tabs.
    for _, row in df.iterrows():
        with st.container(border=True):
            col_info, col_actions = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{row['course_name']}**  `{row['course_code']}`")
                st.caption(
                    f"{row['semester']} {row['year']}  ·  "
                    f"{row['credit_hours']} credit hours  ·  "
                    f"Instructor: {row['instructor_name']}  ·  "
                    f"Status: {row['status']}"
                )
                if row.get("description"):
                    st.caption(row["description"])
            with col_actions:
                c_id   = int(row["id"])
                c_name = str(row["course_name"])
                c_code = str(row["course_code"])
                if st.button("Open", key=f"open_course_{c_id}", width="stretch"):
                    st.session_state.selected_course = {"id": c_id, "name": c_name, "code": c_code}
                    st.session_state.view_level = "assessments"
                    st.session_state.current_page = "dashboard"
                    st.rerun()
                if st.button("Delete", key=f"del_course_{c_id}", width="stretch", type="primary"):
                    dialog_delete_course(engine, c_id, c_name)

    st.divider()

    # ---- Bulk Edit Courses ----
    # Allows batch updates to course fields. Validation runs across all changed
    # rows before any DB write is committed.
    with st.expander("Bulk Edit Courses", expanded=False):
        bulk_config = {
            "id":            None,
            "instructor_id": None,
            "created_at":    None,
            "semester":      st.column_config.SelectboxColumn("Semester", options=["Winter", "Spring", "Summer", "Fall"], required=True),
            "status":        st.column_config.SelectboxColumn("Status",   options=["active", "inactive"], required=True),
        }
        st.data_editor(df, column_config=bulk_config, hide_index=True,
                       width="stretch", key="admin_course_editor")

        if st.button("Apply Course Changes", type="primary", key="bulk_course_update"):
            changes = st.session_state.get("admin_course_editor", {}).get("edited_rows", {})
            if not changes:
                st.info("No changes to apply.")
                return

            all_errors = []
            for row_idx, vals in changes.items():
                c_id  = int(df.iloc[row_idx]["id"])
                code  = str(vals.get("course_code",     df.iloc[row_idx]["course_code"])).strip()
                name  = str(vals.get("course_name",     df.iloc[row_idx]["course_name"])).strip()
                hours = vals.get("credit_hours",        df.iloc[row_idx]["credit_hours"])
                year  = vals.get("year",                df.iloc[row_idx]["year"])
                inst  = str(vals.get("instructor_name", df.iloc[row_idx]["instructor_name"])).strip()
                row_errors = validate_course_form(
                    course_code=code, course_name=name,
                    credit_hours=hours, year=year, instructor_name=inst,
                )
                for err in row_errors:
                    all_errors.append(f"Row {row_idx + 1}: {err}")
                if not row_errors and not is_course_code_unique(code, exclude_id=c_id):
                    all_errors.append(
                        f"Row {row_idx + 1}: Course code '{code}' is already used by another course."
                    )

            if all_errors:
                show_errors(all_errors)
                return

            try:
                for row_idx, vals in changes.items():
                    c_id = int(df.iloc[row_idx]["id"])
                    update_course_details(
                        c_id,
                        str(vals.get("course_code",    df.iloc[row_idx]["course_code"])).strip().upper(),
                        str(vals.get("course_name",    df.iloc[row_idx]["course_name"])).strip(),
                        int(vals.get("credit_hours",   df.iloc[row_idx]["credit_hours"])),
                        int(vals.get("year",           df.iloc[row_idx]["year"])),
                        str(vals.get("semester",       df.iloc[row_idx]["semester"])),
                        str(vals.get("description",    df.iloc[row_idx]["description"])),
                        str(vals.get("instructor_name",df.iloc[row_idx]["instructor_name"])).strip(),
                    )
                st.session_state["admin_course_editor"]["edited_rows"] = {}
                st.toast("Courses updated.")
                st.rerun()
            except Exception as exc:
                st.error(f"Bulk update failed: {exc}")


def _render_course_access_panel(engine, course_id: int, tab_key=None):
    """
    Access management panel for a single course.

    Sharing rules implemented here:

      - Admins can share the course with teachers and students.
      - The teacher who created/owns the course can share it with teachers and students.
      - A shared teacher can still manage student sharing, but cannot share the
        course with additional teachers.
      - Students never receive this panel because their access is read-only.

    tab_key namespaces all widget keys so this panel can be rendered inside
    each of the three feature tabs simultaneously without DuplicateWidgetID errors.
    No navigation state is written here — only access management — so _nav_key()
    is used exclusively for widget keys, not for session state nav reads/writes.
    """
    perms = get_course_permission_context(engine, course_id)
    if not perms["can_manage_sharing"]:
        st.info("Only admins and teachers with approved teacher access can manage course sharing.")
        return

    course_row = pd.read_sql(
        text("SELECT instructor_id FROM courses WHERE id = :cid"),
        engine,
        params={"cid": int(course_id)},
    )
    owner_id = int(course_row.iloc[0]["instructor_id"]) if not course_row.empty else None
    current_uid = int(st.session_state.user["id"])

    # Only admins and the course owner can share the course with other teachers.
    # Shared teachers are intentionally blocked from teacher-to-teacher sharing.
    can_share_teachers = perms["is_admin"] or perms["is_owner"]

    users_df = pd.read_sql(
        text("""
            SELECT id, username, role, status
            FROM users
            WHERE status = 'active'
            ORDER BY username
        """),
        engine,
    )

    access_df = pd.read_sql(
        text("""
            SELECT ca.user_id, u.username, ca.access_role, ca.status, ca.updated_at
            FROM course_access ca
            JOIN users u ON u.id = ca.user_id
            WHERE ca.course_id = :cid
            ORDER BY ca.access_role, u.username
        """),
        engine,
        params={"cid": int(course_id)},
    )

    active_access = access_df[access_df["status"] == "approved"].copy() if not access_df.empty else pd.DataFrame()

    shared_teacher_ids = set()
    shared_student_ids = set()
    if not active_access.empty:
        shared_teacher_ids = set(
            active_access.loc[active_access["access_role"] == "teacher", "user_id"].astype(int).tolist()
        )
        shared_student_ids = set(
            active_access.loc[active_access["access_role"] == "student", "user_id"].astype(int).tolist()
        )

    st.markdown("**Share Course Access**")
    col_t, col_s = st.columns(2)

    with col_t:
        st.caption("Share with teachers")

        if not can_share_teachers:
            st.info("Only the course owner or an admin can share this course with other teachers.")
        else:
            teacher_df = users_df[users_df["role"] == "teacher"].copy()

            if shared_teacher_ids:
                teacher_df = teacher_df[~teacher_df["id"].astype(int).isin(shared_teacher_ids)]

            if teacher_df.empty:
                st.info("No additional active teachers are available to share with.")
            else:
                teacher_map = {
                    f"{r.username} (ID {r.id})": int(r.id)
                    for r in teacher_df.itertuples(index=False)
                }
                teacher_sel = st.selectbox(
                    "Teacher account",
                    ["-- Select --"] + list(teacher_map.keys()),
                    key=f"share_teacher_{tab_key}_{course_id}" if tab_key else f"share_teacher_{course_id}",
                )
                if teacher_sel != "-- Select --":
                    _gt_key = f"grant_teacher_{tab_key}_{course_id}" if tab_key else f"grant_teacher_{course_id}"
                    if st.button("Grant Teacher Access", key=_gt_key, width="stretch"):
                        grant_course_access(course_id, teacher_map[teacher_sel], "teacher")
                        st.toast("Teacher access granted.")
                        st.rerun()

    with col_s:
        st.caption("Share with students")
        student_df = users_df[users_df["role"] == "student"].copy()

        if shared_student_ids:
            student_df = student_df[~student_df["id"].astype(int).isin(shared_student_ids)]

        if student_df.empty:
            st.info("No additional active students are available to share with.")
        else:
            student_map = {
                f"{r.username} (ID {r.id})": int(r.id)
                for r in student_df.itertuples(index=False)
            }
            student_sel = st.selectbox(
                "Student account",
                ["-- Select --"] + list(student_map.keys()),
                key=f"share_student_{tab_key}_{course_id}" if tab_key else f"share_student_{course_id}",
            )
            if student_sel != "-- Select --":
                _gs_key = f"grant_student_{tab_key}_{course_id}" if tab_key else f"grant_student_{course_id}"
                if st.button("Grant Student Access", key=_gs_key, width="stretch"):
                    grant_course_access(course_id, student_map[student_sel], "student")
                    st.toast("Student access granted.")
                    st.rerun()

    st.divider()
    st.markdown("**Current Access**")

    if access_df.empty:
        st.info("No access records for this course.")
        return

    for _, row in access_df.iterrows():
        target_user_id = int(row["user_id"])
        target_role    = str(row["access_role"])
        is_owner_row   = owner_id is not None and target_user_id == owner_id and target_role == "teacher"

        col_info, col_btn = st.columns([5, 1])
        with col_info:
            badges = []
            if is_owner_row:
                badges.append("Owner")
            if target_user_id == current_uid:
                badges.append("You")
            badge_text = f" [{' · '.join(badges)}]" if badges else ""
            st.markdown(
                f"**{row['username']}** — {target_role.capitalize()}{badge_text}  "
                f"·  Status: {row['status']}"
            )

        with col_btn:
            btn_key = (f"revoke_{tab_key}_{course_id}_{target_user_id}_{target_role}"
                       if tab_key else f"revoke_{course_id}_{target_user_id}_{target_role}")
            revoke_disabled = False
            revoke_help = None

            if not perms["is_admin"] and is_owner_row:
                revoke_disabled = True
                revoke_help = "Only an admin can revoke the owning teacher's access."

            if st.button("Revoke", key=btn_key, width="stretch", disabled=revoke_disabled, help=revoke_help):
                dialog_revoke_access(
                    engine,
                    course_id,
                    target_user_id,
                    row["username"],
                    target_role,
                )


# =============================================================================
# TEACHER / STUDENT / BASIC USER ENTRY POINTS
# =============================================================================

def teacher_page():
    """
    Entry point for users with the teacher role on the Dashboard page.

    Delegates to render_dashboard(), which builds the feature tab list
    dynamically. Teachers see all nine tabs, including Exam Grading, Exam
    Creation, Oral Examination, and Video Lectures.
    """
    st.title("Dashboard")
    render_dashboard()


def student_page():
    """
    Entry point for users with the student role on the Dashboard page.

    Delegates to render_dashboard(), which filters the tab list based on role.
    Students see eight tabs — Exam Creation is excluded entirely from the
    rendered tab set; Exam Grading and Oral Examination stay visible and each
    render a cut-down student view instead of the full teacher/admin workflow.
    """
    st.title("Dashboard")
    render_dashboard()


def home_page():
    """
    Entry point for authenticated users with the base 'user' role who have not
    yet been assigned a functional role by an administrator.
    """
    st.title("Dashboard")
    st.info(
        "Your account is active but has not been assigned a role yet. "
        "Contact an administrator to be assigned the teacher or student role "
        "and gain access to courses."
    )


# =============================================================================
# SHARED HIERARCHICAL DASHBOARD (Courses → Assessments → Files)
# =============================================================================

def render_hierarchy_dashboard():
    """
    Shared course/assessment/files navigation used by all role views.

    view_level drives which view is rendered:
      "courses"     → course card grid
      "assessments" → assessment accordion (+ Access sub-tab for admins)
      "files"       → file list and AI prompt interface

    The breadcrumb bar is shown on the assessments and files levels and acts
    as the primary back-navigation mechanism.
    """
    engine = get_engine()
    level  = st.session_state.view_level

    if level in ("assessments", "files"):
        render_breadcrumb()

    if level == "courses":
        render_courses_view(engine)
    elif level == "assessments":
        render_assessments_view(engine)
    elif level == "files":
        render_files_view(engine)


def render_courses_view(engine, tab_key=None):
    """
    Top-level courses view shared by all roles.
    Admins and teachers see a course creation form above the card grid.
    Admins see all courses; teachers see only courses with approved access
    (including any they created). Students see only courses with approved access.

    Teacher course creation:
      On successful INSERT, grant_course_access() is called immediately with
      status='approved' so the new course appears on the teacher's dashboard
      without requiring admin approval.

    Teacher duplication:
      Any teacher can duplicate any course visible in their course list.
      The duplicate becomes a brand-new course owned only by that teacher,
      including copied assessments and files, but no copied shared access.
    """
    role = st.session_state.user.get("role")
    uid  = int(st.session_state.user["id"])

    # ---- Course creation form (admin and teacher only) ----
    if role in ("admin", "teacher"):
        default_inst = (
            f"{st.session_state.user.get('first_name', '')} "
            f"{st.session_state.user.get('last_name', '')}".strip()
            if role == "teacher" else ""
        )

        with st.expander("Create New Course", expanded=False):
            with st.form(_nav_key("new_course_form", tab_key), clear_on_submit=True):
                cc1, cc2 = st.columns(2)
                with cc1:
                    c_code  = st.text_input("Course Code")
                    c_hours = st.number_input("Credit Hours", min_value=1, max_value=12, value=3)
                    c_sem   = st.selectbox("Semester", ["Winter", "Spring", "Summer", "Fall"])
                with cc2:
                    c_name = st.text_input("Course Name")
                    c_year = st.number_input("Year", min_value=2000, max_value=2100, value=2026)
                c_inst_name = st.text_input("Instructor Name", value=default_inst)
                c_desc      = st.text_area("Description (optional)")
                create_sub  = st.form_submit_button("Create Course")

        if create_sub:
            c_code      = c_code.strip()
            c_name      = c_name.strip()
            c_inst_name = c_inst_name.strip()
            c_desc      = c_desc.strip()

            course_errors = validate_course_form(
                course_code=c_code, course_name=c_name,
                credit_hours=c_hours, year=c_year, instructor_name=c_inst_name,
            )
            if course_errors:
                show_errors(course_errors)
            elif not is_course_code_unique(c_code):
                st.error(f"Course code '{c_code}' is already in use.")
            else:
                try:
                    with engine.begin() as conn:
                        result = conn.execute(
                            text("""
                                INSERT INTO courses
                                    (course_code, course_name, credit_hours, year, semester,
                                     description, instructor_id, instructor_name)
                                VALUES
                                    (:code, :name, :hours, :year, :sem,
                                     :desc, :ins_id, :ins_name)
                            """),
                            {
                                "code":     c_code.upper(),
                                "name":     c_name,
                                "hours":    int(c_hours),
                                "year":     int(c_year),
                                "sem":      c_sem,
                                "desc":     c_desc,
                                "ins_id":   uid,
                                "ins_name": c_inst_name,
                            },
                        )
                        new_course_id = result.lastrowid

                    if role == "teacher":
                        grant_course_access(new_course_id, uid, "teacher")

                    st.toast("Course created.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Database error: {exc}")

    # ---- Load courses ----
    if role == "admin":
        df = pd.read_sql(
            "SELECT * FROM courses ORDER BY year DESC, semester, course_name", engine
        )
    else:
        access_role = "teacher" if role == "teacher" else "student"
        df = pd.read_sql(
            text("""
                SELECT c.*
                FROM courses c
                JOIN course_access ca ON ca.course_id = c.id
                WHERE ca.user_id     = :uid
                  AND ca.access_role = :ar
                  AND ca.status      = 'approved'
                ORDER BY c.year DESC, c.semester, c.course_name
            """),
            engine,
            params={"uid": uid, "ar": access_role},
        )

    if df.empty:
        st.info(
            "No courses are assigned to your account. "
            "Contact an administrator if you believe this is an error."
            if role != "admin"
            else "No courses have been created yet."
        )
        return

    # ---- Course cards ----
    st.subheader("Courses")
    for _, row in df.iterrows():
        with st.container(border=True):
            col_info, col_actions = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{row['course_name']}**  `{row['course_code']}`")
                st.caption(
                    f"{row['semester']} {row['year']}  ·  "
                    f"{row['credit_hours']} credit hours  ·  "
                    f"Instructor: {row['instructor_name']}"
                )
                if row.get("description"):
                    st.caption(row["description"])

            with col_actions:
                c_id   = int(row["id"])
                c_name = str(row["course_name"])
                c_code = str(row["course_code"])

                if st.button("Open", key=_nav_key(f"course_open_{c_id}", tab_key), width="stretch"):
                    st.session_state[_nav_key("selected_course", tab_key)] = {"id": c_id, "name": c_name, "code": c_code}
                    st.session_state[_nav_key("view_level", tab_key)] = "assessments"
                    st.rerun()

                # Edit button: visible to admin and to the teacher who created
                # this course. Passes the full row as a dict so the modal can
                # pre-populate every field without an extra DB query.
                is_owner = (role == "teacher" and int(row.get("instructor_id", -1)) == uid)
                if role == "admin" or is_owner:
                    if st.button("Edit", key=_nav_key(f"course_edit_{c_id}", tab_key), width="stretch"):
                        dialog_edit_course(engine, c_id, row.to_dict(), role, tab_key=tab_key)

                # Any teacher can duplicate any course visible in their own list.
                # The duplicate becomes a fully independent course they own.
                if role == "teacher":
                    if st.button("Duplicate", key=_nav_key(f"course_dup_{c_id}", tab_key), width="stretch"):
                        try:
                            owner_name = (
                                f"{st.session_state.user.get('first_name', '')} "
                                f"{st.session_state.user.get('last_name', '')}"
                            ).strip() or st.session_state.user.get("username", "Teacher")

                            new_course_id = duplicate_course_for_teacher(
                                source_course_id=c_id,
                                new_owner_user_id=uid,
                                new_owner_name=owner_name,
                            )

                            st.toast("Course duplicated.")
                            st.session_state[_nav_key("selected_course", tab_key)] = {
                                "id": new_course_id,
                                "name": f"{c_name} (Copy)",
                            }
                            st.session_state[_nav_key("view_level", tab_key)] = "courses"
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Course duplication failed: {exc}")

                # Teachers can only delete courses they created themselves.
                if role == "admin" or is_owner:
                    if st.button("Delete", key=_nav_key(f"course_del_{c_id}", tab_key),
                                 width="stretch", type="primary"):
                        dialog_delete_course(engine, c_id, c_name, tab_key=tab_key)




def render_assessments_view(engine, tab_key=None):
    """
    Assessments view for a selected course.

    Admins and teachers with approved teacher access receive:
      - The Assessments tab for internal course content.
      - The Access tab for sharing the course with teachers or students.

    Students receive only the assessments list and cannot modify content.

    tab_key is forwarded to every nested function so that all widget keys
    and navigation state reads/writes remain isolated to this tab.
    When None, global session state keys are used (legacy behaviour for
    render_hierarchy_dashboard()).
    """
    c_id = int(st.session_state[_nav_key("selected_course", tab_key)]["id"])
    perms = get_course_permission_context(engine, c_id)

    if not perms["can_view"]:
        st.error("You do not have access to this course.")
        reset_navigation(tab_key)
        return

    if perms["can_manage_sharing"]:
        tab_asm, tab_access = st.tabs(["Assessments", "Access"])
        with tab_asm:
            _render_assessments_content(engine, c_id, perms, tab_key=tab_key)
        with tab_access:
            _render_course_access_panel(engine, c_id, tab_key=tab_key)
    else:
        _render_assessments_content(engine, c_id, perms, tab_key=tab_key)


def _render_assessments_content(engine, c_id: int, perms: dict, tab_key=None):
    """
    Render the assessments content for a course using the resolved permission
    context for the current user.

    Teacher-level access (owner or shared teacher) can create, edit, and delete
    internal course content. Student-level access is read-only.

    tab_key namespaces all widget keys so this function can be rendered
    simultaneously inside all three feature tabs without DuplicateWidgetID errors.
    When None, the original unnamespaced keys are used (global hierarchy context).
    """
    can_edit_content = perms["can_edit_content"]
    is_student_read_only = perms["is_student_read_only"]

    if can_edit_content:
        with st.expander("Create New Assessment", expanded=False):
            # Form key namespaced to prevent collision across the three tabs.
            with st.form(_nav_key("new_assessment_form", tab_key), clear_on_submit=True):
                a_title = st.text_input("Title")
                a_desc  = st.text_area("Description (optional)")
                create_sub = st.form_submit_button("Create Assessment")

        if create_sub:
            a_title = a_title.strip()
            a_desc  = a_desc.strip()

            asm_errors = validate_assessment_form(title=a_title)
            if asm_errors:
                show_errors(asm_errors)
            else:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO assessments
                                (course_id, title, description)
                            VALUES
                                (:c_id, :title, :desc)
                        """),
                        {
                            "c_id":  c_id,
                            "title": a_title,
                            "desc":  a_desc,
                        },
                    )
                st.toast("Assessment created.")
                st.rerun()
    elif is_student_read_only:
        st.info("You have limited access to this course.")

    df = pd.read_sql(
        text("SELECT * FROM assessments WHERE course_id = :cid ORDER BY created_at, title"),
        engine,
        params={"cid": c_id},
    )

    if df.empty:
        st.info("No assessments have been created for this course yet.")
        return

    st.subheader("Assessments")
    for _, row in df.iterrows():
        a_id    = int(row["id"])
        a_title = str(row["title"])
        with st.container(border=True):
            col_info, col_actions = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{a_title}**")
                st.caption(f"Created: {row['created_at']}")
                if row.get("description"):
                    st.caption(row["description"])
            with col_actions:
                # Open button: namespaced so the same assessment ID does not
                # produce the same key across three simultaneously-rendered tabs.
                if st.button("Open", key=_nav_key(f"open_asm_{a_id}", tab_key), width="stretch"):
                    st.session_state[_nav_key("selected_assessment", tab_key)] = {
                        "id": a_id,
                        "title": a_title,
                    }
                    st.session_state[_nav_key("view_level", tab_key)] = "files"
                    st.rerun()

                if can_edit_content:
                    # Edit button opens a modal pre-populated with all fields
                    # for this assessment. Passes the row as a dict to avoid
                    # an extra DB query inside the dialog.
                    if st.button("Edit", key=_nav_key(f"edit_asm_{a_id}", tab_key), width="stretch"):
                        dialog_edit_assessment(engine, a_id, row.to_dict(), tab_key=tab_key)

                if can_edit_content:
                    if st.button("Delete", key=_nav_key(f"del_asm_{a_id}", tab_key),
                                 width="stretch", type="primary"):
                        dialog_delete_assessment(engine, a_id, a_title)



def render_files_view(engine):
    """
    Files view for a selected assessment.

    Admins and teachers with approved teacher access can upload and delete
    course files. Students with approved student access can read the file list
    only and do not receive modification or AI prompt controls here.
    """
    a_id = int(st.session_state.selected_assessment["id"])
    c_id = int(st.session_state.selected_course["id"])
    perms = get_course_permission_context(engine, c_id)

    if not perms["can_view"]:
        st.error("You do not have access to this course.")
        reset_navigation()
        return

    can_edit_content = perms["can_edit_content"]
    is_student_read_only = perms["is_student_read_only"]

    if can_edit_content:
        with st.expander("Upload Files", expanded=False):
            uploaded_files = st.file_uploader(
                "Select one or more files",
                type=["pdf", "txt", "png", "jpg", "jpeg", "webp", "md", "html", "json", "xml", "csv"],
                accept_multiple_files=True,
                key="file_uploader_widget",
            )
            if st.button("Upload", disabled=not uploaded_files, type="primary"):
                success_count = 0
                for uf in uploaded_files:
                    try:
                        saved_name, saved_path = save_uploaded_file(
                            file_bytes=uf.read(),
                            original_name=uf.name,
                            course_name=st.session_state.selected_course["name"],
                            assessment_name=st.session_state.selected_assessment["title"],
                            course_id=c_id,
                            feature_name="general",
                        )
                        with engine.begin() as conn:
                            conn.execute(
                                text("""
                                    INSERT INTO files (file_name, file_path, course_id, assessment_id, uploaded_by, feature_name)
                                    VALUES (:name, :path, :cid, :aid, :uid, :feat)
                                """),
                                {
                                    "name": saved_name,
                                    "path": saved_path,
                                    "cid":  c_id,
                                    "aid":  a_id,
                                    "uid":  int(st.session_state.user["id"]),
                                    "feat": "general",
                                },
                            )
                        success_count += 1
                    except Exception as exc:
                        st.error(f"Error uploading '{uf.name}': {exc}")
                if success_count:
                    st.toast(f"{success_count} file(s) uploaded.")
                    st.rerun()
    elif is_student_read_only:
        st.info("You have student access to this course. Files are read-only.")

    st.subheader("Files")
    df_files = pd.read_sql(
        text("SELECT * FROM files WHERE assessment_id = :aid ORDER BY uploaded_at DESC"),
        engine,
        params={"aid": a_id},
    )

    if df_files.empty:
        st.info("No files have been uploaded for this assessment.")
    else:
        for _, row in df_files.iterrows():
            f_id   = int(row["id"])
            f_name = str(row["file_name"])
            f_path = str(row["file_path"])
            if can_edit_content:
                col_name, col_date, col_btn = st.columns([4, 2, 1])
            else:
                col_name, col_date = st.columns([4, 2])

            with col_name:
                st.markdown(f"`{f_name}`")
            with col_date:
                st.caption(str(row["uploaded_at"]))
            if can_edit_content:
                with col_btn:
                    if st.button("Delete", key=f"del_file_{f_id}", width="stretch", type="primary"):
                        dialog_delete_file(engine, f_id, f_name, f_path)

    st.divider()

    # -----------------------------------------------------------------
    # STUDENT VIEW: Published quizzes for this assessment
    # Students see interactive quiz forms for any quiz the instructor
    # has published. The AI prompt tools are not shown to students.
    # -----------------------------------------------------------------
    if is_student_read_only:
        st.subheader("Quizzes")
        _render_student_quiz_view(engine, a_id)
        return

    # -----------------------------------------------------------------
    # INSTRUCTOR / ADMIN VIEW: Quizzes
    # -----------------------------------------------------------------
    st.subheader("Quizzes")
    _render_instructor_quiz_tab(engine, a_id)


# =============================================================================
# INSTRUCTOR QUIZ MANAGEMENT TAB
# =============================================================================

# CSS injected once for the quiz preview table. Uses a unique class name to
# avoid conflicting with any other tables on the page. Borders and padding
# mirror the general card style used elsewhere in the application.
_QUIZ_PREVIEW_CSS = """
<style>
.quiz-preview-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
    margin-top: 0.5rem;
}
.quiz-preview-table th {
    text-align: left;
    padding: 6px 10px;
    border-bottom: 2px solid #444;
    color: #aaa;
    font-weight: 600;
    white-space: nowrap;
}
.quiz-preview-table td {
    padding: 8px 10px;
    border-bottom: 1px solid #2e2e2e;
    vertical-align: top;
    line-height: 1.45;
}
.quiz-preview-table tr:last-child td { border-bottom: none; }
.quiz-preview-table .badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.badge-tf     { background: #1e3a5f; color: #7ab3e0; }
.badge-mcq    { background: #1e3d2f; color: #6dcf9e; }
.badge-sa     { background: #3d2a1e; color: #d4956a; }
.answer-text  { color: #6dcf9e; font-weight: 500; }
.option-correct { font-weight: 600; }
</style>
"""


def _render_instructor_quiz_tab(engine, a_id: int):
    """
    Render the Quizzes tab visible to instructors and admins.

    Each quiz card shows:
      - Title, question count, grading mode, and creation timestamp.
      - Publish / Unpublish button to control whether students can see the quiz.
      - Show Grades / Hide Grades button — independent of publish so the
        instructor can collect all submissions before releasing scores.
      - A full question preview table with correct answers highlighted.
      - A Submissions section listing every student who has submitted, with
        their auto-calculated score and controls for manual or AI grading.

    Status labels use plain text (Published / Unpublished, Grades Visible /
    Grades Hidden) rather than emoji icons to keep the interface clean and
    consistent with the rest of the application.
    """
    st.markdown(_QUIZ_PREVIEW_CSS, unsafe_allow_html=True)

    quizzes_df = pd.read_sql(
        text("""
            SELECT
                q.id,
                q.title,
                q.published,
                q.grades_visible,
                q.grading_mode,
                q.created_at,
                COUNT(qq.id) AS question_count
            FROM quizzes q
            LEFT JOIN quiz_questions qq ON qq.quiz_id = q.id
            WHERE q.assessment_id = :aid
            GROUP BY q.id
            ORDER BY q.created_at DESC
        """),
        engine,
        params={"aid": a_id},
    )

    if quizzes_df.empty:
        st.info("No quizzes have been created for this assessment yet.")
        return

    for _, row in quizzes_df.iterrows():
        quiz_id        = int(row["id"])
        is_published   = bool(row["published"])
        grades_visible = bool(row["grades_visible"])
        grading_mode   = str(row["grading_mode"])
        q_count        = int(row["question_count"])

        # Determine which AI provider / key to use for AI grading, resolved
        # lazily here so it is available to the grading controls below.
        user           = st.session_state.user

        with st.container(border=True):

            # ---- Quiz header row ----
            st.markdown(f"#### {row['title']}")
            st.caption(
                f"{q_count} question(s)  ·  "
                f"Grading: {grading_mode.capitalize()}  ·  "
                f"Created: {row['created_at']}"
            )

            # ---- Control row: publish, grades, grading mode change ----
            ctrl1, ctrl2, ctrl3 = st.columns(3)

            with ctrl1:
                # Publish toggle: controls question visibility to students.
                pub_label = "Unpublish" if is_published else "Publish"
                pub_status = "Published" if is_published else "Unpublished"
                st.caption(f"Status: {pub_status}")
                if st.button(pub_label, key=f"pub_{quiz_id}", width="stretch"):
                    set_quiz_published(quiz_id, not is_published)
                    st.toast(f"Quiz {'unpublished' if is_published else 'published'}.")
                    st.rerun()

            with ctrl2:
                # Grades visibility toggle: independent of publish so instructors
                # can finish reviewing before revealing scores to students.
                grade_status = "Grades Visible" if grades_visible else "Grades Hidden"
                grade_label  = "Hide Grades" if grades_visible else "Show Grades"
                st.caption(f"Grades: {grade_status}")
                if st.button(grade_label, key=f"grade_vis_{quiz_id}", width="stretch"):
                    set_quiz_grades_visible(quiz_id, not grades_visible)
                    st.toast(f"Grades {'hidden' if grades_visible else 'visible'} for students.")
                    st.rerun()

            with ctrl3:
                # Grading mode selector. Changes are applied immediately on
                # selection so the instructor does not need a separate save step.
                mode_options  = ["auto", "manual"]
                mode_display  = {"auto": "Auto", "manual": "Manual"}
                current_index = mode_options.index(grading_mode) if grading_mode in mode_options else 0
                new_mode = st.selectbox(
                    "Grading Mode",
                    mode_options,
                    index=current_index,
                    format_func=lambda m: mode_display.get(m, m),
                    key=f"mode_sel_{quiz_id}",
                )
                if new_mode != grading_mode:
                    with engine.begin() as conn:
                        conn.execute(
                            text("UPDATE quizzes SET grading_mode = :m WHERE id = :qid"),
                            {"m": new_mode, "qid": quiz_id},
                        )
                    st.toast("Grading mode updated.")
                    st.rerun()

            st.divider()

            # ---- Question preview ----
            # Renders a styled HTML table so every question, its type badge,
            # options, and correct answer are visible in a compact scannable layout.
            with st.expander("Question Preview", expanded=False):
                questions_df = pd.read_sql(
                    text("""
                        SELECT id, question_order, question_type, question_text,
                               options_json, correct_answer
                        FROM quiz_questions
                        WHERE quiz_id = :qid
                        ORDER BY
                            FIELD(question_type, 'true_false', 'mcq', 'short_answer'),
                            question_order
                    """),
                    engine,
                    params={"qid": quiz_id},
                )

                if questions_df.empty:
                    st.info("This quiz has no questions.")
                else:
                    _render_question_preview_table(questions_df)

            # ---- Submissions panel ----
            with st.expander("Submissions", expanded=False):
                _render_submission_panel(engine, quiz_id, grading_mode, user)


def _render_question_preview_table(questions_df):
    """
    Render a compact HTML table of all questions in a quiz for instructor review.

    Each row shows the question number, a type badge (TF / MCQ / SA), the
    question body, the answer choices for MCQ questions (with the correct one
    highlighted), and the correct answer in a distinct colour.

    Plain HTML is used rather than individual st.markdown calls so all
    questions are rendered in a single paint pass without the per-row
    spacing overhead that Streamlit applies to block elements. The styling
    class names are defined in _QUIZ_PREVIEW_CSS, which is injected once at
    the top of _render_instructor_quiz_tab().
    """
    type_badge = {
        "true_false":   '<span class="badge badge-tf">T / F</span>',
        "mcq":          '<span class="badge badge-mcq">MCQ</span>',
        "short_answer": '<span class="badge badge-sa">SA</span>',
    }

    rows_html = ""
    q_num = 1

    for _, qrow in questions_df.iterrows():
        q_type  = str(qrow["question_type"])
        badge   = type_badge.get(q_type, q_type)
        q_text  = str(qrow["question_text"])
        correct = qrow.get("correct_answer") or ""

        # Build the answer / options cell content per question type.
        if q_type == "mcq" and qrow.get("options_json"):
            try:
                options = json.loads(qrow["options_json"])
                option_parts = []
                for opt in options:
                    if opt == correct:
                        option_parts.append(
                            f'<span class="option-correct answer-text">{opt} (correct)</span>'
                        )
                    else:
                        option_parts.append(opt)
                answer_cell = "<br>".join(option_parts)
            except (json.JSONDecodeError, TypeError):
                answer_cell = f'<span class="answer-text">{correct}</span>'
        elif q_type == "true_false":
            answer_cell = f'<span class="answer-text">{correct}</span>'
        else:
            # Short answer: show the model reference answer if present.
            answer_cell = (
                f'<span class="answer-text">{correct}</span>' if correct
                else '<span style="color:#666">—</span>'
            )

        rows_html += (
            f"<tr>"
            f"<td style='width:2.5rem;color:#888'>{q_num}</td>"
            f"<td style='width:5rem'>{badge}</td>"
            f"<td>{q_text}</td>"
            f"<td>{answer_cell}</td>"
            f"</tr>"
        )
        q_num += 1

    table_html = (
        '<table class="quiz-preview-table">'
        "<thead><tr>"
        "<th>#</th><th>Type</th><th>Question</th><th>Correct Answer</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def _render_submission_panel(engine, quiz_id: int, grading_mode: str, user: dict):
    """
    Render the submissions panel for a single quiz inside the instructor view.

    Lists every student who has submitted the quiz with their calculated score.
    The grading controls rendered per submission depend on the quiz's grading_mode:

      auto   — The auto-calculated score is shown. The instructor can optionally
               override it with a manual score using the override form.
      manual — The instructor enters a final score and optional notes per
               submission using a number input and text area.
    """
    submissions_df = pd.read_sql(
        text("""
            SELECT
                qs.id          AS submission_id,
                qs.student_id,
                u.username,
                u.first_name,
                u.last_name,
                qs.score,
                qs.manual_score,
                qs.grading_notes,
                qs.submitted_at
            FROM quiz_submissions qs
            JOIN users u ON u.id = qs.student_id
            WHERE qs.quiz_id = :qid
            ORDER BY qs.submitted_at ASC
        """),
        engine,
        params={"qid": quiz_id},
    )

    if submissions_df.empty:
        st.info("No students have submitted this quiz yet.")
        return

    # Load all questions once so the grading prompt can be built for any
    # submission without an additional query per row.
    questions_df = pd.read_sql(
        text("""
            SELECT id, question_type, question_text, options_json, correct_answer, question_order
            FROM quiz_questions
            WHERE quiz_id = :qid
            ORDER BY FIELD(question_type, 'true_false', 'mcq', 'short_answer'), question_order
        """),
        engine,
        params={"qid": quiz_id},
    )

    for _, sub in submissions_df.iterrows():
        sub_id      = int(sub["submission_id"])
        student_uid = int(sub["student_id"])
        auto_score  = sub["score"]
        man_score   = sub["manual_score"]
        notes       = sub.get("grading_notes") or ""
        display_name = f"{sub.get('first_name', '')} {sub.get('last_name', '')}".strip() \
                       or str(sub["username"])

        # The displayed score is the manual/AI override when set, otherwise
        # the auto-calculated score. None means not yet graded.
        effective_score = man_score if man_score is not None else auto_score
        score_text = f"{effective_score:.1f}%" if effective_score is not None else "Not graded"

        with st.container(border=True):
            st.markdown(f"**{display_name}**  ·  Score: {score_text}  ·  Submitted: {sub['submitted_at']}")
            if notes:
                st.caption(f"Notes: {notes}")

            # Load this student's individual answers for the grading prompt
            # and for display in the review expander.
            answers_df = pd.read_sql(
                text("""
                    SELECT qa.question_id, qa.answer_text, qa.is_correct
                    FROM quiz_answers qa
                    WHERE qa.submission_id = :sid
                """),
                engine,
                params={"sid": sub_id},
            )
            answer_map = {
                int(r["question_id"]): str(r.get("answer_text") or "")
                for _, r in answers_df.iterrows()
            }

            # ---- Student answers review expander ----
            # Parse per-question notes from grading_notes so the display
            # function can show the AI's explanation alongside each verdict.
            # grading_notes stores lines in the format "Q1: Correct — <note>"
            # after an AI grading pass; the dict maps 1-based question index
            # to the note text extracted from the right-hand side of " — ".
            q_notes_map: dict[int, str] = {}
            if notes:
                for line in notes.splitlines():
                    line = line.strip()
                    # Match lines that start with "Q<number>:" to extract
                    # the note portion after the verdict separator " — ".
                    if line.startswith("Q") and ":" in line and " — " in line:
                        try:
                            q_part = line.split(":")[0]  # e.g. "Q6"
                            q_idx  = int(q_part[1:])
                            note   = line.split(" — ", 1)[1].strip()
                            q_notes_map[q_idx] = note
                        except (ValueError, IndexError):
                            pass

            with st.expander("View Answers", expanded=False):
                _render_submission_answers(questions_df, answers_df, q_notes_map)

            # ---- Grading controls ----
            if grading_mode in ("manual", "auto"):
                # Both auto and manual mode expose an override form so the
                # instructor can correct the machine score when needed.
                label = "Override Score" if grading_mode == "auto" else "Enter Grade"
                with st.form(key=f"grade_form_{sub_id}"):
                    g1, g2 = st.columns([1, 3])
                    with g1:
                        new_score = st.number_input(
                            label,
                            min_value=0.0,
                            max_value=100.0,
                            value=float(man_score) if man_score is not None else (
                                float(auto_score) if auto_score is not None else 0.0
                            ),
                            step=0.5,
                            key=f"score_input_{sub_id}",
                        )
                    with g2:
                        new_notes = st.text_area(
                            "Grading Notes (optional)",
                            value=notes,
                            height=68,
                            key=f"notes_input_{sub_id}",
                        )
                    if st.form_submit_button("Save Grade", type="primary"):
                        save_grade(sub_id, new_score, new_notes)
                        st.toast(f"Grade saved for {display_name}.")
                        st.rerun()



def _render_submission_answers(questions_df, answers_df, q_notes_map: dict = None):
    """
    Render a read-only review of one student's answers for the instructor.

    Displayed inside the View Answers expander on each submission row.

    For True/False and MCQ questions, the student's answer is shown inline
    alongside a Correct / Incorrect verdict and the expected answer. These
    are always auto-graded at submission time so is_correct is always set.

    For Short Answer questions, the student's response is shown in a text
    area. If AI grading has been run (is_correct is not NULL), the verdict,
    the AI's per-question note explaining the evaluation, and the reference
    answer are all shown beneath the response. If the question has not yet
    been AI-graded, only the reference answer is shown for the instructor
    to assess manually.

    q_notes_map is an optional dict mapping 1-based question index to the
    AI note string extracted from the grading_notes field on the submission.
    It is built by _render_submission_panel before calling this function.
    """
    if q_notes_map is None:
        q_notes_map = {}

    answer_map = {
        int(r["question_id"]): r
        for _, r in answers_df.iterrows()
    }
    type_labels = {
        "true_false":   "True / False",
        "mcq":          "Multiple Choice",
        "short_answer": "Short Answer",
    }
    shown_types = set()
    q_num = 1

    for _, qrow in questions_df.iterrows():
        q_type = str(qrow["question_type"])
        q_id   = int(qrow["id"])

        if q_type not in shown_types:
            st.markdown(f"**{type_labels.get(q_type, q_type)}**")
            shown_types.add(q_type)

        a_row       = answer_map.get(q_id, {})
        student_ans = str(a_row.get("answer_text") or "")

        # is_correct is NULL until grading writes it. pandas may return
        # numpy integers or None, so check explicitly rather than relying
        # on truthiness — 0 (Incorrect) must not be treated as ungraded.
        is_correct_raw = a_row.get("is_correct")
        is_graded      = is_correct_raw is not None and str(is_correct_raw) != "None"
        is_correct     = bool(is_correct_raw) if is_graded else None

        if q_type in ("true_false", "mcq"):
            # Auto-graded at submission time — is_correct is always present.
            result = "Correct" if is_correct else "Incorrect"
            st.markdown(
                f"**Q{q_num}.** {qrow['question_text']}  \n"
                f"Answer: **{student_ans}**  ·  {result}  ·  "
                f"Expected: *{qrow.get('correct_answer', '—')}*"
            )
        else:
            # Short answer: show the question and the student's typed response.
            st.markdown(f"**Q{q_num}.** {qrow['question_text']}")
            st.text_area(
                "Student answer",
                value=student_ans,
                disabled=True,
                height=70,
                key=f"ins_review_{int(qrow['id'])}_{q_num}",
                label_visibility="collapsed",
            )

            ref = qrow.get("correct_answer") or ""

            if is_graded:
                # AI has evaluated this response. Show:
                #   - the Correct / Incorrect verdict
                #   - the AI's note explaining why (from q_notes_map)
                #   - the reference answer, even if it is empty, so the
                #     instructor always has full context in one place.
                verdict    = "Correct" if is_correct else "Incorrect"
                ai_note    = q_notes_map.get(q_num, "")
                note_text  = f" — {ai_note}" if ai_note else ""
                ref_text   = f"  ·  Reference: *{ref}*" if ref else ""
                st.caption(f"AI verdict: **{verdict}**{note_text}{ref_text}")
            else:
                # Not yet AI-graded — show the reference answer so the
                # instructor can make their own assessment.
                if ref:
                    st.caption(f"Reference answer: {ref}")

        q_num += 1




# =============================================================================
# STUDENT QUIZ VIEW
# =============================================================================

def _render_student_quiz_view(engine, a_id: int):
    """
    Render published quizzes as interactive, solvable forms for students.

    Only quizzes with published=1 are shown. Each quiz is presented as a
    sequential form of questions:
      - True/False: radio button with two options.
      - MCQ:        radio button with the four model-generated choices.
      - Short Answer: text area for a free-form written response.

    After submission a confirmation is shown immediately. The score and answer
    review are only revealed once the instructor switches on grades_visible for
    that quiz, allowing instructors to finish reviewing all submissions before
    releasing results to the cohort.

    Instructor prompts, raw AI responses, and prompt history are never
    shown in this view — only the rendered quiz questions and the student's
    own score and feedback once grades are released.
    """
    quizzes_df = pd.read_sql(
        text("""
            SELECT q.id, q.title, q.grades_visible, q.created_at
            FROM quizzes q
            WHERE q.assessment_id = :aid
              AND q.published = 1
            ORDER BY q.created_at DESC
        """),
        engine,
        params={"aid": a_id},
    )

    if quizzes_df.empty:
        st.info("No quizzes have been published for this assessment yet.")
        return

    student_id = int(st.session_state.user["id"])

    for _, quiz_row in quizzes_df.iterrows():
        quiz_id        = int(quiz_row["id"])
        quiz_title     = str(quiz_row["title"])
        grades_visible = bool(quiz_row["grades_visible"])

        with st.container(border=True):
            st.markdown(f"### {quiz_title}")

            # Load questions ordered by type then by their original generation order.
            questions_df = pd.read_sql(
                text("""
                    SELECT id, question_order, question_type, question_text,
                           options_json, correct_answer
                    FROM quiz_questions
                    WHERE quiz_id = :qid
                    ORDER BY
                        FIELD(question_type, 'true_false', 'mcq', 'short_answer'),
                        question_order
                """),
                engine,
                params={"qid": quiz_id},
            )

            if questions_df.empty:
                st.info("This quiz has no questions.")
                continue

            # Check whether the student has already submitted this quiz.
            # This is a targeted lookup against the submissions table only —
            # answers are fetched separately below so that the guard works
            # correctly even when a quiz has no questions saved (which would
            # produce zero rows from a JOIN-based check).
            submission_row = pd.read_sql(
                text("""
                    SELECT id AS submission_id, score, manual_score,
                           grading_notes, submitted_at
                    FROM quiz_submissions
                    WHERE quiz_id    = :qid
                      AND student_id = :sid
                    LIMIT 1
                """),
                engine,
                params={"qid": quiz_id, "sid": student_id},
            )

            # ---- Already submitted ----
            if not submission_row.empty:
                st.info("You have submitted this quiz.")

                if not grades_visible:
                    # Grades not yet released — show only the confirmation.
                    # The score and answer review are withheld until the
                    # instructor enables grades_visible from the Quizzes tab.
                    st.caption("Your grade will appear here once the instructor releases results.")
                    continue

                # Grades visible: fetch answers then show score, notes, and
                # the per-question review. Answers are loaded here rather than
                # in the submission check query so they are only read when
                # the instructor has released grades and the data is needed.
                first_row     = submission_row.iloc[0]
                sub_id        = int(first_row["submission_id"])
                auto_score    = first_row["score"]
                manual_score  = first_row["manual_score"]
                grading_notes = first_row.get("grading_notes") or ""

                answers_df = pd.read_sql(
                    text("""
                        SELECT question_id, answer_text, is_correct
                        FROM quiz_answers
                        WHERE submission_id = :sid
                    """),
                    engine,
                    params={"sid": sub_id},
                )

                # The effective displayed score is the manual/AI override when set,
                # otherwise the auto-calculated machine score.
                display_score = manual_score if manual_score is not None else auto_score
                if display_score is not None:
                    st.success(
                        f"**Your score: {display_score:.1f}%**  ·  "
                        f"Submitted: {first_row['submitted_at']}"
                    )
                if grading_notes:
                    st.markdown(f"**Feedback:** {grading_notes}")

                answer_map = {
                    int(r["question_id"]): r
                    for _, r in answers_df.iterrows()
                }

                type_labels = {
                    "true_false":   "True / False",
                    "mcq":          "Multiple Choice",
                    "short_answer": "Short Answer",
                }
                shown_types = set()
                q_counter   = 1

                for _, qrow in questions_df.iterrows():
                    q_type = str(qrow["question_type"])
                    if q_type not in shown_types:
                        st.markdown(f"##### {type_labels.get(q_type, q_type)}")
                        shown_types.add(q_type)

                    q_id        = int(qrow["id"])
                    student_ans = str(answer_map.get(q_id, {}).get("answer_text") or "")
                    is_correct  = answer_map.get(q_id, {}).get("is_correct")

                    if q_type in ("true_false", "mcq"):
                        result = "Correct" if is_correct else "Incorrect"
                        st.markdown(
                            f"**Q{q_counter}.** {qrow['question_text']}  \n"
                            f"Your answer: **{student_ans}**  ·  {result}  ·  "
                            f"Expected: *{qrow.get('correct_answer', '—')}*"
                        )
                    else:
                        # Short answer: display the student's response and the
                        # model reference answer for self-review.
                        st.markdown(f"**Q{q_counter}.** {qrow['question_text']}")
                        st.text_area(
                            "Your answer",
                            value=student_ans,
                            disabled=True,
                            key=f"review_sa_{quiz_id}_{q_id}",
                            label_visibility="collapsed",
                            height=80,
                        )
                        model_ans = qrow.get("correct_answer")
                        if model_ans:
                            st.caption(f"Reference answer: {model_ans}")

                    q_counter += 1

                continue  # Skip the submission form for this quiz.

            # ---- Not yet submitted: render the interactive quiz form ----
            with st.form(key=f"quiz_form_{quiz_id}"):
                student_answers = {}

                type_labels = {
                    "true_false":   "True / False",
                    "mcq":          "Multiple Choice",
                    "short_answer": "Short Answer",
                }
                shown_types = set()
                q_counter   = 1

                for _, qrow in questions_df.iterrows():
                    q_type = str(qrow["question_type"])
                    q_id   = int(qrow["id"])

                    if q_type not in shown_types:
                        st.markdown(f"##### {type_labels.get(q_type, q_type)}")
                        shown_types.add(q_type)

                    st.markdown(f"**Q{q_counter}.** {qrow['question_text']}")

                    widget_key = f"quiz_{quiz_id}_q_{q_id}"

                    if q_type == "true_false":
                        # No default selection (index=None) so the student must
                        # actively choose before the form can be submitted.
                        answer = st.radio(
                            "Answer",
                            ["True", "False"],
                            key=widget_key,
                            horizontal=True,
                            label_visibility="collapsed",
                            index=None,
                        )
                        student_answers[q_id] = answer or ""

                    elif q_type == "mcq":
                        options = []
                        if qrow.get("options_json"):
                            try:
                                options = json.loads(qrow["options_json"])
                            except (json.JSONDecodeError, TypeError):
                                options = []
                        answer = st.radio(
                            "Answer",
                            options if options else ["(No options available)"],
                            key=widget_key,
                            label_visibility="collapsed",
                            index=None,
                        )
                        student_answers[q_id] = answer or ""

                    elif q_type == "short_answer":
                        answer = st.text_area(
                            "Your answer",
                            key=widget_key,
                            height=80,
                            label_visibility="collapsed",
                            placeholder="Type your answer here...",
                        )
                        student_answers[q_id] = answer or ""

                    q_counter += 1

                submitted = st.form_submit_button("Submit Quiz", type="primary")

            if submitted:
                # Require all True/False and MCQ questions to be answered.
                # Short-answer blanks are accepted since they are not machine-graded.
                unanswered = [
                    q_id for q_id, ans in student_answers.items()
                    if not ans and questions_df.loc[
                        questions_df["id"] == q_id, "question_type"
                    ].values[0] in ("true_false", "mcq")
                ]
                if unanswered:
                    st.error(
                        f"Please answer all True/False and Multiple Choice questions "
                        f"before submitting. ({len(unanswered)} unanswered)"
                    )
                else:
                    try:
                        save_quiz_submission(
                            quiz_id=quiz_id,
                            student_id=student_id,
                            answers=student_answers,
                        )
                        st.success(
                            "Quiz submitted. "
                            "Your grade will be visible here once the instructor releases results."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not save your submission: {exc}")


# =============================================================================
# SESSION TIMEOUT
# =============================================================================
# Checks whether the authenticated session has been idle for longer than
# SESSION_TIMEOUT_SECONDS. If so, the session is cleared and the user is
# returned to the login screen. The last_active timestamp is updated on every
# authenticated page render so normal interaction resets the timer.
#
# This logic was ported from UReap's app.py and adapted to use Prebinary's
# st.session_state.logged_in key rather than UReap's login_success key.

SESSION_TIMEOUT_SECONDS = 15 * 60  # 15 minutes


def _check_session_timeout() -> None:
    """
    Expire the session if the user has been idle for SESSION_TIMEOUT_SECONDS.
    Called at the start of every authenticated render before any page content
    is drawn. On expiry, all session state is cleared via logout() and a
    warning is shown on the login page.
    """
    if not st.session_state.get("logged_in"):
        return
    last_active = st.session_state.get("last_active")
    if last_active and (_time.time() - last_active) > SESSION_TIMEOUT_SECONDS:
        logout()
        st.warning("Your session timed out. Please log in again.")
        return
    st.session_state["last_active"] = _time.time()


# =============================================================================
# MAIN ROUTER
# =============================================================================
# Determines which top-level view to render based on authentication state,
# the current_page session key, and the logged-in user's role.
#
# current_page values:
#   "dashboard"   — UReap feature tab layout (all authenticated users)
#   "profile"     — Profile and settings page (all authenticated users)
#   "admin_panel" — User management panel (admin role only)

if st.session_state.logged_in:
    _check_session_timeout()

    # Re-check after potential timeout logout — _check_session_timeout() may
    # have cleared logged_in via logout().
    if st.session_state.get("logged_in"):
        render_sidebar()
        page = st.session_state.current_page
        role = st.session_state.user.get("role")

        if page == "profile":
            profile_page()
        elif page == "admin_panel" and role == "admin":
            admin_panel_page()
        else:
            # Dashboard routing is role-based. All roles call render_dashboard()
            # which builds the tab list dynamically based on the user's role.
            if role == "admin":
                admin_page()
            elif role == "teacher":
                teacher_page()
            elif role == "student":
                student_page()
            else:
                home_page()
else:
    auth_page()