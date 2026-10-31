"""A binned distribution any check's result may carry (REQ-QAC-333 criteria 9
and 10): GENERIC - its bin edges and its two queries are declared with the
check, under a `histogram` attribute, and nothing here or on the page knows
which check carries one.

    histogram:
      values: <SQL giving one number per thing counted>
      population: <SQL giving one number - what the things are counted among>
      edges: [51, 101, 151, ...]

Measured in the orchestrator's run step, where the run's connection is open
(CLAUDE.md: a computation needing supply rows never belongs to the build), and
recorded as counts only - no value the queries read is kept. Each bin is
[edge, next edge), the last open-ended.
"""
from __future__ import annotations

from pathlib import Path


def declared(path: str | Path) -> dict[str, dict]:
    """{check_id: its histogram declaration} for every check in a Soda file
    that declares one."""
    from qa_tools.common import config_yaml

    doc = config_yaml.parse(Path(path).read_text()) or {}
    out = {}
    for key, checks in doc.items():
        if not str(key).startswith("checks for"):
            continue
        for check in checks or []:
            for cfg in (check or {}).values():
                attrs = (cfg or {}).get("attributes") or {} if isinstance(cfg, dict) else {}
                if attrs.get("check_id") and isinstance(attrs.get("histogram"), dict):
                    out[attrs["check_id"]] = attrs["histogram"]
    return out


def bins(values, edges) -> list[dict]:
    """[{from, to, count}] - `to` None for the last, open-ended bin."""
    edges = [float(e) for e in edges]
    out = [{"from": edges[i], "to": edges[i + 1] if i + 1 < len(edges) else None, "count": 0}
           for i in range(len(edges))]
    for v in values:
        v = float(v)
        for b in reversed(out):
            if v >= b["from"]:
                b["count"] += 1
                break
    return out


def measure(conn, spec: dict) -> dict:
    """The recorded distribution: the bins, how many things were counted and
    the population they were counted among."""
    values = [r[0] for r in conn.execute(spec["values"]).fetchall() if r[0] is not None]
    population = None
    if spec.get("population"):
        row = conn.execute(spec["population"]).fetchone()
        population = int(row[0]) if row and row[0] is not None else None
    return {"bins": bins(values, spec["edges"]), "count": len(values), "population": population}
