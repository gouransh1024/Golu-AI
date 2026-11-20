"""Project Golu: Active Learning & Long-Term Memory Engine.
Extracts user profile updates and facts directly from conversation,
persisting them in:
1. Encrypted SQLite Vault (deterministic personal attributes)
2. Hybrid ChromaDB RAG store (unstructured experiences, facts, preferences)
"""

import re
import logging
from typing import Optional, Dict, Any, List

from backend.memory.vault_sql import vault_sql
from backend.memory.rag_store import rag_store

logger = logging.getLogger("golu.memory.learning")


class ActiveLearningEngine:
    """Detects, extracts, and memorizes personal facts and profile updates."""

    def __init__(self):
        pass

    def extract_and_learn(self, query: str) -> Optional[Dict[str, Any]]:
        """Analyzes query for explicit self-disclosure or learning commands.
        Returns Dict with learned key, value, and acknowledgement if learned, else None.
        """
        text = query.strip()
        lower = text.lower()
        learned_items = []

        # 1. Name disclosure: "my name is Gouransh Soni", "mera naam X hai", "i am called X"
        name_match = re.search(r"(?:my name is|mera naam|i am called|call me)\s+([A-Za-z\s]+?)(?:\s+and|\s+aur|\s+hai|\.|$)", text, flags=re.IGNORECASE)
        if name_match:
            raw_name = name_match.group(1).strip()
            cleaned_name = " ".join([w.capitalize() for w in raw_name.split() if w.lower() not in ("hai", "ka", "ki", "mera", "naam", "and", "aur", "the")])
            if cleaned_name and len(cleaned_name) >= 3:
                parts = cleaned_name.split()
                vault_sql.set_value(
                    canonical_key="full_name",
                    value=cleaned_name,
                    category="personal",
                    aliases=[cleaned_name.lower(), "my name", "mera naam", "full name", "name", "who am i", parts[0].lower()]
                )
                if len(parts) > 1:
                    vault_sql.set_value("first_name", parts[0], "personal", ["first name", "pehla naam", parts[0].lower()])
                    vault_sql.set_value("last_name", " ".join(parts[1:]), "personal", ["last name", "surname"])
                logger.info("Active Learning: Learned user full name -> %s", cleaned_name)
                learned_items.append(f"naam: {cleaned_name}")

        # 2. College / Education disclosure: "i completed my graduation from X", "my college is X", "mera college X hai"
        college_match = re.search(
            r"(?:graduated from|graduation from|completed my graduation from|studied at|my college is|my university is|mera college|mera university)\s+([A-Za-z0-9\s,]+?)(?:\s+hai|\.|$)",
            text,
            flags=re.IGNORECASE
        )
        if college_match:
            raw_college = college_match.group(1).strip()
            cleaned_college = " ".join([w.capitalize() if w.lower() not in ("of", "and", "in", "at") else w.lower() for w in raw_college.split() if w.lower() not in ("hai", "se", "mera", "college")])
            if cleaned_college and len(cleaned_college) >= 4:
                vault_sql.set_value(
                    canonical_key="university",
                    value=cleaned_college,
                    category="education",
                    aliases=[cleaned_college.lower(), "college", "university", "my college", "mera college", "alma mater"]
                )
                logger.info("Active Learning: Learned user university -> %s", cleaned_college)
                learned_items.append(f"college: {cleaned_college}")

        # 3. Email disclosure: "my email is X", "mera email X hai"
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        if email_match and any(w in lower for w in ["email", "mail", "contact"]):
            email_val = email_match.group(0).strip()
            vault_sql.set_value("email", email_val, "contact", ["email", "email address", "my email", "mera email"])
            logger.info("Active Learning: Learned user email -> %s", email_val)
            learned_items.append(f"email: {email_val}")

        # 4. Phone disclosure: "my phone is X", "mera phone X hai"
        phone_match = re.search(r"(?:\+91[\-\s]?)?[6789]\d{9}", text)
        if phone_match and any(w in lower for w in ["phone", "mobile", "number", "call"]):
            phone_val = phone_match.group(0).strip()
            vault_sql.set_value("phone", phone_val, "contact", ["phone", "mobile", "my phone", "mera phone"])
            logger.info("Active Learning: Learned user phone -> %s", phone_val)
            learned_items.append(f"phone: {phone_val}")

        # 5. General "remember that X" / "yaad rakhna ki X"
        remember_match = re.search(r"(?:remember that|yaad rakhna ki|note down that|remember)\s+(.+)", text, flags=re.IGNORECASE)
        if remember_match:
            fact = remember_match.group(1).strip()
            if fact:
                doc_id = f"fact_{abs(hash(fact)) % 100000}"
                rag_store.add_documents([{
                    "id": doc_id,
                    "text": f"User fact: {fact}",
                    "metadata": {"source": "active_learning_fact", "category": "user_memory"}
                }])
                logger.info("Active Learning: Stored unstructured user fact in RAG: %s", fact)
                learned_items.append(f"fact: '{fact}'")

        if learned_items:
            details_str = ", ".join(learned_items)
            ack_msg = f"Haan bhai, bilkul! Maine yaad rakh liya aur secure vault me save kar diya hai ({details_str})."
            return {
                "key": "multi" if len(learned_items) > 1 else learned_items[0].split(":")[0],
                "value": details_str,
                "ack": ack_msg
            }

        return None


# Global active learning engine singleton
active_learning_engine = ActiveLearningEngine()
