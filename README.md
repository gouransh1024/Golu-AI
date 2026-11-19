# Project Golu: Production-Grade Local AI Agent (4GB VRAM Edition)

Project Golu is engineered as a **Zero-Cloud, Local Client–Server AI System**: a single secured Python orchestrator (`127.0.0.1:8000`) serving four specialized thin clients:
1. Universal Browser Extension (Manifest V3)
2. Hinglish Voice Interface ("Hey Golu")
3. Desktop / Vision Automation Engine
4. Invisible Meeting Co-Pilot HUD

The system follows three non-negotiable engineering laws:
- **Strict 4GB VRAM Partitioning**: Zero Out-Of-Memory crashes on GTX 1650 (4096 MiB).
- **Zero-Trust Localhost Security**: Websites cannot exfiltrate personal vault data (Strict CORS + DPAPI + rotating `X-Golu-Token` + Injection Firewall).
- **Deterministic-First Accuracy**: Never use a probabilistic LLM where exact lookup (< 5ms) or DOM/OS APIs achieve 99.9% precision.

---

## 🚀 Quickstart & Verification (Day 1 Complete)

### 1. Run the Evaluation Benchmark
Verify all Day 1 Exit Gates:
```powershell
python tests/eval_benchmark.py
```

### 2. Start the FastAPI Orchestrator
```powershell
python backend/main.py
```
Server binds strictly to `http://127.0.0.1:8000`.

### 3. Check System Health & VRAM Watchdog
```powershell
curl http://127.0.0.1:8000/api/health
```

---

## 📁 Repository Structure

```text
golu-ai/
├── PROJECT_MASTER_TRACKER.md       # Master 4-day progress and architectural memory
├── backend/
│   ├── main.py                     # FastAPI + Token Auth + Strict CORS + Endpoints
│   ├── security.py                 # DPAPI Keyring + Fernet AES-256 + Injection Firewall
│   ├── router.py                   # Automatic Confidence Router + Accuracy Validators
│   ├── llm_engine.py               # Core Brain + VRAM Watchdog (nvidia-smi polling)
│   ├── memory/
│   │   ├── vault_sql.py            # Encrypted SQLite + RapidFuzz In-Memory Cache (<5ms)
│   │   ├── rag_store.py            # ChromaDB + BM25Okapi RRF Hybrid Search
│   │   └── ingest.py               # PDF/DOCX/TXT chunker + default profile
│   ├── audio/                      # Voice & WASAPI loopback (Day 3)
│   └── automation/                 # Windows UIA & Vision fallback (Day 2)
├── browser_extension/              # Manifest V3 extension (Day 2)
├── stealth_hud/                    # Invisible PyQt6 HUD (Day 3)
├── tests/
│   └── eval_benchmark.py           # Day 1 Mandatory Exit Gate Test Suite
└── data/
    ├── vault.db                    # AES-256 encrypted SQLite database
    ├── chroma_db/                  # Local vector database
    ├── bm25_corpus.json            # Sparse BM25 keyword index
    └── resume.txt                  # Grounding profile document
```

---

## 🗓️ 4-Day Execution Plan

- **Day 1 (0% → 25%)**: Brain, Security & Memory Architecture (✅ **COMPLETE**)
- **Day 2 (25% → 50%)**: Universal Form & Desktop Engine (Manifest V3 + Windows UIA + Vision fallback)
- **Day 3 (50% → 75%)**: Golu Voice ("Hey Golu") & Undetectable Meeting Co-Pilot HUD
- **Day 4 (75% → 100%)**: Integration, Exhibition Proof & Offline Demo
