# W-AUDIT-8a Phase B/C/D Worktree Decomposition + Dispatch Roadmap

Date: 2026-05-18
Role: PA(default)
Workgroup: A-3 / W-AUDIT-8a
Repo root: `/Users/ncyu/Projects/TradeBot/srv`
Report status: PA design — worktree decomposition for PM dispatch
Implementation status: NOT AUTHORIZED by this report

Spec source: `docs/execution_plan/2026-05-16--w_audit_8a_phase_b_c_d_infrastructure_spec.md` v0.1
Prior PA verdict: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8a_phase_b_c_d_pa_verdict_and_sprint_roadmap.md`

---

## §0 Executive Summary

11 worktree decomposition of Phase B / Phase C / Phase D infrastructure work, dispatched across 3 Waves over Sprints N+3 / N+4 / N+5.

| Wave | Sprint | Worktree count | Parallel-safe | Total persondays |
|---|---|---|---|---|
| Wave 1 | N+3 (W7-W8) | 4 | yes | 8.5 |
| Wave 2 | N+4 (W9-W10) | 4 | yes | 23 |
| Wave 3 | N+5 (W11-W12) | 3 | partial (D3 last) | 18 |
| **Total** | — | **11** | — | **49.5 pd** |

Cumulative calendar timeline at 4 E1 active capacity: **~6 sprints / 12 weeks**, matching FA §0 Sprint Milestone Banner N+3 → N+5 plus 1 buffer sprint absorbing C1-LIQ writer, microstructure consumer wiring slip, and Sprint N+4 D-contract review.

**Critical bottleneck**: Worktree `B-REM-5` (source-tier and cohort semantics report fields) is a Wave 1 enabler. Five downstream worktrees inherit its source-tier enum and cohort skip-reason schema — postponing B-REM-5 to Wave 2 forces redesign of `C2-ORDERFLOW`, `C3-SPREAD`, `D1-EVENT`, `D2-REGIME`, and `D3-SENTIMENT` report layers.

**High-risk top-3**:
1. `C1-LIQ-WRITER` — production WS subscription IS now wired (`0e8a8ae8`), but the strategy-facing `AlphaSurface.liquidation_pulse` provider has not landed. High risk if not properly gated on C1 24h proof artifact + BB cor-side mapping confirmation.
2. `C2-ORDERFLOW` — new Tier 3 panel + Bybit `orderbook.50` fanout integration; touches WS event handlers + IPC slots + new V### migration; needs PA+E1+E2+E4+QA + MIT (schema) + BB (WS topic) full chain.
3. `D1-EVENT` — first Scout/Python → Rust Tier 4 cross-language bridge; needs IPC contract design + provider TTL state machine; PA+E1+E2+E4 + CC (cross-language invariant) chain.

---

## §1 Decomposition Table

Field meanings:
- **ID**: stable worktree handle for dispatch packet reference.
- **Files**: anticipated touch set (paths from current repo; not exhaustive).
- **Deps**: blocking dependencies on other worktrees.
- **Risk**: LOW / MEDIUM / HIGH (impl complexity + safety surface + cross-process boundary).
- **PD**: persondays at single E1 throughput.
- **Owner**: dispatch chain (per `CLAUDE.md` §八).
- **Accept**: 2-3 acceptance criteria (exit evidence).

### Wave 1 — Phase B completion + Phase C design lock (Sprint N+3)

| ID | Scope | Files | Deps | Risk | PD | Owner | Accept |
|---|---|---|---|---|---|---|---|
| **B-REM-1** | Dispatch snapshot contract test + report coverage | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` (READ); new test in same module; candidate report writer | none | LOW | 1.5 | E1 + E2 | (1) Test proves funding/OI slot age reported and `try_read` failure soft-fails. (2) No panic on missing panel; surface defaults to `None`, never synthetic. (3) E2 confirms zero lock held across strategy dispatch. |
| **B-REM-2** | Funding consumer completeness reporting | `rust/openclaw_engine/src/strategies/funding_arb/mod.rs` or W-AUDIT-8b Stage 0R candidate report path; surface availability counters | B-REM-1 | LOW | 1 | E1 | (1) W-AUDIT-8b Stage 0R reports emit funding panel availability ratio + cohort + freshness + source tier per cell. (2) No funding-derived promotion is dispatched without Stage 0R + Demo evidence (governance assertion, not code change). |
| **B-REM-3** | OI consumer unavailable-reason instrumentation | `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs`; candidate report writer | B-REM-1 | LOW-MED | 2 | E1 + E2 | (1) `bb_breakout` candidate report counts `oi_panel_unavailable` by reason: absent / stale / missing-symbol / non-finite absolute / non-finite delta. (2) `enable_oi_signal` fail-closed verified by unit test that synthesizes each reason. (3) E2 confirms no silent degrade path. |
| **B-REM-5** | Source-tier / cohort semantics report schema | `rust/openclaw_core/src/alpha_surface.rs` (READ; possible enum addition); shared report-fields helper module | none | LOW-MED | 2 | E1 + PA | (1) New enum `SourceAvailability { WsLive, RestSeed, CohortExcluded, StalePanel, Absent }` (or string equiv) used by B-REM-2/3 + C2/C3 + D1/D2/D3 reports. (2) ADR or memo lock semantics. (3) Six downstream worktree specs cite this schema before Wave 2 IMPL. |
| **C1-LIQ-WRITER** | Liquidation pulse provider + `AlphaSurface.liquidation_pulse` wire | `rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs` (new); `tick_pipeline/on_tick/step_4_5_dispatch.rs`; `alpha_surface.rs` consumer; healthcheck | C1 proof PASS (DONE 2026-05-17) + BB cor-side mapping (DONE) + V095 apply (DONE) + production WS revival (DONE `0e8a8ae8`) | **HIGH** | 2 | PA → E1 → E2 → E4 + MIT (schema) + BB (topic) + QA → PM | (1) Rust producer reads `market.liquidations` rolling window + emits `LiquidationPulse` IPC slot. (2) `AlphaSurface.liquidation_pulse` set only when freshness + topic age + parser-error rate all green; `None` otherwise. (3) New healthcheck `[67]+` covers topic freshness + row volume + parse errors + symbol coverage. (4) No strategy consumer added in this worktree — provider-only. |

### Wave 2 — Phase C impl + Phase D contract review (Sprint N+4)

| ID | Scope | Files | Deps | Risk | PD | Owner | Accept |
|---|---|---|---|---|---|---|---|
| **C2-ORDERFLOW** | Tier 3 orderflow panel (queue imbalance + trade imbalance + large-trade) | `rust/openclaw_engine/src/panel_aggregator/orderflow.rs` (new); `database/orderflow_writer.rs` (new); new V### migration for `panel.orderflow_microstructure_panel`; `alpha_surface.rs` `OrderflowFeatures`; healthcheck | B-REM-5 + C1-LIQ-WRITER complete (proves the WS-fanout / V### / IPC-slot / healthcheck pattern); MIT schema approval; BB topic approval | **HIGH** | 5 | PA → E1 → E2 → E4 + MIT (schema + Linux PG dry-run x2) + BB (WS topic) + QA → PM | (1) V### `panel.orderflow_microstructure_panel` lands with Guard A/B per `feedback_v_migration_pg_dry_run`. (2) Producer derives from existing `orderbook.50` + public trade events; no new REST polling. (3) `AlphaSurface.orderflow` populated only with finite features; missing/stale → `None`. (4) Healthcheck `[68]+` covers freshness/finite/coverage/latency. (5) No strategy consumer added — provider-only. |
| **C3-SPREAD** | Tier 3 bid-ask spread dynamics on same microstructure panel (sharing C2 storage) | Same panel as C2-ORDERFLOW; columns `best_bid`, `best_ask`, `spread_bps`, `spread_zscore_5m`, `spread_p95_1h`, `abnormal_spread`; `alpha_surface.rs` field addition | C2-ORDERFLOW (V### schema lands first; this adds columns or extends rows) | MEDIUM | 3 | PA → E1 → E2 → E4 + MIT (schema delta) + QA → PM | (1) Spread fields on same `panel.orderflow_microstructure_panel` row OR Z-score in sibling continuous aggregate. (2) Spread non-negative + finite checks in healthcheck. (3) `AlphaSurface.orderflow.spread_*` or separate `SpreadFeatures` slice (PA decides during IMPL spec). (4) No strategy consumer; first use is advisory/risk suppressor in a later sprint. |
| **D-CONTRACT-LOCK** | Phase D provider contract review (no IMPL) | New PA spec doc `docs/execution_plan/2026-05-XX--phase_d_provider_contracts.md`; lock TTL state machine + dedupe key + severity normalization | B-REM-5 | LOW | 2 | PA + MIT + CC | (1) EventAlert provider spec: source/severity/affected_symbols/TTL/dedupe key, bounded active-alert list, no raw Scout artifact bleed-through. (2) RegimeTag provider spec: existing `market.regime_snapshots` reader + `Unknown` default + transition churn bound. (3) SentimentPanel provider spec: `market.news_signals.sentiment` aggregation rules + low-sample-as-unavailable semantics + cost budget. (4) CC + MIT sign-off before Wave 3 IMPL dispatch. |
| **HEALTH-CRON-DECISION** | `[66]/[67]+` cron vs passive-runner authority decision | `helper_scripts/db/passive_wait_healthcheck/runner.py`; optional cron/systemd unit; OPS-approved rollback plan if cron path chosen | none (independent) | LOW | 1 | E3 + OPS + PM | (1) Either no-op ops note "passive runner sufficient" OR OPS-approved cron/systemd installer with documented rollback. (2) No runtime behavior change beyond install/uninstall flips. |

### Wave 3 — Phase D impl + canary preparation (Sprint N+5)

| ID | Scope | Files | Deps | Risk | PD | Owner | Accept |
|---|---|---|---|---|---|---|---|
| **D1-EVENT** | EventAlert provider — Python Scout → Rust IPC bridge | New `rust/openclaw_engine/src/panel_aggregator/event_alerts.rs`; new IPC slot `EventAlertsSlot`; Python writer in `scout_agent.py` or sibling; `step_4_5_dispatch.rs` wire | D-CONTRACT-LOCK + B-REM-5 | **HIGH** | 5 | PA → E1 → E2 → E4 + CC (cross-language IPC invariant) + MIT (schema) + QA → PM | (1) IPC slot publishes bounded `EventAlert[]` (per-symbol + global cap). (2) Active-alert TTL expiry runs deterministically every tick. (3) `surface.event_alerts: &[EventAlert]` non-empty only when fresh. (4) Healthcheck `[69]+`: stale active alerts, dedupe rate, source freshness, symbol mapping. (5) Strategy consumption deferred to a separate worktree. |
| **D2-REGIME** | RegimeTag provider — read existing `market.regime_snapshots` | New `rust/openclaw_engine/src/panel_aggregator/regime_tag.rs`; new IPC slot `RegimeTagSlot`; `step_4_5_dispatch.rs` wire | D-CONTRACT-LOCK + B-REM-5 | MEDIUM | 4 | PA → E1 → E2 → E4 + MIT + QA → PM | (1) `surface.regime: RegimeTag` defaults `Unknown`; non-Unknown only when snapshot finite + fresh + within churn budget. (2) Healthcheck `[70]+`: snapshot age, unknown-ratio threshold, transition churn limit. (3) `Unknown` is unavailable (not neutral); strategy reports must count `regime=Unknown` skips. |
| **D3-SENTIMENT** | SentimentPanel provider from `market.news_signals.sentiment` | New `rust/openclaw_engine/src/panel_aggregator/sentiment.rs`; new IPC slot `SentimentPanelSlot`; `step_4_5_dispatch.rs` wire | D-CONTRACT-LOCK + B-REM-5; D1-EVENT IMPL pattern reuse | MEDIUM | 4 | PA → E1 → E2 → E4 + MIT + QA → PM | (1) Aggregate by symbol + bounded window; preserve per-source contribution + sample count. (2) `surface.sentiment_panel: Option<&SentimentPanel>` `Some` only when sample-count floor passed. (3) Healthcheck `[71]+`: sample-count floor, freshness, per-source contribution, finite-range. (4) No external API call adds runtime cost without OPS budget review. |

---

## §2 Dependency Graph

```text
                                 ┌─────────────────┐
                                 │   B-REM-1       │ (LOW, 1.5pd)
                                 │ dispatch test   │
                                 └────┬───────┬────┘
                                      │       │
                          ┌───────────┘       └───────────┐
                          ▼                               ▼
                  ┌──────────────┐                  ┌──────────────┐
                  │  B-REM-2     │                  │  B-REM-3     │
                  │ funding rpt  │                  │  OI rpt      │
                  │ (LOW, 1pd)   │                  │ (LOW-M, 2pd) │
                  └──────────────┘                  └──────────────┘

   ┌────────────────┐                                ┌─────────────────────┐
   │  B-REM-5       │◀═══════enables══════════════▶ │  C1-LIQ-WRITER      │
   │ source-tier    │  (parallel; B-REM-5 not       │ HIGH, 2pd           │
   │ schema (L-M)   │   strictly required for       │ depends on C1 proof │
   │  2pd           │   C1 since C1 uses existing   │ + V095 + WS revival │
   └───────┬────────┘   panel.* pattern)            │ ALL DONE 2026-05-17 │
           │                                         └─────────────────────┘
           │
       (Wave 1 ends; Wave 2 begins after Wave 1 all-green)
           │
           ▼
   ┌────────────────┐
   │  C2-ORDERFLOW  │──────┐                       ┌─────────────────────┐
   │  HIGH, 5pd     │      │                       │  HEALTH-CRON-DEC    │
   │  new V###      │      ▼                       │ LOW, 1pd            │
   │  + IPC + HC    │   ┌──────────────┐           │ independent         │
   └────────────────┘   │  C3-SPREAD   │           └─────────────────────┘
                        │ MED, 3pd     │
                        │ same panel   │           ┌─────────────────────┐
                        │ extension    │           │  D-CONTRACT-LOCK    │
                        └──────────────┘           │ LOW, 2pd            │
                                                   │ provider specs only │
                                                   └─────────┬───────────┘
       (Wave 2 ends; Wave 3 begins after Wave 2 all-green)   │
                                                              ▼
                                ┌─────────────────────────────┐
                                │  D1-EVENT (HIGH, 5pd)       │
                                │  Scout→Rust IPC bridge      │
                                └──────────┬──────────────────┘
                                           │ (IMPL pattern reuse)
                          ┌────────────────┘
                          ▼                                ▼
                  ┌─────────────────┐              ┌─────────────────┐
                  │  D2-REGIME      │              │  D3-SENTIMENT   │
                  │  MED, 4pd       │              │  MED, 4pd       │
                  │  regime_snapshots│             │  news_signals   │
                  └─────────────────┘              └─────────────────┘
```

Critical path: `B-REM-1 → B-REM-5 → C2-ORDERFLOW → C3-SPREAD → D-CONTRACT-LOCK → D1-EVENT → D2/D3` ≈ 1.5 + 2 + 5 + 3 + 2 + 5 + 4 ≈ 22.5 pd serial. Wave parallelism collapses this to ≈ 14 wallclock pd at 4 E1 active.

---

## §3 Wave Dispatch Order

### Wave 1 — Sprint N+3 (Weeks 7-8 of FA banner)

**Dispatch immediately (4 worktree, 8.5 pd total, ETA 2 weeks @ 4 parallel E1)**:

1. **B-REM-1** (LOW, 1.5pd) — E1 + E2; independent.
2. **B-REM-5** (LOW-M, 2pd) — E1 + PA; independent (do this in parallel with B-REM-1).
3. **C1-LIQ-WRITER** (HIGH, 2pd) — full chain PA→E1→E2→E4 + MIT + BB + QA → PM; depends only on C1/V095/revival, all DONE 2026-05-17.
4. **B-REM-2 + B-REM-3** (LOW + LOW-MED, 1 + 2pd) — kick off after B-REM-1 lands; can run sequentially or pair-dispatched.

Wave 1 exit gate: 4 worktree all-green + Wave 2 IMPL specs (`C2-ORDERFLOW` + `C3-SPREAD`) drafted by PA in last 2 days of Wave 1.

### Wave 2 — Sprint N+4 (Weeks 9-10)

**Dispatch after Wave 1 exit gate** (4 worktree, 11 pd total, ETA 3 weeks @ 4 parallel E1):

1. **C2-ORDERFLOW** (HIGH, 5pd) — full chain; first.
2. **HEALTH-CRON-DECISION** (LOW, 1pd) — E3 + OPS + PM; independent, can run any time.
3. **D-CONTRACT-LOCK** (LOW, 2pd) — PA + MIT + CC; runs in parallel with C2.
4. **C3-SPREAD** (MEDIUM, 3pd) — chain on C2-ORDERFLOW V### landing; can start ~day 3 of C2.

Wave 2 exit gate: 4 worktree all-green + Wave 3 IMPL specs (`D1-EVENT` + `D2-REGIME` + `D3-SENTIMENT`) PA-locked.

### Wave 3 — Sprint N+5 (Weeks 11-12)

**Dispatch after Wave 2 exit gate** (3 worktree, 13 pd total, ETA 3.5 weeks @ 3 parallel E1):

1. **D1-EVENT** (HIGH, 5pd) — full chain + CC (cross-language IPC); first because IMPL pattern flows down to D2/D3.
2. **D2-REGIME** (MEDIUM, 4pd) — chain on D1-EVENT IPC pattern; start day 3 of D1.
3. **D3-SENTIMENT** (MEDIUM, 4pd) — chain on D1-EVENT IPC + D2-REGIME pattern; start ~day 5 of D2.

Wave 3 exit gate: 3 worktree all-green + Stage 0R replay-preflight tooling unblocked for first per-alpha-source promotion candidate (W-AUDIT-8e dispatch unblock).

**Total wallclock**: 2 + 3 + 3.5 = **8.5 weeks** @ 4 active E1 (matches N+3 → N+5 calendar with 0.5 sprint buffer; absorbs deploy slip, healthcheck verify cycles, MIT Linux PG dry-run cycles).

---

## §4 Risk Matrix

### §4.1 High-risk Rust IPC / cross-process worktree (require full PA+E1+E2+E4+QA chain per CLAUDE.md §八)

| Worktree | Reason | Mandatory review chain |
|---|---|---|
| **C1-LIQ-WRITER** | Provider for production-revived but governance-gated alpha; touches AlphaSurface field that was historically tombstoned (`liquidation_cascade` requires_revival=true). C1 proof PASS + V095 + WS revival are prerequisites; this worktree must not loosen any gate. | PA → E1 → E2 → E4 + MIT (schema) + BB (Bybit topic correctness re-verify) + QA → PM. CLAUDE.md §八 §12 9-invariant audit required pre-deploy. |
| **C2-ORDERFLOW** | New V### migration + new IPC slot + new Bybit WS fanout integration + new healthcheck; touches 4 cross-cutting surfaces. | PA → E1 → E2 → E4 + MIT (V### + Linux PG dry-run x2 per `feedback_v_migration_pg_dry_run`) + BB (WS topic + rate budget) + QA → PM. |
| **D1-EVENT** | First cross-language Python(Scout) → Rust(panel_aggregator) bridge for Tier 4; cross-process invariant management (TTL/dedupe/cap); IPC slot lifecycle. | PA → E1 → E2 → E4 + CC (cross-language invariant + fail-closed semantics) + MIT (schema if needed) + QA → PM. |

### §4.2 V### migration worktree (MIT Linux PG dry-run x2 mandatory per `feedback_v_migration_pg_dry_run`)

| Worktree | Migration delta |
|---|---|
| **C2-ORDERFLOW** | New `panel.orderflow_microstructure_panel` + continuous aggregates; Guard A on CREATE TABLE; Guard B on type-sensitive ADD COLUMN if iterative. |
| **C3-SPREAD** | Likely column extension on C2 panel OR sibling materialized view; MIT review of whether sibling table is justified. |
| **D1-EVENT** | Optional — IPC-slot-first approach may avoid new schema; PA-spec time will decide if `panel.event_alerts_audit` is needed. |
| **D3-SENTIMENT** | Optional — first IMPL aggregates `market.news_signals.sentiment` in-memory; persistence deferred per spec §11.4. |

### §4.3 ML pipeline / learning surface (MIT review required)

| Worktree | ML touch |
|---|---|
| **B-REM-2** | W-AUDIT-8b Stage 0R report fields (read-only ML consumer surface). |
| **B-REM-3** | `bb_breakout` candidate report fields feed into `learning.strategy_trial_ledger`. |
| **D-CONTRACT-LOCK** | Phase D providers feed Stage 0R replay packet inputs (W-AUDIT-8e/8f future consumer). |

MIT review required for all three. Not full PA+MIT chain blocking, but MIT sign-off required before E2 closes.

### §4.4 Bybit endpoint / WS topic (BB review required)

| Worktree | Bybit surface |
|---|---|
| **C1-LIQ-WRITER** | Re-verifies `allLiquidation.{symbol}` parser semantics with corrected side mapping; BB sign-off DONE in W-AUDIT-8c but worktree must cite the artifact. |
| **C2-ORDERFLOW** | New `orderbook.50` parsing rules + public trade event aggregation; rate-budget review; topic-name and `topics_per_symbol` accounting. |
| **C3-SPREAD** | Shares C2 surface; BB review folded into C2 dispatch. |

### §4.5 Cross-process / cognitive modulation / hard-boundary surface

No worktree in this decomposition touches the 5-gate live boundary, `live_execution_allowed`, `OPENCLAW_ALLOW_MAINNET`, `authorization.json`, or `max_retries=0` constants. All worktrees are alpha-source infrastructure providers; **none authorize strategy promotion, live order dispatch, or autonomy widening**.

Strategy consumption of new alpha sources is **out-of-scope for Phase B/C/D infrastructure** and handled by W-AUDIT-8e/8f (R-2/R-3) deferred to Sprint N+4/N+5 IMPL.

---

## §5 Effort Total + Cumulative Timeline

| Wave | Worktree | PD | Parallel-safe within wave |
|---|---|---|---|
| Wave 1 | B-REM-1 | 1.5 | yes (independent) |
| Wave 1 | B-REM-5 | 2 | yes (independent) |
| Wave 1 | B-REM-2 | 1 | after B-REM-1 |
| Wave 1 | B-REM-3 | 2 | after B-REM-1 |
| Wave 1 | C1-LIQ-WRITER | 2 | yes (independent; uses landed C1+V095 evidence) |
| **Wave 1 subtotal** | 5 worktree | **8.5 pd** | 2 wallclock weeks @ 4 E1 |
| Wave 2 | C2-ORDERFLOW | 5 | first; HIGH risk full chain |
| Wave 2 | C3-SPREAD | 3 | after C2 V### lands |
| Wave 2 | D-CONTRACT-LOCK | 2 | parallel with C2 |
| Wave 2 | HEALTH-CRON-DECISION | 1 | independent |
| **Wave 2 subtotal** | 4 worktree | **11 pd** | 3 wallclock weeks @ 4 E1 |
| Wave 3 | D1-EVENT | 5 | first; HIGH risk full chain |
| Wave 3 | D2-REGIME | 4 | chain on D1 IMPL pattern |
| Wave 3 | D3-SENTIMENT | 4 | chain on D2 IMPL pattern |
| **Wave 3 subtotal** | 3 worktree | **13 pd** | 3.5 wallclock weeks @ 3 E1 |
| **TOTAL** | **11 worktree** | **32.5 pd** | **8.5 weeks** |

Engineering safety buffer: +30% on HIGH-risk (`C1-LIQ-WRITER` / `C2-ORDERFLOW` / `D1-EVENT`) = +3.6 pd contingency → **effective budget 36.1 pd / 9 weeks**.

Calendar: Wave 1 land ~2026-05-31 → Wave 2 land ~2026-06-21 → Wave 3 land ~2026-07-14 (per FA banner N+3-W7 to N+5-W12).

---

## §6 Recommended Wave 1 Dispatch Packet Drafts

Each worktree has a ready-to-dispatch E1 prompt skeleton. PM customizes operator/sub-agent header per actual dispatch.

### §6.1 B-REM-1 — Dispatch Snapshot Contract Test

```text
任務: W-AUDIT-8a B-REM-1 — Dispatch snapshot contract test + report coverage

範圍: 在 rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs
所在 module 添加單元/集成測試，覆蓋 4 條 invariant：
1. funding_curve slot 存在 → AlphaSurface.funding_curve = Some(&snapshot) 且 age 可讀
2. oi_delta_panel slot 存在 → AlphaSurface.oi_delta_panel = Some(&panel) 且 age 可讀
3. try_read failure → AlphaSurface 對應 field = None (soft-fail), 無 panic
4. 缺 panel slot → 不創造合成 neutral 數據; AlphaSurface 對應 field = None

不可改 dispatch 主邏輯; 純 test 添加 + 必要時 expose 內部 helper 供 test。

完成條件:
- cargo test --workspace 通過
- E2 (sub-agent) 確認 0 lock held across strategy dispatch (現有設計)
- 在 candidate report 中 age 欄位被覆蓋 (可選)

風險: LOW
鏈: E1 IMPL → E2 review (對抗審 1 軸: lock-free 證明) → E4 regression → 主會話 sign-off
ETA: 1.5 persondays
```

### §6.2 B-REM-5 — Source-Tier / Cohort Schema (shared schema for 6 downstream worktree)

```text
任務: W-AUDIT-8a B-REM-5 — Source-tier 與 cohort skip-reason 共享 schema

範圍:
1. PA + E1 在 rust/openclaw_core/src/alpha_surface.rs 添加共用 enum:
   pub enum SourceAvailability {
       WsLive,             // WS-first 實時源
       RestSeed,           // REST cold-start seeded
       CohortExcluded,     // symbol 不在 cohort
       StalePanel,         // panel 存在但 freshness 超 threshold
       Absent,             // panel 完全不存在
   }
2. 加 #[derive(Serialize, Deserialize)] + as_metric_label() helper
3. PA 寫 ADR-002X-source-availability-schema.md 鎖定 enum 變更治理 (添加/刪除/重命名觸發 ADR)
4. 在後續 B-REM-2 / B-REM-3 / C2 / C3 / D1 / D2 / D3 spec 中強制引用此 enum 用於 candidate report 的 unavailable_reason 欄位

不可改: 現有 AlphaSurface fields, panel_aggregator producer 行為

完成條件:
- enum + tests 通過
- ADR land
- 後續 6 worktree spec 引用本 enum 的 commitment 寫入下一份 PA spec (Wave 2 起算)

風險: LOW-MEDIUM (downstream coupling)
鏈: E1 IMPL → E2 review → PA ADR draft → E4 regression → 主會話 sign-off
ETA: 2 persondays
```

### §6.3 C1-LIQ-WRITER — LiquidationPulse Provider (Highest priority Wave 1)

```text
任務: W-AUDIT-8a C1-LIQ-WRITER — LiquidationPulse provider + AlphaSurface 接線

範圍:
1. 新建 rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs:
   - LiquidationPulseAggregator: 從 market.liquidations 讀 rolling 5m/15m window
   - 計算 pulse magnitude (per symbol + per side + clustering)
   - IPC slot LiquidationPulseSlot (新建 in ipc_server/slots.rs)
2. tick_pipeline/on_tick/step_4_5_dispatch.rs 接線 AlphaSurface.liquidation_pulse
3. 健康檢查 [67]+ 寫入 helper_scripts/db/passive_wait_healthcheck/checks_market_liquidations_pulse.py:
   - topic freshness (market.liquidations 最新 row age < threshold)
   - row volume (last 5m bounded but non-zero)
   - parse-error rate (per BB cor-side mapping; 0% expected)
   - symbol coverage (主動 cohort coverage ratio)
4. AlphaSurface.liquidation_pulse 只在以上 4 條全綠時 Some(&pulse), 否則 None

不可改: V095 schema, market.liquidations writer (in main.rs 0e8a8ae8 已 land),
        bb_breakout 或任何策略 (本 worktree 純 provider, 策略消費不在範圍)

不可繞: C1 24h proof PASS_C1_PROOF_CANDIDATE artifact (DONE 2026-05-17),
        BB cor-side mapping (DONE), V095 Linux apply (DONE)

完成條件:
- E2 確認 IPC slot zero-lock cross-tick; failed-closed semantics
- E4 regression (cargo workspace) 全綠
- MIT 確認 schema 不需要新 V### (純 read-only consumer)
- BB 確認 Bybit topic semantics 未變化 (re-verify artifact citation)
- QA 確認本 worktree 不觸 P0/P1/P2 風控邊界, 不觸 16 根原則硬邊界

風險: HIGH (新 provider + 新 IPC slot + 涉 governance-gated alpha source)
鏈: PA → E1 → E2 → E4 + MIT + BB + QA → PM
ETA: 2 persondays + 30% buffer = 2.6 persondays
```

### §6.4 B-REM-2 + B-REM-3 — sibling consumer reporting (after B-REM-1)

```text
任務 (B-REM-2): W-AUDIT-8b Stage 0R candidate report 加 funding-panel
availability + cohort coverage + freshness + source_tier (引用 B-REM-5 enum)

任務 (B-REM-3): bb_breakout candidate report 加 oi_panel_unavailable 分項
(absent / stale / missing-symbol / non-finite-absolute / non-finite-delta);
unit test 合成每條 reason; E2 確認 enable_oi_signal fail-closed 不退化

風險: LOW + LOW-MED
鏈: E1 → E2 → E4 → 主會話 sign-off (B-REM-2)
鏈: E1 → E2 → E4 → 主會話 sign-off (B-REM-3)
ETA: 1 + 2 persondays
```

---

## §7 16-Root + 9-Invariant Compliance (本 PA 報告)

- 本 worktree decomposition 純 design / dispatch packet; **0 runtime mutation / 0 schema mutation / 0 trading-state mutation**
- 不觸 5-gate live boundary / live_execution_allowed / max_retries=0 / OPENCLAW_ALLOW_MAINNET / authorization.json
- DOC-08 §12 9-invariant: 本 worktree decomposition N/A; 各 worktree IMPL 階段在自身 sign-off 內 audit
- 16 根原則: A 級 (16/16 + 硬邊界 0 觸碰; 純 PA design output, governance-only)

各 worktree IMPL 階段對 16 根原則的責任分配:
- **原則 1 / 2** (單一寫入口 / 讀寫分離): 所有 worktree 都是 read-only consumer 或 alpha-source provider 寫入新 panel; 不觸 IntentProcessor / submit_intent / authorize_write
- **原則 3** (AI 輸出 ≠ 命令): 本 decomposition 全部是基礎設施提供 AlphaSurface field, 不創造任何 AI → trade 路徑
- **原則 4** (策略不繞風控): 本 decomposition 不接線任何策略消費; W-AUDIT-8e/8f 才處理策略接線, 屆時必經 Guardian + RiskConfig
- **原則 5 / 6** (生存 > 利潤 / 失敗默認收縮): 所有 worktree 的 AlphaSurface field 必須 fail-closed: missing/stale/non-finite → None; 此為 PA 強制驗收條件
- **原則 7** (學習 ≠ 改寫 Live): 本 decomposition 純 provider, 不涉 learning state
- **原則 8** (交易可解釋): 所有 candidate report 必需引用 SourceAvailability enum (B-REM-5 共享 schema)
- **原則 9** (本地 + 交易所雙重防線): N/A (本 decomposition 不接線交易所 conditional order)
- **原則 10** (FACT / INFERENCE / HYPOTHESIS): 各 worktree provider data 屬 FACT (panel snapshot) 或 INFERENCE (aggregated metric); 強制 source_tier 標籤
- **原則 11** (Agent P0/P1 內自主): 本 decomposition 不收緊 Agent 能力, 不擴充 (純基礎設施)
- **原則 12** (持續進化): 本 decomposition 是 alpha source 擴張的演化, 但每條源必過 Stage 0R + Demo
- **原則 13** (AI 成本): 本 decomposition 0 AI call cost; D3-SENTIMENT IMPL 時若引外部 API 必過 OPS budget review
- **原則 14** (零外部成本): 所有 worktree 不引入外部付費依賴 (D3 sentiment 若引外部 API 需 OPS approve)
- **原則 15** (多 Agent 協作 formal): 本 decomposition 各 worktree 對應正式 owner chain
- **原則 16** (組合級風險): 本 decomposition 不觸組合級; W-AUDIT-8g IMPL 才處理 per-alpha-source LiveBudget

---

## §8 Assumptions

1. C1 24h proof PASS_C1_PROOF_CANDIDATE artifact on `trade-core` (DONE 2026-05-17) is treated as authoritative for `C1-LIQ-WRITER` dispatch.
2. V095 (`market.liquidations` identity) is applied on Linux PG (DONE 2026-05-17); `C1-LIQ-WRITER` is provider-only and does not require a sibling migration.
3. Production `allLiquidation.{symbol}` subscription is live since `0e8a8ae8`; `bedc40c3` log fix is applied; `C1-LIQ-WRITER` reads from live `market.liquidations` rows.
4. FA Sprint banner N+3-W7 starts the Wave 1 dispatch window; PM may adjust calendar by ±1 sprint depending on W-AUDIT-8b Round 2 ≥7d panel verdict + Operator (a) standby-E1 activation.
5. W-AUDIT-8e (R-2 Strategist Alpha Source Orchestrator) IMPL is deferred to N+5; this decomposition deliberately stops at provider-level, leaving strategy consumption for the next sprint group.
6. W-AUDIT-8b Round 2 ≥7d panel verdict has not landed (preliminary RED at 6.92d per `2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md`); B-REM-2 funding consumer reporting still produces evidence regardless of W-AUDIT-8b verdict (verdict affects W-AUDIT-8b/Strategy IMPL, not the panel-provider plumbing).
7. `OrderflowFeatures` and `OrderflowFeatures.spread_*` extension is one panel (per spec §6.C3); MIT may overrule during C3-SPREAD dispatch if retention/query patterns argue separation.

---

## §9 Files Touched By This PA Session

- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md` (new — this report)
- No other files mutated. Spec `2026-05-16--w_audit_8a_phase_b_c_d_infrastructure_spec.md` v0.1 not edited.

---

## §10 PA Sign-Off

```text
PA DESIGN DONE: W-AUDIT-8a Phase B/C/D worktree decomposition v1.0 ready for PM dispatch.
11 worktree across 3 Waves; total 32.5 pd + 30% HIGH-risk buffer ≈ 36.1 pd.
Wave 1 ready for immediate dispatch.
Implementation remains BLOCKED until PM dispatches each scoped E1 / E2 / E4 / MIT / BB / QA chain per worktree.
Report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md
```

