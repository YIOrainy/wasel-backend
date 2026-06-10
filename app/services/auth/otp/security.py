import hmac
from hashlib import sha256
from secrets import randbelow

from app.config import settings

CODE_LENGTH = 6


def generate_code() -> str:
    return f"{randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(code: str) -> str:
    return hmac.new(settings.otp_pepper.encode(), code.encode(), sha256).hexdigest()


def verify_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code), code_hash)
