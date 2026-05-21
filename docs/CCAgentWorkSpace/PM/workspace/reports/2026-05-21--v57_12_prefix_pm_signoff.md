# v5.7 12 條 CRITICAL prefix — PM 驗收 sign-off

**日期**：2026-05-21
**範圍**：TODO §0.5 v57-C1 ~ v57-C12 全部完成 + FA + PA 核實後 PM 驗收
**verdict**：**APPROVE — Sprint 1A 派發 GO-WITH-CONDITIONS**（5 PM 仲裁項決議 / 2 operator follow-up / 3 派發前 must-fix；不阻塞今日 commit + 三端同步）

---

## 一、12 條 prefix 完成狀態彙總

| ID | 內容 | 落地 | FA verdict | PA verdict |
|---|---|---|---|---|
| C1 | v5.7 主檔 git rename | `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` | ✅ APPROVE | ✅ |
| C2 | 4 ADR draft 0030/0031/0032/0033 | `docs/adr/` 926 行 | ✅ APPROVE | ✅ 風格 100% 對齊 |
| C3 | V103/V104 schema spec | `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` 940 行 | ⚠️ CAVEAT（V### 命名 + 4 audit field 缺）| ⚠️ NEEDS-ARBITRATION |
| C4 | Bybit Earn endpoint verdict | BB report — (a) API EXISTS 12 endpoint | ✅ APPROVE | ✅ |
| C5 | Earn API key scope | BB report — (a) non-withdraw sufficient | ⚠️ CAVEAT（operator 查 key 發行日）| ⚠️ |
| C6 | liquidation writer claim | BB report — (a) PROOF PASS 31,473 rows | ✅ APPROVE-STRONG | ✅ 推翻 v57 audit Risk 1 |
| C7 | Sprint 1B C10 Stage 0R+Demo | dispatch_packet §1 | ✅ APPROVE | ✅ |
| C8 | Earn governance spec | `docs/execution_plan/2026-05-21--earn_governance_spec.md` 460 行 | ⚠️ CAVEAT（§4 待 finalize）| ⚠️ |
| C9 | V103/V104 PG empirical dry-run | `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` + PA report | ✅ APPROVE-STRONG | ✅ |
| C10 | Sprint 1A 工時 + §9 sub-agent mandate | dispatch_packet §2 | ⚠️ CAVEAT（工時衝突）| ⚠️ |
| C11 | Apple Silicon CI clause | dispatch_packet §3 | ✅ APPROVE | ⚠️ clippy 17 既有 errors |
| C12 | 中文注釋 + SCRIPT_INDEX + MODULE_NOTE | dispatch_packet §4 | ✅ APPROVE | ✅ |

**統計**：FA 8 ✅ / 4 ⚠️ / 0 ❌ ；PA 8 ✅ / 4 ⚠️ / 0 ❌

---

## 二、PM 仲裁決議（5 條）

### 仲裁 1：G5 V### re-number — 採路徑 A ✅

**FA + PA 共識推薦 A**。

決議：採 **option A**
- V097 / V098 = Linux catch-up（不變）
- V099 / V100 = Track v3 schema（v5.7 §3 V101/V102 移此）
- **V101 / V102 = Earn schema**（v5.7 §3 V103/V104 移此）

**理由**：
- C9 empirical 證實 DB head=V096；V101/V102 尚未 land
- V101 spec v3 自留「順延 V103/V104」option（per C9 PA 報告 §6.2）
- 30-60 min search/replace churn 可清（4 ADR + V103 spec + earn_governance_spec + v5.7 主檔 + dispatch_packet）

**執行範圍**（**派 PA + TW 補位 5-8 hr 完成**；不在本 sign-off 範圍）：
- v5.7 主檔 §3 §7.5 字眼搜尋替換
- V103 spec rename → V101/V102 + 內文 V### 替換
- ADR-0030/0031/0032/0033 cross-ref V### 替換
- earn_governance_spec §10.2 上游列表替換
- dispatch_packet §5 prerequisite check list 替換

### 仲裁 2：G3 工時 reconcile — 採 75-105 hr 中間值 ✅

**PA 推薦中間值**；FA 推薦 90-130 hr 全 buffer。

決議：採 **PA 中間值 75-105 hr**
- 不全回滾 65-85 hr（BB C6 推翻僅 §6 部分，並非全部）
- 不維持 90-130 hr 全 buffer（BB C6 確實推翻 +15-20 hr 反估）
- **75-105 hr 含 GUI 8-12 hr buffer + 5 並行 track coordination overhead + 字典補錄 4-6 hr**

**理由**：14 agent 中 11/14 認為 60-80 hr 系統性低估，buffer 不浪費；但 BB C6 推翻 v57 audit Risk 1 後 §6 工時確實減 15-20 hr，全 reconcile 為中間值最誠實。

**Y1 total reconcile**：1,275-1,710 hr（per 中間值線性放大；非 90-130 hr 線性放大的 1,295-1,740 hr）

**執行範圍**：更新 dispatch_packet §2 數字（本 sign-off 一併處理）

### 仲裁 3：G2 V101 字段集 — 採路徑 A ✅

**FA 推薦 A**；PA 未提（無衝突）。

決議：採 **路徑 A**（v5.7 brief 字段集 / 廢棄 V101 spec §3.3.1+§3.3.2 字段集）

**理由**：
- v5.7 brief 字段集服務 dual-track（direct_exploit + asds_factory）+ Sprint 1B 統計 sample size gating
- V101 字段集服務 ADR-0026 v3 single-track（direct_exploit only event-study）
- v5.7 brief 涵蓋面更廣 + 對應 operator intent
- V101 §3.3 兩表「new spec」尚未 IMPL 故字段集 swap 0 runtime cost

### 仲裁 4：G7 C8 §4 finalize 為條件 A ✅

**BB C4 verdict 已下 (a) API exists**。

決議：採 **條件 A**（Earn demo + live 兩環境；demo OPENCLAW_ALLOW_MAINNET 不適用 / live 強制）
- Earn governance spec status DRAFT-FOR-PM-REVIEW → **DRAFT-FOR-FIVE-ROLE-CROSS-REF**（§4 條件 A 採納；待 FA + E3 + QA + MIT cross-ref 後 final）

**執行範圍**：更新 earn_governance_spec.md §4 標明條件 A 採納（本 sign-off 一併 patch）

### 仲裁 5：Apple Silicon CI clippy 軟強制 ✅

**PA 發現 17 既有 clippy errors**。

決議：採 **PA 雙軌建議**
- Sprint 1A 派 sub-agent prompt：`cargo check --target aarch64-apple-darwin --release` **必過**（hard gate）
- `cargo clippy -- -D warnings` **暫時軟強制**：新 crate 必過；既有 17 errors 標 P2 ticket 並行清
- 開 P2-CLIPPY-CLEANUP-1（owner E1 / 工時 4-6 hr / Sprint 1A 進行中可並行補）

**執行範圍**：更新 dispatch_packet §3 加雙軌條款 + P2 ticket 標記（本 sign-off 一併 patch）

---

## 三、operator follow-up 項（不阻塞今日 commit）

| ID | 內容 | 工時 | 路徑 |
|---|---|---|---|
| **G4** | OpenClaw key 發行日 verify（Bybit Web → API management 查 read_only + trading key Last edited date） | 5 min | operator hands-on；TODO §0.5 標 ⏳；Sprint 1A read-only first 不阻塞；Sprint 1B stake/redeem 派發前必驗 |
| **H2** | Console tab 歸屬決策（Earn → governance / Allocator → agents / Counterfactual → learning）| 1-2 hr | A3 + PA + operator 工作會；TODO 標 H 級 should-fix；不阻塞 Sprint 1A 派發 |

---

## 四、Sprint 1A 派發前 must-fix（PA + sub-agent 補；不需 operator）

| ID | 內容 | 工時 | Owner | 觸發 |
|---|---|---|---|---|
| **G6** | V103 earn_movement_log schema 補 4-5 audit field（lease_id / approval_id / actor_id / bybit_request_payload / rationale）| 5-8 hr | PA + MIT | 仲裁 1 V### re-number 同 batch 處理；2026-05-22 內 land |
| **C9-followup** | docs/agents/context-loading.md 或 CLAUDE.md 補 PG connection 範例（防 future audit script 誤導 psql -d openclaw -U openclaw）| 30 min | TW | 2026-05-22 內 land |
| **C8-cross-ref** | Earn governance spec 五角色 cross-ref（FA + E3 + QA + MIT） | 各 1-2 hr | 5 並行 sub-agent | 預 2026-05-22 內 land |

---

## 五、本 sign-off 同步 patch 範圍

PM 在本 sign-off 階段 hands-on patch 3 個 file：

1. **dispatch_packet §2** 工時數字改 75-105 hr（per 仲裁 2）
2. **dispatch_packet §3** 加 clippy 雙軌條款 + P2-CLIPPY-CLEANUP-1（per 仲裁 5）
3. **earn_governance_spec §4** 標明條件 A 採納 + status 改 DRAFT-FOR-FIVE-ROLE-CROSS-REF（per 仲裁 4）

仲裁 1（V### re-number）+ 仲裁 3（V101 字段集）為大範圍 search/replace + 4-5 audit field 補；**派 PA + MIT 在 2026-05-22 內完成**，不在本 sign-off patch 範圍。

---

## 六、TODO §0.5 更新範圍

12 條 prefix 全部標 ✅（C1-C12 對應 sign-off verdict）：
- C1/C7/C10/C11/C12：PM hands-on PASS
- C2：TW 4 ADR draft land
- C3：MIT spec land（V### re-number + audit field 補待 2026-05-22 PA+MIT 補位 patch）
- C4/C5/C6：BB verdict (a)(a)(a) 三選一全勝（C5 + 1 operator follow-up）
- C8：CC spec land（§4 condition A finalize 待 PM patch；五角色 cross-ref 待 2026-05-22）
- C9：PA dry-run land（揭重大 V### 衝突，已 PM 仲裁採 option A）

§0.5 表格加 "DONE 2026-05-21" 標記 + 補充 follow-up 提示。**§1 路線變更區仍維持空白**（per D6 暫不批准；本 sign-off 不重填）。

---

## 七、PM 一句話結論

> v5.7 12 條 CRITICAL prefix **全部完成**；5 PM 仲裁項已決議（全採 FA + PA 推薦）；2 operator follow-up 不阻塞；3 派發前 must-fix 派 PA + TW + 5 並行 sub-agent 在 2026-05-22 內完成；Sprint 1A 派發 GO-WITH-CONDITIONS — D+1 5 並行 track 可派。

**PM SIGN-OFF DONE 2026-05-21**

**verdict**: APPROVE — Sprint 1A 派發 GO-WITH-CONDITIONS

**next step**: 三端同步（commit + push origin + ssh trade-core fast-forward）→ 派 PA + MIT + TW 補 must-fix → D+2 Sprint 1A 正式 dispatch
