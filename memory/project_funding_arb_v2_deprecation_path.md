---
name: funding_arb V2 中期棄策略路徑（2A 決策 2026-05-02）
description: funding_arb V2 directional 設計已 QC 量化否決 delta-neutral 改造；中期方向棄策略，slot 留 R-02 重設計；短期 1B 保留 active=true 收 EDGE-DIAG-2 樣本 + 3% tight SL
type: project
originSessionId: f6f6c16c-3c99-47e7-9e9b-b70f05a78674
---
# funding_arb V2 棄策略路徑（中期 2A 決策）

## 決策時間
2026-05-02 15:39:15 BUSDT 單筆 -10.12 USDT 後 operator 1B+2A+3C 決策。

## 為什麼棄而不改 delta-neutral

QC 2026-05-02 量化分析（agentId: a5f95166dcc70775a）：

1. **數學不成立**：spot 來回 20bps + perp 11bps + slip 3bps = 34 bps round-trip；funding 8h 中位數 ~1.5 bps → break-even **7.6 天**持倉
2. **basis spread vol 5-15 bps** 在 7 天區間直接吞掉期望，net edge 趨近 0
3. **Bybit demo 無 spot lending** → delta-neutral 在 demo 環境根本無法回測驗證；要直接上 live 違反 demo 21d gross > 0 政策
4. **救不了 13 筆 -36.76 bps**：把 directional loss 換成確定 cost drag，期望值更負；funding rate 預測本身有沒有 alpha 13 sample 不足以分辨
5. **替代方案皆不可行**：
   - directional + tight SL 2-3%：SL 100x funding mean，一次 SL 吞 30 cycle
   - 入場門檻 |F|>10 bps + 8h close：唯一 net positive 候選但月度 1-3 次入場，capacity 太低不值佔 strategy slot

## 短期保留收樣本（1B）的條件

3C(b) 已綁 demo TOML：
- `srv/settings/risk_control_rules/risk_config_demo.toml`
- `[per_strategy.funding_arb] stop_loss_max_pct_override = 3.0`（commit a19797d）
- 限制單筆損失 ≤ 3%（vs 原本 dynamic stop 約 8-12% 才接住）

## 中期執行條件（2A 觸發點）

何時把 funding_arb 整體 deprecate：
1. EDGE-DIAG-2 cost_gate min-n stratify 樣本收完（operator 判定）
2. 或 1B 期間累積 fire 次數 ≥ 30，gross PnL 確定為負（達 detect Sharpe > 0 sample 量門檻）
3. R-02 Strategist 重設計 strategy slot 啟動

## 棄策略時的最小改動清單

當 2A 觸發時：
- `srv/settings/strategy_params_demo.toml` `[funding_arb] active = false`（恢復 2026-04-18 G-2 v2 verdict）
- `srv/settings/risk_control_rules/risk_config_demo.toml` 整 `[per_strategy.funding_arb]` block 連同雙語註解一起移除
- IPC `reload_risk_config` + `update_strategy_params` 持久化
- `rust/openclaw_engine/src/strategies/funding_arb.rs` 暫不刪（保留至 R-02 確認新 strategy slot 是否會 reuse 部分代碼）

## 關鍵文件路徑

- E1 TOML 改動：commit `a19797d` on `feature/2026-05-02-funding-arb-tight-sl-base-ratio`
- E4 regression report：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--funding_arb_tight_sl_regression.md`
- QC delta-neutral 量化分析：sub-agent agentId `a5f95166dcc70775a`（已過期，不可 SendMessage 喚回，僅供歷史參考）
- 相關記憶：`project_g2_funding_arb_monitor.md`（2026-04-18 G-2 v2 NEGATIVE 結案）
