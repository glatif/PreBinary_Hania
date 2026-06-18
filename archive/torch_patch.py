"""
Patch for fixing torch._classes.path issue with Streamlit.

Import this module at the top of your Streamlit app to fix
the path issue with torch._classes.
"""
import types
from functools import wraps
import os

# Apply patch automatically when module is imported
try:
    import torch
    
    # Create a dummy path class
    class DummyPath:
        _path = []
    
    # Add the dummy path to torch._classes
    if not hasattr(torch._classes, '__path__'):
        torch._classes.__path__ = DummyPath()
    
    # Patch the getattr method of torch._classes
    original_getattr = torch._classes.__getattr__
    
    @wraps(original_getattr)
    def patched_getattr(self, attr):
        if attr == '__path__':
            return DummyPath()
        try:
            return original_getattr(self, attr)
        except RuntimeError as e:
            if '__path__._path' in str(e):
                return DummyPath()
            raise
    
    torch._classes.__getattr__ = patched_getattr
    
    # Create a patch for torch._C._get_custom_class_python_wrapper
    if hasattr(torch._C, '_get_custom_class_python_wrapper'):
        original_get_wrapper = torch._C._get_custom_class_python_wrapper
        
        @wraps(original_get_wrapper)
        def patched_get_wrapper(ns, attr):
            # Special handling for problematic attributes
            if (ns == '__path__' and attr == '_path') or (ns == 'path' and attr == 'path'):
                return DummyPath
            
            # Otherwise use original implementation with error handling
            try:
                return original_get_wrapper(ns, attr)
            except RuntimeError as e:
                if 'does not exist' in str(e):
                    return DummyPath
                raise
        
        # Apply the patch
        torch._C._get_custom_class_python_wrapper = patched_get_wrapper
        
        # Print success message (only if not in Streamlit headless mode)
        if not os.environ.get('STREAMLIT_HEADLESS'):
            print("✅ torch._classes.path patch applied")
    else:
        # Print warning (only if not in Streamlit headless mode)
        if not os.environ.get('STREAMLIT_HEADLESS'):
            print("⚠️ Could not find torch._C._get_custom_class_python_wrapper - patch not applied")
except ImportError:
    # Print warning (only if not in Streamlit headless mode)
    if not os.environ.get('STREAMLIT_HEADLESS', False):
        print("⚠️ Could not import torch - patch not applied")
except Exception as e:
    # Print error (only if not in Streamlit headless mode)
    if not os.environ.get('STREAMLIT_HEADLESS', False):
        print(f"⚠️ Error applying torch patch: {str(e)}") 