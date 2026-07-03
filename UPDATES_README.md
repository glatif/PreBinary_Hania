# Project Updates

## Updated By

Hania Rasheed

## Overview

This document summarises the latest updates made across the AI Instructor system. The main areas updated include:

* Exam Grading Feature
* Advisor AI Feature
* Narrated Slideshow Generator
* Student Verification for Quiz Submission
* Proctoring: Keystroke Tracking and Monitoring Data Controls
* Oral Examination Feature

The updates focus on improving upload flexibility, URL scraping, slideshow narration, video generation, quiz submission verification, proctoring monitoring, monitoring data management, and adding a new fully proctored, AI-graded oral examination workflow.

---

# 1. Exam Grading Feature

## Summary

The exam grading feature has been expanded from PDF-only upload to support multiple file types. The system now supports:

* PDF
* Word documents
* PowerPoint files
* Text files
* ZIP folders with internal folders/sub-folders

This applies to question paper uploads, student submission uploads, and ZIP-based upload workflows.

## Current Status

The upload and question-processing workflow is working for the most part. The system can extract and organise text from different file types using filename separators, which helps the AI understand where each piece of content came from.

## Testing Still Required

* Word, PowerPoint, text, and ZIP uploads
* ZIP folders with internal folders
* Mixed file types inside ZIP folders
* Question extraction and generation
* AI grading and feedback accuracy
* Matching student submissions with the correct questions

---

# 2. Advisor AI Feature

## Summary

The Advisor AI feature has been improved to support more flexible URL management and webpage scraping.

Admins can now add URLs through:

* Single URL entry
* Bulk URL paste
* `Label | URL` format
* `.txt` file upload

A generic scraping fallback has also been added, so the system can process pages that do not match the original TRU-specific layouts.

## Current Status

The URL management and scraping workflow is working for the most part. Admin-added websites can now be saved using `websites.json`, so they remain available after the app reloads.

## Testing Still Required

* Generic webpage scraping reliability
* Rebuilding the FAISS index across all sources
* Website persistence after reload
* Handling unusual, broken, or low-content webpages

---

# 3. Narrated Slideshow Generator

## Summary

The Narrated Slideshow Generator has been improved. The video narration feature has been fixed and is now working.

The update improves the slideshow generation workflow by making narration and video generation more reliable.

## Current Status

The video narration feature is now working. Further testing is still required with larger slide decks and different input types.

## Testing Still Required

* Longer presentations
* Larger slide decks
* Audio timing and narration consistency
* Final video export reliability
* Missing or incomplete narration handling

---

# 4. Student Verification for Quiz Submission

## Summary

A new student verification feature has been started for quiz submission. The feature uses a student card to verify the student before or during quiz submission.

## Current Status

The initial student verification functionality has been added and pushed to Git. More work is needed to complete the full workflow and connect it properly with quiz submission.

## Testing Still Required

* Student card input handling
* Verification accuracy
* Invalid or unclear student card cases
* Quiz submission integration
* Error messages and user flow

---

# 5. Proctoring: Screen Sharing, Tab Switching and Keystroke Tracking and Monitoring Data Controls

## Summary

Keystroke tracking has been added to the existing proctoring workflow. This works alongside the current tab-switch/focus-loss detection and screen-share monitoring.

The keystroke tracking is active from identity verification through final submission in both:

* Practice Quiz flow
* Exam Grading “Submit My Exam” flow

## Current Status

Keystrokes are batched and flushed client-side approximately every 15 seconds instead of being sent on every keypress. This helps reduce lag while the student is typing.

Instructors can now review logged keystrokes alongside tab-switch counts and screen capture frames on the Student Attempts and Student Submissions screens.

Admins and teachers can also permanently delete a student’s monitoring data directly from the review screen. This can be done:

* Per attempt for Practice Quiz
* Per assessment for Exam Grading

This is in addition to the existing age-based bulk cleanup option in the Admin Panel.

## Testing Still Required

* Keystroke logging during full quiz and exam submission flows
* Behaviour after identity verification
* Client-side batching and flushing reliability
* Instructor review screen display
* Monitoring data deletion per attempt
* Monitoring data deletion per assessment
* Compatibility with existing age-based cleanup in the Admin Panel

---

# 6. Oral Examination Feature

## Summary

A new Oral Examination feature has been added as its own tab in the main dashboard, alongside Exam Grading, Exam Creation, and Practice Quiz. An AI generates open-ended exam questions from teacher-provided material, students answer by speaking into their microphone, and the AI grades the transcribed answers once the teacher runs grading.

The feature reuses the existing proctoring system rather than duplicating it, so the same monitoring already used by Exam Grading — screen-share capture, webcam with face/eye-gaze and head-pose analysis, keystroke logging, and mouse activity logging — runs for the full oral exam session.

## Current Status

The feature is fully built and wired into the dashboard, and the required database tables have been created. Questions are revealed to students one at a time and are not shown in advance; once a student has answered every question the exam is locked, with no re-submission.

Recorded answers are transcribed automatically using Groq's or OpenAI's Whisper API (Groq preferred when both are available) — students need one of these keys saved on their account, and are now warned up front, before identity verification and recording, if neither is set.

Teachers grade all completed responses in one batch against a saved rubric, using the same grading logic as Exam Grading. Results include a per-question score, feedback, and detailed explanation, plus each student's proctoring summary for review alongside their grade. Past grading runs can be revisited in a History tab.

Manual testing surfaced and fixed two real issues: AI question generation was initially returning only 1 question instead of the requested number (caused by an incorrect JSON-mode flag plus a local model needing a more explicit prompt), and students were only finding out they needed an API key after already recording an answer rather than before. Both are fixed and verified.

## Setup Required

Pulling the latest code is not enough on its own to get this feature working — the following steps are also needed on any machine running this app for the first time after this update:

* Run the new migration once against the app's MySQL database, in addition to every other `migration_add_*.sql` file already required by this project (there is no automated migration runner):
  ```
  mysql -u streamlit_user -p streamlit_database < migration_add_oral_examination.sql
  ```
* Save a Groq or OpenAI API key under Profile → AI API Keys on any account that will take an oral exam — this is stored per-user in the database and does not come across with the code, and transcription will not work without it.
* If using the default local model (DeepSeek via Ollama) for question generation, make sure Ollama is running locally with `deepseek-r1:1.5b` pulled; otherwise select a cloud model that account has a saved key for.
* No new Python packages were added, so a normal `pip install -r requirements.txt` is sufficient — no extra dependency setup is required.

## Testing Still Required

* Full student flow end-to-end with a Groq or OpenAI key configured, including transcription accuracy
* AI question generation reliability across different models (cloud models vs. small local Ollama models)
* Batch grading across a full class-sized set of students and questions
* Teachers editing/re-saving questions after students have already started answering (a warning is shown, but question numbering has no versioning)
* Concurrent or repeated submissions for the same question (a database constraint now prevents duplicate rows, but this hasn't been tested under real concurrent use)

---

# 7. Overall Status

The main updates are working at a basic level, but further testing is still required before the features can be considered fully stable.

Current progress includes:

* Multi-format grading uploads
* ZIP folder handling with internal folders
* Improved Advisor AI URL scraping
* Website persistence for Advisor AI
* Fixed video narration feature
* Started student verification for quiz submission
* Added keystroke tracking for proctoring
* Added monitoring data controls for admins and teachers
* Added Oral Examination feature with AI question generation, proctored spoken answers, and AI grading

---
