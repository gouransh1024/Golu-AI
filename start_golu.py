"""Project Golu: Production One-Click Orchestration Launcher.
Coordinates all local AI subsystems into a single cohesive runtime:
1. Ollama Daemon (127.0.0.1:11434)
2. Sub-second Model Pre-Warming & VRAM Pinning
3. Secure FastAPI Orchestrator (127.0.0.1:8000)
4. Floating Siri-like Voice Assistant HUD (PyQt6 glassmorphic window)
5. Invisible Meeting Co-Pilot HUD (PyQt6 with WDA_EXCLUDEFROMCAPTURE)
6. Global Hotkey State Manager ([Ctrl+Alt+A/M/H/X])
7. Automatic Dashboard Browser Opener (http://127.0.0.1:8000/dashboard)
"""

import os
import sys
import time
import signal
import logging
import threading
import subprocess
import webbrowser
import uvicorn

# Offline & telemetry blocking flags
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_IMPL"] = "none"
os.environ["HF_HUB_OFFLINE"] = "1"

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] golu.launcher: %(message)s")
logger = logging.getLogger("golu.launcher")

from backend.llm_engine import llm_engine
from backend.state_machine import state_machine, GoluMode
from warmup import run_full_warmup


def ensure_ollama_daemon():
    """Checks if Ollama is running; if not, starts the daemon."""
    if not llm_engine.is_ollama_available():
        logger.info("Ollama daemon not detected on 127.0.0.1:11434. Starting Ollama in background...")
        ollama_bin = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        if os.path.exists(ollama_bin):
            subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
        else:
            logger.warning("Ollama executable not found at %s. Ensure ollama serve is running.", ollama_bin)
    else:
        logger.info("Ollama daemon is active on 127.0.0.1:11434.")


def start_fastapi_thread() -> uvicorn.Server:
    """Runs FastAPI orchestrator on 127.0.0.1:8000 in a background daemon thread."""
    logger.info("Starting Project Golu Secure Orchestrator on http://127.0.0.1:8000...")
    config = uvicorn.Config(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    api_thread = threading.Thread(target=server.run, daemon=True)
    api_thread.start()
    return server


def open_dashboard_in_browser():
    """Automatically opens the executive metrics dashboard in the default browser."""
    time.sleep(1.2)
    logger.info("Opening Project Golu Executive Dashboard at http://127.0.0.1:8000/dashboard ...")
    try:
        webbrowser.open("http://127.0.0.1:8000/dashboard")
    except Exception as e:
        logger.debug("Browser open note: %s", e)


def main():
    print("""
    ==================================================================
        PROJECT GOLU: ZERO-CLOUD LOCAL AI ORCHESTRATOR (4GB VRAM)
    ==================================================================
      Target Hardware : NVIDIA GeForce GTX 1650 (4096 MB VRAM)
      Localhost API   : http://127.0.0.1:8000
      Web Dashboard   : http://127.0.0.1:8000/dashboard
      Hotkeys:
        [Ctrl + Alt + A] : Assistant Mode (Floating Siri HUD + Mic)
        [Ctrl + Alt + M] : Meeting Mode (Hard-Muted TTS + Stealth HUD)
        [Ctrl + Alt + H] : Hide / Reveal Stealth HUD
        [Ctrl + Alt + X] : Emergency Hardware Kill Switch (<50ms)
    ==================================================================
    """)

    # 1. Check Ollama
    ensure_ollama_daemon()

    # 2. Pre-warm AI Models & VRAM
    run_full_warmup()

    # 3. Start Background FastAPI Server
    api_server = start_fastapi_thread()

    # 4. Open Web Dashboard in default browser
    threading.Thread(target=open_dashboard_in_browser, daemon=True).start()

    # 5. Start Global Hotkey Listener & Live Mic Assistant
    state_machine.start_hotkey_listener()
    state_machine.transition_to(GoluMode.ASSISTANT)

    # Play startup confirmation sound
    from backend.audio.golu_voice import voice_engine
    voice_engine.speak("Haan bhai, bolo!")
    logger.info("Project Golu Voice Engine active and listening for 'Hey Golu' or [Ctrl+Alt+A].")

    # 6. Launch Floating Siri HUD GUI on main thread (with fallback for headless environments)
    try:
        from PyQt6.QtWidgets import QApplication
        from stealth_hud.siri_hud import FloatingSiriHUD, siri_communicator

        app = QApplication(sys.argv)
        siri_hud = FloatingSiriHUD(siri_communicator)
        siri_hud.show()
        logger.info("Floating Siri-like HUD window launched and visible on screen.")

        # Run Qt Event Loop on main thread
        app.exec()
    except Exception as e:
        logger.info("GUI event loop notice: %s. Running in terminal server mode.", e)
        # Fallback loop if headless
        try:
            while True:
                time.sleep(1.0)
        except (KeyboardInterrupt, SystemExit):
            pass
    finally:
        logger.info("Shutting down Project Golu gracefully...")
        state_machine.transition_to(GoluMode.KILL)
        state_machine.stop_hotkey_listener()
        logger.info("All handles released. Golu stopped cleanly.")


if __name__ == "__main__":
    main()
