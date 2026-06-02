import sys
import os
import subprocess
import time
import httpx
import sqlite3
import socket

# Ensure desktop is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop.app import MnemoApp
from desktop.client import MnemoClient

def get_api_key():
    # Attempt to read from backend/data/mnemo.db directly
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "data", "mnemo.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'api_key'")
            row = cursor.fetchone()
            conn.close()
            if row:
                val = row[0]
                try:
                    from backend.app.core.security import decrypt_value
                    val = decrypt_value(val)
                except Exception as e:
                    print(f"Failed to decrypt API key: {e}")
                return val
        except Exception as e:
            print(f"Failed to read API key from DB: {e}")
            
    # Try reading from backend/.env
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("MNEMO_API_KEY="):
                        key = line.strip().split("=", 1)[1]
                        if key:
                            return key
        except Exception as e:
            pass
    return ""

def main():
    # DPI Awareness
    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
            
    # Port Auto-Discovery (8765-8770)
    def find_free_port(start_port=8765, max_port=8770):
        for port in range(start_port, max_port + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        return start_port # fallback to default if all seemingly taken

    target_port = find_free_port()
    base_url = f"http://127.0.0.1:{target_port}/api/v1"
    
    # Check if backend is already running on any of the standard ports
    is_running = False
    for port in range(8765, 8771):
        try:
            res = httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=0.5)
            if res.status_code == 200:
                is_running = True
                base_url = f"http://127.0.0.1:{port}/api/v1"
                target_port = port
                break
        except httpx.RequestError:
            pass
        
    backend_process = None
    if not is_running:
        print("Backend not running. Starting backend...")
        backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
        
        # We need to run uvicorn. It might be available in the venv.
        # Since desktop and backend share the same environment for this MVP:
        python_exec = sys.executable
        
        backend_process = subprocess.Popen(
            [python_exec, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(target_port)],
            cwd=backend_dir
        )
        
        # Wait for it to start
        for _ in range(15):
            time.sleep(1)
            try:
                res = httpx.get(f"{base_url}/health", timeout=1.0)
                if res.status_code == 200:
                    is_running = True
                    break
            except httpx.RequestError:
                pass
                
        if not is_running:
            print("Failed to start backend. Check logs.")
            # If backend fails, we should still open the UI, it'll just show disconnected status
        else:
            print("Backend started successfully.")

    api_key = get_api_key()
    
    client = MnemoClient(base_url, api_key)
    
    app = MnemoApp(client)
    app.mainloop()
    
    if backend_process:
        print("Terminating backend process...")
        backend_process.terminate()

if __name__ == "__main__":
    main()
