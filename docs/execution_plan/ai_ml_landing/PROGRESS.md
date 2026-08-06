# AI/ML Landing Progress Ledger

**Program**: `AIML-LONG-LIVED-LANDING-V2`
**Ledger version**: 26
**Updated**: 2026-08-06（Tier 1 durability anchor 四輪對抗複核收口；round-3／round-4 補入帳本；W5 round-11 re-emission）
**Overall state**: `PROGRAM_ADOPTED` · **`S1_CLOSED`** · every S2 effect-session
source-seam predicate is narrowly `SOURCE_READY` (S2.0 + S2.1 + S2.2A + S2.3 +
S2.4 + S2.5 + S2.2B), while Sprint 2 remains
**`S2_EFFECT_EXECUTION_READINESS_ACTIVE`**. The nine effect-readiness split
packages are **5/9 source-landed**: `S2E.0`, `S2E.1`, `S2E.2a`,
`S2E.2b-1`, and `S2E.3`. The only unclosed package entry is `S2E.2b-2`;
its LW1 subwave is external-blocked, and the dependency order remains
`LW1 → LW2 → S2E.2b-3 → S2E.4 → S2E.5`.
`S2E-LW1` has a clean source implementation checkpoint at `44edecd91`
(Tier 1 durability anchor, after four rounds of adversarial review; candidate PR,
not merged), but is `WAITING_EXTERNAL_PREREQUISITES`: W0 genesis and LW1 receipts
are absent, the transition did not `ADVANCE`, and LW2 remains locked. The closed
machine packet
at `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_lw1_external_prerequisite_action_packet.json`
records 16 blocking prerequisites (12 fixed paths + 4 services) at its own pinned
checkpoint `970734ae0`. `S2-operator-action-packet-v1.md` remains
`DRAFT_NOT_EXECUTABLE`; the real S2.5 host/recovery effect lane, S2.4 row drivers,
authenticated runtime closure, and disposable full-DAG rehearsal remain open.
All landed readiness packages were `NONE`-effect: no
runtime/PG/broker/order effect occurred and nine authorities stay false.
**S2 is NOT `S2_CLOSED`**: production effect progress is **0/6**. Linux
observation at 2026-08-02T22:13:32Z (Linux head `097c879b9`, clean) found both
candidate learning units `not-found/inactive/dead`, both canonical AIML install/
state roots absent, and all 11 LW1 fixed trust/attestor paths absent. The three
host-side durability-anchor/replica/registry service prerequisites are
`NOT_OBSERVED`, not self-declared ready.
Nine authorities remain false; no production effect may start before the S2E
source waves close and a newly emitted packet receives fresh exact authority.
The 2026-07-30 calibration-checkpoint narrative and the S0/S1
finalization/provenance narrative were moved verbatim to
`PROGRESS-archive-1.md`(2026-08-01 generation split; information-
conserving). Their conclusions stand unchanged: the calibration
checkpoint closed only launch-gate review debt — it issued no W0/LW1
receipt, did not satisfy `S2E_2B_2A_SECURITY_RECOVERY_READY`, did not
unlock LW2, and did not change the 5/9 package projection or
production effect 0/6. The 2026-08-02 implementation checkpoint adds the missing
source/security contracts and replaces caller-authored host-capture signing with a
zero-input root-owned attestor that must derive the complete signed artifact from an
immutable source view; it
does not change those receipt/effect conclusions.
**Adopted source generation**: reviewed head
`1a933fcc28e9f7341e023b5d401c479957c14c5f`, merged as
`fed223bebd278c50b0ab3330980e66441a30c9ed`. Program-adoption receipt
`docs/execution_plan/ai_ml_landing/receipts/S0.3-program-adoption-receipt-v1.json`
(`sha256:1a124bcaebb741a69c97e37a828e5b85c9b6499cdf053e8ef62451448878f93b`);
finalization attestation + trusted execution bundle (each plus `.sig`, verifying
against the adopted source trust root) live in the same receipts directory.
**Next gate**: consume the LW1 prerequisite action packet and obtain fresh
machine evidence for the fixed roots, signer capability, host append-only
durability anchor, off-host append-only replica and distinct host append-only
predecessor registry. The three root-owned producer capabilities behind those
service prerequisites are unimplemented, so no W0/LW1 receipt can be emitted
until they exist.
Only a current-head W0 genesis plus LW1 transition `ADVANCE` may unlock LW2;
then continue `LW2 → S2E.2b-3 → S2E.4 → S2E.5`. Do not reopen the five
completed packages or rerun a no-delta source loop.
The production effect DAG remains
`S2.0→S2.4→S2.5A→S2.1→S2.5B→S2.2B` and then requires fresh exact Operator
authority per step.
**Canonical boundary**: S0 and S1 are closed. S1 has committed real disposable
S1.5 evidence, a platform-attested Linux S1.6 effect, a complete validated
closure packet, and a domain-separated operator SSHSIG. These prove the
Sprint-1 disposable effect seams and selected runtime mechanism; they do not
grant production runtime/build/PG/migration/deploy/ML5/ML6/broker/order
authority. All nine grants remain false and source adoption is not production
runtime readiness.

## Ledger Contract

`TODO.md` owns active priority. Immutable `session_attempt_v1` and
`closure_packet_v1`/Report Sink records own authoritative Session outcomes; this
file is their repo-resident projection and resume index. Update a row only with
the exact branch/PR/head and completion receipt. Preserve prior outcomes in the
row notes or append a dated ledger event; do not silently rewrite failed
evidence. A later Session consumes only valid, scope-compatible, hash-bound
dependency generations.

Allowed status:

```text
PLANNED | READY | IN_PROGRESS | SOURCE_READY | RECOVERY_REQUIRED | BLOCKED | BLOCKED_STALE_EVIDENCE | NOT_APPLICABLE_NO_CANDIDATE |
DONE | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | SUPERSEDED
```

Required closure fields for a `DONE` row:

- `(session_id, landing_scope_id, cohort_epoch, attempt)` or `PROGRAM` template;
- `platform_scope`, `policy_surface_id`, exact covered decision cells and
  evidence-environment promotion edges;
- exact branch, reviewed head, PR/merge head and owned path manifest;
- route/DAG digest, explicit node IDs/classes/permissions/path ownership/
  predecessors and builder -> E2 -> E4 plus post-build semantic review;
- focused/local validation and CI classifier digest, selected workflows, exact
  head, invocation count and failure fingerprints;
- classifier-derived `required_effects`, Adapter ID, actor node, rollback and
  distinct postcheck node, including a typed `NONE` when no effect is possible;
- completion receipt hash, validity class, causal-time edges and next dependency.

Before work, W0 CAS-creates the attempt with owner lease epoch/expiry/heartbeat,
branch/worktree, baseline/checkpoint, path manifest and dependency generations.
Lease expiry moves to `RECOVERY_REQUIRED`; only CAS adoption/finalization can
resume or close it.

Class-specific invalidity recursively demotes all dependent attempts.
`CURRENT_STATE_TTL` expiry and explicit retroactive compromise/revocation do;
natural expiry of already consumed `EFFECT_TIME_AUTHORITY` does not invalidate
its `IMMUTABLE_CONSUMED_EFFECT`. `IMMUTABLE_LINEAGE` fails only on hash/causality
break. No generic scope template can be `DONE`; it must first be instantiated.

## Amendment A2 — Sprint 2 effect predicate split (source vs effect)

Normative text: `docs/agents/ai-ml-landing-delivery-protocol.md` §Sprint 2
Amendment A2. The full ledger-side elaboration was moved verbatim to
`PROGRESS-archive-1.md` (2026-08-01 generation split). Summary: every S2
effect Session and the runtime-`DONE` session S2.2B carry two mechanical
predicates — `SOURCE_READY` (fail-closed until exact operator
authorization; nine authorities false) and `EFFECT_DONE` (real
operator-authenticated production apply). Dependency qualifiers apply per
predicate: `SOURCE_READY` consumes upstream `@SOURCE_READY`; `EFFECT_DONE`
consumes upstream `@EFFECT_DONE`. The `source_deps` build order is
`S2.0→S2.1→S2.4→S2.5→S2.2B`; the serial operator-gated apply chain is
`S2.0→S2.4→S2.5A→S2.1→S2.5B→S2.2B`, surfaced as one minimal
`BLOCKED_OPERATOR_ACTION_PACKET_READY` after every source predicate lands.
Session IDs are unchanged.

## Current Sessions

closed S0.x/S1.x rows(全部 DONE)已遷 `PROGRESS-archive-1.md`(資訊守恆);本表保留 S2 起的 current/future rows。

| Sprint | Session | Work package | Scope template | Dependencies | Required role route template | Status | Completion receipt | Required effect | Sync / CI policy |
|---:|---|---|---|---|---|---|---|---|---|
| 2 | S2.0 | Bootstrap production PG observer role/auth/ACL only | PROGRAM | EFFECT_SEAMS_READY | PM -> external admin Adapter -> distinct OPS/E3 -> QA -> PM | SOURCE_READY | **`SOURCE_READY`** (WP2): `pg_observer_bootstrap_adapter_v1` (registry `declared_production_apply_disabled_until_operator_sshsig`) — typed intent/result/postcheck/rollback schemas + structured-SQL-allowlist read-only observer role (role-level `default_transaction_read_only`/`search_path=pg_catalog`) + disposable-PG apply/rollback/postcheck proofs (real 42501/28P01); branch `agent/aiml-s2-wp2-s20-observer`, reviewed head `b831f3ff0`, PR #127 merge `e86e945bf`; 5-reviewer wave (E2/E4/CC/E3/OPS) + 4 adversarial delta/closure gates + 4 Codex P1/P2 all resolved. **Hash-bound proof**: the adapter IS the source deliverable, hash-bound by merge commit `e86e945bf`; the disposable apply/rollback/postcheck proof is `tests/structure/test_agent_governance_pg_observer_bootstrap_disposable.py` (real 42501/28P01 on a throwaway cluster), reproducible from that checkout — so `S2.0@SOURCE_READY` is validatable/invalidatable by checkout+rerun, with no standalone receipt artifact (unlike the NONE-effect S2.2A/S2.3, whose deliverable IS a receipt file). Evidence `LOCAL_REPRODUCIBLE` (59 offline+disposable; frozen classifier `sha256:1cf8c021…` unchanged, `PROGRAM_SCHEMA_PATHS` untouched); apply fail-closed `EXTERNAL_VERIFICATION_PENDING` until operator SSHSIG. **`EFFECT_DONE` pending** operator SSHSIG at the S2.0 EFFECT session | `PG_OBSERVER_BOOTSTRAP` | Exact intent; no migration/writer |
| 2 | S2.1 | LR0 evidence/quiescence/static guards | PROGRAM | S2.0, S1.6 | PM -> OPS/E3 -> E1 -> E2 -> E4 -> QA -> PM | SOURCE_READY | **`SOURCE_READY`** (WP3): `alr_quiesce_fence_adapter_v1` (registry `declared_production_fence_disabled_until_s20_effect_and_operator_sshsig`) — typed `quiesce_{intent,observation,result,rollback}_v1` schemas (centrally registered in `SCHEMA_FILES`) + owner/process/unit/cgroup/env/restart/watchdog/queue/credential inventory (`agent_governance_alr_quiesce_inventory.py`) that fences **only** a confirmed single ALR owner (C1 exact 10-token content-addressed invocation + `posixpath.normpath` anti-traversal guard, C2/C3 `candidate_pids==[main_pid]`) via the unit's own **system-level** `systemctl stop` (never pid/name/pattern) + `apply_quiesce_fence` with try/finally un-fence guarantee (typed `FAILED` on exception) + C4 TTL cross-field bound (`duration+sample_interval ≤ min(ttl, MAX_AUTHORIZATION_TTL=900)`); route CLASS with no effect-node injection; SSHSIG namespace `arcane-equilibrium-aiml-s2-quiesce-fence`; production fence fail-closed `PENDING`/`EXTERNAL_VERIFICATION_PENDING` until `S2.0@EFFECT_DONE` + operator SSHSIG. Branch `agent/aiml-s2-wp3-s21-quiesce`, reviewed head `5fe1fc11a`, final `c8e88c652`, PR #129 merge `31ef0b4bc`; 5-reviewer wave (E2/E4/CC/E3/OPS) + 4 Codex P1 + C4-TTL all resolved. **System-unit amendment (Blocker-1, PR #134 merge `e514f1e76`)**: per the operator's corrected S2.4 §8 this seam was realigned from the user-level `openclaw-alr-shadow.service`/`systemctl --user`/`alr_shadow` to the **system-level** `arcane-equilibrium-aiml-engine-scanner.service` (`User=aiml-engine-scanner`, content-addressed ExecStart, DB `trading_ai`, PG role `aiml_engine_scanner`, `LoadCredentialEncrypted` DSN, hardened) — the byte-for-byte unit identity WP4 §8 installs; C1 is now a 10-token content-addressed fingerprint with a `posixpath.normpath` anti-traversal guard. This satisfies the WP4-`SOURCE_READY` admission requirement "WP3 landed and aligned to the same system unit" (§11.2); together with the landed program-DAG amendment (Blocker-2, PR #132), **both WP4 admission blockers are cleared**. Evidence `LOCAL_REPRODUCIBLE` (86 offline+disposable, disposable ran on a throwaway cluster; frozen classifier `sha256:1cf8c021…` unchanged, `PROGRAM_SCHEMA_PATHS` untouched). **`EFFECT_DONE` pending** `S2.0@EFFECT_DONE` + per-adapter operator SSHSIG at the S2.1 EFFECT session | `QUIESCE_FENCE` | Typed intent; no general CI |
| 2 | S2.2A | LR1 scoped compatibility source implementation | PROGRAM | S1.6 | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM | SOURCE_READY | `source_compatibility_receipt_v1` (`receipts/S2.2A-source-compatibility-receipt-v1.json`) self `sha256:a8fba423…`, `learning_runtime_digest sha256:6cf76b60…`, 10 V151-V160 fingerprints; branch `agent/aiml-s2-2a-lr1-compat`, reviewed `7054a3b0`, PR #121 merge `87a3a2503`; E2/E3 PASS + E4 PASS_WITH_CONCERNS; evidence `LOCAL_REPRODUCIBLE` (415/1 + 2259/36); receipt reproduces from checkout | `NONE` | Narrow Python local-first; exited SOURCE_READY. Runtime `DONE` is S2.2B |
| 2 | S2.2B | LR1 runtime revalidation of exact S2.2A manifest | PROGRAM | S2.5, S2.2A@SOURCE_READY | PM -> independent OPS/E4 -> QA -> PM | SOURCE_READY | **`SOURCE_READY`** (WP5 tranche 2, PM declaration 2026-07-28, PR #150 merge `6be29043c`): `ingestion_compatibility_receipt_v1` closed schema + central leaf + builder/CLI + fixtures anchored on the real persisted S2.2A receipt and a fully re-validated `s2_5_final_attestation_v1`; runtime-`DONE` still consumes `S2.5B@EFFECT_DONE` and remains the only row that may issue the LR1 runtime DONE | `REMOTE_READONLY` | Only row that issues LR1 runtime DONE |
| 2 | S2.3 | LR2 sealed immutable runtime build/trust chain | PROGRAM | S1.3, S1.6 | PM -> PA -> E1 -> E2 -> E4 -> CC/OPS -> QA -> PM | SOURCE_READY | `sealed_build_receipt_v1` self `sha256:169d2e6c…` (runtime_content `sha256:8b2092e8…`, closure `sha256:26307134…`, target `x86_64-unknown-linux-gnu`) + `expected_identity_receipt_v1` self `sha256:a08c6965…`; real `requirements-ml.lock` (38 pinned/0 unpinned); branch `agent/aiml-s2-3-lr2-sealed`, reviewed `73b083e9`, PR #122 merge `051df8262`; E2/E3/E4/CC/OPS + 2 Codex P2 + FA/CC final audit PASS; heavy `learning-runtime-sealed-build` CI job green (real offline install+import on Linux) | `NONE` | Runtime/build CI green; NOT a running attestation (S2.5/LR6). Central-validator registration = serialized follow-up |
| 2 | S2.4 | Credential/PG/unit/install effects and component restore | PROGRAM | S2.0, S2.1, S2.2A@SOURCE_READY, S2.3 | PM -> OPS preflight -> E3 -> Adapter -> distinct OPS -> QA -> PM | SOURCE_READY | **`SOURCE_READY`** (WP4/W5, PM declaration 2026-07-28, PR #145 merge `e1b14b7d5`): W0–W5 chain + eight persisted receipts bound `f30ede36134f1464cef4bc025f808b931aebe180` (carrier `3df9d2f451ceb7ab66117de6e33fd882d59a9531`, round 9, ledger digest `sha256:90f9261845b4782e577ef34e40369b3bcaf30381ce46d62d7246c087b3ed208e`) + ABI-pinned obligation ledger (28 rows) + discriminator projection regression; effect route unchanged and still gated — the S2.4-AMEND-1/2 **source** preconditions landed in S2E.0 (final head `f30ede361`, 2026-07-28: §9.2 refresh ingress in APPLY, terminal-receipt refresh digests, §9.1 profile discriminators, plan-derived `expected_topology`); `S2.4@EFFECT_DONE` still requires the remaining `S2E.2b-2 → S2E.2b-3 → S2E.4 → S2E.5` chain and fresh operator authorization | `CREDENTIAL_PG_UNIT_INSTALL` | Intermediate exact-head sync first |
| 2 | S2.5 | Running attestation, watchdog-last recovery, observer/dead-man and rollback | PROGRAM | S2.4 | PM -> OPS/E3 -> E4 -> QA -> PM | SOURCE_READY | **`SOURCE_READY`** (WP5 tranche 1/1b/2, PM declaration 2026-07-28, PR #148 merge `dab875882` + PR #150 merge `6be29043c`): five closed s2_5 schemas + the replay-ledger schema, additive v3 classifier (frozen digests unchanged), lifecycle/attestation/driver leaves + CLI, three-state lifecycle fixtures, hold-style lock across the consume→persist window, §6 closure binding; effect route unchanged and still gated — `S2.5A/S2.5B@EFFECT_DONE` need fresh operator permits per the S2 operator action packet | `WATCHDOG_ROLLBACK_TEST` | Platform-attested; no CI without source change |
| 3 | S3.1A | LR3 durable queue/controller/worker source implementation | PROGRAM | S2.3 | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | PLANNED | queue source receipt | classifier-derived PG/service source | Migration/ACL/runtime CI; exits SOURCE_READY |
| 3 | S3.1B | LR3 runtime queue/controller/worker verification | PROGRAM | S2.5, S3.1A@SOURCE_READY | PM -> independent OPS/E4 -> QA -> PM | PLANNED | `queue_recovery_receipt_v1` | `REMOTE_READONLY` | Only row that issues LR3 runtime DONE |
| 3 | S3.2 | LR4 loss-aware Scanner gap/drop-SLO handoff | landing_scope_id instance | S2.5, S3.1B | PM -> PA -> E1 -> E2 -> E4 -> QC/OPS -> QA -> PM | PLANNED | loss-aware Scanner receipt | classifier-derived engine deploy | Rust CI if Scanner changes |
| 3 | S3.2A | Pre-filter universe/PIT/reason/choice/policy/RNG/propensity persistence | landing_scope_id instance | S3.2 | PM -> QC/MIT -> E1 -> E2 -> E4 -> QA -> PM | PLANNED | universe/selection receipt | classifier-derived PG/engine effect | Rust/migration CI as classified |
| 3 | S3.3 | LR5 physical retention/backpressure/deleter/restore | PROGRAM | S2.5, S3.1B | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | PLANNED | retention apply/per-object receipts | `RETENTION_APPLY_RESTORE` | Destructive fixtures before apply |
| 3 | S3.4 | LR6 faults, independent observer and 72h/two-cycle soak | landing_scope_id instance | S3.1B, S3.2, S3.2A, S3.3 | PM -> distinct OPS observer -> E4 -> QA -> PM | PLANNED | `foundation_ready_receipt_v1` | `FAULT_INJECTION_OBSERVE` | Platform-attested; no CI without change |

尚未開始的 S4-S8 template rows(全部 PLANNED,零 receipt/狀態;normative session map=protocol §6)已遷 `PROGRESS-archive-1.md`;PM 開 S4 前**必先遷回本 active ledger 再實例化**——archive 檔凍結,不得就地實例化或承載任何 live 狀態。

## Ledger Events

| Time | Session | Event | Evidence |
|---|---|---|---|
| 2026-08-06 | S2E-LW1 round-4 review | **Fourth round of three independent reviews (E2 / E3 / E4-verifier): all three returned FAIL; fixed, then released for PR.** Both P1 were introduced by this branch and missed by all three earlier rounds. **R4-1 (E3, independently reproduced by E2):** `git_argv` carried a command-domain `-c safe.directory=<repo>`, added in round 3 so a root-owned producer could read an ncyu-owned repo instead of dying on dubious ownership — and its own honesty note claimed the family runs no config key that executes a program. Both clauses false: the family runs `git status` in fifteen places and `core.fsmonitor` executes. Measured on git 2.50.1 (status and diff fire, log/show/rev-parse do not); E2's PoC needs no uid trick at all, only `--repo-root` pointed at a repo the attacker prepared. The flag is removed rather than patched, because a per-key denylist does not converge — `filter.<drv>.clean` reaches the same place through `.gitattributes`. Git's own refusal returns, and `check=True` makes it a typed refusal rather than a silent pass; the differing-uid topology is unblocked by the operator writing the path into root's own protected config, where the repo owner cannot write. **F-1 (E4):** the branch left `SCHEMA_FILES == 93` against a real 94 while both round-3 commits reported "Five S2E files: 127 passed" — the red test is not one of the five. E2 asked whether more existed outside that selection; widening to fourteen files found two more and a repo-wide grep found a third that was in neither set. **Four assertions, one number, and a green that only ever covered what the author chose to run.** Five P2 closed: the 2-of-2 docstring claiming the spec's rollback clauses hold structurally (host root can rewrite the replica trust root and needs no second machine — the design master says so, the docstring did not); an operator prompt naming a pre-Tier-1 `attestor_class` and one field set for four profiles when two take ten fields; `patternProperties` compiling outside the single ECMA-faithful entry point; the design master's prerequisite arithmetic wrong a second time (`11 path + 4 service = 16`); and an observations docstring calling serialization a programmatic consumer for one slot while honestly denying it for the other slot in the same dict. **Carried explicitly, not silently a third time:** the action packet still lists `COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR` after `fdf3c0fa6` committed that floor, invisible to every test because `EXPECTED_ACTION_IDS` is static; and `447e5bad7..acca2095f` is a red bisect window. **Not erased by the FAIL:** E2 killed 17 of 17 mutations (re-running every narrow survivor wider), E4 killed 8 of 8, E3 verified by construction that E3-A is closed, that a forged `refs/remotes/origin/main` does not rescue an orphan floor, that `UNVERIFIED` is unreachable-to-upgrade, and that the 9,156-line diff carries no secret. All three independently confirmed that no source, docstring, design or TODO sentence overstates P0-1 — the first round in this chain where the honesty surface had no hole. | review record `2026-08-06--s2e_tier1_round4_review.md`; `aiml_gate_receipt_schema_core.py:452-476`; four `SCHEMA_FILES` sites; authority 0/9, effect 0/6 |
| 2026-08-04 | S2E-LW1 round-3 closure | **Third round (E2 / E3) raised nine findings; all nine closed in source.** Recorded here because the round previously existed only inside commit messages, which is not a ledger. E3-A was a real RCE: ambient `PATH` inheritance let a hostile `git` first on the path fabricate a `VERIFIED` verdict without the repo even existing; `git_executable()` now resolves only inside a code-owned search path with an absolute `argv[0]`, and the env allowlist is `("TZ",)`. Also closed: `<git-common-dir>/info/grafts` (E1 measured E2's construction right and E3's wrong — E2's form flips a rolled-back repo from REJECTED to `VERIFIED gen=1`), the history cap 32 → 256 with the derivation written above the constant, `timeout=` on every git call after a promisor clone turned a "pure verification function" into an unbounded network fetch, `fullmatch` + `\Z` because `$` admits a trailing newline and the value did reach argv, `safe.directory` (which round 4 then removed — see above), per-file host-key degradation after a UTF-8 comment silently dropped a fingerprint while the status still claimed observation, and the module docstring's externality assertion, rewritten rather than patched. **E3-B was closed in `6f563c299` and then falsely recorded as open**: PM ran a case-sensitive `grep` for "verdict" that could not match `FloorVerdictObservation`, turned the zero hit into a claim of unfinished work, and wrote it into a commit message and then into `TODO.md`. E1 refused the resulting no-op, found the gap that was genuinely open — `issue_s2e_launch_receipt` called three floor-reading validators and passed observations to none — and wired all three. **Recording a finished item as unfinished is the same failure this chain has been fighting, pointed the other way.** Both of PM's form suggestions in that round were refused by E1 with reasons that check out. | `6f563c299`, `c720a3718`, `5d32b1f19`, `8d070334e`; `aiml_gate_receipt_s2e_anchor_floor.py`; five S2E files 127 passed |
| 2026-08-03 | S2E-LW1 remediation P1 batch | **Five of six P1 closed in source; the sixth is now honest rather than falsely closed.** The floor reader returns a typed verdict, so a non-VERIFIED reading can no longer carry an empty error list — that was the 0-byte fail-open's exact shape. `at_commit` is hex-validated before reaching git and every call takes `--end-of-options`, after PM measured `--output=` truncating an existing file to zero bytes; all twelve subprocess sites in the family now pass an env allowlist, since ambient `GIT_DIR` overrode `-C` and on the consumption module would have redirected the single-use ledger; the history sentinel is `None` with dedupe after shape parsing; a floor history must start at `GENESIS_ARMED`, and the fixture that had frozen that hole as normal behaviour is corrected; shallow clones and replace refs are rejected. **On P0-1 the operator ruled to accept `UNVERIFIED` as the honest terminal state.** The protected-ref binding is in and is a module-level constant with no injection path, but PM measured one `git update-ref` turning `UNVERIFIED` back into `VERIFIED` at generation 4242 — `refs/remotes/origin/main` is a *local* ref, and whoever can write `.git` is precisely the single writer §LW1 names. The binding is kept because it catches accident and drift (unmerged, unfetched, wrong commit, CI shallow checkout) rather than because it closes the finding, and §LW1 itself prescribes `UNVERIFIED` for this case. Real externality needs a verifier that does not share a uid with the attacked host — the same direction as the NAS replica key, and unscheduled. E1 disclosed two surviving mutations rather than hiding them, and established that M14 needed no source change, only the missing test. Five S2E files 114 passed, PM-rerun. | `aiml_gate_receipt_s2e_anchor_floor.py`; design `S2E-LW1-tier1-remediation.md` 演變軌跡; authority 0/9, effect 0/6 |
| 2026-08-03 | S2E-LW1 remediation review | **Second round of three independent reviews: E2 FAIL, E3 FAIL, E4 PASS-with-must-dos — overall FAIL.** The load-bearing claim did not survive: nothing in code binds the anchor floor to a protected ref. `at_commit` comes from the receipt under validation and `repo_root` from a CLI flag, so an attacker needs neither GitHub nor a history rewrite — a local branch off the real genesis commit, carrying a self-made floor, returns zero errors. E2 and E3 proved this independently. §LW1's "same writer coherent rewrite may only yield UNVERIFIED" therefore still fails on the code line, and PM's earlier "structurally unreachable" wording is retracted as unsupported. Five further P1: `at_commit` reaches git before `--` with no hex validation, which PM measured **truncating an existing file to zero bytes**, not merely creating one; a committed 0-byte floor is a zero-error fail-open because the dedupe `continue` precedes the shape check with `last_raw` initialised to `b""`; the floor history need not begin at `GENESIS_ARMED`, a hole a current fixture has already frozen as normal behaviour; a shallow clone reduces the whole history check to a no-op; and ambient `GIT_DIR` overrides `-C` because no call passes `env=`. **Genuinely closed and not erased by the verdict:** the replica second signature (signing it with the anchor key is now typed-rejected both ways), the carrier and review anchor bindings that ran naked last round (10 mutations killed), the renamed predicate, the replica freshness floor, `--full-history` with real test backing, and the `require_current_freshness` exemption, which E4 confirmed precise — its single `False` call site covers only artifacts an issued receipt has pinned. Zero date-rot findings; line counts 1991/1983/418 all reconfirmed. **PM correction:** the manifest bound rationale was wrong — baseline was 254 with two slots free, not exactly full at 256; this branch's three new governed files consumed them and overran by one. Corrected in place and the bound narrowed 288 → 264. | review record `2026-08-03--s2e_tier1_remediation_review_fail.md`; `aiml_gate_receipt_s2e_anchor_floor.py:60,122-132,146,167-176`; `aiml_gate_receipt_s2e_launch.py:942-947,1600-1602` |
| 2026-08-03 | S2E-LW1 Tier 1 remediation landed | **Remediation source is landed branch-local; five S2E suites at 100 passed.** The committed anchor floor is in at `GENESIS_ARMED` generation zero, read by the validator from commit bytes. **The claim that this makes git the external monotonic layer §LW1 demands did not survive review** — see the 2026-08-03 remediation-review row. The replica now carries its own signer, trust root, digest and freshness window, with the private key assigned to `ncyu-nas`, intended to make the same-writer coherent rewrite structurally unreachable — a claim the 2026-08-03 review then falsified, since nothing in code binds the floor to a protected ref. The three `const: true` readback flags are deleted, host fingerprints must differ, and the 600s hot-handoff defect is closed by `require_current_freshness` — window-length bounds stay unconditional and only the "now falls inside the window" predicate is exempted, only for artifacts an issued receipt has already pinned. Prerequisites are 14 → 16 (12 paths + 4 services); packet digest `sha256:b28d49fe…a9cdf` at checkpoint `970734ae0`. E1 corrected two design errors rather than following them: the prerequisite arithmetic, and the floor history walk needing `--full-history` because git's default simplification can hide a regressed floor merged from a side branch. **Explicitly not done:** the remediation has had no adversarial review — it must run before any PR; the W5 re-emission cannot run yet because `w5-emit` requires `--test-evidence` and `--review-provenance`, so it follows the review and must also settle `209793b70`'s unpaid emission; the provisioning prompt still says 10 keys where it should say 11; and the three root-owned producers remain unwritten while `ncyu-nas` has no SSH listener, so no receipt can be emitted regardless. **Named for review:** PM raised the review-manifest cost guard and stated the bound was already exactly full at 256. **That was wrong** — E2 and E4 independently measured the baseline at 254 with two slots free, which this branch's three new governed files consumed and overran by one. Corrected to 254 → 257 with the bound at 264. | branch `agent/aiml-s2e-tier1-durability-anchor-20260802`, 18 commits, unpushed; `aiml_gate_receipt_s2e_anchor_floor.py`; `receipts/S2E-LW1-LW5/durability-anchor-floor-v1.json` |
| 2026-08-03 | S2E-LW1 Tier 1 remediation | **Operator ruled: fix it to be genuinely spec-compliant, not retreat to Tier 0.** Four decisions: (1) remediate rather than revert; (2) the replica's second signature goes on a genuinely separate machine — `ncyu-nas` — with trade-core root never holding its private key, which turns §LW1's "a single signature cannot prevent rollback" from a written assumption into a structural fact; (3) the 600s hot-handoff latent P1 that PA surfaced is fixed in this round; (4) the `BLOCKED_EXTERNAL_PREREQUISITES_*` token stays unrenamed and remains a named drift. PA's design master is `design/S2E-LW1-tier1-remediation.md`, built on two load-bearing pieces: a code-owned anchor floor the validator itself reads from git by commit bytes (PA correctly corrected the earlier PM/E3 framing — data merely *being* in git means nothing to a validator whose three transition-gate inputs are all caller-supplied file paths), and a real 2-of-2 replica signature. **PM-measured infrastructure facts (read-only):** `ncyu-nas` (100.77.15.17, linux) exists on the tailnet; trade-core has **no NAS mount at all** (empty fstab, no nfs/cifs client mounts, only the kernel's `nfsd on /proc/fs/nfsd`); `trade-core → ncyu-nas:22` is **Connection refused** — host up, network fine, no SSH listener. That adds a named provisioning prerequisite (a runnable signing path on `ncyu-nas`) in the same class as the three unimplemented root-owned producers: it does not block source work, it blocks receipt emission. Also verified: `aiml_gate_receipt_validator.py` is 1986 lines against the 2000 threshold that `aiml_gate_receipt_s2e_review.py:571` measures and raises on, leaving ~14 lines of headroom. | `design/S2E-LW1-tier1-remediation.md`; review record `2026-08-03--s2e_tier1_adversarial_review_fail.md`; `aiml_gate_receipt_s2e_launch.py:626,868,1358-1372,1478-1492` |
| 2026-08-03 | S2E-LW1 Tier 1 review | **Three independent adversarial reviews (E2 / E3 / E4-verifier) all returned FAIL; PM re-verified each finding against source and spec.** The decisive one: the implementation violates the very §LW1 sentence cited to authorize it. The spec's second disjunct requires an **external** monotonic counter/append-only head, states plainly that **a single signature cannot prevent rollback**, and rules that a same-writer coherent rewrite may only yield `UNVERIFIED`. The implementation is host-local, single-signature, and same-writer — all three violated verbatim, with independent PoCs from two reviewers returning `errors == []` for a truncate-and-rebind and for a fabricated `gen=999` with a never-existed previous head. (`TODO.md`'s abbreviated projection of the spec had dropped the word "external"; that is the likely source of the misreading.) Four P1: monotonic continuity checks only null-vs-non-null shape with no persisted head; the off-host readback flags are `const: true` in schema and self-signed by the anchor key, so the distinct-actor requirement that Tier 0 and `.codex/agent_registry_v1.json` both state verbatim has no replacement; "off-host" has zero enforcement (`replica:offhost-append-only:localhost` passes); and the entire new carrier/review anchor-binding enforcement can be disabled with all 72 tests staying green (found independently by E2 and E4). Six P2 including a signed governance predicate that literally asserts `EXTERNAL_WORM_IMMUTABLE_READBACK_VALID` when no external WORM participates. **Confirmed sound and not erased by the FAIL:** trust-root TOCTOU hardening, SSHSIG domain separation, per-item digest recomputation, no secret/SQL/subprocess/argv exposure, no coverage net loss from the three-part removal, and every verifiable number in the delivery report — including the headroom red-herring's byte-neutrality, independently reproduced at baseline. **No PR until the §六 remediation lands.** | review record `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-03--s2e_tier1_adversarial_review_fail.md`; spec `design/S2E-launch-wave-specs.md` §LW1; `aiml_gate_receipt_s2e_external_evidence.py:473-498`; `aiml_gate_receipt_s2e_launch.py:1159-1174,1478-1492` |
| 2026-08-02 | S2E-LW1 Tier 1 | **Durability anchor replaces external WORM custody; operator packet rebound.** Operator ratified Tier 1, so the LW1 receipt chain now uses `TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1` — the second branch of the §LW1 anchor disjunction that the carrier schema already declared — instead of three distinct-custody paid external services. The five load-bearing semantics are unchanged (distinct key custody, monotonic generation/previous-head continuity, entry/head digest recomputation, ≤10 min freshness, proven immutable readback); what is dropped is paid custody and irreversible COMPLIANCE retention, with durability carried by an off-host replica that must read back the exact anchor head. Negative coverage rose 9 → 26 cases. **Correction to the downgrade proposal:** blockers stay at **14**, not 11 — composition changed (paid external custody 3 → 0, unimplemented root-owned capabilities 1 → 3), so Tier 1 costs more development, not less. The committed operator packet was still the Tier 0 artifact and **failed this branch's own validator** (3 errors); no test binds the artifact to its generator, so CI could not catch it. Rebuilt from a fresh read-only observation; validator now PASS. **Not done:** the three root-owned producer capabilities (`attest-v2`, durability anchor, predecessor registry) are unimplemented, so W0/LW1 receipts still cannot be emitted; no independent E2/E4 adversarial review has run; branch is unpushed with no PR. The `BLOCKED_EXTERNAL_PREREQUISITES_*` state token and `next_action` string still say "EXTERNAL" although no external prerequisite remains — recorded as operator adjudication, not silently renamed. | implementation checkpoint `0253814b0` (branch-local); packet `sha256:d4ad8ede…de367`; focused suites `72 passed` (26/23/10/13) and packet suite `13 passed` re-run after rebind; Linux read-only observation 2026-08-02T22:13:32Z |
| 2026-08-02 | G0 / S2E-LW1 | **Source checkpoint complete; true LW1 exit external-blocked.** G0 is `SOURCE_COMPLETE_RUNTIME_INDETERMINATE`. LW1 source closes dispatch/clock, fixed host capture, independent WORM/provider/registry evidence, consume-once registry and action-packet contracts. Fail-first recovery found raw-command gaps; Codex reviews then found 3 P1＋3 P2. The last P1 invalidated the earlier full-worktree-clean defense: project modules were already imported before Git status/head, so same-UID code could restore bytes before signing. `e68966670` removes that claim path: the producer authors no source/host/process/clock facts and submits no signing payload; the sole kernel exec invokes a zero-input root-owned `attest-v2` capability which must derive the complete SSHSIG artifact from an immutable source view. Focused host-capture/action-packet `48 passed`, host kernel `211 passed, 9 skipped`, and S2E/recovery adjacent `416 passed, 9 skipped`. Linux read-only evidence still shows 11 fixed paths absent and three external services `NOT_OBSERVED`; W0/LW1 receipts remain absent, LW2 locked, authority 0/9, production effect 0/6. | implementation checkpoint `e68966670`; packet `sha256:c13142b4…d5809`; PM report `2026-08-02--g0_s2e_lw1_checkpoint_and_blocker.md` |
| 2026-08-01 | LEDGER | **Ledger generation split (framework-health P1-6; docs-only, zero status change)** — closed-generation sections (masthead narrative, Amendment A2 full text, S0/S1 session rows, ledger events 2026-07-20→2026-07-29, S0.3 finalization, S0.3 accepted coverage debt) moved verbatim to `PROGRESS-archive-1.md`. The machine-pinned sections (`W5-RECEIPT-BINDING` marker, S2.4 unclosed owned obligations, W5 PM-owned adjudication) stay in this file. Information-conserving move; no row status, receipt, digest or authority changed. | this commit + `PROGRESS-archive-1.md` |
| 2026-07-29 | S2E W0 handoff | **Current projection frozen before W1:** nine readiness packages are 5/9 source-landed (`S2E.0`, `S2E.1`, `S2E.2a`, `S2E.2b-1`, `S2E.3`); the only ACTIVE entry is `S2E.2b-2`, followed strictly by `S2E.2b-3 → S2E.4 → S2E.5`. Production effect stays 0/6; S2 remains open and the packet remains `DRAFT_NOT_EXECUTABLE`. `S2E.2b-2` now owns the full S2.5 runner/recovery/anchor/penetration/nonce/2004-line exit; `S2E.4` owns runtime capture, closure schema, actor/verifier identity and trusted-attestor source repair plus explicit adjudication of the 2231-line effect-binding test; `S2E.5` owns the forgery-negative full-DAG proof, 28-obligation closure, and CodeQL #95 fix/evidence adjudication before any terminal packet. S2.0 EFFECT operator prerequisites are pinned in the packet: lazy GRANT strictly between adapter steps 7/8, dedicated login `NOSUPERUSER`, post-window REVOKE, and out-of-band `credential_escalation_connect`. This event changes governance projection only: no source contract/schema/test/runtime/receipt, no W5 re-emission, no deploy/restart/PG/broker/order mutation. | W0 intake baseline `83dc0ec3017e541e156e557c2e2d16f1704682a3`; TODO v861 / ledger v16 / packet handoff calibration |

舊世代 events(2026-07-20 → 2026-07-29 其餘各列)全文=`PROGRESS-archive-1.md`。

## S2.4 (WP4) unclosed owned obligations

**Generated, not maintained by hand.** The single source of truth is
`aiml_gate_receipt_wave_w5._W5_EXPORTED_ABI["remaining_owned_obligations"]`
(pure data in `program_code/ml_training/aiml_gate_receipt_w5_obligations.py`), and
`tests/structure/test_agent_governance_s2_4_install_w5.py` fails if this table and that
list disagree by a single `obligation_id`. Regenerate rather than edit:

```text
python3 -c "import sys;sys.path[:0]=['program_code/ml_training','program_code'];\
import aiml_gate_receipt_validator as v;\
[print(r['obligation_id'], r['typed_status'], r['owner_wave']) \
 for r in v._W5_EXPORTED_ABI['remaining_owned_obligations']]"
```

At the current W5 generation (source head
`f30ede36134f1464cef4bc025f808b931aebe180`, round-9 receipt carrier
`3df9d2f451ceb7ab66117de6e33fd882d59a9531`, ledger digest
`sha256:90f9261845b4782e577ef34e40369b3bcaf30381ce46d62d7246c087b3ed208e`)
every row below remains on the 28-row ledger; five rows now carry a
`CLOSED_BY_*` typed status (row 22 by S2.5 source under the PM O-1 ruling, and
rows 16/23/26 by `S2.4-AMEND-1` plus row 25 by `S2.4-AMEND-2`, both landed as
source in S2E.0), and the remaining rows are unclosed with their named owners.
Review history per generation: what was independently reviewed at the merged head `756a59ef7` (GitHub main
`427bd0dd7`, same tree), by two reviewers, is the round-3 remediation, the W5 emitter
(`agent_governance_s2_4_w5_emit.py` + the `w5-emit` CLI verb), the §10.1.2 owned-path
amendment, and the eight then-persisted W5 artifacts — none of which had been reviewed
before. Round 3's own head `a757c006f` was **never** reviewed by anyone; an earlier
version of this sentence named it as the reviewed head, which is the claim class §11.2
predicate 4 exists to check. That round returned 3 P1 plus six P2 (remediated as
`c2a7263ce`). Round 5 (reviewing `25d501366`) returned 1 P1 + 2 P2, remediated as
`aaee7f1a2` with the receipts re-emitted at that head and committed as `456bd0c20`.
The round-6 PM audit (at `456bd0c20`) reproduced one remaining P1 — the active-state
projection in `TODO.md` and this file still described the `c2a7263ce` generation and a
stale PM-owner projection — closed by the commit carrying this sentence together with
the discriminator regression
`tests/structure/test_aiml_w5_receipt_binding_projection.py`.

`owner_wave` names who must close it; `PM` rows are design decisions §10.4 forbids a
worker from taking. Full statements are in the W5 derivation record
(`receipts/S2.4-WP4-W5/S2.4-WP4-W5-derivation-record.json`, emitted by PM) under
`remaining_owned_obligations`, pinned by `obligation_ledger_digest`. An earlier
hand-maintained projection carried 13 of these rows; that is the drift this generated
section exists to prevent.

**The persisted receipt set in this tree is bound to `651bd4e38` — the Tier 1
durability anchor branch after four rounds of adversarial review — and was committed
one commit later, as `f4d94d7ec` (round 11).**
Round 10 (bound to `8644c5f00`, carried by `6146f8572`) is superseded one commit
after it landed: its embedded evidence prose quoted the very number the
file-line-policy scanner forbids while describing the violation it had just fixed,
so the artifact tripped that scanner. The derivation was sound; only the prose was
not, and receipt bytes cannot be hand-edited.
Round 10 exists because `209793b70` changed three W5-owned paths
(`aiml_gate_receipt_schema_core.py`, `aiml_gate_receipt_validator.py`,
`application_bundle_runtime_closure_v1.json`) and emitted nothing, so the round-9
artifacts spent that whole branch describing a head it no longer was; PA found the
debt, three review rounds had not. Round 9 was bound to `f30ede361` (the S2E.0 final
head: S2.4-AMEND-1/2 chain `223a479d7`→`e9b26e895`→`a48355a29`→`cc6a8b97a`, round-8
receipts `c911ea9c1`, projection `23037eb0b`, then the PR#153 Codex-review fixes)
and carried by `3df9d2f45`. *Bound to*
and *committed at* are different facts and the artifacts state the first: each of the
eight carries `source_head = 651bd4e38cef0e39545f6f8f378829800feea17f`. Read the
binding out of the artifact field, never out of this paragraph; the discriminator regression
`tests/structure/test_aiml_w5_receipt_binding_projection.py` mechanically requires one
unique `source_head` across all eight artifacts and requires every claim of that form in
`TODO.md` and this file to equal the artifacts' actual value. Superseded generations,
each replaced rather than edited: the set bound to `cc6a8b97a` (S2E.0 AMEND head,
committed as `c911ea9c1`, round 8, same ledger digest), before it the set bound to
`5be472193` (WP5-tranche-2 head,
committed as `0eb90e40c`, round 7, ledger digest `sha256:57696d69…53ea`), before it
the set bound to `0faa6499d` (WP5 tranche-1
ledger-closure head, committed as `0b06982e0`), before it the set bound to `aaee7f1a2`
(round-5 remediation head, committed as `456bd0c20`, ledger digest
`sha256:fe3558a3…ca97`), before it the
set bound to `c2a7263ce` (round-4 remediation head, committed as `25d501366`), and
before it the set bound to `fcc44eca7` (committed as `756a59ef7`, ledger digest
`sha256:4548d526…e5af` — what stood here once called that set "bound to `756a59ef7`",
which was only the commit it landed in). The current `obligation_ledger_digest` is
`sha256:90f9261845b4782e577ef34e40369b3bcaf30381ce46d62d7246c087b3ed208e`, equal to the
live ABI digest at this head after the S2E.0 ledger change (rows 16/23/26 →
`CLOSED_BY_S2_4_AMEND_1_SOURCE`, row 25 → `CLOSED_BY_S2_4_AMEND_2_SOURCE`; rows kept,
owner unchanged, statements appended not rewritten, mirroring the O-1 precedent).
`persisted_dir` is repo-relative and `remaining_owned_obligation_count=28`.
The standing rule: a receipt is re-emitted after the last owned-path change of a round,
at the head that carries it. Round 5 edited a W5-owned test path, so PM re-emitted at
`aaee7f1a2`; WP5 tranche 1 edited `aiml_gate_receipt_w5_obligations.py` (W5-owned, at
`7e2c2c490`), so PM re-emitted at the tranche head `0faa6499d`; WP5 tranche 2 edited
the four W5-owned central-registration files (SCHEMA_FILES 78→79, the facade delegate
branch, the runtime-closure reseal and the count pin), so PM re-emitted at `5be472193`
(round 7); S2E.0 edited `aiml_gate_receipt_w5_obligations.py` and `…wave_w5.py`
(W5-owned) inside its atomic commit 3, so PM re-emitted at `cc6a8b97a` (round 8), and
after the PR#153 Codex-review fixes touched further owned paths PM re-emitted at the
round's final head `f30ede361` (round 9) — the emitter enforces the rule mechanically rather than in prose
(`W5_EMIT_REFUSED` on a dirty owned scope with zero files written;
`W5_RECEIPTS_EMITTED` on the clean committed head). Round 8 changed the ledger digest
(four typed-status flips); round 9 re-binds owned-path blobs only (ledger unchanged).

W5-RECEIPT-BINDING: source_head=651bd4e38cef0e39545f6f8f378829800feea17f carrier_commit=f4d94d7ecbeef8139d08b564f81253a0d60e93c2 artifacts=8 round=11 status=COMMITTED

| # | `obligation_id` | `typed_status` | `owner_wave` | Spec refs |
|---|---|---|---|---|
| 1 | `ENCRYPTED_BLOB_DIGEST_ORDERING` | `OPEN_DESIGN_QUESTION` | `W6` | `§5.1`, `§7` |
| 2 | `OBSERVER_SPACE_PRE_STATE_DIGEST` | `PARTIALLY_PROVIDED_BY_W4B` | `W6B` | `§5.2`, `§5.4`, `§6` |
| 3 | `PRIOR_LINEAGE_ENTRY_IDENTITY` | `NOT_PROVIDED_BY_W5` | `W6B` | `§5.1`, `§9.1` |
| 4 | `PLAN_EXPIRY_OUTSIDE_SIGNED_CORE` | `PARTIALLY_PROVIDED_BY_W4B` | `W6B` | `§9`, `§9.2`, `§10.4`, `§10.5 #28` |
| 5 | `INSTALLED_UNIT_PROBE_CORE_BINDING` | `PARTIALLY_PROVIDED_BY_W4B` | `W6B` | `§6`, `§10.4`, `§10.5 #36` |
| 6 | `EFFECT_RECEIPT_RECONCILE_BINDING` | `PARTIALLY_PROVIDED_BY_W4B` | `W6B` | `§5.2`, `§10.4` |
| 7 | `STARTUP_RECONCILE_SURFACE_ABSENT` | `OPEN_BY_DESIGN_W6_RUNNER_PRECONDITION` | `W6` | `§5.2`, `§10.5 #39` |
| 8 | `STARTUP_JOURNAL_PARENTS_MUST_PREEXIST` | `NOT_PROVIDED_BY_W5` | `W6B` | `§5.2` |
| 9 | `RECEIPT_EMISSION_PENDING_IS_NOT_A_RECEIPT_RETRY` | `PARTIALLY_PROVIDED_BY_W4B` | `W6B` | `§10.5 #8`, `§10.5 #14` |
| 10 | `STRANDED_WAL_TEMP_FILES_ARE_REPORT_ONLY` | `PARTIALLY_PROVIDED_BY_W4B` | `W6B` | `§5.2` |
| 11 | `ATTESTATION_EXPIRY_AND_HOST_TIME_ARE_NOT_CROSS_CHECKED` | `NOT_PROVIDED_BY_W5` | `W6B` | `§9.1`, `§10.2` |
| 12 | `ATTESTED_EVIDENCE_CLASS_VERIFIER` | `VERIFIER_PROVIDED_BY_W4B_ATTESTATION_PENDING` | `W6B` | `§6`, `§9.1`, `§10.2`, `§10.5 #13`, `§10.5 #14` |
| 13 | `ATTESTOR_KEY_IS_NOT_SEPARATE_FROM_THE_PERMIT_KEY` | `NOT_PROVIDED_BY_W5` | `W6B` | `§9.1`, `§10.2` |
| 14 | `REPLAY_LEDGER_CONSUME_ONCE_IS_A_FILESYSTEM_PROPERTY` | `OPEN_HONEST_BOUNDARY` | `W6B` | `§9.1`, `§10.5 #8` |
| 15 | `STARTUP_RECONCILE_LANE_PATHS` | `NOT_PROVIDED_BY_W5` | `W6B` | `§5.2` |
| 16 | `DEPENDENCY_REFRESH_RECEIPT_BINDING_ABSENT` | `CLOSED_BY_S2_4_AMEND_1_SOURCE` | `PM` | `§3`, `§10.4`, `§11.3` |
| 17 | `DEPENDENCY_REFRESH_REPRODUCER_NODE_IS_DECLARATIVE` | `PARTIALLY_PROVIDED_BY_W5` | `W6` | `§9.1`, `§9.2` |
| 18 | `DEPENDENCY_OBSERVATION_WINDOW_IS_CALLER_AUTHORED` | `PARTIALLY_PROVIDED_BY_W5` | `W6` | `§9.2`, `§10.5 #28` |
| 19 | `ENCODED_SECRET_SCAN_MISSES_COMPOSITE_PAYLOADS` | `RECORDED_NOT_CLOSED` | `W6B` | `§10.5 #15` |
| 20 | `PROGRAM_CODE_IS_ON_THE_SCANNER_PATH_VIA_W2_W3_AND_W4` | `PROVIDED_BY_W5_UNDER_PM_RULING` | `W5` | `§10.1.1` |
| 21 | `PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED` | `NOT_PROVIDED_BY_W5` | `W6B` | `§7`, `§10.5 #26` |
| 22 | `S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST` | `CLOSED_BY_S2_5_SOURCE` | `S2.5A` | `§10.5 #29`, `§11.3` |
| 23 | `SOURCE_IDENTITY_FRESHNESS_HAS_NO_PRODUCTION_CALL_SITE` | `CLOSED_BY_S2_4_AMEND_1_SOURCE` | `PM` | `§8`, `§9.2`, `§10.1.1`, `§10.4`, `§10.5 #28` |
| 24 | `EMITTED_EVIDENCE_DIGESTS_ARE_UNAUTHENTICATED` | `RECORDED_NOT_CLOSED` | `PM` | `§10.3`, `§10.5 #27`, `§11.3` |
| 25 | `EXPECTED_TOPOLOGY_IS_CALLER_SUPPLIED_AND_UNSIGNED` | `CLOSED_BY_S2_4_AMEND_2_SOURCE` | `PM` | `§8.2`, `§10.1.1`, `§10.2`, `§10.4`, `§10.5 #25` |
| 26 | `EVIDENCE_CLASS_TO_SCHEMA_MAP_IS_MANY_TO_ONE` | `CLOSED_BY_S2_4_AMEND_1_SOURCE` | `PM` | `§9.1`, `§9.2`, `§10.5 #28` |
| 27 | `S1_3_ASSURANCE_CLASS_IS_INFLATABLE_WITHOUT_CHANGING_THE_PROJECTION` | `RECORDED_NOT_CLOSED` | `S1.3` | `§9.2`, `§10.1.1` |
| 28 | `OWNED_PATH_PROJECTION_RULER_IS_NOT_UNIFORM` | `RECORDED_NOT_ABSORBED` | `PM` | `§10.3` |

## W5 PM-owned obligations adjudication (2026-07-28)

PM adjudication of every `owner_wave=PM` row in the live ABI (six rows; the set below
is pinned set-equal to the ABI by
`tests/structure/test_aiml_w5_receipt_binding_projection.py`, so a PM row added to or
removed from the ABI without a matching adjudication row is red). Each row is classified
`source_closure_blocker` (blocks `S2.4@SOURCE_READY`), `accepted_carry_forward`
(accepted with its condition, closure owned by a named later lane), or
`separately_scheduled` (closed by a named PM amendment that gates `S2.4@EFFECT_DONE`,
not `SOURCE_READY`). W6/W6B/W5/S2.5A/S1.3-owned rows are deliberately **not**
adjudicated here — recording them for their owner is not closure, and W5 is not asked to
solve rows outside its ownership.

<!-- W5-PM-OWNED-ADJUDICATION-BEGIN generated-from=_W5_EXPORTED_ABI -->
- `DEPENDENCY_REFRESH_RECEIPT_BINDING_ABSENT` → classification=separately_scheduled —
  folded into **S2.4-AMEND-1** (one PM decision: where the dependency refresh enters
  APPLY, plus the terminal `s2_4_install_effect_receipt_v1` fields for the §3 refresh
  digests, plus the §9.1 profile threading below). It gates `S2.4@EFFECT_DONE`: the
  shipped S2.2A/S2.3 dependency identities are genuinely expired, so the W6 apply run
  must admit them via §9.2 refresh, and without the receipt field a §3-conformant
  terminal receipt cannot be produced. It does not gate `SOURCE_READY`: the §9.2 gate
  source is complete and the missing field is an exported-schema amendment §10.4
  reserves to PM.
- `SOURCE_IDENTITY_FRESHNESS_HAS_NO_PRODUCTION_CALL_SITE` → classification=separately_scheduled —
  the same S2.4-AMEND-1 decision (the refresh ingress point *is* the missing production
  call site). Wiring it today would permanently break the W3 wave exit (the shipped
  receipts are expired and nothing can carry a refresh yet), so a half-wiring is
  refused; the two-way latch already fails the wave exit if the row is deleted while
  the zero-call-site fact holds or kept once a call site appears. Gates
  `S2.4@EFFECT_DONE` via S2.4-AMEND-1.
- `EMITTED_EVIDENCE_DIGESTS_ARE_UNAUTHENTICATED` → classification=accepted_carry_forward —
  structurally unclosable in the source lane (a packet-local artifact cannot
  authenticate its own execution; CLAUDE.md's three evidence tiers). Acceptance
  condition, already load-bearing in the gate text and `replay_note`: any
  `SOURCE_READY` declared from the chain licenses source structure at a head only, and
  every test number must cite a measured suite run. Closure belongs to the W6
  trusted-host lane where `ORCHESTRATOR_BOUND`/`PLATFORM_OR_EXTERNAL_ATTESTED`
  evidence exists.
- `EXPECTED_TOPOLOGY_IS_CALLER_SUPPLIED_AND_UNSIGNED` → classification=separately_scheduled —
  **S2.4-AMEND-2**: make `expected_topology` plan-derived (thread the signed
  `s2_4_pg_hba_delta_v1` and the plan core's `topology_pre_digest`/`hba_delta_digest`
  into the row, as the W5 prescription already names) instead of caller-supplied. It
  gates the `PG_ROLE_ACL_MIGRATION` step of `S2.4@EFFECT_DONE` — a different-cluster
  substitution via omitted baseline keys is a substitution of the subject and must not
  reach an effect run. It does not gate `SOURCE_READY`: omission of the whole object is
  already fail-closed (`PG_TOPOLOGY_UNPROVEN`) and the only weakening path is key
  omission by the caller, which in the source lane is a governed repo fixture.
- `EVIDENCE_CLASS_TO_SCHEMA_MAP_IS_MANY_TO_ONE` → classification=separately_scheduled —
  folded into **S2.4-AMEND-1** (threading the §9.1 profile/scope check into the
  class→artifact resolution is part of deciding where the permit set enters §9.2).
  Measured severity bound: all nine never-refreshable classes yield refusals under
  §9.2, the verdict has zero production consumers today, and the substitution can at
  most buy `SOURCE_DEPENDENCY_FRESH` for a wrong-profile permit — it authorizes
  nothing. Closes with S2.4-AMEND-1 before `S2.4@EFFECT_DONE`.
- `OWNED_PATH_PROJECTION_RULER_IS_NOT_UNIFORM` → classification=accepted_carry_forward —
  bounded residual: the content-addressed `owned_scope_worktree_delta` is already
  consumed fail-closed for W0..W5, so no receipt can be derived from a tree whose owned
  scope drifts from its bound commit; the remaining divergence is that W3/W4's own
  projections hash working-tree bytes. Unifying them edits W3/W4-owned paths — a PM
  path-scope call scheduled for the next wave that legitimately touches those files
  (W6 intake), not a W5 obligation and not a `SOURCE_READY` blocker.
<!-- W5-PM-OWNED-ADJUDICATION-END -->

**Closure update (2026-07-28, S2E.0):** the two `separately_scheduled` amendments have
landed as source at head `cc6a8b97a` — `S2.4-AMEND-1` closed rows 16/23/26 and
`S2.4-AMEND-2` closed row 25 (typed statuses `CLOSED_BY_S2_4_AMEND_1_SOURCE` /
`CLOSED_BY_S2_4_AMEND_2_SOURCE` in the live ABI; rows kept with owner `PM` and
appended closure notes, mirroring the O-1 precedent). The classifications recorded in
the generated block above are preserved as the adjudication history; the two
`accepted_carry_forward` rows (24/28) remain open with their named owners. The closure
licenses source structure only; `S2.4@EFFECT_DONE` still requires the S2E.1-S2E.5
chain and fresh operator authorization.

Net result: **0 source-closure blockers**. `S2.4-AMEND-1` (refresh ingress + terminal
receipt refresh-digest binding + §9.1 profile threading; closes rows 16/23/26) and
`S2.4-AMEND-2` (plan-derived `expected_topology`; closes row 25) are PM amendments that
must land before `S2.4@EFFECT_DONE` and are named preconditions of the operator action
packet; rows 24/28 are accepted carry-forwards with named owners. Gate ② of the
`S2.4@SOURCE_READY` exit conditions is therefore **ADJUDICATED**; the `SOURCE_READY`
declaration itself remains a post-merge PM projection after gates ①④⑤ are verified at
the merged head, and it licenses source structure only — nine authorities stay false and
no runtime/PG/unit/service/deploy/broker/order/live effect is granted by it.

## Archived sections

`S0.3 Trusted-Host Finalization (completed)` 與 `Accepted Coverage Debt
(S0.3 review, non-blocking)` 全文已遷 `PROGRESS-archive-1.md`(2026-08-01
世代切檔;debt 條目狀態不變,仍為 accepted/non-blocking)。
