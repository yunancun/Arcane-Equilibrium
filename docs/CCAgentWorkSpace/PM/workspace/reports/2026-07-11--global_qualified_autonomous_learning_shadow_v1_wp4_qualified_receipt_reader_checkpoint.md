# WP4 Qualified Receipt Reader — Source Checkpoint

Date: 2026-07-11
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Work item: `WP4-QUALIFIED-RECEIPT-READER-TDD`
Source checkpoint: `fb842a36f006ad58249ff536a455232d2c455f8b`
Status: `DONE_SOURCE_ACCEPTED_QUALIFIED_RECEIPT_READER_TRACER`

## Accepted source effect

`read_qualified_training_receipt(connection, *, training_contract)` exposes no
raw-hash lookup. It deep-copies and validates one existing
`alr_challenger_training_contract_v1`, derives its exact durable-receipt and
training-key hashes, then calls only:

```sql
SELECT learning.read_alr_qualified_training_receipt_v1(%s::text, %s::text) AS repository_result /* alr-challenger-repository:qualified-receipt-reader */
```

`FOUND` must return the exact typed 20-field receipt, offset-aware
`created_at`, canonical payload, and authority-map parity already required by
the writer. `NOT_FOUND` must be exactly the two-key response with `receipt`
null. Writer statuses, extra/missing fields, divergent hashes, Boolean/integer
aliases, naive timestamps, and mutable-input drift fail closed.

The reader uses the same dedicated clean psycopg2 contract: `autocommit is
False` and exact integer transaction status IDLE before cursor acquisition.
Success commits only after response validation. Execute, fetch, validation, or
commit failure rolls back once; a rejected pending connection is untouched.

Frozen SHA-256 values:

- repository module: `fbf733ab82428cbee5b450f9b06243cd155fea850287d50018436184bb48ea72`
- repository tests: `683688b4da417a49eb065e8c3ffdab8ad16cb28248266c2169f94b6106676628`

## Verification

- RED 1: import failed because `read_qualified_training_receipt` did not exist.
- RED 2: exact `NOT_FOUND` failed with `receipt_response_status_invalid` before
  the separate read-response branch existed.
- Focused repository suite: `61 passed`.
- Adjacent repository/training-contract/V158 suite: `130 passed`.
- Full ML suite: `1911 passed, 36 skipped in 20.12s`.
- Same-environment baseline: all non-repository ML tests `1850/36` plus the
  unchanged writer subset `31`; baseline `1881/36`, exact reader delta `+30`.
- Governed E4 captures: focused
  `79d0c1ce5f00cff5597d798aa1d6495059cb63f2e7fd383fea8973049504b552`,
  adjacent
  `5175cc83b3bc9186cce5a947f2ca4598ee801d783e1c7712b9650d6ff361941c`,
  diff check
  `75dcc6d9a44b375aa093fd8943ead24a1bac3da789842c423604993b1f73989b`.
- E2, E4, MIT, and parallel exact review: PASS; P0/P1/P2 `0/0/0`.
- Python compile, exact SQL/argument pins, public-signature pin, forbidden-path
  scan, and diff checks: PASS.

E2's isolated command environment initially hid the user-installed pytest;
E4 used a transient `/tmp` venv exposing the already-installed local pytest and
produced the governed execution captures above. No repository byte changed for
that environment repair.

## Deliberate unexecuted boundary

This was source and fake-connection TDD only. V158 was not applied or exercised
against PostgreSQL; `_sqlx_migrations`, Linux, runtime services, and exchanges
were not contacted. This step created no receipt/run/artifact/registry row,
proof/reward fact, fit, model or ONNX byte, file, symlink, serving/promotion
state, order, lease, Cost Gate change, or authority. G3 and G4 remain failed at
runtime.

## Next safe action

The Goal remains `ACTIVE`. Implement only a pure
`alr_challenger_training_result_contract_v1` builder/validator before exposing
V158's broad result writer. It may validate synthetic fixtures but must not
claim actual fit or artifacts. Receipt/result API calls, trainer execution,
fit, filesystem publication, registry, V158 apply, PG/Linux/runtime, serving,
and exchange work remain outside that cycle.
