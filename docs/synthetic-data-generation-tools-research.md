# Research: tools for realistic, population-scale, multi-decade synthetic data

Research pass done in response to Keith digging into `plans/data-
generation.md` #4 — specifically the question "are there
existing Python (or other-language) libraries genuinely built for
population-scale, multi-decade synthetic data generation, rather than
what this project's `synthetic_data_generator/` hand-rolled?"

Not yet actioned — logged here to come back to. Two prior findings from
the "digging into population.py" session directly motivate this: the
hand-authored name pools collide heavily at population scale (`Charlotte
Smith` × 5,499 at 200k people; ~5,000 genuine full-name+DOB collisions),
and the whole generator is a single point-in-time snapshot with no time
dimension at all — mortality is computed but never enforced, there's no
address history, and a `has_child_protection_history` flag that the code
comments claim is "lifelong" can structurally never reach an adult.

## A genuinely useful side-discovery first

`generator/names_au.py`'s own docstring (imported by `synthetic_data_generator/`
from there, not a separate copy - see `plans/publishing-and-history.md`
#3) says the name/geo pools were hand-authored because there was "no
Faker/pip access in this environment" at the time of the original build.
**That constraint no longer holds** — this session has full PyPI access (confirmed installing
dbt-core, Soda Core, datacontract-cli, Evidently earlier in this
project). Verified directly:

```
Faker en_AU unique first names sampled from 5000 draws: 618
Faker en_AU unique last names sampled from 5000 draws: 934
```

— versus the current 142 given names / 98 surnames. That alone would
substantially cut the collision rate.

**Caveat, and it's a real one**: Faker's `en_AU` address provider invents
fictional place names and doesn't reliably keep state/postcode
consistent — a test draw produced `"Jennabury, NT, 2106"` (2106 is a
Sydney postcode, not NT). This project's own hand-rolled `SUBURBS` list
in `generator/names_au.py` is real WA geography and is *better* than
Faker there. So the recommendation isn't "adopt Faker wholesale," it's
**swap only the name provider, keep the existing real suburb/postcode
list**. Mimesis is the faster (~12x reported), more localized (34
locales) alternative to Faker if that matters at this project's scale —
worth a quick bake-off between the two rather than picking blind.

## Two different categories of "better," and this project has needs in both

### A. Point-in-time population synthesis from real census data

Replaces `population.py`'s hand-picked, uncited household-type weights
(`0.28, 0.24, 0.09, ...`) with structure actually calibrated to real ABS
numbers.

| Tool | Stack | Status |
|---|---|---|
| [UDST/synthpop](https://github.com/UDST/synthpop) | Python, IPF against US Census PUMS | Active, US-calibrated — architecture is portable, data isn't |
| [nismod/household_microsynth](https://github.com/nismod/household_microsynth) + `humanleague` | Python/R, C++ core, IPF/QIS/QISI | UK-calibrated, same story |
| [agentsoz/synthetic-population](https://github.com/agentsoz/synthetic-population) | Java+R, real ABS census — built Melbourne's actual 4.5M synthetic population | **Archived Dec 2023, read-only, 12 stars, wrong language** |
| [wniroshan/oz-population](https://github.com/wniroshan/oz-population) | ABS TableBuilder-based | Smaller, similar story |

None of these are drop-ins — the Australian ones are dead or in the
wrong language; the maintained ones are calibrated to the wrong country.
The *method* (IPF/QIS against real marginal tables) is right, and ABS
publishes what it needs: Census DataPacks give the marginal distributions
needed for IPF without requiring restricted-access unit-record
microdata. This is a "borrow the method, recalibrate the numbers"
situation, not a library install.

### B. Dynamic, multi-decade life-course microsimulation

The category that actually answers "multi-decade": people age, form/
dissolve households, move, die *over simulated time*, rather than one
static snapshot per run. This is also where this generator's real gaps
live (mortality never enforced, no address history, the CP-history flag
that can't reach adulthood) — not bugs so much as the predictable result
of having no time dimension at all.

| Tool | Stack | Notes |
|---|---|---|
| [Synthea](https://synthetichealth.github.io/synthea/) (MITRE) | Java | Mature, real-world-proven exemplar: a "Generic Module Framework" — a state machine per life-domain, chained over a simulated lifetime, calibrated to real epidemiological data. Wrong domain (healthcare) and wrong language, but the best *architecture* to borrow from |
| [PySynthea](https://arxiv.org/abs/2606.28346) | Python | Brand-new (2026) Python-native reimplementation of Synthea's approach. Promising, unproven — one paper, no track record yet |
| [LIAM2](https://ideas.repec.org/a/jas/jasssj/2014-7-2.html) | Python (DSL) | Real government-policy adoption across 9+ countries; define fertility/mortality/marriage/migration transition rules, it simulates a population forward year by year. Closest existing Python tool to "multi-decade demographic simulation" specifically |
| [neworder](https://github.com/virgesmith/neworder) | Python (C++ core via pybind11), MIT | Actively developed (1,067 commits), pip-installable. Less batteries-included than LIAM2 — gives the simulation engine/scheduler/reproducible-RNG machinery, model itself is plain Python/pandas rather than a bespoke DSL |
| Statistics Canada's Modgen/LifePaths | C++/Windows DSL | The tool real statistical agencies use for exactly this ("synthetic life histories from birth to death representative of a country's population"). Reference point, not a practical adoption target — institutional distribution, Windows-only |

One more find worth naming even though it's not a generator:
[OpenCRVS](https://www.opencrvs.org/) is the leading open-source civil
registration *system* itself (what a real BDM might run on) — not
synthetic data, but a possible reference for what genuine registration-
record shape and workflow actually look like.

## Honest read / possible path, in increasing effort

1. **Cheap, low-risk**: swap the name pools for Faker or Mimesis's
   `en_AU` locale; keep the existing real WA suburb list. Directly fixes
   the collision problem measured this session.
2. **Medium**: recalibrate household/age structure against real ABS
   Census DataPack marginals using an IPF-style method (borrowing the
   *approach* from synthpop/humanleague, not their US/UK data) instead of
   hand-picked weights.
3. **Larger, only if the multi-decade dimension is actually wanted**:
   adopt `neworder` (or LIAM2 if a DSL is acceptable) as the actual
   simulation engine, so the population has real state over time. This
   would also retroactively fix mortality-not-enforced, no-address-
   history, and the CP-flag-can't-reach-adults gaps, since those become
   the engine's job rather than something `population.py` has to fake in
   one shot.

No single tool found is a clean drop-in for "Python, Australian
government agency data, three linked agencies, both a demographic
snapshot and (potentially) time-evolving history" — the path above is
assemble-from-parts, not install-and-go.

## Sources

- [Synthea](https://synthetichealth.github.io/synthea/)
- [PySynthea (arXiv)](https://arxiv.org/abs/2606.28346)
- [LIAM2 (JASSS)](https://ideas.repec.org/a/jas/jasssj/2014-7-2.html)
- [neworder (JOSS)](https://joss.theoj.org/papers/10.21105/joss.03351)
- [neworder GitHub](https://github.com/virgesmith/neworder)
- [simPop (JSS)](https://www.jstatsoft.org/article/view/v079i10)
- [UDST/synthpop](https://github.com/UDST/synthpop)
- [nismod/household_microsynth](https://github.com/nismod/household_microsynth)
- [agentsoz/synthetic-population](https://github.com/agentsoz/synthetic-population)
- [wniroshan/oz-population](https://github.com/wniroshan/oz-population)
- [Building a large synthetic population from Australian census data (arXiv)](https://arxiv.org/pdf/2008.11660)
- [Mimesis](https://mimesis.name/)
- [Statistics Canada Modgen/LifePaths](https://microsimulation.pub/articles/00060)
- [OpenCRVS](https://www.opencrvs.org/)
