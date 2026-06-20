# Project Updates

## Updated By

Hania Rasheed

## Overview

This document summarises the latest updates made across the AI Instructor system. The main areas updated include:

* Exam Grading Feature
* Advisor AI Feature
* Narrated Slideshow Generator
* Student Verification for Quiz Submission

The updates focus on improving upload flexibility, URL scraping, slideshow narration, video generation, and quiz submission verification.

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

# 5. Overall Status

The main updates are working at a basic level, but further testing is still required before the features can be considered fully stable.

Current progress includes:

* Multi-format grading uploads
* ZIP folder handling with internal folders
* Improved Advisor AI URL scraping
* Website persistence for Advisor AI
* Fixed video narration feature
* Started student verification for quiz submission

---
