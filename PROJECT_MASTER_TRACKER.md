# Project Golu: Master Architecture & Daily Progress Tracker (4GB VRAM Edition)

> **Zero-Cloud, Local Client-Server AI System**
> Production Orchestrator: `127.0.0.1:8000` | Target GPU: NVIDIA GeForce GTX 1650 (4096 MiB VRAM)

---

## 📊 4-Day Execution Plan & Milestone Progress

| Stage | Milestone | Target Deliverables | Mandatory Exit Gate Status |
|---|---|---|---|
| **Day 1** (Today) | **0% → 25%** | **Brain, Security & Memory Subsystems**<br>• Python 3.13 environment + dependencies<br>• `backend/security.py` (DPAPI + AES-256 + X-Golu-Token + XML Injection Firewall)<br>• `backend/memory/vault_sql.py` (Encrypted SQLite + RapidFuzz + In-Memory Cache)<br>• `backend/memory/rag_store.py` (ChromaDB + BM25 RRF + Zero-Cloud Embedding)<br>• `backend/memory/ingest.py` (Semantic chunker + Gourab's verified resume profile)<br>• `backend/llm_engine.py` (Ollama client + VRAM Watchdog + Grounded fallback)<br>• `backend/router.py` (Dual-Memory Confidence Router + Regex Guard + Length Enforcer)<br>• `backend/main.py` (FastAPI orchestrator on `127.0.0.1:8000` + Token Auth)<br>• `tests/eval_benchmark.py` (Complete Exit Gate Test Suite) | ✅ **PASSED (100%)**<br>• Peak VRAM: 111.0 MB / 4096 MB (≤ 3.5 GB)<br>• Vault Latency: **3.81 ms** (Target: < 20 ms)<br>• Unauthenticated requests: **401 Unauthorized**<br>• Grounded RAG accuracy: **100% facts verified**<br>• Deny-List & Injection Firewall: **100% blocked** |
| **Day 2** (Tomorrow) | **25% → 50%** | **Universal Form & Desktop Automation Engine**<br>• Manifest V3 Extension (`manifest.json`, `background.js`, `content.js`)<br>• Floating Tab suggestion pill UI with native React/Vue/Angular dispatch<br>• Batch full-form autofill WebSocket (`/ws/browser`) with green preview highlight<br>• Active Learning Toast ("Save to Golu's encrypted vault?")<br>• Tier 2 Desktop Accessibility Engine (`backend/automation/desktop_uia.py`)<br>• Tier 3 Constrained Vision Fallback (`backend/automation/vision_fallback.py`) | ⏳ *Scheduled for Day 2* |
| **Day 3** | **50% → 75%** | **Voice Persona & Undetectable Meeting Co-Pilot**<br>• Hinglish Voice Engine (`backend/audio/golu_voice.py`)<br>• Silero VAD + Faster-Whisper (small int8 on CPU) + Kokoro-82M TTS<br>• Sub-100ms instant reaction audio clips ("Haan bhai, bolo?")<br>• WASAPI Loopback listener (`backend/audio/loopback_listener.py`)<br>• Stealth PyQt6 HUD (`stealth_hud/overlay.py`) with `WDA_EXCLUDEFROMCAPTURE`<br>• Global FSM Hotkey State Manager (`backend/state_machine.py`) | ⏳ *Scheduled for Day 3* |
| **Day 4** | **75% → 100%** | **Integration, Exhibition Proof & Offline Demo**<br>• One-click launcher (`start_golu.bat`) and pre-warming (`warmup.py`)<br>• End-to-end 50-field real-world evaluation benchmark<br>• Airplane Mode (Wi-Fi OFF) verification rehearsal<br>• Hardware Kill Switch (`Ctrl+Alt+X`) < 50ms test<br>• Live Judge Metrics Readout card | ⏳ *Scheduled for Day 4* |

---

## 🔒 Security Architecture Verified on Day 1

1. **Localhost Socket Isolation**:
   - Orchestrator binds strictly to `127.0.0.1:8000` (refuses `0.0.0.0`).
   - CORS strictly restricted to `chrome-extension://*` and `http://127.0.0.1:8000`.
2. **Rotating Session Secret (`X-Golu-Token`)**:
   - 256-bit cryptographic token stored in `data/.session_token`.
   - Verified via constant-time comparison (`secrets.compare_digest`).
   - All protected endpoints return `401 Unauthorized` if token is absent or invalid.
3. **AES-256 (Fernet) Encryption**:
   - Master key managed via Windows DPAPI Credential Manager (service: `golu_ai`, user: `master_vault_key`).
   - Cryptographic fallback persisted in secure local keyfile.
4. **Prompt-Injection Firewall**:
   - Wraps inputs in `<untrusted_input>...</untrusted_input>`.
   - Sanitizes and neutralizes injection vectors (`ignore previous instructions`, `dump vault`, `<script>`, `dan mode`).
5. **Sensitive Field Deny-List**:
   - Completely ignores and denies requests for `password`, `otp`, `cvv`, `pin`, `aadhaar`, `pan_card`, and financial attributes.

---

## ⚡ Performance Benchmark Readout (Measured Day 1)

```text
======================================================================
PROJECT GOLU: DAY 1 MANDATORY EXIT GATE EVALUATION BENCHMARK
======================================================================
Test 01: Unauthenticated request security test         -> PASSED (401 Unauthorized)
Test 02: Vault sub-20ms latency benchmark             -> PASSED (Avg: 3.81ms, Max: 4.59ms)
Test 03: Hybrid RAG factual grounding test            -> PASSED (100% factual, zero hallucination)
Test 04: Sensitive field deny-list test               -> PASSED (100% blocked)
Test 05: Prompt-injection firewall test               -> PASSED (All injections neutralized)
Test 06: Active learning loop test                    -> PASSED (Instant commit & recall)
Test 07: VRAM Watchdog & system health                -> PASSED (111.0 MB / 4096 MB used)
======================================================================
🎉 ALL DAY 1 MANDATORY EXIT GATES PASSED CLEANLY IN 5.43s!
======================================================================
```

---

## 🎯 Plan for Day 2 (Tomorrow: 25% → 50%)

When we resume tomorrow, we will execute:
1. **Universal Manifest V3 Browser Extension**:
   - `browser_extension/manifest.json`: Manifest V3 specification with host permissions strictly for `http://127.0.0.1:8000/*`.
   - `browser_extension/background.js`: Holds `X-Golu-Token`, communicates with FastAPI orchestrator via REST/WebSocket, and bridges requests securely without exposing token to web page DOM.
   - `browser_extension/content.js`: Non-intrusive input listener, floating suggestion pill (⚡ Vault / 🧠 Golu AI), `Tab` key handler dispatching native React/Vue/Angular input events, and green highlight review.
2. **Batch Full-Form Automation**:
   - WebSocket `/ws/browser` batch field scraping and autofilling.
3. **Active Learning UI**:
   - Non-intrusive toast popup on manual form entry: "Save to Golu's encrypted vault?".
4. **Tier 2 Desktop Accessibility Engine (`backend/automation/desktop_uia.py`)**:
   - Windows UI Automation (`uiautomation`) to inspect desktop windows and forms without screenshots.
5. **Tier 3 Constrained Vision Fallback (`backend/automation/vision_fallback.py`)**:
   - `mss` 1280x720 window capture + Ollama JSON schema parser + `pyautogui.FAILSAFE = True`.
