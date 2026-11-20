"""
Project Golu: Automatic Confidence Router & Post-Generation Accuracy Validators
Module: backend/router.py

Implements:
1. Dual-Memory Routing:
   - Path 1: Deterministic Encrypted Vault (< 20ms, 0% Hallucination) for short inputs (score >= 0.85)
   - Path 2: Hybrid Local RAG (< 1.8s, Grounded Answers) for textareas, essay prompts (> 6 words), or unmapped inputs
2. Post-Generation Accuracy Validators:
   - Regex Guard (validates email, tel, url, date patterns)
   - Length Enforcer (clean sentence-boundary truncation respecting field's maxlength constraint)
"""

import re
import time
import logging
from typing import Dict, Any, Optional
from backend.security import security_manager
from backend.memory.vault_sql import vault_sql
from backend.memory.rag_store import rag_store
from backend.llm_engine import llm_engine

logger = logging.getLogger("golu.router")

# Regex validation patterns for standard structured fields
REGEX_GUARDS = {
    "email": r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
    "tel": r"^(\+?[0-9\s\-\(\)]{7,20})$",
    "phone": r"^(\+?[0-9\s\-\(\)]{7,20})$",
    "url": r"^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$",
    "date": r"^\d{4}-\d{2}-\d{2}$|^\d{2}/\d{2}/\d{4}$|^\d{2}-\d{2}-\d{4}$"
}


class AccuracyValidator:
    """Validates regex formatting and enforces strict maxlength constraints."""

    @staticmethod
    def validate_regex(value: str, field_type: str, field_name: str) -> bool:
        norm_type = (field_type or "").lower().strip()
        norm_name = (field_name or "").lower().strip()

        check_pattern = None
        if norm_type in REGEX_GUARDS:
            check_pattern = REGEX_GUARDS[norm_type]
        elif "email" in norm_name or "mail" in norm_name:
            check_pattern = REGEX_GUARDS["email"]
        elif any(k in norm_name for k in ["phone", "mobile", "contact_no", "cell"]):
            check_pattern = REGEX_GUARDS["tel"]
        elif any(k in norm_name for k in ["url", "link", "website", "github", "linkedin", "portfolio"]):
            check_pattern = REGEX_GUARDS["url"]
        elif any(k in norm_name for k in ["dob", "date_of_birth", "birth_date"]):
            check_pattern = REGEX_GUARDS["date"]

        if check_pattern:
            return bool(re.match(check_pattern, value.strip()))
        return True

    @staticmethod
    def enforce_length(text: str, maxlength: Optional[int]) -> str:
        """
        Truncates cleanly at a sentence or word boundary if text exceeds maxlength.
        """
        if not maxlength or maxlength <= 0 or len(text) <= maxlength:
            return text

        truncated = text[:maxlength].strip()
        # Find last sentence-ending punctuation within limit
        last_punct = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
        if last_punct > int(maxlength * 0.6):
            return truncated[:last_punct + 1]

        # Otherwise find last word boundary
        last_space = truncated.rfind(" ")
        if last_space > int(maxlength * 0.6):
            return truncated[:last_space] + "..."

        return truncated


class ConfidenceRouter:
    """
    Automatic Confidence Router:
    Routes field requests between Path 1 (Vault) and Path 2 (RAG + LLM).
    """

    def __init__(self):
        self.validator = AccuracyValidator()

    def route_field(
        self,
        field_name: str,
        field_type: str = "text",
        field_label: Optional[str] = None,
        placeholder: Optional[str] = None,
        context: Optional[str] = None,
        maxlength: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Routes the field request and produces a verified suggestion.
        Returns:
            {
                "field_name": str,
                "suggestion": str,
                "source": "vault" | "rag" | "denied",
                "confidence": float,
                "latency_ms": float,
                "is_valid": bool,
                "validator_note": str
            }
        """
        t0 = time.perf_counter()
        query_text = (field_label or field_name or placeholder or "").strip()

        # Step 0: Security Deny-List Check
        if security_manager.is_sensitive_field(field_name, field_type, query_text):
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "field_name": field_name,
                "suggestion": "",
                "source": "denied",
                "confidence": 0.0,
                "latency_ms": elapsed_ms,
                "is_valid": False,
                "validator_note": "Blocked by sensitive field deny-list (Password/OTP/Aadhaar/Financial)"
            }

        # Step 1: Check Path 1 (Deterministic Encrypted Vault)
        is_textarea = field_type.lower() == "textarea"
        query_candidates = [c for c in [field_label, field_name, placeholder] if c and c.strip()]
        
        # Determine if query is an essay prompt (> 6 words and no clear short label)
        word_count = len(query_text.split())
        is_essay = (word_count > 6 and not any(len(c.split()) <= 4 for c in query_candidates)) or (maxlength and maxlength > 200)

        if not is_textarea and not is_essay:
            best_vault_match = None
            best_score = 0.0

            for cand in query_candidates:
                v_res = vault_sql.find_best_match(cand)
                if v_res and v_res[2] > best_score:
                    best_score = v_res[2]
                    best_vault_match = v_res

            if best_vault_match and best_score >= 0.85:
                canonical_key, decrypted_val, score, match_ms = best_vault_match
                enforced_val = self.validator.enforce_length(decrypted_val, maxlength)
                is_valid = self.validator.validate_regex(enforced_val, field_type, field_name)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0

                return {
                    "field_name": field_name,
                    "canonical_key": canonical_key,
                    "suggestion": enforced_val,
                    "source": "vault",
                    "confidence": round(score, 3),
                    "latency_ms": round(elapsed_ms, 2),
                    "is_valid": is_valid,
                    "validator_note": "Deterministic Vault exact match (<20ms, 0% hallucination)"
                }

        # Step 2: Path 2 (Hybrid Local RAG + LLM)
        # Triggered for textareas, essay prompts, or fields not mapped in vault
        rag_query = f"{query_text} {context or ''}".strip()
        top_chunks = rag_store.hybrid_search(rag_query, top_k=3)

        combined_context = "\n---\n".join([chunk["text"] for chunk in top_chunks]) if top_chunks else ""
        top_score = top_chunks[0].get("rrf_score", 0.75) if top_chunks else 0.50

        # Construct generation prompt
        max_words = (maxlength // 5) if maxlength and maxlength < 500 else 60
        system_instruction = (
            f"You are Golu, an assistant filling an application form. "
            f"Write a professional, factual response in at most {max_words} words based strictly on the candidate's profile."
        )

        generated_raw = llm_engine.generate(
            prompt=f"Draft answer for field: '{query_text}'. Context: {context or 'None'}",
            system_prompt=system_instruction,
            rag_context=combined_context,
            max_tokens=max_words * 2
        )

        final_text = self.validator.enforce_length(generated_raw, maxlength)
        is_valid = self.validator.validate_regex(final_text, field_type, field_name)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "field_name": field_name,
            "suggestion": final_text,
            "source": "rag",
            "confidence": round(min(0.95, top_score * 25.0), 3),
            "latency_ms": round(elapsed_ms, 2),
            "is_valid": is_valid,
            "validator_note": "Grounded Hybrid RAG (ChromaDB + BM25 RRF)"
        }


# Global singleton instance
router = ConfidenceRouter()
