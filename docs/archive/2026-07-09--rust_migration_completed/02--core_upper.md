# Phase R-02：core 上半——感知 + 認知 + 風控（Week 3-4）

**週期**：Rust 主開發 Week 3-4
**工時**：~2 週
**前置**：`01--ipc_shared_types_ws.md` Go + Golden Dataset 穩態組就緒
**下一階段**：`03--core_lower.md`

---

## 上下文導航

```
源文件：V3-FINAL §2.1（行數表）+ §5.4（浮點容差）
認知 SPEC：docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md
前置完成：IPC 通信穩定 · WS 接收數據 · shared_types 對齊
本階段目標：Rust 能獨立計算全部 13 指標 + 8 信號 + 認知三模組 + H0 門控
```

**QC 提醒**：
- SMA 用 Kahan 補償求和 [V3-QC-2]（Python 已改 fsum）
- 信號邊界豁免區按類型：RSI ±0.1% / MA Cross ±1e-8 / ATR ±0.01% [V3-QC-1]

---

## 具體任務

### [ ] R02-1：core/klines.rs — K 線聚合
- 源碼：kline_manager.py（1,055 行）
- 多時間框架聚合 · 滾動窗口 · 缺失填充
- **~1,800 行 Rust**

### [ ] R02-2：core/indicators.rs — 13 指標計算
- 源碼：indicator_engine.py + indicators/*.py（1,733 行合計）
- SMA(**Kahan**)·EMA·RSI·MACD·BB·ATR·Stochastic + KAMA·ADX·Hurst·EWMA Vol·VolumeRatio·Donchian
- 每個指標帶 `#[test]` 對比 Golden Dataset 穩態值
- **~2,000 行 Rust**

### [ ] R02-3：core/signals.rs — 8 信號規則
- 源碼：signal_generator.py（1,212 行）
- 邊界豁免區按類型實現 [V3-QC-1]
- **~2,000 行 Rust**

### [ ] R02-4：core/h0_gate.rs — 5 項門控
- 源碼：h0_gate.py（832 行）
- freshness / health / eligibility / envelope / cooldown
- **~1,400 行 Rust**

### [ ] R02-5：core/risk.rs — 風控計算 + cost_gate
- 源碼：risk_manager.py（1,633 行）+ cost_gate.py（185 行）
- ATR 雙窗口 · 動態止損 · 成本感知門檻
- **~2,800 行 Rust**

### [ ] R02-6：core/attention.rs — 注意力級別
- 源碼：market_data_dispatcher.py 部分（~120 行邏輯）
- dormant/low/medium/high/critical 計算
- **~200 行 Rust**

### [ ] R02-7：core/cognitive.rs — CognitiveModulator
- 源碼：認知 SPEC §2（V1.1+R1）
- EMA 平滑 · max 單因子 · 連虧忽略負向 · 4 個 _compute_*() 方法
- **~200 行 Rust**

### [ ] R02-8：core/opportunity.rs — OpportunityTracker
- 源碼：認知 SPEC §3
- 虛擬 PnL 扣 2x fee · 歸一化遺憾 · flush_closed · 緩存
- **~400 行 Rust**

### [ ] R02-9：core/dream.rs — DreamEngine
- 源碼：認知 SPEC §4
- threading → tokio::spawn（低優先級 task）· binomial test · 獨立 RNG seed
- **~600 行 Rust**

### [ ] R02-10：Golden Dataset 對比驗證
- 穩態組 3000 根 K 線逐 tick 對比
- Comparator 腳本（Python）讀 Rust 輸出 JSONL + Python 影子 JSONL
- 按 §5.4 容差分級判定

---

## Go/No-Go 門控

- [ ] `cargo test -p openclaw_core` 全部通過（~200 單元測試）
- [ ] Golden Dataset 穩態組：FAIL=0 · BOUNDARY < 1%
- [ ] 所有指標 Kahan/fsum 對比差異 < 1e-10

---

## 與現有工作交叉

| 交叉點 | 處理 |
|--------|------|
| Phase 1 PositionSizer/HealthMonitor/EWMA/Hurst | 這些的 Python 接口在 Phase 1 已穩定+凍結，Rust 按凍結接口實現 |
| Phase 1 認知三模組（Python 版） | Python 版在 Phase 1 已實現並跑了 2+ 週收集數據，Rust 版是精確移植 |

---

## 進度追蹤

| 任務 | 狀態 | 完成日期 | commit |
|------|------|---------|--------|
| R02-1 klines.rs | [x] | 2026-04-03 | pending |
| R02-2 indicators.rs | [x] | 2026-04-03 | pending |
| R02-3 signals.rs | [x] | 2026-04-03 | pending |
| R02-4 h0_gate.rs | [x] | 2026-04-03 | pending |
| R02-5 risk.rs | [x] | 2026-04-03 | pending |
| R02-6 attention.rs | [x] | 2026-04-03 | pending |
| R02-7 cognitive.rs | [x] | 2026-04-03 | pending |
| R02-8 opportunity.rs | [x] | 2026-04-03 | pending |
| R02-9 dream.rs | [x] | 2026-04-03 | pending |
| R02-10 Golden Dataset 對比 | [x] | 2026-04-03 | pending |

---

## 問題與變更

（空）
