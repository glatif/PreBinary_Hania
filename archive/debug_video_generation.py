#!/usr/bin/env python3
"""
Debug script for video generation issues
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, '/Users/macbook/Documents/MyProjects/UReap/AI_Instructor/src')

def test_video_generation_debug():
    """Test video generation with mock data to debug the issue"""
    try:
        from features.narrated_slideshow.video_generator import (
            generate_slideshow_video,
            create_placeholder_image,
            validate_slideshow_data
        )
        
        # Create mock slide images
        slide_images = {
            1: create_placeholder_image(text="Test Slide 1"),
            2: create_placeholder_image(text="Test Slide 2")
        }
        
        # Create mock audio files (we need actual files)
        # For this test, let's check if the validation finds the issue
        audio_files = {
            1: {"filepath": "/path/to/nonexistent/audio1.mp3", "duration": 5.0},
            2: {"filepath": "/path/to/nonexistent/audio2.mp3", "duration": 3.0}
        }
        
        narrations = {
            1: {"narration_text": "This is slide 1"},
            2: {"narration_text": "This is slide 2"}
        }
        
        print("🔍 Testing validation first...")
        validation = validate_slideshow_data(slide_images, audio_files, narrations)
        print(f"Validation result: {validation}")
        
        if not validation["valid"]:
            print("❌ Validation failed as expected (audio files don't exist)")
            print("Issues:", validation["issues"])
            print("Warnings:", validation["warnings"])
            return True
        
        print("🎬 Attempting video generation (this should fail gracefully)...")
        
        def progress_callback(progress, status):
            print(f"Progress: {progress*100:.1f}% - {status}")
        
        result = generate_slideshow_video(
            slide_images=slide_images,
            audio_files=audio_files,
            narrations=narrations,
            progress_callback=progress_callback
        )
        
        print(f"Result: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during debug test: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_image_creation():
    """Test just the image creation part"""
    try:
        from features.narrated_slideshow.video_generator import create_placeholder_image
        
        print("🖼️ Testing placeholder image creation...")
        img_bytes = create_placeholder_image(text="Debug Test")
        print(f"✅ Created image: {len(img_bytes)} bytes")
        
        # Test if we can validate it
        from PIL import Image as PILImage
        from io import BytesIO
        
        img = PILImage.open(BytesIO(img_bytes))
        print(f"✅ Image validation successful: {img.format} {img.size} {img.mode}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during image test: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Run debug tests"""
    print("🐛 Video Generation Debug Tests")
    print("=" * 50)
    
    tests = [
        ("Image Creation Test", test_image_creation),
        ("Video Generation Debug", test_video_generation_debug)
    ]
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running: {test_name}")
        print("-" * 30)
        try:
            result = test_func()
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {test_name}")
        except Exception as e:
            print(f"❌ FAIL: {test_name} - {e}")

if __name__ == "__main__":
    main()
