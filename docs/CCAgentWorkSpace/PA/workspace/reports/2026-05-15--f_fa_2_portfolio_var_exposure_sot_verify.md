# PA · F-FA-2 portfolio_var exposure SoT verify

**Date**：2026-05-15
**Author**：PA (Track A3 Wave 1)
**Scope**：read-only verify · F-FA-2（FA verdict §二 #16 CONDITIONAL）pre-IMPL gate
**Triggered by**：Operator dispatch / EDGE-P2-3 Phase 1b close-maker-first AMD-2026-05-15-02 IMPL Prereq #5
**Source verdicts read**：
- `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md`
- `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md`
- `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md`

**Hard constraints honored**：read-only · 無 IMPL · 無 sub-agent · 唯一 commit = 本 report。

---

## §1 驗證範圍 + 來源檔案清單

### Scope（按 dispatch §「驗證 questions」5 條）

| Q | 主題 | 結論摘要 |
|---|---|---|
| Q1 | portfolio_var calculator qty source | **NO portfolio_var 模塊存在**；最接近 = `compute_correlated_exposure_pct` + `compute_exposure_pct` 共用 PaperPosition.qty(filled) — see §2 |
| Q2 | correlation gate qty source | 同 Q1 SoT；**risk_config.correlation.max_pairwise_r 在 intent_processor 路徑為 dead config** — see §3 |
| Q3 | entry-side resting maker baseline | entry path 與 close path 用 **同一** SoT — see §4 |
| Q4 | partial cancel race | Paper resting all-or-nothing；exchange cum_filled_qty 獨立但不入 paper_state portfolio 計算 — see §5 |
| Q5 | paper_state vs exchange close path consistency | **完全一致**（同函數同 SoT）— see §6 |

### 來源檔案 + 行號

關鍵 source code：
- `srv/rust/openclaw_engine/src/risk_checks.rs:99-183` — `PositionCheck` + `check_order_allowed()` 入口（接 caller pre-computed exposure）
- `srv/rust/openclaw_engine/src/risk_checks.rs:137-138` — `is_reducing → return PositionCheck::allow()`（reducing 永遠 bypass）
- `srv/rust/openclaw_engine/src/intent_processor/mod.rs:761-775` — `compute_exposure_pct()` 唯一定義（Σ p.qty × price / balance）
- `srv/rust/openclaw_engine/src/intent_processor/mod.rs:788-805` — `compute_correlated_exposure_pct()` 唯一定義（max(long_notional, short_notional) / balance）
- `srv/rust/openclaw_engine/src/intent_processor/router.rs:261-265` — paper path `is_reducing` 判定（用 PaperPosition.qty）
- `srv/rust/openclaw_engine/src/intent_processor/router.rs:438-450` — paper path Gate 2.7 caller
- `srv/rust/openclaw_engine/src/intent_processor/router.rs:752-756` — exchange path `is_reducing` 判定（用 PaperPosition.qty）
- `srv/rust/openclaw_engine/src/intent_processor/router.rs:904-916` — exchange path Gate 2.7 caller
- `srv/rust/openclaw_engine/src/paper_state/containers.rs:18-86` — `PaperPosition.qty` 是 filled qty
- `srv/rust/openclaw_engine/src/paper_state/accessor.rs:184` — `pub fn positions()` 唯一 accessor，僅 return PaperPosition
- `srv/rust/openclaw_engine/src/paper_state/resting_orders.rs:261-298` — `RestingLimitOrder` struct（已含 request `qty: f64`）
- `srv/rust/openclaw_engine/src/config/risk_config.rs:125` — `pub correlation: Correlation` field 存在於 RiskConfig
- `srv/rust/openclaw_engine/src/config/risk_config_advanced.rs:321-346` — `Correlation { max_pairwise_r, window_minutes }` schema
- `srv/rust/openclaw_engine/src/tick_pipeline/pipeline_config.rs:56-66` — historical `max_correlation` field on GuardianConfig 已被刪除（dead code 註釋）

控制路徑 grep 結果（read-only verify）：
- `grep "portfolio_var" rust/openclaw_engine/src/` → **0 結果**
- `grep "request_qty" rust/openclaw_engine/src/` → 只在 `agent_spine/contracts.rs:246/runtime_shadow/mod.rs:219` 命中（observability lineage 用，**非** risk gate input）
- `grep "max_pairwise_r" rust/openclaw_engine/src/` → 只在 `risk_config*.rs` schema 與 test 命中，無任何 risk_checks / intent_processor caller

---

## §2 portfolio_var calculator qty source — finding

### Finding：**NEEDS-FIX (P1) · 但 framing 比 FA 提的更深**

**真實 SoT 唯一定義**（`intent_processor/mod.rs:761-805`）：

```rust
fn compute_exposure_pct(paper_state: &PaperState) -> f64 {
    let balance = paper_state.balance();
    if balance <= 0.0 { return 0.0; }
    let total_notional: f64 = paper_state
        .positions()                                   // ← Vec<&PaperPosition>，僅 filled
        .iter()
        .map(|p| {
            let price = paper_state.latest_price(&p.symbol).unwrap_or(p.entry_price);
            p.qty * price                              // ← p.qty = PaperPosition.qty (filled)
        })
        .sum();
    (total_notional / balance * 100.0).min(999.0)
}

fn compute_correlated_exposure_pct(paper_state: &PaperState) -> f64 {
    let balance = paper_state.balance();
    if balance <= 0.0 { return 0.0; }
    let mut long_notional = 0.0_f64;
    let mut short_notional = 0.0_f64;
    for p in paper_state.positions() {                 // ← 同樣只迭代 filled
        let price = paper_state.latest_price(&p.symbol).unwrap_or(p.entry_price);
        let notional = p.qty * price;                  // ← 同樣 PaperPosition.qty (filled)
        if p.is_long { long_notional += notional; }
        else         { short_notional += notional; }
    }
    (long_notional.max(short_notional) / balance * 100.0).min(999.0)
}
```

**結論明確**：
1. **SoT = `PaperPosition.qty`**（`paper_state/containers.rs:18-21`），這是 **filled qty**（accumulated by fill events，per `event_consumer/loop_exchange.rs:192` `po.cum_filled_qty += exec_qty`）
2. **完全沒有讀 `paper_state.resting_orders`**（即未填的 maker pending）
3. **沒有 `portfolio_var` 模塊**；FA verdict 用「portfolio_var」是 framing word，實際對應的是 `compute_exposure_pct` + `compute_correlated_exposure_pct` 兩個 helper

### FA framing 重要修正（PA 對抗性核驗）

FA verdict §二 #16 寫「maker pending 期間 portfolio risk 會被 **under-estimate**」。PA 發現實際方向**取決於 close 還是 open scenario**：

| Scenario | 實際方向 | 解釋 |
|---|---|---|
| **新 close maker pending（同 symbol）對 close intent 自身** | N/A | `is_reducing=true → check_order_allowed line 137 直接 allow`，**根本不觸 portfolio gate** |
| **新 close maker pending（symbol A）對 後續 NEW open intent（symbol B）** | **OVER-estimate**（不是 under）| symbol A 仍有 PaperPosition.qty=full（close pending 未 fill），於是 portfolio long_notional 含 A full → symbol B open 計算的 correlated exposure 偏高 → entry 可能被誤拒 |
| **新 entry maker pending（symbol B）對 後續 NEW open intent（symbol C）** | **UNDER-estimate**（FA 方向）| symbol B PaperPosition.qty 還是 0（entry pending 未 fill），portfolio 計算把 B 當 0 → symbol C 評估時 portfolio 偏低 → entry 可能被誤准 |

**FA 的 risk 核心成立**（risk view 不準），但 close-maker-first 對 entry 拒絕誤判的方向**反了**。真正 under-estimate 風險來自 entry-side resting（已實裝），close-side resting 是 over-estimate。

### Finding 等級

**NEEDS-FIX (P1)** — 不是 close-maker-first 引入的新問題，而是 **Phase 1B-4.2 entry-side resting maker landing 時就已存在的 systemic gap**。close-maker-first IMPL 會擴大此 gap 的暴露面（更多 pending orders simultaneously alive），但 root cause 是 portfolio gate 不感知 resting_orders。

---

## §3 correlation gate qty source — finding

### Finding：**RiskConfig.correlation 是 DEAD config in intent path**

**證據**：
1. `risk_config.rs:125` 定義 `pub correlation: Correlation`
2. `risk_config_advanced.rs:321-346` 定義 schema `Correlation { max_pairwise_r ∈ [0,1], window_minutes }`
3. `risk_config_tests.rs:197-199` validate test 存在
4. **grep `max_pairwise_r` outside `config/`+`tests/` → 0 callers in intent_processor / risk_checks**
5. `tick_pipeline/pipeline_config.rs:56-66` dead-code 註釋明示：

   > "dead `max_correlation` field on GuardianConfig was deleted"
   > 「死欄位 max_correlation 已刪除」

**結論**：
- intent_processor **沒有獨立的 pairwise correlation gate**
- 唯一 portfolio-level "correlation" gate = `correlated_exposure_max_pct`（透過 `compute_correlated_exposure_pct` 實現的「max(long, short) / balance」proxy）
- 與 FA framing 提到的「correlation gate」對應 **僅是 §2 的 `compute_correlated_exposure_pct`**，不是真實的 pairwise r matrix
- `scanner/scorer.rs:495` 的 `apply_correlation_filter` 是 **scanner 階段** 的 BTC-beta sector cap 邏輯，**與 intent_processor risk gate 無關**

**SoT 結論**：correlation gate 與 portfolio_var 共用同一 SoT（§2 結論完全適用）。**`max_pairwise_r` 是 dead config，建議併入 §8 fix scope**：要嘛接線、要嘛刪除 schema 防混淆。

---

## §4 entry-side resting maker baseline 對照

### Finding：**entry path 與 close path 用同一 broken SoT**

兩個 caller 完全對稱（`router.rs:438-450` paper path / `router.rs:904-916` exchange path）：

```rust
let exposure_pct = Self::compute_exposure_pct(paper_state);
let daily_loss = self.daily_loss_pct(balance);
let check_result = check_order_allowed(
    final_qty,
    price,
    balance,
    exposure_pct,                                              // ← §2 SoT
    Self::compute_correlated_exposure_pct(paper_state),        // ← §2 SoT
    Self::compute_leverage(paper_state),                       // ← compute_exposure_pct/100
    daily_loss,
    is_reducing,
    &self.risk_config,
);
```

**Critical baseline 結論**：
- entry-side resting maker **已實裝於 Phase 1B-4.2**（`paper_state/resting_orders.rs` line 261-298），但 entry resting 的 `RestingLimitOrder.qty` **不被 portfolio gate 讀**
- close-maker-first 不是 regression — 它 mirror entry 的設計，**繼承相同 gap**
- AMD-2026-05-15-02 §7 #16 的「mirror entry」設計**技術上等價**，但 mirror 的是「broken baseline」

### 對 IMPL 設計的暗示

如果 close-maker-first IMPL **必須 mirror entry baseline**（即不要單獨修 fix），則 §二 #16 CONDITIONAL 可降為 ACCEPTED — close path 不引入新 risk vector，systemic gap 屬另案 P1（建議獨立 ticket）。

---

## §5 partial cancel race 行為 — finding

### Finding：**Paper resting 為 all-or-nothing，無 partial cancel race；exchange-side partial 邏輯不入 portfolio**

**Paper 側證據**（`paper_state/resting_orders.rs:64-89`）：
```rust
pub enum RestingSweepAction {
    Keep,
    FillFull,        // 100% 一次成交
    FillPartial,     // 註釋 line 80：「紙盤全有/全無：heads → FillFull; tails → Keep」
    Timeout,
}
```
`FillPartial` 變體存在但 sweep 端 binary 處理（`resting_partial_fill_heads()` 50/50 coin flip → 全成交 or 不成交，沒有真實 partial qty）。`schema.filled_qty` 是 future extension（bias guard #2），1B-4 不啟用。

**Exchange 側獨立**（`event_consumer/loop_exchange.rs:192-251`）：
- `po.cum_filled_qty += exec_qty` 在 PendingOrder 上累計
- `fully_filled = po.cum_filled_qty >= po.qty * 0.999`
- 但 PendingOrder（exchange tracker）**不影響** `paper_state.positions()`；只有 fully_filled 後才 emit close fill 進 paper_state

**Cancel race 行為**（exchange-side）：
- 在 fully_filled 之前所有 partial fill 都會增 PendingOrder.cum_filled_qty
- 但 `paper_state.positions()` 在這段期間反映 **舊 entry full qty**（沒減）
- 一旦 cancel 發生（Bybit cancel + ack） → engine 不會 update PaperPosition.qty 因為對 paper view 來說沒事發生
- 真實 fully_filled 會 emit fill event → 此時 PaperPosition.qty 才減

**對 portfolio gate 的影響**：
- Phase 1B-4 關注 paper-only resting；exchange 的 cum_filled_qty 部分填仍未在 paper_state portfolio 計算內反映
- close-maker-first **paper-only** scope 下，partial cancel race 不存在
- **如果未來把 close-maker-first 推到 exchange path**，paper_state portfolio gate 會持續 over-estimate（直到 close fully filled 才減）— 但這是 Phase 1B-4 之後的 scope

### Finding 等級

**P2 (advisory)** — close-maker-first paper-only IMPL 不暴露此 race；exchange path 推 close-maker-first 的 future Phase 才需處理。

---

## §6 paper_state / resting_orders 與 exchange close path exposure 計算一致性

### Finding：**完全一致 — 兩 path 共用同函數同 SoT**

對比 `router.rs:438-450` (paper) vs `router.rs:904-916` (exchange)：
- 都呼叫 `Self::compute_exposure_pct(paper_state)`
- 都呼叫 `Self::compute_correlated_exposure_pct(paper_state)`
- 都呼叫 `Self::compute_leverage(paper_state)`
- 都用 `is_reducing` flag 走 `paper_state.get_position()` 比對 `is_long`

**Confirmed**：consistency = YES。但兩 path 都繼承同一 systemic gap（§2 結論完全適用）。

**唯一差異**：
- exchange path 多 `DuplicatePosition` rejection（同向開倉時直接拒，paper path 只有 reducing 邏輯）
- exchange path 有 `BLOCKER-3 D15: cross-engine global notional cap` check（同樣存在於 paper path）
- 兩者均不影響 portfolio gate SoT 結論

---

## §7 結論：§二 #16 CONDITIONAL → 處置

### Verdict：**CONDITIONAL → MAINTAIN**（不解除，但 carve out scope）

**理由**：
1. close-maker-first IMPL 本身**不引入新 portfolio risk vector** — entry-side resting maker（Phase 1B-4.2 已 land）已存在同一 gap
2. fix 範圍**遠超 close-maker-first 設計** — 是 portfolio gate 全面 retrofit（read resting_orders + 計算 effective notional）
3. 強制 close-maker-first 等待 portfolio fix 完成 = 不必要 block

### 三選項供 PM 裁決

**選項 A（PA 推薦）**：
- close-maker-first §二 #16 從 CONDITIONAL **降為 ACCEPTED-WITH-CARVE-OUT**
- 開新 P1 ticket `P1-PORTFOLIO-RESTING-EXPOSURE-1`（scope 見 §8）
- close-maker-first IMPL 與此 P1 ticket 解耦平行；close-maker-first 不阻 ticket，ticket 不阻 close-maker-first
- 對應 healthcheck 加一條 `[58] portfolio_resting_exposure_lineage`（passive monitor over_estimate / under_estimate magnitude）

**選項 B（保守）**：
- 維持 CONDITIONAL；close-maker-first IMPL prereq 必含 portfolio fix
- 新 ticket 設計 + IMPL + E2 + E4 + healthcheck → 估 +2~3 sprint days，close-maker-first 同步延後

**選項 C（激進）**：
- 解除 CONDITIONAL → ACCEPTED；不開 ticket，視為 known-acceptable risk
- **PA 反對**：systemic gap 在 LG-5 Constrained Live 階段會放大（live 多 symbol 真實 portfolio 對沖場景），不可後期再修

### 升級到 P1 fix 的判定依據

如果 PM 採選項 A 或 B，新 ticket scope 寫入 §8。

---

## §8 P1 fix scope 建議（如 PM 採納）

### Ticket title
**P1-PORTFOLIO-RESTING-EXPOSURE-1** — portfolio_var / correlated_exposure 計算包含 resting_orders effective notional

### 建議 fix scope

#### 改動文件（read-only PA proposal）

| 檔案 | 改動類型 | 估 LOC |
|---|---|---|
| `rust/openclaw_engine/src/intent_processor/mod.rs:761-805` | 修改 `compute_exposure_pct` + `compute_correlated_exposure_pct` 加 resting_orders 累計 | ~40 LOC（含註釋）|
| `rust/openclaw_engine/src/intent_processor/mod.rs` | 新增 helper `compute_effective_long_short_notional(paper_state)`（DRY 用）| ~30 LOC |
| `rust/openclaw_engine/src/intent_processor/tests.rs` | 4 新測試：(1) entry resting only / (2) close resting only / (3) entry+close mixed / (4) is_long-aware netting | ~120 LOC |
| `rust/openclaw_engine/src/paper_state/accessor.rs` | 新增 `pub fn resting_orders_iter() -> impl Iterator<...>`（如 accessor 不 expose）| ~10 LOC |
| `helper_scripts/db/passive_wait_healthcheck.py` | 新增 `check_portfolio_resting_exposure_lineage()` healthcheck `[58]` | ~50 LOC |

**總計估 LOC**：~250

#### 設計要點

1. **Effective notional formula**：
   ```
   for each symbol:
       filled_long  = Σ PaperPosition.qty × price (where is_long=true)
       filled_short = Σ PaperPosition.qty × price (where is_long=false)
       resting_long_pending  = Σ RestingLimitOrder.qty × limit_price (is_long=true)
       resting_short_pending = Σ RestingLimitOrder.qty × limit_price (is_long=false)

       # close maker pending 應 net out 既有 filled position（同 symbol 反向 resting = 預期 close）
       effective_long_notional  = filled_long + resting_long_pending
       effective_short_notional = filled_short + resting_short_pending

       # 但若 close intent: 對 portfolio 的 "對沖估計" 應 already-pending close 計入 reduce
       # → 進階：netting 邏輯（symbol level）：對同 symbol 的 close pending 從 same-side filled 扣減
   ```
   實際公式 PA/E1 設計時細審；保守版 = sum without netting（仍 over-estimate 但比現狀好）；激進版 = symbol-level netting。

2. **Behavior change**：
   - over-estimate scenarios（close pending）→ correlated_exposure 偏高 → 可能拒絕更多 entry → 行為**更保守**（符合原則 5/6）
   - under-estimate scenarios（entry pending）→ correlated_exposure 偏高 → 同上
   - **唯一 risk regression**：partial fill scenarios 暫時 over-count（exchange path），需 healthcheck 監控

3. **Backward compat**：
   - `correlated_exposure_max_pct` config 不變
   - `is_reducing → allow` 短路邏輯不變（reducing 仍 bypass 全 gate）
   - 只改 caller pre-compute 階段

#### 估工時

- PA 設計細化：0.5d（PA decide netting 策略）
- E1 IMPL：1d
- E2 review：0.5d
- E4 regression（含新 4 tests）：0.5d
- A3+E2 對抗性核驗（feedback_impl_done_adversarial_review.md 強制）：0.5d
- 總計：**3 person-day**

#### 是否阻 IMPL prereq #5

**選項 A**：**不阻**（close-maker-first IMPL 與此 P1 ticket 平行）
**選項 B**：**阻**（IMPL prereq #5 解除前必完成此 ticket）
**選項 C**：**N/A**（CONDITIONAL 解除）

#### E1 worktree 並行可能

- 可單一 E1 完成（範圍小、文件少、無跨模塊副作用）
- 不需要 isolation worktree
- 估 1d IMPL（單線程 E1 task）

---

## §9 副作用識別清單（PA 對抗性自審）

對 §8 fix scope 提問：

1. **是否其他模塊 import 了這個函數？**
   - `compute_exposure_pct` / `compute_correlated_exposure_pct` 是 `intent_processor/mod.rs` 私有 fn（`fn`，非 `pub fn`），僅被 `intent_processor/router.rs` 同 crate 使用
   - 無外部 import 風險
2. **改動的函數在哪些測試中被 mock？**
   - `risk_checks.rs:467-1027` 27 個 unit test 直測 `check_order_allowed` 用 hardcoded exposure 數字（不 mock helper），不受影響
   - `intent_processor/tests.rs` + `tests_predictor_router.rs` 1585+1489 行 — 需 grep `compute_exposure_pct` / `compute_correlated_exposure_pct` 命中數，PA 暫不在 read-only scope 完整審；E1 IMPL 時必審
3. **是否涉及 asyncio/threading 混用邊界？**
   - 不涉及（純 sync fn 在 router hot path 同步呼叫）
4. **是否改動 API response schema？**
   - 不改（純內部風控 gate 邏輯）
5. **是否觸 RustEngine ↔ Python IPC schema？**
   - 不觸（純 Rust hot path 內部）

**副作用評級**：**LOW**（IMPL risk 可控）。

## §10 § 二 16 條根原則合規快速核對（PA 對抗性自審）

| # | 原則 | 影響 |
|---|---|---|
| 4 | 策略不能繞過風控 | fix 強化此原則（pending orders 不再隱藏於 gate 視野） |
| 5 | 生存 > 利潤 | 行為更保守（over-estimate 偏向拒絕 entry），符合 |
| 6 | 失敗默認收縮 | 同上，符合 |
| 8 | 交易可解釋 | healthcheck `[58]` lineage 強化可審計，符合 |
| 11 | Agent 最大自主權 | 不影響 P0/P1 硬邊界，僅修正既有風控視角 |
| 16 | 組合級風險意識 | 直接強化此原則（從 broken baseline → effective notional） |

**硬邊界檢查**（CLAUDE.md §四）：
- 不觸 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json`
- 不觸 lease 授權邏輯
- 不觸 H0 Gate 主路徑

**全 GREEN**。

---

## §11 PA verdict 與下一步

### Verdict
- **§2 Q1**：portfolio_var SoT = `compute_correlated_exposure_pct + compute_exposure_pct` (PaperPosition.qty filled only)；**NEEDS-FIX P1**
- **§3 Q2**：correlation gate SoT 同 §2；`max_pairwise_r` config 是 dead；**NEEDS-FIX P1**（建議併入同 ticket 處理）
- **§4 Q3**：entry baseline 同 close path → mirror 設計合理但繼承 broken baseline
- **§5 Q4**：partial cancel race 在 paper-only scope 不存在；exchange future scope P2
- **§6 Q5**：paper / exchange path consistency = YES，但都繼承同一 gap

### §二 #16 處置建議
**選項 A（推薦）**：CONDITIONAL → ACCEPTED-WITH-CARVE-OUT；新開 `P1-PORTFOLIO-RESTING-EXPOSURE-1` ticket 與 close-maker-first IMPL 平行。

### 給 PM 的下一步

1. PM 裁決選項 A/B/C（單行 verdict 即可）
2. 若採 A：
   - PM 在 TODO.md 新增 ticket `P1-PORTFOLIO-RESTING-EXPOSURE-1`（estimated 3d）
   - 更新 AMD-2026-05-15-02 §7 #16 verdict（CONDITIONAL → ACCEPTED-WITH-CARVE-OUT，引此 PA report）
   - 更新 AMD §8 IMPL Prereq #5 文字（F-FA-2 verify done → ticket 解耦並行）
   - close-maker-first IMPL kickoff 不必再等 portfolio fix
3. 若採 B：
   - close-maker-first IMPL 凍結至 ticket 完成
   - 新 ticket 走標準 E1+E2+E4+A3 流程
4. 若採 C：
   - PA 不簽署（理由見 §7 選項 C「PA 反對」）

### 不在本 report scope（dispatch §「不在你 scope」對齊）
- AMD v0.2 / spec v1.1 patch（Track A1 PA 並行）
- F-FA-3 guard tests 設計（Track A4 PA 並行）
- V094 migration spec（Wave 2）
- IMPL（IMPL prereq 全解後 E1 做）

---

**PA DESIGN DONE**：report path：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_2_portfolio_var_exposure_sot_verify.md`
