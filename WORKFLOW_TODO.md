# 工作流與多代理優化待辦

## 文件狀態與邊界

- **文件狀態：**可執行路線圖；W0 final source checkpoint 為 `c90408613d6ce436abae619437a0bdc4acf4787f`。
- **正典位置：**repo 為 `srv/`（本 worktree 即其 linked worktree），分支為 `agent/workflow-optimization-w0-20260903`。
- **證據邊界：**本文件只規劃來源碼、設定、文件與本機可重現驗證；不授權 runtime、PG、服務、broker、下單、交易或獲利宣稱。來源、runtime、交易與獲利證據須分列。
- **更新協議：**root 每次只處理一個 `ACTIVE` 項目；完成後以受綁定的 before/apply/post 證據更新本文件，將下一個已解除依賴者轉為 `READY` 或 `ACTIVE`。任何 scope、權限、DAG、Registry 或 Context 漂移均停止並重新入場；不可藉由文件狀態自行延續工作。

### 固定狀態詞彙

`ACTIVE`（本回合唯一執行項）、`READY`（已可入場但尚未啟動）、`BLOCKED`（等待明確依賴）、`DONE`（驗收與證據已關閉）、`SKIPPED`（明載理由與殘餘風險）。建立時恰有一個工作項為 `ACTIVE`。

### 成功量測基線與注意事項

主 KPI 僅為 `elapsed_time_ms`、`input_tokens` 與 `orchestration_load`；後者是 penalty points：`calls + waits + 2*retries + 2*compactions`，不是完整 action count。Host token total 受 cached input 支配，不能直接推導美元成本。output/cache 及 duplicate exec/wait 僅為 diagnostic；exec/spawn/message/followup coverage 目前 `UNAVAILABLE/DEFERRED`，不得據此推論實際節省。所有比較仍須保留任務形狀、Context/DAG、重試、等待與驗證。

先前稽核的精簡證據基線：

- PM-only governance query 約 10.8k context。
- 單檔 E1/E2/E4 各約 13.2k，對 12k cap，且重複約 52KB。
- 一個 48 分鐘 bug fix：149 次 exec、9 次 wait、3 次 spawn，輸入由 26.5k 升至 191.9k。
- 一個 4.93 小時單元：262 次 wait、40 次 exec。
- 曾觀察到巢狀設定與 runtime 不一致；只記錄觀察，尚不宣稱成因。

### 不可削弱的安全骨架

- 精確 task、Registry、DAG、Context 綁定，且變更需重新入場。
- dirty scope、單一 writer 與不碰未擁有變更。
- 來源／runtime／交易／獲利證據分離。
- 每個可變更動作都有 effect 的 pre/apply/post 證據。
- full audit 維持固定圖，不以省 token 為由省略硬節點。
- 在有受認證 host verifier 前，capture 後仍須 trusted replay；重用也須有完整、未過期的資格證據。

### 依賴圖

`W0 → W1 → {W2, W3, W7}`；`W0 → {W5, W10}`；`{W2, W3} → W4`；`{W3, W7} → W8`；`{W1, W3} → W9`；`{W4, W5} → W6`（W6 內含 ADR/HITL）；`W2…W10 → W11`。

其中 W4 的 R4 僅在低風險 assurance lane 通過後條件式納入；W6、W10 需 HITL 決策。依賴解除後可同時有多個 `READY` 切片，但 root 每回合只提升並處理一個 `ACTIVE` 項目；各切片優先 AFK，除架構／政策決策及實質權限變更外不要求使用者介入。

## 工作項

### W0｜基線語料與成功閘門

- **類型：**HITL／量測定義；**狀態：**DONE；**阻擋於：**無。
- **成果：**以可重播樣本鎖定 baseline corpus、計算口徑、品質與安全 guardrails；建立後續 A/B 可比較的 evidence manifest。
- **擁有介面／Adapter：**candidate `measurement corpus adapter`、`success-gate projection`；本切片才決定資料欄位，不預先定義精確 API。
- **驗收：**使用者只需作一項決定：核准或調整目標 `Q0 ≤5m`、`Q1 ≤15m`、P0/P1 漏失為零、且 reopen/rework/false-closure 不增加。其餘門檻與樣本依此決定具體化。
- **驗證：**保存 baseline task/Context/DAG、call telemetry、品質結果與無法量測項，並標註 host token 的非唯一／非成本性。
- **回退或停止：**未取得此一 HITL 決定即停止，不產生後續 admission；基線不足則標記缺口，不以猜測補值。
- **明確非目標：**不改 host、agent、runtime、交易策略或既有固定 full-audit 圖。

#### W0 evidence ledger

- HITL 核准：每個 qualified run `Q0 ≤300s`、`Q1 ≤900s`、P0/P1 missed=`0`、reopen/rework/false closure 不增加。
- 初始 checkpoint admission `7328ef69a939c61c7487de70a95e8a88`；parent task digest `sha256:0cf10bb2ec2e0b034d028ce30a75cb27ef9fd113fe67579661efe6de8485441e`；DAG `sha256:470d27f060b347ccd899af87c3282448ad7c3a18563f8b4b64a2bde9309e6bdd`；source checkpoint `9f9d277bf2ce2037c74597f065d41312f1ed53bc`。
- Docs-alignment/final-semantics docs Context artifact `sha256:a4b5bc4ecf1e1771499526b36fe86472cd81099f35501e3f06b8f12189a71c1b`；task digest `sha256:df36d299ef558d6e7f69355581404ae5d50b6ae023272a10f48e36a362c076e4`；metric catalog `sha256:d4a24d037aedc0b35f5ef51887f77adfc4abf1e27aa2723d72d95e48823ca43a`；policy `sha256:4a34349dbe2ef6e28da0167c3ba4a54d983cd6bada056716e4eafdf83cfa0068`；Registry `sha256:0ab769848bb7490b9be067ae601b76b8e557d068bf0c481aca00b835e8ca8b23`；corpus `sha256:c7fb2c8310f9f80009ae1332c5a3cc7f5f1418a701a1dca0c9cc1f637b32cd01`；manifest `sha256:b3039203d8c5b002ec2bb826b12f2a3d53aed92d219e730afbeb23611a3826e2`。
- AI-E 初檢發現兩個 P1；bounded repair 後 AI-E PASS、E2 PASS，focused direct 為 `58 passed`。
- Final exact-head E4：source checkpoint `c90408613d6ce436abae619437a0bdc4acf4787f`；Context `sha256:6a1b7444b46e253edde3f7e3be3d35d6543a0a973dc4761cf0a1cfd3d5124b71`；task `sha256:931dc6a16de8d6d7613191afe0c6ce827f236f9ea051785b7319a4318255a9d0`；`65 passed / 30 deselected / 0 failed or denied`。captures：efficiency `sha256:9c0c954f97b017bd4e6f6138e2cae592577fb99d1e6b31f7f24fe3b8e8541ef5`、registry subset `sha256:521510588f9e5e24425b9866b57b27d41c723f4f6eb21220cc291e8b5b9a120b`、validate `sha256:2ad6e2f28f23fafee9ba04348a0248cfcac6b0b466887baa8d9ed881111e8b95`、render `sha256:0756a626dc236cd75050233d122252edbe6f3de68f4ed797c8275f4ba5088227`、diff `sha256:7908a19fe343a87a7f3810a2160c32775b463ade550bf792dce0c3b6f824f02b`；generations unchanged。
- 歷史 initial-checkpoint E2 已關閉四個 P1，frozen diff capture `sha256:b1c32646aca3c4c01ab9d82ab2d23b99856cf6ac181dd3403b7f102e8526f724`；`9f9d277bf2ce2037c74597f065d41312f1ed53bc` 的 E4 Context `sha256:09746b23f55a4dc3e96af4d2a97577e8540b619bcbc07978ed4fc1249a8d624d` 曾得 `60 passed / 30 deselected / 0 fail or denied`。這些是有效歷史證據，但已被 final-source verdict superseded；原始 pre-checkpoint reviewer Context 不可用的限制仍保留。
- **殘餘：**checked-in baseline 為 `UNAVAILABLE/PENDING_CANDIDATE_RUNS`。無 production host verifier、full action coverage、platform-attested usage、actual savings、adoption、runtime、deployment、trading 或 profit evidence。W1 為唯一 ACTIVE，負責建立 execution-surface truth。

### W1｜執行面真相探針與 workspace 設定優先序

- **類型：**AFK／來源設定診斷；**狀態：**ACTIVE；**阻擋於：**無（W0 DONE）。
- **成果：**建立可重現、來源限定的 execution-surface truth probe，列出 workspace、巢狀設定與實際選取設定的優先序及差異。
- **擁有介面／Adapter：**candidate `execution-surface probe`、`config-precedence report`。
- **驗收：**輸出可審閱的設定來源鏈與不一致分類；不得把觀察到的 nested/runtime mismatch 提升為因果結論。
- **驗證：**同一 immutable snapshot 的本機 capture/replay 與設定檔雜湊比對。
- **回退或停止：**若無法取得來源可驗證的選取訊號，停在 `UNVERIFIED` 並記錄缺口。
- **明確非目標：**不改 runtime 設定、不重啟服務、不接觸遠端。

### W2｜host admission、no-delta、depth 與 wait 強制

- **類型：**AFK／治理強化；**狀態：**BLOCKED；**阻擋於：**W1 DONE。
- **成果：**將 admission、無來源增量終止、巢狀深度與 wait 上限轉為 host 可拒絕的檢查點。
- **擁有介面／Adapter：**candidate `host admission guard`、`no-delta receipt`、`depth/wait limiter`。
- **驗收：**相同 task-owned source digest 終止為 `BLOCKED_NO_DELTA`，無 wakeup／重試；超限有可讀拒絕原因。
- **驗證：**fixture 驗證 accepted/rejected cases，並 capture/replay 所有 command。
- **回退或停止：**只新增監測或 guard 時須可移除；若會改變既有權限語義，升格 HITL。
- **明確非目標：**不建立自動續跑，不以 lifecycle 或時間當作進度。

### W3｜Context micro-pack 投影與去重

- **類型：**AFK／Context 效率；**狀態：**BLOCKED；**阻擋於：**W1 DONE。
- **成果：**為角色與任務生成最小、可溯源的 micro-pack，去除重複共同內容但保持 Context 綁定與可重建性。
- **擁有介面／Adapter：**candidate `context micro-pack projector`、`shared-content deduper`。
- **驗收：**同一任務的必要事實無損，重複 payload 可量測下降，且不可用摘要取代必需的精確 task/DAG/Context bytes。
- **驗證：**原投影與微包的語義欄位／digest 覆蓋比較、材料化後 replay。
- **回退或停止：**任何遺失硬節點、claim input 或來源指標即回退該投影。
- **明確非目標：**不降低角色模型層級，不取消 full audit 固定圖。

### W4｜低風險 assurance lanes 與條件式 R4

- **類型：**AFK／保證流程；**狀態：**BLOCKED；**阻擋於：**W2、W3 DONE。
- **成果：**劃分可縮減的低風險 assurance lanes，僅在明確條件成立時接納 R4。
- **擁有介面／Adapter：**candidate `lane classifier`、`conditional R4 admission`。
- **驗收：**每條 lane 有風險、uncertainty、可略過理由與殘餘風險；硬邊、E2/E4 或權限事實不得被 classifier 消除。
- **驗證：**正反例路由 fixture，確認 R4 條件未達即不入場。
- **回退或停止：**分類不確定即回到完整 assurance；不得默認低風險。
- **明確非目標：**不讓成本最佳化凌駕獨立驗證。

### W5｜命令 capture 重用與 host verifier

- **類型：**AFK／驗證可信度；**狀態：**READY；**阻擋於：**無（W0 DONE）。
- **成果：**規範 command capture 的精確簽章、可重用資格與 host verifier 演進路徑。
- **擁有介面／Adapter：**candidate `command-reuse eligibility`、`host verifier`。
- **驗收：**`EXECUTED` 與 `REUSED` 明確分別；重用完整綁定 source/diff/command/toolchain/environment/TTL，host verifier 未認證前保留 replay。
- **驗證：**變更任一簽章維度的失效 fixture，及 capture→trusted replay。
- **回退或停止：**沒有完整資格 receipt 則只執行、不重用；host verifier 不可用則不聲稱已取代 replay。
- **明確非目標：**不以 cache hit 當成測試 PASS。

### W6｜immutable-snapshot E2 與 deterministic-test 平行化

- **類型：**HITL／架構決策；**狀態：**BLOCKED；**阻擋於：**W4、W5 DONE；ADR 0050／0052 的 HITL 決策在本項內完成。
- **成果：**在 immutable snapshot 上設計 E2 與 deterministic tests 的有限平行策略，保持 writer 序列化與驗證獨立性。
- **擁有介面／Adapter：**candidate `snapshot fan-out`、`deterministic-test scheduler`；由本切片定案精確介面。
- **驗收：**使用者核准 ADR 0050／0052 的架構選項；並證明並行工作讀取同一固定世代、無共享 writer 或證據混淆。
- **驗證：**快照雜湊、DAG predecessor、並行 fixture 與回放結果。
- **回退或停止：**未核准 ADR 或任何非決定性／污染跡象即回到串行。
- **明確非目標：**不允許 builders 同波寫 shared worktree，不取消 E2 獨立性。

### W7｜宣告式跨 runtime policy 生成與 canonical helpers

- **類型：**AFK／政策一致性；**狀態：**BLOCKED；**阻擋於：**W1 DONE。
- **成果：**由單一宣告式政策投影跨 runtime 設定與 canonical helpers，降低巢狀配置漂移。
- **擁有介面／Adapter：**candidate `policy generator`、`canonical helper projection`。
- **驗收：**生成物可追到唯一來源，跨 runtime 差異可檢出且無法靜默通過。
- **驗證：**golden projection、drift fixture 與 source-only replay。
- **回退或停止：**若無法無損投影，保留既有設定並輸出差異報告。
- **明確非目標：**不直接套用 runtime 政策、不改服務或權限。

### W8｜治理 locality：延遲載入 S2 adapter 與 context_store 量測

- **類型：**AFK／Context locality；**狀態：**BLOCKED；**阻擋於：**W3、W7 DONE。
- **成果：**僅在 S2 需要時載入專屬 adapter，並先量測 context_store 的 retain/isolate/delete 行為再作保留決策。
- **擁有介面／Adapter：**candidate `S2 lazy loader`、`context_store measurement probe`。
- **驗收：**量測先於資料生命週期調整；各 decision 有上下文節省、正確性與資料隔離證據。
- **驗證：**retain/isolate/delete 對照實驗、digest coverage 與未載入 S2 的負例。
- **回退或停止：**量測不明或隔離失敗即停用 lazy retention 變更。
- **明確非目標：**不刪除所需 Context，不以不可驗證的 token 推測替代量測。

### W9｜精簡 TradeBot bootstrap profile

- **類型：**AFK／啟動路徑；**狀態：**BLOCKED；**阻擋於：**W1、W3 DONE。
- **成果：**建立最小且任務導向的 TradeBot bootstrap profile，僅載入 triage 所需熱路徑。
- **擁有介面／Adapter：**candidate `bootstrap profile selector`、`context manifest`。
- **驗收：**普通窄任務避免 universal preload，同時高風險／runtime／權限任務仍載入對應正典來源。
- **驗證：**任務類型矩陣、必要來源 coverage 與 cold-start 量測。
- **回退或停止：**缺少規範來源或 Context 即回復完整安全載入並報 `NEEDS_CONTEXT`。
- **明確非目標：**不將 profile 當作跳過治理、TODO 或 Registry 的權限。

### W10｜KnowledgePilot 移出 critical path 協議

- **類型：**HITL／政策修訂；**狀態：**READY；**阻擋於：**無（W0 DONE；HITL policy approval/amendment 由本項處理）。
- **成果：**提出將 KnowledgePilot 與關鍵工程循環解耦的安全協議，保留 delta-gated、單一 Vault writer 與可追溯性。
- **擁有介面／Adapter：**candidate `off-critical-path handoff`、`Vault update receipt`。
- **驗收：**使用者核准 parent AGENTS／政策修訂；工程閉環不再被非必要 Vault 寫入阻塞，且知識更新沒有遺失或並發 writer。
- **驗證：**政策 diff、handoff fixture、writer collision 與延後更新情境。
- **回退或停止：**未取得 HITL 或 parent policy 未修訂前維持現行協議。
- **明確非目標：**不自行修改 parent AGENTS，不取消知識沉澱要求。

### W11｜端到端 A/B canary、回退與採用關閉

- **類型：**AFK／整合採用；**狀態：**BLOCKED；**阻擋於：**W2 至 W10 全數 DONE（W0、W1 已隱含）。
- **成果：**在固定 corpus 上執行端到端 A/B canary，依 W0 閘門決定採用、回退或保留研究狀態。
- **擁有介面／Adapter：**candidate `canary comparator`、`adoption closure packet`、`rollback selector`。
- **驗收：**可比較的 task/Context/DAG、品質、安全、wait/exec、token telemetry 與成本不可推導註記；Q0/Q1 與零 P0/P1 漏失滿足，且 reopen／false-closure 未增加。
- **驗證：**固定圖完整覆蓋、獨立驗證、capture/replay，及採用前後 manifest 對比。
- **回退或停止：**任一硬閘失敗即回退至已驗證設定並保留證據；不可將未知量測視為成功。
- **明確非目標：**不宣稱 runtime、交易或獲利改善，不把 canary 結果擴張為部署授權。

## 每次互動協議

1. root 只選取一個 `ACTIVE` 項目，重綁 exact task、Registry、DAG、Context、dirty scope 與權限。
2. 若是 AFK 切片，root 在既定來源邊界內完成並回報 evidence；只有 HITL 或實質權限變更才向使用者要求決策。
3. 完成時記錄 pre/apply/post、驗證、殘餘風險與下一依賴；未完成時以明確 owner/unblock condition 停止。
4. 不可因等待、重試、狀態標籤或未關聯 HEAD 漂移而續跑；相同 task-owned source digest 結束為 `BLOCKED_NO_DELTA`。

## 進度帳本範本

| 欄位 | 紀錄 |
| --- | --- |
| 工作項／狀態 | `W?`／固定狀態詞彙 |
| admission | task、Registry、DAG、Context digest 與 baseline |
| 範圍 | writer、dirty scope、來源／runtime／交易／獲利證據分類 |
| pre/apply/post | 世代、effect、變更紀錄與 command capture |
| 量測 | corpus、品質、安全、wait/exec、host token telemetry 與 caveat |
| 驗證 | fixture、trusted replay、獨立審查、未覆蓋項 |
| 結論 | 驗收、殘餘風險、rollback/stop、下一 owner／unblock condition |
