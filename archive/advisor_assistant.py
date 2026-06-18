import streamlit as st
import requests
from bs4 import BeautifulSoup
import re

st.set_page_config(page_title="📘 TRU Advisor Assistant", layout="wide")

# Helper: scrape professor cards into text chunks
def scrape_professors(url):
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.find_all("div", class_="card-inner")
    chunks = []
    for card in cards:
        front = card.find("div", class_="card-front")
        name = front.find("span", class_="card-title")
        title = front.find("span", class_="card-subtitle")
        phone_tag = front.find("a", href=lambda x: x and x.startswith("tel:"))
        email_tag = front.find("a", href=lambda x: x and x.startswith("mailto:"))
        back = card.find("div", class_="card-back")

        name_text = name.get_text(strip=True) if name else "N/A"
        title_text = title.get_text(strip=True) if title else "N/A"
        phone = phone_tag.get_text(strip=True) if phone_tag else "N/A"
        email = email_tag.get_text(strip=True) if email_tag else "N/A"
        bio = "N/A"
        if back:
            bio_tag = back.find("p", class_="card-bio")
            if bio_tag:
                bio = bio_tag.get_text(strip=True)

        chunk = (
            "----- Professor Info -----\n"
            f"Name       : {name_text}\n"
            f"Title      : {title_text}\n"
            f"Phone      : {phone}\n"
            f"Email      : {email}\n"
            f"Bio        : {bio}"
        )
        chunks.append(chunk)
    return chunks

# Helper: scrape course <details> into text chunks
def scrape_courses(url):
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    details = soup.find_all("details", class_="course-details")
    chunks = []
    for course in details:
        code_tag = course.find("div", class_="course-title")
        sub_tag = course.find("div", class_="sub-title")
        h4 = course.find("h4")
        p_tags = course.find_all("p")

        code = code_tag.get_text(strip=True) if code_tag else "N/A"
        subtitle = sub_tag.get_text(strip=True) if sub_tag else "N/A"
        full_title = h4.get_text(strip=True) if h4 else "N/A"

        credits = delivery = description = prereq = course_link = "N/A"
        if len(p_tags) >= 1:
            info_line = p_tags[0].get_text(" ", strip=True)
            if "Credits:" in info_line:
                parts = info_line.split("Credits:")
                after = parts[1].split("Delivery:") if len(parts) > 1 else ["", ""]
                credits = after[0].strip()
                if "Delivery:" in info_line:
                    delivery = info_line.split("Delivery:")[1].strip()
        if len(p_tags) >= 2:
            text_full = p_tags[1].get_text(" ", strip=True)
            split_desc = text_full.split("Prerequisite:")
            description = split_desc[0].strip()
            if len(split_desc) > 1:
                prereq = split_desc[1].split("For more information")[0].strip()
            link_tag = p_tags[1].find("a", href=True)
            if link_tag:
                course_link = link_tag["href"]

        chunk = (
            "----- Course Info -----\n"
            f"Course Code: {code}\n"
            f"Title      : {subtitle}\n"
            f"Full Title : {full_title}\n"
            f"Credits    : {credits}\n"
            f"Delivery   : {delivery}\n"
            f"Description: {description}\n"
            f"Prerequisite: {prereq}\n"
            f"Link       : {course_link}"
        )
        chunks.append(chunk)
    return chunks

# Helper: turn a friendly name into a safe filename
def sanitize_filename(name):
    return re.sub(r"\W+", "_", name) + ".txt"

# Initialize session state
if "websites" not in st.session_state:
    st.session_state.websites = [
        {"label": "👩‍🔬 CS Faculty List", "url": "https://www.tru.ca/science/departments/compsci/people.html"},
        {
            "label": "📚 CS Bachelor Curriculum",
            "url": "https://www.tru.ca/science/departments/compsci/programs/cs-bachelor-of-science-major-compsci.html"
        },
    ]
if "chunks" not in st.session_state:
    st.session_state.chunks = {}
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Main UI
st.title("📘 TRU Advisor Assistant")
tabs = st.tabs(["🛠 Data Input Settings", "💬 Ask a Question"])

# --- Tab 1: Data Input Settings ---
with tabs[0]:
    st.header("🛠 Data Input Settings")
    st.write("Manage the webpages to scrape data from. Click 🔄 to update, or ❌ to delete.")

    for idx, site in enumerate(st.session_state.websites):
        col1, col2, col3, col4 = st.columns([4, 1, 1, 1], gap="small")
        col1.write(f"**{site['label']}**")
        col2.markdown(f"[🔗 Visit]({site['url']})")
        if col3.button("🔄 Update", key=f"upd_{idx}"):
            if "people.html" in site["url"]:
                new_chunks = scrape_professors(site["url"])
            else:
                new_chunks = scrape_courses(site["url"])
            st.session_state.chunks[site["label"]] = new_chunks

            fname = sanitize_filename(site["label"])
            with open(fname, "w", encoding="utf-8") as f:
                for c in new_chunks:
                    f.write(c + "\n\n")
            st.success(f"🎉 Saved {len(new_chunks)} chunks to `{fname}`")

        if col4.button("❌ Delete", key=f"del_{idx}"):
            st.session_state.websites.pop(idx)
            st.session_state.chunks.pop(site["label"], None)
            st.experimental_rerun()

    if st.button("➕ Add New Website"):
        st.info("Feature coming soon: add custom sites for scraping.")

    st.markdown("---")
    st.subheader("📦 Chunked Data Preview")
    if st.session_state.chunks:
        for label, chunks in st.session_state.chunks.items():
            with st.expander(f"Chunks for {label}", expanded=False):
                if chunks:
                    for c in chunks:
                        st.code(c, language="text")
                else:
                    st.write("_No chunks available._")
    else:
        st.info("No chunks yet. Click 🔄 to fetch data from a site above.")

# --- Tab 2: Ask a Question ---
with tabs[1]:
    st.header("💬 Ask a Question")
    st.write("Enter your question below. 🤖")

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Type your question here…")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        assistant_reply = "🔧 This feature is under development. Future versions will answer based on scraped data."
        st.session_state.chat_history.append({"role": "assistant", "content": assistant_reply})
        with st.chat_message("assistant"):
            st.markdown(assistant_reply)
