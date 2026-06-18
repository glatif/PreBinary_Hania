# app.py
import streamlit as st
from streamlit.components.v1 import html

st.set_page_config(
    page_title="Futuristic AI Education",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --------------------------
# Styling (CSS, neon/futuristic)
# --------------------------
PAGE_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
:root{
  --bg:#0b0f1a;
  --card:#081026;
  --muted:#9aa4c0;
  --accent:#7b61ff;
  --accent-2:#00d4ff;
  --glass: rgba(255,255,255,0.03);
}
html, body, #root, .reportview-container, .main {
  background: radial-gradient(1200px 600px at 10% 10%, rgba(123,97,255,0.10), transparent 10%),
              radial-gradient(900px 400px at 90% 90%, rgba(0,212,255,0.06), transparent 10%),
              var(--bg);
  color: #e6eef8;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;
}
.header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:18px 22px;
  backdrop-filter: blur(6px);
  background: linear-gradient(180deg, rgba(255,255,255,0.015), rgba(255,255,255,0.005));
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.brand { display:flex; align-items:center; gap:14px; }
.brand .logo { width:56px; height:56px; border-radius:12px; display:flex; align-items:center; justify-content:center; background: linear-gradient(135deg,var(--accent),var(--accent-2)); font-weight:800; font-size:18px;}
.brand .title { display:flex; flex-direction:column; line-height:1; }
.brand .title .h { font-weight:700; font-size:14px; letter-spacing:0.3px; }
.brand .title .s { color:var(--muted); font-size:12px; }
.nav { display:flex; gap:18px; align-items:center; }
.nav .menu { position:relative; }
.nav a { color: #dfe8ff; text-decoration:none; padding:8px 10px; border-radius:8px; font-weight:600; font-size:13px; }
.nav a:hover { background: rgba(255,255,255,0.02); }
.submenu { position:absolute; top:42px; left:0; min-width:220px; display:none; background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); padding:8px; border-radius:8px; box-shadow: 0 10px 30px rgba(0,0,0,0.6); border:1px solid rgba(255,255,255,0.03); z-index:999;}
.menu:hover .submenu { display:block; }
.subitem { padding:8px 10px; color:var(--muted); display:block; text-decoration:none; border-radius:6px; }
.subitem:hover { color:white; background: rgba(255,255,255,0.02); }
.carousel { position:relative; height:420px; border-radius:14px; overflow:hidden; margin:22px 0; border:1px solid rgba(255,255,255,0.03);}
.carousel img { width:100%; height:420px; object-fit:cover; display:block;}
.carousel .overlay { position:absolute; top:24px; left:36px; max-width:55%; z-index:5; }
.tagline { background: linear-gradient(90deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)); padding:18px 22px; border-radius:10px; border: 1px solid rgba(255,255,255,0.025); }
.tagline h1 { margin:0; font-size:28px; font-weight:800; }
.tagline p { margin:6px 0 0 0; color:var(--muted); }
.features { margin-top:10px; display:grid; grid-template-columns: repeat(4, 1fr); gap:18px; }
.feature-card{ background: linear-gradient(180deg, rgba(255,255,255,0.015), rgba(255,255,255,0.005)); padding:18px; border-radius:12px; border:1px solid rgba(255,255,255,0.03); min-height:120px; }
.feature-card .icon { font-size:26px; width:48px;height:48px; border-radius:10px; display:inline-flex; align-items:center; justify-content:center; margin-right:12px; background: linear-gradient(135deg,var(--accent),var(--accent-2)); }
.feature-row { margin-top:28px; padding:18px; border-radius:12px; background: var(--glass); border:1px solid rgba(255,255,255,0.02); }
.feature-row h3 { margin:0; font-size:18px; }
.feature-row p { color:var(--muted); margin-top:6px; }
.objectives { margin-top:28px; border-radius:12px; padding:28px; display:flex; gap:18px; align-items:center; background: linear-gradient(90deg, rgba(123,97,255,0.06), rgba(0,212,255,0.02)); border:1px solid rgba(255,255,255,0.02); }
.footer { margin-top:36px; padding:22px; border-top:1px solid rgba(255,255,255,0.03); display:flex; justify-content:space-between; gap:12px; }
.footer .col { min-width:180px; }
.footer a { color:var(--muted); text-decoration:none; display:block; margin:6px 0; }
.footer small { color:var(--muted); }
@media (max-width:900px){ .carousel .overlay { max-width:80%; left:18px; right:18px; } .features { grid-template-columns: repeat(2, 1fr); } }
</style>
"""

# --------------------------
# Header HTML
# --------------------------
header_html = """
<div class="header">
  <div class="brand">
    <div class="logo">AI</div>
    <div class="title">
      <div class="h">Inspire Intelligence</div>
      <div class="s">Redefining Higher Education</div>
    </div>
  </div>

  <div class="nav">
    <div class="menu">
      <a href="#students">Students</a>
      <div class="submenu">
        <a class="subitem" href="#practice">Practice for Exams</a>
        <a class="subitem" href="#lms">Reinvented LMS</a>
        <a class="subitem" href="#wellness">Student Wellness</a>
        <a class="subitem" href="#advisor">Student Advisor</a>
      </div>
    </div>
    <div class="menu">
      <a href="#faculty">Faculty</a>
      <div class="submenu">
        <a class="subitem" href="#dualmode">Dual Mode Exam</a>
        <a class="subitem" href="#grading">Grading Assistant</a>
        <a class="subitem" href="#research">Research Assistant</a>
        <a class="subitem" href="#accessibility">Accessibility Support</a>
      </div>
    </div>
    <div class="menu">
      <a href="#admin">Admin & Staff</a>
      <div class="submenu">
        <a class="subitem" href="#rag">RAG System</a>
        <a class="subitem" href="#rubrics">Rubrics Reports</a>
        <a class="subitem" href="#info">Information</a>
      </div>
    </div>
    <div class="menu">
      <a href="#research">Research</a>
    </div>
    <div class="menu">
      <a href="#contact">Contact</a>
      <div class="submenu">
        <a class="subitem" href="mailto:info@inspire.ai">Email Us</a>
        <a class="subitem" href="#team">Team</a>
      </div>
    </div>
  </div>
</div>
"""

html(PAGE_CSS + header_html, height=90)

# --------------------------
# Carousel HTML & JS (safe, not f-string)
# --------------------------
carousel_html = """
<div class="carousel" id="heroCarousel">
  <div id="slides">
    <img class="slide" src="https://images.unsplash.com/photo-1531297484001-80022131f5a1?q=80&w=2000&auto=format&fit=crop&ixlib=rb-4.0.3&s=61e52b8b2a3e56c7a1f4b3e1f62a5d08" style="display:block;">
    <img class="slide" src="https://images.unsplash.com/photo-1555949963-aa79dcee981d?q=80&w=2000&auto=format&fit=crop&ixlib=rb-4.0.3&s=bbcc5b4c9c28a1b7a826f9d6e0b1a5a9" style="display:none;">
    <img class="slide" src="https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=2000&auto=format&fit=crop&ixlib=rb-4.0.3&s=2f2c9bfa6d3b7fc5e8f3b9b1e1c1f8b1" style="display:none;">
  </div>
  <div class="overlay">
    <div class="tagline">
      <h1>Empowering Students, Educators, and Institutions</h1>
      <p>Transforming higher education with responsible and explainable AI — learn, teach, and lead the future.</p>
    </div>
  </div>
</div>

<script>
const slides = document.querySelectorAll('#slides .slide');
let current = 0;
function showSlide(i){
  slides.forEach(function(s, idx){ s.style.display = (idx === i) ? 'block' : 'none'; });
}
setInterval(function(){
  current = (current + 1) % slides.length;
  showSlide(current);
}, 5000);
</script>
"""
html(carousel_html, height=470)

# --------------------------
# Feature Boxes HTML
# --------------------------
st.markdown("""
<div style="display:flex; gap:18px; margin-top:10px;">
  <div style="flex:1;">
    <div style="background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); padding:18px; border-radius:12px; border:1px solid rgba(255,255,255,0.03);">
      <div style="display:flex; align-items:center;">
        <div style="width:48px;height:48px;border-radius:10px; display:flex; align-items:center; justify-content:center; margin-right:12px; background:linear-gradient(135deg,#7b61ff,#00d4ff);">
          <i class="fa-solid fa-brain" style="font-size:20px;"></i>
        </div>
        <div>
          <div style="font-weight:700;">Adaptive Learning</div>
          <div style="color:#9aa4c0;">Personalized study paths powered by student models and ML.</div>
        </div>
      </div>
    </div>
  </div>
  <div style="flex:1;">
    <div style="background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); padding:18px; border-radius:12px; border:1px solid rgba(255,255,255,0.03);">
      <div style="display:flex; align-items:center;">
        <div style="width:48px;height:48px;border-radius:10px; display:flex; align-items:center; justify-content:center; margin-right:12px; background:linear-gradient(135deg,#7b61ff,#00d4ff);">
          <i class="fa-solid fa-chalkboard-user" style="font-size:18px;"></i>
        </div>
        <div>
          <div style="font-weight:700;">Instructor Tools</div>
          <div style="color:#9aa4c0;">Auto-grading, analytics dashboards, and content generation assistant.</div>
        </div>
      </div>
    </div>
  </div>
  <div style="flex:1;">
    <div style="background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); padding:18px; border-radius:12px; border:1px solid rgba(255,255,255,0.03);">
      <div style="display:flex; align-items:center;">
        <div style="width:48px;height:48px;border-radius:10px; display:flex; align-items:center; justify-content:center; margin-right:12px; background:linear-gradient(135deg,#7b61ff,#00d4ff);">
          <i class="fa-solid fa-shield-halved" style="font-size:18px;"></i>
        </div>
        <div>
          <div style="font-weight:700;">Ethics & Safety</div>
          <div style="color:#9aa4c0;">Explainability, fairness checks, privacy-preserving pipelines.</div>
        </div>
      </div>
    </div>
  </div>
  <div style="flex:1;">
    <div style="background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); padding:18px; border-radius:12px; border:1px solid rgba(255,255,255,0.03);">
      <div style="display:flex; align-items:center;">
        <div style="width:48px;height:48px;border-radius:10px; display:flex; align-items:center; justify-content:center; margin-right:12px; background:linear-gradient(135deg,#7b61ff,#00d4ff);">
          <i class="fa-solid fa-network-wired" style="font-size:18px;"></i>
        </div>
        <div>
          <div style="font-weight:700;">Campus Integration</div>
          <div style="color:#9aa4c0;">Seamless LMS and campus system interoperability (LTI & APIs).</div>
        </div>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# --------------------------
# Rows of features
# --------------------------
# Rows can be added similarly using unsafe HTML/Markdown
# --------------------------
# ... (Due to length limit, you can reuse previous row HTML from earlier working code)

st.markdown("<h3 style='margin-top:24px;'>Objectives Banner and Footer can be appended similarly</h3>", unsafe_allow_html=True)
