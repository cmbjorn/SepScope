"""
SepScope launcher — double-click or run: python launch.py
Creates a virtual environment and installs dependencies on first run.
"""
import os, sys, subprocess, time, webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

VENV = os.path.join(ROOT, ".venv")
PYTHON = os.path.join(VENV, "Scripts" if sys.platform == "win32" else "bin",
                      "python.exe" if sys.platform == "win32" else "python")
PIP    = os.path.join(VENV, "Scripts" if sys.platform == "win32" else "bin",
                      "pip.exe"    if sys.platform == "win32" else "pip")

URL = "http://127.0.0.1:8502"

if not os.path.exists(PYTHON):
    print("No virtual environment found — running first-time setup...")
    subprocess.check_call([sys.executable, "-m", "venv", VENV])
    print("Installing dependencies (this takes a minute the first time)...")
    subprocess.check_call([PIP, "install", "-r", "requirements.txt"])
    print("Setup complete.\n")

print(f"Starting SepScope at {URL}")
print("Close this window or press Ctrl+C to stop.\n")

proc = subprocess.Popen([
    PYTHON, "-m", "streamlit", "run", "app.py",
    "--server.address=127.0.0.1",
    "--server.port=8502",
    "--server.headless=true",
])
time.sleep(5)
webbrowser.open(URL)

try:
    proc.wait()
except KeyboardInterrupt:
    proc.terminate()
