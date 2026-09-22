"""Smoke test for pipeline/build_dashboard_data.py's reshaping logic,
against a small fixture rather than a real (slow) qa_tools/bdm/
orchestrate_bdm.py run - this is meant to catch the kind of silent
shape/crash regression a full pipeline run wouldn't surface quickly, not
to duplicate qa_tools' own integration coverage.

No real DuckDB warehouse here since Phase 3 (plans/publishing-and-
history.md) - value-counts/arrival/check-aggregate data comes from
results_bdm.json's own "dataset_stats" key now (qa_tools/bdm/
dataset_stats.py's precomputed output), not a live query."""
from __future__ import annotations

import json

from qa_tools.common.check_lifecycle import CheckMetadata
from pipeline import build_dashboard_data as bdd

FIXTURE_RUNS = [
    {
        "run_id": "run_01_2026-09-01", "run_index": 1, "delivery_id": "delivery_01",
        "run_date": "2026-09-01", "n_rows_generated": 3, "dirty_severity": None,
    },
    {
        "run_id": "run_02_2026-09-02", "run_index": 2, "delivery_id": "delivery_02",
        "run_date": "2026-09-02", "n_rows_generated": 4, "dirty_severity": "amber",
    },
]

FIXTURE_DATASET_STATS = {
    "run_01_2026-09-01": {
        "manifest_entry": FIXTURE_RUNS[0],
        "value_counts": {"sex": [["M", 1], ["F", 2], ["X", 0]]},
        "arrival": {"max_lag_hours": 5.0, "earliest_extract": "2026-09-01 10:00:00"},
        "check_aggregates": {"sex": {"type": "categorical", "suppressed": False, "total_invalid": 0, "values": []}},
    },
    "run_02_2026-09-02": {
        "manifest_entry": FIXTURE_RUNS[1],
        "value_counts": {"sex": [["M", 2], ["F", 1], ["X", 1]]},
        "arrival": {"max_lag_hours": 6.0, "earliest_extract": "2026-09-02 10:00:00"},
        "check_aggregates": {"sex": {"type": "categorical", "suppressed": False, "total_invalid": 1,
                                      "values": [{"value": "X", "count": 1}]}},
    },
}


def _check(run_id, column_name, value, status="pass", **overrides):
    rec = {
        "column_name": column_name, "check_name": "dbt:accepted_values",
        "dimension": "validity", "label": "Invalid values",
        "run_id": run_id, "metric_value": value, "unit": "count",
        "warn_threshold": 0.0, "fail_threshold": 5.0, "status": status,
        "row_count_total": 3, "row_count_invalid": 0,
        "engine": "dbt-core 1.12 + dbt-duckdb (real)",
        "check_id": f"data-asset-1.registry-services.civil-registration.birth-registrations.{column_name}.accepted_values_dbt",
    }
    rec.update(overrides)
    return rec


FIXTURE_RESULTS = [
    _check("run_01_2026-09-01", "sex", 0),
    _check("run_02_2026-09-02", "sex", 1, status="warn", row_count_invalid=1),
]


def _write_results(tmp_path):
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS, "results": FIXTURE_RESULTS, "dataset_stats": FIXTURE_DATASET_STATS,
    }))
    return results_path


def _no_retired_checks(monkeypatch):
    """Phase 5b's retirement lookup reads real, committed check-definition
    files (collect_checks(None)) - stubbed out here so this fixture-driven
    smoke test stays isolated from the real repo's schema.yml/Soda/contract/
    Evidently files, same as test_embed_dashboard_data.py's own pattern of
    monkeypatching an external collection function rather than depending on
    real repo state."""
    monkeypatch.setattr(bdd, "collect_checks", lambda ref: [])


def test_build_produces_one_entry_per_known_column(tmp_path, monkeypatch):
    _no_retired_checks(monkeypatch)
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()

    # Every REAL column, in order. The two pseudo-columns are in
    # ALL_COLUMNS too but only appear when the dataset actually has a
    # table-level check to put in them - this fixture has none, and an
    # empty "(supply-level checks)" tile would be noise.
    real_columns = [c for c in bdd.ALL_COLUMNS if c not in bdd._PSEUDO_COLUMNS]
    assert [col["name"] for col in data["columns"]] == real_columns
    assert data["rowCount"] == 4  # latest run (run_02)'s n_rows_generated
    assert data["prevRowCount"] == 3


def test_a_column_with_a_real_check_carries_it_through(tmp_path, monkeypatch):
    _no_retired_checks(monkeypatch)
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()
    sex_col = next(c for c in data["columns"] if c["name"] == "sex")
    assert len(sex_col["checks"]) == 1
    assert sex_col["checks"][0]["current"] == 1  # run_02's metric_value
    assert sex_col["checks"][0]["previous"] == 0  # run_01's metric_value
    assert len(sex_col["checks"][0]["history"]) == 2
    # aggregate_values attached from dataset_stats, not a live query
    assert sex_col["checks"][0]["history"][-1]["aggregate_values"]["total_invalid"] == 1
    assert sex_col["stats"]["current"]["valueCounts"] == [["M", 2], ["F", 1], ["X", 1]]


def test_a_column_with_no_check_gets_an_honest_placeholder(tmp_path, monkeypatch):
    _no_retired_checks(monkeypatch)
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()
    # No check in FIXTURE_RESULTS covers "date_registered" - should get the
    # honest placeholder, not a crash or a silently-empty checks list.
    uncovered = next(c for c in data["columns"] if c["name"] == "date_registered")
    assert uncovered["checks"][0]["name"] == "No automated quality rule defined"


def test_stats_by_run_carries_every_run_not_just_latest_and_previous(tmp_path, monkeypatch):
    """Phase 4 prerequisite (plans/publishing-and-history.md Thread C):
    stats["current"]/["previous"] stay exactly as before, but stats
    ["byRun"] now carries every run, keyed by run_id - the actual data
    Thread C's as-of picker will need."""
    _no_retired_checks(monkeypatch)
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()
    sex_col = next(c for c in data["columns"] if c["name"] == "sex")
    by_run = sex_col["stats"]["byRun"]

    assert set(by_run) == {"run_01_2026-09-01", "run_02_2026-09-02"}
    # run_01 is clean (metric_value 0) - matches "previous" above
    assert by_run["run_01_2026-09-01"] == {
        "total": 3, "invalid": 0, "valid": 3, "valueCounts": [["M", 1], ["F", 2], ["X", 0]],
    }
    # run_02 matches "current" above (metric_value 1)
    assert by_run["run_02_2026-09-02"] == {
        "total": 4, "invalid": 1, "valid": 3, "valueCounts": [["M", 2], ["F", 1], ["X", 1]],
    }
    # a column with no real check (the honest-placeholder path) still
    # gets a byRun entry per run, all zero - never crashes or gets skipped
    uncovered = next(c for c in data["columns"] if c["name"] == "date_registered")
    assert set(uncovered["stats"]["byRun"]) == {"run_01_2026-09-01", "run_02_2026-09-02"}


def test_arrival_status_is_genuinely_computed_from_real_cadence(tmp_path, monkeypatch):
    """arrivalStatus (Phase 5j, replacing the old hardcoded-then-max-lag-
    based onTime boolean) is a real classify_arrival() result against
    this dataset's own real cadence (contract/bdm-birth-registrations-
    contract.yaml's slaProperties: - daily, 14:00 AWST = 06:00 UTC the
    same day, 60 min latency grace - corrected from an original 06:00
    AWST placeholder that made "on time" structurally unreachable
    against the real extract-timestamp-ordering check, plans/qa-
    pipeline.md item 67) - not a hardcoded value. Mutating
    earliest_extract to fall inside vs. well outside that grace window
    must flip arrivalStatus accordingly."""
    _no_retired_checks(monkeypatch)
    mixed_stats = json.loads(json.dumps(FIXTURE_DATASET_STATS))
    # run_01: inside the grace window (expected 2026-09-01T06:00:00Z, 60
    # min grace) -> onTime.
    mixed_stats["run_01_2026-09-01"]["arrival"]["earliest_extract"] = "2026-09-01 06:30:00"
    # run_02: hours after the grace window -> late.
    mixed_stats["run_02_2026-09-02"]["arrival"]["earliest_extract"] = "2026-09-02 10:00:00"
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS, "results": FIXTURE_RESULTS, "dataset_stats": mixed_stats,
    }))
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))

    data = bdd.build()

    assert data["arrivalByRun"]["run_01_2026-09-01"]["arrivalStatus"] == "onTime"
    assert data["arrivalByRun"]["run_01_2026-09-01"]["maxLagHours"] == 5.0
    assert data["arrivalByRun"]["run_02_2026-09-02"]["arrivalStatus"] == "late"
    history_by_run = {h["run_id"]: h["arrivalStatus"] for h in data["arrivalHistory"]}
    assert history_by_run == {"run_01_2026-09-01": "onTime", "run_02_2026-09-02": "late"}


def test_a_retired_checks_metadata_is_carried_through(tmp_path, monkeypatch):
    """Phase 5b (plans/publishing-and-history.md Thread D): a check
    result whose check_id has a retired_as_of in check_lifecycle's
    collection gets retired_as_of/retired_reason attached in the
    dashboard-data output - the frontend's retired-checks toggle reads
    these two fields directly."""
    sex_check_id = "data-asset-1.registry-services.civil-registration.birth-registrations.sex.accepted_values_dbt"
    monkeypatch.setattr(bdd, "collect_checks", lambda ref: [
        CheckMetadata(check_id=sex_check_id, category="conformity", tool="dbt", config_hash="abc123", source_file="fake.yml",
                      retired_as_of="2026-09-17", retired_reason="Superseded by a stricter rule."),
    ])
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()

    sex_col = next(c for c in data["columns"] if c["name"] == "sex")
    assert sex_col["checks"][0]["retired_as_of"] == "2026-09-17"
    assert sex_col["checks"][0]["retired_reason"] == "Superseded by a stricter rule."
    # an unrelated column's check, with no matching check_id in the
    # (stubbed) retirement collection, stays un-retired
    uncovered = next(c for c in data["columns"] if c["name"] == "date_registered")
    assert uncovered["checks"][0].get("retired_as_of") is None


def test_a_checks_description_and_changelog_are_carried_through(tmp_path, monkeypatch):
    """Phase 5c (plans/publishing-and-history.md Thread D): the
    check-detail panel's new "What this check does"/changelog sections
    read description/changelog straight off the check record - same
    lifecycle_by_id lookup Phase 5b's retired_as_of/reason already use."""
    sex_check_id = "data-asset-1.registry-services.civil-registration.birth-registrations.sex.accepted_values_dbt"
    changelog = [{"date": "2026-06-01T10:00:00Z", "description": "Tightened threshold",
                  "author": "Keith Moss", "breaking": False}]
    monkeypatch.setattr(bdd, "collect_checks", lambda ref: [
        CheckMetadata(check_id=sex_check_id, category="conformity", tool="dbt", config_hash="abc123", source_file="fake.yml",
                      description="Sex must be one of the closed value set.", changelog=changelog),
    ])
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()

    sex_col = next(c for c in data["columns"] if c["name"] == "sex")
    assert sex_col["checks"][0]["description"] == "Sex must be one of the closed value set."
    assert sex_col["checks"][0]["changelog"] == changelog
    # a check with no matching check_id gets an empty changelog, not a crash
    uncovered = next(c for c in data["columns"] if c["name"] == "date_registered")
    assert uncovered["checks"][0].get("description") is None


# --- plans/qa-pipeline.md item 74, Bug A (fixed 2026-09-19) ------------
#
# build_dashboard_data.py used to substitute 0 for a None warn/fail
# threshold when building each check's dashboard record. The dashboard
# then re-derived every status from those thresholds (checkStatus()/
# statusForValue(), both `value > fail` => red), so a check whose real
# rule CAN'T be expressed as a one-sided "value > threshold" bound got a
# fabricated red.
#
# The real, measured case (2026-09-19, against this repo's own committed
# history): the ODCS `rowCount` rule is `mustBeBetween: [500, 20000]`
# with `severity: warning` - a genuine TWO-SIDED range. Both thresholds
# come through as None (correctly - there is no single upper bound), the
# real tool evaluates it and says `pass`, and the 0-substitution turned
# that into `1939 > 0` => RED on 352/352 BDM runs and 18/18 CP runs
# (the BDM figure as the tree stood then; its history was cut to 30
# deliveries on 2026-09-23) -
# one per dataset, which is exactly what made all 7 datasets read red on
# every single run.
#
# The fix is NOT "pass None through and treat it as unbounded" - that
# would regress the ~63 violation-count checks (not_null/unique/
# relationships/matches_regex) whose null fail_threshold genuinely DOES
# mean "any violation is a failure", and which currently agree with
# their tool exactly. Instead the tool's own verdict is carried through
# and used as the source of truth, with threshold math as the fallback.
ROWCOUNT_CHECK_ID = (
    "data-asset-1.registry-services.civil-registration"
    ".birth-registrations.sex.rowCount_datacontract"
)


def _rowcount_results():
    """A real two-sided-range check: no expressible one-sided threshold,
    a large legitimate metric value, and a real `pass` from the tool."""
    return [
        _check("run_01_2026-09-01", "sex", 1939, status="pass",
               check_name="datacontract:rowCount", label="Row count",
               warn_threshold=None, fail_threshold=None,
               check_id=ROWCOUNT_CHECK_ID, engine="datacontract-cli 1.2.0"),
        _check("run_02_2026-09-02", "sex", 2119, status="pass",
               check_name="datacontract:rowCount", label="Row count",
               warn_threshold=None, fail_threshold=None,
               check_id=ROWCOUNT_CHECK_ID, engine="datacontract-cli 1.2.0"),
    ]


def _write_rowcount_results(tmp_path):
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS, "results": _rowcount_results(),
        "dataset_stats": FIXTURE_DATASET_STATS,
    }))
    return results_path


def test_a_checks_real_tool_verdict_is_carried_into_every_history_entry(tmp_path, monkeypatch):
    """Item 74 Bug A: the tool's own pass/warn/fail verdict is the
    authority on whether a run was green. It already exists on every real
    result record - it just used to be dropped when building history[],
    leaving the dashboard to re-derive it from thresholds."""
    _no_retired_checks(monkeypatch)
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_rowcount_results(tmp_path)))

    check = next(c for c in next(
        col for col in bdd.build()["columns"] if col["name"] == "sex")["checks"])

    assert [h["status"] for h in check["history"]] == ["green", "green"], (
        "each history entry should carry the real tool verdict, mapped to "
        "the dashboard's own green/amber/red vocabulary"
    )
    assert check["current_status"] == "green", (
        "the latest run's real verdict should be carried through too - this "
        "is what checkStatus() reads before falling back to threshold math"
    )


def test_a_two_sided_range_check_keeps_its_null_thresholds(tmp_path, monkeypatch):
    """The other half of Bug A: a threshold that genuinely doesn't exist
    must stay None rather than being substituted with 0, so nothing
    downstream can mistake 'no upper bound' for 'zero tolerance'."""
    _no_retired_checks(monkeypatch)
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_rowcount_results(tmp_path)))

    check = next(c for c in next(
        col for col in bdd.build()["columns"] if col["name"] == "sex")["checks"])

    assert check["warn"] is None and check["fail"] is None, (
        "a mustBeBetween rule has no single-sided warn/fail bound; "
        "substituting 0 is what fabricated the red"
    )


def test_a_violation_count_checks_zero_tolerance_is_not_regressed(tmp_path, monkeypatch):
    """The regression guard that makes the naive fix unsafe: a dbt
    not_null-style check reports a COUNT OF VIOLATING ROWS, and its real
    tool verdict is `fail`. Carrying the verdict through must keep that
    red - it must not become green just because a threshold was null."""
    _no_retired_checks(monkeypatch)
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS,
        "results": [
            _check("run_01_2026-09-01", "sex", 0, status="pass",
                   check_name="dbt:not_null", warn_threshold=None, fail_threshold=None),
            _check("run_02_2026-09-02", "sex", 14, status="fail",
                   check_name="dbt:not_null", warn_threshold=None, fail_threshold=None),
        ],
        "dataset_stats": FIXTURE_DATASET_STATS,
    }))
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))

    check = next(c for c in next(
        col for col in bdd.build()["columns"] if col["name"] == "sex")["checks"])

    assert [h["status"] for h in check["history"]] == ["green", "red"]
    assert check["current_status"] == "red"


# ---- REQ-QAC-024: the two new authored fields ------------------------

def _build_with_authored_check(tmp_path, monkeypatch, **authored):
    """Builds the real dashboard JSON with one check carrying whatever
    authored prose a test wants, and returns that check as the page
    would receive it."""
    check_id = ("data-asset-1.registry-services.civil-registration"
                ".birth-registrations.sex.accepted_values_dbt")
    meta = CheckMetadata(check_id=check_id, category="validity", tool="dbt",
                         config_hash="abc123", source_file="schema.yml",
                         description="Sex must be one of the values the contract allows.",
                         **authored)
    monkeypatch.setattr(bdd, "collect_checks", lambda ref: [meta])
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS,
        "results": [_check("run_02_2026-09-02", "sex", 0, status="pass",
                           check_id=check_id)],
        "dataset_stats": FIXTURE_DATASET_STATS,
    }))
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))
    col = next(c for c in bdd.build()["columns"] if c["name"] == "sex")
    return next(c for c in col["checks"] if c.get("check_id") == check_id)


def test_failure_indicates_reaches_the_page_alongside_description(tmp_path, monkeypatch):
    """`description` says WHAT a check verifies; `failure_indicates`
    says what a failure most likely means happened upstream. Both are
    written for whoever is reading the dashboard, so both have to
    actually arrive there - asserted on the built output rather than by
    reading the builder's source, since a field can be assigned and
    still be dropped by a later transform."""
    check = _build_with_authored_check(
        tmp_path, monkeypatch,
        failure_indicates="The upstream extract probably ran before the day closed.")

    assert check["description"] == "Sex must be one of the values the contract allows."
    assert check["failure_indicates"] == (
        "The upstream extract probably ran before the day closed.")


def test_technical_note_never_reaches_the_page(tmp_path, monkeypatch):
    """The one authored field that must NOT reach a viewer.

    REQ-QAC-024 splits the prose three ways and the third is
    deliberately for contributors - cross-references between checks, and
    why a check behaves as it does by construction. This data is
    published to a public site, so the field's absence is a requirement
    being met, not something someone forgot to wire up.

    Asserted against the whole built payload, not just this check's own
    dict: the way this would really break is someone copying the field
    through somewhere else for symmetry with `description`."""
    check = _build_with_authored_check(
        tmp_path, monkeypatch,
        technical_note="Paired with the Soda check on the same column.")

    assert "technical_note" not in check
    assert "Paired with the Soda check" not in json.dumps(bdd.build())


def test_a_check_with_no_authored_prose_still_builds(tmp_path, monkeypatch):
    """Both fields are optional. `technical_note` is sparse by design -
    on the order of 8 texts across 258 checks - and `failure_indicates`
    may be declared self-evident, so the common case is neither."""
    check = _build_with_authored_check(tmp_path, monkeypatch)
    assert check["failure_indicates"] is None


# ---------------------------------------------------------------------
# Two checks that differ only by check_id.
#
# Found 2026-09-20 on the real data, not invented: Birth Registrations'
# range_check_datacontract and freshness_datacontract both sit on
# date_of_birth and datacontract-cli reports BOTH as check_name
# "datacontract:custom_sql", because it does not distinguish one
# `type: sql` rule from another. The builder keyed its slots on
# (engine, check_name), so the two collapsed into one - and they
# genuinely disagree on 166 of the 352 committed runs (as the tree
# stood then - BDM's history was cut on 2026-09-23), so the surviving
# tile was showing the other check's numbers under its own name.
#
# check_id is the identity the rest of this system already guarantees
# unique (REQ-QAC-023's own grammar and tail-uniqueness gates), so it is
# what the slot key has to be.
# ---------------------------------------------------------------------

def _custom_sql(run_id, value, status, check_id):
    return _check(run_id, "date_of_birth", value, status=status,
                  check_name="datacontract:custom_sql",
                  engine="datacontract-cli 1.2.0",
                  check_id=check_id)


RANGE_ID = ("data-asset-1.registry-services.civil-registration."
            "birth-registrations.date_of_birth.range_check_datacontract")
FRESH_ID = ("data-asset-1.registry-services.civil-registration."
            "birth-registrations.date_of_birth.freshness_datacontract")


def test_two_checks_sharing_a_display_name_stay_separate(tmp_path, monkeypatch):
    _no_retired_checks(monkeypatch)
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS,
        "results": [
            _custom_sql("run_01_2026-09-01", 5, "fail", RANGE_ID),
            _custom_sql("run_01_2026-09-01", 0, "pass", FRESH_ID),
            _custom_sql("run_02_2026-09-02", 0, "pass", RANGE_ID),
            _custom_sql("run_02_2026-09-02", 1, "fail", FRESH_ID),
        ],
        "dataset_stats": FIXTURE_DATASET_STATS,
    }))
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))

    dob = next(c for c in bdd.build()["columns"] if c["name"] == "date_of_birth")
    by_id = {c["check_id"]: c for c in dob["checks"]}

    assert RANGE_ID in by_id and FRESH_ID in by_id, "one check swallowed the other"

    # ...and each keeps its OWN values, rather than whichever result was
    # written to the shared slot last.
    def value(check, run_id):
        return next(h["value"] for h in check["history"] if h["run_id"] == run_id)

    assert value(by_id[RANGE_ID], "run_01_2026-09-01") == 5
    assert value(by_id[FRESH_ID], "run_01_2026-09-01") == 0
    assert value(by_id[RANGE_ID], "run_02_2026-09-02") == 0
    assert value(by_id[FRESH_ID], "run_02_2026-09-02") == 1


def test_a_table_level_check_lands_in_a_pseudo_column(tmp_path, monkeypatch):
    """REQ-DASH-032: "(table)" results used to be dropped
    on the floor - a bare `continue` - so 13 real checks across both
    datasets rendered nowhere at all, prose and all.

    Two pseudo-columns rather than one (Keith, 2026-09-20): a row-count
    check answers "is this supply the right size", which is not the same
    question as a cross-table rule's "do these tables agree".
    """
    _no_retired_checks(monkeypatch)
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS,
        "results": [
            _check("run_01_2026-09-01", "(table)", 3, check_name="datacontract:row_count",
                   engine="datacontract-cli 1.2.0", check_id="a.b.c.d.rowCount_datacontract"),
            _check("run_02_2026-09-02", "(table)", 4, check_name="datacontract:row_count",
                   engine="datacontract-cli 1.2.0", check_id="a.b.c.d.rowCount_datacontract"),
            _check("run_01_2026-09-01", "(table)", 0, check_name="dbt:escalation_completeness",
                   check_id="a.b.c.d.escalation_completeness_dbt"),
            _check("run_02_2026-09-02", "(table)", 0, check_name="dbt:escalation_completeness",
                   check_id="a.b.c.d.escalation_completeness_dbt"),
        ],
        "dataset_stats": FIXTURE_DATASET_STATS,
    }))
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))

    by_name = {c["name"]: c for c in bdd.build()["columns"]}

    supply = by_name[bdd.SUPPLY_LEVEL_PSEUDO_COLUMN]
    table = by_name[bdd.TABLE_LEVEL_PSEUDO_COLUMN]
    assert [c["check_id"] for c in supply["checks"]] == ["a.b.c.d.rowCount_datacontract"]
    assert [c["check_id"] for c in table["checks"]] == ["a.b.c.d.escalation_completeness_dbt"]
