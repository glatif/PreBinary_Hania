import requests
import os
from bs4 import BeautifulSoup
import re
import json
import numpy as np
import faiss
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

# Import embedding utilities
from src.utils.embedding_wrapper import get_embedding_model, DEFAULT_MODEL_NAME

# Model for creating embeddings
EMBEDDING_MODEL = DEFAULT_MODEL_NAME

# Helper: scrape professor cards into text chunks
def scrape_professors(url):
    """
    Scrapes professor information from a webpage and returns as formatted text chunks
    """
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
    """
    Scrapes course information from a webpage and returns as formatted text chunks
    """
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

# Helper: scrape arbitrary pages that don't match the TRU card/course layouts
def scrape_generic(url):
    """
    Scrape readable text content from an arbitrary webpage.

    Used as a fallback whenever a URL doesn't match the structured TRU
    faculty or course page layouts, so admins can add any informational
    page (not just TRU CS pages) as an Advisor AI data source.
    """
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True)

    # Group lines into paragraph-sized chunks so downstream dynamic chunking
    # has reasonably sized units to work with, matching the chunk shape
    # produced by scrape_professors()/scrape_courses().
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    paragraphs = []
    buffer: List[str] = []
    for line in lines:
        buffer.append(line)
        if len(" ".join(buffer)) > 300:
            paragraphs.append(" ".join(buffer))
            buffer = []
    if buffer:
        paragraphs.append(" ".join(buffer))

    return paragraphs


# URL helpers used by the Data Management "add website" UI to validate and
# bulk-import data source URLs (typed in, pasted as a list, or from a
# user-uploaded .txt file).
_URL_RE = re.compile(r'^https?://[^\s]+\.[^\s]{2,}$')


def is_valid_url(url: Optional[str]) -> bool:
    """Return True if url looks like a well-formed http(s) URL."""
    return bool(url) and bool(_URL_RE.match(url.strip()))


def label_from_url(url: str) -> str:
    """Derive a human-readable label from a URL's path or domain for display."""
    parsed = urlparse(url)
    last_segment = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    name = last_segment or parsed.netloc
    name = re.sub(r"\.html?$", "", name).replace("-", " ").replace("_", " ")
    return name.strip().title() or parsed.netloc


def parse_urls_from_text(text: str) -> List[Tuple[Optional[str], str]]:
    """
    Extract distinct http(s) URLs from free-form text, one per line.

    Each line may optionally contain a "Label | URL" pair (label first,
    separated by a pipe); otherwise the whole line is treated as the URL and
    a label is derived later from its domain via label_from_url(). Blank
    lines, invalid URLs, and duplicate URLs (within the same text) are skipped.

    Returns a list of (label_or_none, url) tuples in the order encountered.
    """
    results = []
    seen = set()
    # Strip a leading BOM defensively (in case it survived decoding upstream)
    # so it doesn't glue onto the first URL and fail validation.
    text = text.lstrip("﻿")
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("﻿")
        if not line:
            continue
        if "|" in line:
            label, url = line.split("|", 1)
            label, url = label.strip(), url.strip()
        else:
            label, url = None, line
        if not is_valid_url(url) or url in seen:
            continue
        seen.add(url)
        results.append((label, url))
    return results


# Helper: turn a friendly name into a safe filename
def sanitize_filename(name):
    """
    Convert a friendly name into a safe filename
    """
    return re.sub(r"\W+", "_", name) + ".txt"

# Default websites for scraping
def get_default_websites():
    """
    Returns default websites to scrape for advisor information
    """
    return [
        {"label": "👩‍🔬 CS Faculty List", "url": "https://www.tru.ca/science/departments/compsci/people.html"},
        {
            "label": "📚 CS Bachelor Curriculum",
            "url": "https://www.tru.ca/science/departments/compsci/programs/cs-bachelor-of-science-major-compsci.html"
        },
    ]

# Functions for integration with vector DB
def save_chunks_to_file(chunks, label, save_dir):
    """
    Save chunks to a text file in the specified directory
    """
    os.makedirs(save_dir, exist_ok=True)
    fname = os.path.join(save_dir, sanitize_filename(label))
    with open(fname, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(c + "\n\n")
    return fname

def prepare_chunks_for_indexing(chunks_dict):
    """
    Prepare chunks for indexing in the vector database
    """
    indexed_chunks = []
    for label, chunks in chunks_dict.items():
        for i, chunk in enumerate(chunks):
            indexed_chunks.append({
                "source": label,
                "chunk_id": f"{label}_{i}",
                "chunk": chunk
            })
    return indexed_chunks

# Note: The create_advisor_embeddings function has been moved to the storage.py module
# and improved with dynamic chunking and better error handling.
# See src.features.advisor_ai.storage.create_embeddings for the new implementation.
