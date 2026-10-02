# Glossary seed: notes for Keith

This covers the draft `drafts/glossary.yaml`, which is the seed for `docs/explainers/glossary.yaml` (REQ-DOCS-119). Nothing in the repository has been touched.

## Summary

- There are 50 entries.
- 3 are ideas: one-off extraction, sample, and freshness.
- 3 are drafts: scheduled asset, one-off extraction, and sample. These are the three placeholder names for the asset shapes.
- It loads with `Glossary.model_validate`, and `glossary_problems` returns `[]`.
- I rendered it with `render_glossary_md`. The diagram passes `check_mermaid`, including caption, accTitle and accDescr, seed, and look. It also passes the real Mermaid 11.17 parse. Its only classDef uses the `good` palette colours.
- Every definition passes the house prose checks run on it: 25 words or fewer per sentence, the banned lists, semicolons, eg/ie/etc, negative contractions, dashes, ranges, and no requirement ids or file paths. It also passes the validator's safety patterns (no URL, no HTML).
- The only GOV.UK words-to-avoid hits are "allow" matching inside "grace allowance". I think that is a false positive, because "allowance" is the requirement's own noun.
- The preview render is at `scratchpad/glossary.preview.md`.

## The five things most worth your eye

1. **I put "asset" and "issue" in as aliases, not as entries of their own.** "Asset" is an alias of **data asset**, and "issue" is an alias of **ticket**. This keeps one canonical word per concept. But criterion 11 says the glossary "SHALL define promote, deliver, asset and issue as Mothman terms". An alias has no definition of its own, so the criterion is met only indirectly: glossary.md prints "Also called: asset" under the data asset definition. The literal alternative is a separate `asset` entry and a separate `issue` entry. That gives two definitions for one thing, which is what the glossary exists to prevent. Which do you want?
2. **The recall check makes some aliases and forms expensive.** REQ-DOCS-121 counts a page as using a term whenever the term, an alias or a form appears in its prose, at word boundaries and in any case. The page must then cite that entry's defining requirements, and the least-built rule then pulls the page's badge down.
   - Common words now trip this: schedule, accept, as of, stale, cycle, grace, timeliness, early, late, on time, overdue, blocked, not expected (a form), fill/filling/unfilled, promoted, rejected, inherited, issue/issues, asset/assets, and stand on/standing on.
   - Two examples. "The dataset was not expected to change" would count as using "not-expected period". "No data as of 1 August" would count as using "In place on" (REQ-PIPE-081, not built).
   - This matters for the first page too. Periods and slots will certainly say "supply", "dataset" and "filled". Those cite REQ-PIPE-034, REQ-PIPE-062, REQ-PIPE-075 and REQ-QAC-039, which are all partly built. So the page will badge "partly built", not "built".
   - Separately, REQ-PIPE-053 is now partly built. REQ-DOCS-130's decision says every source of the first page is built and signed. That is no longer true of 053 on its own.
   - Please say whether any alias or form should go, or whether any defining requirement should change.
3. **I put "stand on" under substitute, but inherit stands on something too.** Your re-baseline said "'stand on' is an alias", without saying of what. I followed the naming hazard cluster (carry forward / substitute / patch / stand in / last good one) and put it with substitute. Its forms "stands on", "standing on" and "stood on" went there too. But REQ-PIPE-098's title and the inherit definition both say a period "stands on" its supply. So every inherit page would also count as using substitute. The other options are to drop "stand on" as an alias, or to make it an entry of its own for the shared idea.
4. **The asset shapes overlap with REQ-PIPE-106.**
   - **One-off extraction** is marked as an idea, following REQ-DOCS-116's decision, which uses "one-off project extractions" as its example of an idea. But REQ-PIPE-106 (built) already distinguishes a dataset that "never will" agree a schedule, which it calls "a one-off extraction for a project". So the idea may be only half an idea. The whole-asset shape has no requirement, but the dataset-level case does.
   - **Sample** is reserved for the practice-data asset shape, as you decided. But REQ-PIPE-106 still says "sample data" and "the sample schema" for in-development data. Queue item 9's rename is still pending.
   - The alias **calendar-less** belongs to in development. But a one-off extraction dataset is also calendar-less, permanently.
5. **REQ-GHUB-082 now names eight filing decisions, not seven.** It lists promote, reject, demote, re-file, substitute, **de-substitute**, inherit and un-inherit. The page list still says "the seven filing decisions", and de-substitute has no glossary entry. Should I add it? Should the page be renamed?

## Judgement calls

- **Scope.** I seeded the naming canon, the four GOV.UK words, and the terms periods and slots will need. I added a few supporting entries:
  - staging, reject, re-file and filing decision, because demote and acknowledge are defined in terms of them;
  - ticket, to carry "issue";
  - data asset and dataset, because the first page cannot avoid them.

  I did not add the rest of the page list's concepts, such as agency, collection, receipt, hold, graduate, the data contract, check or the red, amber, and green statuses. Those can come in at each page's brief.
- **Periods and slots terms.** From REQ-PIPE-048 to 053 and 063, I included:
  - period;
  - slot;
  - not-expected period;
  - supply calendar;
  - authored dates;
  - cadence rule;
  - calendar version;
  - delivery month;
  - due time;
  - grace allowance;
  - claim window;
  - filled;
  - closed unfilled;
  - overdue;
  - runway;
  - schedule ended.

  Due time, grace allowance and claim window belong to the claim windows page, but a slot is defined by them, so the first page will use them.
- **Term spellings I chose where the canon was silent.**
  - "due time" (the page list's word), with "due instant" (the requirements' word) as its alias;
  - "grace allowance" (the requirements' word), with "grace" as its alias;
  - "not-expected period", with "not expected" as a form;
  - "schedule ended" (the dashboard's label), with "exhausted schedule" (REQ-PIPE-053's word) as its alias;
  - "filled" as the term, with fill, fills, filling and unfilled as its forms.

  None of these aliases came from the naming session, so each needs your yes.
- **"trial run" is an alias of trial.** The canon says "never 'trial run'". Listing it as an alias maps the forbidden phrase to trial. I did not add "ad-hoc", which REQ-PIPE-103 retired, because it is too common a word to match on.
- **"timeliness" is an alias of recency,** as the canon says (ODCS timeliness). This means arrival timeliness, the early, on time, and late verdicts, must never be called "timeliness" on a page. That matches your decision that timeliness never appears unqualified.
- **"carry forward" is an alias of substitute,** because substitute is its replacement. I also added its forms "carried forward" and "carrying forward". The retired sense of "supplies for the following period" has nowhere to live yet. The claim windows page will need a word for it.
- **Early, on time and late are three entries.** The canon settled them as words for arrivals only. They cannot be aliases of each other. Each cites REQ-PIPE-066 alone.
- **Page paths.** Only period, slot and not-expected period point at a page, `2-calendar/periods-and-slots.md`, using the example path from the brief. Every other entry is `page: null` until its page exists. glossary.md will link to that path before the file exists. The validator does not check glossary.md's links, so nothing fails, but the link is dead until the page lands.
- **Forms.** I kept forms to inflections of the headword, such as plurals and verb endings. I left out forms of "accept", such as "accepted" and "accepts". "Accepted" appears in plain senses in requirements ("when the existing supply was accepted" means promoted), and would trip the recall check everywhere.
- **delivery** and **QA run** each cite one requirement. I dropped REQ-PIPE-105, which is not built, because the definitions rest only on REQ-GEN-042 and REQ-PIPE-036. **arrival** keeps REQ-PIPE-105, because "every file is its own arrival" is 105's idea.
- **The diagram** is a top-to-bottom flowchart. One delivery subgraph holds two arrival subgraphs, and each arrival holds one supply node. The supply nodes use the `good` palette class. The subgraphs keep the neutral theme's default look, because I did not want to rely on classDef styling subgraphs.

## Entries whose defining requirement is not built or not signed

A state other than built is shown as a badge in glossary.md.

| Entry | Derived state | Defining requirements |
|---|---|---|
| delivery agreement | proposed | REQ-PIPE-110 (proposed) |
| arrival | designed, not built yet | REQ-PIPE-105 (designed, not built yet), REQ-PIPE-034 (partly built) |
| ticket | designed, not built yet | REQ-PIPE-083 (designed, not built yet), REQ-GHUB-109 (built) |
| blocked | designed, not built yet | REQ-PIPE-079 (designed, not built yet) |
| In place on | designed, not built yet | REQ-PIPE-081 (designed, not built yet) |
| data asset | partly built | REQ-QAC-039 (partly built), REQ-DASH-003 (built) |
| dataset | partly built | REQ-QAC-039 (partly built), REQ-PIPE-052 (built) |
| filled | partly built | REQ-PIPE-062, REQ-PIPE-075 (both partly built) |
| closed unfilled | partly built | REQ-PIPE-063 (built), REQ-DASH-070 (partly built) |
| runway | partly built | REQ-PIPE-053 (partly built) |
| schedule ended | partly built | REQ-PIPE-053 (partly built) |
| supply | partly built | REQ-PIPE-034, REQ-PIPE-062 (both partly built) |
| early, on time, late | partly built | REQ-PIPE-066 (partly built) |
| QA run | partly built | REQ-PIPE-036 (partly built) |
| staging | partly built | REQ-PIPE-060 (partly built), REQ-PIPE-076 (built) |
| filing decision | partly built | REQ-GHUB-082 (partly built), REQ-PIPE-074 (built) |
| promote | partly built | REQ-PIPE-075, REQ-PIPE-062 (both partly built) |
| demote | partly built | REQ-PIPE-076 (built), REQ-GHUB-082 (partly built) |
| re-file | partly built | REQ-GHUB-082 (partly built) |
| resupply | partly built | REQ-PIPE-062, REQ-PIPE-065 (both partly built) |
| substitute | partly built | REQ-PIPE-084 (partly built), REQ-DASH-085 (built) |
| inherit | partly built | REQ-PIPE-098, REQ-PIPE-099 (partly built), REQ-DASH-100 (built) |
| un-inherit | partly built | REQ-PIPE-099 (partly built) |
| waiting on a person | partly built | REQ-DASH-070 (partly built), REQ-PIPE-076 (built) |
| one-off extraction, sample, freshness | an idea, not designed yet | none |

Every other entry is built. Delivery agreement is the only proposed one. It is also the entry the built supply calendar sits inside, so the container is less built than its contents.

## Canon items I could not place, or placed only partly

- **"patch".** It was in the naming hazard cluster, but it was not in the settled canon, so I left it out.
- **"reconcile".** You noted it as an established word, but no alias was decided. Ticket reconciliation goes to the pipeline docs, so it has no entry.
- **"calendar" on its own, and "table".** Neither is an alias of anything. Pages will say "the calendar" and "table" constantly. Should "calendar" be an alias of supply calendar? Should "table" be an alias of dataset, or stay a plain word?
- **"held" or "hold".** "Held for a human" became a section of group 6, and REQ-PIPE-064 and REQ-PIPE-078 use "hold". The canon settled "waiting on a person" for a supply needing a decision, but did not say whether "held" is an alias or its own concept. Blocked's definition uses "held" as a plain word.
- **"as at".** REQ-PIPE-081 says "as at T". Only "as of" was settled as an alias of In place on.
- **"due date".** Your re-baseline calls the supply calendar "the schedule of periods and due dates", and the house standard writes "supply due 1 August 2026". A period's date and a slot's due time are different things (REQ-PIPE-051 puts no due time on a period). I defined the supply calendar in terms of "the date each period's supply is due" and did not add "due date" as an alias.
- **"project extraction".** This is the older name for the one-off extraction. It was never settled as an alias.
- **The built resupply chain (REQ-QAC-008).** It is deliberately not cited, per triage #27. Resupply is defined only in the model's sense.
- **run_id and rehearsal versus real.** These are excluded as tooling, per the canon.
- **Blocked has a clash in the requirements.** REQ-PIPE-099's title says un-inherit "frees a blocked withdrawal", and REQ-DASH-070 says items that "BLOCK a supply". Both use "blocked" in a sense the canon reserved for the neighbour case. This is like queue item 9's renames. It is flagged here, not fixed.
- **"delivery month".** It keeps "delivery" in the calendar sense that the naming session moved away from (the config key is `delivery_months`). It may belong on queue item 9's rename list.

## Definitions I am unsure of

- **acknowledge.** The canon says it "never sounds like a decision that changes anything", and the sweep says an amber accept is not logged. But REQ-QAC-017's only criterion says the decision is "recorded somewhere real and reflected back in the dashboard's own status". So "it changes nothing about where the supply is filed" is my safe middle ground. Is it recorded or not?
- **recency.** No requirement defines the five check categories. The taxonomy lives in code (`CHECK_CATEGORIES`). I cited REQ-QAC-024, which says every check carries its category, and REQ-QAC-001, which covers the real checks, including dbt's recency macro. Both are weak. The alternatives are to write the missing requirement or to mark recency as an idea, which would be wrong for a built thing.
- **In place on.** "See which supply was promoted into each slot on that date" follows REQ-PIPE-081's first criterion. It says nothing about the as-corrected default, or about later corrections changing the answer, which is the page's real subject.
- **arrival.** "The moment our own storage took it" is REQ-PIPE-105, which is not built. Today's built arrival (REQ-PIPE-034) is per dataset, not per file.
- **overdue.** I followed the canon ("due time has passed with nothing filed"). REQ-PIPE-079 speaks of "past due", and it is not settled whether grace counts. If overdue begins after the grace allowance, the definition should say so.
- **filled.** A substituted slot also counts as filled (REQ-PIPE-084), but my definition names only promotion. That is a simplification.
- **inherit.** "Nobody has to decide it" is true of the automatic case (REQ-PIPE-098). But REQ-PIPE-099 also lets a person inherit, so the sentence is true of the usual case, not every case.
- **The diagram's caption.** "Each arrival carries one supply" skips a file that cannot be loaded or placed. That is still an arrival, but it stages no table (REQ-PIPE-060, REQ-PIPE-057).
- **data asset.** The fact that each asset is its own separate deployment with its own dashboard has no requirement, so I left it out. The definition now covers only the hierarchy, which REQ-QAC-039 and REQ-DASH-003 support.
- **freshness.** It is an idea, and the wording comes from the plans' test scenario, not from a requirement. It is the least certain definition here.

## Canon drift from REQ-DOCS-119's naming-session decision (found 2026-10-02)

REQ-DOCS-119's decisions record the signed canon from the naming
session. Keith's glossary review has since changed several parts of it,
so that decision needs updating, with his approval of the exact wording,
when the glossary moves out of plans:
- demote: canon says "always with its destination (to staging or to
  rejected)". Now: demote is only ever back to staging; a promoted
  supply that will not be used is rejected.
- acknowledge: canon alias "accept" - dropped.
- in development: canon term with aliases pre-agreement, calendar-less,
  not yet agreed - gone; sample data is the term (running-thoughts #60).
- sample: canon "reserved for the practice-data asset shape" - now the
  term for data provided before a calendar is agreed.
- trial: canon term - now "one-off check", with trial and trial check
  as aliases.
- stale (alias of no data): DROPPED by Keith 2026-10-02. timeliness (alias of recency, the ODCS
  name): KEPT by Keith 2026-10-02.

## Categories, approved by Keith 2026-10-02

1. The data: data asset, dataset, scheduled data asset, one-off data,
   sample data, delivery, arrival, supply, permanent reporting
2. Checking it: QA run, one-off check, recency, blocked
3. Deciding what happens to a supply: staging, filing decision, promote,
   reject, demote, re-file, acknowledge, resupply, substitute,
   de-substitute, inherit, un-inherit, waiting on a person, ticket
4. Reading the dashboard: early, on time, late, overdue, filled, closed
   unfilled, no data, freshness, schedule ended, in place on
5. The supply calendar (at the back): delivery agreement, supply
   calendar, authored dates, cadence rule, calendar version, delivery
   month, period, not-expected period, slot, due time, grace allowance,
   claim window, runway

Needs a `category` field in the glossary schema and a render ordered by
category (REQ-DOCS-119 tooling). "timeliness" kept as recency's alias.
