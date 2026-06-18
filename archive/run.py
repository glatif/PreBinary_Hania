#!/usr/bin/env python
import sys
import os
import subprocess

def main():
    """
    Run the Streamlit app with the torch patch applied
    """
    # Get the absolute path of the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the fix_torch_streamlit.py file
    fix_script = os.path.join(script_dir, "fix_torch_streamlit.py")
    
    print("🚀 Starting Streamlit app with torch patch...")
    
    # Run streamlit with our patched script
    cmd = [sys.executable, "-m", "streamlit", "run", fix_script]
    
    try:
        # Execute the command
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running Streamlit: {str(e)}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Streamlit app stopped by user")
    
if __name__ == "__main__":
    main() 