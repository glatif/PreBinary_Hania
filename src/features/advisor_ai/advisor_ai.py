import streamlit as st
import os
from typing import List, Dict, Any

# Import utility functions
from src.utils.llm_utils import stream_llm, MODELS
from src.features.advisor_ai.scraper import scrape_professors, scrape_courses
from src.features.advisor_ai.storage import (
    save_chunks_to_file,
    create_embeddings,
    build_faiss_index,
    save_index_and_chunks,
    load_resources,
    get_relevant_context,
    create_augmented_prompt
)

class AdvisorAI:
    """
    AdvisorAI feature for the UReap application.
    Provides a UI for scraping and querying university professor and course information.
    """
    
    def __init__(self):
        """
        Initialize the AdvisorAI feature.
        Sets up session state variables if they don't exist.
        """
        # Initialize session state for websites
        if "advisor_websites" not in st.session_state:
            st.session_state.advisor_websites = [
                {"label": "👩‍🔬 CS Faculty List", "url": "https://www.tru.ca/science/departments/compsci/people.html"},
                {
                    "label": "📚 CS Bachelor Curriculum",
                    "url": "https://www.tru.ca/science/departments/compsci/programs/cs-bachelor-of-science-major-compsci.html"
                },
            ]
        
        # Initialize session state for chunks
        if "advisor_chunks" not in st.session_state:
            st.session_state.advisor_chunks = {}
        
        # Initialize session state for chat history
        if "advisor_chat_history" not in st.session_state:
            st.session_state.advisor_chat_history = []
            
        # Create data directory if it doesn't exist
        os.makedirs("data/advisor_ai", exist_ok=True)
        
        # Load existing resources if available
        self.embeddings, self.index, self.chunks, self.metadata, self.embedding_model = load_resources()
    
    def render(self):
        """
        Render the AdvisorAI UI.
        """
        st.title("📘 University Advisor Assistant")
        
        # Create tabs for data input and chat
        tabs = st.tabs(["🛠 Data Input Settings", "💬 Ask a Question"])
        
        # Tab 1: Data Input Settings
        with tabs[0]:
            self._render_data_input_tab()
        
        # Tab 2: Ask a Question
        with tabs[1]:
            self._render_chat_tab()
    
    def _render_data_input_tab(self):
        """
        Render the data input tab.
        """
        st.header("🛠 Data Input Settings")
        st.write("Manage the webpages to scrape data from. Click 🔄 to update, or ❌ to delete.")
        
        for idx, site in enumerate(st.session_state.advisor_websites):
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1], gap="small")
            col1.write(f"**{site['label']}**")
            col2.markdown(f"[🔗 Visit]({site['url']})")
            
            if col3.button("🔄 Update", key=f"advisor_upd_{idx}"):
                if "people.html" in site["url"]:
                    new_chunks = scrape_professors(site["url"])
                    chunk_type = "professor"
                else:
                    new_chunks = scrape_courses(site["url"])
                    chunk_type = "course"
                
                # Save chunks to session state
                st.session_state.advisor_chunks[site["label"]] = new_chunks
                
                # Save chunks to file
                fname = save_chunks_to_file(new_chunks, site["label"])
                
                # Update or create vector DB
                self._update_vector_db()
                
                st.success(f"🎉 Saved {len(new_chunks)} chunks to `{fname}` and updated vector database")
            
            if col4.button("❌ Delete", key=f"advisor_del_{idx}"):
                if site["label"] in st.session_state.advisor_chunks:
                    del st.session_state.advisor_chunks[site["label"]]
                st.session_state.advisor_websites.pop(idx)
                
                # Update vector DB after deletion
                self._update_vector_db()
                
                st.experimental_rerun()
        
        if st.button("➕ Add New Website", key="advisor_add_website"):
            st.info("Feature coming soon: add custom sites for scraping.")
        
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
                if self.chunks and len(self.chunks) > 0:
                    with st.expander("Dynamic Chunks (Used for Search)", expanded=False):
                        st.write(f"**Total Dynamic Chunks:** {len(self.chunks)}")
                        for i, chunk in enumerate(self.chunks[:3]):  # Show only first 3 chunks
                            source = chunk.get("filename", "Unknown")
                            st.write(f"**Chunk {i+1}** from {source}")
                            st.code(chunk.get("chunk", ""), language="text")
                        if len(self.chunks) > 3:
                            st.info(f"... and {len(self.chunks) - 3} more chunks")
            except Exception as e:
                # Just don't show dynamic chunks if there's an error
                pass
        else:
            st.info("No chunks yet. Click 🔄 to fetch data from a site above.")
    
    def _render_chat_tab(self):
        """
        Render the chat tab.
        """
        st.header("💬 Ask a Question")
        st.write("Enter your question about courses or professors below. 🤖")
        
        # Display model selection in sidebar
        st.sidebar.subheader("AdvisorAI Settings")
        selected_model = st.sidebar.selectbox(
            "Select LLM Model",
            options=list(MODELS.keys()),
            index=0,
            key="advisor_model_selection"
        )
        model_name = MODELS[selected_model]
        
        # Display chat history
        for msg in st.session_state.advisor_chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        # Chat input
        user_input = st.chat_input("Type your question about courses or professors here…")
        if user_input:
            # Add user message to chat history
            st.session_state.advisor_chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)
            
            # Check if vector DB is available
            if self.index is None or len(self.chunks) == 0:
                assistant_reply = "⚠️ No data available. Please go to the 'Data Input Settings' tab and click 🔄 to fetch data first."
                st.session_state.advisor_chat_history.append({"role": "assistant", "content": assistant_reply})
                with st.chat_message("assistant"):
                    st.markdown(assistant_reply)
                return
            
            # Get relevant context
            relevant_chunks = get_relevant_context(
                user_input, self.index, self.chunks, self.metadata, self.embedding_model, k=3
            )
            
            # Create augmented prompt
            prompt = create_augmented_prompt(relevant_chunks, user_input)
            
            # Stream response from LLM
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                
                # Stream the response
                for chunk in stream_llm(prompt, model_name):
                    full_response += chunk
                    message_placeholder.markdown(full_response + "▌")
                
                message_placeholder.markdown(full_response)
            
            # Add assistant response to chat history
            st.session_state.advisor_chat_history.append({"role": "assistant", "content": full_response})
    
    def _update_vector_db(self):
        """
        Update the vector database with current chunks using dynamic chunking.
        """
        from src.features.advisor_ai.storage import chunk_text_dynamic
        
        # First, check if we have any chunks
        if not st.session_state.advisor_chunks:
            self.embeddings, self.index, self.chunks, self.metadata, self.embedding_model = None, None, [], [], None
            return
            
        # Convert the current chunks to the format needed for dynamic chunking
        all_text = {}
        for label, chunks in st.session_state.advisor_chunks.items():
            all_text[label] = "\n\n".join(chunks)
        
        # Apply dynamic chunking to each text
        dynamic_chunks = []
        
        for label, text in all_text.items():
            # Use dynamic chunking with paragraph-aware splitting
            label_chunks = chunk_text_dynamic(
                text, 
                min_size=100,  # Minimum chunk size
                max_size=500,  # Maximum chunk size
                overlap=50     # Overlap between chunks
            )
            
            # Add source label to each chunk
            for chunk in label_chunks:
                chunk["filename"] = label
            
            dynamic_chunks.extend(label_chunks)
        
        if not dynamic_chunks:
            self.embeddings, self.index, self.chunks, self.metadata, self.embedding_model = None, None, [], [], None
            return
        
        # Create embeddings and index
        try:
            # Create embeddings for the dynamic chunks
            self.embeddings, self.embedding_model = create_embeddings(dynamic_chunks)
            
            # Build FAISS index
            self.index = build_faiss_index(self.embeddings)
            
            # Save the chunks and metadata
            self.chunks = dynamic_chunks
            self.metadata = {i: {"source": chunk.get("filename", "Unknown")} for i, chunk in enumerate(dynamic_chunks)}
            
            # Save resources to disk
            save_result = save_index_and_chunks(
                embeddings=self.embeddings,
                index=self.index,
                chunks=self.chunks,
                metadata=self.metadata,
                save_dir='data/advisor_ai'
            )
            
            if save_result and all(save_result.values()):
                print("✅ Vector database updated successfully!")
            else:
                print("⚠️ Some resources failed to save.")
                
        except Exception as e:
            print(f"Error updating vector database: {str(e)}")
            import traceback
            print(traceback.format_exc())
            self.embeddings, self.index, self.chunks, self.metadata, self.embedding_model = None, None, [], [], None
