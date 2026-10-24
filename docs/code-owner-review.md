# Code-owner review of the delivery agreement

REQ-GHUB-174. A correction to an agreed date or due time
(`corrections:` in `contract/calendar.yaml` or `contract/data-asset.yaml`,
REQ-PIPE-111) names the person who approved it. This page says how far the
repository makes that name mean something, and where it stops.

## What the repository enforces

- `.github/CODEOWNERS` names the GitHub accounts that own
  `contract/calendar.yaml`, `contract/data-asset.yaml`,
  `contract/people.yaml` and the CODEOWNERS file itself.
- The configuration gate (`mothman check --only schedule`, run by the
  pre-commit hook and in CI) refuses a declared correction whose
  `approver` is not one of the code owners of the file it is declared in.
  The approver is matched to a GitHub account through `contract/people.yaml`'s
  `github:` field, and must also be the data asset's manager there.
- Both files are read **as they stood at the base of the change**, so a
  change cannot add its own approver as a code owner, or as the asset's
  manager, and then approve itself.

## What only GitHub can enforce

Requiring a code owner's **review** before a change merges is a
branch-protection setting on the repository. It is held by GitHub, not
in the tree, so this repository can neither set it nor check that it is on.

**It is off in this proof of concept.** Work here is pushed straight to a
branch by its one author, and a sole author cannot approve their own pull
request.

## Turning it on in a real deployment

On GitHub: **Settings → Branches** (or **Rules → Rulesets**) for the default
branch:

1. Require a pull request before merging.
2. Require review from Code Owners.
3. Optionally, dismiss stale approvals when new commits are pushed, so an
   approval covers the change as merged.

With that on, a change to any of the four files cannot merge without a
review from a person this file names, and the gate has already checked that
the correction names one of them. Neither proves the change board met; that
remains a process the approver is accountable for.
