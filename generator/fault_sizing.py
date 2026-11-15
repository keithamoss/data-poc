"""How many faulty rows a preset plants, worked out from the bands of the
checks each fault aims at (REQ-GEN-392).

WHY. generator/dirty.py's presets once carried literal per-row rates, each
calibrated by hand to a band written in a comment beside it. A band edited
in a check file then left the rate behind, and a "red" supply could quietly
land amber. Keith chose to DERIVE the sizes at generation time instead (Q5 of
2026-11-14, option (b)): each fault names the rules it aims at, by
check_bands' rule key (generator/targeting.rule_key), and its size is read
from those rules' warn and fail bands at the frame's own row count, every
tool's unit and operator honoured as check_bands' amber intersection already
does - so a band moved in a check file moves the fault with it.

THE RULES (each Keith's, 2026-11-14):

- A WARN fault sits at the MIDDLE of the aimed rules' amber intersection, in
  rows, rounded down - targeting._target's rule (392 Q1).
- A FAIL fault sits at the lowest failing count PLUS the width of the rule's
  amber band (392 Q2): it scales with how wide the rule's tolerance is.
- A SINGLE-TIER rule (any violation fails, no amber band) gets NOTHING from a
  Warn preset, as REQ-GEN-184 already does, and a fixed FAIL_ROWS from a Fail
  one (392 Q3 (i)). FAIL_ROWS is a chosen number, not a band: it only sets how
  many failing rows the page shows.
- No size that lands somewhere other than asked is ever planted: an empty
  band intersection, or a band the frame's row count cannot reach, is refused
  (criterion 7), naming the preset, the fault, the rules and their bands.

WHAT A COUNT MEANS. For a rule on bad rows (counted or as a percentage) the
size is that many faulty rows. For a cross-supply drop rule - the only
continuous measure a preset aims at today - the metric is the proportion
removed against the previous supply, so the size is the number of rows to
remove from `rows`, the previous supply's count.

PROVISIONAL (overnight 2026-11-16): "the lowest failing count" is the
smallest count at which ANY check of the rule fails - the rule's own verdict,
as targeting._first reads it - and "the width of the amber band" is the
number of counts in the rule's first amber range (hi - lo + 1). Where a fault
aims at several rules, a Fail takes the largest of their sizes and is then
verified against every one; a Warn plants nothing when any aimed rule is
single-tier, since anything planted would fail it.
"""
from __future__ import annotations

#: Q3 (i), Keith 2026-11-14: what a Fail preset plants on a single-tier rule.
#: A CHOSEN NUMBER, not read from any band - it only sets how many failing
#: rows the page shows.
FAIL_ROWS = 5

WARN, FAIL = "amber", "red"


class FaultSizeError(ValueError):
    """No size lands a fault on the verdict asked on every rule it aims at.
    Loud by design: a supply aimed at Fail that lands Warn is worse than no
    supply (REQ-GEN-044 criterion 4)."""


def catalogue():
    """The catalogue of every check's bands, read through check_bands as
    Linkage Products reads it - once per generation by the caller, never per
    frame (the NFR)."""
    from asset_model import check_bands

    return check_bands.catalogue()


def _continuous(rule) -> bool:
    return rule.measure not in ("rows",)


def _metric(rule, x: int, rows: int) -> float:
    """The value `rule`'s checks compare against when `x` rows are faulty -
    the proportion removed for a drop rule, the count otherwise."""
    return (x / rows if rows else 0.0) if _continuous(rule) else x


def _fails(rule, x: int, rows: int) -> bool:
    m = _metric(rule, x, rows)
    return any(c.fails(m, rows) for c in rule.checks)


def _warns(rule, x: int, rows: int) -> bool:
    m = _metric(rule, x, rows)
    return any(c.warns(m, rows) for c in rule.checks)


def _ranges(ok) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for x, good in ok:
        if not good:
            continue
        if out and out[-1][1] == x - 1:
            out[-1] = (out[-1][0], x)
        else:
            out.append((x, x))
    return out


def _amber(rules, rows: int) -> list[tuple[int, int]]:
    """The counts, 1..rows, at which no aimed rule fails and every one warns."""
    return _ranges((x, not any(_fails(r, x, rows) for r in rules)
                    and all(_warns(r, x, rows) for r in rules)) for x in range(1, rows + 1))


def single_tier(rule, rows: int) -> bool:
    """A single faulty row fails the rule: no amber band below its first
    failure."""
    return rows > 0 and _fails(rule, 1, rows)


def _first_fail(rule, rows: int) -> int | None:
    return next((x for x in range(1, rows + 1) if _fails(rule, x, rows)), None)


def bands_text(rule) -> str:
    return "; ".join(f"{c.tool} warn {', '.join(b.text() for b in c.warn) or '-'} "
                     f"fail {', '.join(b.text() for b in c.fail) or '-'}" for c in rule.checks)


def rules_for(cat, dataset_id: str, keys, where: str) -> list:
    from generator.targeting import rule_key

    by_key = {rule_key(r): r for r in cat.rules() if r.dataset_id == dataset_id}
    missing = [k for k in keys if k not in by_key]
    if missing:
        raise FaultSizeError(f"{where}: aims at {missing} on {dataset_id}, and no check of it "
                             f"is in force under that rule key - nothing was planted")
    return [by_key[k] for k in keys]


def size(cat, dataset_id: str, keys, severity: str, rows: int, where: str) -> int:
    """How many rows the fault plants (or, for a drop rule, removes) to land
    `severity` - 'amber' or 'red' - on every rule in `keys`, at `rows` rows.
    Refused, never shifted, where no size lands it (criterion 7)."""
    if severity not in (WARN, FAIL):
        raise FaultSizeError(f"{where}: a preset is amber or red, not {severity!r}")
    rules = rules_for(cat, dataset_id, keys, where)

    def refuse(why: str):
        detail = " | ".join(f"{k}: {bands_text(r)}" for k, r in zip(keys, rules))
        return FaultSizeError(f"{where}: {severity} on {list(keys)} cannot be planted at {rows} "
                              f"rows - {why} ({detail}); nothing was planted")

    if severity == WARN:
        if any(single_tier(r, rows) for r in rules):
            return 0
        bands = _amber(rules, rows)
        if not bands:
            raise refuse("the aimed rules' amber bands do not meet at this row count")
        lo, hi = bands[0]
        want = (lo + hi) // 2
    else:
        sizes = []
        for r in rules:
            if single_tier(r, rows):
                sizes.append(FAIL_ROWS)
                continue
            first = _first_fail(r, rows)
            if first is None:
                raise refuse("no check of it fails at any count this frame can hold")
            own = _amber([r], rows)
            width = (own[0][1] - own[0][0] + 1) if own else 0
            sizes.append(first + width)
        want = max(sizes)
    if want > rows:
        raise refuse(f"{want} rows are needed and the frame holds {rows}")
    verdict_ok = (lambda r: _fails(r, want, rows)) if severity == FAIL else (
        lambda r: _warns(r, want, rows) and not _fails(r, want, rows))
    if not all(verdict_ok(r) for r in rules):
        raise refuse(f"{want} rows do not land {severity} on every aimed rule")
    return want


def lands(cat, dataset_id: str, keys, severity: str, planted: int, rows: int,
          where: str) -> None:
    """Refuse when `planted` rows, as planted, do not land `severity` on
    every aimed rule - the check a drop rule needs, whose achieved count
    depends on the frame it is cut from as well as on the size asked."""
    rules = rules_for(cat, dataset_id, keys, where)
    for k, r in zip(keys, rules):
        ok = _fails(r, planted, rows) if severity == FAIL else (
            not _fails(r, planted, rows) and (planted == 0 or _warns(r, planted, rows)))
        if not ok:
            raise FaultSizeError(f"{where}: {planted} of {rows} rows do not land {severity} "
                                 f"on {k!r} ({bands_text(r)}); nothing was planted")
