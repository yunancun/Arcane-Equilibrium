# Vol-Event Robust Ruling — order-flow edge x high-vol regime

> 自動產出（vol_event_trigger.py）：2026-06-18T22:00:02.226616+00:00
> $0 唯讀 / OFFLINE / leak-free PIT。指標性彙總，**最終 verdict 屬 QC**。
> 不下單、不碰 production engine/risk、不改 sibling 檔。

## 彙總

- 已分析獨立 high_vol 事件：**4**（downside=3 / upside_squeeze=1）
- regime diversity 達成（>=1 upside_squeeze）：**True**
- 過成本牆的事件數：**0 / 4**
- **ROBUST RULING：NO_EDGE_SURVIVES: 跨所有 high_vol 事件，無任一軸過成本牆**

## Per-axis 跨事件存活

| 軸（signal） | 過牆事件數 / 總事件數 |
|---|---|
| OFI@10s_long_short_ofi10s_fwd15s | 0 / 4 |
| OFI@10s_long_short_ofi10s_fwd5s | 0 / 4 |
| microprice_tilt_decile_spread | 0 / 4 |

## Per-event 明細

| anchor(UTC) | direction | anchor_ret_bp | n_hours | n_trade_rows | status | survives_wall | verdict |
|---|---|---:|---:|---:|---|---|---|
| 2026-06-17T08:00:00+00:00 | downside | -93.5 | 1 | 701125 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-17T15:00:00+00:00 | upside_squeeze | 98.5 | 2 | 1585538 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-17T19:00:00+00:00 | downside | -186.8 | 13 | 8060967 | ok | False | HIGH_VOL_NO_EDGE_SURVIVES |
| 2026-06-18T15:00:00+00:00 | downside | -230.6 | 22 | 12717434 | ok | False | HIGH_VOL_NO_EDGE_SURVIVES |

## 方法與不變量

- 事件=tape 可分析窗內連續 high_vol 小時 cluster（gap <= 1h 合併）；anchor=|ret| 最大時；
  direction=anchor ret 符號。regime 標籤 leak-free PIT（regime.py，shift(1) RV）。
- 每事件跑 analysis.run(regime_split=True)，取 high_vol block 的 fee-wall（taker 6bp /
  maker 4bp / microprice 用 own-spread）。survives_wall=any axis 過牆。
- low_power_preliminary（樣本薄）的事件 verdict 為指標性；穩健結論需多事件一致。

## PM 收錄註記

- 本檔內容取自 Linux `trade-core` untracked runtime artifact
  `docs/CCAgentWorkSpace/E1/workspace/reports/vol-event-robust-ruling.md`
  at 2026-06-19 01:54 CEST。
- 收錄目的：讓根 `TODO.md` 的 vol-event ruling 狀態有 repo-tracked evidence pointer。
- 邊界：report-only evidence；不等於 QC final promotion verdict，不授權 strategy/risk/runtime/order/auth mutation。
