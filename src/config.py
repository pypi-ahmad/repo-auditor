"""Application configuration without exposing credential values."""

import os

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """Runtime settings that are safe to expose to the application UI.

    Attributes:
        budget_chars: Default maximum size of a generated repository pack.
        max_files: Default maximum number of packed files.
        model: Fixed Agnes model label used by the application.
        base_url: OpenAI-compatible Agnes API endpoint.
        agnes_api_key_set: Whether the current process has a nonempty key.
    """

    budget_chars: int = Field(default=80_000, ge=10_000, le=500_000)
    max_files: int = Field(default=40, ge=1, le=200)
    model: str = "agnes-3.0-flash"
    base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_api_key_set: bool = False


def get_config() -> AppConfig:
    """Read runtime settings without exposing credential values.

    Returns:
        Configuration with fixed product defaults and only a boolean key-presence flag.
    """
    key = os.environ.get("AGNESAI_API_KEY")
    return AppConfig(agnes_api_key_set=bool(key and key.strip()))
