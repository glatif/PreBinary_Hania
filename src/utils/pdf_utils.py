import os
import pypdf
from typing import Dict, List, Any

def extract_text_from_pdf(pdf_file) -> str:
    """
    Extract text from a PDF file
    
    Args:
        pdf_file: File object or path to the PDF file
        
    Returns:
        Extracted text as a string
    """
    try:
        reader = pypdf.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {str(e)}")

def save_uploaded_pdf(uploaded_file, save_dir='temp_uploads') -> str:
    """
    Save an uploaded PDF file to a temporary directory
    
    Args:
        uploaded_file: The uploaded file object
        save_dir: Directory to save the file
        
    Returns:
        Path to the saved file
    """
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, uploaded_file.name)
    
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    return file_path 