from __future__ import annotations


def normalize_keywords(values: list[str] | tuple[str, ...]) -> list[str]:
    """Keep the first spelling; filtering is case-insensitive so duplicate tags are redundant."""
    result: dict[str, str] = {}
    for value in values:
        word = value.strip()
        if word:
            result.setdefault(word.casefold(), word)
    return list(result.values())
