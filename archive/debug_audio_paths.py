#!/usr/bin/env python3
"""
Test audio file paths from TTS engine
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, '/Users/macbook/Documents/MyProjects/UReap/AI_Instructor/src')

def test_audio_paths():
    """Test the audio file path generation"""
    try:
        from features.narrated_slideshow.tts_engine import ensure_audio_directory
        
        print("🔊 Testing audio directory setup...")
        audio_dir = ensure_audio_directory()
        print(f"Audio directory: {audio_dir}")
        print(f"Directory exists: {os.path.exists(audio_dir)}")
        
        # Test what a typical audio filepath would look like
        test_filepath = os.path.join(audio_dir, "slide_001.mp3")
        print(f"Example audio filepath: {test_filepath}")
        print(f"Example file exists: {os.path.exists(test_filepath)}")
        
        # Check current working directory
        print(f"Current working directory: {os.getcwd()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def check_existing_audio_files():
    """Check if there are any existing audio files"""
    try:
        from features.narrated_slideshow.tts_engine import ensure_audio_directory
        
        audio_dir = ensure_audio_directory()
        print(f"🔍 Checking for existing audio files in: {audio_dir}")
        
        if os.path.exists(audio_dir):
            files = os.listdir(audio_dir)
            audio_files = [f for f in files if f.endswith('.mp3') or f.endswith('.wav')]
            
            print(f"Found {len(audio_files)} audio files:")
            for file in audio_files:
                full_path = os.path.join(audio_dir, file)
                size = os.path.getsize(full_path)
                print(f"  {file} ({size} bytes)")
                
            return len(audio_files) > 0
        else:
            print("Audio directory doesn't exist yet")
            return False
        
    except Exception as e:
        print(f"❌ Error checking audio files: {e}")
        return False

def main():
    """Run audio path tests"""
    print("🎵 Audio Path Debug Tests")
    print("=" * 50)
    
    test_audio_paths()
    print()
    check_existing_audio_files()

if __name__ == "__main__":
    main()
