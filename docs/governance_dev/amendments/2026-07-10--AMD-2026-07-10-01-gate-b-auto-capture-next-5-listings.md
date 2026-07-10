# AMD-2026-07-10-01：Gate-B 新上市自動 capture 授權（未來 5 個新上市，cap=5）

日期：2026-07-10
狀態：**Active — Operator 授權（2026-07-10，經 R3 修復包主 session 轉達）**
作者：E1（R3 修復包 WP-B，charter 轉達 operator 原話「1同意,2我同意並授權你,3同意…進行乾淨修復」）
關聯規範：ADR-0047（Alpha-Edge regime evidence governance）、AMD-2026-05-31-01（bull-data labeling）、DOC-06 + AMD-2026-07-04-01（runtime mutation 紀錄 RM-1..4，cron 活化適用）
關聯基建：`helper_scripts/canary/gate_b_watch.py`（上市偵測 watcher，2026-06-12）、`helper_scripts/research/aeg_gate_b_probe.py`（R-0 隔離 24h capture 探針，2026-06-02 部署）
範圍：**只授權「新上市窗口的隔離 Gate-B capture 自動啟動」**，上限 5 個新上市 symbol。不授權任何交易 / order / Cost Gate / promotion / runtime mutation。

## 背景（為什麼要做這個）

Gate-B listing-capture 基建自 2026-06-02 部署以來維持「alert-only + operator 手動啟動探針」姿態；
2026-06-02 首個 24h 窗口為 operator-timed 一次性授權。2026-07-09 盈利研判 R3 把「新上市寬價差
niche」列為仍開放的機會軸（top move #7），但每次上市窗口都依賴 operator 即時在場手動啟動探針，
稀有事件（PreLaunch→Trading 轉移）屢因人不在場而漏捕。

Operator 於 2026-07-10（經 R3 修復包主 session 轉達）授權：**未來 5 個新上市自動觸發 Gate-B
capture**，cap=5，R-0 zero-leak 邊界原樣，cap 滿自動停 + audit 行。

## 授權條款

> **AMD-2026-07-10-01-1（自動觸發授權，cap=5）**：`gate_b_watch` 偵測到 fresh 新上市窗口
> （`recommended_action == START_GATE_B_NOW` 且 trigger 屬新上市類）時，得自動啟動一次
> `aeg_gate_b_probe.py` 隔離 24h capture。授權總量 = **5 個新上市 symbol**（去重後計數）；
> 計數器持久化於 `gate_b_watch_state.json`（`auto_capture.captured_symbols`），跨 cron 輪 / 重啟不歸零。
>
> **AMD-2026-07-10-01-2（cap 滿自動停 + audit 行）**：第 5 個 symbol 消耗後，自動觸發永久停止
> （fail-closed，不滾動續期），並寫一條 `cap_reached` audit 行到
> `<data_dir>/gate_b_watch/gate_b_auto_capture_audit.jsonl` + 發一條告警。每個 slot 消耗 /
> probe 啟動 / 啟動失敗各寫一條 audit 行（含 `authorization: AMD-2026-07-10-01`）。
> 續期或調升 cap 需**新的 operator 授權（新 AMD）**；代碼內 `AUTO_CAPTURE_CAP = 5` 由測試釘住。
>
> **AMD-2026-07-10-01-3（R-0 zero-leak 邊界原樣）**：自動啟動的唯一目標是既有 R-0 隔離探針
> `aeg_gate_b_probe.py`（不 import 任何生產模組、零 auth / 零 order / 零 DB write）。capture
> 產物只落 `<data_dir>/aeg_gate_b_runs` research artifact 目錄，**不進任何交易路徑**
> （scanner / strategy / intent / Cost Gate / Decision Lease 均不消費）。無 transition 的窗口
> 記為 INCONCLUSIVE_NO_TRANSITION，不作 alpha 證據（ADR-0047）。
>
> **AMD-2026-07-10-01-4（啟用開關與失敗語義）**：功能預設 OFF；env
> `OPENCLAW_GATE_B_AUTO_CAPTURE=1` 才啟用（Linux cron 活化屬 runtime mutation，走 DOC-06
> RM-1..2 before/after 快照，由主 session 執行）。探針 spawn 失敗 fail-soft：**不消耗 cap 名額**、
> 寫 `probe_launch_failed` audit 行，窗口仍 fresh 時下輪 cron 自然重試。

## 觸發邊界（防 cap 誤耗）

- 合格 trigger 僅兩類：`prelaunch_active`（instruments-info PreLaunch，交易所權威源）與
  `announcement_pre_market_listing`（新上市公告；symbol 須同時出現在公告**標題**內，
  防 description 正文提及他幣種的 regex 誤匹配燒名額）。
- `announcement_standard_conversion`（既有 pre-market 轉標準合約，非新上市）與
  pre-IPO review 類**不觸發**，維持 alert-only。
- 同 symbol 只消耗一個名額；同時多個新上市共享一個運行中探針
  （探針 REST 層本就輪詢全部 PreLaunch symbol），每個 symbol 仍各計一個名額。

## 不變量（不因本授權鬆動）

- 無 live / demo-only 姿態不變；本授權零 order、零交易效果。
- Cost Gate / Decision Lease / 5-gate / `live_execution_allowed` 等硬邊界零接觸。
- `gate_b_watch` 其餘行為（告警、artifact、去重 state）不變；public GET only。
- capture 產物做研究判讀（capture_lag / markout / 寬價差 niche 評估）仍走
  `aeg_s3_gate_b_preflight` / `aeg_s3_gate_b_chain` 既有離線 evidence chain，人工 review。

## 驗收標準

- flag OFF（預設）：`gate_b_watch` 行為與授權前 byte-equivalent（alert-only，零 spawn）。
- flag ON：fresh 新上市 → 探針自啟一次 + state 計數 +1 + audit 行；第 5 個 symbol 後任何新上市
  只產生 `CAP_REACHED` 狀態與（一次性）cap_reached audit 行，零 spawn。
- 測試：`helper_scripts/canary/test_gate_b_auto_capture.py` 覆蓋 cap 釘死 / 去重 / cap 滿自停 /
  spawn 失敗不耗名額 / 隔離紅線靜態 grep。
