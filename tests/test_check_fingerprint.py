"""A check's definition fingerprint (REQ-QAC-176): the one writer, its
frozen defaults, its golden, and the stamp every recorded result carries.

The writer is check_fingerprint.fingerprint, which check_lifecycle's parsers
call for config_hash - so the changelog gate and the stored fingerprint are
one function by construction (the code-quality expectation in the
requirement's decisions). These tests drive the real parsers over the real
check files, and the real result writers over a real database.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import textwrap
from pathlib import Path

import pytest

import attempt_support
from conftest import drop_qa_schema
from qa_tools.common import check_fingerprint as fp
from qa_tools.common import check_lifecycle as cl
from qa_tools.common import qa_store, supply_db
from qa_tools.common import validate_check_lifecycle as vcl

ROOT = Path(__file__).resolve().parent.parent


# ---- criterion 15: the golden ---------------------------------------------

#: Literal per-tool settings, in the shape each parser hands the writer, and
#: the v1 fingerprint each must keep. ANY change here - the writer, the
#: normalisation, the frozen defaults at v1, or an rfc8785 upgrade - fails,
#: which is what makes the dependency safe to keep current (NFR 4).
GOLDEN = {
    ("dbt", "not_null"): (
        {"test": "not_null", "config": {"severity": "warn", "warn_if": ">0"}},
        "v1:cb74872c26968939e4760787deec400dae3dbb08e602f6c50980797390872026"),
    ("dbt", "singular"): (
        {"test": "multiple_birth_sibling", "config": {"severity": "error"},
         "definition_source": "-- multiple_birth_sibling.sql\nselect 1 where false\n"},
        "v1:f7d643e077aae87969cd79c13c0dc8c9a84c8fd995e3eae54c1b64742121b64f"),
    ("soda", None): (
        {"check": "missing_count(sex) = 0", "warn": "when > 0"},
        "v1:b63a7cdc441b597441207d19bad0b4e093de2c218509ad6d9fa5b90ef32e2b50"),
    ("datacontract", "sql"): (
        {"type": "sql", "query": "SELECT COUNT(*) FROM t", "mustBeLessThan": 1,
         "dimension": "consistency"},
        "v1:1f285a822971d6c511fa9bd1883e83ac6a213662a63a9b42a2e4e31fb1370207"),
    ("evidently", "psi"): (
        {"column": "sex", "method": "psi", "warn_threshold": 0.1, "fail_threshold": 0.25},
        "v1:dd94a2054a99f6008ec2ab89f5c327774cbe325408ae74a350647fcb4ca47dda"),
    ("file", "encoding"): (
        {"severity": "failure", "formats": ["csv"], "encoding": "utf-8"},
        "v1:416afab8402ee1437bd51932c6369569b370f229684b281d77f41629e665e299"),
}


class TestTheGolden:
    @pytest.mark.parametrize("key", sorted(GOLDEN, key=str))
    def test_each_tools_literal_settings_keep_their_v1_fingerprint(self, key):
        settings, expected = GOLDEN[key]
        assert fp.fingerprint(key[0], key[1], settings) == expected

    def test_v1_is_the_sha256_of_rfc8785_canonical_json(self):
        """Criteria 20 and 21, worked by hand rather than through the writer:
        keys sorted, no whitespace, 0.10 written as 0.1, and the digest whole."""
        settings, expected = GOLDEN[("evidently", "psi")]
        by_hand = b'{"column":"sex","fail_threshold":0.25,"method":"psi","warn_threshold":0.1}'
        assert expected == "v1:" + hashlib.sha256(by_hand).hexdigest()
        assert len(expected) == len("v1:") + 64

    def test_every_real_check_carries_a_v1_fingerprint(self):
        checks = vcl.collect_checks(None)
        assert checks, "no checks were collected - the test would prove nothing"
        assert all(c.config_hash.startswith("v1:") and len(c.config_hash) == 67 for c in checks)


# ---- criterion 7: normalisation --------------------------------------------

class TestNormalisation:
    def test_a_date_is_hashed_as_its_iso_string(self):
        assert (fp.fingerprint("soda", None, {"check": "x", "since": dt.date(2026, 10, 25)})
                == fp.fingerprint("soda", None, {"check": "x", "since": "2026-10-25"}))

    def test_an_unquoted_timestamp_is_refused_naming_the_check_and_the_path(self):
        with pytest.raises(fp.UnhashableSetting) as caught:
            fp.fingerprint("soda", None, {"check": "x", "config": {
                "at": dt.datetime(2026, 10, 25, 9, 0)}}, check_id="a.b.c")
        assert "a.b.c" in str(caught.value) and "config.at" in str(caught.value)

    @pytest.mark.parametrize("value", [{1, 2}, b"bytes", object(), float("nan")])
    def test_a_value_of_an_unknown_type_is_refused_not_coerced(self, value):
        with pytest.raises(fp.UnhashableSetting):
            fp.fingerprint("dbt", "x", {"test": "x", "odd": value}, check_id="a.b.c")

    def test_a_real_parser_refuses_an_unquoted_timestamp_in_a_checks_settings(self, tmp_path):
        path = tmp_path / "checks.yml"
        path.write_text(textwrap.dedent("""\
            checks for t:
              - row_count > 0:
                  since: 2026-10-25 09:00:00
                  attributes: {check_id: a.b.c.d.row_count_soda, category: completeness}
            """))
        with pytest.raises(fp.UnhashableSetting):
            cl.parse_soda_check_metadata(path)


# ---- criteria 8 to 10: frozen defaults -------------------------------------

def _entry(path, value, *, tool="dbt", kind=None, scheme="v1"):
    return {"tool": tool, "path": list(path), "kind": kind, "value": value, "scheme": scheme}


class TestFrozenDefaults:
    BASE = {"test": "not_null", "config": {"severity": "warn"}}

    def _with(self, extra, table):
        return fp.fingerprint("dbt", "not_null", {**self.BASE, **extra}, table=table)

    def test_a_setting_at_its_frozen_default_is_left_out(self):
        table = [_entry(["store_failures"], True)]
        assert self._with({"store_failures": True}, table) == self._with({}, table)
        assert self._with({"store_failures": False}, table) != self._with({}, table)

    def test_compared_by_type_and_value(self):
        assert self._with({"limit": 1}, [_entry(["limit"], 1.0)]) != self._with({}, [])
        assert self._with({"flag": 1}, [_entry(["flag"], True)]) != self._with({}, [])

    def test_maps_are_recursed_and_a_map_left_empty_is_dropped(self):
        table = [_entry(["config", "severity"], "warn")]
        assert (fp.fingerprint("dbt", "not_null", self.BASE, table=table)
                == fp.fingerprint("dbt", "not_null", {"test": "not_null"}, table=table))

    def test_lists_are_compared_whole_never_entry_by_entry(self):
        table = [_entry(["formats"], ["csv"])]
        assert self._with({"formats": ["csv"]}, table) == self._with({}, table)
        assert self._with({"formats": ["csv", "tsv"]}, table) != self._with({}, table)

    def test_null_equals_a_default_only_where_the_table_says_null(self):
        assert self._with({"where": None}, [_entry(["where"], None)]) == self._with({}, [])
        assert self._with({"where": None}, [_entry(["where"], "")]) != self._with({}, [])

    def test_a_default_scoped_to_a_check_kind_applies_to_that_kind_only(self):
        table = [_entry(["store_failures"], True, kind="unique")]
        assert (fp.fingerprint("dbt", "unique", {"test": "u", "store_failures": True}, table=table)
                == fp.fingerprint("dbt", "unique", {"test": "u"}, table=table))
        assert (fp.fingerprint("dbt", "not_null", {"test": "u", "store_failures": True}, table=table)
                != fp.fingerprint("dbt", "not_null", {"test": "u"}, table=table))

    def test_a_default_is_keyed_by_tool(self):
        table = [_entry(["store_failures"], True, tool="soda")]
        assert self._with({"store_failures": True}, table) != self._with({}, table)

    def test_the_committed_table_is_a_literal_the_gate_can_read_at_any_ref(self):
        assert vcl.frozen_defaults_at(None) == tuple(
            __import__("qa_tools.common.frozen_defaults", fromlist=["x"]).FROZEN_DEFAULTS)


# ---- criterion 16: real checks ----------------------------------------------

class TestRealChecks:
    def test_adding_a_setting_at_its_frozen_default_moves_no_real_fingerprint(self):
        """A setting written into every real check at the value a new frozen
        default names leaves every fingerprint where it was."""
        checks = vcl.collect_checks(None)
        assert checks
        for c in checks:
            table = [_entry(["added_in_a_later_release"], "as before", tool=c.tool)]
            grown = {**c.hashed_settings, "added_in_a_later_release": "as before"}
            assert fp.fingerprint(c.tool, c.check_kind, grown, table=table) == c.config_hash, \
                c.check_id

    def test_changing_one_soda_expression_moves_that_check_alone(self, tmp_path):
        rel = "contract/registry-services/bdm-birth-registrations-soda-checks.yml"
        before = {c.check_id: c.config_hash for c in cl.parse_soda_check_metadata(ROOT / rel)}
        text = (ROOT / rel).read_text()
        target = next(c for c in cl.parse_soda_check_metadata(ROOT / rel)
                      if c.hashed_settings["check"].startswith("row_count"))
        expr = target.hashed_settings["check"]
        edited = tmp_path / "soda.yml"
        edited.write_text(text.replace(f"- {expr}:", f"- {expr} + 0:", 1))
        after = {c.check_id: c.config_hash for c in cl.parse_soda_check_metadata(edited)}
        assert {i for i in before if before[i] != after[i]} == {target.check_id}

    def test_changing_one_evidently_threshold_moves_that_check_alone(self):
        rel = "contract/child-protection-family-support/child-protection-evidently-checks.yml"
        checks = cl.load_evidently_checks(ROOT / rel)
        before = {c.check_id: c.config_hash
                  for c in cl.parse_evidently_check_metadata(checks, source=rel)}
        first = next(iter(checks))
        checks[first] = {**checks[first], "fail_threshold": 0.3}
        after = {c.check_id: c.config_hash
                 for c in cl.parse_evidently_check_metadata(checks, source=rel)}
        assert {i for i in before if before[i] != after[i]} == {first}

    def test_changing_one_singular_tests_sql_moves_that_check_alone(self):
        real = vcl.dbt_definitions(None)
        dbt_checks = [c for c in vcl.collect_checks(None) if c.tool == "dbt"]
        singular = next(c for c in dbt_checks if c.check_kind == "singular")
        name = singular.hashed_settings["test"]

        def edited(kind, test):
            text, files = real(kind, test)
            if kind == "singular" and test == name:
                return text + "\n-- tightened", files
            return text, files

        sources = {c.source_file for c in dbt_checks}
        before = {c.check_id: c.config_hash for c in dbt_checks}
        after = {c.check_id: c.config_hash for src in sources
                 for c in cl.parse_dbt_check_metadata(src, definition=edited)}
        assert {i for i in before if before[i] != after.get(i)} == {singular.check_id}

    def test_changing_a_file_checks_definition_moves_it_for_every_dataset_and_no_other(
            self, tmp_path):
        rel = "contract/file-checks.yaml"
        before = cl.parse_file_check_metadata(ROOT / rel)
        name = before[0].check_kind
        text = (ROOT / rel).read_text()
        doc_line = f"check: {name}"
        assert doc_line in text
        edited = tmp_path / "file-checks.yaml"
        # A setting added to that one definition (criterion 22).
        edited.write_text(text.replace(doc_line, f"{doc_line}\n    tightened: true", 1))
        after = {c.check_id: c.config_hash for c in cl.parse_file_check_metadata(edited)}
        moved = {c.check_id for c in before if after[c.check_id] != c.config_hash}
        assert moved == {c.check_id for c in before if c.check_kind == name}
        assert len(moved) > 1, "every dataset's copy of the one definition moves together"

    def test_one_file_check_definition_gives_every_dataset_one_fingerprint(self):
        checks = cl.parse_file_check_metadata(ROOT / "contract/file-checks.yaml")
        by_kind: dict = {}
        for c in checks:
            by_kind.setdefault(c.check_kind, set()).add(c.config_hash)
        assert by_kind and all(len(v) == 1 for v in by_kind.values())


# ---- criterion 12: comparison under the stored scheme -----------------------

class TestComparison:
    def test_a_stored_fingerprint_is_compared_under_its_own_scheme(self):
        check = vcl.collect_checks(None)[0]
        assert not fp.differs(check.config_hash, check)
        assert fp.differs("v1:" + "0" * 64, check)

    def test_a_scheme_this_checkout_does_not_keep_is_refused_not_guessed(self):
        check = vcl.collect_checks(None)[0]
        with pytest.raises(fp.UnknownScheme):
            fp.differs("v9:" + "0" * 64, check)

    def test_hashed_settings_are_outside_the_hash_and_reproduce_it(self):
        for c in vcl.collect_checks(None):
            assert fp.fingerprint(c.tool, c.check_kind, c.hashed_settings) == c.config_hash


# ---- criterion 11: the gate keeps the defaults frozen -----------------------

def _check(check_id, settings, tool="dbt", kind="not_null"):
    return cl.CheckMetadata(check_id=check_id, category="completeness", tool=tool,
                            config_hash="v1:" + "0" * 64, source_file="f",
                            hashed_settings=settings, check_kind=kind)


class TestTheGateKeepsThemFrozen:
    OLD = (_entry(["config", "severity"], "error"),)

    def test_an_unchanged_table_passes(self):
        assert vcl.frozen_default_errors(self.OLD, self.OLD, []) == []

    def test_a_changed_entry_is_refused_naming_it(self):
        changed = (_entry(["config", "severity"], "warn"),)
        errors = vcl.frozen_default_errors(self.OLD, changed, [])
        assert len(errors) == 1 and "#0" in errors[0] and "append-only" in errors[0]

    def test_a_removed_entry_is_refused(self):
        assert vcl.frozen_default_errors(self.OLD, (), [])

    def test_a_new_entry_naming_a_value_a_check_already_writes_is_refused_naming_it(self):
        writes = _check("a.b.c.d.x_dbt", {"test": "not_null", "store_failures": True})
        other = _check("a.b.c.d.y_dbt", {"test": "not_null"})
        new = (*self.OLD, _entry(["store_failures"], True))
        errors = vcl.frozen_default_errors(self.OLD, new, [writes, other])
        assert len(errors) == 1
        assert "#1" in errors[0] and "a.b.c.d.x_dbt" in errors[0]
        assert "a.b.c.d.y_dbt" not in errors[0]

    def test_a_new_entry_no_check_writes_at_that_value_is_accepted(self):
        writes_other = _check("a.b.c.d.x_dbt", {"test": "not_null", "store_failures": False})
        new = (*self.OLD, _entry(["store_failures"], True))
        assert vcl.frozen_default_errors(self.OLD, new, [writes_other]) == []

    def test_a_malformed_entry_is_refused(self):
        assert vcl.frozen_default_errors((), ({"tool": "dbt", "path": ["x"]},), [])

    def test_the_real_gate_passes_on_this_tree(self):
        assert vcl.main() == 0


# ---- criteria 13, 14 and 18: the stamp --------------------------------------

@pytest.fixture
def db(supply_dsn):
    with supply_db.connect(label="test-check-fingerprint") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".run CASCADE')
        yield conn


def _record(check_id):
    return {"dataset_id": "birth-registrations", "check_id": check_id, "status": "pass"}


class TestTheStamp:
    KEYS = {"agency_id": "registry-services", "collection_id": "civil-registration"}

    def _run(self, db, key="fp_run"):
        qa_store.record_run(db, run_key=key, run_timestamp="2026-10-25T10:00:00+08:00",
                            run_by="keith@example.gov.au", environment="sandbox", **self.KEYS)
        return key

    def test_every_row_carries_the_fingerprint_its_map_gives_its_check(self, db):
        key = self._run(db)
        fps = {"c.one": "v1:" + "1" * 64, "c.two": "v1:" + "2" * 64}
        qa_store.record_results(db, key, [_record("c.one"), _record("c.two")], tool="dbt",
                                fingerprints=fps, **self.KEYS)
        rows = dict(db.execute(f'SELECT check_id, definition_fingerprint FROM '
                               f'"{qa_store.SCHEMA}".check_result WHERE run_key = ?',
                               [key]).fetchall())
        assert rows == fps

    def test_a_check_the_map_does_not_hold_is_refused_and_nothing_is_written(self, db):
        key = self._run(db)
        with pytest.raises(fp.NoFingerprint) as caught:
            qa_store.record_results(db, key, [_record("c.one"), _record("c.unknown")],
                                    tool="dbt", fingerprints={"c.one": "v1:" + "1" * 64},
                                    **self.KEYS)
        assert "c.unknown" in str(caught.value)
        assert not db.execute(f'SELECT 1 FROM "{qa_store.SCHEMA}".check_result '
                              "WHERE run_key = ?", [key]).fetchall()

    def test_the_mapping_is_required_by_both_writers(self, db):
        key = self._run(db)
        with pytest.raises(TypeError):
            qa_store.record_results(db, key, [_record("c.one")], tool="dbt", **self.KEYS)
        with pytest.raises(TypeError):
            qa_store.record_file_results(db, key, [_record("c.one")], supply_state="agreed",
                                         load_attempt=1, delivery="d", filename="f",
                                         **self.KEYS)

    def test_a_file_checks_result_is_stamped_too(self, db):
        key = self._run(db)
        qa_store.record_file_results(db, key, [_record("c.file")], supply_state="agreed",
                                     load_attempt=1, delivery="d", filename="f.csv",
                                     fingerprints={"c.file": "v1:" + "3" * 64}, **self.KEYS)
        assert db.execute(f'SELECT definition_fingerprint FROM "{qa_store.SCHEMA}".check_result '
                          "WHERE run_key = ?", [key]).fetchall() == [("v1:" + "3" * 64,)]

    def test_the_column_refuses_a_malformed_or_missing_fingerprint(self, db):
        import psycopg

        key = self._run(db)
        for bad in (None, "abc", "v1:" + "z" * 64):
            with pytest.raises(psycopg.Error):
                db.execute(f'INSERT INTO "{qa_store.SCHEMA}".check_result (run_key, agency_id, '
                           "collection_id, tool, check_id, status, definition_fingerprint) "
                           "VALUES (?, 'a', 'c', 'dbt', 'x', 'pass', ?)", [key, bad])

    def test_the_fingerprint_is_not_carried_into_a_read_back_record(self, db):
        from qa_tools.common import qa_results_reader

        key = self._run(db)
        qa_store.record_results(db, key, [_record("c.one")], tool="dbt",
                                fingerprints=attempt_support.ANY_CHECK, **self.KEYS)
        attempt_support.opened(db, key)
        qa_store.complete_run(db, key)
        records = qa_results_reader.read_one(self.KEYS["agency_id"], self.KEYS["collection_id"],
                                             key, "dbt", dataset="birth-registrations")
        assert records and "definition_fingerprint" not in records[0]


class TestAnOlderDatabaseIsRefused:
    def test_version_48_is_refused_naming_the_rebuild(self):
        """Criterion 18: the bump, refused by the one refusal every bump uses."""
        assert qa_store.SCHEMA_VERSION > 48
        with pytest.raises(qa_store.SchemaVersionError) as caught:
            qa_store._refuse_another_version(48)
        assert "mothman env reset-synthetic" in str(caught.value)
        assert "mothman pipeline bootstrap" in str(caught.value)

    def test_a_real_version_48_database_is_refused_before_any_ddl(self, supply_dsn):
        with supply_db.connect(label="test-check-fingerprint") as conn:
            drop_qa_schema(conn)
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{qa_store.SCHEMA}"')
            conn.execute(f'CREATE TABLE "{qa_store.SCHEMA}".schema_version '
                         "(only_row boolean PRIMARY KEY DEFAULT true, version integer)")
            conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".schema_version (version) VALUES (48)')
            try:
                with pytest.raises(qa_store.SchemaVersionError):
                    qa_store.ensure_schema(conn)
            finally:
                drop_qa_schema(conn)
                qa_store.ensure_schema(conn)


# ---- criterion 24: one map per attempt --------------------------------------

class TestOneMapPerAttempt:
    def test_an_attempts_results_carry_the_map_taken_when_it_opened(self, db, monkeypatch):
        from qa_tools.common import qa_results_writer, tables_read

        opened_with = {"c.one": "v1:" + "4" * 64}
        monkeypatch.setattr(tables_read, "definition_fingerprints", lambda: dict(opened_with))
        attempt = qa_results_writer.open_run("registry-services", "civil-registration",
                                             "fp_attempt", "2026-10-25T10:00:00+08:00",
                                             "keith@example.gov.au")
        try:
            # The definitions change part way through the attempt.
            monkeypatch.setattr(tables_read, "definition_fingerprints",
                                lambda: {"c.one": "v1:" + "5" * 64})
            assert qa_results_writer.fingerprints_for("fp_attempt") == opened_with
            qa_results_writer.write_qa_result("registry-services", "civil-registration",
                                              "fp_attempt", "2026-10-25T10:00:00+08:00", "dbt",
                                              {}, verified=[_record("c.one")])
        finally:
            attempt.end(None, completed=True)
        assert db.execute(f'SELECT definition_fingerprint FROM "{qa_store.SCHEMA}".check_result '
                          "WHERE run_key = 'fp_attempt'").fetchall() == [("v1:" + "4" * 64,)]

    def test_a_write_outside_an_attempt_takes_the_map_current_at_that_write(self, monkeypatch):
        from qa_tools.common import qa_results_writer, tables_read

        monkeypatch.setattr(tables_read, "definition_fingerprints",
                            lambda: {"c.one": "v1:" + "6" * 64})
        assert qa_results_writer.fingerprints_for("not_open") == {"c.one": "v1:" + "6" * 64}

    def test_the_real_map_holds_every_real_check_and_raises_rather_than_go_partial(
            self, monkeypatch):
        from qa_tools.common import tables_read

        tables_read.forget_declared_reads()
        real = tables_read.definition_fingerprints()
        assert real == {c.check_id: c.config_hash for c in vcl.collect_checks(None)}

        def broken(ref):
            raise cl.MissingCheckIdError("a check file that will not parse")

        tables_read.forget_declared_reads()
        monkeypatch.setattr(vcl, "collect_checks", broken)
        with pytest.raises(cl.MissingCheckIdError):
            tables_read.definition_fingerprints()
        tables_read.forget_declared_reads()
