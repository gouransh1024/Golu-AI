"""Project Golu: Document Parser & Form Profile Ingestor.
Extracts text from PDF, DOCX, TXT, and MD files,
indexes into Hybrid RAG (ChromaDB + BM25), and extracts structured
profile attributes into the encrypted SQLite Vault for 1-click form autofill.
"""

import io
import re
import logging
from pathlib import Path
from typing import Dict, Any, List

import pypdf
import docx

from backend.memory.vault_sql import vault_sql
from backend.memory.rag_store import rag_store
from backend.memory.ingest import chunk_text

logger = logging.getLogger("golu.memory.doc_parser")


def extract_text(filename: str, file_bytes: bytes) -> str:
    """Extracts plain text from file bytes based on file extension."""
    ext = Path(filename).suffix.lower()
    text = ""

    if ext == ".pdf":
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages_text).strip()
        except Exception as e:
            logger.error("Failed to parse PDF %s: %s", filename, e)

    elif ext in (".docx", ".doc"):
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            para_text = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    para_text.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
            text = "\n".join(para_text).strip()
        except Exception as e:
            logger.error("Failed to parse DOCX %s: %s", filename, e)

    else:
        # Default text/markdown/json
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1", errors="ignore")

    return text.strip()


def parse_and_ingest_document(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """Parses an uploaded document, indexes chunks into RAG,
    and extracts personal profile fields into the encrypted Vault for web form autofilling.
    """
    text = extract_text(filename, file_bytes)
    if not text:
        return {"error": "Could not extract readable text from uploaded file", "extracted_fields": {}}

    # 1. Chunk and store in RAG
    chunks = chunk_text(text)
    src_clean = Path(filename).stem
    docs = []
    for idx, c in enumerate(chunks):
        doc_id = f"upload_{src_clean}_{idx}"
        docs.append({
            "id": doc_id,
            "text": c,
            "metadata": {
                "source": filename,
                "chunk_index": idx,
                "category": "uploaded_document"
            }
        })
    rag_store.add_documents(docs)
    logger.info("Ingested %d chunks from uploaded document %s into RAG", len(docs), filename)

    # 2. Extract structured profile fields for Form Autofill
    extracted = {}

    # Email
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    if email_match:
        email_val = email_match.group(0).strip()
        vault_sql.set_value("email", email_val, "contact", ["email", "my email", "contact email"])
        extracted["email"] = email_val

    # Phone
    phone_match = re.search(r"(?:\+91[\-\s]?)?[6789]\d{9}", text)
    if phone_match:
        phone_val = phone_match.group(0).strip()
        vault_sql.set_value("phone", phone_val, "contact", ["phone", "my phone", "mobile", "mobile number"])
        extracted["phone"] = phone_val

    # CGPA / GPA
    cgpa_match = re.search(r"(?:cgpa|gpa|score|aggregate)[\s:]*([0-9]\.[0-9]{1,2})", text, flags=re.IGNORECASE)
    if cgpa_match:
        cgpa_val = cgpa_match.group(1).strip()
        vault_sql.set_value("cgpa", cgpa_val, "education", ["cgpa", "gpa", "my cgpa", "marks"])
        extracted["cgpa"] = cgpa_val

    # University / College
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if any(term in line.lower() for term in ["institute of", "university", "college of", "engineering and technology"]):
            # Clean punctuation
            clean_uni = line.split("|")[0].split("-")[0].strip()
            if len(clean_uni) >= 6 and len(clean_uni) <= 80:
                vault_sql.set_value("university", clean_uni, "education", [clean_uni.lower(), "college", "university", "my college"])
                extracted["university"] = clean_uni
                break

    # Full Name (usually first prominent line of resume)
    for line in lines[:5]:
        line_clean = re.sub(r"[^A-Za-z\s]", "", line).strip()
        words = line_clean.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words):
            # Exclude section headers
            if not any(hdr in line_clean.upper() for hdr in ["RESUME", "CURRICULUM", "EDUCATION", "SUMMARY", "EXPERIENCE"]):
                title_name = line_clean.title()
                words_title = title_name.split()
                vault_sql.set_value("full_name", title_name, "personal", [title_name.lower(), "my name", "full name", "name", words_title[0].lower()])
                vault_sql.set_value("first_name", words_title[0], "personal", ["first name", "my first name", words_title[0].lower()])
                vault_sql.set_value("last_name", " ".join(words_title[1:]), "personal", ["last name", "my last name"])
                extracted["full_name"] = title_name
                break

    # Degree / Major
    for line in lines:
        if any(deg in line for deg in ["B.Tech", "Bachelor", "B.E.", "M.Tech", "Master", "B.Sc", "BCA", "MCA"]):
            deg_clean = line.split("|")[0].strip()
            vault_sql.set_value("degree", deg_clean, "education", ["degree", "my degree", "course", "qualification"])
            extracted["degree"] = deg_clean
            if "computer science" in line.lower():
                vault_sql.set_value("major_branch", "Computer Science and Engineering", "education", ["branch", "major", "my branch"])
                extracted["major_branch"] = "Computer Science and Engineering"
            break

    # LinkedIn & GitHub
    linkedin_match = re.search(r"linkedin\.com/in/[\w\-]+", text)
    if linkedin_match:
        li_val = "https://" + linkedin_match.group(0)
        vault_sql.set_value("linkedin_url", li_val, "links", ["linkedin", "linkedin url", "my linkedin"])
        extracted["linkedin_url"] = li_val

    github_match = re.search(r"github\.com/[\w\-]+", text)
    if github_match:
        gh_val = "https://" + github_match.group(0)
        vault_sql.set_value("github_url", gh_val, "links", ["github", "github url", "my github"])
        extracted["github_url"] = gh_val

    logger.info("Document parsed successfully. Fields extracted for Autofill: %s", list(extracted.keys()))
    return {
        "status": "success",
        "filename": filename,
        "chunks_indexed": len(docs),
        "extracted_fields": extracted
    }
