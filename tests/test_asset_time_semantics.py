"""Characterization pin for arrival/as-of semantics (REQ-PIPE-048).

WRITTEN BEFORE THE REFACTOR, DELIBERATELY. That requirement's own NFR
asks for exactly this and says why: the current behaviour is correct by
COINCIDENCE in at least one place - clipDatasetToAsOf() compares date
STRINGS, which gives end-of-day semantics by accident rather than by
design - so "did the refactor change anything" cannot be answered by
reading the new code. It has to be measured against what the old code
actually produced.

tests/fixtures/arrival_semantics_golden.json is that measurement: every
run in committed history, with its arrival instant and its
early/onTime/late verdict. Regenerate it ONLY when the committed
history is legitimately rebuilt, never to make a failing test pass - a
diff here after a timezone change is the finding, not the noise.

REGENERATED THREE TIMES - twice on 2026-09-23, both checked rather than
assumed, and once on 2026-09-28 to UNDO an extension that should never
have happened (see TestEveryCommittedArrivalKeepsItsVerdict's own
docstring). `mothman debug capture-arrival-golden` is how, so the one
operation that can silently destroy this pin has a recorded procedure
instead of an ad-hoc script.

  1. For REQ-GEN-042's rebuild, which renamed every run_id. The verdict
     distribution came back IDENTICAL - 131 onTime, 16 early, 3 late
     over the same 150 arrivals and 7 datasets.

  2. For REQ-GEN-043's, where 16 Birth Registrations runs came back
     with a DIFFERENT verdict under the same run_id, which is exactly
     the shape this pin exists to catch and was not waved through.
     What it turned out to be: run identity now comes from RECEIPT
     ORDER rather than from the generator's slot order, so a resupply
     for an earlier period that arrived after a later period's first
     delivery now sorts where it actually landed. Proved, not assumed,
     by comparing the committed history before and after: the multiset
     of 42 receipt instants is identical, 23 run_ids carry a different
     one, and mapping instant -> verdict instead of run_id -> verdict
     gives ZERO differences. The verdicts never moved; the labels did.

     That check is worth repeating verbatim next time, because the
     distribution staying at 131/16/3 would have looked like proof on
     its own and is not - a permutation preserves it.

THE INSTANT HALF OF THIS PIN MEASURED NOTHING until that second
capture. `arrivalHistory` rows carry no instant, so every `arrivedAt`
in the golden was None and test_no_arrival_instant_changed compared
None to None, 150 times. The instants live in `arrivalByRun`, which is
where the capture command reads them from now. A pin that cannot fail
is worse than no pin, and this one was written specifically to catch a
verdict-preserving eight-hour shift - precisely the case the vacuous
field would have missed.

WHAT 048 DELIBERATELY DOES CHANGE, so it is not mistaken for a
regression: a timestamp with no offset currently gets silently treated
as UTC (pipeline/cadence.py's own `if ... tzinfo is None` branch, whose
docstring admits it). Criterion 4 makes that a loud failure. The
verdicts below must not move; the handling of a naked value must.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline import cadence
from qa_tools.common import asset_time

# NEEDS A BOOTSTRAPPED DEPLOYMENT (plans/tooling.md #27). This module
# reads `reports/*.json`, which is built from the deployment's recorded
# QA history - so it belongs in the CI job that bootstraps one. Nothing
# in a signature says so, which is why the mark is here rather than
# derived; tests/test_publish.py asserts it is not forgotten.
pytestmark = pytest.mark.needs_deployment


def _instant_as_written_before_048(value) -> datetime | None:
    """One stored arrival as an instant, under the pre-048 reading.

    A value with no offset is taken as UTC - which is exactly what
    classify_arrival() used to do silently, and exactly what this
    requirement stops. It survives HERE, in one test, for the single
    purpose of proving that the values written the new way mean the same
    thing the old ones did.
    """
    if value in (None, "None"):
        return None
    parsed = datetime.fromisoformat(str(value).replace(" ", "T"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).parent / "fixtures" / "arrival_semantics_golden.json"

_REPORTS = {
    "birth_registrations_dashboard.json": None,
    "child_protection_dashboard.json": None,
}


def _built_datasets():
    """Every real dataset from the built dashboard JSON, keyed by id.

    Skips rather than fails when the reports are absent - they are
    gitignored build output, and a fresh clone has not built them yet.
    """
    out = {}
    for name in _REPORTS:
        path = ROOT / "reports" / name
        if not path.exists():
            pytest.skip(f"{name} not built - run `mothman dashboard build-data`")
        doc = json.loads(path.read_text())
        for ds in (doc["datasets"] if "datasets" in doc else [doc]):
            out[ds["id"]] = ds
    return out


class TestEveryCommittedArrivalKeepsItsVerdict:
    """The pin proper. 150 real arrivals across 7 datasets.

    IT WAS EXTENDED TO 162 ON 2026-09-27 AND THAT WAS WRONG, corrected
    2026-09-28 - and the correction is worth more than the pin, because
    the mistake was invisible from here and obvious from CI.

    What happened: `_built_datasets()` reads `reports/*.json`, gitignored
    build output, and rebuilding those from the working tree's own
    `data/deliveries/` showed 20 Child Protection runs per dataset where
    the pin held 18. That read as the pin having silently stopped covering
    things, so twelve arrivals were added to the golden - cp_run_019 and
    cp_run_020 across six datasets.

    They were not arrivals. They were `handfiled-*` deliveries that one
    CLI test had been filing into the real delivery tree on every run of
    the suite (see tests/conftest.py's `_no_test_files_a_real_delivery`,
    which now refuses that). A clean checkout has 18, so CI failed three
    ways on a corpus that had never existed anywhere but this container.

    THE LESSON IS ABOUT WHAT A GOLDEN MAY BE CAPTURED FROM. This one is
    captured from `reports/*.json`, which is built from `data/`, which is
    gitignored and accumulates - so the pin is only ever as trustworthy as
    that directory was on the day. A disagreement between the pin and the
    corpus is therefore TWO hypotheses, not one: the pin went stale, or the
    corpus did. It was the corpus, and the reflex was to believe the
    corpus.

    So: before extending this golden, count the deliveries. `mothman
    debug capture-arrival-golden` is still the recorded procedure, and
    `ls data/deliveries | wc -l` is the question to ask first.

    RE-CAPTURED 2026-10-02 FOR REQ-PIPE-080, which moved both axes this
    pin exists to hold still - so it failed, which is the pin working
    rather than a regression. Recorded here because "the golden
    changed" is exactly the event its own lesson says to be suspicious
    of, and the procedure was followed before re-capturing: 60
    deliveries, 18 Child Protection runs, zero `handfiled-*`, matching
    a clean checkout.

    WHAT MOVED, and why each is intended:
      - 133 verdicts. Most are the vocabulary: the retired
        `cadence.classify_arrival()` said `onTime` where
        `arrival_classification` says `on_time`. Twenty-five are real -
        Child Protection supplies that read on time and are genuinely
        late, one of them by eleven days.
      - 34 arrival instants, where our RECEIPT instant differs from the
        `earliest_extract` this used to carry (criterion 4). The other
        116 were already equal, which is why the diff is smaller than
        the change sounds.
    """

    def test_the_golden_covers_every_dataset_and_run_that_exists_now(self):
        """A pin that silently stops covering things is worse than none -
        it goes green by measuring less. Guards both directions."""
        golden = json.loads(GOLDEN.read_text())
        built = _built_datasets()
        assert set(golden) == set(built), "the golden and the built reports disagree about which datasets exist"
        for ds_id, runs in golden.items():
            on_page = {a["run_id"] for a in built[ds_id].get("arrivalHistory") or []}
            assert set(runs) == on_page, f"{ds_id}: the golden and the built history disagree about run ids"

    def test_no_arrival_changed_its_verdict(self):
        golden = json.loads(GOLDEN.read_text())
        built = _built_datasets()
        moved = []
        for ds_id, runs in golden.items():
            actual = {a["run_id"]: a for a in built[ds_id].get("arrivalHistory") or []}
            for run_id, expected in runs.items():
                got = actual[run_id]
                if got.get("arrivalStatus") != expected["arrivalStatus"]:
                    moved.append(f"{ds_id}/{run_id}: {expected['arrivalStatus']} -> {got.get('arrivalStatus')}")
        assert moved == [], "arrival verdicts moved:\n  " + "\n  ".join(moved)

    def test_no_arrival_instant_changed(self):
        """Separate from the verdict deliberately. A verdict can stay
        put while the instant behind it shifts by eight hours, and that
        is precisely the bug this requirement exists to prevent.

        Compared as INSTANTS rather than as strings, because REQ-PIPE-048
        deliberately changes the REPRESENTATION: the golden was captured
        when an arrival was stored as "2026-09-01 10:00:00" and read as
        UTC by whoever got to it, and it is now stored as
        "2026-09-01T10:00:00+00:00" and says so. Those are the same
        moment, and a string comparison would report the fix as the
        regression. The golden's own naked values are read here under
        the rule that was in force when they were written - which is the
        one place in this repo that rule still applies, and only because
        it is being used to prove it was preserved."""
        golden = json.loads(GOLDEN.read_text())
        built = _built_datasets()
        moved = []
        for ds_id, runs in golden.items():
            # arrivalByRun, not arrivalHistory - a history row carries
            # no instant at all, and reading it from there is what made
            # this test compare None to None 150 times over.
            actual = built[ds_id].get("arrivalByRun") or {}
            for run_id, expected in runs.items():
                got = (actual.get(run_id) or {}).get("arrivedAt")
                assert expected["arrivedAt"] is not None, \
                    f"{ds_id}/{run_id}: the golden carries no instant - re-capture it, this test cannot fail as is"
                if _instant_as_written_before_048(expected["arrivedAt"]) != _instant_as_written_before_048(got):
                    moved.append(f"{ds_id}/{run_id}: {expected['arrivedAt']} -> {got}")
        assert moved == [], "arrival instants moved:\n  " + "\n  ".join(moved)

    def test_the_distribution_is_the_one_that_was_measured(self):
        """A blunt backstop for the two tests above, readable without a
        diff: 131 on time, 16 early, 3 late over 150 arrivals.

        THIS NUMBER WENT TO 28 EARLY AND BACK, and the round trip is the
        useful part. It moved to 28 on 2026-09-27 when twelve arrivals were
        added to the golden - all twelve early, which is the only reason a
        single figure moved and looked plausible. Those twelve were the
        `handfiled-*` deliveries one CLI test had been leaving in the real
        delivery tree, not arrivals at all, so the recapture on 2026-09-28
        restored exactly 131 / 16 / 3 - the figure measured on 2026-09-23,
        twice, against a corpus nothing had polluted.

        A distribution coming back identical is therefore evidence the
        corpus is the same corpus, which is precisely what was wanted and
        precisely what 28 could not tell anybody.

        AND THEN IT MOVED AGAIN, TO 129 / 18 / 3, LEGITIMATELY - the same
        day, once REQ-GEN-044 injected its first two scenarios into Birth
        Registrations. That one IS a corpus change: three slots on one
        day instead of a random chain, and two days carrying no supply at
        all. Checked the way this file's own header says to check rather
        than accepted because a number moved - SIX golden entries differ,
        all Birth Registrations, all inside the 2026-09-09 to 2026-09-15
        window the two scenarios occupy; the other 36 Birth
        Registrations arrivals and all 108 Child Protection ones are
        byte-identical.

        Most of that six is the LABEL shift REQ-GEN-043's own recapture
        documented rather than a verdict moving: run ids are positional
        over receipt order, so two suppressed days renumber the tail and
        run_022 through run_027 each carry the instant that used to
        belong to a neighbour.

        AND IT MOVED AGAIN FOR REQ-PIPE-080, to 106 / 14 / 30, which is
        the largest shift this figure has taken and the one with a real
        cause rather than a relabelling. Two things moved it:

          - 25 CHILD PROTECTION SUPPLIES WENT ON-TIME TO LATE, and they
            are the requirement's whole point. Punctuality used to be
            measured from `earliest_extract` - a timestamp inside the
            SUPPLIER'S OWN FILE - so a supplier effectively decided
            whether they were late. It is now measured from when the
            file reached us. Verified by hand rather than inferred:
            cp-clients in cp_run_008 was received 2024-08-13 against a
            2024-Q3 slot due 2024-08-01 with grace to 17:00, so it is
            late by eleven days, and the old reading of "on time" was
            simply wrong.
          - 4 BIRTH REGISTRATIONS SUPPLIES moved between early, on time
            and late for the same reason, in both directions.

        The key `onTime` also becomes `on_time`: the retired
        `cadence.classify_arrival()` and `arrival_classification` spell
        it differently, and the page has rendered both for some time.
        """
        golden = json.loads(GOLDEN.read_text())
        counts: dict[str, int] = {}
        for runs in golden.values():
            for a in runs.values():
                counts[a["arrivalStatus"]] = counts.get(a["arrivalStatus"], 0) + 1
        assert counts == {"on_time": 106, "early": 14, "late": 30}
        assert sum(counts.values()) == 150


class TestTheClassificationBoundaries:
    """The RULE, stated as boundary cases rather than inferred from the
    150 real arrivals above - those happen to cluster, and none of them
    sits on a boundary. Written against aware instants only, since that
    is the half 048 must not move."""

    CADENCE = {"type": "daily", "weekday": None, "anchor_months": None,
               "day_of_month": None, "expected_time": "14:00", "latency_minutes": 60}

    def _expected(self, run_date):
        return cadence.expected_moment(self.CADENCE, cadence.cycle_start(self.CADENCE, run_date))

    def _verdict(self, run_date, arrived):
        """Early / on time / late against this cadence's own expected
        moment and grace.

        SPELLED OUT HERE rather than calling a shared classifier, since
        REQ-PIPE-080 retired `cadence.classify_arrival()`. What these
        tests are about is ASSET TIME - that the expected moment is a
        wall clock in the asset's own zone, and that the grace window is
        closed at both ends - not about which module owns the comparison.
        The arithmetic is three lines and keeping it local is what lets
        them go on asserting the thing they are named for.
        """
        grace = timedelta(minutes=self.CADENCE["latency_minutes"])
        expected = self._expected(run_date)
        arrived = asset_time.parse_instant(arrived, "test arrival")
        if arrived < expected:
            return "early"
        return "onTime" if arrived <= expected + grace else "late"

    @pytest.mark.parametrize("delta,verdict", [
        (timedelta(seconds=-1), "early"),
        (timedelta(0), "onTime"),
        (timedelta(minutes=60), "onTime"),
        (timedelta(minutes=60, seconds=1), "late"),
    ])
    def test_the_grace_window_is_closed_at_both_ends(self, delta, verdict):
        run_date = date(2026, 9, 1)
        arrived = self._expected(run_date) + delta
        assert self._verdict(run_date, arrived) == verdict

    def test_the_expected_moment_is_the_wall_clock_time_in_the_assets_own_zone(self):
        """14:00 in Perth is 06:00 UTC the same day. Pinned as a real
        instant rather than as an offset arithmetic step, so the
        refactor from a hardcoded UTC+8 to a named zone has something
        to be judged against."""
        assert self._expected(date(2026, 9, 1)) == datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)

    def test_an_arrival_the_day_before_is_early_not_late(self):
        """The wrap case the generator's own comment calls out: an AWST
        expected_time before 08:00 lands on the PREVIOUS UTC day, which
        made "on time" structurally unreachable once before."""
        run_date = date(2026, 9, 1)
        arrived = self._expected(run_date) - timedelta(hours=12)
        assert self._verdict(run_date, arrived) == "early"
