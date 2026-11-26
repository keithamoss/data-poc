"""A one-off's RELEASE DECISION (REQ-PIPE-435): one decision for the whole
one-off - release or withhold - with its actor, instant and reason, appended
to a table of its own in the qa schema. Recorded only: nothing here moves,
copies or sends a one-off's data to anyone (criterion 9).

ITS OWN TABLE, NOT THE DECISION LOG (delivery-architect, v4 review): the
decision log is keyed to a dataset's slot and carries filing semantics, and a
release has neither. APPEND-ONLY BY TRIGGER, as qa.filing is, for every role
(criterion 3); the publisher role reads it through the qa schema's SELECT
grant (qa_store.ensure_publisher_role), so a page can carry every decision
(REQ-DASH-444). LAST WINS, ALL KEPT (criterion 6).

NEVER GITHUB (criterion 8, REQ-PIPE-446 criterion 14): the terminal only.
"""
from __future__ import annotations

from dataclasses import dataclass

TABLE = "qa.one_off_decision"
RELEASE, WITHHOLD = "release", "withhold"
DECISIONS = (RELEASE, WITHHOLD)

_DDL = f"""
CREATE SCHEMA IF NOT EXISTS qa;
CREATE TABLE IF NOT EXISTS {TABLE} (
    id          bigserial PRIMARY KEY,
    one_off_id  text NOT NULL,
    decision    text NOT NULL CHECK (decision IN ('release', 'withhold')),
    reason      text NOT NULL CHECK (length(btrim(reason)) > 0),
    actor_email text NOT NULL,
    actor_name  text NOT NULL,
    decided_at  timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION qa.one_off_decision_is_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'qa.one_off_decision is append-only: a % is not permitted. A changed '
        'decision is a new row, and the latest stands (REQ-PIPE-435)', TG_OP;
END $$;
DROP TRIGGER IF EXISTS one_off_decision_append_only ON {TABLE};
CREATE TRIGGER one_off_decision_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON {TABLE}
    FOR EACH STATEMENT EXECUTE FUNCTION qa.one_off_decision_is_append_only();
"""


class DecisionRefused(ValueError):
    """The decision cannot be recorded. Its message says why."""


@dataclass(frozen=True)
class Decision:
    decision: str
    reason: str
    actor_email: str
    actor_name: str
    decided_at: object


@dataclass(frozen=True)
class DatasetResult:
    dataset_id: str
    name: str
    result: str        # 'Pass', 'Warn', 'Fail', or 'Could not be checked'
    outcome: bool      # has a recorded outcome for its checks (criterion 1)


def ensure_table(conn) -> None:
    getattr(conn, "raw", conn).execute(_DDL)


def history(conn) -> list[Decision]:
    """Every decision, newest first; the first stands (criterion 6)."""
    raw = getattr(conn, "raw", conn)
    if raw.execute("SELECT to_regclass(%s)", [TABLE]).fetchone()[0] is None:
        return []
    rows = raw.execute(f"SELECT decision, reason, actor_email, actor_name, decided_at "
                       f"FROM {TABLE} ORDER BY decided_at DESC, id DESC").fetchall()
    return [Decision(*r) for r in rows]


def standing(conn) -> Decision | None:
    found = history(conn)
    return found[0] if found else None


def qa_summary(conn) -> list[DatasetResult]:
    """Each declared dataset's QA result from its completed runs - a
    could-not-load or could-not-check outcome counting as one (Keith
    2026-11-21, v6 Q4 (a)) - for the confirmation (criterion 10)."""
    from asset_model import hierarchy

    raw = getattr(conn, "raw", conn)
    out = []
    for ds in hierarchy.all_datasets():
        runs = raw.execute("SELECT count(*) FROM qa.run WHERE dataset_id = %s AND "
                           "completed_at IS NOT NULL", [ds.dataset_id]).fetchone()[0] \
            if raw.execute("SELECT to_regclass('qa.run')").fetchone()[0] else 0
        statuses = {s for (s,) in raw.execute(
            "SELECT DISTINCT c.status FROM qa.check_result c JOIN qa.run r USING (run_key) "
            "WHERE c.dataset_id = %s AND r.completed_at IS NOT NULL",
            [ds.dataset_id]).fetchall()} if runs else set()
        if statuses & {"fail", "error"}:
            result = "Fail"
        elif "warn" in statuses:
            result = "Warn"
        elif "pass" in statuses:
            result = "Pass"
        else:
            result = "Could not be checked"
        out.append(DatasetResult(ds.dataset_id, ds.dataset_name, result, bool(runs)))
    return out


def refusal(summary: list[DatasetResult]) -> str | None:
    """Criterion 1: offered only once every dataset has a recorded outcome."""
    waiting = [d.dataset_id for d in summary if not d.outcome]
    if waiting:
        return (f"not every dataset has a recorded outcome yet - {', '.join(waiting)} - so "
                f"there is nothing whole to decide on. Load the one-off first: "
                f"mothman one-off load --id <id> <package>.")
    return None


def record(conn, one_off_id: str, decision: str, reason: str, actor: dict) -> Decision:
    """Append one decision for the whole one-off (criteria 2, 5 and 6)."""
    if decision not in DECISIONS:
        raise DecisionRefused(f"{decision!r} is not a decision - release or withhold.")
    if not (reason or "").strip():
        raise DecisionRefused("a decision needs a reason, and none was given. Nothing was "
                              "recorded.")
    from qa_tools.common import people

    ensure_table(conn)
    raw = getattr(conn, "raw", conn)
    row = raw.execute(
        f"INSERT INTO {TABLE} (one_off_id, decision, reason, actor_email, actor_name) "
        f"VALUES (%s, %s, %s, %s, %s) RETURNING decision, reason, actor_email, actor_name, "
        f"decided_at", [one_off_id, decision, reason.strip(), actor["email"],
                        actor.get("name") or people.actor_name(actor)]).fetchone()
    return Decision(*row)


def words(d: Decision) -> str:
    from qa_tools.common import display_time

    verb = "Released" if d.decision == RELEASE else "Withheld"
    return f"{verb} by {d.actor_name}, {display_time.format_instant(d.decided_at)}: {d.reason}"
