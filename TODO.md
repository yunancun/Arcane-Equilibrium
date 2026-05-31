# 玄衡 TODO — Active Dispatch Queue

**版本** v94 ｜ **日期** 2026-05-31 ｜ **source HEAD** latest git log after this doc checkpoint；runtime unchanged
**當前主線**：P0-EDGE-1 Alpha-Edge Regime Evidence Governance。E1 backfill / DB retention / endpoint IMPL / alpha scoring 全部 blocked until AEG-S0 contract sprint passes.
**歷史詳情**：version log `docs/CLAUDE_CHANGELOG.md`；pre-cleanup archive `docs/archive/2026-05-31--todo_v93_pre_aeg_cleanup_archive.md`；older v92 archive `docs/archive/2026-05-31--todo_v92_archive.md`。

---

## §0 Runtime Snapshot

| Area | Current state | Next action |
|---|---|---|
| Source sync | Mac `main` is the active source branch; current batch is docs/governance only. | Commit + push, then fast-forward Linux source. |
| Runtime | Linux engine/API/watchdog were healthy in latest v87 snapshot; this batch does not rebuild/restart runtime. | No deploy in this batch. |
| Operator-gated ops | system-level unit install, first restore drill, live-auth renewal remain hand actions. | Operator chooses low-risk window / auth timing. |

---

## §1 P0 Active Blockers

| ID | Status | Owner chain | Acceptance / Gate | Next action |
|---|---|---|---|---|
| `P0-EDGE-1` | 🔴 ACTIVE | PM -> PA/QC/MIT/BB -> E1 after gate | Closure requires Alpha-Edge evidence path: ≥3 alpha-bearing candidates meeting net/cost/statistical gates, or other accepted P0-EDGE criteria. Bull-only/stale-only/narrative-only positives cannot promote. | Run **AEG-S0 contract sprint** only. PM 2nd sign-off approved AEG-S0, not E1 backfill. |
| `P0-LG-3` | 🟡 SOURCE INTEGRATED / runtime not deployed | PM -> E2 -> E4 -> QA -> operator deploy gate | Review integrated commits `deb3f3af..0802d52b`; V104 checksum discipline; Linux migration dry-run/AUTO_MIGRATE plan; supervised_live tests green. | Run review chain before any deploy/rebuild. |
| `P0-OPS residual` | 🟢 OPS-1 CLOSED / residual OP-gated | Operator + PM/E1/MIT as needed | Restore drill, system-level units, live-auth renewal, replay manifest feed, close-maker max-pending evidence. | Wait for operator hand-action windows; not current coding blocker. |

---

## §2 Alpha-Edge Regime Evidence Program

**SSOT**:

- Governance: `docs/adr/0047-alpha-edge-regime-evidence-governance.md`
- Amendment: `docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md`
- Findings: `docs/audits/2026-05-31--alpha_edge_regime_evidence_governance_findings.md`
- Engineering arrangement: `docs/execution_plan/2026-05-31--alpha_edge_regime_evidence_engineering_arrangement.md`
- PM 2nd sign-off: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--alpha_edge_regime_evidence_pm_second_signoff.md`

**Non-negotiable rules**:

- Bull data is allowed only when explicitly labeled.
- S4 is a global S1-Sx regime/falsification overlay.
- Bybit market APIs are raw state inputs, not prediction.
- Trend/regime labels must be local, leak-free, point-in-time, and fixed before alpha scoring.
- News/X/Reddit agents are side evidence only.

### §2.1 NOW: AEG-S0 Contract Sprint

| Session | Owner chain | Output | Acceptance |
|---|---|---|---|
| `AEG-S0-W0-S1` Evidence Storage Contract | PM -> PA+MIT -> QC | alpha-history manifest, coverage/provenance, regime/breadth/side-evidence artifact contract | Includes `run_id`, `git_sha`, `session_id`, window, symbols, universe, cost model, endpoint list, classifier version; excludes 14d `panel.*` as 18mo history. |
| `AEG-S0-W0-S2` Regime Classifier Freeze | PM -> QC+PA -> MIT | bull/range/bear/chop/high-vol taxonomy + overlay flags | Rules fixed before alpha scoring; closed bars only; all features lagged / `shift(1)`. |
| `AEG-S0-W0-S3` Bybit Endpoint Contract | PM -> MIT+BB -> PA | endpoint adoption plan | Covers pagination, retention, rate limits, client gaps, and BB review for kline/funding/OI/long-short/mark-index-premium/ticker/orderbook/IV. |
| `AEG-S0-W0-S4` TODO Archive Plan | PM -> TW/CC -> PM | active TODO cleanup plan | Active TODO keeps next actions; historical evidence stays in reports/archive. |

Parallelism: 4 sessions can run together; project ceiling remains 7.

### §2.2 E1 Hard Block

E1 must not start any of the following before AEG-S0 passes and PM opens AEG-S1:

- Bybit historical backfill writer.
- `market.klines` retention/runtime PG mutation.
- funding/OI/long-short 18mo backfill.
- mark/index/premium kline client implementation.
- listing-capture collector IMPL.
- alpha scoring / promotion report.

Allowed before AEG-S0 pass: read-only probes and sizing estimates only.

### §2.3 Post-Gate Roadmap

| Sprint | Purpose | Parallelism |
|---|---|---|
| `AEG-S1` Foundation | retention + alpha-history storage; public Bybit backfill writer; PIT universe builder; side-evidence artifact | S1-W1-S1/S3/S4 parallel; backfill writer waits for storage + endpoint contracts |
| `AEG-S2` Evidence automation | regime label runner; breadth ladder runner; robustness matrix builder | regime + breadth parallel; matrix waits for both |
| `AEG-S3` Alpha research | TSMOM, cross-sectional momentum, S4/Sx falsification overlay, S2 PreLaunch probe | up to 4 parallel |
| `AEG-S4` Decision | CP-2 candidate verdict and operator decision | serial PM -> QC/MIT -> PA -> Operator |

---

## §3 Active Engineering Queue

| ID | Priority | Status | Next action |
|---|---:|---|---|
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | 2 | SOURCE DONE on `integration/pm-1-4`; not deployed | BB/E2/E4 review with LG-3 source batch. |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | 3 | SOURCE DONE with reconciler pagination batch | E2/E4 review with same batch. |
| `P1-OPS-2-PHASE-2-CUTOVER` | 1 | WAITING for D+14 soak end 2026-06-10 | If 14d logs clean, E1 PR removes fallback and stale panic/reason variants. |
| `P1-OPS-2-14D-SOAK-OBSERVE` | 1 | ACTIVE passive wait | Daily WARN count must remain 0; at least one `/auth/renew` still operator-blocked. |
| `P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY` | 1 | PARTIAL DONE / OP-gated | Operator schedules first restore drill and system-level units. |
| `P1-A1A2-STAGE0R-RUNNER-IMPL` | 2 | A2 REVISE/HOLD; auth fix branch exists | E2 -> E4 -> PM deploy/runtime verify before trusting runner output. |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | 3 | WAITING for basis_panel >=14d | Trigger around 2026-06-13; then wire A1 as-of basis cohort. |
| `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` | 4 | LATENT BUG | Decide fix/bypass before historical basis/index work. |
| `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` | 2 | PA spec done; IMPL pending | E1 -> BB -> E2 -> E4 -> QA when Sprint 3 resumes. |
| `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE` | 2 | DEFERRED until C4 | Provision restricted `failsafe_ack_role`, then GUI ack endpoint. |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | SOURCE CLOSED / OPERATOR-BLOCKED | OP-1 key refresh + OP-2 Earn variant + OP-3 first stake. |
| `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` | 1 | SPEC/IMPL pending | PA spec must require Rust/Python byte-identical canonical HMAC. |
| `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` | 2 | WAITING for Wave D Rust IPC | Add full frontend -> backend -> Rust IPC integration test. |

---

## §4 Operator Action Checklist

| Action | Trigger | Impact |
|---|---|---|
| OP-1 Bybit mainnet key refresh | Operator availability | Blocks Earn Wave C production path and live-auth renewal. |
| OP-2 Stage 0R Earn variant decision | After OP-1 | Blocks first stake. |
| OP-3 first stake $100-200 USDT Flexible-only | After OP-2 | Creates first `learning.earn_movement_log` evidence. |
| Restore drill window | Low-trading 4h window | Blocks OPS all-green. |
| System-level service install | sudo/operator | Improves runtime protection beyond user watchdog. |

---

## §5 Deferred / Scheduled Watch

| ID | Trigger date / condition |
|---|---|
| `P3-WORKFLOW-F-D7-CARRYOVER` | ~2026-06-02 |
| `P1-CONDITIONAL-WATCH` TONUSDT | 2026-06-09 |
| `P1-OPS-2-PHASE-2-CUTOVER` | 2026-06-10 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` evidence check | ~2026-06-11 |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | ~2026-06-13 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 2026-06-27 |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | 2026-08-21 |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 2026-08-21 |

---

## §6 Handoff Rules

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
