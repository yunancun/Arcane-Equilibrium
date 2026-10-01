# Bybit H2：durable execution recovery（本機候選）

`SOURCE_FIXED_LOCAL_TESTED_NOT_ADOPTED`。2026-09-30 准入，2026-10-01 完成本機修復；
baseline=`c38dc1b9c49cde06520aba44434491e5abd8d3ab`，branch=`codex/bybit-h2-recovery-final`。
原驗收為 workspace `audits/2026-09-28-bybit-historical-solutions/REPORT.md` 的 H2；
本輪 exact-file manifest、驗證及報告在 workspace `audits/2026-10-01-bybit-h2-repair/`。

本節記錄原本機修復階段；後續 commit／審核及三端 source 同步，
以 workspace `audits/2026-10-01-bybit-h2-publication/` 的 exact-head evidence 單獨判定。

## 儲存與恢復

沿用 OMS、PendingOrder、PaperState、逐單對帳及 canonical trading tables，
由 event consumer 的單一 owner 處理恢復。V162 新增三個普通 PG tables：

| Table | 持久化事實 |
|---|---|
| `trading.bybit_recovery` | account/environment scope、generation、financial projection、unresolved tracker checkpoint |
| `trading.bybit_order_intents` | immutable request、原始 pending identity、最新 progress、唯一 venue order ID binding |
| `trading.bybit_execution_inbox` | 首次 execution payload、exec ID、收件序號、applied 狀態 |

detached PG session advisory lock 限定單一 engine owner，checkpoint 更新檢查 generation。
scope 綁定 venue base URL、API-key identity 及 linear category 的 hash；不符時拒絕開啟。
intent／exec ID 不設 TTL，既有 table retention 與 500-ID cache eviction 不解除 durable dedup。
刪除 inbox／intent 會破壞保證，不能作一般清理。

1. 實際 CreateOrderRequest 與 pending 的 symbol、side、qty、price、type、TIF、reduce-only、link ID
   必須一致。immutable intent、canonical order rows、checkpoint 同一 transaction commit 後才送 ready。
   相同 link ID 即使 request 相同也不能取得第二次送單資格。
2. execution 先進 inbox，再 provisional 套用既有 handler。financial projection、tracker progress、
   canonical accounting rows、inbox applied、checkpoint 同一 transaction commit；原 async writer
   共用抽出的 SQL builders，不再重寫這批 accounting rows。
3. commit 成功才公開 snapshot 並更新 Kelly／dynamic-risk closed-trade 統計。失敗回復 financial
   projection、recent fills 及 pending-close observation，保留 unapplied inbox，封鎖所有新提交。
   不確定 COMMIT 結果同樣封鎖；重啟按 PG 實際 committed generation 重建。
4. 重啟先恢復 unresolved tracker、entry／close guards，再重播 unapplied inbox。
   durable terminal progress 保留晚到成交歸屬。僅接受已知 link ID 或明確綁定的 venue ID，
   不以同 symbol／side 猜配。

projection transaction 最多 5 秒，statement timeout 5 秒、lock timeout 1 秒；checkpoint 最大
8 MiB，pending／retired／venue map 各最多 4,096 筆，startup backlog 最多 4,096 筆。
超限保留資料並 fail closed，不靜默截斷。

## 對帳與採用限制

startup／disconnect／DCP 後，新 entry 等逐單 unresolved evidence 收口及 account barrier 完成。
逐單對帳先補 missing execution，再處理 terminal state。account barrier 要求 open orders
完整空頁，USDT one-way positions 的完整分頁及 symbol／side／qty／avg price 與 projection 一致。
未知訂單、缺失／重複 cursor、hedge position 或 drift 保留 entry block。probe 在獨立 task 最多
15 秒、30 秒冷卻，結果須對應同一 generation；slow probe 不等待在 event owner 中。
不完整對帳時既有受控 reduce-only 路徑可用，storage failure 時所有新提交封鎖。
Position WS 只比較，不在 close fill 到達前刪掉持倉及 PnL 歸屬。

首次 adoption 僅容許沒有 legacy order rows、沒有持倉的乾淨 lane；brownfield 必須另有明確
核對的 baseline，本候選拒絕自動從 legacy aggregate／venue snapshot 播種，未提供 baseline 工具。
barrier 不證明 wallet balance／完整歷史 funding 一致，也不能補回 venue history 已不可查的
execution；缺證維持封鎖。這些是現有交易 lane 採用前的具體限制。

## 本機證據

18 項 H2 回歸全部通過；完整 engine library 4,926 通過、17 項 PG 測試預設 ignored，
該 17 項已在 H2 suite 另外執行；strict library Clippy 通過。
指定 `/private/tmp/bybit-h2-pg-*` cluster，每 case 建獨立 DB，最小 canonical tables 加實際 V162
double apply，不使用 ambient DATABASE_URL；不是完整 Timescale migration tree 證明。

| 六類 crash cutpoint | 實際驗證 |
|---|---|
| intent commit 前 | SQL trigger 中斷，沒有 ready、intent、canonical order |
| intent commit 後、venue call 前 | owner teardown／reopen，intent／guard 保留；空 REST 不放行 |
| venue received 後、ACK 前 | SubmissionStarted 後重開，REST fixture 補 partial execution，再處理 cancel |
| inbox 後、projection 前 | receive 後重開，unapplied replay 只計一次 |
| accounting／applied／checkpoint transaction 途中 | 三處 SQL trigger 中斷及 pg_terminate_backend，無部分 accounting，重開一次 |
| projection commit 後、snapshot 前 | 不可寫 snapshot fixture，從 PG 恢復及重播不改 accounting |

另涵蓋 502 筆後最舊 ID replay、partial fill、cancel 後 late close fill、funding restart、
owner／account／execution conflicts、malformed request、未知 venue ID、migration identity guard、
slow／stale account probe。使用 owner teardown／reopen 與真 PG backend death，未執行 Linux
service crash 或真 venue recovery。源碼與本機測試不能推論 production readiness。

PA／E2／E4／BB 獨立 gate 未執行；Controlled CLI review 要求 clean approved committed
checkpoint，本轮為未 commit 的修復候選。沒有啟動 native automatic delegation。
未 commit、push、merge、套用共用 PG migration、部署或呼叫 private broker；runtime 未驗證。
協定參照：[Bybit execution history](https://bybit-exchange.github.io/docs/v5/order/execution)、
[PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html)。
保證由原子 transaction 與恢復測試界定，不能從 ON CONFLICT 單獨推論。

## 2026-10-01 發布審核觀察

Operator 已授權 commit、審核及 Mac／GitHub／Linux source 同步。
候選移至 `codex/bybit-h2-publication-20261001` 的 clean committed checkpoint，
原修復 worktree 與歷史證據保留。本節 supersedes 上節「未 commit」的階段狀態。

PM 檢查確認 `H2PUB-API-001`：account barrier 把 position 的 200-row limit
用於 open-order endpoint，超出其 50-row 上限，使已對帳的空帳戶也不能解鎖。
已改為 open orders `limit=50, openOnly=0`、positions `limit=200`；模擬實際 API
參數拒絕的回歸先 RED 再 GREEN。這是 PM source 檢查，不能代替獨立審核。
[Open-order contract](https://bybit-exchange.github.io/docs/v5/order/open-order)、
[Position contract](https://bybit-exchange.github.io/docs/v5/position)。

本輪重新執行 H2 19 項全部通過，engine library 4,927 通過、17 項 PG 預設 ignored
（已在 H2 suite 另執行），strict library Clippy 通過。
PA controlled CLI 初次及唯一一次 recheck 都在模型請求逾時後停止，未返回 verdict；
獨立 gate 為 `UNVERIFIED`，E2／E4／BB／R4 沒有獨立 PASS。Linux source preflight
SSH 逾時，沒有 Linux 修改。合併與三端採用未完成；可保留 feature commit／draft PR
供後續審核，不能宣告 `DONE`。exact-head 狀態與原失敗紀錄以 workspace
`audits/2026-10-01-bybit-h2-publication/` 為準。沒有部署或套用共用 DB migration。

## 2026-10-01 PR #200 review 修補

本節 supersedes 前段「尚未發佈」的階段狀態；current-head publication、CI、review threads、
merge 與 Mac source 採用，以 workspace `audits/2026-10-01-bybit-h2-merge/` 的 exact-head evidence 判定。
Operator 已指示完成 merge／push，Linux host source 同步略過；不授予 runtime 或共享 DB 變更權。

GitHub PR #200 的六項 review 已在同一 H2 範圍補修：

- Provisional close 的 exit features、Agent Spine lineage、decision lease settlement，
  以及 pipeline 產生的 stop／fallback 請求，都先留在單一 event owner 的 buffer。
  recovery transaction 成功後才發佈；失敗丟棄 buffer、恢复 financial／tracker／close guard。
  這些 derived observations 仍沿原有 best-effort channels，沒有跨 process 的 durable outbox 保證。
- startup 除 checkpoint pending 外，從 durable intents 讀取已綁 venue、尚有未填量的 cancelled／
  rejected terminal trackers，沿原有逐單 REST reconciliation 補 execution 後再跑 account barrier。
  這不依賴 transient retired map 是否被較晚 checkpoint 清除；最多 4,096 筆，超限 fail closed，
  缺失或不可查的 history 仍阻擋 entry，不自動捨棄 identity 或播種 baseline。
- execution.fast 的空 execType 可由 REST 的已知 type 補全，已知 type 寫回 inbox；
  兩個不同的非空 type 仍拒絕。已 applied 的 duplicate 不再計 qty／fee／PnL。
- fence 在排隊後生效時，dispatcher 拒絕並移除未 claimed 的 queued reservation；
  已 claimed 的 intent 仍保留，duplicate 不得終止原單。
- venue order binding 必須有非空 identity 且更新恰好一個 durable intent；未知／manual order
  不再因 UPDATE 0 rows 被視為成功，新提交維持 storage fence。
- V162 Guard C 在重用 partial index 前核對 table、btree、欄位順序、ASC、有效性與 NOT applied
  predicate；不相容的同名 index 明確拒絕，compatible double apply 保持冪等。

六項新回歸先 RED；修補後 H2 25 項全部通過，engine library 4,928 通過、22 項 PG 預設 ignored
已在 H2 suite 另行執行；strict library Clippy、完整 release engine binary 和 schema target 編譯通過。
主程式驗證亦涵蓋 CI 揭露的 Send bound：checkpoint 使用 owner 的 exclusive pipeline borrow，
沒有內部 await 的 account poll 為同步方法，不向 Strategy 增加 Sync 要求。
以上仍為 source／隔離 fixture 證據；原 PA controlled CLI 初次與唯一 recheck 無 verdict 的事實保留，
GitHub current-head review 與 CI 的實際結果另以 publication artifacts 記錄，不改寫成 independent PASS。
