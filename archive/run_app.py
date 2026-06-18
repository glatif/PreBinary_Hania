#!/usr/bin/env python
"""
Simple script to fix the torch._classes path issue in Streamlit
"""
import sys
import os
import importlib
import types
from functools import wraps

def fix_torch_path_issue():
    """
    Fix the torch._classes.path issue by monkey patching
    torch._C._get_custom_class_python_wrapper
    """
    try:
        # Import torch
        import torch
        
        # Create a dummy path class
        class DummyPath:
            _path = []
        
        dummy_path_instance = DummyPath()
        
        # Create a patch for torch._C._get_custom_class_python_wrapper
        original_get_wrapper = torch._C._get_custom_class_python_wrapper
        
        @wraps(original_get_wrapper)
        def patched_get_wrapper(ns, attr):
            # Return our dummy for 'path.path'
            if ns == 'path' and attr == 'path':
                return DummyPath
            # Otherwise use original implementation
            return original_get_wrapper(ns, attr)
        
        # Apply the patch
        torch._C._get_custom_class_python_wrapper = patched_get_wrapper
        
        print("✅ Successfully applied torch._classes patch for Streamlit compatibility")
        return True
    except Exception as e:
        print(f"⚠️ Error applying torch patch: {str(e)}")
        return False

if __name__ == "__main__":
    # Apply the patch
    success = fix_torch_path_issue()
    
    if not success:
        print("❌ Failed to apply patch, but continuing anyway...")
    
    # Run the Streamlit app
    import subprocess
    
    # Get the path to app.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, "app.py")
    
    # Run streamlit with our app
    cmd = [sys.executable, "-m", "streamlit", "run", app_path]
    
    try:
        # Execute streamlit with the app
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n🛑 Streamlit app stopped")
    except Exception as e:
        print(f"❌ Error running Streamlit: {str(e)}")
        sys.exit(1) 