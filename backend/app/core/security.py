"""API Key encryption, decryption, and masking using cryptography.fernet."""

from __future__ import annotations

from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_config
from app.core.exceptions import AppError


def _get_or_create_fernet(secret_path: Path | None = None) -> Fernet:
    """Load local machine Fernet key or generate one on first startup."""
    path = secret_path or get_config().secret_key_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        key = path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        path.write_bytes(key)
    return Fernet(key)


def encrypt_api_key(plain_key: str, secret_path: Path | None = None) -> str:
    """Encrypt plaintext API Key into a UTF-8 Fernet token string."""
    cleaned = plain_key.strip()
    if not cleaned:
        raise AppError(
            code="INVALID_API_KEY",
            message="API Key 不能为空",
            status_code=400,
        )
    fernet = _get_or_create_fernet(secret_path)
    return fernet.encrypt(cleaned.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_key: str, secret_path: Path | None = None) -> str:
    """Decrypt Fernet token string back to plaintext API Key."""
    if not encrypted_key:
        raise AppError(
            code="MISSING_API_KEY",
            message="未配置有效的 API Key",
            status_code=400,
        )
    fernet = _get_or_create_fernet(secret_path)
    try:
        return fernet.decrypt(encrypted_key.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError(
            code="API_KEY_DECRYPT_FAILED",
            message="模型档案 API Key 解密失败，可能本机密钥已变更，请重新填写 API Key",
            detail=str(exc),
            status_code=500,
        ) from exc


def mask_api_key(plain_key: str) -> str:
    """Mask plaintext API key for safe display in frontend responses (e.g. sk-****1234)."""
    cleaned = plain_key.strip()
    if len(cleaned) <= 4:
        return "****"
    if len(cleaned) <= 8:
        return f"{cleaned[:2]}****{cleaned[-2:]}"
    prefix = cleaned[:3] if not cleaned.startswith("sk-") else "sk-"
    suffix = cleaned[-4:]
    return f"{prefix}****{suffix}"


def safe_mask_encrypted_key(encrypted_key: str, secret_path: Path | None = None) -> str:
    """Decrypt and mask an encrypted key without raising if key was corrupted."""
    try:
        plain = decrypt_api_key(encrypted_key, secret_path)
        return mask_api_key(plain)
    except AppError:
        return "****(需重新设置)"
