# CC 合規審計 — 全倉（rust engine / control_api / GUI / helper_scripts / .claude / 治理文檔）· 2026-07-03

**基準**：Mac/origin `d68a13298`（= PM cold-audit baseline SoT）；Linux runtime `262596c69`（clean，落後 3 governance-only commits）。
**模式**：read-only；Linux 證據僅 ssh trade-core 唯讀命令；0 修復 / 0 runtime mutation / 0 auth 觸碰。
**評級**：**B**（13/16 完全合規 + 3 部分合規；硬邊界 0 觸碰；9/9 安全不變量 PASS；0 BLOCKER）
**判定**：Approve（帶 4 MEDIUM 觀察修）

---

## 一、16 原則逐條

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | `intent_processor/mod.rs`（2032L）；`bounded_probe_active_order.rs` writer-mediated；IBKR lane Python no-write AST guard（AMD-2026-06-29-01） |
| 2 | 讀寫分離 | ✅ | `openclaw_authority_contracts.py:18 OPENCLAW_READ_ONLY_ROUTES`；GUI 寫面走 Rust authority（v684+ GUI cap lineage 鏈） |
| 3 | AI 輸出≠命令 | ✅ | Decision Lease 全鏈（TODO row 38：missing lease fail-close）；post-governance `lease_live_count=0` 反覆驗證；thought gate |
| 4 | 不繞風控 | ✅ | GUI/Rust RiskConfig cap lineage 強制（`00680f2b`/`2a7bfa5b`/`da72439d` 系列）；stale 10 USDT 全封 |
| 5 | 生存>利潤 | ✅ | operator 裁決 4（`d68a13298`）重寫 §二 priority 保 survival-first + fail-closed 不因近期 PnL 鬆動；`drawdown_revoke.rs` 已實裝（關 2026-04-24 CRITICAL-G06） |
| 6 | 失敗默認收縮 | ✅ | `demo_learning_lane_soak_gate.rs` indeterminate→fail-closed 照攔；BBO future-skew fail-closed（`d0109517`）；drift gate deny-by-default |
| 7 | 學習≠改寫 Live | ✅ | `cost_gate_learning_proof_promotion_gate_v1` blocked-by-default（`ed8c3595`）；Stage0R flag-OFF；MLDE demo applier 隔離 |
| 8 | 交易可解釋 | ⚠️ 部分 | 強：全鏈 sha/manifest 紀律。缺口：`earn_router.rs:376 governance_approval_id=0` 占位 sentinel（Wave D/E carry-over）→ F4 |
| 9 | 災難雙重防線 | ✅ | `risk_checks.rs`/`position_risk_evaluator.rs` 本地 + conditional order 交易所側；watchdog active（`openclaw-watchdog.service` running） |
| 10 | 認知誠實 | ✅ | profitability scorecard 自報 `EXECUTION_EVIDENCE_MISSING` 不冒認利潤；TODO 每 row 標「grants no authority/proof」 |
| 11 | Agent 最大自主 | ⚠️ 部分 | v710-v738 exact-sha 批准死循環凍結 operator 已授權的 Demo 自主迴圈（over-gate）→ F8；救濟 `d0eeafb41` 已落地待 v739 實走 |
| 12 | 持續進化 | ⚠️ 部分 | 學習管線在（proof gate/learning lane），但 demo evidence loop 因 F8 + standing auth 過期 >40h 凍結，零 fill |
| 13 | AI 成本感知 | ✅ | runtime engine env `OPENCLAW_COST_EDGE_ADVISOR=1`（ssh 實測）；`risk_config_demo.toml:498 [cost_edge]`；advisor daemon 活 |
| 14 | 零外部成本 | ✅(推斷) | Ollama local（max_retries=0 client）；rtk hook fail-open；本輪未深探付費依賴面 |
| 15 | 多 Agent 協作 | ✅ | MessageBus（control_api app 多檔）；18 role `.claude/agents/`；Conductor 非第六交易 agent |
| 16 | 組合級風險 | ✅ | `risk_config.rs:125 correlation` + `:282 validate()`；`black_swan_detector.rs`；anti-cluster |

## 二、安全不變量（DOC-08 §12，9 條）

| # | 不變量 | 狀態 | 證據 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | ✅(結構) | Stage 0R replay preflight 治理（AMD-2026-05-15-01）；runtime 行為證據屬 QA 域，本輪未注入驗證 |
| 2 | Lease 先於執行 | ✅ | `bounded_probe_active_order.rs` fail-closes missing `decision_lease_id`（TODO row 38 源證） |
| 3 | 回報落 fills 表 | ✅ | `database/trading_writer.rs`（1625L）+ `shadow_fill_writer.rs`；apply_fill 唯一 mutator（2026-06-08 修） |
| 4 | 風控降級→自動止血 | ✅ | `drawdown_revoke.rs`（Live auto-revoke；Demo/Paper HaltSession） |
| 5 | 授權失效→cancel_token shutdown | ✅ | `live_auth_watcher.rs`：revoke teardown + `slot_cancel_token`，≤5s TTR |
| 6 | Mainnet 無 flag→spawn 拒 | ✅ | `live_spawn_assert.rs` + `bybit_rest_client.rs:1034`；runtime 實測 `OPENCLAW_ALLOW_MAINNET=0` |
| 7 | retCode!=0 fail-closed 不重試 | ✅ | `bybit_rest_client.rs:202-212`；`:841-850` 註明無 wired auto-retry；advisory 面 `l2_advisory_orchestrator.py:235` max_retries=1 為非交易面合規例外（有註釋界定） |
| 8 | Reconciler 差異→降級 | ✅(結構) | per-pipeline position reconciler（`main_boot_tasks.rs:61`）+ phantom 偵測軸；runtime 注入驗證屬 QA |
| 9 | Operator 角色 + live_reserved 缺一即拒 | ✅ | `live_authorization.rs:136/199-206`：approved_system_mode 必須 `live_reserved`；LiveDemo 不降級（:23-25） |

## 三、硬邊界體檢

指紋掃描（正本 regex）命中面全部位於邊界實作/守衛檔本身；近期兩個「控制替換」commit 均有 operator 批准 + 設計正本 + E2/E4 鏈：
- `d0eeafb41` post-approval drift gate（放寬方向 operator 2026-07-02 批准；deny-by-default、ancestor check、mode-aware binary/gitlink deny、豁免僅 docs/tests/.codex）——放寬有界、方向正確（解 F8 死循環）。
- `77c7ce95b`+`bc76a18e2` IMPL-A dispatch-edge containment（取代 pre-risk 全攔）：soak gate indeterminate fail-closed 照攔；flag=0 kill switch 保留。
- `max_retries=0`（ollama_client.py:64）、mainnet guard、五 live gate、HMAC authorization.json 全部 intact。
**硬邊界觸碰：無。**

## 四、違規/發現清單（全量，含 LOW/INFO）

### F1 [FACT · MEDIUM · high] TODO §0 runtime 事實漂移（G6-04）
TODO.md:4/:37/:233 記 runtime `e16d3323` vs origin `c5fce0c`（ahead 8/behind 164）、engine PID `1538641`。ssh 實測（2026-07-03）：runtime HEAD==origin/main==`262596c69` clean；engine PID `2368227`（03:02:41 CEST 啟動）；reflog `03:15:36 reset: moving to origin/main`、`04:20/04:21 pull --ff-only` ×2。PM cold-audit baseline 已記終態，決策輸入風險受控，但 TODO 為 dispatch 權威且 v739 未刷新。**修法**：v739 TODO 刷新時重採 runtime 三元組（head/PID/service）；建議 refresh SOP 把「引用 runtime 數字必附時戳」納 checklist（已部分存在）。

### F2 [INFERENCE · MEDIUM · med] runtime reset+restart（03:02-04:21 CEST）缺鏈接的 mutation 紀錄
Operator 決策檔（2026-07-02--soak_disarm）只覆蓋 20:34Z restart→PID 2285514；其後 03:02 再啟動 + 03:15 `git reset`（覆過 hotfix head `e16d3323`，TODO.md:37 明示「Do not blind fast-forward over local runtime commits」，reset 更強）+ 兩次 pull 無對應 PM report / changelog 條目（baseline 只記終態）。內容面推斷無損（hotfix `d0109517` 已上游化）；事件面 = DOC-06 change-audit 缺口。可能無害歸因：watchdog auto-heal（restart）+ Codex 夜間 ops（git）——未證實，**交 PA re-probe**（查 watchdog log / .codex session 紀錄）。**修法**：runtime git mutation 一律留 timestamped operator/PM 紀錄；reset 類操作前置 hotfix-上游化證明。

### F3 [FACT · MEDIUM · high] 2000 行硬上限 9 個生產檔超標、無 documented exception
`discovery_loop.py` 5954 / `runtime_runner.py` 4500 / `profitability_path_scorecard.py` 3789 / `fill_sim.py` 2796 / `engine_watchdog.py` 2412 / `tick_pipeline/commands.rs` 2266 / `cost_gate_learning_lane/status.py` 2238 / `step_4_5_dispatch.rs` 2193 / `intent_processor/mod.rs` 2032（另測試檔 `intent_processor/tests.rs` 2785 等為豁免候選但同無登記）。E5 06-14 報 0 破限 → 多數為 Codex 時代累積。按 token 稅計價：前三檔為自主迴圈熱檔（agent 每輪重讀），重複開發成本最高。event_consumer 已拆（`c6f21fd57`）證明治理迴路在動。**修法**：E5 排程拆分（優先 discovery_loop/runtime_runner/status），或按 CLAUDE §七 登記 documented exception。

### F4 [FACT · LOW · high] earn_router 審計 lineage 占位 sentinel
`intent_processor/earn_router.rs:376`：`governance_approval_id: i64 = 0` + TODO 註釋（Wave D/E carry-over）。原則 8 部分缺口（僅 Earn 面；forensic 字串仍留 governance_audit_log）。**修法**：補「先寫 governance_audit_log RETURNING id」chain。

### F5 [FACT · LOW · med] AgentTool 訪問分類與代碼自述漂移
分類正本：DreamEngine=只讀，但 `dream_engine.py:436 persist_dream_insights`（DB insert 路徑，NONE→skip）——實態=學習面受限寫（自稱 0 trading.* write / 0 lease）；OpportunityTracker 正本=受限寫、docstring 自稱 read-only bridge（實態更緊，安全方向）。無安全違規，屬分類表 vs 代碼雙向 doc 漂移。**修法**：R4/FA 更新 B.3 分類表為「學習面受限寫（禁 trading.*）」語義。

### F6 [FACT · INFO · high] advisory 面 max_retries=1 合規例外（假陽性候選）
`l2_advisory_orchestrator.py:221/235-237` 有界重試上限 1，註釋明確與交易 max_retries=0 硬邊界切割。合規；列入供指紋掃描器加白名單參考。

### F7 [FACT · LOW · high] Demo API key 片段入 TODO
TODO.md:32：Demo slot key `FWkGZX...g53T` + sha12。Demo-only + 遮罩，非 live secret；但 key 材料片段常態化寫入治理文檔屬 CLAUDE §十一 精神漂移。**修法**：僅留 sha12 指紋，去掉明文前後綴。

### F8 [FACT · MEDIUM · high] over-gate：v710-v738 exact-sha 批准死循環凍結 Demo 自主迴圈（原則 11/12 雙向審）
Changelog v730/v731/v733/v735/v736/v738 連續 ROTATED/BLOCKED_BY_SOURCE_DRIFT：codex 高頻 docs commits 使 origin/main 在每個 E3/BB review 周期內必然前進 → 批准永遠過期；v731 standing auth 剩 80s 內過期。後果：operator 已授權的 bounded Demo probe 零執行、standing envelope 自 2026-07-01T17:16Z 過期 >40h、v738 零 fill——被壓制的是授權內學習/進化價值（demo 無真錢）。救濟已落地（`d0eeafb41`，operator 批准放寬方向，範圍有界）但 v739 尚未實走 = 效果未驗。**修法**：v739 優先實走 drift gate 路徑刷新 envelope；若再死循環升級 PM 重審 review 拓撲（例如 envelope TTL vs review 周期的結構性錯配）。

### F9 [FACT · INFO · high] IMPL-A containment 源碼已進 runtime checkout、running binary 未含
Engine 03:02 啟動早於 04:20 pull；running binary 仍為舊 build（TODO row 38 記 build head `e8b5c77b`）。soak flag=0（operator 07-02 決策）故 gate 本就 dormant；部署為既定 operator/PM 後續步。下次 rebuild/restart 時需驗 binary-source 對齊。

### F10 [FACT · LOW · med] standing auth 過期後內嵌 status 仍為 ACTIVE
ssh 實測：`standing_demo_operator_authorization.json` 內嵌 `STANDING_DEMO_AUTHORIZATION_ACTIVE` 而實已過期（TODO 已知悉；validators 走 expiry 數學 fail-closed）。對 naive reader/log 是 fake-success 面。假陽性候選（政策上禁讀內嵌 status）。**修法**：refresh 路徑寫回 EXPIRED 或 schema 去掉 status 字段。

### F11 [FACT · INFO · high] Mac memory/ 髒樹懸掛（R4 巡檢未 commit 產物）
44 modified/deleted + 47 untracked 集中 memory/（baseline §2 已記）。多 session race 協議要求 commit-first。交 operator 決定 `git commit --only memory/`。

## 五、結論

0 BLOCKER、0 硬邊界觸碰、0 F 級事項。4 MEDIUM 全部有清晰修復路徑且 2 個（F8/F1）的救濟已在 pipeline 中。雙向審視角：本輪最大的合規問題不是缺控制，而是 F8 的過度控制（已由 operator 批准的有界放寬修正中）——方向與「風控淨貢獻計價」裁決座標一致。

判定：**Approve**。評級 **B**。

— CC · 2026-07-03 · baseline `d68a13298`
