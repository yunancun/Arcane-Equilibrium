# Role Profile, Closure, And Memory Standard

Canonical role Interface: `.codex/agent_registry_v1.json`
Design: `docs/agents/development-agent-governance.md`

## Source split

| Content | Authority |
|---|---|
| Stable role activation, capability, permission, output | Registry |
| Claude/Codex/profile role text | generated Adapter; never hand-edit |
| Domain review depth | referenced role skill/charter Implementation |
| Current queue/blocker/runtime claim | `TODO.md` + fresh evidence |
| One task's outcome/evidence/dissent | `closure_packet_v1` / Report Sink projection |
| New durable recurring lesson | role/global memory after PM closure plus trusted-host promotion attestation |
| Historical detail | reports/archive, on demand |

`docs/CCAgentWorkSpace/*/profile.md` remains for human navigation but is generated
from Registry. It is not a fourth authority. Run:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py render --check
```

## Memory promotion

Memory is a durable lesson index, not a task ledger. A lesson is eligible only
when PM closure proves it likely to change future judgment; actual mutation also
requires the trusted-host authority defined below:

- repeated mistake and proven prevention
- stable operator preference
- recurring role heuristic
- authority/source routing rule
- conflict resolution likely to recur

Do not append daily progress, test counts, runtime PID, current blocker, full
report, diff, stack trace, or repeated boundary boilerplate. Those belong in
TODO/closure/report/archive.

Before promotion, deduplicate against the existing lesson. If superseded, record
an evolution pointer instead of copying both full narratives. Large historical
memory remains searchable but is never universal preload.

## Hot-memory contract

Every active `docs/CCAgentWorkSpace/<ROLE>/memory.md` is a bounded index, not a
transcript. It must be valid UTF-8, end with one newline, stay at or below 300
lines and 48 KiB, and contain exactly these H2 sections in order:

1. `Usage contract`
2. `Durable lessons`
3. `Topical pointers`
4. `Archive pointer`

No nested dated/task section, date-organized history, or task/session ledger row
is admitted. The archive pointer binds the append-only payload by path, byte
offset, byte length, payload digest, pointer digest, and recovery manifest.
Exact historical recovery uses `history_refs` or the manifest; it never makes
the full archive a startup preload.

`helper_scripts/maintenance_scripts/role_memory_compaction.py` is the only
mechanical compactor. It preserves every pre-existing archive prefix, appends
the original active bytes, proves byte-identical recovery, writes
`docs/agents/role-memory-compaction-v1.json`, and is idempotent. The historical
manifest path is unchanged, while its current schema is
`role_memory_compaction_manifest_v3`. A verified, unpromoted v1 or v2 snapshot
upgrades to generation 1 through `--apply` without changing any active-memory
or archive bytes. Check with:

```bash
python3 helper_scripts/maintenance_scripts/role_memory_compaction.py --check
```

Do not manually edit archived payloads, offsets, digests, or generated hot
pointers. Direct active-memory edits, even when accompanied by recomputed active
and manifest digests, fail because the durable-lesson list must equal the
original compacted lessons plus the manifest's promotion lineage.

`PM_CLOSURE` is a requested authority kind, not authorization by itself. A
canonical closure digest, literal authority label, manifest self-digest, or
promotion self-digest proves only repository-record integrity and is
caller-forgeable. Mutation therefore requires all of:

- a typed `role_memory_promotion_authority_v1` whose trust tier is exactly
  `PLATFORM_OR_EXTERNAL_ATTESTED`;
- exact role, durable-lesson digest, closure digest, producer, attestation ID,
  authority kind, and record digest bindings;
- a non-serialized trusted-host
  `PromotionAuthorityVerifier(kind, digest, exact_artifact)` capability that
  authenticates those exact bytes out of band.

The standalone CLI has no such capability. Its `--promote` mode always returns
typed `EXTERNAL_LIMIT` with `mutation_applied=false` and a non-zero exit; it
never treats CLI arguments or a serialized attestation as authority and never
writes memory, archive, or manifest bytes. Promotion remains unavailable until
an embedding trusted host supplies the verifier capability.

The host-only promotion interface also rejects unknown roles,
empty/untrimmed/multiline or ledger-like lessons, malformed or mismatched typed
authority, duplicate lessons with different lineage, and a successor that would
exceed the hot-memory bounds. Every host-authenticated promotion:

1. appends the exact prior hot view and exact canonical prior-manifest bytes to
   the same role's append-only archive;
2. writes a reconstructable marker binding role, request digest, predecessor
   generation/self-digest, and both payload sizes and digests;
3. increments `generation` and binds `supersedes_manifest_digest` to the exact
   preceding manifest;
4. publishes the successor manifest and generated hot view.

Verification exact-parses and reconstructs the archive record, parses the
archived predecessor manifest, checks canonical bytes, self-digest, generation,
promotion prefix, and predecessor active binding. Changing a predecessor digest
and recomputing current self-digests without changing the archive therefore
fails closed. Replaying the same role/lesson/closure/attestation request is
byte-idempotent. If publication stops between the manifest and hot-view writes,
`--apply` resumes only when the current bytes equal the last promotion's
digest-bound prior-active archive slice; arbitrary drift still fails closed.

Standalone `--check` verifies structural integrity and recoverability only. It
does not replay the out-of-band host authentication and must never be cited as
proof that a platform or external producer actually authorized the promotion.

## Codex host memory policy

Project Codex config enables memories but excludes threads that used external
context from generation. Per-thread extraction and global consolidation use
`gpt-5.6-luna`; ordinary role calls do not inherit that choice. These keys are
host capabilities rather than repository authority, so validate them
read-only before claiming support:

```bash
python3 helper_scripts/maintenance_scripts/codex_memory_policy_probe.py
```

The probe checks strict config-key parsing, a deliberately unknown-key negative
control, the local Codex version, and bundled model availability. Its only
positive state is `SUPPORTED`; missing binary, strict parsing, or model catalog
is a typed `EXTERNAL_LIMIT`, never silent fallback. External-context exclusion
reduces accidental retention of MCP/web-derived material; it does not replace
trusted-host-authorized durable promotion or the hot-memory contract.

## Report/closure behavior

Reviewers return immutable structured fragments. They do not write a report and
append memory merely because they reached a conclusion. PM may project one
durable task closure through `report_sink_v1` when future audit/handoff needs it.

The projection preserves:

- source/runtime/external evidence hashes and freshness
- facts/inferences/assumptions
- gate dissent and unresolved coverage
- checks as EXECUTED/REUSED/SKIPPED/FAILED
- skipped roles with reason/residual risk/owner
- measured consumption or unavailable reason

Identical input should produce a byte-stable projection. Operator-facing summary
is a view of the same closure, not a second authority.

## Historical files

Existing `memory.md` and per-role reports are retained as history. Their presence
does not require startup reads or continued per-task growth. When cleanup is
needed, archive mechanically with the compactor and a digest-bound pointer; do
not silently delete evidence.

## Conflict handling

Role/profile/memory cannot override Registry permissions, normative policy,
current TODO, direct source, or fresh runtime evidence. Use the typed authority
matrix; do not apply a total-order winner across classes. Mark DRIFT/CONFLICT and
preserve both claims in closure.
