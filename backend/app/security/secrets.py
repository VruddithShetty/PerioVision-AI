"""Secret loading and a repository scan for hardcoded credentials.

Secrets come from AWS Secrets Manager when USE_AWS_SECRETS=true, otherwise from the
environment. `get_secret` is explicit about failure: a missing *required* secret raises
rather than returning None, so a misconfigured deployment stops at startup instead of
running with authentication silently disabled.
"""
from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)


class SecretNotFound(RuntimeError):
    """A required secret is not configured."""


def _from_aws(secret_name: str) -> str | None:
    try:
        import json

        import boto3
    except ImportError:
        logger.error("USE_AWS_SECRETS is set but boto3 is not installed.")
        return None
    try:
        response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_name)
    except Exception as exc:  # network, permissions, missing secret
        logger.error("Could not read '%s' from AWS Secrets Manager: %s", secret_name, exc)
        return None
    raw = response.get("SecretString")
    if not raw:
        return None
    try:
        return json.loads(raw).get(secret_name, raw)
    except ValueError:
        return raw  # the secret is a bare string, not a JSON document


def get_secret(secret_name: str, *, required: bool = False, default: str | None = None) -> str | None:
    """Read a secret from AWS Secrets Manager (if enabled) or the environment.

    Raises SecretNotFound when `required` and nothing is configured, so the failure is
    loud at startup rather than a None that surfaces much later as a confusing error.
    """
    value = None
    if os.environ.get("USE_AWS_SECRETS", "").lower() == "true":
        value = _from_aws(secret_name)
    if not value:
        value = os.environ.get(secret_name)
    if not value:
        if required:
            raise SecretNotFound(f"Required secret '{secret_name}' is not configured.")
        return default
    return value


# ---------- repository scan ----------
# Narrow patterns: each needs a credential-shaped value, not just any string, so the
# scan stays useful instead of drowning real findings in false positives.
PATTERNS: dict[str, re.Pattern] = {
    "MONGODB_URI": re.compile(r'mongodb(?:\+srv)?://[^\s"\'@/]+:[^\s"\'@/]+@'),
    "AWS_ACCESS_KEY": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "PRIVATE_KEY_BLOCK": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    "JWT_LITERAL": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    "SLACK_TOKEN": re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}"),
    "GITHUB_TOKEN": re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36}\b"),
    "PASSWORD_ASSIGNMENT": re.compile(
        r'(?i)\b(?:password|passwd|secret|api_key|apikey|token)\s*[:=]\s*["\'][^"\']{8,}["\']'),
}

# Values that look like secrets but are placeholders, lookups or obvious examples.
SAFE_VALUE = re.compile(
    r'(?i)(os\.(?:environ|getenv)|getenv\(|get_secret\(|<[^>]+>|\{\{|\$\{|\{[A-Za-z_]|'
    # A value generated at runtime from a CSPRNG is not a committed secret, however
    # long the literal prefix in front of it happens to be.
    r'secrets\.token|token_hex|token_urlsafe|token_bytes|uuid4\(|gensalt\(|'
    r'your[-_ ]?|example|placeholder|changeme|dummy|sample|xxx+|\*{4,}|redacted|todo)')

# Build output and dependencies only. Retired code under legacy/ is deliberately
# scanned: it is excluded from linting, so a credential left there is otherwise
# invisible to every check the project runs.
SKIP_DIRS = {".git", "venv", ".venv", "node_modules", "__pycache__", ".pytest_cache",
             "dist", "build", ".mypy_cache", ".ruff_cache"}
# Lockfiles are nothing but integrity digests; scanning them is pure noise.
SKIP_FILES = {"secrets.py", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
              "poetry.lock", "Pipfile.lock", "composer.lock"}

# A SHA-256 digest and a 64-character hex key are the same shape, so neither entropy
# nor structure can separate them - only the surrounding text can. A line that
# announces itself as a hash is reporting a digest, which is public by design.
HASH_CONTEXT = re.compile(
    r"(?i)(sha\d{0,3}|integrity|digest|checksum|hash|etag|fingerprint|commit"
    r"|revision|signature|manifest_version|\broot\b|_root|_id|\bhmac\b|\bfp\b|\bsid\b|\bjti\b|nonce|salt|blob)")
# Test fixtures carry throwaway credentials by design. Scanning them trains people
# to ignore the warning, which is worse than not scanning. gitleaks still covers
# the whole repository, tests included, in CI.
SKIP_DIR_NAMES = {"tests", "test"}
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml",
                 ".toml", ".ini", ".cfg", ".env", ".sh", ".ps1", ".md"}


def shannon_entropy(value: str) -> float:
    """Bits of entropy per character; random credentials score well above prose."""
    if not value:
        return 0.0
    counts = Counter(value)
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


# Identifiers and paths: lowercase words joined by _ . - or /, which is what most
# false positives look like ("weights/landmark_detection_model").
_IDENTIFIER_LIKE = re.compile(r"^[a-z0-9]+(?:[_./-][a-z0-9]+)+$")
_HEX = re.compile(r"^[0-9a-f]+$", re.IGNORECASE)
_BASE64ISH = re.compile(r"^[A-Za-z0-9+/=_-]+$")


def _looks_like_a_key(literal: str) -> bool:
    """Judge a long quoted string on structure, not entropy alone.

    Entropy by itself cannot do this job here. Hex uses 16 symbols, so a genuinely
    random 64-character hex key - the format this project uses for
    FIELD_ENCRYPTION_KEY and JWT_SECRET_KEY - tops out near 4.0 bits per character,
    which is *lower* than readable snake_case such as
    "restoration_altered_fallback_15px" (4.02). Any threshold that catches the key
    also catches the status tag, and any threshold above the tag misses the key.

    So: reject identifier- and path-shaped strings first, then accept a
    uniform-alphabet blob - long hex, or mixed-case base64 with real variety.
    """
    if _IDENTIFIER_LIKE.match(literal):
        return False
    if _HEX.match(literal):
        # Random hex at key length. Shorter hex is usually a colour, id or hash prefix.
        return len(literal) >= 32
    if not _BASE64ISH.match(literal):
        return False
    # Mixed case plus digits is characteristic of generated tokens, not of prose.
    has_upper = any(c.isupper() for c in literal)
    has_lower = any(c.islower() for c in literal)
    has_digit = any(c.isdigit() for c in literal)
    return has_upper and has_lower and has_digit and shannon_entropy(literal) >= 4.2


def _is_high_entropy_literal(line: str) -> bool:
    """A long, key-shaped quoted string is worth flagging even with no keyword nearby."""
    if HASH_CONTEXT.search(line):
        return False  # a digest, not a secret
    for literal in re.findall(r'["\']([A-Za-z0-9+/=_-]{32,})["\']', line):
        if SAFE_VALUE.search(literal):
            continue
        if _looks_like_a_key(literal):
            return True
    return False


def run_secrets_audit(project_root: str | Path = ".") -> list[dict]:
    """Scan the tree for committed credentials. Returns one finding per match."""
    findings: list[dict] = []
    root = Path(project_root)
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        parts = set(path.parts)
        if path.name in SKIP_FILES or SKIP_DIRS & parts or SKIP_DIR_NAMES & parts:
            continue
        if path.name == ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            logger.debug("Could not read %s: %s", path, exc)
            continue
        for line_num, line in enumerate(text.splitlines(), 1):
            if len(line) > 4000 or SAFE_VALUE.search(line):
                continue
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append({"file": str(path), "line": line_num, "type": name})
            if _is_high_entropy_literal(line):
                findings.append({"file": str(path), "line": line_num, "type": "HIGH_ENTROPY_LITERAL"})
    return findings


def enforce_mongo_tls(mongo_uri: str) -> str:
    """Require TLS on any non-local MongoDB connection."""
    if not mongo_uri:
        return mongo_uri
    # Only for a database on a private container network (docker-compose): set
    # MONGO_REQUIRE_TLS=false. Anything reachable off that network must keep TLS.
    if os.getenv("MONGO_REQUIRE_TLS", "true").strip().lower() == "false":
        return mongo_uri
    host = mongo_uri.split("@")[-1]
    if "localhost" in host or "127.0.0.1" in host or "::1" in host or "mongo:" in host:
        return mongo_uri
    lowered = mongo_uri.lower()
    if "tls=true" in lowered or "ssl=true" in lowered:
        return mongo_uri
    separator = "&" if "?" in mongo_uri else "?"
    return f"{mongo_uri}{separator}tls=true&tlsAllowInvalidCertificates=false"
