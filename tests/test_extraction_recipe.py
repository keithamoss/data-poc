"""An extraction arrives as a package - CSV files plus a recipe JSON whose
format we define - and a package with no valid recipe is refused
(REQ-PIPE-439). Driven through the extraction kind's own reader, the one
`mothman one-off open` uses."""
from __future__ import annotations

import io
import json

import pytest

import extraction_support as ex
import one_off_support
from asset_model.kinds import extraction_recipe as er


@pytest.fixture
def one_offs(tmp_path, monkeypatch):
    world = one_off_support.OneOffs(tmp_path, monkeypatch)
    yield world
    world.close()


def _refused(location, **kw) -> list[str]:
    with pytest.raises(er.RecipeRefused) as refused:
        er.read(str(location), **kw)
    return refused.value.problems


class TestAPackage:
    """Criteria 1 to 4."""

    def test_a_local_package_is_read(self, tmp_path, one_offs):
        got = er.read(str(ex.package(tmp_path / "pkg")))
        r = got.recipe
        assert (r.format_version, r.extraction_id, r.project) == (1, "cohort-2026-a",
                                                                  "The 2026 cohort study")
        assert got.files == ("people.csv", "recipe.json", "visits.csv")
        people, visits = r.tables
        assert (people.agency_id, people.collection_id, people.dataset_id, people.table) == (
            "health-agency", "cohort-study", "cohort-people", "cohort_people")
        assert people.columns[0] == er.Column("person_id", "string", True)
        assert people.cohort == (er.Bound("first_seen", "2020-01-01", "2024-12-31"),)
        assert people.expected_rows == 3 and visits.expected_rows is None
        assert visits.derived is True and people.derived is False
        assert len(r.digest) == 64

    def test_an_s3_package_is_read_through_the_client_given(self, tmp_path, one_offs):
        objects = {"pkgs/a/recipe.json": json.dumps(ex.RECIPE).encode(),
                   "pkgs/a/people.csv": b"a\n", "pkgs/a/visits.csv": b"a\n"}

        class Client:
            def list_objects_v2(self, Bucket, Prefix, **kw):
                assert Bucket == "bucket"
                return {"Contents": [{"Key": k} for k in objects if k.startswith(Prefix)],
                        "IsTruncated": False}

            def get_object(self, Bucket, Key):
                return {"Body": io.BytesIO(objects[Key])}

        got = er.read("s3://bucket/pkgs/a", s3_client=Client())
        assert got.recipe.extraction_id == "cohort-2026-a"
        assert got.files == ("people.csv", "recipe.json", "visits.csv")

    def test_the_filter_is_text_never_executed(self, tmp_path, one_offs):
        got = er.read(str(ex.package(tmp_path / "pkg")))
        assert got.recipe.filter == ex.RECIPE["filter"]

    def test_a_declared_file_missing_from_the_package_is_not_a_refusal(self, tmp_path, one_offs):
        """REQ-QAC-441 criterion 3 records it as a failing result instead."""
        got = er.read(str(ex.package(tmp_path / "pkg", files=("people.csv",))))
        assert "visits.csv" not in got.files


class TestCSVOnly:
    """Criterion 5."""

    def test_another_format_is_refused_naming_the_table(self, tmp_path, one_offs):
        doc = ex.recipe()
        doc["tables"][1]["format"] = "parquet"
        problems = _refused(ex.package(tmp_path / "pkg", doc))
        assert any("'cohort_visits'" in p and "parquet" in p for p in problems), problems


class TestEveryTableNamesAnIdentifier:
    """Criterion 3 AMENDED 2026-11-22 (Keith): every table declares at least
    one primary identifier - a failing row is only ever named by one
    (REQ-QAC-441 criterion 9) - or the recipe is refused, naming the table."""

    def test_a_table_with_none_is_refused_naming_it(self, tmp_path, one_offs):
        doc = ex.recipe()
        for c in doc["tables"][1]["columns"]:
            c["primary_identifier"] = False
        problems = _refused(ex.package(tmp_path / "pkg", doc))
        assert any("cohort_visits" in p and "primary identifier" in p for p in problems), problems
        assert not any("cohort_people" in p for p in problems)


class TestRefusedBeforeAnything:
    """Criterion 6: missing, unparseable or off-schema - every problem named."""

    def test_no_recipe(self, tmp_path, one_offs):
        (tmp_path / "pkg").mkdir()
        assert "no recipe.json" in _refused(tmp_path / "pkg")[0]

    def test_not_json(self, tmp_path, one_offs):
        assert "does not parse" in _refused(ex.package(tmp_path / "pkg", raw="{nope"))[0]

    def test_every_schema_problem_is_named(self, tmp_path, one_offs):
        doc = ex.recipe()
        del doc["project"]
        doc["tables"][0]["columns"][0]["type"] = "uuid"
        problems = _refused(ex.package(tmp_path / "pkg", doc))
        assert any("project" in p for p in problems) and any("uuid" in p for p in problems)

    def test_an_unknown_format_version(self, tmp_path, one_offs):
        problems = _refused(ex.package(tmp_path / "pkg", ex.recipe(recipe_format_version=2)))
        assert "recipe_format_version 2" in problems[0]

    def test_a_file_escaping_the_package(self, tmp_path, one_offs):
        doc = ex.recipe()
        doc["tables"][0]["file"] = "../../etc/passwd"
        assert any("leave the package" in p for p in _refused(ex.package(tmp_path / "pkg", doc)))


class TestTheID:
    """Criterion 7."""

    def test_a_badly_formed_id(self, tmp_path, one_offs):
        problems = _refused(ex.package(tmp_path / "pkg", ex.recipe(extraction_id="Cohort_A")))
        assert any("'Cohort_A'" in p for p in problems)

    def test_an_id_already_an_asset(self, tmp_path, one_offs):
        problems = _refused(ex.package(tmp_path / "pkg", ex.recipe(extraction_id="daily")))
        assert any("assets/daily" in p and "new extraction" in p for p in problems)

    def test_an_id_already_a_one_off(self, tmp_path, one_offs):
        one_offs.add("cohort-2026-a")
        problems = _refused(ex.package(tmp_path / "pkg"))
        assert any("audit/cohort-2026-a" in p for p in problems)


class TestNoDatabase:
    """Criterion 8: reading a recipe opens no connection, so nothing of it can
    be written to one."""

    def test_reading_opens_no_connection(self, tmp_path, one_offs, monkeypatch):
        from qa_tools.common import supply_db

        monkeypatch.setattr(supply_db, "connect", lambda *a, **k: pytest.fail("connected"))
        er.read(str(ex.package(tmp_path / "pkg")))


class TestTheKind:
    def test_the_extraction_kind_is_registered_with_its_words(self):
        from asset_model import one_off_kinds

        kind = one_off_kinds.get("extraction")
        assert (kind.singular, kind.plural, kind.layer) == ("extraction", "extractions",
                                                           "Recipe check")
        assert kind.reader is er.read
        from cli import check

        assert set(kind.gates) == set(check.per_asset_gates()), "every gate declared"


pytestmark = pytest.mark.asset("daily")
