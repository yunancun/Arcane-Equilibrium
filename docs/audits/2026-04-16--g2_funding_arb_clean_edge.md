# G-2 FundingArb Clean Edge Audit — demo 引擎

**生成時間：** 2026-04-17T20:05:25+00:00
**樣本期：** 2026-04-16 15:40:48 UTC → 至今
**樣本數：** 10 個 demo strategy_exit 平倉（目標 10）

---

## Aggregate

- 平倉次數：10
- 累積 realized PnL：$-0.6326
- 累積 fee：$0.4039
- **Net edge：$-1.0365 USDT**
- 累積名義量：$666.45
- **Edge bps：-15.55 bps**
- 勝率：4/10 = 40.0%
- 平均單筆 PnL：$-0.0633
- 平均單筆 fee：$0.0404

## Per-Symbol Breakdown

| symbol | n | sum_pnl | sum_fee | avg_pnl | n_wins | notional |
|---|---:|---:|---:|---:|---:|---:|
| ENJUSDT | 3 | -0.0071 | 0.0982 | -0.0024 | 1 | 178.54 |
| MOVRUSDT | 3 | -0.2146 | 0.1133 | -0.0715 | 2 | 206.01 |
| ORDIUSDT | 2 | -0.3795 | 0.0798 | -0.1898 | 0 | 145.05 |
| GENIUSUSDT | 1 | -0.0660 | 0.0747 | -0.0660 | 0 | 67.88 |
| SOONUSDT | 1 | 0.0345 | 0.0379 | 0.0345 | 1 | 68.97 |

## Verdict

❌ NEGATIVE EDGE — funding_arb 當前參數無法覆蓋成本

建議：升 R-02 重評 funding_arb 入場/退場參數（funding_threshold / max_basis_pct 配對），或考慮停用

## 最近 50 筆 fills（明細）

| ts_utc | symbol | side | qty | price | pnl | fee | reason |
|---|---|---|---:|---:|---:|---:|---|
| 2026-04-17 19:59:09 | MOVRUSDT | Sell | 21.5000 | 3.16620 | 0.0408 | 0.0374 | funding_arb_exit: rate=-0.001153 basis=0.553% |
| 2026-04-17 19:09:12 | SOONUSDT | Sell | 314.0000 | 0.21965 | 0.0345 | 0.0379 | funding_arb_exit: rate=-0.001232 basis=0.516% |
| 2026-04-17 17:05:01 | MOVRUSDT | Sell | 19.3000 | 3.64020 | 0.2412 | 0.0386 | funding_arb_exit: rate=-0.003875 basis=0.508% |
| 2026-04-17 10:33:56 | MOVRUSDT | Sell | 21.5000 | 3.14800 | -0.4967 | 0.0372 | funding_arb_exit: rate=-0.001996 basis=0.508% |
| 2026-04-17 09:38:58 | GENIUSUSDT | Sell | 110.0000 | 0.61710 | -0.0660 | 0.0747 | funding_arb_exit: rate=-0.004269 basis=0.500% |
| 2026-04-17 04:33:59 | ENJUSDT | Sell | 878.7000 | 0.08031 | -0.0378 | 0.0388 | funding_arb_exit: rate=-0.003297 basis=0.500% |
| 2026-04-17 03:33:06 | ENJUSDT | Sell | 420.2000 | 0.07992 | 0.0794 | 0.0185 | funding_arb_exit: rate=-0.002607 basis=0.507% |
| 2026-04-17 00:37:40 | ENJUSDT | Sell | 994.7000 | 0.07479 | -0.0487 | 0.0409 | funding_arb_exit: rate=-0.001972 basis=0.503% |
| 2026-04-16 16:01:50 | ORDIUSDT | Sell | 9.2200 | 8.32200 | 0.0000 | 0.0422 | funding_arb_exit: rate=-0.002028 basis=0.504% |
| 2026-04-16 16:01:37 | ORDIUSDT | Sell | 8.2500 | 8.28100 | -0.3795 | 0.0376 | funding_arb_exit: rate=-0.002028 basis=0.504% |

---

## 監控元數據

- 監控腳本：`/tmp/openclaw/g2_monitor.py`
- 進度日誌：`/tmp/openclaw/g2_monitor.log`
- 自動觸發於：count ≥ 10
- 引擎重啟基準：2026-04-16 15:40:48 UTC
