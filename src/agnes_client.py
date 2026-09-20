"""Official OpenAI SDK client configured for Agnes AI."""

import os

from openai import OpenAI

from src.config import get_config


def create_agnes_client(max_retries: int = 3) -> OpenAI:
    """Create an Agnes client with retries for transient failures, including HTTP 429.

    Args:
        max_retries: Maximum SDK retry count for transient request failures.

    Returns:
        An official OpenAI SDK client configured with the fixed Agnes endpoint.

    Raises:
        RuntimeError: If ``AGNESAI_API_KEY`` is unavailable in the current process.
    """
    api_key = os.environ.get("AGNESAI_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError("AGNESAI_API_KEY is not set.")

    config = get_config()
    return OpenAI(
        api_key=api_key,
        base_url=config.base_url,
        max_retries=max_retries,
        timeout=60.0,
    )
