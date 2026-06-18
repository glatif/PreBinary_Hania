import os
import json
import numpy as np
import faiss
import pypdf
from typing import List, Dict, Any

# Import our custom embedding wrapper instead of sentence-transformers
from src.utils.embedding_wrapper import get_embedding_model, DEFAULT_MODEL_NAME

# Model for creating embeddings
EMBEDDING_MODEL = DEFAULT_MODEL_NAME

def load_pdf_documents(data_dir='data'):
    """Load PDF documents from the specified directory"""
    documents = []
    for filename in os.listdir(data_dir):
        if filename.endswith('.pdf'):
            filepath = os.path.join(data_dir, filename)
            with open(filepath, 'rb') as f:
                reader = pypdf.PdfReader(f)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                documents.append({"filename": filename, "content": text})
    return documents

def chunk_documents(documents, chunk_size=500, chunk_overlap=50):
    """Split documents into overlapping chunks"""
    chunks = []
    for doc in documents:
        content = doc["content"]
        filename = doc["filename"]
        for i in range(0, len(content), chunk_size - chunk_overlap):
            chunk = content[i:i + chunk_size]
            chunks.append({"filename": filename, "chunk": chunk})
    return chunks

def create_embeddings(chunks):
    """Create embeddings for document chunks"""
    model = get_embedding_model(EMBEDDING_MODEL)
    embeddings = model.encode([chunk["chunk"] for chunk in chunks])
    return embeddings

def build_faiss_index(embeddings):
    """Build a FAISS index from embeddings"""
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)  # L2 distance for similarity
    index.add(np.float32(embeddings))
    return index

def save_index_and_chunks(embeddings, index, chunks, save_dir='data'):
    """Save the index, embeddings, and chunks for later retrieval"""
    os.makedirs(save_dir, exist_ok=True)
    
    # Save embeddings
    np.save(os.path.join(save_dir, "embeddings.npy"), embeddings)
    
    # Save FAISS index
    faiss.write_index(index, os.path.join(save_dir, "faiss_index.index"))
    
    # Save chunks
    with open(os.path.join(save_dir, "chunks.json"), 'w') as f:
        json.dump(chunks, f)
    
    return {
        "embeddings_path": os.path.join(save_dir, "embeddings.npy"),
        "index_path": os.path.join(save_dir, "faiss_index.index"),
        "chunks_path": os.path.join(save_dir, "chunks.json")
    }

def load_resources(embeddings_path, index_path, chunks_path):
    """Load saved resources (embeddings, index, chunks)"""
    embeddings = np.load(embeddings_path)
    index = faiss.read_index(index_path)
    with open(chunks_path, 'r') as f:
        chunks = json.load(f)
    embedding_model = get_embedding_model(EMBEDDING_MODEL)
    return embeddings, index, chunks, embedding_model

def get_relevant_context(query_text, index, chunks, embedding_model, k=5):
    """Get the most relevant document chunks for a query"""
    query_embedding = embedding_model.encode([query_text])
    D, I = index.search(np.float32(query_embedding), k=k)
    relevant_chunks = [chunks[i] for i in I[0]]
    return relevant_chunks

def create_augmented_prompt(context, query_text):
    """Create a prompt augmented with context for the LLM"""
    formatted_context = "\n\n".join(
        [f"Chunk:\n{chunk['chunk']}" for chunk in context]
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

def create_augmented_prompt_with_language(context, query_text, language="English"):
    """Create a prompt augmented with context and language specification for the LLM"""
    formatted_context = "\n\n".join(
        [f"Chunk:\n{chunk['chunk']}" for chunk in context]
    )
    
    language_instruction = ""
    if language != "English":
        language_instruction = f"\n- Respond in {language} language."
    
    return f"""You are an expert RAG assistant trained to answer questions based **exclusively** on the provided context from chunks after similarity search.

Context:
{formatted_context}

Question: {query_text}

**Instructions:**  
- Answer using only the context above.  
- If the context is insufficient, respond "I don't have enough information."  
- Keep answers concise and avoid speculation.{language_instruction}
"""