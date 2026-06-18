import os
import sys
import importlib
from functools import wraps
from huggingface_hub import hf_hub_download

# Create a compatbility wrapper for cached_download
def cached_download_wrapper(*args, **kwargs):
    """
    Compatibility wrapper to make hf_hub_download work like cached_download
    """
    # Extract arguments from kwargs that would be used by cached_download
    repo_id = kwargs.get('repo_id', 'sentence-transformers')
    filename = kwargs.get('filename', '')
    
    # Remove repo_id and filename if they are in kwargs to avoid duplication
    kwargs_copy = kwargs.copy()
    if 'repo_id' in kwargs_copy:
        del kwargs_copy['repo_id']
    if 'filename' in kwargs_copy:
        del kwargs_copy['filename']
    
    # Call hf_hub_download with the correct arguments
    return hf_hub_download(repo_id=repo_id, filename=filename, **kwargs_copy)

# Add the cached_download function to the huggingface_hub module
def apply_patch():
    """
    Add a cached_download function to the huggingface_hub module
    """
    try:
        import huggingface_hub
        
        # Check if cached_download is already defined
        if not hasattr(huggingface_hub, 'cached_download'):
            # Add the cached_download function to the huggingface_hub module
            huggingface_hub.cached_download = cached_download_wrapper
            
            # Make it available in the __init__ module
            if '__init__' in dir(huggingface_hub):
                huggingface_hub.__init__.cached_download = cached_download_wrapper
                
        print("✅ Added cached_download compatibility function to huggingface_hub")
    except Exception as e:
        print(f"❌ Error applying huggingface_hub patch: {str(e)}")

# Apply the patch when this module is imported
apply_patch() 