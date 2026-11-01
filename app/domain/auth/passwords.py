import base64
import hashlib
import hmac
import secrets

_N = 2**14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()


def hash_password(password: str) -> str:
    """Return `scrypt$n$r$p$salt$hash`; the parameters travel with the hash."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash. A malformed hash never verifies."""
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        expected_bytes = base64.b64decode(expected, altchars=b"-_", validate=True)
        digest = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt, altchars=b"-_", validate=True),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected_bytes),
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest, expected_bytes)
