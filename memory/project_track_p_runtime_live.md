---
name: Track P 物理層 runtime live（2026-04-21 T4 接線 + 2026-04-22 V2 SWAP + 20:55 CEST 部署生效）
description: DUAL-TRACK-EXIT-1 Track P Phase 1b 全鏈 runtime live — T4 builder 接線（`e95c779` 2026-04-21 20:44 部署）+ V2 SWAP（`306993e` 2026-04-22 20:55 部署）完成，engine PID 158918 Priority 6 每 tick 呼 `physical_micro_profit_lock_v2` + `ExitConfig` 非線性 giveback；v1 linear pure fn + `PhysLockConfig` + 8 v1 直測已退役；engine lib 1843 → 1835 passed（Mac + Linux release 均驗）；合法 Lock 唯二 `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`
type: project
---

# Track P 物理層 runtime live（2026-04-21 + 2026-04-22 合併狀態）

**演進時序**：
- 2026-04-19：Phase 1b Track P v2 pure fn `aee96b9` + 31 單測（ExitConfig 7 參數、非線性 giveback fn）。代碼 live，runtime 未接。
- 2026-04-21 晚 2：Linux audit 揭露 `tick_pipeline/on_tick.rs:1677` 硬編碼 `|_| None` → Priority 6 從未 fire，Track P 所有 commits runtime 影響 = 0（dead）。
- 2026-04-21 晚 3：`TRACK-P-T4-WIRING-1` commit `e95c779` — `|_| None` 替換為實際 `ExitFeatures` builder closure；新 pure fn `exit_features::build_exit_features_for_tick`（查 `paper_state.position_exit_snapshot` + `price_tracker.compute_roc(300ms)` + `intent_processor.edge_estimates().get_cell`）；Mac + Linux release 均驗 engine lib 1827 → 1839 passed（+12 builder tests）。Runtime dead 狀態解除，但 Priority 6 仍呼 v1 linear `physical_micro_profit_lock` + `PhysLockConfig`。
- 2026-04-21 20:44 CEST：`restart_all.sh --rebuild` 部署（baseline commit `f128af5`，engine PID 3954769）— T4 接線首次進 runtime，Priority 6 v1 linear 開始 per-tick 評估。
- 2026-04-22：`TRACK-P-V2-SWAP-1` commit `306993e` — Priority 6 改呼 v2 `physical_micro_profit_lock_v2` + `ExitConfig`；`RiskConfig.phys_lock: PhysLockConfig` → `RiskConfig.exit: ExitConfig`（`#[serde(alias = "phys_lock")]` 保 TOML 相容）；v1 pure fn + `PhysLockConfig` struct + 8 個 v1 直測整塊退役（v2 在 `exit_features/v2.rs` 已有 25 等值單測）；Mac debug + Linux release `cargo test -p openclaw_engine --lib` 均 **1835 / 0 failed**。
- 2026-04-22 20:55 CEST：`ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild"` 部署完成 — engine PID 3954769 → **158918**（uvicorn 158973 隨 rebuild 同期重啟）；binary mtime 2026-04-21 20:44 → **2026-04-22 20:55**；baseline HEAD `9fcc7d4`（docs sync 在 `306993e` + `3d67a99` 上，二者 runtime 首次生效）；Priority 6 v2 non-linear giveback 即時 fire。

**TL;DR**：代碼 + runtime 全鏈 live。Priority 6 每 tick 呼 v2 非線性 giveback (`max(1.0 − 0.15 × peak_atr_norm, 0.3)`)；edge_estimates 冷啟動期 Gate 1 全 Hold（預期 fail-safe，1 小時 scheduler 刷新後逐步解鎖）。v1 ↔ v2 reason-string ABI 完全一致，下游 parse 零改。

## 當前 runtime 狀態（engine PID **158918**，binary mtime **2026-04-22 20:55**）

**Priority 6 call chain（v2 non-linear 版）**：
```rust
// tick_pipeline/on_tick/step_6_risk_checks.rs (T4 接線)
let exit_features_fn = |row: &PositionRow| -> Option<ExitFeatures> {
    let snap = paper_state_ref.position_exit_snapshot(&row.symbol)?;
    let price_roc_short = price_tracker_ref.compute_roc(&row.symbol, 300);
    let est_net_bps = edge_estimates_ref
        .get_cell(&snap.owner_strategy, &row.symbol)
        .map(|c| c.shrunk_bps as f32);
    Some(build_exit_features_for_tick(&snap, row.current_price, row.atr_pct,
                                       price_roc_short, est_net_bps, tick_ts_ms))
};
// risk_checks.rs Priority 6（post-V2-SWAP）
if let Some(features) = exit_features {
    if let PhysicalDecision::Lock(reason) =
        physical_micro_profit_lock_v2(features, &config.exit)  // v2 non-linear
    { return RiskAction::ClosePosition(format!("risk_close:{}", reason)); }
}
```

**合法 Lock 唯二**：`phys_lock_gate4_giveback`（v1 linear 閾值 0.7 giveback ≥）/ `phys_lock_gate4_stale_roc_neg`（peak 陳舊 > stale_peak_ms AND `price_roc_short < 0`）。

**edge_estimates 冷啟動**：`is_populated()=false` → `est_net_bps=None` → v1 Gate 1 `None → Hold`（保守 fail-safe；Phase 5 edge 收斂後自然解鎖）。

## v2 vs v1 runtime 差異（2026-04-22 20:55 起 runtime 為 v2）

| 維度 | v1 linear（2026-04-21 20:44 ~ 2026-04-22 20:54 短窗） | v2 non-linear（2026-04-22 20:55 ~ 當前） |
|---|---|---|
| Gate 1 邊界 | `edge < floor` → Hold | `edge <= floor` → Hold（等於 floor 也擋） |
| Gate 4a 閾值 | 固定 `0.7` | `max(1.0 − 0.15 × peak_atr_norm, 0.3)`（高 peak 更快鎖、淺 peak 更慢鎖） |
| Gate 4b 邊界 | `dt > stale_peak_ms` | `dt >= stale_peak_ms`（剛滿即擋） |

整體方向符合 DUAL-TRACK-EXIT-1 §三 L108-111「防微利即套離場、追求最高單筆 close 盈利」。

## 部署後觀察點（24h）

建議看 `trading.fills.exit_reason LIKE 'risk_close:phys_lock_gate4_%'` 分布：
- 若 `gate4_giveback` 比例明顯上升（高 peak 倉更快鎖）→ v2 非線性生效；
- 若 `gate4_stale_roc_neg` 比例上升 → 邊界 `>=` 效應（通常佔比小）；
- fee/edge 無顯著惡化即接受；
- **冷啟動期（1h 內）**：`edge_estimates` `is_populated=false` → `est_net_bps=None` → Gate 1 全 Hold；等 scheduler 刷新（整點觸發）後逐步解鎖。

## 代碼結構（post-V2-SWAP）

```text
exit_features/
├── mod.rs        # re-export ExitConfig + physical_micro_profit_lock_v2
├── core.rs       # ExitFeatures + PhysicalDecision
├── v2.rs         # ExitConfig + non_linear_giveback_fn + physical_micro_profit_lock_v2 + 25 tests
└── builder.rs    # build_exit_features_for_tick (T4 wiring helper) + 12 tests

risk_checks.rs
└── check_position_on_tick
    └── Priority 6 → physical_micro_profit_lock_v2(features, &config.exit)  # 從 v1 切 v2

config/risk_config.rs
└── RiskConfig.exit: ExitConfig  # 從 phys_lock: PhysLockConfig 切（alias="phys_lock" 保 TOML）
```

## 未來 session 避免誤判

- **代碼 live ≠ runtime live**：`git log` 看到 `306993e` 不代表 v2 在跑；必驗 engine binary mtime 與 commit 時序對齊，或查 `trading.fills.exit_reason` 分布判斷 v1/v2。
- **測試數變化勿慌**：1843 → 1835（−8）不是 regression，是 v1 直測退役；v2 同等覆蓋在 `exit_features/v2.rs` 25 單測（更嚴格，含 non-linear giveback 單調性、volatility normalisation boundary、spike-wick 等 v1 沒有的 scenario）。
- **TOML 相容**：三環境 `risk_config*.toml` 無 `[risk.phys_lock]` 也無 `[risk.exit]` section，全走 `ExitConfig::Default`。`#[serde(alias = "phys_lock")]` 是保險，operator 若手寫 `[risk.phys_lock]` 可 deserialize 進 `exit`，但 v1 專屬欄位 `giveback_atr_norm_threshold` 會被 serde 忽略（v2 用 `giveback_base/slope/floor` 三欄替代）— 若未來真要手寫 TOML 覆蓋，需用 v2 欄位名。
- **Python 端 `program_code/audit/counterfactual_exit_audit.py`** 仍有同名 `PhysLockConfig` dataclass（離線 counterfactual 模擬，獨立 class）；未被 V2 SWAP 影響，但語意落後 v2 — 若要對齊另起 `COUNTERFACTUAL-AUDIT-V2-ALIGN-1` TODO。

## 後續 TODO

- **部署觸發**（operator 決定時機）：`ssh trade-core "... restart_all.sh --rebuild"` — 讓 v2 non-linear giveback 進 runtime。
- **Counterfactual audit**（Linux sub-agent 或 operator）：demo 7d tick-level 重放，校準 v2 `ExitConfig` 3 個非線性 giveback 參數（base/slope/floor）— 目前是設計 seed，未經實 fill 校準。
- **Python audit 對齊 v2**（可選）：`COUNTERFACTUAL-AUDIT-V2-ALIGN-1`（P3，~半天），把 `counterfactual_exit_audit.py::PhysLockConfig` 改非線性，與 Rust `ExitConfig` 對齊。
