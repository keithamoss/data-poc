# Explainers

Plain-English explanations of the concepts this project has invented,
written by a dedicated team of subagents, and the technical
documentation that sits alongside them. Keith's own ask, 2026-09-28:
he wanted this work in its own plans file rather than folded into
`plans/running-thoughts.md`, where it started.

**What belongs here:** the explainer agent team itself (its design,
research, scoping and build), the list of concepts it explains and the
order they come in, and the separate technical pipeline documentation
track (item 2). **What doesn't:** plain-English text for an individual
QA check. That is `REQ-QAC-024` (built), and the standard for it is
`docs/check-authoring-rules.md`.

Same conventions as every other numbered-item plans file: a closed
status (`todo` / `investigate` / `in-progress` / `blocked` / `parked` /
`done` / `superseded`), one or more component tags, and a date. Per
`CLAUDE.md`, anything here that turns into build work becomes a
requirement in `requirements.yaml` and is signed off by Keith before
building starts, and the entry comes out when it lands.

1. **[investigate, 2026-09-28]** **[Docs & process]** **[Dashboard UI]**
   A technical-writing subagent team that explains this project's own
   invented concepts plainly, with hand-drawn-style diagrams and short
   stories or scenarios alongside.

   Keith's own framing: "really accessible, good technical writing"
   that explains "all of the concepts and things that we've been
   inventing in this repository" in an almost layperson way, plus
   diagrams, stories and scenarios alongside. The diagrams should be
   "fun" and "look a bit hand-drawn". Mermaid.js is his starting
   suggestion; Mermaid 11+ has a built-in `look: handDrawn` (rough.js).
   Whether GitHub's own Mermaid rendering honours that look is still
   unverified, and is one of the things being researched.

   **Settled in the first round of questions (2026-09-28):**
   - Readers: new engineers joining; Keith himself, for presenting;
     and team managers of his technical staff. Agency execs and data
     stewards were NOT picked as primary readers.
   - Home: markdown in the repo (a new `docs/` area, readable on
     GitHub) AND embedded as a new top-level dashboard tab, the same
     way as Plans and Demo.
   - Shape: three agents. A writer, an illustrator (diagrams, stories
     and scenarios), and a reader-critic that reads the result cold as
     a newcomer. This follows the same maker/checker split as the
     delivery-* pairs, but it would be the first agent team that
     WRITES output rather than only advising.
   - Built on the active branch rather than the repo's stale default
     branch. The session that started this was cloned from a default
     branch nine days and 511 commits behind, and caught it only
     before writing anything up.

   **Neighbours to keep distinct:** `REQ-QAC-024` (built) gives
   plain-English explanations per CHECK. This is per CONCEPT: a
   supply, a slot, a delivery calendar, promotion, the worst-of status
   rollup, and so on. `plans/running-thoughts.md` #31 (live
   documentation of the configuration files) asks whether that page is
   a reference or an explainer. This work is explainers, so it could be
   what finally answers #31, at least for the calendar half.

   **Second round (same day):**
   - Stories and scenarios: all four kinds (a recurring fictional
     cast, everyday analogies, real-world incident scenarios, and an
     analogy followed by the cast walking through it). The illustrator
     picks whichever explains a given concept best, and can combine
     several in one explainer. It is a per-concept judgement, not a
     house format.
   - Tone: warm and lightly playful. Friendly, with the odd wry line
     and fun diagrams, but safe to put in front of a manager or on a
     slide.
   - Accuracy: every explainer cites the real files and requirements
     it is based on, and the critic checks claims against current
     code before sign-off. There is also a staleness gate (like
     `validate-requirements`) that flags an explainer when a file it
     cites has changed since it was last reviewed.

   **Third round (same day, Keith's answers to four open questions):**
   - **Concepts come in GROUPS, each holding individual concepts.**
     Keith's first sketch:
     - the supply-lifecycle nouns: supply, slot, delivery, period;
     - the ACTIONS that can be taken on a supply: promotion,
       rejection, refiling;
     - the human decisions that fill a gap: accepting that a period
       has no data and patching in the previous period's data through
       a view, and an annual dataset on a quarterly asset being
       "patched in" through a view in the same way.

     "Just the whole thing, basically."
   - **First three, in order:** (1) delivery calendars and claim
     windows; (2) deliveries and supplies; (3) all the actions that
     can be taken on a supply.
   - **Critic persona:** a new data engineer, with a strong UX lens as
     one of its lenses ("I really care about good user experience").
     So it is grounded in `docs/hci-ux-psychology.md` like the
     delivery-* UX agents, not just a plain-language check.
   - **Staleness gate: a hard CI fail**, not a warning badge.
   - **Keith feeds the topics**, and each one is scoped together
     before any writing starts. The team does NOT sweep the repo and
     pick its own. Not everything on my first candidate list counted
     as a concept: "the four QA tools and why there are four" is not
     one and should not be explained here. The CI-never-touches-data
     rule and the delivery-* agent pipeline belong to the separate
     technical pipeline documentation track instead (item 2).
   - **Bundling Mermaid into `dashboard/vendor/` is fine**, even at a
     few MB. Same offline `file://` reasoning as the asciinema player.

   **Research brief (Keith, same answers):** look at existing agent
   collections, but "pull them apart and compose our own, not just
   copy theirs". Bring in Diátaxis (its "explanation" type), Mermaid's
   hand-drawn look, and the two style references he liked (Julia
   Evans' zines, the Illustrated Children's Guide to Kubernetes).
   **He is worried about prompt injection**, both in the research
   (third-party agent prompts are untrusted text, written to instruct
   AI agents) and in the agents themselves once built. The research
   ran in isolated subagents told to treat everything fetched as data
   and report anything that looked like an injection attempt. Blocked
   domains were flagged for allow-listing rather than routed around;
   the list is in `CLAUDE.md`'s blocked-domains bullet.

   **Research done (2026-09-28)**, written up in full in
   `docs/explainer-agents-research.md`: existing agents pulled apart,
   Diátaxis's explanation type, Mermaid's hand-drawn look, the style
   references, and prompt-injection mitigations. The most useful single
   find: Anthropic's own `doc-coauthoring` skill already has a
   fresh-context "reader test" that is almost exactly the critic we
   described. It gives a subagent ONLY the page, with no repo and no
   `CLAUDE.md` (`omitClaudeMd: true`), plus the questions a real reader
   would ask.

   **Fourth round, Keith's calls on the research (same day):**
   - **Hand-drawn only where it fits**, and only on the four diagram
     types Mermaid actually supports it for: flowchart, state, class
     and ER. Anything else (timelines, sequence) renders in the plain
     look. The research flagged a real tension here: the first topic,
     delivery calendars and claim windows, is naturally a timeline,
     which has no hand-drawn support. Not resolved yet - it is a
     per-diagram call for the illustrator when that topic is scoped.
   - **Vendor `@mermaid-js/tiny`** (12.0.0: 2.9 MB raw, ~0.78 MB
     gzipped, keeps hand-drawn, drops mindmap/architecture/maths),
     loaded only when an explainer is opened, like the Demo tab's
     player.
   - **GitHub rendering: tested empirically, and it works.** Keith
     viewed a temporary test page on GitHub (2026-09-28, since
     deleted): GitHub renders with **Mermaid 11.17.2**, a hand-drawn
     flowchart looked visibly different from the same flowchart in the
     plain look, and a hand-drawn state diagram rendered hand-drawn.
     11.17.2 is past every version the four chosen types need (class
     11.4, ER 11.5), so the markdown copy of an explainer on GitHub and
     the dashboard copy can both show the sketch look. Two things still
     hold. We vendor 12.x and GitHub renders 11.x, and v12 changed
     several defaults, so every diagram states `look` and `theme`
     explicitly rather than relying on either version's default. And
     diagrams must still make sense in the plain look, because GitHub
     picks its own version and could change it.
   - **Commit a trimmed version of the research**:
     `docs/explainer-agents-research.md`.

   Still open: turning the research into agent designs to scope with
   Keith before anything is built.

2. **[todo, 2026-09-28]** **[Docs & process]** Separate technical
   pipeline documentation, as its own track apart from the concept
   explainers in item 1.

   Keith, while scoping item 1: some topics are not CONCEPTS to
   explain to a newcomer, they are how the pipeline is built and run.
   His examples: the rule that CI never touches data, and the
   delivery-* agent pipeline itself. "There's probably going to be
   separate technical pipeline documentation that we work on
   together." Not scoped yet: audience, home, and whether item 1's
   agent team writes it or it is written by hand.

3. **[in-progress, 2026-09-29]** **[Docs & process]** Designing the
   three agents: rounds of questions with Keith, big picture first,
   then each agent in turn, until the questions run out.

   Keith's framing: "Ask me several rounds of questions to inform the
   design of each. Starting with big picture questions that inform all
   of them. Keep asking questions until we run out." Architecture
   best-practice research runs alongside it.

   One real constraint carried in from `docs/agent-orchestration.md`:
   no agent can ask Keith anything directly. Every question an agent
   has comes back through the main session.

   **Round 1 - big picture (2026-09-29):**
   - **Process: its own lighter pipeline.** An explainer is
     documentation, not behaviour, so it does not get a
     `requirements.yaml` entry. Keith and the main session scope the
     topic, the three agents write it, and Keith signs off the finished
     page. The agent TEAM itself (plus the staleness gate and the
     dashboard tab) is real behaviour and does get requirements.
   - **Glossary: yes, a first-class file.** One glossary of the
     project's invented terms, giving each term's one-line definition,
     exact spelling, and the explainer that covers it. The writer must
     use terms exactly as defined, the critic flags drift, and it can
     double as a quick-reference panel in the dashboard tab.
   - **Keith's checkpoints: the brief, and the critic's findings.**
     1. He reviews a one-screen brief before any writing: the "why"
        question the page answers, who it is for, the key points, the
        planned story/analogy/diagrams, and the source files it will
        cite.
     2. He sees the critic's findings and decides which to act on;
        the writer does not auto-fix everything.

     He did NOT pick reviewing the first draft, or the final page
     only.
   - **Unit: a group page plus concept pages.** Each group (e.g. the
     supply lifecycle) gets a short overview showing how its concepts
     fit together, linking to one page per concept.

   **Round 2 - how the team runs (2026-09-29):**
   - **Kick-off: a `/explain` project skill.** It walks the main
     session through fixed steps that cannot be skipped or reordered
     by accident: scope with Keith, brief, Keith's OK, write,
     illustrate, critic, Keith triages the findings, final.
   - **The writer agent drafts the brief**, after Keith and the main
     session have scoped the topic. It reads the sources itself, so
     the brief rests on the specialist's reading rather than the main
     session's.
   - **Writer first, then illustrator.** The writer drafts the page
     with marked slots (e.g. `[diagram: supply lifecycle]`,
     `[story: ...]`). The illustrator fills them after reading the
     draft, so each picture answers a question the prose raises.
   - **Opus for all three**: quality over cost, because explainers are
     few, long-lived and put in front of managers. (But see the
     research below: it argues for the critic being a DIFFERENT model,
     which is taken back to Keith in round 3.)

   **Architecture research (2026-09-29).** Mostly primary sources:
   code.claude.com docs, Anthropic's engineering posts, the
   anthropics/skills repo and the official code-review plugin. What
   changes the design:
   - **Subagents CAN now start other subagents** (up to 3 layers by
     default; `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`), verified in the
     sub-agents docs. It does not change the plan. `AskUserQuestion`
     is still unavailable inside any subagent, so Keith's two
     checkpoints must sit in the main session. A critic nested under
     the writer would hide its findings from him. None of the three
     gets the `Agent` tool.
   - **`omitClaudeMd: true` exists**, verified in the same docs. It
     starts an agent without any CLAUDE.md, which gives the critic a
     genuinely cold read.
   - **Write access can be enforced, not just asked for.** A
     `PreToolUse` hook in the agent's own frontmatter, matching
     `Write|Edit`, can refuse any path outside the explainers folder.
     Frontmatter hooks are skipped silently in an untrusted folder, so
     back it up with a post-run check that the diff only touches that
     folder. No Bash for any of the three (hooks do not see inside
     Bash).
   - **`memory:` silently grants Read, Write and Edit**, so never give
     it to the critic.
   - **Shared knowledge goes in one preloaded skill** (`skills:` in
     each agent's frontmatter), not wording copied into three prompts.
     Bulky reference such as the glossary lives in sibling files read
     on demand. That skill's wording is an authoring standard, so under
     CLAUDE.md's standing rule Keith approves the exact text.
   - **Cap revision loops in the `/explain` skill, not in a prompt**
     (research suggests 2). Anthropic's own cookbook loop is
     uncapped, so don't copy it.
   - **Reviewers asked to find gaps usually invent some.** The critic
     needs "no findings" to be a legitimate answer. It should be tested
     against a clean page as well as a page with planted defects.
   - **Write the evals before the agents**: a few seeded-defect pages,
     a clean page, and a prompt-injection fixture, each run about three
     times in fresh sessions.
   - **Worth testing whether the illustrator should merge into the
     writer.** Anthropic's default is the simplest system, and a
     separate illustrator is justified only if it measurably improves
     the pictures.

   **Round 3 - tensions from the research (2026-09-29):**
   - **Critic model: test both.** Run the critic's evals on Opus and on
     Sonnet 5, and keep whichever catches the planted defects without
     inventing false ones. This settles the tension between Keith's
     all-Opus call and the self-preference evidence, which is
     snippet-only because arXiv is blocked.
   - **Glossary: the writer proposes and Keith approves.** New or
     changed terms appear in the brief, Keith approves them at the
     brief checkpoint, and only then does the writer add them. The
     glossary cannot drift without him seeing it.
   - **Evals: a small set, built before the agents.**
     - About three pages with planted defects: jargon, a wrong fact,
       and a diagram that decorates rather than explains.
     - One clean page, which is the critic's negative control.
     - One prompt-injection fixture.

     Each runs about three times, and the set grows from real failures
     later.
   - **Illustrator: build three, then A/B it** on the first real topic
     against the writer doing its own pictures, before committing to
     the split.

   **Round 4 - the house standard and layout (2026-09-29):**
   - **Citable sources are requirements and config, fingerprinted
     entry by entry.** An explainer cites requirement ids (e.g.
     `REQ-PIPE-049`) and specific config or code files (e.g.
     `contract/data-asset.yaml`). The staleness gate fingerprints just
     that requirement's entry, not the whole of `requirements.yaml`.
     **`plans/*.md` is never a citable source**, because it is working
     material that gets deleted as requirements land. Without this
     rule, the daily churn of plans files and CLAUDE.md would fail the
     gate constantly.
   - **Style: a mix of the Australian Government Style Manual and
     Keith's own preferences.** Australian spelling and the Style
     Manual's plain-language rules form the baseline, with Keith's own
     preferences layered on top. Those preferences are still to be
     gathered.
   - **A fixed cast, defined once** in the house standard: a small
     named cast with roles and personalities, reused in every story so
     readers get to know them. Keith approves the cast.
   - **Location: `docs/explainers/<group>/`.** For example:
     - `docs/explainers/glossary.md`;
     - `docs/explainers/supply-lifecycle/index.md` (the group page);
     - `docs/explainers/supply-lifecycle/claim-windows.md`.

     The write-restriction hook allows exactly this folder.

   **Round 5 - the writer (2026-09-29):**
   - **Page shape: free-form.** Keith chose this over a fixed
     skeleton and over "required elements, free order". Two answers in
     the same round do fix a couple of parts, though: every page has an
     "In short" box on top and a short "why it's this way" section.
     Round 1's "why" question and cited sources are needed too. So the
     page is free-form apart from those four.
   - **Length: short, about 500-800 words** plus diagrams, readable in
     3-4 minutes. Deeper detail links out to other pages.
   - **Two readers: an "In short" box on top**, 3-4 sentences that a
     manager can stop after. The rest of the page is for the engineer.
   - **Decisions: a short "why it's this way" section** of 2-4 bullets
     drawn from the requirement's `decisions:` field: what was chosen,
     what was rejected, and why.
   - **Still open: Keith's own writing preferences** layered over the
     Style Manual. Asked as an open question (words he dislikes,
     em-dashes, humour, second person, Oxford commas, question-style
     headings, writing he loves or hates).

   **Round 6 - the illustrator (2026-09-29):**
   - **Diagram count: as many as it takes.** It is the illustrator's
     call, and the critic flags excess. Every diagram still has to pass
     the "does it argue?" tests from the research.
   - **When a concept's natural shape can't be hand-drawn, use the
     right shape, plain.** Use a plain timeline or gantt where that is
     genuinely clearest. Correctness beats consistency: hand-drawn is
     the default, not a rule that bends the diagram. This settles the
     timeline tension for the first topic.
   - **Story form: the illustrator's choice** between a short vignette
     (the Phippy pattern) and numbered zine-style panels (the Julia
     Evans pattern), whichever fits the concept.
   - **Required on every diagram, all three:**
     1. a one-line caption saying what it shows, which doubles as the
        accessible description;
     2. a shared colour palette in the house standard, tested in light
        and dark mode and matched to the dashboard;
     3. one fixed `handDrawnSeed` across all diagrams, so the wobble is
        stable between renders and between GitHub and the dashboard.

   **Round 7 - the critic (2026-09-29):**
   - **Accuracy gets its own agent: a separate FACT-CHECKER, making a
     team of four.** The critic stays a purely cold reader, judging
     clarity and UX. The fact-checker checks each claim on the page
     against only that page's cited sources. Keith chose this over one
     critic doing two passes, and over relying on the citations plus
     his sign-off. The reason is cleaner roles: a reader who knows the
     answer can't tell whether the page taught it.
   - **Reader questions come from both places.** The writer puts 5-8
     "a new engineer should be able to answer..." questions in the
     brief, and Keith sees and tweaks them at his checkpoint. The
     critic answers them from the page alone, and a wrong or missing
     answer is a finding. On top of those, the critic adds whatever
     else it found itself wondering.
   - **Findings are severity-ranked and all shown.** Each one quotes
     the exact text and gives a severity (blocker / should fix /
     polish) and a suggested change. Keith sees them all, grouped by
     severity, and picks which the writer acts on. There is no
     confidence filter.
   - **UX lens: the rendered page from day one.** The critic views the
     page in the real dashboard tab through a real browser (Playwright
     MCP), like the delivery-*-ux-critics. Two consequences:
     - The tab has to exist before the critic can run, which fixes the
       build order.
     - The critic needs browser tools on top of a cold start.

     "Cold" therefore means no CLAUDE.md and no repo browsing; it can
     still see the rendered page.

   **Round 8 - preview and the fact-checker (2026-09-29):**
   - **Preview: an explainers-only preview command** (something like
     `mothman explainers preview`). It renders the dashboard template
     with only the explainer tab's content embedded and no QA data, so
     it takes seconds rather than a four-minute bootstrap, and shows
     exactly what the tab will show. It is built as part of the tab
     work.
   - **Fact-checker report: a full claim-by-claim table, problems
     first.** Every factual claim on the page is marked supported,
     contradicted, or not found in the sources, with the exact source
     it was checked against (a requirement id, or a file and line).
     Contradicted and not-found rows sort to the top.
   - **The critic and fact-checker run in parallel.** They are
     independent (one reads cold, the other reads sources), and Keith
     triages both reports together at his one findings checkpoint.
   - **The fact-checker runs on Opus.** Careful claim-checking against
     requirements and config is reasoning work, and its errors reach
     managers. It is not part of the Opus-versus-Sonnet test; only the
     critic is.

   **Round 9 - revisions, the tab and sign-off (2026-09-29):**
   - **Revisions: re-check, at most 2 loops.** After Keith triages and
     the writer revises, the critic and fact-checker re-run on the
     revised page and Keith triages again. The `/explain` skill caps
     this at 2 revision loops. If the page still isn't right after
     that, the session stops and talks rather than looping.
   - **The tab offers all four extras:**
     1. **"What's this?" links elsewhere in the dashboard.** Where the
        rest of the dashboard shows an invented term (a claim window,
        a slot, a promoted supply), a small link opens its explainer,
        so the explanation sits where the confusion happens.
     2. **A glossary panel**: the glossary as a searchable
        quick-reference.
     3. **Search** across all explainer pages.
     4. **A staleness badge** showing each page's last-reviewed date,
        even though CI hard-fails on stale pages.
   - **Sign-off lives in each page's front matter, with fingerprints.**
     The front matter records `signed_off` (by, date) and a fingerprint
     of every cited source at that moment. The staleness gate compares
     the fingerprints. A `mothman explainers sign-off` command updates
     them, and only once Keith has approved.
   - **When the gate fires, the fact-checker proposes a fix.** It
     re-runs on just the changed sources and reports which claims
     broke, the writer proposes minimal edits, and Keith re-signs.

   **Round 10 - sources, safety, requirements, build order
   (2026-09-29):**
   - **The writer may READ `plans/*.md` for background but never cite
     it.** Every claim must rest on a citable source (a requirement,
     config, or code). The fact-checker enforces this: a claim
     supported only by plans prose is marked "not found".
   - **Prompt injection: report it and carry on.** Text that looks
     addressed to an AI is treated as content, quoted as a
     top-severity finding, and the task finishes normally. Keith sees
     it at the next checkpoint. This avoids false alarms stopping runs
     (CLAUDE.md is full of "never do X" sentences).
   - **Requirements for the agent team: `delivery-scoper`, drafting
     from this design.** The scoper gets items 1-3 of this file as its
     SOURCE, so the decisions carry over (per CLAUDE.md's
     carry-decisions-at-drafting-time rule). It drafts small
     requirements: the house standard, the glossary, the agents,
     `/explain`, the preview command, the staleness gate, and the tab.
     They then go through sign-off with Keith.
   - **Build order: standard, then agents, then the first page:**
     1. the house standard and cast (Keith approves the wording);
     2. a glossary seed;
     3. the preview command;
     4. the evals;
     5. the four agents;
     6. `/explain`;
     7. the first real explainer (delivery calendars and claim
        windows);
     8. the tab's extras (search, "what's this?" links, badges) and
        the staleness gate.

   **Round 11 - persona, the manager check, names, changelog
   (2026-09-29):**
   - **The critic's persona is competent but new to this project.** A
     mid-level data engineer: comfortable with SQL, pipelines and data
     quality in general, has heard of dbt. Knows nothing about this
     project, its invented terms, or WA government data sharing. Busy,
     and reads on a laptop between meetings.
   - **The critic also does a quick manager pass.** After its main
     read, it re-reads only the "In short" box as a technical team
     manager and asks: could I explain this concept to my boss from
     these sentences alone?
   - **Names: `docs-*`**: `docs-writer`, `docs-illustrator`,
     `docs-critic` and `docs-fact-checker`. Keith chose this over
     `explainer-*`. It is broader, and reads as though the same team
     may later write the pipeline documentation too (item 2). That
     implication is asked about in round 12.
   - **Changelog: only the tab launch** gets a `CHANGELOG.yaml` entry.
     Individual explainer pages are not announced.

   **Round 12 - scope and cast (2026-09-29):**
   - **Design for item 2 as well.** The house standard, the agents and
     the gates stay general enough to take a second document type
     later: pipeline documentation, which is how-to and reference in
     Diátaxis terms rather than explanation. Only explainers are BUILT
     now.
   - **The cast: the main session drafts, Keith reacts.** Four or five
     characters, each with a name, role, agency, one personality trait
     and what they typically struggle with, grounded in the real kinds
     of people this project serves. Keith edits and approves the
     wording as part of the house standard.

   **Where this leaves the design.** Every question the main session
   could see has been asked. Still open:
   1. Keith's own writing preferences (round 5), for the house
      standard.
   2. The cast draft.
   3. Running `delivery-scoper` over items 1-3 to draft the
      requirements, then signing them off with Keith.

   Nothing gets built before that sign-off.

   **Raised by Keith after round 12 (2026-09-29), still open:**
   - **Brainstorm the topics, concepts and group-page structure
     FIRST**, before the writing preferences, the cast or the
     requirements. His sequencing.
   - **"How will we handle stochasticity?"** The same brief can produce
     a different page, diagram or set of critic findings on every run.
   - **"Is there anything we can learn from RAG?"** The writer and
     fact-checker are effectively doing retrieval-augmented generation
     over this repo's own sources.

   **Stochasticity and RAG research (2026-09-29).** Mostly primary:
   Anthropic's API reference and prompting guides, "Demystifying
   evals", the Contextual Retrieval post, and RAGAS's own docs source.
   - **There is no temperature to turn down.** Checked in the Messages
     API reference: models released after Claude Opus 4.6 reject any
     temperature other than 1.0, and even 0.0 was never fully
     deterministic. Subagent frontmatter has no temperature field
     either, and unknown fields are silently ignored. So consistency
     has to come from STRUCTURE:
     - precise output formats and examples;
     - a fixed set of sources;
     - prompt chaining;
     - models pinned by full id rather than an alias like `opus`,
       which moves;
     - above all, freezing a signed-off page so it is never
       regenerated, only edited.
   - **Anthropic's anti-hallucination advice maps straight onto the
     fact-checker:** extract quotes first, retract any claim with no
     supporting quote, and treat disagreement between repeated runs as
     a warning sign.
   - **pass^k, not pass@k, for consistency.** At 75% per run, all three
     runs passing is only 42%. LLM judges need calibrating against
     people and an "Unknown" way out.
   - **The gap RAG exposes: context recall.** The fact-checker (RAGAS's
     "faithfulness") only checks a page against the sources the page
     itself cites. A page can be 100% faithful and still miss, or
     contradict, a requirement it never cited. Nothing in the current
     design checks the SOURCE SET.
   - **Prompted citations aren't guaranteed valid.** The API's
     Citations feature is, but subagents can't use it. The equivalent
     is a script that checks every quoted passage appears verbatim in
     the source it cites.
   - **Size.** `requirements.yaml` is 1.2 MB, about 300k tokens, too
     big to load whole. One concept's cited set, perhaps 20-40k tokens,
     fits easily. So the problem is choosing sources, not fitting them.
     Each requirement's `implemented_by` and `decisions:` already form
     a walkable map from requirement to code.

   **Round 13 - stochasticity and RAG (2026-09-29):**
   - **Source recall: a per-group source index.** Each group gets a
     `sources.yaml`, which Keith reviews once. It lists every requirement
     and config file relevant to the group, with one line of context
     each. The writer starts from it. A script flags any glossary term
     on a page whose defining requirement is not cited, and the
     staleness gate fingerprints the index too. This closes the
     "faithful but incomplete" gap.
   - **The fact-checker runs twice per round, and the results are
     combined.** Any claim that either run marks contradicted or not
     found is shown to Keith. Claims the two runs disagree on are
     flagged "unstable", which is Anthropic's own hallucination-warning
     signal. A deterministic script also checks that every quoted
     passage appears verbatim in the source it cites.
   - **A fourth verdict: "sources disagree".** When a requirement and
     the code say different things, the page does not pick a side. The
     finding always goes to Keith, because it may be a real bug in the
     code or a stale requirement rather than an explainer problem.
   - **Variation as a feature, confined to the brief.** The writer's
     brief offers 2-3 candidate analogies or story angles, and Keith
     picks one or asks for another at his brief checkpoint. Everything
     after that runs once, and the signed page is frozen: only edited,
     never regenerated.

4. **[todo, 2026-09-29]** **[Docs & process]** The concept map: which
   groups and concepts the explainers cover, in what order, and what a
   group page holds.

   Drafted by the main session from `plans/supply-model.md`'s "Concept
   inventory" and the 108 requirements, then shaped with Keith. It
   becomes the source the glossary seed and every `/explain` run
   start from, and moves into the real glossary and group pages as
   they are written.

   **Groups, as a numbered learning path** (Keith's call: read in this
   order, but anyone can jump in anywhere):
   1. **The shape of the data asset**: data asset; agency, collection,
      dataset and column; environments; same code, separate deployment
      per asset.
   2. **The calendar** (Keith's first topic): delivery calendar,
      schedule, period, slot, due time and grace, claim window, a
      dataset that joins a calendar or never has one, and a schedule
      that runs out.
   3. **What arrives** (his second): delivery (one physical drop),
      supply (one table's version), receipt, recognising files by
      pattern, two files for one dataset being held, a hand-filed
      supply, and early / on time / late / overdue.
   4. **Filing a supply** (his third): staging, slot assignment (the
      claim rule), held for a human, promotion, rejection, demotion,
      un-decide, re-file, resupply (an arrival into a filled slot), the
      mixed-period delivery, and the decision log.
   5. **Filling the gaps** (his "patch in via a view"): a period
      standing in on the last good one, inherit and un-inherit (an
      annual dataset on a quarterly asset), and why neither reads as an
      ordinary green.
   6. **Judging quality**: check and `check_id`; check scopes (column,
      dataset, supply, cross-table, file); red/amber/green and the
      worst-of rollup; red-for-unrun; amber accept/reject; retiring a
      check; what drift is measured against.
   7. **Looking back in time**: as-of viewing, "as at T" answered from
      filing events, snapshots, and the activity feed.

   **A known trap to guard against: "delivery" changed meaning.** It
   used to mean the logical obligation, which is now a SLOT, and that
   old sense survives in the generator code (`plans/supply-model.md`,
   "The collision"). It is exactly what the glossary exists for, and a
   good early test for the fact-checker.

   **Keith's calls (2026-09-29):**
   - **Designed-but-unbuilt concepts ARE included, clearly badged**
     "designed, not built yet". Much of groups 4 and 5 is signed off
     but not built. Every such page is revisited as the build lands.
   - **A group page holds all four of:**
     1. a big-picture story walking the whole group end to end with
        the cast;
     2. one overview diagram whose nodes link to the concept pages;
     3. concept cards in reading order (a glossary one-liner plus a
        link);
     4. "read first" prerequisites.
   - **The concept map lives here** until it moves into the real
     glossary and group pages.

   **Still open:** Keith's own review of the list above (what's
   missing or misplaced, and whether anything on it isn't really a
   concept), asked as an open question.
