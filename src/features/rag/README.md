# RAG (Retrieval Augmented Generation) System

## Overview

The RAG (Retrieval Augmented Generation) system enables you to upload documents in multiple formats, create embeddings in a vector database, and then query those documents using natural language. The system retrieves the most relevant context from the documents and uses AI models to generate responses based on that context. All chat sessions are persisted to the database and can be loaded and continued across logins.

## Key Features

### 1. Multi-Format Document Support
- **PDF Files**: Process academic papers, textbooks, and reports
- **Word Documents (.docx)**: Handle formatted documents and reports
- **PowerPoint Presentations (.pptx)**: Extract content from presentation slides
- **Text Files (.txt)**: Process plain text documents and notes

### 2. Advanced Language Support
- **Multi-Language Responses**: Get answers in your preferred language
- **Supported Languages**: English (default), French, Arabic, Hindi
- **Language-Aware Processing**: Optimized prompts for each language

### 3. Flexible AI Model Selection
- **Local Models**: DeepSeek R1, Llama 3.2 (via Ollama)
- **Cloud Models**: Llama 3.3-70B (Groq), Gemini 2.5 Flash, GPT-4o (OpenAI)
- **Intelligent Routing**: Automatic API key validation and model selection

### 4. Persistent Chat History
- **Session Storage**: Every conversation is saved to the database per user
- **History Tab**: Browse, review, and reload past sessions across logins
- **FAISS Snapshot Restoration**: Loading a past session restores the exact document index used at the time, so the conversation can be continued against the original document set

## How It Works

1. **Document Indexing**: 
   - Upload documents in PDF, DOCX, PPTX, or TXT format
   - Documents are processed with format-specific extractors
   - Text is split into optimized chunks for better retrieval
   - Embeddings are created using state-of-the-art sentence transformers
   - FAISS vector store enables efficient similarity search

2. **Query Processing**:
   - User questions are converted to embeddings
   - Similar chunks are retrieved from the vector store
   - Retrieved context and question are sent to the selected AI model
   - Language-specific prompts ensure responses in the chosen language
   - AI generates contextual responses based on document content

## Usage Instructions

### Step 1: Index Documents

1. Go to the "RAG System" tab in the application
2. Select the "Index Documents" section
3. Upload documents in supported formats (PDF, DOCX, PPTX, TXT) or use existing directory
4. Click "Index Documents" to process and create embeddings
5. View ingested documents and manage your document library

### Step 2: Query Documents

1. Go to the "Query Documents" section
2. Select your preferred AI model from the dropdown
3. Choose your response language (English, French, Arabic, or Hindi)
4. Enter your question in the text input
5. Click "Search" to retrieve information from the documents
6. View the retrieved context and the AI-generated answer

### Step 3: View and Continue Chat History

All query sessions are saved to the database and available in the History tab.

1. Go to the "History" tab
2. Each row represents one chat session, showing the date, source documents, and the opening question
3. Expand a session to read the full conversation transcript
4. **Load and Continue**: Click to restore the session's document index and conversation into the Query Documents tab, allowing the conversation to be continued exactly where it left off
5. **Delete**: Permanently removes all database rows and the FAISS snapshot directory for that session

## Enhanced Features

### Document Management
- **Document Library**: View all previously ingested documents
- **Selective Processing**: Choose which documents to query
- **Document Deletion**: Remove documents from the index when needed
- **Metadata Tracking**: Track ingestion dates and document information

### Chat History
- **Persistent Sessions**: Every conversation is stored in the database, grouped by session
- **Cross-Login Access**: Sessions are available whenever the user logs in
- **Snapshot-Based Continuation**: Each session has a corresponding FAISS index snapshot saved to disk, allowing any past conversation to be resumed against the exact document set used at the time

### Multi-Language Support
- **Language Selection**: Choose response language from the dropdown
- **Optimized Prompts**: Language-specific prompt engineering for better results
- **Consistent Experience**: Maintain language preference throughout the session

### AI Model Flexibility
- **Model Comparison**: Try different models to compare response quality
- **Cloud Integration**: Seamless access to powerful cloud-based models
- **API Key Management**: Secure handling of API credentials

## Sample Queries

Once your documents are indexed, you can ask questions like:

- "What are the key points in the document?"
- "Summarize the main argument in chapter 3"
- "What does the author say about [specific topic]?"
- "Explain the concept of [term mentioned in the document]"
- "Compare the viewpoints presented in different sections"

## Technical Details

- Embedding Model: `sentence-transformers/all-MiniLM-L6-v2`
- Vector Database: FAISS (Facebook AI Similarity Search)
- LLM Options: DeepSeek-r1:1.5b and Llama 3.2 (accessed via Ollama)
- Chunk Size: 500 tokens with 50 token overlap
- Chat sessions are persisted in the `rag_query_history` table, grouped by `chat_session_id` (UUID). Each session also has a FAISS snapshot saved to `data/rag/{user_id}/{chat_session_id}/` on disk, which is used to restore the exact document index when the session is loaded from history.

## Future Improvements

- Improved chunking strategies
- Enhanced filtering and metadata capabilities
- Better relevance ranking algorithms
- User feedback mechanisms to improve retrieval quality