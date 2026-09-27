"""Tests for qa_tools/common/local_check.py - shared logic behind the
Thread A on-demand CLIs (plans/running-thoughts.md #5, 2026-09-19)."""
from __future__ import annotations
import os

from qa_tools.common.local_check import copy_into, run_id_from_path


def test_run_id_from_path_includes_the_source_stem():
    """The hyphens in the date become underscores (2026-09-27). A run id
    becomes a PostgreSQL schema name, and a hyphen in an unquoted
    identifier is not a hyphen - it is a minus sign - so this is
    normalised at the point it is minted rather than encoded at the point
    it is used. The stem is still recognisable, which is the whole reason
    it is in the id."""
    run_id = run_id_from_path("/home/keith/Downloads/birth_registrations_2026-09-19.csv")
    assert run_id.startswith("adhoc_birth_registrations_2026_09_19_")


def test_run_id_from_path_strips_a_trailing_slash_for_a_folder():
    run_id = run_id_from_path("/home/keith/Downloads/cp_delivery_09/", prefix="ref")
    assert run_id.startswith("ref_cp_delivery_09_")


def test_run_id_from_path_carries_a_real_utc_timestamp_suffix():
    import re
    run_id = run_id_from_path("x.csv")
    # Lowercase t/z since 2026-09-27 - see the stem test above.
    assert re.search(r"_\d{8}t\d{6}z$", run_id), f"expected a real UTC timestamp suffix, got {run_id!r}"


def test_a_run_id_is_always_a_usable_schema_name():
    """THE INVARIANT THIS FUNCTION NOW CARRIES, and the reason the hex
    encoding could be deleted. Everywhere else a run id is minted
    `run_001`-style and is safe by construction; here it is built from a
    filename a person chose, so it is the one place an unsafe name can
    enter. supply_db._ident() refuses anything unsafe, so a regression
    here fails loudly rather than producing a schema dbt and Soda cannot
    see."""
    from qa_tools.common import supply_db
    for path in ["Births Jan.csv", "weird--name!!.csv", "ALLCAPS.CSV",
                 "/tmp/a folder with spaces/", "2026 extract.csv"]:
        run_id = run_id_from_path(path)
        # Raises SupplyDbError if the id is not a usable identifier.
        assert supply_db.run_schema(run_id).startswith(supply_db.RUN_SCHEMA_PREFIX)
        assert supply_db.run_id_of(supply_db.run_schema(run_id)) == run_id, \
            "a run id must survive the schema round trip exactly"


def test_copy_into_creates_dest_dir_and_copies_content(tmp_path):
    src = tmp_path / "src.csv"
    src.write_text("id\n1\n")
    dest_dir = tmp_path / "nested" / "dest"

    dest_path = copy_into(str(src), str(dest_dir), "copied.csv")

    assert dest_path == os.path.join(str(dest_dir), "copied.csv")
    assert open(dest_path).read() == "id\n1\n"


def test_copy_into_is_a_no_op_when_src_already_is_dest(tmp_path):
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    existing = dest_dir / "same.csv"
    existing.write_text("id\n1\n")

    dest_path = copy_into(str(existing), str(dest_dir), "same.csv")

    assert dest_path == str(existing)
    assert open(dest_path).read() == "id\n1\n"
