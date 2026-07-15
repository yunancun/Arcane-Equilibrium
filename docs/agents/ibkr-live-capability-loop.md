# IBKR Live-Capability Loop(W2→W11 自主推進協議)

版本 v1(2026-07-15)。本檔是**穩定協議正本**:當前任務狀態不寫進本檔(讀 `TODO.md` W 行);工程設計細節不寫進本檔(讀 repo 根 `IBKR_TODO.md`)。任何 session(現任或接棒)照本協議即可續跑。**本檔非授權文件**:授權鏈=AMD-2026-07-11-01(development-only)+ ADR-0048(amended);活化(EA1-EA8)全 Operator-gated,loop 永不執行。

## 0. Load(每輪必讀,順序固定)

1. 本檔 → `IBKR_TODO.md`(工程正本:§5 每包 DoD、§4.4 差距表、§2 邊界)→ `TODO.md` 的 `*-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-*` 行(dispatch 正本)→ 帳本 `docs/execution_plan/ibkr_live_capability/PROGRESS.md` 最後 3 行。
2. 職責分界:TODO.md 管「哪個包、什麼狀態」;IBKR_TODO.md 管「怎麼做、驗收什麼」;本檔管「每輪怎麼轉」;帳本管「轉過什麼」。四者衝突時按 todo-maintenance.md 的 class 規則裁,不得平均化。

## 1. 角色

主 session = PM+Conductor(不寫業務碼,只編排/裁決/記帳);實作與審查全派 sub-agent,role chain 按 TODO 行(PA/E1/E1a/E2/E3/E4/IB/OPS/QA/CC)。E1 一律 worktree 隔離;BG agent 按駐留等收 SOP 收割。

## 2. 硬邊界(每輪 S0 自查,任何一條被工作觸碰即停輪記帳)

- **零真實接觸**:不連任何 socket 到 IBKR/Gateway、不裝真憑證、不 production seal、不 enable Gateway systemd unit、不把 lane/connector/contact/order 任何旗標翻 true。fake-TWS 與本地 fixture 不算接觸(AMD-07-11 明文)。
- 不碰 Bybit `crypto_perp` 路徑(每包帶 bybit-live-unchanged 回歸);不降 global Cost Gate;不繞/不弱化 Guardian、Decision Lease、idempotency、audit、limits、kill switch。
- secret 永遠 stat-only;live slot 必須缺席(healthcheck 語義見 IBKR_TODO W9-5);env-var credential fallback 永禁。
- Python/FastAPI/GUI 不得獲得 order/risk/activation authority;非 GET route 只按 IBKR_TODO §5 W9-2 的單方法白名單流程開。
- 測試 fixture 禁硬編日期(相對/凍結時鐘);參數禁假功能;禁 `allow(dead_code)`/fixtures 藏 caller;注釋只寫中文。
- UNVERIFIED 外部事實(GFV 執行機制、paper 2FA 適用性等)未經 IB 帶來源現勘,不得寫成代碼常數或測試斷言。

## 3. Cycle(R-N,一輪 = 一個 coherent 切片 = 一個 PR)

**S0 同步門(不過不開工)**
a. `git fetch --prune origin`;讀 origin/main head;`gh pr list --repo yunancun/BybitOpenClaw --state open` + `git branch -r | grep agent/ibkr` 查在途工作——撞工(同包已有未合 PR/在途分支)即改選其他包或收割它。
b. `ssh trade-core 'cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && git rev-parse --short HEAD'`;記 Linux head。引擎 build_sha 與 main 差距**只觀測、只記帳**(binary 落後屬預期;部署窗只在 W10,operator-gated)。ff-only 失敗 = 三端異常 → 停輪報 operator。
c. re-read TODO W 行;行狀態與 repo 實況漂移時,本輪優先修對位(docs PR),再談派工。
d. §2 邊界自查 + runtime 側無 IBKR 異動(引擎 log 零 ibkr 蹤跡屬預期)。

**S1 選工**:按 IBKR_TODO §5 依賴圖 + TODO 行狀態,挑「最高優先、依賴齊、無撞工」的**單一 coherent 切片**;XL 包(W7/W9)必須先由 PA 出切片計劃再逐片跑。reviewer 帶寬空時最多兩切片並行,且不得同檔案面。

**S2 派工**:按該行 role chain 派 sub-agent 波;每個 prompt 給定:切片範圍 in/out、IBKR_TODO 對應節、DoD、§2 硬邊界摘要、輸出格式。dispatch 前置照 fetch-before-dispatch 紀律;prompt 留 NO-OP exit(發現已被做過就退出報告,不重做)。

**S3 質量門**:E1 自評不算數。E2 對抗審必過(pr-adversarial-review;發現退回 E1,不代寫);安全/authority 面 +E3(+CC 於硬邊界字段);IBKR 面 +IB(官方事實帶來源+日期);runtime/service 面 +OPS;e2e 宣稱 +QA。E4 計數紀律:新增/總量/PASS,Mac(aarch64)+ Linux 兩腿都要。**同一包連續兩輪被 REJECT → 停該包,PM 反省寫帳本,不硬闖。**

**S4 落地(git 紀律)**
- 分支:`agent/ibkr-w<N>-<slug>`(單輪單分支);commit 規範 `feat|fix|test|docs(ibkr…)`,docs-only 才 `[skip ci]`;meta-doc(TODO/IBKR_TODO/PROGRESS/CHANGELOG)用 `git commit --only`。
- 合入:exact-head PR → CI 綠 → `gh pr merge --merge --delete-branch`。main 禁直推(pre-push hook 已擋);禁 force-push 已審分支;禁改他人分支;worktree 用完即 `git worktree remove`。
- 一輪一 PR,小步可回滾;PR body 註明:切片、role chain 結論、測試計數、對應 W 行。

**S5 三端收斂**:merge 後 `ssh trade-core '… git pull --ff-only origin main'`;涉 Rust 的切片在 Linux 跑 `cargo test -p openclaw_types <filter>` / `-p openclaw_engine <filter>` 取 Linux 證據(E4 leg);失敗 = 本輪不閉,回 S2 修。Mac/origin/Linux 三 SHA 一致(或 Linux 落後待 pull 型)才算收斂。

**S6 記帳**:PROGRESS 追加一行(R-N|日期|切片|PR#+merge SHA|測試證據|verdict|殘項/教訓;殘項禁空泛);TODO 行狀態遷移(同輪或緊隨 docs PR;版本升級照 todo-maintenance.md,敘事進 `docs/CLAUDE_CHANGELOG.md`);IBKR_TODO §4.4/§5 僅設計變更才動。

**S7 排下輪**:session 存活 → ScheduleWakeup(`/loop` 原 prompt 原樣;delay 按下輪型態:剛派 BG 波=長 fallback ≥1200s 駐留等收、純接續=120-600s、撞 operator 決策全阻=停 loop);session 將盡 → 確認 S6 已落 repo 即可安全死亡,接棒見 §6。

## 4. 三端同步鐵律

Mac(worktree 寫碼)→ origin(PR merge 唯一入口)→ Linux(`pull --ff-only` 唯一動作)。Linux 永不本地改碼、永不 rebase;Mac 禁 merge/rebase/reset(ff-only pull 允許)。每輪 S0b + S5 兩次核對;引擎 binary 與 main 的差距是**觀測值不是缺陷**,只在 W10 inactive deploy 窗收斂(operator-gated)。任何非 ff 可收斂的分歧 → 停輪報 operator,不擅自 merge。

## 5. 質量與申報紀律

- 申報一律用 IBKR_TODO §3 狀態梯度詞彙;source-landed ≠ GUI-wired ≠ runtime-verified,混稱=申報缺陷,E2/QA 應退回。
- 每包 DoD 以 IBKR_TODO §5 為準;W5/W8 的負測試矩陣(未知前綴按 live 拒、seal≠活化、envelope×port/verb 交叉拒)不可省。
- Operator 決策點(IBKR_TODO §9 D1-D7、OPEN-GOV-1/2)撞到即:記帳 + 該支線標 WAITING(named operator action)+ 繞行其他可推進包;**全支線阻塞才停 loop**,停前 PushNotification 一句話。
- 成本:hosted CI 遵 2000min/月政策(macOS 最小化);agent 波規模與包規模對齊,不為快而省 reviewer。

## 6. 接棒協議(session 死亡安全)

loop 狀態 100% 落 repo:TODO W 行(狀態)+ PROGRESS(履歷)+ 本檔(協議)+ IBKR_TODO(設計)。新 session 接棒 = §0 Load 四件套 → 從 S0 起跑;禁依賴前 session 記憶。in-flight 遠端分支以 remote 為準:可收割(續審合入)或棄置(關 PR 留言原因),不得放置不管。

## 7. 停機條件

- **正常終態**:W11 收口、TODO banner 宣告 `IBKR_FULL_LIVE_CAPABILITY_COMPLETE_EXTERNAL_ACTIVATION_PENDING` → loop 停,EA 跑道文件化移交 operator(PushNotification)。
- **異常停**:三端非 ff 分歧無法收斂/同包兩輪 REJECT 無解/全支線撞 operator 決策點/§2 邊界被觸碰。停前必寫帳本(原因+現場+建議)。
- loop 重啟隨時可由 operator 以 `/loop` + 本檔路徑再拉起。
