"""Which dataset a delivered file belongs to, decided by that dataset's
own declared pattern and by nothing else (REQ-PIPE-058).

THE FILENAME IS THE ONLY THING INSIDE A DELIVERY THAT CARRIES MEANING.
Not the delivery's name, which is arbitrary by design - deriving a
dataset from it would mean recognition passing by parsing a name we
wrote ourselves. Not the file's position, not the collection the rest of
the delivery belongs to, and not elimination: "the one file in a Birth
Registrations delivery must be Birth Registrations" reads perfectly
reasonable and is exactly how a garbage file quietly becomes a supply.

A REGULAR EXPRESSION, in a field of its own (Keith, 2026-09-24). The
fork was decided on expressiveness: the drafted middle option -
placeholders in a dedicated field - cannot express a split extract
without gaining optionality, then repetition, then alternation, which is
reinventing regex badly. It deliberately does NOT reuse the ODCS
contract's `arrivalPattern` keyPattern, which is an S3 key and a
TRANSPORT concern; qa_tools/common/file_arrival.py still owns that, and
keeping the two apart is the whole point of criterion 4.

THE ReDoS RISK IS BOUNDED MECHANICALLY rather than by trusting the
author. Keith accepted the residual risk - "I'm kind of willing to
accept the risk of someone stuffing up a regex" - on the grounds that WE
author the pattern and the supplier only supplies the filename, so the
real exposure is us writing a subtly wrong one rather than anyone
attacking. What makes that acceptable is that it is asymmetrically
protected: a pattern that is too BROAD lets two datasets claim one file,
which the configuration gate fails on and the runtime holds; a pattern
that is too NARROW leaves a file unrecognised, which is reported rather
than silent. On top of that, three things here are structural:

  - every filename is length-capped BEFORE matching (anything over 255
    characters is already invalid on every filesystem this runs on),
  - every pattern is compiled ONCE, at config load, and a bad one raises
    a named configuration error rather than a stack trace at
    recognition time, and
  - matching is `re.fullmatch`, so criterion 5's anchoring holds whether
    or not an author remembered to write `^...$`.

TWO DATASETS MATCHING ONE FILE AND ONE DATASET MATCHING TWO FILES ARE
OPPOSITE THINGS, and they sit adjacent in this code. The first is always
a configuration error: the file is attributed to nobody and held for a
person (criterion 9). The second is the legitimate split-extract shape:
both files belong to that dataset, and what happens to them is
REQ-PIPE-059's hold rather than anything here.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass

from qa_tools.common import hierarchy

#: Longer than any filesystem this runs on will accept, so a name over
#: this is already not a real file. Capping before the match is what
#: bounds the cost of a badly-written pattern.
MAX_FILENAME_LENGTH = 255


class ArrivalPatternError(ValueError):
    """A pattern that cannot be used, named at config-load time.

    Raised where the alternative is a stack trace out of `re` in the
    middle of recognising a delivery, which says nothing about which
    dataset's configuration is wrong.
    """


@dataclass(frozen=True)
class Attribution:
    """What a filename turned out to be.

    Three outcomes, and they are kept apart because they need different
    things done about them: one dataset claimed it, nobody claimed it,
    or several did.
    """

    filename: str
    dataset_ids: tuple[str, ...]

    @property
    def dataset_id(self) -> str | None:
        """The dataset this file belongs to, or None where that is not
        a single answer. Ambiguity is NOT resolved by taking the first:
        that is a choice made invisibly, which is the shape this whole
        module exists to refuse."""
        return self.dataset_ids[0] if len(self.dataset_ids) == 1 else None

    @property
    def is_attributed(self) -> bool:
        return len(self.dataset_ids) == 1

    @property
    def is_unrecognised(self) -> bool:
        return not self.dataset_ids

    @property
    def is_contested(self) -> bool:
        """Several datasets' patterns claim it - always a configuration
        error, never a supplier's doing."""
        return len(self.dataset_ids) > 1


def _compile(dataset_id: str, pattern: str) -> re.Pattern:
    if not isinstance(pattern, str) or not pattern.strip():
        raise ArrivalPatternError(
            f"dataset {dataset_id!r} declares an empty arrival_pattern")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ArrivalPatternError(
            f"dataset {dataset_id!r} declares an arrival_pattern that is not a "
            f"usable regular expression ({exc}): {pattern}") from exc


@functools.lru_cache(maxsize=1)
def compiled_patterns() -> dict[str, re.Pattern]:
    """Every declared pattern, compiled once, keyed by dataset id.

    Datasets that declare none are simply absent. Whether that is
    allowed is the configuration gate's question (criterion 7), not
    this function's - a dataset with no pattern attributes nothing,
    which is a coherent state to be in while one is being added.
    """
    out: dict[str, re.Pattern] = {}
    for entry in hierarchy.all_datasets():
        if entry.arrival_pattern:
            out[entry.dataset_id] = _compile(entry.dataset_id, entry.arrival_pattern)
    return out


def attribute(filename: str) -> Attribution:
    """Which dataset owns this file.

    EVERY pattern is evaluated, not just up to the first that matches
    (criterion 6). Stopping early would make attribution depend on
    declaration order, and would hide the two-datasets-one-file case
    entirely - the very thing worth finding.
    """
    name = (filename or "").strip()
    if not name or len(name) > MAX_FILENAME_LENGTH:
        return Attribution(filename=filename, dataset_ids=())
    matched = tuple(sorted(
        dataset_id for dataset_id, rx in compiled_patterns().items()
        if rx.fullmatch(name)))
    return Attribution(filename=name, dataset_ids=matched)


def dataset_for_filename(filename: str) -> str | None:
    """The one dataset this file belongs to, or None.

    None covers both "nobody claimed it" and "several did". A caller
    that needs to tell those apart - and anything reporting to a person
    does - asks `attribute()` instead.
    """
    return attribute(filename).dataset_id
