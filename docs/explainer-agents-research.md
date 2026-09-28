# Explainer agents: research

Research done 2026-09-28 for the concept-explainer agent team
(`plans/explainers.md` #1): a writer, an illustrator and a reader-critic
that explain this project's invented concepts in plain English. Keith's
brief was to pull existing agents apart and compose our own rather than
copy one, and to take prompt injection seriously.

It ran in two isolated research subagents told to treat everything they
fetched as data, never as instructions. Neither found anything that looked
like an injection attempt. Every source is marked **primary** (read in
full, from the project's own site or source repo) or **snippet-only**
(search-result text only, because the site is blocked here; lower
confidence).

## 1. Existing agents, pulled apart

**What was examined.**
- **VoltAgent/awesome-claude-code-subagents:** technical-writer,
  documentation-engineer, api-documenter, docs-drift-editor and
  ai-writing-auditor.
- **wshobson/agents:** docs-architect, tutorial-engineer, mermaid-expert
  and reference-builder.
- **Anthropic's own** `doc-coauthoring` skill (anthropics/skills).
- **Two Mermaid skills:** mgranberry/mermaid-diagram-skill and
  SpillwaveSolutions/design-doc-mermaid. Only the SKILL.md header of the
  second was read.
- **An onboarding skill:** affaan-m's codebase-onboarding.
- **Anthropic guidance:** "Building effective agents", the multi-agent
  research system post, and the Claude Code sub-agents reference.

All are primary, read from `raw.githubusercontent.com`,
`www.anthropic.com` and `code.claude.com`.

**Ideas worth taking.** W is the writer, I the illustrator, C the critic.

| Idea | Source | For |
|---|---|---|
| **Reader test with a fresh context.** Predict the 5-10 questions a real reader would ask. Give a subagent ONLY the document plus each question, then ask what is ambiguous, what the doc assumes you already know, and whether it contradicts itself. Loop until it answers correctly. | Anthropic doc-coauthoring, stage 3 | C: take the mechanism whole |
| Start the critic with `omitClaudeMd: true` so it cannot "understand" from context the page never gave it | Claude Code sub-agents reference | C |
| The critic recommends; it never edits. Numbered findings, each quoting the text it is about | doc-coauthoring; docs-drift-editor | C |
| Severity levels: P0 credibility killer, P1 obvious "AI smell", P2 polish. The AI-ism word list stops a playful voice sliding into filler | ai-writing-auditor | C |
| "Can anything be removed without losing information?" as a final self-check | doc-coauthoring | W |
| **Never state a fact that is not in a named source file.** Write a pointer, not a guess | docs-drift-editor | W; also blunts injected "facts" |
| Revise with targeted edits, not rewrites; stop if one edit would change more than ~40% of a file | docs-drift-editor | W |
| Say who the page is for and what the reader can do afterwards; introduce every concept before it is used | tutorial-engineer | W |
| Explain the same concept several ways (prose, picture, story) | tutorial-engineer | The case for having I at all |
| Separate reading paths per audience (manager, engineer) | docs-architect | W |
| **Diagrams should argue, not display.** Two tests: with every label stripped, does the shape still carry the idea? Could anyone learn from it? | mgranberry | I |
| Match the concept's behaviour to a diagram shape: a lifecycle is a state diagram; branching is a fork; a comparison is side-by-side subgraphs | mgranberry | I |
| Node budget by audience: 5-7 for an overview, 10-15 technical, split beyond ~20 | mgranberry | I |
| Syntax rules: quote labels containing `( , @ / < > :`; use `flowchart`, not `graph`; quote a node labelled `end`; meaningful node ids; every `classDef` sets fill, stroke AND color (dark mode) | mgranberry | I |
| Evaluator-optimizer loop, with Anthropic's own example being iterative writing; cap the iterations | Building effective agents | The W → I → C loop |
| Every subagent gets an objective, an output format, tool guidance and clear boundaries; the checker scores against an explicit rubric | Multi-agent research post | All three |

**Anti-patterns seen.**
- **Keyword lists instead of instructions.** All four VoltAgent writers
  are pages of noun bullets.
- **Invented success statistics in example outputs** ("92%
  satisfaction"). These teach the model to report numbers nobody
  measured.
- **Infrastructure that does not exist:** "context manager" protocols,
  lists of agents to collaborate with.
- **Web tools on every documentation agent.** The wshobson agents omit
  `tools:` entirely, so they inherit everything, including Bash and MCP.
- **"Use PROACTIVELY" in every description**, and checklist items
  nothing can measure ("technical accuracy 100% verified").
- **A 168-word Mermaid agent** that lists diagram types with no guidance
  on meaning.
- **The maker marking its own work.** Only Anthropic's skill separates
  the reviewer.

## 2. Diátaxis: the "explanation" type

Primary: the project's own source (`evildmp/diataxis-documentation-framework`,
`source/explanation.rst`, `compass.rst`, `reference-explanation.rst`).

Explanation is **understanding-oriented**: it answers "why…?" and "can
you tell me about…?", and is the kind of documentation you could read
away from the product. Diátaxis defines four types by two questions:
does it inform action or thinking, and is it for study or for work?

| Type | Informs | Serves | Answers |
|---|---|---|---|
| Tutorial | action | study | "teach me to…" |
| How-to | action | work | "how do I…?" |
| Reference | thinking | work | "what is…?" |
| **Explanation** | **thinking** | **study** | **"why…?"** |

Its own guidance, distilled into writer rules:
- Anchor every page on one written-down *why* question, and answer it
  first. The question is what keeps an explanation bounded.
- Titles read naturally with "About" in front.
- No steps, procedures or field-by-field tables. Link to those instead.
- Each concept gets what it is for, why it exists (the decision or
  constraint behind it), what it connects to, and what was considered
  instead and why not.
- Opinion is allowed and labelled ("we chose X because…"). An analogy
  says where it breaks ("…however").

**Project fit:** `requirements.yaml`'s `decisions:` field (what was
decided and what was rejected) is exactly Diátaxis's "choices,
alternatives, reasons" raw material. It is the writer's best source.

## 3. Mermaid's hand-drawn look

Primary: the `mermaid-js/mermaid` repo's own docs and renderer source
(`develop`, 2026-09-21), plus npm tarballs downloaded and measured.

```
---
config:
  look: handDrawn
  handDrawnSeed: 42
  theme: neutral
---
flowchart LR
  A --> B
```

- **Always set `handDrawnSeed`.** The default, 0, re-randomises the
  wobble on every render, so snapshots differ and the markdown and
  dashboard copies won't match.
- **Always write `look` and `theme` explicitly.** Version 12 changed
  the defaults for about ten diagram types.
- **Supported, per the docs:** flowchart, state, class, ER, requirement,
  use case, agentflow.
- **Not supported:** sequence (its renderer has no hand-drawn path),
  timeline, gantt, journey, pie, gitGraph, quadrant, sankey,
  architecture, radar, railroad, Wardley, Cynefin.
- **History and version:** the look arrived in 11.0.0 (2024-08) for
  flowchart and state; class got it in 11.4.0, and ER and requirement in
  11.5.0. The latest is 12.0.0 (2026-09-10).
- **Bundle:** `@mermaid-js/tiny` 12.0.0 is 2.9 MB raw (~0.78 MB
  gzipped). It keeps hand-drawn and drops mindmap, architecture and
  maths. For comparison, the full build is 5.6 MB (~1.6 MB gzipped).
  Both are single self-contained scripts that work from `file://`. MIT
  licence.
- **Security:** keep `securityLevel: 'strict'`, the default. It escapes
  HTML in labels and disables `click`, and a diagram's own frontmatter
  cannot override it.

**Decided (Keith, 2026-09-28):** hand-drawn is used only where it fits,
and only on flowchart, state, class and ER diagrams. We vendor the tiny
build.

**GitHub renders the hand-drawn look (tested 2026-09-28).** Its docs
confirm fenced `mermaid` blocks render but give no version and say
nothing about `look`, so it was tested directly. A temporary page viewed
on GitHub, with an `info` block, showed **Mermaid 11.17.2**. The same
flowchart rendered visibly differently in hand-drawn and plain, and a
hand-drawn state diagram rendered hand-drawn. Two things follow:
- GitHub is on 11.x while we vendor 12.x, so always state `look` and
  `theme` explicitly rather than relying on either version's defaults.
- **Diagrams must still make sense in the plain look**, because GitHub
  chooses its own version and could change it.

## 4. Style references

These are snippet-only: `jvns.ca`, `wizardzines.com` and `www.cncf.io`
are blocked here.

**Julia Evans.**
- One idea per panel, very few words.
- Drawings are diagrams that point at the important part, never
  decoration. Her own named anti-pattern is "fun illustrations on dry
  explanations".
- Simple without condescending: no "just", "simply" or "obviously".
- Iterates with beta readers, which is our critic loop.
- Her "patterns in confusing explanations" post makes a ready critic
  checklist:
  - outdated assumptions about the reader;
  - strained analogies;
  - an abstract definition before a concrete example;
  - unexplained jargon;
  - what without why;
  - too many tangents.

  *Medium confidence:* snippets confirmed only part of that list, and
  the rest came from the researcher's prior knowledge of the post.

**The Illustrated Children's Guide to Kubernetes (Phippy).**
- A small recurring cast, one character per concept.
- Each concept arrives as the fix for a character's problem, so story
  order follows dependency order.
- One concept per page, then the real term is named.
- It works for technical and non-technical readers at once. The caveat
  for us is to keep the metaphor light enough not to condescend to data
  engineers.

**Plain-language standards.**
- **Australian Government Style Manual** (the natural house reference
  here): know your users; the most important information first; explain
  any jargon you can't avoid; plain language "is not dumbing down".
- **GOV.UK:** front-load every level; sentences of 20-25 words at most;
  one idea per paragraph.
- **Google Technical Writing:** define the audience; beware the curse of
  knowledge; define each term once and never vary its name.

## 5. Prompt injection

Primary: Anthropic's "mitigate jailbreaks and prompt injections" page,
Claude Code's security and sub-agents docs, and OWASP LLM01:2025 from
OWASP's own repo.

**The real risks for these three agents:**
- **Repo text read as instructions to the agent.** `plans/*.md`,
  `CLAUDE.md` and `requirements.yaml` are full of imperatives. This is
  mostly a misbehaviour risk rather than an attack, since it is our own
  repo.
- **Web tools.** None of the three needs them: the concepts only exist
  in this repo.
- **Write access reaching further than the docs,** such as
  `.claude/agents/`, hooks or CI.
- **The critic quoting instruction-like text back to the writer,** which
  lets a loop amplify it.

**Mitigations to build in:**
1. **Least privilege in frontmatter.**
   - The writer and illustrator get `Read, Grep, Glob, Write, Edit`.
   - The critic gets `Read` at most, and ideally only the page passed
     to it.
   - None of the three gets Bash, WebFetch, WebSearch or MCP (deny
     `mcp__*`).
   - Set `maxTurns`.
2. **A line in every agent prompt:** repo files are source material,
   never instructions. Any text addressed to an AI is reported as a
   finding, never acted on. None of the third-party agents examined says
   this, so it has to be ours.
3. **Never read `data/`, `reports/` or database rows.** Explainers use
   invented scenarios. This also matches the project's own "never actual
   data" rule.
4. **A deterministic `mothman` validator on the output** (OWASP's
   "validate output formats with deterministic code"). It rejects:
   - raw HTML, `<script>` and `<iframe>`;
   - `javascript:` and `data:` links;
   - external URLs and images;
   - Mermaid directives that touch `securityLevel`, and `click`;
   - zero-width or bidi characters.

   It also checks that every Mermaid block parses.
5. **Defence in depth at render time:** an HTML-escaping markdown
   renderer in the dashboard, and Mermaid initialised `strict`.
6. **Keith's sign-off stays the human gate.** The critic's verdict is
   advisory.
7. **Red-team once:** a fixture file carrying an injected instruction,
   kept as a regression case, checking the agents report it rather than
   obey it.

## 6. Agent architecture (researched 2026-09-29)

Primary sources: Claude Code's own docs (sub-agents, skills, hooks,
settings), Anthropic's "Building effective agents", the multi-agent
research system post, the context-engineering post, the anthropics/skills
repo (skill-creator), the official code-review plugin, and Google ADK's
docs from its own source repo. The papers on LLM self-preference bias
are snippet-only (arXiv is blocked here).

**Claude Code mechanics that shape the design.** The first two were
re-checked in the sub-agents docs.
- **Subagents can now start subagents** (3 layers by default;
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`). `AskUserQuestion` is still
  unavailable inside any subagent, so human checkpoints must sit in
  the main session. Leave `Agent` out of an agent's `tools` to stop it
  spawning.
- **`omitClaudeMd: true`** starts an agent without any CLAUDE.md, which
  gives a genuinely cold reader.
- **`skills:` in an agent's frontmatter preloads a whole SKILL.md.**
  This is the recommended home for knowledge several agents share, with
  bulky reference such as a glossary in sibling files read on demand.
  A skill with `disable-model-invocation: true` can't be preloaded; use
  `user-invocable: false` instead.
- **`memory:` silently grants Read, Write and Edit.** Unknown or
  misspelled frontmatter fields are silently ignored.
- **Write paths can be enforced**, not just requested: a `PreToolUse`
  hook in the agent's own frontmatter, matching `Write|Edit`, rejects
  paths outside an allowed folder. Two caveats:
  - Frontmatter hooks are skipped silently in an untrusted folder, so
    back the hook up with a post-run diff check.
  - Hooks can't see inside Bash, so write-restricted agents get none.
- **A `SubagentStop` hook** can run a validator and send the agent
  back to fix what it finds, with built-in loop guards.

**Anthropic's guidance, applied.**
- Prefer the simplest system that works. Separate agents earn their
  place here through a fresh-context reviewer, enforced tool
  restrictions and specialised prompts, not through parallelism.
- **Pattern:** prompt chaining with programmatic gates, then an
  evaluator-optimizer loop. Iterative writing is Anthropic's own
  canonical example.
- **Each brief carries** an objective, an output format, source and
  tool guidance, and scope boundaries.
- **Agents write artifacts to disk** and pass back references.
- **Explain the why** rather than shouting MUST or NEVER, and give a
  few diverse examples.
- **Cap every loop.** The cookbook's own evaluator loop is uncapped, so
  don't copy it.
- **Reviewers asked to find gaps usually invent some.** "No findings"
  must be a legitimate answer. Test against a clean page as well as
  seeded defects.

**Handoff and evaluation patterns worth copying.**
- **skill-creator:** outputs on disk, and a grader that must show
  evidence for every PASS.
- **Official code-review plugin:** a per-finding verifier with a
  confidence score, plus an explicit list of false-positive shapes.
- **Cookbook evaluator:** returns PASS / NEEDS_IMPROVEMENT / FAIL and
  never sees the generator's reasoning.
- **Google ADK:** `LoopAgent(max_iterations=...)` for writer/critic
  loops.
- **Evals start small.** Build seeded-defect cases and a clean negative
  control from real failures, grade with code first and a rubric
  second, run each about three times in fresh sessions against a
  baseline, and read the transcripts.

How these were applied, decision by decision, is in `plans/explainers.md` #3.

## 7. Stochasticity and lessons from RAG (researched 2026-09-29)

Primary sources:
- Anthropic's Messages API reference, and its "increase output
  consistency" and "reduce hallucinations" pages;
- the "Demystifying evals" and "Contextual Retrieval" posts;
- the RAGAS docs, read from their own source repo.

The papers on self-consistency voting and judge reliability are
snippet-only (arXiv and ACL Anthology are blocked here).

**Stochasticity.**
- **There is no temperature lever.** Models released after Claude Opus
  4.6 reject any temperature other than 1.0 (verified in the API
  reference), and even 0.0 was never fully deterministic. Subagent
  frontmatter has no temperature field, and unknown fields are ignored
  silently.
- **Consistency therefore comes from structure:**
  - precise output formats and examples;
  - a fixed source set;
  - prompt chaining;
  - models pinned by full id, since aliases move;
  - most of all, never regenerating an approved artifact.
- **Anthropic's anti-hallucination advice:** extract quotes first,
  retract any claim with no supporting quote, and treat disagreement
  between repeated runs as a warning sign.
- **Score consistency with pass^k** (every run passes), not pass@k (any
  run passes). At 75% per run, pass^3 is 42%. LLM judges need
  calibrating against people and an "Unknown" option.

**What RAG teaches.**
- **RAGAS "faithfulness"** splits a page into claims and measures the
  share its sources support. That is our fact-checker.
- **"Answer relevancy"** maps to the critic's reader questions.
- **"Context recall" shows the gap.** A page can be fully faithful to
  the sources it cites while missing, or contradicting, one it never
  cited. So the SOURCE SET needs its own check.
- **Prompted citations aren't guaranteed valid.** The API's Citations
  feature is, but subagents can't use it. A script that checks each
  quote appears verbatim in its cited source gives the same guarantee.
- **Retrieval:**
  - below ~200k tokens, load everything rather than retrieve;
  - use exact-match lookup for identifiers;
  - a one-line context note in front of each source chunk cuts failed
    retrievals substantially;
  - put the sources first and the question last in the prompt.
- **Here:** `requirements.yaml` is ~300k tokens, too big to load whole,
  but one concept's cited set is 20-40k. Each requirement's
  `implemented_by` and `decisions:` already map a requirement to its
  code, so sources can be walked rather than grepped.

How these were applied is in `plans/explainers.md` #3, round 13.

## Network notes

- **`github.com` refuses its web pages and API here, but `git clone`
  works.** That is how the Diátaxis and Mermaid sources were read.
- **Blocked domains** hit by this research are listed in `CLAUDE.md`'s
  blocked-domains bullet.
