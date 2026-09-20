"""Provider discovery and OpenAI SDK client setup honoring hard environment rules."""

import os
from dataclasses import dataclass

from openai import OpenAI

from src.agnes_client import create_agnes_client


@dataclass
class ProviderConfig:
    """Non-secret metadata for an available model provider.

    Attributes:
        name: Display name for the provider.
        models: Supported model identifiers.
        default_model: Model selected by the app.
        base_url: OpenAI-compatible endpoint, when applicable.
        api_key_env_var: Name of the required process environment variable.
        has_api_key: Whether that variable is available without exposing its value.
    """

    name: str
    models: list[str]
    default_model: str
    base_url: str | None
    api_key_env_var: str
    has_api_key: bool


def get_available_providers() -> dict[str, ProviderConfig]:
    """Return the single supported Agnes AI provider.

    Never exposes secret values; only checks presence.

    Returns:
        The single supported Agnes provider keyed by its display name.
    """
    agnes_key = os.environ.get("AGNESAI_API_KEY")
    has_agnes = bool(agnes_key and agnes_key.strip())
    return {
        "Agnes AI": ProviderConfig(
            name="Agnes AI",
            models=["agnes-3.0-flash"],
            default_model="agnes-3.0-flash",
            base_url="https://apihub.agnes-ai.com/v1",
            api_key_env_var="AGNESAI_API_KEY",
            has_api_key=has_agnes,
        )
    }


def create_openai_client(provider_name: str) -> OpenAI | None:
    """Create the official OpenAI SDK client for a supported Agnes provider.

    Args:
        provider_name: Provider display name returned by ``get_available_providers``.

    Returns:
        A configured SDK client, or ``None`` when the provider or its key is unavailable.
    """
    providers = get_available_providers()
    cfg = providers.get(provider_name)
    if not cfg:
        return None

    api_key = os.environ.get(cfg.api_key_env_var)
    if not api_key or not api_key.strip():
        return None
    return create_agnes_client()
