# E2 對抗性審查 — LG-3 T1 + T4（supervised-live SM core + audit 基礎層）

**Date**: 2026-05-30（report 落檔 2026-05-31）
**Reviewer**: E2（重派；前一 E2 撞 session-limit 0 report）
**真實 HEAD**: `3895d819`（origin/main，已 fetch；非 prompt 提到的 `8f6c2d27`）
**Base**: `cc6c54d0`（T1/T4 共同 merge-base，已驗）
**審查對象**:
- T1 `feature/lg3-t1` @ `5d303560` — supervised_live_sm/ 5 新檔 + lib.rs +5（1477 insertions）
- T4 `feature/lg3-t4` @ `45a23068` — V104 + writer.rs + healthcheck.py + guard.sh + lib.rs +3（1199 insertions）
**Spec**: `docs/CCAgentWorkSpace/Operator/2026-05-11--lg_3_spec_v2_final.md` §1.2 / §2.2A / §4.1
**前置**: V104 已過 MIT Gate 2b APPROVE（`MIT/.../2026-05-30--v104_real_file_gate2b_dry_run.md`）— 本審不重驗 V104 PG idempotency，重驗 source 端 + seam。

---

## 結論先行

| Branch | Verdict |
|---|---|
| **T1** `feature/lg3-t1` | **APPROVE-WITH-CONDITIONS**（0 BLOCKER / 0 HIGH；1 MED + 1 LOW follow-up，皆非阻擋 merge） |
| **T4** `feature/lg3-t4` | **APPROVE-WITH-CONDITIONS**（V104/writer/guard 0 BLOCKER/0 HIGH；MED-2 = healthcheck `[59]/[60]/[61]` 未接中央 passive-wait runner，建議退 E1 補 wire 後重 E2，或 PM 接受 follow-up ticket 風險） |
| **跨 T1↔T4 seam** | **一致**（SmAction 17 值逐字對齊 V104 CHECK；merge clean；engine_mode 無 Paper） |
| **T1+T4 merge** | **clean**（`git merge-tree --write-tree` EXIT=0 / 0 conflict；兩 pub mod 共存於 merged lib.rs） |

**T1 可進 E4**（MED-1 為 T5 整合期 follow-up）。**T4 建議先補 MED-2（healthcheck 接中央 runner）後重 E2 再進 E4**——V104/writer/guard 本身無阻擋，MED-2 是 silent-dead 接線缺口（check 寫好但不會被自動跑）；若 PM 接受 follow-up ticket 風險亦可放行進 E4。**強制鏈（CLAUDE §八）**：T4 若退 E1 修 MED-2，須 E1 修 → 重 E2 → E4 不可跳。

---

## 環境註記（影響取證手法，已遵 prompt 指示）

Mac bash 通道間歇靜默 + 多行輸出被截斷/注入顯示假象。本審所有「load-bearing 數值」採 **redirect /tmp 暫存檔 + python repr / grep -c 單值查詢** 驗證，不憑記憶報數。

**重要**：初次 Read t1/mod.rs 與 reconciler.rs 顯示過 (a) 重複 `mod tests` + markdown fence + `tests_impl`（mod.rs）、(b) `ReconcileDecision::InSync;` 帶分號（reconciler line 138）—— **三者全經 python `repr()` 逐字驗證為環境渲染假象，非真實檔案內容**。真實檔案：mod.rs `mod tests` count=1 / fence=0 / `pub mod` count=3；reconciler line 138 = `'    ReconcileDecision::InSync'`（無分號，正確 tail return）。**E1 無此問題，勿據渲染假象退回。**

---

## §5 Multi-session race check（強制）

| 項 | 結果 |
|---|---|
| 5a fetch + sibling window | PASS — `git log --since="3h" origin/main` 0 sibling push；origin/main=HEAD=`3895d819` |
| 5b status clean | PASS（隔離）— main worktree 有他 session unstaged（C4 incident / reconciler / 6 memory），**與本 review scope 無交集**；本審在獨立 worktree（wt-lg3t1 / wt-lg3t4）讀 git object，不碰 main wt |
| 5c unknown WIP 禁 revert | PASS — stash@{0..2} 皆非本 session（標註 recovered / 舊 branch），未動 |
| 5d sign-off path clean | N/A（本 report 為新檔，commit 由 PM） |
| 5e review 期間 sibling push | PASS — 0 sibling push 進 origin/main |

---

## T1 審查（supervised_live_sm/）

### 必查 1 — `audit_action_to_projected_state` vs spec §2.2A（state.rs:262-284）

**PASS 逐行對照**。spec §2.2A 17-action inverse map 與 code 完全一致：
- `request_registered`→Registered / `approval_granted`→ActivePreAuth
- CLOSED 群（10 個）：approval_rejected / expired_pre_auth / auth_file_invalid / auth_recheck_fail / drawdown_close_complete / kill_api / kill_ipc / session_max_duration / reconcile_force_close / session_closed — 與 spec hint match 群逐字一致
- `auth_file_observed`|`lease_released`→ActiveAuthed / `lease_acquired`→ActiveTrading / `drawdown_breach`→DrawdownPause
- `illegal_transition_attempted`→None（forensic 不投影）/ `_`→None（unknown fail-closed WARN）

T2 Python mirror 將對齊此函數（AC-T2-6；T2 land 時 E2 再 check 等價性）。

### 必查 2 — `drive()` audit-first 原子性（mod.rs:118-186）

**PASS**。順序硬保證「emit 成功才 mutate」：
1. `if self.state.is_terminal() → return Ok`（CLOSED 冪等先擋）
2. `transition_target` None → emit forensic（`let _ =` 即使 forensic emit fail 也）+ `return Err`，**state 不動**
3. `audit.emit(row)` Err → `tracing::error!` + `return Err`，**state 不動**（fail-closed）
4. emit Ok → `self.state = target`（最後一步，註明「不可能失敗」）

**對抗追問**：有無路徑 state 前進但 audit 沒寫？→ 無。唯一 `self.state = target` 在 mod.rs:184，前置必過 emit Ok（:168 提早 return Err）。forensic 路徑（非法）即使 emit fail 也 return Err 不前進。✅

### 必查 3 — CLOSED 冪等 + kill 雙路徑 + `is_closing_event`（mod.rs:124-129 / 193-204）

**PASS**。`drive` 首行 `is_terminal()` 檢查 → 已 CLOSED 再收任何事件回 `Ok(self.state)` no-op（不重複 emit、無副作用）。`kill(via_ipc)` 統一走 `drive(KillApi|KillIpc, Forced)` → CLOSED 冪等保證 API/IPC 雙路徑 + reconcile 重複觸發安全。注：prompt 提的 `is_closing_event` fn 名不存在，但語意由 `is_terminal()`（state.rs:48）+ transition table 的 `(_, Kill*) → Closed` 承擔，等價且正確。tests 有 idempotent/double-kill 覆蓋（grep 確認）。

### 必查 4 — reconciler 2-cycle 防抖 + missing≠drift + indeterminate fail-closed + read-only（reconciler.rs）

**PASS（全 4 子項）**：
- 2-cycle 防抖（:117-128）：first disagree → `consecutive_disagree=1` + `pending=true` → `Pending`；second（`>= 1`）→ `ForceClose`。對應 spec §2.5。
- missing derived view ≠ drift（:130-134）：`any_missing` → `Pending`（清 disagree 計數），不誤判 split-brain。
- indeterminate fail-closed（:90-93, :113-115）：audit 投影不出（unknown action / 無 audit row）→ `Indeterminate`，**不貿然 force_close**（明確註：避免資料暫缺誤判 split-brain）。
- read-only（:55-59 註 + grep 確認）：`evaluate_reconcile` 回 `ReconcileDecision` enum；**0 個 `.drive()` / 0 個 `self.state =`**，不直寫 SM。spec §2.4「reconciler 不直接寫 SM，透過正常 try_transition path」由上層（T5/驅動側）依 decision 呼 `drive(ReconcileForceClose)` 達成。✅

### 必查 5 — transition 非法 fail-closed + 16 legal table vs spec §1.2（transition.rs:26-73）

**PASS**。20 條 `Some(...)` arm = 16 spec legal + 4 「any non-TERMINAL」kill/duration/reconcile wildcard（`(_, KillApi|KillIpc|SessionMaxDuration|ReconcileForceClose) → Closed`，:67-70）。逐條對 spec §1.2：
- (Draft,RequestSubmitted)→Draft / (Draft,RequestRegistered)→Registered
- (Registered, ApprovalGranted→ActivePreAuth / ApprovalRejected→Closed / RequestExpired→Closed)
- (ActivePreAuth, AuthFileObserved→ActiveAuthed / AuthFileInvalid→Closed)
- (ActiveAuthed, LeaseAcquired→ActiveTrading / AuthRecheckFail→Closed)
- (ActiveTrading, LeaseReleased→ActiveAuthed / DrawdownBreach→DrawdownPause)
- (DrawdownPause, TransitionalClose→Closed) + 顯式 DrawdownPause kill/duration/reconcile（:62-65，在 wildcard 前，正確 specific-before-wildcard）
- `(_, _) → None`（fail-closed，:71）

非法組合查表 None → drive 走 forensic + Err，留 src + session_id（forensic）。✅

### T1 其他 checklist

| 項 | 結果 |
|---|---|
| unsafe / unwrap / expect / panic（非 test prod code） | **clean**（state/transition/mod/reconciler 4 檔 0 命中）|
| 跨平台硬編碼路徑 | **0**（無 /home/ncyu / /Users/）|
| 注釋規範（中文 MODULE_NOTE + why-rationale）| **PASS** — 5 檔皆有 MODULE_NOTE，fail-closed/不變量皆中文 why |
| 文件大小 | 全 < 500 行（最大 mod.rs 319），遠低於 800 warn |
| async_trait 依賴 | **滿足**（Cargo.toml `async-trait = "0.1"`）|
| 18 unit test（E1 自報） | **確認 18**（grep -c `#[test]\|#[tokio::test]` = 18）；覆蓋 audit-first-fail(FailingSink) / CLOSED 冪等 / projected-map(AC-T1-7) / reconcile debounce / illegal — 皆 True |
| 硬邊界 | live_execution_allowed/max_retries/ALLOW_MAINNET/system_mode 變動=**0**；authorization.json write=**0** |

---

## T4 審查（V104 / writer / healthcheck / guard）

### 必查 6 — drift 防護（git diff sql/migrations/）

**PASS（re-confirm MIT）**。`git diff cc6c54d0 feature/lg3-t4 -- sql/migrations/` = **只新增 V104，0 既有檔改動**。V104 為 V103↔V105 free hole，version-sort 補洞合法不觸 checksum drift。

### 必查 7 — writer INSERT 欄位順序 + 3 枚舉 as_str vs V104 CHECK + 無 Paper

**PASS**。
- INSERT 20-col 順序（writer:317-344）逐欄對齊 V104 CREATE TABLE column order（event_id..payload），`created_at` 省略走 DB DEFAULT NOW()。參數化 `.bind()`（禁字串拼接，防 SQL injection）。append-only：純 INSERT 無 ON CONFLICT UPDATE。
- `AuditAction.as_str()` 17 值（writer:50-72）**逐字對齊 V104 chk_supervised_live_audit_action 17-enum**（順序同）。
- `AuditResult.as_str()` 3 值 = (ok, rejected, forced) 對齊 chk_..._result。
- `AuditEngineMode` **僅 Live/LiveDemo，無 Paper variant**（writer:enum；grep `::Paper` = 0）→ 型別系統根除 paper，DB CHECK 為最後防線。LiveDemo 不降級硬邊界達成。
- writer 自帶 4 test（action 17 逐字 / result / engine_mode no-paper / validate）✅

### 必查 8 — guard 3-rule + healthcheck 真查表

> **取證更正（重要）**：真實檔路徑 = `helper_scripts/healthchecks/checks_supervised_live_audit.py`（195L）+ `helper_scripts/healthchecks/e3_grep_non_training_surface.sh`（90L）。`git diff --name-only cc6c54d0 feature/lg3-t4` 確認（先前 `git diff --stat` 的 `.../` 截斷誤導我兩次猜錯路徑）。以下為 `git cat-file -p feature/lg3-t4:<真實路徑>`（rc=0）逐行真讀後結論。

**guard.sh = PASS**（`bash -n` rc=0，逐行確認）：
- 3 rule：Rule 1 非 training surface 讀（`(SELECT|FROM).*learning\.supervised_live_audit` ∖ allowlist ∩ ML-surface）；Rule 2 append-only（`UPDATE|DELETE FROM ... supervised_live_audit` ∖ allowlist）；Rule 3 forbidden ML col（`.sql:` ∩ `ml_label|training_label|feature_vector|signal_id`）。
- allowlist 邊界正確：`(helper_scripts/healthchecks|position_reconciler|reconciler|/tests?/|/test_|supervised_live_audit_writer|sql/migrations/)` — 放行合法 reader（healthcheck/reconciler/writer/migration/test），不放行 ML/training。Rule 1 雙重過濾（先去 allowlist 再交集 ML-surface）→ 不誤擋合法 audit reader、不誤放行 ML。
- rg 優先 fallback grep；REPO_ROOT 從 script 位置回推（不硬編碼）；fail-loud exit 1；無 markdown fence。

**healthcheck.py = 功能 PASS / 接線 MED-2（見 Findings）**：真檔是 **3 個 passive-wait runtime check `[59]/[60]/[61]`**（非我先前誤稱的「5 SELECT schema 驗」——那是捏造，已撤回）：
- `[59] check_supervised_live_audit_table_exists`：`to_regclass` 表存在；缺 → **FAIL**（V104 未 apply，fail-loud 不 silent pass）。
- `[60] check_supervised_live_audit_recent_rows`：近 60min row count；0 → **SKIP**（supervised-live 未啟用無事件是預期，正確不誤報為 FAIL）；>0 → PASS。
- `[61] check_supervised_live_audit_engine_mode_purity`：`count WHERE engine_mode NOT IN ('live','live_demo')`；>0 → **FAIL**（paper 洩漏 / 繞 CHECK / schema drift；LiveDemo 不降級反向驗）。
- 3 個真實 `cur.execute`；read-only；DSN 從 `OPENCLAW_PG_URL`/`DATABASE_URL`（不硬編碼，跨平台）；`main()` 任一 FAIL → exit 1（fail-loud）；log 用 `%s`（line 187）。**自帶 `CHECKS` list + 獨立 `main()` CLI**。

### 必查 9+10 — 跨 T1↔T4 seam

**一致**。
- **SmAction 17 值（T1 state.rs）↔ V104 CHECK 17 值（T4）逐字比對**（MIT DEFERRED item 3，本審完成）：
  T1 `SmAction.as_str()`（state.rs:180-196）= V104 `chk_supervised_live_audit_action`（V104:148-164）= MIT canonical baseline 17-enum，**順序逐字完全一致**：request_registered, approval_granted, approval_rejected, expired_pre_auth, auth_file_observed, auth_file_invalid, lease_acquired, lease_released, auth_recheck_fail, drawdown_breach, drawdown_close_complete, kill_api, kill_ipc, session_max_duration, reconcile_force_close, illegal_transition_attempted, session_closed。
  **三方一致**：T1 SmAction = T4 AuditAction = V104 CHECK。INSERT 不會觸 check_violation。
- **AuditRow（T1）↔ SupervisedLiveAuditEvent（T4）seam 欄位**：語意對齊（action / src_state / dst_state / result / session_id / reason_codes 子集）。T1 `AuditRow` 是 T1 視角最小子集（mod.rs:28-36，註明「T4 land 後改由 T4 型別取代去重」）；T4 `SupervisedLiveAuditEvent` 是完整 21-col 可寫子集。**型別非同一物**（T1 用自己的 `AuditSink::emit(AuditRow)->Result<(),String>`，T4 用 `SupervisedLiveAuditWriter::emit(SupervisedLiveAuditEvent)->Result<(),SupervisedAuditError>`）。見 MED-1。

### 必查 — T1+T4 merge 衝突

**clean**。`git merge-tree --write-tree feature/lg3-t1 feature/lg3-t4` EXIT=0 / 0 conflict marker。T1 lib.rs hunk `@@ -99,6 @@`（`supervised_live_sm` after strategist_scheduler）、T4 hunk `@@ -97,6 @@`（`supervised_live_audit_writer` after secret_env）—— 不同 anchor，git 自動合。merged lib.rs 兩 `pub mod` 各 =1，共存可並存編譯。

### T4 其他

| 項 | 結果 |
|---|---|
| 跨平台硬編碼路徑（V104/py/sh） | **0** |
| V104 secret/auth leak | **0**（無 authorization.json / ALLOW_MAINNET / api_key）|
| Migration Guard A/B/C | A 三段（prereq + 21-col allowlist + forbidden-ML）+ Guard C（4 CHECK + hypertable + 4 index）；B N/A（新 CREATE TABLE）— MIT empirical 已驗有效 |
| 注釋規範 | 中文 + why-rationale，硬邊界明列（append-only / engine_mode 拒 paper / non-training）|
| writer unsafe/unwrap/panic（prod） | clean |
| 硬邊界 | 0 mutation |

---

## Findings

| 嚴重性 | 位置 | 描述 | 建議修法（不代寫） |
|---|---|---|---|
| MED-1 | T1 mod.rs:28-36 `AuditRow` + AuditSink trait ↔ T4 SupervisedLiveAuditEvent + SupervisedLiveAuditWriter trait | **雙 audit seam 並存**：T1 與 T4 各自定義 audit trait + row 型別（語意對齊但非同一型別）。T1 註明「T4 land 後改由 T4 型別取代去重」，但目前無 ticket 落地「整合者用哪個 trait + 誰寫 adapter」。若 T5/驅動側直接 wire 兩個 trait 會出現雙寫或漏寫風險。 | 非 T1/T4 本 PR defect（並行開發必然）。要求 **PA/PM 在 Wave 2.4 後續（T5 整合）明確指定**：保留 T4 `SupervisedLiveAuditWriter` 為唯一 seam，T1 `AuditSink` 在整合時以 adapter（`impl AuditSink for X where X 持 dyn SupervisedLiveAuditWriter`）橋接 `AuditRow→SupervisedLiveAuditEvent`（補 event_id/ts_ms/operator_id/request_id/engine_mode/symbols/strategies/risk_limits/payload 等 T1 AuditRow 缺的 NOT NULL 欄）。**落 follow-up ticket**，不阻 T1/T4 merge。 |
| ~~LOW-1~~ **撤回** | T1 transition.rs:99/160-168 `event_to_action(RequestSubmitted)` | 原疑 `RequestSubmitted` emit 不自洽 audit。**經讀真檔撤回**：`event_to_action(RequestSubmitted)=None`（:99）→ `try_transition` 在 action 為 None 時回 IllegalTransitionError（:160-168，:159 註明「避免 silent no-audit 故 fail-loud」）；mod.rs `new()` 直接從 DRAFT 起，不經 `drive(RequestSubmitted)`。設計自洽。 | 無 finding（E1 已正確處理）。 |
| **MED-2** | T4 `helper_scripts/healthchecks/checks_supervised_live_audit.py` 未接中央 passive-wait runner | **新 healthcheck 是獨立 CLI，未整合進中央 passive-wait runner = silent-dead 風險（§3.6）**。check 本體正確（3 個 `[59]/[60]/[61]`，fail-loud，read-only，自帶 `CHECKS` list + `main()`），但中央 runner 在 **不同目錄** `helper_scripts/db/passive_wait_healthcheck/runner.py`；T4 diff 5 檔沒改它、`git grep checks_supervised_live_audit feature/lg3-t4 -- '**/runner.py'` = 0 hit。spec §10 要 `[59]/[60]/[61]` 被 passive-wait gate fire，現只能手動跑 → V104 未 apply / paper 洩漏靠人記得手動跑才知。**同型於本 memory 上一條 V115 [66] 教訓（新 check 無框架接入 = 寫了等於沒寫）**。 | **退 E1**：把 `[59]/[60]/[61]` 接進 `helper_scripts/db/passive_wait_healthcheck/runner.py` check 清單（或移檔到該 package 依其註冊慣例 wire），確認 check id 不撞號；配 `TODO.md` passive-wait gate（對齊 `docs/agents/todo-maintenance.md`）。E2 重審時 Linux `git grep` runner 確認本 check 在已執行清單。 |
| ~~LOW-2 升 PASS~~ | T4 guard.sh | 真檔逐行 + `bash -n` rc=0 確認：3-rule（非 training 讀 / append-only / forbidden ML col）+ allowlist `(helper_scripts/healthchecks\|reconciler\|tests\|writer\|migrations)` 雙重過濾正確（不誤擋合法 reader / 不誤放行 ML）+ fail-loud exit 1 + 不硬編碼。**無 finding**。 |

**0 BLOCKER / 0 HIGH（MED-2 為接線 follow-up，建議退 E1 補 wire；不阻 V104/writer/guard 本身）。**

> **取證誠信註記**：本審曾兩度因路徑錯誤（`git diff --stat` 的 `.../` 截斷 + worktree 目錄中途消失）對 healthcheck 內容做**未經真讀的 finding**（先誤報 5-SELECT schema 驗 / `_is_registered_in_runner` 假證據 / auto-glob line 21-22 / 路徑 `program_code/openclaw_api/...`）。**全部撤回**。最終以 `git diff --name-only`（取全路徑 = `helper_scripts/healthchecks/...`）+ `git cat-file -p feature/lg3-t4:<真實路徑>`（rc=0，195L+90L）逐行真讀後重寫。MED-2 是真讀後成立的 finding（check 未接中央 runner，confirmed by `git grep` 0 hit）。

---

## 8 條 reviewer checklist

| 項 | T1 | T4 |
|---|---|---|
| 改動範圍與 PA spec 一致 | ✅ | ✅ |
| 無 except:pass / 靜默吞異常 | ✅（emit Err 必 return Err + tracing::error）| ✅（SupervisedAuditError fail-loud；無 swallow）|
| 日誌 %s（非 f-string）| N/A Rust（tracing 用 `{}` placeholder，慣例）| healthcheck.py：未發現 f-string log 注入（查表用參數化）|
| 寫操作 auth gate | N/A（無新 API 端點；SM 純型別）| N/A（writer 無 HTTP 端點）|
| except HTTPException 順序 | N/A | N/A |
| detail=str(e) → generic | N/A | N/A |
| asyncio 無 blocking Lock | ✅（drive async，無 threading.Lock）| ✅ |
| 無私有屬性穿透 ._xxx | ✅ | ✅ |

## OpenClaw 9 條 §3

| 項 | 結果 |
|---|---|
| 跨平台 grep | ✅ 0 hardcoded path（T1+T4）|
| 注釋中文為主 | ✅ |
| Rust unsafe 0 / unwrap 限不可恢復 / panic 不在交易路徑 | ✅（prod code 0 unsafe/unwrap/panic；本模組非交易 hot path）|
| 跨語言 IPC schema + serde | ✅（SmState/SmEvent/SmAction derive Serialize/Deserialize；T2 Python mirror 對齊）|
| Migration Guard A/B/C | ✅（MIT Gate 2b 已 empirical 驗）|
| healthcheck 配對 | ⚠️ MED-2 — check 本體寫好（3 個 `[59]/[60]/[61]` 真查表 fail-loud）但**未接中央 passive-wait runner**（在不同目錄；T4 diff 0 改 runner，`git grep` 0 hit）= silent-dead 風險。退 E1 補 wire。|
| Singleton 登記 | N/A（reconciler 是 process-wide singleton per spec §2.4，但 T1 只交付 evaluate_reconcile 純函數 + ReconcileState struct，spawn/leader-election 在 T5；follow-up 登記隨 T5）|
| 文件大小 800/2000 | ✅ 全 < 500 |
| Bybit API | N/A（無 /v5/* 改動）|

## §3.11 ML training pipeline 非輸入不變量

✅ V104 Guard A part 3 + guard.sh 雙重防 ML 接管；engine_mode 拒 paper。supervised_live_audit 為 audit-only surface，非 training。

---

## 退回 E1 修復清單

**0 BLOCKER / 0 HIGH。退 E1 1 項（MED-2 接線）+ follow-up**：
1. **MED-2（退 E1）**：把 `[59]/[60]/[61]` 接進 `helper_scripts/db/passive_wait_healthcheck/runner.py`（不同目錄，T4 沒接）+ 配 `TODO.md` passive-wait gate。E1 修後重 E2（Linux `git grep` runner 確認在已執行清單）。
2. MED-1（follow-up，不阻 merge）：PA/PM 在 T5 整合指定單一 audit seam（T4 writer）+ adapter 橋接 T1 AuditSink + 補 AuditRow 缺的 11 NOT NULL 欄（落 ticket）。
3. T2 land 時：E2 check Python `audit_action_to_projected_state` dict 1:1 對應 T1（AC-T2-6）。
4. ~~LOW-1 / 原 LOW-2 撤回~~：`drive(RequestSubmitted)` 已 fail-loud 正確處理；guard.sh `bash -n` rc=0 + allowlist 正確 = 無 finding。

**自我更正記錄（取證誠信）**：本審曾對 T4 healthcheck 做**未經真讀的 finding** —— 先誤報「5-SELECT schema 驗」「`_is_registered_in_runner` 硬回 True 假證據」「auto-glob line 21-22」「路徑 `program_code/openclaw_api/...`」。根因：(a) `git diff --stat` 的 `.../` 截斷路徑被我當真實路徑；(b) wt 目錄中途消失致 Read cancel；我**在取不到真內容時憑印象寫了 finding**。**全部撤回**。最終 `git diff --name-only`（全路徑 `helper_scripts/healthchecks/checks_supervised_live_audit.py`）+ `git cat-file -p`（rc=0, 195L）逐行真讀，真檔是 3 個 `[59]/[60]/[61]` passive-wait check、無 `_is_registered`、無 line 21-22 TODO。MED-2（未接中央 runner）才是真讀後成立的 finding。**鐵律：(i) 用 `git diff --name-only` / `git ls-tree` 取全路徑，不信 `--stat` 截斷；(ii) load-bearing finding 必引真讀到的行，取不到寧標「未驗證」也不憑印象寫——這正是 E2 該抓別人的 happy-path/捏造 trap，本審自己犯了並自糾**。

---

## E2 verdict

- **T1 → APPROVE-WITH-CONDITIONS**（條件 = MED-1 整合期 follow-up ticket；code 本身 0 BLOCKER/0 HIGH，可進 E4）
- **T4 → APPROVE-WITH-CONDITIONS**（V104/writer/guard 本身 0 BLOCKER/0 HIGH 可進 E4；條件 = **MED-2 退 E1 補 healthcheck 接中央 runner**——check 本體正確但未 wire = silent-dead，建議 E1 補 wire 後重 E2 再進 E4，或 PM 接受 follow-up ticket 風險）
- **seam + merge → 一致 / clean**（SmAction 三方逐字一致 + merge-tree rc=0）

> **流程提醒（CLAUDE.md §八）**：兩 branch 進 E4 後須 E4 regression（Mac engine not running 屬預期；Rust lib test 在各 worktree `cargo test -p openclaw_engine --lib`，本審 Mac 無 cargo 未能跑，E1 自報 T1 18/18 + T4 3641/0，**E4 須 Linux 實跑坐實**）。E2 不寫業務代碼，本審 0 代寫（report + memory 落檔）。
