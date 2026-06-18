"""
Narrated Slideshow Feature - Main UI Component (Restructured)

This module provides the main user interface for the narrated slideshow feature,
allowing professors to upload PDF/PPT files and generate auto-narrated presentations.
"""

import streamlit as st
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Import feature modules
from .document_processor import process_uploaded_file, validate_file_limits
from .narration_generator import generate_slide_narrations
from .tts_engine import generate_audio_batch, cleanup_audio_files, get_available_providers
from .slideshow_player import render_slideshow_player
from .slide_visualizer import extract_pdf_page_images, extract_ppt_slide_images

# Import video generation module
try:
    from .video_generator import generate_slideshow_video, get_video_generation_info, cleanup_video_files
    VIDEO_GENERATION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Video generation not available: {e}")
    VIDEO_GENERATION_AVAILABLE = False
    
    # Define fallback functions
    def generate_slideshow_video(*args, **kwargs):
        return {"success": False, "error": "Video generation module not available"}
    
    def get_video_generation_info():
        return {"moviepy_available": False, "moviepy_error": "MoviePy not installed"}
    
    def cleanup_video_files(*args, **kwargs):
        pass

# Import quiz modules with try/except for graceful fallback
try:
    from .quiz_generator import generate_quiz_questions
    from .quiz_ui_components import render_quiz_overlay, get_quiz_status_indicator, render_quiz_progress_summary
    QUIZ_MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Quiz modules not available: {e}")
    QUIZ_MODULES_AVAILABLE = False
    
    # Define fallback functions
    def generate_quiz_questions(*args, **kwargs):
        return {"success": False, "error": "Quiz generation module not available"}
    
    def render_quiz_overlay(*args, **kwargs):
        return False
    
    def get_quiz_status_indicator(*args, **kwargs):
        return None
    
    def render_quiz_progress_summary(*args, **kwargs):
        pass

# Import existing LLM utilities
from src.utils.llm_utils import MODELS, MODEL_PROVIDERS

def log_debug(phase: str, status: str, message: str) -> None:
    """Log debug messages with consistent formatting"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[NARRATED_SLIDESHOW] [{timestamp}] [{phase}] [{status}] {message}")

def initialize_slideshow_session_state():
    """Initialize session state variables for the narrated slideshow feature"""
    log_debug("INIT", "INFO", "Initializing session state variables")
    
    if "slideshow_uploaded_file" not in st.session_state:
        st.session_state.slideshow_uploaded_file = None
    if "slideshow_extracted_content" not in st.session_state:
        st.session_state.slideshow_extracted_content = {}
    if "slideshow_education_level" not in st.session_state:
        st.session_state.slideshow_education_level = "Undergraduate"
    if "slideshow_file_processed" not in st.session_state:
        st.session_state.slideshow_file_processed = False
    if "slideshow_processing_error" not in st.session_state:
        st.session_state.slideshow_processing_error = None
    
    # Phase 2+ additions
    if "slideshow_selected_model" not in st.session_state:
        st.session_state.slideshow_selected_model = list(MODELS.keys())[0] if MODELS else "llama3.2"
    if "slideshow_narrations_generated" not in st.session_state:
        st.session_state.slideshow_narrations_generated = False
    if "slideshow_narrations" not in st.session_state:
        st.session_state.slideshow_narrations = {}
    if "slideshow_audio_generated" not in st.session_state:
        st.session_state.slideshow_audio_generated = False
    if "slideshow_audio_files" not in st.session_state:
        st.session_state.slideshow_audio_files = {}
    if "slideshow_current_phase" not in st.session_state:
        st.session_state.slideshow_current_phase = 1
    if "slideshow_slide_images" not in st.session_state:
        st.session_state.slideshow_slide_images = {}
    
    # TTS provider settings
    if "slideshow_tts_provider" not in st.session_state:
        st.session_state.slideshow_tts_provider = "google"
    if "slideshow_tts_api_key" not in st.session_state:
        st.session_state.slideshow_tts_api_key = None
    
    # Quiz-related session state variables
    if "slideshow_quiz_frequency" not in st.session_state:
        st.session_state.slideshow_quiz_frequency = "None"
    if "slideshow_quiz_type" not in st.session_state:
        st.session_state.slideshow_quiz_type = "Mixed"
    if "slideshow_quiz_generated" not in st.session_state:
        st.session_state.slideshow_quiz_generated = False
    if "slideshow_quiz_questions" not in st.session_state:
        st.session_state.slideshow_quiz_questions = {}
    if "slideshow_current_quiz" not in st.session_state:
        st.session_state.slideshow_current_quiz = None
    if "slideshow_quiz_answers" not in st.session_state:
        st.session_state.slideshow_quiz_answers = {}
    if "slideshow_quiz_blocking_navigation" not in st.session_state:
        st.session_state.slideshow_quiz_blocking_navigation = False
    if "slideshow_quiz_completion_status" not in st.session_state:
        st.session_state.slideshow_quiz_completion_status = {}
    
    # Video generation session state variables
    if "slideshow_video_generated" not in st.session_state:
        st.session_state.slideshow_video_generated = False
    if "slideshow_video_file_path" not in st.session_state:
        st.session_state.slideshow_video_file_path = None
    if "slideshow_video_generation_progress" not in st.session_state:
        st.session_state.slideshow_video_generation_progress = 0
    if "slideshow_video_generation_status" not in st.session_state:
        st.session_state.slideshow_video_generation_status = ""
    if "slideshow_video_info" not in st.session_state:
        st.session_state.slideshow_video_info = {}
    


def render_input_tab():
    """Render the Input tab with clean, minimalistic sections"""
    st.header("📁 Input Configuration")
    
    # Configuration section in columns
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🎓 Education Level")
        education_levels = ["High School", "Undergraduate", "Postgraduate", "PhD"]
        
        selected_level = st.selectbox(
            "Choose the appropriate education level:",
            education_levels,
            index=education_levels.index(st.session_state.slideshow_education_level),
            key="education_level_selector_main"
        )
        
        if selected_level != st.session_state.slideshow_education_level:
            st.session_state.slideshow_education_level = selected_level
            log_debug("UI", "INFO", f"Education level changed to: {selected_level}")
    
    with col2:
        st.subheader("🤖 AI Model")
        available_models = list(MODELS.keys()) if MODELS else ["llama3.2"]
        
        # Resolve the saved preference written by _load_model_preferences() at
        # login into slideshow_selected_model (mapped from pref_model_video_lectures).
        saved_slideshow_model = st.session_state.get("slideshow_selected_model", available_models[0])
        if saved_slideshow_model not in available_models:
            saved_slideshow_model = available_models[0]

        selected_model = st.selectbox(
            "Choose AI model:",
            available_models,
            index=available_models.index(saved_slideshow_model),
            key="slideshow_model_selector_main",
        )
        
        if selected_model != st.session_state.slideshow_selected_model:
            st.session_state.slideshow_selected_model = selected_model
            log_debug("UI", "INFO", f"Model changed to: {selected_model}")
    
    st.divider()
    
    # Section 1: Document Upload
    st.subheader("📂 Document Upload")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Choose your presentation file",
            type=['pdf', 'ppt', 'pptx'],
            key="slideshow_file_uploader_main"
        )
    
    with col2:
        st.markdown("**Audio Provider**")
        tts_options = ["Google TTS (Free)", "ElevenLabs (Premium)", "Cartesia AI (Premium)"]
        selected_tts = st.selectbox(
            "TTS Provider:",
            tts_options,
            index=0,
            key="tts_model_selector_main"
        )
        
        # Store TTS provider
        if selected_tts == "Google TTS (Free)":
            st.session_state.slideshow_tts_provider = "google"
            st.session_state.slideshow_tts_api_key = None
        elif selected_tts == "ElevenLabs (Premium)":
            st.session_state.slideshow_tts_provider = "elevenlabs"
            api_key = st.text_input(
                "API Key:",
                type="password",
                key="elevenlabs_api_key_main",
                placeholder="Enter ElevenLabs API key"
            )
            st.session_state.slideshow_tts_api_key = api_key if api_key else None
        elif selected_tts == "Cartesia AI (Premium)":
            st.session_state.slideshow_tts_provider = "cartesia"
            api_key = st.text_input(
                "API Key:",
                type="password", 
                key="cartesia_api_key_main",
                placeholder="Enter Cartesia AI API key"
            )
            st.session_state.slideshow_tts_api_key = api_key if api_key else None
    
    # Show file info if uploaded
    if uploaded_file is not None:
        # Reset state for new file
        if (st.session_state.slideshow_uploaded_file is None or 
            st.session_state.slideshow_uploaded_file.name != uploaded_file.name):
            
            st.session_state.slideshow_uploaded_file = uploaded_file
            st.session_state.slideshow_file_processed = False
            st.session_state.slideshow_extracted_content = {}
            st.session_state.slideshow_processing_error = None
            st.session_state.slideshow_narrations_generated = False
            st.session_state.slideshow_narrations = {}
            st.session_state.slideshow_audio_generated = False
            st.session_state.slideshow_audio_files = {}
        
        # File validation
        validation_result = validate_file_limits(uploaded_file)
        if validation_result["valid"]:
            st.success(f"✅ {uploaded_file.name} ready for processing")
            
            st.divider()
            
            # Section 2: Quiz Configuration
            st.subheader("🎯 Quiz Configuration")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                quiz_enabled = st.toggle(
                    "Enable Quiz Questions",
                    value=st.session_state.slideshow_quiz_frequency != "None",
                    key="quiz_toggle_main"
                )
                
                if quiz_enabled and st.session_state.slideshow_quiz_frequency == "None":
                    st.session_state.slideshow_quiz_frequency = "Frequent"
                elif not quiz_enabled:
                    st.session_state.slideshow_quiz_frequency = "None"
            
            with col2:
                if quiz_enabled:
                    frequency_options = ["Less Frequent", "Frequent", "Very Frequent"]
                    selected_frequency = st.selectbox(
                        "Question Frequency:",
                        frequency_options,
                        index=frequency_options.index(st.session_state.slideshow_quiz_frequency) if st.session_state.slideshow_quiz_frequency in frequency_options else 1,
                        key="quiz_frequency_selector_main"
                    )
                    
                    if selected_frequency != st.session_state.slideshow_quiz_frequency:
                        st.session_state.slideshow_quiz_frequency = selected_frequency
                        st.session_state.slideshow_quiz_generated = False
                        st.session_state.slideshow_quiz_questions = {}
                else:
                    st.info("Quiz disabled")
            
            with col3:
                if quiz_enabled:
                    question_type_options = ["Mixed", "MCQs Only", "True/False Only"]
                    selected_question_type = st.selectbox(
                        "Question Type:",
                        question_type_options,
                        index=question_type_options.index(st.session_state.slideshow_quiz_type),
                        key="quiz_type_selector_main"
                    )
                    
                    if selected_question_type != st.session_state.slideshow_quiz_type:
                        st.session_state.slideshow_quiz_type = selected_question_type
                        st.session_state.slideshow_quiz_generated = False
                        st.session_state.slideshow_quiz_questions = {}
                else:
                    st.info("No questions")
            
            st.divider()
            
            # Section 3: Processing Steps
            st.subheader("⚡ Processing")
            
            # Step 1: Process File
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.session_state.slideshow_file_processed:
                    st.success("✅ File processed successfully")
                else:
                    st.info("📄 Extract content from document")
            with col2:
                if not st.session_state.slideshow_file_processed:
                    if st.button("Process", type="primary", key="process_btn"):
                        process_uploaded_document()
                else:
                    st.success("Done")
            
            # Step 2: Generate Narrations
            if st.session_state.slideshow_file_processed:
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.session_state.slideshow_narrations_generated:
                        st.success("✅ Narrations generated successfully")
                    else:
                        st.info("🎙️ Generate AI narrations for slides")
                with col2:
                    if not st.session_state.slideshow_narrations_generated:
                        if st.button("Generate", type="primary", key="narrations_btn"):
                            generate_narrations()
                    else:
                        st.success("Done")
            
            # Step 3: Generate Quiz (if enabled)
            if st.session_state.slideshow_narrations_generated and quiz_enabled:
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.session_state.slideshow_quiz_generated:
                        quiz_count = len(st.session_state.slideshow_quiz_questions)
                        st.success(f"✅ Generated {quiz_count} quiz questions")
                    else:
                        st.info("🎯 Generate quiz questions")
                with col2:
                    if not st.session_state.slideshow_quiz_generated:
                        if st.button("Generate", type="primary", key="quiz_btn"):
                            generate_quiz_questions_wrapper()
                    else:
                        st.success("Done")
            
            # Step 4: Generate Audio
            quiz_ready = (not quiz_enabled or st.session_state.slideshow_quiz_generated)
            if st.session_state.slideshow_narrations_generated and quiz_ready:
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.session_state.slideshow_audio_generated:
                        audio_count = len(st.session_state.slideshow_audio_files)
                        st.success(f"✅ Generated {audio_count} audio files")
                    else:
                        provider_name = {
                            "google": "Google TTS",
                            "cartesia": "Cartesia AI", 
                            "elevenlabs": "ElevenLabs"
                        }.get(st.session_state.slideshow_tts_provider, "TTS")
                        st.info(f"🔊 Generate audio using {provider_name}")
                with col2:
                    if not st.session_state.slideshow_audio_generated:
                        if st.button("Generate", type="primary", key="audio_btn"):
                            generate_audio_files()
                    else:
                        st.success("Done")
            
            # Completion
            if st.session_state.slideshow_audio_generated:
                st.success("🎉 **Slideshow Ready!** Go to the Slideshow tab to present.")
                st.balloons()
        else:
            st.error(f"❌ {validation_result['message']}")
    
    else:
        st.info("👆 Upload a PDF or PowerPoint file to get started")
    
    # Error display
    if st.session_state.slideshow_processing_error:
        st.error(f"❌ {st.session_state.slideshow_processing_error}")
    
    # Content preview (minimalistic)
    if st.session_state.slideshow_file_processed and st.session_state.slideshow_extracted_content:
        with st.expander("📄 Content Preview", expanded=False):
            content = st.session_state.slideshow_extracted_content
            st.info(f"📊 {len(content)} slides extracted")
            
            if content:
                first_slide = list(content.keys())[0]
                first_content = str(content[first_slide])[:200] + "..."
                st.text_area("Sample:", value=first_content, height=80, disabled=True)
    
    # Quiz preview (minimalistic)
    if st.session_state.slideshow_quiz_generated and st.session_state.slideshow_quiz_questions:
        with st.expander("🎯 Quiz Preview", expanded=False):
            quiz_questions = st.session_state.slideshow_quiz_questions
            st.info(f"📊 {len(quiz_questions)} questions generated")
            
            for slide_after in sorted(list(quiz_questions.keys())[:2]):  # Show first 2 only
                question_data = quiz_questions[slide_after]
                st.write(f"**After slide {slide_after}:** {question_data.get('question_text', '')[:100]}...")
            
            if len(quiz_questions) > 2:
                st.write(f"... and {len(quiz_questions) - 2} more questions")

def render_slideshow_tab():
    """Render the Slideshow tab with player and controls"""
    if not st.session_state.slideshow_audio_generated or not st.session_state.slideshow_audio_files:
        st.info("🎬 Complete the setup in the Input tab to start your slideshow")
        
        # Show current progress
        progress_items = [
            ("📄 File Upload", st.session_state.slideshow_uploaded_file is not None),
            ("🔄 File Processing", st.session_state.slideshow_file_processed),
            ("🎙️ Narration Generation", st.session_state.slideshow_narrations_generated),
        ]
        
        # Add quiz progress if enabled
        if st.session_state.slideshow_quiz_frequency != "None":
            progress_items.append(("🎯 Quiz Generation", st.session_state.slideshow_quiz_generated))
        
        progress_items.append(("🔊 Audio Generation", st.session_state.slideshow_audio_generated))
        
        st.markdown("**Setup Progress:**")
        for item, completed in progress_items:
            status = "✅" if completed else "⏳"
            st.markdown(f"{status} {item}")
        
        return
    
    st.header("🎬 Interactive Slideshow")
    
    # Show quiz status if enabled
    if st.session_state.slideshow_quiz_frequency != "None" and st.session_state.slideshow_quiz_questions:
        quiz_status = get_quiz_status_indicator(
            st.session_state.slideshow_quiz_questions, 
            st.session_state.get("slideshow_current_slide", 1)
        )
        if quiz_status:
            st.info(quiz_status)
    
    # Check if we should show a quiz overlay
    current_slide = st.session_state.get("slideshow_current_slide", 1)
    
    # Check if there's a quiz question that should appear after the previous slide
    quiz_to_show = None
    if (st.session_state.slideshow_quiz_frequency != "None" and 
        st.session_state.slideshow_quiz_questions and
        current_slide > 1):
        
        # Look for quiz questions that should appear after the previous slide
        prev_slide = current_slide - 1
        if prev_slide in st.session_state.slideshow_quiz_questions:
            quiz_to_show = st.session_state.slideshow_quiz_questions[prev_slide]
            
            # Check if this quiz is already completed
            question_type = quiz_to_show["question_type"]
            question_key = f"slide_{prev_slide}_{question_type.lower()}"
            quiz_completion_key = f"quiz_completed_{question_key}"
            
            if not st.session_state.get(quiz_completion_key, False):
                # Quiz needs to be shown
                st.session_state.slideshow_current_quiz = quiz_to_show
                st.session_state.slideshow_quiz_blocking_navigation = True
    
    # Show quiz overlay if there's an active quiz
    if (st.session_state.get("slideshow_current_quiz") and 
        st.session_state.get("slideshow_quiz_blocking_navigation", False)):
        
        quiz_data = st.session_state.slideshow_current_quiz
        slide_after = None
        
        # Find which slide this quiz comes after
        for slide_num, question_data in st.session_state.slideshow_quiz_questions.items():
            if question_data == quiz_data:
                slide_after = slide_num
                break
        
        if slide_after is not None:
            quiz_completed = render_quiz_overlay(quiz_data, slide_after)
            
            if quiz_completed:
                # Quiz was completed, clear the blocking state
                st.session_state.slideshow_current_quiz = None
                st.session_state.slideshow_quiz_blocking_navigation = False
                # Force a rerun to show the slideshow content
                st.rerun()
            return  # Don't show slideshow while quiz is active
    
    # Render the slideshow player
    render_slideshow_player(
        st.session_state.slideshow_extracted_content,
        st.session_state.slideshow_audio_files,
        st.session_state.slideshow_narrations,
        st.session_state.slideshow_slide_images
    )
    
    # Show quiz progress summary at the bottom if quizzes are enabled
    if (st.session_state.slideshow_quiz_frequency != "None" and 
        st.session_state.slideshow_quiz_questions):
        st.markdown("---")
        render_quiz_progress_summary(st.session_state.slideshow_quiz_questions)
    
    # Video Generation Section
    render_video_generation_section()

def process_uploaded_document():
    """Process the uploaded document and extract text content"""
    if st.session_state.slideshow_uploaded_file is None:
        log_debug("PROCESSING", "ERROR", "No file to process")
        st.error("❌ No file selected for processing")
        return
    
    log_debug("PROCESSING", "INFO", "Starting document processing")
    log_debug("PROCESSING", "INFO", f"Processing file: {st.session_state.slideshow_uploaded_file.name}")
    
    with st.spinner("🔄 Processing document and extracting text..."):
        try:
            # Process the file
            result = process_uploaded_file(st.session_state.slideshow_uploaded_file)
            log_debug("PROCESSING", "INFO", f"Process result: {result.get('success', False)}")
            
            if result["success"]:
                st.session_state.slideshow_extracted_content = result["content"]
                st.session_state.slideshow_file_processed = True
                st.session_state.slideshow_processing_error = None
                st.session_state.slideshow_current_phase = max(st.session_state.slideshow_current_phase, 2)
                
                # Extract slide images for visual preview
                log_debug("PROCESSING", "INFO", "Extracting slide images for preview")
                file_type = st.session_state.slideshow_uploaded_file.type.lower()
                
                if 'pdf' in file_type:
                    slide_images = extract_pdf_page_images(
                        st.session_state.slideshow_uploaded_file,
                        max_pages=25
                    )
                elif 'presentation' in file_type or 'powerpoint' in file_type:
                    slide_images = extract_ppt_slide_images(
                        st.session_state.slideshow_uploaded_file,
                        max_slides=20
                    )
                else:
                    slide_images = {}
                
                st.session_state.slideshow_slide_images = slide_images
                log_debug("PROCESSING", "INFO", f"Extracted {len(slide_images)} slide images")
                
                log_debug("PROCESSING", "SUCCESS", 
                         f"Successfully extracted text from {len(result['content'])} pages/slides")
                
                # Calculate total characters
                total_chars = sum(len(str(text)) for text in result["content"].values())
                log_debug("PROCESSING", "INFO", f"Total characters extracted: {total_chars}")
                
                st.success(f"✅ Successfully processed {len(result['content'])} pages/slides with {total_chars:,} characters!")
                
                # Show a quick preview
                if result["content"]:
                    first_page = list(result["content"].keys())[0]
                    first_content = str(result["content"][first_page])[:100]
                    st.info(f"Preview of page/slide {first_page}: {first_content}...")
                
                st.rerun()
                
            else:
                st.session_state.slideshow_processing_error = result["error"]
                log_debug("PROCESSING", "ERROR", f"Processing failed: {result['error']}")
                st.error(f"❌ Processing failed: {result['error']}")
                
        except Exception as e:
            error_msg = f"Unexpected error during processing: {str(e)}"
            st.session_state.slideshow_processing_error = error_msg
            log_debug("PROCESSING", "ERROR", error_msg)
            st.error(f"❌ {error_msg}")

def generate_quiz_questions_wrapper():
    """Generate quiz questions for the slideshow"""
    log_debug("QUIZ", "INFO", "Starting quiz generation")
    
    # Check if we have narrations to work with
    if not st.session_state.slideshow_narrations:
        st.error("❌ No narrations available. Please generate narrations first.")
        return
    
    # Check if quiz is disabled
    if st.session_state.slideshow_quiz_frequency == "None":
        st.info("ℹ️ Quiz generation is disabled. Change frequency to enable.")
        return
    
    # Check if we have the necessary API key for the selected model
    selected_model_display = st.session_state.slideshow_selected_model
    model_id = MODELS.get(selected_model_display, selected_model_display)
    model_provider = MODEL_PROVIDERS.get(model_id, "ollama")
    
    # Check API key availability
    if model_provider == "groq" and not st.session_state.get("groq_api_key"):
        st.error("⚠️ Groq API key is required for this model. Please add your API key in your profile settings.")
        return
    elif model_provider == "openai" and not st.session_state.get("openai_api_key"):
        st.error("⚠️ OpenAI API key is required for this model. Please add your API key in your profile settings.")
        return
    elif model_provider == "gemini" and not st.session_state.get("gemini_api_key"):
        st.error("⚠️ Gemini API key is required for this model. Please add your API key in your profile settings.")
        return
    
    with st.spinner("🎯 Generating intelligent quiz questions... This may take a moment."):
        try:
            log_debug("QUIZ", "INFO", f"Using model: {model_id} for quiz generation")
            
            result = generate_quiz_questions(
                st.session_state.slideshow_narrations,
                st.session_state.slideshow_quiz_frequency,
                st.session_state.slideshow_quiz_type,
                st.session_state.slideshow_education_level,
                model_id
            )
            
            if result["success"]:
                # Convert list to dictionary keyed by slide_number_after
                quiz_dict = {}
                for question in result["quiz_questions"]:
                    slide_after = question["slide_number_after"]
                    quiz_dict[slide_after] = question
                
                st.session_state.slideshow_quiz_questions = quiz_dict
                st.session_state.slideshow_quiz_generated = True
                
                success_msg = f"Successfully generated {result['total_questions']} quiz questions"
                st.success(f"✅ {success_msg}")
                log_debug("QUIZ", "SUCCESS", success_msg)
                
                # Show quiz placement summary
                slide_placements = sorted(result.get("slide_numbers_used", []))
                if slide_placements:
                    st.info(f"📍 **Quiz Questions Placed After Slides:** {', '.join(map(str, slide_placements))}")
                
                if result.get("warnings"):
                    with st.expander("⚠️ View Warnings", expanded=False):
                        for warning in result["warnings"]:
                            st.warning(warning)
                
                st.rerun()
            else:
                error_msg = f"Failed to generate quiz questions: {result.get('error', 'Unknown error')}"
                st.error(f"❌ {error_msg}")
                log_debug("QUIZ", "ERROR", error_msg)
                
                # Show validation errors if available
                if result.get("validation_errors"):
                    with st.expander("🔍 View Detailed Errors", expanded=False):
                        for error in result["validation_errors"]:
                            st.error(error)
                
        except Exception as e:
            error_msg = f"Unexpected error during quiz generation: {str(e)}"
            st.error(f"❌ {error_msg}")
            log_debug("QUIZ", "ERROR", error_msg)

def generate_narrations():
    """Generate narrations for all slides"""
    log_debug("NARRATION", "INFO", "Starting narration generation")
    
    # Check if we have the necessary API key for the selected model
    selected_model_display = st.session_state.slideshow_selected_model
    model_id = MODELS.get(selected_model_display, selected_model_display)
    model_provider = MODEL_PROVIDERS.get(model_id, "ollama")
    
    # Check API key availability
    if model_provider == "groq" and not st.session_state.get("groq_api_key"):
        st.error("⚠️ Groq API key is required for this model. Please add your API key in your profile settings.")
        return
    elif model_provider == "openai" and not st.session_state.get("openai_api_key"):
        st.error("⚠️ OpenAI API key is required for this model. Please add your API key in your profile settings.")
        return
    elif model_provider == "gemini" and not st.session_state.get("gemini_api_key"):
        st.error("⚠️ Gemini API key is required for this model. Please add your API key in your profile settings.")
        return
    
    with st.spinner("🎬 Generating AI narrations... This may take a few minutes."):
        try:
            log_debug("NARRATION", "INFO", f"Using display name: {selected_model_display}, model ID: {model_id}, provider: {model_provider}")
            
            result = generate_slide_narrations(
                st.session_state.slideshow_extracted_content,
                st.session_state.slideshow_education_level,
                st.session_state.slideshow_uploaded_file.name,
                model_id
            )
            
            if result["success"]:
                st.session_state.slideshow_narrations = result["narrations"]
                st.session_state.slideshow_narrations_generated = True
                st.session_state.slideshow_current_phase = max(st.session_state.slideshow_current_phase, 3)
                
                success_msg = f"Successfully generated {result['total_processed']} narrations"
                if result["errors"]:
                    success_msg += f" ({result['total_errors']} errors)"
                
                st.success(f"✅ {success_msg}")
                log_debug("NARRATION", "SUCCESS", success_msg)
                
                if result["errors"]:
                    with st.expander("⚠️ View Errors", expanded=False):
                        for error in result["errors"]:
                            st.error(error)
                
                st.rerun()
            else:
                # Show detailed error messages instead of just "Unknown error"  
                error_details = result.get('error', 'Unknown error occurred')
                st.error(f"❌ **Failed to generate narrations:** {error_details}")
                log_debug("NARRATION", "ERROR", error_details)
                
        except Exception as e:
            error_msg = f"Unexpected error during narration generation: {str(e)}"
            st.error(f"❌ {error_msg}")
            log_debug("NARRATION", "ERROR", error_msg)

def render_narrations_preview():
    """Render preview of generated narrations with 2-column layout"""
    st.subheader("📝 Generated Narrations Preview")
    
    narrations = st.session_state.slideshow_narrations
    
    # Summary
    total_narration_chars = sum(len(n.get("narration_text", "")) for n in narrations.values())
    st.info(f"📊 **Summary:** {len(narrations)} narrations • {total_narration_chars:,} characters total")
    
    # Single expander with 2-column layout inside
    with st.expander(f"📖 View All Narrations ({len(narrations)} slides)", expanded=True):
        # Display all slides in a clean 2-column format
        for slide_num in sorted(narrations.keys()):
            narration_data = narrations[slide_num]
            narration_text = narration_data.get("narration_text", "")
            original_content = st.session_state.slideshow_extracted_content.get(slide_num, "")
            
            # Create a divider between slides
            if slide_num > 1:
                st.markdown("---")
            
            st.markdown(f"### 📄 Slide {slide_num}")
            
            # 2-column layout for content and narration
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("**📋 Original Content:**")
                st.text_area(
                    f"Slide {slide_num} content:",
                    value=original_content,
                    height=120,
                    disabled=True,
                    key=f"compact_original_{slide_num}",
                    label_visibility="collapsed"
                )
                
                # Quick metrics
                char_count = len(original_content)
                st.caption(f"📊 {char_count} characters")
            
            with col2:
                st.markdown("**🎙️ Generated Narration:**")
                st.text_area(
                    f"Slide {slide_num} narration:",
                    value=narration_text,
                    height=120,
                    disabled=True,
                    key=f"compact_narration_{slide_num}",
                    label_visibility="collapsed"
                )
                
                # Quick metrics
                narration_chars = len(narration_text)
                estimated_time = (narration_chars / 5) / 150 * 60  # seconds
                st.caption(f"📊 {narration_chars} characters • ~{estimated_time:.1f}s")

def render_quiz_preview():
    """Render preview of generated quiz questions"""
    st.subheader("🎯 Generated Quiz Questions Preview")
    
    quiz_questions = st.session_state.slideshow_quiz_questions
    
    # Summary
    total_questions = len(quiz_questions)
    mcq_count = sum(1 for q in quiz_questions.values() if q.get("question_type") == "MCQ")
    tf_count = sum(1 for q in quiz_questions.values() if q.get("question_type") == "True/False")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Questions", total_questions)
    with col2:
        st.metric("Multiple Choice", mcq_count)
    with col3:
        st.metric("True/False", tf_count)
    
    # Show placement information
    placement_info = []
    for slide_after in sorted(quiz_questions.keys()):
        question_data = quiz_questions[slide_after]
        question_type = question_data.get("question_type", "Unknown")
        placement_info.append(f"After slide {slide_after}: {question_type}")
    
    st.info(f"📍 **Question Placement:** {' • '.join(placement_info)}")
    
    # Detailed preview in expander
    with st.expander(f"📋 View All Quiz Questions ({total_questions} questions)", expanded=False):
        for slide_after in sorted(quiz_questions.keys()):
            question_data = quiz_questions[slide_after]
            question_type = question_data.get("question_type", "Unknown")
            question_text = question_data.get("question_text", "")
            correct_answer = question_data.get("correct_answer", "")
            
            # Create a divider between questions
            if slide_after != sorted(quiz_questions.keys())[0]:
                st.markdown("---")
            
            st.markdown(f"### 🎯 Question (After Slide {slide_after})")
            
            # Show question details
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown("**Question:**")
                st.write(question_text)
                
                if question_type == "MCQ":
                    options = question_data.get("options", [])
                    st.markdown("**Options:**")
                    for i, option in enumerate(options, 1):
                        prefix = "✅" if option == correct_answer else "  "
                        st.write(f"{prefix} {i}. {option}")
                else:
                    st.markdown("**Type:** True/False")
                    st.write(f"✅ Correct Answer: **{correct_answer}**")
            
            with col2:
                st.markdown("**Details:**")
                st.write(f"**Type:** {question_type}")
                st.write(f"**Placement:** After slide {slide_after}")
                
                # Character count for question
                question_chars = len(question_text)
                st.caption(f"📊 {question_chars} characters")

def generate_audio_files():
    """Generate audio files from narrations"""
    log_debug("AUDIO", "INFO", "Starting audio generation")
    
    # Get TTS provider and API key from session state
    tts_provider = st.session_state.get("slideshow_tts_provider", "google")
    api_key = st.session_state.get("slideshow_tts_api_key", None)
    
    # Check if API key is required and provided
    if tts_provider in ["cartesia", "elevenlabs"] and not api_key:
        st.error(f"❌ API key is required for {tts_provider.title()} TTS provider.")
        return
    
    provider_name = {
        "google": "Google TTS",
        "cartesia": "Cartesia AI", 
        "elevenlabs": "ElevenLabs"
    }.get(tts_provider, tts_provider)
    
    with st.spinner(f"🎵 Generating audio files using {provider_name}... This may take a few minutes."):
        try:
            result = generate_audio_batch(
                st.session_state.slideshow_narrations,
                tts_provider=tts_provider,
                api_key=api_key
            )
            
            if result["success"]:
                st.session_state.slideshow_audio_files = result["audio_files"]
                st.session_state.slideshow_audio_generated = True
                st.session_state.slideshow_current_phase = max(st.session_state.slideshow_current_phase, 4)
                
                total_duration = result.get("total_duration", 0)
                provider_used = result.get("provider", provider_name)
                success_msg = f"Generated {result['total_processed']} audio files using {provider_used} (Total: {total_duration:.1f}s)"
                
                st.success(f"✅ {success_msg}")
                log_debug("AUDIO", "SUCCESS", success_msg)
                
                if result["errors"]:
                    with st.expander("⚠️ Audio Generation Errors", expanded=False):
                        for error in result["errors"]:
                            st.error(error)
                
                st.rerun()
            else:
                error_msg = f"Failed to generate audio: {result.get('errors', ['Unknown error'])}"
                st.error(f"❌ {error_msg}")
                log_debug("AUDIO", "ERROR", error_msg)
                
        except Exception as e:
            error_msg = f"Unexpected error during audio generation: {str(e)}"
            st.error(f"❌ {error_msg}")
            log_debug("AUDIO", "ERROR", error_msg)

def update_video_progress(progress: float, status: str):
    """Update video generation progress in session state"""
    st.session_state.slideshow_video_generation_progress = progress
    st.session_state.slideshow_video_generation_status = status

def generate_slideshow_video_wrapper():
    """Wrapper function to generate slideshow video with progress tracking"""
    log_debug("VIDEO", "INFO", "Starting video generation")
    
    # Check if video generation is available
    video_info = get_video_generation_info()
    if not video_info.get("moviepy_available", False):
        st.error(f"❌ {video_info.get('moviepy_error', 'Video generation not available')}")
        st.info("💡 To enable video generation, install MoviePy: `pip install moviepy imageio-ffmpeg`")
        return
    
    # Validate prerequisites
    if not st.session_state.slideshow_audio_generated or not st.session_state.slideshow_audio_files:
        st.error("❌ Audio files must be generated before creating video")
        return
    
    if not st.session_state.slideshow_slide_images:
        st.error("❌ Slide images must be available for video generation")
        return
    
    # Reset video state
    st.session_state.slideshow_video_generated = False
    st.session_state.slideshow_video_file_path = None
    st.session_state.slideshow_video_info = {}
    
    # Create progress placeholder
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    
    try:
        with st.spinner("🎬 Generating video... This may take several minutes."):
            
            def progress_callback(progress: float, status: str):
                update_video_progress(progress, status)
                progress_placeholder.progress(progress, text=f"Progress: {progress*100:.1f}%")
                status_placeholder.info(f"📹 {status}")
            
            # Generate the video
            result = generate_slideshow_video(
                slide_images=st.session_state.slideshow_slide_images,
                audio_files=st.session_state.slideshow_audio_files,
                narrations=st.session_state.slideshow_narrations,
                progress_callback=progress_callback
            )
            
            if result["success"]:
                st.session_state.slideshow_video_generated = True
                st.session_state.slideshow_video_file_path = result["output_path"]
                st.session_state.slideshow_video_info = result
                
                # Clear progress indicators
                progress_placeholder.empty()
                status_placeholder.empty()
                
                # Show success message
                file_size_mb = result.get("file_size_mb", 0)
                duration = result.get("duration_seconds", 0)
                success_msg = f"Video generated successfully! ({file_size_mb:.1f}MB, {duration:.1f}s)"
                st.success(f"✅ {success_msg}")
                log_debug("VIDEO", "SUCCESS", success_msg)
                
                # Show warnings if any
                if result.get("warnings"):
                    with st.expander("⚠️ View Warnings", expanded=False):
                        for warning in result["warnings"]:
                            st.warning(warning)
                
                st.rerun()
            else:
                # Clear progress indicators
                progress_placeholder.empty()
                status_placeholder.empty()
                
                error_msg = f"Failed to generate video: {result.get('error', 'Unknown error')}"
                st.error(f"❌ {error_msg}")
                log_debug("VIDEO", "ERROR", error_msg)
                
                # Show detailed errors if available
                if result.get("errors"):
                    with st.expander("🔍 View Detailed Errors", expanded=False):
                        for error in result["errors"]:
                            st.error(error)
                
    except Exception as e:
        # Clear progress indicators
        progress_placeholder.empty()
        status_placeholder.empty()
        
        error_msg = f"Unexpected error during video generation: {str(e)}"
        st.error(f"❌ {error_msg}")
        log_debug("VIDEO", "ERROR", error_msg)

def render_video_generation_section():
    """Render the video generation section in the slideshow tab"""
    
    # Only show if audio files are generated and slide images are available
    if (not st.session_state.slideshow_audio_generated or 
        not st.session_state.slideshow_audio_files or
        not st.session_state.slideshow_slide_images):
        return
    
    st.markdown("---")
    st.subheader("🎬 Video Generation")
    
    # Get video generation info
    video_info = get_video_generation_info()
    
    # Show video generation capabilities
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if video_info.get("moviepy_available", False):
            st.info(f"📹 **Ready to generate video** • {video_info.get('video_resolution', 'Unknown resolution')} • {video_info.get('video_fps', 30)} FPS")
            
            slide_count = len(st.session_state.slideshow_slide_images)
            if slide_count > video_info.get("max_slides", 50):
                st.warning(f"⚠️ Too many slides ({slide_count}). Maximum supported: {video_info.get('max_slides', 50)}")
                return
            
            # Estimate processing time and file size
            estimated_time = f"{slide_count * 30}-{slide_count * 60}"  # 30-60 seconds per slide
            st.caption(f"📊 {slide_count} slides • Estimated processing time: {estimated_time} seconds")
            
        else:
            st.error(f"❌ {video_info.get('moviepy_error', 'Video generation not available')}")
            st.info("💡 To enable video generation, run: `pip install moviepy imageio-ffmpeg`")
            return
    
    with col2:
        if st.session_state.slideshow_video_generated:
            st.success("✅ Video ready!")
        else:
            if st.button("🎬 Generate Video", type="primary", key="generate_video_btn"):
                generate_slideshow_video_wrapper()
    
    # Show video download section if video is generated
    if st.session_state.slideshow_video_generated and st.session_state.slideshow_video_file_path:
        render_video_download_section()

def render_video_download_section():
    """Render the video download section"""
    video_info = st.session_state.slideshow_video_info
    video_path = st.session_state.slideshow_video_file_path
    
    if not video_path or not os.path.exists(video_path):
        st.error("❌ Generated video file not found")
        return
    
    st.markdown("### 📥 Download Video")
    
    # Video information
    col1, col2, col3 = st.columns(3)
    
    with col1:
        file_size_mb = video_info.get("file_size_mb", 0)
        st.metric("File Size", f"{file_size_mb:.1f} MB")
    
    with col2:
        duration = video_info.get("duration_seconds", 0)
        duration_str = f"{int(duration//60)}:{int(duration%60):02d}"
        st.metric("Duration", duration_str)
    
    with col3:
        total_slides = video_info.get("total_slides", 0)
        st.metric("Total Slides", total_slides)
    
    # Download button
    try:
        with open(video_path, "rb") as video_file:
            video_bytes = video_file.read()
        
        # Generate download filename
        original_filename = st.session_state.slideshow_uploaded_file.name if st.session_state.slideshow_uploaded_file else "presentation"
        base_name = os.path.splitext(original_filename)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_filename = f"{base_name}_video_{timestamp}.mp4"
        
        st.download_button(
            label="📥 Download Video (MP4)",
            data=video_bytes,
            file_name=download_filename,
            mime="video/mp4",
            key="download_video_btn",
            help=f"Download the generated slideshow video ({file_size_mb:.1f} MB)"
        )
        
        # Additional options
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Regenerate Video", key="regenerate_video_btn", help="Generate a new video with different transitions"):
                st.session_state.slideshow_video_generated = False
                st.session_state.slideshow_video_file_path = None
                st.session_state.slideshow_video_info = {}
                st.rerun()
        
        with col2:
            if st.button("🧹 Clean Old Videos", key="cleanup_videos_btn", help="Clean up old video files"):
                cleanup_video_files(max_age_hours=24)
                st.success("✅ Cleaned up old video files")
        
        # Show video creation details in expander
        with st.expander("📋 Video Details", expanded=False):
            st.write(f"**Output Path:** {video_path}")
            st.write(f"**Resolution:** {video_info.get('video_resolution', 'Unknown')}")
            st.write(f"**Format:** MP4 (H.264 video, AAC audio)")
            st.write(f"**Transitions:** Random transitions between slides")
            
            if video_info.get("warnings"):
                st.write("**Warnings:**")
                for warning in video_info["warnings"]:
                    st.write(f"- {warning}")
        
    except Exception as e:
        st.error(f"❌ Error preparing video download: {str(e)}")
        log_debug("VIDEO_DOWNLOAD", "ERROR", f"Error preparing download: {str(e)}")

def render_narrated_slideshow_feature():
    """Main function to render the narrated slideshow feature"""
    log_debug("MAIN", "INFO", "Rendering narrated slideshow feature")
    
    # Initialize session state
    initialize_slideshow_session_state()
    
    # Feature header
    st.title("🎬 Narrated Slideshow Generator")
    st.markdown("""
    Transform your presentations into engaging auto-narrated slideshows! Upload your PDF or PowerPoint files 
    and let AI generate educational narrations tailored to your audience level.
    """)
    
    # Create tabs
    tab1, tab2 = st.tabs(["📁 Input", "🎬 Slideshow"])
    
    with tab1:
        render_input_tab()
    
    with tab2:
        render_slideshow_tab()
    
    log_debug("MAIN", "INFO", "Narrated slideshow feature rendering complete")