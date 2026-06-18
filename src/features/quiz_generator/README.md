# Practice for Exam/Quiz Feature

## Overview

The Practice for Exam/Quiz feature (formerly Quiz Generator) allows students to upload their study materials and automatically generate personalized quiz questions using AI. This tool helps students test their knowledge, identify learning gaps, and improve retention through interactive practice sessions. Source files and generated quizzes are persisted to the database, allowing files to be reused across sessions and quiz attempts to be reviewed in a history tab.

## Key Features

### 1. Multi-Format Document Support
- **PDF Files**: Extract text from PDF documents including textbooks, lecture notes, and research papers
- **Word Documents (.docx)**: Process Microsoft Word documents with formatted text
- **PowerPoint Presentations (.pptx)**: Extract content from presentation slides
- **Text Files (.txt)**: Process plain text documents

### 2. Multi-Type Question Generation
- **Multiple Choice Questions**: Generate questions with 4 options and clear correct answers
- **True/False Questions**: Create statements that test factual understanding
- **Short Answer Questions**: Generate questions requiring brief written responses
- **Simultaneous Generation**: Create all three question types in a single session
- **Flexible Question Count**: 0-15 questions per type (default: 5 each)
- **Type Exclusion**: Set any question type to 0 to exclude it from generation

### 3. Advanced Quiz Customization
- **Per-Type Question Control**: Independently set the number of questions for each type
- **Difficulty Levels**: 
  - Easy: Direct recall of facts
  - Medium: Application of concepts
  - Hard: Analysis and synthesis
- **Topic Filtering**: Focus on specific topics or subjects
- **AI Model Selection**: Choose from multiple AI models including local and cloud options

### 4. Export and Download Options
- **Word Document Export**: Download generated quizzes in professional Word format
  - **Questions Only**: Clean format for taking the quiz
  - **Questions + Answers**: Complete answer key with explanations
- **JSON Export**: Technical format for integration with other systems
- **Multiple Download Formats**: Choose the format that best suits your needs

### 5. Interactive Quiz Interface
- **Real-time Answer Tracking**: Track answers as students progress through questions
- **Immediate Feedback**: Provide explanations for correct answers
- **Performance Metrics**: Display scores, percentages, and grades
- **Mixed Question Types**: Handle multiple question types in a single session
- **Retake Options**: Allow students to retake quizzes with the same questions

### 6. Persistent File Storage
- Uploaded study materials are saved to the assessment directory and stored in the database
- Saved files can be selected for future quiz generation sessions without re-uploading
- Instructors can manage (view and delete) saved files from within the feature

### 7. Quiz and Attempt History
- Generated quizzes and student attempts are stored in the database per assessment
- **My History tab**: Each student can review all their own attempts, including scores, source files used, and a full question-by-question breakdown. Individual attempts can be downloaded or deleted.
- **Student Attempts tab** (instructor and admin only): Displays all student attempts across the assessment in a single view, with the same per-attempt detail and download options available for each entry

## How to Use

### Step 1: Data Input & Analysis

1. **Upload Study Materials**
   - Click on the file uploader and select your study documents, or select from previously saved files
   - Supported formats: PDF, DOCX, PPTX, TXT
   - Uploaded files are saved to the assessment and available for reuse in future sessions

- For testing purposes, a sample pdf is provided on the topic of Photosynthesis: [photosynthesis.pdf](./photosynthesis.pdf)

2. **Configure Quiz Settings**
   - **Question Types**: Set the number of questions for each type:
     - Multiple Choice: 0-15 questions (default: 5)
     - True/False: 0-15 questions (default: 5)
     - Short Answer: 0-15 questions (default: 5)
   - **Total Questions**: The interface shows your total question count
   - **Difficulty Level**: Pick Easy, Medium, or Hard
   - **Topic Focus**: Optionally specify topics to focus on

3. **Select AI Model**
   - Choose from available AI models (local or cloud-based)
   - Available models: DeepSeek, Llama 3.2, Llama 3.3-70B (Groq), Gemini 2.5 Flash, GPT-4o (OpenAI), GPT-4o (GitHub Models)
   - Ensure API keys are configured for cloud models

4. **Generate Quiz**
   - Click "Analyze Content & Generate Quiz"
   - The system makes separate LLM calls for each question type
   - Results are automatically merged into a single comprehensive quiz
   - Wait for the system to process documents and generate questions

### Step 2: Quiz Interface

1. **Review Quiz Details**
   - Check the number of questions by type (MC, T/F, SA)
   - See total question count and difficulty level
   - View which AI model was used for generation

2. **Download Options**
   - **Questions Only (Word)**: Clean format for taking the quiz
   - **Questions + Answers (Word)**: Complete answer key with explanations
   - **JSON Format**: Technical format for system integration

3. **Answer Questions**
   - Navigate through mixed question types in a single interface
   - Select answers for multiple choice/true-false questions
   - Type responses for short answer questions

4. **Submit and Review**
   - Click "Submit Quiz" when finished
   - Review results with explanations for each question type
   - Check your score and grade (for objective questions)

5. **Retake Quiz** (Optional)
   - Use the "Take Quiz Again" button to retry with the same questions

## Technical Details

### Enhanced Document Processing Pipeline
1. **Multi-Format File Upload**: Streamlit file uploader handles PDF, DOCX, PPTX, TXT
2. **Specialized Text Extraction**: Format-specific extractors for optimal content retrieval
3. **Content Validation**: Ensures sufficient content quality for question generation
4. **Unified Content Processing**: Merges all extracted text for comprehensive analysis

### Advanced Question Generation
1. **Multi-Type LLM Calls**: Separate API calls for each question type ensure optimal results
2. **Intelligent Merging**: Combines different question types into a cohesive quiz experience
3. **Question Numbering**: Sequential numbering across all question types
4. **Metadata Tracking**: Comprehensive tracking of generation success and statistics

### AI Question Generation
- Uses advanced language models to analyze content and generate questions
- Structured prompts ensure consistent question format and quality
- JSON response parsing for reliable question extraction
- Error handling for malformed responses

### Database Persistence
- Generated quizzes are stored in the `practice_quiz_generated` table, linked to the current assessment and user
- Student attempts are stored in the `practice_quiz_attempts` table, linked to the quiz and assessment
- Uploaded source files are stored in the `files` table with `feature_name = 'practice_quiz'`, saved to `uploads/{course_id}_{course_name}/practice_quiz/{assessment_title}/` on disk

### Supported AI Models
- **Local Models** (via Ollama):
  - DeepSeek R1: 1.5B
  - Llama 3.2
- **Cloud Models** (API key required):
  - Groq (Llama 3.3-70B)
  - Google Gemini 2.5 Flash
  - OpenAI GPT-4o
  - GitHub Models GPT-4o

## Best Practices

### For Optimal Question Quality
1. **Upload Comprehensive Content**: Include detailed study materials with clear explanations
2. **Use Quality Sources**: Upload well-structured documents with good formatting
3. **Specify Topics**: Use topic filters to focus on specific subjects
4. **Choose Appropriate Difficulty**: Match difficulty to your learning level

### For Better Learning Outcomes
1. **Review Explanations**: Read explanations for both correct and incorrect answers
2. **Retake Quizzes**: Practice with the same questions to improve retention
3. **Vary Question Types**: Use different question types to test various skills
4. **Progressive Difficulty**: Start with easier questions and gradually increase difficulty

## File Structure

```
quiz_generator/
├── __init__.py                    # Package initialization
├── quiz_generator_feature.py      # Main UI and feature logic
├── document_processor.py          # Document text extraction utilities
├── quiz_generator.py             # Quiz generation and LLM integration
└── README.md                     # This documentation file
```

## Dependencies

- **PyPDF2**: PDF text extraction
- **python-docx**: Word document processing
- **python-pptx**: PowerPoint presentation processing
- **streamlit**: Web interface framework
- **json**: JSON response parsing

## Error Handling

The feature includes comprehensive error handling for:
- Unsupported file formats
- Corrupted or unreadable files
- Insufficient content for question generation
- LLM API failures
- Malformed JSON responses
- Network connectivity issues

## Future Enhancements

- **Adaptive Difficulty**: Automatically adjust question difficulty based on performance
- **Collaborative Features**: Share quizzes with classmates or study groups
- **Analytics Dashboard**: Track learning progress over time
- **Integration with LMS**: Connect with learning management systems

## Troubleshooting

### Common Issues

1. **"Insufficient content extracted"**
   - Ensure uploaded files contain readable text
   - Check that PDFs are not image-only (scanned documents)
   - Verify file size is reasonable (not too large or too small)

2. **"Failed to generate quiz"**
   - Check internet connection for cloud models
   - Verify API keys are correctly configured
   - Try reducing the number of questions
   - Switch to a different AI model

3. **"Invalid quiz data"**
   - The AI model may have returned malformed data
   - Try regenerating the quiz
   - Consider using a different AI model
   - Check if content is suitable for the selected question type

### Performance Tips

- **File Size**: Keep uploaded files under 10MB for best performance
- **Content Quality**: Use well-formatted documents with clear text
- **Question Count**: Start with fewer questions (5-10) for faster generation
- **Model Selection**: Local models are faster but may have lower quality