"""What a held supply costs the checks that read it (REQ-PIPE-078
criterion 10).

THE BLAST RADIUS IS SCOPED, NOT ZERO, and both halves of that are
decisions rather than consequences. Every other dataset in the same
delivery is processed exactly as usual - one dataset nobody could place
must not cost the other twenty-nine their QA, which is the blast-radius
rule this whole area applies. But a cross-table check reading the held
table is NOT fine, and reporting it green or silent would be the
dangerous direction: `cp_clients` alone is read by referential checks on
`cp_notifications`, `cp_investigations` and `cp_placements`, so holding
one table genuinely changes what three others can be said to have
verified.

WHY A SYNTHESISED RESULT RATHER THAN LETTING THE TOOL FAIL. Withholding
the view (REQ-PIPE-078 criterion 9, in `supply_db.create_run_views`)
makes the table unreadable, and each tool then does its own thing about
that: dbt SKIPS the test, which produces no result at all. A check that
silently does not appear is indistinguishable from a check that passed,
to every reader downstream - the dashboard, the promotion gate, the
tickets. Criterion 10 asks for RED, and it asks for the held table to be
NAMED, because "this check did not run" sends somebody looking for a
broken check rather than for the supply nobody has placed.

IT IS NOT A VERDICT ON ANYBODY'S DATA, and the text says so. The check
did not fail; it could not be evaluated, and the honest report of that
is red with the reason attached. Same distinction `outstanding.py`
draws between event severity and data-quality status, applied to the one
place where they have to share a field.

WHAT IT DELIBERATELY DOES NOT DO: emit a result for a check belonging to
the HELD dataset itself. That is criterion 9's other half - no check
result is recorded against a supply with no period - so those checks
produce nothing, and the hold itself is what the queue shows.
"""
from __future__ import annotations

from qa_tools.common import check_id as check_id_mod

#: A check that could not be evaluated reads RED. Not "error" and not a
#: fourth status: the promotion gate treats anything that is not green
#: or amber as a supply waiting for a person, which is exactly right
#: here, and inventing a status for this case would mean teaching every
#: reader about it.
STATUS = "fail"

#: What the check's own dimension says when the check never ran. The
#: check's real dimension describes what it WOULD have measured, and
#: carrying it here would put a completeness verdict on a completeness
#: check that produced no measurement.
DIMENSION = "completeness"

LABEL = "Not evaluated - a table it reads is held"


def _reason(logical: str, physical: str | None) -> str:
    which = f" ({physical})" if physical else ""
    return (f"{logical}{which} is held: a supply for it arrived and nobody has "
            f"said which period it belongs to, so it was not staged into this "
            f"run and nothing could be checked against it. This check did not "
            f"fail - it could not be evaluated. Resolving the hold is what "
            f"makes it answerable again.")


def results_for(*, held: dict[str, str], reads: dict[str, list[str]],
                 run_id: str, run_timestamp: str,
                 checks_by_id: dict | None = None) -> list[dict]:
    """One red result per check that reads a held table, naming every held
    table it reads (REQ-PIPE-115 criterion 2 as amended 2026-10-05).

    `held` is `Resolution.held` - logical table -> the physical table
    being withheld. `reads` is what
    `tables_read.declared_by_check_id()` returns.

    ONE PER CHECK, NAMING EVERY HELD TABLE. It was one per (check, held
    table) so a check reading two held tables named both - but that is
    two results for one check in one run. `held_tables` and the reason
    name them all; `column_name` carries the first, the field the
    dashboard renders as "what this is about".

    A CHECK BELONGING TO THE HELD DATASET ITSELF IS SKIPPED. Its
    supply has no period, and criterion 9 forbids recording a check
    result against one.
    """
    if not held or not reads:
        return []
    checks_by_id = checks_by_id or {}
    out: list[dict] = []
    for check, tables in sorted(reads.items()):
        parsed = check_id_mod.try_parse(check)
        if parsed is None:
            # A declaration whose id does not parse is a configuration
            # fault the lifecycle gate reports; it must not stop a run.
            continue
        own_table = _table_of(parsed.dataset)
        if own_table is not None and own_table in held:
            continue
        blocked = sorted(set(tables) & set(held))
        if blocked:
            logical = blocked[0]
            meta = checks_by_id.get(check)
            out.append({
                "agency_id": parsed.agency,
                "collection_id": parsed.collection,
                "dataset_id": parsed.dataset,
                "check_id": check,
                "check_name": getattr(meta, "name", None) or parsed.check_name,
                "column_name": logical,
                "dimension": DIMENSION,
                "label": LABEL,
                "run_id": run_id,
                "run_timestamp": run_timestamp,
                "status": STATUS,
                "metric_value": None,
                "unit": None,
                "warn_threshold": None,
                "fail_threshold": None,
                "row_count_total": None,
                "row_count_invalid": None,
                "on_fail_action": "flag",
                "engine": getattr(meta, "tool", None) or parsed.tool,
                "held_table": logical,
                # ONE RECORD NAMING EVERY HELD TABLE (REQ-PIPE-115
                # criterion 2 as amended 2026-10-05, Keith): a check keeps
                # one result per run, and still names all it was blocked by.
                "held_tables": blocked,
                "held_reason": " ".join(_reason(t, held.get(t) or None) for t in blocked),
            })
    return out


def _table_of(dataset_id: str) -> str | None:
    from qa_tools.common import hierarchy

    try:
        return hierarchy.dataset(dataset_id).table
    except Exception:
        return None


def describe(results) -> str:
    """One line for the terminal, never one per result.

    Same reason the holds themselves aggregate: at ~30 datasets a
    referential check each is how a real message becomes wallpaper.
    """
    reddened = [r for r in results if r.get("held_table")]
    if not reddened:
        return ""
    tables = sorted({r["held_table"] for r in reddened})
    return (f"{len(reddened)} check(s) could not be evaluated because "
            f"{len(tables)} held table(s) were not staged into this run - "
            f"{', '.join(tables)}. They read red naming the held table; none "
            f"of them is a verdict on anybody's data.")


#: The pseudo-tool these are recorded under, alongside `dataset_stats`
#: and `tables_read`. DELIBERATELY NOT IN `EXPECTED_TOOLS`: a run with
#: nothing held writes nothing here, and a completeness rule demanding
#: it would make every clean run incomplete.
TOOL = "held"
