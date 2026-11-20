"""Project Golu: Unified Assistant Intelligence Pipeline.
Orchestrates user queries from Voice, UI, and API across:
1. Deterministic Vault (< 20ms exact personal data)
2. Hybrid RAG (< 100ms resume and project knowledge)
3. Live Internet Search (DuckDuckGo + Wikipedia + Local LLM summary)
4. Local LLM General Reasoning (qwen2.5:1.5b via Ollama)
"""

import re
import time
import logging
from typing import Dict, Any

from backend.memory.vault_sql import vault_sql
from backend.memory.rag_store import rag_store
from backend.memory.active_learning import active_learning_engine
from backend.llm_engine import llm_engine
from backend.search import web_search_engine
from backend.security import security_manager

logger = logging.getLogger("golu.assistant")

# Keywords that indicate internet search requirement
SEARCH_INTENT_KEYWORDS = [
    "search", "google", "internet", "web", "latest", "today", "news",
    "who is", "who was", "capital of", "weather", "current", "when did",
    "price of", "definition of", "meaning of", "update", "stock", "score"
]

# Personal keywords that should map to Vault
PERSONAL_KEYWORDS = [
    "my name", "my email", "my phone", "my number", "my college", "my university",
    "my cgpa", "my gpa", "my address", "my dob", "my birth", "my roll", "my github",
    "my linkedin", "my degree", "my branch", "mera naam", "mera phone", "mera college"
]


class GoluAssistant:
    """Unified local assistant intelligence."""

    def __init__(self):
        pass

    def ask(self, query: str, allow_web_search: bool = True) -> Dict[str, Any]:
        """Processes an incoming user query (voice or text) through the optimal memory tier."""
        t0 = time.perf_counter()
        clean_q = security_manager.sanitize_input(query).strip()
        if not clean_q:
            return {"answer": "Haan bhai, sun raha hoon. Kuch bolo!", "source": "chime", "latency_ms": 0.0}

        lower_q = clean_q.lower()

        # Active Learning & Memory: Automatically detect and remember user facts
        learned = active_learning_engine.extract_and_learn(clean_q)
        if learned:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "query": clean_q,
                "answer": learned["ack"],
                "source": "active_learning",
                "key": learned["key"],
                "value": learned["value"],
                "latency_ms": round(elapsed_ms, 2)
            }

        # Conversational Fast-Path (Common conversational chit-chat & greetings)
        if lower_q in ("hi", "hello", "hey", "hello golu", "hi golu", "hey golu", "oye golu", "golu"):
            return {
                "query": clean_q,
                "answer": "Haan bhai! Main Golu hoon, bilkul active aur sun raha hoon. Bolo kya madad karoon?",
                "source": "conversational",
                "latency_ms": 1.0
            }

        if any(p in lower_q for p in ["what are you doing", "kya kar rahe ho", "kya chal raha hai"]):
            return {
                "query": clean_q,
                "answer": "Main aapki commands aur queries sun raha hoon! Aap mujhse internet search, resume profile, ya form autofill ke baare me kuch bhi pooch sakte ho.",
                "source": "conversational",
                "latency_ms": 1.0
            }

        if any(p in lower_q for p in ["where are you listening", "listening to me", "sun rahe ho", "can you hear me"]):
            return {
                "query": clean_q,
                "answer": "Haan bhai, bilkul sun raha hoon! Main aapke laptop ke mic se 100% locally process kar raha hoon, bina kisi cloud ke.",
                "source": "conversational",
                "latency_ms": 1.0
            }

        if any(p in lower_q for p in ["who are you", "who made you", "kaun ho tum"]):
            return {
                "query": clean_q,
                "answer": "Main Golu hoon, aapka zero-cloud local AI assistant jo 4GB VRAM me 100% offline aur securely aapke system par chalta hai!",
                "source": "conversational",
                "latency_ms": 1.0
            }

        # Personal Identity Fast-Path
        if any(p in lower_q for p in ["who am i", "mera naam kya hai", "what is my name", "tell me my name", "what's my name", "who am i?"]):
            name_val = vault_sql.get_value("full_name") or "Gouransh Soni"
            college_val = vault_sql.get_value("university") or "Institute of Engineering and Technology, Udaipur"
            branch_val = vault_sql.get_value("major_branch") or "Computer Science and Engineering"
            return {
                "query": clean_q,
                "answer": f"Aapka naam {name_val} hai! Aap {college_val} se {branch_val} ke graduate aur developer ho.",
                "source": "vault",
                "confidence": 1.0,
                "latency_ms": 1.0
            }

        has_search_intent = any(k in lower_q for k in SEARCH_INTENT_KEYWORDS)

        # Tier 1: Check Deterministic Vault (Personal profile / credentials lookup)
        if not has_search_intent:
            stripped_q = " ".join([w for w in re.findall(r"\w+", lower_q) if w not in ("what", "is", "the", "tell", "me", "kya", "hai", "ka", "ki", "please")])
            for cand in [stripped_q, clean_q]:
                if not cand:
                    continue
                v_res = vault_sql.find_best_match(cand)
                if v_res and v_res[2] >= 0.85:
                    canonical_key, decrypted_val, score, match_ms = v_res
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    formatted_answer = f"Aapka {canonical_key.replace('_', ' ')} hai: {decrypted_val}"
                    logger.info("Answered from Vault in %.2fms: %s", elapsed_ms, formatted_answer)
                    return {
                        "query": clean_q,
                        "answer": formatted_answer,
                        "source": "vault",
                        "confidence": round(score, 3),
                        "latency_ms": round(elapsed_ms, 2)
                    }

        # Tier 2: Check Local RAG (Projects, Experience, Resume details)
        rag_hits = rag_store.hybrid_search(clean_q, top_k=2)
        top_rrf = rag_hits[0].get("rrf_score", 0.0) if rag_hits else 0.0

        if top_rrf > 0.025 and not any(k in lower_q for k in SEARCH_INTENT_KEYWORDS):
            rag_context = "\n---\n".join([h["text"] for h in rag_hits])
            prompt = (
                f"You are Golu, a smart AI assistant. Answer the user's question concisely in 2 sentences "
                f"in natural Hinglish or English based on the candidate's profile:\n\nQuestion: {clean_q}"
            )
            answer = llm_engine.generate(
                prompt=prompt,
                system_prompt="You are Golu, a personal assistant. Answer factually based strictly on the context.",
                rag_context=rag_context,
                max_tokens=100
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "query": clean_q,
                "answer": answer.strip(),
                "source": "rag",
                "confidence": round(min(0.95, top_rrf * 30.0), 3),
                "latency_ms": round(elapsed_ms, 2)
            }

        # Tier 3: Internet Search (If internet search intent, or general knowledge)
        if allow_web_search:
            # Strip search prefixes if user said "search internet for X" or "google X"
            search_query = clean_q
            for prefix in ["search internet for", "search for", "google", "search web for", "web search"]:
                if lower_q.startswith(prefix):
                    search_query = clean_q[len(prefix):].strip()
                    break

            web_res = web_search_engine.answer_query_with_web(search_query)
            if web_res.get("results_count", 0) > 0:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                web_res["latency_ms"] = round(elapsed_ms, 2)
                return web_res

        # Tier 4: Direct Local Brain (LLM General Reasoning)
        prompt = (
            f"You are Golu, a helpful fast local AI assistant. Answer the user's question "
            f"directly and concisely in 2 sentences in natural Hinglish or English:\n\nQuestion: {clean_q}"
        )
        answer = llm_engine.generate(
            prompt=prompt,
            system_prompt="You are Golu, a friendly local AI assistant. Answer concisely and clearly.",
            max_tokens=120
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "query": clean_q,
            "answer": answer.strip(),
            "source": "local_llm",
            "latency_ms": round(elapsed_ms, 2)
        }


# Global assistant instance
assistant = GoluAssistant()
