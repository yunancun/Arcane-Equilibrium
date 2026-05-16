# BB Short Re-Review — phys_lock Live Enable AMD DRAFT

**Date**: 2026-05-16
**Reviewer**: BB (Bybit Broker Compatibility Auditor)
**Subject**: `2026-05-XX-XX-phys-lock-live-enable-draft.md` v0.1 DRAFT
**Mode**: Short focused re-review（Bybit-side only；不重做 §三大 audit）
**HEAD**: dict v1.3 (28c571c7)；AMD DRAFT v0.1 (2026-05-16)
**Subject mapping**: 修改對象 = `risk_config_live.toml [exit]` 加 `missing_edge_fallback_bps = 10.0` override；live default `-10.0` 解除 → Gate 1 從永遠 Hold 變允許進 Gate 2-4
**Verdict**: **APPROVED-CONDITIONAL** — 1 must + 2 should + 0 dict update needed

> 註：BB agent read-only；本檔由主會話按 BB agent 返回原文存檔。

---

## §1 phys_lock fire 對 Bybit rate limit 評估

**Demo baseline 換算（per AMD §2.3）**：
- 86 fires / 7d / 25 sym ≈ **0.49 fire/symbol/day**
- live 25 sym × 30d ≈ **~370 fires/月** 預期觸發頻率
- 跨 5 策略總 fire rate 換算：370 / 30 / 24 / 3600 ≈ **0.000143 fire/s** sustained

**對應 Bybit Order group 累積分析**：
- BB W1+W2 2026-05-10 baseline: ~0.7 req/s sustained
- close-maker-first Phase 1b 增量（worst case 全 fallback to taker）: ~0.017 req/s
- phys_lock 啟用增量（per AMD assumption 370 fires/月 × 2 dispatch per fire avg = 1 cancel + 1 market re-dispatch worst case）: **0.000286 req/s**（負可忽略）
- 三者合計 sustained: **~0.72 req/s** vs Order group 20 req/s per UID cap = **3.6% 利用率**（96.4% 餘裕）
- 即使 25 sym 同時 fire burst：25 × 2 req / 5s = **10 req/s** vs 20 req/s = 50% 餘裕（per BB-MF-2 dynamic backoff Race D 已 cover）

**Verdict**: phys_lock 增量 fire rate 對 Bybit Order group rate budget **可忽略**（< 0.001 req/s sustained）；無 rate throttle / IP ban 風險。

---

## §2 phys_lock close path 與 close-maker-first 互動

**白名單兼容性**:
- AMD §2.2 positive whitelist 已含 `phys_lock_gate4_giveback` + `phys_lock_gate4_stale_roc_neg`
- 字典 §1.10.2 兩項 phys_lock_gate4 已 land
- 啟用 live phys_lock 後，phys_lock fire close → maker-first dispatch → Bybit PostOnly limit 合規

**Phase 1b initial cooldown 互動（per AMD-2026-05-15-02 v0.4 §11.2）**:
- per-symbol 5min 固定 cooldown 是 `reject_cooldown` split 升 P0 後的初始 IMPL
- phys_lock fire rate 0.49 fire/symbol/day << per-symbol 5min cooldown reset window；極不可能單 symbol 5min 內連續 phys_lock fire
- close maker reject → 5min cooldown 觸發 → 期間若再 phys_lock fire 走 fallback to taker market（per Race E）→ 仍 fail-closed 安全

**QC-MF-2 timeout 設計檢驗**:
- `phys_lock_gate4_giveback` timeout = 15000ms（不是 30000ms）+ buffer_ticks=1 + offset=0.5
- `phys_lock_gate4_stale_roc_neg` timeout = 10000ms + buffer=1 + offset=0.5
- 設計理由（QC-MF-2 footnote）：gate4 fire 時 peak ATR 已 surrender，下一秒 unfavourable drift 機率高於 random walk

**Verdict**: phys_lock close path 與 close-maker-first dispatch chain **完全相容**；whitelist 已 land；無新 dispatch risk。

---

## §3 Mainnet 啟用前置 7 條件覆蓋度

per BB round-2 §9 7 條（仍對 phys_lock Mainnet 啟用有約束）:

| # | 條件 | AMD DRAFT 覆蓋狀態 |
|---|---|---|
| 3.1 | 真實 fee rate verify | ❌ **MISSING** |
| 3.2 | rate_limit_remaining baseline | ❌ **MISSING** |
| 3.3 | IP whitelist | ❌ **MISSING** |
| 3.4 | EarnedTrust T0→T1 promote | ❌ **MISSING** |
| 3.5 | MAG-083/084 evidence chain | ✅ **CLOSED 2026-05-11**（per CLAUDE.md §三）|
| 3.6 | 24h mainnet smoke | ❌ **MISSING** |
| 3.7 | kill-switch 物理測試 | ⚠️ **PARTIAL** — AMD §6.1 hot rollback 設計 OK，但「物理測試」未明文要求 mainnet 驗 |

**結論**: AMD DRAFT §3 6 gates 重點放在 governance / statistical evidence，未含 Mainnet 啟用前置物理 / 合規 / infra 7 條。

**Verdict**: **MUST-FIX BB-PL-1** — AMD §3 必加 Gate 3.7 (Mainnet 7 prereq cross-ref，標「pending Phase 3 carve-out AMD」或 inline 補完)。

---

## §4 Demo vs Mainnet 行為差異

**phys_lock Gate 1-4 觸發條件對 endpoint 差異敏感性**:
- **Gate 1 (`missing_edge_fallback_bps`)**: 取自 internal edge_estimates state，**與 endpoint 無關** ✅
- **Gate 2 (`min_hold_secs ≥ 30`)**: 取自本地 position 時鐘，**與 endpoint 無關** ✅
- **Gate 3 (`min_peak_atr_norm ≥ 0.5`)**: 取自本地 ATR + peak tracking，**與 endpoint 無關** ✅
- **Gate 4 (`giveback_*` / `stale_roc_neg`)**: 取自本地 peak + ROC 計算，**與 endpoint 無關** ✅

**=> phys_lock fire 觸發機制本身對 demo vs mainnet endpoint 完全不敏感**。

**但 close path PostOnly dispatch + fill 行為對 endpoint 敏感**:
- demo 0 reject sample 可能是 demo silent degradation（per §4.3 第 14 條）
- 啟用 live phys_lock 後 live_demo (走 api-demo.bybit.com) 觀察的 close maker fill rate ≠ live mainnet
- AC-19 30% threshold + AC-15 reject sample healthcheck 已覆蓋此 gap

**Verdict**: phys_lock fire **觸發層 demo/mainnet 對稱**；fire close **dispatch 層** demo/mainnet 不對稱（已由現有 AC-15/19 + [65] healthcheck 覆蓋）。AMD §4.4 風險評估「Demo/Live Regime 行為對稱性假設風險 MEDIUM」結論 **partially correct**。

**ADVISORY**: AMD §4.4 「殘留風險 MEDIUM」可降為 LOW（phys_lock fire 觸發層）+ 引用 close-maker-first AMD 的 demo/mainnet drift gap。

---

## §5 Broker rebate / fee tier impact

**phys_lock 啟用後 close 路徑頻率變化**:
- 預期 370 fires/月 新增 close opportunity
- 若 30% maker fill rate × 370 fires × 30d/月 = ~111 maker fills 增量 + ~259 taker fallback 增量

**對 fee tier upgrade 影響**:
- per BB round-2 §4 已驗：OpenClaw 30d volume ≪ VIP 1 $1M threshold，維持 tier 0
- phys_lock 啟用 11% maker fill rate 增量對 30d maker ratio 影響：< 0.1pp（unmeasurable）
- **不會** trigger fee tier upgrade

**Broker rebate eligibility**:
- 30d volume threshold $10M
- phys_lock 增量 volume：370 fires × $300/fire × 1.0 = ~$111k/月 = **0.111% of $10M threshold/月**
- **不會** affect broker rebate eligibility

**Verdict**: phys_lock 啟用對 fee tier / broker rebate **可忽略**。無新 fee economics risk。

---

## §6 ToS / 地理 / 合規

**phys_lock 法律性質**:
- profit-protection logic = internal close timing optimization
- **不違反 anti-wash trading** / **不違反 spoofing** / **不違反 multi-account 規避** / **不違反 insider / front-running**

**Bybit changelog last 30d**: 字典 v1.3 已 sync；30d 0 breaking change

**地理 / KYC**: phys_lock 啟用不改變 operator KYC tier / 地區限制

**Verdict**: ToS / 地理 / 合規 **0 風險**。

---

## §7 Rollback path Bybit-side

**AMD §6.1 hot rollback design**:
- `risk_config_live.toml [exit] missing_edge_fallback_bps = -10.0`
- ArcSwap snapshot 1 tick 內生效
- next `compute_physical_decision()` invocation Gate 1 即回 fail-safe Hold

**已 in-flight 的 phys_lock close maker pending order 處理**:
- ArcSwap 是 **per-tick read-fresh** semantic
- rollback 時刻已 dispatch 的 pending PostOnly Limit close maker order：
  - **TOML rollback 不直接 cancel pending orders**（rollback 只關 future fire，不動 in-flight）
  - 已 dispatch 的 order 走既有 close-maker-first state machine：timeout (15s/10s per QC-MF-2) → Race E mandatory fallback to taker market → 成交
  - **Bybit-side impact**: pending order 自然 timeout 後 cancel + market re-dispatch；對 Bybit Order group rate budget = 額外 ~50 req 一次性 burst

**Engine shutdown / cancel_token rollback path**: reconciler 接手後對 Bybit pending orders 走既有 `bybit_sync` → cancel-all → close-position 序列

**Verdict**: rollback path 對 Bybit-side **設計正確**；無 rollback drift risk。

---

## §8 BB verdict

### **APPROVED-CONDITIONAL**

**整體判斷**: phys_lock Live Enable AMD DRAFT 從 Bybit-side 立場 **架構正確**；rate budget 餘裕（< 0.001 req/s 增量）；fire 觸發層 demo/mainnet 完全對稱；fee tier / broker rebate / ToS 0 風險；rollback path 設計合理。

**Confidence**: HIGH。

### Must-fix（必修補件）

**BB-PL-1**: AMD §3 必加 Gate 3.7 — **Mainnet 7 prereq cross-ref**：(a) 真實 fee rate verify / (b) rate_limit_remaining baseline / (c) IP whitelist / (d) EarnedTrust T0→T1 / (e) MAG-083/084 ✅ closed / (f) 24h mainnet smoke / (g) kill-switch 物理測試。

### Should-fix（強烈建議）

**BB-PL-2**: AMD §4.4 「Demo/Live Regime 行為對稱性假設風險 MEDIUM」應 split：
- phys_lock 觸發層（Gate 1-4）對 demo/mainnet endpoint **完全對稱 LOW**
- close dispatch 層 demo/mainnet drift 已由 close-maker-first AMD-2026-05-15-02 AC-15/19 + [65] healthcheck 覆蓋

**BB-PL-3**: AMD §5.1 evidence packet 5.1.1 必含「demo endpoint vs mainnet endpoint mapping 註腳」

### 補錄字典手冊（無 — 不需更新）

字典 v1.3 已含 `phys_lock_gate4_*` 兩項 positive whitelist + demo silent degradation 警告；**字典無新增需求**。

### Observability note (BB future audit cycle)

phys_lock 啟用後 30d trend 監控建議:
- `phys_lock_live_fire_rate` vs demo baseline 7d 偏差
- `close_maker_per_symbol_backoff_active` for phys_lock_gate4_* tagged dispatches
- Order group rate limit sustained 與 phys_lock fire 同時 land + close-maker-first Phase 2b active 期合計 ≤ 1.5 req/s

---

**Pre-enable timing**: BB 視角不阻 DRAFT 進入 review chain，但 Gate 3.7 (Mainnet 7 prereq) 不補完 → BB block Phase 3 carve-out promote。

**Estimate**: BB-PL-1 inline patch ~0.3h cosmetic + BB-PL-2 ~0.1h wording adjust + BB-PL-3 footnote 添加 ~0.1h；總計 ~0.5h AMD revision 工作量。
