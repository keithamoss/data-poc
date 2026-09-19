# HCI and behavioral-psychology grounding for this project's UX work

The deeper grounding Keith asked to revisit once the UX/visual-critic
build loop was done (`plans/wider.md` #10's own deferred item, from
right after that split) - real research on human psychology and use of
computer/digital systems, not just "consistency + workflow fit."
Scoped with Keith directly (2026-09-19, two rounds of clarifying
questions before any research started): covers **both** classic HCI/
usability psychology and behavioral/motivational psychology, roughly
equal weight; reaches **both** the dashboard and the CLI/TUI (`mothman`)
- the interactive wizard and plain non-interactive command-line usage
alike; proactive/foundational rather than a response to one bad moment;
and the guidance below is **context-indexed** (Keith's own explicit
ask) - different principles get emphasized for different kinds of
interaction moments, not one flat checklist applied everywhere.

Read by: `requirements-ux`/`requirements-ux-critic` (dashboard, pre-
and post-build) and `requirements-cli-ux`/`requirements-cli-ux-critic`
(CLI/TUI, pre- and post-build).

## The research (see Sources at the bottom for the real citations)

**HCI / usability psychology:**
- **Cognitive Load Theory** (Sweller) - working memory holds ~7±2
  items (Miller's Law); *intrinsic* load is a task's natural
  difficulty, *extraneous* load comes from poor layout, inconsistent
  navigation, or confusing labels - chunking (grouping related
  elements, multi-step flows) is the standard mitigation.
- **Nielsen's 10 usability heuristics** - visibility of system status,
  match between system and the real world, user control/freedom,
  consistency and standards, error prevention, recognition rather than
  recall, flexibility/efficiency of use, aesthetic/minimalist design,
  help users recognize/diagnose/recover from errors, help and
  documentation.
- **Hick's Law** - decision time grows with the number and complexity
  of choices; **progressive disclosure** (show essentials, reveal more
  as intent narrows) is the standard fix.
- **Fitts's Law** - the time to acquire a target is a function of its
  size and distance (a tap-target/mouse-target concern, mostly
  dashboard-relevant).
- **Doherty Threshold** - productivity peaks when a system responds to
  the user in **under 400ms** - a real, concrete number, not just
  "make it fast."
- **Gestalt principles** - proximity, similarity, figure-ground, common
  region, Prägnanz (the simplest interpretation wins) - how visual
  grouping and hierarchy get read at a glance.
- **Von Restorff Effect** - the one item that differs from similar
  surrounding items is what gets remembered.
- **Jakob's Law** - users spend most of their time on OTHER
  tools/sites, so they prefer yours to work the way those already do.
- **Paradox of the Active User** - users never read manuals; they start
  using the software immediately. A real corrective against assuming
  verbose help text alone solves discoverability.
- **Tesler's Law** (conservation of complexity) - complexity can't be
  eliminated, only relocated - a real justification for *why*
  progressive disclosure exists: drill-down doesn't remove a QA
  pipeline's real complexity, it just relocates where the user meets it.
- **Zeigarnik Effect** / **Goal-Gradient Effect** - incomplete tasks are
  remembered more vividly than completed ones, and motivation rises as
  a goal gets closer - both relevant to multi-step wizard flows.
- **CLI-specific** (`clig.dev`, a real, detailed primary source):
  human-first design; help text that leads with examples; errors
  rewritten for humans with a suggested fix, not a raw stack trace;
  flags preferred over positional args; confirm before destructive
  actions, with typed confirmation for severe risk; progress shown
  within 100ms; respect `NO_COLOR`/`--json`/TTY-detection conventions;
  never phone home without explicit opt-in.
- **TUI-specific**: spatial consistency (fixed panel positions build a
  real mental map - never rearrange without explicit user action);
  progressive disclosure via a few visible shortcuts plus full help
  behind `?`; async operations that never freeze the UI, with real
  progress indication.

**Behavioral / motivational psychology:**
- **Self-Determination Theory** (Deci & Ryan) - three basic
  psychological needs: autonomy (real, self-endorsed choice),
  competence (feeling effective), relatedness (feeling connected).
  Most tools over-index on competence (metrics, progress bars,
  achievements) and neglect autonomy and relatedness.
- **Fogg Behavior Model** - behavior = motivation × ability × prompt.
  For HABITUAL use specifically, raising *ability* (removing friction)
  beats raising motivation.
- **Habit formation** (Lally et al., 2010, real longitudinal study) -
  automaticity took a median of ~66 days across real participants
  (range 18-254), and **consistency of the cue/context predicted habit
  formation better than motivation did** - a single missed day did not
  meaningfully hurt it.
- **Learned helplessness** (Seligman & Maier) - repeated unhelpful
  errors teach people to stop trying, not just to feel briefly annoyed.
- **Negativity bias** (Baumeister, Bratslavsky, Finkenauer & Vohs,
  2001; Rozin & Royzman) - broad, well-replicated, cross-domain
  research. The specific mechanism that matters most here is
  **negativity dominance**: an experience's overall impression skews
  MORE negative than a simple average of its good and bad moments would
  predict - "the whole is more negative than the sum of its parts."
- **Attribution theory** (via the service-recovery-paradox literature) -
  people judge a failure by *locus* (who's responsible), *stability*
  (how likely to recur), and *controllability*. People who attribute a
  failure to external factors are measurably more forgiving than those
  who blame the system itself.
- **Service recovery paradox** - a well-handled failure CAN produce
  higher trust than no failure at all, but this is narrower than
  commonly quoted: a real 2009 study (Michel & Coughlan) found it only
  holds when baseline service isn't already excellent and the failure
  reads as non-serious and out of the provider's control; meta-analyses
  find a real effect on satisfaction but not consistently on behavior.
  Worth aiming for, not the main justification for investing in error
  states - negativity bias is the more robust reason.
- **Peak-End Rule** (Kahneman & Fredrickson, 1993) - people judge an
  experience by its most intense moment and its ending, not the
  average - "duration neglect." NN/g's own real elaboration: this
  applies to BOTH ends of the spectrum - a genuinely good ending (a
  clean "all checks passed" moment) and a genuinely bad one (an
  unexplained, dead-end error) both get outsized weight in how the
  whole session is remembered.
- **First impressions** (Lindgaard et al., 2006, a real, heavily-cited
  study) - visual appeal judgments form in as little as **50
  milliseconds** and correlate with later judgments of credibility and
  usability (a halo effect).
- **Flow state** (Csikszentmihalyi) - clear goals, timely feedback,
  minimal distraction, challenge matched to skill.

## The context taxonomy

Six real interaction moments that exist on BOTH surfaces today, each
with different dominant principles - proposed after the research, not
before, per how Keith asked this to work (he confirmed the taxonomy and
the weighting below, 2026-09-19).

| Context | Dashboard example | CLI/TUI example | Dominant principles |
|---|---|---|---|
| **At-a-glance / scanning** | exec tier | `mothman` main menu | recognition over recall, Gestalt hierarchy, Hick's Law (don't overload the first screen), Von Restorff Effect (a failing check should visually stand out, not just be color-coded) |
| **Investigating / drill-down** | dataset/column/check tiers | `mothman debug run-*`, real dbt/Soda output | progressive disclosure, flow state, Tesler's Law (complexity relocated here, not eliminated) |
| **First-time use** | a new agency data owner's first visit | a new user's first `mothman` run | autonomy (real choice, not a forced path), Paradox of the Active User (smart defaults + inline hints, don't rely on docs being read), Jakob's Law (match existing conventions) |
| **Routine daily use** | a steward's daily QA check-in | a steward's daily `mothman bdm qa` | Fogg model (minimize friction over motivation), consistency, Doherty Threshold (<400ms), Goal-Gradient Effect (wizard progress) |
| **Error / failure states** | a failing check, a bad as-of state | a `ClickException`, a real dbt/Soda bug | non-punitive framing, avoiding learned helplessness, `clig.dev`'s own edge-case guidance (explain what broke + a realistic next step, never blame the user for an infra issue) |
| **Configuration / setup** | editing a check's own lifecycle metadata | writing a new check, editing contract YAML | error prevention (confirm destructive actions), recognition over recall (follow existing patterns), Hick's Law |

**Cross-cutting, not tied to one row**: peak-end applies at the
whole-session level too - the moment a QA run or wizard flow *finishes*
is a real, deliberate design opportunity (a clean "all checks passed"
moment), not just a state to reach and move past.

## The research-based weighting

Not every context is backed by research of equal strength - stated
honestly rather than presenting a false, uniform precision:

1. **Error/failure states - the most strongly justified priority**, for
   two separate, convergent reasons: negativity bias means a single bad
   moment disproportionately colors an otherwise-clean session (it
   doesn't average out), and attribution theory gives the precise
   mechanism for damage control (be honest about locus/stability - a
   real infra failure is not the user's fault, and say whether it's a
   one-off or something that will keep happening). The service-recovery-
   paradox angle is real but narrower than often assumed - a bonus to
   aim for, not the main justification.
2. **First-time use - high priority, for a narrower reason than
   "impressions matter" generically.** Lindgaard's 50ms finding is
   specifically about how fast VISUAL judgments form and correlate with
   later credibility/usability judgments - the strongest argument for
   investing in the very first screen specifically (the dashboard's
   first load, `mothman`'s own banner/main menu), not a claim about the
   rest of onboarding.
3. **Routine daily use - real, but on a long horizon, and about a
   different thing than motivation.** Lally's research argues for
   investing in PREDICTABILITY (same place, same flow, every time) over
   trying to make routine use "delightful" on each individual run - a
   single missed day doesn't break habit formation, an inconsistent cue
   does.
4. **At-a-glance/scanning, investigating/drill-down, and configuration/
   setup** - real, established theory (Doherty Threshold, Hick's/
   Fitts's Law, flow state, Nielsen's heuristics), but no research found
   that quantifies how much these matter RELATIVE to each other or to
   the three above - they stay in the taxonomy on solid theoretical
   footing, without the same evidentiary weight.

Net ordering: **error states > first-time use > routine daily use >
(scanning / investigating / configuration, theory-grounded but not
evidentially ranked against each other).**

## Sources

Real primary/well-cited sources actually read or fetched (not just
WebSearch synthesis) during this research:
- `raw.githubusercontent.com/cli-guidelines/cli-guidelines` (`clig.dev`'s
  own real source - the site itself is blocked, see `CLAUDE.md`)
- `lawsofux.com` - the real, full list of 26 laws/principles
- NN/g, "The Peak-End Rule: How Impressions Become Memories" (Lexie
  Kane, 2018) - including the real Spotify error-message worked example
- Wikipedia, "Negativity bias" (Rozin & Royzman's four-element model,
  the "dishonest person" asymmetry example, the attention/cognition
  evidence)
- Wikipedia, "Service recovery paradox" (the blame-attribution model,
  the real conditions under which the paradox does and doesn't hold,
  the Michel & Coughlan 2009 finding)

Real, named studies/papers cited above via WebSearch synthesis (not
directly fetched, but consistently and specifically attributed across
multiple independent secondary sources):
- Baumeister, Bratslavsky, Finkenauer & Vohs (2001), "Bad is Stronger
  than Good," *Review of General Psychology*
- Kahneman, Fredrickson, Schreiber & Redelmeier (1993), "When More Pain
  Is Preferred to Less: Adding a Better End," *Psychological Science*
- Lindgaard, Fernandes, Dudek & Brown (2006), "Attention web designers:
  You have 50 milliseconds to make a good first impression!," *Behaviour
  & Information Technology*
- Lally, van Jaarsveld, Potts & Wardle (2010), "How are habits formed:
  Modelling habit formation in the real world," *European Journal of
  Social Psychology*
- McCollough & Bharadwaj (1992) and Michel & Coughlan (2009) - the
  service-recovery-paradox literature
- Sweller (cognitive load theory), Nielsen & Molich (1990)/Nielsen
  (1994) (usability heuristics), Seligman & Maier (learned helplessness),
  Deci & Ryan (Self-Determination Theory), Fogg (Behavior Model),
  Csikszentmihalyi (flow) - foundational, widely-cited work referenced
  consistently across multiple independent sources during this research
