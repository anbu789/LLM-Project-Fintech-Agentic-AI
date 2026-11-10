"""
FinTech Agent — Core Logging Configuration
Provides structured logging with sensitive value redaction.
"""

import logging
import re
import sys
from typing import Optional

# Secret redaction patterns
REDACT_PATTERNS = [
    re.compile(r"(api[_-]?key\s*[:=]\s*)['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?", re.IGNORECASE),
    re.compile(r"(password\s*[:=]\s*)['\"]?([^'\"\s]+)['\"]?", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE),
    re.compile(r"(sk-[a-zA-Z0-9_\-]{15,})", re.IGNORECASE),
    re.compile(r"(gsk_[a-zA-Z0-9_\-]{15,})", re.IGNORECASE),
]


def sanitize_error_message(msg: str) -> str:
    """Scrubs any potential keys, tokens, or credentials from user-facing error messages."""
    if not msg:
        return msg
    sanitized = str(msg)
    for pattern in REDACT_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


class RedactingFormatter(logging.Formatter):
    """Custom formatter that scrubs sensitive keys and credentials from log messages."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return sanitize_error_message(msg)


def setup_logger(name: str = "fintech_agent", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a centralized application logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        fmt = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
        formatter = RedactingFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger


logger = setup_logger()
