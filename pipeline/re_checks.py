"""What the dashboard says about a supply re-checked after we fixed a check -
REQ-DASH-221 - worked out at build time and looked up by the page.

A RE-CHECK (REQ-PIPE-164) is a person's decision that runs a supply's QA
again where it is filed; a BULK RE-CHECK (REQ-PIPE-177) is one such decision
per supply a corrected check judged under its old definition, each naming the
check and its changelog entry. Neither moves a supply. What the page needs
about each is:

- who, when and why - the decision's person and reason, the run's instant
  (when the new verdict exists: the as-of rule every other decision follows,
  so a re-check never changes what an earlier date shows);
- the supply's verdict just before that run and just after it, and, for a
  bulk re-check, whether results of OTHER checks changed in the same run
  ('and other checks');
- per bulk re-check, one line for the corrected check's drawer: how many
  supplies across how many datasets, the date, the person, the reason, and
  which of its supplies changed, each with the instant it did.

A TRIAL (REQ-PIPE-178) records no decision and its runs are marked trial, so
nothing here ever sees one (criterion 11).

ONE FUNCTION FOR THE VERDICT (REQ-PIPE-121 NFR 4): before and after are
supply_status.latest_results as at the instant - the newest counted result
per check, recorded by then, in the warehouse as the decision log had it
then - read for display (promotion.status_of, for_gate=False), as
pipeline.red_promoted reads a promoted supply's steps. RECORDED QA RESULTS
AND THE DECISION LOG ONLY, never a supply row (criterion 13).
"""
from __future__ import annotations

from datetime import timedelta

from qa_tools.common import decision_log, qa_store


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _person(actor: str | None) -> str:
    """A person by display name - 'a person' where only an address is known,
    as every other line on the page names one (REQ-PIPE-147 criterion 7)."""
    from qa_tools.common import people

    shown = people.display_name(actor) if actor else ""
    return "a person" if not shown or "@" in shown else shown


class Rechecks:
    """A collection's re-checks, as the page reads them."""

    def __init__(self):
        #: {supply: [event]}, oldest first - see for_collection.
        self.by_supply: dict[str, list[dict]] = {}
        #: {check id: [line]} - one per bulk re-check of that check.
        self.lines: dict[str, list[dict]] = {}
        #: {supply: [acknowledgement]} for each supply re-checked.
        self.acks: dict[str, list[dict]] = {}

    def for_dataset(self, dataset_id: str, check_ids) -> dict:
        prefix = dataset_id + "@"
        supplies = {s: e for s, e in self.by_supply.items() if s.startswith(prefix)}
        lines = {c: self.lines[c] for c in sorted(set(check_ids)) if c in self.lines}
        acks = {s: a for s, a in self.acks.items() if s in supplies and a}
        return {"supplies": supplies, "lines": lines, "acks": acks} \
            if supplies or lines else {}


def for_collection(conn, collection_id: str) -> Rechecks:
    """Every re-check recorded in this collection that has RUN, with the
    verdicts either side of it; and one line per bulk re-check."""
    from qa_tools.common import promotion, supply_status

    out = Rechecks()
    s = qa_store.SCHEMA
    decisions = conn.execute(
        f"SELECT id, dataset_id, supply, actor, reason, effective_at, bulk_recheck, check_id, "
        f"check_changelog_date FROM {decision_log.TABLE} WHERE collection_id = ? AND action = ? "
        "AND supply IS NOT NULL ORDER BY effective_at, id",
        [collection_id, decision_log.RECHECK]).fetchall()
    if not decisions:
        return out
    by_id = {d[0]: d for d in decisions}
    runs = conn.execute(
        f'SELECT run_key, caused_by_decision, run_instant FROM "{s}".run_visible '
        "WHERE caused_by_decision = ANY(?) AND completed_at IS NOT NULL AND NOT trial "
        "AND scope <> 'readers' ORDER BY run_seq", [sorted(by_id)]).fetchall()
    reads = promotion._declared_reads()

    def verdict(dataset_id, supply, at):
        newest = supply_status.latest_results(conn, dataset_id, supply,
                                              view=supply_status.View(as_at=at))
        try:
            status = promotion.status_of(dataset_id, newest, reads=reads, for_gate=False)
        except promotion.UnreadableVerdictError:
            status = None
        return status, {r["check_id"]: r.get("status") for r in newest}

    bulk_changes: dict[int, list[str]] = {}
    seen: set[int] = set()
    for run_key, decision_id, run_at in runs:
        # ONE RUN PER DECISION: a re-check retried after a run that broke is
        # still one re-check, its verdict the completed run's.
        if decision_id in seen:
            continue
        seen.add(decision_id)
        (_id, dataset_id, supply, actor, reason, _at, bulk, check_id, changelog_date) = \
            by_id[decision_id]
        before, before_checks = verdict(dataset_id, supply, run_at - timedelta(microseconds=1))
        after, after_checks = verdict(dataset_id, supply, run_at)
        changed = sorted(c for c in set(before_checks) | set(after_checks)
                         if before_checks.get(c) != after_checks.get(c))
        event = {"at": _iso(run_at), "decisionId": int(decision_id), "person": _person(actor),
                 "reason": reason or "", "before": before, "after": after}
        if bulk is not None:
            event["bulk"] = {"id": int(bulk), "checkId": check_id,
                             "changelogDate": changelog_date and str(changelog_date)[:10],
                             "others": any(c != check_id for c in changed)}
            if before != after:
                bulk_changes.setdefault(int(bulk), []).append(_iso(run_at))
        out.by_supply.setdefault(supply, []).append(event)

    bulks = sorted({d[6] for d in decisions if d[6] is not None})
    if bulks:
        datasets: dict[int, set[str]] = {}
        for d in decisions:
            if d[6] is not None:
                datasets.setdefault(int(d[6]), set()).add(d[1])
        for bid, check_id, raised_at, reason, actor, supplies, changelog_date in conn.execute(
                f'SELECT id, check_id, raised_at, reason, actor, supplies, changelog_date '
                f'FROM "{s}".bulk_recheck WHERE id = ANY(?) ORDER BY raised_at, id',
                [bulks]).fetchall():
            out.lines.setdefault(check_id, []).append({
                "id": int(bid), "at": _iso(raised_at), "person": _person(actor),
                "reason": reason or "", "supplies": int(supplies),
                "datasets": len(datasets.get(int(bid), ())),
                "changelogDate": changelog_date and str(changelog_date)[:10],
                "changes": sorted(bulk_changes.get(int(bid), []))})

    # WHO ACKNOWLEDGED A SUPPLY RE-CHECKED WORSE (criterion 8: the badge stays
    # after acknowledgement, naming who) - every acknowledgement of each
    # re-checked supply, with its withdrawal, as the acknowledgement badge
    # reads them.
    if out.by_supply:
        from pipeline.closed_slots import withdrawals
        from qa_tools.common import people

        withdrawn_by_ds: dict[str, dict] = {}
        for ack_id, dataset_id, supply, actor, reason, at in conn.execute(
                f"SELECT id, dataset_id, supply, actor, reason, effective_at "
                f"FROM {decision_log.TABLE} WHERE collection_id = ? AND action = ? "
                "AND supply = ANY(?) ORDER BY effective_at, id",
                [collection_id, decision_log.ACKNOWLEDGE, sorted(out.by_supply)]).fetchall():
            if dataset_id not in withdrawn_by_ds:
                withdrawn_by_ds[dataset_id] = withdrawals(conn, dataset_id)
            out.acks.setdefault(supply, []).append({
                "actor": people.display_name(actor), "reason": reason or "", "at": _iso(at),
                "withdrawn": withdrawn_by_ds[dataset_id].get(ack_id)})
    return out
