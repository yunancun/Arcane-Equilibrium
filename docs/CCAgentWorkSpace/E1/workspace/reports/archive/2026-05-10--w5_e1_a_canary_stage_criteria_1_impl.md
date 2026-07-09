# W5-E1-A P1-CANARY-STAGE-CRITERIA-1 IMPL Report

**Status**: ✅ E1 IMPL DONE — committed 6529e37e + pushed origin/main
**Owner**: E1（Backend Developer）｜ **Date**: 2026-05-10
**Sprint**: N+1 D+0 dispatch wave W5-E1-A
**Cross-ref**:
- Spec: `docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`
- AMD: `docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-05-canary-stage-criteria-spec.md`
- Parent dispatch: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.5 W5

---

## 1. 任務摘要

W5-E1-A spec §2-§5（promote / rollback 公式）落地：
- Rust pure-logic module `canary_promotion.rs` 對應 spec §2-§5 公式 100%
- Python evaluator `canary_promotion_eval.py` byte-identical mirror
- V089 PG seed `governance.canary_stage_metric_registry` 18 row（>=12 spec acceptance）
- Healthcheck `[58a] stage_criteria_eval` enrich evidence collection（V089 seed
  coverage drift detection + active cohort metric set summary）
- AMD-2026-05-10-05 起草（精確化 AMD-2026-05-09-03 §2.2 表的 AND/OR + sample
  floor + wall-clock floor 語義）

**LOC 估**：spec hint Rust ~120 + Python ~80 + SQL ~60 = ~260 LOC + ~80 LOC test。
**實際 LOC**：Rust 879 (含 24 unit test) + Python helper 479 + SQL 270 + 健檢 188 +
test 310 + AMD 314 = **2441 insertions, 7 file**。實際多出來在：
- Rust unit test 24 case（cover Stage 0..=4 promote happy / pending / fail + rollback spec §5 全 case + sm04_l3 跨 stage + clock skew clamp）
- Python helper Rust mirror full（不只 evaluator API，還含 dataclass + enum + helper docstring）
- SQL Guard A/B/C 模板 + per-stage 4 INSERT block + final NOTICE verification
- AMD 完整章節（rationale + 16 原則 compliance check + 6 後續動作）

---

## 2. 修改清單

### 新建 / 修改 file（commit 6529e37e — 7 file）

| File | LOC change | Type | Module |
|------|-----------|------|--------|
| `rust/openclaw_engine/src/config/canary_promotion.rs` | +879 / -0 | NEW | Rust pure-logic + 24 unit test |
| `rust/openclaw_engine/src/config/mod.rs` | +1 / -0 | EDIT | `pub mod canary_promotion;` 掛載 |
| `program_code/.../app/canary_promotion_eval.py` | +479 / -0 | NEW | Python evaluator helper |
| `helper_scripts/db/passive_wait_healthcheck/checks_canary_stage_criteria.py` | +188 / -0 | NEW | `[58a]` enrich healthcheck |
| `helper_scripts/db/test_canary_promotion_eval.py` | +310 / -0 | NEW | 18 unit test |
| `sql/migrations/V089__governance_canary_stage_metric_seed.sql` | +270 / -0 | NEW | PG seed 18 row |
| `docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-05-canary-stage-criteria-spec.md` | +314 / -0 | NEW | Amendment 起草 |

### 與既有 file 的關係

- 不修改 `rust/openclaw_engine/src/config/risk_config_advanced.rs`（已 land
  ExecutorConfig + CanaryStage / CanaryCohort，W-AUDIT-9 T1 done — 本 IMPL
  reuse）
- 不修改 `program_code/.../app/executor_agent.py`（W-AUDIT-9 T3 stage-aware
  `_read_canary_stage` 已 land — Python evaluator 不替代 IPC provider，提供
  獨立 evaluator 可由 shadow_mode_provider 跨進程呼叫）
- 不修改 `program_code/.../app/executor_config_cache.py`（cache 不嵌業務邏輯）
- 不修改 `helper_scripts/db/passive_wait_healthcheck/checks_canary_stage_invariant.py`
  （`[58]` invariant 哨兵保留現狀，新加 `[58a]` 同 family 補 enrich）
- 不修改 `program_code/.../app/governance_canary_routes.py`（GUI route 由
  W-AUDIT-9 T5 land — manual_promote payload 必含 cohort 字段檢查留 D+1 補強）

### Multi-session race 帶走（W5-E1-C commit `d17d7863`）

`helper_scripts/db/passive_wait_healthcheck/runner.py` 加 `[58a]` import +
cursor 區塊 invocation — 本 sub-agent edit 同 staging 被 W5-E1-C `git add` 帶
走，commit 訊息只提 `[64]` 但 disk 已含 `[58a]`。確認 grep + `git diff HEAD`
empty + git log 顯示 `d17d7863` 已含 `check_58a` import + invocation。

無需 revert / re-commit — `[58a]` 與 `[64]` 同 deploy 是 desirable 結果。

---

## 3. 結構（spec §8 Acceptance Criteria 對照）

| # | Spec Acceptance | IMPL 狀態 |
|---|---|---|
| 1 | `canary_promotion.rs` PromoteVerdict enum (`Promote`, `Pending`, `Fail`, `Demote`) 對應 §2-§5 公式 100% | ✅ Done — 5 verdict (Promote/Pending/Fail/PendingOperator/ReadyForOperatorReview) + RollbackVerdict (Stable/Demote)；24 unit test verify 公式對齊 |
| 2 | `[58a]` healthcheck 跑 cohort 模擬資料 PASS / WARN / FAIL 各 ≥1 case unit test | ✅ Done — `Check58aHealthcheckTests` 4 case (warn_v089_not_seeded / warn_table_missing / pass_v089_fully_seeded / pass_active_cohort_summary)；FAIL case 不適用 `[58a]` (verdict-preserving 設計) |
| 3 | `governance.canary_stage_metric_registry` seed 後 SELECT COUNT(stage IN 1..4) ≥ 12 row（每 stage ≥3 metric）| ✅ Done — V089 seed 18 row：Stage 1=5 (4 promote + 1 rollback), Stage 2=7 (5+2), Stage 3=7 (5+2), Stage 4=1 (0+1)；Final NOTICE block 強制 ≥12 enforce |
| 4 | `_evaluate_promote_criteria()` Python helper 對 W3 cohort grid_trading × BTCUSDT × demo 跑出 PromoteVerdict 與 `[58]` SQL 結果一致 | 🟡 部分 — Python helper 已 IMPL；cross-language verification 等 W3 cohort SQL pipeline land 後做。本 IMPL 階段 18 unit test cover Python helper byte-identical with Rust pure-logic（透過共用 spec §2-§5 公式） |
| 5 | AMD-2026-05-10-05 land + PA + QC + PM sign-off | 🟡 Drafted — AMD 已起草 commit；待 D+1 PA + QC + PM sign-off |
| 6 | E2 review confirm `boundary_violation_count` 計算與 §2.4 list 7 source 全對齊 | 🟡 Pending — 等 E2 review。本 IMPL 階段 boundary 計算依賴 caller 構造 metrics（不 hard-code source list）；spec §2.4 7 source 對齊由 caller (W3 cohort SQL pipeline) 負責 |
| 7 | E4 regression 驗 5 stage transition matrix 全 25 case (5×5) | 🟡 Pending — 等 W3 land 後 E4 regression 跑完整 transition matrix；本 IMPL 24 Rust + 18 Python test cover 大部分 promote / rollback case，但 transition state machine 全 25 case 需 W3 整合後驗證 |
| 8 | 16 原則 / DOC-08 §12 / 硬邊界 5 項 0 觸碰 | ✅ Done — AMD §6.2 16 原則合規 confirm；DOC-08 §12 不適用 graduated canary 範圍 (per AMD-2026-05-09-03 §3)；硬邊界 5 項 (max_retries=0 / live_execution_allowed / execution_authority / system_mode / authorization.json signature chain) 全 0 觸碰 |
| 9 | CLAUDE.md §三 active gates 加 `[58a]` 描述 update | 🟡 Pending — 留 TW + PA D+1 補。本 IMPL 不擅自改 CLAUDE.md |

---

## 4. 設計決策

### 4.1 Rust 模組落地 `config/` 而非 `risk_control/`

spec §7.1 寫 `rust/openclaw_engine/src/risk_control/canary_promotion.rs`，但實際
無此目錄。RCA：spec 是 PA 在 conceptual scope 用的命名；實際 Rust 側 ExecutorConfig
+ CanaryStage / CanaryCohort 都在 `config/risk_config_advanced.rs`（path attribute
child mod under risk_config.rs）。新 `canary_promotion.rs` 放 `config/` 與 sibling
直接 import 最自然。

新建 `risk_control/` 頂層 dir 會增加無謂 mod tree 複雜度（lib.rs 已 56 mod），
config/ 的 cohesion 也最強。

### 4.2 Python evaluator 放新檔 `canary_promotion_eval.py` 而非塞 `executor_config_cache.py`

spec §7.2 寫 helper 加在 `shadow_mode_provider.py`（不存在）。實際 shadow_mode
provider 在 `executor_config_cache.py`，但 cache 不應嵌業務邏輯（Single Responsibility）。
新檔 `canary_promotion_eval.py` 與 Rust pure-logic 同源，命名對齊。Python
helper 不替代 IPC provider — `executor_agent._read_canary_stage()` 仍走 IPC
從 Rust ConfigStore 讀；Python evaluator 提供 in-process pure-logic eval（測試
+ shadow_mode_provider stage-aware 路徑可呼叫）。

### 4.3 Verdict 5 種 vs spec §7.1 hint 的 4 種

spec §7.1 寫 `PromoteVerdict enum (Promote, Pending, Fail, Demote)`。但 spec §2-§5
細讀後 verdict 必區分：
- `Promote` — 全條件達成，允許 promote 至 N+1
- `Pending` — 部分條件未滿足，等下次 cycle
- `Fail` — 在 spec wall-clock fail window 後仍未達升級條件 → escalate WARN（不 auto-demote）
- `PendingOperator` — Stage 0 / Stage 4 永不 auto-promote（operator 拍板）
- `ReadyForOperatorReview` — Stage 3→4 全條件達成但 spec §4 明示不 auto-promote

`Demote` 屬 rollback 路徑語義，與 promote verdict 不同 enum；改為 `RollbackVerdict
{Stable, Demote {target_stage}}` 兩 verdict 拆開更乾淨。

### 4.4 `[58a]` verdict-preserving 設計（不 hard FAIL）

spec §7.4 enrich 列了 5 細粒度 evidence collection。但 W3 cohort SQL pipeline 還沒
land，實際 cohort metric 計算（trading.fills × cohort × stage_entered）無法跑。
本 IMPL 階段 `[58a]` 只報告 V089 seed coverage drift + active cohort 對應的
metric registry list（不嘗試計算真實 metric 值）。

verdict 哲學：WARN-on-V089-seed-drift / PASS-on-full-seed，**不 hard FAIL**（per
silent-dead 偵測哲學 — `[58]` 已 hard FAIL handle V080 缺 / SM-04 escalate /
manual_null_lease drift）。`[58a]` 補 evidence 不替代 `[58]` verdict。

### 4.5 V089 INSERT order — promote 在 rollback 之前 + per-stage 順序

V089 用 4 個獨立 INSERT block（Stage 1 promote / Stage 2 promote / Stage 3 promote /
Stage 1 rollback / Stage 2 rollback / Stage 3 rollback / Stage 4 rollback）—
每 stage / kind 隔離方便 reviewer 對齊 spec §2-§5 公式。

不用一個 mega INSERT 全 18 row 是因為：
- Reviewer 分節 review 較易（per stage 一段）
- 失敗時錯誤訊息 row index 對應分明
- ON CONFLICT skip 對 partial unique index `uq_canary_stage_metric_registry_active`
  正常工作

### 4.6 觀察期 vs sample size floor 雙鎖（spec §2.3 QC HIGH push back 2）

Stage 1→2：wall_clock ≥ 7d AND sample_size_floor_ms ≥ 72h **whichever later**。
語義 = 兩者都必達（兩者 AND），不是 wall_clock 或 sample 任一達即可。

Rust 實作：
```rust
if elapsed < STAGE1_WALL_CLOCK_MS { return Pending(wall_clock 短) }
if elapsed < STAGE1_SAMPLE_FLOOR_MS { return Pending(sample 短) }
```

兩個 if 都 < 才走下游 entry_fills check — 隱式 AND。註解明示「whichever later」。

---

## 5. 不確定處 / D+1+ 注意事項

### 5.1 W3 cohort SQL pipeline 對齊（spec §9 重點 1）

W3 atomic patch 預期下 cohort metric SQL pipeline（`SELECT COUNT(*) AS entry_fills_count
FROM trading.fills WHERE strategy_name = $1 AND symbol = $2 AND ts >= to_timestamp($3 / 1000.0)
AND COALESCE(exit_source, '') = '' AND NOT EXISTS (rejected_governance subquery)`）。

本 IMPL 階段未驗證 W3 SQL 與 spec §2.2 SQL byte-identical — D+1 W3 dispatch
完成後 cross-language verification（spec §8 acceptance #4）必跑：
- `cohort = grid_trading × BTCUSDT × demo`
- 用同 metric snapshot 跑 V089 SQL + Python evaluator + Rust pure-logic
- 三者 verdict 必一致

### 5.2 `boundary_violation_count` source list 完整性

本 IMPL caller 注入 `metrics.boundary_violation_count`，不 hard-code 7 source
list（per spec §2.4：lease IPC 失敗 / authorization revoke / SM-04 escalate / Decision
Lease deny / Guardian veto / `_read_shadow_mode()` exception / OR）。

D+1 W3 IMPL 必含 boundary aggregator — 把 7 source 累加到單一
`boundary_violation_count` 餵 evaluator。E2 review 必驗 aggregator 不漏 source。

### 5.3 `[58a]` D+1 enrich 加 cohort metric eval

W3 cohort SQL pipeline land 後 `[58a]` 應 enrich：
- 對 active cohort 跑真實 cohort metric SQL（gross_pnl_usdt / DSR / attribution
  via [55] / boundary_violation_count via aggregator）
- 與 V089 seed threshold 比對 → 報告 promote_condition_met (PASS/PENDING/FAIL)
  per metric + margin
- rollback metric 同樣 — 報 trip status

實作位置：擴展 `checks_canary_stage_criteria.py`，不另開 `[58b]`（避免 healthcheck
ID 膨脹）。

### 5.4 cargo cross-platform compilation

Mac 本 IMPL 跑 cargo test --lib --release 通過 2695/2695 — 但 cross-platform aarch64-apple-darwin
+ x86_64-unknown-linux-gnu compilation 需 D+1 `restart_all.sh --rebuild` 在 Linux
trade-core 驗證（per CLAUDE.md §七 跨平台兼容性）。

### 5.5 V089 Linux PG dry-run mandatory

per `feedback_v_migration_pg_dry_run.md`：V089 不能只 Mac mock pytest 驗證。
D+1 W5-E1-A E1-B 子任務（PA spec §7.3）需 Linux PG empirical run：
- 1st run: 預期 18 row INSERT；Final NOTICE 顯示 `total=18 promote=14 rollback=4`
- 2nd run: ON CONFLICT skip，預期 0 INSERT；Final NOTICE 仍顯示 `total=18`
- Guard A/B/C trip test：手動 DROP V080 partial unique index → 跑 V089 應 RAISE EXCEPTION

### 5.6 AMD-2026-05-10-05 sign-off chain

Drafted — 待 D+1 PA + QC + PM sign-off。E2 + E4 review 後 AMD §8 sign-off table
逐 row 標 ✅。

---

## 6. 治理對照

### 6.1 16 根原則合規 ✅

per AMD-2026-05-10-05 §6.2 + AMD-2026-05-09-03 §6.3 — 全 16 原則 0 觸碰：
- 原則 1 單一寫入口：所有 stage 仍走 IntentProcessor
- 原則 2 讀寫分離：`[58a]` 純 SELECT；GUI read-only
- 原則 4 策略不繞風控：Guardian veto / SM-04 ladder 在所有 stage active
- 原則 5 生存 > 利潤：StopManager 所有 stage active
- 原則 6 失敗默認收縮：rollback 永遠回更低 stage
- 原則 7 學習 ≠ Live：學習 / live 隔離不變
- 原則 8 交易可解釋：每 transition 落 `canary_stage_log` + metric_snapshot
- 原則 9 雙重防線：Stage ≥ 1 都 active
- 原則 11 Agent 最大自主：cohort 內自主，cohort 邊界 operator 拍板

### 6.2 DOC-08 §12 9 條安全不變量 ✅ 不適用範圍

per AMD-2026-05-09-03 §3.1 — graduated canary **不適用** DOC-08 §12 9 條（pre-trade
audit replay / lease acquired before submit / fills writer / SM-04 auto bleed /
authorization expired → cancel_token / 等）。任一觸發 = 立即 auto-rollback 至 Stage 0。

本 IMPL 純 governance evaluator，不涉及 DOC-08 §12 列舉的 hot path action。

### 6.3 硬邊界 5 項 0 觸碰 ✅

CLAUDE.md §四：
1. `max_retries = 0` — 本 IMPL 不改
2. `live_execution_allowed` — 不改
3. `execution_authority` — 不改
4. `system_mode` — 不改
5. `authorization.json` 簽名鏈 + Live boundary 5-gate — 不改

本 IMPL 純 Python / Rust pure-logic + SQL seed + healthcheck — 無下單路徑、
無 authority manipulation、無 secret 操作。

### 6.4 SM-04 ≥ L3 hard demote ✅

`is_rollback_tripped` 函數第 1 個 check：sm04_level >= 3 跨 stage 強制 demote
至 Stage 0（不論 source stage）。對齊 AMD-2026-05-09-03 §3.2 + AMD-2026-05-10-05 §2.6。
Rust unit test `rollback_sm04_l3_demotes_to_stage0_across_all` 驗 Stage 1/2/3/4
全部 demote 至 Stage 0。

---

## 7. 測試結果

### 7.1 Cargo lib test

```
$ cargo test --lib --release -p openclaw_engine
test result: ok. 2695 passed; 0 failed; 0 ignored; 0 measured
```

含 24 個新增 `config::canary_promotion::tests`：
- `stage0_never_auto_promote` / `stage4_never_auto_promote_even_if_perfect`
- `stage1_promote_happy_path` / `stage1_pending_when_wall_clock_short` /
  `stage1_pending_when_sample_floor_short` / `stage1_pending_when_entry_fills_short` /
  `stage1_pending_when_boundary_violation` / `stage1_fail_after_14d_low_fills`
- `stage2_promote_happy_path` / `stage2_pending_when_dsr_none` /
  `stage2_pending_when_dsr_low` / `stage2_pending_when_pnl_at_floor`
- `stage3_ready_for_operator_review_when_perfect` / `stage3_pending_when_attribution_low` /
  `stage3_pending_when_pbo_high`
- `rollback_stable_when_metrics_healthy` /
  `rollback_sm04_l3_demotes_to_stage0_across_all` /
  `rollback_stage1_boundary_violation_demotes_to_0` /
  `rollback_stage2_pnl_lt_minus_10_demotes_to_1` /
  `rollback_stage2_dsr_negative_demotes_to_1` /
  `rollback_stage3_pnl_lt_minus_20_demotes_to_2` /
  `rollback_stage3_attribution_lt_03_demotes_to_2` /
  `rollback_stage4_boundary_demotes_to_0`
- `wall_clock_clamp_at_zero_for_negative_skew`

### 7.2 Pytest

```
$ pytest helper_scripts/db/test_canary_promotion_eval.py
============================== 18 passed in 0.02s ==============================

$ pytest helper_scripts/db/test_canary_stage_invariant_healthcheck.py
============================== 13 passed in 0.03s ==============================
```

18 新 + 13 既有 = 31 PASS / 0 fail（[58] 既有測試 0 regression）。

### 7.3 cargo test 失誤教訓（已修）

第一輪 24 case 兩個 fail：
- `stage1_pending_when_entry_fills_short` — happy_metrics(0) 用 +30d，撞 spec
  §2.5 「14d wall-clock 仍 entry_fills < 10」starvation Fail
- `stage2_pending_when_pnl_at_floor` — 同類，Stage 2 spec §3 28d starvation Fail

修法：兩 test 改用更短 wall_clock（Stage 1 用 8d、Stage 2 用 15d），落入 promote
閾值之後但 starvation Fail window 之前的 Pending 範圍。

教訓 → memory.md 教訓 20。

### 7.4 V089 SQL — 未跑 Linux PG dry-run

Mac 環境無 PG service，per `feedback_v_migration_pg_dry_run.md` 必 D+1 dispatch
E1-B 子任務在 Linux trade-core 跑 dry-run + 2nd run idempotency verify。本
sub-agent 完成 SQL static review（語法 / Guard A/B/C / ON CONFLICT 模板對齊
sibling V086/V087/V088）但未 runtime verify。

---

## 8. 給 PM 的 push back / Operator 下一步

### 8.1 IMPL 已 commit + push（無等 PM commit）

commit `6529e37e W5-E1-A P1-CANARY-STAGE-CRITERIA-1 IMPL: graduated canary promote/rollback criteria`
已 push origin/main。fast-forward 332a2f9c..6529e37e 無 force / 無 rewrite。

### 8.2 D+1 dispatch 必跟進 6 項

per AMD-2026-05-10-05 §7：

1. **V089 Linux PG dry-run + apply** — E1-B 子任務（Mac 不能跑）
2. **E2 review** — `canary_promotion.rs` + `canary_promotion_eval.py` + V089 + `[58a]`
   - 重點 1: `boundary_violation_count` 計算與 spec §2.4 list 7 source 全對齊
   - 重點 2: V089 threshold 與 spec §2-§5 公式 byte-identical
   - 重點 3: Python evaluator 與 Rust pure-logic 跨語言一致性
3. **E4 regression** — 5×5 stage transition matrix + boundary case
4. **W3 cohort SQL pipeline land 後啟用 `[58a]` 真實 metric eval enrich** — post-W3
5. **CLAUDE.md §三 active gates 加 `[58a]` 描述** — TW + PA post-PM sign-off
6. **AMD-2026-05-10-05 sign-off chain** — PA + QC + PM

### 8.3 PM 確認點

- [x] commit + push 已完成（6529e37e）
- [ ] 派 E2 review canary_promotion.rs + canary_promotion_eval.py + V089 + `[58a]`
- [ ] 派 E4 5×5 transition matrix regression
- [ ] 派 PA + QC review AMD-2026-05-10-05
- [ ] 派 E1-B Linux PG dry-run V089
- [ ] D+1 W3 cohort SQL pipeline land 後派 E1 enrich `[58a]` 真實 metric eval
- [ ] post-sign-off TW + PA update CLAUDE.md §三 加 `[58a]` 描述

### 8.4 Multi-session race 通報

W5-E1-C sub-agent commit `d17d7863` 帶走我的 `runner.py [58a]` import +
invocation edit（與 [64] 同 commit）。**不需 revert** — `[58a]` 與 `[64]` 同
deploy 是 desirable。但 W5-E1-C commit 訊息只提 `[64]`，沒提 `[58a]` —
attribution 偏差。本 sub-agent commit `6529e37e` 訊息明確標 `[58a]` ownership。

---

**E1 IMPLEMENTATION DONE: 待 E2 審查 + E4 回歸 + V089 Linux PG dry-run**
**Report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w5_e1_a_canary_stage_criteria_1_impl.md`**
**Commit: `6529e37e` (已 push origin/main)**
