"""The first arrival a change can affect is worked out from the inputs, never
chosen by hand (REQ-TEST-160, signed by Keith 2026-10-06), from one input list
shared with CI's bootstrap cache (REQ-TEST-117)."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

from qa_tools.common import replay_inputs as ri

ROOT = Path(__file__).resolve().parent.parent


def _tree(root: Path, deliveries: list[tuple[str, str, str, str]]) -> tuple[Path, Path]:
    """A delivery tree: (delivery, file, content, received_at) per file."""
    d, r = root / "deliveries", root / "receipts"
    for seq, (name, filename, content, received_at) in enumerate(deliveries, start=1):
        (d / name).mkdir(parents=True, exist_ok=True)
        (r / name).mkdir(parents=True, exist_ok=True)
        (d / name / filename).write_text(content)
        (r / name / f"{filename}.json").write_text(json.dumps({
            "delivery": name, "file": filename, "received_at": received_at,
            "received_from": "storage", "sequence": 1000 + seq, "filed_by": {"kind": "automated"}}))
    return d, r


HEADER = "client_id,given_name\n"
CP = [("Extract A", "cp_clients.csv", HEADER + "1,Ann\n", "2023-02-01T01:00:00+00:00"),
      ("Extract B", "cp_clients.csv", HEADER + "1,Ann\n2,Bo\n", "2023-05-01T01:00:00+00:00"),
      ("Extract C", "cp_clients.csv", HEADER + "1,Ann\n2,Bo\n3,Cy\n", "2023-08-01T01:00:00+00:00")]


def _print(tmp_path, rows):
    d, r = _tree(tmp_path, rows)
    return ri.deliveries_print("child-protection", d, r)


class TestOneInputList:
    """NFR: one input list shared with REQ-TEST-117, not a copy."""

    def test_the_list_is_criterion_1s(self):
        assert set(ri.INPUTS) == {"generator/**", "synthetic_data_generator/**", "pipeline/**",
                                  "qa_tools/**", "contract/**", "dbt_project/**", "cli/pipeline.py",
                                  "pyproject.toml", "uv.lock", ".github/workflows/test.yml"}

    def test_a_replay_compares_it_less_the_generators(self):
        files = ri.input_files(ri.REPLAY_INPUTS)
        assert files and not any(p.startswith(("generator/", "synthetic_data_generator/"))
                                 for p in files)
        assert "contract/data-asset.yaml" in files and "cli/pipeline.py" in files
        assert not any(p.startswith("cli/") and p != "cli/pipeline.py" for p in files)

    def test_ignored_files_are_not_inputs(self):
        """dbt deps installs dbt_packages/ under dbt_project/, and a key that
        moved with it would never hit."""
        assert not any("dbt_packages/" in p or "/target/" in p
                       for p in ri.input_files(("dbt_project/**",)))

    def test_ci_keys_its_cache_on_the_same_list(self):
        workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text()
        assert "mothman pipeline cache-key" in workflow
        assert "hashFiles(" not in workflow.split("Key the bootstrap cache", 1)[1].split("- name:", 1)[0]

    def test_the_key_never_touches_a_database(self, monkeypatch):
        """CI computes it before its database exists (tests/test_db_identity
        exempts it by name on the strength of this)."""
        from qa_tools.common import supply_db

        def refuse(*a, **k):
            raise AssertionError("cache_key connected to a database")
        monkeypatch.setattr(supply_db, "connect", refuse)
        monkeypatch.setattr("psycopg.connect", refuse)
        assert ri.cache_key().startswith(ri.KEY_PREFIX)

    def test_the_key_moves_with_any_input_and_not_otherwise(self, monkeypatch):
        files = {"qa_tools/a.py": "1", "contract/b.yaml": "2"}
        monkeypatch.setattr(ri, "input_files", lambda patterns=ri.INPUTS: dict(files))
        before = ri.cache_key()
        assert ri.cache_key() == before
        files["contract/b.yaml"] = "3"
        assert ri.cache_key() != before


class TestTheDeliveriesPrint:
    """Criterion 1."""

    def test_one_entry_per_arrival_in_receipt_order(self, tmp_path):
        p = _print(tmp_path, CP)
        assert [a.delivery for a in p] == ["Extract A", "Extract B", "Extract C"]

    def test_the_receipt_counter_is_not_part_of_it(self, tmp_path):
        """The generator's receipt sequence is a counter that moves on every
        regeneration of identical data - comparing it would make every resume
        a full replay."""
        a = _print(tmp_path / "a", CP)
        d, r = _tree(tmp_path / "b", CP)
        for f in r.rglob("*.json"):
            doc = json.loads(f.read_text())
            doc["sequence"] += 500
            f.write_text(json.dumps(doc))
        assert ri.deliveries_print("child-protection", d, r) == a

    def test_content_and_receipt_are_both_in_it(self, tmp_path):
        base = _print(tmp_path / "a", CP)
        changed = [CP[0], (CP[1][0], CP[1][1], CP[1][2] + "9,Zed\n", CP[1][3]), CP[2]]
        later = [CP[0], (CP[1][0], CP[1][1], CP[1][2], "2023-05-02T01:00:00+00:00"), CP[2]]
        assert _print(tmp_path / "b", changed)[1] != base[1]
        assert _print(tmp_path / "c", later)[1] != base[1]


class TestTheFirstAffectedArrival:
    """Criteria 2 to 5."""

    def _recorded(self, tmp_path, rows=CP):
        return ri.Recorded(collection_id="child-protection", arrivals=_print(tmp_path, rows),
                           inputs={"qa_tools/a.py": "x", "contract/b.yaml": "y"})

    def test_nothing_differs_is_nothing_to_replay(self, tmp_path):
        rec = self._recorded(tmp_path / "rec")
        got = ri.first_affected(rec, arrivals=_print(tmp_path / "now", CP), inputs=dict(rec.inputs))
        assert got.arrival is None and "nothing" in got.reason

    def test_a_changed_delivery_is_the_first_affected(self, tmp_path):
        rec = self._recorded(tmp_path / "rec")
        now = [CP[0], CP[1], (CP[2][0], CP[2][1], CP[2][2] + "4,Di\n", CP[2][3])]
        got = ri.first_affected(rec, arrivals=_print(tmp_path / "now", now), inputs=dict(rec.inputs))
        assert got.arrival == 3 and "Extract C" in got.reason

    def test_an_added_delivery_is_the_first_affected(self, tmp_path):
        rec = self._recorded(tmp_path / "rec", CP[:2])
        got = ri.first_affected(rec, arrivals=_print(tmp_path / "now", CP), inputs=dict(rec.inputs))
        assert got.arrival == 3

    def test_a_removed_delivery_is_the_first_affected(self, tmp_path):
        rec = self._recorded(tmp_path / "rec")
        got = ri.first_affected(rec, arrivals=_print(tmp_path / "now", [CP[0], CP[2]]),
                                inputs=dict(rec.inputs))
        assert got.arrival == 2 and "Extract B" in got.reason

    def test_a_delivery_is_affected_from_its_first_arrival(self, tmp_path):
        """A delivery's second file changed: the delivery's FIRST arrival is
        where its effect can begin."""
        two = [("Extract A", "cp_carers.csv", "carer_id\n1\n", "2023-02-01T01:00:00+00:00"),
               ("Extract A", "cp_clients.csv", HEADER + "1,Ann\n", "2023-02-01T01:05:00+00:00")]
        rec = self._recorded(tmp_path / "rec", two)
        now = [two[0], (two[1][0], two[1][1], two[1][2] + "2,Bo\n", two[1][3])]
        got = ri.first_affected(rec, arrivals=_print(tmp_path / "now", now), inputs=dict(rec.inputs))
        assert got.arrival == 1

    def test_any_other_input_restarts_the_collection_and_is_named(self, tmp_path):
        rec = self._recorded(tmp_path / "rec")
        inputs = dict(rec.inputs, **{"contract/b.yaml": "changed"})
        got = ri.first_affected(rec, arrivals=_print(tmp_path / "now", CP), inputs=inputs)
        assert got.arrival == 1 and "contract/b.yaml" in got.reason

    def test_an_added_or_removed_input_counts_too(self, tmp_path):
        rec = self._recorded(tmp_path / "rec")
        for inputs in ({"qa_tools/a.py": "x"}, dict(rec.inputs, **{"qa_tools/new.py": "z"})):
            got = ri.first_affected(rec, arrivals=_print(tmp_path / f"now{len(inputs)}", CP),
                                    inputs=inputs)
            assert got.arrival == 1

    def test_an_unreadable_record_resolves_to_the_first_arrival(self):
        """NFR FAILS SAFE: doubt resolves earlier, never later."""
        got = ri.first_affected(ri.Recorded.from_json({"collection_id": "child-protection"}),
                                arrivals=[], inputs={})
        assert got.arrival == 1 and "cannot" in got.reason

    def test_a_record_round_trips(self, tmp_path):
        rec = self._recorded(tmp_path)
        assert ri.Recorded.from_json(json.loads(json.dumps(rec.to_json()))) == rec

    def test_no_person_supplies_an_arrival_number(self):
        """Criterion 5: nothing in the API takes one."""
        for fn in (ri.first_affected,):
            params = set(inspect.signature(fn).parameters)
            assert not params & {"n", "arrival", "start", "from_arrival", "first"}


class TestRegeneratingToCompare:
    """Criterion 2: the deliveries are regenerated to compare, and nothing
    under data/ is touched in doing so."""

    def test_regenerating_matches_the_real_tree_and_leaves_it_alone(self, tmp_path):
        from qa_tools.common import delivery

        real = Path(delivery.DELIVERIES_DIR)
        before = sorted(p.name for p in real.iterdir()) if real.exists() else None
        regenerated = ri.regenerated_print("child-protection")
        after = sorted(p.name for p in real.iterdir()) if real.exists() else None
        assert after == before
        assert regenerated and all(a.content for a in regenerated)
        assert ri.regenerated_print("child-protection") == regenerated, "not deterministic"


class TestAnArrivalHoldingSeveralFiles:
    """post-build-review #131 D1: the print is one entry per FILE, and an
    arrival can hold several files for one dataset (the contested case), so
    counting entries as arrivals reported every later arrival too late - the
    one direction the fail-safe NFR forbids."""

    def _prints(self, second_content="b"):
        mk = ri.ArrivalPrint
        return [mk("r1", "d1", "clients.csv", "a1", "x"),
                mk("r1", "d1", "clients (2).csv", "a2", "x"),
                mk("r2", "d2", "clients.csv", second_content, "x")]

    def test_a_change_after_a_two_file_arrival_is_arrival_two(self):
        rec = ri.Recorded(collection_id="child-protection", arrivals=self._prints(),
                          inputs={"q.py": "1"})
        got = ri.first_affected(rec, arrivals=self._prints("changed"), inputs={"q.py": "1"})
        assert got.arrival == 2, got

    def test_a_changed_file_is_called_changed_not_removed(self):
        rec = ri.Recorded(collection_id="child-protection", arrivals=self._prints(),
                          inputs={"q.py": "1"})
        got = ri.first_affected(rec, arrivals=self._prints("changed"), inputs={"q.py": "1"})
        assert "was changed" in got.reason, got.reason
