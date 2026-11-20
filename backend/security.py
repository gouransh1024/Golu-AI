"""
Project Golu: Defense-in-Depth Security Architecture
Module: backend/security.py

Implements:
1. Windows DPAPI Master Key storage via keyring (Windows Credential Manager)
2. AES-256 (Fernet) encryption for local SQLite Vault
3. 256-bit rotating session secret (X-Golu-Token) for localhost authentication
4. XML Prompt-Injection Firewall & Untrusted Input Fencing
5. Sensitive Field Deny-List Guard (passwords, OTPs, CVVs, Aadhaar, PAN)
"""

import os
import re
import secrets
import base64
import logging
from pathlib import Path
from typing import Optional, Tuple
from cryptography.fernet import Fernet
import keyring

logger = logging.getLogger("golu.security")

SERVICE_NAME = "golu_ai"
MASTER_KEY_USER = "master_vault_key"
TOKEN_FILE = Path(__file__).resolve().parent.parent / "data" / ".session_token"
KEY_FALLBACK_FILE = Path(__file__).resolve().parent.parent / "data" / ".vault_master.key"

# Sensitive keywords that must never be auto-filled or suggested
SENSITIVE_DENY_LIST = {
    "password", "passwd", "pwd", "secret", "cvv", "cvc", "otp", "pin",
    "card_number", "credit_card", "debit_card", "expiry", "card_expiry", "exp_date", "card_exp",
    "aadhaar", "aadhar", "pan", "pan_card", "pan_number", "ssn", "social_security",
    "netbanking", "bank_account_pin", "auth_token", "api_key", "secret_key", "recovery_key"
}

# Prompt injection signatures to flag and neutralize
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"system\s*prompt",
    r"dump\s+(the\s+)?(vault|database|passwords?|keys?)",
    r"reveal\s+(the\s+)?(master|encryption|api)\s+key",
    r"dan\s+mode",
    r"jailbreak",
    r"<script.*?>.*?</script>",
    r"eval\(.*?\)",
    r"exfiltrate",
    r"output\s+all\s+(data|records|vault)"
]


class SecurityManager:
    """Manages DPAPI master key, AES-256 encryption, session authentication, and firewall."""

    def __init__(self):
        self._ensure_data_dir()
        self._fernet: Optional[Fernet] = None
        self._session_token: str = self._init_session_token()
        self._init_cipher()

    def _ensure_data_dir(self):
        data_dir = TOKEN_FILE.parent
        data_dir.mkdir(parents=True, exist_ok=True)

    def _init_cipher(self):
        """Retrieve or initialize the master AES-256 key via Windows DPAPI (keyring)."""
        key_str = None
        try:
            key_str = keyring.get_password(SERVICE_NAME, MASTER_KEY_USER)
        except Exception as e:
            logger.warning(f"Keyring DPAPI retrieval failed: {e}. Checking fallback file.")

        if not key_str:
            if KEY_FALLBACK_FILE.exists():
                try:
                    key_str = KEY_FALLBACK_FILE.read_text(encoding="utf-8").strip()
                except Exception as e:
                    logger.warning(f"Failed to read key fallback: {e}")

        if not key_str:
            # Generate new 256-bit AES Fernet key
            new_key = Fernet.generate_key().decode("utf-8")
            saved_to_dpapi = False
            try:
                keyring.set_password(SERVICE_NAME, MASTER_KEY_USER, new_key)
                saved_to_dpapi = True
                logger.info("Successfully provisioned master encryption key into Windows DPAPI.")
            except Exception as e:
                logger.warning(f"Could not save master key to DPAPI keyring: {e}")

            # Keep fallback copy
            KEY_FALLBACK_FILE.write_text(new_key, encoding="utf-8")
            key_str = new_key
            logger.info("Master AES-256 encryption key initialized.")

        self._fernet = Fernet(key_str.encode("utf-8"))

    def _init_session_token(self) -> str:
        """Generates or loads the 256-bit rotating session secret (X-Golu-Token)."""
        token = secrets.token_hex(32)  # 256-bit cryptographic token
        try:
            TOKEN_FILE.write_text(token, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write session token: {e}")
        return token

    @property
    def session_token(self) -> str:
        return self._session_token

    def verify_token(self, token: Optional[str]) -> bool:
        """Constant-time token comparison to avoid timing attacks."""
        if not token:
            return False
        return secrets.compare_digest(token.strip(), self._session_token)

    def rotate_session_token(self) -> str:
        """Rotates session token for fresh pairing."""
        self._session_token = self._init_session_token()
        return self._session_token

    def encrypt_value(self, plaintext: str) -> str:
        """Encrypts a plaintext value using AES-256 (Fernet)."""
        if not plaintext:
            return ""
        if not self._fernet:
            raise RuntimeError("SecurityManager cipher not initialized")
        encrypted_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt_value(self, ciphertext: str) -> str:
        """Decrypts an AES-256 encrypted ciphertext into plaintext."""
        if not ciphertext:
            return ""
        if not self._fernet:
            raise RuntimeError("SecurityManager cipher not initialized")
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError("Invalid ciphertext or corrupted key")

    # ================= Prompt Injection Firewall =================

    @staticmethod
    def is_sensitive_field(field_name: str, field_type: str = "text", field_label: str = "") -> bool:
        """
        Deny-List Filter:
        Returns True if the field is a password, OTP, CVV, Card, Aadhaar, PAN, or PIN.
        Checks both field_name, field_type, and field_label.
        """
        if field_type.lower() in {"password", "hidden"}:
            return True

        combined = f"{field_name} {field_label}".lower()
        normalized = re.sub(r"[^a-zA-Z0-9]", "_", combined)
        for blocked in SENSITIVE_DENY_LIST:
            if blocked in normalized:
                return True
        return False

    @staticmethod
    def inspect_and_fence_input(raw_input: str) -> Tuple[str, bool, str]:
        """
        Prompt-Injection Firewall:
        1. Checks for injection attacks / jailbreak patterns.
        2. Neutralizes XML / script tags.
        3. Wraps safely into strict XML data fence: <untrusted_input>...</untrusted_input>.
        Returns: (fenced_string, is_safe, reason)
        """
        if not raw_input:
            return "<untrusted_input></untrusted_input>", True, "empty"

        cleaned = raw_input.strip()

        # Check injection patterns
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                logger.warning(f"Prompt injection detected with pattern: {pattern}")
                # Neutralize injection attempt
                neutralized = re.sub(pattern, "[BLOCKED_INJECTION_PATTERN]", cleaned, flags=re.IGNORECASE)
                # Escape XML brackets to prevent prompt escape
                escaped = neutralized.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                fenced = f"<untrusted_input>{escaped}</untrusted_input>"
                return fenced, False, f"Malicious injection pattern detected: {pattern}"

        # Clean normal string
        escaped = cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        fenced = f"<untrusted_input>{escaped}</untrusted_input>"
        return fenced, True, "safe"

    @staticmethod
    def sanitize_input(raw_input: str) -> str:
        """Sanitizes raw input against prompt injections and returns cleaned string."""
        fenced, is_safe, _ = SecurityManager.inspect_and_fence_input(raw_input)
        clean = fenced.replace("<untrusted_input>", "").replace("</untrusted_input>", "")
        return clean.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


# Global singleton instance
security_manager = SecurityManager()
