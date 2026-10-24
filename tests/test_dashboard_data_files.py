"""REQ-DASH-291 and REQ-DASH-293: the dashboard's data files, at the level
of the one module that writes and reads them (dashboard/data_files.py).

What a built page does with these files is proven in a real browser by
tests/test_dashboard_e2e.py; what embed() writes is in
tests/test_embed_dashboard_data.py. This file covers the encoding itself:
that a payload goes in and comes back out unchanged, under a name taken
from its bytes, within the budget, and that the one reader finds the same
data in sibling files or inlined.
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from dashboard import data_files


def _payload(size: int = 2000) -> dict:
    # Every character the encoding has to escape, so a round trip proves
    # each one: quotes of both kinds, a backslash, "</script>", a line
    # separator and non-ASCII text.
    return {"datasets": [{"id": "d", "note": "it's \"quoted\" \\ </script> <!--   café",
                          "blob": "x" * size}]}


def _files(*payloads, budget=None):
    out = []
    for i, p in enumerate(payloads):
        out += data_files.encode(f"collection-c{i}", p, kind="collection", collection=f"c{i}",
                                 budget=budget)
    return out


class TestEncoding:
    """REQ-DASH-291 criteria 3 and 5, REQ-DASH-293 criteria 1 and 2."""

    def test_a_file_is_named_from_its_key_and_the_sha256_of_its_bytes(self):
        [f] = data_files.encode("collection-civil-registration", _payload(), kind="collection",
                                collection="civil-registration")
        digest = hashlib.sha256(f.content).hexdigest()
        assert f.entry["name"] == f"collection-civil-registration.{digest[:12]}.js"
        assert f.entry["sha256"] == digest and f.entry["bytes"] == len(f.content)

    def test_identical_content_gives_identical_names_and_any_change_a_new_one(self):
        a = data_files.encode("collection-x", _payload(), kind="collection", collection="x")
        b = data_files.encode("collection-x", _payload(), kind="collection", collection="x")
        c = data_files.encode("collection-x", _payload(2001), kind="collection", collection="x")
        assert [f.content for f in a] == [f.content for f in b]
        assert [f.entry["name"] for f in a] == [f.entry["name"] for f in b]
        assert a[0].entry["name"] != c[0].entry["name"]

    def test_a_file_registers_one_string_and_its_build_under_its_own_key(self):
        [f] = data_files.encode("collection-x", _payload(), kind="collection", collection="x")
        text = f.content.decode("ascii")
        assert re.fullmatch(
            r'\(window\.MOTHMAN_DATA=window\.MOTHMAN_DATA\|\|\{\}\)\["collection-x#1"\]='
            r'\{build:"[0-9a-f]{12}",text:\'.*\'\};\n', text, re.DOTALL), text[:200]
        assert f.entry["build"] in text
        # Inert to an HTML parser, so a snapshot can inline it unchanged.
        assert "<" not in text

    def test_the_payload_comes_back_out_unchanged(self):
        files = data_files.encode("collection-x", _payload(), kind="collection", collection="x")
        decoded = [data_files.decode(f.content) for f in files]
        assert json.loads("".join(d.text for d in decoded)) == _payload()
        assert {d.key for d in decoded} == {"collection-x"}

    def test_a_payload_over_the_budget_is_written_as_numbered_parts_within_it(self):
        budget = 4096
        files = data_files.encode("collection-x", _payload(20000), kind="collection",
                                  collection="x", budget=budget)
        assert len(files) > 1
        assert [f.entry["part"] for f in files] == list(range(1, len(files) + 1))
        assert all(f.entry["parts"] == len(files) for f in files)
        assert all(len(f.content) <= budget for f in files)
        for f in files:
            digest = hashlib.sha256(f.content).hexdigest()
            assert f.entry["name"] == f"collection-x.part{f.entry['part']}.{digest[:12]}.js"
        assert len({f.entry["build"] for f in files}) == 1, "the parts of one payload share its build"
        joined = "".join(data_files.decode(f.content).text for f in files)
        assert json.loads(joined) == _payload(20000)

    def test_the_budget_is_ten_mebibytes_in_one_named_constant(self):
        assert data_files.BUDGET_BYTES == 10 * 1024 * 1024


class TestTheManifest:
    """REQ-DASH-291 criterion 4."""

    def test_it_lists_each_files_key_name_size_and_sha256_and_the_builds_id(self):
        files = _files(_payload(), _payload(10))
        manifest = data_files.manifest(files)
        assert re.fullmatch(r"[0-9a-f]{12}", manifest["build"])
        assert [e["name"] for e in manifest["files"]] == [f.entry["name"] for f in files]
        for e in manifest["files"]:
            assert {"key", "name", "bytes", "sha256", "build", "part", "parts", "kind"} <= set(e)

    def test_the_builds_id_follows_its_content(self):
        assert (data_files.manifest(_files(_payload()))["build"]
                == data_files.manifest(_files(_payload()))["build"])
        assert (data_files.manifest(_files(_payload()))["build"]
                != data_files.manifest(_files(_payload(5)))["build"])


def _built_page(tmp_path, files, *, requirements_plans=None):
    """A minimal page in the built page's own shape, written the way embed()
    writes it, with its files beside it."""
    if requirements_plans is not None:
        files = files + data_files.encode(data_files.REQUIREMENTS_PLANS_KEY, requirements_plans,
                                          kind=data_files.REQUIREMENTS_PLANS_KEY)
    manifest = data_files.manifest(files)
    html = ("<html>\n<!-- mothman:data-files -->\n<script>\nconst DATA_FILES = null;\n"
            "const COLLECTION_DATA = null;\n</script>\n</html>\n")
    html = data_files.embed_into_page(html, manifest)
    page = tmp_path / "page.html"
    data_files.write(files, tmp_path / "data")
    page.write_text(html)
    return page


class TestTheOneReader:
    """REQ-DASH-291 criterion 13: one helper returns a built page's data,
    from sibling files or inlined."""

    def test_it_reads_sibling_files(self, tmp_path):
        page = _built_page(tmp_path, _files(_payload(), _payload(3)),
                           requirements_plans={"requirements": [{"id": "R"}], "plans": {"items": []}})
        got = data_files.read_page(page.read_text(), page.parent)
        assert got.problems == []
        assert got.collections == {"c0": _payload(), "c1": _payload(3)}
        assert got.requirements == [{"id": "R"}] and got.plans == {"items": []}

    def test_it_reads_the_same_data_inlined(self, tmp_path):
        page = _built_page(tmp_path, _files(_payload(), _payload(3)),
                           requirements_plans={"requirements": [], "plans": {}})
        inlined = data_files.inline(page.read_text(), page.parent)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        got = data_files.read_page(inlined, elsewhere)
        assert got.problems == []
        assert got.collections == {"c0": _payload(), "c1": _payload(3)}

    def test_it_names_a_missing_file_and_one_whose_sha256_differs(self, tmp_path):
        files = _files(_payload(), _payload(3))
        page = _built_page(tmp_path, files)
        (tmp_path / "data" / files[0].entry["name"]).unlink()
        tampered = tmp_path / "data" / files[1].entry["name"]
        tampered.write_bytes(tampered.read_bytes().replace(b"xxx", b"yyy", 1))
        got = data_files.read_page(page.read_text(), page.parent)
        assert any(files[0].entry["name"] in p and "missing" in p for p in got.problems), got.problems
        assert any(files[1].entry["name"] in p and "SHA-256" in p for p in got.problems), got.problems

    def test_a_page_with_its_data_inline_in_a_const_is_read_too(self, tmp_path):
        html = '<script>\nconst COLLECTION_DATA = {"c0": {"datasets": []}};\n</script>\n'
        got = data_files.read_page(html, tmp_path)
        assert got.problems == [] and got.collections == {"c0": {"datasets": []}}


class TestWriting:
    """REQ-DASH-291 criterion 11."""

    def test_prune_removes_only_unreferenced_files_in_the_data_directory(self, tmp_path):
        data = tmp_path / "data"
        files = _files(_payload())
        data_files.write(files, data)
        (data / "collection-c0.000000000000.js").write_text("stale")
        (tmp_path / "beside.js").write_text("not ours")
        removed = data_files.prune(data, [f.entry["name"] for f in files])
        assert [p.name for p in removed] == ["collection-c0.000000000000.js"]
        assert sorted(p.name for p in data.iterdir()) == [files[0].entry["name"]]
        assert (tmp_path / "beside.js").exists()


class TestSizes:
    """REQ-DASH-293 criterion 4 and REQ-PIPE-255 criterion 26."""

    def test_every_file_is_printed_and_the_budget_and_ceiling_warn(self, tmp_path):
        page = tmp_path / "page.html"
        page.write_bytes(b"x" * 100)
        small = tmp_path / "small.js"
        small.write_bytes(b"x" * 10)
        at_budget = tmp_path / "budget.js"
        at_budget.write_bytes(b"x" * data_files.BUDGET_BYTES)
        big = tmp_path / "big.js"
        big.write_bytes(b"x" * data_files.WARN_BYTES)
        lines = data_files.size_report(page, [small, at_budget, big])
        info = [t for level, t in lines if level == "info"]
        warn = [t for level, t in lines if level == "warn"]
        assert any("page.html" in t for t in info) and any("small.js" in t for t in info)
        assert any("budget.js" in t and "10 MiB budget" in t for t in warn), warn
        assert any("big.js" in t and "25 MiB" in t for t in warn), warn
        assert not any("small.js" in t for t in warn)


def test_dashboard_data_is_gitignored():
    """REQ-DASH-291 criterion 12."""
    import subprocess

    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    probe = "dashboard/data/collection-x.000000000000.js"
    result = subprocess.run(["git", "check-ignore", "-q", probe], cwd=root)
    assert result.returncode == 0, f"{probe} is not gitignored"


@pytest.mark.parametrize("budget", [None, 3000])
def test_the_split_of_an_inlined_page_writes_every_file_back_byte_for_byte(tmp_path, budget):
    """REQ-DASH-292 criterion 5: the split form's files match the list the
    page carries - the guard against an off-by-one-byte split, which would
    make every publish count as changed (REQ-PIPE-255 criterion 24)."""
    files = _files(_payload(), _payload(9000), budget=budget)
    page = _built_page(tmp_path, files, requirements_plans={"requirements": [], "plans": {}})
    original = {p.name: p.read_bytes() for p in (tmp_path / "data").iterdir()}
    inlined = data_files.inline(page.read_text(), page.parent)
    split_html, written = data_files.split(inlined, "snap.data")
    assert written == original
    again = data_files.read_page(split_html, tmp_path / "nowhere")
    assert again.problems  # the split page reads its files from snap.data/
    site = tmp_path / "site"
    (site / "snap.data").mkdir(parents=True)
    for name, content in written.items():
        (site / "snap.data" / name).write_bytes(content)
    assert data_files.read_page(split_html, site).problems == []
