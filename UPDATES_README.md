# Project Updates - Exam Grading Feature

## Updated By
Hania Rasheed 

## Summary of Changes
This update expands the exam grading feature from PDF-only support to a wider multi-file upload system. The system now supports PDF, Word documents, PowerPoint files, text files, and ZIP folders with internal sub-folder handling.

## Features Added

### 1. Expanded File Upload Support
The grading upload system now supports:
- PDF files
- Word documents
- PowerPoint files
- Text files
- ZIP folders

This applies to:
- Question paper upload
- Student submission upload
- ZIP-based upload workflow

### 2. ZIP Folder Processing
ZIP upload support has been improved to detect supported files inside internal folders and sub-folders. The system scans the ZIP structure, extracts supported files, and processes their text content.

### 3. Structured Text Extraction
Extracted content from multiple files is combined using filename separators. This helps the AI identify which content belongs to each uploaded file and improves multi-file question extraction.

### 4. AI Question Creation Workflow
Teachers can now either:
- Format existing questions from uploaded material
- Generate new questions using a custom prompt

Supported generated question types include:
- Multiple-choice questions
- True/false questions
- Short-answer questions

### 5. PowerPoint Question Handling
The AI prompt has been improved to better recognise question-style content in PowerPoint slides. This includes slide titles, bullet points, and multiple-choice options such as A, B, C, and D.

## Current Status
The main functionality is working for the most part, but further testing is still required across different file combinations and ZIP folder structures.

## Testing Required
Further testing should be carried out for:
- AI-generated MCQs, true/false, and short-answer questions
- AI based grading and feedback

## Notes
Some edge cases may still need checking, especially files with unusual formatting, nested ZIP folders, unsupported file types, or PowerPoint slides with non-standard layouts.

---

# Project Updates - Oral Examination Feature

## Updated By
Hania Rasheed

## Summary of Changes
This update adds a new Oral Examination feature as its own tab in the main dashboard, alongside Exam Grading, Exam Creation, and Practice Quiz. An AI generates open-ended exam questions from teacher-provided material, students answer by speaking into their microphone while the existing proctoring system (screen share, webcam with eye/gaze tracking, keystrokes, and mouse activity) monitors the session, and the AI grades the transcribed answers once the teacher runs grading.

## Features Added

### 1. AI Question Generation
Teachers enter a topic or source material and the AI generates a set number of open-ended, spoken-answer questions (no multiple choice or true/false), with a difficulty level and a grading rubric. Questions can be reviewed, edited, added to, or removed before saving.

### 2. Spoken Student Answers
Students answer one question at a time using the browser's built-in microphone recorder. Questions are only revealed one at a time and are not shown in advance, matching how a real oral exam works. Once a student has answered every question, the exam is locked — there is no re-submission.

### 3. Speech-to-Text Transcription
Recorded answers are transcribed to text automatically using Groq's or OpenAI's Whisper API (Groq is preferred when both are available). Students need a Groq or OpenAI API key saved on their account for this to work, and are now warned up front — before identity verification and recording — if neither key is set.

### 4. Full Proctoring Reuse
The oral exam session is monitored using the same proctoring system already used by Exam Grading: screen-share capture, webcam capture with face/eye-gaze and head-pose analysis, keystroke logging, and mouse activity logging. No proctoring code was duplicated — the existing functions are called directly.

### 5. AI Grading
Teachers grade all completed student responses in one batch. Each answer is scored against the saved rubric using the same grading logic as Exam Grading, and results include a per-question score, feedback, and detailed explanation, plus each student's proctoring summary (tab-switch warnings, camera/gaze flags, keystrokes, and mouse activity) for review alongside their grade.

### 6. Grading History
Past grading runs for an assessment can be revisited in a History tab, showing each student's per-question breakdown and total score.

## Current Status
The feature is fully built and wired into the dashboard, and the required database tables have been created on the local database. Manual testing surfaced and fixed two real issues: AI question generation was initially returning only 1 question instead of the requested number (caused by an incorrect JSON-mode flag plus a local model needing a more explicit prompt), and students were only finding out they needed an API key after already recording an answer rather than before. Both are fixed and verified.

## Testing Required
Further testing should be carried out for:
- The full student flow end-to-end with a Groq or OpenAI key configured, including transcription accuracy
- AI question generation reliability across different models (cloud models vs. small local Ollama models)
- Batch grading across a full class-sized set of students and questions
- Teachers editing/re-saving questions after students have already started answering (a warning is shown, but the underlying question numbering has no versioning)
- Concurrent or repeated submissions for the same question (a database constraint now prevents duplicate rows, but this hasn't been tested under real concurrent use)

## Notes
Speech-to-text currently requires a Groq or OpenAI API key — there is no offline/local transcription option, to avoid adding heavy dependencies that could conflict with the app's existing pinned packages. Audio files are saved to disk per response even if transcription fails, so a failed transcription never loses the student's recording.