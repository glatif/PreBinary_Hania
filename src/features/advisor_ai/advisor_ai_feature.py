# =============================================================================
# advisor_ai_feature.py — Advisor AI Feature
# =============================================================================
# Provides the full Advisor AI UI and all supporting database operations.
#
# Feature overview:
#   The Advisor AI answers student questions about TRU Computing Science faculty,
#   courses, and curriculum. It scrapes and indexes data from the TRU website
#   into a per-user FAISS index stored on disk, then uses RAG to augment LLM
#   responses with retrieved context. Multi-turn conversation history is
#   maintained in session state and persisted to the database.
#
# Database integration:
#   - Each conversation turn (user message + assistant reply) is saved to
#     advisor_chat_history, grouped by a chat_session_id UUID.
#   - The History tab queries all sessions for the current user and allows
#     them to load a past session and continue it, or delete it permanently.
#
# FAISS storage:
#   The FAISS index, embeddings, and chunks are stored under:
#     src/features/advisor_ai/data/
#   This is a single shared index for the feature (not per-user), updated
#   whenever an admin or teacher triggers a website re-scrape.
#
# Session state keys used by this feature:
#   advisor_websites           — list of {label, url} dicts for data sources
#   advisor_chunks             — dict of {label: [chunk, ...]} scraped content
#   advisor_chat_history       — list of {role, content} message dicts
#   advisor_current_session_id — UUID string for the active chat session
#   advisor_selected_model     — display name of the currently selected model
# =============================================================================

import streamlit as st
import os
import faiss
import numpy as np
import json
from typing import List, Dict, Any, Optional, Tuple

# Standard library and third-party imports
import uuid
import pandas as pd
from sqlalchemy import text

# Database connection
from db import get_connection, get_engine

# LLM interface — stream_llm_chat is used for multi-turn conversation,
# stream_llm for single-turn. MODELS and MODEL_PROVIDERS drive the model
# selector and provider dispatch.
from src.utils.llm_utils import stream_llm, stream_llm_chat, MODELS, MODEL_PROVIDERS

# Embedding model wrapper used to encode query text for FAISS similarity search.
from src.utils.embedding_wrapper import get_embedding_model, DEFAULT_MODEL_NAME

# Advisor-specific scraping and data preparation utilities.
from src.features.advisor_ai.advisor_utils import (
    scrape_professors,
    scrape_courses,
    scrape_generic,
    sanitize_filename,
    get_default_websites,
    prepare_chunks_for_indexing,
    is_valid_url,
    label_from_url,
    parse_urls_from_text,
)

# Local FAISS/embedding storage and the system message builder for multi-turn chat.
from src.features.advisor_ai.storage import (
    load_resources,
    save_index_and_chunks,
    get_relevant_context,
    create_advisor_system_message,
    chunk_text_dynamic,
    save_chunks_to_file,
)

# =============================================================================
# CONSTANTS
# =============================================================================

# Paths to the shared FAISS index stored on disk under the advisor_ai feature
# data directory. These files are written by save_index_and_chunks() and read
# by load_resources() when the feature initialises.
ADVISOR_DATA_DIR        = os.path.join('src', 'features', 'advisor_ai', 'data')
ADVISOR_INDEX_PATH      = os.path.join(ADVISOR_DATA_DIR, 'faiss_index.index')
ADVISOR_EMBEDDINGS_PATH = os.path.join(ADVISOR_DATA_DIR, 'embeddings.npy')
ADVISOR_CHUNKS_PATH     = os.path.join(ADVISOR_DATA_DIR, 'chunks.json')

# Registry of configured data source websites ({label, url} dicts), persisted
# separately from the scraped chunks/index so the admin's list of sources
# survives app reloads and new sessions instead of resetting to the two
# built-in defaults every time st.session_state is recreated.
ADVISOR_WEBSITES_PATH   = os.path.join(ADVISOR_DATA_DIR, 'websites.json')

# Embedding model used to encode both documents and query text. Must match the
# model used when the index was built; changing it requires re-indexing.
EMBEDDING_MODEL = DEFAULT_MODEL_NAME

# Number of prior conversation turns passed to the LLM as context on each
# query. Each turn is one user message plus one assistant reply. Keeping this
# bounded prevents the context window from growing unbounded across long sessions.
ADVISOR_CHAT_CONTEXT_TURNS = 10


# =============================================================================
# SESSION STATE HELPERS
# =============================================================================

def initialize_session_state():
    """
    Initialise all session state keys used by the Advisor AI feature.

    Called once at the start of advisor_ai_ui() before any UI is rendered.
    Guards on 'not in st.session_state' ensure re-runs do not reset live state.

    Keys initialised:
        advisor_websites           — list of {label, url} dicts scraped as data sources.
        advisor_chunks             — dict mapping website label to list of text chunks.
        advisor_chat_history       — list of {role, content} message dicts for the
                                     active chat session (displayed in the chat UI).
        advisor_current_session_id — UUID string for the active DB-persisted session,
                                     or None when no session is loaded.
        advisor_resources_loaded   — True once the FAISS index has been loaded from disk.
        advisor_selected_model     — display name of the currently selected LLM.
    """
    if "advisor_websites" not in st.session_state:
        st.session_state.advisor_websites = load_advisor_websites()
    if "advisor_chunks" not in st.session_state:
        st.session_state.advisor_chunks = {}
    if "advisor_chat_history" not in st.session_state:
        st.session_state.advisor_chat_history = []
    if "advisor_current_session_id" not in st.session_state:
        st.session_state.advisor_current_session_id = None
    if "advisor_resources_loaded" not in st.session_state:
        st.session_state.advisor_resources_loaded = False
    if "advisor_selected_model" not in st.session_state:
        st.session_state.advisor_selected_model = list(MODELS.keys())[0]

def get_current_user_id() -> Optional[int]:
    """Return the logged-in user ID from session state, if available."""
    return st.session_state.get("user", {}).get("id")


def load_advisor_websites() -> List[Dict[str, str]]:
    """
    Load the persisted list of Advisor AI data source websites from disk.

    Falls back to the two built-in TRU defaults if no websites.json file
    exists yet (first run) or it can't be read. Any admin-added websites are
    written to this file via save_advisor_websites() so they survive app
    restarts and new browser sessions instead of resetting every reload.
    """
    if os.path.exists(ADVISOR_WEBSITES_PATH):
        try:
            with open(ADVISOR_WEBSITES_PATH, 'r', encoding='utf-8') as f:
                websites = json.load(f)
            if isinstance(websites, list) and websites:
                return websites
        except Exception:
            pass
    return get_default_websites()


def save_advisor_websites(websites: List[Dict[str, str]]) -> None:
    """Persist the current list of Advisor AI data source websites to disk."""
    os.makedirs(ADVISOR_DATA_DIR, exist_ok=True)
    with open(ADVISOR_WEBSITES_PATH, 'w', encoding='utf-8') as f:
        json.dump(websites, f, indent=2)


def _scrape_site(url: str) -> List[str]:
    """
    Scrape a single data source URL into a list of text chunks.

    Uses the structured TRU faculty/course scrapers when the URL matches
    their known page layout, and falls back to generic text extraction
    (scrape_generic) for any other admin-added URL, so arbitrary websites
    can be used as data sources, not just the two default TRU pages.
    """
    try:
        if "people.html" in url:
            chunks = scrape_professors(url)
            if chunks:
                return chunks
        elif any(kw in url.lower() for kw in ("course", "curriculum", "program")):
            chunks = scrape_courses(url)
            if chunks:
                return chunks
    except Exception:
        pass
    return scrape_generic(url)


def _add_websites_from_text(text: str) -> Tuple[int, int]:
    """
    Parse URLs out of free-form text (one per line, optionally "Label | URL")
    and add any new, valid ones to advisor_websites in session state.

    Used by both the bulk-paste textarea and the .txt file uploader in the
    Data Management tab so admins can register many URLs at once instead of
    one at a time.

    Returns (added_count, skipped_count), where skipped covers both invalid
    URLs and ones already present in advisor_websites.
    """
    non_blank_lines = [line for line in text.splitlines() if line.strip()]
    parsed = parse_urls_from_text(text)
    invalid_count = len(non_blank_lines) - len(parsed)

    existing_urls = {site["url"] for site in st.session_state.advisor_websites}
    added = 0
    duplicate_count = 0
    for label, url in parsed:
        if url in existing_urls:
            duplicate_count += 1
            continue
        st.session_state.advisor_websites.append({
            "label": label or label_from_url(url),
            "url": url,
        })
        existing_urls.add(url)
        added += 1

    if added:
        save_advisor_websites(st.session_state.advisor_websites)

    return added, invalid_count + duplicate_count


def _rebuild_advisor_index() -> bool:
    """
    Rebuild the shared Advisor AI FAISS index from all current advisor_chunks.

    Re-applies dynamic chunking to every scraped source, creates fresh
    embeddings, builds a new FAISS index, and persists all three to disk —
    this is what makes search queries cover every configured website rather
    than just the most recently updated one, since the index is a single
    merged store across all sources. Returns True on success; on failure an
    error is shown via st.error/st.warning and False is returned.
    """
    if not st.session_state.advisor_chunks:
        st.warning("⚠️ No data chunks available. Please update at least one website first.")
        return False

    try:
        all_text = {
            label: "\n\n".join(chunks)
            for label, chunks in st.session_state.advisor_chunks.items()
        }

        dynamic_chunks = []
        for label, text in all_text.items():
            label_chunks = chunk_text_dynamic(text, min_size=100, max_size=500, overlap=50)
            for chunk in label_chunks:
                chunk["filename"] = label
            dynamic_chunks.extend(label_chunks)

        if not dynamic_chunks:
            st.warning("⚠️ No chunks to index. Please make sure you've updated at least one website.")
            return False

        from src.features.advisor_ai.storage import create_embeddings, build_faiss_index, save_index_and_chunks
        embeddings, _ = create_embeddings(dynamic_chunks)
        index = build_faiss_index(embeddings)
        save_result = save_index_and_chunks(
            embeddings=embeddings,
            index=index,
            chunks=dynamic_chunks,
            save_dir='data/advisor_ai',
        )

        if save_result and all(save_result.values()):
            # Force the next query to reload from disk so it sees this rebuild.
            st.session_state.advisor_resources_loaded = False
            return True

        st.error("Failed to save resources.")
        return False
    except Exception as e:
        st.error(f"Error creating index: {str(e)}")
        return False


def save_advisor_chat_turn(
    chat_session_id: str,
    user_id: int,
    role: str,
    message_text: str,
    model_name: Optional[str] = None,
    language: Optional[str] = None,
) -> None:
    """Persist one Advisor AI conversation turn to advisor_chat_history."""
    model_provider = MODEL_PROVIDERS.get(model_name) if model_name else None

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO advisor_chat_history (
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


def get_advisor_chat_sessions(user_id: int) -> List[Dict[str, Any]]:
    """Return one summary row per advisor chat session for the user."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                h.chat_session_id,
                first_msg.message_text AS first_message,
                COUNT(*) AS turn_count,
                MAX(h.created_at) AS last_active,
                last_asst.model_name AS model_name,
                last_asst.language AS language
            FROM advisor_chat_history h

            JOIN (
                SELECT chat_session_id, message_text
                FROM advisor_chat_history
                WHERE role = 'user'
                  AND user_id = %s
                  AND id = (
                      SELECT MIN(id)
                      FROM advisor_chat_history a2
                      WHERE a2.chat_session_id = advisor_chat_history.chat_session_id
                        AND a2.role = 'user'
                  )
            ) first_msg ON first_msg.chat_session_id = h.chat_session_id

            LEFT JOIN (
                SELECT chat_session_id, model_name, language
                FROM advisor_chat_history
                WHERE role = 'assistant'
                  AND user_id = %s
                  AND id = (
                      SELECT MAX(id)
                      FROM advisor_chat_history a3
                      WHERE a3.chat_session_id = advisor_chat_history.chat_session_id
                        AND a3.role = 'assistant'
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


def get_advisor_chat_session_turns(chat_session_id: str, user_id: int) -> List[Dict[str, Any]]:
    """Return all turns for a single advisor chat session in chronological order."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, role, message_text, model_name, language, created_at
            FROM advisor_chat_history
            WHERE chat_session_id = %s
              AND user_id = %s
            ORDER BY created_at ASC, id ASC
        """, (chat_session_id, user_id))
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()


def delete_advisor_chat_session(chat_session_id: str, user_id: int) -> None:
    """Delete all rows for an Advisor AI chat session."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM advisor_chat_history
            WHERE chat_session_id = %s AND user_id = %s
        """, (chat_session_id, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _render_advisor_history_tab() -> None:
    """Render the Advisor AI History tab with load and delete actions."""
    user_id = get_current_user_id()
    if not user_id:
        st.info("Please log in to view your advisor chat history.")
        return

    sessions = get_advisor_chat_sessions(user_id)
    if not sessions:
        st.info("No chat sessions found yet. Start a conversation in the Ask Advisor tab.")
        return

    for session in sessions:
        session_id = session["chat_session_id"]
        first_message = session.get("first_message") or "Untitled chat"
        last_active = session.get("last_active")
        if hasattr(last_active, "strftime"):
            last_active_display = last_active.strftime("%Y-%m-%d %H:%M")
        else:
            last_active_display = str(last_active)

        title = f"{last_active_display} · {first_message[:80]}{'...' if len(first_message) > 80 else ''}"

        with st.expander(title):
            turns = get_advisor_chat_session_turns(session_id, user_id)
            for turn in turns:
                with st.chat_message(turn["role"]):
                    st.markdown(turn["message_text"])
                    if turn["role"] == "assistant":
                        st.caption(
                            f"Model: {turn.get('model_name') or 'N/A'}  ·  Language: {turn.get('language', 'English') or 'English'}"
                        )

            col_load, col_delete, _ = st.columns([2, 2, 5])

            with col_load:
                if st.button("Load and Continue", key=f"load_advisor_session_{session_id}"):
                    if st.session_state.get("advisor_current_session_id") != session_id:
                        st.session_state["advisor_chat_history"] = []
                        st.session_state["advisor_current_session_id"] = None

                    st.session_state["advisor_chat_history"] = [
                        {"role": t["role"], "content": t["message_text"]}
                        for t in turns
                    ]
                    st.session_state["advisor_current_session_id"] = session_id
                    st.success("Session loaded. Switch to the Ask Advisor tab to continue.")
                    st.rerun()

            with col_delete:
                if st.button(
                    "Delete",
                    key=f"delete_advisor_session_{session_id}",
                    type="primary",
                ):
                    _dialog_delete_advisor_session(session_id, user_id)


@st.dialog("Delete Chat Session")
def _dialog_delete_advisor_session(session_id: str, user_id: int) -> None:
    """
    Confirmation modal for permanently deleting an Advisor AI chat session.

    If the session being deleted is currently active, the in-memory chat
    history and session id are also cleared so the UI returns to the
    no-session state correctly.
    """
    st.warning("Are you sure you want to delete this chat session? This cannot be undone.")
    col1, col2 = st.columns(2)
    if col1.button("Delete", type="primary", key="advisor_dialog_confirm_delete"):
        if st.session_state.get("advisor_current_session_id") == session_id:
            st.session_state["advisor_chat_history"] = []
            st.session_state["advisor_current_session_id"] = None
        delete_advisor_chat_session(session_id, user_id)
        st.toast("Chat session deleted.")
        st.rerun()
    if col2.button("Cancel", key="advisor_dialog_cancel_delete"):
        st.rerun()


def advisor_ai_ui():
    """Main UI function for the Advisor AI feature"""
    # Initialize session state
    initialize_session_state()
    
    st.markdown('<h2 class="feature-header">🎓 Academic Advisor AI</h2>', unsafe_allow_html=True)
    st.write("Get information about professors, courses, and programs by querying university website data.")
    
    # Create tabs for data management and advisor chat
    tabs = st.tabs(["📊 Data Management", "💬 Ask Advisor", "🕘 History"])
    
    # Tab 1: Data Management
    with tabs[0]:
        st.header("📊 Data Management")
        st.write("Manage the webpages to scrape data from. Click 🔄 to update, or ❌ to delete.")
        
        # Create directory if it doesn't exist
        os.makedirs(ADVISOR_DATA_DIR, exist_ok=True)
        
        # Display websites and allow updating/deleting
        for idx, site in enumerate(st.session_state.advisor_websites):
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1], gap="small")
            col1.write(f"**{site['label']}**")
            col2.markdown(f"[🔗 Visit]({site['url']})")
            if col3.button("🔄 Update", key=f"advisor_upd_{idx}"):
                with st.spinner(f"Scraping data from {site['label']}..."):
                    new_chunks = _scrape_site(site["url"])
                    st.session_state.advisor_chunks[site["label"]] = new_chunks

                    # Save chunks to file
                    fname = save_chunks_to_file(new_chunks, site["label"], ADVISOR_DATA_DIR)
                    st.success(f"🎉 Saved {len(new_chunks)} chunks from {site['label']}")

            if col4.button("❌ Delete", key=f"advisor_del_{idx}"):
                st.session_state.advisor_websites.pop(idx)
                st.session_state.advisor_chunks.pop(site["label"], None)
                save_advisor_websites(st.session_state.advisor_websites)
                st.rerun()

        st.markdown("##### ➕ Add Data Sources")
        st.caption("Admins can add any number of website URLs, individually, pasted as a list, or imported from a .txt file.")
        add_tabs = st.tabs(["Single URL", "Multiple URLs", "Upload .txt File"])

        with add_tabs[0]:
            with st.form("advisor_add_single_url", clear_on_submit=True):
                new_label = st.text_input("Label (optional)", key="advisor_new_label")
                new_url = st.text_input("Website URL", key="advisor_new_url")
                submitted = st.form_submit_button("Add Website")
                if submitted:
                    url = new_url.strip()
                    if not is_valid_url(url):
                        st.error("Please enter a valid http(s) URL.")
                    elif any(s["url"] == url for s in st.session_state.advisor_websites):
                        st.warning("This URL has already been added.")
                    else:
                        label = new_label.strip() or label_from_url(url)
                        st.session_state.advisor_websites.append({"label": label, "url": url})
                        save_advisor_websites(st.session_state.advisor_websites)
                        st.success(f"Added '{label}'. Click 🔄 Update above to scrape it.")
                        st.rerun()

        with add_tabs[1]:
            st.caption('One URL per line. Optionally prefix with a label: "Label | https://example.com"')
            bulk_text = st.text_area("URLs", key="advisor_bulk_urls", height=120)
            if st.button("Add URLs", key="advisor_add_bulk"):
                added, skipped = _add_websites_from_text(bulk_text)
                if added:
                    st.success(f"Added {added} new website(s).")
                if skipped:
                    st.warning(f"Skipped {skipped} invalid or duplicate URL(s).")
                if added:
                    st.rerun()

        with add_tabs[2]:
            uploaded_file = st.file_uploader(
                "Upload a .txt file containing URLs (one per line)",
                type=["txt"],
                key="advisor_url_file",
            )
            if uploaded_file is not None and st.button("Import URLs from File", key="advisor_import_file"):
                # utf-8-sig strips a leading BOM if present (e.g. files saved by
                # Windows Notepad's default "UTF-8" encoding), which would
                # otherwise attach to the first URL and fail validation.
                file_text = uploaded_file.read().decode("utf-8-sig", errors="ignore")
                added, skipped = _add_websites_from_text(file_text)
                if added:
                    st.success(f"Imported {added} new website(s).")
                if skipped:
                    st.warning(f"Skipped {skipped} invalid or duplicate URL(s).")
                if added:
                    st.rerun()

        st.markdown("---")

        col_update_all, col_create_index = st.columns(2)

        # Convenience action for bulk-added sites: scrape every configured
        # website and rebuild the merged search index in one click, so newly
        # added URLs are searchable without updating each one individually.
        if col_update_all.button("🔄 Update All Sites & Rebuild Index", key="advisor_update_all"):
            if not st.session_state.advisor_websites:
                st.warning("⚠️ No websites configured yet. Add one above first.")
            else:
                with st.spinner(f"Scraping {len(st.session_state.advisor_websites)} website(s)..."):
                    for site in st.session_state.advisor_websites:
                        new_chunks = _scrape_site(site["url"])
                        st.session_state.advisor_chunks[site["label"]] = new_chunks
                        save_chunks_to_file(new_chunks, site["label"], ADVISOR_DATA_DIR)
                with st.spinner("Rebuilding search index..."):
                    if _rebuild_advisor_index():
                        st.success("✅ All websites scraped — search now covers every source.")

        # Builds the index from whatever chunks are already cached (e.g. after
        # updating individual sites one at a time above).
        if col_create_index.button("🔍 Create Search Index", key="advisor_create_index"):
            with st.spinner("Creating search index from all chunks..."):
                if _rebuild_advisor_index():
                    st.success("✅ Search index created and saved successfully! All added websites are now searchable.")

        st.markdown("---")
        st.subheader("📦 Chunked Data Preview")
        if st.session_state.advisor_chunks:
            # Show original chunks first
            with st.expander("Original Chunks", expanded=False):
                for label, chunks in st.session_state.advisor_chunks.items():
                    st.write(f"**Source: {label}** ({len(chunks)} chunks)")
                    if chunks:
                        for i, c in enumerate(chunks[:3]):  # Show only first 3 chunks to avoid clutter
                            st.code(c, language="text")
                        if len(chunks) > 3:
                            st.info(f"... and {len(chunks) - 3} more chunks")
                    else:
                        st.write("_No chunks available._")
                        
            # Show dynamically chunked data if available
            try:
                # Load the saved chunks if they exist
                from src.features.advisor_ai.storage import load_resources
                _, _, dynamic_chunks, _, _ = load_resources(save_dir='data/advisor_ai')
                
                if dynamic_chunks:
                    with st.expander("Dynamic Chunks (Used for Search)", expanded=False):
                        st.write(f"**Total Dynamic Chunks:** {len(dynamic_chunks)}")
                        for i, chunk in enumerate(dynamic_chunks[:3]):  # Show only first 3 chunks
                            source = chunk.get("filename", "Unknown")
                            st.write(f"**Chunk {i+1}** from {source}")
                            st.code(chunk.get("chunk", ""), language="text")
                        if len(dynamic_chunks) > 3:
                            st.info(f"... and {len(dynamic_chunks) - 3} more chunks")
            except Exception as e:
                # Just don't show dynamic chunks if there's an error
                pass
        else:
            st.info("No chunks yet. Click 🔄 to fetch data from a site above.")
    
    # Tab 2: Ask Advisor
    with tabs[1]:
        st.header("💬 Ask Advisor AI")
        st.write("Enter your question about professors, courses, or programs.")
        
        # Model and language selection dropdown
        col1, col2 = st.columns(2)
        with col1:
            model_keys = list(MODELS.keys())
            saved = st.session_state.get("advisor_selected_model", model_keys[0])
            if saved not in model_keys:
                saved = model_keys[0]

            sel = st.selectbox(
                "Select AI Model",
                model_keys,
                index=model_keys.index(saved),
                key="advisor_model_selectbox",
                help="Choose which AI model to use for generating responses"
            )
            st.session_state["advisor_selected_model"] = sel
        
        with col2:
            # Language selection
            languages = {
                "English": "English",
                "French": "French",
                "Arabic": "Arabic", 
                "Hindi": "Hindi"
            }
            if "advisor_selected_language" not in st.session_state:
                st.session_state.advisor_selected_language = "English"
            
            st.session_state.advisor_selected_language = st.selectbox(
                "Response Language:",
                options=list(languages.keys()),
                index=list(languages.keys()).index(st.session_state.advisor_selected_language),
                key="selectbox1",
                help="Select the language for the AI response"
            )
        
        # Check if API keys are needed for the selected model
        selected_model_id = MODELS[st.session_state.advisor_selected_model]
        model_provider = MODEL_PROVIDERS.get(selected_model_id, "")
        
        if model_provider == "groq" and ("groq_api_key" not in st.session_state or not st.session_state.groq_api_key):
            st.warning("⚠️ Groq API key is required for this model. Please add your API key in your profile settings.")
        
        if model_provider == "gemini" and ("gemini_api_key" not in st.session_state or not st.session_state.gemini_api_key):
            st.warning("⚠️ Google Gemini API key is required for this model. Please add your API key in your profile settings.")
        
        if model_provider == "openai" and ("openai_api_key" not in st.session_state or not st.session_state.openai_api_key):
            st.warning("⚠️ OpenAI API key is required for this model. Please add your API key in your profile settings.")
        
        if model_provider == "github" and ("github_token" not in st.session_state or not st.session_state.github_token):
            st.warning("⚠️ GitHub token is required for this model. Please add your GitHub token in your profile settings.")
        
        # Load resources if not already loaded
        if not st.session_state.advisor_resources_loaded:
            # Use the improved load_resources function from storage module
            from src.features.advisor_ai.storage import load_resources
            embeddings, index, chunks, metadata, embedding_model = load_resources(save_dir='data/advisor_ai')
            
            if not all([embeddings is not None, index is not None, chunks]):
                st.warning("⚠️ No search index available. Go to the Data Management tab and create an index first.")
            else:
                st.session_state.advisor_resources_loaded = True
        
        # Allow the user to start a brand-new conversation without touching
        # the shared advisor index on disk. Only the in-memory chat state is reset.
        if st.button("New Chat", key="advisor_new_chat"):
            st.session_state["advisor_chat_history"] = []
            st.session_state["advisor_current_session_id"] = None
            st.rerun()

        # Display the current in-memory chat transcript.
        for msg in st.session_state.advisor_chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # st.chat_input handles submit-on-enter and keeps the UI aligned with
        # the chat experience used in the RAG feature.
        user_input = st.chat_input("Ask about professors, courses, or programs...")
        if user_input and user_input.strip():
            process_advisor_query(user_input.strip())
            st.rerun()

    # Tab 3: History
    with tabs[2]:
        st.header("🕘 History")
        _render_advisor_history_tab()

def process_advisor_query(user_input):
    """Process a user query for the advisor AI."""
    if not user_input:
        return

    user_id = get_current_user_id()
    if not user_id:
        st.error("Please log in to use Advisor AI chat.")
        return

    # Start a new logical conversation only when no advisor session is active.
    if st.session_state.get("advisor_current_session_id") is None:
        st.session_state["advisor_current_session_id"] = str(uuid.uuid4())

    # Add the user turn to the on-screen transcript first so reruns preserve
    # the conversation exactly as the user saw it.
    st.session_state.advisor_chat_history.append({"role": "user", "content": user_input})
    save_advisor_chat_turn(
        st.session_state.get("advisor_current_session_id"),
        user_id,
        "user",
        user_input,
    )

    # The Advisor AI always reads the latest shared FAISS index from disk.
    embeddings, index, chunks, metadata, embedding_model = load_resources(save_dir='data/advisor_ai')

    if not all([embeddings is not None, index is not None, chunks]):
        error_msg = "⚠️ No search index available. Go to the Data Management tab and create an index first."
        st.session_state.advisor_chat_history.append({"role": "assistant", "content": error_msg})
        save_advisor_chat_turn(
            st.session_state.get("advisor_current_session_id"),
            user_id,
            "assistant",
            error_msg,
        )
        return

    relevant_chunks = get_relevant_context(
        query_text=user_input,
        index=index,
        chunks=chunks,
        metadata=metadata,
        embedding_model=embedding_model,
        k=5,
    )

    selected_language = st.session_state.get("advisor_selected_language", "English")
    system_content = create_advisor_system_message(relevant_chunks, selected_language)

    selected_model_id = MODELS[st.session_state.advisor_selected_model]
    model_provider = MODEL_PROVIDERS.get(selected_model_id, "")

    print(f"DEBUG: Selected model: {st.session_state.advisor_selected_model}")
    print(f"DEBUG: Model ID: {selected_model_id}")
    print(f"DEBUG: Model provider: {model_provider}")

    can_use_model = True
    error_message = ""

    if model_provider == "groq" and ("groq_api_key" not in st.session_state or not st.session_state.groq_api_key):
        can_use_model = False
        error_message = "⚠️ Groq API key is required. Please add your API key in your profile settings."
    elif model_provider == "gemini" and ("gemini_api_key" not in st.session_state or not st.session_state.gemini_api_key):
        can_use_model = False
        error_message = "⚠️ Google Gemini API key is required. Please add your API key in your profile settings."
    elif model_provider == "openai" and ("openai_api_key" not in st.session_state or not st.session_state.openai_api_key):
        can_use_model = False
        error_message = "⚠️ OpenAI API key is required. Please add your API key in your profile settings."
    elif model_provider == "github" and ("github_token" not in st.session_state or not st.session_state.github_token):
        can_use_model = False
        error_message = "⚠️ GitHub token is required. Please add your GitHub token in your profile settings."

    if not can_use_model:
        st.session_state.advisor_chat_history.append({"role": "assistant", "content": error_message})
        save_advisor_chat_turn(
            st.session_state.get("advisor_current_session_id"),
            user_id,
            "assistant",
            error_message,
            model_name=selected_model_id,
            language=selected_language,
        )
        print(f"DEBUG: Cannot use model - {error_message}")
        return

    try:
        print(f"DEBUG: Making API call to {selected_model_id}")

        # Build messages: system context first, then the last ADVISOR_CHAT_CONTEXT_TURNS
        # turns. The current user message is already at the end of advisor_chat_history
        # (appended above) so it is included naturally without being stated twice.
        history_window = st.session_state.advisor_chat_history[-ADVISOR_CHAT_CONTEXT_TURNS:]
        messages = [{"role": "system", "content": system_content}] + [
            {"role": m["role"], "content": m["content"]}
            for m in history_window
        ]

        with st.spinner(f"Thinking... (using {st.session_state.advisor_selected_model})"):
            full_response = ""
            for text in stream_llm_chat(messages, selected_model_id):
                full_response += text

            print(f"DEBUG: Received response length: {len(full_response)} characters")
            print(f"DEBUG: Response preview: {full_response[:200]}...")

        st.session_state.advisor_chat_history.append({"role": "assistant", "content": full_response})
        save_advisor_chat_turn(
            st.session_state.get("advisor_current_session_id"),
            user_id,
            "assistant",
            full_response,
            model_name=selected_model_id,
            language=selected_language,
        )

    except Exception as e:
        error_msg = f"Error calling {st.session_state.advisor_selected_model}: {str(e)}"
        print(f"DEBUG: Error occurred - {error_msg}")
        import traceback
        print(f"DEBUG: Full traceback: {traceback.format_exc()}")

        st.session_state.advisor_chat_history.append({"role": "assistant", "content": error_msg})
        save_advisor_chat_turn(
            st.session_state.get("advisor_current_session_id"),
            user_id,
            "assistant",
            error_msg,
            model_name=selected_model_id,
            language=selected_language,
        )