"""
Text-to-Speech Engine for Narrated Slideshow Feature

This module handles the conversion of narration text to audio files
using various TTS providers.
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional
import streamlit as st

try:
    from gtts import gTTS
    import pydub
    from mutagen.mp3 import MP3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

# Try importing premium TTS providers
try:
    from cartesia import Cartesia
    CARTESIA_AVAILABLE = True
except ImportError:
    CARTESIA_AVAILABLE = False

try:
    from elevenlabs import ElevenLabs, save
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False

def log_debug(phase: str, status: str, message: str) -> None:
    """Log debug messages with consistent formatting"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[NARRATED_SLIDESHOW] [{timestamp}] [{phase}] [{status}] {message}")

def ensure_audio_directory():
    """Ensure the audio directory exists"""
    # Make the path relative to the project root
    audio_dir = os.path.join(os.getcwd(), "data", "narrated_slideshow", "audio")
    os.makedirs(audio_dir, exist_ok=True)
    log_debug("TTS", "DEBUG", f"Audio directory: {audio_dir}")
    return audio_dir

def generate_audio_gtts(text: str, slide_number: int, language: str = 'en') -> Dict[str, Any]:
    """
    Generate audio file using Google Text-to-Speech
    
    Args:
        text: Text to convert to speech
        slide_number: Slide number for file naming
        language: Language code for TTS
        
    Returns:
        Dict with generation results
    """
    if not TTS_AVAILABLE:
        return {
            "success": False,
            "error": "TTS libraries not available. Please install gtts and pydub."
        }
    
    try:
        log_debug("TTS", "INFO", f"Generating audio for slide {slide_number}")
        
        # Create TTS object
        tts = gTTS(text=text, lang=language, slow=False)
        
        # Ensure audio directory exists
        audio_dir = ensure_audio_directory()
        
        # Generate filename
        filename = f"slide_{slide_number:03d}.mp3"
        filepath = os.path.join(audio_dir, filename)
        
        # Save audio file
        tts.save(filepath)
        
        # Get audio duration
        try:
            audio = MP3(filepath)
            duration = audio.info.length
            log_debug("TTS", "INFO", f"Audio generated for slide {slide_number}: {duration:.2f}s")
        except:
            duration = None
            log_debug("TTS", "WARNING", f"Could not determine duration for slide {slide_number}")
        
        return {
            "success": True,
            "filepath": filepath,
            "filename": filename,
            "duration": duration
        }
        
    except Exception as e:
        error_msg = f"Error generating audio for slide {slide_number}: {str(e)}"
        log_debug("TTS", "ERROR", error_msg)
        return {
            "success": False,
            "error": error_msg
        }

def generate_audio_cartesia(text: str, slide_number: int, api_key: str) -> Dict[str, Any]:
    """
    Generate audio file using Cartesia AI TTS
    
    Args:
        text: Text to convert to speech
        slide_number: Slide number for file naming
        api_key: Cartesia API key
        
    Returns:
        Dict with generation results
    """
    if not CARTESIA_AVAILABLE:
        return {
            "success": False,
            "error": "Cartesia library not available. Please install cartesia package."
        }
    
    try:
        log_debug("TTS", "INFO", f"Generating Cartesia audio for slide {slide_number}")
        
        # Initialize Cartesia client
        client = Cartesia(api_key=api_key)
        
        # Generate audio using Sonic voice (Cartesia's default high-quality voice)
        audio_generator = client.tts.bytes(
            model_id='sonic-2',
            transcript=text,
            voice={"mode": "id", "id": "6f84f4b8-58a2-430c-8c79-688dad597532"},  # Sonic voice ID
            output_format={"container": "wav", "encoding": "pcm_f32le", "sample_rate": 44100}
        )
        
        # Collect audio bytes from generator
        audio_bytes = b""
        for chunk in audio_generator:
            audio_bytes += chunk
        
        # Ensure audio directory exists
        audio_dir = ensure_audio_directory()
        
        # Generate filename
        filename = f"slide_{slide_number:03d}.wav"
        filepath = os.path.join(audio_dir, filename)
        
        # Save audio file
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
        
        # Get audio duration (approximate, since we can't easily get exact duration from raw bytes)
        try:
            audio = pydub.AudioSegment.from_wav(filepath)
            duration = len(audio) / 1000.0  # Convert from milliseconds to seconds
            log_debug("TTS", "INFO", f"Cartesia audio generated for slide {slide_number}: {duration:.2f}s")
        except:
            duration = None
            log_debug("TTS", "WARNING", f"Could not determine duration for slide {slide_number}")
        
        return {
            "success": True,
            "filepath": filepath,
            "filename": filename,
            "duration": duration
        }
        
    except Exception as e:
        error_msg = f"Error generating Cartesia audio for slide {slide_number}: {str(e)}"
        log_debug("TTS", "ERROR", error_msg)
        return {
            "success": False,
            "error": error_msg
        }

def generate_audio_elevenlabs(text: str, slide_number: int, api_key: str) -> Dict[str, Any]:
    """
    Generate audio file using ElevenLabs TTS
    
    Args:
        text: Text to convert to speech
        slide_number: Slide number for file naming
        api_key: ElevenLabs API key
        
    Returns:
        Dict with generation results
    """
    if not ELEVENLABS_AVAILABLE:
        return {
            "success": False,
            "error": "ElevenLabs library not available. Please install elevenlabs package."
        }
    
    try:
        log_debug("TTS", "INFO", f"Generating ElevenLabs audio for slide {slide_number}")
        
        # Initialize ElevenLabs client
        client = ElevenLabs(api_key=api_key)
        
        # Generate audio using Rachel voice with correct API method
        # Note: ElevenLabs API uses client.text_to_speech.convert(), not client.generate()
        audio = client.text_to_speech.convert(
            text=text,
            voice_id="21m00Tcm4TlvDq8ikWAM"  # Rachel voice ID
        )
        
        # Ensure audio directory exists
        audio_dir = ensure_audio_directory()
        
        # Generate filename
        filename = f"slide_{slide_number:03d}.mp3"
        filepath = os.path.join(audio_dir, filename)
        
        # Save audio file using ElevenLabs save function
        save(audio, filepath)
        
        # Get audio duration
        try:
            audio_file = MP3(filepath)
            duration = audio_file.info.length
            log_debug("TTS", "INFO", f"ElevenLabs audio generated for slide {slide_number}: {duration:.2f}s")
        except:
            duration = None
            log_debug("TTS", "WARNING", f"Could not determine duration for slide {slide_number}")
        
        return {
            "success": True,
            "filepath": filepath,
            "filename": filename,
            "duration": duration
        }
        
    except Exception as e:
        error_msg = f"Error generating ElevenLabs audio for slide {slide_number}: {str(e)}"
        log_debug("TTS", "ERROR", error_msg)
        return {
            "success": False,
            "error": error_msg
        }

def generate_audio_batch(narrations: Dict[int, Dict], tts_provider: str = "google", api_key: str = None, language: str = 'en') -> Dict[str, Any]:
    """
    Generate audio files for all narrations using the specified TTS provider
    
    Args:
        narrations: Dictionary of slide narrations
        tts_provider: TTS provider to use ("google", "cartesia", "elevenlabs")
        api_key: API key for premium providers
        language: Language code for TTS (used only for Google)
        
    Returns:
        Dict with batch generation results
    """
    provider_name = {
        "google": "Google TTS",
        "cartesia": "Cartesia AI", 
        "elevenlabs": "ElevenLabs"
    }.get(tts_provider, tts_provider)
    
    log_debug("TTS", "INFO", f"Starting batch audio generation for {len(narrations)} slides using {provider_name}")
    
    audio_files = {}
    errors = []
    total_duration = 0
    
    for slide_num, narration_data in narrations.items():
        if "narration_text" not in narration_data:
            errors.append(f"Slide {slide_num}: Missing narration text")
            continue
            
        # Choose the appropriate TTS function based on provider
        if tts_provider == "google":
            result = generate_audio_gtts(
                narration_data["narration_text"], 
                slide_num, 
                language
            )
        elif tts_provider == "cartesia":
            if not api_key:
                errors.append(f"Slide {slide_num}: Missing Cartesia API key")
                continue
            result = generate_audio_cartesia(
                narration_data["narration_text"],
                slide_num,
                api_key
            )
        elif tts_provider == "elevenlabs":
            if not api_key:
                errors.append(f"Slide {slide_num}: Missing ElevenLabs API key")
                continue
            result = generate_audio_elevenlabs(
                narration_data["narration_text"],
                slide_num,
                api_key
            )
        else:
            errors.append(f"Slide {slide_num}: Unsupported TTS provider '{tts_provider}'")
            continue
        
        if result["success"]:
            audio_files[slide_num] = result
            if result.get("duration"):
                total_duration += result["duration"]
        else:
            errors.append(f"Slide {slide_num}: {result['error']}")
    
    log_debug("TTS", "INFO", f"Batch audio generation complete using {provider_name}: {len(audio_files)} successful, {len(errors)} errors")
    log_debug("TTS", "INFO", f"Total audio duration: {total_duration:.2f} seconds")
    
    return {
        "success": len(audio_files) > 0,
        "audio_files": audio_files,
        "errors": errors,
        "total_processed": len(audio_files),
        "total_errors": len(errors),
        "total_duration": total_duration,
        "provider": provider_name
    }

def cleanup_audio_files(audio_files: Dict[int, Dict]) -> None:
    """
    Clean up generated audio files
    
    Args:
        audio_files: Dictionary of audio file information
    """
    log_debug("TTS", "INFO", "Cleaning up audio files")
    
    for slide_num, file_info in audio_files.items():
        try:
            if "filepath" in file_info and os.path.exists(file_info["filepath"]):
                os.remove(file_info["filepath"])
                log_debug("TTS", "INFO", f"Deleted audio file for slide {slide_num}")
        except Exception as e:
            log_debug("TTS", "WARNING", f"Could not delete audio file for slide {slide_num}: {str(e)}")

def get_available_providers() -> Dict[str, bool]:
    """
    Get information about available TTS providers
    
    Returns:
        Dict with provider availability
    """
    return {
        "google": TTS_AVAILABLE,
        "cartesia": CARTESIA_AVAILABLE,
        "elevenlabs": ELEVENLABS_AVAILABLE
    }
