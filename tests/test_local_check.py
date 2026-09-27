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
    it is in the id - and since 2026-09-27 it is also CAPPED, so what
    survives is the recognisable start of the name rather than all of
    it (see TestTheStemIsCapped below for the arithmetic)."""
    run_id = run_id_from_path("/home/keith/Downloads/birth_registrations_2026-09-19.csv")
    assert run_id.startswith("adhoc_birth_registrat_")
    assert "-" not in run_id, "a hyphen is a minus sign in an unquoted identifier"


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


class TestTheStemIsCapped:
    """A run id built from a filename must stay a workable name.

    KEITH'S QUESTION, 2026-09-27: "why are the ad hoc ids so long?"
    The arithmetic: `adhoc` + the file stem + a UTC timestamp, and the
    stem was the whole filename - thirty of the fifty-three characters
    in `adhoc_birth_registrations_2026_09_20_20260927t041329z`. For
    this project's own deliveries that stem already carries the
    dataset name and a date, so the staged table name said
    `birth_registrations` twice and carried two dates: 74 bytes
    against PostgreSQL's 63-byte identifier limit.

    supply_db.arrival_segment() bounds the TABLE NAME with a digest,
    which stopped the failure but left the id itself long in committed
    history and in every listing a person reads. Capping the stem
    treats the cause instead.
    """

    MAX_STEM = 20

    def test_a_long_stem_is_capped(self):
        run_id = run_id_from_path("/downloads/birth_registrations_2026_09_20.csv")
        assert len(run_id) < 45, f"still long: {run_id!r} ({len(run_id)})"
        assert run_id.startswith("adhoc_birth_registrat"), run_id

    def test_the_timestamp_survives_intact(self):
        """Capping the whole id rather than the stem would eat the
        timestamp, which is what makes a repeat check of the same file
        a different run."""
        import re
        run_id = run_id_from_path("/downloads/an_extremely_long_supplier_filename_indeed.csv")
        assert re.search(r"_\d{8}t\d{6}z$", run_id), run_id

    def test_a_short_stem_is_left_alone(self):
        run_id = run_id_from_path("/downloads/jan.csv")
        assert run_id.startswith("adhoc_jan_"), run_id

    def test_no_doubled_or_trailing_underscores_in_the_stem(self):
        """A cap landing on an underscore, or a name that normalises to
        one, must not produce `adhoc_births__20260927...` - `__` is the
        separator supply_db.split_staged() reads a staged table name
        by, and a run id carrying one splits the name in the wrong
        place."""
        for path in ["/downloads/births_____jan.csv",
                     "/downloads/a_name_that_is_cut_right_here_ok.csv",
                     "/downloads/!!!.csv"]:
            run_id = run_id_from_path(path)
            assert "__" not in run_id, f"{path} -> {run_id!r}"

    def test_a_realistic_long_filename_needs_no_digest_to_be_staged(self):
        """The end of the chain, and the point of the change: the
        staged table name fits without arrival_segment() having to
        truncate and hash it."""
        from qa_tools.common import supply_db

        run_id = run_id_from_path("/downloads/birth_registrations_2026_09_20.csv")
        assert supply_db.arrival_segment(run_id) == run_id, \
            "the id still has to be shortened to be a table name"
        name = supply_db.staged_table("birth_registrations", run_id)
        assert len(name.encode()) <= 63, f"{name} is {len(name.encode())} bytes"

    def test_two_different_long_files_still_differ(self):
        """Capping trades some distinctness for length, and the
        timestamp plus prefix carry the rest - but two files whose
        names differ inside the cap must not collide."""
        a = run_id_from_path("/downloads/northern_region_extract.csv")
        b = run_id_from_path("/downloads/southern_region_extract.csv")
        assert a != b
