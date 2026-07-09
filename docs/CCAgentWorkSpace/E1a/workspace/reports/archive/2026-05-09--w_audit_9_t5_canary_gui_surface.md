# E1a Sprint N+0 W2 — W-AUDIT-9 T5 Graduated Canary GUI Surface

**作者**：E1a
**日期**：2026-05-09
**對應派工**：Sprint N+0 W2 W-AUDIT-9 T5 — GUI surface for Graduated Canary stage observability + manual promote
**Cross-wave dependency**：T1 (Rust schema) + T2 (V080 PG migration) + T6 (LeaseScope::CanaryStagePromotion) 已 done by E1-A/B/D
**HEAD baseline**：W1 commit `26b7186d`

---

## 1. 任務摘要

實作 AMD-2026-05-09-03 §4.3 GUI surface 配套：在 OpenClaw Control Console **Governance tab** 加 *Graduated Canary Cohort Status* section（不放 Settings tab — 治理 namespace 對齊比歷史 placement 重要）。

GUI 元素：
- 5-stage 視覺合約 ladder（Stage 0..=4）+ scope 文案
- active cohort 列表（latest stage / stage_entered_at_ms / 觀察期進度條 / last_transition_kind / 縮 lease_id）
- Manual Promote 按鈕（Stage 0/1/2 顯示；Stage 3+ 隱藏）— 走 `openTypedConfirmModal` typed-confirm（phrase=`PROMOTE`）+ window.prompt 收 reason
- Stage Metric Registry 折疊表（讀 `governance.canary_stage_metric_registry`）

後端 endpoint：
- `GET  /api/v1/governance/canary/cohorts` — read-only；fail-soft（PG 不可用回空）
- `POST /api/v1/governance/canary/manual_promote` — operator + lease + audit row 5 步流程

---

## 2. 修改清單

### 2.1 新檔
| 檔 | LOC | 註解 |
|---|---:|---|
| `program_code/.../app/governance_canary_routes.py` | 350 | 後端 routes：cohorts GET + manual_promote POST |
| `program_code/.../app/static/canary-tab.js` | 360 | GUI 渲染：5-stage ladder + cohort grid + promote handler |
| `program_code/.../tests/test_governance_canary_routes.py` | 360 | 25 pytest case：payload / SHADOW_BYPASS / lease / DB / handler full flow |
| `program_code/.../tests/static/test_w_audit_9_t5_canary_gui.py` | 245 | 12 pytest case：HTML / JS balance / node check / DOM IDs / a11y / XSS / lease constants |

### 2.2 修改檔
| 檔 | 動作 | LOC delta |
|---|---|---:|
| `program_code/.../app/main.py` | governance_canary_routes import（同時補 governance_extended / governance_promotion 既有缺漏 import） | +5 |
| `program_code/.../app/static/tab-governance.html` | script tag + Canary section + CSS（5-stage ladder / cohort card / progress bar / mobile retrofit） | +245 / -0 |

### 2.3 報告 + memory
- `docs/CCAgentWorkSpace/E1a/workspace/reports/2026-05-09--w_audit_9_t5_canary_gui_surface.md`（本檔）
- `docs/CCAgentWorkSpace/E1a/memory.md` 追加 9 條 lessons

---

## 3. 關鍵 diff（trade-off 點 + 易誤解處）

### 3.1 Tab 選擇：governance > settings
AMD §4.3 給 implementer 自由拍板。選 governance：cohort lineage / Decision Lease / observation gate / promotion semantics 與 SM-01..04 同 namespace；settings tab 4 sub-tab 已塞 engines/system/connection/debug 沒治理空間。

### 3.2 後端用既有 governance_router prefix
governance_extended_routes / governance_promotion_routes pattern 一致：import `governance_router` + decorator attach；main.py 必加 `from . import governance_canary_routes` 觸發 decorator 註冊（順帶補 main.py 既有缺漏的 governance_extended / governance_promotion explicit import）。

### 3.3 LeaseScope 字符串 facade（不擴 enum signature）
T6 IMPL 已加 typed enum + 專用 method，但保留既有 `acquire_lease(scope: &str, ...)` 不動。T5 後端直接呼字符串 `'CanaryStagePromotion'` 對齊 `LeaseScope::as_audit_str()` — 最小調用面，不撞 W-AUDIT-8a Phase A 時序。

### 3.4 SHADOW_BYPASS sentinel 雙層拒
`shadow_mode_provider() == True` → `acquire_lease()` 回 `SHADOW_BYPASS:<intent_id>`（per PA push back #2）。canary_stage_log.decision_lease_id 是 PG `UUID` type；SHADOW_BYPASS 字面值不是合法 UUID。應用層 `_is_shadow_bypass_lease()` 拒 409 + DB layer `uuid.UUID()` 校驗 fail-closed — 雙鎖防 sentinel 進 audit chain。

### 3.5 typed-confirm phrase 'PROMOTE' + window.prompt reason
critical decision（晉升動作）走高摩擦 typed-confirm；reason 收 audit context 走低摩擦 native prompt（對齊 settings tab restart simple-step pattern）。避免每欄位 typed-confirm 疲勞使 operator 簡化 input。

### 3.6 caller try/catch 包 await openTypedConfirmModal
W-AUDIT-7c Round 3 E2 RETURN HIGH-1 lesson 內化：`let proceed; try { proceed = await ...; } catch { ocToast warn; return; } if (!proceed) { ocToast neutral; return; } 業務`。三態完整收口；零 retrofit 成本。

### 3.7 data-* + addEventListener > onclick="fn(...)"
cohort_id 可能含 quote / backslash；inline `onclick="fn('${id}')"` 字面注入會 break parsing。改 `<button data-cohort-id="${ocEsc(id)}" ...>` + JS `btn.addEventListener('click', ev => { ... ev.currentTarget.dataset.cohortId ... })`。

### 3.8 5-stage grid 5-col + mobile wrap 2-col
desktop grid-template-columns 5 等寬；`@media (max-width: 700px)` wrap 2-col（page-scoped 同 SEV-2 #1 retrofit pattern）。Stage 0 = neutral gray；Stage 1-3 = blue active；Stage 4 = red warn（governance 顏色語義對齊）。

---

## 4. 治理對照

### 4.1 §五 invariant 11（PA-9）—— manual_promote NOT NULL constraint 已守
- V080 PG schema CHECK constraint `canary_stage_log_manual_promote_lease_required_chk`
- 後端 route `_is_shadow_bypass_lease()` 拒 SHADOW_BYPASS sentinel
- 後端 `_write_canary_stage_log_manual_promote()` 用 `uuid.UUID()` 校驗
- 三層 fail-closed：sentinel 拒 → UUID 校驗 → PG CHECK
- 25 後端 pytest case 有 4 case 直接覆蓋 SHADOW_BYPASS 路徑

### 4.2 §五 invariant 4 — Stage 1 cohort active + 7d 觀察期
- 觀察期計算：`STAGE_OBSERVATION_MS[1] = 7d`（per AMD §2.2）
- GUI 顯示「已用 X / 剩餘 Y」+ progress bar（aria-valuenow ratio）
- Manual promote 按鈕只對 Stage 0/1/2 顯示；Stage 3 自動 / Stage 4 走 5-gate（後端 400 拒）
- 觀察期未滿不阻 manual promote（per AMD §2.2 manual 路徑為 operator override 設計，operator 拍板優先；自動晉升才查觀察期）

### 4.3 AMD-2026-05-09-03 §4.5 配套
- TTL 60s strict（caller 不可覆寫）✓ —— `_CANARY_PROMOTION_LEASE_TTL_SECONDS = 60.0`
- operator-only path（FastAPI Depends `_get_auth_actor` + `_require_operator_role`）✓
- 不走 per-intent Decision Lease；CanaryStagePromotion 是擴充非替代 ✓
- audit chain：`canary_stage_log.decision_lease_id` 必填 for `manual_promote` ✓

### 4.4 §二 16 原則合規
- 原則 2（讀寫分離）：GUI 顯示 read-only；任何 stage 變更走 IPC + Lease ✓
- 原則 3（AI ≠ 命令）：stage promote 必 operator + typed-confirm + lease + audit ✓
- 原則 6（失敗默認收縮）：rollback 永遠回 Stage 0；本端點不接 to_stage < from_stage（400 拒）✓
- 原則 8（交易可解釋）：每 transition 落 `canary_stage_log` row + lease_id ✓
- 原則 11（Agent 最大自主）：cohort 內 Agent 自主不變；cohort 邊界由 operator 拍 ✓

### 4.5 GUI Style Guide 三原則
- **交易環境優先**：promote button 走 typed-confirm 防誤觸；actor / impact / rollback metadata 全載 ✓
- **可審計**：每 promote action 寫 PG row + GUI toast 顯 stage_log_id；歷史可從 governance_events feed 回查 ✓
- **簡單優於華麗**：純 CSS + addEventListener；無動畫 framework；progress bar 用 div + width 純 CSS ✓

---

## 5. Test 結果

| 範圍 | 結果 | 註 |
|---|---|---|
| `pytest tests/test_governance_canary_routes.py` | **25 passed** | payload / SHADOW_BYPASS / DB / handler full flow / constants |
| `pytest tests/static/test_w_audit_9_t5_canary_gui.py` | **12 passed** | HTML / JS balance / node check / DOM IDs / a11y / XSS / lease constants |
| `pytest tests/test_governance_routes_auth.py` (regression) | **13 passed** | 與 T5 改動 0 重疊 |
| `pytest tests/static/test_w_audit_7c_typed_confirm_modal.py` (regression) | **10 passed** | 確認 W-AUDIT-7c modal pattern 未破 |
| **聯合（4 file）** | **60 passed / 0 failed** | Linux trade-core .venv |

**Mac 結構驗證**：
- HTMLParser tab-governance.html stack residue=0（2 個 mismatched `</meta>` 是 void element 已知 false positive）
- canary-tab.js: brace=53/53 paren=171/171 square=13/13
- canary-tab.js: `node --check` PASS
- governance_canary_routes.py: `python3 -m py_compile` PASS

**Routes 註冊驗證（Linux）**：
- governance_router.routes 32 個（含 `/api/v1/governance/canary/cohorts` + `/api/v1/governance/canary/manual_promote`）

---

## 6. 不確定之處（FA / E2 push back 用）

### 6.1 觀察期未滿 manual promote 是否該攔
本 IMPL：manual promote 在 Stage 0/1/2 任何時點可觸發（不查觀察期）。理由：manual 路徑是 operator override；自動 promote 才查觀察期 SLA。**push back trigger**：若 PA / FA 認為「Stage 1 entry_fills < 10 但 7d 已到」應拒 manual promote，請開 follow-up ticket（會牽 GUI metric live read 取 cohort 真實 entry_fills 對 threshold 比對 — 屬於 W-AUDIT-9 T3 stage-aware provider 範疇，非 T5 GUI 範疇）。

### 6.2 reason 用 native prompt 是否夠 audit-aware
governance critical 寫操作 W-AUDIT-7c lesson 是「native confirm() 禁用」。native prompt 不在 W-AUDIT-7c 禁列（只禁 confirm()）。reason 是 audit 補充上下文非 critical decision phrase。**push back trigger**：若 A3 認為 reason 也應走 typed-confirm-style modal（多行 textarea + character count），可 follow-up retrofit；本 task 接受 settings tab restart pattern 一致（Round 1 風險最低）。

### 6.3 cohort 自選 wizard 不在 T5 範圍
AMD §4.3 提到「operator 從候選 strategy list 拍板 1 strategy + 1 symbol」是 cohort 初始選擇 wizard。本 T5 IMPL 只顯示**已存在** cohort（讀 canary_stage_log latest row）；cohort 初始選擇是 W-AUDIT-9 T3 shadow_mode_provider stage-aware 配套或獨立 follow-up。Stage 0 → Stage 1 manual promote 仍可在 GUI 操作（GOV_HUB lease + audit row 寫入 cohort_id 字面值；UI 端點需 operator 提供 cohort_id 字串 — 本 task 暫由 button data-* 帶；缺 wizard 時新 cohort 創建需 IPC 直發 / SQL seed）。**push back trigger**：若 PM 認為 T5 必含 wizard，請估 +1 sprint week。

### 6.4 GUI 30s polling 未接
AMD §4.3 暗示「升級進度條」live 顯示。本 IMPL 只在 page load + 「刷新」按鈕點擊時 reload；無 setInterval。理由：（1）governance tab 已有 10s 主 polling 觸 governance.js loadGovernance() — Canary section 接此 polling 風險低成本（後續 follow-up）；（2）setInterval iframe race protection 規範（W-AUDIT-7c W2 R4 lesson）必加，當前 task scope 不收。**規律**：first land = read-only manual refresh；polling 屬 W2 follow-up。

---

## 7. Operator 下一步

1. **PM 階段性 sign-off**：本 task done 後 W-AUDIT-9 T5 + 配套 60 pytest PASS；E2 review chain 啟動
2. **E2 review**：governance_canary_routes.py + canary-tab.js + tab-governance.html + 兩 fixture
3. **A3 review**：UX flow / typed-confirm fit / 5-stage 視覺合約適合性 / reason native prompt vs typed-confirm 決策
4. **E4 regression**：cross-platform full test suite + Linux real browser smoke test（manual promote modal 視覺驗證）
5. **PM final sign-off**：60 pytest + Linux runtime register OK + GUI smoke pass

---

## 8. Final commit 規劃

per task spec：「commit + push origin main 自動執行」。

兩 commit 規劃：
1. `e1a-w2: W-AUDIT-9 T5 GUI graduated canary surface + manual promote [skip ci]` —— 新檔 + GUI 改動 + main.py
2. `docs(e1a): W-AUDIT-9 T5 memory + report` —— memory + report final commit（不加 [skip ci]）

multi-session race 守則：staged 只加 5 檔（4 新檔 + 4 修改檔，但 explicit 列檔；不 `git add .`）。

---

E1a IMPLEMENTATION DONE: 待 E2 + A3 + E4 review · report path: `srv/docs/CCAgentWorkSpace/E1a/workspace/reports/2026-05-09--w_audit_9_t5_canary_gui_surface.md`
