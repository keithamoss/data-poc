"""The checkout declares the PostgreSQL major it targets, and refuses a server
on a different one (REQ-PIPE-146)."""
from __future__ import annotations

import inspect

import pytest

from qa_tools.common import postgres_version as pv
from qa_tools.common import supply_db


class _Conn:
    def __init__(self, num):
        self.num, self.sql = num, []

    def execute(self, sql):
        self.sql.append(sql)
        return self

    def fetchone(self):
        return (self.num,)


class TestTheDeclaration:
    """Criteria 1 and 6."""

    def test_the_committed_asset_declares_16(self):
        assert pv.declared_major() == 16
        assert pv.declaration_errors() == []

    @pytest.mark.parametrize("body, says", [
        ("data_asset_id: x\n", "missing"),
        ("postgres_major: '16'\n", "not a whole-number"),
        ("postgres_major: 16.8\n", "not a whole-number"),
        ("postgres_major: true\n", "not a whole-number"),
        ("postgres_major: 0\n", "not a whole-number"),
    ])
    def test_missing_or_not_a_whole_number_is_rejected(self, tmp_path, body, says):
        p = tmp_path / "data-asset.yaml"
        p.write_text(body)
        errors = pv.declaration_errors(p)
        assert len(errors) == 1 and says in errors[0]

    def test_the_gate_that_reads_data_asset_yaml_runs_it(self, monkeypatch):
        from qa_tools.common import validate_hierarchy

        monkeypatch.setattr(pv, "errors", lambda: ["the declaration is wrong"])
        assert "the declaration is wrong" in validate_hierarchy.validate()


class TestTheServerIsAsserted:
    """Criteria 2, 3 and 4."""

    def test_a_different_major_is_refused_naming_both(self):
        with pytest.raises(pv.VersionMismatch, match=r"PostgreSQL 17.*postgres_major 16"):
            pv.check_server(_Conn("170002"), declared=16)

    def test_any_minor_of_the_declared_major_is_accepted_silently(self, capsys):
        for num in ("160000", "160008", "160013", "160099"):
            pv.check_server(_Conn(num), declared=16)
        assert capsys.readouterr() == ("", "")

    def test_it_reads_server_version_num_and_never_aurora_version(self):
        conn = _Conn("160013")
        pv.check_server(conn, declared=16)
        assert conn.sql == ["SELECT current_setting('server_version_num')"]
        assert "SELECT aurora_version" not in inspect.getsource(pv)

    def test_a_real_connection_is_refused_when_the_majors_differ(self, supply_dsn, monkeypatch):
        """Through supply_db.connect itself, against the real server."""
        monkeypatch.setattr(pv, "declared_major", lambda path=None: 9)
        with pytest.raises(supply_db.SupplyDbError,
                           match=r"PostgreSQL 16 .*postgres_major 9"):
            supply_db.connect(dsn=supply_dsn)

    def test_a_real_connection_on_the_declared_major_opens(self, supply_dsn):
        conn = supply_db.connect(dsn=supply_dsn, read_only=True)
        conn.close()


class TestEveryImageTagNamesTheDeclaredMajor:
    """Criterion 5 - every tag, not the first (post-build-review #87)."""

    COMPOSE = "services:\n  db:\n    image: postgres:16\n  app:\n    image: python:3.11\n"

    def _workflow(self, *images):
        jobs = "".join(
            f"  job{i}:\n    runs-on: x\n    services:\n      postgres:\n        image: {img}\n"
            for i, img in enumerate(images))
        return f"jobs:\n{jobs}"

    def _write(self, tmp_path, compose, workflow):
        c, w = tmp_path / "compose.yml", tmp_path / "test.yml"
        c.write_text(compose)
        w.write_text(workflow)
        return c, w

    def test_the_committed_files_agree(self):
        assert pv.image_tag_errors() == []
        assert len(pv.image_tags()) == 3

    def test_the_second_ci_job_is_checked_too(self, tmp_path):
        c, w = self._write(tmp_path, self.COMPOSE, self._workflow("postgres:16", "postgres:17"))
        errors = pv.image_tag_errors(16, c, w)
        assert len(errors) == 1 and "job1" in errors[0] and "postgres:17" in errors[0]

    def test_the_dev_container_is_checked(self, tmp_path):
        c, w = self._write(tmp_path, self.COMPOSE.replace("postgres:16", "postgres:15-alpine"),
                           self._workflow("postgres:16"))
        errors = pv.image_tag_errors(16, c, w)
        assert len(errors) == 1 and "docker-compose" in errors[0]

    def test_a_minor_or_variant_tag_of_the_major_passes(self, tmp_path):
        c, w = self._write(tmp_path, self.COMPOSE.replace("postgres:16", "postgres:16.8"),
                           self._workflow("postgres:16-alpine", "docker.io/library/postgres:16.13"))
        assert pv.image_tag_errors(16, c, w) == []

    def test_no_image_at_all_is_not_a_silent_pass(self, tmp_path):
        c, w = self._write(tmp_path, "services: {}\n", "jobs: {}\n")
        assert pv.image_tag_errors(16, c, w)


def test_major_of():
    assert pv.major_of("160013") == 16 and pv.major_of(170002) == 17
