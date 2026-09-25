"""What constitutes one delivery, stated per source (REQ-PIPE-057
criteria 2 and 3).

THE BOUNDARY COMES FROM THE TRANSPORT, not from the data. One folder
drop, one S3 prefix, one SFTP session - a delivery is an OBSERVED
TRANSPORT UNIT, and noticing what arrived together is categorically
different from reading a supplier's declaration of what they sent. That
distinction is worth keeping sharp: a format that read a declaration of
intent would reintroduce the design Thread B rejected, by a back door.

SO IT IS CONFIGURED RATHER THAN ASSUMED. Every source states what a
delivery is for it. A source that cannot express one - six unrelated S3
PUTs with no common prefix - needs a boundary arranged as a plumbing
step: a folder convention, a trigger file, a batch endpoint. That is an
operational transport arrangement rather than asking a supplier to
classify their own data.

AND A SOURCE THAT STATES NOTHING IS A FAILURE, never a default. The
alternative is inferring a grouping from filenames, timestamps or
arrival proximity, all of which are guesses that look like facts: files
landing within a minute of each other is a plausible delivery and also
what two unrelated suppliers look like on a busy morning. A wrong
boundary is not a cosmetic error - every arrival fact downstream is
derived from it.

TODAY EVERY SOURCE SAYS THE SAME THING, and that is not an argument for
hardcoding it. The value of stating it is that a second transport can be
DESCRIBED rather than requiring this module to grow a special case, and
that the day one is added, the one that was never configured fails
loudly instead of quietly inheriting a convention that does not apply
to it.
"""
from __future__ import annotations

from qa_tools.common import hierarchy

#: One directory under the deliveries root is one delivery. The only
#: boundary this PoC's transport expresses.
DIRECTORY = "directory"

#: Stated rather than open-ended, because an unknown value is a typo
#: far more often than it is a transport nobody has built yet, and the
#: two must not look the same.
KNOWN = (DIRECTORY,)


class DeliveryBoundaryError(ValueError):
    """A source whose delivery boundary cannot be acted on - missing,
    or naming something this transport does not implement. Names the
    source and the configuration, because "boundary not configured"
    sends somebody reading a file they have never opened."""


def boundary_for(collection_id: str) -> str:
    """What one delivery is, for this source.

    The SOURCE is the collection: it is what a supplier delivers, and
    what carries its own transport configuration in the ODCS contract.
    """
    entry = next((d for d in hierarchy.all_datasets()
                  if d.collection_id == collection_id), None)
    if entry is None:
        raise DeliveryBoundaryError(
            f"{collection_id!r} is not a collection in contract/data-asset.yaml.")
    declared = (entry.delivery_boundary or "").strip()
    if not declared:
        raise DeliveryBoundaryError(
            f"collection {collection_id!r} declares no `delivery_boundary:` in "
            f"contract/data-asset.yaml, so there is nothing to say what one delivery "
            f"from this source IS. This will not infer a grouping from filenames, "
            f"timestamps or arrival proximity - those are guesses that look like "
            f"facts, and every arrival fact downstream is derived from the boundary. "
            f"Declare one of: {', '.join(KNOWN)}.")
    if declared not in KNOWN:
        raise DeliveryBoundaryError(
            f"collection {collection_id!r} declares delivery_boundary {declared!r}, "
            f"which this transport does not implement. Known: {', '.join(KNOWN)}.")
    return declared


def check_all() -> dict[str, str]:
    """Every source's boundary, or an error naming every source that
    has none.

    ALL OF THEM AT ONCE rather than the first: somebody adding a
    collection has usually forgotten the same key in every one they
    added, and finding out one at a time is three runs instead of one.
    """
    problems, found = [], {}
    for collection_id in sorted({d.collection_id for d in hierarchy.all_datasets()}):
        try:
            found[collection_id] = boundary_for(collection_id)
        except DeliveryBoundaryError as exc:
            problems.append(str(exc))
    if problems:
        raise DeliveryBoundaryError("\n".join(problems))
    return found
