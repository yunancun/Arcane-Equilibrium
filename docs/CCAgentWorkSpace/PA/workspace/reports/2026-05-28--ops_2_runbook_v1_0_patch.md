---
title: P1-OPS-2-RUNBOOK-V1.0-PATCH — credential_rotation.md v0.9 → v1.0
owner: PA
date: 2026-05-28
status: DONE — 4 patches land；待 PM commit + push timing
ssot_target: srv/docs/runbooks/credential_rotation.md
ssot_aligned_to: srv/docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-27--ops_2_secret_split_adversarial_review.md
---

# P1-OPS-2-RUNBOOK-V1.0-PATCH — Deliverable Report

## §1. Patch 1-4 before/after diff 摘要

### Patch 1 — §4.2.1 Phase 1 backward-compat note

**Range**：runbook line 77-101 → 77-114（新增 14 行 note block）
**改動位置**：§4.2.1 P-1/P-2 標題下、shell block 之前
**核心改動**：
- 新增 quote 框（`> ⚠️ Phase 1 backward-compat exception ...`）說明 restart_all `prepare_runtime_secret_files` `[ ! -f ]` guard 在 Phase 1 期間 seed `live_auth_signing_key.txt` from `ipc_secret.txt`，**不視為違反** urandom 要求
- 明確 echo banner 字串：`>>> OPS-2 SECRET-SPLIT phase 1: seeded live_auth_signing_key.txt from ipc_secret.txt (backward compat; rotate to fresh urandom on next scheduled rotation per §5.2.2)`
- 釘 3 條 invariant：(a) 第一次 90d rotation 必 from urandom 禁再次 seed-from-ipc；(b) Phase 2 cutover 後 missing = fail-closed panic；(c) cross-ref §13 + §10.1.1
- 原 shell block 完整保留（urandom 路徑屬 Phase 2 後正規 deploy 動作）

### Patch 2 — §10.1.1 Phase 1 fallback WARN invariant

**Range**：原 runbook §10.1 末（line 440 後）→ 新增 §10.1.1 sub-section（line 453-470，18 行）
**改動位置**：§10.1 Engine status shell block 之後、§10.2 之前
**核心改動**：
- 新 anchor `#### 10.1.1 Phase 1 fallback WARN invariant（D+0 → Phase 2 cutover D+14 前每日跑）`
- 動機 1 段解釋為何 fallback 在 Phase 1 正常運行下不應該觸發（env 已注入；任一觸發 = Rust live_authorization 走錯 = 2 key 未正確分離）
- 單行 one-liner：`ssh trade-core "grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/engine.log /tmp/openclaw/api.log"`（per `feedback_shell_paste_safety`，無 heredoc / 無多行 for / 無複雜 variable injection）
- AC 表：兩 file 累積 = 0；任一 ≥1 = Phase 2 BLOCK
- cross-ref E1 IMPL §5.4 + §13

### Patch 3 — §10.5 Cross-language HMAC sanity check

**Range**：原 runbook §10.4 末（line 471 後）→ 新增 §10.5 整節（line 496-551，56 行）
**改動位置**：§10.4 Bybit endpoint trust-status 之後、§11 之前
**核心改動**：
- 動機段：雙端 canonical 順序漂移 = HMAC 失配 = Earn / live-auth silent fail（fail-closed `BadSignature` 不具體 cause）
- canonical_payload format 規格表（serialize JSON / sort_keys=True / separators (",", ":") / UTF-8 / HMAC-SHA256 / lowercase hex 64 char）
- Wave D Earn HMAC 採 pipe-delimited（非 JSON）clarification + cross-ref Wave D spec
- Pinned fixture（per E1 IMPL line 13/31/41）：
  - fixture key：`b'test-live-auth-signing-key-do-not-use-in-prod'`
  - fixture payload：`2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo`
  - pinned hex：`1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc`
- Python stdlib 單行 one-liner（無依賴）：`python3 -c "import hmac,hashlib; print(hmac.new(...).hexdigest())"`
- Rust 單行：`ssh trade-core "cd ... && cargo test --release --quiet cross_lang_hmac_fixture_is_byte_identical -- --nocapture"`（複用 E1 已 pin test）
- AC 三向：Rust hex == Python hex == pinned hex；任一不等 = secret split 完整性破壞 = rollback + forensic
- cross-ref TODO `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` + E1 IMPL pinned hex 出處 + spec §8.5 E2 重點 #1

### Patch 4 — §13 Phase 2 Cutover SOP（新章）

**Range**：原 runbook 末（line 495 後）→ 新增 §13 整章（line 582-685，104 行）
**改動位置**：§12 Cross-References 之後（章節編號順向，per 任務 SOP）
**核心改動**：6 sub-sections
- **§13.1 前置（D+14 = 2026-06-10）**：5-gate readiness 表（fallback WARN 0 / ≥1 次 /auth/renew / live_auth_signing_key.txt 完整 / engine PID 穩 / PM 確認 Sprint 4 first Live ≥ 2026-06-10），對應 A3 conditional #4
- **§13.2 Operator 外部監控同步**：新 alert pattern (`live_auth_signing_key_missing` + `AuthError::LiveAuthSigningKeyMissing`) + parallel 14d buffer 保留舊字串 + operator 親簽 checklist；對應 A3 §7
- **§13.3 PR dispatch**：4 文件改動表（live_authorization.rs fallback 刪除 + AuthError::IpcSecretMissing 變體刪除 / main.rs:402 後第二 panic block / live_auth_watcher_tests.rs teardown 改 / live_trust_routes.py:473 reason rename），cross-ref TODO `P1-OPS-2-PHASE-2-CUTOVER`
- **§13.4 Panic verify**：強制 sandbox / cargo test 走 `live_auth_signing_key_missing_panics_when_live`，**禁** production engine 直觸（避 SIGABRT 蕩 live pipeline）
- **§13.5 Rollback**：≤30 min timeline target，4-step one-liner（stop_all / ls -la 驗 / 緊急 seed / git revert + restart_all --rebuild）
- **§13.6 Verify SOP cutover 後 D+15~D+44**：5 invariant 表 + first scheduled rotation due date pin = **2026-09-08**（cutover + 90d，per spec §3.1）+ D+44 PM sign-off archive 路徑

### 附帶更新

- **Header line 3-4**：DRAFT v0.9 → v1.0；版本字串改 `v1.0（A3-aligned，Phase 2 SOP land）`
- **§11 Revision History**：新增 v1.0 row（2026-05-28 / PA / 4-patch 摘要 + A3 SSOT path）
- **§12 Cross-References**：新增 3 條（A3 SSOT / E1 IMPL SSOT / §13 self-link）+ memory `feedback_shell_paste_safety` + TODO 2 條（Phase 2 cutover + Wave D HMAC canonical）+ Phase 2 cutover § anchor + Phase 1 backward-compat note 3-anchor refs
- **End marker**：`END OF RUNBOOK v0.9 DRAFT` → `END OF RUNBOOK v1.0`

### 總計

- 原 v0.9：495 line / 12 章
- 新 v1.0：687 line / 13 章（+192 line / +1 章 / +1 sub-section §10.1.1 / +1 sub-section §10.5）

---

## §2. 對齊 A3 4 conditional items 表

| Patch # | A3 condition # | A3 原話 | Land 章節 | Status |
|---|---|---|---|---|
| 1 | #1 | runbook §4.2.1 vs IMPL §5.3 urandom vs seed 同值 language drift fix — Phase 1 期間 seed-from-ipc 是 backward-compat note | §4.2.1 quote box block | ✅ CLOSED |
| 2 | #3 | D+0 verify SOP 加 `grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/{engine,api}.log = 0` invariant | §10.1.1（新 sub-section）| ✅ CLOSED |
| 3 | A3 §5（cross-lang HMAC fixture verify） | runbook §10.5 補 cross-lang HMAC sanity check + canonical_payload format 說明 | §10.5（新 section）| ✅ CLOSED |
| 4 | #2 | runbook v1.0 補 §13 Phase 2 cutover SOP — 含外部 Grafana 新字串 / 14d soak result / E1 dispatch / panic verify | §13（6 sub-sections）+ §13.2 對應 A3 §7 提示 | ✅ CLOSED |
| — | #4（A3 conditional） | PM confirm Sprint 4 first Live ≥ 2026-06-10 | §13.1 Preconditions 表 row 5 列入 readiness gate | ✅ TRACKED（依賴 PM action，非 runbook 文字可閉 — runbook 已 surface gate） |

**對齊狀態**：A3 條件 4/4 close（#1/#2/#3 完整 land；#4 列為 §13.1 readiness gate 由 PM 在 D+14 前確認）。

---

## §3. Cross-ref 同步：新 §13 / §10.5 anchor 與 §11 §12 互引完整性

- **§11 Revision History v1.0 row**：明列 4 patches + ref A3 SSOT 完整 link
- **§12 Cross-References**：4 條新引用
  1. A3 對抗性核驗 SSOT（v1.0 patch 對齊源）
  2. E1 Phase 1 IMPL SSOT（pinned hex / fallback WARN invariant 出處）
  3. Phase 2 cutover SOP self-link 指 §13
  4. Phase 1 backward-compat note 指 §4.2.1 + §10.1.1 + §10.5
  5. memory `feedback_shell_paste_safety`（新引）
  6. TODO 上游條目 2 條（`P1-OPS-2-PHASE-2-CUTOVER` + `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM`）
- **§4.2.1 quote box** cross-ref to：§13 / §10.1.1 / OPS-2 spec §3.1 / §3.2
- **§10.1.1** cross-ref to：E1 IMPL §5.4 + §13
- **§10.5** cross-ref to：TODO Wave D / E1 IMPL line 出處 / spec §8.5
- **§13.1** cross-ref to：§10.1.1 + E1 IMPL §5.4 + spec §3.1
- **§13.5** cross-ref to：spec §3.3 + §7.2
- **§13.6** cross-ref to：§10.1.1 + §10.5 + §5.2.2 + §4.2.1 backward-compat note

**互引完整性**：13 章節雙向 link 全部對齊；無孤立 anchor / 無漂移 ref。

---

## §4. Out-of-scope 觀察（A3 條件外 risk，標 carry-over）

審 runbook 全文時發現以下 risk，**未自作主張擴範圍**（per 任務 non-negotiable）；列為 P2 carry-over：

### Carry-over #1 — §10.3 Healthcheck SQL routine 未實裝

**現況**：§10.3 line 460 quote：「Healthcheck SQL routine **建議**新增（P2-OPS-2-AUDIT-ENDPOINT follow-up）；目前未實裝以 §8 SQL 替代」。
**Risk 評估**：MEDIUM；目前 §10.3 依賴 operator 跑 `passive_wait_healthcheck.py --check secret_rotation`，若該 routine 不存在會 silent skip → Cross-system verify §10 4 條 verify 變實質 3 條。
**建議**：列 P2 TODO `P2-OPS-2-AUDIT-ENDPOINT` confirm 是否已建立或開新 ticket。**不在本次 v1.0 patch scope**。

### Carry-over #2 — A-1 authorization.json 缺 audit row 規格

**現況**：§2.2 A-1 line 38 寫 emergency revoke 路徑「`POST /api/v1/live/auth/revoke` ≤5s」但 §6.2.4 line 287 沒 audit row INSERT 範例（vs §6.2.1-§6.2.3 三 primary class 都有 step 6 audit row）。
**Risk 評估**：LOW；A-1 revoke 屬 API path，內部應已寫 `learning.live_auth_renewals` 之類 row，但 runbook §9 SOP step 3 操作者 acknowledge cycle 在 A-1 emergency revoke scenario 是否觸發 audit row 寫入無明文 contract。
**建議**：列 P2 TODO 檢視 `/auth/revoke` route 是否寫 audit row；若否補 SOP。**不在本次 v1.0 patch scope**。

### Carry-over #3 — §5.2.3 P-3 Bybit「24h soak 再 revoke old」流程缺 audit row

**現況**：§5.2.3 line 213-214 提到「24h soak：觀察 Bybit retCode error rate，OK 後再 Web UI revoke old」但無 audit row 寫 `old_key_revoked_at` timestamp，無法後續追溯 rotation grace window 是否完整。
**Risk 評估**：LOW；不影響 OPS-2 P-2 scope。
**建議**：列 P2 TODO 為 §5.2.3 補 step 7（second audit row：action='bybit_old_key_revoked'）；本次 v1.0 patch scope 外。

---

## §5. Sign-off

### PA 自核

- ✅ Patch 1-4 全 land；diff 摘要完整
- ✅ A3 4 conditional items 4/4 close（#4 surface in §13.1 readiness gate）
- ✅ Cross-ref 完整；無孤立 anchor
- ✅ Non-negotiable 規約全守：
  - shell 一律單行 one-liner（§10.1.1 + §10.5 + §13.5 全部驗）
  - anchor 風格 `## 13. Phase 2 Cutover SOP` 與 §1-§12 一致
  - §11 + §12 已 update
  - 中文為主（per `feedback_chinese_only_comments`），英文僅留 CLI / hex / fingerprint / variant 名
  - 未擴範圍（3 out-of-scope risk 列 P2 carry-over，不動本次 runbook）
- ✅ 687 line 完成（原 495 line + 192 line = 38.8% 文檔增長；主要在 §13 104 line + §10.5 56 line + §10.1.1 18 line + §4.2.1 note 14 line）

### Next step 建議（PA 個人判斷）

1. **PM 收 deliverable 後 commit + push**：建議 commit message 含 `[skip ci]`（doc-only）；branch 視 PM TODO 流程定。
2. **是否需 E2/TW review**：
   - **E2**：建議 LIGHT review（10-15 min skim）— v1.0 patch 純文檔 + 1 shell one-liner（§10.1.1 grep）+ 2 Python/Rust test invocation pattern（§10.5）；無 code 改動；無 IPC schema 改動；風險 LOW。E2 重點：確認 §10.5 pinned hex 與 E1 IMPL 報告 line 13/31/41 完全一致（已親自比對 ✅，但 E2 二次驗 cheap）。
   - **TW**（technical writing）：**NO**；本 runbook 純 ops SOP，非 user-facing docs；無語言風格 review 必要。
3. **A3 followup**：A3 §3 「Phase 2 panic block trigger MEDIUM RISK」已透過 §13.3 + §13.4 文檔化；A3 可 next round 復查確認本 v1.0 patch 是否滿足條件 close ticket。
4. **D+0 ~ D+14 期間**：operator 每日跑 §10.1.1 grep（已有 one-liner）+ E1 IMPL §5.4 Observable 表並列；若 ≥1 觸發 → §13.1 Preconditions BLOCK，cutover 延期。
5. **D+14 cutover 前 1 週**：PM 提醒 operator 確認外部 Grafana / journald alert rule 已加新字串（§13.2 checklist）。

### Land confirm

- 4 patches：全 land ✅
- v0.9 → v1.0 header + Revision History + Cross-References：全 update ✅
- 687 line 結構順序 §1 → §13 + END marker：✅
- 中文為主、shell paste-safe、無擴範圍：✅

---

**PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--ops_2_runbook_v1_0_patch.md**
