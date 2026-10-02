"""`mothman docs validate` - the deterministic checks every explainer
page passes before any reviewer reads it (REQ-DOCS-122, REQ-DOCS-132).

WHAT IT CHECKS. Every file under docs/explainers/ except the gitignored
working folder `_work/`: safety (no HTML, images, URLs, hidden
characters, stray file types), structure (front matter, the 'In short'
box, links), Mermaid (parses in the version GitHub renders, the house
look, theme, seed and caption), the mechanical prose rules, sign-off
and its hash, and build state against requirements.yaml.

RULES ARE DATA, AND THE STANDARD OWNS THEM. Every rule has a stable id
that the house standard (.claude/skills/docs-house-style/SKILL.md)
marks inline, and `--list-rules` prints them; a test holds the two sets
equal. The banned lists, the exemptions and the house seed are read
from the standard's own `yaml house-rules` block - there is no copy of
any of them in this file, so a word Keith approves or removes changes
what is rejected without a code change.

FAIL CLOSED. If Node or the pinned mermaid package is missing while a
page has a diagram, the run fails naming the setup step. It never skips
the parse and reports green, which would be a summary claiming more than
ran.

WHAT IT DELIBERATELY DOES NOT JUDGE. Anything a reader has to judge -
whether the answer comes first, whether a diagram argues, pattern-shaped
tics, the sensitivity rule - belongs to the reader-judgement skill and
the critic. This file checks only what a machine can check without
opinion.

It reads committed files under docs/explainers/, the two skill files,
the docs-* agent definitions, requirements.yaml and the list of files
git tracks. It never opens a database or anything under data/ or
reports/ (REQ-DOCS-122 criterion 28).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPLAINERS = Path("docs/explainers")
WORK = EXPLAINERS / "_work"
HOUSE_STANDARD = Path(".claude/skills/docs-house-style/SKILL.md")
READER_JUDGEMENT = Path(".claude/skills/docs-reader-judgement/SKILL.md")
EXPLAIN_SKILL = Path(".claude/skills/explain/SKILL.md")
AGENTS_DIR = Path(".claude/agents")
MERMAID_SCRIPT = Path("qa_tools/common/mermaid_parse.mjs")

_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# Every rule, with the one line `--list-rules` prints. The ids must be
# exactly the set the house standard marks - tests/test_validate_explainers.py
# holds them equal in both directions.
RULES: dict[str, str] = {
    "V-sentence-length": "A sentence other than a heading is at most 25 words.",
    "V-paragraph-length": "A paragraph is at most 5 sentences.",
    "V-banned-phrase": "No word or phrase from the house standard's banned lists.",
    "V-banned-cluster": "No two watch-list words in one paragraph, list item or heading.",
    "V-semicolon": "No semicolons in prose.",
    "V-latin-abbreviation": "No eg, ie or etc in any spelling.",
    "V-negative-contraction": "No negative contractions such as don't or can't.",
    "V-midnight": "No 'midnight' - write 11:59pm.",
    "V-question-heading": "No heading ends in a question mark.",
    "V-dash": "A break in a sentence is a spaced en dash; no em dash or spaced hyphen.",
    "V-range-dash": "No hyphen or dash joining two numbers or dates - write 'to'.",
    "V-body-requirement-id": "No requirement id outside the 'where this comes from' list.",
    "V-body-code": "No inline code, and no fenced block other than Mermaid.",
    "V-body-file-path": "No repository file path outside a link target or the sources list.",
    "V-file-type": "Only .md and .yaml files under docs/explainers/.",
    "V-raw-html": "No raw HTML of any kind, including comments.",
    "V-image": "No images - every picture is a Mermaid diagram.",
    "V-external-url": "No URL of any kind: no scheme://, no //, no javascript: or data:.",
    "V-link-target": "Links are relative and resolve to an allowed, existing file.",
    "V-hidden-character": "No zero-width or bidirectional-control characters.",
    "V-in-short": "Exactly one alert block, a NOTE of 3 or 4 sentences, first after the title.",
    "V-mermaid-directive": "No click directive and nothing touching securityLevel.",
    "V-mermaid-parse": "Every Mermaid block parses in the pinned Mermaid 11.17.",
    "V-mermaid-config": "Every Mermaid block states its look and theme.",
    "V-hand-drawn-type": "handDrawn only on flowchart, state, class and ER diagrams.",
    "V-hand-drawn-seed": "A hand-drawn block uses the house seed; a plain block has none.",
    "V-caption": "Every diagram has a one-sentence italic caption on the next line.",
    "V-caption-accessible": "accTitle and accDescr both equal the caption.",
    "V-front-matter": "Every required front-matter field is present and valid.",
    "V-summary-length": "The summary is at most 160 characters.",
    "V-sign-off-record": "A signed-off page carries a full sign-off record.",
    "V-sign-off-hash": "A signed-off page has not changed since it was signed.",
    "V-build-state": "Build state, the block and heading markers agree with requirements.yaml.",
    "V-idea-page-state": "A page's own state is never 'an idea, not designed yet'.",
    "V-idea-section": "An idea section holds one sentence using an idea term.",
}

STATES = ("an idea, not designed yet", "proposed", "designed, not built yet",
          "partly built", "built")
PAGE_STATES = STATES[1:]
MARKER_TEXT = {
    "an idea, not designed yet": "Build state: an idea, not designed yet.",
    "proposed": "Build state: proposed. This design is not yet agreed and may change.",
    "designed, not built yet": "Build state: designed, not built yet.",
    "partly built": "Build state: partly built.",
}
BLOCK_LABEL = {
    "an idea, not designed yet": "An idea, not designed yet",
    "proposed": "Proposed, not yet agreed and may change",
    "designed, not built yet": "Designed, not built yet",
    "partly built": "Partly built",
    "built": "Built",
}
BLOCK_HEADER = "Build state, by section:"
SOURCES_HEADING = "where this comes from"
REQUIRED_FRONT = ("question", "summary", "group", "sources", "build_state", "status")
SIGN_OFF_FIELDS = ("by", "date", "hash", "last_reviewed", "review_by")
HAND_DRAWN_TYPES = ("flowchart", "graph", "statediagram", "statediagram-v2",
                    "classdiagram", "erdiagram")

HIDDEN = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿؜]")
URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://|(?:^|[\s(\[\"'<])//\S|\b(?:javascript|data|vbscript):",
                 re.I)
HTML = re.compile(r"<(?:[A-Za-z][A-Za-z0-9-]*[\s/>]|[A-Za-z][A-Za-z0-9-]*$|/[A-Za-z]|!)")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]*)\)")
REQ_ID = re.compile(r"\bREQ-[A-Z]+-\d+\b")
INLINE_CODE = re.compile(r"`[^`]+`")
FILE_PATH = re.compile(r"(?:\b[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+\b|\b[\w-]+\.(?:ya?ml|py|mjs|js|json|toml|sql|csv|md)\b")
LATIN = re.compile(r"\b(?:e\.?\s?g|i\.?\s?e|etc)\b\.?", re.I)
NEG_CONTRACTION = re.compile(r"\b[A-Za-z]+n['’]t\b", re.I)
MIDNIGHT = re.compile(r"\bmidnight\b", re.I)
EM_DASH = re.compile("—")
BAD_EN_DASH = re.compile(r"(?<! )–|–(?! )")
SPACED_HYPHEN = re.compile(r" - ")
PERIOD_NAME = re.compile(r"\b\d{4}-Q[1-4]\b")
RANGE = re.compile(r"\d\s*[-–—]\s*\d")
ALERT = re.compile(r"^>\s*\[!([A-Z]+)\]\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^(`{3,}|~{3,})\s*(\S*)")
WORD = re.compile(r"[A-Za-z0-9]")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


# --------------------------------------------------------- house rules


def load_house_rules(repo: Path = REPO_ROOT) -> dict:
    text = (repo / HOUSE_STANDARD).read_text()
    m = re.search(r"^```yaml house-rules\n(.*?)^```", text, re.S | re.M)
    if not m:
        raise ValueError(f"{HOUSE_STANDARD} has no ```yaml house-rules block")
    return yaml.load(m.group(1), Loader=_Loader)


def standard_rule_ids(repo: Path = REPO_ROOT) -> set[str]:
    """Every [V-...] marker in the house standard's rules (not its closing list)."""
    text = (repo / HOUSE_STANDARD).read_text().split("\n## Rule ids")[0]
    return set(re.findall(r"\[(V-[a-z-]+)\]", text))


def _word_pattern(w: str) -> re.Pattern:
    return re.compile(r"(?<![\w'])" + re.escape(w) + r"(?![\w'])", re.I)


def _banned_patterns(rules: dict) -> list[tuple[str, re.Pattern]]:
    return [(w, _word_pattern(w)) for words in (rules.get("banned") or {}).values() for w in words]


def _watch_patterns(rules: dict) -> list[tuple[str, re.Pattern]]:
    """The watch list: words that are fine alone and a tell when they
    gather (Keith, 2026-10-02). Read from the standard like the banned
    lists, so no word is ever copied into this module."""
    return [(w, _word_pattern(w)) for w in rules.get("watch") or []]


def _exemption_spans(text: str, rules: dict) -> list[tuple[int, int]]:
    spans = []
    for ex in rules.get("exemptions") or []:
        phrase = ex["phrase"] if isinstance(ex, dict) else ex
        for m in re.finditer(re.escape(phrase), text, re.I):
            spans.append(m.span())
    return spans


# -------------------------------------------------------- requirements


def load_requirement_states(repo: Path = REPO_ROOT) -> dict[str, str]:
    doc = yaml.load((repo / "requirements.yaml").read_text(), Loader=_Loader) or {}
    out = {}
    for r in doc.get("requirements") or []:
        out[r["id"]] = requirement_state(r)
    return out


def requirement_state(r: dict) -> str:
    """REQ-DOCS-116 criterion 11's derivation, and nothing else."""
    if not r.get("signed_off"):
        return "proposed"
    if r.get("status") != "built":
        return "designed, not built yet"
    return "partly built" if r.get("unmet_criteria") else "built"


def least_built(states) -> str:
    states = list(states)
    return min(states, key=STATES.index) if states else "built"


# ------------------------------------------------------------- parsing


@dataclass
class Unit:
    kind: str  # heading, paragraph, item, cell, inshort, caption
    text: str
    line: int


@dataclass
class Mermaid:
    source: str
    line: int
    caption: str | None
    caption_line: int


def split_front_matter(lines: list[str]) -> tuple[dict | None, int]:
    """(front matter, index of the first body line). None if absent or unparseable."""
    if not lines or lines[0].strip() != "---":
        return None, 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                fm = yaml.load("\n".join(lines[1:i]), Loader=_Loader)
            except yaml.YAMLError:
                return None, i + 1
            return (fm if isinstance(fm, dict) else None), i + 1
    return None, 0


def _strip_links(text: str) -> str:
    return LINK.sub(lambda m: m.group(1), text)


def sentences(text: str) -> list[str]:
    parts = [s for s in SENTENCE_END.split(text.strip()) if s.strip()]
    return parts


def word_count(sentence: str) -> int:
    return sum(1 for tok in sentence.split() if WORD.search(tok))


class Page:
    """One explainer page, split into the parts the rules talk about."""

    def __init__(self, rel: str, text: str):
        self.rel = rel
        self.text = text
        self.lines = text.split("\n")
        self.front, self.body_start = split_front_matter(self.lines)
        self.units: list[Unit] = []
        self.mermaid: list[Mermaid] = []
        self.other_fences: list[int] = []
        self.alerts: list[tuple[int, str]] = []
        self.headings: list[tuple[int, int, str]] = []  # (line, level, text)
        self.title_line: int | None = None
        self.block: list[tuple[int, str]] = []  # build-state block under the title
        self.markers: dict[int, tuple[int, str]] = {}  # heading line -> (line, text)
        self.sources_from: int | None = None  # first line of the sources section
        self.first_content_after_title: int | None = None
        self._parse()

    def _parse(self) -> None:
        lines = self.lines
        i = self.body_start
        para: list[tuple[int, str]] = []
        last_heading: int | None = None
        expecting_marker_for: int | None = None
        in_block = False

        def flush():
            if para:
                self.units.append(Unit("paragraph", " ".join(t for _, t in para), para[0][0]))
                para.clear()

        while i < len(lines):
            raw = lines[i]
            ln = i + 1
            s = raw.strip()
            fence = FENCE.match(s)
            if fence:
                flush()
                marker, info = fence.group(1), fence.group(2).lower()
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith(marker):
                    j += 1
                body = "\n".join(lines[i + 1:j])
                if info == "mermaid":
                    k = j + 1
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    nxt = lines[k].strip() if k < len(lines) else ""
                    # Only an italic line is consumed as the caption. Anything
                    # else - a heading, a paragraph - is left to be parsed as
                    # itself, and V-caption reports the missing caption.
                    cap = nxt if nxt[:1] in ("*", "_") else None
                    self.mermaid.append(Mermaid(body, ln, cap, k + 1))
                    if cap is not None and self.sources_from is None:
                        self.units.append(Unit("caption", cap.strip("*_ "), k + 1))
                    i = k + 1 if cap is not None else j + 1
                else:
                    self.other_fences.append(ln)
                    i = j + 1
                self._note_content(ln)
                expecting_marker_for = None
                in_block = False
                continue
            if not s:
                flush()
                in_block = False
                i += 1
                continue
            h = HEADING.match(s)
            if h:
                flush()
                level, text = len(h.group(1)), h.group(2)
                self.headings.append((ln, level, text))
                if level == 1 and self.title_line is None:
                    self.title_line = ln
                    expecting_marker_for = -1  # the page's own block
                else:
                    self._note_content(ln)
                    expecting_marker_for = ln
                    if text.strip().lower() == SOURCES_HEADING and self.sources_from is None:
                        self.sources_from = ln
                if self.sources_from is None or ln == self.sources_from:
                    self.units.append(Unit("heading", text, ln))
                last_heading = ln
                i += 1
                continue
            if s.startswith("Build state") and expecting_marker_for is not None:
                flush()
                if expecting_marker_for == -1:
                    self.block.append((ln, s))
                    in_block = s == BLOCK_HEADER
                else:
                    self.markers[expecting_marker_for] = (ln, s)
                i += 1
                continue
            if in_block and s.startswith("- "):
                self.block.append((ln, s))
                i += 1
                continue
            expecting_marker_for = None
            in_block = False
            self._note_content(ln)
            if self.sources_from is not None:
                i += 1
                continue
            alert = ALERT.match(s)
            if alert:
                flush()
                self.alerts.append((ln, alert.group(1)))
                j = i + 1
                box = []
                while j < len(lines) and lines[j].strip().startswith(">"):
                    box.append(lines[j].strip()[1:].strip())
                    j += 1
                self.units.append(Unit("inshort", " ".join(b for b in box if b), ln + 1))
                i = j
                continue
            if s.startswith(">"):
                para.append((ln, s[1:].strip()))
                i += 1
                continue
            if re.match(r"^([-*+]|\d+[.)])\s+", s):
                flush()
                self.units.append(Unit("item", re.sub(r"^([-*+]|\d+[.)])\s+", "", s), ln))
                i += 1
                continue
            if s.startswith("|"):
                flush()
                if not re.match(r"^\|[\s:|-]+\|?$", s):
                    for cell in s.strip("|").split("|"):
                        if cell.strip():
                            self.units.append(Unit("cell", cell.strip(), ln))
                i += 1
                continue
            para.append((ln, s))
            i += 1
        flush()
        del last_heading

    def _note_content(self, ln: int) -> None:
        if self.title_line is not None and self.first_content_after_title is None:
            self.first_content_after_title = ln

    def body_lines(self):
        """(line number, text) for every line outside front matter and the
        sources section, fences included."""
        end = (self.sources_from - 1) if self.sources_from else len(self.lines)
        for i in range(self.body_start, end):
            yield i + 1, self.lines[i]

    def sections(self) -> list[tuple[int, str]]:
        """Level-2 headings that are sections a reader could land on."""
        return [(ln, t) for ln, lvl, t in self.headings
                if lvl == 2 and ln != self.sources_from]


# --------------------------------------------------------------- hashing


def page_hash(text: str) -> str:
    """The hash of a page as signed: everything except its status, its
    build_state field, its sign-off record, the build-state block and
    every heading marker (REQ-DOCS-122 criterion 18). Those change when
    Keith signs or a cited requirement is built, which must never force
    a fresh sign-off; any change to prose or diagrams must."""
    lines = text.split("\n")
    out = []
    in_front = bool(lines) and lines[0].strip() == "---"
    skipping_record = False
    in_block = False
    for idx, line in enumerate(lines):
        s = line.strip()
        if in_front:
            if idx > 0 and s == "---":
                in_front = False
                out.append(line)
                continue
            if skipping_record and (line.startswith(" ") or line.startswith("\t")):
                continue
            skipping_record = False
            if re.match(r"^(status|build_state)\s*:", line):
                continue
            if re.match(r"^signed_off\s*:", line):
                skipping_record = True
                continue
            out.append(line)
            continue
        if s.startswith("Build state"):
            in_block = s == BLOCK_HEADER
            continue
        if in_block and s.startswith("- "):
            continue
        in_block = False
        out.append(line)
    # Collapse blank-line runs, so removing a build-state line (and the
    # blank line that separated it) is not itself a change.
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return hashlib.sha256(body.encode()).hexdigest()


# -------------------------------------------------------------- checks


class Validator:
    def __init__(self, repo: Path = REPO_ROOT):
        self.repo = repo
        self.rules = load_house_rules(repo)
        self.banned = _banned_patterns(self.rules)
        self.watch = _watch_patterns(self.rules)
        self.seed = self.rules.get("hand_drawn_seed")
        self._req_states: dict[str, str] | None = None
        self._tracked: set[str] | None = None
        self._idea_terms: list[str] | None = None
        self.findings: list[Finding] = []
        self.mermaid_jobs: list[tuple[str, int, str]] = []

    # lazy loads
    @property
    def req_states(self) -> dict[str, str]:
        if self._req_states is None:
            self._req_states = load_requirement_states(self.repo)
        return self._req_states

    @property
    def tracked(self) -> set[str]:
        if self._tracked is None:
            try:
                out = subprocess.run(["git", "ls-files"], cwd=self.repo, capture_output=True,
                                     text=True, check=True).stdout
                self._tracked = set(out.splitlines())
            except (OSError, subprocess.CalledProcessError):
                self._tracked = set()
        return self._tracked

    @property
    def idea_terms(self) -> list[str]:
        if self._idea_terms is None:
            terms: list[str] = []
            if (self.repo / EXPLAINERS / "glossary.yaml").exists():
                from qa_tools.common import explainers
                try:
                    for e in explainers.load_glossary(self.repo).entries:
                        if e.idea:
                            terms += [e.term, *e.aliases]
                except Exception:  # noqa: BLE001 - reported by check_glossary
                    pass
            self._idea_terms = [t for t in terms if t]
        return self._idea_terms

    def add(self, path: str, line: int, rule: str, message: str) -> None:
        self.findings.append(Finding(path, line, rule, message))

    # ---- whole run

    def run(self) -> list[Finding]:
        root = self.repo / EXPLAINERS
        if root.exists():
            for f in sorted(root.rglob("*")):
                if f.is_dir():
                    continue
                rel = f.relative_to(self.repo)
                if rel == WORK or WORK in rel.parents:
                    continue
                self.check_file(rel)
        self.check_glossary()
        for extra in (HOUSE_STANDARD, READER_JUDGEMENT, EXPLAIN_SKILL):
            if (self.repo / extra).exists():
                self.check_hidden(extra)
        if (self.repo / AGENTS_DIR).exists():
            for a in sorted((self.repo / AGENTS_DIR).glob("docs-*.md")):
                self.check_hidden(a.relative_to(self.repo))
        self.run_mermaid()
        return sorted(self.findings, key=lambda f: (f.path, f.line, f.rule))

    def check_glossary(self) -> None:
        """REQ-DOCS-119: the strict schema, the alias and idea rules, and
        that the committed glossary.md is what the generator would write.
        These are configuration checks rather than rules of the house
        standard, so they report under their own names, outside the V-
        rule set the standard marks."""
        from qa_tools.common import explainers

        path = str(EXPLAINERS / "glossary.yaml")
        if not (self.repo / EXPLAINERS / "glossary.yaml").exists():
            return
        try:
            glossary = explainers.load_glossary(self.repo)
        except explainers.ValidationError as exc:
            for err in exc.errors():
                where = ".".join(str(x) for x in err["loc"])
                self.add(path, 1, "glossary-schema", f"{where}: {err['msg']}")
            return
        except yaml.YAMLError as exc:
            self.add(path, 1, "glossary-schema", f"glossary.yaml does not parse: {exc}")
            return
        for problem in explainers.glossary_problems(glossary, set(self.req_states)):
            self.add(path, 1, "glossary", problem)
        if not explainers.glossary_is_current(self.repo):
            self.add(str(EXPLAINERS / "glossary.md"), 1, "glossary-stale",
                     "glossary.md is out of date - run 'mothman docs glossary' and commit the result")
        md = self.repo / EXPLAINERS / "glossary.md"
        if md.exists():
            page = Page(str(EXPLAINERS / "glossary.md"), md.read_text())
            for m in page.mermaid:
                self.check_mermaid(page, m)

    def check_hidden(self, rel: Path) -> None:
        for n, line in enumerate((self.repo / rel).read_text().split("\n"), 1):
            if HIDDEN.search(line):
                self.add(str(rel), n, "V-hidden-character",
                         "remove the zero-width or bidirectional-control character on this line")

    def check_file(self, rel: Path) -> None:
        if rel.suffix not in (".md", ".yaml"):
            self.add(str(rel), 1, "V-file-type",
                     f"only .md and .yaml files may live under {EXPLAINERS}/ - remove this file")
            return
        text = (self.repo / rel).read_text()
        self.check_hidden(rel)
        self.check_safety(str(rel), text.split("\n"))
        if rel.suffix == ".md" and rel.name != "glossary.md":
            self.check_page(rel, text)

    def check_safety(self, path: str, lines: list[str]) -> None:
        for n, line in enumerate(lines, 1):
            if URL.search(line):
                self.add(path, n, "V-external-url",
                         "remove the URL - link only by relative path, and never write an address")
            if HTML.search(line):
                self.add(path, n, "V-raw-html", "remove the raw HTML - write plain markdown instead")
            if IMAGE.search(line):
                self.add(path, n, "V-image", "remove the image - draw a Mermaid diagram instead")

    # ---- a page

    def check_page(self, rel: Path, text: str) -> None:
        path = str(rel)
        page = Page(path, text)
        self.check_front(page)
        self.check_in_short(page)
        self.check_links(page, rel)
        self.check_body_rules(page)
        self.check_prose(page)
        for m in page.mermaid:
            self.check_mermaid(page, m)
        self.check_build_state(page)

    def check_front(self, page: Page) -> None:
        fm = page.front
        if fm is None:
            self.add(page.rel, 1, "V-front-matter",
                     "add front matter between two '---' lines at the top of the page")
            return
        for key in REQUIRED_FRONT:
            if key not in fm or fm[key] in (None, "", []):
                self.add(page.rel, 1, "V-front-matter", f"add the front-matter field '{key}'")
        if fm.get("build_state") not in (None, *PAGE_STATES, STATES[0]):
            self.add(page.rel, 1, "V-front-matter",
                     f"set build_state to one of: {', '.join(PAGE_STATES)}")
        if fm.get("status") not in (None, "draft", "signed off"):
            self.add(page.rel, 1, "V-front-matter", "set status to 'draft' or 'signed off'")
        summary = fm.get("summary")
        if isinstance(summary, str) and len(summary) > 160:
            self.add(page.rel, 1, "V-summary-length",
                     f"shorten the summary to 160 characters or fewer (it is {len(summary)})")
        if fm.get("status") == "signed off":
            rec = fm.get("signed_off")
            missing = [k for k in SIGN_OFF_FIELDS if not isinstance(rec, dict) or not rec.get(k)]
            if missing:
                self.add(page.rel, 1, "V-sign-off-record",
                         f"a signed-off page needs its sign-off record - missing {', '.join(missing)}")
            elif str(rec["hash"]) != page_hash(page.text):
                self.add(page.rel, 1, "V-sign-off-hash",
                         "this page has changed since Keith signed it off and needs his fresh sign-off")

    def check_in_short(self, page: Page) -> None:
        if len(page.alerts) != 1:
            self.add(page.rel, page.alerts[1][0] if len(page.alerts) > 1 else 1, "V-in-short",
                     "a page has exactly one alert block, the 'In short' box")
            return
        ln, kind = page.alerts[0]
        if kind != "NOTE":
            self.add(page.rel, ln, "V-in-short", "make the 'In short' box a [!NOTE] alert")
        if page.first_content_after_title != ln:
            self.add(page.rel, ln, "V-in-short",
                     "put the 'In short' box first, straight after the title and any build-state block")
        box = next(u for u in page.units if u.kind == "inshort")
        n = len(sentences(_strip_links(box.text)))
        if n not in (3, 4):
            self.add(page.rel, ln, "V-in-short", f"write the 'In short' box in 3 or 4 sentences (it has {n})")

    def check_links(self, page: Page, rel: Path) -> None:
        explainers = (self.repo / EXPLAINERS).resolve()
        work = (self.repo / WORK).resolve()
        repo = self.repo.resolve()
        for n, line in enumerate(page.lines, 1):
            if n <= page.body_start:
                continue
            in_sources = page.sources_from is not None and n > page.sources_from
            for m in LINK.finditer(line):
                target = m.group(2).split("#", 1)[0]
                if not target or target.startswith("/") or ":" in target:
                    if not target and m.group(2).startswith("#"):
                        continue
                    self.add(page.rel, n, "V-link-target", f"make '{m.group(2)}' a relative path")
                    continue
                resolved = ((self.repo / rel).parent / target).resolve()
                ok = resolved.exists() and resolved.is_file()
                if in_sources:
                    rrel = resolved.relative_to(repo).as_posix() if resolved.is_relative_to(repo) else None
                    ok = ok and rrel is not None and rrel in self.tracked and not any(
                        rrel == d or rrel.startswith(d + "/") for d in ("data", "reports", WORK.as_posix()))
                    where = "a committed repository file outside data/, reports/ and _work/"
                else:
                    ok = ok and resolved.is_relative_to(explainers) and not resolved.is_relative_to(work)
                    where = f"an existing file inside {EXPLAINERS}/, outside _work/"
                if not ok:
                    self.add(page.rel, n, "V-link-target", f"point '{m.group(2)}' at {where}")

    def check_body_rules(self, page: Page) -> None:
        mermaid_lines = set()
        for m in page.mermaid:
            mermaid_lines.update(range(m.line, m.line + m.source.count("\n") + 3))
        for fence_ln in page.other_fences:
            self.add(page.rel, fence_ln, "V-body-code",
                     "remove the code block - only Mermaid blocks belong on a page")
        for n, line in page.body_lines():
            if REQ_ID.search(line):
                self.add(page.rel, n, "V-body-requirement-id",
                         "move the requirement id into the 'where this comes from' list")
            if n in mermaid_lines:
                continue
            if INLINE_CODE.search(line):
                self.add(page.rel, n, "V-body-code", "remove the inline code - say it in words")
            if FILE_PATH.search(LINK.sub(lambda mm: mm.group(1), line)):
                self.add(page.rel, n, "V-body-file-path",
                         "move the file path into the 'where this comes from' list")

    def check_prose(self, page: Page) -> None:
        for u in page.units:
            text = _strip_links(u.text)
            text = INLINE_CODE.sub("", text)
            if u.kind == "heading" and text.rstrip().endswith("?"):
                self.add(page.rel, u.line, "V-question-heading", "rewrite the heading as a statement")
            if ";" in text:
                self.add(page.rel, u.line, "V-semicolon", "split the sentence in two instead of using a semicolon")
            if LATIN.search(text):
                self.add(page.rel, u.line, "V-latin-abbreviation",
                         "write 'for example' or 'that is', or name every item")
            if NEG_CONTRACTION.search(text):
                self.add(page.rel, u.line, "V-negative-contraction",
                         f"write '{NEG_CONTRACTION.search(text).group(0)}' in full")
            if MIDNIGHT.search(text):
                self.add(page.rel, u.line, "V-midnight", "write the time as 11:59pm")
            if EM_DASH.search(text) or BAD_EN_DASH.search(text) or SPACED_HYPHEN.search(text):
                self.add(page.rel, u.line, "V-dash",
                         "mark a break with a spaced en dash ( – ) and nothing else")
            if RANGE.search(PERIOD_NAME.sub("PERIOD", text)):
                self.add(page.rel, u.line, "V-range-dash", "join the two numbers or dates with 'to'")
            spans = _exemption_spans(text, self.rules)
            for word, pat in self.banned:
                for m in pat.finditer(text):
                    if not any(a <= m.start() and m.end() <= b for a, b in spans):
                        self.add(page.rel, u.line, "V-banned-phrase",
                                 f"replace '{m.group(0)}', which is on the house standard's banned list")
            gathered = [m.group(0) for _, pat in self.watch for m in pat.finditer(text)
                        if not any(a <= m.start() and m.end() <= b for a, b in spans)]
            if len(gathered) >= 2:
                self.add(page.rel, u.line, "V-banned-cluster",
                         "reword so at most one watch-list word is left here - found "
                         + ", ".join(f"'{w}'" for w in gathered))
            sents = sentences(text)
            if u.kind != "heading":
                for s in sents:
                    if word_count(s) > 25:
                        self.add(page.rel, u.line, "V-sentence-length",
                                 f"split this {word_count(s)}-word sentence - the limit is 25")
            if u.kind == "paragraph" and len(sents) > 5:
                self.add(page.rel, u.line, "V-paragraph-length",
                         f"split this {len(sents)}-sentence paragraph - the limit is 5")

    # ---- Mermaid

    def check_mermaid(self, page: Page, m: Mermaid) -> None:
        src = m.source
        config: dict = {}
        diagram = src
        fm = re.match(r"^\s*---\n(.*?)\n---\n(.*)$", src, re.S)
        if fm:
            try:
                meta = yaml.load(fm.group(1), Loader=_Loader) or {}
                config = meta.get("config") or {}
            except yaml.YAMLError:
                config = {}
            diagram = fm.group(2)
        if re.search(r"^\s*click\s", diagram, re.M) or "%%{" in src or "securityLevel" in src:
            self.add(page.rel, m.line, "V-mermaid-directive",
                     "remove the click or init directive - diagrams carry no links or settings of their own")
        look, theme = config.get("look"), config.get("theme")
        if not look or not theme:
            self.add(page.rel, m.line, "V-mermaid-config", "state both look and theme in the block's config")
        first = next((ln.strip() for ln in diagram.split("\n") if ln.strip()), "")
        dtype = first.split()[0].lower() if first else ""
        if look == "handDrawn":
            if dtype not in HAND_DRAWN_TYPES:
                self.add(page.rel, m.line, "V-hand-drawn-type",
                         f"use the classic look on a {dtype or 'diagram'} - handDrawn is only for "
                         "flowchart, state, class and ER diagrams")
            if config.get("handDrawnSeed") != self.seed:
                self.add(page.rel, m.line, "V-hand-drawn-seed", f"set handDrawnSeed to the house seed, {self.seed}")
        elif look is not None and look != "classic":
            self.add(page.rel, m.line, "V-mermaid-config", "set look to handDrawn or classic")
        elif "handDrawnSeed" in config:
            self.add(page.rel, m.line, "V-hand-drawn-seed", "remove handDrawnSeed from a plain block")
        cap = m.caption
        cap_ok = bool(cap) and bool(re.fullmatch(r"\*[^*].*[^*]\*|_[^_].*[^_]_", cap or ""))
        cap_text = (cap or "").strip("*_ ")
        if not cap_ok or len(sentences(cap_text)) != 1:
            self.add(page.rel, m.caption_line if cap else m.line, "V-caption",
                     "put a one-sentence caption, wholly in italics, on the first line after the diagram")
        norm = lambda s: " ".join(s.split())  # noqa: E731
        acc = {k: norm(v) for k, v in re.findall(r"^\s*(accTitle|accDescr)\s*:\s*(.*)$", diagram, re.M)}
        if cap_ok and (acc.get("accTitle") != norm(cap_text) or acc.get("accDescr") != norm(cap_text)):
            self.add(page.rel, m.line, "V-caption-accessible",
                     "copy the caption's text into the block as both accTitle and accDescr")
        self.mermaid_jobs.append((page.rel, m.line, src))

    def run_mermaid(self) -> None:
        if not self.mermaid_jobs:
            return
        node = shutil.which("node")
        # The tooling always comes from this checkout, whichever tree is
        # being validated - tests validate a temporary tree.
        mod = REPO_ROOT / "node_modules" / "mermaid" / "package.json"
        if not node or not mod.exists():
            missing = "Node" if not node else "the pinned mermaid package"
            for path, line, _ in self.mermaid_jobs:
                self.add(path, line, "V-mermaid-parse",
                         f"cannot check this diagram: {missing} is not installed - run 'npm ci' "
                         "and try again (the check is never skipped)")
            return
        payload = [{"id": f"{i}", "source": src} for i, (_, _, src) in enumerate(self.mermaid_jobs)]
        proc = subprocess.run([node, str(REPO_ROOT / MERMAID_SCRIPT)], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=REPO_ROOT)
        if proc.returncode != 0:
            for path, line, _ in self.mermaid_jobs:
                self.add(path, line, "V-mermaid-parse",
                         f"the Mermaid check failed to run: {proc.stderr.strip()[:200]}")
            return
        for res in json.loads(proc.stdout):
            if not res["ok"]:
                path, line, _ = self.mermaid_jobs[int(res["id"])]
                first = res["error"].split("\n")[0]
                self.add(path, line, "V-mermaid-parse", f"fix the diagram so Mermaid 11.17 parses it: {first}")

    # ---- build state

    def check_build_state(self, page: Page) -> None:
        fm = page.front or {}
        sources = [s for s in (fm.get("sources") or []) if isinstance(s, str)]
        req_ids = [s for s in sources if REQ_ID.fullmatch(s)]
        for rid in req_ids:
            if rid not in self.req_states:
                self.add(page.rel, 1, "V-build-state", f"{rid} is not in requirements.yaml")
        page_state = least_built(self.req_states.get(r, "proposed") for r in req_ids)
        if fm.get("build_state") in (STATES[0],) or any(
                s == MARKER_TEXT[STATES[0]] for _, s in page.block[:1]):
            self.add(page.rel, 1, "V-idea-page-state", "a page's own state is never 'an idea, not designed yet'")
        if fm.get("build_state") and fm.get("build_state") != page_state:
            self.add(page.rel, 1, "V-build-state",
                     f"set build_state to '{page_state}', which its cited requirements give it")

        section_sources = fm.get("section_sources") or {}
        states: dict[str, str] = {}
        idea_sections: list[tuple[int, str]] = []
        # The page's opening - everything between the title and its first
        # section - is a section too, named by the title. Without it a
        # page whose body and later sections differ lost its body's state.
        title = next((t for ln, lvl, t in page.headings if lvl == 1), None)
        if title is not None:
            reqs = section_sources.get(title)
            states[title] = (least_built(self.req_states.get(r, "proposed") for r in reqs)
                             if reqs else page_state)
        for ln, heading in page.sections():
            marker = page.markers.get(ln)
            if marker and marker[1] == MARKER_TEXT[STATES[0]]:
                states[heading] = STATES[0]
                idea_sections.append((ln, heading))
                continue
            reqs = section_sources.get(heading)
            if reqs:
                states[heading] = least_built(self.req_states.get(r, "proposed") for r in reqs)
            else:
                states[heading] = page_state
        for heading in section_sources:
            if heading not in states:
                self.add(page.rel, 1, "V-build-state",
                         f"section_sources names '{heading}', which is not a section heading on the page")

        # heading markers
        for ln, heading in page.sections():
            want = None if states[heading] == "built" else MARKER_TEXT[states[heading]]
            got = page.markers.get(ln, (None, None))[1]
            if want != got:
                self.add(page.rel, ln, "V-build-state",
                         f"put '{want}' under this heading" if want else
                         "remove the build-state marker - this section is built")

        # the block under the title
        distinct = set(states.values()) or {page_state}
        block_lines = [s for _, s in page.block]
        if distinct == {"built"} and page_state == "built":
            expected: list[str] = []
        elif len(distinct) == 1:
            only = next(iter(distinct))
            expected = [MARKER_TEXT.get(only, "")] if only != "built" else []
        else:
            expected = [BLOCK_HEADER]
            for st in STATES:
                names = [h for h, s in states.items() if s == st]
                if names:
                    expected.append(f"- {BLOCK_LABEL[st]}: " + ", ".join(f'"{h}"' for h in names) + ".")
        if block_lines != expected:
            where = page.block[0][0] if page.block else (page.title_line or 1)
            self.add(page.rel, where, "V-build-state",
                     "the build-state block under the title should read: " +
                     (" | ".join(expected) if expected else "(no block - the page is built)"))

        # idea sections
        for ln, heading in idea_sections:
            body = [u for u in page.units if u.kind in ("paragraph", "item")
                    and ln < u.line < self._next_heading_line(page, ln)]
            text = " ".join(u.text for u in body)
            if len(sentences(text)) != 1 or not any(
                    re.search(r"\b" + re.escape(t) + r"\b", text, re.I) for t in self.idea_terms):
                self.add(page.rel, ln, "V-idea-section",
                         "an idea section holds exactly one sentence, using a term marked as an idea in the glossary")

    @staticmethod
    def _next_heading_line(page: Page, after: int) -> int:
        later = [ln for ln, _, _ in page.headings if ln > after]
        return later[0] if later else len(page.lines) + 1


def validate(repo: Path = REPO_ROOT) -> list[Finding]:
    return Validator(repo).run()


def main(argv: list[str] | None = None) -> int:
    findings = validate()
    for f in findings:
        print(f.render())
    if findings:
        print(f"explainer validation FAILED - {len(findings)} finding(s).")
        return 1
    print("explainer validation OK - zero findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
