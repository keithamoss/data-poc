"""REQ-PIPE-075 criterion 2 - the gate reads EVERY check that contributes.

The criterion names three sources and forbids gating on a subset: a
dataset's own table-level and column-level checks, the CROSS-TABLE checks
it participates in whether or not it is the dataset they are filed under,
and any other scope that folds into its status.

THE MIDDLE ONE IS THE WHOLE POINT, and it is the one a naive
implementation misses. A referential check between placements and carers
is filed under whichever dataset it happened to be declared on. Gating
cp-carers on its own results alone would promote a supply that a
cross-table check had just gone red over - the false-green direction.

The mapping from a check to the tables it reads already exists and is
what the dashboard uses: tables_read.declared_by_check_id(). Reusing it
rather than inventing a second one is deliberate - two implementations of
"which checks touch this dataset" would drift, and the drift would show
as a supply promoting itself past a red check.
"""
from __future__ import annotations

import pytest

from qa_tools.common import promotion


def r(status, *, dataset_id=None, check_id="c1", scope="dataset"):
    """One recorded result, in the vocabulary qa.check_result holds.

    A REAL RESULT CARRIES ITS TOOL'S OWN VERDICT - pass, warn, fail,
    error - not the dashboard's green/amber/red. These tests used to be
    written in the second vocabulary, which is how status_of() shipped
    feeding raw verdicts into a rollup that orders only the first: every
    real result would have raised. The test was self-consistent and
    wrong about the world, so it proved nothing.
    """
    return {"status": status, "dataset_id": dataset_id, "check_id": check_id,
            "scope": scope}


class TestItFoldsTheDatasetsOwnChecks:
    def test_all_green_is_green(self):
        assert promotion.status_of("cp-carers", [r("pass", dataset_id="cp-carers"),
                                                 r("pass", dataset_id="cp-carers")],
                                   reads={}) == "green"

    def test_one_red_makes_it_red(self):
        assert promotion.status_of("cp-carers", [r("pass", dataset_id="cp-carers"),
                                                 r("fail", dataset_id="cp-carers")],
                                   reads={}) == "red"

    def test_an_amber_among_greens_is_amber(self):
        assert promotion.status_of("cp-carers", [r("pass", dataset_id="cp-carers"),
                                                 r("warn", dataset_id="cp-carers")],
                                   reads={}) == "amber"


class TestItFoldsCrossTableChecksItParticipatesIn:
    """The criterion's own words: 'whether or not it is the dataset they
    are filed under'."""

    def test_a_red_cross_table_check_filed_under_ANOTHER_dataset_counts(self):
        results = [r("pass", dataset_id="cp-carers"),
                   # Filed under placements, but it READS carers.
                   r("fail", dataset_id="cp-placements", check_id="xt1")]
        reads = {"xt1": ["cp_placements", "cp_carers"]}
        assert promotion.status_of("cp-carers", results, reads=reads) == "red", \
            "gating on its own results alone is the false-green direction"

    def test_a_cross_table_check_that_does_NOT_read_it_is_ignored(self):
        results = [r("pass", dataset_id="cp-carers"),
                   r("fail", dataset_id="cp-placements", check_id="xt1")]
        reads = {"xt1": ["cp_placements", "cp_clients"]}
        assert promotion.status_of("cp-carers", results, reads=reads) == "green", \
            "another pair's failure is not this dataset's problem"


class TestAbsenceIsNotGreen:
    """A dataset with no contributing check at all has no verdict to
    gate on, and saying 'green' would be the check-free table problem
    criterion 12 exists for, arriving by a different road."""

    def test_no_results_is_not_green(self):
        assert promotion.status_of("cp-carers", [], reads={}) is None


class TestAVerdictThisGateCannotReadStopsIt:
    """An unknown tool status is not evidence of health, so it can never
    be dropped - that would promote a supply on the strength of a result
    nobody could read.

    RAISED RATHER THAN MAPPED TO RED, because "it is red" sends an
    operator looking for a failing check when the real problem is that a
    verdict arrived in a vocabulary nothing here knows."""

    def test_it_raises_and_names_the_check_and_the_status(self):
        with pytest.raises(promotion.UnreadableVerdictError) as exc:
            promotion.status_of(
                "cp-carers",
                [r("pass", dataset_id="cp-carers"),
                 r("indeterminate", dataset_id="cp-carers", check_id="c2")],
                reads={})
        assert "c2" in str(exc.value) and "indeterminate" in str(exc.value)

    def test_a_result_belonging_to_another_dataset_is_not_our_problem(self):
        assert promotion.status_of(
            "cp-carers",
            [r("pass", dataset_id="cp-carers"),
             r("indeterminate", dataset_id="cp-placements", check_id="c2")],
            reads={}) == "green"


class TestACheckWithNoReferenceIsNotEvidenceOfHealth:
    """REQ-QAC-108 criterion 5 reaching the promotion gate.

    A drift check whose reference period does not exist records
    `nodata` - it measured nothing. Two things have to be true of that
    at once, and they pull in opposite directions, which is why they are
    tested together.
    """

    def test_it_never_outranks_a_real_verdict(self):
        """One unmeasurable drift check must not hold up a dataset whose
        real checks are green - it would make every dataset's first
        supply wait for a person, for ever, for no reason."""
        assert promotion.status_of(
            "cp-carers",
            [r("pass", dataset_id="cp-carers"),
             r("nodata", dataset_id="cp-carers", check_id="drift")],
            reads={}) == "green"

    def test_it_never_loses_a_red_either(self):
        assert promotion.status_of(
            "cp-carers",
            [r("fail", dataset_id="cp-carers"),
             r("nodata", dataset_id="cp-carers", check_id="drift")],
            reads={}) == "red"

    def test_a_dataset_whose_EVERY_check_is_quiet_does_not_read_green(self):
        """THE FALSE GREEN THIS LINE EXISTS FOR. worst_of() is a reduce
        seeded at green, so a dataset with nothing but quiet verdicts
        rolled up to green and promoted itself on the strength of
        nothing having been measured. Caught by writing the test rather
        than by anything failing, which is why it is written down."""
        got = promotion.status_of(
            "cp-carers", [r("nodata", dataset_id="cp-carers", check_id="drift")],
            reads={})
        assert got == "nodata"
        assert got not in promotion.PROMOTES_ITSELF, \
            "a supply nobody measured must not promote itself"
