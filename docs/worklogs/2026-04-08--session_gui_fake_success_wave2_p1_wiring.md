---
title: GUI Fake-Success Wave 2 + P1 Per-Trade Risk → Rust 接線
date: 2026-04-08
session: gui-fake-success-wave2
ends_at_commit: (uncommitted at compact)
---

# Session 進度 — Wave 2

## ✅ 已完成（uncommitted）

### 1. Risk tab fake-success 全套修復
**根因**：`tab-risk.html:798` `cfg = d.data` 後讀 `cfg.global_config`，但路由實際包在 `d.data.config.global_config` — 少讀一層 → `gc = {}` → 所有顯示/輸入框 fallback 到 JS 字面預設值（5/15/20）。

**修復**：
- `tab-risk.html`: `const cfg = (d.data && d.data.config) || d.data || {}`
- 同時誤把 `cfg.overrides` 加入 p0 fallback 鏈，導致 `Object.entries(null)` 拋錯 → 已移除
- `risk_routes.py`: `consecutive_loss_cooldown_minutes` Pydantic 從 `float` 改 `int`（Rust 是 u32，Python 序列化 30.0 帶 .0 失敗）

### 2. P1 Per-Trade Risk → Rust 完整接線（架構級修復）
**問題**：`intent_processor.rs:56` `DEFAULT_P1_RISK_PCT = 0.02` 寫死，GUI P1 input 是 localStorage hack，根本沒進 Rust。

**改動**：
- `rust/openclaw_engine/src/config/risk_config.rs`:
  - `GlobalLimits` 加 `per_trade_risk_pct: f64` 欄位 + `default_per_trade_risk_pct() = 0.02`
  - `Default::default()` 帶上
  - `validate()` 加 `[0.0001, 0.20]` 範圍檢查
- `rust/openclaw_engine/src/intent_processor.rs:204`:
  - `update_risk_config(&mut self, config: RiskConfig)` 內呼叫 `self.set_p1_risk_pct(config.limits.per_trade_risk_pct)`
  - tick-level hot-reload 自動帶到（既有 1C-2 機制）
- `risk_view_client.py`:
  - `_GLOBAL_TO_RUST` 加 `"p1_risk_pct": ("limits", "per_trade_risk_pct")`
  - `_remap_global_to_rust` 加單位換算：value > 1 時 / 100（GUI percent → Rust fraction）
- `risk_routes.py`: flat global_config builder 加 `p1_risk_pct = limits.per_trade_risk_pct * 100`
- `tab-risk.html`: 砍掉 localStorage hack；savePositionSettings 把 `p1_risk_pct` 加回 body；loadRiskConfig 直接讀 `gc.p1_risk_pct`

**驗證端到端通了**：
```
GUI POST p1_risk_pct=8 (percent)
  → Python remap → 0.08 (fraction)
  → Rust ConfigStore per_trade_risk_pct=0.08, version bumps
  → 下一個 tick update_risk_config → set_p1_risk_pct(0.08)
  → Gate 2.6 用新值
  → notional 從 $19.52 → $77 (4× 提升，剛好對應 2%→8%)
```

`cargo build --release -p openclaw_engine` 通過（只有 pre-existing warnings）。重啟後 Rust 引擎健康。

### 3. Task #4 + Task #3 已 commit（前一個 session）
- HEAD commits: `5a824d8` (risk display + dual-engine stop) + `d5e8097` (worklog Wave 1)
- 都已驗證

## ⚠️ 發現的下一個瓶頸（結構性，非 bug）

**所有 intent 仍被 cost_gate 拒絕**，但這次原因不同：

```
EV / fee 比例與 position size 完全無關：
EV  = atr × conf × qty
fee = qty × price × 2 × fee_rate
EV/fee = (atr × conf) / (price × 2 × fee_rate)  ← qty 約掉了

當前 BTC：
  atr=24.76, conf=0.65, fee=0.055%, price=$67000
  EV/fee = (24.76 × 0.65) / (67000 × 2 × 0.00055) = 0.22×
  cost_gate.k_small 要 ≥ 3.0×
  差 14 倍 → P1 調多大都沒用
```

**意義**：BTC 當前低波動期 + grid_trading 信號，**結構上不可能過 k=3 的 cost_gate**。

要真的下單需要：
1. 高波動 symbol（小幣 ATR% > 0.5%）
2. 更高 confidence 信號
3. 下調 cost_gate.k_small（不推薦，會放垃圾單）
4. 找其他 strategy/symbol 組合（17 active strategy × 50 symbol）

## 🔜 接手 checklist

1. `git status` 確認未 commit 變更：
   - `rust/openclaw_engine/src/config/risk_config.rs`（+欄位 +default +validate）
   - `rust/openclaw_engine/src/intent_processor.rs`（update_risk_config 內呼叫 setter）
   - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_view_client.py`（mapping + 換算）
   - `.../app/risk_routes.py`（Pydantic int + flat builder p1_risk_pct）
   - `.../app/static/tab-risk.html`（cfg 路徑修 + p1 接 backend + 移除 localStorage）
2. `cargo build --release -p openclaw_engine` 已通過
3. 引擎在跑（PID 變化但 healthy），balance $976，0 positions / 0 fills
4. 待用戶決定：
   - (A) 我幫他掃描其他 strategy/symbol 找能通過 cost_gate 的組合
   - (B) 先 commit P1 接線這個正確的架構工作
5. 還有未 commit 的 Task #2（Mode control）已被用戶確認"感覺已正常"，可一併 commit

## 重要的 sticky 知識點

**P1 接線後 cost_gate 仍是最終 gating**：永遠要記住 EV/fee 不隨 size 變化。下單根本問題不是 P1，是信號質量 + 標的波動 + 費率。下次 session 不要再以為調 P1 能解。

## Commit 鏈
```
(uncommitted) feat(risk+ipc): wire P1 per_trade_risk_pct to Rust ConfigStore + GUI fake-success Wave 2
d5e8097 docs(worklog): GUI fake-success Wave 1 progress + Task #2 reframing  ← session 開始前
5a824d8 fix(gui): kill 2 fake-success bugs — risk display refresh + dual-engine stop label  ← session 開始前
```
