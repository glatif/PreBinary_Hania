# =============================================================================
# validators.py — Prebinary
# =============================================================================
# All input validation rules for the application.
#
# Every form and bulk editor in app.py calls these helpers before any database
# write. Individual validators return None on success or an error string on
# failure. Composite validators collect all errors for their form and return
# them as a list, so all problems can be surfaced to the user at once rather
# than one at a time.
#
# Validation rules summary:
#   - Username:     3–30 characters, letters / digits / underscores only.
#   - Password:     Minimum 8 characters. No other complexity constraints.
#   - Names:        1–50 characters, letters (incl. accented) / spaces /
#                   hyphens / apostrophes.
#   - Email:        Validated and normalised via the email-validator library.
#   - Phone:        Optional. When provided: 6–20 characters, digits / spaces /
#                   + / - / ( / ) only (international format).
#   - Postal code:  Optional. When provided: max 20 characters (international).
#   - API keys:     Optional. When provided: max 255 characters, no whitespace.
#   - Course code:  1–20 characters, letters and digits only.
#   - Text fields:  Length-capped to their DB column sizes; required flag
#                   controls whether blank values are rejected.
#   - Marks:        Integer ≥ 1.
#   - Year:         Integer 2000–2100.
#   - Credit hours: Integer 1–12.
# =============================================================================

from __future__ import annotations
import re
from email_validator import validate_email, EmailNotValidError


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _none_or_str(v) -> str:
    """Coerce a value to a stripped string. Treats None and non-string types safely."""
    return str(v).strip() if v is not None else ""


# =============================================================================
# EMAIL
# =============================================================================

def validate_email_field(value: str) -> tuple[str, str | None]:
    """
    Validate and normalise an email address using the email-validator library.

    Normalisation lowercases the domain and applies RFC-compliant canonicalisation
    (e.g. gmail dot-stripping), so the stored value is consistent regardless of
    how the user typed it.

    Returns:
        (normalised_email, None)      on success
        ("",               error_msg) on failure
    """
    v = _none_or_str(value)
    if not v:
        return "", "Email is required."
    try:
        normalised = validate_email(v).email
        return normalised, None
    except EmailNotValidError as exc:
        return "", f"Invalid email address: {exc}"


# =============================================================================
# PASSWORD
# =============================================================================

def validate_password(value: str) -> str | None:
    """
    Validate password strength.

    Only a minimum length of 8 characters is enforced. No complexity rules
    (uppercase, symbols, etc.) are applied, keeping the requirement accessible
    while still preventing trivially short passwords.

    Returns None on success, error string on failure.
    """
    if not value:
        return "Password is required."
    if len(value) < 8:
        return "Password must be at least 8 characters long."
    return None


# =============================================================================
# USERNAME
# =============================================================================

_USERNAME_RE = re.compile(r'^[A-Za-z0-9_]{3,30}$')


def validate_username(value: str) -> str | None:
    """
    Validate a username.

    Must be 3–30 characters containing only letters, digits, and underscores.
    Spaces and special characters are disallowed to keep usernames safe for
    use in URLs and file paths if needed.

    Returns None on success, error string on failure.
    """
    v = _none_or_str(value)
    if not v:
        return "Username is required."
    if not _USERNAME_RE.match(v):
        return (
            "Username must be 3–30 characters and contain only "
            "letters, numbers, and underscores."
        )
    return None


# =============================================================================
# NAME (first name / last name)
# =============================================================================

# Allows accented Latin characters (À–ö, ø–ÿ) to support international names,
# plus spaces, hyphens, and apostrophes for compound names like O'Brien or
# Martínez-García.
_NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' \-]{1,50}$")


def validate_name(value: str, field_label: str = "Name") -> str | None:
    """
    Validate a first or last name.

    Accepts 1–50 characters of letters (including accented), spaces, hyphens,
    and apostrophes. Digits and most punctuation are rejected.

    Returns None on success, error string on failure.
    """
    v = _none_or_str(value)
    if not v:
        return f"{field_label} is required."
    if len(v) > 50:
        return f"{field_label} must be 50 characters or fewer."
    if not _NAME_RE.match(v):
        return f"{field_label} must contain only letters, spaces, hyphens, or apostrophes."
    return None


# =============================================================================
# PHONE  (international, optional)
# =============================================================================

# Permits the characters commonly used in international phone number notation:
# digits, spaces, +, -, (, ). Length bounds (6–20) cover short local numbers
# through long international ones with formatting.
_PHONE_RE = re.compile(r'^[\d\s\+\-\(\)]{6,20}$')


def validate_phone(value: str) -> str | None:
    """
    Validate an international phone number.

    Phone is optional everywhere. When a non-empty value is provided, it must
    be 6–20 characters using only digits, spaces, +, -, (, ).

    Returns None on success (including when empty), error string on failure.
    """
    v = _none_or_str(value)
    if not v:
        return None  # optional — blank is acceptable
    if not _PHONE_RE.match(v):
        return (
            "Phone number must be 6–20 characters and contain only "
            "digits, spaces, +, -, (, or )."
        )
    return None


# =============================================================================
# POSTAL CODE  (international, optional)
# =============================================================================

def validate_postal_code(value: str) -> str | None:
    """
    Validate an international postal code.

    Postal code is optional. When provided, only a maximum length of 20
    characters is enforced. No format pattern is applied because postal code
    formats vary widely across countries (alphanumeric, hyphenated, spaced).

    Returns None on success (including when empty), error string on failure.
    """
    v = _none_or_str(value)
    if not v:
        return None  # optional
    if len(v) > 20:
        return "Postal code must be 20 characters or fewer."
    return None


# =============================================================================
# API KEY  (optional)
# =============================================================================

def validate_api_key(value: str, provider_label: str) -> str | None:
    """
    Validate a stored AI provider API key.

    API keys are optional. When provided, they must fit within the users table
    VARCHAR(255) columns and must not contain whitespace or control characters,
    which are almost always the result of accidental paste or input errors.

    Args:
        value:          Raw key string from the widget (may be None or empty).
        provider_label: Human-readable provider name used in error messages
                        (e.g. "ChatGPT", "Gemini", "Grok").

    Returns None on success (including when empty), error string on failure.
    """
    v = _none_or_str(value)
    if not v:
        return None  # optional — blank means the key is simply not set
    if len(v) > 255:
        return f"{provider_label} API key must be 255 characters or fewer."
    if any(ch.isspace() for ch in v):
        return f"{provider_label} API key must not contain spaces or line breaks."
    return None


# =============================================================================
# GENERIC TEXT FIELD
# =============================================================================

def validate_text_field(
    value: str,
    field_label: str,
    max_len: int,
    required: bool = False,
) -> str | None:
    """
    Validate a generic bounded text field.

    Used for street address, city, state/province, country, instructor name,
    and any other column-backed text input where only a length constraint and
    an optional required flag are needed.

    Args:
        value:       Raw input string.
        field_label: Label used in user-facing error messages.
        max_len:     Maximum allowed character count, matching the DB column size.
        required:    If True, empty values are rejected with an error.

    Returns None on success, error string on failure.
    """
    v = _none_or_str(value)
    if not v:
        if required:
            return f"{field_label} is required."
        return None
    if len(v) > max_len:
        return f"{field_label} must be {max_len} characters or fewer."
    return None


# =============================================================================
# COURSE CODE
# =============================================================================

# Letters and digits only — no spaces or special characters. This keeps course
# codes safe for use in filesystem paths (upload directory names) and avoids
# ambiguity in display contexts.
_COURSE_CODE_RE = re.compile(r'^[A-Za-z0-9]{1,20}$')


def validate_course_code(value: str) -> str | None:
    """
    Validate a course code.

    Must be 1–20 characters of letters and digits only (e.g. CS101, MATH202).
    Uniqueness is not checked here; the caller must call is_course_code_unique()
    from auth.py separately after this validation passes.

    Returns None on success, error string on failure.
    """
    v = _none_or_str(value)
    if not v:
        return "Course code is required."
    if not _COURSE_CODE_RE.match(v):
        return (
            "Course code must be 1–20 characters and contain only "
            "letters and digits (e.g. CS101, MATH202)."
        )
    return None


# =============================================================================
# COURSE NAME / ASSESSMENT TITLE
# =============================================================================

def validate_course_name(value: str) -> str | None:
    """
    Validate a course name.

    Required, maximum 255 characters (matching the DB column size).
    """
    return validate_text_field(value, "Course name", 255, required=True)


def validate_assessment_title(value: str) -> str | None:
    """
    Validate an assessment title.

    Required, maximum 255 characters (matching the DB column size).
    """
    return validate_text_field(value, "Assessment title", 255, required=True)


def validate_quiz_title(value: str) -> str | None:
    """
    Validate a quiz title.

    Required, maximum 255 characters (matching the quizzes.title column size).
    Used by the Quiz Generation form in app.py before the quiz INSERT is issued,
    ensuring the same pre-write validation pattern applied to assessment titles
    and course names is consistent across all user-supplied name fields.
    """
    return validate_text_field(value, "Quiz title", 255, required=True)


# =============================================================================
# NUMERIC FIELDS
# =============================================================================

def validate_credit_hours(value) -> str | None:
    """
    Validate credit hours for a course.

    Must be an integer between 1 and 12 inclusive.

    Returns None on success, error string on failure.
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "Credit hours must be a whole number."
    if not (1 <= v <= 12):
        return "Credit hours must be between 1 and 12."
    return None


def validate_year(value) -> str | None:
    """
    Validate a course year.

    Must be an integer between 2000 and 2100 inclusive. The upper bound
    provides headroom for future-dated course planning without being unbounded.

    Returns None on success, error string on failure.
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "Year must be a whole number."
    if not (2000 <= v <= 2100):
        return "Year must be between 2000 and 2100."
    return None


# =============================================================================
# COMPOSITE: FULL USER FORM
# =============================================================================

def validate_user_form(
    *,
    username: str,
    email: str,
    password: str | None = None,
    first_name: str,
    last_name: str,
    phone: str,
    street: str,
    city: str,
    state_prov: str,
    postal_code: str,
    country: str,
) -> list[str]:
    """
    Validate all standard user form fields in a single call.

    Returns a list of error strings (empty list means all fields are valid).
    All errors are collected before returning so the user can see and fix
    every problem at once rather than encountering them one by one.

    Callers are responsible for uniqueness checks (username, email, phone)
    since those require DB access and are separate from format validation.

    The password argument should be the raw value from the widget — do not
    strip it before passing. Pass None to skip password validation entirely
    (e.g. when editing a user without changing their password).
    """
    errors: list[str] = []

    def _add(result):
        if result:
            errors.append(result)

    _add(validate_username(username))

    _, email_err = validate_email_field(email)
    if email_err:
        errors.append(email_err)

    if password is not None:
        _add(validate_password(password))

    _add(validate_name(first_name, "First name"))
    _add(validate_name(last_name,  "Last name"))
    _add(validate_phone(phone))
    _add(validate_text_field(street,     "Street address", 255))
    _add(validate_text_field(city,       "City",           100))
    _add(validate_text_field(state_prov, "State/Province", 100))
    _add(validate_postal_code(postal_code))
    _add(validate_text_field(country,    "Country",        100))

    return errors


# =============================================================================
# COMPOSITE: FULL COURSE FORM
# =============================================================================

def validate_course_form(
    *,
    course_code: str,
    course_name: str,
    credit_hours,
    year,
    instructor_name: str,
) -> list[str]:
    """
    Validate all course creation and edit fields in a single call.

    Returns a list of error strings (empty list means all fields are valid).
    Uniqueness of course_code must be checked separately by the caller via
    is_course_code_unique() in auth.py, since that requires a DB query.
    """
    errors: list[str] = []

    def _add(result):
        if result:
            errors.append(result)

    _add(validate_course_code(course_code))
    _add(validate_course_name(course_name))
    _add(validate_credit_hours(credit_hours))
    _add(validate_year(year))
    _add(validate_text_field(instructor_name, "Instructor name", 255))

    return errors


# =============================================================================
# COMPOSITE: ASSESSMENT FORM
# =============================================================================

def validate_assessment_form(*, title: str) -> list[str]:
    """
    Validate assessment creation and edit fields.

    Returns a list of error strings (empty list means all fields are valid).
    """
    errors: list[str] = []

    def _add(result):
        if result:
            errors.append(result)

    _add(validate_assessment_title(title))

    return errors