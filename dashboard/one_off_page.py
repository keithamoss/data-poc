"""What a one-off's page knows about itself (REQ-DASH-444, REQ-DASH-447), as the
ONE_OFF const the embed writes - None for an enduring asset's page.

KIND-NEUTRAL, EXCEPT ONE PART (REQ-DASH-444's split, Keith round 4): the site
name, the kind's display words, the release decisions, the publication and the
two commits are every kind's; what the one-off DECLARED - an extraction's
recipe - is its kind's plug-in's `declaration`, so a second kind brings its
own and changes nothing here.

READ FROM RECORDED QA METADATA AND COMMITTED CONFIGURATION ONLY (the build
rule): the one-off's data-asset.yaml and calendar.yaml, and, in its database,
qa.one_off_load (the package, and the commit its checks ran at - REQ-PIPE-442
criterion 3) and qa.one_off_decision (REQ-PIPE-435). Never a supply row, and
never the recipe file (REQ-DASH-447 criterion 4).
"""
from __future__ import annotations

from asset_model import assets


def _short(sha: str | None) -> str | None:
    return sha[:7] if sha else None


def _built_at() -> str | None:
    """The commit of this repository that built the page, labelled 'built at'
    (REQ-DASH-444 criterion 8) - snapshot_dashboard's own provenance helper."""
    from dashboard.snapshot_dashboard import _git_short_sha

    sha = _git_short_sha(cwd=assets.ROOT)
    return None if sha == "nogit" else sha


def record() -> dict | None:
    """The selected one-off's ONE_OFF, or None for an enduring asset."""
    asset = assets.selected()
    if asset.kind is None:
        return None
    from asset_model import config_yaml, one_off_kinds
    from qa_tools.common import display_time, one_off_decision, one_off_load, one_off_publish
    from qa_tools.common import supply_db

    kind = one_off_kinds.get(asset.kind)
    doc = config_yaml.load(asset.data_asset_yaml) or {}
    project = str(doc.get("project") or "")
    with supply_db.connect(read_only=True, label="mothman:one-off-page") as conn:
        load = one_off_load.recorded_load(conn) or {}
        history = one_off_decision.history(conn)
    decisions = []
    for i, d in enumerate(history):
        decisions.append({
            "decision": d.decision, "reason": d.reason, "actor": d.actor_name,
            "at": d.decided_at.isoformat(), "atWords": display_time.format_instant(d.decided_at),
            "current": i == 0,
            # REPLACED BY THE ONE AFTER IT (criterion 6): newest first, so the
            # decision that replaced this one is the one listed before it.
            "replacedBy": None if i == 0 else history[i - 1].decided_at.isoformat(),
            "replacedByWords": None if i == 0 else display_time.format_instant(
                history[i - 1].decided_at)})
    published = one_off_publish.publication()
    out = {
        "id": asset.name, "project": project,
        "siteName": f"{asset.name} · {project} · QA report",
        "kind": {"singular": kind.singular if kind else asset.kind,
                 "plural": kind.plural if kind else asset.kind,
                 "layer": kind.layer if kind else "Kind check"},
        "decisions": decisions,
        "publishedAt": (published or {}).get("at"),
        "address": (published or {}).get("address"),
        "builtAt": _built_at(),
        "checkedAt": _short(load.get("loaded_commit")),
        "declaration": (kind.declaration(asset.folder)
                        if kind is not None and kind.declaration else None),
    }
    return out


def identity(rec: dict) -> dict:
    """What the page's <meta> carries - read back by a later publish, load or
    drop (qa_tools/common/one_off_publish.py)."""
    from qa_tools.common import one_off_load, supply_db

    with supply_db.connect(read_only=True, label="mothman:one-off-page") as conn:
        load = one_off_load.recorded_load(conn) or {}
    return {"one_off_id": rec["id"], "package_digest": load.get("package_digest"),
            "recipe_digest": load.get("recipe_digest"),
            "published_at": rec["publishedAt"],
            "decisions": len(rec["decisions"]),
            "latest_decision_at": rec["decisions"][0]["at"] if rec["decisions"] else None}

