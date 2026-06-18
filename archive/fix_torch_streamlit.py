import sys
import types
from functools import wraps
import streamlit.web.bootstrap as bootstrap
from streamlit.web.bootstrap import run

def apply_torch_patch():
    """
    Apply a patch to torch._classes to prevent Streamlit file watcher from 
    raising errors when trying to access torch.classes.path
    """
    try:
        import torch 
        
        # Create a dummy path object to satisfy Streamlit's module inspection
        class DummyPath:
            def __init__(self):
                self._path = []
        
        # Create a wrapped _get_custom_class_python_wrapper function
        if hasattr(torch._C, '_get_custom_class_python_wrapper'):
            original_get_wrapper = torch._C._get_custom_class_python_wrapper
            
            @wraps(original_get_wrapper)
            def patched_get_wrapper(ns, attr):
                # If trying to access 'path' class, return our dummy
                if ns == 'path' and attr == 'path':
                    return DummyPath
                # Otherwise, call the original function
                return original_get_wrapper(ns, attr)
            
            # Apply the patch
            torch._C._get_custom_class_python_wrapper = patched_get_wrapper
            
            print("✅ Successfully applied torch._classes patch for Streamlit compatibility")
        else:
            print("⚠️ Could not find torch._C._get_custom_class_python_wrapper - patch not applied")
            
    except ImportError:
        print("⚠️ Could not import torch - patch not applied")
    except Exception as e:
        print(f"⚠️ Error applying torch patch: {str(e)}")

# Patch the main run function for Streamlit
original_run = bootstrap.run

@wraps(original_run)
def patched_run(main_script_path, command_line, args=None):
    """Run the Streamlit app after applying our patch"""
    apply_torch_patch()
    return original_run(main_script_path, command_line, args)

# Apply the patch to Streamlit's bootstrap
bootstrap.run = patched_run

if __name__ == "__main__":
    # When this file is run directly with streamlit run,
    # it will apply the patch then execute the actual app.py
    import os
    
    # Get path to app.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, "app.py")
    
    # Check if app.py exists
    if not os.path.exists(app_path):
        print(f"❌ Error: Cannot find {app_path}")
        sys.exit(1)
        
    # This will execute the app with our patch applied
    # The patch will have already been applied to streamlit.bootstrap.run
    sys.argv = ["streamlit", "run", app_path]
    sys.exit(0) 