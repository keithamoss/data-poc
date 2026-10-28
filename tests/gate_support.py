"""Child Protection scenarios driven through the REAL per-arrival lifecycle,
with each QA tool's evaluation stood in for (REQ-PIPE-266, 267, 270, 278).

WHAT IS REAL: delivery files written and recognised, staged, filed by the
real rule against the real quarterly calendar, the period overlay, the
orchestrator's own run step (open_run, the own-table guard, carried checks,
the held and could-not-run records, the left-out reconciliation, the
missing-check refusal), the gate and the decision log - every line between
an arrival landing and its promotion or hold-back.

WHAT IS STOOD IN FOR: the four tools' EVALUATION, and nothing else. Each
fake does what a real runner does around its tool - asks asked_for for the
run's scope, leaves out (and notes) every asked check over a table the run
cannot read, and records a verdict for the rest through write_qa_result,
which applies the run's scope and records what each cross-table result read
(qa.check_read). The verdict itself comes from a rule the scenario states -
"Clients v2 is red on its own data" - which is what lets a test state each
table's content as a fact rather than building rows that would fail a real
check. The rules the tests pin are the gate's, never the tools'.

Each test uses its own database (private_supply_dsn): the decision log is
append-only, so a period another test promoted into cannot be cleaned up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CP = "child-protection"
TABLES = ("cp_clients", "cp_notifications", "cp_investigations", "cp_placements",
          "cp_carers", "cp_case_workers")
DATASET = {t: "cp-" + t[3:].replace("_", "-") for t in TABLES}
TABLE_OF = {d: t for t, d in DATASET.items()}

#: The fixture's clean reference delivery, whose six files every scenario
#: delivers copies of (conftest.cp_raw_dir).
from fixture_ids import CP_REF_RUN_ID  # noqa: E402

TOOLS = ("dbt", "soda", "datacontract", "evidently")

#: The person a scenario's decisions are made by - a real entry of
#: contract/people.yaml, so the page names them.
REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"
#: A definition fingerprint no check has (REQ-QAC-176's scheme, a value
#: nobody's definition hashes to).
OLD_DEFINITION = "v1:" + "a" * 64


@dataclass
class Ctx:
    """What a verdict rule is asked about: one check, in one run, and the
    supply each table it reads was read as (by label where the scenario
    named it)."""
    run_id: str
    check_id: str
    dataset_id: str
    reads: tuple[str, ...]
    #: {table: label} for every table the run read - the scenario's labels
    #: ("C1", "N2") where it named the supply, else the supply id.
    read_as: dict[str, str]
    own_label: str | None

    @property
    def cross_table(self) -> bool:
        return bool(self.reads)


def declared_reads() -> dict[str, list[str]]:
    from qa_tools.common import promotion

    return promotion._declared_reads()


def checks_reading(table: str, declared_on: str) -> list[str]:
    """The cross-table checks declared on `declared_on`'s dataset that read
    `table`."""
    from qa_tools.common import check_id as cid

    out = []
    for check, tables in declared_reads().items():
        parsed = cid.try_parse(check)
        if parsed and parsed.dataset == declared_on and table in tables:
            out.append(check)
    return sorted(out)


@dataclass
class Scenario:
    """A Child Protection history, delivered and processed one arrival at a
    time through the real lifecycle."""
    root: Path
    raw_dir: Path
    #: (Ctx) -> 'pass' | 'warn' | 'fail'; default green.
    rules: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    #: (tool, run_id) -> raise: makes one run fail at one tool's stage.
    crash: set = field(default_factory=set)
    labels: dict[str, str] = field(default_factory=dict)
    processed: set[str] = field(default_factory=set)
    _n: int = 0

    @property
    def deliveries(self) -> Path:
        return self.root / "deliveries"

    @property
    def receipts(self) -> Path:
        return self.root / "receipts"

    # ---- delivering ---------------------------------------------------------

    def deliver(self, at, tables: dict[str, str], name: str | None = None) -> dict[str, str]:
        """Deliver files at `at` - one instant for a zip, or {table: instant}
        for staggered files of one delivery - each labelled ({table: "N2"}).
        Returns {label: supply id}."""
        from qa_tools.common import asset_time, delivery

        self._n += 1
        name = name or f"cp-scenario-{self._n:03d}"
        files, stamps = {}, {}
        for table in tables:
            text = (self.raw_dir / CP_REF_RUN_ID / f"{table}.csv").read_text()
            files[f"{table}.csv"] = text
            instant = at[table] if isinstance(at, dict) else at
            stamps[f"{table}.csv"] = _instant(instant)
        delivery.write_delivery(name, files, received_at=stamps,
                                deliveries_dir=self.deliveries, receipts_dir=self.receipts)
        out = {}
        for table, label in tables.items():
            supply = f"{DATASET[table]}@{asset_time.arrival_key(stamps[f'{table}.csv'])}"
            self.labels[supply] = label
            out[label] = supply
        return out

    def arrivals(self) -> list:
        from qa_tools.common import arrivals

        return arrivals.arrivals_for(CP, "cp_run_", self.deliveries, self.receipts)

    def process(self, *, stop_before: str | None = None) -> list:
        """Process every arrival not yet processed, in receipt order, through
        the real lifecycle - stopping before the arrival whose supply is
        labelled `stop_before`, as a pass that stops part-way does."""
        from qa_tools.common import arrival_lifecycle
        from qa_tools.tools import orchestrate, stage

        found = sorted(self.arrivals(), key=lambda a: (a.received_at, a.sequence, a.run_id))
        todo = []
        for a in found:
            if a.run_id in self.processed:
                continue
            if stop_before and self.label_of(a) == stop_before:
                break
            todo.append(a)
        if not todo:
            return []
        prepare = arrival_lifecycle.staged_as_it_arrives(stage.stager(CP))
        steps = orchestrate.steps(CP)
        out = []
        self.failures = []
        for a in todo:
            prepare(a, found)
            try:
                out.extend(arrival_lifecycle.process(
                    a, steps=steps, among=found, run_timestamp=_iso(a.received_at),
                    run_by="pytest@example.org"))
            except arrival_lifecycle.StageFailed as exc:
                # A FAILED ARRIVAL holds back the later ones, as the pass does.
                self.failures.append(exc)
                break
            self.processed.add(a.run_id)
        return out

    def run_owed(self, kinds=None):
        """Run what is owed, as the processing pass does after arrivals."""
        from qa_tools.common import recheck

        return recheck.run_all_owed(
            collection_id=CP, kinds=kinds or (recheck.REEVALUATE, recheck.RECHECK,
                                              recheck.GATE),
            run_by="pytest@example.org")

    def label_of(self, arrival) -> str | None:
        from qa_tools.common import asset_time

        (dataset_id,) = arrival.files_by_dataset
        return self.labels.get(f"{dataset_id}@{asset_time.arrival_key(arrival.received_at)}")

    # ---- the fixture contents ------------------------------------------------

    def promote_by_hand(self, supply: str, period: str, *, at=None,
                        follow_up: bool = False) -> None:
        """A person's promotion - how a fixture puts a supply in the warehouse
        whatever the gate made of it (REQ-PIPE-267 criterion 19). Through
        promotion.promote, the one move; `follow_up` then runs the knock-on
        as a person's decision at the terminal does."""
        from qa_tools.common import (asset_time, decision_log, hierarchy, knock_on,
                                     promotion, supply_db, supply_files)

        dataset_id = supply.split("@", 1)[0]
        ds = hierarchy.dataset(dataset_id)
        with supply_db.connect(label="pytest-fixture-promote") as conn:
            if decision_log.promoted_into(conn, dataset_id, period) != supply:
                promotion.promote(
                    conn, agency_id=ds.agency_id, collection_id=ds.collection_id,
                    dataset_id=dataset_id, supply=supply, period=period,
                    physical_tables=supply_files.tables_in(conn, dataset_id, supply,
                                                           supply_db.STAGING_SCHEMA),
                    actor="fixture@example.org", actor_kind=decision_log.PERSON,
                    effective_at=_iso(at) if at else asset_time.now().isoformat(),
                    reason="fixture: put in the warehouse", supply_is_red=True)
        if follow_up:
            knock_on.follow_up(CP, run_by="pytest@example.org")

    # ---- re-checks (REQ-PIPE-164, REQ-PIPE-177) ---------------------------------

    def recheck(self, supply: str, period: str, *, at, reason: str = "our check was wrong",
                person: str | None = None, run: bool = True):
        """A person's re-check of `supply` where it is filed, at `at`, through
        the one decision entry point - then, unless `run` is False, the
        owed re-check run as the processing pass runs it."""
        from qa_tools.common import filing_decisions as fd
        from qa_tools.common import people, supply_db

        with supply_db.connect(label="pytest-recheck") as conn:
            fd.apply(fd.Request(operation=fd.RECHECK, dataset_id=supply.split("@", 1)[0],
                                actor=people.person_by_email(person or REAL_PERSON),
                                reason=reason, confirmed=True, period=period, supply=supply),
                     effective_at=_iso(at), conn=conn)
        return self.run_owed() if run else []

    def judged_under_an_old_definition(self, check_id: str, supplies) -> None:
        """Every result of `check_id` about these supplies recorded under a
        definition the check no longer has - as if the check had since been
        corrected (REQ-QAC-176's fingerprint)."""
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(label="pytest-old-definition") as conn:
            conn.execute(
                f'UPDATE "{qa_store.SCHEMA}".check_result SET definition_fingerprint = ? '
                f'WHERE check_id = ? AND run_key IN (SELECT run_key FROM "{qa_store.SCHEMA}".run '
                "WHERE supply_id = ANY(?))", [OLD_DEFINITION, check_id, list(supplies)])

    def bulk_recheck(self, check_id: str, *, at, reason: str = "we corrected the check",
                     run: bool = True):
        """A bulk re-check of `check_id`, recorded as the terminal records it
        (the plan shown, then confirmed by its key), then run."""
        from qa_tools.common import bulk_recheck, people, supply_db

        with supply_db.connect(label="pytest-bulk-recheck") as conn:
            shown = bulk_recheck.plan(conn, check_id)
            got = bulk_recheck.record(conn, check_id, actor=people.person_by_email(REAL_PERSON),
                                      reason=reason, effective_at=_iso(at),
                                      acknowledged=shown.key, shown=shown)
        if run:
            self.run_owed()
        return got

    def acknowledge(self, supply: str, period: str, *, at, reason: str = "known, it stays"):
        from qa_tools.common import filing_decisions as fd
        from qa_tools.common import people, supply_db

        with supply_db.connect(label="pytest-acknowledge") as conn:
            fd.apply(fd.Request(operation=fd.ACKNOWLEDGE, dataset_id=supply.split("@", 1)[0],
                                actor=people.person_by_email(REAL_PERSON), reason=reason,
                                confirmed=True, period=period, supply=supply),
                     effective_at=_iso(at), conn=conn)

    # ---- reading back --------------------------------------------------------

    def decisions(self, supply: str) -> list[dict]:
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(read_only=True, label="pytest-scenario") as conn:
            cursor = conn.execute(
                f'SELECT * FROM "{qa_store.SCHEMA}".decision WHERE supply = ? ORDER BY id',
                [supply])
            return qa_store._dicts(cursor)

    def actions(self, supply: str) -> list[str]:
        return [d["action"] for d in self.decisions(supply)]

    def holder(self, dataset_id: str, period: str) -> str | None:
        from qa_tools.common import decision_log, supply_db

        with supply_db.connect(read_only=True, label="pytest-scenario") as conn:
            h = decision_log.held(conn, dataset_id, period)
        return h.holder if h and h.held_as else None

    def runs(self, supply: str) -> list[dict]:
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(read_only=True, label="pytest-scenario") as conn:
            return qa_store._dicts(conn.execute(
                f'SELECT * FROM "{qa_store.SCHEMA}".run WHERE supply_id = ? '
                "ORDER BY run_seq NULLS LAST", [supply]))

    def results(self, run_key: str) -> list[dict]:
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(read_only=True, label="pytest-scenario") as conn:
            return qa_store._dicts(conn.execute(
                f'SELECT * FROM "{qa_store.SCHEMA}".check_result WHERE run_key = ? '
                "ORDER BY id", [run_key]))

    def owed(self, kind: str | None = None) -> list:
        from qa_tools.common import recheck, supply_db

        with supply_db.connect(read_only=True, label="pytest-scenario") as conn:
            return [o for o in recheck.owed(conn) if kind is None or o.kind == kind]

    def verdict(self, ctx: Ctx) -> str:
        for rule in self.rules:
            got = rule(ctx)
            if got:
                return got
        return "pass"


def _instant(value) -> datetime:
    from qa_tools.common import asset_time

    return value if isinstance(value, datetime) else asset_time.parse_instant(value, "scenario")


def _iso(value) -> str:
    return _instant(value).isoformat()


def install_fake_tools(monkeypatch, scenario: Scenario) -> None:
    """Stand in for the four tools' evaluation - see the module docstring -
    and point every reader of the delivery tree at the scenario's own."""
    from qa_tools.common import delivery
    from qa_tools.tools import run_datacontract, run_dbt, run_evidently, run_soda

    monkeypatch.setattr(delivery, "DELIVERIES_DIR", scenario.deliveries)
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", scenario.receipts)
    monkeypatch.setattr(delivery, "BOOKKEEPING_PATH", scenario.root / "bookkeeping.json")

    for module, tool in ((run_dbt, "dbt"), (run_soda, "soda"),
                         (run_datacontract, "datacontract"), (run_evidently, "evidently")):
        monkeypatch.setattr(module, "evaluate", _fake(tool, scenario))


def _fake(tool: str, scenario: Scenario):
    def evaluate(collection_id: str, run_id: str, run_timestamp: str, **_kw) -> list[dict]:
        from qa_tools import collections
        from qa_tools.common import asked_for, hierarchy, left_out, supply_db
        from qa_tools.common import check_id as cid
        from qa_tools.common.qa_results_writer import write_qa_result

        coll = collections.by_id(collection_id)
        for crash_tool, prefix in list(scenario.crash):
            if crash_tool == tool and run_id.startswith(prefix):
                raise RuntimeError(f"{tool} crashed on {run_id} (scenario)")
        asked = asked_for.ask(run_id, run_timestamp, coll.agency_id, coll.id, tool)
        reads = declared_reads()
        with supply_db.connect(read_only=True, label="pytest-fake-tool") as conn:
            readable = supply_db.readable_in(conn, run_id)
            res = supply_db.resolution_for(conn, run_id)
        owner = supply_db.split_staged(run_id)
        read_as = {t: scenario.labels.get(s, s) for t, s in res.supply_of.items()}
        left, out = [], []
        for check in asked:
            parsed = cid.try_parse(check)
            if parsed is None:
                continue
            home = hierarchy.dataset(parsed.dataset).table
            needs = {home, *(reads.get(check) or ())}
            if not needs <= set(readable):
                left.append(check)
                continue
            own_label = read_as.get(home)
            status = scenario.verdict(Ctx(run_id=run_id, check_id=check,
                                          dataset_id=parsed.dataset,
                                          reads=tuple(reads.get(check) or ()),
                                          read_as=read_as, own_label=own_label))
            out.append({
                "agency_id": parsed.agency, "collection_id": parsed.collection,
                "dataset_id": parsed.dataset, "check_id": check,
                "check_name": parsed.check_name, "column_name": parsed.column,
                "dimension": "validity", "label": parsed.check_name, "run_id": run_id,
                "run_timestamp": run_timestamp, "status": status, "metric_value": 0.0,
                "unit": None, "warn_threshold": None, "fail_threshold": None,
                "row_count_total": None, "row_count_invalid": None,
                "on_fail_action": "flag", "engine": tool})
        del owner
        left_out.note(run_id, tool, left)
        write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, tool,
                        {"fake": tool}, verified=out)
        return out
    return evaluate


# ---- verdict rules -------------------------------------------------------------

def own_red(label: str):
    """The supply labelled `label` is red on its own data (one check)."""
    def rule(ctx: Ctx):
        if not ctx.cross_table and ctx.own_label == label and ctx.check_id.endswith("_dbt") \
                and ".unique_" not in ctx.check_id and _first_own(ctx):
            return "fail"
        return None
    return rule


def _first_own(ctx: Ctx) -> bool:
    """One own check per dataset - the first not-null dbt check it declares -
    so 'red on its own data' is one failing check, not every one."""
    from qa_tools.common import asked_for

    mine = [c for c in asked_for.collection_checks(CP, "dbt")
            if c.split(".")[3] == ctx.dataset_id and c not in declared_reads()
            and "not_null" in c]
    return bool(mine) and ctx.check_id == mine[0]


def cross_red(declared_on: str, table: str, *, when: dict[str, str]):
    """The checks declared on `declared_on` reading `table` fail where the
    run read each table in `when` as the labelled supply."""
    def rule(ctx: Ctx):
        if (ctx.cross_table and ctx.dataset_id == declared_on and table in ctx.reads
                and all(ctx.read_as.get(t) == lab for t, lab in when.items())):
            return "fail"
        return None
    return rule


def pin_replacement_setting(monkeypatch) -> None:
    """A GREEN RESUPPLY MAY REPLACE A PROMOTED ONE, pinned rather than read
    from configuration (REQ-PIPE-267 criterion 16), so a 'hold' setting can
    never make a green branch read as a deadlock."""
    from qa_tools.common import amber_setting, replacement_setting

    monkeypatch.setattr(replacement_setting, "resolve",
                        lambda dataset_id, at, **kw: amber_setting.Resolved(
                            value=replacement_setting.GREEN, level="test", version="test"))
