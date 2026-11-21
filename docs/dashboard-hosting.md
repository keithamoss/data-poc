# Hosting the dashboard: Cloudflare Pages behind Cloudflare Access

This is the runbook for publishing each data asset's dashboard. The two
requirements behind it are REQ-PIPE-255 (the upload) and REQ-PIPE-257 (the
sign-in).

Each asset has its own Cloudflare Pages project and its own Access allow-list
(REQ-PIPE-354). Each project is named in the asset's `assets/<asset>/data-asset.yaml`,
under `hosting:`.

| Asset | Pages project | Address |
|---|---|---|
| quarterly | `data-poc-quarterly` | https://data-poc-quarterly.pages.dev |
| daily | `data-poc-daily` | https://data-poc-daily.pages.dev |

Everything in this file is done by hand in the Cloudflare dashboard. mothman
never configures Access through the API. A token that could do that could also
change who may read the site, and the allow-list would have to be committed.
Instead, mothman **checks** the result: before every upload, after every
upload, and on demand with `mothman dashboard verify-access`.

## 1. The Pages projects

Do this once per asset.

1. Go to **Workers & Pages → Create → Pages → Upload assets**.
2. Name the project exactly as `hosting.pages_project` says: `data-poc-quarterly`
   or `data-poc-daily`.
3. Upload any placeholder file to create the project, then leave it. Every
   later deployment comes from `mothman dashboard publish`.
4. Under **Settings → Builds & deployments**, confirm that the production branch
   is `main`, the asset's `hosting.production_branch`. mothman passes it on
   every upload, so a publish from any git branch is a production deployment.

## 2. The publishing token

Create one token for both projects, with least privilege.

1. Go to **My Profile → API Tokens → Create Token → Create Custom Token**.
2. Give it exactly one permission: **Account → Cloudflare Pages → Edit**, scoped
   to this one account.
3. Give it no Zone, DNS or Access permission. A leaked token can then replace a
   site, but it can never change who may read one.
4. Record the token in the publishing environment only (section 6). It is never
   committed, and never put on a command line.

**Rotating the token:** create a new one the same way, replace
`CLOUDFLARE_API_TOKEN` where it is set, publish once to prove it works, then
delete the old token.

## 3. One-time PIN

1. Go to **Zero Trust → Settings → Authentication → Login methods → Add new →
   One-time PIN**.
2. Make it the only login method these applications offer (REQ-PIPE-257
   criterion 2).
3. Note your team domain, `<team>.cloudflareaccess.com`, shown under **Zero
   Trust → Settings → Custom pages**.
4. Put the team domain in each asset's `hosting.access_domain` in place of
   `CHANGE-ME.cloudflareaccess.com`, and commit it. It is configuration, not a
   secret.

Until this is done, every publish is refused: the pre-upload check sees a
redirect to a domain that is not the configured one. Nothing can be made public
by accident.

## 4. The Access applications and the policy

Do this per asset. Each project gets **two** applications under one policy.

1. Go to **Zero Trust → Access → Applications → Add an application → Self-hosted**.
2. **Application 1, the production hostname:** `<project>.pages.dev`.
3. **Application 2, every deployment and branch alias:** `*.<project>.pages.dev`.
   The project's "Enable access policy" setting protects preview deployments
   only, so don't rely on it.
4. Under **Identity providers** on each application, allow **One-time PIN only**.
5. **Policy:** Action **Allow**, with an **Include** rule of **Emails**, listing
   each person's work email one by one.
   - Never add an email-domain rule, an Everyone rule, or a Bypass or Service
     Auth rule (REQ-PIPE-257 criterion 3).
   - The email addresses live in Cloudflare only and are never committed
     (criterion 5).
6. **Session duration:** 24 hours, on each application.
7. **Cookie settings:** set each application's `CF_Authorization` cookie to
   **SameSite = Lax**, explicitly. Cloudflare documents no default for it.
   **Strict** can loop sign-in redirects (`ERR_TOO_MANY_REDIRECTS`), and the
   dashboard's data files need the cookie on same-site loads.
8. If a custom domain is ever attached to the project, give it an Access
   application of its own under the same policy (criterion 4).

## 5. Adding and removing a person

- **To add someone:** edit the policy from section 4 and add their work email
  to the Emails rule. They sign in with a one-time code sent to that address.
- **To remove someone:** delete their email from the rule. Then revoke any live
  session under **Zero Trust → Logs → Access → (their sessions) → Revoke**.
- **On both assets:** each asset has its own allow-list. Change the policy on
  each project the person should or should not see.

## 6. Publishing from a Claude Code cloud session

Set the secrets in the cloud environment's own settings. They sit beside
`MOTHMAN_ENVIRONMENT` and the database variables:

| Variable | What it is |
|---|---|
| `CLOUDFLARE_API_TOKEN` | the token from section 2 (a secret) |
| `CLOUDFLARE_ACCOUNT_ID` | the account id, from the dashboard's right-hand sidebar |
| `MOTHMAN_ENVIRONMENT` | `sandbox`, the one environment that publishes (`assets/environments.yaml`) |

The session's network must also allow:

- `api.cloudflare.com` and Cloudflare's upload endpoints, for the upload;
- `*.pages.dev`, for the checks before and after every upload;
- your `<team>.cloudflareaccess.com`, for the sign-in redirect the checks expect.

All three were refused by the session proxy when measured on 2026-10-18. Until
they are allowed, a publish fails at its pre-upload check, which says "could not
be checked".

The publishing environment needs Node as well as Python: run `npm ci` once
(it installs the pinned `wrangler`), beside `uv sync` and
`uv run playwright install chromium`.

## 7. Publishing, and checking

- **`MOTHMAN_ASSET=<asset> mothman dashboard publish`** builds, gates and checks
  the sign-in. If the content has changed since this asset's newest snapshot, it
  archives one, uploads, and checks the new deployment's own address. If the
  content is unchanged, it uploads nothing.
- **`... publish --dry-run`** says what would be uploaded, and uploads and
  archives nothing.
- **`MOTHMAN_ASSET=<asset> mothman dashboard verify-access`** checks the
  production address and the newest deployment's address, uploading nothing.

## 8. The first live publish, recorded once

REQ-PIPE-257 criterion 14 must be checked once, from an environment that can
reach Cloudflare. Record each result on the requirement, with who did it and
when, but no email addresses:

1. An unauthenticated `curl` of the production URL, and one of a deployment URL,
   each returning the Access sign-in redirect.
2. The `CF_Authorization` cookie set by a real sign-in carrying `SameSite=Lax`,
   on both applications.
3. One allow-listed person other than Keith signing in and seeing the dashboard.
