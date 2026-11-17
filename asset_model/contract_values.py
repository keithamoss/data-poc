"""A column's allowed values, read from its collection's ODCS contract
(REQ-QAC-389 criterion 1) - the one reader the QA adapters' statistics and the
Linkage Products provider's drift planning share.

THE CONTRACT IS THE COPY THAT SURVIVES WHICHEVER TOOL IS DROPPED (SPLIT D3,
Keith 2026-11-03): Soda and dbt keep their own copies of a list, with no gate
holding them equal, and nothing here reads them. A column declares its list
either as a field-level `enum:` (Linkage Products' match_level) or as a
datacontract `invalidValues` quality rule's `validValues` (every other list
today); both are read, and where a column declares both and they disagree the
reader refuses rather than picking one.

IN THE ORDER THE CONTRACT DECLARES IT (criterion 3), because recorded value
counts keep their declared order (REQ-QAC-247).

A list that cannot be found is a named refusal (criterion 4), never an empty
list that would count every value invalid.
"""
from __future__ import annotations

from pathlib import Path

import yaml

__all__ = ["AllowedValuesError", "allowed_values", "declared_lists", "lists_for"]


class AllowedValuesError(ValueError):
    """A column an adapter names has no allowed-value list in its contract,
    or declares two that disagree. The message names the contract, the
    column, what is wrong and the fix."""


def _enum_values(entries) -> list:
    return [e["value"] if isinstance(e, dict) else e for e in entries]


def declared_lists(contract: dict) -> dict[tuple[str, str], list[list]]:
    """Every allowed-value list each (table, column) declares, in declared
    order - one entry per declaration, so a caller can see two."""
    found: dict[tuple[str, str], list[list]] = {}
    for table in contract.get("schema") or []:
        for prop in table.get("properties") or []:
            key = (table.get("name"), prop.get("name"))
            if prop.get("enum") is not None:
                found.setdefault(key, []).append(_enum_values(prop["enum"]))
            for rule in prop.get("quality") or []:
                valid = (rule.get("arguments") or {}).get("validValues")
                if rule.get("metric") == "invalidValues" and valid is not None:
                    found.setdefault(key, []).append(list(valid))
    return found


def _fix(table: str, column: str, path) -> str:
    return f"add an invalidValues rule or `enum:` to {column} in {path} ({table})"


def _one(found: dict, path, table: str, column: str) -> list:
    lists = found.get((table, column))
    if not lists:
        raise AllowedValuesError(
            f"{path}: {table}.{column} declares no allowed-value list, and the statistics count "
            f"it against one - {_fix(table, column, path)}")
    first = lists[0]
    for other in lists[1:]:
        if other != first:
            raise AllowedValuesError(
                f"{path}: {table}.{column} declares two allowed-value lists that disagree "
                f"({first!r} and {other!r}) - make the `enum:` and the invalidValues rule's "
                f"validValues the same list")
    if not first:
        raise AllowedValuesError(
            f"{path}: {table}.{column}'s allowed-value list is empty, which would count every "
            f"value invalid - {_fix(table, column, path)}")
    return list(first)


def _load(path) -> dict:
    return yaml.safe_load(Path(path).read_text()) or {}


def allowed_values(path, table: str, column: str) -> list:
    """`column`'s allowed values in `table`, as the contract at `path`
    declares them."""
    return _one(declared_lists(_load(path)), path, table, column)


def lists_for(path, pairs) -> dict[tuple[str, str], list]:
    """Each (table, column) in `pairs`' allowed values, the contract read
    ONCE (NFR PERFORMANCE). Refuses on the first column without a list."""
    found = declared_lists(_load(path))
    return {(t, c): _one(found, path, t, c) for (t, c) in pairs}
