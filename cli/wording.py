"""Small grammar helpers for text built from a collection's names - no
imports, so help text can use them without slowing `--help`."""
from __future__ import annotations


def a_or_an(word: str) -> str:
    """`a Birth Registrations`, `an Emergency Department`: the article a
    name built into help text needs, by its first letter."""
    return f"{'an' if word[:1].upper() in 'AEIOU' else 'a'} {word}"


def all_of(n: int, noun: str) -> str:
    """`both tables` for two, `all 6 tables` otherwise."""
    return f"both {noun}" if n == 2 else f"all {n} {noun}"
