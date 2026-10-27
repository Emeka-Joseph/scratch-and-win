import re
import secrets

# Uppercase letters + digits without look-alikes (0/O, 1/I/L) so codes are easy to read aloud and type.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ"
_DIGITS = "23456789"


def random_code(length):
    """Random code that always mixes letters and numbers."""
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if any(c in _LETTERS for c in code) and any(c in _DIGITS for c in code):
            return code


def qr_token():
    return secrets.token_urlsafe(32)


def temp_password():
    return secrets.token_urlsafe(9)


def normalize_code(raw):
    return re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()


def normalize_email(raw):
    return (raw or "").strip().lower()


def normalize_mobile(raw):
    """Keep a leading + and digits only; convert a leading 00 to +."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    return digits


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def is_valid_email(email):
    return bool(EMAIL_RE.match(email or "")) and len(email) <= 190


def is_valid_mobile(mobile):
    digits = mobile.lstrip("+")
    return digits.isdigit() and 7 <= len(digits) <= 15


def slugify(text):
    text = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return text[:60] or "brand"
