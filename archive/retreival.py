import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import json
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
MODELS = {
    "DeepSeek (Thinking model)": "deepseek-r1:1.5B",
    "Llama 3.2 (by Meta)": "llama3.2"
}
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# --- Load Resources ---
@st.cache_resource
def load_resources():
    embeddings = np.load("embeddings.npy")
    index = faiss.read_index("faiss_index.index")
    with open("chunks.json", 'r') as f:
        chunks = json.load(f)
    embedding_model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
    return embeddings, index, chunks, embedding_model

embeddings, index, chunks, embedding_model = load_resources()

# --- Query Functions ---
def stream_local_llm(prompt, model_name):
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True
    }
    
    try:
        with requests.post(OLLAMA_API_URL, json=payload, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    json_data = json.loads(line.decode('utf-8'))
                    yield json_data["response"]
    except requests.exceptions.RequestException as e:
        yield f"Error: Failed to get response from local model. Details: {str(e)}"

def get_relevant_context(query_text, index, chunks, embedding_model, k=5):
    query_embedding = embedding_model.encode([query_text])
    D, I = index.search(np.float32(query_embedding), k=k)
    relevant_chunks = [chunks[i] for i in I[0]]
    return relevant_chunks

def create_augmented_prompt(context, query_text):
    formatted_context = "\n\n".join(
        [f"Chunk:\n{chunk['chunk']}" for i, chunk in enumerate(context)]
    )
    return f"""You are an expert RAG assistant trained to answer questions based **exclusively** on the provided context from chunks after similarity search.

Context:
{formatted_context}

Question: {query_text}

**Instructions:**  
- Answer using only the context above.  
- If the context is insufficient, respond "I don't have enough information."  
- Keep answers concise and avoid speculation.
"""

# --- Streamlit UI ---
def main():
    st.title("RAG System with Local LLMs")
    st.write("Ask questions about the PDF documents using one of the local models.")

    # Session state for clearing
    if "clear" not in st.session_state:
        st.session_state.clear = False

    # Input fields
    query_text = st.text_input("Enter your question:", placeholder="What is the main topic of the document?", key="query_text")
    selected_model_key = st.selectbox("Select the model to use:", list(MODELS.keys()), key="model_select")
    selected_model = MODELS[selected_model_key]

    # Action buttons
    col1, col2 = st.columns(2)
    with col1:
        search_clicked = st.button("🔍 Search")
    with col2:
        reset_clicked = st.button("🧹 Reset")

    if reset_clicked:
        st.session_state.query_text = ""
        st.session_state.clear = True
        st.experimental_rerun()

    if search_clicked and query_text.strip() != "":
        st.session_state.clear = False
        st.markdown("**Retrieving relevant context...**")
        with st.spinner("Retrieving relevant context..."):
            context = get_relevant_context(query_text, index, chunks, embedding_model)

        # Display context
        with st.expander("View retrieved context"):
            context_text = "\n\n".join(
                [f"Document {i+1}:\n{chunk['chunk']}" for i, chunk in enumerate(context)]
            )
            st.text(context_text)

        # Create prompt
        augmented_prompt = create_augmented_prompt(context, query_text)

        # Show selected model
        st.info(f"Using model: **{selected_model_key}**")

        # Stream the response
        st.markdown("### Answer:")
        response_placeholder = st.empty()
        full_response = ""

        with st.spinner("Generating response..."):
            try:
                for response_chunk in stream_local_llm(augmented_prompt, selected_model):
                    full_response += response_chunk
                    response_placeholder.markdown(full_response)
            except Exception as e:
                st.error(f"Error generating response: {str(e)}")

# --- Main ---
if __name__ == '__main__':
    main()
