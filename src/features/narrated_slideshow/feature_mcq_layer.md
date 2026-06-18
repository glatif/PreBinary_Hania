# Interactive Quiz Layer Feature Plan

## Overview
This document outlines the plan for implementing an intelligent, interactive quiz layer that actively engages students during the narrated slideshow feature. The LLM will be responsible for generating questions and deciding their placement throughout the presentation.

## Feature Goals
- Add an interactive quiz layer to keep students engaged during slideshow narration
- Let the LLM decide question placement and frequency for dynamic experience
- Block navigation until students answer questions correctly
- Support multiple question types (MCQ, True/False, Mixed)
- Maintain modular architecture and seamless integration

## Implementation Checkpoints

### Phase 1: Backend Quiz Generation
- [ ] Create `quiz_generator.py` module for LLM-based quiz generation
- [ ] Design comprehensive prompt engineering for question generation and placement
- [ ] Implement JSON schema validation for quiz response parsing
- [ ] Add frequency-aware question generation logic
- [ ] Integrate with existing LLM utilities framework

### Phase 2: Frontend UI Updates
- [ ] Update Input tab with quiz configuration options
- [ ] Add frequency dropdown (None, Less Frequent, Frequent, Very Frequent)
- [ ] Add question type selector (MCQs Only, True/False Only, Mixed)
- [ ] Implement quiz generation button and progress tracking
- [ ] Update session state management for quiz data

### Phase 3: Slideshow Player Enhancement
- [ ] Create `quiz_ui_components.py` for quiz display components
- [ ] Implement question placement logic in slideshow flow
- [ ] Add navigation blocking mechanism until correct answers
- [ ] Design clean and modern quiz UI (MCQ and True/False layouts)
- [ ] Implement answer validation and feedback system

### Phase 4: Integration & Testing
- [ ] Update main feature file with quiz workflow integration
- [ ] Add comprehensive error handling and validation
- [ ] Implement debug logging for quiz functionality
- [ ] Test with various frequency settings and question types
- [ ] Ensure backward compatibility with existing slideshow functionality

## Updated Folder Structure
```
src/features/narrated_slideshow/
├── README.md                           # Updated with quiz feature documentation
├── __init__.py
├── narrated_slideshow_feature.py       # Main feature - updated with quiz integration
├── document_processor.py               # Unchanged
├── narration_generator.py              # Unchanged
├── slide_visualizer.py                 # Unchanged
├── slideshow_player.py                 # Updated with quiz integration
├── tts_engine.py                       # Unchanged
├── quiz_generator.py                   # NEW - LLM-based quiz generation
└── quiz_ui_components.py               # NEW - Quiz UI components
```

## Module Responsibilities

### quiz_generator.py (NEW)
- **Purpose**: Generate intelligent quiz questions using LLM
- **Key Functions**:
  - `create_quiz_system_prompt()`: Create LLM system prompt for quiz generation
  - `create_quiz_user_prompt()`: Build user prompt with narration content and frequency
  - `generate_quiz_questions()`: Main function to call LLM and parse quiz JSON
  - `validate_quiz_response()`: Validate and sanitize LLM quiz response
- **Input**: Slideshow narrations, frequency setting, question type preference
- **Output**: Structured quiz data with placement information

### quiz_ui_components.py (NEW)
- **Purpose**: Render quiz UI components
- **Key Functions**:
  - `render_mcq_question()`: Display multiple choice question with 4 options
  - `render_true_false_question()`: Display true/false question
  - `handle_answer_submission()`: Process and validate answer submission
  - `render_quiz_feedback()`: Show correct/incorrect feedback
- **Input**: Quiz question data, user interaction
- **Output**: Quiz UI elements and answer validation

### narrated_slideshow_feature.py (UPDATED)
- **New Functions**:
  - `render_quiz_configuration()`: Quiz settings in Input tab
  - `generate_quiz_questions()`: Trigger quiz generation workflow
  - `integrate_quiz_in_slideshow()`: Add quiz to slideshow flow
- **Updated Functions**:
  - `initialize_slideshow_session_state()`: Add quiz-related session variables
  - `render_input_tab()`: Include quiz configuration options
  - `render_slideshow_tab()`: Integrate quiz display logic

### slideshow_player.py (UPDATED)
- **New Functions**:
  - `check_quiz_placement()`: Determine if quiz should appear at current position
  - `render_quiz_overlay()`: Display quiz UI over slideshow
  - `handle_navigation_blocking()`: Block navigation until quiz completion
- **Updated Functions**:
  - `render_slideshow_player()`: Integrate quiz placement logic
  - Navigation controls: Add quiz completion checks

## Data Flow & API Interaction Schema

### Quiz Generation Workflow
```
1. User completes narration generation
2. User selects quiz frequency (None/Less Frequent/Frequent/Very Frequent)
3. User selects question type (MCQs Only/True/False Only/Mixed)
4. System triggers second LLM API call with:
   - All narration texts as context
   - Frequency preference as string
   - Question type preference
5. LLM returns JSON with questions and placement information
6. System validates and stores quiz data in session state
```

### LLM Quiz API Call Schema

#### Input to LLM:
- **System Prompt**: Quiz generation instructions with education level context
- **User Prompt**: 
  - Narration content for all slides
  - Frequency instruction (e.g., "Generate a 'less frequent' number of questions")
  - Question type preference
  - JSON schema specification

#### Expected LLM Response Schema:
```json
{
  "quiz_questions": [
    {
      "slide_number_after": 3,
      "question_type": "MCQ",
      "question_text": "What is the main principle discussed in the previous slides?",
      "options": [
        "Option A text",
        "Option B text", 
        "Option C text",
        "Option D text"
      ],
      "correct_answer": "Option B text"
    },
    {
      "slide_number_after": 6,
      "question_type": "True/False",
      "question_text": "The concept mentioned applies to all scenarios.",
      "correct_answer": "False"
    }
  ],
  "total_questions": 2,
  "frequency_applied": "less frequent"
}
```

### Session State Schema Extensions
```python
# New quiz-related session state variables
"slideshow_quiz_frequency": "None",           # User's frequency choice
"slideshow_quiz_type": "Mixed",               # User's question type choice  
"slideshow_quiz_generated": False,            # Quiz generation status
"slideshow_quiz_questions": {},               # Generated quiz data
"slideshow_current_quiz": None,               # Current active quiz
"slideshow_quiz_answers": {},                 # User's quiz answers
"slideshow_quiz_blocking_navigation": False,  # Navigation lock status
"slideshow_quiz_completion_status": {}        # Per-question completion tracking
```

### Quiz Placement Logic
```
For each slide transition (current_slide -> next_slide):
1. Check if quiz_questions contains entry with slide_number_after == current_slide
2. If quiz exists:
   - Set slideshow_quiz_blocking_navigation = True
   - Set slideshow_current_quiz = quiz_data
   - Render quiz overlay
   - Block Next button until correct answer
3. If no quiz or quiz completed:
   - Allow normal navigation
   - Continue slideshow flow
```

## Integration Points

### With Existing LLM Utilities
- Use existing `stream_llm()` function for quiz generation
- Leverage existing model selection and API key management
- Follow established error handling patterns

### With Current UI Framework
- Maintain existing Streamlit session state patterns
- Use established debug logging format
- Follow existing column layout and styling conventions
- Preserve current tab structure (Input/Slideshow)

### With Slideshow Player
- Integrate quiz placement checks into existing slide navigation
- Maintain current manual navigation control philosophy
- Preserve existing audio synchronization behavior

## Quality Assurance Considerations

### Error Handling
- Invalid LLM responses for quiz generation
- Malformed JSON from quiz API calls
- Missing or incomplete question data
- API timeout or connection issues

### User Experience
- Clear visual feedback for quiz completion status
- Intuitive navigation blocking indicators
- Smooth transition between questions and slides
- Responsive quiz UI on different screen sizes

### Performance
- Efficient quiz placement lookups during navigation
- Minimal impact on existing slideshow performance
- Proper memory management for quiz data storage
- Reasonable quiz generation time expectations

## Backward Compatibility
- All existing slideshow functionality remains unchanged when quiz frequency is "None"
- No breaking changes to existing API or session state variables
- Existing narration and TTS workflows unaffected
- Previous slideshows without quiz data continue to work normally
