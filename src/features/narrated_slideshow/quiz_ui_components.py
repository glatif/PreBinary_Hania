"""
Quiz UI Components for Narrated Slideshow Feature

This module provides UI components for displaying quiz questions and handling user interactions.
"""

import streamlit as st
from datetime import datetime
from typing import Dict, Any, Optional, List

def log_debug(phase: str, status: str, message: str) -> None:
    """Log debug messages with consistent formatting"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[NARRATED_SLIDESHOW] [{timestamp}] [{phase}] [{status}] {message}")

def render_mcq_question(question_data: Dict[str, Any], question_key: str) -> Optional[str]:
    """
    Render a multiple choice question with 4 options
    
    Args:
        question_data: Question data containing text, options, and correct answer
        question_key: Unique key for this question instance
        
    Returns:
        Selected answer or None if no selection made
    """
    question_text = question_data["question_text"]
    options = question_data["options"]
    
    # Question header
    st.markdown("### 🤔 Quiz Question")
    st.markdown(f"**{question_text}**")
    
    st.markdown("---")
    
    # Radio button options with custom styling
    selected_answer = st.radio(
        "Choose your answer:",
        options,
        index=None,  # No default selection
        key=f"mcq_answer_{question_key}",
        label_visibility="visible"
    )
    
    return selected_answer

def render_true_false_question(question_data: Dict[str, Any], question_key: str) -> Optional[str]:
    """
    Render a True/False question
    
    Args:
        question_data: Question data containing text and correct answer
        question_key: Unique key for this question instance
        
    Returns:
        Selected answer ("True" or "False") or None if no selection made
    """
    question_text = question_data["question_text"]
    
    # Question header
    st.markdown("### 🤔 Quiz Question")
    st.markdown(f"**{question_text}**")
    
    st.markdown("---")
    
    # True/False options with custom styling
    selected_answer = st.radio(
        "Choose your answer:",
        ["True", "False"],
        index=None,  # No default selection
        key=f"tf_answer_{question_key}",
        label_visibility="visible"
    )
    
    return selected_answer

def render_quiz_feedback(is_correct: bool, correct_answer: str, user_answer: str, 
                        question_type: str) -> None:
    """
    Show feedback after user submits an answer
    
    Args:
        is_correct: Whether the user's answer was correct
        correct_answer: The correct answer
        user_answer: The user's selected answer
        question_type: Type of question (MCQ or True/False)
    """
    if is_correct:
        st.success("✅ **Correct!** Well done!")
        log_debug("QUIZ_UI", "INFO", f"User answered correctly: {user_answer}")
    else:
        st.error(f"❌ **Incorrect.** The correct answer is: **{correct_answer}**")
        log_debug("QUIZ_UI", "INFO", f"User answered incorrectly: {user_answer} (correct: {correct_answer})")
        
        # Additional encouragement for incorrect answers
        if question_type == "MCQ":
            st.info("💡 Review the previous slides and try to understand the key concepts discussed.")
        else:
            st.info("💡 Consider the information presented in the previous slides more carefully.")

def handle_answer_submission(question_data: Dict[str, Any], selected_answer: str, 
                           question_key: str) -> Dict[str, Any]:
    """
    Process and validate answer submission
    
    Args:
        question_data: Question data with correct answer
        selected_answer: User's selected answer
        question_key: Unique key for this question
        
    Returns:
        Dict with submission results
    """
    correct_answer = question_data["correct_answer"]
    is_correct = selected_answer == correct_answer
    question_type = question_data["question_type"]
    
    log_debug("QUIZ_SUBMISSION", "INFO", 
             f"Answer submitted for question {question_key}: {selected_answer} (correct: {is_correct})")
    
    return {
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "user_answer": selected_answer,
        "question_type": question_type,
        "question_key": question_key
    }

def render_quiz_overlay(question_data: Dict[str, Any], slide_number_after: int) -> bool:
    """
    Render the complete quiz overlay UI
    
    Args:
        question_data: Complete question data
        slide_number_after: Slide number this question appears after
        
    Returns:
        True if quiz is completed (correct answer), False if still in progress
    """
    question_type = question_data["question_type"]
    question_key = f"slide_{slide_number_after}_{question_type.lower()}"
    
    # Create a container for the quiz with custom styling
    quiz_container = st.container()
    
    with quiz_container:
        # Quiz header with context
        st.markdown("---")
        st.markdown("### 🎯 **Quiz Time!**")
        st.info(f"📚 **Learning Check:** Based on the content from slides 1-{slide_number_after}")
        
        # Check if this question has been answered correctly already
        quiz_completion_key = f"quiz_completed_{question_key}"
        if st.session_state.get(quiz_completion_key, False):
            # Question already completed - show success and allow continuation
            st.success("✅ **Quiz Completed!** You may continue to the next slide.")
            render_continue_button("Continue to Next Slide")
            return True
        
        # Check if we're showing feedback
        feedback_key = f"show_feedback_{question_key}"
        answer_key = f"submitted_answer_{question_key}"
        
        if st.session_state.get(feedback_key, False):
            # Show feedback and retry option
            submitted_answer = st.session_state.get(answer_key)
            is_correct = submitted_answer == question_data["correct_answer"]
            
            # Show the submitted answer and feedback
            st.markdown("### 📝 Your Answer")
            if question_type == "MCQ":
                st.info(f"You selected: **{submitted_answer}**")
            else:
                st.info(f"You answered: **{submitted_answer}**")
            
            # Show feedback with correct answer
            render_quiz_feedback(is_correct, question_data["correct_answer"], 
                               submitted_answer, question_type)
            
            # Show the correct answer prominently
            if not is_correct:
                st.markdown("### ✅ Correct Answer")
                st.success(f"The correct answer is: **{question_data['correct_answer']}**")
                
                # Show explanation if available
                if "explanation" in question_data and question_data["explanation"]:
                    st.markdown("### 💡 Explanation")
                    st.info(question_data["explanation"])
            
            st.markdown("---")
            
            if is_correct:
                # Mark as completed and show continue button
                st.session_state[quiz_completion_key] = True
                st.success("🎉 **Great job!** You got it right!")
                render_continue_button("Continue to Next Slide")
                return True
            else:
                # Show options: try again or continue
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 Try Again", type="secondary", use_container_width=True, 
                               key=f"retry_{question_key}"):
                        # Reset feedback state to try again
                        st.session_state[feedback_key] = False
                        if answer_key in st.session_state:
                            del st.session_state[answer_key]
                        st.rerun()
                with col2:
                    if st.button("➡️ Continue Anyway", type="primary", use_container_width=True,
                               key=f"continue_anyway_{question_key}"):
                        # Mark as completed (even though incorrect) and continue
                        st.session_state[quiz_completion_key] = True
                        render_continue_button("Continue to Next Slide")
                        st.rerun()
                
                st.caption("💡 You can try again to improve your score or continue with the slideshow.")
                return False
        
        # Show the question
        if question_type == "MCQ":
            selected_answer = render_mcq_question(question_data, question_key)
        else:  # True/False
            selected_answer = render_true_false_question(question_data, question_key)
        
        # Show submit button if answer is selected
        if selected_answer:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("✅ Submit Answer", type="primary", use_container_width=True,
                           key=f"submit_{question_key}"):
                    # Store the submitted answer and show feedback
                    st.session_state[answer_key] = selected_answer
                    st.session_state[feedback_key] = True
                    st.rerun()
        else:
            # Show disabled submit button with instruction
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.button("✅ Submit Answer", type="primary", use_container_width=True,
                         disabled=True, key=f"submit_disabled_{question_key}")
            st.caption("👆 Please select an answer to continue")
        
        # Show navigation blocking message
        st.markdown("---")
        st.warning("🔒 **Navigation is locked** until you answer this question correctly.")
        
    return False

def render_continue_button(button_text: str = "Continue to Next Slide") -> None:
    """Render the continue button after successful quiz completion"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(f"➡️ {button_text}", type="primary", use_container_width=True,
                   key="quiz_continue_btn"):
            # Clear quiz state and proceed
            clear_active_quiz_state()
            st.rerun()

def clear_active_quiz_state() -> None:
    """Clear the active quiz state to allow navigation"""
    if "slideshow_current_quiz" in st.session_state:
        st.session_state.slideshow_current_quiz = None
    if "slideshow_quiz_blocking_navigation" in st.session_state:
        st.session_state.slideshow_quiz_blocking_navigation = False
    
    log_debug("QUIZ_UI", "INFO", "Cleared active quiz state - navigation unlocked")

def get_quiz_status_indicator(quiz_questions: Dict[int, Dict], current_slide: int) -> str:
    """
    Get a status indicator for quiz progress
    
    Args:
        quiz_questions: Dictionary of quiz questions keyed by slide_number_after
        current_slide: Current slide number
        
    Returns:
        Status indicator string
    """
    if not quiz_questions:
        return ""
    
    total_quizzes = len(quiz_questions)
    completed_quizzes = 0
    
    for slide_after, question_data in quiz_questions.items():
        question_type = question_data["question_type"]
        question_key = f"slide_{slide_after}_{question_type.lower()}"
        quiz_completion_key = f"quiz_completed_{question_key}"
        
        if st.session_state.get(quiz_completion_key, False):
            completed_quizzes += 1
    
    if completed_quizzes == total_quizzes:
        return f"🏆 All quizzes completed ({completed_quizzes}/{total_quizzes})"
    else:
        return f"📝 Quiz progress: {completed_quizzes}/{total_quizzes} completed"

def render_quiz_progress_summary(quiz_questions: Dict[int, Dict]) -> None:
    """
    Render a summary of quiz progress with score card
    
    Args:
        quiz_questions: Dictionary of quiz questions keyed by slide_number_after
    """
    if not quiz_questions:
        return
    
    st.markdown("#### 📊 Quiz Performance")
    
    # Calculate statistics
    attempted_questions = []
    correct_answers = 0
    incorrect_questions = []
    
    for slide_after in sorted(quiz_questions.keys()):
        question_data = quiz_questions[slide_after]
        question_type = question_data["question_type"]
        question_key = f"slide_{slide_after}_{question_type.lower()}"
        
        # Check if question was attempted
        answer_key = f"submitted_answer_{question_key}"
        if answer_key in st.session_state:
            attempted_questions.append({
                "question_number": len(attempted_questions) + 1,
                "question_text": question_data["question_text"],
                "question_type": question_type,
                "user_answer": st.session_state[answer_key],
                "correct_answer": question_data["correct_answer"],
                "is_correct": st.session_state[answer_key] == question_data["correct_answer"],
                "slide_after": slide_after
            })
            
            if st.session_state[answer_key] == question_data["correct_answer"]:
                correct_answers += 1
            else:
                incorrect_questions.append(attempted_questions[-1])
    
    # Show score card
    if attempted_questions:
        total_attempted = len(attempted_questions)
        score_percentage = (correct_answers / total_attempted) * 100 if total_attempted > 0 else 0
        
        # Score metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Questions Attempted", total_attempted)
        with col2:
            st.metric("Correct Answers", correct_answers)
        with col3:
            st.metric("Incorrect Answers", total_attempted - correct_answers)
        with col4:
            st.metric("Score", f"{score_percentage:.1f}%")
        
        # Progress bar
        st.progress(score_percentage / 100, text=f"Performance: {score_percentage:.1f}%")
        
        # Show incorrect answers in expandable section
        if incorrect_questions:
            with st.expander(f"❌ Review Incorrect Answers ({len(incorrect_questions)} questions)", expanded=False):
                for i, question in enumerate(incorrect_questions, 1):
                    st.markdown(f"**Question {question['question_number']}:** {question['question_text']}")
                    st.markdown(f"- Your answer: **{question['user_answer']}** ❌")
                    st.markdown(f"- Correct answer: **{question['correct_answer']}** ✅")
                    if i < len(incorrect_questions):
                        st.divider()
        
        # Performance feedback
        if score_percentage >= 80:
            st.success("🏆 Excellent work! You're mastering the material.")
        elif score_percentage >= 60:
            st.info("👍 Good job! Keep reviewing the material to improve further.")
        else:
            st.warning("📚 Consider reviewing the slides again to strengthen your understanding.")
    
    else:
        st.info("📝 No questions attempted yet. Quiz questions will appear as you progress through the slideshow.")
