"""Tests for qa_tools/common/file_arrival.py - the AWS event-driven MVP's
file-arrival pattern matching (plans/running-thoughts.md #5 Thread B /
docs/aws-event-driven-mvp-design.md). Pure logic, no AWS - fixture pattern
specs, not the real (not-yet-written) contract customProperties."""
from __future__ import annotations

import os
import zipfile

import pytest

from qa_tools.common.file_arrival import (
    ArrivalPatternError,
    extract_zip_members,
    match_arrival,
)

_BDM_PATTERN = {
    "type": "single_file",
    "keyPattern": "raw/bdm/birth_registrations_{run_id}.csv",
    "dataset_id": "birth-registrations",
}
_CP_TABLE_PATTERN = {
    "type": "nested_folder",
    "keyPattern": "raw/cp/{run_id}/cp_clients.csv",
    "dataset_id": "cp-clients",
    "extractTo": "cp_clients",
}
# A SECOND nested_folder PATTERN, and it is deliberately not a completion
# marker any more (REQ-PIPE-105 retired those). What the test below is
# actually about is pattern DISCRIMINATION - that two patterns matching
# under one prefix resolve to different tables - and a second real table
# exercises that without reintroducing a shape the design has dropped.
_CP_SECOND_TABLE_PATTERN = {
    "type": "nested_folder",
    "keyPattern": "raw/cp/{run_id}/cp_carers.csv",
    "dataset_id": "cp-carers",
    "extractTo": "cp_carers",
}
_ZIP_PATTERN = {
    "type": "zip_archive",
    "keyPattern": "raw/cp/{run_id}.zip",
    "dataset_id": "cp-collection",
    "extractTo": {"cp_clients.csv": "cp_clients", "cp_carers.csv": "cp_carers"},
}


def test_single_file_pattern_matches_and_extracts_named_group():
    match = match_arrival("raw/bdm/birth_registrations_run_042.csv", [_BDM_PATTERN])
    assert match is not None
    assert match.pattern_type == "single_file"
    assert match.dataset_id == "birth-registrations"
    assert match.groups == {"run_id": "run_042"}


def test_nested_folder_pattern_resolves_table_via_extract_to():
    match = match_arrival("raw/cp/cp_run_09/cp_clients.csv", [_CP_TABLE_PATTERN])
    assert match is not None
    assert match.pattern_type == "nested_folder"
    assert match.table == "cp_clients"
    assert match.groups == {"run_id": "cp_run_09"}


def test_two_patterns_under_one_prefix_resolve_to_different_tables():
    match = match_arrival("raw/cp/cp_run_09/cp_carers.csv",
                           [_CP_TABLE_PATTERN, _CP_SECOND_TABLE_PATTERN])
    assert match is not None
    assert match.table == "cp_carers", (
        "a key matching the second pattern must not be attributed to the first - "
        "under per-file arrivals this is how six tables in one folder stay six "
        "distinct supplies")


def test_unmatched_key_returns_none_not_an_error():
    assert match_arrival("raw/some-other-teams-file.csv", [_BDM_PATTERN, _CP_TABLE_PATTERN]) is None


def test_first_matching_pattern_wins_when_multiple_could_apply():
    generic = {"type": "single_file", "keyPattern": "raw/bdm/{anything}", "dataset_id": "generic"}
    match = match_arrival("raw/bdm/birth_registrations_run_042.csv", [_BDM_PATTERN, generic])
    assert match.dataset_id == "birth-registrations"


def test_malformed_pattern_missing_key_pattern_raises():
    with pytest.raises(ArrivalPatternError):
        match_arrival("raw/bdm/anything.csv", [{"type": "single_file", "dataset_id": "x"}])


def test_malformed_pattern_unknown_type_raises():
    with pytest.raises(ArrivalPatternError):
        match_arrival("raw/bdm/anything.csv", [{"type": "smoke_signal", "keyPattern": "x", "dataset_id": "x"}])


def test_zip_archive_pattern_matches_and_carries_extract_map():
    match = match_arrival("raw/cp/cp_run_09.zip", [_ZIP_PATTERN])
    assert match is not None
    assert match.pattern_type == "zip_archive"
    assert match.extract_map == {"cp_clients.csv": "cp_clients", "cp_carers.csv": "cp_carers"}


def test_extract_zip_members_extracts_named_members_to_dest_dir(tmp_path):
    zip_path = tmp_path / "cp_run_09.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("cp_clients.csv", "id,name\n1,Alice\n")
        zf.writestr("cp_carers.csv", "id,name\n1,Bob\n")
        zf.writestr("cp_investigations.csv", "id\n1\n")  # not in the extract map - should be ignored

    dest_dir = tmp_path / "extracted"
    extracted = extract_zip_members(str(zip_path), {"cp_clients.csv": "cp_clients", "cp_carers.csv": "cp_carers"},
                                     str(dest_dir))

    assert set(extracted) == {"cp_clients", "cp_carers"}
    assert os.path.isfile(extracted["cp_clients"])
    with open(extracted["cp_clients"]) as f:
        assert "Alice" in f.read()
