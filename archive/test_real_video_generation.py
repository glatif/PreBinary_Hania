#!/usr/bin/env python3
"""
Test video generation with real audio files
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, '/Users/macbook/Documents/MyProjects/UReap/AI_Instructor/src')

def test_real_video_generation():
    """Test video generation with actual audio files that exist"""
    try:
        from features.narrated_slideshow.video_generator import (
            generate_slideshow_video,
            create_placeholder_image
        )
        from features.narrated_slideshow.tts_engine import ensure_audio_directory
        
        # Get the audio directory
        audio_dir = ensure_audio_directory()
        
        # Create mock data using actual audio files
        slide_images = {
            1: create_placeholder_image(text="Test Slide 1"),
            2: create_placeholder_image(text="Test Slide 2")
        }
        
        # Use the actual audio files that exist
        audio_files = {
            1: {
                "filepath": os.path.join(audio_dir, "slide_001.mp3"),
                "duration": 5.0,
                "filename": "slide_001.mp3"
            },
            2: {
                "filepath": os.path.join(audio_dir, "slide_002.mp3"), 
                "duration": 3.0,
                "filename": "slide_002.mp3"
            }
        }
        
        narrations = {
            1: {"narration_text": "This is slide 1"},
            2: {"narration_text": "This is slide 2"}
        }
        
        print("🎬 Testing video generation with real audio files...")
        print(f"Audio file 1: {audio_files[1]['filepath']}")
        print(f"Audio file 1 exists: {os.path.exists(audio_files[1]['filepath'])}")
        print(f"Audio file 2: {audio_files[2]['filepath']}")
        print(f"Audio file 2 exists: {os.path.exists(audio_files[2]['filepath'])}")
        
        def progress_callback(progress, status):
            print(f"Progress: {progress*100:.1f}% - {status}")
        
        result = generate_slideshow_video(
            slide_images=slide_images,
            audio_files=audio_files,
            narrations=narrations,
            progress_callback=progress_callback
        )
        
        print("\n" + "="*50)
        print("🎯 VIDEO GENERATION RESULT:")
        print(f"Success: {result.get('success', False)}")
        
        if result.get('success'):
            print(f"Output path: {result.get('output_path')}")
            print(f"File size: {result.get('file_size_mb', 0):.1f} MB")
            print(f"Duration: {result.get('duration_seconds', 0):.1f}s")
            if os.path.exists(result.get('output_path', '')):
                print("✅ Video file exists!")
            else:
                print("❌ Video file was not created")
        else:
            print(f"Error: {result.get('error')}")
            if result.get('errors'):
                print("Detailed errors:")
                for error in result['errors']:
                    print(f"  - {error}")
        
        if result.get('warnings'):
            print("Warnings:")
            for warning in result['warnings']:
                print(f"  - {warning}")
        
        return result.get('success', False)
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Run the real video generation test"""
    print("🎬 Real Video Generation Test")
    print("=" * 50)
    
    success = test_real_video_generation()
    
    print("\n" + "="*50)
    if success:
        print("🎉 Test completed successfully!")
    else:
        print("❌ Test failed - check the errors above")

if __name__ == "__main__":
    main()
