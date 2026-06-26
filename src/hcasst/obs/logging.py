"""PHI-safe structured logging.

All patient data is treated as PHI: emails, phone numbers, SSNs, and dates of
birth are masked before anything is written to a log or persisted trace. This is
the control that makes durable audit logging HIPAA-*aligned* (not compliant —
compliance needs certified infrastructure beyond the software).
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

_CONFIGURED = False

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<email>"),
    # SSN before phone (more specific), keep ordering deliberate
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<ssn>"),
    # International / Indian phones: optional +CC then 6+ digits with -/.\/space
    (re.compile(r"(?<!\d)\+?\d{1,3}[-.\s]\d{4,5}[-.\s]\d{4,6}(?!\d)"), "<phone>"),
    # US phones: XXX-XXX-XXXX (with optional separators)
    (re.compile(r"(?<!\d)\d{3}[-.\s]\d{3}[-.\s]\d{4}(?!\d)"), "<phone>"),
    # Bare 10-15 digit runs (phone-like)
    (re.compile(r"(?<!\d)\d{10,15}(?!\d)"), "<phone>"),
    # DOB / dates: ISO YYYY-MM-DD -> keep year
    (re.compile(r"\b(\d{4})-\d{2}-\d{2}\b"), r"\1-**-**"),
    # DOB / dates: MM/DD/YYYY or M/D/YYYY -> keep year only
    (re.compile(r"\b\d{1,2}/\d{1,2}/(\d{4})\b"), r"**/**/\1"),
]


def mask_phi(text: str) -> str:
    if not text:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def mask_obj(obj: Any) -> Any:
    """Recursively mask PHI in str/dict/list structures for safe trace logging."""
    if isinstance(obj, str):
        return mask_phi(obj)
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(mask_obj(v) for v in obj)
    return obj


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
    root = logging.getLogger("hcasst")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"hcasst.{name}")

    