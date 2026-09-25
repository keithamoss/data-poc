"""Validates every `.claude/agents/*.md` subagent definition's YAML
frontmatter - Keith's ask, 2026-09-22, after a real incident.

THE INCIDENT. Four of this project's eight subagents - both
`delivery-*-ux` pairs - had a `description:` hard-wrapped across a dozen
lines at zero indentation. That is not a valid plain scalar, so the
frontmatter never parsed, so Claude Code silently did not register those
agents. They had been unloadable since the day they were written. The
symptom was visible in the file itself: `delivery-cli-ux`'s description
text ended with the literal words `tools: Read, Grep,` - its own `tools:`
key, swallowed into the string.

Nothing noticed for three days. `CLAUDE.md`'s own periodic check
("Re-checked 2026-09-19 evening... 8 real agents") counted FILES ON
DISK, which is exactly the number you get whether they load or not.

WHY A PRE-COMMIT GATE RATHER THAN A TEST. Keith's own call, and it
matches the precedent already set for `contract/*.yaml`: a malformed
config file that still commits cleanly is caught at commit time by
actually parsing it, not by a unit test asserting a behaviour. Same
reasoning as the `check-yaml` hook added 2026-09-18 - `ruff` only reads
Python, so a broken YAML file sails past every other gate.

WHY IT CANNOT JUST BE `check-yaml`. That hook globs `*.yml`/`*.yaml`.
These are `*.md` files with frontmatter, so it never looks at them. The
frontmatter has to be sliced out before `yaml.safe_load` sees it, which
is the only thing this module does that a stock hook could not.

WHAT IT CHECKS, and each one is a real failure this could have had:
- The frontmatter parses at all (the actual incident).
- It is a mapping, not a bare string - which is what a subtly-wrong
  indentation produces, and it fails far less obviously than a syntax
  error.
- `name` and `description` are present and non-empty.
- `name` matches the filename, since the filename is what a caller
  types as `subagent_type` and a mismatch is invisible until a spawn
  fails.
- No unknown top-level key, which catches a typo'd `tool:`/`models:`
  that would otherwise be accepted and ignored forever - the same
  "silently dropped field" reasoning as `requirements.yaml`'s own
  `extra="forbid"`.

It also REPORTS the combined `description:` budget. Claude Code warns
once all non-built-in descriptions exceed ~15,000 tokens, and only that
field loads for every session regardless of whether the agent ever
runs - so it is the one number worth watching. `CLAUDE.md` asked for
this as a periodic manual check; folding it in here means it happens on
every commit instead of whenever someone remembers. Deliberately a
REPORT and not a failure: the limit is a Claude Code warning, not a
hard error, and a gate that blocks a commit over a soft upstream
threshold would be wrong.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

AGENTS_DIR = Path(__file__).resolve().parent.parent.parent / ".claude" / "agents"

# Every key Claude Code actually reads from a subagent definition. A key
# outside this set is a typo, and a typo here fails silently - the file
# still parses, the agent still loads, and whatever that key was meant
# to configure simply never applies.
KNOWN_KEYS = frozenset({
    "name", "description", "tools", "model",
    "permissionMode", "mcpServers", "skills", "isolation",
})

# Claude Code warns above ~15,000 tokens of combined description. Four
# characters per token is the same rough estimate CLAUDE.md's own
# manual check used, kept identical so the two numbers stay comparable.
CHARS_PER_TOKEN = 4
BUDGET_TOKENS = 15_000


def split_frontmatter(text: str) -> str | None:
    """The YAML block between the opening `---` and the next one.

    Returns None when there is no frontmatter at all, which is a
    different failure from frontmatter that does not parse - an agent
    file with no frontmatter is not an agent file.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return "\n".join(lines[1:i])
    return None


def validate_file(path: Path) -> tuple[list[str], int]:
    """Returns (errors, description length). An unparseable file reports
    a length of 0 rather than raising, so one broken agent cannot hide
    the budget figure for the other seven."""
    errors: list[str] = []
    block = split_frontmatter(path.read_text())
    if block is None:
        return ([f"{path.name}: no YAML frontmatter (expected a leading '---' block)"], 0)

    try:
        front = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        # The real incident's shape. Worth naming the likely cause in
        # the message: the error PyYAML gives for a hard-wrapped plain
        # scalar does not mention wrapping, so the fix is not obvious
        # from the error alone.
        detail = str(exc).replace("\n", " ")
        return ([f"{path.name}: frontmatter does not parse as YAML - {detail}. "
                 f"A hard-wrapped multi-line 'description:' is the usual cause; "
                 f"keep it on one line."], 0)

    if not isinstance(front, dict):
        return ([f"{path.name}: frontmatter is {type(front).__name__}, not a mapping"], 0)

    for key in ("name", "description"):
        if not str(front.get(key) or "").strip():
            errors.append(f"{path.name}: '{key}' is missing or empty")

    name = front.get("name")
    if name and name != path.stem:
        errors.append(f"{path.name}: 'name' is {name!r} but the filename says "
                      f"{path.stem!r} - the filename is what a caller types")

    for key in sorted(set(front) - KNOWN_KEYS):
        errors.append(f"{path.name}: unknown key {key!r} - it would be silently ignored")

    return (errors, len(str(front.get("description") or "")))


def main() -> int:
    """Returns an exit code rather than calling sys.exit, matching
    validate_requirements/validate_changelog - cli/ wraps the int in a
    ClickException so the CLI reports it the same way as every other
    gate."""
    if not AGENTS_DIR.is_dir():
        print(f"No agents directory at {AGENTS_DIR} - nothing to validate.")
        return 0

    paths = sorted(AGENTS_DIR.glob("*.md"))
    all_errors: list[str] = []
    total_chars = 0
    for path in paths:
        errors, length = validate_file(path)
        all_errors.extend(errors)
        total_chars += length

    if all_errors:
        print(f"agent validation FAILED ({len(all_errors)} error(s)):")
        for error in all_errors:
            print(f"  - {error}")
        return 1

    tokens = total_chars // CHARS_PER_TOKEN
    print(f"agent validation OK - {len(paths)} agents, zero errors.")
    print(f"  combined description budget: ~{tokens:,} tokens "
          f"of ~{BUDGET_TOKENS:,} ({tokens / BUDGET_TOKENS:.0%}).")
    if tokens > BUDGET_TOKENS:
        # Reported, never fatal - see this module's own docstring.
        print("  WARNING: over the budget Claude Code warns at. Shorten the "
              "longest descriptions; only that field loads every session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
