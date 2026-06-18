import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

def scrape_professors(url: str) -> List[str]:
    """
    Scrape professor information from a university website.
    
    Args:
        url: URL of the professors page
        
    Returns:
        List of text chunks containing professor information
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

def scrape_courses(url: str) -> List[str]:
    """
    Scrape course information from a university website.
    
    Args:
        url: URL of the courses page
        
    Returns:
        List of text chunks containing course information
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
