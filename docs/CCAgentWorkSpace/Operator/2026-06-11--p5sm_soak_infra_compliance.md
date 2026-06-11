# CC 合規審計 — P5-SM soak 監測基建 · feat/p5sm-soak-observability @ d7a9eacf · 2026-06-11

> **PM 代落盤註記**:本報告由 CC agent 產出,該 session 無 Write 工具,內容由 PM 逐字代存(2026-06-11,前例=2026-06-10 OPS-2 CC 報告)。

- 對象:worktree `/tmp/wt-p5sm-soak`,base main `bb02b14c`,7 commits(Wave1 `58ad4dba` → E2-fix `0ce0874c` → E4 補測 `d7a9eacf`)
- 鏈位:鏈尾治理覆核(PA 設計 §5.2 指定),前置 E2×2 ACCEPT + E4 PASS;CC 不重做隔離性/零 mutation/回歸軸,僅治理軸
- 工具限制:本 session 無 Write/Bash,靜態審計以 Read/Grep 對 worktree 實檔執行;0 Rust 改動(E4 親驗)

## 評級:A · 判定:Approve(0 BLOCKER;2 LOW + 3 INFO 不阻)
合規:16/16(適用項全 PASS,N/A 標註)+ 9/9 不變量(適用項)+ 硬邊界 0 觸碰

## 軸 1 — SM 治理邊界:PASS

| 組件 | 權威路徑接觸 | 證據 |
|---|---|---|
| canary | 0 | 只打 `METHOD_IS_AUTHORIZED`/`METHOD_GET_STATUS` 兩讀 arm(governance_ipc_canary.py:87-92,297-322);`acquire_lease\|release_lease` grep 全檔唯一 hit=:65 docstring(聲明 0 引用);0 PG 寫;dispatcher=lazy `one_shot_ipc_call` 同 lease bridge fail-closed 生產路徑(:270-283),無新 IPC 面 |
| flusher 擴充 | 0 | 寫面=V129 UPSERT(既有觀測投影模式)+V137 純 INSERT(:347);讀 flag 與計數器 getter;0 lease 操作;全步驟 fail-soft 不向權威路徑傳播 |
| `[82]` healthcheck | 0 | 0 寫 SQL;純 SELECT+防禦 rollback(:386-389 鏡 check_81);0 IPC |
| smoke(S5b) | 走 SM 正門,mutating 面圈住 | 經生產 bridge 穿過 lease SM 而非繞過。圈欄五重:①零排程接線(獨立 grep 復核;雙重明文禁 cron)②默認 dry-run exit 0 零 IPC ③mainnet guard exit 7 ④互動確認 unless --yes ⑤`soak_smoke:` intent 前綴+TTL 30s+release 即收+PG session 硬 readonly(:191) |

## 軸 2 — 自主性方向:PASS(0 自動擴權)
`[82]` 結果全 repo 唯一消費者=runner(append 進 results 供 operator 判讀,無程式化迴路翻 flag/晉升);step-iii CUTOVER 明文 operator sign-off+CC/E2/BB/E4;canary 失敗只降頻;無新 AgentTool。

## 軸 3 — V137 append-only 紀律:PASS(1 INFO)
全 worktree 該表 UPDATE/DELETE/TRUNCATE=0;唯一寫入端=`_insert_soak_events` 純 INSERT,fail-soft;heartbeat tracker 寫入成功才前移(寧重勿漏);Guard A fail-closed+7 型 CHECK fail-loud+`created_at DEFAULT now()` DB-side 權威。INFO-1:append-only 靠 writer 慣例非 REVOKE(同 V054/V129 慣例)。

## 軸 4 — flag 語義:PASS(1 LOW)
嚴格 `=="1"` 默認 OFF;持久化=針對前兩輪 soak「restart 無聲終結」的修復;operator-env 一次性語義仍優先;SOP 三處明文 soak 結束移除。LOW-1:「soak 結束 flag 忘關」無自動絆線(失守代價有界:flag 只控唯讀探針+heartbeat ~48 row/day)。

## 軸 5 — 16 原則+9 不變量:適用項全 PASS,0 違反
重點:#1 訂單面零接觸/#3 smoke 行使而非繞過 Lease/#5 mainnet guard+五條 fire-防護/#6 全鏈 fail-closed(唯一 fail-safe 例外=cadence 解析回默認,理由文檔化+`[82]` floor 兜底)/#7 寫入限 learning.* 觀測表。不變量 #2 被強化(smoke 正是驗 acquire→ACTIVE audit 的儀器)、#6 同向加固(smoke 對 mainnet 反向加閘)、#7 方向一致;其餘 N/A。

## 硬邊界體檢
無觸碰。app 4 生產檔+`[82]`+V137=0 hit;runner :1413=pre-existing 自證注釋;restart_all.sh hits 全 pre-existing 段(本分支新增僅 :770-777/:795-796 兩 canary env);smoke 4 hit 全為防禦性 mainnet guard(加閘方向)。0 新增/修改/移除 fail-closed;新碼 0 硬編路徑。

## 違規清單 + 建議(全量,濾裁交 PM)

| # | severity/confidence | 描述 | 建議 |
|---|---|---|---|
| LOW-1 | LOW/高 | soak 結束 flag 忘關無自動絆線;移除靠 SOP 人工,`[82]` 對健康常開窗永遠 PASS | 可選:`[82]` 窗齡 >21d WARN 或 SOP 加 review date;不阻 |
| LOW-2 | LOW/中 | 假陽性候選:`[82]` active 推定計全部 72h 內事件(無 flag 過濾),flag-OFF 期間 restart(pre-soak 先部署後開 flag、或 post-soak 移 flag 後)→ 連續 ≤72h FAIL「soak invalid: flag currently OFF」噪音,風險=alert fatigue。happy-path 部署序不觸發;方向 fail-closed 非假綠 | 任選:active 推定只計 `flag_enabled=true` 事件;或 SOP 文檔化「移 flag 後 72h 內 [82] FAIL 屬預期」;不阻 |
| INFO-1 | INFO | V137 無 REVOKE 防禦層(echo E2 INFO-1,同 V054/V129 慣例) | 可選防禦性 REVOKE;不阻 |
| INFO-2 | INFO | cadence env 無下限鉗(1s=PM 批准的 E4 鉤子);single-flight+2s timeout 已界上限,E4 1s/240s 實測零影響 | 若要加固=非 E4 環境鉗 ≥30s;不阻 |
| INFO-3 | INFO | smoke 確實簽發真 Production Decision Lease(S5b 目的即此):intent 綁定+TTL 30s+即釋+不掛單 | 無需動作;收口報告如實表述 |

## 前置 owed(非 CC 新增,確認站立)
V137 正式 apply 前 per-SOP Linux PG 雙跑(PM 已親驗 prod=136+dry-run 重做 PASS)=deploy gate;soak 真啟動後 runtime 觀察期=deploy gate;step-iii cutover=operator sign-off+CC/E2/BB/E4。

判定:**Approve(A)**。本基建把治理 SM 的 soak 證據從「易揮發 in-memory」升級為「append-only 可重建帳本」,方向與原則 8/10/12 一致;唯一 mutating 面圈欄完整。
