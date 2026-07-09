# FA Sign-off — Decision Lease Three-Way Review · Path A

**日期**：2026-05-02
**審計員**：FA（Functional Auditor）
**對應 agenda**：`docs/CCAgentWorkSpace/PM/2026-05-02--decision_lease_review_agenda.md`（commit `548b145`）
**Commit base**：`a7b93d5`（Mac/Linux/origin 同步）
**判定**：**Approve Path A**（spec 改動 0；可審計性 100% 恢復）

---

## 1. 確認或推翻 FA archaeology 結論

### 1.1 路徑 A 仍推薦

維持。Rust `acquire_lease()` facade + Python IPC 轉呼方案是**SM-02 §scope 內的 last-mile 兌現**，不是新加 spec。三點具體理由：

- **SM-02 §scope 條文（287-spec audit §SM-02 lines 109-130）明寫**：「Time-bound right to execute trading decision with: Unique ID / TTL / Revocation / Full audit trail. No order without lease. SM02-R22: Full audit trail from emission → outcome.」「No order without lease」是無條件條文，沒有「Python only」例外子句。Rust 熱路徑 0 acquire_lease = 直接破口。
- **Mandatory Rule 1（287-spec lines 376-381）**：`No order without lease — SM-03/EX-02 requires active SM-02 lease`。Rust intent_processor/router.rs 是真實意圖出口的事實 = 該 router 必經 lease 是 spec 的字面要求。
- **Rust migration v3 plan §1.3** 已寫應有 `acquire_lease/release_lease` facade（agenda §0 已 cite）；這不是新 spec，是回填 R-04 漏做。

### 1.2 對 PA 提案沒有 spec 層 push back

PA 提的「Rust acquire_lease facade + Python IPC 轉呼」與 SM-02 / DOC-01 §5.3 條文沒有衝突，反而更貼合：

- **SM-02 §scope 不破壞**：Rust `lease.rs` 9 狀態（Draft / Registered / Active / Bridged / Frozen / Revoked / Expired / Rejected / Consumed）已實作，`acquire_lease` facade 只是把已存在的 SM 包成 single-call entry，狀態機本體不動。
- **DOC-01 §5.3（根原則 #3）強化**：「AI 輸出 ≠ 即時命令 → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行」— Path A 後 Rust 熱路徑也走 lease，原則 #3 從 PARTIAL→PASS。
- **EX-06（Agent Conflict Arbitration）對齊**：spec 要求「Formal object communication（SignalEvent, DecisionLease, ExecutionStatus）」，Path A 把 DecisionLease 從 Python-local 對象升為跨平面 formal object。
- **EX-07（Agent Data Access Control）**：Python IPC 轉呼意味著 `governance_hub.py`（EX-07 implementing module）成為 cross-SM 真實調度入口，符合 spec 本意。

### 1.3 雙寫過渡期 4 週對 6-element trade reconstruction 的影響

DOC07-R 6 elements（pre-decision state / decision basis / risk approval / **authorization basis** / execution action / post-execution result）。

- **Element 4「authorization basis」過渡期需特別 SOP**：4 週內 Python ExecutorAgent 走 Python local SM + Rust IPC 雙寫，lease_id namespace 必須 prefix 隔離（PA 提案 `py_*` / `rs_*`）。audit reconstruction 需明文：「同一筆 trade 的 authorization basis 可能引用兩個 lease_id」這是 by-design transitional artifact。
- **元素 1/2/3/5/6 不受影響**：state / basis / verdict / action / result 是 Rust 平面寫的，與 lease facade 無關。
- **Audit 連續性**：4 週內 audit 重建 lease 元素時必須 union 兩個 namespace，FA 建議 retrofit 同 commit 加一條 SQL view（`v_lease_unified`）暫時融合兩平面，Path A 完成 + Python 平面 deprecate 後刪除。

---

## 2. SM-02 R-04 retrofit amendment 文件

完整文件已寫入 `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`（PM commit）。

---

## 3. 16 根原則影響評估

### 3.1 Path A 完成後升級的 4 條

| # | 原則 | 當前狀態 | Path A 完成後 | 證據 |
|---|---|---|---|---|
| #3 | AI 輸出 ≠ 即時命令 | **PARTIAL→FAIL on hot path**（Python ExecutorAgent only；Rust router.rs 0 acquire_lease） | **PASS** | 5 Agent 鏈 + Rust intent_processor 都過 lease；DOC07-R element 4 真填 lease_id |
| #8 | 交易可解釋（6-element auth） | **PARTIAL**（element 4 由 GovernanceProfile verdict 替代，語義漂移） | **PASS** | element 4 = production lease_id，namespace unified；audit reconstruction 不再有歧義 |
| #11 | Agent 最大自主權（LG-5 contract） | **RFC only**（25d8e54 LG-5 RFC commit；contract 缺 lease 形式化憑據） | **可簽 contract** | LG-5「Constrained Autonomous Live」的 constraint = lease TTL + revocability，現在有 production formal object |
| #15 | 多 Agent 協作（EX-06 formal object） | **0 流動**（DecisionLease 在 production message bus 0 emit） | **production 真活** | Rust router 每筆 production-profile intent acquire/release，bus traffic 從 0 升到～real intent rate |

### 3.2 其他原則副作用評估（無 regression）

- 原則 #1（單一寫入口）：Path A 強化，因 Rust router 是真實單一寫入口，加 lease gate 不引入第二寫入口
- 原則 #2（讀寫分離）：無變化
- 原則 #4（策略不能繞過風控）：無 regression；Guardian gate 仍在 lease 之後
- 原則 #5/6（生存 / 失敗收縮）：lease IPC 失敗時 fail-closed 拒絕意圖 = 收縮，與當前 Python 平面行為一致
- 原則 #7（學習 ≠ 改寫 Live）：無關
- 原則 #9（雙重防線）：無變化
- 原則 #10（認知誠實）：無關
- 原則 #12（持續進化）：無關
- 原則 #13（AI 資源成本感知）：lease 呼叫～10µs，遠低於 cost_edge_ratio 噪聲下限
- 原則 #14（零外部成本）：純本機 IPC，無外部成本
- 原則 #16（組合級風險）：無關

**唯一需監控的副作用**：`#13` AI 成本記錄不應把 lease IPC 計入 AI invocation cost（lease 是 governance 不是 AI）；retrofit 同 commit 必確認 `record_ollama_call` / `cost_edge_ratio` 計算口徑不被汙染。

---

## 4. 治理 source 修復策略

### 4.1 問題定義

`docs/governance_dev/DEPRECATED.md`（2026-04-06）整目錄標退役，但 `SPECIFICATION_REGISTER.md` SM-02 / DOC-01 / 全 16 條 SM/EX/DOC 仍 Active；DEPRECATED.md 也明說「歷史參考」非廢條文。**這是 silent drift 的根源**：spec 條文 active 但條文所在目錄被掛 deprecated 大標籤，sub-agent 引用時陷入 trust paradox。

### 4.2 FA 推薦處置（同 retrofit commit 落地）

**優先方案**：**Option A — 部分重啟 governance_dev/，明文聲明 amendments/ 子目錄是 active**
- 在 `DEPRECATED.md` 開頭加「**Exception**: `amendments/` 子目錄 + `SPECIFICATION_REGISTER.md` 仍 Active；本 disclaimer 僅針對 `phase{0..12}` / `T2.xx` 等歷史 changelog」
- 新建 `docs/governance_dev/amendments/` 目錄（本次 Path A amendment 文件落腳處）
- 在 `SPECIFICATION_REGISTER.md` 新加「Amendments」section 索引所有 amendment 文件，與 SM/EX/DOC 表並列

**理由**：把條文整體搬到 `docs/specifications/` 會打破 22 份 governance 文件的歷史 ref-chain（多份 RFC / audit 報告硬寫 `docs/governance_dev/...` 路徑），高風險低收益。

**不推薦的兩條**：
- ~~Option B：把條文展開搬到 `docs/specifications/`~~ — 多份歷史 audit 引用斷鏈，需大量 collateral fix
- ~~Option C：保留現狀只加 amendment 文件~~ — silent drift 根源未解，下次審計會再標 Critical

### 4.3 SPECIFICATION_REGISTER.md 同步動作

retrofit commit 同次更新：
```diff
 ## Active Specifications / 活躍規範
+
+## Amendments / 規範修訂（2026-05 新增）
+| Code | 對應 spec | 路徑 | 日期 | 摘要 |
+|------|----------|------|------|------|
+| AMD-2026-05-02-01 | SM-02 §scope · DOC-01 §5.3 | docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md | 2026-05-02 | Path A — Rust acquire_lease facade R-04 retrofit |
```

`Last Updated:` 由 `2026-04-29` → `2026-05-02`，maintainer 加 `FA Sign-off (path A)`。

---

## 5. FA Sign-off Statement（commit-message-style，≤200 字）

```
FA sign-off (2026-05-02): Path A approved. SM-02 amendment file
attached at docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md.
Spec change: 0 — Rust acquire_lease facade is within SM-02 §scope
("No order without lease", SM02-R22 audit trail) as originally
specified; R-04 last-mile fill, not new requirement.
16 principles impact: #3 PARTIAL→PASS, #8 PARTIAL→PASS, #11 RFC→
signable contract, #15 0-flow→production message bus active.
Acceptance criteria for E4:
  (1) >=5 of 9 SM-02 transitions logged in 24h (DRAFT/REGISTERED/
      ACTIVE/BRIDGED/CONSUMED happy path);
  (2) 6-element auth fill rate >=95% on 10 sampled trade_attribution rows;
  (3) production lease_id flow >=1/24h in learning.directive_executions
      (or equivalent table);
  (4) weekly SM-02 transition coverage audit shows no degradation.
Failure rollback: see amendment §6 (Path B reserved for hot-path
performance disaster only; Path C reserved for dual-plane semantic
divergence only; no silent drift rollback).
Closes P0-GOV-1.
```

---

**FA AUDIT DONE**: 本 sign-off + amendment 文件由 PM 同 commit 落地。Memory append 同步加入 `docs/CCAgentWorkSpace/FA/memory.md`（FA-2026-05-02-PATH-A-SIGNOFF）。
