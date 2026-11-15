"""What shapes a replay, and the first arrival a change can affect
(REQ-TEST-160, signed by Keith 2026-10-06; the input list is REQ-TEST-117's).

ONE INPUT LIST, two readers. CI keys its cached bootstrap on it
(`mothman pipeline cache-key`, REQ-TEST-117 criterion 1), and a checkpoint
records it so a resume can tell whether anything but the generated data has
changed (criterion 1 here). It used to be a `hashFiles(...)` list inside
.github/workflows/test.yml; a second copy here would be two lists that agree
until the day one is edited.

FILES, NOT PATTERNS, ARE COMPARED: every file git would consider part of the
checkout under those paths - tracked, or new and not ignored - hashed as it
is in the working tree. Ignored files are left out on purpose: `mothman env
dbt-deps` installs dbt_packages/ under each asset's dbt project
(assets/<asset>/dbt/), and a key that moved with it would never hit. A new module not yet added to git is IN, because it can
change what a replay does.

THE FIRST AFFECTED ARRIVAL IS COMPUTED, NEVER TYPED IN (criterion 5, and a
person-supplied N was offered and not chosen): only a change to the
GENERATED DATA has a knowable first effect, so any other input restarts the
collection, and anything that cannot be read resolves to the first arrival
too. A wasted minute is cheap; a stale verdict is the failure this project
exists to prevent.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Every input that shapes a bootstrap (REQ-TEST-117 criterion 1, as amended
#: 2026-10-06: no cli/ file but the one the bootstrap entered through, so a
#: terminal change never costs a full bootstrap). SINCE REQ-GEN-381 (criterion
#: 7) the bootstrap reaches nothing of cli/pipeline.py, so it is no input any
#: more, and the packages moved out of qa_tools/ - bootstrap/ and scenarios/,
#: beside asset_model/ - are, so a change to code that left qa_tools/** still
#: restarts a resume and misses the cache.
#:
#: THE SHARED INPUTS - everything but an asset's own folder. Since the asset
#: split: dbt_shared/, the macros and tests both assets' dbt projects read
#: through their macro-paths and test-paths (C12), and assets/environments.yaml,
#: the one asset-wide file both read.
#:
#: A KEY PER ASSET (REQ-PIPE-365 criterion 3, REQ-TEST-353 criterion 1): each
#: asset's key is these plus ITS OWN folder (inputs() below) - its
#: configuration, adapters, providers and dbt project - and never another
#: asset's, so a daily-only edit rebuilds only the daily bootstrap. A shared
#: edit still restarts both, which costs time and never leaves a stale verdict.
INPUTS = ("asset_model/**", "bootstrap/**", "scenarios/**", "generator/**",
          "synthetic_data_generator/**", "pipeline/**", "qa_tools/**",
          "dbt_shared/**", "pyproject.toml", "uv.lock",
          ".github/workflows/test.yml", "assets/environments.yaml")

#: The selected asset's own folder, the one input that differs by asset.
ASSET_FOLDER = "assets/{asset}/**"

#: What a replay compares as "every other input" (REQ-TEST-160 criterion 1):
#: the generators are left out because their effect is compared directly, as
#: the deliveries they produce - the shared generator and, since the asset
#: split, the asset's own providers under assets/<asset>/synthetic/collections/.
GENERATORS = ("generator/**", "synthetic_data_generator/**")
PROVIDERS = "assets/{asset}/synthetic/collections/**"
#: The shared half of it; replay_patterns() adds the asset's own folder, less
#: its providers.
REPLAY_INPUTS = tuple(p for p in INPUTS if p not in GENERATORS)

#: Bumped when what the key covers changes shape, so an old cache never
#: matches a new meaning (v3: assets/ and dbt_shared/ since the split; v4: one
#: key per asset, the asset named in it; v5: asset_model/, the shared reading
#: code REQ-PIPE-380 moved out of qa_tools/; v6: bootstrap/ and scenarios/, and
#: no cli/ file, REQ-GEN-381 criterion 7).
KEY_PREFIX = "bootstrap-v6-"


def _asset(asset: str | None) -> str:
    """`asset`, or the selected one - refused, as every reader refuses,
    without one."""
    if asset:
        return asset
    from asset_model import assets

    return assets.selected().name


def inputs(asset: str | None = None) -> tuple[str, ...]:
    """Every input that shapes `asset`'s bootstrap (default the selected
    asset's): the shared inputs and that asset's folder, no other's."""
    return INPUTS + (ASSET_FOLDER.format(asset=_asset(asset)),)


def replay_patterns(asset: str | None = None) -> tuple[str, ...]:
    """What a replay of `asset` compares: its inputs less the generators and
    its providers (A43)."""
    asset = _asset(asset)
    return REPLAY_INPUTS + (ASSET_FOLDER.format(asset=asset),
                            "!" + PROVIDERS.format(asset=asset))


def _pathspec(pattern: str) -> str:
    """A git pathspec for `pattern`; a leading `!` excludes what it matches."""
    if pattern.startswith("!"):
        # glob magic, so the `*` in assets/*/... stops at a slash and `**`
        # reaches below - git's default exclude matches neither here.
        return ":(exclude,glob)" + pattern[1:]
    return pattern[:-3] + "/" if pattern.endswith("/**") else pattern


def input_files(patterns=None) -> dict[str, str]:
    """{repo-relative path: sha256 of its working-tree bytes} for every file
    in the checkout under `patterns` (default the selected asset's inputs),
    ignored files excepted."""
    if patterns is None:
        patterns = inputs()
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
         *(_pathspec(p) for p in patterns)],
        cwd=ROOT, check=True, capture_output=True).stdout.decode("utf-8")
    out = {}
    for rel in sorted(set(filter(None, listed.split("\0")))):
        path = ROOT / rel
        if path.is_file():  # tracked but deleted in the working tree: not an input
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _digest(files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + files[rel].encode() + b"\n")
    return h.hexdigest()


def cache_key(asset: str | None = None) -> str:
    """CI's bootstrap cache key for `asset`, default the selected one
    (REQ-TEST-117; REQ-PIPE-365 criterion 3): its inputs as one digest, the
    asset named in the key so two assets' caches can never be mistaken for
    each other's, whatever their files."""
    asset = _asset(asset)
    return f"{KEY_PREFIX}{asset}-{_digest(input_files(inputs(asset)))}"


@dataclass(frozen=True)
class ArrivalPrint:
    """One arrival, as far as a replay can tell it from another."""

    run_id: str
    delivery: str
    file: str
    content: str
    receipt: str


#: A receipt field that is a stamp rather than a fact about the arrival: the
#: generator's global receipt counter moves on every regeneration of
#: identical data (measured 2026-10-06, 5929 against 5971 for the same file),
#: so comparing it would make every resume a full replay. ORDER is still
#: compared - it is the print's order, receipt order.
_RECEIPT_STAMPS = frozenset({"sequence"})


def _receipt_digest(receipts_dir: Path, delivery: str, filename: str) -> str:
    path = Path(receipts_dir) / delivery / f"{filename}.json"
    if not path.is_file():
        return "absent"
    doc = {k: v for k, v in json.loads(path.read_text()).items() if k not in _RECEIPT_STAMPS}
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()


def deliveries_print(collection_id: str, deliveries_dir: Path | None = None,
                     receipts_dir: Path | None = None) -> list[ArrivalPrint]:
    """Criterion 1: every arrival of the collection, in receipt order, with a
    digest of its file and of its receipt."""
    from asset_model import arrivals as arrival_tree, delivery as delivery_tree

    receipts_dir = Path(receipts_dir or delivery_tree.default_receipts_dir())
    out = []
    for a in arrival_tree.arrivals_for(collection_id, "", deliveries_dir, receipts_dir):
        for names in a.files_by_dataset.values():
            for name in names:
                out.append(ArrivalPrint(
                    run_id=a.run_id, delivery=a.delivery_name, file=name,
                    content=hashlib.sha256((Path(a.path) / name).read_bytes()).hexdigest(),
                    receipt=_receipt_digest(receipts_dir, a.delivery_name, name)))
    return out


def regenerated_print(collection_id: str) -> list[ArrivalPrint]:
    """Criterion 2: regenerate both collections' deliveries somewhere of their
    own - never data/ - and print this one's. About 5 seconds."""
    import contextlib
    import io
    import warnings

    # THROUGH THE GENERATOR'S ONE PUBLIC MODULE (REQ-GEN-381 criterion 3): the
    # bootstrap may import the generator, but only generator/public.py, and
    # never cli/ (the imports gate, REQ-TEST-384).
    from generator.public import generated_into

    # QUIET: the generators narrate every delivery they write, which is
    # noise in the middle of a resume that only wants the comparison.
    with tempfile.TemporaryDirectory(prefix="mothman-replay-") as tmp, \
            contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with generated_into(Path(tmp)) as root:
            return deliveries_print(collection_id, root / "deliveries", root / "receipts")


@dataclass(frozen=True)
class Recorded:
    """What a checkpoint holds about its inputs (criterion 1)."""

    collection_id: str
    arrivals: list[ArrivalPrint] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)
    readable: bool = True

    def to_json(self) -> dict:
        return {"collection_id": self.collection_id,
                "arrivals": [asdict(a) for a in self.arrivals],
                "inputs": dict(self.inputs)}

    @classmethod
    def from_json(cls, doc: dict) -> "Recorded":
        try:
            return cls(collection_id=doc["collection_id"],
                       arrivals=[ArrivalPrint(**a) for a in doc["arrivals"]],
                       inputs=dict(doc["inputs"]))
        except (KeyError, TypeError):
            return cls(collection_id=doc.get("collection_id", ""), readable=False)

    @classmethod
    def now(cls, collection_id: str, deliveries_dir: Path | None = None,
            receipts_dir: Path | None = None) -> "Recorded":
        """The inputs as they stand: the deliveries a replay is about to read,
        and every other input in the checkout."""
        return cls(collection_id=collection_id,
                   arrivals=deliveries_print(collection_id, deliveries_dir, receipts_dir),
                   inputs=input_files(replay_patterns()))


@dataclass(frozen=True)
class FirstAffected:
    """`arrival` is 1-based in the collection's receipt order; None means
    nothing differs and nothing is to be replayed (criterion 4). `reason` is a
    finished sentence, shown as it is."""

    arrival: int | None
    reason: str


def _named(paths: list[str]) -> str:
    shown = ", ".join(paths[:3])
    return shown + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")


def first_affected(recorded: Recorded, *, arrivals: list[ArrivalPrint] | None = None,
                   inputs: dict[str, str] | None = None) -> FirstAffected:
    """Criteria 2 to 4. `arrivals` and `inputs` default to regenerating the
    deliveries and reading the checkout - they are parameters so the rule can
    be tested without either. Nothing here accepts an arrival number."""
    if not recorded.readable:
        return FirstAffected(1, "The checkpoint's record of its inputs cannot be read, "
                                "so nothing says where a change begins - from the first arrival")
    if inputs is None:
        inputs = input_files(replay_patterns())
    changed = sorted(p for p in set(inputs) | set(recorded.inputs)
                     if inputs.get(p) != recorded.inputs.get(p))
    if changed:
        return FirstAffected(1, f"An input changed since the checkpoint ({_named(changed)}), "
                                "which can alter any arrival - from the first arrival")
    if arrivals is None:
        arrivals = regenerated_print(recorded.collection_id)
    old, new = recorded.arrivals, arrivals
    first = next((i for i in range(max(len(old), len(new)))
                  if i >= len(old) or i >= len(new) or old[i] != new[i]), None)
    if first is None:
        return FirstAffected(None, "Nothing differs from the checkpoint - nothing to replay")
    # WHICH FILE, AND WHAT HAPPENED TO IT, by its identity (arrival,
    # delivery, file) rather than the whole entry - a changed digest is a
    # CHANGED file, never a removed one (post-build-review #131 D1).
    def key(p: ArrivalPrint) -> tuple[str, str, str]:
        return (p.run_id, p.delivery, p.file)
    old_keys, new_keys = {key(p) for p in old}, {key(p) for p in new}
    if first < len(old) and key(old[first]) not in new_keys:
        differing, what, side = old[first], "removed", old
    elif first < len(new) and key(new[first]) not in old_keys:
        differing, what, side = new[first], "added", new
    elif first < len(new) and first < len(old) and key(old[first]) == key(new[first]):
        differing, what, side = new[first], "changed", new
    else:
        differing, what, side = (new if first < len(new) else old)[first], "moved", (
            new if first < len(new) else old)
    # A DELIVERY IS AFFECTED FROM ITS FIRST ARRIVAL: its files are one
    # delivery's, so its effect can begin at the earliest of them. Everything
    # before `first` is the same in both lists.
    earliest = next((i for i, a in enumerate(side[:first]) if a.delivery == differing.delivery),
                    first)
    # AN ARRIVAL NUMBER, NOT A FILE POSITION: the print has one entry per
    # file and an arrival can carry several files for one dataset, so the
    # position is counted in distinct arrivals (#131 D1 - counting files
    # reported every later arrival too late, the direction the fail-safe
    # NFR forbids).
    arrival = len(dict.fromkeys(p.run_id for p in side[:earliest + 1]))
    return FirstAffected(arrival, f"Delivery {differing.delivery!r} ({differing.file}) "
                                  f"was {what} - from arrival {arrival}")
