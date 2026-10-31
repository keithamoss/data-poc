# Sending a delivery: guidance for supplying teams

**Status: guidance for suppliers** (REQ-DOCS-274). Short on purpose. It is
the one place this advice lives, so when a delivery can mark its own
boundary some other way, only this page changes.

## Send the files of one delivery as one zip

When a delivery is more than one file - several tables of one collection
for the same period - send them **together, as one zip**. That applies
however you send them:

- **into a delivery directory**: one zip, not the files one by one;
- **through the cloud upload path**: upload one zip, not a separate object
  per file.

## Why: files sent separately are checked as they arrive

Each file is checked when it arrives. Some checks compare one table with
another - every notification names a client the client file holds, for
example. If the file a check needs has not arrived yet, that check cannot
run, and a check that cannot run reads **red**: nothing is reported green
that nobody could check.

So if you send the notifications file on Monday and the clients file on
Wednesday, the notifications file reads red from Monday until Wednesday.

**That red clears by itself.** Once the later file arrives and is promoted,
the earlier one is checked again against it, and nobody needs to do
anything. But for those two days the data team sees a red and may be told
about it - which is the whole reason for this page.

**A zip avoids it.** The files of one zip arrive at one instant and are
checked and decided together, so no file is judged against a partner that
has not arrived.

## What counts as "together"

Files are a delivery's package when they **arrive at the same instant** -
in practice, today, one zip. Files sent minutes apart are separate
arrivals, however close together. There is no other way yet to say that
separate files belong together; when there is one, this page will say so.

See also: [the on-disk delivery format](delivery-format.md) and the
[AWS design's cloud ingest limitation](aws-event-driven-mvp-design.md#known-limitation-on-the-cloud-path-every-file-is-a-package-of-one).
