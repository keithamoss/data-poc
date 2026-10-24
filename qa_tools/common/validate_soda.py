"""The configuration-time gate over this project's SodaCL files (the
road-testing sweep's #7, Keith 2026-10-06).

TWO KINDS OF CHECK ARE REFUSED HERE, before any run:
- one Soda Core cannot parse - it logs an error and runs the rest, and the
  check never reports;
- one that needs Soda Cloud to evaluate - change-over-time and anomaly
  checks. They PARSE cleanly, so only knowing the kind catches them; at run
  time Soda Core logs that it must connect to Soda Cloud, leaves the check
  out of its results, and the run carries on (verified 2026-09-24 against
  soda-core 3.5.6; REQ-QAC-108's decisions carry the experiment).

The run-time half is soda_common.unreported_checks(): whatever this gate
cannot foresee still comes out red, "could not be evaluated", never absent.
Retired check files are not run, so they are not checked.
"""
from __future__ import annotations

import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Check kinds Soda Core cannot evaluate without Soda Cloud.
_CLOUD_ONLY = ("change ", "anomaly score", "anomaly detection")


def check_files() -> list[str]:
    return sorted(p for p in glob.glob(os.path.join(ROOT, "contract", "*-soda-checks.yml"))
                  if not p.endswith("-retired.yml"))


def problems(paths=None) -> list[str]:
    import yaml
    from soda.scan import Scan

    found: list[str] = []
    for path in paths or check_files():
        name = os.path.basename(str(path))
        scan = Scan()
        scan.set_data_source_name("config-check")
        scan.add_sodacl_yaml_file(str(path))
        for log in scan.get_error_logs():
            found.append(f"{name}: Soda Core cannot parse it - {' '.join(str(log.message).split())}")
        with open(path) as f:
            doc = yaml.safe_load(f) or {}
        for key, checks in doc.items():
            if not (isinstance(key, str) and key.startswith("checks for ")):
                continue
            for item in checks or ():
                line = next(iter(item)) if isinstance(item, dict) else str(item)
                if line.strip().lower().startswith(_CLOUD_ONLY):
                    found.append(f"{name}: '{line}' needs Soda Cloud to evaluate, which this "
                                 f"project does not use - compute it ourselves, as the volume "
                                 f"check does (REQ-QAC-108)")
    return found


def main() -> int:
    found = problems()
    for line in found:
        print(f"ERROR: {line}")
    if found:
        return 1
    print(f"Soda check files OK - {len(check_files())} file(s), every check runnable here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
