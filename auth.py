# =============================================================================
# auth.py — Prebinary × UReap Integration
# =============================================================================
# Authentication, authorisation, and all database write operations.
#
# Module structure:
#   - File storage helpers      save/delete uploaded files on disk
#   - Uniqueness checks         query-only helpers used by app.py before writes
#   - Password utilities        bcrypt hash and verify
#   - User actions              signup, login, profile/password/api-key/
#                               model-preference/permission updates
#   - Entity update actions     course, assessment, and file record updates
#                               (deferred sprint — functions retained for future use)
#   - Admin user CRUD           admin-specific create and full-edit operations
#   - Course access             grant and revoke course_access records
#                               (deferred sprint — functions retained for future use)
#   - Quiz write operations     persist quizzes, submissions, and answers
#                               (deferred sprint — functions retained for future use)
#
# All write functions use raw mysql.connector connections from db.get_connection()
# and close both cursor and connection in a try/finally block. Callers in app.py
# are responsible for validation before calling any write function here.
# =============================================================================

import bcrypt
import json
import os
import random
import smtplib
import ssl
import uuid
from email.mime.text import MIMEText
from pathlib import Path
import shutil

from db import get_connection


# =============================================================================
# FILE STORAGE HELPERS
# =============================================================================

UPLOAD_ROOT = Path("uploads")

# Permitted file extensions for upload. Checked before writing to disk to
# prevent arbitrary file types from being stored on the server.
# .docx and .pptx are included to support UReap features (RAG, Quiz Generator,
# Exam Creation) that accept Office document formats.
# .zip is included to support Exam Grading, which accepts a ZIP archive of
# student PDF submissions. The ZIP is saved to disk before extraction so the
# original submission bundle is preserved under the course/assessment directory.
ALLOWED_EXTENSIONS = {
    ".pdf", ".txt", ".png", ".jpg", ".jpeg",
    ".webp", ".md", ".html", ".json", ".xml", ".csv",
    ".docx", ".pptx", ".zip",
}


def save_uploaded_file(
    file_bytes: bytes,
    original_name: str,
    course_name: str,
    assessment_name: str,
    course_id: int,
    feature_name: str = "general",
) -> tuple[str, str]:
    """
    Write an uploaded file to disk under:
        uploads/{course_id}_{course_name}/{feature_name}/{assessment_name}/

    Each feature stores its files in its own subdirectory within the course
    directory so that files from different features do not share a namespace.
    The feature_name should be one of: "exam_grading", "exam_creation",
    "practice_quiz", or "general" for files uploaded through the generic
    course file panel.

    The file is renamed to {uuid}_{original_name} to prevent name collisions
    when multiple users upload files with the same filename to the same
    assessment. The UUID prefix also prevents directory traversal via crafted
    filenames.

    The stored path is kept relative to the project root so the application
    remains portable across deployments. It is read back as raw bytes when
    constructing AI API payloads in app.py.

    Returns:
        (saved_filename, relative_file_path) on success.
    Raises:
        ValueError if the file extension is not in ALLOWED_EXTENSIONS.
    """
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type '{ext}' is not permitted.")

    dest_dir = UPLOAD_ROOT / f"{course_id}_{course_name}" / feature_name / assessment_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    dest_path   = dest_dir / unique_name
    dest_path.write_bytes(file_bytes)

    return unique_name, str(dest_path)


def delete_physical_file(file_path: str) -> None:
    """
    Remove a file from disk given its stored relative path.

    Errors are caught silently because the database record — not the physical
    file — is the source of truth for what files exist. A missing file on disk
    should not prevent the DB record from being deleted.
    """
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
    except Exception:
        pass


# =============================================================================
# UNIQUENESS CHECKS
# =============================================================================
# These functions are query-only and return a boolean. They are called in
# app.py immediately before any insert or update to provide user-facing
# error messages without relying on database constraint violations.

def is_username_unique(username: str) -> bool:
    """Return True if no existing user has the given username."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (username.strip(),))
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return not exists


def is_email_unique(email: str) -> bool:
    """Return True if no existing user has the given email address."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = %s", (email.strip(),))
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return not exists


def is_phone_unique(phone: str, exclude_id: int = None) -> bool:
    """
    Return True if no existing user has the given phone number.

    The exclude_id parameter allows the check to skip the user currently being
    edited, so their existing phone number does not trigger a false conflict.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        if exclude_id:
            cursor.execute(
                "SELECT id FROM users WHERE phone = %s AND id != %s",
                (phone.strip(), int(exclude_id)),
            )
        else:
            cursor.execute("SELECT id FROM users WHERE phone = %s", (phone.strip(),))
        return cursor.fetchone() is None
    finally:
        cursor.close()
        conn.close()


def is_username_unique_for_update(username: str, exclude_id: int) -> bool:
    """
    Return True if no other user (excluding exclude_id) has the given username.
    Used during admin user edits to avoid false conflicts with the user's own
    current username.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM users WHERE username = %s AND id != %s",
            (username.strip(), int(exclude_id)),
        )
        return cursor.fetchone() is None
    finally:
        cursor.close()
        conn.close()


def is_email_unique_for_update(email: str, exclude_id: int) -> bool:
    """
    Return True if no other user (excluding exclude_id) has the given email.
    Used during admin user edits to avoid false conflicts with the user's own
    current email address.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM users WHERE email = %s AND id != %s",
            (email.strip(), int(exclude_id)),
        )
        return cursor.fetchone() is None
    finally:
        cursor.close()
        conn.close()


def is_roll_no_unique(roll_no: str, exclude_id: int = None) -> bool:
    """
    Return True if no other user has the given roll number.

    The exclude_id parameter allows the check to skip the user currently being
    edited, so their existing roll number does not trigger a false conflict.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        if exclude_id:
            cursor.execute(
                "SELECT id FROM users WHERE roll_no = %s AND id != %s",
                (roll_no.strip(), int(exclude_id)),
            )
        else:
            cursor.execute("SELECT id FROM users WHERE roll_no = %s", (roll_no.strip(),))
        return cursor.fetchone() is None
    finally:
        cursor.close()
        conn.close()


def is_course_code_unique(course_code: str, exclude_id: int = None) -> bool:
    """
    Return True if no existing course has the given course code.

    The exclude_id parameter allows the check to skip the course currently
    being edited, so its existing code does not trigger a false conflict.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    if exclude_id:
        cursor.execute(
            "SELECT id FROM courses WHERE course_code = %s AND id != %s",
            (str(course_code).strip(), exclude_id),
        )
    else:
        cursor.execute(
            "SELECT id FROM courses WHERE course_code = %s",
            (str(course_code).strip(),),
        )
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return not exists


# =============================================================================
# PASSWORD UTILITIES
# =============================================================================

def hash_password(password: str) -> str:
    """
    Return a bcrypt hash of the given plaintext password.

    A new salt is generated on every call via bcrypt.gensalt(). The result
    is stored as a UTF-8 string in the users.password column.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """
    Return True if the plaintext password matches the stored bcrypt hash.

    Both values are stripped of incidental whitespace before comparison to
    handle any encoding artefacts introduced by the storage layer.
    """
    return bcrypt.checkpw(
        password.encode(),
        hashed.strip().encode(),
    )


# =============================================================================
# EMAIL VERIFICATION UTILITIES
# =============================================================================
# These utilities support email-based verification of new user accounts.
#
# Currently, email verification is NOT enforced during signup. New accounts
# are created immediately and placed into 'inactive' status, requiring an
# administrator to activate them manually. This module is included so that
# email verification can be enabled in a future sprint without restructuring
# the authentication flow — only the caller in app.py needs to be updated.
#
# To activate email verification:
#   1. Configure SMTP_SENDER_EMAIL and SMTP_APP_PASSWORD below with a valid
#      Gmail address and its corresponding App Password (not the account
#      password). App Passwords are generated at:
#      https://myaccount.google.com/apppasswords
#   2. Enable 2-Step Verification on the Gmail account first.
#   3. In _render_signup_form() (app.py), call send_verification_email() after
#      form submission and gate the signup_user() call on verify_email_code().
# =============================================================================

# SMTP configuration for Gmail. Both values must be populated before email
# verification can be used. Left empty so the module loads safely without
# credentials configured.
SMTP_SERVER       = "smtp.gmail.com"
SMTP_PORT         = 465          # SSL
SMTP_SENDER_EMAIL = ""           # Set to the sending Gmail address
SMTP_APP_PASSWORD = ""           # Set to the Gmail App Password, not the account password


def send_verification_email(receiver_email: str) -> str:
    """
    Send a six-digit verification code to the given email address and return
    the code so the caller can store it for later comparison.

    Uses Gmail SMTP over SSL. SMTP_SENDER_EMAIL and SMTP_APP_PASSWORD must be
    configured above before this function will work. If either value is empty
    the function raises a RuntimeError so the caller can surface a clear error
    rather than failing silently.

    Args:
        receiver_email: The address to send the verification code to.

    Returns:
        The six-digit code as a string, for the caller to store in session state
        and compare against the user's input.

    Raises:
        RuntimeError: If SMTP credentials are not configured.
        smtplib.SMTPException: If the email cannot be delivered.
    """
    if not SMTP_SENDER_EMAIL or not SMTP_APP_PASSWORD:
        raise RuntimeError(
            "Email verification is not configured. "
            "Set SMTP_SENDER_EMAIL and SMTP_APP_PASSWORD in auth.py."
        )

    code = str(random.randint(100000, 999999))

    msg             = MIMEText(f"Your Prebinary verification code is: {code}")
    msg["Subject"]  = "Prebinary — Email Verification Code"
    msg["From"]     = SMTP_SENDER_EMAIL
    msg["To"]       = receiver_email

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SMTP_SENDER_EMAIL, SMTP_APP_PASSWORD)
        server.sendmail(SMTP_SENDER_EMAIL, receiver_email, msg.as_string())

    return code


def verify_email_code(user_input: str, expected_code: str) -> bool:
    """
    Return True if the user-supplied code matches the expected verification code.

    Both values are stripped before comparison to handle accidental whitespace
    in the input field.

    Args:
        user_input:    The code entered by the user in the verification field.
        expected_code: The code returned by send_verification_email() and stored
                       in session state.
    """
    return user_input.strip() == expected_code.strip()


# =============================================================================
# USER ACTIONS
# =============================================================================

def signup_user(
    username: str,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    phone: str,
    street: str,
    city: str,
    state_prov: str,
    postal_code: str,
    country: str,
) -> None:
    """
    Insert a new user record created via the public sign-up form.

    All new accounts are set to role='user' and status='inactive'. An
    administrator must activate the account before the user can log in.
    The password is hashed before storage; the plaintext value is never
    persisted.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (
                username, email, password,
                first_name, last_name, phone,
                street_address, city, state_province, postal_code, country,
                role, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'user', 'inactive')
            """,
            (
                username, email, hash_password(password),
                first_name, last_name, phone,
                street, city, state_prov, postal_code, country,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def login_user(username: str, password: str):
    """
    Verify login credentials and return the user record on success.

    Returns:
        dict   — the full user row (password field removed) on successful login.
        "inactive" — if credentials are correct but the account is not active.
        None   — if the username does not exist or the password is incorrect.

    The password field is removed from the returned dict so it is never stored
    in Streamlit session state.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username.strip(),))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and verify_password(password, user["password"]):
        if user["status"] == "active":
            user.pop("password", None)
            return user
        return "inactive"
    return None


def update_user_permissions(user_id: int, new_role: str, new_status: str) -> None:
    """
    Update a user's role and status.

    Called by the admin bulk role/status editor. Only these two fields are
    written; all other user data is unchanged.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET role = %s, status = %s WHERE id = %s",
        (new_role, new_status, user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


def update_user_profile(
    user_id: int,
    first_name: str,
    last_name: str,
    phone: str,
    street: str,
    city: str,
    state_prov: str,
    postal_code: str,
    country: str,
    roll_no: str = None,
) -> None:
    """
    Update the non-sensitive profile fields for a user editing their own account.

    Username, email, role, status, and password are not touched here. Those
    are handled by their own dedicated functions. roll_no is only meaningful
    for student accounts and is stored as-is (None/blank clears it).
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE users SET
                first_name     = %s,
                last_name      = %s,
                phone          = %s,
                street_address = %s,
                city           = %s,
                state_province = %s,
                postal_code    = %s,
                country        = %s,
                roll_no        = %s
            WHERE id = %s
            """,
            (first_name, last_name, phone, street, city, state_prov, postal_code, country, roll_no, user_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def change_user_password(user_id: int, new_password: str) -> None:
    """
    Hash and store a new password for a user changing their own password.

    The current password is verified by the caller (app.py) before this
    function is invoked. Passwords are never stripped before hashing.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = %s WHERE id = %s",
        (hash_password(new_password), user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


def admin_reset_user_password(user_id: int, new_password: str) -> None:
    """
    Hash and store a new password on behalf of a user, initiated by an admin.

    Unlike change_user_password(), no verification of the existing password
    is required. Validation of the new password's strength is performed by
    the caller in app.py before this function is invoked.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = %s WHERE id = %s",
        (hash_password(new_password), user_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


def delete_user_account(user_id: int) -> None:
    """
    Permanently delete a user account and all associated data.

    Cascade deletes defined in schema_clean.sql remove any course_access records,
    uploaded file records, and AI output records linked to this user.

    In addition to the DB delete, this function removes the user's RAG data
    directory from disk. This covers both the active FAISS index and all
    per-session chat snapshot directories stored under data/rag/{user_id}/.
    The directory removal uses ignore_errors=True so a missing directory on
    disk does not raise an exception if it was already cleaned up elsewhere.
    """
    import shutil
    from pathlib import Path

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    rag_dir = Path("data") / "rag" / str(user_id)
    if rag_dir.exists():
        shutil.rmtree(rag_dir, ignore_errors=True)


def update_user_api_keys(
    user_id: int,
    chatgpt_key: str,
    gemini_key: str,
    groq_key: str,
    github_token: str,
    elevenlabs_key: str,
    cartesia_key: str,
) -> None:
    """
    Update the stored AI provider API keys for a user.

    Called from the Profile → API Keys tab when the user saves their keys.
    Keys are passed as None when the field was left blank, which stores NULL
    in the database. This allows the profile page to correctly show "Not set"
    for keys that have been cleared.

    Key-to-provider mapping:
      chatgpt_api_key    → ChatGPT / OpenAI (UReap reads as openai_api_key)
      gemini_api_key     → Google Gemini
      groq_api_key       → Groq (Llama 3.3-70B via Groq)
      github_token       → GPT-4o via GitHub Models
      elevenlabs_api_key → ElevenLabs TTS (Narrated Slideshow — future sprint)
      cartesia_api_key   → Cartesia TTS (Narrated Slideshow — future sprint)
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE users SET
                chatgpt_api_key    = %s,
                gemini_api_key     = %s,
                groq_api_key       = %s,
                github_token       = %s,
                elevenlabs_api_key = %s,
                cartesia_api_key   = %s
            WHERE id = %s
            """,
            (chatgpt_key, gemini_key, groq_key, github_token,
             elevenlabs_key, cartesia_key, user_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def update_user_model_prefs(
    user_id: int,
    pref_rag: str,
    pref_exam_grading: str,
    pref_exam_creation: str,
    pref_advisor_ai: str,
    pref_wellness: str,
    pref_quiz_generator: str,
    pref_video_lectures: str = None,
) -> None:
    """
    Persist per-feature model preferences for a user.

    Called from the Profile → Model Preferences tab when the user saves their
    preferred model for each UReap feature. Preferences are stored as model ID
    strings (e.g. 'gemini-2.5-flash'), not display names, so they can be used
    directly with llm_utils.stream_llm() without a reverse lookup.

    Passing None for any preference stores NULL in the database, which causes
    the application to fall back to the first model in llm_utils.MODELS for
    that feature.

    Feature-to-column mapping:
      pref_model_rag            → RAG System
      pref_model_exam_grading   → Exam Grading
      pref_model_exam_creation  → Exam Creation
      pref_model_advisor_ai     → Advisor AI
      pref_model_wellness       → Student Wellness Assistant
      pref_model_quiz_generator → Practice Quiz (Quiz Generator)
      pref_model_video_lectures → Video Lectures (Narrated Slideshow)
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE users SET
                pref_model_rag            = %s,
                pref_model_exam_grading   = %s,
                pref_model_exam_creation  = %s,
                pref_model_advisor_ai     = %s,
                pref_model_wellness       = %s,
                pref_model_quiz_generator = %s,
                pref_model_video_lectures = %s
            WHERE id = %s
            """,
            (
                pref_rag, pref_exam_grading, pref_exam_creation,
                pref_advisor_ai, pref_wellness, pref_quiz_generator,
                pref_video_lectures, user_id,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# ENTITY UPDATE ACTIONS
# =============================================================================

def update_course_details(
    course_id: int,
    code: str,
    name: str,
    hours: int,
    year: int,
    sem: str,
    desc: str,
    inst_name: str,
) -> None:
    """
    Update the editable fields for an existing course.

    instructor_id and created_at are not modified here. Course code is stored
    as provided (uppercasing is handled by the caller in app.py).
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE courses SET
                course_code     = %s,
                course_name     = %s,
                credit_hours    = %s,
                year            = %s,
                semester        = %s,
                description     = %s,
                instructor_name = %s
            WHERE id = %s
            """,
            (code, name, hours, year, sem, desc, inst_name, course_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def update_assessment_details(
    asm_id: int,
    title: str,
    desc: str,
) -> None:
    """
    Update the editable fields for an existing assessment.

    Only title and description are editable.
    course_id and created_at are never modified.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE assessments SET
                title       = %s,
                description = %s
            WHERE id = %s
            """,
            (title, desc, asm_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def update_file_details(file_id: int, name: str, path: str) -> None:
    """
    Update the filename and path for an existing file record.

    This is used if a file is renamed or moved on disk after initial upload.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE files SET file_name = %s, file_path = %s WHERE id = %s",
        (name, path, file_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


# =============================================================================
# ADMIN USER CRUD
# =============================================================================

def admin_create_user(
    username: str,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    phone: str,
    street: str,
    city: str,
    state_prov: str,
    postal_code: str,
    country: str,
    role: str,
    status: str,
    chatgpt_key: str          = None,
    gemini_key: str           = None,
    groq_key: str             = None,
    github_token: str         = None,
    elevenlabs_key: str       = None,
    cartesia_key: str         = None,
    pref_rag: str             = None,
    pref_exam_grading: str    = None,
    pref_exam_creation: str   = None,
    pref_advisor_ai: str      = None,
    pref_wellness: str        = None,
    pref_quiz_generator: str  = None,
    pref_video_lectures: str  = None,
    roll_no: str              = None,
) -> None:
    """
    Insert a new user record created directly by an admin.

    Unlike signup_user(), the admin can specify the role, status, and per-feature
    model preferences at creation time. API keys and model preferences are
    optional and default to None (stored as NULL), which causes each feature to
    fall back to the first model in llm_utils.MODELS at login.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (
                username, email, password,
                first_name, last_name, phone,
                street_address, city, state_province, postal_code, country,
                roll_no,
                chatgpt_api_key, gemini_api_key, groq_api_key,
                github_token, elevenlabs_api_key, cartesia_api_key,
                role, status,
                pref_model_rag, pref_model_exam_grading, pref_model_exam_creation,
                pref_model_advisor_ai, pref_model_wellness,
                pref_model_quiz_generator, pref_model_video_lectures
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                username.strip(),
                email.strip(),
                hash_password(password),
                first_name,
                last_name,
                phone,
                street,
                city,
                state_prov,
                postal_code,
                country,
                roll_no,
                chatgpt_key,
                gemini_key,
                groq_key,
                github_token,
                elevenlabs_key,
                cartesia_key,
                role,
                status,
                pref_rag,
                pref_exam_grading,
                pref_exam_creation,
                pref_advisor_ai,
                pref_wellness,
                pref_quiz_generator,
                pref_video_lectures,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def admin_update_user_full(
    user_id: int,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    phone: str,
    street: str,
    city: str,
    state_prov: str,
    postal_code: str,
    country: str,
    role: str,
    status: str,
    chatgpt_key: str,
    gemini_key: str,
    groq_key: str,
    github_token: str,
    elevenlabs_key: str,
    cartesia_key: str,
    pref_rag: str             = None,
    pref_exam_grading: str    = None,
    pref_exam_creation: str   = None,
    pref_advisor_ai: str      = None,
    pref_wellness: str        = None,
    pref_quiz_generator: str  = None,
    pref_video_lectures: str  = None,
    roll_no: str              = None,
) -> None:
    """
    Update all editable fields for a user record, as performed by an admin.

    Covers everything except the password, which is handled separately via
    admin_reset_user_password() to keep the reset flow explicit and auditable.
    API key values of None are stored as NULL, clearing a previously saved key.
    Model preference values of None store NULL, causing the feature to fall
    back to the default model in llm_utils.MODELS at the user's next login.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE users SET
                username                  = %s,
                email                     = %s,
                first_name                = %s,
                last_name                 = %s,
                phone                     = %s,
                street_address            = %s,
                city                      = %s,
                state_province            = %s,
                postal_code               = %s,
                country                   = %s,
                roll_no                   = %s,
                role                      = %s,
                status                    = %s,
                chatgpt_api_key           = %s,
                gemini_api_key            = %s,
                groq_api_key              = %s,
                github_token              = %s,
                elevenlabs_api_key        = %s,
                cartesia_api_key          = %s,
                pref_model_rag            = %s,
                pref_model_exam_grading   = %s,
                pref_model_exam_creation  = %s,
                pref_model_advisor_ai     = %s,
                pref_model_wellness       = %s,
                pref_model_quiz_generator = %s,
                pref_model_video_lectures = %s
            WHERE id = %s
            """,
            (
                username.strip(),
                email.strip(),
                first_name,
                last_name,
                phone,
                street,
                city,
                state_prov,
                postal_code,
                country,
                roll_no,
                role,
                status,
                chatgpt_key,
                gemini_key,
                groq_key,
                github_token,
                elevenlabs_key,
                cartesia_key,
                pref_rag,
                pref_exam_grading,
                pref_exam_creation,
                pref_advisor_ai,
                pref_wellness,
                pref_quiz_generator,
                pref_video_lectures,
                int(user_id),
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# COURSE ACCESS
# =============================================================================

def grant_course_access(course_id: int, user_id: int, access_role: str) -> None:
    """
    Grant a user access to a course with status='approved'.

    Uses INSERT ... ON DUPLICATE KEY UPDATE so the operation is idempotent:
    calling it on a user who already has a record (even if revoked) resets
    their status to 'approved' without creating a duplicate row.

    access_role must be 'teacher' or 'student' to match the course_access
    ENUM constraint in schema_clean.sql.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO course_access (course_id, user_id, access_role, status)
            VALUES (%s, %s, %s, 'approved')
            ON DUPLICATE KEY UPDATE status = 'approved'
            """,
            (int(course_id), int(user_id), str(access_role)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def revoke_course_access(course_id: int, user_id: int, access_role: str) -> None:
    """
    Set a course_access record to status='revoked'.

    The row is not deleted, preserving the audit trail of who had access and
    when it was last changed (via the updated_at timestamp in schema_clean.sql).
    Access can be re-granted at any time by calling grant_course_access().
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE course_access
            SET status = 'revoked'
            WHERE course_id = %s AND user_id = %s AND access_role = %s
            """,
            (int(course_id), int(user_id), str(access_role)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def duplicate_course_for_teacher(source_course_id: int, new_owner_user_id: int, new_owner_name: str) -> int:
    """
    Create a full independent duplicate of an existing course for a teacher.

    Duplication rules implemented here:

      - The new course is owned by the duplicating teacher.
      - The duplicate includes all assessments, uploaded files, and feature
        generation history (exam grading sessions, exam creation questions,
        practice quiz records and attempts) from the source course.
      - Assessment IDs are remapped to the new assessment rows. Session
        identifiers (grading_session_id, creation_session_id) are remapped
        to fresh UUIDs so history in the duplicate is independent from the
        source course.
      - The original course and its access records remain unchanged.
      - No shared access is copied to the duplicate.
      - The duplicating teacher is granted approved teacher access to the new
        course so it behaves like a course they created normally.

    Returns:
        The new duplicated course ID.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # ---------------------------------------------------------------------
        # Load the source course record.
        # ---------------------------------------------------------------------
        cursor.execute(
            """
            SELECT
                id,
                course_code,
                course_name,
                credit_hours,
                year,
                semester,
                description,
                status
            FROM courses
            WHERE id = %s
            """,
            (int(source_course_id),),
        )
        source_course = cursor.fetchone()

        if not source_course:
            raise ValueError("Source course not found.")

        # ---------------------------------------------------------------------
        # Build a unique course code for the duplicate.
        #
        # course_code has a NOT NULL UNIQUE constraint so the duplicate must
        # have a distinct code. A numeric dash suffix is appended and
        # incremented until an unused code is found. The suffix is kept on
        # the code only — the course name receives "(Copy)" separately so
        # the two fields stay semantically independent.
        #   COMP1000  →  COMP1000-2  (or COMP1000-3 if -2 is taken, etc.)
        # ---------------------------------------------------------------------
        base_code = source_course['course_code']
        counter   = 2

        while True:
            new_code = f"{base_code}-{counter}"
            cursor.execute("SELECT id FROM courses WHERE course_code = %s", (new_code,))
            if cursor.fetchone() is None:
                break
            counter += 1

        # ---------------------------------------------------------------------
        # Create the duplicated course as a brand-new course owned by the
        # duplicating teacher.
        # ---------------------------------------------------------------------
        duplicated_name = f"{source_course['course_name']} (Copy)"

        cursor.execute(
            """
            INSERT INTO courses
                (course_code, course_name, credit_hours, year, semester,
                 description, instructor_id, instructor_name, status)
            VALUES
                (%s, %s, %s, %s, %s,
                 %s, %s, %s, %s)
            """,
            (
                new_code,
                duplicated_name,
                int(source_course["credit_hours"]),
                int(source_course["year"]),
                source_course["semester"],
                source_course["description"],
                int(new_owner_user_id),
                new_owner_name,
                source_course.get("status", "active"),
            ),
        )
        new_course_id = cursor.lastrowid

        # ---------------------------------------------------------------------
        # Duplicate all assessments from the source course and keep a mapping
        # from old assessment IDs to new assessment IDs so files can be linked
        # correctly to the duplicated assessments.
        # ---------------------------------------------------------------------
        cursor.execute(
            """
            SELECT
                id,
                title,
                description
            FROM assessments
            WHERE course_id = %s
            ORDER BY id
            """,
            (int(source_course_id),),
        )
        source_assessments = cursor.fetchall()

        assessment_id_map = {}

        for asm in source_assessments:
            cursor.execute(
                """
                INSERT INTO assessments
                    (course_id, title, description)
                VALUES
                    (%s, %s, %s)
                """,
                (
                    int(new_course_id),
                    asm["title"],
                    asm["description"],
                ),
            )
            assessment_id_map[int(asm["id"])] = int(cursor.lastrowid)

        # ---------------------------------------------------------------------
        # Duplicate all file records and copy the physical files to the new
        # course folder structure.
        #
        # The copied file receives a new UUID-based stored filename through
        # save_uploaded_file(), which avoids collisions and keeps the duplicate
        # fully independent from the source course on disk.
        # ---------------------------------------------------------------------
        cursor.execute(
            """
            SELECT
                id,
                file_name,
                file_path,
                assessment_id,
                feature_name
            FROM files
            WHERE course_id = %s
            ORDER BY id
            """,
            (int(source_course_id),),
        )
        source_files = cursor.fetchall()

        for file_row in source_files:
            # Skip files that have no assessment linkage. All current uploads
            # are assessment-scoped, but the assessment_id column is nullable
            # so this guard prevents a TypeError on int() conversion.
            if file_row["assessment_id"] is None:
                continue

            old_assessment_id = int(file_row["assessment_id"])
            new_assessment_id = assessment_id_map.get(old_assessment_id)

            if not new_assessment_id:
                continue

            # Read the original file bytes if the physical file still exists.
            # Skip silently if the file has been removed from disk — the DB
            # record may outlive the physical file in some edge cases.
            old_path = Path(file_row["file_path"])
            if not old_path.exists():
                continue

            file_bytes = old_path.read_bytes()

            # Resolve the destination assessment title for the duplicated
            # assessment so the saved folder structure matches the new course.
            cursor.execute(
                "SELECT title FROM assessments WHERE id = %s",
                (int(new_assessment_id),),
            )
            new_assessment_row = cursor.fetchone()
            new_assessment_title = (
                new_assessment_row["title"] if new_assessment_row else "Assessment"
            )

            # Preserve the source file's feature_name so duplicated files land
            # in the correct feature subdirectory (e.g. exam_creation,
            # practice_quiz) and appear in those features' saved file lists.
            # Files without a feature_name default to 'general'.
            source_feature_name = file_row["feature_name"] or "general"

            saved_name, saved_path = save_uploaded_file(
                file_bytes=file_bytes,
                original_name=file_row["file_name"],
                course_name=duplicated_name,
                assessment_name=new_assessment_title,
                course_id=int(new_course_id),
                feature_name=source_feature_name,
            )

            cursor.execute(
                """
                INSERT INTO files
                    (file_name, file_path, course_id, assessment_id, uploaded_by, feature_name)
                VALUES
                    (%s, %s, %s, %s, %s, %s)
                """,
                (
                    saved_name,
                    saved_path,
                    int(new_course_id),
                    int(new_assessment_id),
                    int(new_owner_user_id),
                    source_feature_name,
                ),
            )

        # ---------------------------------------------------------------------
        # Duplicate generation history for all feature tables that store
        # data by assessment_id.
        #
        # Each feature's history rows are copied with assessment_id remapped
        # to the new assessment IDs using assessment_id_map. Session/group
        # identifiers (grading_session_id, creation_session_id) are remapped
        # to fresh UUIDs so that sessions in the duplicate course are fully
        # independent from those in the source course. All rows that shared
        # a session ID in the source still share the same new session ID in
        # the duplicate, preserving the grouping that the History tabs rely
        # on for display.
        #
        # Insertion order matters: practice_quiz_attempts references
        # practice_quiz_generated via quiz_id FK, so generated quizzes
        # must be inserted before attempts.
        # ---------------------------------------------------------------------

        # ── Exam Grading Results ──────────────────────────────────────────
        old_assessment_ids = list(assessment_id_map.keys())

        if old_assessment_ids:
            fmt = ",".join(["%s"] * len(old_assessment_ids))
            cursor.execute(
                f"""
                SELECT
                    grading_session_id,
                    graded_by,
                    assessment_id,
                    student_name,
                    student_id_parsed,
                    questions_text,
                    rubric,
                    sub_rubric,
                    score,
                    max_points,
                    feedback,
                    detailed_explanation,
                    model_provider,
                    model_name
                FROM exam_grading_results
                WHERE assessment_id IN ({fmt})
                ORDER BY id
                """,
                old_assessment_ids,
            )
            grading_rows = cursor.fetchall()

            # Build a mapping from each original grading_session_id to a new
            # UUID so all rows in the same session share one new session ID.
            grading_session_map = {}
            for row in grading_rows:
                old_sid = row["grading_session_id"]
                if old_sid not in grading_session_map:
                    grading_session_map[old_sid] = str(uuid.uuid4())

            for row in grading_rows:
                cursor.execute(
                    """
                    INSERT INTO exam_grading_results (
                        grading_session_id,
                        graded_by,
                        assessment_id,
                        student_name,
                        student_id_parsed,
                        questions_text,
                        rubric,
                        sub_rubric,
                        score,
                        max_points,
                        feedback,
                        detailed_explanation,
                        model_provider,
                        model_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        grading_session_map[row["grading_session_id"]],
                        row["graded_by"],
                        assessment_id_map[int(row["assessment_id"])],
                        row["student_name"],
                        row["student_id_parsed"],
                        row["questions_text"],
                        row["rubric"],
                        row["sub_rubric"],
                        row["score"],
                        row["max_points"],
                        row["feedback"],
                        row["detailed_explanation"],
                        row["model_provider"],
                        row["model_name"],
                    ),
                )

            # ── Exam Creation Questions ───────────────────────────────────
            cursor.execute(
                f"""
                SELECT
                    creation_session_id,
                    user_id,
                    assessment_id,
                    creation_mode,
                    original_question_text,
                    question_text,
                    question_type,
                    topic,
                    difficulty,
                    answer_guidance
                FROM exam_creation_questions
                WHERE assessment_id IN ({fmt})
                ORDER BY id
                """,
                old_assessment_ids,
            )
            creation_rows = cursor.fetchall()

            # Map each original creation_session_id to a new UUID so grouped
            # question sets remain grouped under the same new session ID.
            creation_session_map = {}
            for row in creation_rows:
                old_sid = row["creation_session_id"]
                if old_sid not in creation_session_map:
                    creation_session_map[old_sid] = str(uuid.uuid4())

            for row in creation_rows:
                cursor.execute(
                    """
                    INSERT INTO exam_creation_questions (
                        creation_session_id,
                        user_id,
                        assessment_id,
                        creation_mode,
                        original_question_text,
                        question_text,
                        question_type,
                        topic,
                        difficulty,
                        answer_guidance
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        creation_session_map[row["creation_session_id"]],
                        row["user_id"],
                        assessment_id_map[int(row["assessment_id"])],
                        row["creation_mode"],
                        row["original_question_text"],
                        row["question_text"],
                        row["question_type"],
                        row["topic"],
                        row["difficulty"],
                        row["answer_guidance"],
                    ),
                )

            # ── Practice Quiz Generated ───────────────────────────────────
            # quiz_id_map tracks old practice_quiz_generated.id → new id so
            # that practice_quiz_attempts can reference the correct new rows.
            cursor.execute(
                f"""
                SELECT
                    id,
                    user_id,
                    assessment_id,
                    source_filenames,
                    questions_json,
                    mc_count,
                    tf_count,
                    sa_count,
                    difficulty,
                    topic_focus,
                    model_used
                FROM practice_quiz_generated
                WHERE assessment_id IN ({fmt})
                ORDER BY id
                """,
                old_assessment_ids,
            )
            quiz_rows = cursor.fetchall()
            quiz_id_map = {}

            for row in quiz_rows:
                cursor.execute(
                    """
                    INSERT INTO practice_quiz_generated (
                        user_id,
                        assessment_id,
                        source_filenames,
                        questions_json,
                        mc_count,
                        tf_count,
                        sa_count,
                        difficulty,
                        topic_focus,
                        model_used
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row["user_id"],
                        assessment_id_map[int(row["assessment_id"])],
                        row["source_filenames"],
                        row["questions_json"],
                        row["mc_count"],
                        row["tf_count"],
                        row["sa_count"],
                        row["difficulty"],
                        row["topic_focus"],
                        row["model_used"],
                    ),
                )
                quiz_id_map[int(row["id"])] = int(cursor.lastrowid)

            # ── Practice Quiz Attempts ────────────────────────────────────
            # Must be inserted after practice_quiz_generated rows exist due
            # to the quiz_id FK. Fetch by old quiz IDs, not assessment_id,
            # to avoid a join and to guarantee only attempts for the source
            # course's quizzes are copied.
            if quiz_id_map:
                old_quiz_ids = list(quiz_id_map.keys())
                fmt_q = ",".join(["%s"] * len(old_quiz_ids))
                cursor.execute(
                    f"""
                    SELECT
                        user_id,
                        quiz_id,
                        assessment_id,
                        answers_json,
                        score
                    FROM practice_quiz_attempts
                    WHERE quiz_id IN ({fmt_q})
                    ORDER BY id
                    """,
                    old_quiz_ids,
                )
                attempt_rows = cursor.fetchall()

                for row in attempt_rows:
                    new_quiz_id = quiz_id_map.get(int(row["quiz_id"]))
                    new_assessment_id = assessment_id_map.get(int(row["assessment_id"])) if row["assessment_id"] else None
                    if not new_quiz_id:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO practice_quiz_attempts (
                            user_id,
                            quiz_id,
                            assessment_id,
                            answers_json,
                            score
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            row["user_id"],
                            new_quiz_id,
                            new_assessment_id,
                            row["answers_json"],
                            row["score"],
                        ),
                    )

        # ---------------------------------------------------------------------
        # Grant the duplicating teacher approved ownership-level teacher access
        # to the new course. No other access records are copied.
        # ---------------------------------------------------------------------
        cursor.execute(
            """
            INSERT INTO course_access (course_id, user_id, access_role, status)
            VALUES (%s, %s, 'teacher', 'approved')
            ON DUPLICATE KEY UPDATE status = 'approved'
            """,
            (int(new_course_id), int(new_owner_user_id)),
        )

        conn.commit()
        return int(new_course_id)

    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()       

# =============================================================================
# QUIZ WRITE OPERATIONS
# =============================================================================
# Functions for persisting AI-generated quiz structures and student submissions.
# All quiz data originates from a structured parse of an ai_outputs record;
# the quiz tables are downstream of that record and cascade-delete with it.


def save_quiz(assessment_id: int, title: str, questions: list,
              grading_mode: str = "auto") -> int:
    """
    Persist a generated quiz and its questions to the database.

    Called after the UReap quiz pipeline parses a structured question list.
    Creates a quizzes row linked to the given assessment, then bulk-inserts all
    question rows with their type, text, options, correct answer, and order.

    The ai_output_id column has been removed from the quizzes table — quizzes
    are now generated directly by the UReap quiz pipeline (quiz_generator_ui)
    rather than through the retired Prebinary AI prompt feature.

    grading_mode controls how submissions for this quiz are evaluated:
      'auto'   — True/False and MCQ graded at submission time.
      'manual' — The instructor enters a final score per submission.
      'ai'     — An AI grading pass is triggered by the instructor after all
                 students have submitted, scoring all question types.

    questions is a list of dicts. Each dict must have the keys:
        question_text   str   — the question body
        question_type   str   — 'true_false' | 'mcq' | 'short_answer'
        options         list  — choice strings for MCQ; empty list otherwise
        correct_answer  str   — expected answer; None for short_answer
        question_order  int   — display index within the full question list

    Returns:
        The primary key of the newly created quizzes row.

    Raises:
        Any mysql.connector exception is propagated to the caller (app.py)
        so the user-facing error handler can display it via st.error().
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO quizzes
                (assessment_id, title, published, grades_visible, grading_mode)
            VALUES (%s, %s, 0, 0, %s)
            """,
            (int(assessment_id), str(title), str(grading_mode)),
        )
        quiz_id = cursor.lastrowid

        # Bulk-insert all question rows. options_json stores MCQ choices as a
        # JSON array; True/False and short-answer questions store NULL.
        for q in questions:
            options_json = (
                json.dumps(q["options"]) if q.get("options") else None
            )
            cursor.execute(
                """
                INSERT INTO quiz_questions
                    (quiz_id, question_text, question_type,
                     options_json, correct_answer, question_order)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    quiz_id,
                    str(q["question_text"]),
                    str(q["question_type"]),
                    options_json,
                    q.get("correct_answer"),
                    int(q["question_order"]),
                ),
            )

        conn.commit()
        return int(quiz_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def set_quiz_published(quiz_id: int, published: bool) -> None:
    """
    Toggle the published flag on a quiz row.

    When published is True, the quiz questions become visible to students on
    the student-facing files view for the linked assessment. When False, the
    quiz is hidden and only visible to instructors and admins. This flag
    controls question visibility only — grade visibility is controlled
    separately via set_quiz_grades_visible().
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE quizzes SET published = %s WHERE id = %s",
            (1 if published else 0, int(quiz_id)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def set_quiz_grades_visible(quiz_id: int, visible: bool) -> None:
    """
    Toggle the grades_visible flag on a quiz row.

    When True, students who have submitted can see their score, per-question
    correctness indicators, and any grading notes on their submission. When
    False, the submission confirmation is shown but no score or feedback is
    revealed. This allows instructors to finish reviewing all submissions
    before releasing results to the cohort at once.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE quizzes SET grades_visible = %s WHERE id = %s",
            (1 if visible else 0, int(quiz_id)),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def save_grade(submission_id: int, score: float, grading_notes: str) -> None:
    """
    Write a final grade and optional feedback to a quiz submission row.

    Both manual instructor grading and AI-generated grading write through this
    function. The distinction between the two grading paths is made at the call
    site in app.py, not in storage — both outcomes occupy the same manual_score
    and grading_notes columns so the student-facing display logic is uniform
    regardless of how the grade was produced.

    The auto-calculated score column is intentionally left unchanged so the
    original machine result is always preserved for audit purposes. Callers
    should validate that score is in the range 0–100 before invoking this
    function; no range check is applied here.

    grading_notes may be an empty string. An empty string is stored as NULL
    so that NULL reliably means "no feedback provided" in downstream queries.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE quiz_submissions
            SET manual_score  = %s,
                grading_notes = %s
            WHERE id = %s
            """,
            (
                float(score),
                grading_notes.strip() or None,
                int(submission_id),
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def save_ai_answer_corrections(submission_id: int, corrections: dict) -> None:
    """
    Write per-question correctness verdicts back to quiz_answers after an
    AI grading pass.

    corrections is a dict mapping question_id (int) to a boolean or integer
    correctness value (True/1 = correct, False/0 = incorrect). Only rows
    whose question_id appears in the dict are updated; questions absent from
    the dict are left unchanged.

    This is called alongside save_grade() so that the per-question
    is_correct column reflects the AI's evaluation for every question type,
    including short-answer questions that were left as NULL at submission time.
    The student-facing review display then shows Correct / Incorrect for all
    questions once grades are released.

    Raises:
        Any mysql.connector exception is propagated to the caller (app.py).
    """
    if not corrections:
        return

    conn   = get_connection()
    cursor = conn.cursor()
    try:
        for question_id, is_correct in corrections.items():
            cursor.execute(
                """
                UPDATE quiz_answers
                SET is_correct = %s
                WHERE submission_id = %s
                  AND question_id   = %s
                """,
                (
                    1 if is_correct else 0,
                    int(submission_id),
                    int(question_id),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def save_quiz_submission(quiz_id: int, student_id: int, answers: dict) -> float:
    """
    Record a student's quiz submission and calculate their score.

    answers is a dict mapping question_id (int) to the student's answer_text
    (str). This function:

      1. Fetches all questions for the quiz to obtain their correct answers
         and question types.
      2. Inserts a quiz_submissions row. The UNIQUE KEY (quiz_id, student_id)
         prevents re-submission — callers should check for an existing row
         before calling this function and block re-attempts at the UI layer.
      3. For each answered question, inserts a quiz_answers row and computes
         is_correct for auto-graded types (true_false, mcq). Short-answer
         questions receive is_correct = NULL.
      4. Calculates the score as:
             (auto-graded correct count / total auto-graded questions) × 100
         Short-answer questions are excluded from the denominator because they
         have no machine-verifiable correct answer.
      5. Updates the quiz_submissions row with the computed score.

    Returns:
        The final score as a float (0.0–100.0). Returns 0.0 if no auto-graded
        questions are present (all short-answer quiz).

    Raises:
        Any mysql.connector exception is propagated to the caller.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Load question metadata needed for grading.
        cursor.execute(
            """
            SELECT id, question_type, correct_answer
            FROM quiz_questions
            WHERE quiz_id = %s
            """,
            (int(quiz_id),),
        )
        questions = cursor.fetchall()

        # Insert the submission header row. Score is NULL until grading completes.
        cursor.execute(
            """
            INSERT INTO quiz_submissions (quiz_id, student_id, score)
            VALUES (%s, %s, NULL)
            """,
            (int(quiz_id), int(student_id)),
        )
        submission_id = cursor.lastrowid

        auto_graded_total   = 0
        auto_graded_correct = 0

        for q in questions:
            q_id   = int(q["id"])
            q_type = str(q["question_type"])
            correct = q.get("correct_answer")

            student_answer = answers.get(q_id, "")
            is_correct     = None

            if q_type in ("true_false", "mcq") and correct is not None:
                # Case-insensitive comparison handles any capitalisation
                # differences between the stored answer and student input.
                is_correct = 1 if student_answer.strip().lower() == correct.strip().lower() else 0
                auto_graded_total  += 1
                auto_graded_correct += int(is_correct)

            cursor.execute(
                """
                INSERT INTO quiz_answers
                    (submission_id, question_id, answer_text, is_correct)
                VALUES (%s, %s, %s, %s)
                """,
                (submission_id, q_id, student_answer, is_correct),
            )

        # Compute the percentage score from auto-graded questions only.
        score = (auto_graded_correct / auto_graded_total * 100) if auto_graded_total > 0 else 0.0

        cursor.execute(
            "UPDATE quiz_submissions SET score = %s WHERE id = %s",
            (score, submission_id),
        )

        conn.commit()
        return float(score)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()