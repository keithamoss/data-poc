"""
Check-lifecycle metadata: parsing, hashing, and the two validations that
gate publishing (plans/publishing-and-history.md Thread D, Phase 1).
Every check across all 4 tools (dbt, Soda, the ODCS contract, Evidently)
carries hand-authored metadata living directly in its own definition -
no CLI, per Keith's own call (see that file's "Authoring" section) -
this module is what reads it back and checks it's correct, not what
writes it.

Two things this validates, both settled 2026-09-16:
1. Every `check_id` across the whole system (all 30 datasets, eventually
   - today BDM + Child Protection) must be globally unique.
2. If a check's real config (thresholds, accepted values, logic - NOT
   its description/meta) changed since the last known state, there must
   be a new `changelog` entry documenting it. Detected automatically via
   a config hash, not left to a human to remember to flag.

`check_id` is the stable identity checks are tracked under (format:
`<data-asset-name>.<agency>.<dataset>.<table>.<column>.<check_name>`,
column omitted for table-level checks - see that plan file for why this
needed to be introduced explicitly rather than derived from any tool's
own naming). A check with no `check_id` in its metadata is a hard error
(`MissingCheckIdError`) - mandatory, no grace period, since Phase 1's
retrofit already gave every real check across the system a check_id.

Config-hash scope is deliberately narrow and tool-specific: only the
fields that define what the check actually DOES (thresholds, accepted
values, patterns, the check expression itself) count - `meta`/
`attributes`/`customProperties` (where the lifecycle metadata itself
lives) and cosmetic fields (`name`, `description`) never do, or every
check would "change" the moment its description got proofread.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent


class MissingCheckIdError(ValueError):
    """Raised when a check has no check_id in its metadata. Mandatory,
    no grace period: Phase 1's retrofit gave every real check a
    check_id, so from here on a check with none is a mistake to catch
    at parse time (and eventually CI), not something to silently treat
    as "not yet migrated"."""


@dataclass
class CheckMetadata:
    check_id: str
    tool: str
    config_hash: str
    source_file: str
    introduced_date: str | None = None
    retired_as_of: str | None = None
    retired_reason: str | None = None
    description: str | None = None
    changelog: list[dict] = field(default_factory=list)


def _config_hash(config: dict) -> str:
    """A stable fingerprint of "what the check actually does" - sorted
    keys so field-reordering in the YAML never looks like a real change,
    `default=str` so any odd YAML-native type (dates, etc.) doesn't
    crash the hash."""
    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _lifecycle_fields(meta: dict) -> dict:
    return {
        "introduced_date": meta.get("introduced_date"),
        "retired_as_of": meta.get("retired_as_of"),
        "retired_reason": meta.get("retired_reason"),
        "description": meta.get("description"),
        "changelog": list(meta.get("changelog") or []),
    }


# ---- dbt schema.yml -------------------------------------------------

def _parse_dbt_test(test: Any, source: str, location: str) -> list[CheckMetadata]:
    if isinstance(test, str):
        raise MissingCheckIdError(
            f"{source}: {location}: bare test {test!r} has no meta.check_id "
            "(bare test form can't carry metadata - use the dict form with a meta: block)"
        )
    if not isinstance(test, dict) or len(test) != 1:
        return []
    (test_type, test_config), = test.items()
    test_config = dict(test_config or {})
    meta = test_config.pop("meta", None) or {}
    check_id = meta.get("check_id")
    if not check_id:
        raise MissingCheckIdError(f"{source}: {location}: dbt test {test_type!r} has no meta.check_id")
    return [CheckMetadata(
        check_id=check_id, tool="dbt", config_hash=_config_hash(test_config),
        source_file=source, **_lifecycle_fields(meta),
    )]


def parse_dbt_check_metadata(schema_yml_path: Path | str) -> list[CheckMetadata]:
    with open(schema_yml_path) as f:
        doc = yaml.safe_load(f) or {}
    out: list[CheckMetadata] = []
    errors: list[str] = []
    source = str(schema_yml_path)
    for model in doc.get("models", []) or []:
        for test in model.get("tests", []) or []:  # model-level (dbt_utils.expression_is_true etc.)
            try:
                out.extend(_parse_dbt_test(test, source, f"model {model['name']!r}"))
            except MissingCheckIdError as e:
                errors.append(str(e))
        for col in model.get("columns", []) or []:
            for test in col.get("tests", []) or []:
                try:
                    out.extend(_parse_dbt_test(test, source, f"model {model['name']!r} column {col['name']!r}"))
                except MissingCheckIdError as e:
                    errors.append(str(e))
    if errors:
        raise MissingCheckIdError("\n".join(errors))
    return out


# ---- Soda checks YAML ------------------------------------------------

def _parse_soda_check(check: Any, source: str, location: str) -> list[CheckMetadata]:
    if isinstance(check, str):
        raise MissingCheckIdError(f"{source}: {location}: bare check {check!r} has no attributes.check_id")
    if not isinstance(check, dict) or len(check) != 1:
        return []
    (check_expr, check_config), = check.items()
    if check_expr == "attributes":
        return []  # dataset-level default attributes block, not a check
    check_config = dict(check_config or {})
    attributes = check_config.pop("attributes", None) or {}
    check_id = attributes.get("check_id")
    if not check_id:
        raise MissingCheckIdError(f"{source}: {location}: soda check {check_expr!r} has no attributes.check_id")
    check_config.pop("name", None)  # cosmetic label, not part of what the check does
    return [CheckMetadata(
        check_id=check_id, tool="soda", config_hash=_config_hash(check_config),
        source_file=source, **_lifecycle_fields(attributes),
    )]


def parse_soda_check_metadata(soda_yml_path: Path | str) -> list[CheckMetadata]:
    with open(soda_yml_path) as f:
        doc = yaml.safe_load(f) or {}
    out: list[CheckMetadata] = []
    errors: list[str] = []
    source = str(soda_yml_path)
    for key, checks in doc.items():
        if not key.startswith("checks for"):
            continue
        for check in checks or []:
            try:
                out.extend(_parse_soda_check(check, source, key))
            except MissingCheckIdError as e:
                errors.append(str(e))
    if errors:
        raise MissingCheckIdError("\n".join(errors))
    return out


# ---- ODCS contract YAML -----------------------------------------------

def _custom_properties_to_dict(custom_properties: list[dict]) -> dict:
    return {cp["property"]: cp["value"] for cp in custom_properties if "property" in cp}


def _parse_contract_quality_rule(rule: dict, source: str, location: str) -> list[CheckMetadata]:
    rule = dict(rule)
    custom_properties = rule.pop("customProperties", None) or []
    meta = _custom_properties_to_dict(custom_properties)
    check_id = meta.get("check_id")
    if not check_id:
        rule_label = rule.get("rule") or rule.get("type") or rule.get("metric")
        raise MissingCheckIdError(f"{source}: {location}: quality rule {rule_label!r} has no check_id customProperty")
    native_description = rule.pop("description", None)
    changelog = meta.get("changelog")
    if isinstance(changelog, str):
        changelog = json.loads(changelog)  # ODCS customProperties values are scalar - a list gets stored as a JSON string
    return [CheckMetadata(
        check_id=check_id, tool="datacontract", config_hash=_config_hash(rule),
        source_file=source,
        introduced_date=meta.get("introduced_date"), retired_as_of=meta.get("retired_as_of"),
        retired_reason=meta.get("retired_reason"),
        # ODCS quality rules already commonly carry their own native
        # `description:` field (a real ODCS property, unlike dbt's/
        # Soda's tool-specific config) - reuse it rather than requiring
        # every rule to duplicate the same text into customProperties
        # too. customProperties' own `description` wins if both exist
        # (an explicit override for this metadata specifically).
        description=meta.get("description") or native_description,
        changelog=changelog or [],
    )]


def parse_contract_check_metadata(contract_yaml_path: Path | str) -> list[CheckMetadata]:
    with open(contract_yaml_path) as f:
        doc = yaml.safe_load(f) or {}
    out: list[CheckMetadata] = []
    errors: list[str] = []
    source = str(contract_yaml_path)
    for table in doc.get("schema", []) or []:
        table_name = table.get("name")
        for rule in table.get("quality", []) or []:  # table-level quality rules
            try:
                out.extend(_parse_contract_quality_rule(rule, source, f"table {table_name!r}"))
            except MissingCheckIdError as e:
                errors.append(str(e))
        for prop in table.get("properties", []) or []:
            for rule in prop.get("quality", []) or []:
                try:
                    out.extend(_parse_contract_quality_rule(rule, source, f"table {table_name!r} column {prop.get('name')!r}"))
                except MissingCheckIdError as e:
                    errors.append(str(e))
    if errors:
        raise MissingCheckIdError("\n".join(errors))
    return out


# ---- Evidently (plain Python dicts, no YAML) --------------------------

def parse_evidently_check_metadata(check_lifecycle: dict, source: str) -> list[CheckMetadata]:
    """`check_lifecycle` is a `CHECK_LIFECYCLE`-shaped dict (check_id ->
    metadata) - imported and passed in by the caller rather than this
    function importing a module itself, so this stays a pure function
    testable with a plain dict fixture."""
    out = []
    for check_id, meta in check_lifecycle.items():
        config = {k: v for k, v in meta.items()
                  if k not in ("introduced_date", "retired_as_of", "retired_reason", "description", "changelog")}
        out.append(CheckMetadata(
            check_id=check_id, tool="evidently", config_hash=_config_hash(config),
            source_file=source, **_lifecycle_fields(meta),
        ))
    return out


# ---- Validation --------------------------------------------------------

def find_duplicate_check_ids(checks: list[CheckMetadata]) -> list[str]:
    """Returns check_ids that appear more than once - each must be
    globally unique across the whole system (plans/publishing-and-
    history.md Thread D)."""
    seen: dict[str, int] = {}
    for c in checks:
        seen[c.check_id] = seen.get(c.check_id, 0) + 1
    return sorted(check_id for check_id, count in seen.items() if count > 1)


def find_undocumented_changes(old_checks: list[CheckMetadata], new_checks: list[CheckMetadata]) -> list[str]:
    """Returns check_ids whose config_hash changed between `old_checks`
    and `new_checks` without a new changelog entry to explain it (the
    new changelog must be strictly longer than the old one - simple,
    robust, doesn't need precise date/time reasoning about which entry
    is "the new one"). A check present only in `new_checks` (newly
    check_id'd) is never flagged - there's nothing to have changed FROM."""
    old_by_id = {c.check_id: c for c in old_checks}
    undocumented = []
    for new in new_checks:
        old = old_by_id.get(new.check_id)
        if old is None:
            continue
        if old.config_hash != new.config_hash and len(new.changelog) <= len(old.changelog):
            undocumented.append(new.check_id)
    return sorted(undocumented)


def validate(old_checks: list[CheckMetadata], new_checks: list[CheckMetadata]) -> list[str]:
    """The single entry point the CI gate calls (Phase 3). Returns a list
    of human-readable error strings - empty means valid."""
    errors = []
    for check_id in find_duplicate_check_ids(new_checks):
        errors.append(f"Duplicate check_id: {check_id!r}")
    for check_id in find_undocumented_changes(old_checks, new_checks):
        errors.append(f"Check config changed without a new changelog entry: {check_id!r}")
    return errors
