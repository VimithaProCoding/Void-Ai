"""Secure API-key storage for Void-Ai using the Python keyring package."""

from __future__ import annotations

import logging
from typing import Dict, Iterable, Mapping

SERVICE_NAME = "Void-Ai"
SUPPORTED_PROVIDERS = ("Groq AI", "OpenRouter", "Ollama Cloud")

try:
    import keyring
    from keyring.errors import PasswordDeleteError
except Exception:  # pragma: no cover - dependency availability is environment-specific
    keyring = None

    class PasswordDeleteError(Exception):
        pass


def is_available() -> bool:
    return keyring is not None


def _normalize_provider(provider: str) -> str:
    return str(provider or "").strip()


def get_api_key(provider: str) -> str:
    provider = _normalize_provider(provider)
    if not provider or keyring is None:
        return ""
    try:
        return str(keyring.get_password(SERVICE_NAME, provider) or "").strip()
    except Exception as exc:
        logging.error("Keyring read failed for %s: %s", provider, exc)
        return ""


def set_api_key(provider: str, value: str) -> bool:
    provider = _normalize_provider(provider)
    value = str(value or "").strip()
    if not provider or keyring is None:
        logging.error("Cannot save API key: keyring package is unavailable.")
        return False

    try:
        if value:
            keyring.set_password(SERVICE_NAME, provider, value)
        else:
            delete_api_key(provider)
        return True
    except Exception as exc:
        logging.error("Keyring write failed for %s: %s", provider, exc)
        return False


def delete_api_key(provider: str) -> bool:
    provider = _normalize_provider(provider)
    if not provider or keyring is None:
        return False

    try:
        keyring.delete_password(SERVICE_NAME, provider)
    except PasswordDeleteError:
        return True
    except Exception as exc:
        logging.error("Keyring delete failed for %s: %s", provider, exc)
        return False
    return True


def load_provider_keys(providers: Iterable[str] = SUPPORTED_PROVIDERS) -> Dict[str, str]:
    return {provider: get_api_key(provider) for provider in providers}


def migrate_legacy_keys(legacy_keys: Mapping[str, str] | None) -> bool:
    """Move plaintext keys from old appdata into keyring without overwriting an existing keyring value."""
    if not isinstance(legacy_keys, Mapping):
        return False
    if keyring is None:
        logging.error("Legacy API-key migration skipped: install the 'keyring' package.")
        return False

    migrated = False
    for provider, value in legacy_keys.items():
        provider = _normalize_provider(provider)
        value = str(value or "").strip()
        if not provider or not value:
            continue
        try:
            current = str(keyring.get_password(SERVICE_NAME, provider) or "").strip()
            if not current:
                keyring.set_password(SERVICE_NAME, provider, value)
                migrated = True
        except Exception as exc:
            logging.error("Could not migrate legacy key for %s: %s", provider, exc)
    return migrated


def clear_all_keys(providers: Iterable[str] = SUPPORTED_PROVIDERS) -> bool:
    """Remove all Void-Ai provider credentials from the keyring."""
    ok = True
    for provider in providers:
        if not delete_api_key(provider):
            ok = False
    return ok
