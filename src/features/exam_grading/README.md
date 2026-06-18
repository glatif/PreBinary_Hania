# Exam Grading System

## Overview

The Exam Grading System automates the grading of student exam submissions using local LLMs. Professors can define questions, rubrics, and sub-rubrics, then upload student PDF submissions. The system will analyze and grade each submission according to the defined criteria. All grading sessions are persisted to the database and accessible across logins.

## Features

- Define exam questions and detailed grading rubrics
- Set maximum points for the exam
- Upload individual student PDF submissions or a ZIP file containing multiple submissions
- Automated grading of submissions using local LLMs
- Detailed feedback for each student
- Export results to CSV for record-keeping
- Grading history stored in the database, grouped by session per assessment
- Load previous session setup (questions and rubric) directly into the Setup Exam tab for reuse

## Usage Instructions

### Step 1: Setup Exam

1. Go to the "Exam Grading" tab in the application
2. Select the "Setup Exam" section
3. Enter the exam questions in the text area
4. Define the grading rubric, including specific point allocations
5. (Optional) Add sub-rubrics with more detailed grading guidelines
6. Set the maximum points for the exam

Example setup:
```
Question 1:
- Describe the process of photosynthesis and name its main products.

Question 2:
- State Newton's second law of motion and explain its significance.

Question 3:
- Explain what a list is in Python, including its characteristics and use cases.
```

Rubric:
```
- Content Accuracy – 6 marks  
  - Correctness of factual information  
  - Demonstrates understanding of key concepts  

- Completeness – 2 marks  
  - Addresses all parts of the question  
  - Includes required definitions/examples  

- Clarity & Organization – 1 mark  
  - Logical flow of ideas  
  - Well-structured and easy to follow  

- Grammar & Language – 1 mark  
  - Proper use of vocabulary and syntax  
  - Minimal spelling or punctuation errors 
```

### Step 2: Upload Student Submissions

1. Go to the "Student Submissions" section
2. You can either:
   - Upload individual PDF files (one per student)
   - Upload a ZIP file containing multiple PDF submissions
3. The system will process the submissions and extract the text content

Naming convention for files:
- Individual files: `StudentName_StudentID.pdf` (the system will extract name and ID if available)
- Files in ZIP: Same naming convention as above
You can test the system using a sample ZIP folder containing student submissions. Click [here](../src/features/exam_grading/zipfolder/testing.zip) to download the sample ZIP folder.


### Step 3: Grade Submissions

1. Go to the "Grading Results" section
2. Select which LLM model to use for grading (DeepSeek or Llama)
3. Click "Grade All Submissions" to start the automated grading process
4. View the grading results, including:
   - Student name/ID
   - Score
   - Percentage
   - Feedback
   - Detailed explanation of the grading
5. Export the results to CSV by clicking "Download Results as CSV"

### Step 4: View and Reuse Grading History

All grading sessions are saved to the database and available in the History tab for the current assessment.

1. Go to the "History" tab
2. Each row represents one grading session, showing the date and number of students graded
3. Expand a session to view individual student results
4. **Load Setup**: Click "Load Setup" on any past session to restore its exam questions, rubric, sub-rubric, and maximum points directly into the Setup Exam tab — allowing the same exam to be reused for a new cohort without re-entering any details
5. **Download Results**: Export any session as a CSV file
6. **Delete**: Permanently remove a session and all its results

## Sample Data

The repository includes sample test data in the appropriate directory format:
- Question and rubric examples
- Sample student submissions


### Sample Prompts

To effectively use the exam grading system, you can utilize the following sample prompts for questions and rubrics:

- **Question Prompt**: Clearly state the question to be answered by the student. Ensure it is specific and unambiguous to facilitate accurate grading by the LLM.

- **Rubric Prompt**: Define the criteria for grading, including content accuracy, completeness, clarity, organization, and grammar. A detailed rubric helps in achieving consistent grading results.

```
Question 1:
- Describe the process of photosynthesis and name its main products.

Question 2:
- State Newton's second law of motion and explain its significance.

Question 3:
- Explain what a list is in Python, including its characteristics and use cases.
```

Rubric:
```
- Content Accuracy – 6 marks  
  - Correctness of factual information  
  - Demonstrates understanding of key concepts  

- Completeness – 2 marks  
  - Addresses all parts of the question  
  - Includes required definitions/examples  

- Clarity & Organization – 1 mark  
  - Logical flow of ideas  
  - Well-structured and easy to follow  

- Grammar & Language – 1 mark  
  - Proper use of vocabulary and syntax  
  - Minimal spelling or punctuation errors 
```

### Download Sample ZIP Folder

To test the system, you can download a sample ZIP folder containing student submissions. Click [here](../src/features/exam_grading/zipfolder/testing.zip) to download the sample ZIP folder.




You can use these to test the system before using it with real exam data.

## Technical Details

- Text extraction from PDFs using PyPDF
- LLM options: All models supported by the application — DeepSeek R1:1.5B and Llama 3.2 (local, via Ollama), Llama 3.3-70B (Groq), Gemini 2.5 Flash (Google), GPT-4o (OpenAI), GPT-4o (GitHub Models)
- Prompt engineering to ensure consistent grading
- Structured JSON response parsing for consistent score formats
- Grading results stored in the `exam_grading_results` table, grouped by `grading_session_id`
- Each row stores the full exam setup (questions, rubric, sub-rubric, max points) alongside the student result, so any session can be fully restored from history alone

## Best Practices

1. **Detailed Rubrics**: The more detailed your rubrics, the more consistent the grading will be
2. **Clear Questions**: Ensure questions are clearly stated to help the LLM grade accurately
3. **Review Results**: Always review the AI-generated grades before sharing with students
4. **Model Selection**: Try both available models to see which performs better for your specific exam content
5. **PDF Quality**: Ensure submitted PDFs have proper text extraction (not scanned images without OCR)