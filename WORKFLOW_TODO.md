# 工作流優化總帳（校準版）

此檔是來源限定的狀態索引；根 `TODO.md` 是唯一 physical dispatch authority。歷史完整總帳可由 Git `d5d4ef145:WORKFLOW_TODO.md` 讀取；不在此複製 PR190/security 敘事。

## 最小修復與最快完成路徑

`WF-PR-01 = LOCAL_SOURCE_REPAIR`：只修改既有 review control 與 routing，
不重建 framework。修補前公開回歸重現 11 項失敗；修補後的 exact source 與
獨立驗證結果見本節收口記錄。這是本地來源修復，不宣稱 native host 已恢復。

1. 一位實作 owner；E2 審邏輯／範圍，E4 驗證行為。事先固定各自問題，
   docs 的直接審查保留，其他專業角色只按實際任務事實加入。
2. 同 generation 的相同 finding 完整一致才去重，保留所有 reviewer 原文；
   同 ID 分歧明確拒絕合併。全部意見集中一次修復，原 blocker 最多一次複核。
3. 舊帳、範圍外建議、host 與成本量測只保留為觀察或 WAITING；不自動升為
   prerequisite，也不另開 prompt。達成當次驗收就停止，未解 blocker 明確交還。

根因校準：原有有界 multiagent 設計仍適用；執行時沒有守住原交付邊界，
加上跨 reviewer finding 重複與泛用 workflow 標籤自動觸發 AI-E，會放大重工。
此修復消除後兩個可重現缺陷，並明定前者的 PM 收口責任。它不證明所有歷史
loop 都有同一原因，也不把文檔規則誤稱為平台攔截器。

Operator 已要求保留有限 peer review，可在現有可用入口安排；這與重新打開
native 通用自動派工分開。替代 CLI 試跑未成功（Codex 90 秒 timeout；Claude
回傳認證拒絕），已停止，不自動發起帳戶／環境修復或再試。

## 當前控制狀態

`WF-RC-02 = NATIVE_AUTO_DELEGATION_DISABLED`：先停用本地未受控 native 自動派工，保留框架程式。canonical `.codex/config.toml` 與桌面 workspace root 的最小本地投影均須關閉 `features.multi_agent` / `agents.enabled`；新載入入口適用，既有執行中 task 不宣稱已被 retroactive 改寫。代理不得自行重開或改用另一入口。

完整 native scope enforcement **尚未關閉**：WF-RC-01 只保護固定 paired IDs；省略 IDs、換 pair、移除 surface 的三項 CLI 實測仍可 admission。Registry native surface 仍 `reported_only` / `mandatory_role_eligible=false`，不能把設定或角色文字當成執行控制證據。重新啟用前，必須先有 Operator 明確要求，並證明實際派工入口強制綁定父交付、固定子節點／路徑、禁止遞迴、有限呼叫／等待／時限、缺綁定零派工。Operator 已明確要求保留 bounded peer review；通用 native 重新啟用仍為 `WAITING_ENTRY_PROOF`，不自動成為其他任務的前置工作。

本交付完成後不新增自動派工或修復 prompt；根 TODO 保持零 ACTIVE。PM 與 subagent 發現超出原目標／驗收的問題只記錄 exact delta，不得自行更名、重開或整合。

## 當前本地修復

| 項目 | 狀態 | 可證事實與限制 |
|---|---|---|
| WF-RC-01 local delivery guard | `LOCAL_CLI_VERIFIED`，source `217efeba0c8c73b3cb7e7937440236aaad925131` | E2 initial map-key P1 `WF-RC-KEY-001` 已修，exact recheck PASS `sha256:60ca2652ec9ea061d7ee8224019255d3b494a6b62df8867c6c3b979e16ab1fa7`；E4 independent exact run `61 passed / 0 failed`、45.81s、exit 0，`sha256:ab66390f32fdd89c790f762bb6542b6a3906e74ed2bf1bb48a2889f9dc41219a`。PM public CLI 以 separate processes/two worktrees 證 first PASS、release、second `DELIVERY_REPAIR_NOT_AUTHORIZED`。該 evidence 不建立 host、runtime、remote 或效率 effects。 |

修復只使用既有 `agent_workflow` paired `work_item_id`/`lane_id`：同一 user delivery 跨 task/worktree/process 重用；journal 凍結 objective、acceptance、hard stops 和 roots，scope 只能縮小，release 保留 history。repo-bound review 保留原 contract/完整 initial reviewers，僅一 repair 加一 exact recheck；同 non-null blocker 的 comment-byte churn 在 explicit loop 停為 `BLOCKED_NO_DELTA`。legacy/unbound compatibility 不得到 aggregate claim；map-key mismatch 為 `DELIVERY_STATE_AMBIGUOUS`。

根因是 per-task/packet budget reset 與 byte-churn 被誤作 progress（public RED 已示範）；PM 曾錯把無關 PR190 當 prerequisite，已撤回且未改其 source。歷史 amplification 只是具體資料的 inference，不證明所有 loops 相同。

兩個操作界線：`artifact_digest` 雜湊 canonical plan，不是 outer pretty JSON；用 native validator。verification preflight `DENIED` 等於零次測試執行，應留存 denial 並改用既有 code-owned provider/allowed argv；它與真正 test failure 分開，不能重設 task、Context 或 budget。兩次 E4 preflight denial 因此不是測試證據；較早 E2 lost-handle 亦不可作 PASS。全 repo writer-lease 2031>2000 是 pre-existing debt，不是本回歸或 global-green claim。

## 歷史 checkpoint 與未完成依賴

| 項目 | 狀態／出口 |
|---|---|
| W0 baseline/economics | `UNAVAILABLE/PENDING_CANDIDATE_RUNS`；需 provider-attested usage、comparable runs，不能由 cache 推成本。 |
| W1 local collector / host selection | source-only closed；selected host evidence 仍 `WAITING_EXTERNAL_EVIDENCE`。 |
| W2 local / host integration | local controls closed source-only；daily host `WAITING_OPERATOR_APPROVED_HOST_INTEGRATION`。 |
| W3 Context micro-pack | closed source-only；無 usage/time/cost/adoption claim。 |
| W4 assurance | conditional source-only；不自動開 W6。 |
| W5 reuse | entry closed source-only；只有 exact source/command/toolchain/environment signature 與 TTL 合格才可 `REUSED`，否則 `EXECUTED`；兩者都須 validated command capture。production trusted host verifier 未具備時，兩者均維持 trusted replay。 |
| W6 snapshot | W4 已滿足；仍需 W5 reuse evidence 與 HITL。 |
| W8 locality | 需 fresh retain/isolate/delete measurement 與 correctness。 |
| W10 KnowledgePilot | 需 explicit policy amendment；single Vault writer 與 delta-gated 保留。 |
| W11 adoption | 需 qualified comparable adoption evidence 與 policy；移除 all-W2…W10 dependency 的舊 proposal 未採用，非 current fix gate。 |
| W7 broad generator residual | generated drift closed narrow/source-only；broad generator redesign 仍待 PM gap-list assessment。 |
| W9 bootstrap residual | closed source-only；manual-pointer compliance 與 qualified host E2E 仍未證。 |
| WF6-01 / WF6-04 | 分別由 W3 selector 與 W3/W9 exact Context scoped work 關閉，僅 historical source boundary。 |
| WF6-02 | provider-attested price/usage/cache、failed/reopened cohort 與 follow-up。 |
| WF6-03 | 對應 W1/W5 inventory，非獨立 survey；缺 provider 為 `EXTERNAL_LIMIT`。 |
| WF6-05 | 需 W3/W9、Registry/generated parity、compatibility 與 rollback。 |
| WF6-06 | 需 02/03/05、fixed DAG/corpus qualified baseline、cost/call cap 與 authorized paid run。 |
| WF6-07 | optional fixed-model routing comparison。 |
| PR190 / host / measurement | 獨立 WAITING；不是 WF-RC-01 prerequisite。 |

## 收口規則

當前 physical queue 為零 ACTIVE，WF-RC-01 不需要另一個 repair prompt。任何新問題先比對 frozen acceptance；超出 scope、需要另一 subsystem/adapter 或外部 authority 時停止，形成 exact delta 後才可 fresh-admit。source completion、PM adoption、host integration 與實際效率是四個不同結論。
