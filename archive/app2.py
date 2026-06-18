import streamlit as st
from PIL import Image
import itertools # Used for cycling through images for the 'slider'
import time # Used for the 'slider' loop

# --- 1. CONFIGURATION AND STYLES (Futuristic Theme) ---
st.set_page_config(
    page_title="FutureLearn AI University",
    page_icon="🤖",
    layout="wide"
)

# Custom CSS for a futuristic, AI-inspired look
st.markdown("""
<style>
    /* Global Background and Text */
    .stApp {
        background-color: #0A1931; /* Deep Blue/Black */
        color: #E0E7FF; /* Light Blue/White Text */
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    /* Headers - Primary Color Accent */
    h1, h2, h3 {
        color: #00BCD4; /* Cyan/Aqua Accent */
        text-shadow: 1px 1px 3px rgba(0, 188, 212, 0.4);
    }

    /* Primary Buttons */
    div.stButton > button:first-child {
        background-color: #00BCD4;
        color: #0A1931;
        font-weight: bold;
        border: 2px solid #00BCD4;
        transition: all 0.3s;
    }
    div.stButton > button:first-child:hover {
        background-color: #0A1931;
        color: #00BCD4;
        border: 2px solid #00BCD4;
    }
    
    /* Boxed Features Styling */
    .feature-box {
        background-color: #1A3051; /* Darker Blue Box */
        border: 1px solid #00BCD4;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 4px 8px rgba(0, 188, 212, 0.2);
        min-height: 200px;
    }
    .feature-box h4 {
        color: #FFC107; /* Gold/Amber for feature titles */
        margin-top: 0;
    }
    .feature-icon {
        font-size: 2.5em;
        color: #00BCD4;
        margin-bottom: 10px;
    }
    
    /* Banner Tagline Style */
    .tagline-container {
        position: relative;
        text-align: center;
        color: white;
        padding: 50px 0;
    }
    .tagline-text {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        font-size: 3em;
        font-weight: 900;
        color: #FFC107;
        text-shadow: 2px 2px 6px #000000;
        z-index: 10;
    }
    
    /* Footer Styling */
    .footer {
        background-color: #050E1A; /* Even darker footer */
        color: #E0E7FF;
        padding: 20px 0;
        margin-top: 40px;
        text-align: center;
        border-top: 3px solid #00BCD4;
    }
    
    /* Adjust Streamlit's top padding for a tighter fit */
    .css-18e3th9 {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. DATA (Placeholder Content) ---

# Note: Streamlit doesn't support nested menus (sub-menus) in the main layout without custom HTML/CSS.
# We will represent them as a simple list of main links.
MENU_ITEMS = {
    "Programs": ["B.S. in AI Ethics", "M.S. in Neural Networks"],
    "Admissions": ["Apply Now", "Financial Aid"],
    "Research": ["AI Labs", "Faculty"],
    "Community": ["Student Life", "Alumni Network"],
    "About": ["Our Mission", "Contact Us"]
}

# Feature Boxes Data
FEATURES = [
    {"icon": "🧠", "title": "Cognitive Engines", "desc": "AI-driven personalized learning paths."},
    {"icon": "⚙️", "title": "Automated Grading", "desc": "Instant, unbiased feedback on all assignments."},
    {"icon": "🌐", "title": "Global Simulation", "desc": "VR/AR labs for hands-on, remote training."},
    {"icon": "📊", "title": "Data-Powered Insights", "desc": "Real-time analytics on student progress."},
]

# Feature Rows Data
FEATURE_ROWS = [
    {"title": "The AI Curriculum Revolution", "desc": "Our programs are continually updated by a learning AI to stay ahead of industry demands, ensuring relevance and future-proofing your career.", "features": FEATURES[0:2]},
    {"title": "Immersive Learning Environments", "desc": "Step into the future of education with synthetic environments designed for collaboration and complex problem-solving.", "features": FEATURES[2:4]},
]

# Image Placeholders (Replace these with actual image file paths or URLs)
IMAGE_PATHS = [
    "assets/img/ai_classroom.jpg",  # Placeholder for an image file
    "assets/img/neural_network.jpg",
    "assets/img/future_campus.jpg"
]

# To make the code run without external files, we'll use placeholder images from a common source (e.g., Unsplash/Pexels style abstract tech images).
# NOTE: For a real app, replace these with your own images.
# In a local environment, you would use: Image.open("your_file.jpg")
try:
    img1 = Image.new('RGB', (1600, 400), color = '#2C3E50')
    img2 = Image.new('RGB', (1600, 400), color = '#1D3B51')
    img3 = Image.new('RGB', (1600, 400), color = '#34495E')
    IMAGE_OBJECTS = [img1, img2, img3]
except:
    st.warning("Pillow library not found or images couldn't be created. Banner will be blank.")
    IMAGE_OBJECTS = [None, None, None]


# --- 3. HELPER FUNCTIONS ---

# Function to create the menu bar with sub-menu simulation
def create_menu_bar():
    st.markdown('<div style="display: flex; justify-content: space-around; background-color: #1A3051; padding: 10px 0; border-radius: 5px;">', unsafe_allow_html=True)
    for main_item, sub_items in MENU_ITEMS.items():
        # Display main menu item
        st.markdown(f'**<span style="color: #FFC107;">{main_item} ▼</span>**', unsafe_allow_html=True)
        
        # Display sub-menu items (Simple text representation, not interactive dropdowns)
        sub_menu_html = ' | '.join([f'<a href="#" style="color: #E0E7FF; text-decoration: none;">{sub}</a>' for sub in sub_items])
        st.markdown(f'<span style="font-size: 0.8em; margin-left: 10px;">({sub_menu_html})</span>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# Function to simulate the image slider (requires a specific Streamlit execution loop)
def image_slider(images, tagline, interval=5):
    placeholder = st.empty()
    image_cycler = itertools.cycle(images)
    
    # Check if the app is in its initial run state (to avoid re-running the loop constantly)
    if 'current_image_index' not in st.session_state:
        st.session_state.current_image_index = 0
        
    # Streamlit doesn't natively support background threads for auto-slideshows.
    # A common workaround is to use a specific display pattern, but true auto-sliding
    # requires a custom component or a constant loop which re-runs the whole app.
    # For a static example:
    
    with placeholder.container():
        # Display the image with the tagline overlay
        st.markdown('<div class="tagline-container">', unsafe_allow_html=True)
        if images[st.session_state.current_image_index] is not None:
             st.image(images[st.session_state.current_image_index], use_column_width='always')
        else:
             st.markdown('<div style="height:400px; background-color: #2C3E50;"></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="tagline-text">{tagline}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Add basic navigation buttons for manual control
        col_prev, col_next = st.columns([1, 1])
        with col_prev:
            if st.button("⬅️ Previous Image"):
                st.session_state.current_image_index = (st.session_state.current_image_index - 1) % len(images)
                st.rerun()
        with col_next:
            if st.button("Next Image ➡️"):
                st.session_state.current_image_index = (st.session_state.current_image_index + 1) % len(images)
                st.rerun()


# --- 4. WEB PAGE STRUCTURE ---

# HEADER: Logo and Navigation
st.container()
logo_col, menu_col = st.columns([1, 4])

with logo_col:
    # Logo at top left
    st.image("https://streamlit.io/logo.svg", width=100, caption="FutureLearn AI U") 

with menu_col:
    # 5 Menu Items (with simulated sub-menu links)
    create_menu_bar()

st.markdown("---")

## 1. AI Banner / Image Slider
tagline = "Engineering the Minds of Tomorrow"
image_slider(IMAGE_OBJECTS, tagline, interval=5)

st.markdown("---")

## 2. Feature Section (The Grid)
st.header("🔬 Core Features of the AI University")
st.write("Leveraging state-of-the-art AI to redefine the educational experience, making it personalized, efficient, and deeply engaging.")
st.markdown("<br>", unsafe_allow_html=True)


# Features Listed in Three Rows
for row_data in FEATURE_ROWS:
    st.subheader(f"✨ {row_data['title']}")
    st.markdown(f"<p style='font-size: 1.1em;'>{row_data['desc']}</p>", unsafe_allow_html=True)
    
    # Create 4 columns for the features (even though we only have 2 per row in the example data)
    cols = st.columns(4) 
    
    # Distribute features into the columns
    for i, feature in enumerate(row_data['features']):
        with cols[i]:
            # Use custom HTML for the box structure
            st.markdown(f"""
            <div class="feature-box">
                <div class="feature-icon">{feature['icon']}</div>
                <h4>{feature['title']}</h4>
                <p>{feature['desc']}</p>
            </div>
            """, unsafe_allow_html=True)
            
    st.markdown("<br>", unsafe_allow_html=True)

st.markdown("---")

## 3. Objectives Banner
st.header("🎯 Our Planetary Objectives")
obj_col1, obj_col2 = st.columns([3, 1])

with obj_col1:
    st.markdown("""
    <div style="background-color: #1A3051; padding: 30px; border-radius: 10px; border-left: 5px solid #FFC107;">
        <h3 style="color: #E0E7FF; margin-top: 0;">Igniting the Next Era of Human-AI Collaboration</h3>
        <p>Our core objective is to cultivate a new generation of leaders who don't just use AI, but **master** it. We aim to bridge the gap between theoretical knowledge and practical application, ensuring our graduates are instantly impactful in a rapidly evolving technological landscape. This means a relentless focus on **ethical AI**, **critical thinking**, and **interdisciplinary problem-solving**.</p>
    </div>
    """, unsafe_allow_html=True)

with obj_col2:
    # Another banner image placeholder
    st.image("assets/img/objectives_banner.jpg", caption="Innovation Hub")
    # Using placeholder image
    st.markdown('<div style="height: 200px; background-color: #00BCD4; border-radius: 10px;"></div>', unsafe_allow_html=True)


st.markdown("---")

## 4. Footer Section
st.markdown('<div class="footer">', unsafe_allow_html=True)

# Footer Menu (Listing main and sub-menu for clarity)
st.subheader("Navigation")
footer_menu_cols = st.columns(len(MENU_ITEMS))
for i, (main_item, sub_items) in enumerate(MENU_ITEMS.items()):
    with footer_menu_cols[i]:
        st.markdown(f"**{main_item}**", unsafe_allow_html=True)
        for sub in sub_items:
            st.markdown(f"- <a href='#' style='color: #8D99AE; text-decoration: none;'>{sub}</a>", unsafe_allow_html=True)

st.markdown("<hr style='border-top: 1px dashed #4C5773;'>", unsafe_allow_html=True)

# Webpage Information at the end
st.markdown("""
    <p style='font-size: 0.9em; margin-bottom: 5px;'>
        FutureLearn AI University | &copy; 2042 All Rights Reserved.
    </p>
    <p style='font-size: 0.8em; color: #8D99AE;'>
        Designed on the Streamlit Framework for Rapid Prototyping.
        The Future of Higher Education is Algorithmic.
    </p>
    <p>🤖 Built with Python & Love for Data Science 🧠</p>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)