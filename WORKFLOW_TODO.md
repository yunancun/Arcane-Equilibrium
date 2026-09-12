# 開發代理工作流交付總帳

本總帳沿用 W0–W11、WF6 與 WF-RC／WF-PR 的既有成果。目標是：使用者提出開發需求後，Codex／Claude Code 能完成實作、互補審查、行為驗證及交付，減少重工與人工糾偏。對象是 PM／PA／E1–E5／CC 等開發代理。

根 `TODO.md` 是唯一 physical dispatch authority；本檔保存採用決策、交付規格與證據。歷史完整總帳見 Git `d5d4ef145:WORKFLOW_TODO.md`；歷史 checkpoint 不提供當前執行權。

## 當前決策（2026-09-13 整體完成度校準）

核對基準：clean canonical main `1a91eca6032c49bdb349d5c7f2a3cb31278b22a3`，fresh GitHub main 相同；PR191
已按受審 head41ed05fb9 合併。本節取代下方 2026-09-09 的「W3 未採用／待複核」
與舊執行提示；原驗收、候選 SHA、修補與審查歷史保留。這是狀態校準，不啟動其他工程。

**整體判定：尚未全部完成。** 已有 WF-RC-01、WF-PR-01 與選定 W3 交付三項
完成結果；它們有不同範圍，不能以三項除以全部別名計算完成率。W0–W11 與 WF6
彼此重疊；候選存在、source 已整合、Mac 日常採用、host enforcement、效率成效分層判定。

**上一單元判定**：W3 為 DAILY_SOURCE_ADOPTED，Linux 三端同步仍 INDETERMINATE。
**關鍵證據**：[PR191](https://github.com/yunancun/Arcane-Equilibrium/pull/191) merged；
[CI34707782190](https://github.com/yunancun/Arcane-Equilibrium/actions/runs/34707782190)
attempt1 的八分片與 aggregate PASS。治理摘要4618 passed／0 failed／95 skipped，
aggregate 獨立驗證4649個唯一nodeid；另362 migration contracts passed。
Mac main-sync／ff-only／post-sync PASS；五個公開 Context case 符合預期。
**偏移**：舊 TODO 把已完成 W3 留在 WAITING，舊第81行提示會重派同一實作。
**功能性可用度**：有人統籌的有限交付有成功案例；通用 native 自動派工及效率改善尚未驗收。
**下一 prompt 決策**：停止 W3 實作重派；先使兩份狀態文件反映已發生的採用，接著
以一項使用者指定的小型需求驗收交付體驗。未有瓶頸證據前不自動選 W9／W2／模型比較。

| 原 ID | 校準後完成度 | 剩餘驗收／安排 |
|---|---|---|
| W0 | evaluator 已有；新 economics 候選與成效未完成 | 真實可比 runs、failed/reopened cohort、attested usage／price；不可把 planned tokens 當節省 |
| W1 | collector／inventory 候選；未全部採用 | canonical 缺候選 collector；僅在真實試點缺具名欄位時承接，缺 provider 為 EXTERNAL_LIMIT |
| W2 | local 修補可用；daily host enforcement 未證 | native pre-action／cancel／depth／wait 實際入口證據；不得用 wrapper 或設定文字代替 |
| W3 | 選定 current-state integration 已 DAILY_SOURCE_ADOPTED | PR191、Mac 五項公開 Context 驗收完成；Linux source sync 仍 WAITING，無新 runtime 證據 |
| W4 | narrow editorial assurance 候選未採用 | 另有審查政策決策與驗收才承接；不放寬既有互補 review |
| W5 | source subject-binding 候選未採用；完整 reuse 未證 | exact source／command／toolchain／environment／TTL 與可信 verifier 仍必須 |
| W6 | snapshot 平行化未完成 | W5 reuse／原 HITL 前置保留；不先為平行化新增工程 |
| W7 | W3 需要的現行 generator parity 已驗證；完整 W7 未完成 | 只在生成漂移有具名缺口時承接其他候選 |
| W8 | locality／lazy-loading 未驗收 | 先有 profile 瓶頸與 retain／isolate／delete 正確性證據 |
| W9 | 啟動精簡候選未 daily-adopted | 試點若證明載入瓶頸才整合；保留現行 containment／peer-review／delivery 規則 |
| W10 | 現行 KnowledgePilot 流程有執行證據；舊政策改革未採用 | delta-gated、single Vault writer 保留；最近同步兩頁，負面檢索 canary 尚未驗證 |
| W11 | 有 W3 單一交付成功案例；全量 qualified adoption／效率未證 | 下一階段是一項使用者指定小需求的有限交付試點；一個成功案例不構成比較成效 |
| WF6-01 | 本次 W3 selector 範圍已採用 | 沿用，不重做 |
| WF6-02 | 真實成本／重開 cohort 未完成 | 缺值寫 unavailable；不填零成本或推估節省 |
| WF6-03 | inventory／collector 候選可重用，selected-host evidence 不足 | 只補具名缺漏，不再做整體 survey |
| WF6-04 | 部分完成：W3-owned 選段已採用 | W9 等其他 section-loading／啟動項未採用，不能整項標 DONE |
| WF6-05 | model candidate／compatibility／rollback 未驗收 | 不改 default；另有具體需求才承接 |
| WF6-06 | 固定 DAG／corpus 的模型比較未執行 | 需 WF6-02／03／05、可比 baseline 與明確付費範圍 |
| WF6-07 | 可選 routing A/B 未執行 | 先有固定模型與資料；不是必做前置 |
| WF-RC-01 | LOCAL_CLI_VERIFIED，保留已完成 | 原 scope／paired IDs／review history 保留，不提升為 host enforcement |
| WF-RC-02 | NATIVE_AUTO_DELEGATION_DISABLED；WAITING_ENTRY_PROOF | 停用措施生效不等於完整入口控制完成 |
| WF-PR-01 | LOCAL_SOURCE_REPAIR_CLOSED，保留已完成 | finding 去重、分歧拒絕及互補審查已在使用 |
| W3-CURRENT-STATE-INTEGRATION | DAILY_SOURCE_ADOPTED；Mac 交付收口 | 不重派實作／review；三端同步仍未關閉，等待 fresh Linux source 證據 |
| PR190 | OPEN／unmerged，五個 unresolved threads，CI failure | 獨立 WAITING；不整包採用、不作已完成 W3 的前置 |


Linux／engine 最近一次觀察是上一單元的 SSH timeout 與 four-head INDETERMINATE；
此輪未重試 SSH，不宣稱主機 down、Linux 已採用或 runtime 健康。Mac 與 GitHub
source 相同已驗證。相同外部條件下不重複 retry，也不把 Linux 等待變成 Mac 文件／開發前置。

## 下一步任務安排（有限，非自動派發）

1. **狀態回寫採用**：只修改 TODO.md 的 workflow／local-workflow 段與本總帳。
   保留全部原 ID、W3 六項驗收、原證據及 S2E／交易 queue；將 W3 實作標為已採用，
   把 Linux source gate 分開保留待驗，替換會重派 W3 的舊入口提示。驗證公開 Context
   讀到精確新段落；完成需要實際採用文件的 source，不能只把修正稿當 canonical。
2. **小型真實需求交付試點**：由使用者指定需求，PM 凍結單一 outcome／少量路徑／驗收，
   使用已採用 W3 與有限互補 review。只記錄實際 elapsed、重開、重工、人工糾偏；
   缺 token／cache／價格的 platform 證據就記 unavailable。沒有 baseline 時不報節省率。
3. **按試點證據分流**：載入瓶頸才選 W9；入口控制瓶頸才選 W2；量測缺欄位才選
   W1／W0；reuse 缺口才選 W5。W4／W6／W7／W8／W10 改革及 WF6-05–07 保留原啟動條件。

第一步不需要重做 W3 source／CI／review；文件變更只做自身必要檢查，發布仍按
當前 exact-head gates 與相應授權。第二步沒有使用者具體需求前不造 task、不轉 ACTIVE。
本安排沒有 scheduler、wakeup、generic delegation、runtime／PG／broker／order／funds authority。

### 下一次執行提示（取代舊 W3 提示）

> 先按 WORKFLOW_TODO 的 2026-09-13 校準核對 current head、PR191 及原始採用證據。
> 若兩份文件已符合本校準，狀態回寫即已關閉，不再修改／重驗相同內容；轉為等待使用者
> 指定一項小型實際需求。尚未回寫時，本次只完成兩份 TODO 狀態回寫與採用：保留全部 ID、原驗收、歷史 review 與 S2E 段，
> 關閉已採用 W3 的實作待辦，Linux source sync 另列待驗，移除重派 W3 的有效入口。
> 使用 linked worktree、fresh task contract／Context／exclusive lease，按真實文件變更
> facts 路由必要檢查；不重跑無關治理全套，不重做已完成 E2／E4，不整包合併 PR190。
> 驗證新 workflow section 被公開 context CLI 精確選中、stable 不載入 TODO、S2E 投影
> bytes 不變、git diff --check 及兩檔 scope。按既有相應授權走發布／採用 gate；缺授權
> 或證據時留下精確可 review 結果，不宣稱 canonical 已更新。完成後回報上一單元判定／
> 關鍵證據／偏移／功能性可用度／下一 prompt 決策。後續小型實際需求待使用者指定，
> 不自動開始 W9、W2-host、模型 A/B、主機修復或交易任務。

## 原候選核對與採用決策（2026-09-09 歷史）

以下是整合前的 dated observation；W3 的當前狀態以上方 2026-09-13 驗收為準。

以下 SHA 均已由本地 Git 核實存在。各候選 checkpoint 不是目前 main 的 ancestor；這項檢查本身不排除 cherry-pick，所以另核對改動與現行功能。W3 的行為差異已用公開 compiler 重新觀察，其他歷史測試數不當作本輪實跑。

| 既有成果 | 已核對的來源 | 本次採用決策與限制 |
|---|---|---|
| W3 Context | 實作 `4b31399dfbd739a60b93dc29d8a8fbd9dfb195de`；修正後受測 `1f87d68f9a0b8535e8fb46cba52858fa57fbb3d9`；候選 worktree `workflow-w3-context-20260906` 的 head `aee17bc01cfdf2331e6c0949d616c1a9903eaec2` | **承接既有兩個 code/test delta**，重用 micro-pack 測試。實作／測試 bytes 未被其後 docs commits 改動。現行 main 拒絕 typed surface；候選可選出正確 workflow section。新工作只做相容整合，不能重寫相同功能或 merge 整條祖先鏈。 |
| W9 啟動精簡 | `bf6839c505d0083f9e1e5717b770347c597e69cf`；現存 candidate head `a5db6c0454f4177e6eec38a9b1078b9b7981106e` | 採用「熱路徑＋條件指針」方法作後續參考；不整檔覆蓋目前 AGENTS／context router，以免丟失後來的 containment、交付與審查修補。不是 W3 前置。 |
| W7 generated drift | `e134c772e48aef74de2f585239e16a89b9816681` | 沿用 generator／parity 驗證方法；依當前 Registry 重新生成必要區塊，不搬舊 digest 或另造 generator。 |
| W1 collector | `b92417b7afed1de6a1913279af6e5743fb085b34` | 保留現成 collector 作日後需要的候選；不以新 telemetry 工程阻塞 W3。 |
| W2 local／host | local `1de695218e8fbf11a317a40396ad1713e940b930`；host worktree head `3a0e0debfd6088d199dff1e193f6bb5e6cf603d3` | 重用既有 control／隔離 App Server probe 結論，不重跑相同調查；daily desktop enforcement 仍缺證據，不以 wrapper、配置文字或孤立 primitive 宣稱完成。 |
| W0 economics | `c90408613d6ce436abae619437a0bdc4acf4787f` | 採用 elapsed／重工／重開／人工糾偏的交付評估方向；actual usage／金額成本仍需真實資料。本輪不修改 evaluator。 |
| W4／W5 | `4818a65d0052020b74eb3c7edfba12b5331deb7f`／`60bc55673f170a06ee4b93a2080c060160707566` | 保存已有成果，不重做。W4 涉及審查政策；W5 涉及捕獲／replay 路徑；都不是 W3 typed state 功能的自動前置。 |

W3 精確重用方式：從 `git show 4b31399df` 與 `git show 1f87d68f9` 取該次 delta；不要用 `main..candidate` 整包搬入，因其祖先還帶有 W0／W1／W5／舊總帳。保持目前 main 的 WF-RC／WF-PR 行為，以當前 Registry 合併欄位並重新生成衍生區塊。本輪 `git apply --check` 證第一個 delta 只有三份 generated workflow（agent-wave、openclaw-full-audit、profit-diagnosis）不能直接套用，第二個 test delta 可套用；三份衝突應透過當前 generator 解決，不覆蓋舊 Registry 區塊。這是靜態套用檢查，非已完成整合／測試。

## 已驗收交付：W3 current-state integration

**交付結果**：日常 canonical source 的 Context compiler 接受 `current_workflow_state`，正確讀取根 TODO 的開發工作狀態；穩定查詢保留最小 Context，AIML／runtime 狀態按各自真實觸發條件載入。這是可執行功能修補，不是再交一份 survey、packet 或更新完成標籤。

沿用 W3；本次整合的固定 `work_item_id=W3-CURRENT-STATE-INTEGRATION`、`lane_id=workflow-w3-delivery` 在該交付內不更換。候選核對已完成；開始時只驗 current source／candidate fingerprint 與乾淨工作區，然後建立該交付的 fresh task contract、Context 和 exclusive writer lease。若身份未變，不再重新審計 W0–W11。

### 固定範圍與執行

一位 implementation owner；PM 整合，E2 查正確性與範圍，E4 執行行為驗證，直接文件由 R4 審查。使用已授權、可用的有限 peer-review 入口。不能為找 reviewer 啟動另一個 CLI／帳戶／host 修復；若入口缺失，保留可 review 的實作與本地驗證，明確記錄缺少的獨立 verdict，不能冒充 PASS 或繼續派替代者。

沿用 W3 既有 16 個 code/test 路徑，以及六份直接文件，共 22 個候選路徑；准入時以此清單凍結，再只縮小：
- `.codex/agent_registry_v1.json`
- `.claude/workflows/agent-wave.js`、`.claude/workflows/context-admission-v1.fragment.js`、`.claude/workflows/openclaw-full-audit.js`、`.claude/workflows/profit-diagnosis.js`（僅 generator 管理的對應區塊）
- `helper_scripts/maintenance_scripts/agent_governance_context.py`、`agent_governance_context_refs.py`、`agent_governance_context_specs.py`、`agent_governance_context_validation.py`、`agent_governance_execution.py`、`agent_governance_routing.py`、`agent_governance_vocabulary.py`、`agent_governance_workflow_codegen.py`（後七項沿用同一目錄）
- `tests/structure/test_agent_governance_context_micro_pack.py`、`test_agent_governance_context_adversarial.py`、`test_agent_governance_workflow_codegen.py`（後兩項沿用同一目錄）
- `TODO.md`、`WORKFLOW_TODO.md`、`docs/agents/context-loading.md`、`docs/agents/development-agent-governance.md`、`docs/adr/0050-development-agent-governance.md`、`docs/CLAUDE_CHANGELOG.md`

這是 task 總範圍，checkpoint 仍遵守既有 file／line cap；如需分批，只在同一 task／pair／lease 的範圍內分本地 checkpoint，中間 checkpoint 不叫完成，也不補充 review／repair 預算。新 subsystem、額外 adapter 或名單外路徑不能自動加入。

Bootstrapping：main 尚未支援新 surface 前，實作任務使用現有 `agent_workflow`／`python` 等真實 facts，先人工讀取本檔與根 TODO 的有界 workflow section；不要把未知 surface 填入 pre-change admission 再為此造新准入框架。新 surface 是修補後的 acceptance input。

### 完成條件

1. 在整合後的實際 source 執行公開 `agent_governance.py context`／compiler，low／medium uncertainty 的 workflow-only task 可選出 exact `TODO.md#Workflow optimization physical queue（source-only）`，內容與根 TODO 當前 section 一致。失效／缺漏／重複 heading 應明確拒絕；穩定查詢不額外載入 current state。
2. 沒有 AIML／runtime 觸發的 workflow-only task，不誤帶 S2E 狀態；有真實相關 facts 時保留原觸發。原 S2E EMPTY／WAITING 及其他 TODO 內容不改變。
3. 重用 W3 的 section／required-source／tamper 測試；未選段的改動不改 selected content／content digest。完整來源 provenance 仍如實反映來源變化，不要求偽造不變的 artifact digest。
4. Python 與 saved-workflow 的 Context inventory／identity／generator parity 同步；沿用當前生成器。WF-PR 的最短路由與 finding 去重、WF-RC 的既有交付控制保持有效。
5. E2 與 E4 問題互補。E4 只跑 W3 直接測試、受影響的 context／codegen 檢查與必要的既有 peer-review routing 回歸；沿用無關、未變的證據，不跑全框架／全 repo 大審计。先收一批 findings，再一次集中修復，原 blocker 最多一次 exact recheck。
6. 最終交付包含可 review 的 source diff、上述公開行為的真實 command result、驗證結果與使用入口。只有整合到日常使用的 source 並重跑相應公開命令，才可標 `DAILY_SOURCE_ADOPTED`；僅 feature checkpoint 則標 `SOURCE_READY_NOT_ADOPTED`，並具名剩餘採用步驟。remote publication 依既有授權與發布 gate，不把本地檔案等同遠端已落地。

上述六份文件覆蓋 W3 原有直接文件與現行 Interface 維護要求；不新增文件／索引頁。若確認 22 個候選路徑不足以合法整合，停止在精確路徑／規則差異，保留已完成 patch，不能改做另一個大單元。

### 收斂與後續

每一步都應改變當前可驗收行為或解決原 blocker。相同 source／failure／外部條件下重複調查、重印 receipt、換 task ID、重述相同結論，都不算進展。相同 blocker 且沒有語義 delta，或一次修復／複核後仍未解決，就返回精確 owner／unblock condition 並停止；不自動 wakeup、重開、建立 successor。

W3 驗收不等待 W2-host、PR190、W4、完整 W5、W6、W8、W10、W11 或 GPT‑6／成本 A/B。這是本次 W3 邊界的明確採用決策，不宣稱這些工作整體被取消或其獨立政策已修改。

W3 完成後先用一項獨立的小型開發需求檢查完整交付體驗；由使用者指定需求，PM 凍結驗收。只量記已發生的完成時間、重開、重工及人工糾偏。只有實際瓶頸指向啟動載入或 native 入口時，才分別承接 W9／W2；GPT‑6 模型比較保留在功能可用之後。這些均不自動啟動。

### 原 W3 執行提示（歷史，禁止重派）

> 執行既有 Workflow TODO 的 W3-CURRENT-STATE-INTEGRATION。先讀 canonical AGENTS、PM、context router，再讀本檔「下一個真實開發交付」與根 TODO workflow section。核對當前 main／候選 fingerprints，承接 4b31399df＋1f87d68f9 的既有 delta，不重寫、不 merge 整條候選祖先鏈。依本節固定範圍 fresh-admit，交付 current_workflow_state 的實際功能與驗證；保留 WF-RC／WF-PR 和 native containment。既定範圍內自主完成，一批審查、一次集中修復、一次原 blocker 複核；缺 peer-review 入口時保留實作並如實報未驗，不另修帳戶／host。完成、無 delta 或限額耗盡即停止，無自動 successor。收尾回報上一單元判定、關鍵證據、偏移、功能性可用度、下一 prompt 決策。

## W3 有限審查修補 checkpoint（2026-09-09）

本節記錄提交時的證據，覆蓋下節「獨立入口 unavailable」的舊狀態。Operator 先選 A
授權既有本地 CLI 的一批 E2／E4／R4 審查、一次集中修復及一次原問題複核，再選 1
授權 repository 唯讀、指定隔離暫存可寫的本次 sandbox 修正。設定只經呼叫參數傳入，
沒有永久修改 containment、Registry budget、role adapter 或 capture policy。

- 初審固定 `a657ea1ab39246584f112d8ce7b3382243666b56`：R4 PASS；E2 完成來源檢查並
  指出選段反例，但期限到期，唯一結果恢復仍為 UNVERIFIED；E4 因 supplied pytest
  launcher 不符既有 bootstrap 而 FAIL，亦記錄同一選段隔離缺口。原始 packets 全保留。
- PM 將 E2 原事件觀察與實際反例歸為原 blocker，沒有把恢復結果改寫成 PASS。修補只
  令已由 peer／higher heading 結束的選段不再受後方未閉合 fence 影響；選段內／前方
  遮蔽 heading 的未閉合 fence 仍拒絕。新增 public compiler/materializer 回歸先得
  2 FAIL／1 PASS，修後整份 micro-pack 17 PASS；這是 implementation owner 的定點證據。
- E4 改用既有 `GOVERNED_PYTEST_PREFIX`／required args；受控 collection preflight PASS。
  獨立八份 suite、五種公開 Context case 及原 blocker exact recheck 留給原角色，
  不能把 preflight 或先前 207 PASS／1 skip 冒充本批獨立執行。
- 本 checkpoint 為 `SOURCE_READY_NOT_ADOPTED`；後續只有本批原問題一次複核及既有
  publication／canonical adoption gate。原始證據與判定存於
  `/private/tmp/w3-review-resume-20260909/`；未收到 final exact-head verdict 與日常 source
  公開命令結果前，不宣稱 DAILY_SOURCE_ADOPTED。沒有 native host attestation 或 runtime 效果。

## W3 單次授權修復結果（2026-09-09，source-only）

**本地交付**：`DONE_WITH_CONCERNS`，`SOURCE_READY_NOT_ADOPTED`。兩個已知 fixture
blocker 已解除；獨立 E2／E4／R4 verdict 仍 unavailable，整體 gate 為 `UNVERIFIED`。
下節保存前輪失敗與停止記錄；本節 supersedes 其「尚待修復兩個 blocker」的狀態。

- **本次授權**：Operator 原文「謹本次授權繞過限額，把已發現的問題修復掉」。只用於
  同一 `W3-CURRENT-STATE-INTEGRATION`／`workflow-w3-delivery` 已知問題的續作。
  原 frozen envelope／release history 保留；在既有 store lock 下為該 pair 記錄一次性
  repair allowance，並由 fresh admission 消耗。這是人類授權的本次例外，並非 compiler
  能自行推導的授權，也沒有永久修改 Registry 預算、治理程式或 native containment。
- **修補內容**：`materializer_repo` 使用真實臨時 Git repo、一份固定 source 與測試專用
  Context pack，避免真 repo 文件／索引成長在 DAG 篡改檢查前耗盡 Context。兩個測試
  先驗正常 artifact 可 compile／materialize／validate，再分別驗重簽後空 DAG 與
  reviewer substitution 被原有拒絕條件攔下；`narrow` envelope 及 12,000 上限保留。
- **驗證**：修前原命令 `2 failed in 0.82s`；修後定點 `2 passed in 0.30s`。原有八份
  聚焦 suite 完整實跑 `207 passed, 1 skipped in 104.96s`，exit 0。唯一 skip 是 macOS
  不執行 Linux kernel argv-cap 檢查；沒有測試 failure。Registry／generator parity
  通過；W3 low／medium workflow 選段、stable omission 與 S2E trigger 保留。
- **範圍／來源**：承接前輪保留 patch，全部仍在原 22 路徑內；本次額外語義變更只有
  adversarial fixture 與 TODO／總帳／changelog。原 worktree 保留；續作 worktree 為
  `/Users/ncyu/Projects/TradeBot/.codex-worktrees/workflow-w3-fixture-repair-20260909`。
  証據命令／原始 log 與單次授權記錄保存在 `/private/tmp/w3-fixture-repair-20260909/`；
  這些是 conductor 本地證據，不是獨立 role 或 platform attestation。
- **採用剩餘步驟**：PM 在既有可用入口取得 E2／E4／R4 的有限獨立 review，依既有
  publication／adoption gate 採用到 canonical source，再於該 source 重跑公開 Context
  命令。未做到之前不能標 `DAILY_SOURCE_ADOPTED`。不另修 reviewer transport，沒有
  自動 successor；通用修復限額不因本次例外永久失效。

使用入口與固定 acceptance 沿用上節規格及下節例子；兩個原 fixture 問題已修，不需
再次為同一 failure 啟動新調查。日常 canonical main 尚未收到本次 feature source。

## 前輪 W3 執行結果（2026-09-09，source-only）

**判定**：`BLOCKED`／`gate_verdict=FAIL`，`SOURCE_PATCH_PRESERVED_NOT_ADOPTED`。
第一個本地 checkpoint `624f21cb9` 與同一 worktree 的剩餘 diff 保留；canonical
main 仍為 `bf574e2102fef29e4a865c3e4678025964c7473a`。沒有 daily adoption、push
或 main sync。上方是本輪已使用的固定規格，不構成自動重開或補充修補預算。

- **准入／範圍**：以 clean main fresh-admit 固定 pair 與 22 個路徑；Context 已
  materialize、exclusive writer lease 已取得。精確重用兩個候選 delta，三份 workflow
  由目前 generator 重建；其 generated 區塊外 bytes 與 base 相同。native containment、
  WF-RC／WF-PR source 邊界保留。
- **功能證據**：公開 `agent_governance.py context --role PM @task-facts.json`
  已驗 low／medium workflow 任務選 exact workflow section、內容與當前 TODO 一致；
  stable query 不選 current state，`current_s2e_state`／runtime facts 保留 S2E trigger。
  四個非 runtime artifact 的 materialize／validate 均無 error；runtime observation
  仍是 evidence debt，不作 runtime 效果主張。Registry 與 generator parity PASS。
- **測試**：直接 micro-pack 首跑 14 PASS。完整聚焦 batch 實跑 `202 passed / 5 failed /
  1 skipped`（45.33s）；skip 為本機 macOS 不測 Linux kernel argv cap。5 個 failure
  在 clean main 同樣重現：過時的 economics 路由前提／empty-DAG error expectation。
  於既定 adversarial 檔一次修補，保留具名 `consumption` 才觸發 AI-E；唯一原 blocker
  recheck 為 `3 passed / 2 failed`（1.58s）。不得把兩批相加稱為全綠。
- **停止原因**：`test_materializer_rejects_rehashed_empty_binding_for_routed_call` 與
  `test_materializer_rejects_rehashed_routed_node_substitution` 的真實 fixture Context
  planned estimate 分別約 12,594／12,592，超過 narrow 上限 12,000，先以
  `context plan is not call_allowed and cannot be materialized` 拒絕，未到預期 tamper
  boundary。這是 planned accounting，不是真實 provider usage。未調高上限、未改
  AGENTS 或啟動 W9；本輪 repair／recheck 預算已用完，不再修補或重跑。
- **獨立性**：本平台無可用原生 reviewer 工具，E2／E4／R4 verdict 均
  `UNAVAILABLE`；上述為 conductor 本地驗證。未啟動替代 CLI／帳戶／host。
- **owner／unblock**：PM 等待 Operator 明確 reopen 同一 W3 pair，僅處理上述兩個
  測試 fixture 的可准入 Context，保留 tamper 的負向目的與現行預算邊界；仍須取得
  可用的獨立 review verdict，才能另行判定 source ready／採用。沒有自動 successor。

本地 review 根目錄：`../.codex-worktrees/workflow-w3-integration-20260909`（相對 workspace
父層定位；實際絕對路徑 `/Users/ncyu/Projects/TradeBot/.codex-worktrees/workflow-w3-integration-20260909`）。
驗證命令／原始輸出保存在本機 `/private/tmp/w3-integration-20260909/`；它們是本輪
local evidence，不是可跨機重用的 trusted captures。完整 patch 可在該 worktree 用
`git diff bf574e2102fef29e4a865c3e4678025964c7473a --` 審查。

**使用入口**：low uncertainty 的狀態查詢用 `task_shape=query`、
`surfaces=["current_workflow_state"]`、low risk、無 direct interfaces；medium uncertainty
用 `task_shape=review` 並綁實際 compiler interface，其他 mandatory task fields 照現行
Context 契約填入。執行 `python3 helper_scripts/maintenance_scripts/agent_governance.py
context --role PM @task-facts.json`。日常 canonical source 尚未採用此 surface。

## 保留的本地修補與原始驗證

WF-PR-01 source `bf72d7095b2c2ac31782693ce31da22eb89b60c8`；E4 受測 `5fe62aa9cccabf91ec269549974062e7e3486a10`，原始 `27 passed in 0.45s`、exit 0。E2 capture `sha256:a619dbae39167d346090fb2b06c2ac30741c2fa1f2c4cd0c7c6d6b0c6a645187`；E4 capture `sha256:2f52457085bd99e49e672e66d766d61e773014c355f88b04811d309e88fb6526`；R4 capture `sha256:721f1e5b2d86263a37a2f8dcd652b36edf3342f1e53207b6dcecfbbffe921a5f`。本輪四個受測程式／測試檔與原 E4 版本相同；沒有重跑這 27 項，也不把 PM 較早 77 項重疊回歸相加。

WF-RC-01 source `217efeba0c8c73b3cb7e7937440236aaad925131`；原 E4 `61 passed / 0 failed`、45.81s、exit 0，capture `sha256:ab66390f32fdd89c790f762bb6542b6a3906e74ed2bf1bb48a2889f9dc41219a`。E2 exact recheck `sha256:60ca2652ec9ea061d7ee8224019255d3b494a6b62df8867c6c3b979e16ab1fa7`。僅固定 paired IDs 的本地 source／CLI 保證；省略／換 pair／移除 surface 與 native enforcement 限制保留。

完整原始 review、preflight denial、PR190 偏移及其撤回記錄保留在 Git `aa0a90cda:WORKFLOW_TODO.md`。本次不重設其 repair budget。歷史驗證是歷史驗證，不構成本輪獨立審查或實際效率改善。

## 其餘既有工作：保持原 ID，按需要承接

| 原項目 | 殘餘／啟動條件 |
|---|---|
| W0／WF6-02 | 真實可比 runs、usage／price 與 failed／reopened cohort；資料不足即 unavailable，非零成本 |
| W1／WF6-03 | 已有 collector／surface inventory；只補具名缺失的 selected-host evidence，不重做 survey |
| W2 | local control 可重用；daily host integration 需明確對應入口與可信 pre-action／cancel／depth／wait 證據 |
| W3／WF6-01／04 | W3 integration／WF6-01／W3-owned WF6-04 已採用；WF6-04 其他部分仍未完成，見當前矩陣 |
| W4 | narrow editorial assurance 的條件式候選；政策採用與獨立 review 要求另行判定 |
| W5 | source subject binding 已有候選；完整 reuse 仍需 exact source／command／toolchain／environment／TTL 與可信 verifier |
| W6 | snapshot 平行化需 W5 reuse 與原有 HITL，不影響 W3 |
| W7 | narrow generated drift 有候選；只在有真實缺口時評估 broad generator，W3 沿用既有 generator |
| W8 | locality／lazy loading 須先證實瓶頸及 retain／isolate／delete 的正確性 |
| W9 | 啟動精簡候選保留；若採用，須保留目前 containment／peer-review 與 delivery 規則 |
| W10 | KnowledgePilot 更新政策不變；仍 delta-gated、single Vault writer |
| W11 | 完整 adoption／效能結論仍須可比證據及相應政策；不把其舊 all-W2…W10 依賴套到本次 W3 source 交付 |
| WF6-05 | GPT‑6 candidate 透過 Registry／generated parity、compatibility 與 rollback；不靜默改 default |
| WF6-06／07 | 固定 DAG 的模型比較／固定模型的可選 routing 比較；保留品質與費用邊界，缺資料不啟動空跑 |
| PR190 | 獨立 WAITING，不是 W3／WF-RC／WF-PR 的前置 |

## 2026-09-09 其餘 TODO freshness 複驗

本次僅維護總帳。上方 W3 已選定的交付方向、固定 pair／範圍／驗收保持有效，沒有在本次執行整合或啟動其他待辦。

對 W0–W11、WF6-01–07、WF-RC-01/02、WF-PR-01、W3 integration 與 PR190 逐項核對。W0/W1/W2/W3/W4/W5/W7/W9 的 10 個歷史 checkpoint 均可在 Git 解析、位於 PR190 head 的祖先鏈，均不是本次 canonical main 的 ancestor；精確 SHA 與逐項殘餘見 [freshness audit](docs/references/2026-09-09--todo-workflow-freshness-audit.md)。這是 ancestry 結論，不單憑它判斷是否已有等價 cherry-pick。W3/W9 等候選不得標為 daily-main adopted。

PR190 本次讀取為 OPEN／unmerged，head `3a0e0debfd6088d199dff1e193f6bb5e6cf603d3`；CI run `34054578577` failure、5 個 unresolved review threads。其他本地分支的修補不等於該 PR head 已修；保留獨立 WAITING，不阻塞 W3。W6 的 W4／W5 候選可重用性不等於 canonical 採用或 host proof；原 HITL／review 前置保留。WF6-06 仍需可比真實 baseline 與明確的付費 trial 範圍；WF6-07 可選，無資料不空跑。

主 TODO 已完成的 BLOCKED predecessor source 修補與 WF-RC-02 的 native 入口驗證是不同層級：前者本次本地回歸 PASS，後者維持 WAITING_ENTRY_PROOF。全量效率／成本／日常自動派工完成度仍未證。

## 先前文件交付的驗證界線（整合前）

本輪已做 Git／candidate bytes 核對、main 與 W3 公開 compiler 行為對照、patch 靜態套用檢查，以及本文件的 scope／links／queue／保存條件檢查。沒有執行候選程式整合、GPT‑6 A/B 或 host 派工。

目前 conductor 沒有可用的原生 subagent 工具；依 containment 不改用其他 CLI／task 建立 reviewer。本文件為 PM 完成的交付校準；獨立 R4 verdict `UNAVAILABLE`，不聲稱獨立審查 PASS，也不為取得該標籤擴出新工程。
