"""Where a kind's one-offs are published (REQ-PIPE-443 criterion 1), read live
from the kind's template, one-offs/<kind>/_template/publishing.yaml, at the
moment of publishing (REQ-PIPE-440 criterion 13) - never copied into a
one-off's folder, so changing where a kind publishes is one edit, and a page
already published stays where it was written.

SHARED BY EVERY KIND: the file, its one field and its gate are the same for
every kind's template; only the value differs.

CONFIGURATION ONLY: this reads the template's file and says what is wrong with
it. Writing a page, and reading one back, is qa_tools/common/one_off_publish.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: The template file naming the destination.
DESTINATION_FILE = "publishing.yaml"
S3 = "s3://"


class NoDestination(ValueError):
    """The kind's template names no usable destination. Its message says why."""


@dataclass(frozen=True)
class Destination:
    """A filesystem folder or an S3 prefix, as the template names it."""

    #: As written in the template - a path (relative ones are read from the
    #: repository root) or s3://bucket/prefix.
    stated: str
    #: The folder, resolved, for a filesystem destination; None for S3.
    folder: Path | None
    bucket: str | None = None
    prefix: str = ""

    @property
    def is_s3(self) -> bool:
        return self.bucket is not None

    def address(self, name: str) -> str:
        """Where `name` is written - a path, or an s3:// address."""
        if self.is_s3:
            return f"{S3}{self.bucket}/{self.prefix + '/' if self.prefix else ''}{name}"
        return str(self.folder / name)


def problems(template: Path) -> list[str]:
    """What is wrong with the template's destination - the template gate
    (REQ-PIPE-448 criterion 6), and the publish's refusal."""
    try:
        read(template)
    except NoDestination as exc:
        return [str(exc)]
    return []


def read(template: Path) -> Destination:
    """The destination the template names, read now."""
    from asset_model import assets, config_yaml

    path = Path(template) / DESTINATION_FILE
    if not path.is_file():
        raise NoDestination(f"{path} is missing - it names where this kind's one-offs are "
                            f"published (`destination:`, a folder or an s3:// prefix).")
    doc = config_yaml.load(path) or {}
    stated = doc.get("destination") if isinstance(doc, dict) else None
    if not isinstance(stated, str) or not stated.strip():
        raise NoDestination(f"{path} names no `destination:` - a folder or an s3:// prefix.")
    stated = stated.strip()
    if stated.startswith(S3):
        bucket, _, prefix = stated[len(S3):].partition("/")
        if not bucket:
            raise NoDestination(f"{path}'s destination {stated!r} names no bucket.")
        return Destination(stated, None, bucket, prefix.strip("/"))
    folder = Path(stated)
    if not folder.is_absolute():
        folder = assets.ROOT / folder
    return Destination(stated, folder)
