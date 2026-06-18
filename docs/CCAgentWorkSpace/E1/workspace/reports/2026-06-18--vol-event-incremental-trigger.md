# E1 IMPLEMENTATION — vol-event 增量自動累積器（待 E2 審查）

> 2026-06-18 · E1 · $0 唯讀 OFFLINE · Linux runtime (ssh trade-core) · 無 commit

## 任務摘要

把既有一次性的 regime-aware 決定性 fee-wall harness（`helper_scripts/research/order_flow_alpha/`
的 `analysis.py` + `regime.py`，本 session 所建）變成 **INCREMENTAL 自動累積器**：未來的 vol 事件
被自動分析、累積進持久化 ledger，無需人工 polling，最終建立一份穩健的 ≥3-event ruling。

READ-ONLY 全程；不下單、不碰 production engine/risk、不改 sibling microstructure 檔、不改 harness 檔（只 import 復用）。

## 修改清單

| 檔 | 性質 | 行數 |
|---|---|---|
| `helper_scripts/research/order_flow_alpha/vol_event_trigger.py` | **新增** trigger 主程式 | 521 |
| `helper_scripts/research/order_flow_alpha/vol_event_trigger.sh` | **新增** cron 薄包裝 | 30 |
| `helper_scripts/SCRIPT_INDEX.md` | 登記 2 新腳本 | +2 行 |
| `docs/CCAgentWorkSpace/E1/memory.md` | 追加結論 | +5 行 |

不改任何 sibling / harness / production 檔（純 import 復用 `analysis.run` / `regime.classify_hours` /
`data_loader.connect` / `canary.alert_sink.append_alert_sink`）。

## 設計關鍵（核心決策）

### 事件 = high_vol 小時 cluster（不是每小時一事件）
trailing RV 是 24h 平均、滯後回落，行情過後常一連幾十小時仍被標 high_vol。若「每個 high_vol 小時
= 一個事件」會造出幾十個高度重疊的假事件，破壞「≥3 獨立事件」的統計獨立性。故：**連續（gap ≤ 1h）
的 high_vol 小時合併成一個 cluster = 一個獨立事件**；anchor = cluster 內 |hourly ret_bp| 最大的小時；
**direction = anchor 小時 ret 符號**（< 0 = downside / > 0 = upside_squeeze）。實證：tape 內 16 個
high_vol 小時 → 收斂成 3 個獨立事件 cluster（而非 16 個假事件）。

### idempotent / 增量 / bounded
- ledger key = anchor 小時 ISO；已分析事件**永不重跑**（rerun 實證 0 重跑、0.5s）。
- 每次運行按 anchor |ret_bp| 由大到小排序、最多取 `--max-events` 個新事件（預設 2）→ bounded + 快。
- 原子寫 ledger（temp + os.replace）；損毀 ledger fail-soft 重建。

### NOTIFICATION 通道（mandate §5）
先 grep 既有耐久 sink：找到 `helper_scripts/canary/alert_sink.py` 的 `append_alert_sink(data_dir,
subject, body, severity, channels_attempted)` — 純本地 append `<data_dir>/alerts/alerts.jsonl`、
**零外部發送**（W-2 永不拋、自帶 redactor + 輪轉）。**這是 read-only-safe 的既有 established sink**，
故用它當主通道，傳 `channels_attempted=[]` 明確「不嘗試任何外部發送」。同時**恆寫** self-contained
run log（`logs/vol_event_trigger.log`）+ 達里程碑寫 marker 檔（mandate 要的 fallback 一併保留作冗餘審計線）。
**未 wire 任何外部訊息發送**。實證：vol_event INFO 告警與既有 BB-SENTINEL 告警同落 alerts.jsonl。

## 關鍵 diff（行為核心）

事件偵測 → 分析 → 入帳：
```
detect_events: classify_hours → tape 窗內 high_vol 小時 → gap≤1h 合併 cluster → anchor/direction
analyze_event: analysis.run(since=cluster_start, until=cluster_end+1h, regime_split=True)
               → 抽 report["regime_split_decisive"]["high_vol"] 的 fee_wall_test
               → per-axis {gross_bps, net, survives_taker/maker, verdict} + n_rows + status
ledger.events[anchor_iso] = {direction, anchor_ret_bp, cluster, hours[], analysis{...}, event_index}
```

## 治理對照

| 硬約束 | 本任務 |
|---|---|
| 唯讀 PG（不寫） | connect 已 set_session(readonly=True)；0 INSERT/UPDATE；只寫 research artifact |
| 不碰 max_retries / live / execution_authority / system_mode | 完全未觸碰任何 production engine/risk 檔 |
| 不改 sibling microstructure 檔 | 只 import `data_loader`，0 修改 |
| 不擴 scope | 只編排 + 累積 + 通知，0 新統計（leak-free 由既有 harness 保證 shift(1) PIT） |
| 跨平台路徑 | 全走 `$HOME` / env（`OPENCLAW_BASE_DIR` / `OPENCLAW_DATA_DIR`）；無硬編 user path |
| 注釋規範 | 新檔 MODULE_NOTE + 中文 rationale（為什麼 cluster / 為什麼 sink read-only-safe） |
| SCRIPT_INDEX 登記 | 已登 2 腳本 |
| 新 singleton | 無（無 mutable singleton；ledger 是檔案狀態非進程單例） |
| 檔案大小 | py 521 行 / sh 30 行（< 800） |

無新 SQL migration（純 SELECT），故 Guard A/B/C 不適用。

## Dry-run 實證（Linux，2026-06-18）

```
./vol_event_trigger.sh --dry-run --max-events 1
→ detected 3 event clusters in tape; 3 new; analyzing 1 this run
→ event #1: downside anchor=2026-06-17T19:00:00+00:00 (-186.8bp)
→ status=ok n_trade_rows=8060967 survives_wall=False verdict=HIGH_VOL_NO_EDGE_SURVIVES
→ notify via durable_sink(alerts.jsonl) + run_log(vol_event_trigger.log)
→ threshold not yet met: 1/3 events, 0 upside_squeeze; RUN done in 45.5s
```

**Ledger event #1**（`/tmp/openclaw/order_flow_alpha/vol_event_ledger.json`）：
- direction=**downside**, anchor_ts=2026-06-17T19:00:00Z, anchor_ret_bp=-186.8
- cluster 18:00→06:00（13 high_vol 小時，any_spike=true）
- analysis: status=ok, n_trade_rows=8,060,967, n_obtop_rows=1,305,266, 12 grid symbols 含 BTCUSDT
- 3 軸全不過牆：OFI@10s fwd5s gross 0.26bp / fwd15s -0.18bp（net_vs_taker ≈ -5.8bp）；
  microprice gross 6.81bp 但 net_minus_own_spread -5.77bp = `ARTIFACT_BELOW_OWN_SPREAD`
- decisive_verdict=**HIGH_VOL_NO_EDGE_SURVIVES**, survives_wall=False

**idempotency rerun**（`--max-events 0`）：detected 3 clusters / 2 new / analyzing 0 / ledger 仍 1 event / 0.5s。

NOTIFICATION 落點確認：`alerts.jsonl` 末行 = vol_event INFO（channels_attempted=[]）；
`logs/vol_event_trigger.log` 三行 run 記錄；per-event artifact `events/event_20260617T1900.json`(37KB)。

## 提議 crontab 行（**不自行安裝**，待 parent 審查 + 安裝）

每 2 小時；env-prefix 與既有 OpenClaw cron 慣例一致；DB URL 由 `.sh` 從 runtime_secrets 檔解析（不入 cron 行）：

```
0 */2 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/research/order_flow_alpha/vol_event_trigger.sh >>/tmp/openclaw/logs/vol_event_trigger.cron.log 2>&1
```

## 不確定之處 / 偏差

1. **dry-run 用 `--max-events 1`** 以乾淨 seed「event #1 = 19:00 downside」（符合 mandate §7 措辭）。
   tape 內另有 2 個更早的 cluster（08:00 -93.5bp downside / 14-15h spike+98.5bp）尚未入帳；正式 cron
   會按 |ret| 排序逐次補入（最強優先）。**理由**：mandate §7 明指 event #1 = 19:00；最強優先排序讓最具
   決定性的事件先入帳，且 bounded。
2. **upside_squeeze 仍缺**（regime diversity 未達）：tape 內最強事件皆 downside；14-15h cluster 的 anchor
   是 15:00 +98.5bp（upside），下次 cron 取到它即補上 squeeze。robust-ruling md 在 ≥3 事件 + ≥1
   upside_squeeze 前不產出（現 pending，正確）。
3. **事件窗大時 trade rows 大**（19:00 cluster 13h = 8M rows / 45.5s）。仍 < 2min，但若未來捕捉更長
   的連續 high_vol run，單事件可能逼近 2min。已 bounded（max-events 限事件數）；若需可加單事件窗上限，
   屬後續增強（未在本 mandate scope）。

## Operator / parent 下一步

1. E2 審查本實作（強制鏈 E1→E2→E4→QA→PM）。
2. 審查並安裝上方 crontab 行（每 2h）。安裝後 cron 會逐次補入剩餘事件（含 15:00 upside_squeeze），
   累積到 ≥3 事件含 ≥1 squeeze 時自動寫 `docs/CCAgentWorkSpace/E1/workspace/reports/vol-event-robust-ruling.md`。
3. 兩新檔已 scp 至 Linux `~/BybitOpenClaw/srv/helper_scripts/research/order_flow_alpha/`（與 Mac 同步）。
