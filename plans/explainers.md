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
