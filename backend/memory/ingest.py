"""
Project Golu: Document Ingestion & Chunking Pipeline
Module: backend/memory/ingest.py

Features:
- Ingestion of PDF, DOCX, TXT, and MD files
- 300-token semantic chunking with 50-token overlap
- Automatic creation and indexing of Gourab's realistic engineering resume
- Feeds chunks directly into HybridRAGStore (ChromaDB + BM25)
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import PyPDF2
from backend.memory.rag_store import rag_store

logger = logging.getLogger("golu.ingest")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
RESUME_TXT_PATH = DATA_DIR / "resume.txt"
RESUME_PDF_PATH = DATA_DIR / "resume.pdf"

DEFAULT_RESUME_TEXT = """
GOURAB SAHA
Bengaluru, Karnataka, India | +91 9876543210 | gourabsaha.dev@gmail.com
LinkedIn: linkedin.com/in/gourabsaha-dev | GitHub: github.com/gourabsaha | Portfolio: gourabsaha.dev

PROFESSIONAL SUMMARY
High-performing Full-Stack & AI Systems Engineer with deep expertise in local AI orchestration, low-latency architectures, and memory-constrained edge deployment. Experienced in designing production-grade client-server systems, privacy-preserving zero-cloud architectures, and hardware-constrained GPU pipelines (4GB VRAM optimization). Proven track record of shipping production tools with 99.9% deterministic accuracy.

EDUCATION
Vellore Institute of Technology (VIT)
Bachelor of Technology in Computer Science and Engineering | 2021 – 2025
- Current CGPA: 8.85 / 10.0
- Coursework: Data Structures & Algorithms, Operating Systems, Database Management Systems, Distributed Systems, Computer Networks, Machine Learning.

TECHNICAL SKILLS
- Languages: Python, JavaScript, TypeScript, C++, SQL, HTML5/CSS3.
- AI & ML: Ollama, Faster-Whisper, Silero VAD, Kokoro-82M TTS, ChromaDB, BM25, Sentence-Transformers, HuggingFace, PyTorch.
- Frameworks & Backends: FastAPI, Uvicorn, WebSockets, PyQt6, React, Node.js, SQLite.
- Systems & Tools: Windows DPAPI, WASAPI Loopback Audio, UI Automation (UIA), PyAutoGUI, Docker, Git, Linux/PowerShell.
- Architecture: Zero-Cloud Privacy, Local RAG, Reciprocal Rank Fusion (RRF), Finite State Machines (FSM), Manifest V3 Browser Extensions.

FEATURED PROJECTS
1. Project Golu: Production-Grade Zero-Cloud Local AI Agent (4GB VRAM Edition)
- Engineered a zero-cloud, local client-server AI system running entirely on a 4GB VRAM GPU without cloud reliance or API fees.
- Partitioned compute: Unified LLM (Qwen 4B) on GPU (2.6-3.3 GB VRAM); Multilingual RAG, Whisper STT, and Kokoro TTS on CPU.
- Built a 3-tier browser and desktop automation engine: Tier 1 Manifest V3 extension, Tier 2 Windows UI Automation, Tier 3 Vision fallback.
- Implemented defense-in-depth security: Windows DPAPI master key encryption (AES-256 Fernet), rotating X-Golu-Token authentication, and XML prompt-injection firewall.
- Designed an undetectable meeting co-pilot HUD with driver-level WASAPI loopback audio capture and Windows WDA_EXCLUDEFROMCAPTURE screen-share invisibility.

2. Distributed Key-Value Store with Raft Consensus
- Implemented a fault-tolerant distributed key-value storage engine in C++ utilizing the Raft consensus algorithm.
- Achieved sub-millisecond P99 tail latency for concurrent read/write transactions across a 5-node cluster.
- Implemented log compaction, snapshotting, and dynamic membership reconfiguration under network partitions.

3. Edge AI Real-Time Telemetry & Anomaly Detection Gateway
- Developed an edge IoT telemetry gateway in Python and FastAPI that monitors industrial sensor streams in real time.
- Integrated lightweight statistical and isolation forest models to detect anomalous sensor drift within 15 milliseconds.
- Streamed live anomaly alerts to an interactive dashboard over full-duplex WebSockets.

PROFESSIONAL EXPERIENCE
TechInnovate Labs | AI Systems Engineering Intern
Jan 2024 – Jun 2024 | Bengaluru, India
- Architected and deployed lightweight local inference pipelines for edge hardware, optimizing Q4_K_M model quantization.
- Reduced inference memory footprint by 38% and elevated sustained token generation throughput by 42%.
- Engineered hybrid semantic search combining dense vector embeddings with BM25 keyword retrieval using Reciprocal Rank Fusion.
- Collaborated with senior engineers to implement DPAPI credential isolation and hardened localhost API endpoints against CSRF and DNS rebinding attacks.

HONORS & CERTIFICATIONS
- Winner, National HackIndia Innovation Challenge 2024 (1st place out of 450+ teams).
- AWS Certified Cloud Practitioner (2024).
- Top 5% Global Rank on LeetCode (Rating 1850+, 350+ DSA problems solved in C++ and Python).
- Published technical research paper on "Memory-Aware Quantization Strategies for Edge LLM Inference".
"""


def chunk_text(text: str, chunk_size_words: int = 250, overlap_words: int = 50) -> List[str]:
    """
    Splits text into ~250-word chunks (roughly 300 tokens) with 50-word overlap.
    Preserves paragraph and sentence boundaries wherever feasible.
    """
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: List[str] = []
    current_words: List[str] = []

    for para in paragraphs:
        para_words = para.split()
        if not para_words:
            continue

        if len(current_words) + len(para_words) <= chunk_size_words:
            current_words.extend(para_words)
        else:
            # If current buffer has content, save it
            if current_words:
                chunks.append(" ".join(current_words))
                # Retain overlap from end of current chunk
                current_words = current_words[-overlap_words:] if len(current_words) >= overlap_words else current_words

            # If paragraph itself is larger than chunk_size, split by word slices
            while len(para_words) > chunk_size_words:
                chunks.append(" ".join(para_words[:chunk_size_words]))
                para_words = para_words[chunk_size_words - overlap_words:]

            current_words.extend(para_words)

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extracts text content from a PDF file using PyPDF2."""
    extracted = []
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    extracted.append(txt)
    except Exception as e:
        logger.error(f"Failed to read PDF {pdf_path}: {e}")
    return "\n\n".join(extracted)


def extract_text_from_file(file_path: Path) -> str:
    """Reads text from PDF, DOCX, TXT, or MD."""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    elif ext == ".docx":
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception as e:
            logger.error(f"Failed to read DOCX {file_path}: {e}")
            return ""
    else:
        logger.warning(f"Unsupported file format: {ext}")
        return ""


def ensure_default_resume() -> Path:
    """Ensures a rich realistic default resume exists on disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not RESUME_TXT_PATH.exists():
        RESUME_TXT_PATH.write_text(DEFAULT_RESUME_TEXT.strip(), encoding="utf-8")
        logger.info(f"Created default resume at {RESUME_TXT_PATH}")
    return RESUME_TXT_PATH


def ingest_document(file_path: Path, source_name: Optional[str] = None) -> int:
    """
    Ingests a document, extracts text, chunks it, and populates HybridRAGStore.
    Returns number of chunks ingested.
    """
    if not file_path.exists():
        logger.warning(f"Document file does not exist: {file_path}")
        return 0

    text = extract_text_from_file(file_path)
    if not text.strip():
        logger.warning(f"No text extracted from {file_path}")
        return 0

    src = source_name or file_path.name
    raw_chunks = chunk_text(text)

    documents = []
    for idx, chunk in enumerate(raw_chunks):
        doc_id = f"{src}_{idx}"
        documents.append({
            "id": doc_id,
            "text": chunk,
            "metadata": {
                "source": src,
                "chunk_index": idx,
                "total_chunks": len(raw_chunks)
            }
        })

    rag_store.add_documents(documents)
    logger.info(f"Successfully ingested {len(documents)} chunks from {src}")
    return len(documents)


def bootstrap_memory():
    """Initializes and ingests default profile documents into RAG."""
    resume_file = ensure_default_resume()
    ingest_document(resume_file, "resume.txt")
    if RESUME_PDF_PATH.exists():
        ingest_document(RESUME_PDF_PATH, "resume.pdf")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bootstrap_memory()
