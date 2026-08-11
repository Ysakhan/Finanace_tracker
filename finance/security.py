"""
Encryption utilities for sensitive user data in FinRoll.
Pure Python standard library implementation using SHA-256 derived key stream & Base64 encoding.
No external pip dependencies required.
"""
import base64
import hashlib
from django.conf import settings


def _get_key_stream(length: int, salt: bytes) -> bytes:
    """Generate a pseudo-random key stream derived from SECRET_KEY and salt."""
    key = settings.SECRET_KEY.encode('utf-8')
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hashlib.sha256(key + salt + counter.to_bytes(4, 'big')).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])


def encrypt_data(text: str) -> str:
    """Encrypt plaintext string using standard library cipher. Returns string token starting with 'ENC:'."""
    if not text:
        return ""
    try:
        raw_bytes = text.encode('utf-8')
        salt = hashlib.md5(settings.SECRET_KEY.encode()).digest()[:8]
        key_stream = _get_key_stream(len(raw_bytes), salt)
        cipher_bytes = bytes(b ^ k for b, k in zip(raw_bytes, key_stream))
        encoded = base64.urlsafe_b64encode(salt + cipher_bytes).decode('ascii')
        return "ENC:" + encoded
    except Exception:
        return text


def decrypt_data(text: str) -> str:
    """Decrypt string token starting with 'ENC:'. Returns plaintext string."""
    if not text or not isinstance(text, str) or not text.startswith("ENC:"):
        return text
    try:
        raw_encoded = text[4:]
        data = base64.urlsafe_b64decode(raw_encoded.encode('ascii'))
        salt = data[:8]
        cipher_bytes = data[8:]
        key_stream = _get_key_stream(len(cipher_bytes), salt)
        plain_bytes = bytes(c ^ k for c, k in zip(cipher_bytes, key_stream))
        return plain_bytes.decode('utf-8')
    except Exception:
        return text
