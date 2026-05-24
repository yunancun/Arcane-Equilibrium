---
report: cost_gate cell-level DENY 兩階段修復(EDGE-DIAG-2 PM RCA + MIT sensitivity sweep)
date: 2026-05-23
author: E1 (Backend Developer, Rust + Config)
phase: PM RCA 完成 → E1 IMPL DONE → 待 E2 review
status: IMPL DONE — 待 E2 review
parent dispatch:
  - operator prompt 2026-05-23(PM + MIT + PA 拍板)
runtime: Mac development(cargo check 通過)
production engine: 未碰 / 不 rebuild
---

# E1 cost_gate cell-level DENY 兩階段修復 — 2026-05-23

## §0. TL;DR

PM + MIT + PA 拍板兩階段修復 `cost_gate_moderate_with_slippage` 對 low-sample 深負 cell 的放行漏洞。NEARUSDT(n=18, shrunk_bps=-16.46)6 天累損 -21.98 USD demo 案例觸發。兩 atomic commit 落地:

| # | Commit | File | LOC | 性質 |
|---|---|---|---|---|
| 1 | `718c1ddd` | `settings/risk_control_rules/risk_config_demo.toml` | +3 / -1 | TOML threshold 30→15 |
| 2 | `188f244a` | `rust/openclaw_engine/src/intent_processor/gates.rs` | +23 | Rust 加 low-sample 深負 arm |

`cargo check -p openclaw_engine`: **PASS** (9.15s, 0 new warning)
不跑 full test(E4 後續)/不 rebuild(Phase B 才做)/不 push(等 E2 review)。

## §1. 任務背景

- **Root cause** (PA RCA 已完成):`gates.rs:130-143` `cost_gate_moderate_with_slippage` low-sample arm 對 `n_trades < min_n` cell 直接 `None`(放行) → NEARUSDT(n=18, shrunk_bps=-16.46)在 noise band 內持續放行,6 天累損 -21.98 USD demo。
- **兩階段修復設計**(MIT sensitivity sweep 拍板):
  - 步驟 1:TOML `cost_gate_min_n_trades_for_block` 30→15(NEARUSDT n=18 跨入 robust arm → robust arm 既有 negative-bps deny 邏輯生效)
  - 步驟 2:Rust 加 low-sample 深負 arm,n<min_n 且 shrunk_bps<-15.0 直接 deny(防未來新 cell 在 n=5~14 累深負)
- **Cutoff `-15.0 bps` 由 MIT sweep 拍板**:
  - cross-validation 50% 命中率顯示 [-15, 0) 是 noise band(grid_trading OPUSDT shrunk -10.88 卻 7d 賺 +32.58)
  - deep tail < -15 才方向可靠
  - 1B funding_arb 框架僅 LABUSDT outlier 被影響;6 個 funding_arb cell 繼續收 EDGE-DIAG-2 樣本

## §2. Commit 1 — TOML threshold 30→15

### 2.1 改動

`srv/settings/risk_control_rules/risk_config_demo.toml` line 314 附近:

```diff
 # EDGE-DIAG-2（2026-04-28）：demo cost_gate_moderate 對 n_trades<30 的負 edge cell
 # 走探索模式（放行+log）而非阻擋。Live 不受影響。觀察後可調高（50/100）。
-cost_gate_min_n_trades_for_block = 30
+# EDGE-DIAG-2 探索期門檻 30→15(2026-05-23 PM RCA + MIT sensitivity sweep)
+# 配合 gates.rs 新 low-sample 深負 arm 防 NEARUSDT 類 cell 累損
+cost_gate_min_n_trades_for_block = 15
```

### 2.2 注釋處理

per `feedback_chinese_only_comments` 2026-05-05「觸及的注釋移除英文只保留中文,未觸及的鄰近注釋不主動清」:
- **未動**:line 308-313 既有 EDGE-DIAG-2 (2026-04-28) 5 行中英對照 doc(未觸及不主動清)
- **新增**:line 314-315 純中文 2 行 inline 注釋(觸及 → 默認中文)
- 最小影響原則,保歷史 trace 不擾動 reviewer 視角

### 2.3 commit message

```
config(demo): cost_gate_min_n_trades_for_block 30→15

EDGE-DIAG-2 探索期門檻調整。MIT sensitivity sweep(2026-05-23)確認:
- NEARUSDT (n=18, shrunk_bps=-16.46) 跨入 robust arm 觸發 negative-bps deny
- 連帶 catch PENGUUSDT (n=28) / ZECUSDT (n=27) / FARTCOINUSDT (n=24)
- 1B funding_arb 框架影響極小(僅 LABUSDT outlier)

ref: PM RCA 2026-05-23 / MIT sensitivity sweep
```

## §3. Commit 2 — Rust gates.rs low-sample 深負 arm

### 3.1 改動位置

`srv/rust/openclaw_engine/src/intent_processor/gates.rs` `cost_gate_moderate_with_slippage` 函式 line 130 之前(既有 unconditional low-sample arm 之前)。

### 3.2 新 arm 內容

```rust
// EDGE-DIAG-2 補:即使 low-sample,當 shrunk_bps 落在
// crypto 結構性 noise band 以下(< -15 bps),不放行;
// 避免 cell 在 noise band 內累損直到跨 min_n。
// cutoff 由 MIT sensitivity sweep 拍板(2026-05-23):
//   - cross-validation 50% 命中率顯示 [-15, 0) 是 noise band
//   - deep tail < -15 才方向可靠
//   - 1B funding_arb 框架僅 LABUSDT outlier 被影響
Some(cell) if cell.n_trades < min_n && cell.shrunk_bps < -15.0 => {
    tracing::info!(
        strategy,
        symbol,
        shrunk_bps = cell.shrunk_bps,
        n_trades = cell.n_trades,
        cutoff_bps = -15.0,
        "cost_gate(JS-demo): low sample but deep-negative — block / 低樣本深負阻擋"
    );
    return Some(ExchangeGateResult::rejected(
        RejectionCode::CostGateJsDemoNegative {
            estimated_bps: cell.shrunk_bps,
        }
        .format(),
    ));
}
```

### 3.3 Arm 順序驗證

```
match self.edge_estimates.get_cell(strategy, symbol) {
    Some(cell) if cell.n_trades < min_n && cell.shrunk_bps < -15.0 => { ... DENY ... }  ← 新 arm (line 130-152)
    Some(cell) if cell.n_trades < min_n => { ... 探索模式 None ... }                     ← 既有 (line 153-167)
    Some(cell) if cell.shrunk_bps > 0.0 => { ... threshold check ... }                  ← 既有
    Some(cell) => { ... robust 負 → deny ... }                                          ← 既有
    None => { ... cold-start 放行 ... }                                                  ← 既有
}
```

**Rust pattern match 短路順序對**:新 arm 在 unconditional `n_trades < min_n` 之前 → 深負子集優先觸發 deny,普通 low-sample fallback 到探索模式。若放後面會被前面 unconditional arm 吃掉(0 效果)。

### 3.4 RejectionCode variant 復用

`CostGateJsDemoNegative { estimated_bps: f64 }` variant 存在於 `rejection_coding.rs:111`,既有 robust arm (L165-174) 已使用同 variant + 同 format。本次新 arm 不引新 variant,只 1 field `estimated_bps`,完整復用 → 不 cascade 動 `rejection_coding.rs` 5 處 (line 111/219/286/343/494)。

### 3.5 commit message

```
feat(gates): cost_gate_moderate 加 low-sample 深負 arm (cutoff=-15bps)

防止 cell 在 noise band 內累損直到跨 min_n_trades_for_block 門檻
(NEARUSDT 案例:n=18 累積 -21.98 USD demo 6 天)。

新 arm 在 cost_gate_moderate_with_slippage 中,當:
  cell.n_trades < min_n AND cell.shrunk_bps < -15.0 bps
直接 deny via CostGateJsDemoNegative。

cutoff -15.0 由 MIT sensitivity sweep 確認:
- cross-validation 顯示 [-15, 0) 是 noise band(50% 方向命中率)
- < -15 deep tail 方向可靠
- 不影響 1B funding_arb 探索(僅 LABUSDT outlier 被 deny)

不動 cost_gate_paper / cost_gate_live。

ref: PM RCA 2026-05-23 / MIT sensitivity sweep
```

## §4. cargo check 結果

```bash
cd srv/rust && cargo check -p openclaw_engine
```

| Verify | Result |
|---|---|
| `cargo check -p openclaw_engine` | **PASS** — 9.15s |
| 本 patch 新 warning | **0** |
| Pre-existing warning(3 條,與本 patch 無關) | `unused import LEAD_WINDOW_SECS_MAIN` (panel_aggregator/btc_lead_lag/db_writer.rs:13) / `make_intent dead_code` (strategies/ma_crossover/helpers.rs:26) / `spawn_position_reconciler dead_code` (tasks.rs:749) |
| Finished profile | `dev` (unoptimized + debuginfo) |

**結論**:cost_gate 修改編譯通過,0 type error / 0 borrow check error / 0 lifetime issue。E4 後續跑 full `cargo test --release` regression。

## §5. 修改清單

| File | 性質 | 改動 LOC | 摘要 |
|---|---|---|---|
| `settings/risk_control_rules/risk_config_demo.toml` | edit | +3 / -1 | line 314 `cost_gate_min_n_trades_for_block = 30 → 15` + 2 行中文 inline 注釋 |
| `rust/openclaw_engine/src/intent_processor/gates.rs` | extend | +23 | `cost_gate_moderate_with_slippage` 新增 low-sample 深負 arm(深負優先 deny) |

**不動 file**(per dispatch §禁忌):
- `gates.rs` `cost_gate_paper` (L14)
- `gates.rs` `cost_gate_live` (L203)
- `settings/risk_control_rules/risk_config_live.toml`
- `settings/risk_control_rules/risk_config_paper.toml`
- `intent_processor/router.rs`
- `intent_processor/mode_state.rs`
- `intent_processor/edge_estimates.rs`
- `intent_processor/rejection_coding.rs`(variant 復用,不擴新 variant)
- `config_manager.rs` / ArcSwap loader

## §6. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / live TOML / production engine ✓ |
| **§七 Code And Docs Rules** | 新代碼注釋全中文(per `feedback_chinese_only_comments` 2026-05-05);觸及既有 bilingual block 不主動清;無 emoji ✓ |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 review;不自行 commit push;不派下游 sub-agent ✓(注:本 task 已 commit local 2 atomic,per dispatch 明示「不 push 等 E2 review」;E2 PASS + E4 regression PASS 後 PM 統一 push) |
| **§九 Code Structure Guardrails** | `gates.rs` 264→287 LOC(< 800 OK);無業務邏輯擴張 |
| **AC-5 production binary 0 mock time** | 未引 mock_instant / tokio::time::pause / spike feature ✓ |
| **反模式對齊** | (a) 不擴 scope(僅 2 file 改動)✓ / (b) 不動 cost_gate_paper / live / paper TOML / live TOML ✓ / (c) 不加 blocked_symbols ✓ / (d) 不 propose atr_stop_mult ✓ / (e) 不設計新 architecture ✓ / (f) 不動 ArcSwap loader ✓ / (g) 不 rebuild engine ✓ / (h) 中文為主 0 emoji ✓ |

## §7. 不確定之處

1. **MIT cutoff -15.0 hardcoded vs TOML knob**:本 patch 將 cutoff hardcoded 在 Rust arm guard `cell.shrunk_bps < -15.0`,而非寫入 TOML。設計權衡:
   - **hardcoded 優點**:cutoff 是「noise band 邊界」概念屬 Rust 邏輯而非 ops knob;與 `min_n` 樣本門檻職責分離
   - **TOML knob 優點**:未來 sensitivity sweep 重跑可調無需 rebuild
   - 本 patch 走 hardcoded(per dispatch 範例);若 PA / MIT 後續決定 cutoff 也應 TOML 化,可 follow-up patch 引入 `cost_gate_low_sample_deep_negative_cutoff_bps` knob
2. **funding_arb 1B 框架影響評估**:dispatch 已說明「僅 LABUSDT outlier 被 deny,保留 6 個 funding_arb cell」,但本 E1 IMPL 未獨立驗證 funding_arb cell 的 shrunk_bps 分布;依賴 MIT sweep 結論
3. **cargo full test 未跑**:per dispatch「不需跑 full test suite(E4 後續做)」;cargo check 9.15s PASS 守 type/borrow 一致;E4 regression 期跑 `cargo test --release` 全套 + spike 一致性

## §8. Operator 下一步

1. **PM 派 E2 review**:focus on
   - Rust arm 順序(新 arm 在既有 unconditional arm 之前是 short-circuit 關鍵)
   - `CostGateJsDemoNegative` variant 復用是否對齊既有 robust arm L165-174 語意
   - TOML 注釋處理是否符合 `feedback_chinese_only_comments` 觸及/未觸及邊界
   - tracing::info! log fields 是否含 reviewer 需要的 audit 信息(shrunk_bps + n_trades + cutoff_bps)
2. **E4 regression**(E2 PASS 後):跑 `cargo test --release` 全套(預期 3961 PASS baseline)+ spike feature regression + nm scan AC-5
3. **PM 統一 commit chain**:E2 PASS + E4 regression PASS 後 PM push(per dispatch「不 push 等 E2 review」)
4. **Phase B deploy**:operator 後續 `restart_all --rebuild` 拉 engine pid 新 binary 才生效;本 patch 不觸發 deploy

---

**E1 IMPLEMENTATION DONE: 待 E2 審查 (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--cost_gate_cell_level_deny_fix.md`)**
