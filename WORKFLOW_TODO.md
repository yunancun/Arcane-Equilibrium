# 開發代理工作流交付總帳

本總帳沿用 W0–W11、WF6 與 WF-RC／WF-PR 的既有成果。目標是：使用者提出開發需求後，Codex／Claude Code 能完成實作、互補審查、行為驗證及交付，減少重工與人工糾偏。對象是 PM／PA／E1–E5／CC 等開發代理。

根 `TODO.md` 是唯一 physical dispatch authority；本檔保存採用決策、交付規格與證據。歷史完整總帳見 Git `d5d4ef145:WORKFLOW_TODO.md`；歷史 checkpoint 不提供當前執行權。

## 當前決策（2026-09-09 交付校準）

核對基準：clean canonical main `aa0a90cda1b7024bfd86aca9d0c0ab016d0b9048`。本次用戶要求沿用總帳、核對並承接既有候選、令下一步能真實交付。本輪完成候選核對及採用決策；候選程式尚未整合，不能標為 main-adopted。

| 工作 | 當前判定 | 下一動作 |
|---|---|---|
| WF-RC-01、WF-PR-01 | 既有本地修補已完成；保留 scope／review history、finding 去重及互補 E2／E4 | 沿用，僅在新整合可能影響時執行相關回歸 |
| W3／WF6-01／W3-owned WF6-04 | 已核對候選；選為唯一優先整合交付 | 按下節凍結規格整合，直接解決 current workflow Context 缺失 |
| WF-RC-02／W2-host | 原生通用自動派工維持停用；完整入口控制未證 | 不作 W3 source delivery 前置，不自行開啟或換 transport |
| W9／W7 | 有可重用的精簡方案／生成器方法；尚非日常已採用 | W3 用當前生成器保持 parity；W9 整體精簡留待獨立需要 |
| WF6-05／06／07、W0／W11 成效 | 模型候選、真實效率／成本比較尚未完成 | 交付可用後再比較；不阻塞本次 source 功能 |
| 工作流 physical queue | 狀態以根 TODO 的 `Workflow optimization physical queue（source-only）` 為準 | 只允許 W3 這個指定交付在 fresh admission 後成為 ACTIVE |

**上一單元判定**：WF-RC-01／WF-PR-01 保留已完成；通用 native enforcement 未完成。
**偏移校準**：source checkpoint、日常採用與效率成效分別判定；取消把「完成全部歷史優化」當作本次 W3 交付的隱含前置。
**功能性可用度**：已有可重用 source 與有限 peer-review 規則；日常完整自動派工尚未驗收。
**下一 prompt 決策**：直接承接 W3 整合；技術准入讀當前 source，不重新做全框架盤點或再次確認已選方向。

## 候選核對與採用決策

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

## 下一個真實開發交付：W3 current-state integration

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

### 下一次執行提示

> 執行既有 Workflow TODO 的 W3-CURRENT-STATE-INTEGRATION。先讀 canonical AGENTS、PM、context router，再讀本檔「下一個真實開發交付」與根 TODO workflow section。核對當前 main／候選 fingerprints，承接 4b31399df＋1f87d68f9 的既有 delta，不重寫、不 merge 整條候選祖先鏈。依本節固定範圍 fresh-admit，交付 current_workflow_state 的實際功能與驗證；保留 WF-RC／WF-PR 和 native containment。既定範圍內自主完成，一批審查、一次集中修復、一次原 blocker 複核；缺 peer-review 入口時保留實作並如實報未驗，不另修帳戶／host。完成、無 delta 或限額耗盡即停止，無自動 successor。收尾回報上一單元判定、關鍵證據、偏移、功能性可用度、下一 prompt 決策。

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
| W3／WF6-01／04 | 本次已選為下一 source integration，依上節驗收 |
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

## 本次文件交付的驗證界線

本輪已做 Git／candidate bytes 核對、main 與 W3 公開 compiler 行為對照、patch 靜態套用檢查，以及本文件的 scope／links／queue／保存條件檢查。沒有執行候選程式整合、GPT‑6 A/B 或 host 派工。

目前 conductor 沒有可用的原生 subagent 工具；依 containment 不改用其他 CLI／task 建立 reviewer。本文件為 PM 完成的交付校準；獨立 R4 verdict `UNAVAILABLE`，不聲稱獨立審查 PASS，也不為取得該標籤擴出新工程。
