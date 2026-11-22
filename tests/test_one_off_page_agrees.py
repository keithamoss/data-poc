"""A one-off whose ONLY problems are package facts, run open -> load -> list ->
publish, and every layer a person reads asked whether it agrees
(post-build-review: the worked mock run of 2026-11-22, its D1 to D5).

WHY A JOURNEY OF ITS OWN. tests/test_one_off_end_to_end.py's fixture fails
its home dataset on its data too, and that hid the false green found on the
mock run: an undeclared file failed its home dataset's own pill while the
collection and agency above it read Pass, the load said "0 failing", and the
dataset page named no failing check. Here nothing but package facts fail:

- health-agency / cohort-study / cohort-people (people.csv): clean - the
  first counted dataset, so the undeclared extra.csv is recorded against it
  (REQ-QAC-441, Keith 2026-11-22 'first dataset + home');
- health-agency / lab-study / lab-results (labs.csv): clean;
- other-agency / visit-study / cohort-visits (visits.csv): declared and
  ABSENT, so its 'declared table arrived' fails and it has no run of data;
- other-agency / visit-study / cohort-summary (summary.csv): a DERIVED
  product, one value of it no integer - failing, and counted in no status.

The statuses are asserted at the layer a human sees - the built page, in a
real browser, through the page's own functions - and against
qa_tools/common/dataset_status.py over the same embedded data (CLAUDE.md:
verify at the LAST transform).
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import psycopg
import pytest
from click.testing import CliRunner

from asset_model import assets

from test_one_off_load import World, _point, _said

pytestmark = pytest.mark.asset("daily")

HA, OA = {"id": "health-agency", "name": "Health Agency"}, {"id": "other-agency",
                                                              "name": "Other Agency"}


def _table(file, agency, collection, dataset, *, derived=False, columns, expected=None):
    t = {"file": file, "format": "csv", "agency": agency, "collection": collection,
         "dataset": dataset, "derived": derived, "columns": columns, "cohort": []}
    if expected is not None:
        t["expected_rows"] = expected
    return t


def _clean_package(where: Path, one_off_id: str) -> Path:
    cohort = {"id": "cohort-study", "name": "Cohort Study"}
    labs = {"id": "lab-study", "name": "Lab Study"}
    visits = {"id": "visit-study", "name": "Visit Study"}
    ident = lambda n, t="string": {"name": n, "type": t, "primary_identifier": True}  # noqa: E731
    plain = lambda n, t: {"name": n, "type": t, "primary_identifier": False}  # noqa: E731
    recipe = {"recipe_format_version": 1, "extraction_id": one_off_id,
              "project": "The agreement study", "filter": "Everyone, 2020 to 2024.",
              "tables": [
                  _table("people.csv", HA, cohort, {"id": "cohort-people", "name": "People",
                                                    "table": "cohort_people"},
                         columns=[ident("person_id"), plain("first_seen", "date")], expected=2),
                  _table("labs.csv", HA, labs, {"id": "lab-results", "name": "Lab results",
                                                "table": "lab_results"},
                         columns=[ident("lab_id"), plain("reading", "number")], expected=2),
                  _table("visits.csv", OA, visits, {"id": "cohort-visits", "name": "Visits",
                                                    "table": "cohort_visits"},
                         columns=[ident("visit_id")]),
                  _table("summary.csv", OA, visits, {"id": "cohort-summary",
                                                     "name": "Yearly summary",
                                                     "table": "cohort_summary"},
                         derived=True, columns=[ident("year", "integer"),
                                                plain("people", "integer")]),
              ]}
    where.mkdir(parents=True)
    (where / "recipe.json").write_text(json.dumps(recipe, indent=1))
    (where / "people.csv").write_text("person_id,first_seen\np1,2021-01-01\np2,2022-02-02\n")
    (where / "labs.csv").write_text("lab_id,reading\nl1,1.5\nl2,2.25\n")
    (where / "summary.csv").write_text("year,people\n2021,1\n2022,lots\n")
    (where / "extra.csv").write_text("anything\n1\n")
    return where


def _invoke(args, *, input=None):
    from cli.one_off import one_off_group

    got = CliRunner().invoke(one_off_group, args, input=input)
    assets.release_claim()
    assets.deselect_one_off()
    return got


@pytest.fixture(scope="module")
def trip(tmp_path_factory):
    from qa_tools.common import git_identity

    w = World(tmp_path_factory.mktemp("one-off-agrees"))
    w.package = _clean_package(w.base / "clean-pkg", w.id)
    w.dest = w.base / "destination"
    (w.root / "extraction" / "_template" / "publishing.yaml").write_text(
        f"destination: {w.dest}\n")
    w.commit("the test's destination")
    # A DATABASE ON THE SERVER THAT IS NO ONE-OFF'S (D4): named like one,
    # holding nothing a one-off load writes.
    w.plain_db = f"supply_x-{uuid.uuid4().hex[:6]}-plain"
    with psycopg.connect(w.admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{w.plain_db}"')
    w.said = {}
    with pytest.MonkeyPatch.context() as mp:
        _point(w, mp)
        mp.setattr(git_identity, "get_run_by", lambda: "tester@example.org")
        try:
            opened = _invoke(["open", "--kind", "extraction", str(w.package)])
            assert opened.exit_code == 0, opened.output
            w.commit("open")
            # EACH STEP, AND `list` AFTER IT (REQ-PIPE-442 criterion 10 as
            # amended 2026-11-22): loaded, decided, published.
            for step, args in (("load", ["load", "--id", w.id, str(w.package)]),
                               ("list", ["list"]),
                               ("decide", ["decide", "--id", w.id, "--decision", "withhold",
                                           "--reason", "The visits table never arrived.",
                                           "--yes"]),
                               ("list-decided", ["list"]),
                               ("publish", ["publish", "--id", w.id, "--yes"]),
                               ("list-published", ["list"])):
                w.said[step] = _invoke(args)
                assert w.said[step].exit_code == 0, (step, w.said[step].output[-3000:],
                                                     w.said[step].exception)
            w.page = w.dest / f"{w.id}.html"
            w.failing_in_db = w.query(
                "SELECT count(*) FROM qa.check_result c JOIN qa.run r USING (run_key) "
                "WHERE r.completed_at IS NOT NULL AND c.status IN ('fail', 'error')")[0][0]
            w.results_in_db = w.query(
                "SELECT count(*) FROM qa.check_result c JOIN qa.run r USING (run_key) "
                "WHERE r.completed_at IS NOT NULL")[0][0]
            # DROPPED AFTER PUBLISHING: its page stays, its database goes, and
            # `list` must not offer the load the publish refuses (the mock
            # run's D3).
            from cli import common

            mp.setattr(common, "require_tty", lambda hint: None)
            w.said["drop"] = _invoke(["drop", "--id", w.id], input=w.id + "\n")
            assert w.said["drop"].exit_code == 0, w.said["drop"].output[-2000:]
            w.said["list-dropped"] = _invoke(["list"])
            w.said["load-dropped"] = _invoke(["load", "--id", w.id, str(w.package)])
            yield w
        finally:
            assets.deselect_one_off()
            assets.use_one_offs_root(None)
            w.drop()
            with psycopg.connect(w.admin, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{w.plain_db}" WITH (FORCE)')


def _out(trip, step) -> str:
    return _said(trip.said[step])


# ---- D1, the first layer: the load's own count -----------------------------

class TestTheLoadCountsWhatFailed:
    def test_its_failing_count_is_the_databases(self, trip):
        said = _out(trip, "load")
        assert trip.failing_in_db >= 3, "the fixture must fail its package checks"
        got = re.search(r"(\d+) failing", said)
        assert got and int(got.group(1)) == trip.failing_in_db, said

    def test_its_total_is_every_recorded_result(self, trip):
        said = _out(trip, "load")
        got = re.search(r"(\d+) check result\(s\) recorded", said)
        assert got and int(got.group(1)) == trip.results_in_db, said


# ---- D5: noise a one-off's load and publish do not need ---------------------

class TestNoNoise:
    def test_no_owed_note_on_the_load(self, trip):
        assert "currently owed" not in _out(trip, "load")

    def test_no_calendar_note_on_the_publish(self, trip):
        said = _out(trip, "publish")
        assert "NoCalendarAgreed" not in said and "could not read" not in said, said

    def test_no_github_links(self, trip):
        # SAID, because this test's one-off is outside the repository, which
        # leaves the links out by another road (embed_dashboard_data's
        # github_links_or_none) - a real one-off's folder is inside it.
        assert "GITHUB_LINKS left out: a one-off never uses GitHub." in _out(trip, "publish")
        page = trip.page.read_text(encoding="utf-8")
        found = re.search(r"const GITHUB_LINKS = (.*?);\n", page)
        assert json.loads(found.group(1))["checks"] == {}


# ---- D4: `list` lists only one-off databases --------------------------------

class TestTheListsDatabases:
    def test_only_one_offs(self, trip):
        said = trip.said["list"].output
        listed = said.split("One-off databases on the server:")[1]
        assert f"supply_{trip.id} " in listed, said
        assert trip.plain_db not in listed, said


# ---- D3: `list` says decided and published, and never offers a refused step

def _row(trip, step) -> tuple[str, str]:
    """(the one-off's own line, its next step) in one `list`'s output."""
    lines = trip.said[step].output.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith(trip.id + " "))
    return lines[at], lines[at + 1]


class TestTheListFollowsTheStages:
    def test_loaded(self, trip):
        line, _next = _row(trip, "list")
        assert line.split()[2] == "loaded", line

    def test_decided(self, trip):
        line, nxt = _row(trip, "list-decided")
        assert line.split()[2] == "decided", line
        assert nxt.strip() == f"next: mothman one-off publish --id {trip.id}", nxt

    def test_published(self, trip):
        line, nxt = _row(trip, "list-published")
        assert line.split()[2] == "published", line
        assert "load" not in nxt and f"mothman one-off drop --id {trip.id}" in nxt, nxt

    def test_published_and_dropped_offers_no_load(self, trip):
        assert trip.said["load-dropped"].exit_code != 0, "the fixture's load must be refused"
        line, nxt = _row(trip, "list-dropped")
        assert line.split()[2] == "published", line
        assert "mothman one-off load" not in nxt, nxt
        assert str(trip.page) in nxt, nxt


# ---- D1 and D2 on the page --------------------------------------------------

EXPECTED_DATASETS = {"cohort-people": "red", "lab-results": "green",
                     "cohort-visits": "red", "cohort-summary": "red"}
EXPECTED_COLLECTIONS = {"cohort-study": "red", "lab-study": "green", "visit-study": "red"}
EXPECTED_AGENCIES = {"health-agency": "red", "other-agency": "red"}


def _open(page, trip, route=""):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"file://{trip.page}{route}")
    page.wait_for_function("Number(document.documentElement.dataset.renderCount || 0) >= 1")
    return errors


def _page_statuses(page) -> dict:
    return page.evaluate("""() => {
      const out = {datasets: {}, collections: {}, agencies: {}};
      DATA.agencies.forEach(ag => { out.agencies[ag.id] = ag.status;
        ag.collections.forEach(c => { out.collections[c.id] = c.status;
          c.datasets.forEach(d => { out.datasets[d.id] = d.status; }); }); });
      return out; }""")


class TestEveryLayerAgrees:
    def test_the_pages_statuses(self, page, trip):
        assert _open(page, trip) == []
        got = _page_statuses(page)
        assert got["datasets"] == EXPECTED_DATASETS, got
        assert got["collections"] == EXPECTED_COLLECTIONS, got
        assert got["agencies"] == EXPECTED_AGENCIES, got

    def test_the_python_mirror_agrees(self, page, trip):
        from qa_tools.common import dataset_status

        _open(page, trip)
        raw = page.evaluate("() => COLLECTION_DATA")
        hierarchy = page.evaluate("() => HIERARCHY")
        by_id = {d["id"]: d for e in raw.values() for d in e["datasets"]}
        for ds, want in EXPECTED_DATASETS.items():
            assert dataset_status.dataset_status(by_id[ds]) == want, ds
        # THE ROLLUP READS THE PAGE'S OWN DATASETS (their columns' statuses
        # and flags), with the raw package checks the page reads beside them.
        built = page.evaluate("""() => { const out = {};
          DATA.agencies.forEach(ag => ag.collections.forEach(c => c.datasets.forEach(d => {
            out[d.id] = {columns: d.columns.map(x => ({status: x.status})),
              derived: d.derived, noDataInPlaceOn: d.noDataInPlaceOn, packageOnly: d.packageOnly,
              scheduleExhausted: d.scheduleExhausted, notYetChecked: d.notYetChecked,
              turnedOffOutOfRollup: d.turnedOffOutOfRollup,
              scheduleNotAgreed: d.scheduleNotAgreed}; }))); return out; }""")
        for ag in hierarchy["agencies"]:
            for col in ag["collections"]:
                got = dataset_status.rollup_datasets(
                    {**built[d["id"]], "fileChecks": by_id[d["id"]].get("fileChecks")}
                    for d in col["datasets"])
                assert got == EXPECTED_COLLECTIONS[col["id"]], col["id"]

    def test_the_agency_and_collection_pills(self, page, trip):
        _open(page, trip, "#/agency/health-agency")
        assert page.locator(".view-head .pill").first.inner_text().strip() == "Fail"
        titles = {b.locator("h3").text_content(): b.locator(".pill").first.inner_text().strip()
                  for b in page.locator(".collection-title").all()}
        assert titles == {"Cohort Study": "Fail", "Lab Study": "Pass"}, titles
        _open(page, trip, "#/agency/other-agency")
        assert page.locator(".view-head .pill").first.inner_text().strip() == "Fail"

    def test_the_home_dataset_names_its_failing_check(self, page, trip):
        _open(page, trip, "#/agency/health-agency/collection/cohort-study/dataset/cohort-people")
        found = page.locator("[data-package-check='undeclared_file']")
        assert found.count() == 1
        assert "Fail" in found.locator(".pill").inner_text()
        assert "extra.csv" in found.inner_text()


class TestTheDefaultLayersWords:
    """D2: a default-layer check carries its template's name and prose."""

    def test_identifier_recorded(self, page, trip):
        _open(page, trip)
        raw = page.evaluate("() => COLLECTION_DATA")
        checks = [ck for e in raw.values() for d in e["datasets"] for c in d["columns"]
                  for ck in c["checks"] if ck["key"].startswith("identifier_not_null")]
        assert checks, "no default-layer identifier check on the page"
        for ck in checks:
            # EVIDENTLY'S CHECKS ARE NAMED BY THEIR METHOD, recipe layer and
            # default alike ('Null rate', 'Row count') - its own convention.
            if not ck["key"].endswith("_evidently"):
                assert ck["name"] == "Identifier recorded", ck
            assert ck.get("description") == "This value must never be empty.", ck


# ---- the recurring assets' parts of the page (Keith 2026-11-22) -------------

ABSENT = ("snapshots-panel", "in-place-on-panel", "period-panel", "leaderboard-panel",
          "feedback-btn")
TEMPLATE = Path(__file__).resolve().parent.parent / "dashboard" / \
    "qa-reporting-dashboard.template.html"


class TestTheRecurringAssetsPartsAreAbsent:
    def test_hidden_on_a_one_off(self, page, trip):
        _open(page, trip)
        for name in ABSENT:
            found = page.locator(f"#{name}")
            assert found.get_attribute("hidden") is not None and found.is_hidden(), name
        assert page.evaluate("() => getComputedStyle(document.getElementById("
                             "'snapshots-panel')).display") == "none"

    def test_kept_on_an_enduring_assets_page(self, page):
        page.goto(f"file://{TEMPLATE}")
        page.wait_for_function("Number(document.documentElement.dataset.renderCount || 0) >= 1")
        for name in ABSENT:
            assert page.locator(f"#{name}").get_attribute("hidden") is None, name
        assert page.evaluate("() => getComputedStyle(document.getElementById("
                             "'snapshots-panel')).display") != "none"
        assert "cross-table" in page.locator("footer").inner_text()


class TestAOneOffsWords:
    def test_the_footer(self, page, trip):
        _open(page, trip)
        footer = page.locator("footer").inner_text()
        assert "cross-table" not in footer and "synthetic" not in footer, footer
        assert footer.startswith("QA report for one extraction"), footer

    def test_the_home_and_agency_lines(self, page, trip):
        _open(page, trip)
        assert "in this extraction." in page.locator(".view-sub").first.inner_text()
        assert "multi-agency" not in page.locator("#view").inner_text()
        _open(page, trip, "#/agency/health-agency")
        sub = page.locator(".view-head .view-sub").first.inner_text()
        assert sub == "QA results for Health Agency's tables in this extraction.", sub

    def test_the_arrival_and_the_warehouse(self, page, trip):
        _open(page, trip, "#/agency/health-agency")
        text = page.locator("#view").inner_text()
        assert not re.search(r"waiting \d", text) and "Unknown" not in text, text
        assert "Received" in page.locator(".dataset-table thead").first.text_content()
        _open(page, trip, "#/agency/health-agency/collection/cohort-study/dataset/cohort-people")
        text = page.locator("#view").inner_text()
        assert "warehouse" not in text and "Awaiting a decision" not in text, text
        assert page.locator("[data-verdict-of='one-off']").inner_text().startswith(
            "The results below are the supply received ")

    def test_no_cross_table_section(self, page, trip):
        _open(page, trip, "#/agency/other-agency/collection/visit-study/dataset/cohort-summary")
        assert page.locator("[data-scope='cross-table']").count() == 0
        _open(page, trip, "#/agency/other-agency")
        assert "Cross-table checks" not in page.locator("#view").inner_text()


class TestAFailingDerivedProductOnTheHomeView:
    def test_one_line(self, page, trip):
        _open(page, trip)
        found = page.locator("[data-derived-failing]")
        assert found.count() == 1
        n = page.evaluate("""() => { let n = 0; DATA.agencies.forEach(a => a.collections.forEach(
            c => c.datasets.filter(d => d.id === 'cohort-summary').forEach(d => d.columns.forEach(
            col => col.checks.forEach(ck => { if(!ck.retired && checkStatus(ck) === 'red') n++; })))));
            return n; }""")
        assert n >= 1
        words = f"{n} check" + ("" if n == 1 else "s")
        assert found.inner_text().strip() == (
            f"The derived product Yearly summary fails {words}; derived products don't count "
            f"in this status.")
