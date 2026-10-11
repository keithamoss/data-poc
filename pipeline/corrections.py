"""What calendar corrections did to a dataset, for the dashboard
(REQ-DASH-172, consuming REQ-PIPE-168's recorded verdicts and REQ-PIPE-170's
confirmation).

THE CORRECTED VERDICT IS ALREADY THE PAGE'S (criterion 1): qa.filing_current
reads the newest verdict, so nothing here changes what a supply shows. This
carries what is one interaction away (NFR 1): the original verdict, the
correction that re-judged it and who approved it; a supply kept in place
against a correction's move, with the reason; and a correction still
awaiting the asset manager.

Keyed by the RUN that checked the supply, through slot_timeline's one
mapping from a supply to its run, as pipeline/excuses.py is - so each sits
on the row it describes.

RECORDED FACTS AND CONFIGURATION ONLY (criterion 6): qa.verdict,
qa.decision, qa.correction_applied and the declared corrections - never a
schema holding supply rows.
"""
from __future__ import annotations

import re

from qa_tools.common import supply_db

#: A keep's reason begins with the correction it was kept against - written
#: so by correction_apply.confirm, and the one place the reference travels.
_KEPT_UNDER = re.compile(r"under correction (\S+?):\s*(.*)\Z", re.S)


def _declared() -> dict[str, dict]:
    """{reference: {approver, date, reason}} from the configuration - empty
    where it cannot be read, so the page still builds and simply names no
    approver."""
    from qa_tools.common import correction_apply, correction_trial

    try:
        docs = correction_trial.working()
    except correction_trial.Unreadable:
        return {}
    return {p.reference: {"approver": p.approver, "date": p.date, "reason": p.reason}
            for p in correction_apply._declared(*docs)}


def _name(identity: str | None) -> str | None:
    from qa_tools.common import people

    return people.display_name(identity) if identity else None


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def for_dataset(dataset_id: str, conn: supply_db.SupplyConnection | None = None,
                declared: dict | None = None) -> dict:
    """{"rejudged": {run_id: [...]}, "kept": {run_id: [...]}, "awaiting": [...]}."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:corrections") as opened:
            return for_dataset(dataset_id, opened, declared)
    from pipeline import slot_timeline
    from qa_tools.common import correction_apply, decision_log, verdict

    import json

    declared = _declared() if declared is None else declared
    applied, kept_under, moved = {}, {}, []
    for reference, applied_at, actor, summary in conn.execute(
            f"SELECT change_reference, applied_at, actor, summary FROM "
            f"{correction_apply.APPLIED}").fetchall():
        applied[reference] = (applied_at, actor)
        # WHICH CORRECTION A KEEP WAS AGAINST, from the applied record that
        # lists it (delivery-critic on 172, #4) - never parsed back out of the
        # keep's prose, where a reference holding a colon or a space was
        # misread or lost.
        done = summary if isinstance(summary, dict) else json.loads(summary or "{}")
        for ds, _supply, _period, why, *rest in done.get("kept") or []:
            if rest:
                kept_under[rest[0]] = (reference, why)
        # A MOVED SUPPLY CARRIES THE SAME NOTE (Keith, 2026-10-11, (r)).
        for ds, supply, frm, to, old, new in done.get("moved_verdicts") or []:
            if ds == dataset_id:
                moved.append((reference, applied_at, actor, supply, frm, to, old, new))
    runs: dict[str, str | None] = {}

    def run_of(supply: str) -> str | None:
        if supply not in runs:
            runs[supply] = slot_timeline._run_for(conn, dataset_id, supply)
        return runs[supply]

    rejudged: dict[str, list[dict]] = {}
    rows = conn.execute(
        f"SELECT v.supply_id, w.classification, v.classification, v.correction_ref, "
        f"v.recorded_at FROM {verdict.TABLE} v JOIN {verdict.TABLE} w ON w.id = v.supersedes "
        "WHERE v.dataset_id = ? AND v.correction_ref IS NOT NULL ORDER BY v.id",
        [dataset_id]).fetchall()
    for supply, original, new, reference, recorded_at in rows:
        run_id = run_of(supply)
        if not run_id:
            continue
        when, actor = applied.get(reference, (recorded_at, None))
        rejudged.setdefault(run_id, []).append({
            "original": original, "new": new, "reference": reference,
            "approver": _name((declared.get(reference) or {}).get("approver")),
            "appliedAt": _iso(when), "confirmedBy": _name(actor)})

    for reference, when, actor, supply, frm, to, old, new in moved:
        run_id = run_of(supply)
        if not run_id:
            continue
        rejudged.setdefault(run_id, []).append({
            "original": old, "new": new, "reference": reference,
            "approver": _name((declared.get(reference) or {}).get("approver")),
            "appliedAt": _iso(when), "confirmedBy": _name(actor),
            "movedFrom": frm, "movedTo": to})

    kept: dict[str, list[dict]] = {}
    kept_held: list[dict] = []
    for decision_id, supply, to_slot, from_slot, reason, actor, at in conn.execute(
            f"SELECT id, supply, to_slot, from_slot, reason, actor, effective_at FROM "
            f"{decision_log.TABLE} WHERE dataset_id = ? AND action = ? ORDER BY id",
            [dataset_id, decision_log.KEEP]).fetchall():
        reference, why = kept_under.get(decision_id, (None, None))
        if reference is None:
            found = _KEPT_UNDER.search(reason or "")
            reference, why = ((found.group(1), found.group(2).strip()) if found
                              else (None, reason or ""))
        entry = {"supply": supply, "reference": reference, "reason": why,
                 "period": to_slot, "keptOutOf": from_slot if not to_slot else None,
                 "actor": _name(actor), "at": _iso(at)}
        run_id = run_of(supply)
        if run_id:
            kept.setdefault(run_id, []).append(entry)
        else:
            # A SUPPLY KEPT HELD HAS NO RUN, and so no history row (delivery-
            # critic on 172, #2) - said on its dataset instead.
            kept_held.append(entry)

    awaiting, unknown = [], False
    try:
        docs = correction_trial_docs()
        for p in correction_apply.pending(conn, docs):
            if dataset_id in correction_apply.affected_datasets(p, docs[0]):
                awaiting.append({"reference": p.reference, "date": p.date, "reason": p.reason})
    except Exception as exc:  # noqa: BLE001 - said, never an all-clear (delivery-critic on 172, #6)
        print(f"note: could not work out the corrections awaiting {dataset_id} "
              f"({type(exc).__name__}: {exc}) - its page says so.")
        awaiting, unknown = [], True
    return {"rejudged": rejudged, "kept": kept, "keptHeld": kept_held, "awaiting": awaiting,
            "awaitingUnknown": unknown}


def correction_trial_docs():
    from qa_tools.common import correction_trial

    return correction_trial.working()


def applied_feed(conn: supply_db.SupplyConnection | None = None) -> list[dict]:
    """Each applied correction ONCE, asset-wide, for the activity panel
    (criterion 8): who confirmed it, when, and what it did."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:corrections") as opened:
            return applied_feed(opened)
    import json

    from qa_tools.common import correction_apply

    declared = _declared()
    out = []
    for reference, owner, actor, applied_at, summary in conn.execute(
            f"SELECT change_reference, owner, actor, applied_at, summary FROM "
            f"{correction_apply.APPLIED} ORDER BY applied_at").fetchall():
        done = summary if isinstance(summary, dict) else json.loads(summary or "{}")
        out.append({
            "kind": "correction", "reference": reference, "owner": owner,
            "label": f"Calendar correction {reference}",
            "run_by": _name(actor), "published_at": _iso(applied_at),
            "approver": _name((declared.get(reference) or {}).get("approver")),
            "reason": (declared.get(reference) or {}).get("reason"),
            "moved": len(done.get("moved") or []) + len(done.get("placed") or []),
            "held": len(done.get("held") or []), "kept": len(done.get("kept") or []),
            "rejudged": len(done.get("rejudged") or [])})
    return out
