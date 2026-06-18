import os
import json
import shutil
import datetime
import streamlit as st
import uuid
from typing import Dict, List, Optional
from pathlib import Path

from db import get_connection

from src.utils.rag_utils import (
    load_pdf_documents,
    chunk_documents,
    create_embeddings,
    build_faiss_index,
    save_index_and_chunks,
    load_resources,
    get_relevant_context,
)
from src.utils.llm_utils import MODELS, MODEL_PROVIDERS, stream_llm, stream_llm_chat
from src.features.quiz_generator.document_processor import (
    process_uploaded_files,
    validate_extracted_content,
)


# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum number of past conversation turns passed to the LLM as context.
# Older turns beyond this cap are still displayed in the UI and saved in the
# DB — the cap only affects what is included in the LLM request to avoid
# exceeding model context windows.
RAG_CHAT_CONTEXT_TURNS = 10

# Supported languages for RAG responses.
RAG_LANGUAGES = ["English", "French", "Arabic", "Hindi"]


# =============================================================================
# PER-USER INGESTION METADATA
# =============================================================================
# Each user has a JSON sidecar file at data/rag/{user_id}/ingestion_metadata.json
# that tracks every indexing batch run by that user. Each entry records a unique
# ingestion ID, the list of filenames in the batch, the path to that batch's
# FAISS index directory, and the timestamp of indexing.
#
# Each indexing run writes its FAISS files to a unique directory
# data/rag/{user_id}/{ingestion_id}/ so every batch is independently
# preserved on disk. The Use button loads a batch's directory as the active
# index for querying, making it a true document switcher rather than a
# display-only label change.
#
# The rag_indexes DB row tracks which directory is currently active; the
# metadata JSON tracks the full history of batches for the UI table.

def _ingestion_metadata_path(user_id: int) -> Path:
    """Return the path to the per-user ingestion metadata JSON file."""
    return Path("data") / "rag" / str(user_id) / "ingestion_metadata.json"


def get_ingested_documents(user_id: int) -> List[Dict]:
    """
    Return the list of ingestion batch records for a user, ordered by most
    recent first. Each record contains: id, filenames (list), label (str),
    index_dir (str), timestamp (str).
    Returns an empty list if the metadata file does not exist or cannot be read.
    """
    path = _ingestion_metadata_path(user_id)
    if not path.exists():
        return []
    try:
        with open(path) as f:
            records = json.load(f)
        return sorted(records, key=lambda r: r.get("timestamp", ""), reverse=True)
    except (json.JSONDecodeError, OSError):
        return []


def _save_ingestion_metadata(user_id: int, records: List[Dict]) -> None:
    """Write the ingestion metadata list to disk, creating the directory if needed."""
    path = _ingestion_metadata_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(records, f, indent=2, default=str)


def add_ingestion_to_metadata(
    user_id: int,
    ingestion_id: str,
    filenames: List[str],
    index_dir: str,
) -> None:
    """
    Add one ingestion batch record to the per-user metadata file.
    Each batch gets a unique ingestion_id and its own index_dir on disk.
    The label is the comma-joined list of filenames, truncated for display.
    """
    path = _ingestion_metadata_path(user_id)
    records = []
    if path.exists():
        try:
            with open(path) as f:
                records = json.load(f)
        except (json.JSONDecodeError, OSError):
            records = []

    label = ", ".join(filenames) if filenames else ingestion_id

    records.append({
        "id":        ingestion_id,
        "filenames": filenames,
        "label":     label,
        "index_dir": index_dir,
        "timestamp": datetime.datetime.now().isoformat(),
    })
    _save_ingestion_metadata(user_id, records)


def remove_ingestion_from_metadata(user_id: int, ingestion_id: str) -> None:
    """
    Remove a single ingestion batch record and delete its FAISS directory
    from disk. If the deleted batch was the active index, the caller is
    responsible for clearing the active index state.
    """
    path = _ingestion_metadata_path(user_id)
    if not path.exists():
        return
    try:
        with open(path) as f:
            records = json.load(f)

        # Find the record to get its index_dir before removing it.
        to_remove = next((r for r in records if r.get("id") == ingestion_id), None)
        records = [r for r in records if r.get("id") != ingestion_id]
        _save_ingestion_metadata(user_id, records)

        # Delete the batch's FAISS directory from disk.
        # Safety: only delete if index_dir is a non-empty string that resolves
        # to a path inside data/rag/{user_id}/. An empty string resolves to
        # the current working directory via Path("") == Path("."), which would
        # cause rmtree to delete the entire project. This guard prevents that.
        if to_remove:
            raw_dir = to_remove.get("index_dir", "")
            if raw_dir:
                batch_dir = Path(raw_dir).resolve()
                safe_root = (Path("data") / "rag" / str(user_id)).resolve()
                if batch_dir != safe_root and str(batch_dir).startswith(str(safe_root)):
                    shutil.rmtree(batch_dir, ignore_errors=True)

    except (json.JSONDecodeError, OSError):
        pass




def get_current_user_id() -> Optional[int]:
    """Return the logged-in user's ID from session state, or None."""
    user = st.session_state.get("user", {})
    return user.get("id")


def _init_rag_session_state() -> None:
    """
    Initialise all RAG-specific session state keys if not already present.
    Called at the top of rag_ui() on every render so downstream code can
    read these keys without KeyError guards.

    rag_chat_history      — list of {"role": str, "content": str} dicts
                            representing the current in-progress conversation.
    rag_current_session_id — UUID string of the active chat session, or None
                            if no conversation has been started this session.
    last_loaded_index_dir — path of the FAISS directory currently loaded into
                            session state. Used to detect when the index has
                            changed and resources must be reloaded.
    """
    defaults = {
        "rag_chat_history":        [],
        "rag_current_session_id":  None,
        "last_loaded_index_dir":   None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _clear_rag_chat_session() -> None:
    """
    Clear the in-memory chat session state without touching the database.
    Called when re-indexing, deleting the index, or switching to a different
    chat session from the History tab. The DB record of any past session is
    preserved — only the in-memory state is cleared.
    """
    st.session_state["rag_chat_history"]       = []
    st.session_state["rag_current_session_id"] = None


def _clear_faiss_resources() -> None:
    """
    Remove the loaded FAISS resources from session state so they are
    reloaded on the next render. Called whenever the active index directory
    changes — either because new documents were indexed or a past session's
    snapshot was restored as the active index.
    """
    for key in ["embeddings", "index", "chunks", "embedding_model",
                "last_loaded_index_dir"]:
        st.session_state.pop(key, None)


# =============================================================================
# DATABASE — RAG INDEXES
# =============================================================================

def get_user_rag_index(user_id: int) -> Optional[Dict]:
    """
    Fetch the current user's RAG index row from rag_indexes.
    Returns None if the user has not yet indexed any documents.

    The indexed_filenames_json column is parsed into a list on the returned
    dict under the key 'indexed_filenames' for convenient UI display.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, user_id, index_dir_path, indexed_filenames_json,
                   document_count, chunk_count, active_chat_session_id,
                   created_at, updated_at
            FROM rag_indexes
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        try:
            row["indexed_filenames"] = json.loads(row["indexed_filenames_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            row["indexed_filenames"] = []
        return row
    finally:
        cursor.close()
        conn.close()


def upsert_user_rag_index(
    user_id: int,
    index_dir_path: str,
    filenames: List[str],
    document_count: int,
    chunk_count: int,
    active_chat_session_id: Optional[str] = None,
) -> None:
    """
    Insert or update the user's single rag_indexes row.

    active_chat_session_id is set to None when the user indexes new documents
    (clearing any reference to a previously loaded chat session snapshot) and
    set to a session UUID when a past chat session is restored as the active index.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO rag_indexes (
                user_id, index_dir_path, indexed_filenames_json,
                document_count, chunk_count, active_chat_session_id
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                index_dir_path         = VALUES(index_dir_path),
                indexed_filenames_json = VALUES(indexed_filenames_json),
                document_count         = VALUES(document_count),
                chunk_count            = VALUES(chunk_count),
                active_chat_session_id = VALUES(active_chat_session_id),
                updated_at             = CURRENT_TIMESTAMP
        """, (
            user_id,
            index_dir_path,
            json.dumps(filenames),
            document_count,
            chunk_count,
            active_chat_session_id,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_user_rag_index(user_id: int) -> None:
    """
    Delete the user's rag_indexes row and remove the active index directory
    from disk. Session snapshot directories under data/rag/{user_id}/ are
    not removed here — they remain available for loading from the History tab.
    Only the active index directory (data/rag/{user_id}/ itself, not its
    subdirectories) is removed.
    """
    existing = get_user_rag_index(user_id)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM rag_indexes WHERE user_id = %s", (user_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    if existing:
        active_dir = existing.get("index_dir_path")
        if active_dir and os.path.exists(active_dir):
            # Only remove files in the active directory, not subdirectories
            # (which are session snapshots). This preserves past chat sessions.
            for filename in ["embeddings.npy", "faiss_index.index", "chunks.json"]:
                filepath = os.path.join(active_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)


# =============================================================================
# DATABASE — RAG CHAT HISTORY
# =============================================================================

def save_rag_chat_turn(
    chat_session_id: str,
    user_id: int,
    role: str,
    message_text: str,
    model_name: Optional[str] = None,
    language: Optional[str] = None,
) -> None:
    """
    Persist one conversation turn to rag_query_history.

    role must be 'user' or 'assistant'. model_name and language are only
    meaningful for assistant turns — pass None for user turns and they will
    be stored as NULL, matching the pattern used by advisor_chat_history
    and wellness_chat_history.
    """
    model_provider = MODEL_PROVIDERS.get(model_name) if model_name else None

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO rag_query_history (
                chat_session_id, user_id, role,
                message_text, model_provider, model_name, language
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            chat_session_id, user_id, role,
            message_text, model_provider, model_name, language,
        ))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_rag_chat_sessions(user_id: int) -> List[Dict]:
    """
    Return one summary row per distinct chat session for the user, ordered
    by most recent activity descending.

    Each row contains:
      chat_session_id — the session UUID
      first_message   — the first user turn text (used as the session title)
      turn_count      — total number of turns in the session
      last_active     — timestamp of the most recent turn
      model_name      — model used in the most recent assistant turn
      language        — language of the most recent assistant turn
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                h.chat_session_id,
                first_msg.message_text  AS first_message,
                COUNT(*)                AS turn_count,
                MAX(h.created_at)       AS last_active,
                last_asst.model_name    AS model_name,
                last_asst.language      AS language
            FROM rag_query_history h

            -- Subquery: first user turn per session (session title)
            JOIN (
                SELECT chat_session_id, message_text
                FROM rag_query_history
                WHERE role = 'user'
                  AND user_id = %s
                  AND id = (
                      SELECT MIN(id)
                      FROM rag_query_history r2
                      WHERE r2.chat_session_id = rag_query_history.chat_session_id
                        AND r2.role = 'user'
                  )
            ) first_msg ON first_msg.chat_session_id = h.chat_session_id

            -- Subquery: most recent assistant turn per session (model/language)
            LEFT JOIN (
                SELECT chat_session_id, model_name, language
                FROM rag_query_history
                WHERE role = 'assistant'
                  AND user_id = %s
                  AND id = (
                      SELECT MAX(id)
                      FROM rag_query_history r3
                      WHERE r3.chat_session_id = rag_query_history.chat_session_id
                        AND r3.role = 'assistant'
                  )
            ) last_asst ON last_asst.chat_session_id = h.chat_session_id

            WHERE h.user_id = %s
            GROUP BY h.chat_session_id, first_msg.message_text,
                     last_asst.model_name, last_asst.language
            ORDER BY last_active DESC
        """, (user_id, user_id, user_id))
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def get_rag_chat_session_turns(chat_session_id: str, user_id: int) -> List[Dict]:
    """
    Return all turns for a specific chat session in chronological order.
    Used both for the History tab display and for seeding session state
    when a past conversation is loaded.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, role, message_text, model_name, language, created_at
            FROM rag_query_history
            WHERE chat_session_id = %s
              AND user_id = %s
            ORDER BY created_at ASC, id ASC
        """, (chat_session_id, user_id))
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def delete_rag_chat_session(chat_session_id: str, user_id: int) -> None:
    """
    Delete all DB rows for a chat session and remove its FAISS snapshot
    directory from disk.

    If the session being deleted is currently loaded as the active index
    (rag_indexes.active_chat_session_id matches), the active index row is
    also cleared so the user is not left with a reference to a deleted index.
    In that case the caller is responsible for also clearing FAISS session
    state so the UI shows the no-index state correctly.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM rag_query_history
            WHERE chat_session_id = %s AND user_id = %s
        """, (chat_session_id, user_id))

        # If this session is currently the active index, clear that reference.
        cursor.execute("""
            UPDATE rag_indexes
            SET active_chat_session_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
              AND active_chat_session_id = %s
        """, (user_id, chat_session_id))

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    # Remove the session snapshot directory from disk.
    snapshot_dir = Path("data") / "rag" / str(user_id) / chat_session_id
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir, ignore_errors=True)


@st.dialog("Delete Document Batch")
def _dialog_delete_rag_ingestion(ingestion_id: str, index_dir: str, label: str, user_id: int) -> None:
    """
    Confirmation modal for permanently deleting a RAG document ingestion batch.

    Removes the batch's FAISS directory from disk and its record from the
    ingestion metadata file. If this batch is currently loaded as the active
    index, the active index state and in-memory FAISS resources are also
    cleared so the UI returns to the no-index state correctly.
    """
    st.warning(
        f"Are you sure you want to delete **{label}**? "
        "The document index for this batch will be permanently removed. "
        "This cannot be undone."
    )
    col1, col2 = st.columns(2)
    if col1.button("Delete", type="primary", key="rag_ingest_dialog_confirm_delete"):
        rag_index = get_user_rag_index(user_id)
        if rag_index and rag_index.get("index_dir_path") == index_dir:
            delete_user_rag_index(user_id)
            _clear_rag_chat_session()
            _clear_faiss_resources()
        remove_ingestion_from_metadata(user_id, ingestion_id)
        st.toast(f"Deleted: {label}")
        st.rerun()
    if col2.button("Cancel", key="rag_ingest_dialog_cancel_delete"):
        st.rerun()


@st.dialog("Delete Chat Session")
def _dialog_delete_rag_session(session_id: str, user_id: int) -> None:
    """
    Confirmation modal for permanently deleting a RAG chat session.

    If the session being deleted is currently active, the in-memory chat
    state and FAISS resources are also cleared so the UI returns to the
    no-session state correctly.
    """
    st.warning("Are you sure you want to delete this chat session? This cannot be undone.")
    col1, col2 = st.columns(2)
    if col1.button("Delete", type="primary", key="rag_dialog_confirm_delete"):
        if st.session_state.get("rag_current_session_id") == session_id:
            _clear_rag_chat_session()
            _clear_faiss_resources()
        delete_rag_chat_session(session_id, user_id)
        st.toast("Chat session deleted.")
        st.rerun()
    if col2.button("Cancel", key="rag_dialog_cancel_delete"):
        st.rerun()


# =============================================================================
# FAISS SESSION SNAPSHOT — FILE OPERATIONS
# =============================================================================

def _get_active_index_paths(user_id: int):
    """
    Return the file paths for the user's currently active FAISS index directory
    by reading rag_indexes.index_dir_path from the DB.

    Since each indexing run now writes to its own unique per-batch directory,
    the active directory is not a fixed path but whatever the DB row currently
    points at. Returns None if the user has no active index.
    """
    rag_index = get_user_rag_index(user_id)
    if not rag_index:
        return None
    index_dir = rag_index["index_dir_path"]
    return {
        "index_dir":       index_dir,
        "embeddings_path": os.path.join(index_dir, "embeddings.npy"),
        "index_path":      os.path.join(index_dir, "faiss_index.index"),
        "chunks_path":     os.path.join(index_dir, "chunks.json"),
    }


def snapshot_index_for_session(user_id: int, chat_session_id: str) -> bool:
    """
    Copy the user's current active FAISS index files into a session-specific
    snapshot directory at data/rag/{user_id}/{chat_session_id}/.

    This snapshot permanently links the chat session to the document batch that
    was active when the conversation started, so the session can be loaded and
    continued even after the user switches to a different batch.

    A metadata.json file is also written to the snapshot directory containing
    the filenames, document count, and chunk count from the active index at
    snapshot time. This allows restore_index_from_session() to display the
    correct document names in the Index Documents tab after loading.

    Called exactly once per chat session, on the first user message.
    Returns True on success, False if the source files are missing.
    The operation is idempotent — if the destination directory already exists
    the function returns True without copying again.
    """
    snapshot_dir = Path("data") / "rag" / str(user_id) / chat_session_id

    if snapshot_dir.exists():
        return True

    # Read the active index directory from the DB rather than a fixed path,
    # since each batch now has its own unique directory.
    paths = _get_active_index_paths(user_id)
    if not paths:
        return False

    source_files = [
        paths["embeddings_path"],
        paths["index_path"],
        paths["chunks_path"],
    ]

    if not all(os.path.exists(f) for f in source_files):
        return False

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for src in source_files:
        shutil.copy2(src, snapshot_dir / Path(src).name)

    # Save the current index metadata alongside the FAISS files so the
    # correct filenames and counts can be restored when this session is loaded.
    current = get_user_rag_index(user_id)
    if current:
        metadata = {
            "filenames":      current.get("indexed_filenames", []),
            "document_count": current.get("document_count", 0),
            "chunk_count":    current.get("chunk_count", 0),
        }
        with open(snapshot_dir / "metadata.json", "w") as f:
            json.dump(metadata, f)

    return True
def restore_index_from_session(user_id: int, chat_session_id: str) -> bool:
    """
    Restore a past chat session as the active index by updating the DB to
    point at the session's snapshot directory.

    Rather than copying files back to the active directory, this function
    updates rag_indexes.index_dir_path to point directly at the snapshot
    directory. The existing last_loaded_index_dir guard in the query tab
    detects the path change on the next render and reloads FAISS resources
    from the snapshot automatically — no file I/O beyond the DB update.

    The snapshot's metadata.json is read to restore the correct filenames,
    document count, and chunk count for the session's original document set.
    This ensures the Index Documents tab shows the documents that belong to
    the loaded session rather than the most recently indexed documents.

    Returns True on success, False if the snapshot directory does not exist
    on disk (e.g. the server files were cleaned up manually).
    """
    snapshot_dir = Path("data") / "rag" / str(user_id) / chat_session_id

    if not snapshot_dir.exists():
        return False

    # Read the session's saved metadata to restore the correct filenames and
    # counts. Fall back to the current index values if metadata is missing
    # (e.g. sessions created before this feature was added).
    metadata_path = snapshot_dir / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)
        filenames   = metadata.get("filenames", [])
        doc_count   = metadata.get("document_count", 0)
        chunk_count = metadata.get("chunk_count", 0)
    else:
        current     = get_user_rag_index(user_id)
        filenames   = current["indexed_filenames"] if current else []
        doc_count   = current["document_count"]    if current else 0
        chunk_count = current["chunk_count"]       if current else 0

    upsert_user_rag_index(
        user_id=user_id,
        index_dir_path=str(snapshot_dir),
        filenames=filenames,
        document_count=doc_count,
        chunk_count=chunk_count,
        active_chat_session_id=chat_session_id,
    )
    return True


# =============================================================================
# DOCUMENT INDEXING
# =============================================================================

def index_documents(files=None, data_dir=None):
    """
    Build a user-scoped RAG index from uploaded files or an existing directory.

    Each indexing run writes its FAISS files to a unique directory at
    data/rag/{user_id}/{ingestion_id}/ so every batch is independently
    preserved on disk. The rag_indexes DB row is updated to point at the
    new batch directory, making it the active index immediately. An ingestion
    metadata record is appended so the batch appears in the Document Management
    table and can be selected via the Use button.

    Args:
        files:    Streamlit UploadedFile list from st.file_uploader.
        data_dir: Server-side directory path for bulk indexing without browser upload.
    """
    user_id = get_current_user_id()
    if not user_id:
        return {"status": "error", "message": "No logged-in user found."}

    documents = []
    filenames  = []

    if files:
        try:
            extracted_texts = process_uploaded_files(files)
            if not validate_extracted_content(extracted_texts):
                return {
                    "status": "error",
                    "message": "Insufficient content extracted from files.",
                }
            for filename, text in extracted_texts:
                documents.append({"filename": filename, "content": text})
                filenames.append(filename)
        except Exception as e:
            return {"status": "error", "message": f"Error processing files: {str(e)}"}

    elif data_dir:
        documents = load_pdf_documents(data_dir)
        filenames  = [doc["filename"] for doc in documents]

    if not documents:
        return {"status": "error", "message": "No documents found to index."}

    chunks     = chunk_documents(documents)
    embeddings = create_embeddings(chunks)
    index      = build_faiss_index(embeddings)

    # Write FAISS files to a unique per-batch directory so each indexing run
    # is independently stored and can be loaded as a distinct active index.
    ingestion_id = str(uuid.uuid4())
    save_dir     = os.path.join("data", "rag", str(user_id), ingestion_id)
    os.makedirs(save_dir, exist_ok=True)

    save_index_and_chunks(embeddings, index, chunks, save_dir)

    # Update the DB to point at this batch's directory as the active index.
    upsert_user_rag_index(
        user_id=user_id,
        index_dir_path=save_dir,
        filenames=filenames,
        document_count=len(documents),
        chunk_count=len(chunks),
        active_chat_session_id=None,
    )

    # Record this batch in the per-user ingestion metadata so it appears in
    # the Document Management table with its own Use and delete controls.
    add_ingestion_to_metadata(
        user_id=user_id,
        ingestion_id=ingestion_id,
        filenames=filenames,
        index_dir=save_dir,
    )

    return {
        "status":         "success",
        "message":        (
            f"Successfully indexed {len(documents)} document(s) "
            f"with {len(chunks)} chunks."
        ),
        "document_count": len(documents),
        "chunk_count":    len(chunks),
        "filenames":      filenames,
    }


# =============================================================================
# MAIN UI
# =============================================================================

def rag_ui():
    """
    Top-level entry point for the RAG System feature tab.

    Renders three tabs:
      📚 Index Documents — upload and index documents; manage the active index.
      🔍 Query Documents — multi-turn chat interface grounded in indexed documents.
      🕘 History         — browse, load, and delete past chat sessions.
    """
    st.subheader("RAG System with Multiple LLM Providers")
    _init_rag_session_state()

    tab1, tab2, tab3 = st.tabs([
        "📚 Index Documents",
        "🔍 Query Documents",
        "🕘 History",
    ])

    with tab1:
        _render_index_tab()

    with tab2:
        _render_chat_tab()

    with tab3:
        _render_history_tab()


# =============================================================================
# TAB 1 — INDEX DOCUMENTS
# =============================================================================

def _render_index_tab():
    """
    Index Documents tab.

    Displays the per-user ingestion history as a table of previously ingested
    document batches — one row per indexing run with the filenames, ingestion
    date, and Use / 🗑️ action buttons.

    Use is a true document switcher: clicking it loads that batch's own FAISS
    index directory as the active index. If a chat session is currently in
    progress, its turns are already persisted to the DB turn-by-turn, so
    clearing in-memory state loses nothing — the session appears in History.
    A fresh chat is then started against the selected batch.

    Each indexing run writes its FAISS files to a unique directory so all
    batches remain available on disk indefinitely until explicitly deleted.
    Deleting a batch removes its metadata record and its FAISS directory.

    The 'Use existing documents in data directory' option is available to all
    users and reads from the shared server-side data/ directory, matching the
    original UReap behaviour. The resulting index is written to a unique
    per-batch directory under data/rag/{user_id}/, keeping output per-user.
    """
    st.write("Upload PDF documents to be indexed or use existing documents")

    user_id = get_current_user_id()

    # ── Document Management ──────────────────────────────────────────────────
    st.subheader("Document Management")

    ingested_docs = get_ingested_documents(user_id) if user_id else []

    if ingested_docs:
        st.write("Previously ingested documents:")

        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.write("**Document Name**")
        with col2:
            st.write("**Ingestion Date**")
        with col3:
            st.write("**Actions**")

        for doc in ingested_docs:
            ingestion_id  = doc["id"]
            label         = doc.get("label", ingestion_id)
            index_dir     = doc.get("index_dir", "")
            filenames     = doc.get("filenames", [])
            timestamp_raw = doc.get("timestamp", "")

            # Format the ISO timestamp to a readable date string.
            try:
                ts = datetime.datetime.fromisoformat(timestamp_raw)
                timestamp_display = ts.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                timestamp_display = "Unknown date"

            col1, col2, col3 = st.columns([3, 2, 1])

            with col1:
                st.write(label)

            with col2:
                st.write(timestamp_display)

            with col3:
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("Use", key=f"rag_use_{ingestion_id}"):
                        # True document switcher: load this batch's FAISS
                        # directory as the active index. Clear any in-progress
                        # chat (already persisted turn-by-turn to DB) so a
                        # fresh session starts against the selected batch.
                        # Safety: only proceed if index_dir is a non-empty,
                        # valid path within the user's rag data directory.
                        if not index_dir:
                            st.error("This batch has no index directory recorded. Please re-index the documents.")
                        else:
                            batch_dir = Path(index_dir)
                            if not batch_dir.exists():
                                st.error(
                                    "The index files for this batch are no longer "
                                    "available on disk. Please re-index the documents."
                                )
                            else:
                                # Read the chunk count directly from the batch's
                                # chunks.json file rather than relying on any stored
                                # metadata value. The chunks.json file is the
                                # authoritative record written at indexing time, so
                                # its length always reflects the true number of chunks
                                # for this batch regardless of how the batch was
                                # selected. Falls back to 0 if the file cannot be
                                # read, which will surface as a missing-file error
                                # when the chat tab next attempts to load resources.
                                chunks_path = batch_dir / "chunks.json"
                                try:
                                    with open(chunks_path) as f:
                                        actual_chunk_count = len(json.load(f))
                                except (OSError, json.JSONDecodeError):
                                    actual_chunk_count = 0

                                _clear_rag_chat_session()
                                _clear_faiss_resources()
                                upsert_user_rag_index(
                                    user_id=user_id,
                                    index_dir_path=index_dir,
                                    filenames=filenames,
                                    document_count=len(filenames),
                                    chunk_count=actual_chunk_count,
                                    active_chat_session_id=None,
                                )
                                st.success(f"Now using: {label}")
                                st.rerun()
                with btn_col2:
                    if st.button("🗑️", key=f"rag_del_{ingestion_id}"):
                        _dialog_delete_rag_ingestion(ingestion_id, index_dir, label, user_id)
    else:
        st.info("No documents have been ingested yet.")

    st.divider()

    # ── Upload and index ─────────────────────────────────────────────────────
    st.subheader("Upload New Documents")
    uploaded_files = st.file_uploader(
        "Upload documents (PDF, DOCX, PPTX, TXT)",
        type=["pdf", "docx", "pptx", "txt"],
        accept_multiple_files=True,
        help="You can upload multiple files in different formats. All content will be analyzed together.",
    )

    # The data directory option allows any user to index files placed in the
    # shared data/ directory on the server without a browser upload, matching
    # the original UReap behaviour. The resulting index is written to a unique
    # per-batch directory under data/rag/{user_id}/, keeping output per-user.
    use_existing = st.checkbox(
        "Use existing documents in data directory",
        help="Index files already present in the server-side data/ directory.",
    )

    if st.button("Index Documents", key="rag_index_documents"):
        if not uploaded_files and not use_existing:
            st.error("Please upload at least one document before indexing.")
        else:
            with st.spinner("Indexing documents..."):
                result = index_documents(
                    files=uploaded_files if uploaded_files else None,
                    data_dir="data" if use_existing else None,
                )

            if result["status"] == "success":
                # Clear the active chat session and FAISS resources — the new
                # batch is a fresh start. Past chat sessions in the History tab
                # are unaffected; their snapshot directories remain on disk.
                _clear_rag_chat_session()
                _clear_faiss_resources()
                st.success(result["message"])
                st.rerun()
            else:
                st.error(result["message"])


# =============================================================================
# TAB 2 — CHAT
# =============================================================================

def _render_chat_tab():
    """
    Chat tab — multi-turn conversation grounded in the user's indexed documents.

    Each user message triggers a FAISS similarity search to retrieve the most
    relevant document chunks, which are injected into the LLM prompt as context.
    The last RAG_CHAT_CONTEXT_TURNS turns of conversation history are also
    included so the model can handle follow-up questions and references to
    prior answers.

    On the first message of a new session, the active FAISS index files are
    snapshot to a session-specific directory so this conversation can always
    be restored from history, even if the user re-indexes later.

    All turns are saved to rag_query_history individually as they happen.
    """
    user_id   = get_current_user_id()
    rag_index = get_user_rag_index(user_id) if user_id else None

    if not rag_index:
        st.warning("No indexed documents found. Please index documents in the Index Documents tab first.")
        return

    index_dir = rag_index["index_dir_path"]
    faiss_files = {
        "embeddings_path": os.path.join(index_dir, "embeddings.npy"),
        "index_path":      os.path.join(index_dir, "faiss_index.index"),
        "chunks_path":     os.path.join(index_dir, "chunks.json"),
    }

    missing = [p for p in faiss_files.values() if not os.path.exists(p)]
    if missing:
        st.error(
            "The index files for your current document set are missing on disk. "
            "Please re-index your documents in the Index Documents tab."
        )
        return

    # ── Load FAISS resources into session state if the index has changed ─────
    if (
        "embeddings" not in st.session_state
        or "index" not in st.session_state
        or "chunks" not in st.session_state
        or st.session_state.get("last_loaded_index_dir") != index_dir
    ):
        with st.spinner("Loading index resources..."):
            (
                st.session_state.embeddings,
                st.session_state.index,
                st.session_state.chunks,
                st.session_state.embedding_model,
            ) = load_resources(
                faiss_files["embeddings_path"],
                faiss_files["index_path"],
                faiss_files["chunks_path"],
            )
            st.session_state.last_loaded_index_dir = index_dir

    # ── Model and language selectors ─────────────────────────────────────────
    model_display_names = list(MODELS.keys())

    # Resolve the saved preference written by _load_model_preferences() at
    # login. Using a separate widget key (rag_model_selectbox) prevents
    # Streamlit's widget state manager from overwriting rag_selected_model on
    # first render, which is the root cause of the preference being ignored.
    # This is the same pattern used by quiz_generator_feature.py.
    saved_model = st.session_state.get("rag_selected_model", model_display_names[0])
    if saved_model not in model_display_names:
        saved_model = model_display_names[0]

    col_model, col_lang = st.columns(2)
    with col_model:
        selected_model_key = st.selectbox(
            "Model",
            model_display_names,
            index=model_display_names.index(saved_model),
            key="rag_model_selectbox",
        )
        # Write the selection back to the canonical session state key so that
        # the value persists across reruns and is available to _handle_chat_message.
        st.session_state["rag_selected_model"] = selected_model_key
    with col_lang:
        selected_language = st.selectbox(
            "Response language",
            RAG_LANGUAGES,
            key="rag_selected_language",
        )

    selected_model = MODELS[selected_model_key]

    # ── API key warnings ──────────────────────────────────────────────────────
    provider = MODEL_PROVIDERS.get(selected_model, "")
    if provider == "groq" and not st.session_state.get("groq_api_key"):
        st.warning("⚠️ Groq API key is required. Please add your API key in your profile settings.")
    if provider == "gemini" and not st.session_state.get("gemini_api_key"):
        st.warning("⚠️ Gemini API key is required. Please add your API key in your profile settings.")
    if provider == "openai" and not st.session_state.get("openai_api_key"):
        st.warning("⚠️ OpenAI API key is required. Please add your API key in your profile settings.")
    if provider == "github" and not st.session_state.get("github_token"):
        st.warning("⚠️ GitHub token is required. Please add your GitHub token in your profile settings.")

    # Show which documents are currently loaded in the active index.
    filenames = rag_index.get("indexed_filenames", [])
    doc_label = ", ".join(filenames) if filenames else "unknown documents"
    st.caption(
        f"📄 Chatting about: {doc_label}  ·  "
        f"{rag_index.get('document_count', 0)} document(s)  ·  "
        f"{rag_index.get('chunk_count', 0)} chunks indexed"
    )

    st.divider()

    # ── Render completed conversation turns ───────────────────────────────────
    # Turns are rendered sequentially above the chat input. As the conversation
    # grows the page scrolls naturally. Streamlit's tab layout does not support
    # true bottom-anchoring of the input, so the simplest reliable approach is
    # to render history first and let the input follow below it.
    for turn in st.session_state.rag_chat_history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    # ── Chat input ────────────────────────────────────────────────────────────
    query_text = st.chat_input("Ask a question about your documents...")

    if query_text and query_text.strip():
        _handle_chat_message(
            query_text=query_text.strip(),
            user_id=user_id,
            selected_model=selected_model,
            selected_model_key=selected_model_key,
            selected_language=selected_language,
            indexed_filenames=filenames,
        )


def _handle_chat_message(
    query_text: str,
    user_id: int,
    selected_model: str,
    selected_model_key: str,
    selected_language: str,
    indexed_filenames: List[str],
) -> None:
    """
    Process one user message in the RAG chat.

    On the first message of a new session:
      1. Generate a chat_session_id UUID.
      2. Snapshot the active FAISS index to the session directory.
      3. Save to session state and proceed.

    For every message:
      1. Save the user turn to the DB.
      2. Retrieve relevant document chunks via FAISS similarity search.
      3. Build the messages list (system context + last N turns + user message).
      4. Collect the full LLM response under a "Thinking..." spinner.
      5. Save the assistant turn to the DB.
      6. Rerun so both turns render cleanly inside the chat history container.

    The system message explicitly names the indexed source documents so all
    models understand that references to "the file", "the document", or "the
    text" refer to the user's uploaded content rather than something unrelated.
    """
    # ── Session initialisation on first message ───────────────────────────────
    if st.session_state["rag_current_session_id"] is None:
        session_id = str(uuid.uuid4())

        if not snapshot_index_for_session(user_id, session_id):
            st.error(
                "Could not create a snapshot of your current index. "
                "Please ensure your documents are indexed and try again."
            )
            return

        st.session_state["rag_current_session_id"] = session_id
    else:
        session_id = st.session_state["rag_current_session_id"]

    # ── Append and persist the user turn ─────────────────────────────────────
    st.session_state.rag_chat_history.append(
        {"role": "user", "content": query_text}
    )
    save_rag_chat_turn(
        chat_session_id=session_id,
        user_id=user_id,
        role="user",
        message_text=query_text,
    )

    # ── Retrieve context, build prompt, and collect response ──────────────────
    # All three steps run inside a single "Thinking..." spinner that names the
    # active model, matching the advisor AI feature's UX pattern. The full
    # response is collected before being appended to history so the rerun
    # renders both turns cleanly inside the scrollable chat history container.
    with st.spinner(f"Thinking... (using {selected_model_key})"):
        # FAISS similarity search for relevant document chunks.
        context_chunks = get_relevant_context(
            query_text,
            st.session_state.index,
            st.session_state.chunks,
            st.session_state.embedding_model,
        )

        formatted_context = "\n\n".join(
            f"Chunk:\n{chunk['chunk']}" for chunk in context_chunks
        )

        language_instruction = (
            f"\n- Respond in {selected_language} language."
            if selected_language != "English"
            else ""
        )

        # Build the system message — mirrors create_augmented_prompt_with_language()
        # from rag_utils.py, adapted for the chat messages format. Document
        # filenames are listed so the model correctly resolves references to
        # "the file" or "the document".
        doc_list = ", ".join(indexed_filenames) if indexed_filenames else "the uploaded documents"

        system_message = {
            "role": "system",
            "content": (
                f"You are an expert RAG assistant trained to answer questions based "
                f"**exclusively** on the provided context from chunks after similarity search. "
                f"The context below is extracted from the user's uploaded document(s): {doc_list}. "
                f"When the user refers to 'the file', 'the document', or 'the text', they mean "
                f"this uploaded content.\n\n"
                f"Context:\n{formatted_context}\n\n"
                f"**Instructions:**\n"
                f"- Answer using only the context above.\n"
                f"- If the context is insufficient, respond "
                f"\"I don't have enough information.\"\n"
                f"- Keep answers concise and avoid speculation."
                f"{language_instruction}"
            ),
        }

        # Build the messages list — system message first, then the last
        # RAG_CHAT_CONTEXT_TURNS turns. The current user message is already
        # appended to rag_chat_history above, so it is included naturally.
        history_window = st.session_state.rag_chat_history[-RAG_CHAT_CONTEXT_TURNS:]
        messages = [system_message] + [
            {"role": turn["role"], "content": turn["content"]}
            for turn in history_window
        ]

        # Collect the full streamed response before updating state so the rerun
        # renders a complete, properly formatted assistant message.
        full_response = ""
        try:
            for chunk in stream_llm_chat(messages, selected_model):
                full_response += chunk
        except Exception as e:
            full_response = f"Error generating response: {str(e)}"

    # ── Persist the assistant turn and trigger rerun ──────────────────────────
    st.session_state.rag_chat_history.append(
        {"role": "assistant", "content": full_response}
    )
    save_rag_chat_turn(
        chat_session_id=session_id,
        user_id=user_id,
        role="assistant",
        message_text=full_response,
        model_name=selected_model,
        language=selected_language,
    )

    st.rerun()


# =============================================================================
# TAB 3 — HISTORY
# =============================================================================

def _render_history_tab():
    """
    History tab — browse, load, and delete past RAG chat sessions.

    Each session is displayed as an expandable card showing the first user
    message as the title, the number of turns, and the date. Expanding a
    session shows the full conversation transcript as a read-only chat view.

    Load and Continue: restores the session's FAISS snapshot as the active
    index and seeds the chat session state, so the user can continue the
    conversation from where it left off.

    Delete: permanently removes all DB rows and the FAISS snapshot directory
    for that session.
    """
    user_id  = get_current_user_id()
    sessions = get_rag_chat_sessions(user_id) if user_id else []

    if not sessions:
        st.info("No chat sessions found yet. Start a conversation in the Query Documents tab.")
        return

    for session in sessions:
        session_id     = session["chat_session_id"]
        first_message  = session.get("first_message", "") or ""
        last_active    = session.get("last_active", "")
        model_name     = session.get("model_name", "")

        # Read the session's document metadata to include in the card title.
        # metadata.json is written into the snapshot directory at session start
        # time alongside the FAISS files.
        snapshot_dir  = Path("data") / "rag" / str(user_id) / session_id
        session_files = []
        metadata_path = snapshot_dir / "metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    meta = json.load(f)
                session_files = meta.get("filenames", [])
            except (json.JSONDecodeError, OSError):
                session_files = []

        # Build the card title: date · documents · first message.
        # Turn count is omitted. Documents fall back to "unknown" if the
        # snapshot metadata is missing.
        doc_label = ", ".join(session_files) if session_files else "unknown documents"
        title_text = (
            first_message[:80] + "..."
            if len(first_message) > 80
            else first_message
        )
        card_title = f"{last_active} · {doc_label} · {title_text}"

        with st.expander(card_title, expanded=False):

            # ── Read-only transcript ──────────────────────────────────────────
            turns = get_rag_chat_session_turns(session_id, user_id)
            for turn in turns:
                with st.chat_message(turn["role"]):
                    st.markdown(turn["message_text"])
                    if turn["role"] == "assistant" and turn.get("model_name"):
                        doc_label = ", ".join(session_files) if session_files else "unknown"
                        st.caption(
                            f"Model: {turn['model_name']}  ·  "
                            f"Language: {turn.get('language', 'English')}  ·  "
                            f"Documents: {doc_label}"
                        )

            st.divider()

            col_load, col_delete, _ = st.columns([2, 2, 5])

            # ── Load and Continue ─────────────────────────────────────────────
            with col_load:
                if st.button("Load and Continue", key=f"load_session_{session_id}"):
                    # If a different session is currently active in memory,
                    # clear it first. The DB already has the complete record
                    # so no data is lost — only session state is cleared.
                    current_session = st.session_state.get("rag_current_session_id")
                    if current_session and current_session != session_id:
                        _clear_rag_chat_session()

                    # Restore the session's FAISS snapshot as the active index.
                    restored = restore_index_from_session(user_id, session_id)

                    if not restored:
                        st.error(
                            "The index files for this session are no longer available "
                            "on disk. The conversation is shown above for reference, "
                            "but it cannot be continued. You may re-index your documents "
                            "to start a new conversation."
                        )
                    else:
                        # Seed session state with the loaded conversation.
                        st.session_state["rag_chat_history"] = [
                            {"role": t["role"], "content": t["message_text"]}
                            for t in turns
                        ]
                        st.session_state["rag_current_session_id"] = session_id

                        # Clear FAISS resources so they reload from the snapshot
                        # directory on next render.
                        _clear_faiss_resources()

                        st.success("Session loaded. Switch to the Query Documents tab to continue.")
                        st.rerun()

            # ── Delete Session ────────────────────────────────────────────────
            with col_delete:
                if st.button("Delete", key=f"delete_session_{session_id}", type="primary"):
                    _dialog_delete_rag_session(session_id, user_id)
