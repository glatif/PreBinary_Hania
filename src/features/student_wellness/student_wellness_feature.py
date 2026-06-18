import streamlit as st
from typing import List, Dict, Any

# Imports from Capstone Project integration
import uuid
from db import get_connection

# Import our utility modules
from src.utils.llm_utils import stream_llm, stream_llm_chat, MODELS, MODEL_PROVIDERS
from src.features.student_wellness.wellness_data import (
    create_wellness_system_message,
    get_services_by_category,
    search_services,
)


# =============================================================================
# SESSION STATE HELPERS
# =============================================================================

def initialize_session_state():
    """Initialize session state variables for the student wellness feature."""
    if "wellness_chat_history" not in st.session_state:
        st.session_state.wellness_chat_history = []
    if "wellness_selected_model" not in st.session_state:
        st.session_state.wellness_selected_model = list(MODELS.keys())[0]
    if "wellness_current_session_id" not in st.session_state:
        st.session_state.wellness_current_session_id = None


def get_current_user_id():
    """Return the logged-in user's database ID from session state."""
    return st.session_state.get("user", {}).get("id")


WELLNESS_CHAT_CONTEXT_TURNS = 10


# =============================================================================
# DATABASE — WELLNESS CHAT HISTORY
# =============================================================================

def save_wellness_chat_turn(
    chat_session_id: str,
    user_id: int,
    role: str,
    message_text: str,
    model_name: str = None,
    language: str = None,
) -> None:
    """Persist one wellness chat turn to wellness_chat_history."""
    model_provider = MODEL_PROVIDERS.get(model_name) if model_name else None

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO wellness_chat_history (
                chat_session_id, user_id, role,
                message_text, model_provider, model_name, language
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                chat_session_id,
                user_id,
                role,
                message_text,
                model_provider,
                model_name,
                language,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()



def get_wellness_chat_sessions(user_id: int) -> List[Dict]:
    """Return one summary row per wellness chat session for the user."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                h.chat_session_id,
                first_msg.message_text AS first_message,
                COUNT(*) AS turn_count,
                MAX(h.created_at) AS last_active,
                last_asst.model_name AS model_name,
                last_asst.language AS language
            FROM wellness_chat_history h

            JOIN (
                SELECT chat_session_id, message_text
                FROM wellness_chat_history
                WHERE role = 'user'
                  AND user_id = %s
                  AND id = (
                      SELECT MIN(id)
                      FROM wellness_chat_history w2
                      WHERE w2.chat_session_id = wellness_chat_history.chat_session_id
                        AND w2.role = 'user'
                  )
            ) first_msg ON first_msg.chat_session_id = h.chat_session_id

            LEFT JOIN (
                SELECT chat_session_id, model_name, language
                FROM wellness_chat_history
                WHERE role = 'assistant'
                  AND user_id = %s
                  AND id = (
                      SELECT MAX(id)
                      FROM wellness_chat_history w3
                      WHERE w3.chat_session_id = wellness_chat_history.chat_session_id
                        AND w3.role = 'assistant'
                  )
            ) last_asst ON last_asst.chat_session_id = h.chat_session_id

            WHERE h.user_id = %s
            GROUP BY h.chat_session_id, first_msg.message_text,
                     last_asst.model_name, last_asst.language
            ORDER BY last_active DESC
            """,
            (user_id, user_id, user_id),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()



def get_wellness_chat_session_turns(chat_session_id: str, user_id: int) -> List[Dict]:
    """Return all turns for a specific wellness chat session in order."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, role, message_text, model_name, language, created_at
            FROM wellness_chat_history
            WHERE chat_session_id = %s
              AND user_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (chat_session_id, user_id),
        )
        return cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()



def delete_wellness_chat_session(chat_session_id: str, user_id: int) -> None:
    """Delete all rows for a wellness chat session."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            DELETE FROM wellness_chat_history
            WHERE chat_session_id = %s AND user_id = %s
            """,
            (chat_session_id, user_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# UI — SERVICES INFORMATION
# =============================================================================

def render_service_card(service: Dict[str, Any]):
    """Render a service card using only Streamlit components with proper styling."""
    icon = service.get("icon", "🏥")
    name = service["name"]
    description = service["description"]
    services = service.get("services", [])
    location = service.get("location", "Not specified")
    contact = service.get("contact", "Not specified")
    hyperlink = service.get("hyperlink", "#")
    use_cases = service.get("use_cases", [])
    category = service.get("category", "General")

    with st.container():
        st.markdown(
            f"""
            <div style="
                border: 2px solid #3498db;
                border-radius: 12px;
                padding: 20px;
                margin: 15px 0;
                background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            ">
                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                    <span style="font-size: 2.5em; margin-right: 15px;">{icon}</span>
                    <div>
                        <h2 style="margin: 0; color: #1a202c; font-size: 1.8em; font-weight: bold;">{name}</h2>
                        <p style="margin: 5px 0 0 0; color: #6366f1; font-weight: 600; font-size: 0.9em; text-transform: uppercase;">{category}</p>
                    </div>
                </div>
                <p style="color: #2d3748; margin-bottom: 15px; line-height: 1.6; font-size: 1.05em;">{description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### 🔹 Services Offered:")
        for svc in services:
            st.markdown(f"• {svc}")

        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 📍 Location")
            st.info(location if location != "Not specified" else "Location not specified")

        with col2:
            st.markdown("### 📞 Contact")
            st.info(contact if contact != "Not specified" else "Contact not specified")

        if hyperlink and hyperlink != "#":
            st.markdown("### 🔗 Official Website")
            st.markdown(f"[🌐 Visit Official Website]({hyperlink})")

        if use_cases:
            with st.expander("💡 Common Questions & Use Cases", expanded=False):
                for i, use_case in enumerate(use_cases, 1):
                    st.markdown(f'{i}. *"{use_case}"*')

        st.markdown("<br>", unsafe_allow_html=True)



def render_services_information():
    """Render the services information tab."""
    st.header("🏥 TRU Student Wellness Services")
    st.write("Comprehensive information about mental and physical health services available to TRU students.")

    search_query = st.text_input("🔍 Search services:", placeholder="Type to search for specific services...")

    if search_query:
        matching_services = search_services(search_query)
        if matching_services:
            st.success(f"Found {len(matching_services)} matching service(s)")
            for service in matching_services:
                render_service_card(service)
        else:
            st.warning("No services found matching your search. Try different keywords.")
            st.info("💡 **Tip:** Try searching for terms like 'mental health', 'counselling', 'medical', 'fitness', 'wellness', etc.")
    else:
        categories = get_services_by_category()
        category_tabs = st.tabs(list(categories.keys()))

        for i, (category, services) in enumerate(categories.items()):
            with category_tabs[i]:
                st.subheader(f"{category}")
                for service in services:
                    render_service_card(service)

    st.markdown("---")
    st.subheader("🚨 Emergency & Quick Contacts")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """
        **🆘 Crisis Support**
        - **Counselling Services:** 250-828-5023
        - **Emergency:** 911
        """
        )

    with col2:
        st.markdown(
            """
        **🏥 Health Services**
        - **Wellness Centre:** 250-828-5010
        - **Medical Clinic:** 250-828-5126
        """
        )

    with col3:
        st.markdown(
            """
        **24/7 Support**
        - **GuardMe App:** Real-time support
        - **Crisis Lines:** Available 24/7
        """
        )


# =============================================================================
# UI — WELLNESS CHAT + HISTORY
# =============================================================================

def process_wellness_query(user_input: str):
    """Process a user query for the wellness chatbot."""
    if not user_input:
        return

    user_id = get_current_user_id()

    # A chat session is created only when the first message is sent.
    if st.session_state.get("wellness_current_session_id") is None:
        st.session_state["wellness_current_session_id"] = str(uuid.uuid4())

    # Add the user's message to the in-memory chat history first.
    st.session_state.wellness_chat_history.append({"role": "user", "content": user_input})

    # Persist the user turn immediately so the DB is updated before rerun.
    if user_id:
        save_wellness_chat_turn(
            st.session_state.get("wellness_current_session_id"),
            user_id,
            "user",
            user_input,
        )

    selected_model_id = MODELS[st.session_state.wellness_selected_model]
    model_provider = MODEL_PROVIDERS.get(selected_model_id, "")

    can_use_model = True
    error_message = ""

    if model_provider == "groq" and (
        "groq_api_key" not in st.session_state or not st.session_state.groq_api_key
    ):
        can_use_model = False
        error_message = "⚠️ Groq API key is required. Please add your API key in your profile settings."
    elif model_provider == "gemini" and (
        "gemini_api_key" not in st.session_state or not st.session_state.gemini_api_key
    ):
        can_use_model = False
        error_message = "⚠️ Google Gemini API key is required. Please add your API key in your profile settings."
    elif model_provider == "openai" and (
        "openai_api_key" not in st.session_state or not st.session_state.openai_api_key
    ):
        can_use_model = False
        error_message = "⚠️ OpenAI API key is required. Please add your API key in your profile settings."
    elif model_provider == "github" and (
        "github_token" not in st.session_state or not st.session_state.github_token
    ):
        can_use_model = False
        error_message = "⚠️ GitHub token is required. Please add your GitHub token in your profile settings."

    if not can_use_model:
        st.session_state.wellness_chat_history.append({"role": "assistant", "content": error_message})

        # selected_language is intentionally omitted here because it is only
        # defined inside the success path below.
        if user_id:
            save_wellness_chat_turn(
                st.session_state.get("wellness_current_session_id"),
                user_id,
                "assistant",
                error_message,
                model_name=selected_model_id,
            )
    else:
        try:
            selected_language = st.session_state.get("wellness_selected_language", "English")
            system_content = create_wellness_system_message(selected_language)

            # Build messages: system content first, then the last WELLNESS_CHAT_CONTEXT_TURNS
            # turns. The current user message is already at the end of wellness_chat_history
            # (appended above) so it is included naturally without being stated twice.
            history_window = st.session_state.wellness_chat_history[-WELLNESS_CHAT_CONTEXT_TURNS:]
            messages = [{"role": "system", "content": system_content}] + [
                {"role": m["role"], "content": m["content"]}
                for m in history_window
            ]

            with st.spinner(f"Thinking... (using {st.session_state.wellness_selected_model})"):
                full_response = ""
                for text in stream_llm_chat(messages, selected_model_id):
                    full_response += text

            st.session_state.wellness_chat_history.append({"role": "assistant", "content": full_response})

            if user_id:
                save_wellness_chat_turn(
                    st.session_state.get("wellness_current_session_id"),
                    user_id,
                    "assistant",
                    full_response,
                    model_name=selected_model_id,
                    language=selected_language,
                )

        except Exception as e:
            # Use the local selected_model_id variable rather than reading from
            # session state, which may not be initialised if the error occurred
            # during model dispatch before session state was fully set up.
            error_msg = f"Error calling {selected_model_id}: {str(e)}"
            st.session_state.wellness_chat_history.append({"role": "assistant", "content": error_msg})

            if user_id:
                save_wellness_chat_turn(
                    st.session_state.get("wellness_current_session_id"),
                    user_id,
                    "assistant",
                    error_msg,
                    model_name=selected_model_id,
                    language=selected_language,
                )



def _render_wellness_history_tab():
    """History tab for browsing, loading, and deleting wellness chat sessions."""
    user_id = get_current_user_id()
    sessions = get_wellness_chat_sessions(user_id) if user_id else []

    if not sessions:
        st.info("No chat sessions found yet. Start a conversation in the Wellness Assistant tab.")
        return

    for session in sessions:
        session_id = session["chat_session_id"]
        first_message = session.get("first_message", "") or ""
        last_active = session.get("last_active", "")
        title = f"{last_active} · {first_message[:80]}{'...' if len(first_message) > 80 else ''}"

        with st.expander(title, expanded=False):
            turns = get_wellness_chat_session_turns(session_id, user_id)
            for turn in turns:
                with st.chat_message(turn["role"]):
                    st.markdown(turn["message_text"])
                    if turn["role"] == "assistant":
                        st.caption(
                            f"Model: {turn['model_name']}  ·  Language: {turn.get('language', 'English')}"
                        )

            col_load, col_delete, _ = st.columns([2, 2, 5])

            with col_load:
                if st.button("Load and Continue", key=f"load_wellness_session_{session_id}"):
                    current_session = st.session_state.get("wellness_current_session_id")
                    if current_session and current_session != session_id:
                        st.session_state["wellness_chat_history"] = []
                        st.session_state["wellness_current_session_id"] = None

                    st.session_state["wellness_chat_history"] = [
                        {"role": t["role"], "content": t["message_text"]}
                        for t in turns
                    ]
                    st.session_state["wellness_current_session_id"] = session_id
                    st.success("Session loaded. Switch to the Wellness Assistant tab to continue.")
                    st.rerun()

            with col_delete:
                if st.button(
                    "Delete",
                    key=f"delete_wellness_session_{session_id}",
                    type="primary",
                ):
                    _dialog_delete_wellness_session(session_id, user_id)



@st.dialog("Delete Chat Session")
def _dialog_delete_wellness_session(session_id: str, user_id: int) -> None:
    """
    Confirmation modal for permanently deleting a Student Wellness chat session.

    If the session being deleted is currently active, the in-memory chat
    history and session id are also cleared so the UI returns to the
    no-session state correctly.
    """
    st.warning("Are you sure you want to delete this chat session? This cannot be undone.")
    col1, col2 = st.columns(2)
    if col1.button("Delete", type="primary", key="wellness_dialog_confirm_delete"):
        if st.session_state.get("wellness_current_session_id") == session_id:
            st.session_state["wellness_chat_history"] = []
            st.session_state["wellness_current_session_id"] = None
        delete_wellness_chat_session(session_id, user_id)
        st.toast("Chat session deleted.")
        st.rerun()
    if col2.button("Cancel", key="wellness_dialog_cancel_delete"):
        st.rerun()


def render_wellness_chat():
    """Render the wellness chatbot interface."""
    st.header("💬 Wellness Services Assistant")
    st.write("Ask questions about TRU's wellness services and get personalized assistance.")

    col1, col2 = st.columns(2)
    with col1:
        model_keys = list(MODELS.keys())
        saved = st.session_state.get("wellness_selected_model", model_keys[0])
        if saved not in model_keys:
            saved = model_keys[0]
        sel = st.selectbox(
            "Select AI Model",
            model_keys,
            index=model_keys.index(saved),
            help="Choose which AI model to use for generating responses",
            key="wellness_model_selectbox",
        )
        st.session_state["wellness_selected_model"] = sel

    with col2:
        languages = {
            "English": "English",
            "French": "French",
            "Arabic": "Arabic",
            "Hindi": "Hindi",
        }
        if "wellness_selected_language" not in st.session_state:
            st.session_state.wellness_selected_language = "English"

        st.session_state.wellness_selected_language = st.selectbox(
            "Response Language:",
            options=list(languages.keys()),
            index=list(languages.keys()).index(st.session_state.wellness_selected_language),
            help="Select the language for the AI response",
            key="wellness_language_select",
        )

    selected_model_id = MODELS[st.session_state.wellness_selected_model]
    model_provider = MODEL_PROVIDERS.get(selected_model_id, "")

    if model_provider == "groq" and (
        "groq_api_key" not in st.session_state or not st.session_state.groq_api_key
    ):
        st.warning("⚠️ Groq API key is required for this model. Please add your API key in your profile settings.")

    if model_provider == "gemini" and (
        "gemini_api_key" not in st.session_state or not st.session_state.gemini_api_key
    ):
        st.warning("⚠️ Google Gemini API key is required for this model. Please add your API key in your profile settings.")

    if model_provider == "openai" and (
        "openai_api_key" not in st.session_state or not st.session_state.openai_api_key
    ):
        st.warning("⚠️ OpenAI API key is required for this model. Please add your API key in your profile settings.")

    if model_provider == "github" and (
        "github_token" not in st.session_state or not st.session_state.github_token
    ):
        st.warning("⚠️ GitHub token is required for this model. Please add your GitHub token in your profile settings.")

    if st.button("New Chat", key="wellness_new_chat"):
        st.session_state["wellness_chat_history"] = []
        st.session_state["wellness_current_session_id"] = None
        st.rerun()

    for msg in st.session_state.wellness_chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.markdown("**💡 Try asking questions like:**")
    sample_questions = [
        "I'm feeling stressed and need someone to talk to. What options do I have?",
        "Where can I get medical care on campus?",
        "What fitness facilities are available at TRU?",
        "How do I access mental health support outside business hours?",
        "What support is available for students with disabilities?",
        "How can I get health insurance through TRU?",
    ]

    cols = st.columns(2)
    for i, question in enumerate(sample_questions):
        with cols[i % 2]:
            if st.button(f"💭 {question[:50]}...", key=f"sample_q_{i}", help=question):
                process_wellness_query(question)
                st.rerun()

    st.markdown("---")

    user_input = st.chat_input("Ask about wellness services, mental health support...")
    if user_input and user_input.strip():
        process_wellness_query(user_input.strip())
        st.rerun()



def student_wellness_ui():
    """Main UI function for the Student Wellness Services feature."""
    initialize_session_state()

    st.markdown('<h2 class="feature-header">🌟 Student Wellness Services</h2>', unsafe_allow_html=True)
    st.write(
        "Access comprehensive information about TRU's mental and physical health services, and get personalized assistance through our AI-powered wellness assistant."
    )

    tabs = st.tabs(["📋 Services Information", "🤖 Wellness Assistant", "🕘 History"])

    with tabs[0]:
        render_services_information()

    with tabs[1]:
        render_wellness_chat()

    with tabs[2]:
        _render_wellness_history_tab()