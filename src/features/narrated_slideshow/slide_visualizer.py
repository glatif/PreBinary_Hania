"""
Slide Visualizer for Narrated Slideshow Feature

This module handles the visual representation of slides/pages from PDF and PowerPoint files.
"""

import os
import tempfile
import platform
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import streamlit as st

try:
    import fitz  # PyMuPDF for PDF to image conversion
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from ppt2pdf import main as ppt2pdf_main
    import comtypes
    PPT2PDF_AVAILABLE = True
except ImportError:
    PPT2PDF_AVAILABLE = False

def log_debug(phase: str, status: str, message: str) -> None:
    """Log debug messages with consistent formatting"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[NARRATED_SLIDESHOW] [{timestamp}] [{phase}] [{status}] {message}")

def convert_ppt_to_pdf(ppt_file_path: str, output_dir: str) -> Optional[str]:
    """
    Convert PowerPoint file to PDF using ppt2pdf library
    
    Args:
        ppt_file_path: Path to the PowerPoint file
        output_dir: Directory to save the converted PDF
        
    Returns:
        Path to the converted PDF file or None if conversion failed
    """
    if not PPT2PDF_AVAILABLE:
        log_debug("CONVERTER", "ERROR", "ppt2pdf library not available - requires Windows platform")
        return None
    
    # comtypes.client.CreateObject (used inside ppt2pdf.main.convert) requires COM
    # to be initialized on the calling thread. Streamlit runs the app script on a
    # ScriptRunner worker thread, not the process main thread, so without this
    # call CreateObject raises "CoInitialize has not been called" - silently
    # caught below, which used to make PPT visual preview always fall back to
    # placeholder images even though everything else (narration/audio) worked.
    com_initialized = False
    try:
        comtypes.CoInitialize()
        com_initialized = True
    except OSError:
        # Already initialized on this thread (e.g. by a prior call) - fine.
        com_initialized = True

    try:
        log_debug("CONVERTER", "INFO", f"Converting PowerPoint to PDF: {ppt_file_path}")

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Convert PowerPoint to PDF.
        # ppt2pdf.main.convert(input, output) forwards `output` verbatim to
        # PowerPoint's COM SaveAs(path, formatType) call - it does NOT treat it as
        # a directory and does not generate a filename inside it. Passing a bare
        # directory here makes PowerPoint try to save a PDF *as* that directory,
        # which always fails with a COM error ("An error occurred while
        # PowerPoint was saving the file"). We must build the full .pdf file path
        # ourselves and pass that.
        base_name = os.path.splitext(os.path.basename(ppt_file_path))[0]
        pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
        ppt2pdf_main.convert(ppt_file_path, pdf_path)

        if os.path.exists(pdf_path):
            log_debug("CONVERTER", "SUCCESS", f"PowerPoint converted to PDF: {pdf_path}")
            return pdf_path
        else:
            log_debug("CONVERTER", "ERROR", f"PDF file not found after conversion: {pdf_path}")
            return None

    except Exception as e:
        log_debug("CONVERTER", "ERROR", f"Error converting PowerPoint to PDF: {str(e)}")
        return None
    finally:
        if com_initialized:
            comtypes.CoUninitialize()

def extract_pdf_page_images(uploaded_file, max_pages: int = 25) -> Dict[int, bytes]:
    """
    Extract page images from PDF file
    
    Args:
        uploaded_file: Streamlit uploaded file object
        max_pages: Maximum number of pages to process
        
    Returns:
        Dictionary mapping page numbers to image bytes
    """
    log_debug("VISUALIZER", "INFO", "Starting PDF page image extraction")
    
    if not PYMUPDF_AVAILABLE:
        log_debug("VISUALIZER", "WARNING", "PyMuPDF not available - using placeholder images")
        return generate_placeholder_images(max_pages, "PDF Page")
    
    try:
        # Reset file pointer
        uploaded_file.seek(0)
        
        # Create temporary file for PyMuPDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(uploaded_file.getbuffer())
            temp_path = temp_file.name
        
        try:
            # Open PDF with PyMuPDF
            pdf_document = fitz.open(temp_path)
            page_images = {}
            
            pages_to_process = min(len(pdf_document), max_pages)
            log_debug("VISUALIZER", "INFO", f"Processing {pages_to_process} PDF pages for visualization")
            
            for page_num in range(pages_to_process):
                try:
                    page = pdf_document.load_page(page_num)
                    
                    # Render page as image (matrix for zoom/quality)
                    mat = fitz.Matrix(1.5, 1.5)  # 1.5x zoom for better quality
                    pix = page.get_pixmap(matrix=mat)
                    
                    # Convert to bytes
                    img_bytes = pix.tobytes("png")
                    page_images[page_num + 1] = img_bytes  # 1-indexed
                    
                    log_debug("VISUALIZER", "INFO", f"Extracted image for page {page_num + 1}")
                    
                except Exception as e:
                    log_debug("VISUALIZER", "WARNING", f"Error extracting page {page_num + 1}: {str(e)}")
                    # Create placeholder for failed page
                    placeholder = create_placeholder_image(f"PDF Page {page_num + 1}\n[Image extraction failed]")
                    page_images[page_num + 1] = placeholder
            
            pdf_document.close()
            log_debug("VISUALIZER", "SUCCESS", f"Successfully extracted {len(page_images)} page images")
            
            return page_images
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        error_msg = f"Error extracting PDF page images: {str(e)}"
        log_debug("VISUALIZER", "ERROR", error_msg)
        return generate_placeholder_images(max_pages, "PDF Page")

def extract_ppt_slide_images(uploaded_file, max_slides: int = 20) -> Dict[int, bytes]:
    """
    Extract slide images from PowerPoint file by converting to PDF first
    
    Args:
        uploaded_file: Streamlit uploaded file object
        max_slides: Maximum number of slides to process
        
    Returns:
        Dictionary mapping slide numbers to image bytes
    """
    log_debug("VISUALIZER", "INFO", "Starting PowerPoint slide image extraction via PDF conversion")
    
    # Check platform compatibility
    current_platform = platform.system()
    if current_platform != "Windows":
        log_debug("VISUALIZER", "WARNING", f"PowerPoint processing not supported on {current_platform}. Requires Windows platform.")
        st.warning(
            "⚠️ **PowerPoint Processing Limitation**\n\n"
            f"PowerPoint file processing is not supported on {current_platform} due to COM technology dependencies. "
            "This feature requires Windows operating system.\n\n"
            "**Recommendation:** Please convert your PowerPoint presentation to PDF format for optimal compatibility "
            "and visual preview quality on your current operating system."
        )
        return generate_placeholder_images(max_slides, "PPT Slide")
    
    if not PPT2PDF_AVAILABLE:
        log_debug("VISUALIZER", "WARNING", "ppt2pdf not available - using placeholder images (requires Windows platform)")
        return generate_placeholder_images(max_slides, "PPT Slide")
    
    if not PYMUPDF_AVAILABLE:
        log_debug("VISUALIZER", "WARNING", "PyMuPDF not available - using placeholder images")
        return generate_placeholder_images(max_slides, "PPT Slide")
    
    # Create temporary directories for processing.
    # ignore_cleanup_errors=True: if PowerPoint's COM process still holds the
    # .pptx file open after a failed/slow SaveAs, directory cleanup would
    # otherwise raise PermissionError on __exit__ and crash this entire
    # function (masking the graceful placeholder-image fallback below).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        try:
            # Reset file pointer
            uploaded_file.seek(0)
            
            # Save uploaded PowerPoint file to temporary location
            ppt_extension = ".pptx" if uploaded_file.name.endswith('.pptx') else ".ppt"
            ppt_temp_path = os.path.join(temp_dir, f"temp_presentation{ppt_extension}")
            
            with open(ppt_temp_path, "wb") as temp_file:
                temp_file.write(uploaded_file.getbuffer())
            
            log_debug("VISUALIZER", "INFO", f"Saved PowerPoint file to: {ppt_temp_path}")
            
            # Convert PowerPoint to PDF
            pdf_output_dir = os.path.join(temp_dir, "pdf_output")
            pdf_path = convert_ppt_to_pdf(ppt_temp_path, pdf_output_dir)
            
            if not pdf_path or not os.path.exists(pdf_path):
                log_debug("VISUALIZER", "ERROR", "Failed to convert PowerPoint to PDF")
                return generate_placeholder_images(max_slides, "PPT Slide")
            
            log_debug("VISUALIZER", "SUCCESS", f"PowerPoint converted to PDF: {pdf_path}")
            
            # Now use the existing PDF processing pipeline
            # Create a file-like object from the PDF
            class PDFFileWrapper:
                def __init__(self, pdf_path):
                    self.pdf_path = pdf_path
                    self._content = None
                
                def seek(self, position):
                    pass  # No-op for file path
                
                def getbuffer(self):
                    if self._content is None:
                        with open(self.pdf_path, 'rb') as f:
                            self._content = f.read()
                    return self._content
            
            pdf_file_wrapper = PDFFileWrapper(pdf_path)
            
            # Use the existing PDF extraction function with slide limit
            slide_images = extract_pdf_page_images(pdf_file_wrapper, max_pages=max_slides)
            
            log_debug("VISUALIZER", "SUCCESS", f"Extracted {len(slide_images)} slide images from converted PDF")
            return slide_images
            
        except Exception as e:
            error_msg = f"Error extracting PowerPoint slide images via PDF conversion: {str(e)}"
            log_debug("VISUALIZER", "ERROR", error_msg)
            return generate_placeholder_images(max_slides, "PPT Slide")

def create_placeholder_image(text: str) -> bytes:
    """Create a simple placeholder image with text"""
    if not PIL_AVAILABLE:
        # Return a simple text representation as bytes
        return text.encode('utf-8')
    
    try:
        width, height = 400, 300
        img = Image.new('RGB', (width, height), '#f0f0f0')
        draw = ImageDraw.Draw(img)
        
        # Draw border
        draw.rectangle([(10, 10), (width-10, height-10)], outline='#cccccc', width=2)
        
        # Draw text
        lines = text.split('\n')
        y_offset = height // 2 - (len(lines) * 10)
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw.text((x, y_offset), line, fill='#666666')
            y_offset += 20
        
        # Convert to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
        
    except Exception as e:
        # Fallback to text
        return text.encode('utf-8')

def generate_placeholder_images(count: int, prefix: str) -> Dict[int, bytes]:
    """Generate placeholder images for multiple slides/pages"""
    images = {}
    for i in range(1, count + 1):
        placeholder_text = f"{prefix} {i}\n[Visual preview not available]"
        images[i] = create_placeholder_image(placeholder_text)
    return images

def display_slide_image(slide_num: int, image_bytes: bytes, caption: str = None) -> None:
    """Display a slide image in Streamlit"""
    try:
        if image_bytes:
            st.image(image_bytes, caption=caption or f"Slide {slide_num}", width="stretch")
        else:
            st.warning(f"⚠️ No image available for slide {slide_num}")
    except Exception as e:
        st.error(f"❌ Error displaying slide {slide_num}: {str(e)}")
        log_debug("VISUALIZER", "ERROR", f"Error displaying slide {slide_num}: {str(e)}")
