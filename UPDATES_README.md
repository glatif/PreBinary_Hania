# Project Updates

## Updated By

Hania Rasheed

## Overview

This document summarises the latest project updates made across the AI Instructor system. The main areas updated include:

- Exam Grading Feature
- Advisor AI Feature
- Narrated Slideshow Generator

The updates focus on improving file upload flexibility, URL management, scraping reliability, question generation, slideshow narration, quiz generation, and video export stability.

---

# 1. Exam Grading Feature Updates

## Summary of Changes

This update expands the exam grading feature from PDF-only support to a wider multi-file upload system. The system now supports PDF files, Word documents, PowerPoint files, text files, and ZIP folders with internal sub-folder handling.

These updates improve the flexibility of the grading workflow by allowing teachers to upload different types of exam material and student submissions. The system can now extract and organise content from multiple file formats, making it easier for the AI to process uploaded material and support question extraction, question generation, grading, and feedback.

## Features Added

### 1.1 Expanded File Upload Support

The grading upload system now supports the following file types:

- PDF files
- Word documents
- PowerPoint files
- Text files
- ZIP folders

This applies to:

- Question paper upload
- Student submission upload
- ZIP-based upload workflow

### 1.2 ZIP Folder Processing

ZIP upload support has been improved to detect supported files inside internal folders and sub-folders. The system scans the ZIP structure, identifies supported file types, extracts their content, and processes the text for use in the grading workflow.

This allows teachers to upload organised ZIP folders containing multiple student submissions or exam-related files without needing to flatten the folder structure manually.

### 1.3 Structured Text Extraction

Extracted content from multiple files is combined using filename separators. This helps the AI identify which content belongs to each uploaded file and improves the reliability of multi-file question extraction.

This is especially useful when processing ZIP folders, mixed file uploads, or multiple student submissions, as it keeps the extracted content clearly separated and easier for the AI to interpret.

### 1.4 AI Question Creation Workflow

Teachers can now either:

- Format existing questions from uploaded material
- Generate new questions using a custom prompt

Supported generated question types include:

- Multiple-choice questions
- True/false questions
- Short-answer questions

This gives teachers more control over how uploaded learning material is converted into assessment questions.

### 1.5 PowerPoint Question Handling

The AI prompt has been improved to better recognise question-style content in PowerPoint slides. This includes slide titles, bullet points, and multiple-choice options such as A, B, C, and D.

This update helps the system handle slide-based exam or quiz content more accurately, especially where questions are not written in a traditional document format.

### 1.6 Proposed Submission Side-Pane Feature

A further interface improvement has been proposed for the grading workflow. When a teacher clicks on a student ID, the student’s submitted work should appear in a side pane beside the grading results.

This would allow teachers to review the student submission and AI-generated grading output side by side, reducing the need to open files separately or switch between pages. This feature is intended to improve usability and make the grading review process more efficient.

## Current Status

The main upload and question-processing functionality is working for the most part. Further testing is still required across different file combinations, ZIP folder structures, and grading scenarios.

The actual AI-based grading and feedback workflow also needs additional validation to confirm accuracy, consistency, and correct matching between questions and student submissions.

## Testing Required

Further testing should be carried out for:

- Word document upload
- PowerPoint upload
- Text file upload
- ZIP upload with internal folders
- ZIP upload with mixed file types
- Question extraction from PowerPoint slides
- AI-generated multiple-choice questions
- AI-generated true/false questions
- AI-generated short-answer questions
- AI-based grading and feedback
- Matching student submissions with the correct questions
- Accuracy and consistency of grading results
- Proposed student ID side-pane submission preview feature

## Notes

Some edge cases may still need checking, especially files with unusual formatting, nested ZIP folders, unsupported file types, or PowerPoint slides with non-standard layouts.

The grading workflow is functional at a basic level, but more testing is needed before considering it fully stable. The proposed side-pane feature also requires feedback before implementation.

---

# 2. Advisor AI Feature Updates

## Summary of Changes

This update improves the Advisor AI feature by expanding the URL management and scraping workflow. Previously, the Advisor AI feature was mainly limited to predefined website sources and TRU-specific page layouts. The system has now been updated so admins can add multiple custom URLs, scrape generic webpages, and rebuild the search index across all configured sources more efficiently.

These updates make the Advisor AI feature more flexible because additional advising, course, faculty, or support-related webpages can be added without changing the code manually.

## Features Added

### 2.1 Unlimited Admin URL Support

Admins can now add unlimited URLs from the Advisor AI Data Management tab.

The system supports:

- Single URL entry with an optional label
- Bulk URL paste, with one URL per line
- Optional bulk format using `Label | URL`
- `.txt` file upload, with one URL per line

This makes it easier to add multiple advising or course-related sources at once.

### 2.2 Generic Web Scraping Fallback

A generic scraping fallback has been added in `advisor_utils.py`.

The system now tries the TRU-specific faculty and course scrapers first. If the page does not match the expected TRU layouts, it falls back to `scrape_generic()` to extract readable text from the webpage.

This allows custom admin-added URLs to be processed even when they do not follow the original TRU page structures.

### 2.3 Search Across All Configured Sources

The Advisor AI search index has been updated so that chunks from every configured site are merged into one FAISS index.

A new **Update All Sites & Rebuild Index** button has also been added. This allows all configured URLs to be scraped and indexed in one step, meaning bulk-added URLs become searchable without updating each site individually.


### 2.4 Website Persistence Fix

Another bug was found where the website list only existed in `st.session_state`. This meant admin-added URLs disappeared after the app was reloaded.

This was fixed by adding disk-based persistence using `websites.json`.

The following helper functions were added:

- `load_advisor_websites()`
- `save_advisor_websites()`

The website list is now saved after every add or delete action, so custom admin-added URLs remain available after reload.

## Current Status

The Advisor AI URL management and scraping updates are working for the most part. Admins can add URLs individually, paste URLs in bulk, upload `.txt` URL lists, and rebuild the index across all configured sources.

The updates have been verified through compile checks and targeted logic tests, including URL parsing, URL deduplication, BOM handling, and website persistence round-trip testing.

## Testing Required

Further testing should be carried out for:

- Generic scraping fallback reliability
- Updating all sites and rebuilding the FAISS index
- Website persistence after app reload

## Notes

Some edge cases may still need checking, especially webpages with unusual layouts, pages requiring authentication, dynamically loaded JavaScript content, broken URLs, duplicate URLs, or pages with very little readable text.

The generic scraper improves flexibility, but some sites may still require custom scraping logic if their content cannot be extracted reliably.

---

# 3. Narrated Slideshow Generator Updates

## Summary of Changes

This update improves the Narrated Slideshow Generator by making the narration, quiz generation, slide preview, and video export workflow more reliable. Several fixes were made to handle incomplete LLM JSON responses, missing slide narrations, quiz validation issues, PowerPoint preview failures, and video export failures caused by missing audio.

It is still not working fully and more improvements are underway.


# 4. Overall Current Status

The main updates have been implemented and are working for the most part.

However, further testing is still required before considering all features fully stable, especially:

- AI-based grading and feedback
- Larger file upload combinations
- ZIP folder edge cases
- Larger narrated slideshow presentations
- Quiz generation reliability
- Visual slide preview reliability
- Video generation for larger slide decks
- Advisor AI scraping reliability across varied webpages

---

# 5. Recommended Next Steps

The following tasks should be prioritised next:

1. Test the actual AI grading workflow more thoroughly.
2. Validate submission-question matching and grading consistency.
3. Review and confirm the proposed student ID side-pane submission preview feature.
4. Test Advisor AI with more custom URLs from different webpage structures.
5. Confirm that admin-added Advisor AI URLs persist after reload.
6. Reproduce the 20-slide Narrated Slideshow issue using the actual file or a larger synthetic file.
7. Capture exact quiz generation errors and raw LLM responses.
8. Trace where slides are being dropped in the slideshow pipeline.
9. Test whether gTTS or LLM response limits are causing missing audio/narrations.
10. Continue documenting any remaining edge cases and fixes.
