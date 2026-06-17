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