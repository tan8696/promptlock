"""Fixture: no LLM calls, no prompt constants. Must produce zero hits."""

MAX_RETRIES = 3
LABEL = "billing"
SEPARATOR = ", "


def add(a: int, b: int) -> int:
    return a + b


def join(parts: list[str]) -> str:
    return SEPARATOR.join(parts)
