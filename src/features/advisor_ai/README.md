# AdvisorAI Feature

## Overview

The AdvisorAI feature is an intelligent academic assistant designed to help students and faculty access information about professors, courses, and academic programs through natural language queries. It uses web scraping to gather data from university websites, processes this information into searchable chunks, indexes it in a vector database, and provides a multilingual chat interface for querying this information. Conversation sessions are persisted to the database and can be loaded and continued across logins.

## Key Features

### 1. Intelligent Information Retrieval
- **Web Scraping**: Automatically extracts structured information from university websites about professors and courses
- **Vector Search**: Advanced semantic search using FAISS for finding the most relevant information
- **Contextual Responses**: AI-powered responses based on the most relevant university data

### 2. Multi-Language Support
- **Language Selection**: Choose response language from English, French, Arabic, or Hindi
- **Optimized Prompts**: Language-specific prompt engineering for accurate responses
- **Consistent Experience**: Maintain language preference throughout the chat session

### 3. Advanced AI Model Integration
- **Multiple AI Models**: Support for local and cloud-based models
  - Local: DeepSeek R1, Llama 3.2 (via Ollama)
  - Cloud: Llama 3.3-70B (Groq), Gemini 2.5 Flash, GPT-4o (OpenAI)
- **Smart Model Selection**: Choose the best model for your needs
- **API Key Management**: Secure handling of cloud model credentials

### 4. Enhanced Chat Interface
- **Conversational UI**: Natural language interaction for asking questions
- **Persistent Chat History**: Conversation sessions are saved to the database and accessible across logins
- **Context Awareness**: Responses based on university-specific information
- **Real-time Processing**: Live response generation with selected AI models

## Supported Data Sources

The AdvisorAI feature currently supports scraping from the following university websites:

1. **Thompson Rivers University Computer Science Department**
   - URL: https://www.tru.ca/science/departments/compsci/people.html
   - Data extracted: Faculty profiles, research interests, contact information, and academic backgrounds
   - Usage: Enter the URL in the scraping section to extract information about TRU CS professors

2. **Thompson Rivers University Computer Science Program**
   - URL: https://www.tru.ca/science/departments/compsci/programs/cs-bachelor-of-science-major-compsci.html
   - Data extracted: Course descriptions, prerequisites, and credits
   - Usage: Enter the URL in the scraping section to extract information about TRU CS courses

## Technical Implementation

### Dynamic Chunking

The feature implements a sophisticated chunking strategy that:
- Respects paragraph boundaries to maintain context
- Allows configurable minimum (100 characters) and maximum (1000 characters) chunk sizes
- Implements chunk overlap (20%) to prevent information loss at boundaries
- Preserves metadata about the source of each chunk

### Embedding and Indexing

- Uses the `sentence-transformers/all-MiniLM-L6-v2` model for creating embeddings
- Implements batched processing for efficient embedding creation
- Stores embeddings in a FAISS index for fast similarity search
- Saves resources (embeddings, index, chunks, metadata) in separate files for easier debugging and incremental updates

### Semantic Search

- Retrieves the most relevant context chunks based on vector similarity
- Includes relevance scores and source metadata in the prompt
- Creates augmented prompts that combine user queries with retrieved context

## Usage Instructions

### Data Management

1. Navigate to the "Data Management" tab in the AdvisorAI section
2. Enter a university faculty or course website URL in the input field
3. Click the 🔄 refresh button to scrape and process the data
4. View both the original scraped chunks and the dynamically processed chunks in the preview section
5. Once data is scraped, the system automatically creates embeddings and builds the vector database

### Interactive Chat

1. Navigate to the "Chat" tab in the AdvisorAI section
2. **Select AI Model**: Choose from available local or cloud-based models
   - Ensure API keys are configured for cloud models (Groq, Gemini, OpenAI)
3. **Choose Response Language**: Select from English, French, Arabic, or Hindi
4. **Ask Questions**: Type your question about professors, courses, or programs
5. **Review Responses**: Get contextual answers based on university data in your chosen language

### Chat History

All conversation sessions are saved to the database and available in the History tab.

1. Go to the "History" tab
2. Each row represents one conversation session, showing the date and a preview of the first message
3. **Load and Continue**: Click to restore a past conversation into the Chat tab and continue where it left off
4. **Delete**: Permanently remove a session and all its messages

### Enhanced Features

#### Multi-Language Responses
- Select your preferred language from the dropdown
- Ask questions in any language and receive responses in your chosen language
- Language preference is maintained throughout your session

#### Advanced AI Model Selection
- **Local Models**: Use DeepSeek or Llama 3.2 for offline processing
- **Cloud Models**: Access powerful models like GPT-4o, Gemini, or Groq-hosted Llama
- **Model Comparison**: Try different models to compare response quality

#### Smart Context Retrieval
- Semantic search finds the most relevant information
- Relevance scores help prioritize the best matches
- Source attribution shows where information comes from

### Example Questions

- "Tell me about 3 professors at TRU"
- "What research areas does Professor Musfiq Rahman focus on?"
- "Tell me about the computer vision faculty at TRU"
- "Which courses are required for the Computer Science major?"
- "Who teaches artificial intelligence courses?"
- "Which professors work on machine learning?"
- "How can I contact prof Jaspreet Kaur?"


## Configuration

The following parameters can be adjusted in the code:

- **Chunk Size**: Minimum and maximum chunk sizes (default: 100-1000 characters)
- **Chunk Overlap**: Amount of text overlap between chunks (default: 20%)
- **Number of Results**: Number of relevant chunks to retrieve for each query (default: 5)
- **Embedding Model**: The sentence transformer model used (default: all-MiniLM-L6-v2)

## Technical Implementation

### Data Flow

1. **Scraping**: Web data is scraped using BeautifulSoup and formatted into text chunks.
2. **Chunking**: Each professor or course becomes a separate chunk with structured information.
3. **Indexing**: Chunks are embedded using the project's embedding model and indexed in FAISS.
4. **Retrieval**: User queries are embedded and used to find the most similar chunks in the database.
5. **Response Generation**: Retrieved chunks are used as context for the LLM to generate an appropriate response.

### Database Persistence

Conversation turns are stored in the `advisor_chat_history` table, with each logical session identified by a `chat_session_id` (UUID). The History tab groups rows by session ID to display and reload past conversations. Sessions cascade-delete when the owning user account is removed.

### Data Sources

By default, the system scrapes data from:
- Faculty listing pages (professor information)
- Curriculum/program pages (course information)

### File Structure

- `advisor_utils.py`: Contains scraping functions and vector database utilities
- `advisor_ai_feature.py`: Main UI implementation and logic
- `data/`: Directory for storing scraped chunks and vector database files

## Future Enhancements

- Support for custom website scraping through a user interface
- Enhanced prompt engineering for better answer quality
- Fine-tuning of vector search parameters
- Support for more complex academic data sources (research publications, department news, etc.)
- Multi-university support