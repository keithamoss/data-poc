"""Tests for qa_tools/common/arrivals.py - where the delivery format
stops being a file layout and becomes something the pipeline acts on
(REQ-GEN-043).

tests/test_delivery.py covers what the FORMAT refuses to believe. This
covers what RECOGNITION works out for itself: which dataset a file
belongs to, which collection a delivery is for, what order arrivals
happened in, and what a run is called. Every one of those is derived
from something observable, and the tests are written to fail if any of
them ever comes from a declaration instead.

The last class is the criterion-7 firewall, and it is a static one on
purpose - see its own docstring for why a runtime assertion would not
be enough.
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from qa_tools.common import arrivals, asset_time, delivery, hierarchy

PERTH = timezone(timedelta(hours=8))
WHEN = datetime(2026, 8, 24, 14, 36, 3, tzinfo=PERTH)

_BDM_FILE = "birth_registrations_2026-08-24.csv"
_CP_FILES = ("cp_clients.csv", "cp_notifications.csv", "cp_investigations.csv",
             "cp_placements.csv", "cp_carers.csv", "cp_case_workers.csv")


@pytest.fixture
def dirs(tmp_path):
    return tmp_path / "deliveries", tmp_path / "receipts"


def _write(dirs, name, files, when=WHEN):
    d, r = dirs
    return delivery.write_delivery(name, files, received_at=when, deliveries_dir=d, receipts_dir=r)


def _bdm(dirs, name, when=WHEN, filename=_BDM_FILE):
    return _write(dirs, name, {filename: "registration_number\n1\n"}, when)


def _cp(dirs, name, when=WHEN):
    return _write(dirs, name, {f: "a\n1\n" for f in _CP_FILES}, when)


def _for(dirs, collection="civil-registration", prefix="run_"):
    d, r = dirs
    return arrivals.arrivals_for(collection, prefix, d, r)


class TestAnUnknownCollectionIsAnError:
    """post-build-review #41. `arrivals_for()` answered an unknown
    collection id with `[]` - a pipeline that processes nothing and
    reports nothing wrong, which is the false-green direction.

    It matters because the id is restated inline in several entry
    points (#36), so renaming a collection in `contract/data-asset.yaml`
    used to give every BDM/CP run zero arrivals rather than an error.
    Everywhere else in this layer an unknown id raises -
    `hierarchy.dataset`, `schedule.calendar`, `datasets_in_collection` -
    and this was the one exception.
    """

    def test_a_renamed_collection_raises_rather_than_returning_nothing(self, dirs):
        _bdm(dirs, "d1")
        with pytest.raises(hierarchy.UnknownDatasetError, match="civil-registration-RENAMED"):
            _for(dirs, collection="civil-registration-RENAMED")

    def test_the_error_names_the_collections_that_do_exist(self, dirs):
        """The usual cause is a near miss, so the error has to be
        actionable without opening the config."""
        with pytest.raises(hierarchy.UnknownDatasetError, match="civil-registration"):
            _for(dirs, collection="civil-registrations")

    def test_a_real_collection_with_no_deliveries_still_answers_empty(self, dirs):
        """The must-not-change half: nothing having arrived yet is an
        ordinary state, not an error. Only an id the tree does not
        define is."""
        assert _for(dirs) == []


class TestADeliveryIsRecognisedNotLabelled:
    """Criterion 3 - the dataset comes from the filename, through that
    dataset's own configured pattern, and from nothing else."""

    def test_the_dataset_comes_from_the_filename_alone(self, dirs):
        _bdm(dirs, "a-name-that-says-nothing")
        found = _for(dirs)
        assert [a.files_by_dataset for a in found] == [{"birth-registrations": (_BDM_FILE,)}]

    def test_the_collection_is_worked_out_from_the_files_not_declared(self, dirs):
        _cp(dirs, "2026-Q3")
        # SIX ARRIVALS SINCE REQ-PIPE-105, one per file - the
        # attribution being tested is unchanged, only the count.
        assert {a.collection_id for a in _for(dirs, "child-protection", "cp_run_")} \
            == {"child-protection"}
        # And the same delivery is NOT claimed by the other collection.
        assert _for(dirs) == []

    def test_a_delivery_nothing_can_place_is_reported_not_guessed_at(self, dirs):
        _write(dirs, "mystery-drop", {"covering_note.pdf": "%PDF-1.4\n"})
        d, r = dirs
        assert [x.name for x in arrivals.unplaceable(d, r)] == ["mystery-drop"]
        # Reported, and the run does not fail (criterion 13).
        with pytest.warns(UserWarning, match="covering_note.pdf"):
            assert _for(dirs) == []
        with pytest.warns(UserWarning):
            assert _for(dirs, "child-protection", "cp_run_") == []

    def test_a_delivery_spanning_two_collections_is_attributed_not_held(self, dirs):
        """REVERSED 2026-09-24 (Keith), and this test's old name said
        the opposite: a spanning delivery used to RAISE, which took the
        whole run down for one odd drop. The argument for holding was
        that spanning means the transport BOUNDARY is wrong rather than
        the data - and it does not survive the observation that
        spanning is legitimate, because a hold stops healthy supply on
        a boundary that is working.

        One delivery, two runs: the DELIVERY is the transport unit and
        the RUN is the per-collection QA unit, and they were only ever
        the same thing by coincidence of this PoC's generated data."""
        _write(dirs, "mixed", {_BDM_FILE: "registration_number\n1\n", "cp_clients.csv": "a\n1\n"})

        bdm = _for(dirs)
        cp = _for(dirs, "child-protection", "cp_run_")

        assert [a.delivery_name for a in bdm] == ["mixed"]
        assert [a.delivery_name for a in cp] == ["mixed"]
        assert bdm[0].run_id.startswith("birth_registrations__")
        assert cp[0].run_id.startswith("cp_clients__")
        # Each side sees only its OWN files - attribution is per file,
        # on its own dataset's terms.
        assert bdm[0].files_by_dataset == {"birth-registrations": (_BDM_FILE,)}
        assert cp[0].files_by_dataset == {"cp-clients": ("cp_clients.csv",)}

    def test_a_spanning_delivery_names_both_collections(self, dirs):
        _write(dirs, "mixed", {_BDM_FILE: "registration_number\n1\n", "cp_clients.csv": "a\n1\n"})
        d, r = dirs
        [one] = delivery.list_deliveries(d, r)
        assert arrivals.recognise(one).collections == (
            "child-protection", "civil-registration")


class TestRunIdsComeFromWhatArrivedAndWhen:
    """REQ-PIPE-057 criterion 18, met at last by REQ-PIPE-105 - and
    this class asserted the opposite until 2026-10-02, so what it used
    to say is worth keeping.

    It read `TestRunIdsComeFromReceiptOrder` and pinned a POSITIONAL
    scheme: `run_001` for the first delivery recognised, `run_002` for
    the second. That is exactly what criterion 18 forbids - an id must
    not come from a position recognition can reorder or shorten - and
    the class docstring recorded the damage in passing, "the thing
    that permuted 23 real run_ids when this landed". It was a pin on a
    known defect.

    The id now says WHAT arrived and WHEN, in the staged physical
    table's own spelling. Receipt ORDER still decides processing order
    and `run_index` still reports it; what changed is that nothing
    keys on it.
    """

    def test_the_id_names_the_table_and_the_arrival(self, dirs):
        _bdm(dirs, "first", when=WHEN)
        got = _for(dirs)[0]
        assert got.run_id == f"birth_registrations__{asset_time.arrival_key(WHEN)}"

    def test_receipt_order_still_decides_PROCESSING_order(self, dirs):
        """The half that did not change, and must not: filing depends
        on what the arrival before it promoted."""
        _bdm(dirs, "second", when=WHEN + timedelta(days=1))
        _bdm(dirs, "first", when=WHEN, filename="birth_registrations_2026-08-23.csv")
        assert [a.delivery_name for a in _for(dirs)] == ["first", "second"]

    def test_but_nothing_renumbers_when_an_earlier_one_appears(self, dirs):
        """The property criterion 18 is actually about. Under the old
        scheme inserting an earlier delivery renamed every later run;
        here the ids are untouched."""
        _bdm(dirs, "second", when=WHEN + timedelta(days=1))
        before = {a.run_id for a in _for(dirs)}
        _bdm(dirs, "first", when=WHEN, filename="birth_registrations_2026-08-23.csv")
        after = {a.run_id for a in _for(dirs)}
        assert before < after, "an earlier delivery re-keyed the later one"

    def test_the_directory_name_never_decides_the_order(self, dirs):
        """Named so that alphabetical order is the exact reverse of
        receipt order - a sort that fell back to the name would pass
        every other test in this file and fail this one."""
        _bdm(dirs, "zzz-earliest", when=WHEN)
        _bdm(dirs, "aaa-latest", when=WHEN + timedelta(hours=1),
             filename="birth_registrations_2026-08-25.csv")
        assert [a.delivery_name for a in _for(dirs)] == ["zzz-earliest", "aaa-latest"]

    def test_the_id_carries_OUR_receipt_instant_not_the_suppliers_date(self, dirs):
        """REQ-GEN-042 settled that a run id must not carry a date the
        anchor can move. Our own receipt instant is not that: it is a
        fact about when the file reached us, and it never moves."""
        _bdm(dirs, "drop")
        got = _for(dirs)[0]
        assert got.run_id.endswith(asset_time.arrival_key(got.received_at))

    def test_the_prefix_no_longer_decides_anything(self, dirs):
        """`run_id_prefix` is kept in the signature - every call site
        passes it and it still says which collection is meant - but it
        is no longer part of the id, so a caller cannot change
        identity by passing a different one."""
        _cp(dirs, "whatever")
        one = _for(dirs, "child-protection", "cp_run_")[0].run_id
        other = _for(dirs, "child-protection", "anything_")[0].run_id
        assert one == other

    def test_run_index_reports_position_without_being_identity(self, dirs):
        _bdm(dirs, "one", when=WHEN)
        _bdm(dirs, "two", when=WHEN + timedelta(days=1),
             filename="birth_registrations_2026-08-25.csv")
        assert [a.run_index for a in _for(dirs)] == [1, 2]


class TestWhatAnArrivalHandsToThePipeline:
    """Criterion 7 at the boundary: as_entry() is what every
    orchestrator passes around, so it is the shape that decides what
    CAN reach committed history."""

    def test_an_entry_carries_only_observed_facts(self, dirs):
        _bdm(dirs, "BDM_20260824")
        entry = _for(dirs)[0].as_entry()
        assert set(entry) == {"run_id", "run_index", "received_at", "delivery", "path"}

    def test_the_received_at_is_ours_and_carries_its_offset(self, dirs):
        _bdm(dirs, "drop")
        entry = _for(dirs)[0].as_entry()
        assert entry["received_at"] == WHEN.isoformat()
        assert datetime.fromisoformat(entry["received_at"]).tzinfo is not None

    def test_a_receipt_lookalike_inside_the_delivery_does_not_set_the_instant(self, dirs):
        """The one attack the boundary exists to stop, checked through
        recognition rather than only at the format layer."""
        forged = datetime(1999, 1, 1, tzinfo=timezone.utc).isoformat()
        _write(dirs, "forged", {_BDM_FILE: "registration_number\n1\n",
                                 "receipt.json": json.dumps({"received_at": forged})})
        found = _for(dirs)[0]
        assert found.received_at == WHEN
        assert any("receipt" in a.lower() for a in found.anomalies)

    def test_path_for_returns_the_real_file_that_arrived(self, dirs):
        _bdm(dirs, "BDM_20260824")
        path = _for(dirs)[0].path_for("birth-registrations")
        assert path.name == _BDM_FILE, "the supplier's own filename, not one built from the run_id"
        assert path.is_file()

    def test_path_for_refuses_rather_than_picking_one_of_several(self, dirs):
        """Criterion 8 says the FORMAT must carry a split extract. It
        does not say a loader may quietly take the first half."""
        _write(dirs, "split", {"birth_registrations_2026-08-24.csv": "registration_number\n1\n",
                                "birth_registrations_2026-08-24_part2.csv": "registration_number\n2\n"})
        found = _for(dirs)[0]
        assert len(found.files_by_dataset["birth-registrations"]) == 2
        with pytest.raises(delivery.DeliveryFormatError, match="matched 2 files"):
            found.path_for("birth-registrations")

    def test_an_unmatched_file_is_carried_not_swallowed(self, dirs):
        """Criterion 9 - a covering note is a real thing suppliers
        send, and losing it silently is not the same as handling it."""
        _write(dirs, "with-note", {_BDM_FILE: "registration_number\n1\n",
                                    "covering_note.pdf": "%PDF-1.4\n"})
        found = _for(dirs)[0]
        assert found.unmatched == ("covering_note.pdf",)
        assert found.files_by_dataset == {"birth-registrations": (_BDM_FILE,)}

    def test_files_for_several_datasets_are_one_arrival_EACH(self, dirs):
        """REVERSED BY REQ-PIPE-105 criterion 1, and the old assertion
        is worth stating because it was the whole model until
        2026-10-02: six CP tables landing together were ONE arrival
        carrying six datasets, which is what made "is the delivery
        complete?" a question anything had to ask.

        They are now six arrivals of one dataset each, processed
        without waiting for one another. The DELIVERY is still one
        thing - every arrival here names it - and it is no longer the
        unit of work."""
        _cp(dirs, "2026-Q3")
        found = _for(dirs, "child-protection", "cp_run_")
        assert len(found) == 6
        assert all(len(a.files_by_dataset) == 1 for a in found)
        assert {a.delivery_name for a in found} == {"2026-Q3"}


class TestTheGeneratorsBookkeepingIsWalledOff:
    """Criterion 7, enforced STATICALLY rather than by observation.

    A runtime test can only show that today's committed history happens
    to be clean, which says nothing about the next module somebody adds.
    The rule is about what may READ the bookkeeping at all, so it is
    checked by parsing the modules - the same reasoning the check-id and
    hierarchy gates already use.
    """

    ROOT = Path(__file__).resolve().parent.parent
    # Everything downstream of an arrival. The generator itself is
    # deliberately absent: writing the bookkeeping is its job.
    WALLED = ("qa_tools", "pipeline", "dashboard", "cli")

    # delivery.py DEFINES the constant so the generator has one name to
    # write to, and defining it is not reading it.
    DEFINES_THE_NAME = "qa_tools/common/delivery.py"
    # The modules whose job is to RUN the generator - `mothman bdm
    # generate-synthetic-data` and `mothman cp generate-synthetic-data`.
    # Invoking the generator is not reading its bookkeeping, and a rule
    # that forbade it would forbid generating data at all.
    #
    # pipeline/orchestrate.py used to be listed here too, as the entry
    # point `mothman bdm generate-synthetic-data` went through. It was
    # deleted with the combined DuckDB warehouse it existed to build
    # (REQ-PIPE-087 criterion 1), and the CLI now calls the generator
    # directly, so cli/ is the whole of the exception again.
    MAY_RUN_THE_GENERATOR = ("cli/",)

    def _modules(self):
        for pkg in self.WALLED:
            yield from sorted((self.ROOT / pkg).rglob("*.py"))

    @staticmethod
    def _docstring_nodes(tree):
        """Every Constant that is a docstring.

        Excluded deliberately: several modules EXPLAIN in prose that
        they must not read the bookkeeping, and a rule that punished
        them for saying so would delete its own documentation.
        """
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None) or []
                first = body[0] if body else None
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                        and isinstance(first.value.value, str):
                    out.add(id(first.value))
        return out

    def test_no_pipeline_module_names_the_bookkeeping_artefact(self):
        offenders = []
        for path in self._modules():
            rel = str(path.relative_to(self.ROOT))
            if rel == self.DEFINES_THE_NAME:
                continue
            tree = ast.parse(path.read_text())
            docstrings = self._docstring_nodes(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and "generator_bookkeeping" in node.value and id(node) not in docstrings:
                    offenders.append(f"{rel}:{node.lineno}")
                if isinstance(node, ast.Attribute) and node.attr == "BOOKKEEPING_PATH":
                    offenders.append(f"{rel}:{node.lineno} (BOOKKEEPING_PATH)")
        assert offenders == [], (
            "the generator's bookkeeping is named inside a pipeline/QA/dashboard module - "
            "filing a supply from a declaration is exactly what criterion 7 forbids:\n  "
            + "\n  ".join(offenders))

    def test_the_bookkeeping_rule_is_checked_against_real_code(self):
        """The test above passes trivially if _modules() finds nothing,
        and a walled package getting renamed is exactly how that would
        happen quietly."""
        found = list(self._modules())
        assert len(found) > 50, f"only {len(found)} modules walked - the walled packages have moved"

    def test_no_pipeline_module_imports_the_generator_package(self):
        offenders = []
        for path in self._modules():
            rel = str(path.relative_to(self.ROOT))
            if rel.startswith(self.MAY_RUN_THE_GENERATOR):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                name = None
                if isinstance(node, ast.ImportFrom):
                    name = node.module or ""
                elif isinstance(node, ast.Import):
                    name = node.names[0].name
                if name and (name == "generator" or name.startswith("generator.")):
                    offenders.append(f"{rel}:{node.lineno} -> {name}")
        assert offenders == [], (
            "a pipeline/QA/dashboard module imports the generator:\n  " + "\n  ".join(offenders))


class TestNoCommittedResultCarriesBookkeeping:
    """The observational half, kept because the static rule above
    cannot see history that was written before it existed."""

    ROOT = Path(__file__).resolve().parent.parent
    FORBIDDEN = ("dirty_severity", "seed", "id_offset", "slot_id", "period",
                 "n_rows_generated", "manifest_entry", "attempt_number", "is_resupply",
                 "supersedes_run_id")

    def test_every_committed_dataset_stats_file_is_clean(self):
        found = []
        for path in sorted((self.ROOT / "qa_results").rglob("dataset_stats.json")):
            raw = path.read_text()
            for key in self.FORBIDDEN:
                if f'"{key}"' in raw:
                    found.append(f"{path.relative_to(self.ROOT)}: {key}")
        assert found == [], (
            "recorded QA history carries the generator's own bookkeeping:\n  " + "\n  ".join(found))
