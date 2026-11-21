"""Scripted decisions checked and resolved against the pipeline's own rules
(REQ-GEN-135 criterion 13, REQ-GEN-196 criteria 7 and 12, REQ-GEN-200
criterion 8, REQ-GEN-201 criterion 3, REQ-GEN-207) - split from the reader,
scenarios/scripted_decisions.py, by REQ-GEN-386 criterion 4.

WHY HERE. A scripted decision is judged by the rules a person's decision is
held to - the filing decisions and the settlement rule - which are the real
pipeline's. scenarios/ may import only asset_model/, so the reader stays there
and these checks live in the bootstrap, which may import both and whose
decision player is their one caller at replay time; `mothman scenarios
validate` calls problems().
"""
from __future__ import annotations

from asset_model import assets as _assets
from scenarios.scripted_decisions import (CHAIN_MARK, CHAIN_OPERATIONS, CHOOSE_FILE, PERIOD,
                                          PERIOD_SCOPED_OPERATIONS, Script, label)


def answers_for(s: Script, filenames: list[str], period_at) -> list:
    """A scripted settlement's answers, each file's position resolved to its
    filename and each relative re-file to its period - THE ONE resolution
    (REQ-GEN-196 criterion 7), called by the replay with the pair's real
    files in receipt order and by validate with stand-ins. `period_at(n)`
    names the period `n` after the placement's. Raises ValueError, naming
    the fault, on a malformed outcome."""
    from qa_tools.common import settlement

    if len(s.files) != len(filenames):
        raise ValueError(f"it gives {len(s.files)} file outcome(s) and the pair has "
                         f"{len(filenames)} files - give exactly one per position, 1 and 2, "
                         f"in receipt order")
    out = []
    for position, (token, filename) in enumerate(zip(s.files, filenames), 1):
        outcome, _, rest = token.partition(":")
        if outcome not in settlement.OUTCOMES:
            raise ValueError(f"file {position}'s outcome {token!r} is not one of supply, "
                             f"reject, supersede or refile:+N")
        to = None
        if outcome == settlement.REFILE:
            try:
                offset = int(rest)
            except ValueError:
                raise ValueError(f"file {position}'s re-file {token!r} names no period - "
                                 f"write refile:+N, N periods after the placement's") from None
            if offset <= 0:
                raise ValueError(f"file {position}'s re-file {token!r} is not after the "
                                 f"placement's period - the pair's own period is 'supply'")
            to = period_at(offset)
            if to is None:
                raise ValueError(f"file {position}'s re-file {token!r} names a period the "
                                 f"dataset does not have")
        elif rest:
            raise ValueError(f"file {position}'s outcome {token!r} takes no period")
        out.append(settlement.Answer(filename, outcome, to))
    return out


def _settlement_problems(s: Script, where: str) -> list[str]:
    """REQ-GEN-196 criterion 12, from configuration alone: one outcome per
    position, each well formed, and a combination REQ-PIPE-193 criterion 4
    allows - judged by the settlement's own rule, on stand-in files."""
    from qa_tools.common import settlement

    if s.operation != CHOOSE_FILE:
        return ([f"{where}: `files:` is only for a settlement (choose-file)"]
                if s.files else [])
    try:
        answers = answers_for(s, ["file 1", "file 2"], lambda n: f"the period +{n}")
    except ValueError as exc:
        return [f"{where}: {exc}"]
    files = [settlement.PairFile(a.filename, None, "", False) for a in answers]
    broken = settlement.rule_broken(None, s.dataset_id, "the placement's period", files,
                                    answers)
    return [f"{where}: {broken}"] if broken else []


def problems(scripts: list[Script], *, registered: set[str],
             placement_of: dict[str, str] | None = None) -> list[str]:
    """Criterion 13, against configuration alone: every scenario registered,
    every decision a filing decision, every reason present."""
    from qa_tools.common import filing_decisions
    from asset_model import hierarchy

    out = []
    for i, s in enumerate(scripts, 1):
        where = f"{_assets.config_dir()}/synthetic/scripted_decisions.yaml decision {i} ({label(s) if s.scenario or s.period else '?'})"
        if s.period is not None:
            out += _chain_problems(s, where)
        elif s.scenario not in registered:
            out.append(f"{where}: scenario {s.scenario!r} is not in the register")
        if s.operation not in filing_decisions.OPERATIONS:
            out.append(f"{where}: {s.operation!r} is not a filing decision - one of "
                       f"{', '.join(filing_decisions.OPERATIONS)}")
        if s.period_from not in ("filed", "placement"):
            out.append(f"{where}: period_from must be filed or placement, not {s.period_from!r}")
        if not s.reason.strip():
            out.append(f"{where}: a scripted decision needs a reason, as a person's does")
        try:
            hierarchy.dataset(s.dataset_id)
        except hierarchy.UnknownDatasetError:
            out.append(f"{where}: no dataset {s.dataset_id!r} in {_assets.config_dir()}/data-asset.yaml")
        if s.period is None:
            out += _scope_problems(s, where)
            out += _settlement_problems(s, where)
        if s.at is not None and s.after_hours_given:
            out.append(f"{where}: give `at:` (with `day_offset:`) or `after_hours:`, not "
                       f"both - each says when it takes effect")
    # ONE NAME, ONE DECISION, PER PLACEMENT (REQ-GEN-201 criterion 3): a link
    # looks names up across every scenario sharing its placement, so one
    # name on two siblings' decisions names neither (Keith, 2026-10-13).
    # `placement_of` maps a scenario id to its placement's; absent, each
    # scenario is its own.
    group = placement_of or {}
    named: dict[tuple[str, str], int] = {}
    for i, s in enumerate(scripts, 1):
        if s.name is None:
            continue
        first = named.setdefault((group.get(s.scenario, s.scenario), s.name), i)
        if first != i:
            other = scripts[first - 1].scenario
            scope = (f"({s.scenario})" if other == s.scenario
                     else f"({other} and {s.scenario}, which share a placement)")
            out.append(f"{_assets.config_dir()}/synthetic/scripted_decisions.yaml decisions {first} and {i} "
                       f"{scope} are both named {s.name!r} - a name is unique within the "
                       f"scenarios sharing a placement; rename one")
    return out


def _chain_problems(s: Script, where: str) -> list[str]:
    """An ordinary chain's entry (REQ-GEN-207): a period, a supply in it,
    and a settlement - and nothing a scenario's entry needs."""
    out = []
    if s.scenario:
        out.append(f"{where}: names scenario {s.scenario!r} and `period:` - an entry is about "
                   f"a scenario or an ordinary chain's period, not both")
    if s.operation == CHAIN_MARK:
        if s.supply_index is not None:
            out.append(f"{where}: a mark-not-supplied entry names no supply - its period has "
                       f"none - drop `supply:`")
    elif s.supply_index is None:
        out.append(f"{where}: a chain entry needs `supply: <index>` - which of the period's "
                   f"supplies, in receipt order")
    if s.operation not in CHAIN_OPERATIONS and s.operation != CHAIN_MARK:
        out.append(f"{where}: an ordinary chain is settled by promote or reject, or an empty "
                   f"period marked not supplied, not {s.operation!r}")
    for field_name, is_set in (("scope", s.scope is not None),
                               ("to_period", s.to_period is not None),
                               ("period_from", s.period_from != "filed"),
                               ("names_supply", not s.names_supply),
                               ("at", s.at is not None), ("name", s.name is not None),
                               ("files", bool(s.files))):
        if is_set:
            out.append(f"{where}: `{field_name}:` means nothing on a chain entry - drop it")
    return out


def _scope_problems(s: Script, where: str) -> list[str]:
    """REQ-GEN-200 criterion 8, from configuration alone: what a script is
    about, and what a substitution stands on. Each names what to change."""
    out = []
    if s.scope not in (None, PERIOD):
        out.append(f"{where}: scope must be `period` or absent, not {s.scope!r}")
    period_scoped = s.scope == PERIOD
    if s.supply_index is None and not period_scoped:
        out.append(f"{where}: names neither a supply nor a period scope - give `supply: <index>` "
                   f"for a decision about one of the scenario's supplies, or `scope: period` for "
                   f"one about its period")
    if period_scoped and s.supply_index is not None:
        out.append(f"{where}: names both a supply and `scope: period` - a period-scoped decision "
                   f"is timed from the period's due instant; drop `supply:`")
    if period_scoped and s.operation not in PERIOD_SCOPED_OPERATIONS:
        out.append(f"{where}: {s.operation!r} cannot be period-scoped - only "
                   f"{', '.join(PERIOD_SCOPED_OPERATIONS)} are about a period with no supply; "
                   f"name the supply instead")
    if period_scoped and s.operation == "substitute" and s.stands_on is None:
        out.append(f"{where}: a substitution needs `stands_on:` - the period it stands on, as "
                   f"an offset (-1 the period before)")
    # A SUBSTITUTION IS ALWAYS ABOUT A PERIOD (post-build-review #168): one
    # scoped to a supply passed here and then lost its stands_on at play
    # time, so the replay asked for a substitution standing on nothing.
    if s.operation == "substitute" and not period_scoped:
        out.append(f"{where}: a substitution is about a period with no supply of its own - "
                   f"give `scope: period` and `stands_on:` (-1 the period before), not "
                   f"`supply:`")
    if s.after_hours < 0:
        out.append(f"{where}: `after_hours: {s.after_hours}` is before the instant it is timed "
                   f"from - a decision takes effect at or after it")
    if period_scoped:
        # FIELDS A PERIOD-SCOPED DECISION WOULD SILENTLY IGNORE: its period is
        # the placement's and it names no supply.
        for field_name, is_set in (("to_period", s.to_period is not None),
                                   ("period_from", s.period_from != "filed"),
                                   ("names_supply", not s.names_supply)):
            if is_set:
                out.append(f"{where}: `{field_name}:` means nothing on a period-scoped "
                           f"decision, whose period is the scenario's own - drop it")
    if s.stands_on is not None and s.operation != "substitute":
        out.append(f"{where}: `stands_on:` is only for a substitution, not {s.operation!r}")
    if s.stands_on is not None and s.stands_on >= 0:
        out.append(f"{where}: `stands_on: {s.stands_on}` is not before the period it fills - "
                   f"a substitution stands on an EARLIER period (-1 the period before)")
    return out
