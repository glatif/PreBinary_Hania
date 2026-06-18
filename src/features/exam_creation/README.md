# Exam Creation Feature

## Overview

The Exam Creation feature helps educators generate new exam questions and variations of existing questions using AI. This tool is designed to save time and provide diverse question options while maintaining consistent learning objectives. Source files and generated question sets are persisted to the database, allowing both to be reused across sessions without re-uploading or regenerating.

## Key Functions

### 1. Generate Question Variations

This function takes your existing exam questions and creates multiple variations of each, while preserving:
- The same learning objectives
- Similar difficulty level
- Core concepts being tested

#### Benefits:
- Create different versions of exams to discourage cheating
- Refresh test questions while testing the same knowledge
- Generate different examples for practice tests

### 2. Create Exam from Topics

This function generates entirely new exam questions based on provided lecture topics or content:
- Specify the number of questions needed
- Set the difficulty level (Easy, Medium, Hard)
- AI suggests various question types (multiple choice, short answer, problem-solving)
- Each question includes answer guidance for the instructor

#### Benefits:
- Quickly create assessments from lecture materials
- Generate diverse question types automatically
- Receive guidance on expected answers to aid in grading

## How to Use

### For Question Variations:

1. **Input Your Questions**
   - Upload a PDF document containing your existing exam questions, select a previously saved file, or enter questions manually in the text area
   - Uploaded files are saved to the assessment and can be reused in future sessions without re-uploading

2. **Configure Generation Options**
   - Select the number of variations to generate for each question (1-5)
   - Choose the AI model to use

3. **Generate and Review**
   - Click "Generate Question Variations" to start the process
   - Review the original questions and their variations
   - Each variation includes answer guidance

4. **Export Results**
   - Download the generated variations as a JSON file for future use or modification

### For Creating Exams from Topics:

1. **Input Your Topics**
   - Upload a PDF of lecture notes, syllabus, or topic outline, select a previously saved file, or enter topics manually in the text area
   - Uploaded files are saved to the assessment and can be reused in future sessions without re-uploading

2. **Configure Exam Parameters**
   - Specify how many questions to generate (5-30)
   - Set the desired difficulty level
   - Choose the AI model to use

3. **Generate and Review**
   - Click "Generate Exam Questions" to start the process
   - Review the generated questions organized by topic
   - Each question includes type, difficulty, and answer guidance

4. **Export Results**
   - Download the complete exam as a JSON file for further editing or use

### Managing Saved Files

Each input tab includes a "Manage Saved Files" expander listing all files saved for the current assessment under this feature. Individual files can be deleted from here. Saved files are scoped to the assessment and only appear in Exam Creation, not in other features.

### Viewing Generation History

All generation sessions are saved to the database and displayed in the History tab for the current assessment.

1. Go to the "History" tab
2. Each row represents one generation run, showing the date, mode (variation or from topics), and question count
3. Expand a session to view all questions produced in that run
4. **Edit**: Modify individual question text inline and save changes to the database
5. **Download**: Export the full question set for the session as a JSON file
6. **Delete Session**: Permanently remove the session and all its questions

## Best Practices

1. **Review AI-Generated Content**
   - Always review and refine AI-generated questions for accuracy and clarity
   - Verify that the questions appropriately test the intended learning objectives

2. **Provide Clear Input**
   - For best results, provide well-structured and clear input content
   - Include specific topics, concepts, and learning objectives

3. **Use Answer Guidance**
   - The system provides answer guidance to help with grading consistency
   - Consider these suggestions when evaluating student responses

4. **Diversify Question Types**
   - The system will suggest a mix of question types, which helps assess different levels of understanding
   - Consider the balance of question types in your final exam

## Technical Details

The feature uses Large Language Models (LLMs) to analyze your input and generate contextually relevant questions. The quality of generated content can vary based on:
- The clarity and structure of your input
- The selected AI model
- The complexity of the subject matter

Generated questions are stored in the `exam_creation_questions` table, grouped by `creation_session_id`. Uploaded source files are stored in the `files` table with `feature_name = 'exam_creation'`, scoped to the current assessment, and saved to `uploads/{course_id}_{course_name}/exam_creation/{assessment_title}/` on disk.

For optimal results, we recommend using the Groq-hosted Llama 3.3 model or Google's Gemini model, which generally provide more comprehensive and accurate content.