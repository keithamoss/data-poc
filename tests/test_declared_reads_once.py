"""REQ-PIPE-192 criteria 1-5: which tables each check declares it reads is
worked out once per process while no check source changes, from one
function every caller uses.

It used to be two: promotion._declared_reads re-collected every check
definition on every call (8-10ms, 402 times in one Child Protection
bootstrap), and qa_results_writer._declared_reads_tables cached the same
answer with an lru_cache keyed on nothing, so an edited check file was
never seen again in that process.
"""
from __future__ import annotations

import shutil

import pytest

from qa_tools.common import promotion, qa_results_writer, tables_read
from qa_tools.common import validate_check_lifecycle as vcl


@pytest.fixture(autouse=True)
def _fresh():
    tables_read.forget_declared_reads()
    yield
    tables_read.forget_declared_reads()


def _counting(monkeypatch):
    calls = []
    real = vcl.collect_checks

    def counted(ref):
        calls.append(ref)
        return real(ref)
    monkeypatch.setattr(vcl, "collect_checks", counted)
    return calls


class TestOneAnswer:

    def test_every_caller_gets_the_same_answer_from_one_place(self, monkeypatch):
        calls = _counting(monkeypatch)
        answers = [promotion._declared_reads(), qa_results_writer._declared_reads_tables(),
                   tables_read.declared_reads()]
        assert answers[0] and answers[0] == answers[1] == answers[2]
        assert len(calls) == 1, "worked out more than once"

    def test_it_is_not_worked_out_again_while_nothing_changed(self, monkeypatch):
        calls = _counting(monkeypatch)
        for _ in range(20):
            promotion._declared_reads()
        assert len(calls) == 1

    def test_each_caller_gets_its_own_copy(self):
        first = tables_read.declared_reads()
        check = next(iter(first))
        first[check].append("cp_tampered")
        first["made-up"] = ["x"]
        again = tables_read.declared_reads()
        assert "cp_tampered" not in again[check] and "made-up" not in again


class TestAnEditedCheckIsSeen:

    def test_a_changed_source_is_collected_afresh(self, tmp_path, monkeypatch):
        """Keyed on content, not on modification time or size: the edit
        below keeps the file's length exactly."""
        yaml_sources, evidently = vcl._sources(None)
        for rel in [rel for rel, _parser in yaml_sources] + evidently:
            src = vcl.ROOT / rel
            if src.exists():
                (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, tmp_path / rel)
        shutil.copytree(vcl.ROOT / "contract", tmp_path / "contract", dirs_exist_ok=True)
        monkeypatch.setattr(vcl, "ROOT", tmp_path)
        before = tables_read.declared_reads()
        calls = _counting(monkeypatch)
        tables_read.declared_reads()
        assert calls == [], "worked out again with nothing changed"

        contract = tmp_path / "contract" / "child-protection-family-support" / "child-protection-contract.yaml"
        text = contract.read_text()
        assert "cp_carers" in text
        edited = text.replace("cp_carers", "cp_carerz", 1)
        assert len(edited) == len(text)
        contract.write_text(edited)
        tables_read.declared_reads()
        assert calls == [None], "an edited check source was not collected again"
        assert before  # the first answer was real


class TestWhenTheDeclarationsCannotBeRead:

    def test_promotion_keeps_its_fail_safe_and_says_so(self, monkeypatch, capsys):
        def broken(ref):
            raise ValueError("a malformed check source")
        monkeypatch.setattr(vcl, "collect_checks", broken)
        assert promotion._declared_reads() == {}
        assert "could not read the cross-table declarations" in capsys.readouterr().out

    def test_the_failure_is_not_remembered(self, monkeypatch):
        real = vcl.collect_checks
        monkeypatch.setattr(vcl, "collect_checks",
                            lambda ref: (_ for _ in ()).throw(ValueError("broken")))
        assert promotion._declared_reads() == {}
        monkeypatch.setattr(vcl, "collect_checks", real)
        assert promotion._declared_reads(), "a failure was cached"


class TestTheBusiestParsersAskOnce:
    """REQ-PIPE-192 criterion 6: the callers that made 47,000 of one Child
    Protection bootstrap's 53,068 configuration parses (the environments
    file, the asset file's PostgreSQL major, and datacontract-cli's two
    per-rule readers) cache what they derive, keyed on the content it came
    from - so once warm they parse nothing more."""

    @pytest.fixture
    def parses(self, monkeypatch):
        from qa_tools.common import config_yaml

        calls = []
        real = config_yaml.parse

        def counted(source, **kwargs):
            calls.append(1)
            return real(source, **kwargs)
        monkeypatch.setattr(config_yaml, "parse", counted)
        return calls

    def test_the_environments_file(self, parses):
        from qa_tools.common import environments

        first = environments._load()
        parses.clear()
        for _ in range(10):
            assert environments._load() == first
        assert parses == []

    def test_the_declared_postgres_major(self, parses):
        from qa_tools.common import postgres_version

        first = postgres_version.declared_major()
        parses.clear()
        for _ in range(10):
            assert postgres_version.declared_major() == first
            assert postgres_version.declaration_errors() == []
        assert parses == []

    def test_datacontracts_per_rule_readers(self, parses):
        from qa_tools.common import datacontract_common as dc

        text = ("type: sql\nmustBeLessThan: 35\ncustomProperties:\n"
                "  - property: check_id\n    value: a.b.c\n")
        assert dc.check_id_from_quality_definition(text) == "a.b.c"
        assert dc.fail_threshold_from_quality_definition(text, "error") == 35
        parses.clear()
        for _ in range(10):
            assert dc.check_id_from_quality_definition(text) == "a.b.c"
            assert dc.fail_threshold_from_quality_definition(text, "error") == 35
        assert parses == []

    def test_an_edited_file_is_read_again(self, tmp_path, parses):
        from qa_tools.common import environments

        path = tmp_path / "environments.yaml"
        path.write_text(environments.ENVIRONMENTS_PATH.read_text())
        before = environments._load(path)
        path.write_text(path.read_text().replace(before[0].id, before[0].id + "x", 1))
        assert environments._load(path)[0].id == before[0].id + "x"
