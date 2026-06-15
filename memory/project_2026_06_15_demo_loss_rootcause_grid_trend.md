---
name: project_2026_06_15_demo_loss_rootcause_grid_trend
description: 2026-06-14/15 demo「大量虧損」根因 = grid-in-trend × BTC+4.5% 漲;ADPE 主假設被推翻(decorative);揭 ADPE IPC auth bug + 引擎 4 次 crash + 無 demo 損失熔斷
metadata: 
  node_type: memory
  type: project
  originSessionId: 9ed167b4-e281-4181-b080-eb0c9d9ad5e3
---

# 2026-06-14/15 demo 虧損根因研判（ultracode 4-verifier 對抗複核,信心 HIGH）

operator 問「昨晚到今天大量虧損根因」。主會話先取 runtime PG(`ssh trade-core`→docker `trading_postgres`,db `trading_ai`/user `trading_admin`),再派 4-verifier workflow 對抗複核。**初步 ADPE 假設被多重證據推翻。**

## 根因（分類 b:防護不足但可解釋,非 bug 非回歸）
- **= grid_trading 的 grid-in-a-trend / down-beta × BTC +4.5% 上漲行情（廣泛山寨漲:NEAR+17.6% LINK+8.2% ARB+7.0%）。** 同一份靜態代碼:06-12 漲跌下開多獲利,06-15 漲勢中一路向上開空(opens Sell 40 vs Buy 3)、回調以更高價平空 → `grid_close_short` Buy 平倉 37 筆淨 -39.83(僅佔名目 -0.132%,每筆微小逆向,無異常)。06-15 grid 成交量 ~15-21→78(4x)= 漲勢多次上穿格線。
- **方向由市場決定,非配置/參數改動**:grid 代碼自 2026-06-10 零 commit,grid 參數最後實質改 2026-05-31。與所有歷史 NO-GO 同源 [[project_2026_06_13_profit_diagnosis_searchspace_reconfirm]] [[project_2026_06_03_blocked_signal_and_cascade_fade_nogo]]。
- 放行負 edge grid 空單的閘門 = **早於 ADPE 的 EDGE-DIAG-2 低樣本探索分支**(`gates.rs:179-191`,`cost_gate_min_n_trades_for_block=15`,2026-04-28 起);多數 grid cell n<15。平虧空單走 `is_reducing→instant allow`(`risk_checks.rs:150`)完全不過閘。

## 範圍/量級(非緊急)
- **純 Bybit DEMO 沙盒,零真錢**(近 7d fills 只 demo/live_demo,全 is_paper=t,無 live)。
- 06-14 18:00 起:已實現 **-50.79** + 手續費 **29.54** = net-after-fees **~-80**(≈ $87.6k 周轉 9.2bps,**~37% 是手續費**)。relative demo 餘額 ~$9,822:最糟單日 0.65%、兩日 0.89%,距 15% 日損熔斷 ~17x 之遙。**已了結**(僅剩 0.01 BTC 空單 uPnL+1.30)。
- headline「-87」混淆 realized(-50.79)+fees(29.54);grid 乾淨切口 -45.33 非主會話初報 -67(窗口/symbol 口徑差,結論不變)。

## ADPE 主假設被推翻(關鍵新事實)
- ADPE 在虧損窗口 = **near-no-op 觀察者**:每 cycle `all_flat=True`(bandit 正確判每 arm 負 EV),256 skipped_same+64 failed,**零激活/停用/重配**。
- explore-gate 成本放寬實際只 12 筆(06-14 23:33-23:41 UTC 8 分窗,**在峰值虧損 06-15 01:00-07:00 CEST 之外**);且 runtime `edge_estimates.json` explore_eligible=True 計數=0(寫入競態:每小時 :12 的 `edge_estimate_snapshots_cycle_cron` 清掉 ADPE :00/:30 寫的欄位,last-writer-wins)。
- grid 在 ADPE 啟動(06-14 11:00)前數天已活躍 → 非 ADPE arm。
- **ADPE 真實角色 = 次要放大器 + 嚴重防護不足**(keep-explore-active `runner.py:381-400` 覆蓋 bandit 正確的 all_flat stand-down,逼 grid 24/7 不休眠),但**未實質造成此次虧損**。

## 順帶揭出的獨立 latent 問題(已 spawn_task / 列 follow-up)
1. **無 demo 小尺度損失熔斷器**:grep circuit|breaker|loss_cap|max_loss|drawdown|halt 於 ADPE+`regime_bandit_allocator.py`=0;唯一界限 `explore_budget=30`(試次計數非損失)。%-based 日損15%/回撤25% 閾值比此次大 17-30x,數學上永不觸發。建議 per-strategy 日 demo realized 損失上限。
2. **ADPE IPC auth handshake bug**:`set_strategy_active` 每 cycle 因 `first message must be __auth` 失敗 64 次 → ADPE 目前**無任何可用執行通路=裝飾品**(`adaptive_demo_profit_engine/ipc_lever.py`)。
3. **引擎 06-15 crash 4 次**(01:28/01:45/04:04/07:33,watchdog snapshot-staleness 自愈 ~14s,total crashes=6)**不寫 high-severity audit_events** → 造成「零異常」假象。主會話初報「零 crash」**已更正**。獨立穩定性問題。承 [[project_2026_06_05_engine_selfheal_bindhost_incident]]。
4. grid trend hard-stop(`signal.rs:140-149` EDGE-P1-1)對 None 指標 `.unwrap_or` fail-open(adx/hurst None→默認非趨勢=放行)→ 整夜漲勢趨勢停沒觸發;既有弱點非 06-14 回歸。
5. 風控審計可追溯缺口:DB 只記單一 `guardian_checks` 字面字串(`commands.rs:246`),無法區分 normal/低樣本 explore/ADPE explore-pass。

## 明確「不是」原因
引擎重啟(虧損早 13.5h 前已始)/crash 致虧/phantom-fill 賬務 bug(數量對帳吻合、realized 符號正確)/真錢/風控被攻破(98.8% reject=正常 fail-closed)/ADPE 主動下單/配置參數回歸。

## 教訓
- runtime PG 取數:`ssh trade-core 'docker exec -i trading_postgres psql -U trading_admin -d trading_ai'`(SQL 走 stdin 避免巢狀引號);namespaced schema(trading/agent/learning/replay/research)。
- 主假設(時間相關性 ADPE 激活→虧損)被代碼+log+cron 實證推翻 → 相關≠因果,讀源碼勝過時間線推測。
- crash 不入 audit_events,「零高危事件」≠「無 crash」,須查 watchdog.log。

## 演變軌跡
- **2026-06-15:上方 #2「ADPE IPC auth bug = decorative」已 RESOLVED**(commit `3e31d87a`,main)。根因**不在 `ipc_lever.py`**(它正確委派 `sync_ipc_call`,後者本就先送 `__auth` HMAC 握手)——真因是 `helper_scripts/cron/adpe_runner_cron.sh` **未注入 `OPENCLAW_IPC_SECRET_FILE`**;cron 不繼承 engine daemon shell env → `get_secret_value` 回 None → 跳過 auth → `set_strategy_active` 當首幀被引擎拒。與 sibling `ml_training_maintenance_cron.sh`(commit `3d8d543e`)同一 bug 類;fix 即鏡像其 secret-file 注入(env-first/file-fallback,僅傳路徑非值)。讀路徑是 file-based snapshot 故一直能用(故 log 多為 skipped_same,只 write 失敗)。runtime 實證:funding_arb failed→**applied**→持久化(demo snapshot `active:True`)→第二跑全 5 skipped_same(冪等證寫入生效)。**ADPE 自此可在 demo 真實 actuate**(demo 硬鎖 fail-closed,live 5-gate 完全未碰;注 OPENCLAW_IPC_SECRET_FILE 只開 IPC 傳輸層握手,不滿足任何 live gate)。**副作用**:ADPE bandit 現會真的 set demo 策略 active/dormant(此次已激活 funding_arb,explore_budget=30 有界、`--kill-switch` 可還原)。#1(無 demo 損失熔斷)仍 open。
