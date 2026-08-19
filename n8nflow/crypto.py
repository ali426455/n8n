"""Credential encryption. On Streamlit Cloud put encryption_key in secrets."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
KEY_FILE = DATA_DIR / ".key"


def _secrets_key() -> str | None:
    try:
        import streamlit as st

        val = st.secrets.get("encryption_key")
        if val:
            return str(val)
    except Exception:
        pass
    return None


def normalize_key(raw: str) -> bytes:
    raw = (raw or "").strip()
    if not raw:
        raw = "n8n-flow-dev-key"
    try:
        candidate = raw.encode("utf-8")
        Fernet(candidate)
        return candidate
    except Exception:
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


def load_or_create_raw_key() -> str:
    secret = _secrets_key()
    if secret:
        return secret
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    generated = Fernet.generate_key().decode("utf-8")
    try:
        KEY_FILE.write_text(generated, encoding="utf-8")
    except Exception:
        pass
    return generated


def get_fernet() -> Fernet:
    return Fernet(normalize_key(load_or_create_raw_key()))


def encrypt_text(plain: str) -> str:
    return get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    try:
        return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Cannot decrypt credential. Set the same encryption_key in Streamlit secrets."
        ) from exc


def key_source() -> str:
    if _secrets_key():
        return "secrets"
    if KEY_FILE.exists():
        return "file"
    return "ephemeral"
