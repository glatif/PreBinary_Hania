# Student Wellness Services Feature

## Overview

The Student Wellness Services feature is designed to help students at Thompson Rivers University (TRU) access comprehensive information about mental and physical health services available on campus and in the Kamloops community. The feature includes both an information portal and an AI-powered multilingual wellness assistant to provide personalized guidance. Conversation sessions are persisted to the database and can be loaded and continued across logins.

## Key Features

### 1. Comprehensive Services Information Portal

- **Complete Service Directory**: Browse all available wellness services organized by category
- **Advanced Search**: Quickly find specific services using keyword search functionality
- **Detailed Service Information**: Each service includes:
  - Comprehensive descriptions and services offered
  - Location details and contact information
  - Official website links and resources
  - Common use cases and frequently asked questions
- **Intuitive Organization**: Services grouped into logical categories for easy navigation

### 2. Advanced AI-Powered Wellness Assistant

- **Interactive Chat Interface**: Ask questions about wellness services in natural language
- **Multi-Language Support**: Get responses in English, French, Arabic, or Hindi
- **Advanced AI Model Selection**: Choose from multiple AI models:
  - Local Models: DeepSeek R1, Llama 3.2 (via Ollama)
  - Cloud Models: Llama 3.3-70B (Groq), Gemini 2.5 Flash, GPT-4o (OpenAI)
- **Contextual Intelligence**: AI trained on comprehensive TRU wellness services data
- **Crisis-Aware Responses**: Prioritizes safety and emergency contacts for crisis situations
- **Guided Interaction**: Pre-built sample questions to help users get started
- **Persistent Chat History**: Conversation sessions are saved to the database and accessible across logins

### 3. Enhanced User Experience

- **Language Accessibility**: Multi-language support for diverse student populations
- **Model Flexibility**: Try different AI models to find the best responses for your needs
- **Persistent Preferences**: Language and model selections are maintained during your session
- **Real-time Assistance**: Immediate responses to wellness-related questions

## Available Services

The feature provides information about the following TRU wellness services:

1. **🏥 Wellness Centre** - Primary hub for student health and wellness
2. **🧠 Counselling Services** - Professional mental health support
3. **⚕️ TRU Medical Clinic** - On-campus primary health care
4. **🏋️‍♂️ Tournament Capital Centre** - Fitness and recreation facility
5. **🦷 Health and Dental Plan** - Student health insurance coverage
6. **♿ Accessibility Services** - Support for students with disabilities
7. **🏘️ Community Resources** - Off-campus health services in Kamloops
8. **📱 Additional Resources** - GuardMe app, workshops, and extended support

## Usage

### Services Information Tab

1. **Browse All Services**: View services organized by category using the tab navigation
2. **Search Services**: Use the search bar to find specific services by keyword
3. **View Service Details**: Each service card provides comprehensive information including:
   - Contact information and location
   - Services offered
   - Website links
   - Common use cases

### Wellness Assistant Tab

1. **Select AI Model**: Choose your preferred AI model from the dropdown
2. **Ask Questions**: Type questions about wellness services or click sample questions
3. **Get Personalized Responses**: Receive detailed, contextual answers based on TRU's services
4. **Access Emergency Contacts**: For crisis situations, the assistant prioritizes safety information

## Usage Instructions

### Using the Services Portal

1. Navigate to the "Student Wellness" tab
2. Browse services by category or use the search function
3. Click on service cards to view detailed information
4. Follow provided links and contact information to access services

### Using the AI Wellness Assistant

1. **Select AI Model**: Choose from available local or cloud-based models
   - Local: DeepSeek R1, Llama 3.2 (via Ollama)
   - Cloud: Llama 3.3-70B (Groq), Gemini 2.5 Flash, GPT-4o (OpenAI)
2. **Choose Response Language**: Select English, French, Arabic, or Hindi
3. **Ask Questions**: Type your wellness-related questions in the chat interface
4. **Review Sample Questions**: Use provided examples to get started
5. **Get Personalized Guidance**: Receive contextual responses based on TRU services

### Chat History

All conversation sessions are saved to the database and available in the History tab.

1. Go to the "History" tab
2. Each row represents one conversation session, showing the date and a preview of the first message
3. **Load and Continue**: Click to restore a past conversation into the Wellness Assistant tab and continue where it left off
4. **Delete**: Permanently remove a session and all its messages

### Multi-Language Support

- **Language Selection**: Choose your preferred response language from the dropdown
- **Cultural Sensitivity**: Responses adapted for different linguistic backgrounds
- **Consistent Experience**: Language preference maintained throughout your session

### Crisis Support Features

- **Priority Response**: Crisis-related queries receive immediate attention
- **Emergency Information**: Direct access to emergency contacts and resources
- **Safety First**: All crisis responses prioritize student safety and well-being

## Example Questions

The wellness assistant can help with questions like:

- "I'm feeling stressed and need someone to talk to. What options do I have?"
- "Where can I get medical care on campus?"
- "What fitness facilities are available at TRU?"
- "How do I access mental health support outside business hours?"
- "What support is available for students with disabilities?"
- "How can I get health insurance through TRU?"
- "What community resources are available for mental health?"
- "How do I book an appointment at the Wellness Centre?"

## Emergency Contacts

For immediate assistance:

- **🆘 Crisis Support**: Counselling Services (250-828-5023) or Emergency (911)
- **🏥 Health Services**: Wellness Centre (250-828-5010) or Medical Clinic (250-828-5126)
- **24/7 Support**: GuardMe App for real-time mental health support

## Technical Implementation

### Enhanced Data Structure

- **Comprehensive Service Data**: Structured JSON with detailed service information
- **Advanced Master Prompt**: AI prompt optimized for TRU wellness services with language support
- **Smart Search**: Keyword-based search across service descriptions and use cases

### Advanced AI Integration

- **Multi-Model Architecture**: Support for local and cloud-based AI models
- **Language-Aware Processing**: Specialized prompts for different languages
- **Streaming Responses**: Real-time response generation for optimal user experience
- **API Key Management**: Secure handling of cloud model credentials
- **Context-Aware**: AI responses based on comprehensive TRU wellness services knowledge base

### Database Persistence

Conversation turns are stored in the `wellness_chat_history` table, with each logical session identified by a `chat_session_id` (UUID). The History tab groups rows by session ID to display and reload past conversations. Sessions cascade-delete when the owning user account is removed.

### File Structure

- `student_wellness_feature.py`: Main UI implementation and logic
- `wellness_data.py`: Structured data about TRU wellness services and master prompt
- `README.md`: Feature documentation

## Data Sources

All service information is based on official TRU wellness resources as of June 12, 2025:

- TRU Wellness Centre
- TRU Counselling Services
- TRU Medical Clinic
- Tournament Capital Centre
- TRUSU Health and Dental Plan
- TRU Accessibility Services
- Kamloops Community Resources

## Best Practices

1. **Review AI Responses**: While the AI is trained on comprehensive data, always verify important information by contacting services directly
2. **Emergency Situations**: For crisis situations, prioritize calling emergency services (911) or Counselling Services (250-828-5023)
3. **Current Information**: Service details may change; use provided website links for the most current information
4. **Privacy**: The chat interface doesn't store personal information, but avoid sharing sensitive details

## Future Enhancements

- Integration with TRU's appointment booking systems
- Real-time service availability updates
- Personalized wellness recommendations based on user history
- Integration with TRU student portal