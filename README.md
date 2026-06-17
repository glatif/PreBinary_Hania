# Prebinary × UReap Project

A multi-feature AI application for academic tasks, supporting both local LLMs through Ollama and cloud-based LLMs via API integration. The platform provides a full course and assessment management system with persistent database storage, enabling teachers and students to access AI-powered educational tools within a structured course context.

```
AI_Instructor/
├── app.py                # Main Streamlit application and navigation
├── app_validators.py     # Form validation logic for courses, assessments, and users
├── auth.py               # Authentication, user management, file storage, and course operations
├── db.py                 # Database connection factory (mysql.connector and SQLAlchemy)
├── schema_clean.sql      # Clean MySQL schema — creates all tables with no data
├── schema_demo.sql       # Demo schema — same as schema_clean.sql plus seeded demo accounts and courses
├── requirements.txt      # Python dependencies
├── data/                 # Runtime data storage (RAG indexes, narrated slideshow audio)
├── uploads/              # Uploaded files stored per course and assessment
├── archive/              # Original pre-integration project files (retained for reference)
├── src/                  # Source code
│   ├── features/         # Feature implementations
│   │   ├── rag/          # RAG feature code and documentation
│   │   ├── exam_grading/ # Exam grading feature code and documentation
│   │   ├── exam_creation/ # Exam creation feature code and documentation
│   │   ├── advisor_ai/   # Academic advisor AI feature code and documentation
│   │   ├── student_wellness/ # Student wellness services feature code and documentation
│   │   ├── quiz_generator/   # Practice quiz feature code and documentation
│   │   └── narrated_slideshow/ # Narrated slideshow feature code and documentation
│   └── utils/            # Shared utility functions
```

## Features

- **[RAG System (Retrieval Augmented Generation)](./src/features/rag/README.md)**: Query documents with semantic search (supports PDF, DOCX, PPTX, TXT)
- **[Exam Grading System](./src/features/exam_grading/README.md)**: Automate grading of student submissions
- **[Exam Creation System](./src/features/exam_creation/README.md)**: Generate variations of exam questions
- **[AdvisorAI](./src/features/advisor_ai/README.md)**: Access information about professors and courses through natural language queries
- **[Student Wellness Services](./src/features/student_wellness/README.md)**: Comprehensive guide to TRU's mental and physical health services with AI-powered assistance
- **[Practice Quiz](./src/features/quiz_generator/README.md)**: Upload study materials and generate personalized interactive quiz questions
- **[Narrated Slideshow Generator](./src/features/narrated_slideshow/README.md)**: Transform presentations into AI-narrated slideshows with synchronized audio and exportable HD video
- **Course & Assessment Management**: Full admin panel for managing users, courses, and assessments with role-based access control

## LLM Support

This application supports multiple LLM providers:

### Local Models (via Ollama)
- DeepSeek R1: 1.5B
- Llama 3.2

### Cloud Models (API Key Required)
- Groq (Llama 3.3-70B)
- Google Gemini 2.5 Flash
- OpenAI (GPT-4o)
- GitHub Models (GPT-4o)

## Setup Instructions

### 1. Install Ollama and Required Models (For Local LLM Support)

[Ollama](https://ollama.ai/) is required to run the local LLMs used by this application.

#### Installation

1. Download and install Ollama from [https://ollama.ai/](https://ollama.ai/)
2. Once installed, open a terminal and start the Ollama server:

```bash
ollama serve
```

Leave this terminal running. The server listens on localhost:11434 by default.

> **Note:** Ollama only needs to be running if you intend to use the local models (DeepSeek or Llama 3.2). If you plan to use cloud models only (Groq, Gemini, OpenAI, GitHub Models), you can skip running `ollama serve`. The application will start and function normally with only API keys configured.

#### Pull Required Models

In a new terminal, pull the models needed for the application:

```bash
ollama pull llama3.2
ollama pull deepseek-r1:1.5b
```

### 2. API Keys for Cloud Models (Optional)

To use cloud-based models, you'll need to obtain API keys:

- **OpenAI API Key**: Get your key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **GitHub Token**: Get your token from [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)
- **Groq API Key**: Get your key from [console.groq.com/keys](https://console.groq.com/keys)
- **Google Gemini API Key**: Get your key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

API keys are stored per user in the database and can be entered from the Profile page once logged in.

### 3. Set Up MySQL Database

The application requires MySQL 8.0 or later for all persistent data storage, including user accounts, courses, assessments, uploaded file records, and feature generation history.

#### Install MySQL

**macOS (using Homebrew):**
```bash
brew install mysql
brew services start mysql
```

**Windows:**

1. Download the MySQL Community Installer from [dev.mysql.com/downloads/installer](https://dev.mysql.com/downloads/installer/)
2. Run the installer and select "MySQL Server" from the product list
3. Follow the setup wizard, noting the root password you set during installation
4. MySQL will start automatically as a Windows service after installation

**Adding MySQL to your PATH (Windows only):**

After installation, the `mysql` command may not be recognised in your terminal. To fix this:

1. Open **System Properties** → **Advanced** → **Environment Variables**
2. Under **System variables**, select **Path** and click **Edit**
3. Click **New** and add the path to your MySQL `bin` directory. The default location is:
   ```
   C:\Program Files\MySQL\MySQL Server 8.0\bin
   ```
4. Click **OK** on all windows to save, then open a new terminal and run:
   ```bash
   mysql --version
   ```

On macOS and Linux, MySQL is added to the PATH automatically during installation.

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install mysql-server
sudo systemctl start mysql
sudo systemctl enable mysql
```

#### Initialise the Database

Once MySQL is running, choose the appropriate schema file and execute it to create the database, application user, all tables, and the seed accounts.

> **Note:** The schema creates a database user named `streamlit_user` with password `streamlit_pass`. These credentials are hardcoded in `db.py` and the application will use them automatically. If you need to use different credentials, update both the schema file and the `DB_CONFIG` dict in `db.py` before running either file.

**For a clean installation with no pre-existing data:**
```bash
mysql -u root -p < schema_clean.sql
```

**For a demo installation with pre-seeded accounts and courses:**
```bash
mysql -u root -p < schema_demo.sql
```

`schema_clean.sql` creates the full database structure and a single default admin account. It is the correct starting point for a fresh deployment where users and courses will be created through the application.

`schema_demo.sql` contains everything in `schema_clean.sql` plus two active teacher accounts (`teacher1`, `teacher2`), one active student account (`student1`), two courses, four assessments, and the course access records needed for all accounts to see their courses on login. It is intended for demonstrations and testing.

#### Default Admin Account

The schema seeds a default administrator account:

- **Username**: `admin`
- **Password**: `admin`

Log in with these credentials on first run to activate user accounts and configure courses.

#### Demo Account Details

Using schema_demo seeds default user accounts. 
For all accounts the username and password are identical:

- **Usernames**: `teacher1`, `teacher2`, `student1`

### 4. Set Up Python Environment

#### Ensure Python Version 3.11

Before proceeding, make sure you have Python 3.11 installed on your system. You can check your Python version by running:

```bash
python3 --version
```

If you do not have Python 3.11 installed, download it from the [official Python website](https://www.python.org/downloads/) and follow the installation instructions for your operating system.

#### For macOS

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

#### For Windows

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
venv\Scripts\activate
```

### 5. Install Dependencies

```bash
# Install all required packages
pip install -r requirements.txt
```

### 6. Install ffmpeg (Required for Video Export)

ffmpeg is required by the Narrated Slideshow feature to export MP4 videos. It is included automatically via the `imageio-ffmpeg` package in `requirements.txt` on most systems. If you see a "Couldn't find ffmpeg" error on startup, install it manually:

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**

1. Download a pre-built ffmpeg binary from [ffmpeg.org/download.html](https://ffmpeg.org/download.html) (select a Windows build, e.g. from gyan.dev)
2. Extract the archive to a permanent location, for example `C:\ffmpeg`
3. Add the `bin` folder to your PATH using the same steps as MySQL above:
   ```
   C:\ffmpeg\bin
   ```
4. Open a new terminal and run `ffmpeg -version` to confirm it is recognised

**Linux (Ubuntu/Debian):**
```bash
sudo apt install ffmpeg
```

> **Note:** If you do not plan to use the video export feature, this step can be skipped. The application will start normally and all other features will work without ffmpeg. Video export will be disabled but the rest of the Narrated Slideshow feature remains available.

### 7. Run the Application

Make sure Ollama is running in a separate terminal with the `ollama serve` command, then:

```bash
# Start the Streamlit app
streamlit run app.py
```

The application should open in your default browser at http://localhost:8501

## Database Structure

The application uses a MySQL database (`streamlit_database`) with the following table structure:

- **users** — user accounts with roles (admin, teacher, student), API keys, and per-feature model preferences
- **courses** — courses created by instructors, each with a unique code and status
- **assessments** — assessments belonging to a course; cascade-deleted when a course is deleted
- **files** — metadata for files uploaded to a specific assessment, scoped by feature name
- **course_access** — access control records granting teachers and students access to courses
- **quizzes / quiz_questions / quiz_submissions / quiz_answers** — published quiz infrastructure
- **rag_indexes** — per-user FAISS index directory tracking for the RAG feature
- **rag_query_history** — per-user RAG conversation history, grouped by session
- **exam_grading_results** — per-student grading results grouped by session, linked to assessment
- **exam_creation_questions** — generated exam questions grouped by session, linked to assessment
- **advisor_chat_history** — Advisor AI conversation turns per user, grouped by session
- **wellness_chat_history** — Student Wellness conversation turns per user, grouped by session
- **practice_quiz_generated** — generated practice quizzes linked to assessment and user
- **practice_quiz_attempts** — student quiz attempts linked to a generated quiz

All feature history tables cascade-delete when the parent assessment is deleted, ensuring no orphaned records are left behind.

## Project Structure

```
AI_Instructor/
├── app.py                # Main Streamlit application and navigation
├── app_validators.py     # Form validation logic for courses, assessments, and users
├── auth.py               # Authentication, user management, file storage, and course operations
├── db.py                 # Database connection factory (mysql.connector and SQLAlchemy)
├── schema_clean.sql      # Clean MySQL schema — creates all tables with no data
├── schema_demo.sql       # Demo schema — same as schema_clean.sql plus seeded demo accounts and courses
├── requirements.txt      # Python dependencies
├── data/                 # Runtime data storage (RAG indexes, narrated slideshow audio)
├── uploads/              # Uploaded files stored per course and assessment
├── archive/              # Original pre-integration project files (retained for reference)
├── src/                  # Source code
│   ├── features/         # Feature implementations
│   │   ├── rag/          # RAG feature code and documentation
│   │   ├── exam_grading/ # Exam grading feature code and documentation
│   │   ├── exam_creation/ # Exam creation feature code and documentation
│   │   ├── advisor_ai/   # Academic advisor AI feature code and documentation
│   │   ├── student_wellness/ # Student wellness services feature code and documentation
│   │   ├── quiz_generator/   # Practice quiz feature code and documentation
│   │   └── narrated_slideshow/ # Narrated slideshow feature code and documentation
│   └── utils/            # Shared utility functions
```

## Feature Documentation

For detailed information about each feature, refer to the specific documentation:

- [RAG System Documentation](./src/features/rag/README.md)
- [Exam Grading System Documentation](./src/features/exam_grading/README.md)
- [Exam Creation System Documentation](./src/features/exam_creation/README.md)
- [Advisor AI Documentation](./src/features/advisor_ai/README.md)
- [Student Wellness Services Documentation](./src/features/student_wellness/README.md)
- [Practice Quiz Documentation](./src/features/quiz_generator/README.md)
- [Narrated Slideshow Generator Documentation](./src/features/narrated_slideshow/README.md)

## Recent Updates

### Prebinary Integration — Course & Assessment Management
- Full MySQL database backend replacing all local file and session-state persistence
- Admin panel for user management: create, edit, activate/deactivate accounts, and set per-user model preferences
- Course management: create, edit, duplicate, and delete courses with full cascade cleanup of all linked data and uploaded files
- Assessment management: create, edit, and delete assessments with full cascade cleanup
- Course access control: grant or revoke teacher and student access per course
- Course duplication copies all assessments, uploaded files, and feature generation history to the new course, with assessment IDs and session identifiers remapped for full independence
- Per-user model preferences: administrators can configure the default AI model for each feature on a per-user basis, stored in the database and loaded at login
- Profile page: users can manage personal information, API keys, model preferences, and password from a single location

### File Persistence for Exam Creation and Practice Quiz
- Source files uploaded in Exam Creation and Practice Quiz are saved to the assessment directory and stored in the database
- Saved files can be reused across sessions without re-uploading, scoped per assessment and feature
- Files can be managed (viewed and deleted) from within each feature

### Exam Grading History
- Grading sessions are persisted to the database and displayed in a History tab per assessment
- Load Setup button restores the exam questions and rubric from any previous session for immediate reuse
- Sessions can be downloaded as CSV or deleted individually

### Exam Creation History
- Generated question sets are persisted to the database and displayed in a History tab per assessment
- Individual questions can be edited inline, and sessions can be downloaded as JSON or deleted

### Practice Quiz History
- Generated quizzes and student attempts are persisted to the database
- My History tab shows all attempts by the current user with full question-by-question review
- Student Attempts tab (instructor/admin only) shows all student attempts across the assessment

### Chat History for Advisor AI and Student Wellness
- Conversation sessions are persisted to the database
- History tab shows all past sessions; sessions can be loaded and continued or deleted

### New Narrated Slideshow Generator Feature
- Added comprehensive auto-narrated slideshow creation from PDF/PowerPoint files
- **NEW: HD Video Export** - Generate downloadable MP4 videos with synchronized audio and smooth transitions
- AI-powered narration generation with education-level awareness (High School to PhD)
- Integrated Text-to-Speech with Google TTS and support for premium providers (ElevenLabs, Cartesia)
- Interactive slideshow player with synchronized audio playback
- Support for both PDF (up to 25 pages) and PowerPoint (up to 20 slides) files
- Complete workflow from file upload to playable slideshow or downloadable video

### New OpenAI GPT-4o Integration
- Added support for OpenAI's GPT-4o model via direct API
- Added support for GitHub Models GPT-4o endpoint as alternative
- Integrated API key and GitHub token management in the sidebar
- Full streaming support for real-time responses from both endpoints

### Per-Feature Model Selection
- Added model selection preferences for each feature
- Persistent model preferences saved to the database per user
- Easy switching between local and cloud models

### Multi-Language Support
- Added language selection for RAG System, Advisor AI, and Student Wellness features
- Support for English, French, Arabic, and Hindi responses
- Language-aware prompt engineering for better quality responses

### Enhanced File Format Support
- RAG System now supports PDF, DOCX, PPTX, and TXT files
- Unified document processing across features
- Improved content extraction and validation

### New Quiz Generator Feature
- Upload study materials (PDF, DOCX, PPTX, TXT) and generate personalized quiz questions
- Support for multiple question types: Multiple Choice, True/False, and Short Answer
- Customizable difficulty levels and topic filtering
- Interactive quiz interface with immediate feedback and scoring
- Integration with both local and cloud-based LLM models

### New Student Wellness Services Feature
- Comprehensive information portal for TRU's mental and physical health services
- AI-powered wellness assistant for personalized guidance
- Search functionality for quick service discovery
- Emergency contacts and crisis support information
- Integration with both local and cloud-based LLM models

### Cloud LLM Integration
- Added support for Groq-hosted Llama 3.3-70B model
- Added support for Google's Gemini 2.5 Flash model
- Integrated API key management in the sidebar

### RAG System Improvements
- Enhanced document management with ability to view and select previously ingested documents
- Added document deletion functionality
- Fixed issues with new document ingestion

### New Exam Creation Feature
- Generate variations of existing exam questions
- Create new exam questions from lecture topics/content
- Configure difficulty levels and number of questions
- Export results in JSON format for easy integration with other systems

## Recent Updates by Hania

Recent updates to the exam grading feature include expanded upload support for PDF, Word, PowerPoint, text files, and ZIP folders with internal folder handling. The AI question creation workflow has also been updated to support formatting existing questions and generating new questions from uploaded learning material.

For full details, see [UPDATES_README.md](UPDATES_README.md).