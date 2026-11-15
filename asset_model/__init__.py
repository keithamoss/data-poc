"""asset_model/ - the shared reading code (REQ-PIPE-380, SPLIT D1 SETTLED by
Keith 2026-11-03).

ITS CHARTER IS 'CONFIGURATION AND THE DELIVERY TREE, NEVER THE DATABASE'
(QB, SETTLED by Keith 2026-11-14): asset time and its clock, the hierarchy,
the schedule and its slots, the collection registry's declarations, the
check-file readers, drift arithmetic, the declared corrections, the status
order and words, and arrival recognition over the delivery tree. It reads
each asset's definitions from assets/<asset>/ and holds none of its own -
no agency, collection, dataset, calendar date or time zone.

The real pipeline, the generator, scenarios/ and the bootstrap may all import
it, and it imports none of them (REQ-TEST-384's imports gate fails such an
import, naming the file and the line). It imports no database driver,
pandas, numpy or QA tool library at module level, runs no subprocess and no
git, opens no connection, and writes the delivery tree nowhere.
"""
