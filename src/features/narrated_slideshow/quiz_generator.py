"""
Quiz Generator for Narrated Slideshow Feature

This module handles the generation of intelligent quiz questions using LLM APIs,
with dynamic question placement and frequency control.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import streamlit as st

# Import existing LLM utilities
from src.utils.llm_utils import stream_llm, MODELS, MODEL_PROVIDERS
from .llm_json_utils import repair_and_parse_json

def log_debug(phase: str, status: str, message: str) -> None:
    """Log debug messages with consistent formatting"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[NARRATED_SLIDESHOW] [{timestamp}] [{phase}] [{status}] {message}")

def create_quiz_system_prompt(education_level: str) -> str:
    """
    Create system prompt for quiz generation based on education level
    
    Args:
        education_level: Target education level
        
    Returns:
        System prompt string for quiz generation
    """
    
    education_context = {
        "High School": {
            "description": "high school students (ages 14-18)",
            "complexity": "straightforward questions with clear concepts",
            "language": "simple and accessible language"
        },
        "Undergraduate": {
            "description": "undergraduate university students",
            "complexity": "moderately challenging questions that test understanding",
            "language": "academic but clear terminology"
        },
        "Postgraduate": {
            "description": "postgraduate students and professionals",
            "complexity": "in-depth questions that require analytical thinking",
            "language": "advanced academic terminology and concepts"
        },
        "PhD": {
            "description": "PhD students and researchers",
            "complexity": "sophisticated questions that test critical analysis and deep understanding",
            "language": "scholarly and research-oriented terminology"
        }
    }
    
    context = education_context.get(education_level, education_context["Undergraduate"])
    
    system_prompt = f"""You are an expert educational quiz generator specializing in creating engaging and pedagogically sound questions for {context['description']}.

Your role is to:
1. Analyze narration content from educational slideshows and generate quiz questions
2. Strategically place questions to maximize learning engagement and retention
3. Create questions using {context['language']} appropriate for the education level
4. Generate {context['complexity']} that effectively assess comprehension

CRITICAL REQUIREMENTS:
- You MUST decide both the questions AND their placement (which slide number they should appear after)
- Questions should be based on content from preceding slides, not future content
- Question placement should feel natural and strategic, not random
- Each question should test understanding of recently covered material
- Return response in the EXACT JSON format specified in the user prompt
- Ensure all required fields are present and properly formatted

Quality Standards:
- Questions must be clear, unambiguous, and pedagogically valuable
- Multiple choice options should be plausible with only one clearly correct answer
- True/False questions should test meaningful concepts, not trivial facts
- Question placement should create natural checkpoints in the learning journey"""

    return system_prompt

def create_quiz_user_prompt(narrations: Dict[int, Dict], frequency: str, question_type: str, education_level: str) -> str:
    """
    Create user prompt for quiz generation with narration content and preferences
    
    Args:
        narrations: Dictionary of slide narrations
        frequency: User's frequency preference (Less Frequent, Frequent, Very Frequent)
        question_type: User's question type preference (MCQs Only, True/False Only, Mixed)
        education_level: Target education level
        
    Returns:
        User prompt string for quiz generation
    """
    
    # Build narration content
    narrations_content = ""
    total_slides = len(narrations)
    for slide_num in sorted(narrations.keys()):
        narration_data = narrations[slide_num]
        narration_text = narration_data.get("narration_text", "").strip()
        if narration_text:
            narrations_content += f"\nSlide {slide_num} Narration:\n{narration_text}\n"
    
    # Define frequency guidelines
    frequency_guidelines = {
        "Less Frequent": f"Generate 1-2 questions total for this {total_slides}-slide presentation. Place them strategically after slides that cover key concepts.",
        "Frequent": f"Generate 2-4 questions total for this {total_slides}-slide presentation. Distribute them evenly to maintain engagement without overwhelming.",
        "Very Frequent": f"Generate 3-6 questions total for this {total_slides}-slide presentation. Place them frequently to ensure continuous engagement and comprehension checking."
    }
    
    frequency_instruction = frequency_guidelines.get(frequency, frequency_guidelines["Frequent"])
    
    # Define question type instructions
    question_type_instructions = {
        "MCQs Only": "Generate only multiple choice questions. Each question must have exactly 4 options with only one correct answer.",
        "True/False Only": "Generate only True/False questions. Each question should test meaningful understanding, not trivial facts.",
        "Mixed": "Generate a mix of multiple choice and True/False questions. Use the most appropriate question type for each concept being tested."
    }
    
    type_instruction = question_type_instructions.get(question_type, question_type_instructions["Mixed"])
    
    user_prompt = f"""You will analyze the following slideshow narrations and generate quiz questions to enhance student engagement and learning assessment.

---

SLIDESHOW DETAILS:
Education Level: {education_level}
Total Slides: {total_slides}
Frequency Preference: {frequency}
Question Type Preference: {question_type}

NARRATION CONTENT:
{narrations_content}

---

GENERATION INSTRUCTIONS:

Frequency: {frequency_instruction}

Question Types: {type_instruction}

PLACEMENT STRATEGY:
- Choose slide numbers strategically - questions should appear AFTER slides that introduce key concepts
- Ensure questions test content from preceding slides only
- Consider natural break points in the content flow
- Avoid placing questions too early (usually not after slide 1) or too close together

RETURN FORMAT:
You MUST return your response in this EXACT JSON format with no additional text:

{{
  "quiz_questions": [
    {{
      "slide_number_after": 3,
      "question_type": "MCQ",
      "question_text": "Based on the content covered so far, what is the main principle discussed?",
      "options": [
        "First option text",
        "Second option text",
        "Third option text",
        "Fourth option text"
      ],
      "correct_answer": "Second option text"
    }},
    {{
      "slide_number_after": 5,
      "question_type": "True/False",
      "question_text": "The concept explained in the previous slides applies to all scenarios.",
      "correct_answer": "False"
    }}
  ],
  "total_questions": 2,
  "frequency_applied": "{frequency.lower()}"
}}

IMPORTANT REQUIREMENTS:
- slide_number_after must be between 2 and {total_slides - 1} (questions should not appear after the last slide)
- For MCQ questions: exactly 4 options, correct_answer must match one of the options exactly
- For True/False questions: correct_answer must be exactly "True" or "False"
- Question text should be clear and test understanding of preceding slide content
- Generate questions that promote active learning and comprehension assessment"""

    return user_prompt

def validate_quiz_response(response_data: Dict[str, Any], total_slides: int) -> Dict[str, Any]:
    """
    Validate and sanitize quiz response from LLM
    
    Args:
        response_data: Parsed JSON response from LLM
        total_slides: Total number of slides in presentation
        
    Returns:
        Dict with validation results and cleaned data
    """
    log_debug("QUIZ_VALIDATION", "INFO", "Starting quiz response validation")
    
    errors = []
    warnings = []
    validated_questions = []
    
    try:
        # Check top-level structure
        if "quiz_questions" not in response_data:
            return {
                "success": False,
                "error": "Missing 'quiz_questions' field in response",
                "questions": []
            }
        
        questions = response_data["quiz_questions"]
        if not isinstance(questions, list):
            return {
                "success": False,
                "error": "'quiz_questions' must be a list",
                "questions": []
            }
        
        used_slide_numbers = set()
        
        for i, question in enumerate(questions):
            question_errors = []
            
            # Validate required fields
            required_fields = ["slide_number_after", "question_type", "question_text", "correct_answer"]
            for field in required_fields:
                if field not in question:
                    question_errors.append(f"Missing required field: {field}")
            
            if question_errors:
                errors.extend([f"Question {i+1}: {error}" for error in question_errors])
                continue
            
            # Validate slide_number_after
            slide_num = question["slide_number_after"]
            if not isinstance(slide_num, int):
                try:
                    slide_num = int(slide_num)
                    question["slide_number_after"] = slide_num
                except ValueError:
                    errors.append(f"Question {i+1}: slide_number_after must be a number")
                    continue
            
            if slide_num < 2 or slide_num >= total_slides:
                errors.append(f"Question {i+1}: slide_number_after ({slide_num}) must be between 2 and {total_slides-1}")
                continue
            
            if slide_num in used_slide_numbers:
                warnings.append(f"Question {i+1}: Multiple questions placed after slide {slide_num}")
            
            used_slide_numbers.add(slide_num)
            
            # Validate question_type
            question_type = question["question_type"]
            if question_type not in ["MCQ", "True/False"]:
                errors.append(f"Question {i+1}: question_type must be 'MCQ' or 'True/False'")
                continue
            
            # Validate question_text
            question_text = question["question_text"].strip()
            if not question_text:
                errors.append(f"Question {i+1}: question_text cannot be empty")
                continue
            
            # Type-specific validation
            if question_type == "MCQ":
                # Validate options
                if "options" not in question:
                    errors.append(f"Question {i+1}: MCQ missing 'options' field")
                    continue
                
                options = question["options"]
                if not isinstance(options, list) or len(options) != 4:
                    errors.append(f"Question {i+1}: MCQ must have exactly 4 options")
                    continue
                
                # Check if correct_answer matches one of the options
                correct_answer = question["correct_answer"]
                if correct_answer not in options:
                    errors.append(f"Question {i+1}: correct_answer must match one of the options exactly")
                    continue
                
            elif question_type == "True/False":
                # Validate True/False answer
                correct_answer = question["correct_answer"]
                if correct_answer not in ["True", "False"]:
                    errors.append(f"Question {i+1}: True/False correct_answer must be 'True' or 'False'")
                    continue
                
                # Remove options field if present (not needed for True/False)
                if "options" in question:
                    del question["options"]
            
            # If we reach here, question is valid
            validated_questions.append(question)
        
        # Final validation
        if errors:
            log_debug("QUIZ_VALIDATION", "ERROR", f"Validation failed with {len(errors)} errors")
            return {
                "success": False,
                "error": f"Validation failed with {len(errors)} errors",
                "errors": errors,
                "warnings": warnings,
                "questions": []
            }
        
        log_debug("QUIZ_VALIDATION", "SUCCESS", f"Validated {len(validated_questions)} questions successfully")
        
        return {
            "success": True,
            "questions": validated_questions,
            "total_questions": len(validated_questions),
            "warnings": warnings,
            "slide_numbers_used": sorted(list(used_slide_numbers))
        }
        
    except Exception as e:
        error_msg = f"Unexpected error during validation: {str(e)}"
        log_debug("QUIZ_VALIDATION", "ERROR", error_msg)
        return {
            "success": False,
            "error": error_msg,
            "questions": []
        }

def generate_quiz_questions(narrations: Dict[int, Dict], frequency: str, question_type: str, 
                          education_level: str, model_name: str) -> Dict[str, Any]:
    """
    Generate quiz questions using LLM API
    
    Args:
        narrations: Dictionary of slide narrations
        frequency: User's frequency preference
        question_type: User's question type preference
        education_level: Target education level
        model_name: LLM model to use
        
    Returns:
        Dict with generation results and quiz questions
    """
    log_debug("QUIZ_GENERATION", "INFO", f"Starting quiz generation for {len(narrations)} slides")
    log_debug("QUIZ_GENERATION", "INFO", f"Frequency: {frequency}, Type: {question_type}, Level: {education_level}")

    # Valid placement requires "2 <= slide_number_after <= total_slides - 1" (see
    # create_quiz_user_prompt / validate_quiz_response below), which has no
    # solution for presentations with fewer than 3 slides. Skip the LLM call
    # entirely in that case instead of always failing on validation.
    if len(narrations) < 3:
        log_debug("QUIZ_GENERATION", "INFO", "Too few slides for quiz placement, skipping LLM call")
        return {
            "success": False,
            "error": "Quiz questions require at least 3 slides to place questions strategically. This presentation is too short for a quiz."
        }

    try:
        # Create system and user prompts
        system_prompt = create_quiz_system_prompt(education_level)
        user_prompt = create_quiz_user_prompt(narrations, frequency, question_type, education_level)
        
        # Combine prompts for API call
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        log_debug("QUIZ_GENERATION", "INFO", f"Using model: {model_name}")
        log_debug("QUIZ_GENERATION", "DEBUG", f"Full prompt length: {len(full_prompt)} characters")
        
        # Call LLM API
        response_text = ""
        for chunk in stream_llm(full_prompt, model_name):
            response_text += chunk
        
        log_debug("QUIZ_GENERATION", "INFO", f"Received LLM response: {len(response_text)} characters")
        
        if not response_text.strip():
            return {
                "success": False,
                "error": "Empty response from LLM"
            }
        
        # Parse JSON response. repair_and_parse_json handles the common case of
        # small local models (e.g. llama3.2 via Ollama) emitting their stop
        # token one step early and ending the response before the final
        # closing brace - a plain find('{')/rfind('}') extraction can't
        # recover from that, but a balanced-bracket repair can.
        quiz_data = repair_and_parse_json(response_text)
        if quiz_data is None:
            log_debug("QUIZ_GENERATION", "ERROR", "Could not parse JSON from LLM response")
            return {
                "success": False,
                "error": "Could not parse a valid JSON response from the LLM",
                "raw_response": response_text[:500]
            }

        # Validate the quiz response
        validation_result = validate_quiz_response(quiz_data, len(narrations))

        if validation_result["success"]:
            log_debug("QUIZ_GENERATION", "SUCCESS",
                     f"Successfully generated {validation_result['total_questions']} quiz questions")

            return {
                "success": True,
                "quiz_questions": validation_result["questions"],
                "total_questions": validation_result["total_questions"],
                "warnings": validation_result.get("warnings", []),
                "slide_numbers_used": validation_result.get("slide_numbers_used", []),
                "frequency_applied": frequency
            }
        else:
            log_debug("QUIZ_GENERATION", "ERROR", f"Validation failed: {validation_result['error']}")
            return {
                "success": False,
                "error": f"Quiz validation failed: {validation_result['error']}",
                "validation_errors": validation_result.get("errors", []),
                "raw_response": response_text[:500]
            }

    except Exception as e:
        error_msg = f"Error generating quiz questions: {str(e)}"
        log_debug("QUIZ_GENERATION", "ERROR", error_msg)
        return {
            "success": False,
            "error": error_msg
        }
