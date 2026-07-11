# Operator Mirror — WP4 Schema-Required Training Contract Checkpoint

Status: `DONE_SOURCE_ACCEPTED_SCHEMA_REQUIRED_TRAINING_CONTRACT` at
`f36379b9ddf10ee1055daeda27805c409c6ee8bd`.

WP4 now binds a repository-derived WP3 proof/reward receipt to exact candidate,
projection, decision, handoff, proof, after-cost reward, PIT dataset, row/split,
feature/label/leakage, code, dependency, effective LightGBM configuration, and
local resource hashes. The contract accepts no caller-supplied raw candidate,
proof, reward, or PIT inputs. Rehashed substitutions, forged proof-input hashes,
split identities, authority aliases, NaN values, and Boolean/integer aliases
fail closed.

This is not training. Every accepted contract remains `SCHEMA_REQUIRED`, with
`training_allowed=false`, `model_training_performed=false`,
`registry_write_allowed=false`, and no runtime/exchange attestation. The future
path must rehash actual fitted data, split membership, code, source head, and
effective configuration, observe a real fit and model bytes, and use only an
isolated immutable challenger registry. Legacy pipeline/serving registry,
symlink, `_latest`, serving, and promotion paths are explicitly disallowed.

The fresh collision scan found 139 migrations through V157, no duplicates, and
no V158 file/reservation in the observed source/ref/worktree surface. V158 is
only the provisional next candidate. No migration was reserved, created, or
applied; PostgreSQL runtime state was not refreshed.

Final focused tests passed `32`; adjacent tests passed `213` with `3` skips;
the exact-head full ML suite passed `1850` with `36` skips. Independent E2 and
QA final P0/P1/P2 are `0/0/0`.

No Linux, service, PostgreSQL runtime, Bybit, database-write, fit, model,
registry, serving/promotion, order, lease, Cost Gate, or authority action
occurred. G4 remains failed at runtime.

The Goal remains active. Next is an exact current E3/BB gate for provisional
forward-schema reservation/creation and isolated trainer/repository design.
