"""
Declared schemas for this repo's own hand-authored YAML - `requirements.yaml`
and `CHANGELOG.yaml` - as pydantic models (REQ-DOCS-029).

Keith's challenge, 2026-09-20: "can't we use a YAML schema validation
library and give it a spec for this kind of stuff rather than writing
these hacky scripts?" He was right about the half of the validators that
is genuinely schema work - required fields, closed vocabularies, string
patterns, nesting. That half now lives here as a declaration rather than
as a sequence of hand-written `if` statements.

**What deliberately did NOT move here**, because no schema library can
express it:

  - `linked_tests` and `implemented_by` are checked against a real AST
    parse of the file they name, so a renamed function fails the build.
    That is a cross-reference into the codebase, not a shape.
  - `dependencies` must resolve to a real id in the same document.
    Expressible as a model validator in principle, but it belongs with
    the other cross-references rather than split across two files.
  - Duplicate mapping keys. Verified rather than assumed: schema
    validation runs on the already-parsed object, and a duplicate does
    not make a key MISSING - it leaves it present with truncated
    content, so a required-key rule passes. `yamllint`'s key-duplicates
    rule catches that instead, at parse time, before any of this runs.

Those stay in `validate_requirements.py`/`validate_changelog.py`, which
now do schema-validation-then-cross-reference rather than everything by
hand.

These models are the single definition of both files' shape, used by
the validators AND by `dashboard/requirements_yaml.py`/`changelog_yaml.py`.

That is a deliberate change from how this landed (2026-09-20, Keith:
"I don't mind if the parsers would choke and throw an error"). The
parsers used to keep their own `_DEFAULTS` dict and render whatever was
really there, never raising, on the reasoning that a half-written file
should still show in the dashboard. In practice that is a worse
outcome, not a kinder one: a requirement missing its `story` renders as
a requirement with no story, which reads as a requirement that has no
story - and the CI gate that would have caught it runs against the same
file a moment earlier anyway. Now there is one declaration of the shape
instead of two that can drift, and a file that cannot be rendered
honestly stops the build rather than being quietly rendered wrong.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from qa_tools.common.vocab import (
    CHANGELOG_CATEGORIES,
    COMPONENT_CODES,
    MOSCOW,
    REQUIREMENT_STATUSES,
)

# A REQUIRED non-empty string. The blank-rejection itself lives on
# `_Strict` below and covers every string field, optional ones
# included; this type adds the one thing that rule cannot say, which is
# that the key has to be there at all.
NonEmptyStr = Annotated[str, Field(min_length=1)]

_ID_PATTERN = r"^REQ-(?:" + "|".join(COMPONENT_CODES) + r")-\d{3}$"
_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class _Strict(BaseModel):
    """Shared base. `extra="forbid"` is the point: a typo'd field name in
    a hand-authored file would otherwise be accepted and silently ignored
    forever, which is the same failure shape as the duplicate key that
    started this work."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _no_blank_strings(cls, v):
        """A key written with nothing in it is rejected - including for
        the optional fields, where the stripped value would otherwise be
        indistinguishable from the key being absent.

        Absent is a separate question, answered per field by whether it
        has a default. `source` has none (Keith, 2026-09-20) and so is
        required; the rest may be left out entirely, just not left
        empty.

        Keith's call, 2026-09-20, when an earlier draft of this module
        accepted `source: "   "` on the grounds that "I left it blank"
        and "I left it out" mean the same thing. They do not: a blank
        key is someone who started filling it in and stopped, and the
        file should be able to say so. Accepting it is the same silent
        shape as the duplicate mapping key that prompted this work -
        text that looks written down and is not.

        `mode="before"` matters. With `str_strip_whitespace=True` an
        after-validator would see `""` and could not tell a blank value
        from an empty one; and pydantic does not validate a field that
        was never supplied, so absent stays legal without a special
        case here."""
        if isinstance(v, str) and not v.strip():
            # Deliberately does not advise omitting the key - this runs
            # for required fields too, where that would be bad advice.
            raise ValueError("is present but blank - write something real here")
        if isinstance(v, list) and any(isinstance(x, str) and not x.strip() for x in v):
            raise ValueError("list entries must be non-empty strings")
        return v


class SignOff(_Strict):
    """Keith's own sign-off on a requirement, before any building starts.

    His standing instruction, 2026-09-20: a requirement existing in the
    register is not one he has agreed to. Drafting one - by hand or via
    `delivery-scoper` - produces a proposal, and the proposal is
    presented to him as prose he can react to before anything downstream
    begins.

    A structured pair rather than free text ("Keith, 2026-09-20") so the
    date is actually checkable. `by` is deliberately unconstrained: this
    is a small team today and hard-coding one name into a schema is the
    kind of thing that quietly breaks the day someone else signs one.
    """

    by: NonEmptyStr
    date: str

    @field_validator("date")
    @classmethod
    def _real_date(cls, v: str) -> str:
        if not re.match(_DATE_PATTERN, v):
            raise ValueError('must be a real "YYYY-MM-DD" date')
        return v


class UnmetCriterion(_Strict):
    """One acceptance criterion a `built` requirement does not meet.

    WHY A FIELD AND NOT A THIRD STATUS (post-build-review #33, Keith's
    own call, 2026-09-25): `status` is what the register is indexed and
    filtered by, so a third value would make every consumer of it
    decide what "partly built" means - and the honest answer for the
    requirement that prompted this is that it IS built and has a hole
    in it. A hole is a property of the record, not a different kind of
    record.

    ALL THREE FIELDS ARE REQUIRED, and that is the point rather than
    strictness for its own sake. "Some criteria are unmet" is what the
    prose already said, in a `decisions:` note nobody had to read; a
    record that cannot name WHICH, WHY and WHO NEXT is the same
    sentence in a different place. `owner` is free text because the
    next owner is as often a finding or a sprint as a person.
    """

    criterion: NonEmptyStr
    why: NonEmptyStr
    owner: NonEmptyStr


class Requirement(_Strict):
    id: str = Field(pattern=_ID_PATTERN)
    title: NonEmptyStr
    story: NonEmptyStr
    moscow: Literal[*MOSCOW]  # type: ignore[valid-type]
    status: Literal[*REQUIREMENT_STATUSES]  # type: ignore[valid-type]
    acceptance_criteria: list[NonEmptyStr] = Field(min_length=1)

    # Optional in the file; required once `status` is "built", which is
    # a rule about the WHOLE record and so lives in the model validator
    # below rather than on any one field.
    linked_tests: list[str] = []
    implemented_by: list[str] = []
    evidence: list[str] = []
    decisions: list[str] = []

    # Required, and non-blank (Keith, 2026-09-20). Every other field
    # here describes what the requirement IS; this is the only one that
    # says where it came from, and that is the part nobody can
    # reconstruct later. The 22 pre-2026-09-19 entries were backfilled
    # from what the plans files and git history actually record - one
    # of them says plainly that its origin was not recorded, which is
    # real provenance rather than a gap.
    source: NonEmptyStr

    date_written: str = ""

    # Absent until Keith signs the requirement off, and required from
    # the moment its status moves past `not_started` - the rule lives in
    # missing_when_built()'s sibling below, since it is about the whole
    # record rather than this field alone.
    #
    # Why a field and not just the written convention: the convention
    # was written first, the same day, and prose is exactly what had
    # just failed. REQ-DASH-026 sat in this register with ten acceptance
    # criteria while work went ahead against one of them backwards,
    # because nothing required anyone to open it. Nothing in CI could
    # tell a signed-off requirement from an unsigned one.
    signed_off: SignOff | None = None

    non_functional_requirements: list[str] = []
    dependencies: list[str] = []
    open_questions: list[str] = []

    # Acceptance criteria a `built` requirement does not actually meet.
    # Empty for the overwhelming majority, which must not have to say
    # so. Only meaningful once something has been built - see the model
    # validator below.
    unmet_criteria: list[UnmetCriterion] = []

    @field_validator("date_written")
    @classmethod
    def _real_date(cls, v: str) -> str:
        if v and not re.match(_DATE_PATTERN, v):
            raise ValueError('must be a real "YYYY-MM-DD" date')
        return v

    def missing_when_built(self) -> list[str]:
        """The four fields a `built` requirement must carry, and why they
        are checked here rather than as a pydantic rule that would reject
        the document outright: the validator reports EVERY problem in one
        run so an author fixes them together, and a raised exception
        stops at the first."""
        if self.status != "built":
            return []
        return [name for name in ("linked_tests", "implemented_by", "evidence", "decisions")
                if not getattr(self, name)]

    def needs_sign_off(self) -> bool:
        """True when this requirement has moved past `not_started`
        without Keith having signed it off.

        Deliberately allowed while `not_started`: signing off and then
        building is the whole shape of the rule, so a signed but
        not-yet-started requirement is the normal resting state between
        the two, not an error.
        """
        return self.status != "not_started" and self.signed_off is None

    def present_but_not_built(self) -> list[str]:
        """Fields that cannot honestly precede the work, on a requirement
        that does not claim to be built.

        The inverse of the rule above, and it exists because the rule
        above has a blind spot that bit for real (Keith, 2026-09-20):
        REQ-QAC-024 carried a full set of all four fields while still
        reading `not_started`, because the edit meant to flip its status
        matched nothing and failed silently. Nothing looked, since those
        fields are only demanded ONCE status is "built" - so a
        requirement could hold every piece of evidence that it was
        finished and still report that it had not begun.

        `decisions` is deliberately NOT in this list. It is scoping
        material and legitimately grows before any code does - this very
        requirement accumulated fourteen of them over a day of forks
        settled one at a time, and a rule covering it would have failed
        CI on every one of those pushes. The other three each name
        something that cannot exist yet: code that implements it, tests
        that verify it, a measurement taken against it.
        """
        if self.status == "built":
            return []
        out = [name for name in ("linked_tests", "implemented_by", "evidence")
               if getattr(self, name)]
        # Nothing is built, so nothing can be UNmet - and allowing it
        # would make the field mean two different things: "built with a
        # hole" on one record and "scoped but not attempted" on
        # another (post-build-review #33).
        if self.unmet_criteria:
            out.append("unmet_criteria")
        return out


class ChangelogItem(_Strict):
    headline: NonEmptyStr
    description: NonEmptyStr
    components: list[Literal[*COMPONENT_CODES.values()]] = Field(min_length=1)  # type: ignore[valid-type]
    # Optional and normally absent - day-grouping is the point, and a
    # to-the-minute timestamp is detail this audience does not need.
    time: str | None = None


class ChangelogSection(_Strict):
    category: Literal[*CHANGELOG_CATEGORIES]  # type: ignore[valid-type]
    items: list[ChangelogItem] = Field(min_length=1)


class Release(_Strict):
    date: str = Field(pattern=_DATE_PATTERN)
    summary: NonEmptyStr
    changes: list[ChangelogSection] = Field(min_length=1)


class Changelog(_Strict):
    releases: list[Release] = Field(min_length=1)
    intro: str = ""


def format_error(err: dict, where: str) -> str:
    """One pydantic error as a line an author can act on.

    Pydantic's own message lists what a field SHOULD be but not what was
    actually written - "Input should be 'Data generation', ..." leaves
    you to go and find the offending value yourself. The hand-written
    validators this replaced always named it, so the input is appended
    here rather than accepting a quieter error as the price of using a
    schema."""
    field = ".".join(str(x) for x in err["loc"]) or "(entry)"
    msg = err["msg"]
    value = err.get("input")
    if err["type"] not in ("missing",) and isinstance(value, (str, int, float, bool)):
        text = str(value)
        if text.strip():
            msg = f"{msg} - got {text[:60]!r}"
    return f"{where}: {field} - {msg}"


# ---------------------------------------------------------------------
# contract/data-asset.yaml (REQ-PIPE-050).
#
# Declared here rather than in the gate that uses it, for the reason
# this module exists at all: one statement of a hand-authored file's
# shape, not one per reader. `_Strict` does the heavy lifting - a
# mistyped KEY is the failure this whole requirement is about, and
# extra="forbid" is what catches it. A dropped `delivery_months` gives
# a dataset every quarterly date when its author meant two, and nothing
# about the result looks wrong.


class CalendarDate(_Strict):
    period: NonEmptyStr
    date: str


class CadenceRule(_Strict):
    rule: NonEmptyStr


class CalendarVersionConfig(_Strict):
    """`dates` and `cadence` are both optional HERE and mutually
    exclusive in practice - the gate says which, because "exactly one of
    these two" with a useful error is not something a schema says
    readably."""

    effective_from: str
    changelog: list[NonEmptyStr]
    claim_window: str | None = None
    dates: list[CalendarDate] | None = None
    cadence: CadenceRule | None = None


class CalendarConfig(_Strict):
    name: NonEmptyStr
    description: NonEmptyStr
    versions: list[CalendarVersionConfig] = Field(min_length=1)
    # REQ-PIPE-053. Unversioned on purpose - the dates and the claim
    # window are the supplier agreement; this is an operational
    # threshold for when we want telling that they are running out.
    runway_warning_slots: int | None = Field(default=None, ge=1)


class NotExpectedPeriod(_Strict):
    """A reason is REQUIRED, not decoration: "no November file" with
    nothing beside it is indistinguishable, six months later, from
    somebody having forgotten to configure November."""

    period: NonEmptyStr
    reason: NonEmptyStr


class DatasetConfig(_Strict):
    id: NonEmptyStr
    name: NonEmptyStr
    table: NonEmptyStr
    calendar: NonEmptyStr
    delivery_months: list[NonEmptyStr] | None = None
    dates: list[CalendarDate] | None = None
    not_expected: list[NotExpectedPeriod] | None = None


class CollectionConfig(_Strict):
    id: NonEmptyStr
    name: NonEmptyStr
    contract: NonEmptyStr
    datasets: list[DatasetConfig] = Field(min_length=1)


class AgencyConfig(_Strict):
    id: NonEmptyStr
    name: NonEmptyStr
    collections: list[CollectionConfig] = Field(min_length=1)


class HierarchyConfig(_Strict):
    agencies: list[AgencyConfig] = Field(min_length=1)


class DataAsset(_Strict):
    data_asset_id: NonEmptyStr
    timezone: NonEmptyStr
    calendars: list[CalendarConfig] = Field(min_length=1)
    hierarchy: HierarchyConfig
