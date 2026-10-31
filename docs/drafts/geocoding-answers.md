## Geocoding answers (Keith, 2026-10-25 evening)
- Q1(a): Department of Health, in the Linkage Products collection alongside the linkage product.
- Linkage products AND geocoding arrive for the CURRENT period (offset 0): other agencies' Feb data goes into Q2 (+1); Health's linkage/geocoding supply in the Q2 round goes into Q2 and is checked against those supplies.
- ONE GEOCODING DATASET PER SOURCE DATASET (e.g. Child Protection geo, Birth Registrations geo, ...) - draft 294-300 assumed one table; needs reworking.
- Cross-collection checks: definitely needed for geocoding and linkage products (and future things). Q1(b): fine to wait - geocoding v1 own-row checks only; its cross-collection checks come after linkage products build the cross-collection read (REQ-PIPE-331).
- Flag to raise: Birth Registrations is daily - a quarterly BR geo checked against daily periods is a cross-period read.
- Q2 cadence: quarterly, in the linkage round, offset 0. Birth Registrations left OUT of synthetic geocoding (option i - it stands in for a separate data asset; a quarterly geo against daily periods would read across periods).
- Q3 contents: (a) a geo supply geocodes exactly what the period's source supply holds. Source supplies are FULL SNAPSHOTS (Keith), so this is every record, each with one row per declared census year.
- Mixed-offset inheritance (rt3 REQ-PIPE-323) explained to Keith with the Feb/May example; his answer still pending (rt3 Q2).
- Q4 census years: declare 2016 and 2021; REQ-QAC-300 (effective-dated widening) stays IN this batch, synthetic history shows 2026 joining from a recent quarter.
- Q5 widening warning: (a) none - a reviewed config change; the dashboard shows the set in force per period.
- Q6: three separate checks (missing/duplicate/unexpected), each its own bands; one dbt generic test reused across every geo dataset.
- Q7 bands: RED ON ANY for all three (missing, duplicate, unexpected). Amber is kept for the later cross-collection checks against the source datasets.
- SHAPE (Keith): one row per ROW in the source dataset per census year (keyed by source row, not by person/record).
- Follow-up logged in road-testing: how "could not be geocoded" is represented and handled.
- Q8 empty supply: LEAVE IT (Keith) - no special handling and no extra row-count check; the three year checks pass vacuously on an empty file, and the later cross-collection checks (every source row has geo rows) pick it up. KNOWN GAP until then, recorded as a decision: an empty geo file reads green.
- Q9 synthetic geo datasets: (b) Child Protection (cp-clients ONLY) and Emergency Department (scoper to find which ED dataset(s) carry an address), last 12 quarters.
- Q10 planted faults: (a) presets in ordinary supplies AND one named scenario supply per fault.
- Q11 named supplies: (a) in the TS register (plans/supply-model.md) from the next free number (TS-86 expected after A3's TS-81..85; scoper to verify).
- Q12 missing-year sample: (a) constructed pair, worded as such: 'source row 4821 · 2021: no row'.

## Linkage answers (Keith, 2026-10-25 evening)
- L1 counting: (b) a linkage verdict counts against the linked tables it read too, as REQ-PIPE-269 c4 does today - a promoted supply may change colour when its period's linkage product is checked. (Reverses the scoper's REQ-PIPE-332 recommendation; 332 to be redrafted.)
- L2 coverage: CP clients (not carers). Keith: ED ALSO has records in the linkage dataset like any other collection - what differs for ED is only WHEN its linkages arrive relative to its data (same round, vs CP's data a round earlier). Confirming whether the synthetic product covers ED too.
- L2 confirmed: synthetic linkage covers CP clients AND ED's person dataset (ed-presentations). Same-round ED: its linkage check reads red (could not run) until ED's Q2 supply is promoted, then the knock-on re-check clears it - do NOT order the synthetic ED supply ahead to hide it.
- L3 missing linked supply: (a) red could-not-run unless a person has recorded the period's supply as not supplied; then that linked dataset's checks are out of scope.
- L4 history: ALL quarters (every quarter each linked source has, incl. CP's corrected 2013-2015 quarters), and the SAME for geocoding - overrides geocoding Q9's 12 quarters. Bootstrap cost to be measured and reported (budget REQ-PIPE-250 already not met).
- L5 names: keep linkage-products / Linkage Products / lp_run_; linkage-keys / Linkage Keys; geo: Client Register Geocodes, ED Presentations Geocodes.
- L6 Linkage Keys SHAPE (Keith corrected the scoper's columns): linkage_key (a scrambled identifier - no allowed-values range); dataset (the name of the dataset the row is for, e.g. "CP Clients" - an EXPECTED VALUES check); id_1..id_n (map to identifier columns on the source dataset; some datasets use one identifier, others several). NO confidence column, NO match-type column - matching is always probabilistic. Scoper's match_confidence / match_type checks and the match-type drift check are gone.
- L6 check set AGREED: linkage_key not empty; dataset in expected values (declared linked datasets); each row carries exactly the ids its dataset uses; (dataset, ids) unique (linkage_key may repeat across datasets); referential per linked dataset (ids match a row of that period's supply); coverage per linked dataset (amber band). No drift check. Each linked dataset declares its id_1..id_n -> source column mapping in the Linkage Products config beside the linked-dataset list.
- L7 bands: own-row and referential checks red on any; coverage (b) amber below 95%, red below 90%.
- L8: CUT REQ-DASH-338 (the per-page linkage line) - under L1(b) the linked page already shows the checks and their effect.
- #31 could-not-be-geocoded: (a) a row per census year with area codes empty and a 'not geocoded' marker; banded completeness (amber as the share grows). Missing-year stays about process.
- Geo shape AGREED (Keith): one file per geo dataset; columns census_year, sa2_code, lga_code, match_level (address/postcode/suburb/not geocoded; not geocoded leaves codes empty); no address/coords/name/DOB; no mesh block or SA1. KEYS use the SAME id_1..id_n pattern as Linkage Keys (each geo dataset declares its id_n -> source column mapping), replacing the single source_row_id; key = ids + census_year.
- Not-geocoded SHARE check: amber above 5%, red above 10% (the three year checks stay red on any).
- Q13: one Health release per quarter, geo files + linkage_keys.csv in one zip; release due in the afternoon (e.g. 14:00) after ED's morning arrivals; geo and linkage use the last source supply RECEIVED BEFORE the release.
- Q14 confirmations all fine (ordinary checks: exact ids, match_level allowed values, SA2/LGA format when geocoded/empty when not, match_level drift; census years declared once per collection; scenario hosts missing+unexpected on Client Register Geocodes, duplicate on ED Presentations Geocodes; REQ-QAC-340 rescoped once 331 is built) EXCEPT: 2026 joins the census years from 2026-Q3 (not Q1); the unexpected-year scenario sends 2026 in a quarter before that.
- L9 corrected quarters: (b) GENERATE linkage and geocoding in the nine corrected quarters too, and AMEND REQ-GEN-237 (built) so the calendar corrections also re-judge linkage and geocoding supplies, each named in its scenario - reopens the five built correction scenarios (TS-57..61). Amendment to a built requirement: needs its own sign-off wording.
- L9 (b) CONFIRMED after the corrected quarters were explained (5 fictional ED quarter-date corrections, REQ-GEN-205/TS-57..61, 9 quarters altered; ED supplied there, CP suppressed by REQ-GEN-237's empty-elsewhere rule): linkage and geo generated there; the correction re-judges/moves them with ED's supplies (REQ-GEN-237 amendment); CP linkage checks there scripted not-supplied.
- L10: (a) one id column each in the synthetic datasets. Keith: the NEXT dataset we create uses multiple identifiers (logged in running-thoughts).

## Re-sign round (Keith, 2026-10-31 morning)
- Plan agreed: drafts into the repo; scoper refresh against as-built linkage folding the 29 Oct architect + UX findings; delta reviews; questions one at a time; sign-off; build.
- G1 (= architect GA3): (b) - a geocoding check's verdict counts against the source dataset's supply it read, exactly as linkage does (REQ-PIPE-332 / REQ-PIPE-269 c4); a promoted Client Register supply may change colour when its period's geocodes are checked. (Recommendation was (a); Keith chose (b).)
- #291 (linkage referential failing samples empty, REQ-QAC-333 c6): (b) fixed inside the geocoding batch by REQ-PIPE-341 c3 (composite sample key); REQ-QAC-333 c6 goes back to unmet until then.
- GA1: (a) one geocode set per DISTINCT identifier set; a source's duplicate is reported once, by the source's own uniqueness check, never as a geocoding duplicate year.
- GA2: (a) faithful - a geocode follows from the source row's own address columns: a record with none of them filled (e.g. an ED presentation with no postcode) is 'not geocoded', and otherwise is placed no finer than its present columns support; the planned verdict is confirmed by the targeting trial (Keith, 2026-10-31).
- N1 (geocoding coverage bands, REQ-QAC-340): (a) amber below 100 percent, red below 98 (Keith, 2026-10-31).
- Q7 (geocoding named scenarios, REQ-GEN-298): (a) a named scenario for each of REQ-QAC-340's five verdict routes, including the G1 route; the ordinary checks rely on presets (Keith, 2026-10-31).
- GA4 (geocoding id width): (a) the same id_1 to id_N as the Linkage Keys contract, N = 2 today (Keith, 2026-10-31).
- Q10 (census years before 2021, REQ-QAC-300): (b) effective-dated as a real geocoder would deliver, each version ADDING a year: 2011 alone from 2013; 2016 added about 2017-Q3; 2021 added about 2022-Q3; 2026 added from 2026-Q3 (as Q14). Exact quarters of the 2016 and 2021 additions to be proposed by the scoper and confirmed at sign-off (Keith, 2026-10-31).
- Q6 (geocoding participation, REQ-QAC-294 c10): (a) mirror the source's owed periods after its offset, gated (Keith, 2026-10-31).
- Q11 (MEASURES phrases for the shared kinds): (a) reword generically - 'Rows matching no source record' and 'Source records matched' (UX wording); Linkage Keys' built page wording changes too, written up in post-build-review with its e2e text in the same change (Keith, 2026-10-31).
- Architect Q2 / UX N1 (sample heading): (a) site-wide 'Examples: <the check's MEASURES phrase>', keeping 'Examples' and '(key only)', every check page with a declared phrase changes, e2e text updated in the same change (Keith, 2026-10-31; architect had recommended per-kind declared headings). Scoper to state the heading for a check with no declared phrase.
- Architect Q3 ('moves no other check', REQ-GEN-298 c7): (a) a real-tool trial (REQ-GEN-186) over each drafted injected supply (Keith, 2026-10-31).
- G3 (match_level distribution, REQ-DASH-299): (a) the existing per-value bars (Keith, 2026-10-31).
- G4 (census years tile, REQ-DASH-299): (a) an always-present 'Census years' tile from the recorded version (Keith, 2026-10-31).
- Q9 (geocoding due time, REQ-GEN-295): (a) due 19:00 with 8 hours' grace, received 18:05 to 18:55, declared as the dataset's own expected time; REQ-GEN-334 c8's stale 14:00/15:00 amended (Keith, 2026-10-31).
- Q1 (ids, tables, files): (a) as proposed - geo-cp-clients / geo-ed-presentations, tables geo_cp_clients / geo_ed_presentations, files geo_cp_clients.csv / geo_ed_presentations.csv (Keith, 2026-10-31).
- J3 (#289, N5 - linkage and geocoding alike): (a) a left-out check stays in its collection group as a quiet row naming whose supply was not supplied for the period, e.g. 'Not checked: Client Register not supplied for 2024-Q2' (Keith, 2026-10-31). Applies to built linkage too: an amendment, with its own wording at sign-off.
- J4 (#289, N5): (a) the agency page names which collections a cross-collection check reads, long-form, and groups such checks under an 'Across collections' sub-heading in the panel (Keith, 2026-10-31). An amendment to built linkage, wording at sign-off.
- J1 / G1 surfacing: NONE of (a) accept, (b) quiet notice, (c) move timing. Keith wants a PERIOD VIEW of the dashboard alongside the as-at control (running-thoughts #131), scoped as its own requirement. Geocoding does NOT wait for it: the geocoding batch builds with J1 as built (the change shows on the older supply's history row and badge), and the period view is scoped and reviewed alongside the build (Keith, 2026-10-31).

## v5 review round (Keith, 2026-10-31)
- Architect v5 BLOCKING 1 (the trial has no period): (a) the trial takes its slot's period and reads the other collections' tables from that period's warehouse, so every planned verdict, the cross-collection ones included, is confirmed before anything is written. Generic, not geocoding-only.
- Architect v5 Q1 (an always-empty id column): (b) drop TRAILING empty parts from the display only; the recorded sample stays complete, and a middle empty part still shows '—'.
- REQ-QAC-300 open question 1 (when 2016 and 2021 join): (a) 2017-Q3 and 2022-Q3, the first round after the ABS's first release of each census's data.
- 2026's join date: (a) moved to 2027-Q3, so all four years follow one rule (2011 from 2013; 2016 from 2017-Q3; 2021 from 2022-Q3; 2026 from 2027-Q3). This SUPERSEDES Q14's 'from 2026-Q3'. The unexpected-year scenario sends 2026 in any quarter before 2027-Q3.
- REQ-DASH-299 sample lines: (a) 'source record', not 'source row'.
- A2 wording: (a) keep 'by decision' - 'Not checked: Client Register not supplied for 2024-Q2, by decision'.
- A1 scope: (a) EVERY left-out reason (not supplied, not owed, not in the agreement) follows J3's rule - the check stays in its collection group as a quiet 'Not checked: <why>' row, and the separate 'Not run for this supply' block goes.

## v6 questions (Keith, 2026-10-31)
- REQ-GEN-298 Q1 (where the trial gets the other collections' tables): (a) stage the source supplies the generator has just written for that period, so every planned verdict, the cross-collection ones included, is confirmed before anything is written.
- REQ-GEN-298 Q2 (which supplies the trial tries): (a) ambers, reds and named scenarios, about 45 supplies and roughly 10 minutes; ordinary greens are confirmed when replayed.
- REQ-QAC-300 Q1 (the fourth version takes effect after the history ends): (a) declare it now; its tile and the third trend break are proven in Vitest only.
- REQ-DASH-299 Q1 (group-heading count words): SUPERSEDED by Keith's site-wide decision (running-thoughts #132) - Pass / Warn / Fail everywhere, so counts read '1 pass, 2 warn, 1 not checked'. The relabel itself is its own requirement.

## v6 delta round (Keith, 2026-10-31)
- REQ-GEN-298 criterion 11, which sources the trial stages: (a) only the source supplies the generator's plan promotes before the geocoding delivery, which is what the warehouse will hold then (REQ-GEN-334 c12's scheduling already computes this). A held source is not staged, and the trial expects could-not-run, so trial and replay agree. REJECTED (b), every filed source. This needs a signed amendment to REQ-PIPE-331 criterion 3 ('never a staged one'), whose wording comes in v7.
