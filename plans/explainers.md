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

## Open work queue

Priority: work through today, in this order (Keith, 2026-09-29 morning:
"we'll work through that gradually today"). Written into the file so it
survives context compaction. Tick items off here as they land.

1. [done] Finish the paper check: the snippet-only research
   claims re-verified against arXiv and ACL papers, now reachable.
   Report any design decision that should change.
2. [done] **Naming session.** One canonical word per naming hazard
   (#4's concept sweep lists them); the others become glossary aliases.
3. [done: 29 in, 2 to pipeline docs, 2 split] **Triage the 33 missed concepts** (#4's sweep, one by one).
   Keith says what he does NOT want included.
3b. [done] **Sweep the split between the
   two documentation tracks.** Keith, 2026-09-29: "it sounds like we're
   talking about user-facing documentation, whatever we call that. And
   we're also talking about pipeline documentation... I feel like we're
   putting a lot into the user-facing documentation right now and not
   much in the pipeline docs, but I could be wrong." Check the shape of
   both tracks: what belongs in each, whether the concept map is
   over-weighted towards the user-facing side, and a name for the
   user-facing track. At the time of writing, only #9 (actor, reasons
   and the people list) and #6's physical detail had been sent to the
   pipeline docs.
4. [next] **Tiering** for the concepts that survive triage: own page,
   section, or glossary entry only.
5. [todo] **The cast draft**: 4-5 characters for Keith to react to
   (#3, round 12).
6. [todo] **Keith names external writing exemplars** (#3, style round
   4).
7. [todo] **Requirements via `delivery-scoper`**, drafting from items
   1-4, then Keith's sign-off. Nothing is built before this.
8. [done: moot, GOV.UK is the baseline, and its numbers rule applies] Confirm the Style Manual's rule on numbers once
   `www.stylemanual.gov.au` is reachable (#3, style round 4).
9. [todo, NOT explainer work] Renames the naming session implies in
   code and requirements, flagged rather than done. Each needs its own
   scoping:
   - "delivery calendar" to "supply calendar";
   - the `sample` schema, which clashes with the "sample" asset shape;
   - the amber `/accept` command to "acknowledge";
   - "cycle" to "period";
   - "stale" wording to "no data".

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

   **Shape, from the two-track sweep (2026-09-29; see item 3).** Working
   name "Running Mothman". Readers: engineers and operators. The content
   is Diátaxis how-to, reference and technical explanation, first
   inventory:
   - **How-to (mostly for operators):**
     - record a filing decision;
     - deal with a held supply;
     - deal with a load failure;
     - add, change or retire a check (triage #30);
     - add a dataset and its contract;
     - extend a supply calendar before it runs out;
     - hand-file or trial a file;
     - set up an environment;
     - run QA;
     - build and publish the dashboard.
   - **Reference:**
     - the `mothman` commands;
     - each config file (`data-asset.yaml`, the contracts,
       `people.yaml`, `environments.yaml`);
     - who can decide, and required reasons (triage #9);
     - the schemas and storage (triage #6 and #31, storage halves);
     - the CI gates.
   - **Technical explanation (for engineers):**
     - CI never touches data;
     - the repository holds configuration, not state;
     - why PostgreSQL;
     - the per-run views;
     - the `delivery-*` agent pipeline.

   The same agent team writes it later (item 3, round 12: design for
   it, build explainers first). Its own house standard will need
   how-to and reference rules, not just the explanation rules settled
   so far.

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
   order, but anyone can jump in anywhere). Revised 2026-09-29 after
   Keith's review: he added an overview page, flagged that the asset's
   shape varies, split "judging quality" in two, and confirmed that
   every group is a real concept, unlike the four QA tools.

   0. **The overview page** (Keith: "I'm assuming there's an overall
      page"). A very high-level introduction to the whole thing and a
      tour of the groups below.
   1. **The shape of the data asset**: data asset; agency, collection,
      dataset and column; environments; same code, separate deployment
      per asset. **This group must flag that the shape VARIES.** The
      tool is meant to be generic and generalisable, so it will also
      run on one-off project extractions (supplies with no cadence) and
      on sample data, not only on recurring multi-agency assets. Keith:
      "we don't have language for that yet, but it is something that
      will change." So this group's pages are the ones most likely to
      be revisited. Also here (round 16): the DATA CONTRACT, where a
      dataset's columns, checks, due times and file patterns come
      from; a dataset that exists before its schedule is agreed, or
      never gets one (moved from group 2); and which environment a
      dashboard shows.
   2. **The calendar** (Keith's first topic): delivery calendar,
      schedule, period, slot, due time and grace, claim window,
      overdue (moved from group 3: it is about what did NOT arrive),
      and a schedule that runs out.
   3. **What arrives** (his second): delivery (one physical drop),
      supply (one table's version), receipt, recognising files by
      pattern, two files for one dataset being held, a hand-filed
      supply, and early / on time / late.
   4. **Filing a supply** (his third): staging, slot assignment (the
      claim rule), held for a human, promotion, rejection, demotion,
      un-decide, re-file, resupply (an arrival into a filled slot), the
      mixed-period delivery, the decision log, and accepting or
      rejecting an amber supply (moved here in round 14).
   5. **Filling the gaps** (his "patch in via a view"): a period
      standing in on the last good one, inherit and un-inherit (an
      annual dataset on a quarterly asset), and why neither reads as an
      ordinary green.
   6. **When a person is needed** (new in round 16). Holds, the
      asset's single count of everything needing a person, QA
      tickets, overdue tickets, and where decisions are taken (a
      GitHub ticket or the terminal, never the dashboard). It sits
      after filing and filling the gaps, which are where most of
      those decisions arise.
   7. **How status works** (settled in round 15: status only, no
      checks). Red, amber and green; the worst-of rollup up the
      hierarchy (column, dataset, collection, agency); red-for-unrun;
      timeliness verdicts (early, on time, late, overdue) and
      freshness capping a headline; anomalies aggregated rather than
      read as a data verdict. The overview page gives a short
      red/amber/green primer first, so every earlier group can use the
      words (round 15).
   8. **The checks, by level** (Keith's ask for "the broad types of
      column checks", organised BY LEVEL in round 14). Column checks,
      dataset checks, supply-level checks, cross-table checks, and file
      (shape) checks, which are claims about the file, never a verdict
      on the data. Within each level, the types use the five real
      categories every check carries, the ODCS standard's own quality
      dimensions (`qa_tools/common/check_lifecycle.py`
      `CHECK_CATEGORIES`): completeness, uniqueness, conformity,
      consistency, timeliness. Also here: drift and volume and what
      they are measured against, a check's identity (`check_id`), and
      retiring a check. Keith: "we have other checks at data set level
      that I forget" - the concept sweep lists them.
   9. **Looking back in time**: as-of viewing, "as at T" answered from
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

   **Still open:** follow-up questions on the revision above, and a
   sweep of `requirements.yaml` and `plans/*.md` for concepts the map
   has missed (Keith's ask).

   **Round 14 - the revised map (2026-09-29):**
   - **The overview page covers three things: the problem, one journey,
     and a tour.** It opens with the problem this solves, follows a
     single supply from arriving to being judged to appearing on the
     dashboard, and then tours the groups as the reading path.
   - **Group 1 gets placeholder names now** for the asset shapes that
     have no language yet (one-off project extractions, sample data),
     entered in the glossary as draft. Keith approves the names; see
     round 15.
   - **Amber accept/reject belongs in group 4**, with the other actions
     on a supply. Keith added: "but maybe the statuses get explained
     easier as well?" This is read as "EARLIER" (a likely dictation
     artefact): red/amber/green should be met before the reader reaches
     filing. Confirmed in round 15.
   - **Group 7 is organised by LEVEL, not by the five categories.**
     Column checks, dataset checks, cross-table checks and file checks,
     each with its types. That overlaps group 6's "what each layer is
     judged on", so the split between groups 6 and 7 is settled in
     round 15.

   **Round 15 - follow-ups on the revised map (2026-09-29):**
   - **"Earlier" confirmed.** Red, amber and green are first explained
     as a short primer inside the overview page's one-supply journey,
     so every group can use the words. The full detail stays in group
     6.
   - **Groups 6 and 7 divide cleanly: 6 is status, 7 is checks.** Group
     6 is purely how STATUS works. Group 7 is every CHECK, by level.
     The group list above has been updated to match.
   - **Placeholder names for the asset shapes, named by how supplies
     arrive** (draft, for the glossary):
     - a **scheduled asset**: supplies owed on a calendar, today's
       shape;
     - a **one-off extraction**: supplies with no schedule, for a
       single project;
     - a **sample**: practice or test data, never real.
   - **The cast is introduced in the overview's one-supply journey**,
     so every later story can assume the reader knows them.

   **Style round 1 (2026-09-29).** These answers are for the house
   standard; Keith approves the exact wording before it is written:
   - **Voice: a mix of "you" and "we".** "You" when addressing the
     reader; "we" when explaining a choice the project made ("we chose
     X because...").
   - **Humour: wry asides and puns in headings.** For example, the odd
     dry line acknowledging that something is genuinely fiddly, or
     occasional wordplay in a heading or caption. NOT picked: Australian
     references and idiom, or keeping all the humour inside the cast's
     stories.
   - **Dashes: a spaced en dash ( – ),** the Australian Government
     Style Manual's convention for a break in a sentence.
   - **Headings: mostly questions** ("Why does a slot have a claim
     window?"), mirroring the Diátaxis why-question and telling a
     skimmer what each section answers.

   **Concept sweep (2026-09-29).** Keith asked for a pass through
   `requirements.yaml` and `plans/*.md` for concepts the map missed.
   A subagent read all 108 requirements and the plans files; its
   headline claims were spot-checked against `requirements.yaml`.

   **Missed concepts, most-needed first**, with requirement ids.
   B = built, NB = not built, P = partly built; the proposed group is
   in brackets:
   1. The data contract (ODCS) itself, where checks, due times and
      file patterns come from (B) [1 or 7].
   2. What a check is, and warn versus fail thresholds, the thing that
      makes a result amber rather than red (REQ-QAC-047) (B) [needed
      before 6].
   3. Statuses beyond red/amber/green: "No data", "No rule defined",
      "Schedule ended", "unfiled", "unknown", none of them a quality
      verdict (REQ-PIPE-053, REQ-DASH-070) (B) [6].
   4. Qualifiers, meaning a status plus a word rather than a new
      colour: substituted, inherited, uncertain, in development
      (REQ-DASH-085/100, REQ-PIPE-106) (P) [6].
   5. Arrived versus promoted: a dataset's latest arrival and its
      promoted supply are different things (REQ-PIPE-034,
      REQ-DASH-056) (P) [3/4].
   6. Where a supply physically lives: the staging, period, rejected
      and sample schemas (REQ-PIPE-087/060/075/076) (P) [4; possibly
      pipeline docs].
   7. The automatic promotion gate, and "automation defers to a person,
      permanently" (REQ-PIPE-075/076/077) (NB) [4].
   8. The actor on every decision (person or rule), required reasons,
      and the people allowlist (REQ-PIPE-074, REQ-GHUB-082) (P) [4].
   9. The seven filing decisions: four about a supply (promote,
      reject, demote, re-file) and three about a period (substitute,
      inherit, un-inherit), taken from a ticket or the terminal, never
      the dashboard (REQ-GHUB-082) (NB) [4].
   10. Check scopes, and cross-table verdicts counting against EVERY
       dataset they read (REQ-QAC-037) (B) [6/7].
   11. Check dependencies (`depends_on`) and temporal reference
       (REQ-PIPE-035/079) (P) [7].
   12. Why a check could not run, which is the reasons behind
       red-for-unrun (REQ-PIPE-079) (NB) [6].
   13. Load failure (REQ-PIPE-060) (B) [3].
   14. The event severity vocabulary (informational / warning / needs
       action), which is never drawn in red/amber/green (REQ-DASH-070)
       (B) [6].
   15. What recognition cannot place: an unrecognised artefact, an
       unexpected table, an unplaceable delivery, a delivery still in
       flight (REQ-PIPE-057) (B) [3].
   16. The unfiled supply (REQ-PIPE-066) (P) [4].
   17. An assignment made under ambiguity, which defaults backward and
       is marked uncertain (REQ-PIPE-065) (B) [4].
   18. A slot closed unfilled (REQ-PIPE-063) (B) [4].
   19. An arrival verdict follows its filing (REQ-PIPE-067) (B) [3].
   20. Arrived, promoted and filled as three different moments
       (REQ-PIPE-080) (NB) [3].
   21. Calendar detail:
       - not-expected periods and delivery months (REQ-PIPE-049) (B);
       - calendar versions (B);
       - authored dates versus a cadence rule (B);
       - runway (REQ-PIPE-053) (B);
       - the asset's clock, where a bare date means end of day
         (REQ-PIPE-048) (B);
       - supplies for the following period (NB).

       All [2].
   22. Pre-agreement datasets and graduation (REQ-PIPE-106) (B) [1].
   23. The project extraction and its recipe (sprint 29, no
       requirements) (NB) [1].
   24. A trial: checking without keeping (REQ-PIPE-103) (P) [3?].
   25. Staleness shown as "No data as of", distinct from the unbuilt
       freshness capping (REQ-PIPE-007) (B) [6/8].
   26. The BUILT, status-inferred resupply chain (REQ-QAC-008) (B)
       [3/8].
   27. QA and overdue tickets (REQ-GHUB-027/015, REQ-PIPE-083) (P)
       [new group?].
   28. A check's plain-English fields (REQ-QAC-024) (B) [7?].
   29. Check definition changes and the check changelog (REQ-QAC-006)
       (B) [7].
   30. Recorded QA history (REQ-PIPE-089) (B) [8?].
   31. The as-corrected view versus what the page said
       ("In place on", REQ-PIPE-081) (NB) [8].
   32. Newest PROMOTED wins (REQ-PIPE-105) (P) [4].
   33. Which environment a dashboard shows (REQ-DASH-094) (NB) [1].

   **Dataset-level judgements** (Keith: "other checks at data set
   level that I forget"):
   - the rollup of its column checks;
   - supply-level row count;
   - table-level business rules, plus a content-recency check ("recent
     births present");
   - volume and drift, measured against the last promoted earlier
     period (REQ-QAC-108, NB);
   - the cross-table checks it takes part in;
   - missing-dependency red;
   - arrival timeliness, and an overdue slot;
   - "No data as of", and schedule ended plus low runway;
   - not-expected, inherited and substituted periods;
   - the in-development label;
   - amber accept/reject;
   - arrived versus promoted;
   - columns with no rule defined.

   There are further judgements at supply, file, delivery, collection
   and asset level (e.g. the asset's single count of everything
   needing a person, REQ-DASH-070).

   **Naming hazards the glossary must settle:**
   - **delivery**: the obligation sense survives in "delivery
     calendar"; REQ-PIPE-105 also splits delivery (one drop) from
     arrival (one file).
   - **resupply**: the built chain versus the model's arrival into a
     filled slot.
   - **carry forward / substitute / patch / stand in / last good one**:
     all one concept, but "carry forward" also means supplies for the
     following period.
   - **demote / un-decide**: un-decide IS demote-to-staging (verified
     in REQ-PIPE-076's decisions). Demote can also go to rejected.
   - **reject**: an amber reject is a filing reject; an amber accept is
     not logged.
   - **promote**: also "save QA results" in the TUI (being renamed).
   - **as of** is being relabelled "In place on".
   - **timeliness**: as a check category it means CONTENT recency, not
     arrival timeliness.
   - Also: no data; stale / freshness / recency / overdue; run;
     blocked; cycle versus period; and the several names for a
     pre-agreement dataset.

   **Suggested fixes to the map:**
   - move overdue out of group 3 (it is about what did NOT arrive);
   - move the never-a-calendar dataset to group 1;
   - mark groups 4-5 as read-first for drift and volume;
   - badge freshness capping (no requirement yet);
   - the anomaly activity feed is unscoped and differs from the built
     one;
   - explain the built resupply chain where supply history appears.

   Outcomes are in the round below.

   **Round 16 - absorbing the sweep (2026-09-29):**
   - **Three tiers.** A big idea gets its own concept page, a medium
     one becomes a section inside a related page, and a small one is a
     glossary entry only. The main session proposes a tier for each
     concept, and Keith adjusts.
   - **Foundations go in group 1.** The data contract is part of what
     a dataset IS, so group 1 introduces it. A "what's a check" page,
     with warn and fail thresholds, opens the checks group (now 8).
     The overview's red/amber/green primer covers the reader until
     then.
   - **A new group: "When a person is needed"** (now group 6, and the
     later groups renumbered to 7-9).
   - **Naming: a session with Keith.** The main session brings each
     naming hazard with its candidates, where each is used, and a
     recommendation. Keith picks the canonical word, and the others
     become aliases listed in the glossary. Picks that imply renaming
     things in code or requirements get flagged as follow-up work.
   - **Two uncontroversial map fixes from the sweep, applied:** overdue
     moves from group 3 to the calendar (group 2), and datasets that
     never get a calendar move to group 1.

   **Style round 2 (2026-09-29):**
   - **Oxford comma: always** ("red, amber, and green"). This is a
     deliberate departure from the Style Manual, which uses it only
     for clarity. It is one of Keith's own preferences layered on top.
   - **Banned outright, all four kinds:**
     - "AI voice" words: delve, tapestry, crucial, leverage, seamless,
       robust, landscape, "it's worth noting", and so on.
     - Condescension: just, simply, obviously, easy, of course.
     - Corporate filler: utilise, facilitate, going forward, synergy,
       empower.
     - Rhetorical tics: "it's not X, it's Y", "here's the thing",
       rule-of-three padding, and ending a section on a punchy
       one-liner.
   - **Sentences: aim for about 15-20 words, capped at 25.** The critic
     flags anything over the cap.
   - **Dates follow the Style Manual's default** ("29 September 2026"),
     even though the dashboard has its own single date format
     (REQ-DASH-071). Keith chose this over matching the dashboard, so
     an explainer and the dashboard may show a date differently.

   **Style round 3 (2026-09-29):**
   - **New terms:** the first use on a page is in bold, with a plain
     one-clause definition in the same sentence and a link to the
     glossary entry. Later uses are plain text.
   - **Identifiers only in a sources section.** The body stays clean
     for managers: no requirement ids, file names or code identifiers
     mid-sentence. Every page ends with a "where this comes from" list,
     for engineers and for the fact-checker.
   - **Prose first; lists only for real sets** (for example, the seven
     filing decisions). This is Diátaxis's discursive voice.
   - **Bold is reserved for a new term's first appearance**, so bold
     always means "this is a defined word".

   **Style round 4 (2026-09-29):**
   - **Sounds like a colleague at a whiteboard**: a senior engineer who
     built this, explaining it to a smart new hire over coffee.
     Relaxed, precise, and happy to admit where it is fiddly.
   - **Status names in lowercase, plain**: "the dataset turns red", "an
     amber supply". The colour pills on the page carry the visual.
   - **Numbers:** numerals from 2 upward and words for zero and one,
     which is believed to be the current Style Manual's rule. **This is
     unverified**, because `www.stylemanual.gov.au` is blocked; check
     it before the house standard is finalised.
   - **Exemplars:**
     - **Model:** `CHANGELOG.yaml`'s reader voice (the "What's New"
       entries, REQ-DOCS-028).
     - **Anti-model:** the dense, caveat-heavy internal prose of
       `plans/` and `CLAUDE.md` is marked as the thing NOT to sound
       like.
     - **Still to come:** Keith will name external examples himself.
     - NOT picked as a model: the check explanations from REQ-QAC-024.

   **Paper check (2026-09-29).** With arXiv and the ACL Anthology now
   reachable, the snippet-only claims behind rounds 3 and 13 were
   checked against the papers themselves. Three spot-checks were
   re-verified by the main session: that three of the papers exist
   (arXiv 2606.13685, 2410.21819, 2404.13076) and a verbatim quote from
   Zheng et al. Corrections, recorded beside the rounds rather than
   rewriting them:
   - **Self-preference bias is real but weaker evidence than assumed.**
     - Zheng et al. 2023 (arXiv 2306.05685) state: "cannot determine
       whether the models exhibit a self-enhancement bias".
     - Panickssery et al. 2024 (arXiv 2404.13076) do find it, but did
       not control for true quality.
     - Wataoka et al. 2024 (arXiv 2410.21819) find it tracks how
       FAMILIAR text is to the judge, not who wrote it. So a Sonnet
       critic probably shares much of Opus's bias.

     Round 3's "test both models" stands, but for a different reason:
     the planted-defect evals decide, and switching models should NOT
     be expected to remove the bias.
   - **"About 11 runs for a stable vote"** comes from one unreviewed
     2026 paper (arXiv 2606.13685). It tested two OpenAI mini models on
     29 deliberately close pairwise choices, and three runs already
     reached about 90% reliability. Do not cite 11 runs as a
     requirement; round 3's three runs per eval stands.
   - **Running the fact-checker twice is not self-consistency.** Wang et
     al. (arXiv 2203.11171) support majority VOTING, and two runs can't
     form a majority. Round 13's decision stands, described honestly:
     - the union catches more at the cost of more false flags, which
       works because Keith reviews every flag;
     - disagreement between runs IS a supported warning sign;
     - if the union proves too noisy, the backed alternative is three
       runs with a majority vote per claim.
   - **The verbatim-quote script is NOT the same guarantee as the
     Citations feature** (correcting research section 7). ALCE (Gao et
     al., EMNLP 2023) scores a sentence as supported only when its cited
     passages, TOGETHER, back it up, and scores a sentence with no
     citation as zero. A verbatim match proves a quote exists, not that
     it supports the claim. So:
     - the fact-checker judges support sentence by sentence against
       the whole cited set;
     - it flags sentences with no citation;
     - it treats partial support as "not found";
     - the script stays as a separate gate against invented quotes.
   - **Self-correction limits hold, reframed.** Huang et al. (ICLR 2024)
     found that models revising their own reasoning without outside
     feedback got worse. A same-model critic in a fresh context is not
     outside feedback, so the design's real safety comes from the
     sources, the scripts and Keith, not from the critic being a
     separate agent. The paper's "equal effort" point is adopted:
     whatever the critic checks for also goes into the writer's brief.
   - **Lost in the Middle holds, and is cheap to apply** (Liu et al.,
     TACL 2024; tested only at 2-16K tokens on 2023 models). Order each
     agent's context with the defining requirements first, peripheral
     sources in the middle, and the task last (named briefly at the top
     as well).

   All of these papers test 2022-2025 models on tasks unlike this one.
   How far the findings carry over to current Claude models is a
   judgement, not a measurement.

   **Naming session, round 1 (2026-09-29).** Two hazards were already
   settled in signed requirements, so they were not re-opened. The date
   control reads "In place on", not "as of" (REQ-PIPE-081). The seven
   filing decisions already have names (REQ-GHUB-082). "Backfill" was a
   false alarm: it means filling in missing fields, not a synonym.
   Keith's picks:
   - **"Demote", always with its destination.** "Demote to staging"
     (put it back in the queue) or "demote to rejected". "Un-decide"
     becomes a glossary alias. This matches REQ-GHUB-082 (35 uses of
     demote versus 13 of un-decide).
   - **"Substitute" plus "inherit"; "carry forward" is retired.**
     "Substitute" is a person's decision that a period stands on an
     earlier period's supply, shown as "substituted". "Inherit" is the
     automatic case for a dataset that owed nothing that period.
     "Standing in" and "last good one" are plain-English aliases.
     "Carry forward" is retired entirely, because it also means
     supplies for the following period.
   - **"Resupply" takes the model's meaning**: a supply arriving for a
     slot that is already filled. The BUILT status-inferred chain
     (REQ-QAC-008) is explained where supply history appears, badged
     as "how the dashboard guesses today, until the model is built".
   - **"Supply calendar"** replaces "delivery calendar", because
     "delivery" now means one physical drop. **Follow-up flagged:** the
     old phrase appears in code (about 12 uses) and requirements (4).
     The config key is already a plain `calendars`. Renaming the rest is
     separate work, not part of the explainers.

   **Naming session, round 2 (2026-09-29):**
   - **"In development"** is the one name for a dataset that exists
     before its schedule is agreed. It matches the label readers
     already see on the dashboard (REQ-PIPE-106). "Pre-agreement",
     "calendar-less" and "not yet agreed" become aliases. **"Sample"
     stays reserved for the practice-data asset shape**, which clears
     a clash with the `sample` schema. The schema name is a code
     detail; renaming it is flagged as follow-up, not explainer work.
   - **"Recency" for the check category** (the ODCS standard calls it
     "timeliness"). "Early", "on time" and "late" are only ever about
     arrivals. No code change is needed.
   - **Amber "accept" becomes "acknowledge"**, which is what it does,
     so it never sounds like a decision that changes anything.
     "Reject" keeps its meaning as a filing reject. **Follow-up
     flagged:** renaming the `/accept` ticket command.
   - **Four distinct staleness terms, and "stale" retired:**
     - "overdue": a slot whose due time has passed with nothing filed;
     - "no data": nothing to judge as of the chosen date;
     - "recency": a check on the content;
     - "freshness": the (unbuilt) cap on a headline.

     "Stale" is retired as ambiguous, and becomes an alias of "no
     data".

   **Naming session, round 3, and CLOSED (2026-09-29):**
   - **Delivery, arrival and supply are three words, tightly defined.**
     - A **delivery** is one drop from a supplier, which may hold
       several files.
     - An **arrival** is one file we received, with its receipt time
       (REQ-PIPE-105).
     - A **supply** is one table's version, which gets filed and
       judged.

     The glossary shows the three nested in one small diagram.
   - **Readers only ever see "QA run".** A trial is always "a trial",
     never "a trial run". `run_id` and rehearsal-versus-real stay out
     of the explainers, as tooling.
   - **"Waiting on a person" for a supply that needs a decision.**
     "Blocked" is kept only for a healthy table whose check cannot run
     because a neighbouring table is missing or held.
   - **"Cycle" is retired**: "period" everywhere, and "cycle" becomes
     an alias noting the older wording.

   **Glossary canon from the naming session.** Canonical word, then
   aliases:
   - demote (to staging / to rejected) - un-decide;
   - substitute / substituted - standing in, last good one;
   - inherit - (distinct from substitute);
   - carry forward - RETIRED;
   - resupply (arrival into a filled slot) - the built status chain is
     NOT explained (overridden in triage round 7: explain the new
     model only);
   - supply calendar - delivery calendar;
   - in development - pre-agreement, calendar-less, not yet agreed;
   - sample - reserved for the practice-data asset shape;
   - recency (a check category) - ODCS "timeliness";
   - acknowledge (amber) - accept;
   - overdue, no data, recency and freshness are distinct; stale -
     alias of "no data";
   - delivery, arrival and supply are distinct;
   - QA run, and trial;
   - waiting on a person, and blocked (a neighbour);
   - period - cycle;
   - In place on - as of (already settled in REQ-PIPE-081).

   **Triage of the 33 missed concepts (2026-09-29): ALL INCLUDED.**
   Keith's answer, read for intent ("...and default" read as "include
   all by default", a likely dictation artefact): none are excluded.
   The main session had flagged three for him to consider:
   - #6, where a supply physically lives (it leans towards pipeline
     internals);
   - #29, a check's plain-English fields (closer to on-screen help);
   - #31, recorded QA history (its storage half belongs in the
     pipeline docs).

   He did not exclude them either.

   **A standing rule, from the same answer.** Any change to an
   explainer goes through Keith, including when a build changes the
   concept it explains, "just in case there are changes that happen as
   part of building stuff". It was written into CLAUDE.md, because it
   binds every future session, not only this one. Its effect on the
   design: a building session never edits `docs/explainers/` or
   refreshes fingerprints. It reports which explainer is affected, and
   the staleness-gate route (fact-checker proposes, Keith approves and
   re-signs) is the ONLY way an explainer changes. The write-restriction
   hook and the post-run diff check are how the agents are held to
   this; a CI check that `docs/explainers/` changes only in commits
   carrying Keith's sign-off could be added in the requirements.

   **Triage reopened (2026-09-29).** Keith asked to walk through all 33
   one by one with the question tool, giving his triage per concept,
   with the main session's recommendation on each; tiering comes after.
   The "all included" reading above is a default, not his triage. The
   tiering proposal already shown to him (10 own pages, 20 sections, 2
   glossary-only, check scopes carried by group 8's page) is on hold
   until then.

   **Triage walk-through (2026-09-29), recorded round by round.** The
   options per concept were include / leave out / park / pipeline docs,
   each with a main-session recommendation:
   - Round 1: #1 data contract, #2 check and warn/fail thresholds, #3
     statuses that aren't verdicts, #4 qualifiers - all INCLUDE, as
     recommended.
   - Round 1 re-asked after a session restart; same answers.
   - Round 2: #5 arrived vs promoted, #7 automatic promotion gate, #8
     automation defers to a person - INCLUDE. #6 where a supply lives -
     INCLUDE LIGHTLY: explained as places a supply moves between, not
     as schemas; the physical detail goes to the pipeline docs.
   - Round 3: #9 actor, reasons and the people list - PIPELINE DOCS
     (Keith's call, against the main session's "include"
     recommendation). #10 the seven filing decisions, #11 check scopes,
     #12 check dependencies and comparisons - INCLUDE.
   - Round 4: #13 why a check couldn't run, #14 load failure, #15 event
     severity, #16 what recognition can't place - INCLUDE.
   - Round 5: #17 unfiled supply, #18 assignment under ambiguity, #19
     a slot closed unfilled, #20 an arrival verdict follows its filing
     - INCLUDE.
   - Round 6: #21 three moments, #22 calendar detail (all six parts),
     #23 in development and graduating - INCLUDE. #24 one-off
     extraction - INCLUDE LIGHTLY: a short, badged section in group 1's
     "the shape varies", with no detail until requirements exist.
   - Round 7: #25 a trial - INCLUDE BRIEFLY (a glossary entry plus a
     line in the hand-filed supply section). #26 "no data" as of a date
     and #28 QA and overdue tickets - INCLUDE. #27 the built resupply
     chain - NOT explained: "explain the new model instead" (Keith's
     own answer). Resupply is explained only as the model's arrival
     into a filled slot. This overrides the naming-session note that
     the built chain would be explained separately; the glossary canon
     above has been corrected.
   - Round 8: #29 a check's plain-English fields - INCLUDE BRIEFLY (a
     glossary entry plus a line in "what a check is"). #30 changing or
     retiring a check - PIPELINE DOCS (Keith's call, against the main
     session's "include"). #31 recorded QA history - SPLIT: the idea
     ("history is permanent and never rewritten") in the explainers,
     the storage in the pipeline docs. #32 "In place on" versus what
     the page said then - INCLUDE.
   - Round 9: #33 newest promoted wins - INCLUDE.

   **Triage result: 29 included, 2 to the pipeline docs, 2 split.**
   - To the pipeline docs: #9 (who can decide) and #30 (changing or
     retiring a check).
   - Split between the two tracks: #6 (where a supply lives) and #31
     (recorded QA history).
   - Included only briefly: #25 (a trial) and #29 (a check's
     plain-English fields).
   - Included, but explaining only the new model: #27, the built
     resupply chain.

   **The line between the two tracks, confirmed by Keith (2026-09-29):
   how the system is OPERATED AND MAINTAINED belongs in the pipeline
   docs** (permissions, configuration changes, check upkeep). The
   explainers cover what things MEAN to a reader. It came from the two
   concepts he sent to the pipeline docs against the recommendation,
   and it is the starting rule for the split sweep (queue item 3b).

   **The two-track sweep (queue item 3b, 2026-09-29).** Keith suspected
   the explainers were over-weighted and the pipeline docs thin. The
   finding: the imbalance was an artefact of what had been inventoried
   so far. Only CONCEPTS had been sorted, and concepts are naturally
   explanation-shaped. The pipeline docs' content is mostly how-to and
   reference, which had not been listed yet. Once listed (see item 2),
   it is larger than the explainers. Keith's calls:
   - **The tracks split by Diátaxis type.** The explainers are
     explanation: what things mean, for the user. The pipeline docs are
     how-to guides, reference, and technical explanation of how the
     system is built and run. His "operated and maintained" line falls
     out of this.
   - **A concept with two halves is split and cross-linked.** The
     explainer covers what it means and why, and a pipeline how-to
     covers the steps. Each links to the other, and neither repeats the
     other. Examples: the decision log and the seven decisions; calendar
     versions and runway; file patterns; the "when a person is needed"
     group; `check_id`.
   - **The pipeline docs' readers are engineers AND operators.** The
     how-tos are written for the people who operate it day to day
     (making filing decisions, clearing holds); the reference and
     technical explanation are for engineers.
   - **The explainers track is called "Understanding Mothman".** The
     option he picked paired it with **"Running Mothman"** for the
     pipeline docs. That pairing is treated as intended, but is
     unconfirmed. Still open: whether `docs/explainers/` is renamed to
     match.

   **Re-baseline after the overnight merge (2026-09-29).** Keith: the
   other session built a lot overnight, "like promotion", so the map was
   stale. 86 commits were merged in (`e3526d8`). Build status changed
   for 12 concepts the map relies on:
   - REQ-DASH-056 arrived versus promoted;
   - REQ-DASH-085 and REQ-DASH-100 the stand-in qualifiers;
   - REQ-DASH-094 which environment a dashboard shows;
   - REQ-GHUB-082 filing decisions from GitHub or the terminal;
   - REQ-PIPE-074 the decision log;
   - REQ-PIPE-075 the promotion gate;
   - REQ-PIPE-076 rejection, demote, and automation deferring to a
     person;
   - REQ-PIPE-084 substitute;
   - REQ-PIPE-098 and REQ-PIPE-099 inherit and un-inherit;
   - REQ-QAC-108 drift measured against the last promoted period.

   All are now BUILT. REQ-PIPE-079 (why a check couldn't run, QA against
   the filed period) and REQ-PIPE-083 (tickets) are in progress. The
   "designed, not built" badge therefore now applies to much less of
   groups 4-6. Still unbuilt: holds as a recorded state (078), mixed-
   period deliveries (077), "In place on" (081), file-shape checks
   (096/097), and the recorded arrival classification (080).

   **New since the triage**, not yet triaged:
   - **REQ-PIPE-083 re-shaped**: every slot has ONE ticket, reconciled
     to its current state, never a stream of events. REQ-GHUB-109 (a
     ticket comment only when something changed) goes with it. This
     replaces the "an overdue slot raises its own ticket, once" wording
     triaged as #28.
   - **REQ-PIPE-110**: `contract/calendar.yaml` as the one place a
     **delivery agreement** lives (not built).
   - **REQ-PIPE-111**: a calendar's history cannot be edited (not
     built).
   - **REQ-PIPE-112**: the asset's timezone is versioned (not built).
   - **REQ-PIPE-113**: a slot's due instant comes from the agreement,
     and overlapping windows are refused (not built).
   - **REQ-TEST-114**: the terminal says which environment it acts
     against. This is operating the system, so pipeline docs.

   **Naming clashes with the naming session:**
   - "Supply calendar" (Keith's pick) has ZERO uses anywhere. The
     overnight requirements introduced "delivery agreement" (5 uses)
     and a file called `calendar.yaml`.
   - "Reconcile" is now established (79 uses in requirements, 48 in
     code).
   - "Stand on" / "standing on" is widespread (28 in requirements, 24
     in code), and was already a listed alias.

   **Re-baseline decisions (Keith, 2026-09-29):**
   - **"Delivery agreement" and "supply calendar" are nested, both
     kept.** The delivery agreement is what we agreed with a supplier
     (REQ-PIPE-110, in `contract/calendar.yaml`). The supply calendar
     is the schedule of periods and due dates INSIDE it. They are two
     related glossary entries.
   - **Tickets: explain the new model.** Group 6's ticket page explains
     "one ticket per slot, always showing where that supply has got
     to" (REQ-PIPE-083, REQ-GHUB-109). The reconciling mechanics go to
     the pipeline docs. This replaces #28's old wording.
   - **The new calendar requirements (110-113): meaning in, config
     out.** The explainers get the reader's meaning, badged not built:
     a past due date can never change, and windows never overlap so a
     supply belongs to one slot. Where the file lives and how the
     timezone is versioned go to the pipeline docs, as does
     REQ-TEST-114.
   - **Triage decisions stand; the "not built" badge simply drops**
     from the concepts built overnight. Tiering proceeds on the updated
     picture.

   **GOV.UK research (2026-09-29, Keith's ask).** Primary sources are
   the `alphagov` repos on GitHub, because `www.gov.uk` and every
   `*.service.gov.uk` guidance site are blocked:
   - `govuk-content-publishing-guidance`, the source of the A to Z,
     the Technical A to Z and the writing guidelines, read in full;
   - `govuk-developer-docs`;
   - `tech-docs-template`;
   - `gds-way`.

   The main session re-verified two quotes at source: titles and
   headings "not be questions", and "friendliness can lead to a lack
   of precision".

   **Conflicts with style rounds 1-4, for Keith (round 5 of style):**
   - question headings;
   - puns in headings (GOV.UK's tone is "incisive", with no
     metaphors);
   - bold for a new term (GOV.UK marks a term with 'single quotes' and
     uses bold only for interface labels);
   - a sources section at the end (GOV.UK says not to gather links at
     the bottom, though provenance is not "further reading").

   **Clashes with Mothman's own words:** "promote", "deliver", "assets"
   and "issues" are on GOV.UK's words-to-avoid list. The recommendation
   is to give each a glossary entry rather than rename it, since
   GOV.UK's own rule is to explain specialist terms.

   **Agrees with our decisions:**
   - "you" (and "we" once the team is named);
   - a 25-word sentence cap;
   - "29 September 2026" dates;
   - the banned-word lists, with GOV.UK's reason: "easy", "simple"
     and "quick" demoralise readers who do not find it so;
   - splitting documents by type and cross-linking.

   **Numbers:** "one" in words, numerals from 2, which supports round
   4 (the Style Manual itself is still unconfirmed).

   **New rules GOV.UK would add:**
   - "cannot" / "do not" rather than contractions (but "you'll" is
     fine);
   - paragraphs of five sentences at most;
   - no semicolons;
   - no eg / ie / etc;
   - "to" in ranges rather than a dash;
   - "11:59pm" rather than "midnight";
   - accessible titles and descriptions on every diagram.

   **For "Running Mothman", follow GDS closely:**
   - verb-first task titles with no "How to";
   - the steps first, and "how it works" lower down;
   - troubleshooting on the task page, not an FAQ;
   - numbered steps, each saying what the command does;
   - `<CAPS_WITH_UNDERSCORES>` placeholders;
   - "must" / "should" / "can" for requirement / recommendation /
     option;
   - reference generated from the code;
   - a "Get started" page;
   - a last-reviewed date on every page.

   GDS also warns that concept pages are the type readers skip most,
   which argues for each explainer's one-sentence answer coming first.

   **Style round 5 - the GOV.UK conflicts (Keith, 2026-09-29):**
   - **Headings: follow GOV.UK - statements, not questions.** This
     REVERSES style round 1's "mostly questions". Titles are not
     questions either. The why-question lives in each page's brief and
     opening answer, not in its headings.
   - **Humour narrowed: wry asides stay in body text; puns come OUT of
     headings and titles**, where they cost skimming and search.
     Analogies stay, as the explainers' core device.
   - **New terms stay bold** (not GOV.UK's single quotes). Bold is
     still reserved for defined terms only, which answers GOV.UK's real
     concern (no bold for emphasis).
   - **Added from GOV.UK:**
     - "cannot" and "do not" rather than contractions ("you'll" is
       still fine);
     - paragraphs of five sentences at most;
     - no semicolons;
     - no eg / ie / etc;
     - "to" in ranges, never a dash;
     - "11:59pm" rather than the ambiguous "midnight", which matters
       for due times.
   - **Not added: a separate accessible title and description per
     diagram.** Round 6's required caption already doubles as each
     diagram's accessible description.
   - **The sources list stays at the end, and links also go inline.**
     The list is provenance, not "further reading". Links a reader
     actually needs (the glossary, related pages) go inline where they
     are relevant, never only at the bottom.
   - **"Running Mothman" adopts GDS technical-writing conventions
     wholesale** as its house standard:
     - verb-first task titles;
     - the steps first;
     - troubleshooting on the task page;
     - numbered steps;
     - `<CAPS>` placeholders;
     - "must" / "should" / "can";
     - reference generated from code;
     - a "Get started" page;
     - last-reviewed dates.
   - **GOV.UK's words-to-avoid that are real Mothman terms** (promote,
     deliver, assets, issues) are kept as terms and each defined in
     the glossary. In general prose, where they are not the term,
     GOV.UK is followed (e.g. "problems", not "issues").
   - **Answer first, always.** The first sentence of every "In short"
     box is the one-line answer to the page's why-question, so a
     skimmer who reads nothing else still leaves with it. Concept pages
     are also reached from the dashboard's "What's this?" links, where
     readers are actually confused.

   **Baseline switched from the Australian Style Manual to GOV.UK
   (Keith, 2026-09-29): "Fine, ignore the style manual. GovUK is a bit
   better anyway - in my opinion."** The Style Manual cannot be read
   from here anyway (its own host refuses scripted clients; see
   CLAUDE.md). What changes, checked against GOV.UK's A to Z source:
   - **The house baseline** is now GOV.UK's guidance plus Keith's own
     preferences, not "a mix of the Style Manual and Keith's own".
   - **Numbers (queue item 8): resolved by GOV.UK.** Write "one" in
     words unless it is a step or list point; everything else in
     numerals, including 2 to 9. Item 8 is closed, and the Style Manual
     is no longer needed.
   - **Dates** are unchanged ("4 June 2017" style; "to" in ranges,
     already adopted).
   - **Dashes:** GOV.UK has no rule for a break in a sentence, so the
     spaced en dash ( – ) stands as Keith's own preference. It was
     never GOV.UK's.
   - **Oxford comma:** still Keith's own "always". GOV.UK has no rule,
     and its examples omit it.
   - **Spelling:** Australian spelling stays (it differs from GOV.UK's
     UK spelling almost nowhere), but it is now Keith's preference
     rather than a Style Manual rule.
   - **A NEW CONFLICT for Keith:** GOV.UK says "do not use quarter for
     dates, use the months" (e.g. "Jan to Mar 2013"). But Mothman's
     quarterly PERIOD is a real domain concept with its own name (e.g.
     `2026-Q3`). This is to be asked, not assumed.

   **Tiering walk-through (2026-09-29), recorded round by round.** The
   tiers are an own page, a section inside another page, or a glossary
   entry only.
   - **Quarters (the GOV.UK conflict): term plus months on first
     use.** Keep "period" and names like `2026-Q3` (they are what the
     dashboard shows), but prose always says which months on first
     use: "the 2026-Q3 period (July to September 2026)".
   - Round 1:
     - #1 data contract: OWN PAGE (group 1).
     - #2 what a check is, warn versus fail: OWN PAGE (opens group 8).
     - #3 statuses that aren't verdicts: OWN PAGE (group 7), absorbing
       #4 qualifiers, #15 event severity and #26 "no data as of" as
       its sections.
   - Round 2:
     - #5 arrived versus promoted: OWN PAGE (group 4), absorbing #21
       (three moments) and #33 (newest promoted wins).
     - #7 the automatic promotion gate: OWN PAGE (group 4, "how a
       supply goes live"), absorbing #6 (where a supply lives, lightly)
       and #8 (automation defers to a person).
     - #10 the seven filing decisions: OWN PAGE as group 4's hub, with
       all seven in one table linking to where each is explained.
     - #11 check scopes: carried by group 8's GROUP PAGE, with one
       concept page per level.
   - Round 3:
     - #12 check dependencies and comparisons: SECTIONS, with
       dependencies in the cross-table checks page and the comparison
       point in the drift and volume page (group 8).
     - #13 why a check couldn't run: SECTION in group 7's
       red/amber/green page.
     - #16 what recognition can't place: OWN PAGE (group 3, "when a
       file can't be placed or read"), absorbing #14 load failure.
     - #17 unfiled, #18 filed under ambiguity, #19 a slot closed
       unfilled: SECTIONS in group 4's slot-assignment page.
   - Round 4:
     - #20 an arrival verdict follows its filing: SECTION in group 3's
       arrival-timing page.
     - #22 calendar detail plus REQ-PIPE-110 to 113: SECTIONS across
       group 2, AND the **delivery agreement gets its OWN PAGE**
       (Keith's pick over sections only), as the new top-level idea
       the supply calendar sits inside.
     - #23 in development and graduating: OWN PAGE (group 1).
     - #24 one-off extraction: SECTION in "the shape varies", short
       and badged, growing into a page once it has requirements.
   - Round 5:
     - #25 a trial and #29 a check's plain-English fields: GLOSSARY
       plus a line each (in the hand-filed supply section and in "what
       a check is").
     - #28 tickets (the new one-per-slot model): OWN PAGE (group 6).
     - #32 "In place on" versus what the page said then: OWN PAGE
       (group 9), with #31 recorded QA history as a SECTION in it.

   **Result for the 33: 11 own pages:**
   - #1 data contract;
   - #2 what a check is;
   - #3 statuses that aren't verdicts;
   - #5 arrived versus promoted;
   - #7 the promotion gate;
   - #10 the seven filing decisions;
   - #16 when a file can't be placed or read;
   - #23 in development;
   - #28 tickets;
   - #32 In place on;
   - the delivery agreement.

   The rest are sections or glossary entries, as recorded above; #11
   is carried by group 8's group page. **Keith then asked for the
   ORIGINAL map concepts to be tiered the same way, one by one.**
   - Originals, round 1:
     - the data asset and its hierarchy: ONE OWN PAGE for both.
     - the shape varies (scheduled asset, one-off extraction, sample;
       same code, separate deployment): ONE OWN PAGE.
     - environments, and which environment a dashboard shows: SECTION
       in the shapes page (setup goes to the pipeline docs).
     - schedule: FOLDED into the supply calendar ("schedule" becomes a
       glossary alias). Readers get delivery agreement, then supply
       calendar, then periods and slots.

   **CORRECTION, found by the live GOV.UK research and verified in
   `contract/data-asset.yaml` (2026-09-29).** The quarters question
   above was asked with a WRONG example. Mothman's quarterly periods
   are NOT calendar quarters: they are authored dates anchored on 1
   February, May, August and November ("deliberately NOT calendar
   quarters"; Child Protection's real agreed cadence). So "2026-Q3" is
   a named PERIOD whose supply is due on 1 August 2026, not "July to
   September 2026". A WA reader could also read "Q3" as a
   financial-year quarter. Keith's "term plus months on first use"
   answer was given against the wrong example, so it is re-asked below
   rather than applied.

   **Live GOV.UK / GDS research (2026-09-29, second pass, after Keith
   allow-listed the hosts).** It read the GDS Way, the Design System,
   the Service Manual, "Documenting APIs", and 10 GDS blog posts
   (2013-2021). New findings:
   - **Diagram accessibility.** Mermaid exposes an accessible title and
     description only via `accTitle` / `accDescr` in the diagram
     source (GDS Way, "Diagrams as code"). A visible caption counts
     only if it is a `<figcaption>` inside a `<figure>`. Round 5's
     "the caption doubles as the accessible description" needs one of
     those to actually be true.
   - **Don't organise documentation by user type** ("Documenting
     APIs", 2022). Our split by PURPOSE (Understanding / Running) is
     fine, but navigation should not say "for engineers" or "for
     operators".
   - **The writing guidance now lives at
     `guidance.publishing.service.gov.uk`** ("Writing to GOV.UK
     standards"), so citations should point there.
   - **For the explainers:**
     - no heading may use a term before the page has explained it;
     - redefine terms on every page, not only in the glossary;
     - the "In short" box matches the Design System's lead paragraph;
     - page summaries of 160 characters or fewer.
   - **For the dashboard's "What's this?" links:** status tags must
     not be clickable, because users mistook them for buttons. So the
     link goes NEXT TO a status, not on it. UI copy "aims to be
     boring", with no humour.
   - **For Running Mothman:**
     - code blocks with no `$` prompt, no line numbers, pasteable;
     - pages in the order: what it does, Get started, tasks,
       reference, support;
     - link to dbt, Soda and Evidently's own documentation rather than
       paraphrasing it;
     - terminal error messages say what happened and how to fix it
       (no "invalid", "please" or "sorry");
     - every page carries a last-reviewed date, a review-by date and
       an owner, with a reminder bot, because GDS found content cannot
       be tested like code.
   - **A time-based review would complement the fingerprint staleness
     gate.** It catches a world that changed while no cited file did.
   - **Release notes (GDS):** verb headings, "You can now...", no
     "We've fixed...". This touches the `CHANGELOG.yaml` header, which
     needs Keith's approval of exact wording, so it is only flagged.

   **New blocked hosts:** `www.ncsc.gov.uk`, `insidegovuk.blog.gov.uk`,
   `userresearch.blog.gov.uk`, `designnotes.blog.gov.uk`,
   `accessibility.blog.gov.uk`, `service-manual.ons.gov.uk`,
   `analysisfunction.civilservice.gov.uk`, `design.tax.service.gov.uk`,
   `design.education.gov.uk`, `service-manual.nhs.uk`.
   `technology.blog.gov.uk`'s search page served a bot challenge,
   which was not worked around.

   **Keith's calls on the live research (2026-09-29):**
   - **Quarters, re-asked with the correct example: the name plus its
     due date on first use** - "the 2026-Q3 period (supply due 1 August
     2026)" on first use on each page, then just "2026-Q3". The name
     is treated as a defined term, like GOV.UK treats "tax year". This
     REPLACES the earlier "term plus months" answer, which rested on
     the wrong example.
   - **Diagram accessibility: `accTitle` / `accDescr` generated from
     the caption.** The illustrator writes the caption once, and the
     validator checks that every Mermaid block also carries it as
     `accTitle` / `accDescr`. This works identically on GitHub and in
     the dashboard.
   - **Time-based review ALONGSIDE the fingerprint gate.** Every page
     carries a last-reviewed date and a review-by date (say six
     months). Fingerprints catch "a cited source changed"; the review
     date catches "the world changed but no cited file did". The
     staleness badge shows both.
   - **"What's this?" links sit BESIDE a status or term, never on it,
     with plain wording.** There is no humour in any dashboard UI text;
     humour stays in the explainer bodies only.
