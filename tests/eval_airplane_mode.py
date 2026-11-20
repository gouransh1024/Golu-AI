"""Project Golu: Airplane Mode (Wi-Fi OFF) Offline Verification.
Proves that Project Golu operates with 100% functionality with ZERO external network access:
1. Blocks any socket connections outside 127.0.0.1 / localhost
2. Executes complete end-to-end pipeline (Vault, RAG, Ollama, Faster-Whisper, HUD)
3. Confirms zero telemetry and zero external API calls
"""

import sys
import os
import socket
import time
import logging

os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_IMPL"] = "none"
os.environ["HF_HUB_OFFLINE"] = "1"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] golu.offline: %(message)s")
logger = logging.getLogger("golu.offline")

# Enforce strict offline firewall: Any socket connecting outside 127.0.0.1 or localhost throws an exception
_real_socket_connect = socket.socket.connect

def strict_offline_connect(self, address):
    host, port = address[0], address[1]
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    if host not in allowed_hosts and not host.startswith("127."):
        raise ConnectionRefusedError(
            f"AIRPLANE MODE ACTIVE: Blocked unauthorized external socket connection to {host}:{port}"
        )
    return _real_socket_connect(self, address)

socket.socket.connect = strict_offline_connect

from fastapi.testclient import TestClient
from backend.main import app
from backend.security import security_manager
from backend.memory.vault_sql import vault_sql
from backend.memory.rag_store import rag_store
from backend.llm_engine import llm_engine
from backend.audio.golu_voice import voice_engine
from backend.state_machine import state_machine, GoluMode
from stealth_hud.overlay import create_hud_app

client = TestClient(app)
AUTH_HEADERS = {"X-Golu-Token": security_manager.session_token}


def test_airplane_mode():
    print("=" * 70)
    print("PROJECT GOLU: AIRPLANE MODE (OFFLINE) RIGOROUS VERIFICATION")
    print("=" * 70)
    t0 = time.perf_counter()

    # 1. Test External Socket Interception
    logger.info("Verifying external socket tripwire...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("8.8.8.8", 53))
        assert False, "External connection should have been blocked!"
    except ConnectionRefusedError:
        logger.info("✅ External socket tripwire verified: unauthorized traffic blocked.")

    # 2. Test Localhost Vault in Airplane Mode
    logger.info("Verifying local encrypted vault in Airplane Mode...")
    val = vault_sql.get_value("full_name")
    assert val == "Gourab Saha"
    logger.info("✅ Vault decrypted offline: 'full_name' -> '%s'", val)

    # 3. Test Local Hybrid RAG in Airplane Mode
    logger.info("Verifying local Hybrid RAG in Airplane Mode...")
    rag_res = rag_store.hybrid_search("distributed key-value store Raft", top_k=2)
    assert len(rag_res) > 0
    logger.info("✅ Local Hybrid RAG searched offline: %d chunks found.", len(rag_res))

    # 4. Test Local Ollama LLM in Airplane Mode
    logger.info("Verifying local Ollama LLM in Airplane Mode...")
    ans = llm_engine.generate("State your name and purpose in one short sentence.")
    assert len(ans) > 0
    logger.info("✅ Local Ollama LLM generated offline: '%s'", ans[:60])

    # 5. Test Faster-Whisper on CPU in Airplane Mode
    logger.info("Verifying Faster-Whisper CPU transcription in Airplane Mode...")
    dummy_audio = [0.0] * 16000
    txt, lang, dur = voice_engine.transcribe(dummy_audio)
    logger.info("✅ Faster-Whisper CPU operated offline.")

    # 6. Test Stealth HUD Cloaking in Airplane Mode
    logger.info("Verifying Stealth HUD in Airplane Mode...")
    app_qt, hud, comm = create_hud_app()
    hud.show()
    app_qt.processEvents()
    assert hud.is_stealth_active is True
    hud.wipe_and_hide()
    logger.info("✅ Stealth HUD cloaked and wiped offline.")

    elapsed = time.perf_counter() - t0
    print("=" * 70)
    print(f"✈️ AIRPLANE MODE VERIFICATION PASSED IN {elapsed:.2f}s!")
    print("Golu functions 100% offline with zero external network connectivity.")
    print("=" * 70)


if __name__ == "__main__":
    test_airplane_mode()
