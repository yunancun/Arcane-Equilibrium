# IBKR Live-Capability Loop(W5→W11 自主推進協議)

本協議只有在 exact Operator request 明示 `/loop`（或同義持續執行），且 route 綁定
`continuation_mode=operator_loop` 時才 active。普通 IBKR 任務是 `finite`：完成指定
scope 一次、回報、停止；不得因本檔存在或 queue 尚有 row 就排 wakeup。

版本 v2(2026-07-16;v1=2026-07-15)。本檔是**穩定協議正本**:當前任務狀態不寫進本檔(讀 `TODO.md` W 行);工程設計細節不寫進本檔(讀 repo 根 `IBKR_TODO.md`)。任何 session(現任或接棒)照本協議即可續跑。**本檔非授權文件**:授權鏈=AMD-2026-07-11-01(development-only)+ ADR-0048(amended);活化(EA1-EA8)全 Operator-gated,loop 永不執行。

**v2 變更(R8 校準,審計實證驅動)**:①S1 並行從「允許」升為「有程序」(file-surface manifest+指名合格對);②S6 固定記帳 checklist 8 項+前輪 SHA 回填(修 v1 記帳漂移根因:只刷本輪行,IBKR_TODO §0/§4.4 凍結);③CI 節流(draft-PR 閘 macOS/記帳併末次 push/禁 skip 最終 head);④§7 反空轉硬規則(三選一/連續兩輪零代碼 halt/findings 一次性定性);⑤工作樹衛生(worktree 清點/命名/WIP 早推/主 checkout 唯讀);⑥§6 接棒升級(死亡三分類 SOP/billing 事故判別)。v1 骨架(一輪一 PR/S0 同步門/E2 對抗門/帳本 append-only/XL 先切片)經 R0-R7 實證保留不動。

## 0. Load(每輪必讀,順序固定)

1. 本檔 → `IBKR_TODO.md`(工程正本:§5 每包 DoD 與切片計劃、§5.5 日誌安排、§4.4 差距表、§4.5 審計殘項、§2 邊界)→ `TODO.md` 的 `*-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-*` 行(dispatch 正本)→ 帳本 `docs/execution_plan/ibkr_live_capability/PROGRESS.md` 最後 3 行。
2. 職責分界:TODO.md 管「哪個包、什麼狀態」;IBKR_TODO.md 管「怎麼做、驗收什麼」;本檔管「每輪怎麼轉」;帳本管「轉過什麼」。四者衝突時按 todo-maintenance.md 的 class 規則裁,不得平均化。

## 1. 角色

主 session = PM+Conductor(不寫業務碼,只編排/裁決/記帳);實作與審查全派 sub-agent,role chain 按 TODO 行(PA/E1/E1a/E2/E3/E4/IB/OPS/QA/CC)。E1 一律 worktree 隔離;BG agent 按駐留等收 SOP 收割。

## 2. 硬邊界(每輪 S0 自查,任何一條被工作觸碰即停輪記帳)

- **零真實接觸**:不連任何 socket 到 IBKR/Gateway、不裝真憑證、不 production seal、不 enable Gateway systemd unit、不把 lane/connector/contact/order 任何旗標翻 true。fake-TWS 與本地 fixture 不算接觸(AMD-07-11 明文)。W9a 的 Gateway「安裝」是 OPS runtime 動作走 operator 批准窗,安裝後零啟動/零登入/unit masked。
- 不碰 Bybit `crypto_perp` 路徑(每包帶 bybit-live-unchanged 回歸);不降 global Cost Gate;不繞/不弱化 Guardian、Decision Lease、idempotency、audit、limits、kill switch。
- secret 永遠 stat-only;live slot 必須缺席(healthcheck 語義見 IBKR_TODO W9-5);env-var credential fallback 永禁。
- Python/FastAPI/GUI 不得獲得 order/risk/activation authority;非 GET route 只按 IBKR_TODO §5 W9-2 的單方法白名單流程開。
- 測試 fixture 禁硬編日期(相對/凍結時鐘);參數禁假功能;禁 `allow(dead_code)`/fixtures 藏 caller;注釋只寫中文。
- UNVERIFIED 外部事實(GFV 執行機制、paper 2FA 適用性等)未經 IB 帶來源現勘,不得寫成代碼常數或測試斷言。

## 3. Cycle(R-N,一輪 = 一個 coherent 切片 = 一個 PR)

**S0 同步門(不過不開工)**
a. `git fetch --prune origin`;讀 origin/main head;`gh pr list --repo yunancun/Arcane-Equilibrium --state open` + `git branch -r | grep agent/ibkr` 查在途工作——撞工(同包已有未合 PR/在途分支)即改選其他包或收割它(見 §6)。
b. `ssh trade-core 'cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && git rev-parse --short HEAD'`;記 Linux head。引擎 build_sha 與 main 差距**只觀測、只記帳**(binary 落後屬預期;部署窗只在 W10,operator-gated)。ff-only 失敗 = 三端異常 → 停輪報 operator。
c. re-read TODO W 行;行狀態與 repo 實況漂移時,漂移修復**搭本輪代碼 PR 便車**(見 S6 checklist),不獨立成輪。
d. §2 邊界自查 + runtime 側無 IBKR 異動(引擎 log 零 ibkr 蹤跡屬預期)。
e. **worktree 清點**:`git worktree list`,發現本 loop 前輪殘留(`wt-ibkr-*` 非本輪 slug)即 `git worktree remove`+已 merge 分支清理並記帳;**不動其他 session 的 worktree**。
f. **CI 全紅判別**:若所有分支 dispatch 失敗且 run 呈 `runner=''/steps=[]` → Actions spending-limit 事故,非代碼問題——halt+PushNotification 請 operator 提額,禁 debug 空燒;提額後 rerun 即綠。

**S1 選工(含並行程序)**:按 IBKR_TODO §5.5 日誌安排 + §5 切片計劃 + TODO 行狀態,挑「最高優先、依賴齊、無撞工」切片;XL 包(W7/W9)必須先由 PA 出切片計劃再逐片跑。
- **並行程序(v2)**:reviewer 帶寬空時最多兩切片並行。並行前置=每切片列 **file-surface manifest**(允許觸碰的路徑清單,進 dispatch prompt);兩 manifest **交集非空 → 禁並行**;meta-doc 記帳檔(TODO/PROGRESS/IBKR_TODO/CHANGELOG)由 PM 單獨串行提交,不入任何 E1 manifest。
- 指名合格對:W5-S0(Python/tests/ci)∥ W5-S1(openclaw_types 新檔);W8a(engine authority)∥ W9a(helper_scripts/systemd);carve ∥ W6 切片。指名不合格對:完整 W5 ∥ W6(同撞 session 請求路由/fake-TWS 場景/entitlement_state 三面)。

**S2 派工**:按該行 role chain 派 sub-agent 波;每個 prompt 給定:切片範圍 in/out、file-surface manifest、IBKR_TODO 對應節、DoD、§2 硬邊界摘要、輸出格式。dispatch 前置照 fetch-before-dispatch 紀律;prompt 留 NO-OP exit(發現已被做過就退出報告,不重做)。**E1 硬性要求:第一個綠 checkpoint 即 push feature branch(draft PR),之後每個綠 checkpoint 續推**——feature push 零 CI 成本(push 觸發只認 main),且 agent 死亡後 §6 收割才有對象。

**S3 質量門**:E1 自評不算數。E2 對抗審必過(pr-adversarial-review;發現退回 E1,不代寫);安全/authority 面 +E3(+CC 於硬邊界字段);IBKR 面 +IB(官方事實帶來源+日期);runtime/service 面 +OPS;e2e 宣稱 +QA。E4 計數紀律:新增/總量/PASS,Mac(aarch64)+ Linux 兩腿都要。**同一包連續兩輪被 REJECT → 停該包,PM 反省寫帳本,不硬闖。**
- **findings 一次性定性(v2)**:E2/E3 的 APPROVE_WITH_NOTES notes 在 S6 逐條定性為 {blocking→指名歸屬 W|closed|wontfix+理由} 入帳;入帳後不得二次立案,下輪 reviewer 引用編號不重審(防審過審)。
- reviewer 結論凡可機器化者,固化為 tripwire/守衛入 CI(permit-stub/absence-audit 先例),是防回歸的既定慣例。

**S4 落地(git + CI 紀律)**
- 分支:`agent/ibkr-w<N>-<slug>`(單輪單分支);worktree 命名 `wt-ibkr-w<N>-<slug>`;**主 checkout(srv)與唯讀樹(main-sync 等)禁動工**,一切寫入只在本輪 slice worktree。
- commit 規範 `feat|fix|test|docs(ibkr…)`;meta-doc 用 `git commit --only`;**[skip ci] 單一規則:任何 PR 的最終 head 一律不得 [skip ci]**(required checks 缺席會卡 merge)——docs-only PR 依靠 path classifier 天然低成本(gated job 全 skip,僅 ~4 個秒級無條件 job),不必也不應用 [skip ci]。
- **CI 節流(v2)**:E2 迭代期間 PR 保持 **draft**(macOS job 掛 `!draft` 條件,R9 隨 W5-S0 落地;E2 APPROVE 後才 ready-for-review)——每輪 macOS 10x 從 k 次降到 1 次,最終 head 仍雙平台驗證;S6 記帳 commit **必須與末次代碼修復同一次 push**(禁單獨 push 觸發整套 suite)。
- 合入:exact-head PR → CI 綠 → `gh pr merge --merge --delete-branch`;merge 批次前 re-fetch(分支可能被並行 session 宣告 SUPERSEDED)。main 禁直推;禁 force-push 已審分支;禁改他人分支;worktree 用完即 `git worktree remove`。
- 一輪一 PR,小步可回滾;PR body 註明:切片、role chain 結論、測試計數、對應 W 行。

**S5 三端收斂**:merge 後 `ssh trade-core '… git pull --ff-only origin main'`;涉 Rust 的切片在 Linux 跑 `cargo test -p openclaw_types <filter>` / `-p openclaw_engine <filter>` 取 Linux 證據(E4 leg);失敗 = 本輪不閉,回 S2 修。**外層鏡像**:`IBKR_TODO.md` 有變更時同步 `~/Projects/TradeBot/IBKR_TODO.md`(cp+cmp 驗證)。Mac/origin/Linux 三 SHA 一致(或 Linux 落後待 pull 型)才算收斂。

**S6 記帳(v2 固定 checklist,全部進當輪代碼 PR 的一個 `docs(ibkr): R-N 記帳` commit,`git commit --only`,零額外 CI)**
①PROGRESS 追加 R-N 行(PR 欄先寫 branch 名);
②**回填 R-(N-1) 行的 PR#+merge SHA**(`gh pr view` 一查即得);
③TODO W 行狀態遷移;
④CHANGELOG 敘事——**僅 W 收口或治理事件時寫**(v812/v814/v815 先例:per-W-close 非 per-round);
⑤IBKR_TODO §5 本 W 節狀態行(含 SHA);
⑥IBKR_TODO §4.4 本 W 行 + 任何被本輪推翻的舊行;
⑦IBKR_TODO **§0 現況一句話**(僅 W 收口時);
⑧§4.2/§4.3 保持快照語義不回寫,被推翻處只加「(更新 YYYY-MM-DD:…)」注記。
另:殘項欄禁空泛(「無」或具體 ticket/包名);記「本輪淨增/淨減 blocking 移交數」。
**並行輪記帳細則**:兩切片並行時,**僅先合入的 PR 帶記帳 commit**(含兩輪的 R-N 行);後合入 PR 不碰 meta-doc(避免 PROGRESS/TODO 撞衝突),其行若有補充由 PM 在 merge 後搭下一輪 PR 便車(此為 §7 規則 1「漂移修復搭便車」的合法形態,same-push 規則對此豁免)。

**S7 排下輪**:只有 S0 已證明 exact Operator opt-in，且
`agent_governance.py continuation` 對 previous/current semantic progress snapshot 回傳
`CONTINUE_OPERATOR_LOOP + schedule_wakeup=true`，session 存活時才可
ScheduleWakeup(`/loop` 原 prompt 原樣;delay 按下輪型態:剛派 BG 波=長 fallback ≥1200s
駐留等收、純接續=120-600s)。相同 blocker/source/Context/external/work digest 回傳
`BLOCKED_NO_DELTA`，必須停、`next_action=null`，不得以新 timestamp/TODO pointer 重開。
撞 Operator 決策、WAITING 或 terminal status 都停；session 將盡時確認 S6 已落 repo 即可
安全死亡，接棒見 §6。

## 4. 三端同步鐵律

Mac(worktree 寫碼)→ origin(PR merge 唯一入口)→ Linux(`pull --ff-only` 唯一動作)。Linux 永不本地改碼、永不 rebase;Mac 禁 merge/rebase/reset(ff-only pull 允許)。每輪 S0b + S5 兩次核對;引擎 binary 與 main 的差距是**觀測值不是缺陷**,只在 W10 inactive deploy 窗收斂(operator-gated)。任何非 ff 可收斂的分歧 → 停輪報 operator,不擅自 merge。

## 5. 質量與申報紀律

- 申報一律用 IBKR_TODO §3 狀態梯度詞彙;source-landed ≠ GUI-wired ≠ runtime-verified,混稱=申報缺陷,E2/QA 應退回。
- 每包 DoD 以 IBKR_TODO §5 為準;W5/W8 的負測試矩陣(未知前綴按 live 拒、seal≠活化、envelope×port/verb 交叉拒)不可省。
- Operator 決策點(IBKR_TODO §9 D1-D7、OPEN-GOV-1/2)撞到即:記帳 + 該支線標
  WAITING(named operator action)。WAITING 不可由 selector 自動取回；只有已驗證的新 delta
  經 PM 重新 admission 才能回 ACTIVE。若沒有其他 ACTIVE 支線立即停 loop，停前
  PushNotification 一句話。
- 成本:hosted CI 遵 2000min/月政策(macOS 最小化,draft 閘見 S4);agent 波規模與包規模對齊,不為快而省 reviewer。新守衛/script 接入 CI 必附**執行計數證明**(R1 教訓:字面 cargo filter 空轉)。

## 6. 接棒協議(session 死亡安全)

loop 狀態 100% 落 repo:TODO W 行(狀態)+ PROGRESS(履歷)+ 本檔(協議)+ IBKR_TODO(設計)。新 session 接棒(**ScheduleWakeup 喚醒也算新 session**)= §0 Load 四件套 → 從 S0 起跑;禁依賴前 session 記憶。in-flight 遠端分支以 remote 為準:可收割(續審合入)或棄置(關 PR 留言原因),不得放置不管。

**sub-agent 死亡三分類與對策(v2,R2/R3 實證固化)**:
- **transport 中斷**(連線錯誤/socket 斷):SendMessage resume 原 transcript 收 verdict,**禁重派**(R3 實證:E2 斷線後 resume 成功收 verdict)。
- **配額觸頂**(月度用量/api limit):接棒**先實證驗屍**(cargo test/pytest 實跑半成品)再裁續作 vs 重寫,**禁信半成品自報**(R2 實證:三紅全 fixture 非邏輯 bug,續作正確)。
- **idle-kill**(desktop 900s 暫停殺 BG):按既有駐留等收 SOP;復活不可能,按驗屍流程處置遺留分支。
配合 S2 的 WIP 早推,輪中死亡的半成品必在 remote 分支可見;接棒者 S0a 的 `git branch -r | grep agent/ibkr` 即發現,先驗屍後裁決,裁決寫入該輪帳本行。

## 7. 停機與反空轉

- **正常終態**:W11 收口、TODO banner 宣告 `IBKR_FULL_LIVE_CAPABILITY_COMPLETE_EXTERNAL_ACTIVATION_PENDING` → loop 停,EA 跑道文件化移交 operator(PushNotification)。
- **反空轉硬規則(v2)**:
  1. 每輪 S6 必須能指出本輪落地了 {W-DoD 代碼切片 merge | 具名 blocking 移交項代碼閉合 | EA-enabling 工件(W8a/W9a 切片)} 之一;docs-only 輪僅限 bootstrap(R0 型)、**operator 顯式指令的校準/審計輪(R8 型,記帳需引用指令)**、停機報告、或漂移修復搭代碼輪便車;此類白名單輪**不計入規則 2 的零代碼連續計數**。
  2. **連續兩輪零代碼 merge → halt** + PushNotification 一句話 + 帳本寫原因(對稱於「同包兩輪 REJECT 停包」)。
  3. LOW/NOTE 清掃只准搭車且 ≤ 當輪 diff 的次要部分,禁獨立成輪。
  4. findings 一次性定性(S3)入帳後不得二次立案。
  5. blocking 移交債連續兩輪淨增 → 下一輪強制先償還最老 blocking 項再開新面。
  6. 可推進面只剩不合格切片(湊不出規則 1 的三選一)→ halt 上報,不硬湊維生切片。
- **異常停**:三端非 ff 分歧無法收斂/同包兩輪 REJECT 無解/全支線撞 operator 決策點/§2 邊界被觸碰/S0f billing 事故。停前必寫帳本(原因+現場+建議)。
- loop 重啟只能由 operator 以 `/loop` + 本檔路徑建立新的 explicit
  `operator_loop` admission；舊 next_action、wakeup 或 WAITING row 不可自行復活。
