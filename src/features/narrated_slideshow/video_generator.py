"""
Video Generator for Narrated Slideshow Feature

This module handles the generation of MP4 videos from slideshow components,
including slide images, audio narrations, and subtle transitions.
"""

import os
import tempfile
import random
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from io import BytesIO
from PIL import Image

# MoviePy imports
try:
    from moviepy.editor import (
        VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
        concatenate_videoclips, CompositeAudioClip, ColorClip
    )
    from moviepy.video.fx import fadein, fadeout, resize
    # Import transitions more safely
    try:
        from moviepy.video.fx.all import slide_in
        from moviepy.video.fx.all import slide_out
        TRANSITIONS_AVAILABLE = True
    except ImportError:
        TRANSITIONS_AVAILABLE = False
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    TRANSITIONS_AVAILABLE = False

def log_debug(phase: str, status: str, message: str) -> None:
    """Log debug messages with consistent formatting"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[VIDEO_GENERATOR] [{timestamp}] [{phase}] [{status}] {message}")

def check_moviepy_availability() -> Dict[str, Any]:
    """Check if MoviePy is available and return status"""
    if not MOVIEPY_AVAILABLE:
        return {
            "available": False,
            "error": "MoviePy is not installed. Please install it using: pip install moviepy"
        }
    
    try:
        # Test basic MoviePy functionality with a more minimal test
        from moviepy.editor import ColorClip
        test_clip = ColorClip(size=(100, 100), color=(0, 0, 0), duration=0.1)
        test_clip.close()
        return {"available": True}
    except Exception as e:
        return {
            "available": False,
            "error": f"MoviePy installation issue: {str(e)}"
        }

def validate_slideshow_data(slide_images: Dict[int, bytes],
                          audio_files: Dict[int, Dict],
                          narrations: Dict[int, Dict]) -> Dict[str, Any]:
    """
    Validate slideshow components and determine which slides are usable for video export.

    A slide is "usable" if it has a playable audio file - that is the one component a
    video clip cannot exist without. Missing images fall back to a placeholder, and
    missing narration text doesn't block the clip itself. Slides without usable audio
    are skipped (with a warning) instead of failing the whole video, so one bad slide
    (e.g. the LLM omitted a narration, or TTS failed for that slide) doesn't take down
    the entire export.

    Args:
        slide_images: Dictionary of slide images as bytes
        audio_files: Dictionary of audio file information
        narrations: Dictionary of narration data

    Returns:
        Dictionary with validation results. "slide_numbers" contains only usable slides.
    """
    log_debug("VALIDATION", "INFO", "Starting slideshow data validation")

    issues = []
    warnings = []

    if not audio_files:
        issues.append("No audio files available")
        return {
            "valid": False,
            "issues": issues,
            "warnings": warnings,
            "total_slides": 0,
            "slide_numbers": []
        }

    all_slides = set(slide_images.keys()) | set(audio_files.keys()) | set(narrations.keys())

    usable_slides = []
    for slide_num in sorted(all_slides):
        audio_info = audio_files.get(slide_num)
        audio_path = audio_info.get("filepath") if audio_info else None
        if not audio_path or not os.path.exists(audio_path):
            warnings.append(f"Slide {slide_num}: No usable audio file, this slide will be skipped in the video")
            continue
        if slide_num not in slide_images:
            warnings.append(f"Slide {slide_num}: Missing image, will use placeholder")
        if slide_num not in narrations:
            warnings.append(f"Slide {slide_num}: Missing narration text")
        usable_slides.append(slide_num)

    if not usable_slides:
        issues.append("No slides have a usable audio file")

    # Limit slide count for performance
    if len(usable_slides) > 50:
        issues.append(f"Too many slides ({len(usable_slides)}). Maximum supported: 50")

    result = {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "total_slides": len(usable_slides),
        "slide_numbers": usable_slides
    }

    log_debug("VALIDATION", "SUCCESS" if result["valid"] else "ERROR",
             f"Validation complete: {len(issues)} issues, {len(warnings)} warnings, {len(usable_slides)}/{len(all_slides)} slides usable")

    return result

def create_placeholder_image(width: int = 1280, height: int = 720, 
                           text: str = "Slide", bg_color: Tuple[int, int, int] = (240, 240, 240)) -> bytes:
    """
    Create a placeholder image for missing slides
    
    Args:
        width: Image width in pixels
        height: Image height in pixels  
        text: Text to display on placeholder
        bg_color: Background color as RGB tuple
        
    Returns:
        Image bytes
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create image
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        
        # Try to use a default font, fall back to basic font
        try:
            # Try to use a larger font
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 48)
        except:
            try:
                font = ImageFont.load_default()
            except:
                font = None
        
        # Calculate text position for centering
        if font:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        else:
            text_width, text_height = 100, 20  # Fallback estimates
        
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        # Draw text
        draw.text((x, y), text, fill=(100, 100, 100), font=font)
        
        # Convert to bytes
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        return img_bytes.getvalue()
        
    except Exception as e:
        log_debug("PLACEHOLDER", "ERROR", f"Error creating placeholder image: {str(e)}")
        # Return a minimal bytes object if all else fails
        return b''

def get_random_transition() -> str:
    """
    Get a random transition effect for between slides
    
    Returns:
        Transition type string
    """
    # Use simpler transitions that are more likely to work
    transitions = [
        "fade",
        "crossfade"
    ]
    
    # Add slide transitions only if they're available
    if TRANSITIONS_AVAILABLE:
        transitions.extend([
            "slide_left", 
            "slide_right",
            "slide_up",
            "slide_down"
        ])
    
    return random.choice(transitions)

def apply_transition_effect(clip: 'VideoFileClip', transition_type: str, 
                          duration: float = 0.5) -> 'VideoFileClip':
    """
    Apply a transition effect to a video clip
    
    Args:
        clip: MoviePy VideoClip to apply transition to
        transition_type: Type of transition effect
        duration: Duration of transition in seconds
        
    Returns:
        Modified video clip with transition
    """
    try:
        if transition_type == "fade" or transition_type == "crossfade":
            return clip.crossfadein(duration)
        elif transition_type.startswith("slide") and TRANSITIONS_AVAILABLE:
            # Try to use slide transitions if available
            try:
                if transition_type == "slide_left":
                    return clip.fx(slide_in, duration, 'left')
                elif transition_type == "slide_right": 
                    return clip.fx(slide_in, duration, 'right')
                elif transition_type == "slide_up":
                    return clip.fx(slide_in, duration, 'top')
                elif transition_type == "slide_down":
                    return clip.fx(slide_in, duration, 'bottom')
            except:
                # Fall back to fade if slide transitions fail
                return clip.crossfadein(duration)
        else:
            # Default to fade for any unsupported transition
            return clip.crossfadein(duration)
    except Exception as e:
        log_debug("TRANSITION", "WARNING", f"Error applying {transition_type} transition: {str(e)}")
        # Return original clip if transition fails
        return clip

def create_slide_clip(slide_image_bytes: bytes, audio_file_path: str, 
                     slide_number: int, total_slides: int,
                     transition_type: str = "fade", transition_duration: float = 0.3) -> Optional['VideoFileClip']:
    """
    Create a video clip for a single slide with image, audio, and transition
    
    Args:
        slide_image_bytes: Image data as bytes
        audio_file_path: Path to audio file
        slide_number: Current slide number
        total_slides: Total number of slides
        transition_type: Type of transition to apply
        transition_duration: Duration of transition effect
        
    Returns:
        MoviePy VideoFileClip or None if creation fails
    """
    log_debug("CLIP_CREATION", "INFO", f"Creating clip for slide {slide_number}/{total_slides}")
    log_debug("CLIP_CREATION", "DEBUG", f"Audio file path: {audio_file_path}")
    log_debug("CLIP_CREATION", "DEBUG", f"Audio file exists: {os.path.exists(audio_file_path) if audio_file_path else False}")
    log_debug("CLIP_CREATION", "DEBUG", f"Image bytes length: {len(slide_image_bytes) if slide_image_bytes else 0}")
    
    temp_files = []
    
    try:
        # Validate audio file first
        if not audio_file_path or not os.path.exists(audio_file_path):
            raise ValueError(f"Audio file not found: {audio_file_path}")
        
        # Create temporary image file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_img:
            if slide_image_bytes:
                log_debug("CLIP_CREATION", "DEBUG", f"Writing {len(slide_image_bytes)} bytes to temp image")
                # Validate that the image bytes are actually valid image data
                try:
                    # Test if we can open the image with PIL
                    from PIL import Image as PILImage
                    test_img = PILImage.open(BytesIO(slide_image_bytes))
                    test_img.verify()
                    log_debug("CLIP_CREATION", "DEBUG", f"Image validation successful: {test_img.format} {test_img.size}")
                    
                    # Reset the image bytes for writing
                    temp_img.write(slide_image_bytes)
                except Exception as img_error:
                    log_debug("CLIP_CREATION", "WARNING", f"Invalid image bytes, creating placeholder: {img_error}")
                    # Create placeholder image if image bytes are invalid
                    placeholder_bytes = create_placeholder_image(text=f"Slide {slide_number}")
                    temp_img.write(placeholder_bytes)
            else:
                # Create placeholder image
                log_debug("CLIP_CREATION", "DEBUG", "Creating placeholder image")
                placeholder_bytes = create_placeholder_image(text=f"Slide {slide_number}")
                temp_img.write(placeholder_bytes)
            temp_img_path = temp_img.name
            temp_files.append(temp_img_path)
        
        log_debug("CLIP_CREATION", "DEBUG", f"Temp image created: {temp_img_path}")
        log_debug("CLIP_CREATION", "DEBUG", f"Temp image file size: {os.path.getsize(temp_img_path)} bytes")
        
        # Get audio duration
        log_debug("CLIP_CREATION", "DEBUG", "Loading audio file for duration")
        audio_clip = AudioFileClip(audio_file_path)
        audio_duration = audio_clip.duration
        log_debug("CLIP_CREATION", "DEBUG", f"Audio duration: {audio_duration}")
        audio_clip.close()
        
        # Create image clip with proper duration
        log_debug("CLIP_CREATION", "DEBUG", "Creating image clip")
        image_clip = ImageClip(temp_img_path, duration=audio_duration)
        
        # Resize image to standard video dimensions (720p)
        # Use a try-catch to handle Pillow compatibility issues
        log_debug("CLIP_CREATION", "DEBUG", "Resizing image clip")
        try:
            image_clip = image_clip.resize((1280, 720))
        except AttributeError as resize_error:
            log_debug("CLIP_CREATION", "WARNING", f"Resize failed due to Pillow compatibility: {resize_error}")
            # Try alternative resize method or skip resizing if image is already the right size
            try:
                # Check if the image needs resizing
                frame = image_clip.get_frame(0)
                current_height, current_width = frame.shape[:2]
                log_debug("CLIP_CREATION", "DEBUG", f"Current image dimensions: {current_width}x{current_height}")
                
                if current_width != 1280 or current_height != 720:
                    # Use PIL to resize the image before creating the clip
                    from PIL import Image as PILImage
                    
                    # Reopen the image file and resize with PIL
                    with PILImage.open(temp_img_path) as pil_img:
                        # Use LANCZOS (which replaces ANTIALIAS in newer Pillow versions)
                        resized_img = pil_img.resize((1280, 720), PILImage.LANCZOS)
                        
                        # Save the resized image to a new temp file
                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as resized_temp:
                            resized_img.save(resized_temp.name, 'PNG')
                            resized_temp_path = resized_temp.name
                            temp_files.append(resized_temp_path)
                        
                        # Create a new image clip with the resized image
                        image_clip = ImageClip(resized_temp_path, duration=audio_duration)
                        log_debug("CLIP_CREATION", "DEBUG", "Successfully resized image using PIL")
                else:
                    log_debug("CLIP_CREATION", "DEBUG", "Image already at correct dimensions")
                    
            except Exception as pil_error:
                log_debug("CLIP_CREATION", "WARNING", f"PIL resize also failed: {pil_error}")
                log_debug("CLIP_CREATION", "INFO", "Proceeding with original image dimensions")
        
        # Add audio to the clip
        log_debug("CLIP_CREATION", "DEBUG", "Adding audio to clip")
        audio_clip = AudioFileClip(audio_file_path)
        video_clip = image_clip.set_audio(audio_clip)
        
        # Apply transition effect (except for first slide)
        if slide_number > 1:
            log_debug("CLIP_CREATION", "DEBUG", f"Applying {transition_type} transition")
            video_clip = apply_transition_effect(video_clip, transition_type, transition_duration)
        
        log_debug("CLIP_CREATION", "SUCCESS", 
                 f"Created clip for slide {slide_number}: {audio_duration:.2f}s with {transition_type} transition")
        
        return video_clip
        
    except Exception as e:
        error_msg = f"Error creating clip for slide {slide_number}: {str(e)}"
        log_debug("CLIP_CREATION", "ERROR", error_msg)
        import traceback
        log_debug("CLIP_CREATION", "ERROR", f"Full traceback: {traceback.format_exc()}")
        return None
        
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    log_debug("CLEANUP", "DEBUG", f"Deleted temp file: {temp_file}")
            except Exception as e:
                log_debug("CLEANUP", "WARNING", f"Could not delete temp file {temp_file}: {str(e)}")

def generate_slideshow_video(slide_images: Dict[int, bytes],
                           audio_files: Dict[int, Dict],
                           narrations: Dict[int, Dict],
                           output_filename: Optional[str] = None,
                           progress_callback: Optional[callable] = None) -> Dict[str, Any]:
    """
    Generate a complete slideshow video from components
    
    Args:
        slide_images: Dictionary of slide images as bytes
        audio_files: Dictionary of audio file information  
        narrations: Dictionary of narration data
        output_filename: Custom output filename (optional)
        progress_callback: Function to call with progress updates (optional)
        
    Returns:
        Dictionary with generation results
    """
    log_debug("VIDEO_GENERATION", "INFO", "Starting slideshow video generation")
    
    # Check MoviePy availability
    moviepy_check = check_moviepy_availability()
    if not moviepy_check["available"]:
        return {
            "success": False,
            "error": moviepy_check["error"]
        }
    
    # Validate input data
    validation = validate_slideshow_data(slide_images, audio_files, narrations)
    if not validation["valid"]:
        return {
            "success": False,
            "error": f"Validation failed: {'; '.join(validation['issues'])}",
            "warnings": validation["warnings"]
        }
    
    slide_numbers = validation["slide_numbers"]
    total_slides = len(slide_numbers)
    
    # Debug: Log input data details
    log_debug("VIDEO_GENERATION", "DEBUG", f"Slide numbers: {slide_numbers}")
    log_debug("VIDEO_GENERATION", "DEBUG", f"Total slides: {total_slides}")
    log_debug("VIDEO_GENERATION", "DEBUG", f"Slide images keys: {list(slide_images.keys())}")
    log_debug("VIDEO_GENERATION", "DEBUG", f"Audio files keys: {list(audio_files.keys())}")
    
    for slide_num in slide_numbers:
        audio_info = audio_files.get(slide_num, {})
        audio_path = audio_info.get("filepath", "")
        image_size = len(slide_images.get(slide_num, b''))
        log_debug("VIDEO_GENERATION", "DEBUG", f"Slide {slide_num}: audio_path={audio_path}, image_bytes={image_size}")
    
    if progress_callback:
        progress_callback(0, f"Starting video generation for {total_slides} slides...")
    
    video_clips = []
    errors = []
    
    try:
        # Create individual slide clips
        for i, slide_num in enumerate(slide_numbers):
            if progress_callback:
                progress = (i / total_slides) * 0.8  # 80% for clip creation
                progress_callback(progress, f"Creating clip for slide {slide_num}...")
            
            slide_image_bytes = slide_images.get(slide_num, b'')
            audio_info = audio_files.get(slide_num, {})
            audio_path = audio_info.get("filepath", "")
            
            log_debug("VIDEO_GENERATION", "DEBUG", f"Processing slide {slide_num}: image_bytes={len(slide_image_bytes)}, audio_path={audio_path}")
            
            # Get random transition for this slide (except first)
            transition_type = get_random_transition() if slide_num > min(slide_numbers) else "none"
            
            clip = create_slide_clip(
                slide_image_bytes=slide_image_bytes,
                audio_file_path=audio_path,
                slide_number=slide_num,
                total_slides=total_slides,
                transition_type=transition_type,
                transition_duration=0.4  # Quick but noticeable transition
            )
            
            if clip:
                video_clips.append(clip)
                log_debug("VIDEO_GENERATION", "INFO", f"Added clip {i+1}/{total_slides}")
            else:
                error = f"Failed to create clip for slide {slide_num}"
                errors.append(error)
                log_debug("VIDEO_GENERATION", "ERROR", error)
        
        if not video_clips:
            return {
                "success": False,
                "error": "No video clips could be created",
                "errors": errors
            }
        
        if progress_callback:
            progress_callback(0.8, "Combining clips into final video...")
        
        # Combine all clips into final video
        final_video = concatenate_videoclips(video_clips, method="compose")
        
        # Generate output filename
        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"slideshow_video_{timestamp}.mp4"
        
        # Ensure output directory exists
        output_dir = os.path.join(tempfile.gettempdir(), "slideshow_videos")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, output_filename)
        
        if progress_callback:
            progress_callback(0.9, "Exporting final video file...")
        
        # Export video with optimized settings
        final_video.write_videofile(
            output_path,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=None,
            verbose=False,
            logger=None  # Suppress MoviePy logs
        )
        
        # Clean up clips
        for clip in video_clips:
            clip.close()
        final_video.close()
        
        # Get file size for reporting
        file_size = os.path.getsize(output_path)
        file_size_mb = file_size / (1024 * 1024)
        
        if progress_callback:
            progress_callback(1.0, f"Video generation complete! ({file_size_mb:.1f}MB)")
        
        result = {
            "success": True,
            "output_path": output_path,
            "output_filename": output_filename,
            "file_size_bytes": file_size,
            "file_size_mb": file_size_mb,
            "total_slides": total_slides,
            "duration_seconds": final_video.duration if hasattr(final_video, 'duration') else 0,
            "warnings": validation["warnings"] + errors
        }
        
        log_debug("VIDEO_GENERATION", "SUCCESS", 
                 f"Video generated successfully: {output_path} ({file_size_mb:.1f}MB)")
        
        return result
        
    except Exception as e:
        error_msg = f"Error during video generation: {str(e)}"
        log_debug("VIDEO_GENERATION", "ERROR", error_msg)
        
        # Clean up any created clips
        for clip in video_clips:
            try:
                clip.close()
            except:
                pass
        
        return {
            "success": False,
            "error": error_msg,
            "errors": errors
        }

def cleanup_video_files(max_age_hours: int = 24) -> None:
    """
    Clean up old video files from temporary directory
    
    Args:
        max_age_hours: Maximum age of files to keep in hours
    """
    try:
        video_dir = os.path.join(tempfile.gettempdir(), "slideshow_videos")
        if not os.path.exists(video_dir):
            return
        
        import time
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        cleaned_count = 0
        for filename in os.listdir(video_dir):
            if filename.endswith('.mp4'):
                file_path = os.path.join(video_dir, filename)
                file_age = current_time - os.path.getmtime(file_path)
                
                if file_age > max_age_seconds:
                    os.unlink(file_path)
                    cleaned_count += 1
        
        if cleaned_count > 0:
            log_debug("CLEANUP", "INFO", f"Cleaned up {cleaned_count} old video files")
    
    except Exception as e:
        log_debug("CLEANUP", "WARNING", f"Error during video cleanup: {str(e)}")

def get_video_generation_info() -> Dict[str, Any]:
    """
    Get information about video generation capabilities and limits
    
    Returns:
        Dictionary with capability information
    """
    moviepy_status = check_moviepy_availability()
    
    return {
        "moviepy_available": moviepy_status["available"],
        "moviepy_error": moviepy_status.get("error"),
        "max_slides": 50,
        "supported_formats": ["MP4"],
        "video_resolution": "1280x720 (720p HD)",
        "video_fps": 30,
        "transition_types": ["fade", "slide_left", "slide_right", "slide_up", "slide_down", "crossfade"],
        "estimated_processing_time": "~30-60 seconds per slide"
    }
