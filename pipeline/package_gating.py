"""What a dataset page's verdict line says while its supply's gate is not yet
applied, or its gate application has not settled - REQ-DASH-272 criterion
21 - worked out at build time, as at every date, and looked up by the page.

THE FOUR FORMS, per supply and date, judged at the end of each day (the
page's date on show is a day, as cross_table_grid.clause_points judges it):

- an arrival of a package of more than one file whose own run is not yet
  recorded: 'Being checked with its delivery (received <instant>): <n> of
  <m> files checked. Nothing needs deciding yet.' - the page shows no pill
  and no check results for it;
- a checked arrival whose package-mates are not all checked: 'Checked,
  waiting for the rest of its delivery (received <instant>): <n> of <m>
  files checked. Nothing needs deciding yet.';
- a package every file of which is checked but whose 'gate' item is still
  owed, a package of one whose gate is owed, or a supply of a gate
  application not yet settled: 'Checked, being gated (received <instant>).
  Nothing needs deciding yet.';
- each adding, where a package-mate's run stopped and it is not yet checked,
  '<dataset>'s run stopped; the next processing pass re-runs it.'

ONLY FOR A REAL UNFINISHED GATE (Keith, 2026-10-29, open question 1 option
b): in a synthetic replay an application is stamped as started at the receipt
and settled at the receipt plus its seeded promotion lag, and its 'gate' item
owed and cleared at the same two instants - a person taking their time, not a
gate in progress - so the page reads 'Awaiting a decision' through it as it
always has. A package shows these forms only where the record shows its gate
genuinely did not finish when it should have (`_interrupted`):
- a run of one of its files ended other than COMPLETED - a crash, or a time
  budget stopping it part-way (qa.run_attempt);
- an application of it ended 'abandoned', or never ended - a crash mid-gate;
- its 'gate' item records an attempt - the gate found its period lock held
  (contended) and was left owed for a later pass (gate._found_contended);
- a file of it has no completed run at all as the build reads it - the pass
  stopped before it (a time budget, or a failed arrival holding it back).
The last is judged on the record as it stands: once that file has been
checked, the history keeps no mark that a pass stopped before it, so a
later build reads those days as the replay's would. REJECTED (a), building
criterion 21 as written, which read 'Checked, being gated' through every
seeded lag (Child Protection 248 supplies for 1,873 dataset-days on the
2026-10-28 history); and (c), stamping the replay's application at its
effective instant, which changes the recorded history.

FROM THE RECORD ONLY (criterion 21: "computed at build from the owed 'gate'
item, the packages' runs and qa.gate_application"): a package is the
supplies of one collection filed from one delivery at one receipt instant to
one period (qa.supply_receipt over qa.filing_current, the record gate.package_at
reads); a file is CHECKED from the completion of its own run (gate._checked's
rule, as at that instant); a run STOPPED where an attempt of it ended other
than COMPLETED (qa.run_attempt); the gate is OWED from a 'gate' item's owed_at
to its cleared_at (qa.owed_run); an application is OPEN from its started_at to
its ended_at (qa.gate_application), and a supply is OF it where the
application recorded a run or a decision about it, or it is a file of the
package the application gated. Recorded QA metadata and the decision log,
never a supply row.
"""
from __future__ import annotations

from datetime import datetime

from qa_tools.common import asset_time, decision_log, display_time, hierarchy, qa_store

UNCHECKED, WAITING, GATING = "unchecked", "waiting", "gating"

_LEADS = {UNCHECKED: "Being checked with its delivery",
          WAITING: "Checked, waiting for the rest of its delivery",
          GATING: "Checked, being gated"}

#: A decision after which a supply is no longer waiting for its gate: it is
#: in the warehouse, or has left. A demotion makes it wait again.
_SETTLES = {decision_log.PROMOTE: True, decision_log.REJECT: True,
            decision_log.SUPERSEDE: True, decision_log.DEMOTE: False}


def _instant(value) -> datetime:
    return asset_time.parse_instant(value if isinstance(value, datetime) else str(value),
                                    "package gating")


def _key(value) -> str:
    """One spelling of an instant, for grouping a package's files."""
    return _instant(value).isoformat()


def _text(words: str) -> dict:
    return {"text": words}


class _Package:
    def __init__(self, collection_id: str, period: str, delivery: str, received):
        self.collection_id, self.period = collection_id, period
        self.delivery, self.received = delivery, _instant(received)
        self.members: list[tuple[str, str]] = []


def _windows(rows) -> list[tuple[datetime, datetime | None]]:
    return [(_instant(a), _instant(b) if b is not None else None) for a, b in rows]


def _open(windows, when: datetime) -> bool:
    return any(a <= when and (b is None or when < b) for a, b in windows)


def for_collection(conn, collection_id: str) -> dict[str, dict[str, list[dict]]]:
    """{dataset id: {supply: [{on, form, lead, words, received}]}} for every
    supply of this collection that was ever being checked or gated with its
    delivery, as at the end of each day from its receipt until its gate
    settled - the last point's `form` None. A supply never in that state on
    any day's end has no entry."""
    s = qa_store.SCHEMA
    datasets = {d.dataset_id for d in hierarchy.datasets_in_collection(collection_id)}
    if not datasets:
        return {}
    ids = sorted(datasets)
    marks = ", ".join("?" * len(ids))

    packages: dict[tuple, _Package] = {}
    received_of: dict[str, datetime] = {}
    for ds, sup, delivery, received, period in conn.execute(
            f'SELECT rc.dataset_id, rc.supply_id, rc.delivery, rc.received_instant, f.slot '
            f'FROM "{s}".supply_receipt rc JOIN "{s}".filing_current f '
            "ON f.dataset_id = rc.dataset_id AND f.supply_id = rc.supply_id "
            f"WHERE rc.dataset_id IN ({marks}) AND f.slot IS NOT NULL "
            "AND rc.received_instant IS NOT NULL ORDER BY rc.dataset_id, rc.supply_id",
            ids).fetchall():
        key = (period, delivery, _key(received))
        pkg = packages.setdefault(key, _Package(collection_id, period, delivery, received))
        pkg.members.append((ds, sup))
        received_of[sup] = _instant(received)

    checked_at: dict[str, datetime] = {}
    for sup, at in conn.execute(
            f'SELECT supply_id, min(completed_at) FROM "{s}".run '
            f"WHERE dataset_id IN ({marks}) AND supply_id IS NOT NULL "
            "AND completed_at IS NOT NULL AND scope <> 'readers' AND NOT trial "
            "GROUP BY supply_id", ids).fetchall():
        checked_at[sup] = _instant(at)

    stopped_at: dict[str, list[datetime]] = {}
    for sup, at in conn.execute(
            f'SELECT r.supply_id, a.ended_at FROM "{s}".run_attempt a '
            f'JOIN "{s}".run r ON r.run_key = a.run_key '
            f"WHERE r.dataset_id IN ({marks}) AND r.supply_id IS NOT NULL "
            "AND r.scope <> 'readers' AND a.ended_at IS NOT NULL "
            "AND a.outcome <> 'COMPLETED'", ids).fetchall():
        stopped_at.setdefault(sup, []).append(_instant(at))

    owed: dict[tuple, list] = {}
    contended: set[tuple] = set()
    for period, delivery, instant, owed_at, cleared_at, attempts in conn.execute(
            f'SELECT o.period, o.delivery, o.package_instant, o.owed_at, o.cleared_at, '
            f'o.attempts FROM "{s}".owed_run o WHERE o.kind = \'gate\' '
            f"AND o.dataset_id IN ({marks}) AND o.package_instant IS NOT NULL",
            ids).fetchall():
        owed.setdefault((period, delivery, _key(instant)), []).append((owed_at, cleared_at))
        if attempts:
            contended.add((period, delivery, _key(instant)))

    applications: dict[int, tuple] = {}
    package_apps: dict[tuple, list[int]] = {}
    unsettled: dict[int, bool] = {}
    for app, period, started, ended, delivery, instant, how in conn.execute(
            f'SELECT id, period, started_at, ended_at, delivery, package_instant, ended '
            f'FROM "{s}".gate_application WHERE collection_id = ?', [collection_id]).fetchall():
        applications[app] = (_instant(started), _instant(ended) if ended is not None else None)
        unsettled[app] = how != "settled"
        if delivery is not None and instant is not None:
            package_apps.setdefault((period, delivery, _key(instant)), []).append(app)

    apps_of: dict[str, set[int]] = {}
    for sup, app in conn.execute(
            f'SELECT supply_id, gate_application FROM "{s}".run WHERE dataset_id IN ({marks}) '
            "AND supply_id IS NOT NULL AND gate_application IS NOT NULL "
            f'UNION SELECT supply, gate_application FROM {decision_log.TABLE} '
            f"WHERE dataset_id IN ({marks}) AND supply IS NOT NULL "
            "AND gate_application IS NOT NULL", ids + ids).fetchall():
        apps_of.setdefault(sup, set()).add(int(app))

    settles: dict[str, list[tuple[datetime, bool]]] = {}
    actions = list(_SETTLES)
    for sup, action, at in conn.execute(
            f"SELECT supply, action, effective_at FROM {decision_log.TABLE} "
            f"WHERE dataset_id IN ({marks}) AND supply IS NOT NULL "
            f"AND action IN ({', '.join('?' * len(actions))}) ORDER BY effective_at, id",
            ids + actions).fetchall():
        settles.setdefault(sup, []).append((_instant(at), _SETTLES[action]))

    zones = asset_time.timezone_versions()  # once (REQ-PIPE-254 criterion 19)
    out: dict[str, dict[str, list[dict]]] = {}
    for key, pkg in sorted(packages.items(), key=lambda kv: (kv[1].received, kv[0])):
        gate_owed = _windows(owed.get(key, ()))
        own_apps = set(package_apps.get(key, ()))
        if not _interrupted(pkg, checked_at, stopped_at, key in contended,
                            [unsettled.get(a) for a in sorted(own_apps)]):
            continue
        for ds, sup in pkg.members:
            # ITS OWN PACKAGE'S APPLICATIONS, AND ANY OTHER IT WAS PART OF.
            apps = own_apps | apps_of.get(sup, set())
            app_windows = [applications[a] for a in sorted(apps) if a in applications]
            if len(pkg.members) < 2 and not gate_owed and not app_windows:
                continue
            points = _points(ds, sup, pkg, gate_owed, app_windows, checked_at, stopped_at,
                             settles.get(sup, []), zones)
            if points:
                out.setdefault(ds, {})[sup] = points
    return out


def _interrupted(pkg, checked_at, stopped_at, contended: bool, unsettled) -> bool:
    """Whether the record shows this package's gate genuinely unfinished at
    some point - a stopped run, an unsettled application, a contended gate,
    or a file still unchecked (the module's docstring) - rather than only the
    replay's seeded lag."""
    supplies = [s for _d, s in pkg.members]
    return (contended or any(unsettled) or any(stopped_at.get(s) for s in supplies)
            or any(s not in checked_at for s in supplies))


def _settled_by(settles, when: datetime) -> bool:
    """Whether, by `when`, the supply is in the warehouse or has left."""
    done = False
    for at, settling in settles:
        if at <= when:
            done = settling
    return done


def _state(ds, sup, pkg, gate_owed, app_windows, checked_at, stopped_at, settles,
           when: datetime) -> dict | None:
    if when < pkg.received:
        return None
    m = len(pkg.members)
    checked = {s for _d, s in pkg.members if s in checked_at and checked_at[s] <= when}
    n = len(checked)
    own = sup in checked
    if _settled_by(settles, when):
        return None
    if m > 1 and not own:
        form = UNCHECKED
    elif m > 1 and n < m:
        form = WAITING
    elif _open(gate_owed, when) or _open(app_windows, when):
        form = GATING
    else:
        return None
    stopped = [d for d, s in pkg.members if s != sup and s not in checked
               and any(at <= when for at in stopped_at.get(s, ()))]
    return {"form": form, "n": n, "m": m, "stopped": sorted(set(stopped), key=_order)}


def _order(dataset_id: str) -> int:
    ids = [d.dataset_id for d in hierarchy.all_datasets()]
    return ids.index(dataset_id) if dataset_id in ids else len(ids)


def words(state: dict, received) -> tuple[str, list[dict]]:
    """The line's bold lead and the rest of it as segments - every dataset a
    segment the page renders as a link."""
    when = display_time.format_instant(received)
    form = state["form"]
    if form == GATING:
        rest = [_text(f" (received {when}). Nothing needs deciding yet.")]
    else:
        rest = [_text(f" (received {when}): {state['n']} of {state['m']} files checked. "
                      "Nothing needs deciding yet.")]
    for d in state["stopped"]:
        rest += [_text(" "), {"dataset": d},
                 _text("'s run stopped; the next processing pass re-runs it.")]
    return _LEADS[form], rest


def _points(ds, sup, pkg, gate_owed, app_windows, checked_at, stopped_at, settles,
            zones) -> list[dict]:
    """The state at the end of every day anything about it changed, from the
    receipt's day on, with a last point where it ends."""
    events = {pkg.received}
    for _d, s in pkg.members:
        if s in checked_at:
            events.add(checked_at[s])
        events.update(stopped_at.get(s, ()))
    for a, b in [*gate_owed, *app_windows]:
        events.add(a)
        if b is not None:
            events.add(b)
    events.update(at for at, _s in settles)
    days = sorted({asset_time.local_date(e, zones) for e in events
                   if e >= pkg.received})
    points: list[dict] = []
    for day in days:
        when = asset_time.end_of_day(day, zones)
        state = _state(ds, sup, pkg, gate_owed, app_windows, checked_at, stopped_at,
                       settles, when)
        if state is None:
            p = {"on": day.isoformat(), "form": None}
        else:
            lead, rest = words(state, pkg.received)
            p = {"on": day.isoformat(), "form": state["form"], "lead": lead, "words": rest,
                 "received": pkg.received.isoformat()}
        if not points and p["form"] is None:
            continue
        if points and {k: v for k, v in points[-1].items() if k != "on"} == \
                {k: v for k, v in p.items() if k != "on"}:
            continue
        points.append(p)
    return points

