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
- **[Exam Grading System](./src/features/exam_grading/README.md)**: Automate grading of student submissions (accepts PDF, Word, PowerPoint, text, and ZIP — including subfolders — for both question papers and student submissions)
- **[Exam Creation System](./src/features/exam_creation/README.md)**: Generate variations of exam questions
- **Oral Examination**: AI generates questions from teacher-uploaded material (PDF/Word/PPT/text/ZIP); students answer by speaking while the questions are read aloud via TTS, with per-question time limits, auto-submit, skip, and retry-transcription options; teachers grade all transcripts in one batch against a rubric, with results including score, feedback, a proctoring summary, and a History tab. Requires a Groq or OpenAI API key on the student's profile for transcription (or Ollama running `deepseek-r1:1.5b` if using the local model for question generation)
- **[AdvisorAI](./src/features/advisor_ai/README.md)**: Access information about professors and courses through natural language queries — admins can add URLs one at a time, in bulk, as `Label | URL`, or via `.txt` upload, with a fallback scraper for non-standard webpages
- **[Student Wellness Services](./src/features/student_wellness/README.md)**: Comprehensive guide to TRU's mental and physical health services with AI-powered assistance
- **[Practice Quiz](./src/features/quiz_generator/README.md)**: Upload study materials and generate personalized interactive quiz questions
- **[Narrated Slideshow Generator](./src/features/narrated_slideshow/README.md)**: Transform presentations into AI-narrated slideshows with synchronized audio and exportable HD video
- **Course & Assessment Management**: Full admin panel for managing users, courses, and assessments with role-based access control
- **Identity Verification**: Verifies students during quiz/exam submission against any government-issued ID — matching face, name, and ID number, and checking the expiry date where applicable; saves the actual ID-card and selfie photos (not just OCR/match results), viewable by instructors via an expander on review screens
- **Student Verification (Quiz Submission)** *(in progress)*: Verifies students via student card before/during quiz submission; not fully wired up yet
- **Proctoring**: Tab-switch and screen-share monitoring, eye movement tracking, plus keystroke logging (sent every ~15s), mic audio recording (10s clips, kept only if speech is detected), and screen+webcam video recording (30s segments, admin-configurable quality, ~2hr cap). Instructors can stitch segments into full recordings (screen, webcam+audio, or combined picture-in-picture). Heavy analysis runs in the background every 15 minutes or on-demand via Admin Panel → Maintenance. Teachers/admins can delete a student's monitoring data per attempt/assessment, in addition to the existing bulk age-based cleanup
- **Attempt Logging**: Tracks the full lifecycle of quiz/oral exam attempts (started, question reached, submitted, timed out, skipped, completed), so teachers can see who started but didn't finish
- **Email & Password Reset (SMTP)**: Admin-configurable Gmail SMTP settings send temp-password emails on roster import/admin resets, plus a self-service "Forgot password?" flow for users
- **Roster Import**: Instructors upload a CSV/XLSX class list (First Name, Last Name, ID Number, Email); matching students are enrolled and new ones get accounts created, with validation, conflict detection, credential resend, and a per-row Include checkbox to exclude rows before committing
- **Gradebook**: Per-course CSV export combining every quiz/exam/oral exam grade into one row per student, aggregated across all assessment types
- **Plagiarism Scan**: On-demand similarity check across student submissions on the same assessment using local sentence embeddings, with an LLM-generated explanation for pairs above the similarity threshold
- **Access Codes**: Instructors can require an optional access code before a student can start a quiz or exam
- **Admin Privacy & Permission Controls**: Admins can toggle whether ID-card/selfie photos from identity verification are persisted to disk (OCR/face-match still runs either way), whether proctoring captures webcam video at all (vs. screen-only), and can globally lock instructors out of enabling verification/proctoring for their own assessments

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

> **Note:** A Groq or OpenAI key under **Profile → AI API Keys** is required for any account taking an Oral Examination (used for transcription).

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

#### Updating an Existing Database

`schema_clean.sql` and `schema_demo.sql` create every table the application needs (including Oral Exam, Attempt Log, Verification Photos, and Audio/Video Proctoring tables) directly, so a **fresh** database never needs any `migration_add_*.sql` files run by hand.

If you have an **existing database** you want to keep data in, run the relevant `migration_add_*.sql` files instead of recreating the schema:

- `migration_add_proctor_analysis_status.sql` must run **after** `migration_add_audio_proctoring.sql` and `migration_add_video_proctoring.sql`, since it alters their tables
- `migration_add_proctor_video_quality_setting.sql` can run at any time
- `migration_add_course_platform_v2.sql` can run at any time (SMTP settings, roster import support, gradebook, plagiarism results, access codes)
- `migration_add_verification_proctoring_settings.sql` can run at any time (verification photo storage toggles, webcam recording toggle, instructor permission locks)

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
- **exam_setups** — saved exam grading setup (questions/rubric) per session, linked to assessment
- **exam_grading_results** — per-student grading results grouped by session, linked to assessment
- **exam_creation_questions** — generated exam questions grouped by session, linked to assessment
- **advisor_chat_history** — Advisor AI conversation turns per user, grouped by session
- **wellness_chat_history** — Student Wellness conversation turns per user, grouped by session
- **practice_quiz_generated** — generated practice quizzes linked to assessment and user
- **practice_quiz_attempts** — student quiz attempts linked to a generated quiz
- **oral_exam_setups / oral_exam_responses / oral_exam_grading_results** — oral exam sessions, generated questions, per-question student answers/transcripts, and batch grading against a rubric
- **assessment_attempt_log** — full lifecycle tracking (started, question reached, submitted, timed out, skipped, completed) for quiz and oral exam attempts
- **verification_attempts** — identity verification records: stored ID-card and selfie photos, matched face/name/ID number, and expiry check result where applicable
- **quiz_proctor_events** — tab-switch and screen-share monitoring events
- **quiz_proctor_keystrokes** — logged keystrokes (sent every ~15s, not per keypress)
- **quiz_proctor_mouse_events** — mouse activity captured during proctored attempts
- **quiz_proctor_frames** — captured frames used for eye movement tracking
- **quiz_proctor_webcam_frames** — captured webcam frames for proctoring analysis
- **quiz_proctor_audio_clips** — recorded mic audio clips (10s, kept only if speech is detected)
- **quiz_proctor_video_segments** — recorded screen+webcam video segments (30s, admin-configurable quality tier, ~2hr cap)
- **app_settings** — single-row table for SMTP sender credentials, identity-verification photo storage toggles, and instructor permission locks (verification/proctoring)
- **proctor_settings** — single-row table for admin-configurable proctoring video quality tier and webcam recording toggle
- **plagiarism_results** — pairwise similarity scores and LLM-generated overlap explanations between student submissions on the same assessment, keyed by assessment/feature/student pair

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

### Admin Controls — Verification Photo Storage, Webcam Recording, Instructor Locks
- Admins can toggle whether the ID-card photo and/or selfie captured during identity verification are saved to disk — OCR text reading and face-match comparison always run regardless, only whether the image itself is kept afterward is affected
- Admins can toggle whether proctoring captures webcam video at all (continuous video, periodic frames, face/gaze analysis) versus screen-only; when off, students are never asked for camera permission, and mic recording is unaffected
- Admins can globally lock instructors out of requiring identity verification or enabling proctoring for their own exams, quizzes, and oral exams — when locked, the effective setting is forced off at runtime regardless of what any individual assessment has stored
- All three controls live in Admin Panel → Maintenance

### Email / Password Reset, Roster Import, Gradebook, Plagiarism Scan, Access Codes
- Admin-configurable Gmail SMTP settings (Admin Panel → Maintenance) power temp-password emails on roster import/admin resets, plus a self-service "Forgot password?" flow on the login page
- Roster import: instructors upload a CSV/XLSX class list (First Name, Last Name, ID Number, Email); existing accounts are enrolled and new ones are created in one pass, with column-alias detection, validation/preview before commit, ID-number conflict detection, and credential resend. The preview table has a per-row "Include" checkbox so individual rows can be excluded before committing, plus a separate checkbox to opt into updating name/ID number on existing accounts that differ from the file (off by default — matching accounts are enrolled without overwriting their data)
- Gradebook: per-course CSV export with one row per enrolled student and one column per assessment, aggregating Practice Quiz, Exam Grading, and Oral Examination scores into a single download
- Plagiarism scan: on-demand pairwise similarity check across student submissions on the same assessment using the app's local sentence-embedding model (no paid API needed), with an LLM-generated explanation for pairs above the similarity threshold — run from Admin Panel → Maintenance → "Run Plagiarism Scan"
- Access codes: instructors can require an optional access code before a student can start a quiz or exam
- Exam grading results now include a per-question breakdown table

### Exam Grading
- Now accepts PDF, Word, PowerPoint, text, and ZIP (with subfolders) for both question papers and student submissions, not just PDF

### Advisor AI
- Admins can add URLs one at a time, in bulk, as `Label | URL`, or via `.txt` upload
- Added a fallback scraper for non-standard webpages
- URLs persist across app reloads

### Narrated Slideshow Generator
- Video narration is fixed and working again

### Student Verification (Quiz Submission)
- New feature (in progress): verifies students via student card before/during quiz submission — not fully wired up yet

### Proctoring — Keystroke Tracking
- Logs keystrokes (sent every ~15s, not per keypress) alongside existing tab-switch, screen-share, and eye movement monitoring
- Teachers/admins can now delete a student's monitoring data per attempt/assessment, in addition to the existing bulk age-based cleanup

### Proctoring — Audio/Video Recording
- Records actual mic audio (10s clips, kept only if speech detected) and screen+webcam video (30s segments, admin-configurable quality, ~2hr cap)
- Instructors can stitch segments into full recordings (screen, webcam+audio, or combined picture-in-picture) via a button
- Heavy analysis now runs in the background (every 15 min) or on-demand via Admin Panel → Maintenance → "Run Proctoring Analysis Now," instead of slowing down live monitoring

### Oral Examination (New Feature/Tab)
- AI generates questions from teacher material; students answer by speaking; AI grades transcripts
- Questions are read aloud (TTS), mic stays on the whole time, recording starts automatically per question
- Per-question time limits with auto-submit, plus a Skip option and retry transcription if it fails
- Teachers can upload source files (PDF/Word/PPT/text/ZIP) for question generation
- Students need a Groq or OpenAI API key saved on their profile for transcription — warned upfront if missing
- Teachers grade all answers in one batch against a rubric; results include score, feedback, proctoring summary, and a History tab
- Shows students who started but never finished

### Identity Verification
- Verifies against any government-issued ID, matching face, name, and ID number, and checking the expiry date where applicable
- Now saves the actual ID-card and selfie photos (not just OCR/match results)
- Instructors can view them via a new expander on review screens

### Attempt Logging
- New log tracks the full lifecycle of quiz/oral exam attempts (started, question reached, submitted, timed out, skipped, completed), so teachers can see who started but didn't finish

### Proctoring — Configurable Video Quality 
— Admins can now pick a Low (360p)/Medium (480p, previous default)/High (720p) recording quality for proctoring screen+webcam video, from Admin Panel → Maintenance → "Video Recording Quality." Only applies to sessions that start recording after the change — a session already recording keeps using whatever tier was active when it started.

### Reliability Fixes
- Fixed a bug where long exam results could silently fail to save
- Save failures are now reported separately from grading failures
- All LLM/transcription calls now timeout after 120s instead of hanging

### Database Schema
- `schema_clean.sql` and `schema_demo.sql` now create every table this update needs (oral exam, attempt log, verification photos, audio/video proctoring) directly, so a fresh database no longer requires running any `migration_add_*.sql` files by hand
- `schema_demo.sql` was also brought up to date with older proctoring tables it had been missing

### Proctoring — Configurable Video Quality
- Admins can now pick a Low (360p)/Medium (480p, previous default)/High (720p) recording quality for proctoring screen+webcam video, from Admin Panel → Maintenance → "Video Recording Quality"
- Only applies to sessions that start recording after the change — a session already recording keeps using whatever tier was active when it started

### Setup Needed Before Using
- **Fresh server / new database**: just run `schema_clean.sql` (or `schema_demo.sql` for seeded demo accounts) as usual — everything is already included
- **Existing database you want to keep data in**: run the new `migration_add_*.sql` files instead of recreating the schema (see [Updating an Existing Database](#updating-an-existing-database) above)
- Add a Groq or OpenAI key under **Profile → AI API Keys** for any account taking an oral exam
- If using the local model for oral exam questions, make sure Ollama is running with `deepseek-r1:1.5b` pulled
- `pip install -r requirements.txt` picks up new packages automatically (no manual downloads needed)
- To send temp-password/forgot-password emails, configure a sending Gmail address and app password under **Admin Panel → Maintenance → Email (SMTP) Settings**. Roster import, password reset, and the login page's "Forgot password?" flow all fail gracefully with a clear error until this is set

## Deployment (Ubuntu Server, Docker)

For running locally, see [Setup Instructions](#setup-instructions) above. To deploy to a production Ubuntu server using Docker, follow these steps. Full details, troubleshooting, and firewall notes are in `DEPLOYMENT.md`.

**Current server:** Ubuntu (Docker), `144.217.80.160`, app served at `http://144.217.80.160:8501`. Access is via SSH (PuTTY) and SFTP (WinSCP). Credentials are kept in the team's password manager / server `.env` file, not in the repo.

> **Note:** This replaces the earlier IONOS server (`74.208.142.195`), which is no longer the deployment target.

1. **Install local tools** — [PuTTY](https://www.putty.org/) (SSH client) and [WinSCP](https://winscp.net/) (SFTP client).
2. **Connect to the server** — open PuTTY, host `144.217.80.160`, port `22`, log in as `root`.
3. **Initial server setup (one-time)** — `apt update && apt upgrade -y`, reboot if prompted, then add a swap file (recommended for low-RAM servers running ML dependencies).
4. **Install Docker** — add Docker's official apt repo and GPG key, then `apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin`. If `docker.service` fails with a socket-activation error, run `systemctl enable docker.socket && systemctl start docker.socket && systemctl start docker.service`.
5. **Configure the firewall** — `ufw allow OpenSSH`, `ufw allow 8501/tcp`, `ufw allow 80/tcp`, `ufw allow 443/tcp`, then `ufw --force enable`. ⚠️ If the app still isn't reachable publicly afterward, check for a **provider-level firewall** in your hosting control panel — `ufw` rules alone are not enough.
6. **Upload the application** — via WinSCP (SFTP) to `/opt/app`. Upload all `.py` files, `src/`, `requirements.txt`, `*.sql` schema/migration files, and `data/`. Exclude `venv/`, `__pycache__/`, `.git/`, `archive/`, `results/`, `temp_uploads/`, and `uploads/` (local/generated — the container creates its own).
7. **Set environment variables** — create `/opt/app/.env` on the server (never committed to GitHub) with `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, and `MYSQL_ROOT_PASSWORD`. Per-user API keys (Groq, Gemini, OpenAI, GitHub, ElevenLabs, Cartesia) are stored in the database via the app's Profile page — no server-side action needed for those.
8. **Docker files** — `Dockerfile` and `docker-compose.yml` are already committed at the project root and don't need to be recreated. `docker-compose.yml` runs a `db` service (MySQL 8.0, auto-imports `schema_clean.sql` on first run) and an `app` service (the Streamlit app, exposed on port `8501`).
9. **Build and run**:
   ```bash
   cd /opt/app
   docker compose up -d --build
   ```
   The first build can take several minutes up to ~40 minutes depending on server specs, since the app's ML dependencies (torch, tensorflow, deepface, mediapipe) are heavy.
10. **Verify the deployment**:
    ```bash
    docker ps                              # both containers should show "Up"
    docker compose logs app --tail=50      # look for "You can now view your Streamlit app"
    curl -I http://localhost:8501          # should return HTTP/1.1 200 OK
    ```
    Then check public access at `http://144.217.80.160:8501`, and confirm the schema imported correctly with:
    ```bash
    docker exec -it app-db-1 mysql -u streamlit_user -p streamlit_database -e "SHOW TABLES;"
    ```

### Common Operations

| Task | Command |
|---|---|
| View logs | `docker compose logs -f app` |
| Restart app | `docker compose restart app` |
| Stop everything | `docker compose down` (⚠️ does not delete DB volume) |
| Rebuild after code changes | `docker compose up -d --build` |
| Check container status | `docker ps` |
| Check server firewall | `ufw status` |

### Troubleshooting

| Symptom | Likely Cause |
|---|---|
| `Cannot connect to Docker daemon` | Docker service not running — see step 4 fix above |
| App builds but isn't reachable publicly | Provider-level firewall blocking the port — check your hosting control panel, not just `ufw` |
| `Access denied` connecting to MySQL manually | Check `.env` values match exactly; confirm via `docker exec app-db-1 env \| grep MYSQL` |
| Container restarts in a loop | Check `docker compose logs app` for the actual Python error |
| Slow build | Expected — the dependency list (torch/tensorflow/deepface/mediapipe) is large; not a hang |

### Notes on Server Migrations

- The app moved from the original IONOS server (`74.208.142.195`) to the current server (`144.217.80.160`) — this process is server-agnostic, so a future move just repeats steps 1–10 on the new host.
- Each server has its own independent MySQL database (via the Docker `db` service) — user accounts, courses, and any password changes made on one server (including local development) do **not** carry over to another. Always confirm which server/database you're testing against before assuming a login or data change applies everywhere.
- If a new server has more RAM, the swap file (step 3) is optional but still a good safety net.
- Confirm whether a new server's provider also has a separate network-level firewall before assuming `ufw` rules are sufficient.
- Consider adding a reverse proxy (Nginx) + SSL/domain at this stage instead of exposing port `8501` directly.