"""
FinTech Agent — Core Logging Configuration
Provides structured logging with comprehensive sensitive value redaction.
Protects Google API keys, MongoDB URI credentials, Bearer tokens, OpenAI/Anthropic/Groq keys,
and generic secret/password patterns.
"""

import logging
import re
import sys
from typing import List, Tuple

# Comprehensive secret redaction rules: (pattern, replacement)
REDACT_RULES: List[Tuple[re.Pattern, str]] = [
    # 1. MongoDB URIs (standard & srv) with credentials: mongodb://user:pass@host
    (re.compile(r"(mongodb(?:\+srv)?:\/\/[^\s:@'\"]+:)([^@\s'\"]+)(@)", re.IGNORECASE), r"\1[REDACTED]\3"),
    # 2. URL query parameters (e.g. ?key=..., &api_key=..., ?secret=..., ?token=...)
    (re.compile(r"([?&](?:api[_-]?key|apikey|key|secret|token|password)=)([^&\s'\"`]+)", re.IGNORECASE), r"\1[REDACTED]"),
    # 3. Google API Keys (AIza...)
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{20,50}\b"), "[REDACTED]"),
    # 4. Anthropic, OpenAI, Groq Keys
    (re.compile(r"\bsk-ant-[a-zA-Z0-9_\-]{15,}\b", re.IGNORECASE), "[REDACTED]"),
    (re.compile(r"\bsk-proj-[a-zA-Z0-9_\-]{15,}\b", re.IGNORECASE), "[REDACTED]"),
    (re.compile(r"\bsk-[a-zA-Z0-9_\-]{15,}\b", re.IGNORECASE), "[REDACTED]"),
    (re.compile(r"\bgsk_[a-zA-Z0-9_\-]{15,}\b", re.IGNORECASE), "[REDACTED]"),
    # 5. Bearer / Basic tokens & Authorization headers
    (re.compile(r"((?:Bearer|Basic)\s+)[a-zA-Z0-9_\-\.\=\+\/]{15,}", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(Authorization\s*:\s*(?:Bearer\s+)?)[a-zA-Z0-9_\-\.\=\+\/]{15,}", re.IGNORECASE), r"\1[REDACTED]"),
    # 6. Generic key-value pairs (api_key=..., password: ..., client_secret: ..., etc.)
    (re.compile(r"((?:api[_-]?key|password|client_secret|access_token|refresh_token)\s*[:=]\s*)['\"]?([^,;'\"\s]+)['\"]?", re.IGNORECASE), r"\1[REDACTED]"),
]


def sanitize_error_message(msg: str) -> str:
    """Scrubs any potential keys, tokens, or credentials from user-facing error messages and logs."""
    if not msg:
        return ""
    sanitized = str(msg)
    for pattern, replacement in REDACT_RULES:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class RedactingFormatter(logging.Formatter):
    """Custom formatter that scrubs sensitive keys and credentials from log messages."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return sanitize_error_message(msg)


def setup_logger(name: str = "fintech_agent", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a centralized application logger."""
    logger_instance = logging.getLogger(name)
    if not logger_instance.handlers:
        logger_instance.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        fmt = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
        formatter = RedactingFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        logger_instance.addHandler(handler)
        logger_instance.propagate = False
    return logger_instance


logger = setup_logger()
