"""The configuration gate over arrival patterns (REQ-PIPE-058, criteria
7, 8 and 13).

TWO DIFFERENT CHECKS, easy to read as contradicting each other, so the
distinction is spelled out rather than left to the reader:

  - COMPLETENESS (criterion 7): a dataset that has slots - that is
    expected to receive supplies - must declare a pattern. Without one
    it attributes nothing, which means its supplies land as
    unrecognised files for ever and nothing says why.
  - DUPLICATE ATTRIBUTION (criterion 8): no filename we have actually
    seen may match two datasets' patterns. Two datasets quietly
    claiming one filename files a supply against the wrong table, which
    is the false-green direction, and nothing about it is visible by
    reading either dataset's configuration on its own.

THIS IS NOT A HISTORY GATE, and that was rejected deliberately (Keith,
2026-09-24). A gate demanding every historical filename still match
exactly one pattern would force a dataset's old naming to be carried in
its pattern for ever, so patterns could only ever grow alternations,
accumulating every historical naming scheme across thirty datasets over
years. It punishes exactly the change that should be cheap: a supplier
renaming their extract. Old names simply stop matching anything here,
which is not a failure.

WHAT THIS GATE CANNOT DO, so nobody mistakes it for complete: it sees
only collisions a real filename has already witnessed. Two patterns can
overlap on a shape of name nobody has sent yet -
`^cp_clients(_part\\d+)?\\.csv$` and `^cp_.*_part\\d+\\.csv$` collide only
on `cp_clients_part2.csv` - and this stays green until the day that
file arrives. Proving non-overlap properly is decidable and was
rejected on cost; the half that cannot be wrong is the RUNTIME HOLD in
qa_tools/common/arrivals.py, which sees every collision that actually
occurs and does not care whether anyone remembered to run this. The
protection is the pair. This half is nearly free on top and catches a
careless edit when it is cheapest to fix.
"""
from __future__ import annotations

import json
from pathlib import Path

from qa_tools.common import arrival_patterns, hierarchy, schedule

ROOT = Path(__file__).resolve().parent.parent.parent

#: Where REQ-PIPE-069 will commit one file per delivery. Read here
#: rather than data/deliveries/, which is gitignored - putting a data/
#: read into a gate that CI runs would break this project's standing
#: rule outright rather than merely being vacuous.
DELIVERY_LOG_DIR = ROOT / "delivery_log"


class ArrivalPatternConfigError(ValueError):
    """A configuration problem, phrased for the person who has to fix
    it. Patterns are written rarely and read under pressure, so a
    message here names the datasets and the filename that collide -
    "conflict detected" sends somebody diffing seven regexes."""


def committed_filenames(log_dir: Path | None = None) -> list[str]:
    """Every filename the committed delivery log has ever recorded.

    Empty until REQ-PIPE-069 lands, which is stated by the gate rather
    than passed over: a check with no corpus is not a check that
    passed.
    """
    directory = Path(log_dir) if log_dir is not None else DELIVERY_LOG_DIR
    if not directory.is_dir():
        return []
    names: set[str] = set()
    for path in sorted(directory.rglob("*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ArrivalPatternConfigError(
                f"{path} is in the delivery log and cannot be read ({exc})") from exc
        for name in record.get("files") or []:
            names.add(name if isinstance(name, str) else name.get("filename", ""))
    return sorted(n for n in names if n)


def missing_patterns() -> list[str]:
    """Datasets that are owed supplies and have no way to recognise
    one (criterion 7)."""
    out = []
    for entry in hierarchy.all_datasets():
        if entry.arrival_pattern:
            continue
        if schedule.slots_for_dataset(entry.dataset_id):
            out.append(entry.dataset_id)
    return sorted(out)


def duplicate_attributions(filenames: list[str]) -> list[tuple[str, tuple[str, ...]]]:
    """(filename, datasets) for every recorded name two patterns both
    claim (criterion 8)."""
    found = []
    for name in filenames:
        claimed = arrival_patterns.attribute(name)
        if claimed.is_contested:
            found.append((name, claimed.dataset_ids))
    return found


def validate(log_dir: Path | None = None) -> str:
    """Raises ArrivalPatternConfigError on a real problem; returns the
    line `mothman check` prints otherwise."""
    # Compiling every pattern is itself half the gate: a pattern that is
    # not a usable regular expression is a named error here, at the
    # moment somebody can still see what they typed, rather than a
    # stack trace out of `re` in the middle of recognising a delivery.
    try:
        compiled = arrival_patterns.compiled_patterns()
    except arrival_patterns.ArrivalPatternError as exc:
        raise ArrivalPatternConfigError(str(exc)) from exc

    problems = []
    for dataset_id in missing_patterns():
        problems.append(
            f"dataset {dataset_id!r} is expected to receive supplies and declares no "
            f"`arrival_pattern:` in contract/data-asset.yaml, so nothing it is sent can "
            f"ever be recognised as its own.")

    filenames = committed_filenames(log_dir)
    for name, claimants in duplicate_attributions(filenames):
        patterns = ", ".join(
            f"{d} ({compiled[d].pattern})" for d in claimants if d in compiled)
        problems.append(
            f"the delivered file {name!r} matches the arrival pattern of more than one "
            f"dataset - {patterns}. One filename can belong to only one dataset, and at "
            f"runtime this file is held rather than filed.")

    if problems:
        raise ArrivalPatternConfigError("\n".join(problems))

    corpus = (f"{len(filenames)} recorded filename(s)" if filenames
              else "no committed delivery log yet (REQ-PIPE-069), so nothing to "
                   "check for duplicate attribution")
    return (f"arrival pattern validation OK - {len(compiled)} dataset pattern(s), "
            f"{corpus}.")


def main() -> int:
    """`mothman check`'s own entry point - a plain module so the gate
    needs no CLI command of its own, matching validate_agents.py."""
    try:
        print(validate())
    except ArrivalPatternConfigError as exc:
        print(f"arrival pattern validation FAILED\n{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
