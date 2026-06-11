---
name: project-2026-06-10-l2-p4-ratify-p2p-shipped
description: L2 P4 設計三點裁決全清（MIT 7 項+QC sign-off+交叉 ack）+ P2p incident_sentinel 同日全鏈 merge main；OQ-1 揭告警通道全未配置；P4 殘=operator V137 確認
metadata: 
  node_type: memory
  type: project
  originSessionId: 41324aa7-e13b-455f-b627-6a627f93cf4b
---

# L2 P4 ratification + P2p shipped（2026-06-10~11，主會話=PM）

## P4 完工（2026-06-11）— merged main `ddaafda1`+TODO `d46b5cee`，dormant 三重關

E1 三線（A `eb035e4d` 131t / B 兩段+E2 直修 `3cdcc9ed` / C 改號後 `4d7a4d84`）→ E2 對抗（**C RETURN：V137+[82] 被 P5-SM 同日撞號**——E2 §5e race 檢查抓獲；改 **V138 + [83]-[87]** 全鏈改名+Linux dry-run 重跑×4 證）→ PM 裁決 stage0r **三向映射**（pass→True / fail→False 臂=failed+dead-mode 可達（M1 真值表+QC FIX-1.3）/ defer_data+缺席+字彙外→pending 不鑄 lesson）→ E2 窄審 PASS（f08 紅鑑定= main pre-existing `7b5d92e9` 破的，非 C；E2 直修 pin 為組成封閉斷言）→ 整合分支+V137→V138 註釋 sweep 9 處（P5-SM 的 V137 引用正確不動）→ **E4 GREEN**：兩平台 ×2 決定性、真模組接線三證+自補 wiring 釘子（mock 縫：全家族 monkeypatch resolve 點，A 模組消失全鏈靜默 DEFER 無測試會紅）、scratch-DB deployed-E2E 全鏈（V138 雙 apply 冪等/store partial-index arbiter/hash round-trip 三方一致/視圖三態/reconciler --apply 冪等/retrieve_lessons pg_trgm 真檢索 similarity=0.169 命中）、prod 零觸碰。**owed-operator-gated**：V138 prod apply+sqlx → deployed-E2E → flags（runbook 在 reconciler docstring）。
**教訓**：①migration 號+healthcheck 編號是 git 看不見的全局命名空間——同日兩鏈並行必撞，取號 commit 與 merge 距離越短越安全；E2 §5e re-fetch race 檢查 load-bearing。②agent 在 grounding 撞 spend-limit 死=分段 commit 紀律救回 0 浪費（B 段1 已 push 死也不全損）。③前台 Agent 串行=「turn 不落地」最穩實現（E2/E4/E1-fix 全程前台無一死）。

## P4 online-FDR（設計 `b40b9481`）— agent gate 鏈（2026-06-10）

- **MIT M1+M2 final ratification = APPROVE**：7 項=6 APPROVE/1 MODIFY。**#3 binding**：debit 條件=「overall ∈ {pass,fail} OR dsr stage ∈ {pass,fail}」（math gate 五 stage 全跑無 short-circuit、docstring :1003 誤述 → single-config PBO honest-DEFER 下原設計可無限免費 re-look DSR）。**#2 拍板 Option B**（threshold=max(0.95,1−α_i)；Option A 斷帳本-水準恆等被拒）。自含 bound：per-family mFDR ≤ 0.1·α_target；全域 ≤ α_target 需 **N_fam ≤ 1/γ=10**。α_i ≤ 5e-4 恆成立 ⇒ cap vacuous + threshold ≥ 0.9995 ⇒ **初期 discovery≈0 是設計後果**（healthcheck 監測 conducted>0 非 discoveries>0）。5 條 DB NOTE（V137 CHECK 三值邏輯洞 NULL n_eff 可過/refund×debit_failed 無互斥/orphan refund 向量/debit_id 決定性/pre_reg_id 無 FK）折入 E1-C。
- **QC sign-off = APPROVE-with-FIX**（含 §9 原文重裁）：**FIX-2.1b 唯一 §9 阻斷**——gate 4(b) 原文 `>` 點比較對 daily-bar 區間對象語義不足（`==` off-by-one + 非對齊 oos_start straddle 全漏），正確=「末 bar 尾端 ≤ oos_start」鏡像 `_bucket_admissible`，reason 統一 `sealed_holdout_overlap`。FIX-1.1（consume 限 supersedes head）/FIX-1.2（hash 釘 evidence 窗+先於渲染）/FIX-1.3（falsification 真評估+鑄 dead-mode lesson）/FIX-2.3（confirm=accounting-confirm，null-confirm 率 15-40%，re-scope M1/P5）。
- **FIX-3.1 MIT ACK-with-4-條件**：pre-DSR input-availability skip 謂詞須 **value-invariance**（存在性/計數/日曆 span 可；任何 price/returns 值函數不可）；QC verbatim 的 down-span<180d 親驗為 BTC value-derived 須換「candidate history span<180d」。skip=不渲染不付費，#3 debit 規則一字不改。
- **P4 E1 dispatch 契約=三件套**：PA 設計 + MIT 報告（含 §5a）+ QC 報告。報告皆在 `docs/CCAgentWorkSpace/{MIT,QC}/workspace/reports/2026-06-10--*.md`（Operator/ 有複本）。main commits：`72a08506`/`677b14ff`。

## P2p incident_sentinel — 同日全鏈 merge main `661699e5`

PA `e5a39342` → E1 `d7f5f283`(800 行主件+56 tests) → E2 RETURN（2 MED：read-only 斷言被 docstring 撞字=no-bite；A2 游標 int() 截秒同秒 burst 跨輪吞）→ E1 `1e2b094d` → E2 PASS（200k float round-trip 實證）→ E4 **RED**（A3 默認 loopback vs uvicorn bind Tailscale IP=健康系統常駐假 CRITICAL；+補 timeout 測試 `8b7994fb`）→ E1 `bd324886`（cron wrapper TS autodetect，mirror m11 inline；lib/api_bind_host.sh 是 server-bind 視角不適用）→ E2 PASS → E4 **GREEN**（三證+真 cron PATH /usr/bin/tailscale+真 DSN 7 軸全綠 exit 0）。58 tests 雙平台 parity。
**殘 owed（operator-gated）**：installer apply（`OPENCLAW_SENTINEL_CRON_APPLY=1`）+ §8.3-1 通道 probe + §8.3-3 prod 兩輪 all-pass。

## OQ-1 重大發現 + operator 拍板

Linux runtime **告警通道完全未配置**（`/tmp/openclaw/alert_config.json` 不存在；watchdog 進程 env 0 cred keys）⇒ **既有 watchdog 告警（06-05 接線）一直是靜默 no-op**，20h 事故形狀防線未武裝。operator 拍板**配 Telegram**，creds 至 session 尾未提供（待）。注意 data_dir=/tmp 重啟即失 → creds 持久層建議 env-file（basic_system_services.env），alert_config.json 作 GUI 層。

## 教訓

- QC agent 無 Bash 讀不到 branch-only 文件 → 重構原文失準；救回靠它自留的「不符回我重裁」條款 + PM 把原文 verbatim 貼進續審 prompt。**派 read-only agent 審 branch 文件時，PM 應直接在 prompt 內貼關鍵原文**。
- subagent 撞 monthly spend limit 會以一句話「completed」死亡（result=限額訊息，usage 90 tokens）——重派時加殘留清理條款。
- E4 的真 runtime smoke 是 load-bearing：A3 拓樸缺陷（deployed-default 假 CRITICAL）單元測試結構性抓不到，只有真連線抓得到。對位 [[feedback_evidence_discipline_under_degraded_tools]]。
- 本地 Mac main 落後且帶 patch-equivalent 重複 commit（`88bddd03`≡`175afa01`）——全程用 detached worktree + push HEAD:main，未動本地 main（留樹清理）。
- **Background agent「卡死」RCA（2026-06-11 完整封閉，前一版教訓有誤已修正）**：本 session 所有 agent 死亡皆有明確外因，**0 個真卡死**——(i) 首個 E4=monthly spend limit（result 即限額訊息）；(ii) P4 一代 A/B/C=**operator UI 動作中斷**（三個 transcript 末條同為 `[Request interrupted by user]`，~23:25 operator 問「是否卡住」時的 Esc/stop 動作所殺；A 其實已完成 commit、B/C transcript 已 676/758KB=深度工作中）；(iii) 二代 B/C=PM 誤殺（儀器錯誤）。**儀器真相**：tasks/*.output 是 **symlink**（`stat -f %z` 回 135=路徑長非檔案大小！），真 transcript=`~/.claude/projects/<proj>/<session>/subagents/agent-<id>.jsonl`；**活性正解=stat 該 jsonl 的 size/mtime**（活 agent 秒級增長）；**死因正解=`tail -1` 該 jsonl**（`[Request interrupted by user]`=人為中斷）。E1 重 grounding 期可 ~700KB transcript 全讀零寫檔=正常,勿以 worktree mtime 判死。TaskStop 回「No task found」=已死；殺得掉=原本活著。操作守則：**有 background agent 在跑時 operator 勿按 Esc/stop**；長任務 prompt 加「儘早動手+分段 commit」。**官方語義（claude-code-guide 查證）**：文檔聲稱 Esc 一次/發新訊息只斷主會話 tool、背景 task 應存活；但 desktop app 的 Stop/UI 動作會斷背景 agent（v2.1.144 changelog），且存在 spurious interrupt 開放 bug（[#21477](https://github.com/anthropics/claude-code/issues/21477)）；中斷後 task 移出 registry 且 completion notification 不可靠（[#59962](https://github.com/anthropics/claude-code/issues/59962)）——「同時三個死+No task found+零通知」與此完全吻合。監控正道=`claude agents` 面板 / transcript tail（subagents/*.jsonl）；SubagentStop hook 可發外部通知但有 bug（#19220/#22087），未配置。
