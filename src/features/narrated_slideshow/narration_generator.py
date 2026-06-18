"""
Narration Generator for Narrated Slideshow Feature

This module handles the generation of educational narrations using LLM APIs,
with education-level-aware prompt engineering.
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

def create_system_prompt(education_level: str) -> str:
    """
    Create system prompt based on education level
    
    Args:
        education_level: Target education level
        
    Returns:
        System prompt string
    """
    
    education_context = {
        "High School": {
            "description": "high school students (ages 14-18)",
            "style": "clear, engaging, and age-appropriate",
            "complexity": "simple explanations with everyday examples"
        },
        "Undergraduate": {
            "description": "undergraduate university students",
            "style": "informative, structured, and academic",
            "complexity": "moderate depth with some technical terms explained clearly"
        },
        "Postgraduate": {
            "description": "postgraduate students and professionals",
            "style": "academic, comprehensive, and analytical",
            "complexity": "in-depth analysis with theoretical frameworks and advanced concepts"
        },
        "PhD": {
            "description": "PhD students and researchers",
            "style": "scholarly, analytical, and research-oriented",
            "complexity": "sophisticated analysis with research implications and specialized terminology"
        }
    }
    
    context = education_context.get(education_level, education_context["Undergraduate"])
    
    system_prompt = f"""You are an expert educational narrator. Your job is to generate {context['style']} narrations for slide-based educational content, suitable for {context['description']}.

Your narrations should:
- Be engaging and educational with {context['complexity']}
- Take 30-90 seconds to read aloud (approximately 50-150 words)
- Flow naturally as spoken content, not just reading bullet points
- Add context and explanations appropriate for {education_level} level
- Use smooth transitions and connecting phrases
- Make complex topics accessible and interesting

Always respond in the exact JSON format requested."""

    return system_prompt

def create_user_prompt(content_dict: Dict[int, str], education_level: str, 
                      file_name: str) -> str:
    """
    Create user prompt with slide content for batch processing
    
    Args:
        content_dict: Dictionary of slide/page content
        education_level: Target education level
        file_name: Name of the source file
        
    Returns:
        User prompt string
    """
    
    # Extract topic from filename (remove extension and clean up)
    topic = file_name.replace('.pdf', '').replace('.ppt', '').replace('.pptx', '')
    topic = topic.replace('-', ' ').replace('_', ' ').title()
    
    # Build slides content
    slides_content = ""
    for slide_num in sorted(content_dict.keys()):
        slide_text = content_dict[slide_num].strip()
        if slide_text:
            slides_content += f"\nSlide {slide_num}:\n{slide_text}\n"
    
    user_prompt = f"""You will receive text content for each slide of a presentation. Your task is to generate engaging narrations for each slide, written in a way that {education_level.lower()} students can easily understand and find engaging.

---

Education Level: {education_level}
Topic: {topic}
Total Slides: {len(content_dict)}

Slides:
{slides_content}

---

Return the response in this exact JSON format:

{{
  "slides": [
    {{
      "slide_number": 1,
      "narration_text": "..."
    }},
    {{
      "slide_number": 2,
      "narration_text": "..."
    }}
  ]
}}

Important: Generate narrations for ALL slides provided. Each narration should be 30-90 seconds when spoken (50-150 words)."""

    return user_prompt

def _parse_narration_response(response_text: str) -> Optional[Dict[int, Dict[str, Any]]]:
    """
    Parse a raw LLM response into a {slide_number: {slide_number, narration_text}} dict.

    Returns None if the response is an error marker, too short, not valid JSON,
    or missing the expected "slides" array - callers treat None as "no usable
    narrations from this call" without raising.
    """
    if not response_text or response_text.strip().startswith("Error:"):
        return None
    if len(response_text.strip()) < 10:
        return None

    # repair_and_parse_json handles small local models (e.g. llama3.2 via
    # Ollama) that emit their stop token one step early and end the response
    # before the final closing brace - a plain find('{')/rfind('}') extraction
    # can't recover from that, but a balanced-bracket repair can.
    narration_data = repair_and_parse_json(response_text)
    if narration_data is None:
        return None

    if "slides" not in narration_data or not isinstance(narration_data["slides"], list):
        return None

    narrations = {}
    for slide_data in narration_data["slides"]:
        if "slide_number" in slide_data and "narration_text" in slide_data:
            slide_num = slide_data["slide_number"]
            narrations[slide_num] = {
                "slide_number": slide_num,
                "narration_text": slide_data["narration_text"]
            }
    return narrations


def _call_llm_for_narrations(content_dict: Dict[int, str], education_level: str,
                            file_name: str, model_name: str) -> Optional[Dict[int, Dict[str, Any]]]:
    """Run one LLM call for the given slides and return parsed narrations, or None on any failure."""
    system_prompt = create_system_prompt(education_level)
    user_prompt = create_user_prompt(content_dict, education_level, file_name)
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    response_text = ""
    try:
        for chunk in stream_llm(full_prompt, model_name):
            response_text += chunk
    except Exception as e:
        log_debug("NARRATION", "ERROR", f"Error during LLM streaming: {str(e)}")
        return None

    return _parse_narration_response(response_text)


def _build_fallback_narration(slide_text: str) -> str:
    """
    Build a simple narration directly from the slide's source text.

    Used only when the LLM omits a slide even after a retry, so a single
    uncooperative slide never leaves a hole that breaks downstream audio/video
    generation. Not LLM-quality narration, just enough spoken content to keep
    the slide playable.
    """
    text = " ".join(slide_text.split())
    if not text:
        return "Let's move on to the next part of this presentation."
    words = text.split()
    if len(words) > 120:
        text = " ".join(words[:120]) + "..."
    return f"Let's take a look at this slide: {text}"


def generate_slide_narrations(content_dict: Dict[int, str], education_level: str,
                            file_name: str, model_name: str) -> Dict[str, Any]:
    """
    Generate narrations for all slides using a single API call.

    LLMs - especially small local models - sometimes silently drop a slide from
    the requested batch even when the JSON they return is otherwise well-formed.
    Previously, any such gap propagated downstream: no narration meant no audio
    file for that slide, which then failed the *entire* video export (see
    video_generator.validate_slideshow_data). To keep one dropped slide from
    breaking the whole pipeline, this function now:
      1. Detects any requested slide numbers missing from the response.
      2. Retries once, asking only for the missing slides.
      3. Falls back to a simple text-derived narration for any slide still
         missing after the retry, so every requested slide always ends up with
         a narration.

    Args:
        content_dict: Dictionary of slide/page content
        education_level: Target education level
        file_name: Name of the source file
        model_name: LLM model to use

    Returns:
        Dict with generation results
    """
    log_debug("NARRATION", "INFO", f"Generating narrations for {len(content_dict)} slides using single API call")

    try:
        narrations = _call_llm_for_narrations(content_dict, education_level, file_name, model_name)

        if narrations is None:
            # Distinguish "LLM call failed outright" from "parsed empty" only for
            # logging purposes; both are a hard failure since we have nothing to work with.
            log_debug("NARRATION", "ERROR", "LLM call failed or returned an unparseable response")
            return {
                "success": False,
                "error": "Failed to generate narrations: LLM returned an error or invalid response"
            }

        errors = []
        missing_slides = sorted(set(content_dict.keys()) - set(narrations.keys()))

        if missing_slides:
            log_debug("NARRATION", "WARNING",
                     f"LLM omitted {len(missing_slides)} slide(s): {missing_slides}. Retrying just those.")
            retry_content = {num: content_dict[num] for num in missing_slides}
            retry_narrations = _call_llm_for_narrations(retry_content, education_level, file_name, model_name)

            if retry_narrations:
                narrations.update(retry_narrations)
                missing_slides = sorted(set(content_dict.keys()) - set(narrations.keys()))

            # Anything still missing gets a text-derived fallback so no slide is ever dropped.
            for slide_num in missing_slides:
                narrations[slide_num] = {
                    "slide_number": slide_num,
                    "narration_text": _build_fallback_narration(content_dict[slide_num])
                }
                errors.append(f"Slide {slide_num}: LLM did not generate a narration; used basic fallback text")
                log_debug("NARRATION", "WARNING", f"Slide {slide_num}: using fallback narration")

        log_debug("NARRATION", "SUCCESS", f"Successfully generated narrations for {len(narrations)} slides")
        return {
            "success": True,
            "narrations": narrations,
            "total_processed": len(narrations),
            "total_errors": len(errors),
            "errors": errors
        }

    except Exception as e:
        error_msg = f"Error generating narrations: {str(e)}"
        log_debug("NARRATION", "ERROR", error_msg)
        return {
            "success": False,
            "error": error_msg
        }


