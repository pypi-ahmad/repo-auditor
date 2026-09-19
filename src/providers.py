"""Provider discovery and OpenAI SDK client setup honoring hard environment rules."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from openai import OpenAI


@dataclass
class ProviderConfig:
    name: str
    models: List[str]
    default_model: str
    base_url: Optional[str]
    api_key_env_var: str
    has_api_key: bool


def get_available_providers() -> Dict[str, ProviderConfig]:
    """Inspects environment and returns only configured providers.

    Never exposes secret values; only checks presence.
    """
    providers: Dict[str, ProviderConfig] = {}

    # 1. Agnes AI (Default)
    agnes_key = os.environ.get("AGNESAI_API_KEY")
    has_agnes = bool(agnes_key and agnes_key.strip())
    providers["Agnes AI"] = ProviderConfig(
        name="Agnes AI",
        models=["agnes-3.0-flash"],
        default_model="agnes-3.0-flash",
        base_url="https://apihub.agnes-ai.com/v1",
        api_key_env_var="AGNESAI_API_KEY",
        has_api_key=has_agnes,
    )

    # 2. OpenAI / Custom Gateway (Optional)
    openai_key = os.environ.get("OPENAI_API_KEY")
    openai_base = os.environ.get("OPENAI_BASE_URL")
    if openai_key and openai_key.strip() and openai_base and openai_base.strip():
        providers["OpenAI (Custom)"] = ProviderConfig(
            name="OpenAI (Custom)",
            models=["gpt-5.6-luna", "gpt-5.6-terra"],
            default_model="gpt-5.6-luna",
            base_url=openai_base.strip(),
            api_key_env_var="OPENAI_API_KEY",
            has_api_key=True,
        )

    # 3. Google Gemini (Optional)
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key and google_key.strip():
        providers["Google Gemini"] = ProviderConfig(
            name="Google Gemini",
            models=["gemini-3.5-flash-lite", "gemini-3.7-flash"],
            default_model="gemini-3.5-flash-lite",
            base_url=None,
            api_key_env_var="GOOGLE_API_KEY",
            has_api_key=True,
        )

    return providers


def create_openai_client(provider_name: str) -> Optional[OpenAI]:
    """Creates an OpenAI SDK client for the selected provider if key exists."""
    providers = get_available_providers()
    cfg = providers.get(provider_name)
    if not cfg:
        return None

    api_key = os.environ.get(cfg.api_key_env_var)
    if not api_key:
        return None

    if cfg.base_url:
        return OpenAI(api_key=api_key, base_url=cfg.base_url)
    return OpenAI(api_key=api_key)
