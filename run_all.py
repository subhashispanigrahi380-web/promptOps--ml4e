import subprocess
import time
import sys

def main():
    print("Starting PromptOps Backend API (FastAPI) on port 8000...")
    api_process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"])
    
    time.sleep(2) # Give API a moment to start
    
    print("Starting PromptOps UI (Streamlit)...")
    ui_process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/ui.py"])
    
    try:
        api_process.wait()
        ui_process.wait()
    except KeyboardInterrupt:
        print("Shutting down...")
        api_process.terminate()
        ui_process.terminate()

if __name__ == "__main__":
    main()
