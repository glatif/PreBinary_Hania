# Handle torch issue directly
import os
import sys
import types
import importlib.abc

# Create a comprehensive patch for torch before importing anything else
try:
    # First, let's create a custom module finder that will handle torch._classes
    class TorchClassesFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == 'torch._classes' or fullname.startswith('torch._classes.'):
                # Create a dummy module with __path__ attribute
                class DummyPath:
                    _path = []
                    
                # Create a loader that returns our dummy module
                class DummyLoader(importlib.abc.Loader):
                    def create_module(self, spec):
                        module = types.ModuleType(fullname)
                        module.__path__ = DummyPath()
                        return module
                        
                    def exec_module(self, module):
                        pass  # Do nothing
                
                # Return a spec with our loader
                return importlib.machinery.ModuleSpec(
                    name=fullname,
                    loader=DummyLoader(),
                    is_package=True
                )
            return None
    
    # Register our finder at the beginning of sys.meta_path
    sys.meta_path.insert(0, TorchClassesFinder())
    
    # Now try to import torch
    import torch
    
    # Create a dummy path class
    class DummyPath:
        _path = []
    
    # Monkey patch torch._classes to avoid the __path__ issue if it exists
    if hasattr(torch, '_classes'):
        # Add __path__ if it doesn't exist
        if not hasattr(torch._classes, '__path__'):
            torch._classes.__path__ = DummyPath()
        
        # Override the problematic __getattr__ method
        original_getattr = getattr(torch._classes, '__getattr__', None)
        
        def safe_getattr(self, name=None):
            # Handle case where name is not provided
            if name is None:
                return DummyPath()
                
            if name == '__path__':
                return DummyPath()
            if original_getattr:
                try:
                    return original_getattr(self, name)
                except Exception as e:
                    pass
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
        
        # Apply the patch
        torch._classes.__getattr__ = safe_getattr
        
        # Also patch _get_custom_class_python_wrapper if it exists
        if hasattr(torch._C, '_get_custom_class_python_wrapper'):
            original_wrapper = torch._C._get_custom_class_python_wrapper
            
            def safe_wrapper(name=None, attr=None):
                # Handle case where arguments are missing
                if name is None or attr is None:
                    return DummyPath()
                    
                if attr == '__path__' or name == '__path__':
                    return DummyPath()
                try:
                    return original_wrapper(name, attr)
                except Exception:
                    return None
            
            torch._C._get_custom_class_python_wrapper = safe_wrapper
        
        print("✅ Applied comprehensive torch._classes patch")
except Exception as e:
    print(f"⚠️ Torch patch error: {e}")



import os
import streamlit as st
from PIL import Image

# Import feature modules
from src.features.rag.rag_feature import rag_ui
from src.features.exam_grading.exam_grading_feature import exam_grading_ui
from src.features.exam_creation.exam_creation_feature import exam_creation_ui
from src.features.advisor_ai.advisor_ai_feature import advisor_ai_ui
from src.features.student_wellness.student_wellness_feature import student_wellness_ui
from src.features.quiz_generator.quiz_generator_feature import quiz_generator_ui
from src.features.narrated_slideshow.narrated_slideshow_feature import render_narrated_slideshow_feature

# Set page configuration
st.set_page_config(
    page_title="UReap - University AI Tools",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        margin-bottom: 1rem;
    }
    .feature-header {
        font-size: 1.8rem;
        margin-top: 1rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        height: 4rem;
        white-space: pre-wrap;
        font-size: 1rem;
    }
</style>
""", unsafe_allow_html=True)

def main():
    """Main function to render the Streamlit application"""
    
    # Application header
    st.markdown('<h1 class="main-header">Multi-Feature AI Application</h1>', unsafe_allow_html=True)
    st.write("A comprehensive platform for university students and faculty, offering AI-powered tools for document analysis, exam creation, and automated grading using both local and cloud-based LLMs.")
    
    # Create tabs for different features
    tabs = st.tabs([
        "📚 RAG System", 
        "📝 Exam Grading",
        "✨ Exam Creation",
        "🎓 Advisor AI",
        "🌟 Student Wellness",
        "🧠 Practice for Exam/Quiz",
        "🎬 Video Lectures",
        "➕ More Features Coming Soon"
    ])
    
    # RAG System Tab
    with tabs[0]:
        rag_ui()
    
    # Exam Grading Tab
    with tabs[1]:
        exam_grading_ui()
    
    # Exam Creation Tab
    with tabs[2]:
        exam_creation_ui()
    
    # Advisor AI Tab
    with tabs[3]:
        advisor_ai_ui()
    
    # Student Wellness Tab
    with tabs[4]:
        student_wellness_ui()
    
    # Quiz Generator Tab
    with tabs[5]:
        quiz_generator_ui()
    
    # Narrated Slideshow Tab
    with tabs[6]:
        render_narrated_slideshow_feature()
    
    # Future Features Tab
    with tabs[7]:
        st.subheader("More Features Coming Soon")
        st.write("This tab is reserved for future features. Check back later for updates!")
        
        # Placeholder for future features
        st.info("Future features may include:")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("- **Text Summarization**")
            st.markdown("- **Document Translation**")
            st.markdown("- **Content Generation**")
        with col2:
            st.markdown("- **Image Analysis**")
            st.markdown("- **Custom Training**")
            st.markdown("- **API Integrations**")

# Add sidebar information
def sidebar():
    with st.sidebar:
        st.title("About")
        st.write("This application integrates multiple AI features using local and cloud LLMs.")
        
        # Features Section
        with st.expander("📋 Features"):
            st.markdown("""
            - **RAG System**: Query documents with semantic search
            - **Exam Grading**: Automate grading of student submissions
            - **Exam Creation**: Generate variations of exam questions
            - **Advisor AI**: Query professor and course information
            - **Student Wellness**: Access TRU health and wellness services
            - **Quiz Generator**: Create interactive quizzes from study materials
            - **Narrated Slideshow**: Generate auto-narrated presentations from PDFs/PPTs
            """)

        # Models Section
        with st.expander("🤖 Models"):
            st.markdown("""
            This application supports:
            - **Local models** (via Ollama):
              - DeepSeek R1: 1.5B
              - Llama 3.2
            - **Cloud models** (API key required):
              - Groq (Llama 3.3)
              - Google Gemini
              - OpenAI (GPT-4o)
              - GitHub Models (GPT-4o)
            """)
        
        # Model Selection per Feature
        with st.expander("⚙️ Default Model Selection per Feature"):
            st.write("Select default AI models for each feature:")
            
            # Import MODELS from utils
            from src.utils.llm_utils import MODELS
            
            # Initialize session state for default models
            feature_models = {
                'rag_model': 'RAG System',
                'exam_grading_model': 'Exam Grading',
                'exam_creation_model': 'Exam Creation',
                'advisor_ai_model': 'Advisor AI',
                'student_wellness_model': 'Student Wellness',
                'quiz_generator_model': 'Quiz Generator',
                'narrated_slideshow_model': 'Narrated Slideshow'
            }
            
            for model_key, feature_name in feature_models.items():
                if model_key not in st.session_state:
                    st.session_state[model_key] = list(MODELS.keys())[0]  # Default to first model
                
                selected_model = st.selectbox(
                    f"{feature_name}",
                    options=list(MODELS.keys()),
                    index=list(MODELS.keys()).index(st.session_state[model_key]) if st.session_state[model_key] in MODELS.keys() else 0,
                    key=f"select_{model_key}",
                    help=f"Default model for {feature_name}"
                )
                st.session_state[model_key] = selected_model
        
        # API Keys Section
        st.divider()
        st.subheader("API Keys")
        st.write("Enter your API keys to use cloud-based models:")
        
        # API Key links
        st.markdown("""
        🔑 Get your API keys:
        - [OpenAI API Key](https://platform.openai.com/api-keys)
        - [GitHub Token](https://github.com/settings/personal-access-tokens)
        - [Gemini API Key](https://aistudio.google.com/apikey)
        - [Groq API Key](https://console.groq.com/keys)
        """)
        
        # Initialize session state for API keys
        if 'groq_api_key' not in st.session_state:
            st.session_state.groq_api_key = ""
        if 'gemini_api_key' not in st.session_state:
            st.session_state.gemini_api_key = ""
        if 'openai_api_key' not in st.session_state:
            st.session_state.openai_api_key = ""
        if 'github_token' not in st.session_state:
            st.session_state.github_token = ""
        
        # OpenAI API Key
        openai_key = st.text_input("OpenAI API Key", 
                                 value=st.session_state.openai_api_key, 
                                 type="password",
                                 help="Enter your OpenAI API key to use GPT-4o")
        
        # GitHub Token
        github_token = st.text_input("GitHub Token", 
                                   value=st.session_state.github_token, 
                                   type="password",
                                   help="Enter your GitHub token to use GPT-4o via GitHub Models")
        
        # Groq API Key
        groq_key = st.text_input("Groq API Key", 
                               value=st.session_state.groq_api_key, 
                               type="password",
                               help="Enter your Groq API key to use Llama models via Groq")
        
        # Gemini API Key
        gemini_key = st.text_input("Google Gemini API Key", 
                                 value=st.session_state.gemini_api_key, 
                                 type="password",
                                 help="Enter your Google Gemini API key")
        
        # Save button for API keys
        if st.button("Save API Keys"):
            st.session_state.openai_api_key = openai_key
            st.session_state.github_token = github_token
            st.session_state.groq_api_key = groq_key
            st.session_state.gemini_api_key = gemini_key
            st.success("API keys saved successfully!")
                
        # Add a link to the GitHub repository
        st.markdown("""
        ---
        🌟 **Explore the Project**:  
        [GitHub Repository](https://github.com/glatif/AI_Instructor)  
        Dive into the source code and contribute to the project!
        """, unsafe_allow_html=True)
        
        
        st.caption("AI Instructor: A tool for Instructors 📚, Students 🎓 and Researchers 🔬 ")

# Run the application
if __name__ == "__main__":
    sidebar()
    main()