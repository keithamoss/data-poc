"""Publishing a one-off's page (REQ-PIPE-443): one page named by its id,
written with its fonts/ beside it to the destination its kind's template names
(asset_model/one_off_publishing.py), read at the moment of publishing.

THE FOUR STEPS OF ANY ASSET'S BUILD, AND NOTHING ELSE (criteria 1 and 2;
delivery-architect D2): rebuild the results from the recorded history,
reshape them, embed them and render-gate the page - in a scratch directory of
its own, never the real reports/ or dashboard/. NOT the recurring assets'
publish(): no snapshot archived into the committed dashboard/snapshots/, no
build fingerprint compared, no publish-environment gate, and never their
hosting (criterion 10). The page's data files are then inlined into the one
page, as a snapshot inlines them, and that page is render-gated again before
it is written.

THE PUBLISHED PAGE IS ITS OWN RECORD. Nothing is kept of a publish anywhere
else: the page carries, in a <meta> element, the one-off and package it is
for, when it was published and the decisions it shows. That is what refuses
another package's overwrite (criterion 5), what refuses a load of a one-off
already published (criterion 7) - by then the database may be gone - and what
the drop's warnings (criteria 8 and 9) and the decide step's note (REQ-PIPE-435
criterion 11) compare the recorded decisions with.

NEVER DELETED, NEVER INDEXED (criterion 6): nothing here removes a page or
writes anything but the one-off's own page and the fonts beside it.
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from asset_model import assets, one_off_publishing

#: The <meta> element a one-off's page carries its identity in.
META_NAME = "mothman-one-off"
_META_RE = re.compile(r'<meta name="' + META_NAME + r'" content="([^"]*)">')
#: How the publication - its instant and address - reaches the embed, which may
#: run in another process (as build_output's directory does).
PUBLICATION_ENV = "MOTHMAN_ONE_OFF_PUBLICATION"
#: The fonts the page loads from beside itself.
FONTS = Path(__file__).resolve().parents[2] / "dashboard" / "fonts"


class PublishRefused(RuntimeError):
    """The publish cannot go ahead. Its message says why; nothing was written."""


def page_name(one_off_id: str) -> str:
    return f"{one_off_id}.html"


def meta_tag(identity: dict) -> str:
    """The element the embed writes into a one-off's page."""
    return (f'<meta name="{META_NAME}" content="'
            f'{_html.escape(json.dumps(identity, sort_keys=True), quote=True)}">')


def identity_of(page: str) -> dict | None:
    """What a published page says it is - or None where it carries no
    readable identity (and so belongs to nobody this system can name)."""
    found = _META_RE.search(page)
    if not found:
        return None
    try:
        return json.loads(_html.unescape(found.group(1)))
    except ValueError:
        return None


# ---- the destination: a folder or an S3 prefix ------------------------------

def destination(kind: str) -> one_off_publishing.Destination:
    """The kind's destination, read from its template now."""
    try:
        return one_off_publishing.read(assets.kind_template(kind))
    except one_off_publishing.NoDestination as exc:
        raise PublishRefused(str(exc)) from None


def _s3(client):
    if client is not None:
        return client
    import boto3

    return boto3.client("s3")


def _key(dest, name: str) -> str:
    return f"{dest.prefix}/{name}" if dest.prefix else name


def read_page(dest, one_off_id: str, *, s3_client=None) -> str | None:
    """The page published at the one-off's address, or None where there is none."""
    name = page_name(one_off_id)
    if not dest.is_s3:
        path = dest.folder / name
        return path.read_text(encoding="utf-8") if path.is_file() else None
    client = _s3(s3_client)
    try:
        got = client.get_object(Bucket=dest.bucket, Key=_key(dest, name))
    except Exception as exc:  # noqa: BLE001 - botocore's NoSuchKey, and a 404
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    return got["Body"].read().decode("utf-8")


def write_page(dest, page: Path, one_off_id: str, *, s3_client=None) -> str:
    """Write the page and the fonts beside it; return the page's address."""
    name = page_name(one_off_id)
    if not dest.is_s3:
        dest.folder.mkdir(parents=True, exist_ok=True)
        shutil.copytree(FONTS, dest.folder / "fonts", dirs_exist_ok=True)
        # Written beside, then renamed over: a reader never meets half a page.
        partial = dest.folder / f".{name}.partial"
        shutil.copyfile(page, partial)
        os.replace(partial, dest.folder / name)
        return dest.address(name)
    client = _s3(s3_client)
    for font in sorted(FONTS.rglob("*")):
        if font.is_file():
            client.put_object(Bucket=dest.bucket, Key=_key(dest, f"fonts/{font.relative_to(FONTS).as_posix()}"),
                              Body=font.read_bytes())
    client.put_object(Bucket=dest.bucket, Key=_key(dest, name), Body=page.read_bytes(),
                      ContentType="text/html; charset=utf-8")
    return dest.address(name)


# ---- what is published, against what is recorded ---------------------------

@dataclass(frozen=True)
class Published:
    """A page found at a one-off's address."""

    address: str
    identity: dict | None

    @property
    def published_at(self) -> str | None:
        return (self.identity or {}).get("published_at")

    @property
    def latest_decision_at(self) -> str | None:
        return (self.identity or {}).get("latest_decision_at")


def published(kind: str, one_off_id: str, *, s3_client=None) -> Published | None:
    """The page at the one-off's address, or None where nothing is published."""
    dest = destination(kind)
    page = read_page(dest, one_off_id, s3_client=s3_client)
    if page is None:
        return None
    return Published(dest.address(page_name(one_off_id)), identity_of(page))


def _instant(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def decisions_since(found: Published, decisions) -> list:
    """Every recorded decision the published page does not show - those decided
    after the newest one it carries (criterion 9; delivery-cli-ux G1)."""
    from datetime import datetime

    shown = found.latest_decision_at
    if shown is None:
        return list(decisions)
    cut = datetime.fromisoformat(shown)
    return [d for d in decisions if d.decided_at > cut]


def load_refusal(kind: str, one_off_id: str) -> str | None:
    """Criterion 7: a load of a one-off whose page is already published."""
    try:
        found = published(kind, one_off_id)
    except PublishRefused:
        return None  # no destination: nothing can be published there, so nothing is
    if found is None:
        return None
    return (f"{one_off_id}'s page is already published at {found.address}, so its QA is "
            f"recorded for good and it is not loaded again. A re-send is a new one-off, "
            f"with an id of its own.")


def drop_warnings(kind: str, one_off_id: str, decisions) -> tuple[list[str], bool]:
    """(the warnings for the drop's confirmation, whether to offer to publish
    first) - criteria 8 and 9."""
    found = published(kind, one_off_id)
    if found is None:
        return ([f"Warning: {one_off_id} has no published page. Once it is dropped, no record "
                 f"of its QA results or decisions will remain - only its committed "
                 f"configuration. `mothman one-off publish --id {one_off_id}` publishes it."],
                False)
    missed = decisions_since(found, decisions)
    if missed:
        from qa_tools.common import one_off_decision

        return ([f"Warning: the page published at {found.address} does not show "
                 f"{'the latest decision' if len(missed) == 1 else f'the {len(missed)} latest decisions'}"
                 f" ({one_off_decision.words(missed[0])}), and once it is dropped nothing else "
                 f"will."], True)
    return [], False


# ---- the publish ------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """What a publish will do, shown before it is confirmed (criterion 3)."""

    one_off_id: str
    address: str
    in_force: object          # the standing Decision, or None
    not_yet_checked: list     # dataset ids with no recorded outcome
    package_digest: str
    replaces: bool            # a page of this package is already there


def plan(one_off_id: str, *, s3_client=None) -> Plan:
    """Everything the confirmation shows, and every refusal before it."""
    from qa_tools.common import one_off_decision, one_off_load, supply_db

    asset = assets.selected()
    dest = destination(asset.kind)
    with supply_db.connect(read_only=True, label="mothman:one-off-publish") as conn:
        load = one_off_load.recorded_load(conn)
        if load is None:
            raise PublishRefused(f"{one_off_id} has not been loaded, so there are no QA results "
                                 f"to publish. Load it first: mothman one-off load --id "
                                 f"{one_off_id} <package>.")
        in_force = one_off_decision.standing(conn)
        summary = one_off_decision.qa_summary(conn)
    address = dest.address(page_name(one_off_id))
    page = read_page(dest, one_off_id, s3_client=s3_client)
    replaces = False
    if page is not None:
        held = identity_of(page) or {}
        if held.get("one_off_id") != one_off_id or \
                held.get("package_digest") != load["package_digest"]:
            raise PublishRefused(
                f"a page is already published at {address} for "
                f"{'another package' if held else 'something this system cannot name'}"
                f"{' (package ' + held['package_digest'] + ')' if held.get('package_digest') else ''}"
                f", so nothing was written over it. Published pages are never replaced by "
                f"another one-off's.")
        replaces = True
    return Plan(one_off_id, address, in_force,
                [d.dataset_id for d in summary if not d.outcome], load["package_digest"], replaces)


def build_page(into: Path, publication: dict, steps, say=print) -> Path:
    """Build the selected one-off's page in `into`: `steps`, the caller's
    [(words, step)] - the rebuild, reshape, embed and render-gate steps of any
    asset's build, which are the CLI's - then its data inlined into one page,
    render-gated again. Returns the page."""
    from dashboard import check_dashboard_renders, data_files
    from qa_tools.common import build_output

    before = os.environ.get(build_output.OUT_DIR_ENV)
    os.environ[PUBLICATION_ENV] = json.dumps(publication)
    try:
        build_output.use(into)
        for words, step in steps:
            say(words)
            step()
        built = Path(into) / build_output.PAGE_NAME
        one = Path(into) / "page" / page_name(assets.selected().name)
        one.parent.mkdir(parents=True, exist_ok=True)
        one.write_text(data_files.inline(built.read_text(encoding="utf-8"), built.parent),
                       encoding="utf-8")
        shutil.copytree(FONTS, one.parent / "fonts", dirs_exist_ok=True)
        errors = check_dashboard_renders.render_errors(one, "the one-off's page")
        if errors:
            raise PublishRefused("the page failed its render check, so nothing was written:\n"
                                 + "\n".join(f"  - {e}" for e in errors))
        return one
    finally:
        os.environ.pop(PUBLICATION_ENV, None)
        if before is None:
            os.environ.pop(build_output.OUT_DIR_ENV, None)
        else:
            os.environ[build_output.OUT_DIR_ENV] = before


def publication() -> dict | None:
    """The publication the embed is building for, or None (a plain build)."""
    raw = os.environ.get(PUBLICATION_ENV)
    return json.loads(raw) if raw else None


def publish(planned: Plan, steps, *, s3_client=None, say=print) -> str:
    """Build the page by `steps` (build_page) and write it to its destination;
    return its address."""
    asset = assets.selected()
    dest = destination(asset.kind)
    # THE CHECK WORKSPACE, AS THE LOAD BUILT IT (the mock run's D2,
    # 2026-11-22): the committed folder holds the recipe layer only, and the
    # default layer's names and prose live in the kind's template, read live
    # and never copied in (REQ-PIPE-440 criterion 13). Built from the folder
    # and the template, so the page words every check as the load did.
    from qa_tools.common import one_off_checks

    workspace = one_off_checks.materialise()
    assets.use_workspace(workspace)
    try:
        with tempfile.TemporaryDirectory(prefix="mothman-one-off-publish-") as tmp:
            return _build_and_write(planned, dest, Path(tmp), steps, s3_client=s3_client,
                                    say=say)
    finally:
        assets.use_workspace(None)


def _build_and_write(planned: Plan, dest, tmp: Path, steps, *, s3_client, say) -> str:
    from asset_model import asset_time

    page = build_page(tmp, {"at": asset_time.now().isoformat(),
                            "address": planned.address}, steps, say=say)
    # ASKED AGAIN AT THE MOMENT OF WRITING: another package's page may have
    # arrived while this one was building.
    held = read_page(dest, planned.one_off_id, s3_client=s3_client)
    if held is not None and (identity_of(held) or {}).get("package_digest") \
            != planned.package_digest:
        raise PublishRefused(f"a page for another package was published at "
                             f"{planned.address} while this one was building, so nothing "
                             f"was written over it.")
    return write_page(dest, page, planned.one_off_id, s3_client=s3_client)
