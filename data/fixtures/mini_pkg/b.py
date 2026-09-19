"""Module B: Consumer module calling Module A."""

from a import greet as greetz, say_hello


def run(user_name: str) -> str:
    """Greets user using module a functions."""
    # greet as greetz exists, but say_hello was renamed to greet in a.py and is missing
    msg = greetz(user_name)
    alt_msg = say_hello(user_name)
    return f"{msg} | {alt_msg}"
