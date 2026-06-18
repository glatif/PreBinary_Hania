"""
Slideshow Player for Narrated Slideshow Feature

This module handles the manual navigation of slides with audio narration,
providing a simplified and reliable user experience.
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional
import streamlit as st

# Import slide visualization
from .slide_visualizer import display_slide_image

def log_debug(phase: str, status: str, message: str) -> None:
    """Log debug messages with consistent formatting"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[NARRATED_SLIDESHOW] [{timestamp}] [{phase}] [{status}] {message}")

def get_audio_duration(audio_file_path: str) -> float:
    """
    Get audio duration from file using mutagen or fallback methods
    
    Args:
        audio_file_path: Path to the audio file
        
    Returns:
        Duration in seconds, or default 5.0 if unable to determine
    """
    try:
        # Try using mutagen first
        from mutagen.mp3 import MP3
        from mutagen.wave import WAVE
        from mutagen import File
        
        audio_file = File(audio_file_path)
        if audio_file and hasattr(audio_file, 'info') and hasattr(audio_file.info, 'length'):
            duration = audio_file.info.length
            log_debug("PLAYER", "INFO", f"Audio duration from mutagen: {duration:.2f}s")
            return duration
            
    except ImportError:
        log_debug("PLAYER", "WARNING", "mutagen not available for audio duration detection")
    except Exception as e:
        log_debug("PLAYER", "WARNING", f"Error getting audio duration with mutagen: {str(e)}")
    
    try:
        # Fallback: try using pydub
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_file_path)
        duration = len(audio) / 1000.0  # Convert from milliseconds to seconds
        log_debug("PLAYER", "INFO", f"Audio duration from pydub: {duration:.2f}s")
        return duration
        
    except ImportError:
        log_debug("PLAYER", "WARNING", "pydub not available for audio duration detection")
    except Exception as e:
        log_debug("PLAYER", "WARNING", f"Error getting audio duration with pydub: {str(e)}")
    
    # Final fallback
    log_debug("PLAYER", "WARNING", "Using default duration of 5.0 seconds")
    return 5.0


def check_quiz_placement(current_slide: int, target_slide: int, quiz_questions: Dict[int, Dict]) -> Optional[Dict]:
    """
    Check if there's a quiz question that should block navigation
    
    Args:
        current_slide: Current slide number
        target_slide: Target slide number
        quiz_questions: Dictionary of quiz questions keyed by slide_number_after
        
    Returns:
        Quiz question data if navigation should be blocked, None otherwise
    """
    if not quiz_questions or target_slide <= current_slide:
        return None
    
    # Check if there's a quiz question between current and target slide
    for slide_after in range(current_slide, target_slide):
        if slide_after in quiz_questions:
            question_data = quiz_questions[slide_after]
            question_type = question_data["question_type"]
            question_key = f"slide_{slide_after}_{question_type.lower()}"
            quiz_completion_key = f"quiz_completed_{question_key}"
            
            # Check if this quiz is not completed
            if not st.session_state.get(quiz_completion_key, False):
                return question_data
    
    return None

def render_slideshow_player(slide_content: Dict[int, str], 
                          audio_files: Dict[int, Dict],
                          narrations: Dict[int, Dict],
                          slide_images: Optional[Dict[int, bytes]] = None) -> None:
    """
    Render the interactive slideshow player with manual navigation controls
    
    Args:
        slide_content: Dictionary of slide content
        audio_files: Dictionary of audio file information
        narrations: Dictionary of slide narrations
        slide_images: Optional dictionary of slide images
    """
    log_debug("PLAYER", "INFO", "Rendering slideshow player with manual controls")
    
    if not slide_content or not audio_files:
        st.warning("⚠️ No slides or audio files available for playback.")
        return
    
    # Initialize simple session state (only current slide needed)
    if "slideshow_current_slide" not in st.session_state:
        st.session_state.slideshow_current_slide = 1
    
    # Get basic info
    total_slides = len(slide_content)
    current_slide_num = st.session_state.slideshow_current_slide
    
    # Ensure current slide is within bounds
    if current_slide_num > total_slides:
        st.session_state.slideshow_current_slide = total_slides
        current_slide_num = total_slides
    elif current_slide_num < 1:
        st.session_state.slideshow_current_slide = 1
        current_slide_num = 1
    
    # Get current slide data
    current_slide_content = slide_content.get(current_slide_num, "")
    current_audio_info = audio_files.get(current_slide_num, {})
    current_narration = narrations.get(current_slide_num, {})
    
    # === MAIN SLIDE DISPLAY ===
    st.markdown(f"### 📄 Slide {current_slide_num} of {total_slides}")
    
    # Display slide image or content
    if slide_images and current_slide_num in slide_images:
        display_slide_image(
            current_slide_num, 
            slide_images[current_slide_num],
            f"Slide {current_slide_num} of {total_slides}"
        )
    else:
        # Fallback: show content as text preview
        st.text_area(
            "Slide Content:",
            value=current_slide_content,
            height=300,
            disabled=True,
            key=f"slide_preview_{current_slide_num}"
        )
    
    # Show narration text
    narration_text = current_narration.get("narration_text", "")
    if narration_text:
        st.text_area(
            "Narration for this slide:",
            value=narration_text,
            height=100,
            disabled=True,
            key=f"narration_display_{current_slide_num}"
        )
    
    st.divider()
    
    # Get quiz questions for navigation blocking
    quiz_questions = st.session_state.get("slideshow_quiz_questions", {})
    
    # Main control layout: [Previous] [Audio Player] [Next]
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        # Previous Button - no quiz blocking for going backwards
        prev_disabled = current_slide_num <= 1
        if st.button("⏮️ Previous", 
                    use_container_width=True, 
                    disabled=prev_disabled,
                    key="prev_btn",
                    help="Go to previous slide" if not prev_disabled else "No previous slide"):
            if current_slide_num > 1:
                st.session_state.slideshow_current_slide -= 1
                log_debug("PLAYER", "INFO", f"Navigate to slide {st.session_state.slideshow_current_slide}")
                st.rerun()
    
    with col2:
        # Audio Player (Center)
        audio_file = current_audio_info.get("filepath")
        if audio_file and os.path.exists(audio_file):
            with open(audio_file, "rb") as audio_file_obj:
                audio_bytes = audio_file_obj.read()
            
            # Display audio player with automatic playback controls
            st.audio(audio_bytes, format="audio/mp3")
            
        else:
            st.warning("⚠️ Audio file not found for this slide")
            log_debug("PLAYER", "WARNING", f"Audio file not found: {audio_file}")
    
    with col3:
        # Next Button - check for quiz blocking
        next_disabled = current_slide_num >= total_slides
        
        # Check if there's a quiz blocking forward navigation
        quiz_blocking = False
        if not next_disabled and quiz_questions:
            blocking_quiz = check_quiz_placement(current_slide_num, current_slide_num + 1, quiz_questions)
            if blocking_quiz:
                quiz_blocking = True
                next_disabled = True
        
        if st.button("⏭️ Next", 
                    use_container_width=True,
                    disabled=next_disabled,
                    key="next_btn",
                    help="Go to next slide" if not next_disabled and not quiz_blocking else 
                         ("Complete the quiz to continue" if quiz_blocking else "No next slide")):
            if current_slide_num < total_slides and not quiz_blocking:
                st.session_state.slideshow_current_slide += 1
                log_debug("PLAYER", "INFO", f"Navigate to slide {st.session_state.slideshow_current_slide}")
                st.rerun()
    
    # Show quiz blocking message if applicable
    if quiz_blocking:
        st.warning("🔒 **Quiz Required:** Complete the quiz question to proceed to the next slide.")
    # Overall progress indicator
    overall_progress = (current_slide_num - 1) / max(total_slides - 1, 1)
    st.progress(overall_progress, text=f"Slide {current_slide_num} of {total_slides}")
    
    # Additional controls row
    st.markdown("#### Additional Controls")
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("🏠 First Slide", use_container_width=True, key="first_btn"):
            if current_slide_num != 1:
                st.session_state.slideshow_current_slide = 1
                log_debug("PLAYER", "INFO", "Navigate to first slide")
                st.rerun()
    
    with col2:
        # Disable last slide button if there are incomplete quizzes
        last_slide_disabled = False
        if quiz_questions:
            blocking_quiz = check_quiz_placement(current_slide_num, total_slides, quiz_questions)
            if blocking_quiz:
                last_slide_disabled = True
        
        if st.button("🔚 Last Slide", 
                    use_container_width=True, 
                    key="last_btn",
                    disabled=last_slide_disabled,
                    help="Jump to last slide" if not last_slide_disabled else "Complete all quizzes to access"):
            if current_slide_num != total_slides and not last_slide_disabled:
                st.session_state.slideshow_current_slide = total_slides
                log_debug("PLAYER", "INFO", f"Navigate to last slide ({total_slides})")
                st.rerun()
    
    with col3:
        # Slide selector - restrict based on quiz completion
        max_accessible_slide = total_slides
        if quiz_questions:
            # Find the furthest slide that can be accessed
            for slide_num in range(1, total_slides + 1):
                blocking_quiz = check_quiz_placement(1, slide_num, quiz_questions)
                if blocking_quiz:
                    max_accessible_slide = slide_num - 1
                    break
        
        accessible_slides = list(range(1, max_accessible_slide + 1))
        
        selected_slide = st.selectbox(
            "Jump to slide:",
            options=accessible_slides,
            index=min(current_slide_num - 1, len(accessible_slides) - 1),
            key="slide_selector",
            help="Select a slide to jump to directly" if len(accessible_slides) == total_slides 
                 else f"Only slides 1-{max_accessible_slide} accessible (complete quizzes to unlock more)"
        )
        if selected_slide != current_slide_num and selected_slide in accessible_slides:
            st.session_state.slideshow_current_slide = selected_slide
            log_debug("PLAYER", "INFO", f"Jump to slide {selected_slide}")
            st.rerun()
    
   
    
    log_debug("PLAYER", "SUCCESS", f"Rendered manual slideshow player for {total_slides} slides")
