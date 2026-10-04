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
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class BlockedBy(_Strict):
    """What a deferred criterion is waiting on, resolvably (REQ-DOCS-073).

    A LIST OF SPRINTS AND/OR A LIST OF REQUIREMENTS, not one or the
    other (Keith, 2026-09-26). Requirement ids alone cannot express the
    commonest case in the register - seventeen of twenty-eight
    deferrals wait on the promotion sprint, which owns no requirement
    yet, so there is no id to point at. Sprints alone would lose the
    precision the free text already has, where a deferral names
    `REQ-PIPE-062` rather than the sprint containing it.

    `unowned` IS THE THIRD CASE AND IT IS EXPLICIT ON PURPOSE. Several
    criteria are unmet while waiting on nothing at all - they need a
    requirement written before anyone can build them. That is a
    different thing from being blocked, and it matters: a sprint whose
    remainder is unowned has work of its own to do, where one waiting
    on another sprint does not. Spelling it out rather than letting two
    empty lists mean it keeps "nobody has to do anything yet" distinct
    from "somebody forgot to fill this in".
    """

    sprints: list[int] = []
    requirements: list[str] = []
    unowned: bool = False

    @model_validator(mode="after")
    def _says_something(self) -> "BlockedBy":
        named = bool(self.sprints or self.requirements)
        if named and self.unowned:
            raise ValueError(
                "cannot be both `unowned` and waiting on a named sprint or "
                "requirement - pick whichever is true")
        if not named and not self.unowned:
            raise ValueError(
                "must name at least one sprint or requirement, or say "
                "`unowned: true`")
        return self


class UnmetCriterion(_Strict):
    """One acceptance criterion a `built` requirement does not meet.

    WHY A FIELD AND NOT A THIRD STATUS (post-build-review #33, Keith's
    own call, 2026-09-25): `status` is what the register is indexed and
    filtered by, so a third value would make every consumer of it
    decide what "partly built" means - and the honest answer for the
    requirement that prompted this is that it IS built and has a hole
    in it. A hole is a property of the record, not a different kind of
    record.

    ALL FOUR FIELDS ARE REQUIRED, and that is the point rather than
    strictness for its own sake. "Some criteria are unmet" is what the
    prose already said, in a `decisions:` note nobody had to read; a
    record that cannot name WHICH, WHY and WHO NEXT is the same
    sentence in a different place.

    `owner` STAYS FREE TEXT ALONGSIDE `blocked_by` rather than being
    replaced by it (REQ-DOCS-073's own non-functional constraint). The
    two say different things and both are worth keeping: `blocked_by`
    is what the tooling resolves, `owner` is the sentence explaining
    what about that blocker matters here, which an id cannot carry.
    The register already proved the prose alone insufficient - seven
    deferrals pointed at work that had since shipped and nothing could
    tell, because "waiting on X" and "was waiting on X, which has
    landed" are indistinguishable to anything reading prose.
    """

    criterion: NonEmptyStr
    why: NonEmptyStr
    owner: NonEmptyStr
    blocked_by: BlockedBy


class Retirement(_Strict):
    """Why a requirement - or one of its criteria - is retired
    (REQ-DOCS-143 criteria 2 and 3).

    WHEN, WHO, AND WHAT REPLACED IT are all required: a retirement that
    cannot name its successor is a deletion with extra steps, and the
    successor is the one thing a reader arriving at a retired entry
    needs next. `reason` is optional because the successor's own
    decisions usually say why, and a second account invites drift.
    """

    date: str = Field(pattern=_DATE_PATTERN)
    by: NonEmptyStr
    replaced_by: list[str] = Field(min_length=1)
    reason: NonEmptyStr | None = None


class RetiredCriterion(Retirement):
    """One retired acceptance criterion, by its 1-based position - the
    numbering every decision and amendment already cites, which is why
    the criterion's text stays in place rather than being deleted
    (REQ-DOCS-143 criterion 5: history unchanged)."""

    criterion: int = Field(ge=1)


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

    # REQ-DOCS-143. `retired` is present exactly when status is
    # "retired"; `retired_criteria` lets one criterion go while the rest
    # of the requirement keeps its status. Both checked as whole-record
    # rules in retirement_problems() below, so the validator can report
    # every problem in one run.
    retired: Retirement | None = None
    retired_criteria: list[RetiredCriterion] = []

    @field_validator("date_written")
    @classmethod
    def _real_date(cls, v: str) -> str:
        if v and not re.match(_DATE_PATTERN, v):
            raise ValueError('must be a real "YYYY-MM-DD" date')
        return v

    def retired_positions(self) -> set[int]:
        """1-based positions of this requirement's retired criteria."""
        return {c.criterion for c in self.retired_criteria}

    def counted_criteria(self) -> int:
        """Criteria that still count toward a sprint - none for a retired
        requirement, and never a retired criterion (REQ-DOCS-143
        criterion 4)."""
        if self.status == "retired":
            return 0
        return len(self.acceptance_criteria) - len(self.retired_positions())

    def retirement_problems(self) -> list[str]:
        """Whole-record rules for REQ-DOCS-143 criteria 2 and 3."""
        out = []
        if self.status == "retired" and self.retired is None:
            out.append("status is 'retired' but it has no `retired:` block saying when, "
                       "who decided and what replaced it")
        if self.retired is not None and self.status != "retired":
            out.append(f"has a `retired:` block but status is {self.status!r}")
        positions = [c.criterion for c in self.retired_criteria]
        for n in positions:
            if n > len(self.acceptance_criteria):
                out.append(f"retired_criteria names criterion {n}, but there are only "
                           f"{len(self.acceptance_criteria)}")
        if len(positions) != len(set(positions)):
            out.append("retired_criteria names the same criterion more than once")
        return out

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
        # A retired requirement is history: it may never have been
        # signed (a draft superseded before sign-off), and demanding a
        # signature now would be asking someone to agree to something
        # nobody will build.
        return self.status not in ("not_started", "retired") and self.signed_off is None

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
        # A RETIRED requirement keeps whatever it carried as history
        # (REQ-DOCS-143 criterion 5) - one that was built still names
        # the tests and code that met it.
        if self.status in ("built", "retired"):
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


#: THE AMBER SETTING'S THREE VALUES, STRICTEST FIRST (REQ-PIPE-122
#: criteria 1 and 2). This tuple is the one order; every list of them -
#: an error message, a comment, the documentation - takes it from here.
AMBER_SETTINGS = ("hold", "promote-and-acknowledge", "promote")


class AmberSettingVersion(_Strict):
    """One effective-dated value of the amber setting (REQ-PIPE-122
    criterion 4) - the same shape as a calendar's versions, so a setting
    change is authored as a new version rather than an edit."""
    effective_from: str = Field(pattern=_DATE_PATTERN)
    value: Literal[*AMBER_SETTINGS]  # type: ignore[valid-type]
    changelog: list[NonEmptyStr] = Field(min_length=1)


class AmberSetting(_Strict):
    versions: list[AmberSettingVersion] = Field(min_length=1)


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
    #: OPTIONAL HERE, AND ONLY HERE (REQ-PIPE-106 criteria 1 and 2). A
    #: dataset either names a calendar or declares `no_calendar:`
    #: DELIBERATELY, and this model cannot express "exactly one of these
    #: two" - so the choice is enforced by validate_schedule.py, which
    #: fails a dataset carrying neither, a dataset carrying both, and a
    #: dataset whose declaration is not one of the two recognised values.
    #:
    #: WHY NOT LEAVE IT REQUIRED AND LET THE DECLARATION BE A SEPARATE
    #: THING: pydantic would then reject a legitimately calendar-less
    #: dataset before any of that reasoning ran, and the reader would get
    #: "calendar is required and is not there" for a file that is
    #: correct. The gate's own message is the one worth showing.
    calendar: NonEmptyStr | None = None
    #: The deliberate declaration that this dataset has NO calendar -
    #: `not-yet-agreed` for sample data that will graduate, `never` for a
    #: one-off extraction that has supplies and no cadence at all
    #: (REQ-PIPE-106 criterion 3). The VALUE is checked by
    #: validate_schedule.py rather than by a Literal here, so a mistyped
    #: one gets a message explaining what the two mean.
    no_calendar: NonEmptyStr | None = None
    #: WHEN THIS DATASET GRADUATED - the date it started owing supplies
    #: (REQ-PIPE-106 criterion 16). Absent for every dataset that has
    #: always had a calendar, which today is all seven.
    owes_from: date | None = None
    #: How this dataset's files are named, as a regular expression
    #: (REQ-PIPE-058). Optional HERE because a dataset can coherently
    #: exist while its pattern is being added; whether a dataset that is
    #: owed supplies may go without one is the arrival-pattern gate's
    #: question, and it fails on exactly that.
    arrival_pattern: NonEmptyStr | None = None
    delivery_months: list[NonEmptyStr] | None = None
    dates: list[CalendarDate] | None = None
    not_expected: list[NotExpectedPeriod] | None = None
    amber_setting: AmberSetting | None = None


class CollectionConfig(_Strict):
    id: NonEmptyStr
    name: NonEmptyStr
    contract: NonEmptyStr
    #: What one delivery IS, for this source (REQ-PIPE-057 criteria 2
    #: and 3). Optional HERE and a hard failure at recognition time -
    #: the two are not in tension: a collection can coherently exist
    #: while its transport is being described, and nothing may READ a
    #: delivery from a source that has not said what one is.
    delivery_boundary: NonEmptyStr | None = None
    amber_setting: AmberSetting | None = None
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
    #: Which slots get a ticket (REQ-PIPE-083 criterion 21). Optional
    #: with a default, because an asset that has never thought about
    #: ticketing should not have to declare that it has not - and the
    #: default is the one that keeps the queue worth reading.
    ticket_policy: Literal["all", "needs-action"] = "needs-action"
    #: Whether this asset's history is SYNTHETIC - generated, and so safe
    #: to delete and regenerate (REQ-PIPE-144 criterion 43, REQ-GEN-135
    #: criterion 8). Defaults to False: an asset that never said it was
    #: synthetic is treated as real, which is the direction that refuses.
    synthetic: bool = False
    #: REQUIRED, with no default (REQ-PIPE-122 criterion 9): an asset
    #: that says nothing about amber is a configuration error, never a
    #: quiet "promote".
    amber_setting: AmberSetting
