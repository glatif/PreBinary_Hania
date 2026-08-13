# =============================================================================
# roster_import.py — CSV/Excel student roster upload for course enrollment
# =============================================================================
# Lets an instructor upload a class list (First Name, Last Name, ID Number,
# Email) and either enroll students who already have an account or create
# new accounts for ones who don't, all in one pass. Used from
# _render_course_access_panel() in app.py.
#
# Flow: parse_roster_file() -> validate_roster() -> (instructor reviews/edits
# the preview) -> commit_roster(). Never writes to the database until
# commit_roster() is explicitly called.
#
# Matching rule: email is the identity key. A row whose email matches an
# existing user only enrolls them (never silently overwrites their name/ID
# unless the caller opts into update_existing=True). A row whose ID number
# collides with a *different* existing user's ID number is flagged as a
# conflict and skipped at commit time until the instructor resolves it.
# =============================================================================

import re
from typing import Dict, List

import mysql.connector
import pandas as pd

from auth import (
    admin_create_user,
    admin_reset_user_password,
    grant_course_access,
    generate_temp_password,
    send_temp_password_email,
    update_user_profile,
)
from db import get_connection

_COLUMN_ALIASES = {
    "first_name": {"first name", "firstname", "first"},
    "last_name":  {"last name", "lastname", "last", "surname"},
    "id_number":  {"id number", "id", "student id", "roll no", "roll number", "id_number"},
    "email":      {"email", "email address", "e-mail"},
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_roster_file(uploaded_file) -> pd.DataFrame:
    """
    Read an uploaded .csv or .xlsx roster file into a normalized DataFrame
    with columns: first_name, last_name, id_number, email.

    Column headers are matched case-insensitively against common variants
    (see _COLUMN_ALIASES). Raises ValueError if a required column can't be
    found or the file type isn't supported.
    """
    name = (uploaded_file.name or "").lower()
    if name.endswith(".csv"):
        raw = pd.read_csv(uploaded_file, dtype=str)
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        raw = pd.read_excel(uploaded_file, dtype=str)
    else:
        raise ValueError("Unsupported file type — upload a .csv or .xlsx file.")

    normalized_cols = {c.strip().lower(): c for c in raw.columns}
    resolved = {}
    for field, aliases in _COLUMN_ALIASES.items():
        match = next((normalized_cols[a] for a in aliases if a in normalized_cols), None)
        if match is None:
            raise ValueError(
                f"Couldn't find a column for '{field.replace('_', ' ')}'. "
                f"Expected one of: {', '.join(sorted(aliases))}."
            )
        resolved[field] = match

    df = pd.DataFrame({
        field: raw[col].fillna("").astype(str).str.strip()
        for field, col in resolved.items()
    })
    # Drop fully blank rows (common at the end of a spreadsheet export).
    df = df[(df != "").any(axis=1)].reset_index(drop=True)
    return df


def _suggest_username(first_name: str, last_name: str, taken: set) -> str:
    base = (first_name[:1] + last_name).lower()
    base = re.sub(r"[^a-z0-9]", "", base) or "student"
    candidate = base
    n = 1
    while candidate in taken:
        n += 1
        candidate = f"{base}{n}"
    taken.add(candidate)
    return candidate


def _resolve_available_username(preferred: str) -> str:
    """
    Return `preferred` if it's currently free, otherwise the lowest-numbered
    `preferred{N}` variant that is. One query against live DB state, used
    immediately before an INSERT so a username that looked free at preview
    time (possibly minutes ago) is re-checked right before it's committed.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username FROM users WHERE username LIKE %s", (f"{preferred}%",))
        taken = {row[0].lower() for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()

    if preferred.lower() not in taken:
        return preferred
    n = 1
    while True:
        n += 1
        candidate = f"{preferred}{n}"
        if candidate.lower() not in taken:
            return candidate


def validate_roster(df: pd.DataFrame, course_id: int) -> pd.DataFrame:
    """
    Check each roster row against the live database and annotate it with:

      status              — "new" | "enroll_existing" | "conflict"
      conflict_reason     — human-readable reason, blank unless status == "conflict"
      existing_user_id    — matched users.id for "enroll_existing" rows, else None
      resolved_username   — generated username for "new" rows, else the existing username
      include             — bool, defaults to True except for conflicts

    Never writes to the database.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, username, email, roll_no FROM users")
        all_users = cursor.fetchall()
        cursor.execute(
            "SELECT user_id FROM course_access WHERE course_id = %s AND status != 'revoked'",
            (course_id,),
        )
        already_enrolled = {row["user_id"] for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()

    by_email = {u["email"].lower(): u for u in all_users if u["email"]}
    by_roll_no = {u["roll_no"]: u for u in all_users if u["roll_no"]}
    taken_usernames = {u["username"].lower() for u in all_users}

    seen_emails_in_file = set()
    rows = []
    for _, r in df.iterrows():
        first_name = r["first_name"]
        last_name  = r["last_name"]
        id_number  = r["id_number"]
        email      = r["email"]
        email_lc   = email.lower()

        status, reason, existing_user_id, resolved_username = "new", "", None, ""

        if not email or not _EMAIL_RE.match(email):
            status, reason = "conflict", "Missing or invalid email address."
        elif email_lc in seen_emails_in_file:
            status, reason = "conflict", "Duplicate email within this file."
        elif email_lc in by_email:
            existing = by_email[email_lc]
            existing_user_id = existing["id"]
            resolved_username = existing["username"]
            if existing_user_id in already_enrolled:
                status, reason = "conflict", "Already enrolled in this course."
            else:
                status = "enroll_existing"
                if id_number and existing["roll_no"] and id_number != existing["roll_no"]:
                    reason = (
                        f"Note: file ID '{id_number}' differs from the "
                        f"account's stored ID '{existing['roll_no']}'."
                    )
        elif id_number and id_number in by_roll_no:
            status, reason = (
                "conflict",
                f"ID number already registered to a different email "
                f"({by_roll_no[id_number]['email']}).",
            )
        else:
            status = "new"
            resolved_username = _suggest_username(first_name, last_name, taken_usernames)

        seen_emails_in_file.add(email_lc)
        rows.append({
            "first_name": first_name,
            "last_name": last_name,
            "id_number": id_number,
            "email": email,
            "status": status,
            "conflict_reason": reason,
            "existing_user_id": existing_user_id,
            "resolved_username": resolved_username,
            "include": status != "conflict",
        })

    return pd.DataFrame(rows)


def commit_roster(df: pd.DataFrame, course_id: int, update_existing: bool = False) -> Dict:
    """
    Apply the reviewed roster: create accounts for "new" rows and enroll
    both "new" and "enroll_existing" rows (where include == True) in the
    course. "conflict" rows and any row with include == False are skipped.

    New accounts get a generated temp password, must_change_password set,
    and an emailed notification (email failures — e.g. SMTP not configured —
    are swallowed per-row so one bad row doesn't stop the rest of the roster
    from committing).

    Args:
        update_existing: If True, syncs name/ID number onto existing users
            whose file row differs from their stored profile.

    Returns:
        {"enrolled_existing": n, "created_new": n, "skipped": n, "email_failed": n,
         "failed": [{"name": str, "reason": str}, ...]}

    A row's resolved_username/email were only checked for uniqueness at
    preview time, not right before this INSERT — another row in the same
    batch, a concurrent "Add a Single Student", or simply re-committing a
    stale preview can make that check out of date by the time we get here.
    Username collisions specifically are self-healed by retrying with a
    numeric suffix (checked against the live DB via the INSERT itself, not
    the possibly-stale preview). Any other database error for a row is
    caught and skipped with a reason, rather than raising and aborting the
    rest of the batch — one bad row must not cost the other N-1 their accounts.
    """
    counts = {"enrolled_existing": 0, "created_new": 0, "skipped": 0, "email_failed": 0, "failed": []}

    for _, r in df.iterrows():
        if not r.get("include", False) or r["status"] == "conflict":
            counts["skipped"] += 1
            continue

        try:
            if r["status"] == "enroll_existing":
                user_id = int(r["existing_user_id"])
                if update_existing:
                    update_user_profile(
                        user_id,
                        first_name=r["first_name"], last_name=r["last_name"],
                        phone=None, street=None, city=None, state_prov=None,
                        postal_code=None, country=None, roll_no=r["id_number"] or None,
                    )
                grant_course_access(course_id, user_id, "student")
                counts["enrolled_existing"] += 1

            elif r["status"] == "new":
                temp_password = generate_temp_password()
                # Re-check username availability right before inserting, in one
                # query, rather than trusting the preview-time value — it may
                # have been taken since (another row in this batch, a
                # concurrent "Add a Single Student", or a re-committed stale
                # preview). Cheaper and less connection churn than a blind
                # retry-on-IntegrityError loop.
                username = _resolve_available_username(r["resolved_username"])
                try:
                    new_id = admin_create_user(
                        username=username, email=r["email"], password=temp_password,
                        first_name=r["first_name"], last_name=r["last_name"], phone=None,
                        street=None, city=None, state_prov=None, postal_code=None, country=None,
                        role="student", status="active", roll_no=r["id_number"] or None,
                        must_change_password=True,
                    )
                except mysql.connector.IntegrityError:
                    # Extremely narrow window between the check above and this
                    # insert — one more attempt with a fully re-checked name
                    # before giving up and reporting the row as failed.
                    username = _resolve_available_username(r["resolved_username"])
                    new_id = admin_create_user(
                        username=username, email=r["email"], password=temp_password,
                        first_name=r["first_name"], last_name=r["last_name"], phone=None,
                        street=None, city=None, state_prov=None, postal_code=None, country=None,
                        role="student", status="active", roll_no=r["id_number"] or None,
                        must_change_password=True,
                    )

                grant_course_access(course_id, new_id, "student")
                counts["created_new"] += 1
                try:
                    send_temp_password_email(
                        {"username": username, "email": r["email"], "first_name": r["first_name"]},
                        temp_password,
                    )
                except RuntimeError:
                    counts["email_failed"] += 1

        except Exception as exc:
            counts["failed"].append({
                "name": f"{r['first_name']} {r['last_name']}".strip() or r["email"],
                "reason": str(exc),
            })

    return counts


def resend_login_credentials(user_ids: List[int]) -> Dict:
    """
    Generate a fresh temp password for each given user and email them their
    username + password, setting must_change_password so they're forced to
    choose their own on next login. Used for both the single-student "Send
    Login Email" action and the course-wide "Email All Students" button —
    both call this with a one- or many-element list.

    One user's DB or email failure doesn't stop the rest of the batch, same
    reasoning as commit_roster(): a bad row must not cost everyone else
    their notification.

    Returns:
        {"sent": n, "failed": [{"name": str, "reason": str}, ...]}
    """
    counts = {"sent": 0, "failed": []}

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if not user_ids:
            return counts
        placeholders = ",".join(["%s"] * len(user_ids))
        cursor.execute(
            f"SELECT id, username, email, first_name FROM users WHERE id IN ({placeholders})",
            tuple(user_ids),
        )
        users = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    for user in users:
        try:
            temp_password = generate_temp_password()
            admin_reset_user_password(user["id"], temp_password, must_change=True)
            send_temp_password_email(user, temp_password)
            counts["sent"] += 1
        except Exception as exc:
            counts["failed"].append({"name": user.get("first_name") or user["email"], "reason": str(exc)})

    return counts
