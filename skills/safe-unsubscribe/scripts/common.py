"""Shared helpers for the NoThanks / Safe Unsubscribe scripts. Standard library only."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import sys
from email.utils import parseaddr
from urllib.parse import parse_qsl, urlsplit, unquote

SCHEMA_VERSION = 1

# How a sender can be unsubscribed from, safest first.
METHODS = ("rfc8058-post", "mailto", "preference-page", "none", "unsafe")
USABLE_METHODS = ("rfc8058-post", "mailto", "preference-page")
ACTIONS = ("unsubscribe", "create_rule", "block_or_report", "keep")
CATEGORIES = (
    "promotional",
    "newsletter",
    "community",
    "transactional",
    "personal",
    "suspicious",
    "unknown",
)
RISKS = ("low", "medium", "high")
ENGAGEMENTS = ("low", "medium", "high", "unknown")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- I/O
def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data, private=False):
    """Write JSON. Private files (unsubscribe targets, tokens) are mode 0600."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    if private:
        os.chmod(path, 0o600)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_schema(name):
    return read_json(os.path.join(SKILL_DIR, "schemas", name))


def die(message, code=2):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


# ------------------------------------------------------------------- identities
def split_sender(value):
    """Return (display_name, lower-cased address) from a From header value."""
    name, address = parseaddr(value or "")
    return name.strip(), address.strip().lower()


_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "edu", "ac"}


def registrable_domain(host):
    """Approximate registrable domain (no public-suffix list; stdlib only)."""
    labels = [p for p in (host or "").lower().strip(".").split(".") if p]
    if len(labels) <= 2:
        return ".".join(labels)
    if len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def address_domain(address):
    return address.rpartition("@")[2] if "@" in address else ""


# Fields the AI layer may refine. Everything else in a candidate is script-derived and locked.
EDITABLE_FIELDS = ("category", "recommended_action", "confidence", "reason")


def immutable_digest(candidates):
    """Digest over script-derived facts (risk, method, exclusions, counts...) so edits to
    them are detected by validate_plan.py. Tamper-evidence, not a cryptographic secret."""
    locked = [{k: v for k, v in c.items() if k not in EDITABLE_FIELDS} for c in candidates]
    return hashlib.sha256(json.dumps(locked, sort_keys=True).encode("utf-8")).hexdigest()


def candidate_id(address):
    """Stable local ID derived from the normalized sender address."""
    return "c_" + hashlib.sha256(address.lower().encode("utf-8")).hexdigest()[:12]


# -------------------------------------------------------------------- redaction
def redact_url(url):
    """Keep scheme/host; mask token-looking path segments and the whole query."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    segments = [
        "***" if len(seg) >= 12 or re.search(r"\d{4,}", seg) else seg
        for seg in parts.path.split("/")
    ]
    query = "?<redacted>" if parts.query else ""
    return f"{parts.scheme}://{parts.hostname or ''}{'/'.join(segments)}{query}"


def redact_email(address):
    local, _, domain = address.partition("@")
    if len(local) > 6:
        local = local[:2] + "***"
    return f"{local}@{domain}"


# ------------------------------------------------------------ unsubscribe targets
_MAX_URL = 2048
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".corp")


def check_https_url(url):
    """Static validation of an unsubscribe URL. Returns (ok, reason)."""
    if not url or len(url) > _MAX_URL:
        return False, "empty or too long"
    if any(ord(c) < 33 or ord(c) == 127 for c in url):
        return False, "whitespace or control characters"
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False, "malformed URL"
    if parts.scheme.lower() != "https":
        return False, f"scheme '{parts.scheme}' is not https"
    host = (parts.hostname or "").lower()
    if not host:
        return False, "missing host"
    if parts.username or parts.password:
        return False, "credentials in URL"
    if port not in (None, 443):
        return False, f"non-standard port {port}"
    try:
        ipaddress.ip_address(host)
        return False, "IP-address host"
    except ValueError:
        pass
    if not host.isascii() or "xn--" in host:
        return False, "internationalized/punycode host"
    if "." not in host or host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        return False, "local or non-public host"
    return True, "ok"


_MAILTO_ADDR = re.compile(r"^[A-Za-z0-9._%+=/\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def parse_mailto(uri):
    """Parse a mailto: unsubscribe target. Returns (dict, reason); dict is None if rejected."""
    try:
        parts = urlsplit(uri)
    except ValueError:
        return None, "malformed mailto"
    if parts.scheme.lower() != "mailto":
        return None, "not a mailto URI"
    address = unquote(parts.path).strip()
    if not _MAILTO_ADDR.match(address):
        return None, "invalid or multiple recipients"
    subject, body = "unsubscribe", ""
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        key = key.lower()
        if key == "subject":
            subject = value
        elif key == "body":
            body = value
        else:
            return None, f"unsupported mailto field '{key}'"
    if "\n" in subject or "\r" in subject or len(subject) > 200:
        return None, "invalid subject"
    if len(body) > 1000:
        return None, "body too long"
    return {"address": address.lower(), "subject": subject, "body": body}, "ok"


# ------------------------------------------------- tiny JSON Schema subset validator
_TYPES = {"string": str, "boolean": bool, "array": list, "object": dict, "null": type(None)}


def _type_ok(value, type_name):
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[type_name])


def validate_schema(instance, schema, path="$"):
    """Validate against the JSON Schema subset used by schemas/*.json. Returns error list."""
    errors = []
    expected = schema.get("type")
    if expected is not None:
        names = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(instance, n) for n in names):
            return [f"{path}: expected {expected}, got {type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in {schema['enum']}")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if len(instance) > schema.get("maxLength", 10**9):
            errors.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required '{key}'")
        for key, value in instance.items():
            if key in props:
                errors.extend(validate_schema(value, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property '{key}'")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems") and len({json.dumps(i, sort_keys=True) for i in instance}) != len(instance):
            errors.append(f"{path}: items must be unique")
        if "items" in schema:
            for idx, item in enumerate(instance):
                errors.extend(validate_schema(item, schema["items"], f"{path}[{idx}]"))
    return errors
