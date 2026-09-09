# 2026-09-09 主 TODO 與 workflow freshness audit

範圍：逐項維護根 TODO 與 WORKFLOW_TODO 的現在狀態，並修正直接 ledger／定價註解。沒有執行其中待辦工程。PM conductor 在 native containment 下自行複驗；沒有独立 E2/E4/R4 新 verdict，不能把本地命令改標為正式角色 attestation。

## 基線與並行變更

- 初始 clean main／本次 writer accepted base：`aa0a90cda1b7024bfd86aca9d0c0ab016d0b9048`。原 v880 已逐位保存至 [快照](../archive/2026-09-09--todo-v880-pre-freshness-audit.md)。
- 審核期間另一單元完成 `e887a9c9ee592968ec61859eeff758b741e4291c`，只改 TODO／WORKFLOW_TODO：選定 W3 current-state integration、固定候選與 22 路徑範圍。本次保留全部該交付規格；不執行 W3，也不恢復舊總帳。
- GitHub main 本次只讀核對 `b411435a0063ddcfacfa390cc199b62e05966645`。PR189 已 merged；PR190 OPEN／unmerged，head `3a0e0debfd6088d199dff1e193f6bb5e6cf603d3`，CI `34054578577` failure、5 unresolved threads。PR88 CLOSED／unmerged，head `36e829cb160fa6bcc357c315824f9cc315ab7efc`。時間敏感狀態僅代表本次讀取。
- Linux SSH 連線 timeout；沒有執行遠端命令。service／PG／data／training／serving／profit 仍 UNVERIFIED，不能判為主機 down、零資料或零收益。
- Source 改動僅文件與 `settings/ai_pricing.yaml` 註解；未改數字／active flag、產品程式、role memory、deployment 或 broker 配置。

## 全部主 row 判定（46/46）

原驗收欄保留。CLOSED 行的已完成歷史 successor 改為 null；原始移交／acceptance carry 留於 v880 快照與個別未完成包。未驗 runtime 行仍須具名證據／scope／PM re-admission，不以日期經過為准入。

| ID | 校準後狀態 | 本次判定 |
|---|---|---|
| `P0-AIML-G1-CONTEXT-TRANSPORT-REGISTRY-CAP` | **DONE_SOURCE_LANDED（2026-08-07）；work_status=DONE／gate_verdict=PASS(source only, `LOCAL_REPRODUCIBLE`)／disposition=CLOSED_SOURCE_LANDED。不得重派** | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P0-AIML-G2-SOURCE-EXTERNAL-GATE-SPLIT` | **DONE_SOURCE_LANDED（2026-08-12）；非 ACTIVE，不得重派** | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P0-AIML-S2E-UID-TOPOLOGY-VALIDATION-PUBLICATION` | **`UID_VALIDATION_PUBLICATION_CLOSED`；非 ACTIVE，不得重派** | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-AIML-END-TO-END-LANDING` | BLOCKED_BY_FOUNDATION_READY | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD` | EXPIRED_UNCONSUMABLE_HISTORICAL | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P0-PROFIT-FIRST-DYNAMIC-CANDIDATE-ALIGNED-GATE-REFRESH` | FROZEN_F1_EVIDENCE_INVALIDATED | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P0-CURRENT-CANDIDATE-ACTUAL-ADMISSION-EXECUTION-ENVELOPE-REVIEW` | WAITING_FRESH_SCOPE | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-LEASE-BBO-ORDER-SHAPE-GATE` | DONE_WITH_CONCERNS_NOORDER_SUBSCOPE | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P0-CURRENT-CANDIDATE-NOORDER-REFRESH-CURRENT-HEAD-E3-BB-REQUEST` | FROZEN_F1_EVIDENCE_INVALIDATED | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE` | FROZEN_F1_EVIDENCE_INVALIDATED | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P0-EXECUTION-EVIDENCE-LOOP` | WAITING_ORDER_CAPABLE_SCOPE_AUTHORIZATION | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P0-PROFIT-OUTCOME-REVIEW` | WAITING | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P1-FEE-TIER-PRIVATE-READ-RUNTIME-INVOKE` | DEFERRED | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P1-L2-ADVISORY-MESH-E2E-1` | SOURCE_FIX_DONE_RUNTIME_SINK_UNVERIFIED | 解析修補已在 main；本次純解析 31 tests PASS，真實 sink 仍未複驗。 |
| `P2-GLOBAL-QUALIFIED-AUTONOMOUS-LEARNING-SHADOW-V1` | SUPERSEDED_BY_AIML_LONG_LIVED_LANDING_V2 | 舊 V1 已被 V2 取代；移除「兩個 active」錯誤指針。 |
| `P1-GATE-B-AUTO-CAPTURE-NEXT-5-LISTINGS` | WAITING_RUNTIME_REATTESTATION | 2026-07-12 活化及 0/5 只屬歷史，不可當最新 cap。 |
| `P2-AI-PRICING-SONNET5-INTRO-EXPIRY` | DONE_OFFICIAL_PRICE_RECONFIRMED | 官方已取消 9 月 1 日涨價；數值不變、撤銷過期任務。 |
| `P2-RUNTIME-SOURCE-BUILD-PIN-DRIFT-HYGIENE-2026-07-07` | DEFERRED | 四頭 runtime 資料已過期；本次 SSH timeout 不能證明主機離線。 |
| `P0-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W0` | DONE_POLICY_ACCEPTED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P0-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W1` | DONE_SOURCE_SECURED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W2` | DONE_SOURCE_SECURED_HARDENED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W-CI` | DONE_LANDED_FIRST_GREEN | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W3` | DONE_SOURCE_SECURED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W4` | DONE_SOURCE_SECURED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W5` | DONE_SOURCE_SECURED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W6` | DONE_SOURCE_SECURED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W8A` | DONE_SOURCE_SECURED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W9A` | DONE_SOURCE_SECURED | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P0-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W7` | WAITING_FRESH_ADMISSION_S4 | PR88 已 closed unmerged，不能再標 in-flight；S4 尚未落地。 |
| `P0-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W8` | WAITING_W7_S4 | 保留未完成；具名 predecessor 完成後還須 PM re-admission。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W9` | WAITING_W8 | 保留未完成；具名 predecessor 完成後還須 PM re-admission。 |
| `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W10` | WAITING_W9 | 保留未完成；具名 predecessor 完成後還須 PM re-admission。 |
| `P0-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W11` | WAITING_W10 | 保留未完成；具名 predecessor 完成後還須 PM re-admission。 |
| `P2-AUDIT-REMEDIATION-6-7-Q4-V157-DEPLOY` | WAITING_READONLY_REATTESTATION | source migrations 已在；production apply/shape 仍待新唯讀 attestation。 |
| `P2-AUDIT-SEAM-REPROBES-2026-07-11` | WAITING_NAMED_READONLY_AUDIT | 保留八個獨立 audit 缺口；移除無限期 generic dispatch。 |
| `P2-AUDIT-GUI-9-10-REDO-POST-P0.4` | WAITING_GUI_RESIDUAL_ADMISSION | P0.4 已收官；已有一般彈窗，typed-confirm／diff／PAPER 標示仍待補。 |
| `P3-AUDIT-AE-INVENTORY-ARCHIVE` | DONE | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P0-TRADE-CORE-OOM-STORM-CRON-MEMORY` | SOURCE_MITIGATIONS_LANDED_RUNTIME_UNVERIFIED | source 緩解／streaming 已有，舊部署指令及 in-flight 描述不能作當前狀態。 |
| `P1-WATCHDOG-AUDIT-DSN-RUNTIME-APPLY` | WAITING_OPERATOR_WINDOW | 保留 source-template 已完成與 runtime 未驗；先證實是否仍缺設定。 |
| `P1-PROFIT-MOVE23-RESEARCH-IMPL` | WAITING_RESEARCH_SCOPE_REVALIDATION | 保留 Phase0 歷史；移除「本 session 已授權 --apply」的跨會話繼承。 |
| `P2-FW-WAVE2-FRAMEWORK-OPT-BACKLOG` | DONE_WITH_FOLLOWUPS | 維持已完成／過期結論，移除已過時的自動下一包派發指示；保留歷史 carry。 |
| `P1-ROLE-MEMORY-PROMOTION-VERIFIER` | DEFERRED(named: S2E.2b-2 後 PM re-admission) | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P2-AGENT-WAVE-BLOCKED-PREDECESSOR` | DONE_SOURCE_VERIFIED | main 已拒絕 blocked dependent；聚焦現有回歸 PASS。 |
| `P2-W5-PROJECTION-MEMOIZATION` | DEFERRED(named: PM carve 排程,re-admission 啟動) | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P2-LW1-READONLY-INVENTORY-REFRESH` | DEFERRED（具名；2026-08-09 開立） | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |
| `P2-CONTEXT-STORE-PERSIST-FACE-ONLY` | DEFERRED（G1 結轉，具名） | 保留：未有新的合格解除證據；歷史資料不能轉為當前 runtime／候選／授權。 |

## 其他主 queue 與歷史標記

| 範圍 | 複核結果／解除條件 |
|---|---|
| S2E exact projection | `EMPTY`、active_count=0、dispatchable=false、next_action=null 保留；G1/G2/UID closed，不選作入口。 |
| S2E.0／.1／.2a／.2b-1／.3 | 保留 5/9 source-landed 歷史；非 production effect。 |
| S2E.2b-2／LW2 | WAITING；fresh current-head claims／distinct review／非 caller 控制 verifier 仍必須；PR189 merged 只消除 source publication 舊欠帳。 |
| S2E.2b-3／.4／.5 | WAITING predecessor；五 row drivers／kernel amendments、runtime capture／distinct actor/verifier、disposable 6-stage／9-step rehearsal 殘項完整保留。 |
| LW1 inventory／16 prerequisites | 舊 ABSENT 與後來 PRESENT 觀察均未被可信新 artifact 替代；不手填 inventory、不簽 W0／LW1 receipt。 |
| AIML runtime repair／learning vertical slice | 兩個 umbrella 仍 WAITING；FOUNDATION_READY、fit／registry／Rust consumer／第二代閉環／DR／同窗 authority 未獲新證據。 |
| §2 15 個 closed／family marker rows | 全部保留 no-repeat、候選失效／過期 envelope／maker NO-GO／V1 supersession 邊界；本次未重驗其中歷史商業數據，未開啟新工作。 |
| W3-CURRENT-STATE-INTEGRATION | 保留 e887 的 WAITING 與選定方向；候選核對不是已整合；本次不轉 ACTIVE。 |

## Workflow 全項判定（24 個具名項目）

| ID | 目前判定與必要新 delta |
|---|---|
| W0 | 有 economics evaluator 候選；需真實可比 runs／usage／durable accepted closure，無成本成果。 |
| W1 | collector 候選可重用；selected daily host evidence 缺失，不重做 inventory survey。 |
| W2 | local control 候選及既有本地修補可重用；daily host pre-action/cancel/depth/wait 執法仍未證。 |
| W3 | branch source 候選未 daily-main adopted；承接已選定整合，固定 4b31399df＋1f87d68f9 delta、保持當前 codegen。 |
| W4 | narrow editorial assurance 候選；未形成全局 review 政策放寬。 |
| W5 | source subject-binding 候選；reuse 仍須 exact command/source/toolchain/environment/TTL 與 verifier，不能降低 trusted replay。 |
| W6 | snapshot 方案未完成；W4/W5 branch 成果不等於 main adoption，原 HITL 與 reuse evidence 仍必須。 |
| W7 | narrow generator drift 候選；broad redesign 只有具名缺口才重評，不是 W3 自動前置。 |
| W8 | locality/lazy-loading 需 fresh profile 与 retain/isolate/delete correctness。 |
| W9 | bootstrap 候選保留；不得整檔覆蓋新 containment／peer-review；daily E2E 與 pointer adherence 未證。 |
| W10 | KnowledgePilot 現行 delta-gated／single-writer 規則未修改；舊政策改革 proposal 未採用。 |
| W11 | qualified adoption／性能成效仍未證；歷史整體依賴不擴大 W3 本次交付。 |
| WF6-01 | W3 已有 selector 候選；canonical 整合仍等 W3。 |
| WF6-02 | priced usage／failed-reopened cohort 缺失；cache 不等於節省，unavailable 不當零成本。 |
| WF6-03 | 重用 W1/W5 inventory，缺 provider 為 EXTERNAL_LIMIT。 |
| WF6-04 | W3/W9 section-loading 候選；不等於新 main 已採用。 |
| WF6-05 | model candidate、Registry parity／compatibility／rollback 尚待；不改 default。 |
| WF6-06 | fixed DAG/corpus 的可比 baseline、02/03/05 與明確付費 trial 範圍，未執行。 |
| WF6-07 | optional fixed-model routing A/B，無資料不空跑。 |
| WF-RC-01 | 本地 source/CLI 修補保留；不是完整 host enforcement。 |
| WF-RC-02 | native auto delegation disabled；WAITING_ENTRY_PROOF，不自行恢復。 |
| WF-PR-01 | finding 去重／分歧拒絕／精簡路由 source 修補已完成，原 proof 保留。 |
| W3-CURRENT-STATE-INTEGRATION | 唯一選定的下一 workflow 功能交付；本次只維護 TODO，不生成 successor。 |
| PR190 | OPEN／unmerged，有 CI/review debt；其他本地修補分支不等於 exact PR head 已修。 |

## 獨立 source 複驗

- L2：現存 `l2_ml_advisory_executor.py` 剝除 fenced JSON；pure parse/stage 測試 **31 passed**。現有 cascade test 以 FakeEngine/list sink 為邊界，不是真 DB；本次初次收集因 Python 3.9 缺 tomllib 失敗，Python 3.12 又缺 pytest，故 cascade 標 `NOT_RUN_ENVIRONMENT`。沒有付費 model call 或 sink mutation。
- agent-wave：既有 `test_wave_rejects_unbound_or_cyclic_dag_and_never_runs_blocked_dependents` **1 passed**；未完成 predecessor 沒有 successor call，拒 emit 全 wave receipt。這直接反證「仍需修 blocked predecessor」的舊 row。
- GUI：`risk-tab.js` 245–258 與 `tab-risk.html` 235–250 顯示一般 Live confirm，但沒有 typed input／old→new 值；Danger Zone 和 common-modals reset/unhalt 未標 PAPER。GUI PROGRESS 記 P0.4 `98f0e04f3` 完全收官。保留原三项 UX 殘缺，不再等待舊 redesign。
- OOM：`helper_scripts/cron/lib/cron_oom_victim.sh` 與 `helper_scripts/research/cost_gate_learning_lane/ledger_streaming.py` 在 main；source mitigations 不能證明當前 kernel 無 OOM 或已部署。
- Role memory：`role_memory_compaction.py` 仍要求 out-of-band host verifier，未取得 provider；role memory 不改。context-store 未找到外部 production import；persist integration 仍須 fresh profile，不重開 G1 transport。
- Sonnet 5：2026-09-09 [官方定價](https://platform.claude.com/docs/en/about-claude/pricing) 把 $2/$10 每 MTok 確認為標準價並取消原定 9 月調升。撤銷 expiry task；其餘模型價格未重審。

聚焦命令（在 aa0 source；後續上游 e887 僅改兩份文件，受測 source bytes 不變）：

```sh
python3 -m pytest -q -p no:cacheprovider --import-mode=importlib program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_ml_advisory_fence_strip.py
python3 -m pytest -q -p no:cacheprovider --import-mode=importlib tests/structure/test_agent_governance_wave_receipts.py::test_wave_rejects_unbound_or_cyclic_dag_and_never_runs_blocked_dependents
```

## Workflow checkpoint ancestry

以下 10 個 checkpoint 均不是 aa0／e887 main ancestor、均是 PR190 head ancestor。此檢查不排除等價 cherry-pick；可用性按上表 source inspection／既有核對分別判定，不由 ancestor 布林值代替功能證據。

| 項目 | checkpoint |
|---|---|
| W0 | `bb29fe6e01a68b2ddacd5d89e8421e5c31281520` |
| W1-probe | `23f76fe5efe2b28943c36a4696887b00e05273f0` |
| W1-collector | `2ce6fcab01daac10ffb2183e7ae73d34b688644e` |
| W2-local | `71805fb80ec715a3994403ddc97ca6c35b0a3fef` |
| W2-host | `3a0e0debfd6088d199dff1e193f6bb5e6cf603d3` |
| W3 | `aee17bc01cfdf2331e6c0949d616c1a9903eaec2` |
| W4 | `8bdf3a9db4c1d90b5cc5c00955581c6735644d3b` |
| W5 | `a2fc58a48b1564e9f1b89d7cdc8003afb9fe1dbd` |
| W7 | `177dc0b61a0124b4061e605eb4b7b5b556edde93` |
| W9 | `a5db6c0454f4177e6eec38a9b1078b9b7981106e` |

## 文件驗證与停止條件

收尾以現有 TODO projector、W5 marker binding tests、ID／acceptance conservation、YAML parsed-value equality、diff whitespace 與 scoped path 檢查為準；不因純文件改動重跑整個 Rust／AI/ML suite。實際結果於交付記錄補入。

本次沒有 remote push、Linux sync、deploy/restart、PG query/write、broker/order/funds effect、role-memory promotion 或自動 wakeup。全局 memory 依使用者明確要求只寫一份 ad-hoc update note；Wiki 是 derived_advisory，完成驗證後單 writer local commit／no-embed sync。
