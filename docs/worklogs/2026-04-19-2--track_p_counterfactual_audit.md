---
title: Track P Counterfactual Exit Audit — Phase 1a E2+E4 驗收
date: 2026-04-19
status: closed
tags: [DUAL-TRACK-EXIT-1, Track P, Phase 1a, E2, E4, counterfactual-audit]
related:
  - docs/worklogs/2026-04-18--dual_track_exit_design.md
  - program_code/audit/counterfactual_exit_audit.py
---

# 目標

完成 DUAL-TRACK-EXIT-1 Phase 1a Track P 的 E2+E4 驗收：
1. 盤點 Track P T1-T5 單測總數（要求 ≥18）
2. 跑 T5 counterfactual audit CLI，用 demo 7d fills + 1-min klines 事後歸因 Track P 骨架閾值表現

# 執行

## 單測盤點（≥18 要求 → 實際 ≥47）

| 模組 | 檔案 | 測試數 | Track P 相關 |
|---|---|---:|---:|
| T1 ExitFeatures | `rust/openclaw_engine/src/exit_features.rs` | 6 | 6 |
| T1 exit_feature_schema | `rust/openclaw_engine/src/database/exit_feature_schema.rs` | 3 | 3 |
| T2 compute_roc | `rust/openclaw_core/src/risk/price_tracker.rs` | 30 | 12（compute_roc 專項）|
| T3 physical_micro_profit_lock | `rust/openclaw_engine/src/risk_checks.rs` | 35 | 9（phys_lock 專項）|
| T3 wrapper | `rust/openclaw_engine/src/position_risk_evaluator.rs` | — | 1 |
| T4 combine_layer | `rust/openclaw_engine/src/combine_layer.rs` | 9 | 9 |
| tick_pipeline exit_feature_row | `rust/openclaw_engine/src/tick_pipeline/tests.rs` | — | 7（5 pre-existing WIP + 2 GAP-1 regression）|
| **總計** | | | **47** |

**結論**：遠超 ≥18 要求 ✅

## Counterfactual Audit（T5 CLI 實跑）

環境：engine 重啟 2026-04-19 22:33（binary mtime 22:32，含 commit 35808e9）；market.klines 自 MARKET-KLINES-STALE-1 修復後持續寫入（kline_fresh=true）。

**grid_trading demo 7d**（`/tmp/cf_audit_grid_demo.json`）：
```json
{
  "n_positions": 141, "n_phys_would_lock": 4,
  "delta_bps_mean": -39.44, "delta_bps_p25": -15.37, "delta_bps_p50": 0.0, "delta_bps_p75": 0.0,
  "n_phys_better": 1, "n_phys_worse": 2, "n_neutral": 1
}
```

**ma_crossover demo 7d**（`/tmp/cf_audit_ma_demo.json`）：
```json
{
  "n_positions": 52, "n_phys_would_lock": 10,
  "delta_bps_mean": -95.20, "delta_bps_p25": -62.49, "delta_bps_p50": -4.10, "delta_bps_p75": +54.72,
  "n_phys_better": 5, "n_phys_worse": 5
}
```

# 觀察與判讀

1. **命中率低但方向分歧**：grid 2.8% hit rate / ma_crossover 19.2%；骨架閾值對 grid 極度保守。
2. **ENJUSDT 案例（grid）**：real +2.76% vs cf +0.78% → −198 bps。Track P `giveback_atr_threshold=0.6` + `min_peak_atr_norm=0.5` 的骨架預設會砍掉趨勢性大 winner。
3. **BLURUSDT #2 案例（grid）**：real −0.01% vs cf +0.55% → +55.7 bps。Track P 成功救回 loser；但此類正面案例僅 1/4。
4. **ma_crossover p75 = +54.7 bps** 顯示分佈有「少數贏家 + 多數被提早砍」結構，與 P1-10 STRATEGY-ASYMMETRY-1（ma_crossover R:R 2.54×）一致。

# 結論

- E2+E4 驗收通過（≥47 單測 + 2 策略 7d counterfactual 完跑）
- Phase 1a 骨架閾值**對真實 demo 數據過於保守**，與設計預期一致（`docs/worklogs/2026-04-18--dual_track_exit_design.md` §Phase 1b 完成標準）
- 校準工作正確排入 Phase 1b（累積 ≥1 週 exit_features 後資料驅動 bind）

# 下一步

- 等 Phase 1b exit_features 累積 ≥1000 rows 後重跑此 audit 驗證收斂
- 校準方向（由資料決定）：提高 `min_peak_atr_norm`（避免砍小峰值）+ `giveback_atr_threshold`（給趨勢更多寬容）+ `min_net_floor_bps`（拉高啟用門檻）

# 工件

- CLI：`program_code/audit/counterfactual_exit_audit.py`（commit `4feb17a`）
- 輸出：
  - `/tmp/cf_audit_grid_demo.json`
  - `/tmp/cf_audit_ma_demo.json`
- 執行 venv：`program_code/.../control_api_v1/.venv`
