# Vol-Event Robust Ruling — order-flow edge × high-vol regime

> 自動產出（vol_event_trigger.py）：2026-06-22T04:00:07.686539+00:00
> $0 唯讀 / OFFLINE / leak-free PIT。指標性彙總，**最終 verdict 屬 QC**。
> 不下單、不碰 production engine/risk、不改 sibling 檔。

## 彙總

- 已分析獨立 high_vol 事件：**13**（downside=5 / upside_squeeze=8）
- regime diversity 達成（≥1 upside_squeeze）：**True**
- 過成本牆的事件數：**0 / 13**
- **ROBUST RULING：NO_EDGE_SURVIVES: 跨所有 high_vol 事件，無任一軸過成本牆**

## Per-axis 跨事件存活

| 軸（signal） | 過牆事件數 / 總事件數 |
|---|---|
| OFI@10s_long_short_ofi10s_fwd15s | 0 / 13 |
| OFI@10s_long_short_ofi10s_fwd5s | 0 / 13 |
| microprice_tilt_decile_spread | 0 / 13 |

## Per-event 明細

| anchor(UTC) | direction | anchor_ret_bp | n_hours | n_trade_rows | status | survives_wall | verdict |
|---|---|---|---|---|---|---|---|
| 2026-06-17T08:00:00+00:00 | downside | -93.5 | 1 | 701125 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-17T15:00:00+00:00 | upside_squeeze | 98.5 | 2 | 1585538 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-18T15:00:00+00:00 | downside | -230.6 | 46 | 20589398 | ok | False | HIGH_VOL_NO_EDGE_SURVIVES |
| 2026-06-19T23:00:00+00:00 | upside_squeeze | 35.5 | 1 | 393256 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-20T14:00:00+00:00 | upside_squeeze | 87.4 | 1 | 731459 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-20T17:00:00+00:00 | downside | -29.5 | 1 | 442846 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-20T22:00:00+00:00 | upside_squeeze | 40.3 | 1 | 363389 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-21T03:00:00+00:00 | upside_squeeze | 28.5 | 1 | 256895 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-21T15:00:00+00:00 | upside_squeeze | 12.3 | 1 | 371524 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-21T18:00:00+00:00 | upside_squeeze | 10.1 | 1 | 297306 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-21T20:00:00+00:00 | downside | -55.0 | 1 | 296583 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-22T01:00:00+00:00 | upside_squeeze | 109.3 | 2 | 1298161 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |
| 2026-06-22T03:00:00+00:00 | downside | -45.8 | 1 | 505763 | low_power_preliminary | False | HIGH_VOL_PRELIMINARY_LOW_POWER |

## 方法與不變量

- 事件=tape 可分析窗內連續 high_vol 小時 cluster（gap ≤ 1h 合併）；anchor=|ret| 最大時；
  direction=anchor ret 符號。regime 標籤 leak-free PIT（regime.py，shift(1) RV）。
- 每事件跑 analysis.run(regime_split=True)，取 high_vol block 的 fee-wall（taker 6bp /
  maker 4bp / microprice 用 own-spread）。survives_wall=any axis 過牆。
- low_power_preliminary（樣本薄）的事件 verdict 為指標性；穩健結論需多事件一致。
