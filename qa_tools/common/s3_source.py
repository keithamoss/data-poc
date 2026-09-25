"""Real boto3-backed S3 browsing for mothman's S3 QA source mode (plans/
tooling.md #1 Phase 3) - list what's under a dataset's configured prefix,
download a chosen object (or every object under a chosen "delivery"
prefix, for Child Protection's 6-table shape) to a local staging dir, so
the rest of the flow can reuse the exact same Local files logic
(cli/bdm.py's run_check_local_file()/cli/cp.py's run_check_local_folder())
Phase 2 already built - S3 mode is "download, then Local files mode",
not a third parallel check-running code path.

Verified only via a mocked boto3 client in this sandbox (no real AWS
access - AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY are literal
"proxy-injected" here, same as qa_tools/common/results_s3_sink.py's own
Thread B account) - same s3_client=None-defaults-to-a-real-client
pattern that module already established, reused here rather than
invented fresh."""
from __future__ import annotations
import os


from qa_tools.common import yaml_io


def dataset_s3_config(contract_path: str) -> dict:
    """The 3 real top-level customProperties S3 mode needs
    (s3Source/localSource/arrivalPattern) from a dataset's own real ODCS
    contract YAML (contract/bdm-birth-registrations-contract.yaml /
    contract/child-protection-contract.yaml) - verified 2026-09-19
    against real datacontract-cli parsing before landing there (Keith's
    own explicit go-ahead to wire the previously design-doc-only
    arrivalPattern proposal into the real contract, once verified this
    way - see docs/aws-event-driven-mvp-design.md's own flagged
    "confirm in the morning" item). Missing entries read as None, not an
    error - a contract that genuinely has no S3 source configured yet is
    a real, valid state, not a config bug."""
    with open(contract_path) as f:
        doc = yaml_io.load(f)
    props = {cp["property"]: cp["value"] for cp in doc.get("customProperties") or [] if "property" in cp}
    return {
        "prefix": props.get("s3Source"),
        "local_source": props.get("localSource"),
        "arrival_pattern": props.get("arrivalPattern"),
    }


def _client(s3_client):
    if s3_client is not None:
        return s3_client
    import boto3
    return boto3.client("s3")


def list_keys(bucket: str, prefix: str, s3_client=None) -> list[str]:
    """Every real object key under prefix, sorted - good enough for a
    human picker (BDM's flat "one CSV per key" shape), not meant to
    imply any correctness-bearing order. A single list_objects_v2 call,
    not paginated - this project's own real buckets hold a demo/PoC
    volume of objects, not the 1000+ a paginator would matter for; add
    pagination if that ever stops being true."""
    client = _client(s3_client)
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return sorted(obj["Key"] for obj in response.get("Contents", []))


def list_delivery_prefixes(bucket: str, prefix: str, s3_client=None) -> list[str]:
    """The "folders" one level under prefix, via S3's own Delimiter="/"
    grouping (CommonPrefixes) - the real API mechanism for this, not
    manual key-splitting. Used by Child Protection's S3 mode, where one
    delivery is 6 table CSVs living under a shared prefix
    (<prefix><delivery_id>/), not a single flat key the way BDM's is."""
    client = _client(s3_client)
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")
    return sorted(cp["Prefix"] for cp in response.get("CommonPrefixes", []))


def download_key(bucket: str, key: str, dest_dir: str, s3_client=None) -> str:
    """Downloads one object to dest_dir/<basename of key>, returns the
    local path. dest_dir is created if it doesn't exist yet (a fresh
    per-check tmp staging dir every time, never a shared/reused one)."""
    client = _client(s3_client)
    os.makedirs(dest_dir, exist_ok=True)
    local_path = os.path.join(dest_dir, os.path.basename(key.rstrip("/")))
    client.download_file(bucket, key, local_path)
    return local_path


def download_prefix(bucket: str, prefix: str, dest_dir: str, s3_client=None) -> list[str]:
    """Downloads every object directly under prefix (delivery_prefix from
    list_delivery_prefixes(), typically) into dest_dir, one file per real
    key - Child Protection's S3 mode uses this once per delivery to pull
    all 6 real table CSVs into one local folder, then hands that folder
    straight to run_check_local_folder() exactly as if a human had
    downloaded it themselves. Returns the local paths, in the same order
    list_keys() would return the source keys (sorted)."""
    client = _client(s3_client)
    keys = list_keys(bucket, prefix, s3_client=client)
    return [download_key(bucket, key, dest_dir, s3_client=client) for key in keys]
