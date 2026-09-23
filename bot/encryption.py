import base64

from cryptography.fernet import Fernet

from bot.config import get_settings


class TokenEncryption:
    def __init__(self):
        self._fernet: Fernet | None = None

    def _get_fernet(self) -> Fernet:
        if self._fernet is None:
            settings = get_settings()
            key = settings.encryption_key.encode()
            if len(key) != 44:
                key = base64.urlsafe_b64decode(key)
            self._fernet = Fernet(key)
        return self._fernet

    def encrypt(self, token: str) -> bytes:
        fernet = self._get_fernet()
        return fernet.encrypt(token.encode())

    def decrypt(self, encrypted_token: bytes) -> str:
        fernet = self._get_fernet()
        return fernet.decrypt(encrypted_token).decode()


token_encryption = TokenEncryption()


def encrypt_token(token: str) -> bytes:
    return token_encryption.encrypt(token)


def decrypt_token(encrypted_token: bytes) -> str:
    return token_encryption.decrypt(encrypted_token)
