# Project Golu: Master Architecture & Daily Progress Tracker (4GB VRAM Edition)

> **Zero-Cloud, Local Client-Server AI System**
> Production Orchestrator: `127.0.0.1:8000` | Target GPU: NVIDIA GeForce GTX 1650 (4096 MiB VRAM)

---

## 📊 4-Day Execution Plan & Milestone Progress

| Stage | Milestone | Target Deliverables | Mandatory Exit Gate Status |
|---|---|---|---|
| **Day 1** | **0% → 25%** | **Brain, Security & Memory Subsystems**<br>• Python 3.13 environment + dependencies<br>• `backend/security.py` (DPAPI + AES-256 + X-Golu-Token + XML Injection Firewall)<br>• `backend/memory/vault_sql.py` (Encrypted SQLite + RapidFuzz + In-Memory Cache)<br>• `backend/memory/rag_store.py` (ChromaDB + BM25 RRF + Zero-Cloud Embedding)<br>• `backend/memory/ingest.py` (Semantic chunker + Gourab's verified resume profile)<br>• `backend/llm_engine.py` (Ollama client + VRAM Watchdog + Grounded fallback)<br>• `backend/router.py` (Dual-Memory Confidence Router + Regex Guard + Length Enforcer)<br>• `backend/main.py` (FastAPI orchestrator on `127.0.0.1:8000` + Token Auth)<br>• `tests/eval_benchmark.py` (Complete Exit Gate Test Suite) | ✅ **PASSED (100%)**<br>• Peak VRAM: 111.0 MB / 4096 MB (≤ 3.5 GB)<br>• Vault Latency: **3.81 ms** (Target: < 20 ms)<br>• Unauthenticated requests: **401 Unauthorized**<br>• Grounded RAG accuracy: **100% facts verified**<br>• Deny-List & Injection Firewall: **100% blocked** |
| **Day 2** (Completed) | **25% → 50%** | **Universal Form & Desktop Automation Engine**<br>• Manifest V3 Extension (`manifest.json`, `background.js`, `content.js`)<br>• Floating Tab suggestion pill UI with native React/Vue/Angular dispatch<br>• Batch full-form autofill WebSocket (`/ws/browser`) with green preview highlight<br>• Active Learning Toast ("Save to Golu's encrypted vault?")<br>• Tier 2 Desktop Accessibility Engine (`backend/automation/desktop_uia.py`)<br>• Tier 3 Constrained Vision Fallback (`backend/automation/vision_fallback.py`)<br>• `tests/eval_day2_benchmark.py` (Complete Day 2 Exit Gate Test Suite) | ✅ **PASSED (100%)**<br>• MV3 structure & manifest verified<br>• 14/14 real-world fields autofilled (Google Forms, Internshala, College ERP)<br>• Sensitive credentials rejected: **100%**<br>• Hidden prompt injection neutralized: **100%**<br>• Native UI Automation control tree traversal verified<br>• Constrained 720p vision pipeline verified |
| **Day 3** (Next) | **50% → 75%** | **Voice Persona & Undetectable Meeting Co-Pilot**<br>• Hinglish Voice Engine (`backend/audio/golu_voice.py`)<br>• Silero VAD + Faster-Whisper (small int8 on CPU) + Kokoro-82M TTS<br>• Sub-100ms instant reaction audio clips ("Haan bhai, bolo?")<br>• WASAPI Loopback listener (`backend/audio/loopback_listener.py`)<br>• Stealth PyQt6 HUD (`stealth_hud/overlay.py`) with `WDA_EXCLUDEFROMCAPTURE`<br>• Global FSM Hotkey State Manager (`backend/state_machine.py`) | ⏳ *Scheduled for Day 3* |
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

## ⚡ Performance Benchmark Readout (Measured Day 2)

```text
======================================================================
PROJECT GOLU: DAY 2 MANDATORY EXIT GATE EVALUATION BENCHMARK
======================================================================
Test 01: Manifest V3 extension structure validation      -> PASSED (All files & permissions verified)
Test 02: Real-world multi-site form fill benchmark       -> PASSED (14/14 fields: Google Forms, Internshala, ERP)
Test 03: Security deny-list rejection test               -> PASSED (100% password, OTP, CVV, Aadhaar, PAN blocked)
Test 04: Hidden element injection defense test           -> PASSED (Hidden injection prompt neutralized)
Test 05: Tier 2 Desktop UIA engine test                  -> PASSED (Windows accessibility tree traversal active)
Test 06: Tier 3 Vision Fallback 720p pipeline test       -> PASSED (Constrained 720p downscaling & action plan verified)
======================================================================
🎉 ALL DAY 2 MANDATORY EXIT GATES PASSED IN 1.95s!
======================================================================
```

---

## 🎯 Plan for Day 3 (Milestone: 50% → 75%)

When we execute Day 3, we will deliver:
1. **Hinglish Voice Engine (`backend/audio/golu_voice.py`)**:
   - Silero VAD for low-CPU speech boundary detection (< 2% CPU idle).
   - Faster-Whisper (`small`, `int8` on CPU) for high-accuracy Hinglish speech-to-text.
   - Kokoro-82M TTS (`lang_code="h"`, `hm_omega`) for sub-second offline voice synthesis.
   - Instant reaction audio clips (sub-100ms acknowledge: *"Haan bhai, bolo?"*).
2. **PyAudioWPatch WASAPI Loopback Listener (`backend/audio/loopback_listener.py`)**:
   - Native Windows Audio Session loopback capturing internal speaker audio (WhatsApp, Google Meet, Zoom, MS Teams).
3. **Stealth Undetectable HUD (`stealth_hud/overlay.py`)**:
   - PyQt6 floating overlay with Windows `SetWindowDisplayAffinity(hwnd, 0x00000011)` (`WDA_EXCLUDEFROMCAPTURE`), rendering Golu invisible to screen sharing and recording software.
4. **Global Finite State Machine & Hotkey Manager (`backend/state_machine.py`)**:
   - Mutual exclusivity: `MODE_ASSISTANT` (voice + browser), `MODE_MEETING` (TTS hard-muted, loopback active, stealth HUD), `MODE_HIDE_HUD`, and `MODE_KILL` hardware interrupt (< 50ms).
5. **Day 3 Test Benchmark Suite (`tests/eval_day3_benchmark.py`)**:
   - Verifying state machine transitions, audio capture, Whisper transcription, and HUD invisibility flag.
