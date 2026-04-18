# G-2 FundingArb Clean Edge Audit — demo 引擎

**生成時間：** 2026-04-18T17:00:17+00:00
**樣本期：** 2026-04-17 20:20:57 UTC → 至今
**樣本數：** 13 個 demo strategy_exit 平倉（目標 20）

---

## Aggregate

- 平倉次數：13
- 累積 realized PnL：$-2.1879
- 累積 fee：$0.7090
- **Net edge：$-2.8969 USDT**
- 累積名義量：$788.02
- **Edge bps：-36.76 bps**
- 勝率：0/13 = 0.0%
- 平均單筆 PnL：$-0.1683
- 平均單筆 fee：$0.0545

## Per-Symbol Breakdown

| symbol | n | sum_pnl | sum_fee | avg_pnl | n_wins | notional |
|---|---:|---:|---:|---:|---:|---:|
| RAVEUSDT | 5 | -0.5152 | 0.3133 | -0.1030 | 0 | 284.86 |
| GENIUSUSDT | 2 | -0.1770 | 0.1363 | -0.0885 | 0 | 123.91 |
| SOONUSDT | 2 | -0.3332 | 0.0715 | -0.1666 | 0 | 130.04 |
| SIRENUSDT | 1 | -0.5601 | 0.0672 | -0.5601 | 0 | 61.07 |
| MOVRUSDT | 1 | -0.0920 | 0.0363 | -0.0920 | 0 | 66.08 |
| HIGHUSDT | 1 | -0.1477 | 0.0672 | -0.1477 | 0 | 61.11 |
| CLUSDT | 1 | -0.3628 | 0.0171 | -0.3628 | 0 | 60.95 |

## Verdict

❌ NEGATIVE EDGE — funding_arb 當前參數無法覆蓋成本

建議：升 R-02 重評 funding_arb 入場/退場參數（funding_threshold / max_basis_pct 配對），或考慮停用

---

## Operator 提前結案註記（2026-04-18，n=13/20 partial）

**結案決定：不等 n=20，提前關站。** 三個獨立證據指向明確 NEGATIVE，再跑 7 筆只會增加 negative 樣本而不改變結論：

1. **0/13 勝率**（v1 n=10 勝率 40%）— 跨 MICRO-PROFIT-FIX-1 baseline 勝率不升反歸零，修復未釋放 funding_arb 利潤，反而窄 cost-edge 帶把邊緣勝單砍掉
2. **全部 13 筆 exit 在 `max_basis_pct = 0.5%` 邊界觸發**（basis 範圍 0.501–0.522%）— 說明入場時 basis 已接近止損邊界，`entry_basis_ratio = 0.8` 的 hysteresis buffer（= 0.4%）被 market micro-structure 輕易吃掉
3. **per-fill edge 惡化 15.55 → 36.76 bps**（v1 → v2），趨勢單調，無「後期反轉」合理路徑

**跨 v1→v2 變化解讀：** MICRO-PROFIT-FIX-1 對 funding_arb 無效甚至略負；fast_track 25% entry_notional 底線 + COST EDGE 窄帶 [0.3%, 0.55%] 對 trend/reversion 策略設計，對 funding_arb 的「basis mean-reversion」邏輯是錯誤的成本模型 — funding_arb 利潤來自 funding payment，不是 basis mean-reversion，而當前參數 `total_cost_bps = 34`（約 0.34%）已超過 `max_basis_pct = 0.5%` 的 68%，預算本就太薄。

**動作：**
- Daemon PID 1834915 kill — 本 audit 即終版
- Demo `funding_arb.active` = `true → false`（hot-reload via IPC + TOML 持久化）
- 升 R-02 / Strategist agent：重評 `funding_threshold` / `max_basis_pct` / `total_cost_bps` 三參數配對；考慮 `entry_basis_ratio` 收緊或改 entry-signal 設計
- v1 audit：`docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`（v1 n=10 NEGATIVE，保留比較基準）

## 最近 50 筆 fills（明細）

| ts_utc | symbol | side | qty | price | pnl | fee | reason |
|---|---|---|---:|---:|---:|---:|---|
| 2026-04-18 11:12:31 | CLUSDT | Buy | 0.7100 | 85.83800 | -0.3628 | 0.0171 | funding_arb_exit: rate=0.001834 basis=0.501% |
| 2026-04-18 09:22:32 | HIGHUSDT | Sell | 138.0000 | 0.44282 | -0.1477 | 0.0672 | funding_arb_exit: rate=-0.008927 basis=0.512% |
| 2026-04-18 08:52:32 | SIRENUSDT | Sell | 82.0000 | 0.74473 | -0.5601 | 0.0672 | funding_arb_exit: rate=-0.001532 basis=0.508% |
| 2026-04-18 08:33:04 | GENIUSUSDT | Buy | 74.0000 | 0.82860 | -0.0666 | 0.0674 | funding_arb_exit: rate=0.001153 basis=0.522% |
| 2026-04-18 07:49:21 | RAVEUSDT | Sell | 2.0000 | 26.35964 | -0.2870 | 0.0580 | funding_arb_exit: rate=-0.001281 basis=0.504% |
| 2026-04-18 07:22:48 | GENIUSUSDT | Buy | 69.0000 | 0.90720 | -0.1104 | 0.0689 | funding_arb_exit: rate=0.002314 basis=0.521% |
| 2026-04-18 07:08:00 | SOONUSDT | Sell | 324.0000 | 0.19411 | -0.1847 | 0.0346 | funding_arb_exit: rate=-0.001374 basis=0.507% |
| 2026-04-18 01:55:07 | RAVEUSDT | Sell | 2.0000 | 26.38765 | -0.0392 | 0.0581 | funding_arb_exit: rate=-0.005178 basis=0.515% |
| 2026-04-18 00:55:01 | RAVEUSDT | Sell | 2.0000 | 24.83155 | -0.0394 | 0.0546 | funding_arb_exit: rate=-0.001157 basis=0.503% |
| 2026-04-18 00:05:05 | MOVRUSDT | Sell | 23.0000 | 2.87310 | -0.0920 | 0.0363 | funding_arb_exit: rate=-0.001454 basis=0.520% |
| 2026-04-17 23:24:13 | RAVEUSDT | Sell | 3.0000 | 21.72362 | -0.0859 | 0.0717 | funding_arb_exit: rate=-0.001957 basis=0.503% |
| 2026-04-17 21:23:21 | RAVEUSDT | Sell | 3.0000 | 21.51150 | -0.0637 | 0.0710 | funding_arb_exit: rate=-0.002535 basis=0.511% |
| 2026-04-17 21:05:23 | SOONUSDT | Sell | 303.0000 | 0.22160 | -0.1485 | 0.0369 | funding_arb_exit: rate=-0.001166 basis=0.503% |

---

## 監控元數據

- 監控腳本：`/tmp/openclaw/g2_monitor.py`
- 進度日誌：`/tmp/openclaw/g2_monitor.log`
- 自動觸發於：count ≥ 20
- 引擎重啟基準：2026-04-17 20:20:57 UTC
