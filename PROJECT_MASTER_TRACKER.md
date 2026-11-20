# Project Golu: Master Architecture & Daily Progress Tracker (4GB VRAM Edition)

> **Zero-Cloud, Local Client-Server AI System**
> Production Orchestrator: `127.0.0.1:8000` | Target GPU: NVIDIA GeForce GTX 1650 (4096 MiB VRAM)

---

## 📊 4-Day Execution Plan & Milestone Progress

| Stage | Milestone | Target Deliverables | Mandatory Exit Gate Status |
|---|---|---|---|
| **Day 1** | **0% → 25%** | **Brain, Security & Memory Subsystems**<br>• Python 3.13 environment + dependencies<br>• `backend/security.py` (DPAPI + AES-256 + X-Golu-Token + XML Injection Firewall)<br>• `backend/memory/vault_sql.py` (Encrypted SQLite + RapidFuzz + In-Memory Cache)<br>• `backend/memory/rag_store.py` (ChromaDB + BM25 RRF + Zero-Cloud Embedding)<br>• `backend/memory/ingest.py` (Semantic chunker + Gourab's verified resume profile)<br>• `backend/llm_engine.py` (Ollama client + VRAM Watchdog + Grounded fallback)<br>• `backend/router.py` (Dual-Memory Confidence Router + Regex Guard + Length Enforcer)<br>• `backend/main.py` (FastAPI orchestrator on `127.0.0.1:8000` + Token Auth)<br>• `tests/eval_benchmark.py` (Complete Exit Gate Test Suite) | ✅ **PASSED (100%)**<br>• Peak VRAM: 111.0 MB / 4096 MB (≤ 3.5 GB)<br>• Vault Latency: **3.81 ms** (Target: < 20 ms)<br>• Unauthenticated requests: **401 Unauthorized**<br>• Grounded RAG accuracy: **100% facts verified**<br>• Deny-List & Injection Firewall: **100% blocked** |
| **Day 2** | **25% → 50%** | **Universal Form & Desktop Automation Engine**<br>• Manifest V3 Extension (`manifest.json`, `background.js`, `content.js`)<br>• Floating Tab suggestion pill UI with native React/Vue/Angular dispatch<br>• Batch full-form autofill WebSocket (`/ws/browser`) with green preview highlight<br>• Active Learning Toast ("Save to Golu's encrypted vault?")<br>• Tier 2 Desktop Accessibility Engine (`backend/automation/desktop_uia.py`)<br>• Tier 3 Constrained Vision Fallback (`backend/automation/vision_fallback.py`)<br>• `tests/eval_day2_benchmark.py` (Complete Day 2 Exit Gate Test Suite) | ✅ **PASSED (100%)**<br>• MV3 structure & manifest verified<br>• 14/14 real-world fields autofilled (Google Forms, Internshala, College ERP)<br>• Sensitive credentials rejected: **100%**<br>• Hidden prompt injection neutralized: **100%**<br>• Native UI Automation control tree traversal verified<br>• Constrained 720p vision pipeline verified |
| **Day 3** (Completed) | **50% → 75%** | **Voice Persona & Undetectable Meeting Co-Pilot**<br>• Hinglish Voice Engine (`backend/audio/golu_voice.py`)<br>• Faster-Whisper (CPU int8) + VAD energy filter<br>• Pre-rendered sub-100ms reaction audio clips ("Haan bhai, bolo?")<br>• Token-bounded wake word detection ("Hey Golu" / "Hi Golu")<br>• PyAudioWPatch WASAPI Loopback stream (`backend/audio/loopback_listener.py`)<br>• Stealth PyQt6 HUD (`stealth_hud/overlay.py`) with `WDA_EXCLUDEFROMCAPTURE`<br>• Global FSM Hotkey State Manager (`backend/state_machine.py`)<br>• Meeting Co-Pilot pipeline (`backend/meeting_copilot.py`)<br>• `tests/eval_day3_benchmark.py` (Complete Day 3 Exit Gate Test Suite) | ✅ **PASSED (100%)**<br>• Voice engine runs 100% on CPU (0 MB GPU VRAM)<br>• 100% wake word detection with 0% false positives<br>• WASAPI loopback release: **8.19 ms** (Target: < 50 ms)<br>• Stealth HUD cloaked: `WDA_EXCLUDEFROMCAPTURE` (0x00000011) active<br>• FSM mutual exclusivity & hard-mute: 0% meeting audio leak<br>• Emergency Kill Switch: **10.15 ms** (Target: < 50 ms)<br>• End-to-end co-pilot generation: **1.38 s** |
| **Day 4** (Next) | **75% → 100%** | **Integration, Exhibition Proof & Offline Demo**<br>• One-click launcher (`start_golu.bat`) and pre-warming (`warmup.py`)<br>• End-to-end 50-field real-world evaluation benchmark<br>• Airplane Mode (Wi-Fi OFF) verification rehearsal<br>• Live Judge Metrics Readout card | ⏳ *Scheduled for Day 4* |

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

## ⚡ Performance Benchmark Readout (Measured Day 3)

```text
======================================================================
PROJECT GOLU: DAY 3 MANDATORY EXIT GATE EVALUATION BENCHMARK
======================================================================
Test 01: Voice Engine Initialization & Hinglish ASR   -> PASSED (CPU int8, active VAD filter)
Test 02: Wake word specificity benchmark             -> PASSED (100% precision: 'Hey Golu', 0% false triggers)
Test 03: WASAPI loopback capture & release latency   -> PASSED (Handles released in 8.19ms, Target: < 50ms)
Test 04: Stealth HUD display affinity                -> PASSED (WDA_EXCLUDEFROMCAPTURE 0x00000011 active, wipe verified)
Test 05: FSM mutual exclusivity & kill switch        -> PASSED (TTS hard-muted 0% leak, kill switch in 10.15ms)
Test 06: End-to-end meeting co-pilot simulation      -> PASSED (RAG -> LLM in 1.38s, 100% grounded in resume)
======================================================================
🎉 ALL DAY 3 MANDATORY EXIT GATES PASSED IN 3.38s!
======================================================================
```

---

## 🎯 Plan for Day 4 (Milestone: 75% → 100%)

When we execute Day 4 (Final Milestone), we will deliver:
1. **One-Click Unified Production Launcher (`start_golu.bat`)**:
   - Background launch and health verification of Ollama (`127.0.0.1:11434`), FastAPI Orchestrator (`127.0.0.1:8000`), Stealth HUD (PyQt6), and Global Hotkey listener.
2. **Pre-Warming Pipeline (`warmup.py`)**:
   - Warms up Ollama with `"keep_alive": -1` to eliminate first-token cold start delays.
   - Pre-loads Faster-Whisper and ChromaDB embeddings into RAM.
3. **End-to-End 50-Field Real-World Benchmark (`tests/eval_e2e_exhibition.py`)**:
   - Comprehensive multi-tier stress test covering 50 fields across 5 real portals, multi-turn voice Q&A, and meeting co-pilot queries.
4. **Airplane Mode Verification Rehearsal**:
   - Validating 100% functionality with zero network sockets and telemetry blocked.
5. **Live Judge Readout & Final Architecture Artifact**:
   - Real-time performance dashboard for the exhibition judge display.
