# Project Updates 

**Updated by:** Hania Rasheed

## What's new, feature by feature

**1. Exam Grading** — Now accepts PDF, Word, PowerPoint, text, and ZIP (with subfolders) for both question papers and student submissions, not just PDF.

**2. Advisor AI** — Admins can add URLs one at a time, in bulk, as `Label | URL`, or via `.txt` upload. Added a fallback scraper for non-standard webpages. URLs persist across app reloads.

**3. Narrated Slideshow Generator** — Video narration is fixed and working again.

**4. Student Verification (Quiz Submission)** — New feature (in progress): verifies students via student card before/during quiz submission. Not fully wired up yet.

**5. Proctoring — Keystroke Tracking** — Logs keystrokes (sent every ~15s, not per keypress) alongside existing tab-switch and screen-share monitoring. Teachers/admins can now delete a student's monitoring data per attempt/assessment, in addition to the existing bulk age-based cleanup.

**6. Proctoring — Audio/Video Recording** — Records actual mic audio (10s clips, kept only if speech detected) and screen+webcam video (30s segments, admin-configurable quality — see #12 — ~2hr cap). Instructors can stitch segments into full recordings (screen, webcam+audio, or combined picture-in-picture) via a button. Heavy analysis now runs in the background (every 15 min) or on-demand via Admin Panel → Maintenance → "Run Proctoring Analysis Now," instead of slowing down live monitoring.

**7. Oral Examination (new feature/tab)** — AI generates questions from teacher material; students answer by speaking; AI grades transcripts.
- Questions are read aloud (TTS), mic stays on the whole time, recording starts automatically per question.
- Per-question time limits with auto-submit, plus a **Skip** option and **retry transcription** if it fails.
- Teachers can upload source files (PDF/Word/PPT/text/ZIP) for question generation.
- Students need a Groq or OpenAI API key saved on their profile for transcription — warned upfront if missing.
- Teachers grade all answers in one batch against a rubric; results include score, feedback, proctoring summary, and a History tab.
- Shows students who started but never finished.

**8. Identity Verification** — Now saves the actual ID-card and selfie photos (not just OCR/match results). Instructors can view them via a new expander on review screens.

**9. Attempt Logging** — New log tracks the full lifecycle of quiz/oral exam attempts (started, question reached, submitted, timed out, skipped, completed), so teachers can see who started but didn't finish.

**10. Reliability Fixes** — Fixed a bug where long exam results could silently fail to save; save failures are now reported separately from grading failures; all LLM/transcription calls now timeout after 120s instead of hanging.

**11. Database Schema** — `schema_clean.sql` and `schema_demo.sql` now create every table this update needs (oral exam, attempt log, verification photos, audio/video proctoring) directly, so a fresh database no longer requires running any `migration_add_*.sql` files by hand. `schema_demo.sql` was also brought up to date with older proctoring tables it had been missing.

**12. Proctoring — Configurable Video Quality** — Admins can now pick a Low (360p)/Medium (480p, previous default)/High (720p) recording quality for proctoring screen+webcam video, from Admin Panel → Maintenance → "Video Recording Quality." Only applies to sessions that start recording after the change — a session already recording keeps using whatever tier was active when it started.

## Setup needed before using

- **Fresh server / new database:** just run `schema_clean.sql` (or `schema_demo.sql` for seeded demo accounts) as usual — everything is already included.
- **Existing database you want to keep data in:** run the new `migration_add_*.sql` files instead of recreating the schema (`migration_add_proctor_analysis_status.sql` must run after `migration_add_audio_proctoring.sql`/`migration_add_video_proctoring.sql`, since it alters their tables; `migration_add_proctor_video_quality_setting.sql` can run any time).
- Add a Groq or OpenAI key under **Profile → AI API Keys** for any account taking an oral exam.
- If using the local model for oral exam questions, make sure Ollama is running with `deepseek-r1:1.5b` pulled.
- `pip install -r requirements.txt` picks up new packages automatically (no manual downloads needed).

