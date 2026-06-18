# Operator Brief — TODO v175 Funding/OI Backfill Completed-Row Archive

PM removed `P0-EDGE-1-CAND-FUNDING-OI-BACKFILL` from `TODO.md` §5.

Reason: it is completed foundational data work and still summarized in TODO §2. Read-only DB recheck confirmed funding rows=46,539 and OI rows=348,153 under the single run_id `18b3c2f8-6125-42a8-a42c-cfcc8aec9406`, with 0 NULL values.

Important caveat preserved: the schema is run-versioned, so re-apply appends a new run. Any future cron/refresh needs a fresh active task for clear-old-run and wrapper design.

Boundary: read-only SQL plus docs hygiene only. No deploy, rebuild, restart, DB write, auth/risk/order/trading mutation.
