"""The configuration-time half of the road-testing sweep's #7 (Keith,
2026-10-06): a SodaCL check this project's Soda Core cannot run is refused
in CI, before any run, rather than discovered as a red run later."""
from __future__ import annotations

from qa_tools.common import validate_soda


def _write(tmp_path, body):
    path = tmp_path / "x-soda-checks.yml"
    path.write_text(body)
    return path


def test_the_real_check_files_pass():
    """It must find every collection's Soda file first, or [] == [] proves
    nothing (post-build-review #273: since REQ-QAC-241 moved them under
    contract/<agency-id>/, a top-level glob found none)."""
    from qa_tools import collections

    files = validate_soda.check_files()
    assert files and sorted(files) == sorted(collections.check_files("soda"))
    assert validate_soda.problems() == []


def test_a_check_that_needs_soda_cloud_is_refused(tmp_path):
    path = _write(tmp_path, "checks for t:\n  - change for row_count:\n      warn: when > 10\n"
                            "      attributes:\n        check_id: a.b.c\n")
    found = validate_soda.problems([path])
    assert len(found) == 1 and "Soda Cloud" in found[0] and "change for row_count" in found[0]


def test_a_check_soda_cannot_parse_is_refused(tmp_path):
    path = _write(tmp_path, "checks for t:\n  - row_cnt >>> 0\n")
    found = validate_soda.problems([path])
    assert found and "row_cnt" in found[0]


def test_it_is_a_mothman_check_gate():
    from cli import check

    assert any(name == "soda" for name, *_ in check._GATES)


def test_the_sightings_two_green_misconfigurations_are_refused(tmp_path):
    """The two cases road-testing #7 saw PASS at 0% invalid while checking
    nothing: an unsupported `valid sql`, and `valid min` given a date."""
    sql = _write(tmp_path, "checks for t:\n  - invalid_percent(c):\n      valid sql: \"c > 0\"\n"
                           "      fail: when > 1%\n")
    assert validate_soda.problems([sql])
    date = tmp_path / "y-soda-checks.yml"
    date.write_text("checks for t:\n  - invalid_percent(date_of_birth):\n"
                    "      valid min: 2020-01-01\n      fail: when > 1%\n")
    assert validate_soda.problems([date])


# ---- REQ-PIPE-341 criterion 5: a failed-rows query selects its table's key --

def _failed_rows(tmp_path, query, extra=""):
    q = "\n".join("        " + line for line in query.splitlines())
    tmp_path = tmp_path / f"q{len(list(tmp_path.iterdir()))}"
    tmp_path.mkdir()
    return _write(tmp_path, "checks for linkage_keys:\n  - failed rows:\n      name: Ref\n"
                            f"      fail query: |\n{q}\n      attributes:\n"
                            f"        check_id: a.b.c\n{extra}")


KEYS = {"linkage_keys": ["dataset", "id_1", "id_2"]}


def test_a_failed_rows_query_missing_key_columns_is_refused_naming_them(tmp_path):
    path = _failed_rows(tmp_path, "SELECT l.dataset, l.id_1 FROM linkage_keys l")
    found = validate_soda.problems([path], sample_keys=KEYS)
    assert len(found) == 1 and "Ref" in found[0] and "missing id_2 (" in found[0], found


def test_a_query_selecting_every_key_column_passes_aliases_and_star_included(tmp_path):
    ok = [_failed_rows(tmp_path, "SELECT l.dataset, l.id_1, l.id_2 FROM linkage_keys l"),
          _failed_rows(tmp_path, "SELECT d AS dataset, id_1, id_2, x FROM linkage_keys"),
          _failed_rows(tmp_path, "SELECT * FROM linkage_keys WHERE id_1 IS NULL")]
    for path in ok:
        assert validate_soda.problems([path], sample_keys=KEYS) == [], path.read_text()


def test_a_fail_condition_selects_the_whole_row_and_passes(tmp_path):
    path = _write(tmp_path, "checks for linkage_keys:\n  - failed rows:\n      name: C\n"
                            "      fail condition: id_1 IS NULL\n      attributes:\n"
                            "        check_id: a.b.c\n")
    assert validate_soda.problems([path], sample_keys=KEYS) == []


def test_a_check_declaring_it_names_no_row_is_not_held_to_the_key(tmp_path):
    path = _failed_rows(tmp_path, "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM linkage_keys)",
                        "        names_no_row: true\n")
    assert validate_soda.problems([path], sample_keys=KEYS) == []


def test_a_failed_rows_check_on_a_table_with_no_declared_key_warns(tmp_path):
    """Decisions 2026-11-01: warned, never silently skipped."""
    path = _failed_rows(tmp_path, "SELECT dataset FROM linkage_keys")
    assert validate_soda.problems([path], sample_keys={}) == []
    warned = validate_soda.warnings([path], sample_keys={})
    assert len(warned) == 1 and "linkage_keys" in warned[0] and "Ref" in warned[0]


def test_the_real_files_select_every_key_and_warn_of_nothing():
    """Linkage Keys' referential, expected-identifiers and no-surplus queries
    selected too few columns for the composite key (criterion 5)."""
    assert validate_soda.problems() == []
    assert validate_soda.warnings() == []




def test_two_collections_sharing_a_table_name_are_each_held_to_their_own_key(tmp_path):
    """Post-build-review: keys merged by bare table name across adapters, so
    one collection's key judged another's file."""
    a = _failed_rows(tmp_path, "SELECT x FROM linkage_keys")
    b = _failed_rows(tmp_path, "SELECT x FROM linkage_keys")
    keys = {("coll-a", "linkage_keys"): ["x"], ("coll-b", "linkage_keys"): ["y"]}
    found = validate_soda.problems([a, b], sample_keys=keys,
                                   collection_of={str(a): "coll-a", str(b): "coll-b"})
    assert len(found) == 1 and "missing y (" in found[0], found


def test_the_registry_keys_are_by_collection_and_table():
    from qa_tools import collections

    keys = validate_soda.declared_sample_keys()
    assert keys[("linkage-products", "linkage_keys")] == collections.adapter(
        "linkage-products").sample_key["linkage_keys"]
    assert all(isinstance(k, tuple) and len(k) == 2 for k in keys)
