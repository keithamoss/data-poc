"""mothman population - Tier 4 (plans/tooling.md #1 Phase 5), explicitly
exploratory: synthetic_data_generator/ is a separate, population-scale,
cross-agency-identity-linked generator (millions of rows, 3 agencies'
worth of the SAME underlying fake people), not currently wired into this
project's real QA pipeline (CLAUDE.md's own repo-layout table; see
plans/data-generation.md #3) - Keith wants to revisit and collapse it
down to a single generator eventually, but is happy to expose today's
version rather than hide it in the meantime. Wraps synthetic_data_
generator/generate.py's own real argparse CLI (the project's actual
population-scale demo entry point) with the exact same options and
defaults, under the mothman umbrella - a reorg of the entry point, not a
rewrite of what it does. Not part of the interactive TUI's guided flows
(those are Tier 1/2/3 only) - flag-invocable only, matching its own
"exploratory" framing."""
from __future__ import annotations
import os

import rich_click as click
from rich.console import Console

from . import common

console = Console()

_DEFAULT_OUTDIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "synthetic_data_generator", "output", "demo")


@click.command("population")
@click.option("--population", "population_n", default=200_000, show_default=True,
              help="Target size of the master population (WA's real population is ~2.9M - see "
                   "synthetic_data_generator/README.md for full-scale timing).")
@click.option("--seed", default=42, show_default=True)
@click.option("--case-workers", "n_case_workers", default=60, show_default=True)
@click.option("--dirty", type=click.Choice(["none", "amber", "red"]), default="none", show_default=True,
              help="Seed known QA failure modes into birth_registrations/sex, "
                   "birth_registrations/place_of_birth_facility, and cp_notifications/concern_type.")
@click.option("--outdir", default=None, type=click.Path(),
              help=f"Defaults to {_DEFAULT_OUTDIR}.")
@click.option("--demo-examples", default=3, show_default=True,
              help="How many cross-agency identity examples to print (0 to skip).")
def population_command(population_n: int, seed: int, n_case_workers: int, dirty: str,
                        outdir: str | None, demo_examples: int) -> None:
    """[Tier 4, exploratory] Generate a population-scale, cross-agency-identity-linked synthetic
    dataset via synthetic_data_generator/ - not wired into this project's real QA pipeline."""
    from synthetic_data_generator.generate import (
        build, build_linkage_answer_key, print_cross_agency_demo, write_outputs,
    )

    resolved_outdir = outdir or _DEFAULT_OUTDIR

    console.print(f"Generating synthetic population (target {population_n:,}, seed={seed}, "
                  f"dirty={dirty})...", style=common.TIER_4)
    pop, cp_tables, birth_reg, school = build(population_n, seed, n_case_workers, dirty)

    answer_key = build_linkage_answer_key(cp_tables, birth_reg, school)
    public_dir, internal_dir = write_outputs(resolved_outdir, pop, cp_tables, birth_reg, school, answer_key)

    console.print(f"Wrote public agency tables -> {public_dir}/", style="green")
    console.print(f"Wrote master registry + linkage answer key -> {internal_dir}/ "
                  "(ground truth - do not distribute as test data)", style="dim")

    if demo_examples:
        console.print(f"\n--- {demo_examples} people who appear in all three agencies, "
                       "shown with their master identity resolved ---", style=common.TIER_4)
        print_cross_agency_demo(answer_key, birth_reg, cp_tables, school, n=demo_examples)
