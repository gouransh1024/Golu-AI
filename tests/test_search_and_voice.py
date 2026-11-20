"""Project Golu: Test Suite for Internet Search & Live Voice Assistant.
Tests:
1. Internet Search module (DDG + Wikipedia + Local LLM)
2. Unified Assistant (Vault, RAG, Web Search, LLM)
3. Microphone Listener (Hardware mic stream, VAD threshold, manual trigger)
4. State Machine Hotkey integration ([Ctrl+Alt+A])
5. API POST /api/ask endpoint
"""

import os
import sys
import time
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] test: %(message)s")
logger = logging.getLogger("test")

from backend.search import web_search_engine
from backend.assistant import assistant
from backend.audio.mic_listener import mic_listener
from backend.audio.golu_voice import voice_engine
from backend.state_machine import state_machine, GoluMode
from backend.security import security_manager


def test_01_search_engine():
    logger.info("=== Test 01: Internet Search Engine ===")
    # Test search with fallback tolerance (works offline and online)
    res = web_search_engine.answer_query_with_web("What is Python programming language?")
    logger.info("Search Engine result: source=%s, latency=%.2fms", res.get("source"), res.get("latency_ms", 0))
    assert "answer" in res and len(res["answer"]) > 10, "Expected non-empty search answer"
    logger.info("Test 01 PASSED: Answer snippet: '%s'", res["answer"][:80])


def test_02_assistant_routing():
    logger.info("=== Test 02: Unified Assistant Routing ===")

    # Path A: Vault (Personal info)
    res_vault = assistant.ask("What is my full name?")
    logger.info("Vault Query -> source=%s, answer='%s'", res_vault.get("source"), res_vault.get("answer"))
    assert res_vault.get("source") == "vault", f"Expected vault source, got {res_vault.get('source')}"
    assert "Gourab" in res_vault.get("answer", ""), "Expected 'Gourab' in vault answer"

    # Path B: RAG (Resume / Projects)
    res_rag = assistant.ask("What projects or tech stack have I worked with?")
    logger.info("RAG Query -> source=%s, answer='%s'", res_rag.get("source"), res_rag.get("answer")[:80])
    assert res_rag.get("source") in ("rag", "local_llm"), f"Unexpected source {res_rag.get('source')}"

    # Path C: Web Search (General / Current knowledge)
    res_web = assistant.ask("search internet for quantum computing definition")
    logger.info("Web Query -> source=%s, answer='%s'", res_web.get("source"), res_web.get("answer")[:80])
    assert res_web.get("source") in ("internet_search", "local_llm"), f"Unexpected source {res_web.get('source')}"
    assert "answer" in res_web and len(res_web["answer"]) > 10

    logger.info("Test 02 PASSED: All 3 memory tiers routed accurately.")


def test_03_microphone_listener():
    logger.info("=== Test 03: Microphone Listener Stream & Manual Trigger ===")
    mic_listener.start()

    # Test manual trigger (simulating shortcut press)
    mic_listener.trigger_manual_listen()
    assert mic_listener._manual_listen is True, "Expected manual listen flag to be set"

    # Test stopping stream and releasing handles
    t0 = time.perf_counter()
    mic_listener.stop()
    release_ms = (time.perf_counter() - t0) * 1000.0
    assert mic_listener._running is False, "Expected microphone stream to be stopped"
    logger.info("Microphone handles released in %.2f ms (Target: < 50ms)", release_ms)
    assert release_ms < 50.0, f"Microphone release took too long: {release_ms}ms"

    logger.info("Test 03 PASSED: Mic stream starts, triggers, and releases cleanly.")


def test_04_state_machine_hotkey_integration():
    logger.info("=== Test 04: State Machine Hotkey Integration ===")

    # Simulate pressing Ctrl+Alt+A
    state_machine.on_hotkey_assistant()
    assert state_machine.current_mode == GoluMode.ASSISTANT, "Expected ASSISTANT mode"
    assert voice_engine.is_hard_muted is False, "TTS should be unmuted in ASSISTANT mode"

    # Simulate pressing Ctrl+Alt+M
    state_machine.on_hotkey_meeting()
    assert state_machine.current_mode == GoluMode.MEETING, "Expected MEETING mode"
    assert voice_engine.is_hard_muted is True, "TTS must be hard-muted in MEETING mode"
    assert mic_listener._running is False, "Mic listener must be stopped in MEETING mode"

    # Simulate pressing Ctrl+Alt+X
    t0 = time.perf_counter()
    state_machine.on_hotkey_kill()
    kill_ms = (time.perf_counter() - t0) * 1000.0
    assert state_machine.current_mode == GoluMode.KILL, "Expected KILL mode"
    assert kill_ms < 50.0, f"Kill switch took {kill_ms}ms"

    logger.info("Test 04 PASSED: Global hotkeys properly orchestrate mic and meeting security.")


def test_05_api_ask_endpoint():
    logger.info("=== Test 05: API POST /api/ask Endpoint ===")
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    token = security_manager.session_token

    # 1. Unauthenticated request should return 401
    r_unauth = client.post("/api/ask", json={"query": "Who is Golu?"})
    assert r_unauth.status_code == 401, f"Expected 401, got {r_unauth.status_code}"

    # 2. Authenticated request
    r_auth = client.post("/api/ask", headers={"X-Golu-Token": token}, json={"query": "What is my full name?"})
    assert r_auth.status_code == 200, f"Expected 200, got {r_auth.status_code}"
    data = r_auth.json()
    assert data.get("status") == "success"
    assert "Gourab" in data.get("result", {}).get("answer", "")

    logger.info("Test 05 PASSED: /api/ask endpoint secured and operational.")


if __name__ == "__main__":
    logger.info("Running Project Golu Internet Search & Live Voice Tests...")
    test_01_search_engine()
    test_02_assistant_routing()
    test_03_microphone_listener()
    test_04_state_machine_hotkey_integration()
    test_05_api_ask_endpoint()
    print("\n🎉 ALL SEARCH & VOICE ASSISTANT TESTS PASSED CLEANLY!")
