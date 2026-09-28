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

from qa_tools.common import promotion


def r(status, *, dataset_id=None, check_id="c1", scope="dataset"):
    return {"status": status, "dataset_id": dataset_id, "check_id": check_id,
            "scope": scope}


class TestItFoldsTheDatasetsOwnChecks:
    def test_all_green_is_green(self):
        assert promotion.status_of("cp-carers", [r("green", dataset_id="cp-carers"),
                                                 r("green", dataset_id="cp-carers")],
                                   reads={}) == "green"

    def test_one_red_makes_it_red(self):
        assert promotion.status_of("cp-carers", [r("green", dataset_id="cp-carers"),
                                                 r("red", dataset_id="cp-carers")],
                                   reads={}) == "red"

    def test_an_amber_among_greens_is_amber(self):
        assert promotion.status_of("cp-carers", [r("green", dataset_id="cp-carers"),
                                                 r("amber", dataset_id="cp-carers")],
                                   reads={}) == "amber"


class TestItFoldsCrossTableChecksItParticipatesIn:
    """The criterion's own words: 'whether or not it is the dataset they
    are filed under'."""

    def test_a_red_cross_table_check_filed_under_ANOTHER_dataset_counts(self):
        results = [r("green", dataset_id="cp-carers"),
                   # Filed under placements, but it READS carers.
                   r("red", dataset_id="cp-placements", check_id="xt1")]
        reads = {"xt1": ["cp_placements", "cp_carers"]}
        assert promotion.status_of("cp-carers", results, reads=reads) == "red", \
            "gating on its own results alone is the false-green direction"

    def test_a_cross_table_check_that_does_NOT_read_it_is_ignored(self):
        results = [r("green", dataset_id="cp-carers"),
                   r("red", dataset_id="cp-placements", check_id="xt1")]
        reads = {"xt1": ["cp_placements", "cp_clients"]}
        assert promotion.status_of("cp-carers", results, reads=reads) == "green", \
            "another pair's failure is not this dataset's problem"


class TestAbsenceIsNotGreen:
    """A dataset with no contributing check at all has no verdict to
    gate on, and saying 'green' would be the check-free table problem
    criterion 12 exists for, arriving by a different road."""

    def test_no_results_is_not_green(self):
        assert promotion.status_of("cp-carers", [], reads={}) is None
