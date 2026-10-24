"""Hard exclusions: sensitive and transactional mail is never bulk-actioned.

This is deliberately conservative. A false positive only means a sender is kept;
a false negative could unsubscribe the user from something important.
"""
from __future__ import annotations

import re

SUBJECT_PATTERNS = {
    "security": r"\b(security alert|sign[- ]?in|log[- ]?in|new device|password|passcode|verification code|"
    r"verify your|one[- ]time|2fa|two[- ]factor|account recovery|suspicious activity|"
    r"confirm your (e-?mail|account))\b",
    "financial": r"\b(invoice|receipt|payment|statement|billing|bill|balance|refund|transaction|"
    r"tax|bank|mortgage|loan|credit card)\b",
    "purchase_delivery": r"\b(order (confirmation|#|no\.?|\d+)|your order|shipped|shipping|out for delivery|"
    r"delivered|tracking|booking|reservation|itinerary|e-?ticket)\b",
    "medical": r"\b(prescription|appointment|lab results?|medical|patient|insurance claim|health record)\b",
    "government": r"\b(government|irs|dmv|passport|visa application|court|jury|social security)\b",
}

SENDER_LOCAL_PATTERN = re.compile(
    r"^(security|account-?security|billing|invoices?|receipts?|orders?|payments?|fraud)\b", re.I
)

_COMPILED = {name: re.compile(p, re.I) for name, p in SUBJECT_PATTERNS.items()}


def subject_categories(subject):
    return {name for name, rx in _COMPILED.items() if rx.search(subject or "")}


def sender_categories(address):
    local = address.partition("@")[0]
    return {"sender_role"} if SENDER_LOCAL_PATTERN.match(local) else set()
