import hashlib


def hash_email(email: str | None) -> str:
    """Lowercase + trim + SHA-256 hex, per Meta CAPI advanced-matching spec."""
    if not email:
        return ""
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
