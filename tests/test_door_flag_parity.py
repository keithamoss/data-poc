"""The terminal's filing-decisions door offers every decision the flags would
record, wherever it applies (REQ-GHUB-165).

THE PARITY TEST (criteria 2 to 7). For every slot state the door can show,
and for a held supply of each label, it builds a real example in this test
worker's own database (MOTHMAN_TEST_DSN - never the bootstrapped history,
never a rolled-back transaction: the flag route opens connections of its
own), then tries EVERY filing decision through the flag route's own
implementation, filing_decisions.apply. Where apply would append an entry
for a decision the door does not offer on that state, the test fails -
unless HIDDEN names it, with a reason. One direction only: the door may
offer what apply then refuses (filing_queue.operations_for's own rule).

THE PERIODS ARE MINTED (`2099-...`) so nothing another test files can
answer this one's question, and are made calendar slots for the test's
length with the timing each state needs - so apply's own refusals are the
state's, not "that period is not on the calendar".
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

import test_supersession as _base
from qa_tools.common import decision_log as dl
from qa_tools.common import filing_decisions as fd
from qa_tools.common import (filing_queue, people, schedule, slot_state, slots,
                             supply_holds)
from test_supersession import DS, REAL_PERSON, TABLE, _filed

conn = _base.conn

AG, COL = "child-protection-family-support", "child-protection"

#: An open pair's example, by its period - for choose-file's file outcomes.
PAIRS: dict = {}

#: Decisions deliberately hidden from the door on a state, with why (criterion 2).
_QUEUE_ONLY_STATE = (
    "the queue lists a failed load as could-not-be-loaded and offers reject only "
    "(REQ-PIPE-153 criteria 5 and 6). WHERE THE FAILED LOAD IS ALONE IN ITS SLOT the period "
    "door shows that slot as awaiting a decision, which offers this; where another version "
    "shares the slot, NO door offers it - post-build-review #189 F3/F4, a question for "
    "Keith (should a door list every filed supply in a period?)")
HIDDEN: dict[tuple[str, str], str] = {
    (filing_queue.COULD_NOT_LOAD, fd.REFILE): _QUEUE_ONLY_STATE,
    (filing_queue.COULD_NOT_LOAD, fd.SUPERSEDE): _QUEUE_ONLY_STATE,
    (filing_queue.COULD_NOT_LOAD, fd.SUBSTITUTE): _QUEUE_ONLY_STATE,
    # PROVISIONAL (overnight #5, a question for Keith in the morning report):
    # the flags record a second substitution over a substituted or inherited
    # period; the door has offered only undoing it since REQ-GHUB-082 phase 3
    # ("offers undoing it and not redoing it").
    (slot_state.SUBSTITUTED, fd.SUBSTITUTE): (
        "redoing a substitution is de-substitute then substitute in the door, each with "
        "its own reason - kept as REQ-GHUB-082 built it, pending Keith"),
    (slot_state.INHERITED, fd.SUBSTITUTE): (
        "substituting over an inheritance is un-inherit then substitute in the door - kept "
        "as REQ-GHUB-082 built it, pending Keith"),
    # REQ-PIPE-194 criterion 4: nothing but settling is offered on an open pair.
    # The flags record a substitution over one (#189 F2, a question for Keith).
    (slot_state.TWO_FILES, fd.SUBSTITUTE): (
        "REQ-PIPE-194 criterion 4: an open pair is settled before anything else is "
        "decided for its period; whether the flags should refuse this too is Keith's"),
    ("held:agreement-refused", fd.PLACE): (
        "a hold on a dataset the agreement backstop refuses files itself once the "
        "agreement is put right (REQ-PIPE-173; #188 D9), so the door offers nothing to "
        "choose; on a real refused dataset placing is refused too (REQ-PIPE-163 c35) - the "
        "minted example's dataset is not refused, which is why the flags accept it here"),
    ("held:agreement-refused", fd.REJECT): (
        "as above: it files itself, so the door offers nothing on it"),
    ("held:schedule-ended", fd.REJECT): (
        "REQ-PIPE-163 criterion 22 and REQ-PIPE-154's decision: a hold labelled schedule "
        "ended offers only adding dates - the rule files it once dates cover it - so the "
        "door offers neither place nor reject on it, though the flags still record a reject"),
}


# ---------------------------------------------------------------------------
# Minted calendar slots.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _forget_its_filings(supply_dsn):
    """Each test forgets the cp-carers filings it made (post-build-review
    #191). Filed into minted periods that stop being calendar slots when the
    test ends, they outlived it, and the agreement backstop then read them as
    moved and froze cp-carers for every later module on the worker -
    test_replacement_setting's gate tests went red in CI."""
    import filing_support
    from qa_tools.common import filing, qa_store, supply_db

    with supply_db.connect(label="test-parity-forget") as c:
        qa_store.ensure_schema(c)
        (before,) = c.execute(f"SELECT coalesce(max(id), 0) FROM {filing.TABLE}").fetchone()
    yield
    with supply_db.connect(label="test-parity-forget") as c:
        filing_support.forget(c, "dataset_id = ? AND id > ?", [DS, before])


@pytest.fixture
def minted(monkeypatch):
    """{period: Slot} made part of cp-carers' calendar for this test."""
    from qa_tools.common import asset_time

    registry: dict[str, slots.Slot] = {}
    real = slots.slots_for_dataset

    def with_minted(dataset_id, until=None, agreement=None):
        out = real(dataset_id, until=until, agreement=agreement)
        return out + [s for s in registry.values() if s.dataset_id == dataset_id]

    monkeypatch.setattr(slots, "slots_for_dataset", with_minted)
    # AN OWES-NOTHING PERIOD (`nothing`) is one the dataset does not take part
    # in - the only kind a person may inherit into (REQ-PIPE-099).
    from qa_tools.common import inheritance

    real_date_of = schedule.date_of
    monkeypatch.setattr(schedule, "date_of",
                        lambda name, ds: registry[name].date if name in registry
                        else real_date_of(name, ds))
    real_part = inheritance._does_not_participate
    monkeypatch.setattr(inheritance, "_does_not_participate",
                        lambda ds, p: (True, f"{ds} owes nothing in {p} (minted)")
                        if p.startswith("2099-n") else real_part(ds, p))
    now = asset_time.now()

    def mint(timing: str) -> slots.Slot:
        """open: claimable, not yet due. due: past due, still open. closed:
        the next period's window has opened."""
        due = {"open": now + timedelta(days=10), "due": now - timedelta(days=5),
               "nothing": now - timedelta(days=5),
               "closed": now - timedelta(days=100)}[timing]
        opens = due - timedelta(days=30)
        closes = {"open": now + timedelta(days=40), "due": now + timedelta(days=40),
                  "nothing": now + timedelta(days=40),
                  "closed": now - timedelta(days=10)}[timing]
        name = f"2099-{timing[0]}{uuid.uuid4().hex[:8]}"
        slot = slots.Slot(dataset_id=DS, period=schedule.Period(name=name, date=due.date()),
                          due_at=due, grace=timedelta(0), claim_opens_at=opens,
                          closes_at=closes)
        registry[name] = slot
        return slot

    mint.now = now
    return mint


def _actor():
    return people.person_by_email(REAL_PERSON)


def _iso(at):
    return at.isoformat()


def _state(conn, mint_now, slot, *, filed=None, ever=True):
    return slot_state.state_of(conn, dataset_id=DS, slot=slot, now=mint_now,
                               filings={slot.name: {"supply_id": filed}} if filed else {},
                               ever_delivered=ever)


def _promote(conn, supply, table, period, *, amber=None):
    from qa_tools.common import promotion

    promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                      period=period, physical_tables=[table], actor=promotion.RULE_ACTOR,
                      actor_kind=dl.RULE, effective_at=_iso(_now()), amber=amber,
                      reason=promotion.AUTOMATIC_REASON)


def _now():
    from qa_tools.common import asset_time

    return asset_time.now()


def _person(conn, op, **kw):
    request = fd.Request(operation=op, dataset_id=DS, actor=_actor(), reason="seeding",
                         confirmed=True, **kw)
    key = fd.consequences(conn, request).key
    if key:
        from dataclasses import replace

        request = replace(request, acknowledged=key)
    return fd.apply(request, effective_at=_iso(_now()), conn=conn)


# ---------------------------------------------------------------------------
# One example per state. Each returns (SlotState the door shows, supply).
# ---------------------------------------------------------------------------

def _received_late(slot):
    return _iso(slot.due_at + timedelta(days=1)) if slot.due_at < _now() else _iso(
        slot.claim_opens_at + timedelta(days=1))


def ex_not_yet_due(conn, mint):
    s = mint("open")
    return _state(conn, mint.now, s), None


def ex_overdue(conn, mint):
    s = mint("due")
    return _state(conn, mint.now, s), None


def ex_never_supplied(conn, mint):
    s = mint("due")
    return _state(conn, mint.now, s, ever=False), None


def ex_closed_unfilled(conn, mint):
    s = mint("closed")
    return _state(conn, mint.now, s), None


def ex_awaiting_decision(conn, mint):
    s = mint("due")
    supply, _ = _filed(conn, s.name, _received_late(s))
    return _state(conn, mint.now, s, filed=supply), supply


def ex_amber_waiting(conn, mint):
    from qa_tools.common import amber_setting, promotion

    s = mint("due")
    supply, _ = _filed(conn, s.name, _received_late(s))
    promotion._record_amber_waiting(
        conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply, period=s.name,
        amber=amber_setting.Resolved("hold", amber_setting.ASSET, "2023-01-01"),
        effective_at=_iso(_now()))
    return _state(conn, mint.now, s, filed=supply), supply


def ex_promoted(conn, mint):
    s = mint("due")
    supply, table = _filed(conn, s.name, _received_late(s))
    _promote(conn, supply, table, s.name)
    return _state(conn, mint.now, s, filed=supply), supply


def ex_awaiting_acknowledgement(conn, mint):
    from qa_tools.common import amber_setting

    s = mint("due")
    supply, table = _filed(conn, s.name, _received_late(s))
    _promote(conn, supply, table, s.name, amber=amber_setting.Resolved(
        "promote-and-acknowledge", amber_setting.COLLECTION, "2023-01-01"))
    return _state(conn, mint.now, s, filed=supply), supply


def ex_returned(conn, mint):
    s = mint("due")
    supply, table = _filed(conn, s.name, _received_late(s))
    _promote(conn, supply, table, s.name)
    _person(conn, fd.DEMOTE, period=s.name, supply=supply)
    return _state(conn, mint.now, s, filed=supply), supply


def ex_rejected(conn, mint):
    s = mint("due")
    supply, _ = _filed(conn, s.name, _received_late(s))
    _person(conn, fd.REJECT, period=s.name, supply=supply)
    return _state(conn, mint.now, s, filed=supply), supply


def ex_substituted(conn, mint):
    earlier = mint("closed")
    held, table = _filed(conn, earlier.name, _received_late(earlier))
    _promote(conn, held, table, earlier.name)
    s = mint("due")
    _person(conn, fd.SUBSTITUTE, period=s.name, stands_on=earlier.name, supply=held)
    return _state(conn, mint.now, s), None


def ex_inherited(conn, mint):
    from qa_tools.common import inheritance

    earlier = mint("closed")
    held, table = _filed(conn, earlier.name, _received_late(earlier))
    _promote(conn, held, table, earlier.name)
    from qa_tools.common import period_schema

    s = mint("nothing")
    # A period's schema exists from its birth (inherit_into); a minted one's
    # is made here.
    period_schema.ensure_period_schema(conn, s.name)
    inheritance.inherit_one(conn, dataset_id=DS, period=s.name, actor=REAL_PERSON,
                            reason="seeding", effective_at=_iso(_now()))
    return _state(conn, mint.now, s), None


def ex_not_supplied_accepted(conn, mint):
    s = mint("closed")
    _person(conn, fd.MARK_NOT_SUPPLIED, period=s.name)
    return _state(conn, mint.now, s), None


def ex_another_version_waiting(conn, mint):
    st, supply = ex_promoted(conn, mint)
    later, _ = _filed(conn, st.period, _iso(_now() - timedelta(hours=1)))
    (waiting,) = filing_queue.waiting_over_promoted(conn, [st])
    return waiting, later


def ex_rechecked_worse(conn, mint):
    """Promoted on green, re-checked red (REQ-PIPE-164 criterion 15): the
    queue's own heading. The verdict is set for the example - a minted
    supply has no check results to read one from."""
    from dataclasses import replace
    from unittest import mock

    from qa_tools.common import supply_status

    with mock.patch.object(supply_status, "status", return_value="green"):
        st, supply = ex_promoted(conn, mint)
        got = _person(conn, fd.RECHECK, period=st.period, supply=supply)
        from qa_tools.common import recheck

        recheck.clear(got.owed[0], "rk")   # its re-check ran (#192 F2)
    with mock.patch.object(supply_status, "status", return_value="red"):
        (item,) = filing_queue._rechecked_worse(
            conn, COL, [replace(st, state=slot_state.AWAITING_ACKNOWLEDGEMENT)])
    return item, supply


def ex_could_not_load(conn, mint):
    import filing_support
    from qa_tools.common import assignment, load_log

    s = mint("due")
    arrival = f"t{uuid.uuid4().hex[:10]}"
    load_log.record(f"probe-{arrival}", DS, f"{TABLE}__{arrival}", load_log.FAILED,
                    _iso(_now()), reason="the file is empty", conn=conn)
    supply = f"{DS}@{arrival}"
    filing_support.file(assignment.Assignment(
        dataset_id=DS, supply_id=supply, slot=s.name, branch=assignment.OPEN_UNFILLED,
        considered=(s.name,)))
    (got,) = [x for x in filing_queue.could_not_load(conn, COL) if x.supply == supply]
    return got, supply


def ex_two_files(conn, mint):
    """An open pair - Birth Registrations', whose pattern admits two files a
    day (pair_support), on a free day of the coming year."""
    from datetime import date

    from pair_support import DS as BR
    from pair_support import Pair, _at, free_day

    day = free_day(conn, date(2026, 11, 1))
    p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                          (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
    slot = slots.slot_named(BR, p.period)
    st = slot_state.state_of(conn, dataset_id=BR, slot=slot, now=mint.now,
                             filings={p.period: {"supply_id": p.pair}}, ever_delivered=True,
                             two_files=tuple(f for f, _ in p.files))
    PAIRS[p.period] = p
    return st, p.pair


#: Every slot state the door can show (criterion 5): slot_state's own, plus
#: the two the queue adds - each needs an example below.
EXAMPLES = {
    slot_state.NOT_YET_DUE: ex_not_yet_due,
    slot_state.OVERDUE: ex_overdue,
    slot_state.NEVER_SUPPLIED: ex_never_supplied,
    slot_state.AWAITING_DECISION: ex_awaiting_decision,
    slot_state.AMBER_WAITING: ex_amber_waiting,
    slot_state.PROMOTED: ex_promoted,
    slot_state.AWAITING_ACKNOWLEDGEMENT: ex_awaiting_acknowledgement,
    slot_state.RETURNED: ex_returned,
    slot_state.REJECTED: ex_rejected,
    slot_state.SUBSTITUTED: ex_substituted,
    slot_state.INHERITED: ex_inherited,
    slot_state.NOT_SUPPLIED_ACCEPTED: ex_not_supplied_accepted,
    slot_state.TWO_FILES: ex_two_files,
    filing_queue.ANOTHER_VERSION_WAITING: ex_another_version_waiting,
    filing_queue.COULD_NOT_LOAD: ex_could_not_load,
    filing_queue.RECHECKED_WORSE: ex_rechecked_worse,
    # A closed, unfilled period is OVERDUE with `closed` set: its own offers.
    "closed-unfilled": ex_closed_unfilled,
}

def ov_late(conn, mint):
    """Awaiting a decision, recorded LATE - so excuse-lateness applies."""
    import filing_support
    from qa_tools.common import assignment

    s = mint("due")
    supply = f"{DS}@late{uuid.uuid4().hex[:10]}"
    filing_support.file(assignment.Assignment(
        dataset_id=DS, supply_id=supply, slot=s.name, branch=assignment.OPEN_UNFILLED,
        considered=(s.name,), received_at=s.due_at + timedelta(days=1)))
    return _state(conn, mint.now, s, filed=supply), supply


def ov_excused(conn, mint):
    """Late, with its lateness excused - so withdraw-excuse applies."""
    state, supply = ov_late(conn, mint)
    _person(conn, fd.EXCUSE_LATENESS, period=state.period, supply=supply)
    return state, supply


def ov_superseded_under_promoted(conn, mint):
    """Promoted, with an earlier version superseded - so un-supersede applies."""
    from qa_tools.common import supersession

    s = mint("due")
    older, _ = _filed(conn, s.name, _received_late(s))
    newer, table = _filed(conn, s.name, _iso(_now() - timedelta(hours=2)))
    with conn.raw.transaction():
        supersession.supersede_earlier(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                       period=s.name, newer=newer, effective_at=_iso(_now()))
    _promote(conn, newer, table, s.name)
    return _state(conn, mint.now, s, filed=newer), newer


#: STATES OVERLAID WITH WHAT THE LOG HOLDS (post-build-review #189 F1): the
#: three operations offered from recorded facts rather than from a slot's state
#: - excuse-lateness, withdraw-excuse and un-supersede - had no example the
#: flags would accept, so the parity loop could not see them go missing. Each
#: overlay names the operation it exists for, and asserts the flags accept it.
OVERLAYS = {
    "late": (ov_late, fd.EXCUSE_LATENESS),
    "excused": (ov_excused, fd.WITHDRAW_EXCUSE),
    "superseded-under-promoted": (ov_superseded_under_promoted, fd.UN_SUPERSEDE),
}


#: A held supply of each label (REQ-PIPE-163 criterion 10).
HOLD_LABELS = {
    "plain": {"unavailable": [], "considered": []},
    "correction": {"unavailable": [], "considered": [], "correction": "PYTEST-1",
                   "correction_reason": "seeding"},
    "schedule-ended": {"unavailable": [], "considered": [], "schedule_ended": True,
                       "last_period": "2027-Q4"},
    "agreement-refused": {"unavailable": [], "considered": [], "agreement_refused": True},
    # REQ-PIPE-179: received while its dataset is turned off.
    "turned-off": {"unavailable": [], "considered": [],
                   "turned_off": {"effective_to": "2025-03-31", "reason": "paused",
                                  "level": "dataset", "version_from": "2023-01-01"}},
}

#: The label each is worked out as, from configuration as it stands
#: (REQ-PIPE-179 criterion 18) - set for the test, since a minted period's
#: receipt is covered by its own open slot whatever the record says.
_LABEL_AS = {"plain": "held", "correction": "held", "schedule-ended": "schedule ended",
             "agreement-refused": "held", "turned-off": "turned off"}


def _every_state() -> list[str]:
    """Every state the door can show: the ones it has words for
    (filing_tui._HOW_IT_READS), plus the two the queue adds - so a state
    added later without an example fails criterion 5 rather than passing."""
    import re

    from cli import filing_tui

    # AND slot_state's own (#189 F6): a state added there with no wording
    # entry is still a state the door can show.
    own = {v for k, v in vars(slot_state).items()
           if k.isupper() and isinstance(v, str) and re.fullmatch(r"[a-z]+(-[a-z]+)*", v)}
    return sorted(set(filing_tui._HOW_IT_READS) | own
                  | {filing_queue.ANOTHER_VERSION_WAITING, filing_queue.COULD_NOT_LOAD,
                     filing_queue.RECHECKED_WORSE})


# ---------------------------------------------------------------------------
# The door and the flag route.
# ---------------------------------------------------------------------------

def _door_offers(conn, state) -> set[str]:
    supply_scoped, period_scoped = filing_queue.operations_for(state)
    return (set(supply_scoped) | set(period_scoped)
            | set(filing_queue.excuse_offers(conn, state))
            | set(filing_queue.supersede_offers(conn, state)))


def _request_for(op, state, supply, mint, conn):
    """The arguments the flags would pass for `op` on this example."""
    kw = dict(operation=op, dataset_id=state.dataset_id, actor=_actor(), reason="parity",
              confirmed=True, period=state.period, supply=supply)
    target = mint("due")
    if op in (fd.REFILE, fd.PLACE):
        kw["to_period"] = target.name
    if op == fd.PLACE:
        kw["period"] = None
    if op == fd.SUBSTITUTE:
        earlier = mint("closed")
        held, table = _filed(conn, earlier.name, _received_late(earlier))
        _promote(conn, held, table, earlier.name)
        kw.update(stands_on=earlier.name, supply=held)
    if op == fd.UN_SUPERSEDE:
        from qa_tools.common import supersession

        versions = supersession.superseded_in(conn, state.dataset_id, state.period)
        kw["supply"] = versions[0]["supply"] if versions else supply
    if op == fd.CHOOSE_FILE:
        from qa_tools.common import settlement

        pair = PAIRS.get(state.period)
        if pair is not None:
            kw["file_outcomes"] = (settlement.Answer(pair.files[0][0], settlement.SUPPLY),
                                   settlement.Answer(pair.files[1][0], settlement.SUPERSEDE))
    return fd.Request(**kw)


#: What a refusal looks like from apply - every other exception is a defect
#: the test should surface, not swallow.
def _refusals():
    from qa_tools.common import inheritance, substitution

    return (dl.DecisionRefused, fd.NotOffered, people.UnknownActor,
            substitution.SubstitutionRefused, inheritance.InheritanceRefused)


def _accepted(conn, request) -> bool:
    """Whether the flag route would APPEND an entry: changed, not refused.
    An unchanged outcome counts as not accepted (criterion 4)."""
    from dataclasses import replace

    try:
        key = fd.consequences(conn, request).key
        got = fd.apply(replace(request, acknowledged=key or None),
                       effective_at=_iso(_now()), conn=conn)
    except _refusals():
        return False
    return got.changed


@pytest.fixture
def quiet(monkeypatch):
    """No ticket reconciliation and no knock-on runs while trying decisions."""
    from qa_tools.common import knock_on

    monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
    monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])


class TestEveryStateHasAnExample:
    """Criterion 5: a state with no example fails, naming it."""

    def test_every_state_the_door_can_show_has_one(self):
        missing = [s for s in _every_state() if s not in EXAMPLES]
        assert not missing, f"no parity example for: {missing}"

    @pytest.mark.parametrize("name", sorted(EXAMPLES))
    def test_each_example_shows_its_state(self, conn, minted, name):
        state, _ = EXAMPLES[name](conn, minted)
        want = slot_state.OVERDUE if name == "closed-unfilled" else name
        assert state.state == want, f"{name}: built {state.state}"
        if name == "closed-unfilled":
            assert state.closed


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_the_door_offers_what_the_flags_would_record(conn, minted, quiet, name):
    """Criteria 2, 3 and 4: every operation, from filing_decisions.OPERATIONS."""
    hidden_here = []
    for op in fd.OPERATIONS:
        state, supply = EXAMPLES[name](conn, minted)
        offered = _door_offers(conn, state)
        request = _request_for(op, state, supply, minted, conn)
        if op in offered or (state.state, op) in HIDDEN:
            continue
        if _accepted(conn, request):
            hidden_here.append(op)
    assert not hidden_here, (
        f"on a {name} slot the flags record {hidden_here} but the door does not offer "
        f"them - offer them, or name them in HIDDEN with a reason")


@pytest.mark.parametrize("name", sorted(OVERLAYS))
def test_what_the_log_holds_is_offered_where_the_flags_record_it(conn, minted, quiet, name):
    """Criteria 2 and 3 for the operations offered from recorded facts
    (#189 F1): the overlay's own operation is accepted by the flags AND
    offered by the door, and nothing else the flags record is hidden."""
    build, own = OVERLAYS[name]
    state, supply = build(conn, minted)
    assert own in _door_offers(conn, state), f"{name}: the door does not offer {own}"
    assert _accepted(conn, _request_for(own, state, supply, minted, conn)), (
        f"{name}: the flags refuse {own} - the overlay no longer exercises it")
    hidden_here = []
    for op in fd.OPERATIONS:
        state, supply = build(conn, minted)
        if op in _door_offers(conn, state) or (state.state, op) in HIDDEN:
            continue
        if _accepted(conn, _request_for(op, state, supply, minted, conn)):
            hidden_here.append(op)
    assert not hidden_here, f"{name}: the flags record {hidden_here}, the door hides them"


@pytest.mark.parametrize("label", sorted(HOLD_LABELS))
def test_a_held_supply_offers_what_the_flags_would_record(conn, minted, quiet, label,
                                                          monkeypatch):
    """Criterion 2's held supplies, one per label."""
    import filing_support
    from qa_tools.common import turned_off

    monkeypatch.setattr(turned_off, "label_at", lambda ds, at, agreement=None:
                        turned_off.Label(_LABEL_AS[label]))

    hidden_here = []
    # SUPPLY-SCOPED ONLY: a held supply has no period, and the flags take a
    # period-scoped decision only with --period, about that period - never
    # about a held supply.
    for op in fd.SUPPLY_SCOPED:
        period = minted("due").name
        supply, _ = _filed(conn, period, _iso(_now() - timedelta(days=1)))
        (delivery,) = conn.execute("SELECT delivery FROM qa.filing_current WHERE "
                                   "supply_id = ?", [supply]).fetchall()[0]
        filing_support.place(conn, DS, supply, None, delivery)
        supply_holds.raise_hold(conn, dataset_id=DS, supply_id=supply,
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason=HOLD_LABELS[label], raised_by="pytest")
        (row,) = [r for r in filing_queue.held_in(conn, COL) if r.supply == supply]
        # THE LABEL TOOK (#189 F5): a renamed reason key would otherwise make
        # every example a plain hold and still pass.
        assert (row.schedule_ended, row.agreement_refused, row.turned_off) == (
            label == "schedule-ended", label == "agreement-refused", label == "turned-off"), label
        offered = set(filing_queue.held_operations(row))
        if op in offered or (f"held:{label}", op) in HIDDEN:
            continue
        # The flags take --period for everything but place and a held
        # supply's reject - a period of the dataset, which it is not filed to.
        request = fd.Request(operation=op, dataset_id=DS, actor=_actor(), reason="parity",
                             confirmed=True, supply=supply,
                             period=None if op in (fd.PLACE, fd.REJECT) else period,
                             to_period=minted("due").name if op in (fd.PLACE, fd.REFILE)
                             else None)
        if _accepted(conn, request):
            hidden_here.append(op)
    assert not hidden_here, (
        f"on a held supply ({label}) the flags record {hidden_here} but the door does "
        f"not offer them")


class TestTheTerminalOnlyOnesNeverReachGitHub:
    """Criterion 6: every filing_decisions.TERMINAL_ONLY operation, raised as
    a GitHub comment, appends nothing and says it is made in the terminal."""

    @pytest.mark.parametrize("op", fd.TERMINAL_ONLY)
    def test_refused_naming_the_terminal(self, conn, op):
        from qa_tools.common import filing_from_github as gh

        before = len(dl.decisions_for(conn, DS))
        comment = gh.Comment(author="someone", body=f"/{op}\nwhy", slot_key=f"{DS}/2026-Q1")
        with pytest.raises(dl.DecisionRefused, match="made in the terminal"):
            gh.read(comment)
        assert len(dl.decisions_for(conn, DS)) == before

    def test_there_are_terminal_only_operations_to_check(self):
        assert set(fd.TERMINAL_ONLY) >= {fd.CHOOSE_FILE, fd.PLACE}


class TestUnSupersedeIsOfferedWhereItApplies:
    """Criterion 1: wherever a superseded version could come back, not only
    on a rejected slot - and with how many it could bring back."""

    def _superseded_then(self, conn, minted):
        from qa_tools.common import supersession

        s = minted("due")
        older, _ = _filed(conn, s.name, _received_late(s))
        newer, _ = _filed(conn, s.name, _iso(_now() - timedelta(hours=2)))
        with conn.raw.transaction():
            supersession.supersede_earlier(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                           period=s.name, newer=newer,
                                           effective_at=_iso(_now()))
        return s, older, newer

    def test_offered_once_the_newer_one_is_decided_with_its_count(self, conn, minted,
                                                                 monkeypatch, quiet):
        import contextlib

        from cli import filing_tui

        s, older, newer = self._superseded_then(conn, minted)
        _promote(conn, newer, f"{TABLE}__{newer.split('@')[1]}", s.name)
        state = _state(conn, minted.now, s, filed=newer)
        assert fd.UN_SUPERSEDE in filing_queue.supersede_offers(conn, state)
        monkeypatch.setattr(filing_tui, "open_log", lambda: contextlib.nullcontext(conn))
        seen = []
        monkeypatch.setattr(filing_tui.common, "select",
                            lambda msg, choices, **k: seen.extend(choices) or None)
        filing_tui._decide_on(state, offer=filing_tui._offers(
            state, filing_queue.operations_for(state)[0]))
        assert any(c.startswith("un-supersede") and "(1 earlier version)" in c for c in seen)

    def test_not_offered_while_another_version_waits(self, conn, minted):
        s, older, newer = self._superseded_then(conn, minted)
        state = _state(conn, minted.now, s, filed=newer)
        assert filing_queue.supersede_offers(conn, state) == ()


class TestCriticFindingsOn189:
    """delivery-critic on REQ-GHUB-165 (post-build-review #189). Each failed
    before its fix."""

    def test_7_the_after_placing_offer_goes_through_the_one_combiner(self, monkeypatch):
        """F7: offered after a placement, a late supply's excuse was missing -
        the offer took the slot's operations alone, not _offers()."""
        import contextlib

        from cli import filing_tui

        state = slot_state.SlotState(dataset_id=DS, period="2099-x", state=slot_state.AWAITING_DECISION,
                                     supply="s")
        monkeypatch.setattr(filing_tui, "open_log", lambda: contextlib.nullcontext(None))
        monkeypatch.setattr(filing_queue, "slots_of", lambda *a, **k: [state])
        monkeypatch.setattr(filing_tui.common, "confirm", lambda *a, **k: True)
        monkeypatch.setattr(filing_tui, "_excuse_offers", lambda s: (fd.EXCUSE_LATENESS,))
        monkeypatch.setattr(filing_tui, "_supersede_offers", lambda s: ())
        got = {}
        monkeypatch.setattr(filing_tui, "_decide_on", lambda s, offer: got.update(offer=offer))
        filing_tui._offer_next_decision(DS, "2099-x", "s")
        assert fd.EXCUSE_LATENESS in got["offer"]

    def test_8_the_held_menu_is_what_held_operations_offers(self, monkeypatch):
        """F8: the menu was hard-coded, so an operation held_operations added
        would never reach it."""
        from cli import filing_tui

        row = filing_queue.HeldRow(dataset_id=DS, dataset_name="Carers", supply="s",
                                   received_at=None, received_text="", why="w",
                                   schedule_ended=False)
        monkeypatch.setattr(filing_queue, "held_operations", lambda r: (fd.REJECT,))
        seen = []
        monkeypatch.setattr(filing_tui.common, "select",
                            lambda msg, choices, **k: seen.extend(choices) or None)
        filing_tui.held_flow(row)
        assert len(seen) == 1 and seen[0].startswith("reject")

    def test_10_promoting_nothing_does_not_say_none_is_promoted(self, conn, minted, quiet):
        """F10: a promote naming no supply on an empty period said 'None is
        already promoted into ...'."""
        s = minted("due")
        request = fd.Request(operation=fd.PROMOTE, dataset_id=DS, actor=_actor(),
                             reason="parity", confirmed=True, period=s.name, supply=None)
        before = len(dl.decisions_for(conn, DS))
        with pytest.raises(dl.DecisionRefused) as refused:
            fd.apply(request, effective_at=_iso(_now()), conn=conn)
        assert "None" not in str(refused.value) and "--supply" in str(refused.value)
        assert len(dl.decisions_for(conn, DS)) == before, "nothing was recorded"
