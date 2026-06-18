# =============================================================================
# storage.py — Advisor AI Feature: Local Storage Layer
# =============================================================================
# Handles all FAISS index, embedding, and chunk persistence for the Advisor AI
# feature. The functions here are the lower-level storage operations that
# advisor_ai_feature.py calls to build, save, and query the document index.
#
# Module structure:
#   - Text utilities     sanitize_filename(), chunk_text_dynamic() for
#                        preparing scraped content before indexing.
#   - Index operations   create_embeddings(), build_faiss_index(),
#                        save_index_and_chunks(), load_resources() for
#                        building and persisting the FAISS similarity index.
#   - Query utilities    get_relevant_context() for retrieving the top-k most
#                        similar chunks given a query embedding.
#   - Prompt builders    create_augmented_prompt(), create_advisor_system_message()
#                        for formatting retrieved context into LLM prompts.
#
# The FAISS index is stored on disk under data/advisor_ai/ as three files:
#   faiss_index.index   — binary FAISS IndexFlatL2
#   embeddings.npy      — numpy float32 array of chunk embeddings
#   chunks.json         — JSON array of {chunk, filename} dicts
# =============================================================================

import os
import json
import numpy as np
import faiss
import re
from typing import List, Dict, Any, Tuple

# Embedding wrapper provides a consistent encode() interface across both the
# SentenceTransformer direct path and the manual transformers fallback.
from src.utils.embedding_wrapper import get_embedding_model, DEFAULT_MODEL_NAME

# Embedding model identifier used when creating the index. Must match the model
# used at query time; changing this requires rebuilding the stored index.
EMBEDDING_MODEL = DEFAULT_MODEL_NAME

def sanitize_filename(name: str) -> str:
    """
    Convert a friendly label into a safe filename by replacing all non-word
    characters with underscores and appending a .txt extension.

    Used when saving scraped chunks to the data/advisor_ai/ directory so that
    website labels like '👩‍🔬 CS Faculty List' become valid filenames.
    """
    return re.sub(r"\W+", "_", name) + ".txt"

def chunk_text_dynamic(text: str, min_size: int = 100, max_size: int = 500, overlap: int = 50) -> List[Dict]:
    """
    Split text into overlapping chunks bounded by paragraph boundaries.

    Paragraphs (separated by blank lines) are accumulated into a chunk until
    adding the next paragraph would exceed max_size. When min_size is reached
    the current chunk is saved and a new one begins, carrying over the last
    `overlap` characters from the previous chunk for context continuity.

    Args:
        text:     The text to chunk. Returns an empty list for blank input.
        min_size: Minimum characters before a chunk boundary is allowed.
        max_size: Maximum characters per chunk.
        overlap:  Characters from the end of the previous chunk prepended to
                  the next chunk to preserve cross-boundary context.

    Returns:
        List of {"chunk": str} dicts ready for embedding.
    """
    try:
        if not text or len(text.strip()) == 0:
            return []
        
        # Split text into paragraphs
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed max_size, save current chunk and start a new one
            if len(current_chunk) + len(paragraph) > max_size and len(current_chunk) >= min_size:
                chunks.append({"chunk": current_chunk.strip()})
                # Start new chunk with overlap from previous chunk
                if overlap > 0 and len(current_chunk) > overlap:
                    # Get last 'overlap' characters from previous chunk
                    overlap_text = current_chunk[-overlap:]
                    current_chunk = overlap_text + "\n" + paragraph
                else:
                    current_chunk = paragraph
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # Add the last chunk if it's not empty
        if current_chunk.strip():
            chunks.append({"chunk": current_chunk.strip()})
        
        print(f"Created {len(chunks)} chunks with dynamic sizing")
        return chunks
    except Exception as e:
        error_msg = f"Error creating dynamic chunks: {str(e)}"
        print(error_msg)
        return []

def save_chunks_to_file(chunks: List[Dict], label: str, data_dir: str = 'data/advisor_ai') -> str:
    """
    Persist a list of chunk dicts to a text file in the advisor data directory.

    Each chunk's text is written as a paragraph separated by a blank line.
    The filename is derived from the label via sanitize_filename(). The file
    is used for inspection and debugging; the active index is stored separately
    in the binary FAISS and numpy files.

    Args:
        chunks:   List of {"chunk": str} dicts to write.
        label:    Human-readable label for the data source (e.g. "CS Faculty List").
        data_dir: Directory to write the file into.

    Returns:
        Absolute path to the written file, or an empty string on failure.
    """
    try:
        os.makedirs(data_dir, exist_ok=True)
        fname = os.path.join(data_dir, sanitize_filename(label))
        
        with open(fname, "w", encoding="utf-8") as f:
            for chunk_dict in chunks:
                chunk_text = chunk_dict.get("chunk", "")
                if chunk_text:
                    f.write(chunk_text + "\n\n")
        
        print(f"Saved {len(chunks)} chunks to {fname}")
        return fname
    except Exception as e:
        error_msg = f"Error saving chunks to file: {str(e)}"
        print(error_msg)
        return ""

def create_embeddings(chunks: List[Dict]) -> np.ndarray:
    """
    Encode a list of chunk dicts into a numpy float32 embedding matrix.

    Uses SentenceTransformer with the all-MiniLM-L6-v2 model, which produces
    384-dimensional embeddings. The same model must be used at query time so
    that distances in the FAISS index are meaningful.

    Args:
        chunks: List of {"chunk": str} dicts. Must be non-empty.

    Returns:
        Tuple of (embeddings_array, model), where embeddings_array is a
        (len(chunks), 384) float32 numpy array and model is the loaded
        SentenceTransformer instance for reuse at query time.

    Raises:
        RuntimeError: If the embedding model cannot be loaded or encoding fails.
        ValueError:   If chunks is empty.
    """
    try:
        # Use the same approach as in RAG feature
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        
        if not chunks:
            raise ValueError("No chunks provided for embedding creation")
            
        # Extract the text from each chunk dictionary
        texts = [chunk["chunk"] for chunk in chunks]
        
        # Create embeddings in batches to avoid memory issues
        embeddings = model.encode(texts, convert_to_numpy=True)
        
        return embeddings, model
    except Exception as e:
        error_msg = f"Error creating embeddings: {str(e)}"
        print(error_msg)
        raise RuntimeError(error_msg)

def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatL2:
    """
    Build a FAISS flat L2 index from a numpy embedding matrix.

    IndexFlatL2 performs exact nearest-neighbour search using Euclidean
    distance. For the document counts typical in an advisor context (hundreds
    of chunks) this is both accurate and fast enough without approximation.

    Args:
        embeddings: Float32 numpy array of shape (n_chunks, embedding_dim).

    Returns:
        A populated faiss.IndexFlatL2 ready for similarity search.
    """
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)  # L2 distance for similarity
    index.add(np.float32(embeddings))
    return index

def save_index_and_chunks(embeddings: np.ndarray, index: faiss.IndexFlatL2,
                          chunks: List[Dict], metadata: List[Dict] = None,
                          save_dir: str = 'data/advisor_ai') -> Dict[str, str]:
    """
    Persist the FAISS index, embeddings, chunks, and optional metadata to disk.

    Writes three required files and one optional file into save_dir:
        embeddings.npy      — float32 numpy array of all chunk embeddings.
        faiss_index.index   — binary FAISS index for similarity search.
        chunks.json         — JSON array of {chunk, filename} dicts.
        metadata.json       — JSON array of per-chunk metadata (if provided).

    Args:
        embeddings: Float32 numpy array of shape (n_chunks, embedding_dim).
        index:      Populated faiss.IndexFlatL2.
        chunks:     List of {"chunk": str, "filename": str} dicts.
        metadata:   Optional list of per-chunk metadata dicts.
        save_dir:   Directory to write all files into. Created if absent.

    Returns:
        Dict mapping resource names to their absolute file paths.

    Raises:
        RuntimeError: If any file cannot be written.
    """
    try:
        os.makedirs(save_dir, exist_ok=True)
        
        # Save embeddings
        embeddings_path = os.path.join(save_dir, 'embeddings.npy')
        np.save(embeddings_path, embeddings)
        print(f"Saved embeddings to {embeddings_path}")
        
        # Save FAISS index
        index_path = os.path.join(save_dir, 'faiss_index.index')
        faiss.write_index(index, index_path)
        print(f"Saved FAISS index to {index_path}")
        
        # Save chunks
        chunks_path = os.path.join(save_dir, 'chunks.json')
        with open(chunks_path, 'w') as f:
            json.dump(chunks, f)
        print(f"Saved chunks to {chunks_path}")
        
        # Save metadata if provided
        metadata_path = None
        if metadata:
            metadata_path = os.path.join(save_dir, 'metadata.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
            print(f"Saved metadata to {metadata_path}")
        
        paths = {
            'embeddings_path': embeddings_path,
            'index_path': index_path,
            'chunks_path': chunks_path,
        }
        
        if metadata_path:
            paths['metadata_path'] = metadata_path
            
        return paths
    except Exception as e:
        error_msg = f"Error saving resources: {str(e)}"
        print(error_msg)
        raise RuntimeError(error_msg)

def load_resources(save_dir: str = 'data/advisor_ai') -> Tuple[np.ndarray, faiss.IndexFlatL2, List[Dict], List[Dict], Any]:
    """
    Load the FAISS index and associated data files from disk.

    Reads the three required files (embeddings.npy, faiss_index.index,
    chunks.json) and the optional metadata.json from save_dir, then
    instantiates and returns a fresh SentenceTransformer embedding model
    for use at query time.

    If any required file is missing, or if loading fails, returns a tuple
    of (None, None, [], [], model) with a freshly loaded embedding model so
    the caller can safely check for None index/embeddings and fall back to
    prompting the user to re-index.

    Args:
        save_dir: Directory containing the saved resource files.

    Returns:
        Tuple of (embeddings, index, chunks, metadata, embedding_model).
        embeddings and index are None if the required files are absent.
    """
    try:
        # Define paths
        embeddings_path = os.path.join(save_dir, 'embeddings.npy')
        index_path = os.path.join(save_dir, 'faiss_index.index')
        chunks_path = os.path.join(save_dir, 'chunks.json')
        metadata_path = os.path.join(save_dir, 'metadata.json')
        
        # Check if required files exist
        if not (os.path.exists(embeddings_path) and os.path.exists(index_path) and os.path.exists(chunks_path)):
            print(f"Required resource files not found in {save_dir}")
            # Return empty values and a fresh embedding model
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            return None, None, [], [], model
        
        print("Loading resources...")
        
        # Load embeddings
        embeddings = np.load(embeddings_path)
        print(f"Loaded embeddings with shape {embeddings.shape}")
        
        # Load index
        index = faiss.read_index(index_path)
        print(f"Loaded FAISS index with {index.ntotal} vectors")
        
        # Load chunks
        with open(chunks_path, 'r') as f:
            chunks = json.load(f)
        print(f"Loaded {len(chunks)} chunks")
        
        # Load metadata if it exists
        metadata = []
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            print(f"Loaded metadata for {len(metadata)} chunks")
        
        # Create embedding model
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        print("Created embedding model")
        
        return embeddings, index, chunks, metadata, model
    except Exception as e:
        error_msg = f"Error loading resources: {str(e)}"
        print(error_msg)
        # Return empty values and a fresh embedding model
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        return None, None, [], [], model

def get_relevant_context(query_text: str, index: faiss.IndexFlatL2, chunks: List[Dict],
                         metadata: Dict = None, embedding_model: Any = None, k: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieve the k most relevant chunks for a query via FAISS nearest-neighbour search.

    Encodes the query text using the provided embedding model (or creates a new
    one if not supplied), searches the FAISS index, and returns the top-k chunks
    with their relevance scores and source filenames.

    Args:
        query_text:      The user's question or search string.
        index:           Populated faiss.IndexFlatL2 to search.
        chunks:          List of {"chunk": str, "filename": str} dicts matching
                         the index — positional correspondence is assumed.
        metadata:        Optional dict keyed by str(chunk_index) with extra metadata.
        embedding_model: SentenceTransformer instance for encoding the query.
                         A new model is instantiated if None is passed.
        k:               Number of top results to return.

    Returns:
        List of dicts, each containing "chunk", "score", and optionally
        "filename" and "metadata" fields. Empty list on failure.
    """
    try:
        # Create embedding model if not provided
        if embedding_model is None:
            from sentence_transformers import SentenceTransformer
            embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            print("Created new embedding model for query")
        
        # Create embedding for the query
        query_embedding = embedding_model.encode([query_text], convert_to_numpy=True)
        
        # Search the index
        distances, indices = index.search(np.float32(query_embedding), k)
        
        # Get the relevant chunks and metadata
        results = []
        for i, idx in enumerate(indices[0]):
            # Convert numpy int64 to Python int to avoid serialization issues
            idx_int = int(idx)
            
            # Skip invalid indices
            if idx_int >= len(chunks) or idx_int < 0:
                continue
            
            chunk = chunks[idx_int]
            meta = metadata.get(str(idx_int), {}) if metadata else {}
            
            # Create result with chunk text, metadata, and score
            result = {
                "chunk": chunk.get("chunk", ""),
                "score": float(distances[0][i])
            }
            
            # Add filename if available
            if "filename" in chunk:
                result["filename"] = chunk["filename"]
                
            # Add metadata if available
            if meta:
                result["metadata"] = meta
            
            results.append(result)
        
        return results
    except Exception as e:
        print(f"Error getting relevant context: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return []

def create_augmented_prompt(context: List[Dict[str, Any]], query_text: str) -> str:
    """
    Build a single-turn RAG prompt from retrieved context chunks and a query.

    Formats each context item with its source label and relevance score, then
    wraps the block in advisor-role instructions and appends the user's question.
    Used for single-turn queries. For multi-turn conversations use
    create_advisor_system_message() instead, which separates the context from
    the user query so the query is not embedded twice in the messages list.

    Args:
        context:    List of {"chunk": str, "filename": str, "score": float} dicts
                    from get_relevant_context().
        query_text: The user's question to answer.

    Returns:
        A complete prompt string ready to pass to generate_llm_response().
    """
    try:
        # Format the context with source information if available
        formatted_context = ""
        for i, item in enumerate(context):
            chunk_text = item.get("chunk", "")
            source = item.get("filename", "Unknown")
            score = item.get("score", 0.0)
            
            # Format each context item with source and relevance score
            formatted_context += f"[{i+1}] Source: {source} (Relevance: {score:.2f})\n{chunk_text}\n\n"
        
        # Create a comprehensive prompt with instructions and context
        prompt = f"""You are a helpful academic advisor assistant for a university.

I'll provide you with information about professors, courses, and programs, and you'll help answer questions based on this information.

Here is the relevant information I found:
{formatted_context}

Based on the above information, please answer the following question: {query_text}

If the information provided doesn't contain the answer, please say so clearly and suggest what information might help.
Always maintain a friendly, supportive tone appropriate for an academic advisor.
Format your response in a clear, well-structured manner using markdown formatting where appropriate."""
        
        print(f"Created augmented prompt with {len(context)} context items")
        return prompt
    except Exception as e:
        error_msg = f"Error creating augmented prompt: {str(e)}"
        print(error_msg)
        # Return a basic prompt if there's an error
        return f"You are a helpful academic advisor. Please answer this question as best you can: {query_text}"

def create_augmented_prompt_original(context: List[Dict[str, Any]], query_text: str) -> str:
    """
    Simpler single-turn RAG prompt builder retained from the original implementation.

    Formats context as plain "Chunk: ..." blocks without source or score metadata,
    and uses stricter "answer only from context" instructions compared to
    create_augmented_prompt(). Kept for reference; create_augmented_prompt() is
    the active implementation used by advisor_ai_feature.py.

    Args:
        context:    List of {"chunk": str} dicts from get_relevant_context().
        query_text: The user's question to answer.

    Returns:
        A complete prompt string ready to pass to generate_llm_response().
    """
    formatted_context = "\n\n".join(
        [f"Chunk: {chunk['chunk']}" for chunk in context]
    )
    
    return f"""You are an expert university advisor assistant trained to answer questions based **exclusively** on the provided context from chunks after similarity search.

Context:
{formatted_context}

Question: {query_text}

**Instructions:**  
- Answer using only the context above.  
- If the context is insufficient, respond "I don't have enough information."  
- Keep answers concise and focused on helping students with course and professor information.
- Format your response in a clear, helpful manner.
"""

def create_augmented_prompt_with_language(context: List[Dict[str, Any]], query_text: str, language: str = "English") -> str:
    """
    Build a single-turn RAG prompt with optional language instruction.

    Identical to create_augmented_prompt() but appends a language instruction
    when language is not English. Used by advisor_ai_feature.py for the
    single-turn query path when a non-English response language is selected.
    For multi-turn conversations use create_advisor_system_message() instead.

    Args:
        context:    List of {"chunk": str, "filename": str, "score": float} dicts.
        query_text: The user's question to answer.
        language:   Response language (e.g. "French", "Arabic"). Defaults to "English".

    Returns:
        A complete prompt string ready to pass to generate_llm_response().
    """
    try:
        # Format the context with source information if available
        formatted_context = ""
        for i, item in enumerate(context):
            chunk_text = item.get("chunk", "")
            source = item.get("filename", "Unknown")
            score = item.get("score", 0.0)
            
            # Format each context item with source and relevance score
            formatted_context += f"[{i+1}] Source: {source} (Relevance: {score:.2f})\n{chunk_text}\n\n"
        
        # Create language instruction
        language_instruction = ""
        if language != "English":
            language_instruction = f"\nPlease respond in {language} language."
        
        # Create a comprehensive prompt with instructions and context
        prompt = f"""You are a helpful academic advisor assistant for a university.

I'll provide you with information about professors, courses, and programs, and you'll help answer questions based on this information.

Here is the relevant information I found:
{formatted_context}

Based on the above information, please answer the following question: {query_text}

If the information provided doesn't contain the answer, please say so clearly and suggest what information might help.
Always maintain a friendly, supportive tone appropriate for an academic advisor.{language_instruction}
"""
        
        return prompt
    except Exception as e:
        print(f"Error creating augmented prompt: {e}")
        return f"Error creating prompt: {str(e)}"


def create_advisor_system_message(context: List[Dict[str, Any]], language: str = "English") -> str:
    """
    Build the system message for a multi-turn Advisor AI conversation.

    Returns the retrieved context and behavioural instructions without the
    user query embedded. The query is passed separately as the final user
    turn in the messages list, preventing it from appearing twice in the
    prompt.

    Preserves the original wording from create_augmented_prompt_with_language
    exactly, minus the embedded question line.

    Args:
        context: List of dictionaries with relevant chunks from FAISS search.
        language: Language for the response (default: "English").

    Returns:
        System message string for use as the first element of a messages list.
    """
    formatted_context = ""
    for i, item in enumerate(context):
        chunk_text = item.get("chunk", "")
        source = item.get("filename", "Unknown")
        score = item.get("score", 0.0)
        formatted_context += f"[{i+1}] Source: {source} (Relevance: {score:.2f})\n{chunk_text}\n\n"

    language_instruction = ""
    if language != "English":
        language_instruction = f"\nPlease respond in {language} language."

    return (
        f"You are a helpful academic advisor assistant for a university.\n\n"
        f"I'll provide you with information about professors, courses, and programs, "
        f"and you'll help answer questions based on this information.\n\n"
        f"Here is the relevant information I found:\n{formatted_context}\n"
        f"If the information provided doesn't contain the answer, please say so clearly "
        f"and suggest what information might help.\n"
        f"Always maintain a friendly, supportive tone appropriate for an academic advisor."
        f"{language_instruction}"
    )