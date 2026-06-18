# Narrated Slideshow Feature

## Overview
The Narrated Slideshow feature allows professors to upload PDF or PowerPoint presentations and automatically generate AI-narrated presentations with an optional interactive quiz layer that actively engages students.

## Key Features
- ✅ File upload support for PDF and PowerPoint files with validation limits
- ✅ Education level selection for context-aware narration  
- ✅ Minimalistic 3-section UI: Configuration → Quiz Setup → Step-by-step Processing
- ✅ Multiple TTS providers (Google TTS, ElevenLabs, Cartesia AI)
- ✅ Interactive slideshow player with visual slide previews
- ✅ **Video Generation**: Export narrated slideshows as MP4 videos with transitions
- ✅ Intelligent Quiz Layer with AI-generated questions
- ✅ Performance tracking with score cards and incorrect answer review
- ✅ Navigation blocking until quiz completion

## User Interface

### Minimalistic Design
The interface is organized into three clean sections:

1. **Input Configuration**: Education level and AI model selection
2. **Document Upload**: File upload with TTS provider configuration
3. **Quiz Configuration**: Toggle quiz, set frequency and question types
4. **Processing Steps**: Sequential workflow with clear progress indicators

## Interactive Quiz System

### Features
- **Smart Question Generation**: LLM analyzes content and strategically places questions
- **Privacy-First Progress**: Shows performance metrics without revealing future question locations
- **Comprehensive Feedback**: Displays correct answers and explanations after submission
- **Score Tracking**: Real-time performance metrics with detailed incorrect answer review
- **Flexible Navigation**: Students can retry questions or continue after seeing correct answers

### Configuration Options
- **Quiz Frequency**: None, Less Frequent, Frequent, Very Frequent
- **Question Types**: Mixed, MCQs Only, True/False Only

## Workflow

### Step-by-Step Processing
1. Configure education level and AI model
2. Upload PDF/PowerPoint file
3. Set quiz preferences (optional)
4. Process document to extract content
5. Generate AI narrations for slides
6. Generate quiz questions (if enabled)
7. Create audio files using selected TTS provider
8. **Generate video (optional)**: Create MP4 video with synchronized audio and transitions
9. Present interactive slideshow or download video

### Slideshow Experience
- Visual slide previews with synchronized audio
- **Video Export**: Download complete slideshow as MP4 with smooth transitions
- Quiz questions appear strategically between slides
- Navigation blocked until quiz completion
- Performance tracking without spoiling upcoming questions
- Detailed feedback with correct answers and explanations

## Technical Architecture

### Core Modules
- `narrated_slideshow_feature.py`: Main UI with minimalistic 3-section design
- `video_generator.py`: MP4 video creation with synchronized audio and transitions
- `quiz_generator.py`: LLM-powered quiz question generation
- `quiz_ui_components.py`: Interactive quiz interface with performance tracking
- `slideshow_player.py`: Slideshow presentation with quiz-aware navigation
- `document_processor.py`: File processing and content extraction
- `tts_engine.py`: Multi-provider text-to-speech integration

### Key Capabilities
- Graceful module loading with fallback systems
- Unique widget keys to prevent UI conflicts
- Session state management for complex workflows
- Real-time progress tracking and performance metrics
- Education-level-aware content generation

## Supported Formats
- **PDF files**: Up to 25 pages
- **PowerPoint files**: Up to 20 slides (.ppt, .pptx)

## TTS Providers
- **Google TTS**: Free, no API key required
- **ElevenLabs**: Premium quality, API key required
- **Cartesia AI**: Advanced AI voices, API key required

## Video Generation System

### Features
- **MP4 Export**: Convert narrated slideshows into downloadable video files
- **Smooth Transitions**: Random subtle transitions between slides (fade, crossfade)
- **Synchronized Audio**: Perfect audio-visual synchronization with slide timing
- **High Quality Output**: 1280x720 HD resolution with optimized file sizes
- **Progress Tracking**: Real-time progress updates during video generation
- **Automatic Cleanup**: Temporary files cleaned up after processing

### Video Specifications
- **Resolution**: 1280x720 (HD)
- **Format**: MP4 (H.264 encoding)
- **Audio**: Synchronized with slide narration timing
- **Transitions**: Randomly applied fade effects between slides
- **File Size**: Optimized for web delivery (typically 1-3MB per minute)

### Technical Implementation
- **MoviePy Integration**: Professional video editing capabilities
- **Pillow Compatibility**: Handles image processing with version compatibility
- **Temporary File Management**: Secure creation and cleanup of temporary assets
- **Error Handling**: Graceful fallbacks for compatibility issues

## Testing Assets

To help you test this feature quickly, sample files are provided in the `testing_assets` directory:

- **[photosynthesis_high_school.pdf](./testing_assets/photosynthesis_high_school.pdf)** - A comprehensive PDF presentation about photosynthesis suitable for high school level
- **[photosynthesis_high_school_presentation.pptx](./testing_assets/photosynthesis_high_school_presentation.pptx)** - The same content in PowerPoint format

These files are ideal for testing all feature capabilities including:
- Document processing and content extraction
- AI narration generation at high school education level
- Interactive quiz generation with science-based questions
- Text-to-speech conversion with multiple providers
- Video generation with synchronized audio and transitions

Simply upload either file when testing the narrated slideshow feature to see the complete workflow in action.

## Dependencies
- `python-pptx>=0.6.21` - PowerPoint processing
- `gtts>=2.3.1` - Google Text-to-Speech
- `elevenlabs>=2.8.0` - ElevenLabs TTS
- `cartesia>=2.0.0` - Cartesia AI TTS
- `PyMuPDF>=1.26.0` - PDF processing and slide visualization
- `Pillow>=10.0.0` - Image processing
- `moviepy>=1.0.3` - Video generation and editing
- `imageio-ffmpeg` - Video encoding support

