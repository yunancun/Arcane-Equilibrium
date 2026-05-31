# 玄衡 TODO — Active Dispatch Queue

**版本** v100 ｜ **日期** 2026-06-01 ｜ **source HEAD** 089967b7 base + v100 AEG blocked-item resolution packet；runtime unchanged from latest v87 deploy snapshot.
**當前主線**：P0-EDGE-1 Alpha-Edge Regime Evidence Governance。AEG-S0 formal review PASS; AEG-S1 Foundation blocker packet landed. Safe next work is docs/design/read-only `AEG-S1-FND-1..4` plus `S2-GATE-B-PREP`. E1 backfill writer / DB retention mutation / endpoint ingestion / collector IMPL / alpha scoring remain blocked until separately scoped.
**v96 audit note**：V5.8 設計未被刪除；它作為長期 13-module autonomy architecture 保留，active TODO 只保留可派工 posture。詳見 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md`。
**歷史詳情**：version log `docs/CLAUDE_CHANGELOG.md`；v94 prune audit `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--todo_v94_prune_audit.md`；pre-cleanup archive `docs/archive/2026-05-31--todo_v93_pre_aeg_cleanup_archive.md`；older v92 archive `docs/archive/2026-05-31--todo_v92_archive.md`。

---

## §0 Runtime Snapshot

| Area | Current state | Next action |
|---|---|---|
| Source sync | Mac `main` is the active source branch; this v100 blocker-resolution packet is docs/governance only on top of `089967b7`. Linux fast-forward to the post-v100 docs commit is not verified in this batch. | Commit + push v100 docs/governance packet; no runtime sync unless operator requests it. |
| Runtime | Latest verified deploy remains v87 2026-05-31: Linux engine/API/watchdog healthy; engine PID 968350 in archived snapshot; healthz 200; no runtime rebuild in AEG governance/TODO batches. | No deploy in this batch. Refresh only before runtime-affecting work. |
| Runtime caveat | system-level `openclaw-engine.service` / system watchdog install still sudo/operator-gated; current protection is user watchdog + linger + manual engine process. | Operator schedules system-level install window. |
| Passive health residual | `[48] replay_manifest_registry_growth`, `[74] close_maker_reject_samples`, `[56] live_pipeline_active` remain OPS residual / evidence queue; not OPS-1 reversal. | Keep explicit in OPS queue; do not mark all-green until resolved or accepted. |
| Operator-gated ops | first restore drill, system-level units, live-auth renewal, Earn first stake remain hand actions. | Operator chooses low-risk window / auth timing. |

---

## §1 P0 Active Blockers

| ID | Status | Owner chain | Acceptance / Gate | Next action |
|---|---|---|---|---|
| `P0-EDGE-1` | 🔴 ACTIVE | PM -> PA/QC/MIT/BB -> E1 after gate | Closure requires accepted Alpha-Edge evidence: >=3 alpha-bearing candidates meeting net/cost/statistical gates, or another accepted P0-EDGE path. Bull-only/stale-only/survivor-only/narrative-only positives cannot promote. | Run `AEG-S1-FND-1..4` + `S2-GATE-B-PREP` docs/design/read-only; no backfill writer or scoring. |
| `P0-LG-3` | 🟡 SOURCE INTEGRATED / runtime not deployed | PM -> E2 -> E4 -> QA -> operator deploy gate | Review integrated commits `deb3f3af..0802d52b`; V104 checksum discipline; Linux migration dry-run/AUTO_MIGRATE plan; supervised_live tests green. | Run review chain before any deploy/rebuild. |
| `P0-OPS residual` | 🟢 OPS-1 CLOSED / residual OP-gated | Operator + PM/E1/MIT as needed | Restore drill, system-level units, live-auth renewal, replay manifest feed, close-maker max-pending evidence. | Wait for operator hand-action windows; keep residual rows visible below. |

---

## §2 Alpha-Edge Regime Evidence Program

**SSOT**:

- Governance: `docs/adr/0047-alpha-edge-regime-evidence-governance.md`
- Amendment: `docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md`
- Findings: `docs/audits/2026-05-31--alpha_edge_regime_evidence_governance_findings.md`
- Engineering arrangement: `docs/execution_plan/2026-05-31--alpha_edge_regime_evidence_engineering_arrangement.md`
- S1 unblock packet: `docs/execution_plan/2026-06-01--aeg_s1_foundation_unblock_packet.md`
- PM 2nd sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--alpha_edge_regime_evidence_pm_second_signoff.md`
- PM blocked-item verification: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-01--aeg_blocked_items_resolution_verification.md`

**Non-negotiable rules**:

- Bull data is allowed only when explicitly labeled.
- S4 is a global S1-Sx regime/falsification overlay, not a standalone 2024 bull proof.
- Bybit market APIs are raw market-state inputs, not prediction.
- Trend/regime labels must be local, leak-free, point-in-time, and fixed before alpha scoring.
- News/X/Reddit agents are secondary side evidence only; the promotion core remains mathematical.

**Current contract artifact**: `docs/execution_plan/2026-05-31--aeg_s0_contracts.md` covers AEG-S0-W0-S1..S4. PA/MIT/QC/BB/TW/CC re-review PASS; PM closure is `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--aeg_s0_formal_review_closure.md`. The vague blocked queue is now classified by `docs/execution_plan/2026-06-01--aeg_s1_foundation_unblock_packet.md`: design/read-only Foundation work can proceed; runtime/DB/backfill/scoring remains blocked.

### §2.1 CLOSED: AEG-S0 Contract Sprint

| Session | Owner chain | Output | Acceptance |
|---|---|---|---|
| `AEG-S0-W0-S1` Evidence Storage Contract | PM -> PA+MIT -> QC | PASS after re-review | Includes `run_id`, `git_sha`, `git_dirty`, child artifact digests, window, PIT universe, cost model, endpoint list, classifier version; excludes 14d `panel.*` as 18mo history. |
| `AEG-S0-W0-S2` Regime Classifier Freeze | PM -> QC+PA -> MIT | PASS after re-review | Rules fixed before alpha scoring; closed bars only; all features lagged / `shift(1)`; `durable-alpha` requires non-bull independent support. |
| `AEG-S0-W0-S3` Bybit Endpoint Contract | PM -> MIT+BB -> PA | PASS after re-review | Covers pagination, retention, rate limits, strict parser failures, public-only client isolation, and BB review for kline/funding/OI/long-short/mark-index-premium/ticker/orderbook/IV. |
| `AEG-S0-W0-S4` TODO Archive Plan | PM -> TW/CC -> PM | PASS after re-review | Active TODO keeps next actions; historical evidence stays in reports/archive. |

Formal review parallelism: 4 sessions can run together after operator/tool authorization; project ceiling remains 7.

### §2.2 NOW: AEG-S1 Foundation Blocker Resolution

Allowed now after AEG-S0 PASS + v100 blocker classification:

| ID | Owner chain | Allowed output |
|---|---|---|
| `AEG-S1-FND-1` | PM -> MIT+PA -> E2/E4 review prep | Storage/retention/provenance change-control package for `market.klines` 1095d vs research storage, plus funding/OI/long-short storage branch. |
| `AEG-S1-FND-2` | PM -> MIT -> PA | PIT universe builder contract using `market.symbol_universe_snapshots`; seed evidence is the 797-row survivorship CSV. |
| `AEG-S1-FND-3` | PM -> PA+QC | Side-evidence artifact contract; secondary-only and excluded from promotion gates. |
| `AEG-S1-FND-4` | PM -> BB+PA -> MIT | Public endpoint runner/client-gap + persistence map: kline, funding, OI, long-short, mark/index/premium price-only klines, ticker/orderbook, and `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` fix-vs-bypass design. |
| `S2-GATE-B-PREP` | PM -> BB+MIT -> QC | 24h isolated PreLaunch phase-transition probe plan and capture-only collector design. |

Still blocked until separately scoped and reviewed:

- Bybit historical backfill writer.
- `market.klines` retention/runtime PG mutation.
- funding/OI/long-short 18mo backfill.
- mark/index/premium kline client implementation.
- listing-capture collector IMPL.
- alpha scoring / promotion report.

Allowed work must remain docs/design/read-only unless PM opens a specific S1
implementation task with its own owner chain. Current verification result:
blocker classification is complete; implementation completion is false.

### §2.3 Preserved Foundations

AEG is not a replacement of the prior design. It integrates and constrains these existing foundations:

| Foundation | Use under AEG |
|---|---|
| `market.klines` + proposed/gated 1095d retention path | Primary OHLCV source only after safe retention/backfill gate; current V006 reality is 365d until reviewed mutation lands. |
| `market.symbol_universe_snapshots` | PIT survivorship control; current-survivor-only universe is rejected. |
| `market.funding_rates`, `market.open_interest`, `market.long_short_ratio` | Regime/side evidence inputs; retention/storage gaps must be solved before 18mo use. |
| `market.regime_snapshots`, `market.regime_transitions` | Prior regime storage lineage; AEG classifier must version and not tune on candidates. |
| `market.news_signals` | Side-evidence lineage only; excluded from promotion gates. |
| `AlphaSurface.regime` + `HurstHysteresis` | Existing local math components to assess for trend/state classifier reuse. |
| `panel.basis_panel` | Forward-only A1 basis input; historical basis remains limited until ticker/index persistence is fixed. |
| Sprint 2 / Alpha Tournament artifacts | Retained as evidence and runner lineage, but promotion must pass AEG regime/breadth/freshness matrix. |

### §2.4 Post-Gate Roadmap

| Sprint | Purpose | Parallelism |
|---|---|---|
| `AEG-S1` Foundation | retention + alpha-history storage; public Bybit backfill writer; PIT universe builder; side-evidence artifact | LIMITED OPEN: FND-1..4 docs/design/read-only + S2 Gate-B prep; backfill writer waits for storage/provenance + endpoint implementation scope |
| `AEG-S2` Evidence automation | regime label runner; breadth ladder runner; robustness matrix builder | regime + breadth parallel; matrix waits for both |
| `AEG-S3` Alpha research | TSMOM, cross-sectional momentum, S4/Sx falsification overlay, S2 PreLaunch probe | up to 4 parallel |
| `AEG-S4` Decision | CP-2 candidate verdict and operator decision | serial PM -> QC/MIT -> PA -> Operator |

---

## §3 Active Workflows + Module Posture

| Workflow | State | Next action |
|---|---|---|
| `Alpha-Edge / AEG` | ACTIVE mainline | AEG-S1 Foundation FND-1..4 docs/design/read-only plus S2 Gate-B prep; no backfill writer or scoring before PM opens a scoped S1 task. |
| `Workflow B` ADR-0046 basis observation/execution split | ACTIVE but not Alpha-blocking | PA design -> E1 Rust -> MIT V117 -> E2 -> E4 -> BB -> QA. |
| `Earn Wave C` | OPERATOR-GATED | OP-1 key refresh -> OP-2 Earn variant -> OP-3 first $100-200 USDT Flexible stake. |
| `Layered Autonomy v2 Wave 5` | FROZEN active-IMPL per v92 D1 | Packet A+B runtime and TOTP source exist; Packet C core E4 green; runtime TOTP enrollment + engine integration wait until promotion gate. |
| `Sprint 2 / Stage 0R legacy alpha` | SUBORDINATE to AEG | Keep runner/evidence waits visible; no promotion outside AEG gates. |

### §3.1 M1-M13 Compact Matrix

Preservation checkpoint: V5.8 full design files are retained in `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`, module specs, ADR-0034..0045, and `docs/README.md`; current audit is `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md`. Do not expand TODO back into the full V5.8 ledger; keep only active posture and gates here.

| Module | Current posture | Gate / next action |
|---|---|---|
| M1 Decision Lease LAL | DESIGN-DONE; Track A spike source; active-IMPL frozen | Unfreeze only after first net-positive alpha-bearing `stage0_ready`. |
| M2 Overlay enable SM | DESIGN-DONE; IMPL-PENDING frozen | Wait for alpha evidence gate. |
| M3 Health monitoring | DESIGN-DONE; emitter scaffold PASS with carry-over | Residual health rows tracked in OPS queue. |
| M4 Self-supervised discovery | V100 + Stage 1 source/PG no-writeback empirical done; production writeback blocked by lease/schema mismatch | Keep draft-only until governance/lease path is resolved. |
| M5 Online learning interface | Trait stub done | Y3+ / AUM gate; no active IMPL. |
| M6 Bayesian reward weight | DESIGN-DONE; IMPL-PENDING frozen | Wait for alpha evidence gate. |
| M7 Decay/retirement | V116 spec done; IMPL held | Unfreeze after first candidate reaches `stage0_ready`. |
| M8 Anomaly detection | DESIGN-DONE; IMPL-PENDING frozen | Wait for alpha evidence gate. |
| M9 A/B framework | DESIGN-DONE; IMPL-PENDING frozen | Wait for alpha evidence gate. |
| M10 Discovery pipeline | Tier A baseline done; B-E pending | AEG can feed future Tier B+, but not before evidence contracts. |
| M11 Counterfactual replay | V107 schema/source land; runtime proof incomplete | Replay manifest residual tracked in OPS queue. |
| M12 Adaptive order routing | Trait stub done | Future maker/taker and slicing work; no active IMPL. |
| M13 Multi-asset/venue | Trait stub done; Y3+ earliest | No active IMPL. |

---

## §4 Safety Invariants Snapshot

| Invariant | Active meaning |
|---|---|
| 5-gate live boundary | Any live/demo promotion still requires full boundary checks. |
| Signed authorization | Python renew/approve path remains OP-gated; no silent downgrade. |
| LiveDemo safety | Demo endpoint must not weaken authorization, TTL, risk, or audit semantics. |
| Mainnet env fallback closed | `OPENCLAW_ALLOW_MAINNET=1` must come from controlled secrets path. |
| Bybit fail-closed | Timeout or non-zero `retCode` cannot fabricate rows/fills/evidence. |
| Denylist is not auth | `execution_authority=denylist` never equals positive authorization. |
| GovernanceHub + Decision Lease | Learning/dream/executor/strategist paths cannot bypass lease boundaries. |
| No fake evidence | No fake AI calls, fills, lineage, healthcheck, trading, or test evidence. |
| Paper evidence limit | Paper is not active promotion evidence; Stage 0R replay and demo evidence stay separated. |

---

## §5 Active Engineering Queue

| ID | P | Status | Next action |
|---|---:|---|---|
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | SOURCE DONE on `integration/pm-1-4`; not deployed | BB/E2/E4 review with LG-3 source batch. |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | 3 | SOURCE DONE with reconciler pagination batch | E2/E4 review with same batch. |
| `P3-110017-CONVERGE-AUDIT-OBSERVABILITY` | 3 | Deploy verification residual | MIT/E1 verify missing `exchange_zero_close_converge` audit row and ~63s stop timing; function already cleared position. |
| `P3-110017-BB-DOC-FOLLOWUPS` | 3 | BB/TW doc follow-up | Update 110017 dictionary semantics; verify 110009 doc-version ambiguity before relying on mapping. |
| `P1-OPS-2-PHASE-2-CUTOVER` | 1 | WAITING for D+14 soak end 2026-06-10 | If 14d logs clean, E1 PR removes fallback and stale panic/reason variants. |
| `P1-OPS-2-14D-SOAK-OBSERVE` | 1 | ACTIVE passive wait | Daily WARN count must remain 0; at least one `/auth/renew` still operator-blocked. |
| `P1-OPS-2-DRY-RUN` | 1 | WAITING for OP-1 | Use OP-1 as first end-to-end OPS-2 SOP dry-run; record timing/fail modes into runbook v1.1. |
| `P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY` | 1 | PARTIAL DONE / OP-gated | Operator schedules first restore drill and system-level units. |
| `P3-OPS-4-PG-DUMP-EVENT-EXTEND` | 4 | DEFERRED optional event typing | Add `pg_dump_retention_dropped` / `pg_dump_md5_drift` only if dump audit needs finer events. |
| `P2-OPS-4-GAP-B-D-UNIT-TEST-GAP` | 2 | Backlog governance gap | Add tests for pg_dump/passive health production code after first-day live priorities. |
| `P1-WAVE5-TOTP-BACKEND` | 1 | DEFERRED by operator | Runtime TOTP enrollment waits until full formal go-live / Level 2 promotion gate. |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | 1 | Legacy alpha evidence wait | Around 2026-06-11 check AC-S2-A-3 candidate evidence; subordinate result to AEG gates. |
| `P1-A1A2-STAGE0R-RUNNER-IMPL` | 2 | A2 REVISE/HOLD; auth fix branch exists | E2 -> E4 -> PM deploy/runtime verify before trusting runner output. |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | 3 | WAITING for basis_panel >=14d | Trigger around 2026-06-13; wire A1 as-of basis cohort with QC leak-free gate. |
| `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` | 4 | LATENT BUG / folded into AEG-S1-FND-4 | Decide fix/bypass before historical basis/index work; do not use sparse/dead ticker persistence as promotion evidence. |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 4 | Scheduled watch | On 2026-06-27 decide Stage 0R baseline vs M7 retire for bb_breakout/bb_reversion. |
| `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` | 2 | PA spec done; IMPL pending | E1 -> BB -> E2 -> E4 -> QA when Sprint 3 resumes. |
| `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE` | 2 | DEFERRED until C4 | Provision restricted `failsafe_ack_role`, then GUI ack endpoint. |
| `P1-OPS-2-HOTRELOAD` | 3 | Post-Sprint 4 | Implement `Arc<ArcSwap<BybitCredentials>>` + IPC reload parity with authorization.json. |
| `P2-OPS-2-AUDIT-ENDPOINT` | 3 | Post-Sprint 4 | Add `POST /api/v1/security/ipc-secret/rotate` + governance audit row. |
| `P2-OPS-2-CRON-DRIFT` | 3 | Post-Sprint 4 | Add long-lived secret drift cron report/alert. |
| `P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL` | 3 | Runbook gap | Implement or correct missing `passive_wait_healthcheck.py --check secret_rotation` assumption before citing cutover §10.3. |
| `P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT` | 4 | Runbook/audit contract gap | Specify audit rows for emergency revoke and old-key revoke paths. |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | SOURCE CLOSED / OPERATOR-BLOCKED | OP-1 key refresh + OP-2 Earn variant + OP-3 first stake. |
| `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` | 1 | SPEC/IMPL pending | PA spec must require Rust/Python byte-identical canonical HMAC. |
| `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` | 2 | WAITING for Wave D Rust IPC | Add full frontend -> backend -> Rust IPC integration test. |
| `P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG` | 1 | WAITING for OP-1 secret swap | Change live slot endpoint file from `demo` to `mainnet` during key refresh. |
| `P3-WORKFLOW-F-D7-CARRYOVER` | 4 | Due ~2026-06-02 | E1 piggyback deprecation/doc headers; R4 verify. |
| `P1-LG-5` | 4 | Reviewer maturity watch | 90d cadence review; source active with review_live_candidate defer rows. |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | Passive wait | `halt_audit.log` armed; review 2026-08-21 unless healthcheck regresses. |
| `P1-LEASE-1` | 3 | WAITING on P0-LG-3 | Clean `lease.rs:303` + HashMap leak after LG-3 dispatch. |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | Deferred until Phase 2a Demo PASS | Add full dynamic backoff state machine. |
| `P1-INTENTYPE-FIELD-VISIBILITY-DEFER` | 4 | Deferred refactor | PA builder pattern spec before changing `OrderIntent` visibility. |
| `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` | 3 | SOP debt | Update dispatch prompt template: Linux cargo test after atomic build requires explicit rebuild or carry-over. |

---

## §6 Operator Action Checklist

| Action | Trigger | Impact |
|---|---|---|
| OP-1 Bybit mainnet key refresh | Operator availability | Blocks Earn Wave C production path, live-auth renewal, OPS-2 dry-run, and endpoint-file correction. |
| OP-2 Stage 0R Earn variant decision | After OP-1 | Blocks first stake. |
| OP-3 first stake $100-200 USDT Flexible-only | After OP-2 | Creates first `learning.earn_movement_log` evidence. |
| Restore drill window | Low-trading 4h window | Blocks OPS all-green. |
| System-level service install | sudo/operator | Improves runtime protection beyond user watchdog. |
| AEG-S1-OP-1 `market.klines` 1095d decision | After `AEG-S1-FND-1` package | Determines whether 18mo kline backfill can persist in `market.klines` or needs research storage. |
| AEG-S1-OP-2 funding-history storage choice | After `AEG-S1-FND-1` package | Blocks S4/funding-history persistence: extend `market.funding_rates` or create dedicated research storage. |

---

## §7 Deferred / Scheduled Watch

| ID | Trigger date / condition |
|---|---|
| C10 funding harvest 7d demo sample | 2026-06-01 |
| 14d bucket-split AC verdict | 2026-06-02 |
| `P3-WORKFLOW-F-D7-CARRYOVER` | ~2026-06-02 |
| `P1-OBS-PLACEMENT-BBO-V094` | after Phase 1b 14d freeze (~2026-06-01) |
| `P1-CONDITIONAL-WATCH` TONUSDT | 2026-06-09 |
| `P1-OPS-2-PHASE-2-CUTOVER` | 2026-06-10 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` evidence check | ~2026-06-11 |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | ~2026-06-13 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 2026-06-27 |
| `P2-CLIPPY-CLEANUP-1` | active cleanup backlog; E1 4-6h when sprint bandwidth opens |
| `P2-WP05-CSP-UNSAFE-INLINE` | raise before live gate |
| `P3-H0GATE-FILE-SPLIT` | independent file-size wave |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | 2026-08-21 |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 2026-08-21 |
| Sprint 4 first Live $500 | W18-21 (~2026-09) after P0-EDGE-1 + LG-3 + OPS residual gates close |
| Y1/Y2/Y3 autonomy horizons | Long-range only; no active IMPL before evidence gates |

---

## §8 Cascade / Governance Watch

| Source | Status | Next action |
|---|---|---|
| AMD-2026-05-21-01 v2 Wave 5 | Packet A+B + TOTP source + ADR/R4 landed; active-IMPL frozen | Do not dispatch runtime TOTP enrollment or Packet C engine integration until promotion gate. |
| ADR-0046 Proposed | basis observation/execution split still live | PA design chain remains valid; coordinate with AEG endpoint/storage decisions. |
| v92 V### reconcile | doc-side note pending; SQL head remains V115 | TW can update doc notes without touching applied SQL. |
| AMD-2026-05-31-01 / ADR-0047 | Accepted / active | Every Alpha-Edge verdict must include regime, breadth, freshness, survivorship, execution realism. |

---

## §9 Handoff Rules

- Feature/bug chain: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`.
- Quant/data chain: `PM -> QC -> MIT -> AI-E if model-cost relevant -> PM`.
- Exchange-facing work: include `BB`; update `docs/references/2026-04-04--bybit_api_reference.md` for new/changed endpoints.
- V### migration: Linux PG empirical dry-run before sign-off.
- GUI JS: `node --check` or stronger.
- Meta-doc checkpoint: commit with subject + body; push origin; Linux source fast-forward for three-end sync.

### Handoff Checks

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

**Maintenance contract**：`TODO.md` is the active queue only. Long evidence belongs in reports/archive. See `docs/agents/todo-maintenance.md`.
