"""
Student Wellness Services Data Module

This module contains the structured data about TRU wellness services
extracted from the Master Prompt for TRU Health Services Chatbot.markdown
"""

WELLNESS_SERVICES = [
    {
        "id": "wellness_centre",
        "name": "Wellness Centre",
        "category": "Primary Wellness Hub",
        "description": "The Wellness Centre is the primary hub for student health and wellness at TRU. It offers a range of services, including mental health support through counselling and wellness programming, as well as resources for physical health. The centre emphasizes culturally appropriate care, including Indigenous wellness practices.",
        "services": [
            "Mental health counselling",
            "Wellness workshops", 
            "Health education",
            "Naloxone training for opioid overdose response"
        ],
        "location": "Old Main building, first floor (OM 1479), Kamloops campus",
        "contact": "250-828-5010",
        "hyperlink": "https://www.tru.ca/current/wellness.html",
        "use_cases": [
            "Where can I find mental health support on campus?",
            "What wellness programs are available for students?",
            "How do I access Indigenous wellness services?",
            "Can I get naloxone training at TRU?"
        ],
        "icon": "🏥"
    },
    {
        "id": "counselling_services",
        "name": "Counselling Services",
        "category": "Mental Health Support",
        "description": "TRU's Counselling Services provide professional mental health support from registered social workers and clinical counsellors. Specialized support is available for Indigenous students and those dealing with trauma, anxiety, depression, grief, or addictions.",
        "services": [
            "Individual and group counselling",
            "Crisis intervention",
            "Workshops",
            "Self-help resources"
        ],
        "location": "Not specified",
        "contact": "250-828-5023",
        "hyperlink": "https://www.tru.ca/current/counselling.html",
        "use_cases": [
            "How do I book a counselling appointment?",
            "Is there support for students dealing with anxiety?",
            "Are there group therapy sessions available?",
            "What mental health resources are available for Indigenous students?"
        ],
        "icon": "🧠"
    },
    {
        "id": "medical_clinic",
        "name": "TRU Medical Clinic",
        "category": "Physical Health Services",
        "description": "The TRU Medical Clinic offers primary health care services on campus, making it convenient for students without a local family doctor.",
        "services": [
            "General medical consultations",
            "Treatment for illnesses and injuries",
            "Health assessments",
            "Referrals to specialists"
        ],
        "location": "Old Main building (OM 1461), Kamloops campus",
        "contact": "250-828-5126 or trumedicalclinic@tru.ca",
        "hyperlink": "https://www.tru.ca/current/health-services.html",
        "use_cases": [
            "Is there a medical clinic on campus?",
            "How do I make an appointment at the TRU Medical Clinic?",
            "Can I get a health assessment at TRU?",
            "What should I do if I'm sick and need to see a doctor?"
        ],
        "icon": "⚕️"
    },
    {
        "id": "tournament_capital_centre",
        "name": "Tournament Capital Centre",
        "category": "Physical Fitness & Recreation",
        "description": "This state-of-the-art fitness and recreation facility promotes physical health and well-being through exercise and recreational activities.",
        "services": [
            "Access to a gym",
            "Swimming pool (via U-PASS for the Canada Games Aquatic Centre)",
            "Fitness classes",
            "Recreational sports"
        ],
        "location": "Not specified",
        "contact": "Not specified",
        "hyperlink": "https://www.tru.ca/tcc.html",
        "use_cases": [
            "What fitness facilities are available for students?",
            "How can I access the swimming pool at TRU?",
            "Are there any fitness classes I can join?",
            "Is there a gym on campus?"
        ],
        "icon": "🏋️‍♂️"
    },
    {
        "id": "health_dental_plan",
        "name": "TRU Students' Union Health and Dental Plan",
        "category": "Health Insurance",
        "description": "Offered by the Thompson Rivers University Students' Union (TRUSU), this plan provides affordable health and dental coverage for students.",
        "services": [
            "Coverage for prescriptions",
            "Dental care",
            "Vision care",
            "Extended health services (e.g., physiotherapy, mental health support)"
        ],
        "location": "Not specified",
        "contact": "Not specified",
        "hyperlink": "https://trusu.ca/services/health-dental-plan/",
        "use_cases": [
            "How can I get health insurance through TRU?",
            "What does the student health plan cover?",
            "Is mental health support included in the health plan?",
            "How do I enroll in the dental plan?"
        ],
        "icon": "🦷"
    },
    {
        "id": "accessibility_services",
        "name": "Accessibility Services",
        "category": "Academic Support",
        "description": "Accessibility Services supports students with disabilities, including those with mental health conditions, ensuring they have the resources needed to succeed academically.",
        "services": [
            "Academic accommodations",
            "Advocacy",
            "Assistive technology",
            "Mental health-related support"
        ],
        "location": "Not specified",
        "contact": "Not specified",
        "hyperlink": "https://www.tru.ca/current/accessibility-services.html",
        "use_cases": [
            "What support is available for students with disabilities?",
            "How do I request academic accommodations?",
            "Is there mental health support for students with disabilities?",
            "Can I get assistive technology through TRU?"
        ],
        "icon": "♿"
    },
    {
        "id": "community_resources",
        "name": "Community Resources in Kamloops",
        "category": "Community Support",
        "description": "Beyond on-campus options, students can access mental and physical health services in the Kamloops community.",
        "services": [
            "Interior Health: Mental health assessments, treatment, community support",
            "Kamloops Urgent Primary Care Centre: Urgent medical care (appointment required)",
            "Safe Spaces: Support for youth (ages 14-26) identifying as LGBTQ+ or questioning"
        ],
        "location": "Various locations in Kamloops",
        "contact": "Varies by service",
        "hyperlink": "https://www.tru.ca/current/community-resources.html",
        "use_cases": [
            "Are there any off-campus health services in Kamloops?",
            "Where can I get urgent medical care in Kamloops?",
            "Is there support for LGBTQ+ students in the community?",
            "What mental health resources are available outside of TRU?"
        ],
        "icon": "🏘️"
    },
    {
        "id": "additional_resources",
        "name": "Additional Resources",
        "category": "Extended Support",
        "description": "Additional support services and resources available to TRU students for health and wellness.",
        "services": [
            "GuardMe: A TELUS Health app offering real-time phone and chat support with counsellors",
            "Naloxone Training: Provided by the Wellness Centre",
            "Health and Wellness Workshops: Regular events like mindfulness sessions and yoga"
        ],
        "location": "Various / Online",
        "contact": "Varies by service",
        "hyperlink": "https://www.youtube.com/user/TRUWellness",
        "use_cases": [
            "How can I access mental health support outside of business hours?",
            "What is GuardMe and how do I use it?",
            "Are there any wellness workshops I can attend?",
            "Where can I find recordings of past wellness events?"
        ],
        "icon": "📱"
    }
]

# Master prompt for the LLM chatbot
WELLNESS_MASTER_PROMPT = """You are an AI-powered chatbot designed to assist students at Thompson Rivers University (TRU) in Kamloops, British Columbia, with information about mental and physical health services available to them. Your primary goal is to provide accurate, helpful, and empathetic responses to student queries regarding these services. You should offer detailed information, including service descriptions, locations, contact details, and full hyperlinks to official TRU web pages for further reference.

Always maintain a friendly, supportive, and professional tone. If a student's query is unclear or falls outside the scope of the services listed, politely guide them to contact the Wellness Centre or another relevant service for further assistance. The information you provide is based on the latest available data as of June 12, 2025. Encourage students to visit the provided hyperlinks or contact the services directly for the most current information.

## Available Services:

1. **Wellness Centre** (🏥)
   - Primary hub for student health and wellness at TRU
   - Services: Mental health counselling, wellness workshops, health education, naloxone training
   - Location: Old Main building, first floor (OM 1479), Kamloops campus
   - Contact: 250-828-5010
   - Website: https://www.tru.ca/current/wellness.html

2. **Counselling Services** (🧠)
   - Professional mental health support from registered social workers and clinical counsellors
   - Services: Individual and group counselling, crisis intervention, workshops, self-help resources
   - Contact: 250-828-5023
   - Website: https://www.tru.ca/current/counselling.html

3. **TRU Medical Clinic** (⚕️)
   - Primary health care services on campus
   - Services: General medical consultations, treatment for illnesses and injuries, health assessments, referrals
   - Location: Old Main building (OM 1461), Kamloops campus
   - Contact: 250-828-5126 or trumedicalclinic@tru.ca
   - Website: https://www.tru.ca/current/health-services.html

4. **Tournament Capital Centre** (🏋️‍♂️)
   - State-of-the-art fitness and recreation facility
   - Services: Gym access, swimming pool access (via U-PASS), fitness classes, recreational sports
   - Website: https://www.tru.ca/tcc.html

5. **TRU Students' Union Health and Dental Plan** (🦷)
   - Affordable health and dental coverage for students
   - Services: Prescription coverage, dental care, vision care, extended health services
   - Website: https://trusu.ca/services/health-dental-plan/

6. **Accessibility Services** (♿)
   - Support for students with disabilities, including mental health conditions
   - Services: Academic accommodations, advocacy, assistive technology, mental health-related support
   - Website: https://www.tru.ca/current/accessibility-services.html

7. **Community Resources in Kamloops** (🏘️)
   - Off-campus mental and physical health services
   - Includes: Interior Health, Kamloops Urgent Primary Care Centre, Safe Spaces for LGBTQ+ youth
   - Website: https://www.tru.ca/current/community-resources.html

8. **Additional Resources** (📱)
   - GuardMe app for after-hours mental health support
   - Naloxone training through Wellness Centre
   - Health and wellness workshops with recordings available
   - YouTube Channel: https://www.youtube.com/user/TRUWellness

## Guidelines for Responding:

- Be specific and concise with service names, descriptions, contact information, and hyperlinks
- Use a warm and empathetic tone, especially for mental health queries
- For crisis situations, immediately direct to Counselling Services (250-828-5023) or emergency services (911)
- For vague queries, ask follow-up questions to clarify needs
- Always encourage students to visit hyperlinks or contact services directly for current information
- If a query is outside your scope, suggest contacting the Wellness Centre for guidance

Remember: Always prioritize the student's well-being and provide information that is easy to understand and act upon."""

def get_services_by_category():
    """Group services by category for display purposes"""
    categories = {}
    for service in WELLNESS_SERVICES:
        category = service["category"]
        if category not in categories:
            categories[category] = []
        categories[category].append(service)
    return categories

def search_services(query):
    """Search services based on query text"""
    query_lower = query.lower()
    matching_services = []
    
    for service in WELLNESS_SERVICES:
        # Search in name, description, services, and use cases
        searchable_text = (
            service["name"] + " " +
            service["description"] + " " +
            " ".join(service["services"]) + " " +
            " ".join(service["use_cases"])
        ).lower()
        
        if query_lower in searchable_text:
            matching_services.append(service)
    
    return matching_services


def create_wellness_system_message(language: str = "English") -> str:
    """
    Build the system message for a multi-turn Wellness Assistant conversation.

    Returns WELLNESS_MASTER_PROMPT and the response instructions without the
    user query embedded. The query is passed separately as the final user
    turn in the messages list, preventing it from appearing twice in the
    prompt.

    Preserves the original prompt wording and instruction suffix exactly,
    including the double-newline language instruction format used by this
    feature.

    Args:
        language: Language for the response (default: "English").

    Returns:
        System message string for use as the first element of a messages list.
    """
    language_instruction = ""
    if language != "English":
        language_instruction = f"\n\nPlease respond in {language} language."

    return (
        f"{WELLNESS_MASTER_PROMPT}\n\n"
        f"Please provide a helpful response based on the TRU wellness services "
        f"information above. If the query relates to a crisis situation, "
        f"prioritize safety and direct them to appropriate emergency contacts."
        f"{language_instruction}"
    )