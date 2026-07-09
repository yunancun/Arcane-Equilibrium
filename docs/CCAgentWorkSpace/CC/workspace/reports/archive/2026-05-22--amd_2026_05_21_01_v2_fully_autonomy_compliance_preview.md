# CC 預審 — AMD-2026-05-21-01 v2 (fully autonomy + fail-safe) 合規 preview

**Date**: 2026-05-22 · **Owner**: CC · **Status**: CONDITIONAL APPROVE — 7 條 HC must-fix + 6 條反模式黑名單 + amendment 並存路徑

**SSOT note**: CC role 無 Write 工具，本 report 由 PM 落檔；內容由 CC sub-agent 2026-05-22 audit return 提供。

---

## Verdict 速覽

| 維度 | 結果 |
|---|---|
| 16 根原則 | ✅ 13 PASS / 🟡 2 conditional / 🚫 1 BLOCKER 候選（#3 若 LAL 1/2 不每筆 emit lease） |
| 9 安全不變量（DOC-08 §12） | ✅ 5 PASS / 🟡 3 conditional / 🚫 1 BLOCKER 候選（#2 Lease 必在執行前 acquired） |
| Hard Boundaries（CLAUDE.md §四 5-gate） | ✅ 5/5 PASS — protected scope (b) 永鎖，operator stance 未觸碰 |
| Operator 三條 design 要求（observability / auditability / intervention） | ✅ 3/3 conceptually compliant — 但需 6 條 IMPL hard contract |

**核心結論**：operator stance「fully autonomy + fail-safe 自動觸發」**不等於放棄 protected scope**。CC 立場是 operator insight 是對的，**但「fully autonomy」名稱會被 sub-agent / reviewer 誤讀為「protected 6 條也可 auto」**，PM v2 draft 必須在文字上 hard-disambiguate。

---

## 任務 1 — 16 根原則逐條 walkthrough

| # | 原則 | 狀態 | CC 立場 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ PASS | fail-safe 觸發的 freeze/cancel-all/size-cut 必走同一寫入口，禁設「emergency-only bypass」 |
| 2 | 讀寫分離 | ✅ PASS | toggle state / fail-safe event 落 append-only audit table |
| 3 | AI 輸出 ≠ 命令 | 🚫 **BLOCKER 候選** | v2 第一段必明示「AI proposal → Decision Lease emit → LAL gate → 執行；AI 輸出永遠不直接執行」。每筆 LAL 1/2 auto-approve **仍 emit individual lease** |
| 4 | 策略不繞 Guardian | ✅ PASS — **with hard contract** | fail-safe ⊂ Guardian 治理域；fail-safe 不繞 Guardian |
| 5 | 生存 > 利潤 | ✅ **operator stance 反而強化** | hard-coded fail-safe = 生存先於利潤的 stronger form |
| 6 | 失敗默認收縮 | ✅ PASS | fail-safe 觸發後不可 auto-recover（必 operator click） |
| 7 | 學習 ≠ 改寫 Live | 🟡 CONDITIONAL | v2 明示「LAL eligibility upgrade ≠ Live state mutation」 |
| 8 | 交易可解釋 | ✅ PASS | 每筆 auto-action emit lease_id + auto_approval_metadata + failsafe_trigger_metadata |
| 9 | 災難雙重防線 | ✅ PASS | fail-safe = local stop；exchange-side conditional order 不變 |
| 10 | 認知誠實 | ✅ PASS | v2 必同時寫「protected scope (a)-(f) 不在 autonomy 範圍」 |
| 11 | Agent 最大自主（P0/P1 內）| ✅ **核心對齊** | LAL 1/2 + fail-safe = P0/P1 內最大 autonomy |
| 12 | 持續進化 | ✅ PASS | fail-safe trigger 紀錄本身是 evolution feedback |
| 13 | AI 成本感知 | ✅ PASS | fail-safe 為純規則路徑（無 AI call）cost ≈ 0 |
| 14 | 零外部成本可運行 | ✅ PASS | Slack/email free tier，不影響 trading 路徑 |
| 15 | 多 Agent 協作 | ✅ PASS | fail-safe 是 RiskGovernor 子模組，不是「第六 agent」 |
| 16 | 組合級風險 | ✅ PASS | fail-safe trigger criteria 必含 portfolio-level |

---

## 任務 2 — 9 安全不變量

| # | 不變量 | 狀態 | CC 立場 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | ✅ PASS | M11 continuous replay 強化 |
| 2 | Lease 必在執行前已 acquired | 🚫 **BLOCKER 候選** | v2 明示「fail-safe 觸發 = single lease emit + immediate consume；LAL 1/2 auto-approve 每筆 fill emit individual lease」禁 umbrella lease |
| 3 | 執行回報必落 fills 表 | ✅ PASS | fail-safe trigger 的 cancel-all/freeze 也須落 execution_events + fills |
| 4 | 風控降級 → engine 自動止血 | ✅ **operator stance 直接對齊** | fail-safe 自動觸發 = 不變量 #4 的 stronger form |
| 5 | Auth 過期 → cancel_token shutdown | ✅ PASS | auth 過期是 fail-safe primary trigger |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | ✅ PASS | env-var gate 不被 fully autonomy 觸碰 |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | ✅ PASS | retCode != 0 是 fail-safe trigger source |
| 8 | Reconciler 對賬差異 → 自動降級 | 🟡 CONDITIONAL | v2 重述為「對賬差異 N pps sustained → fail-safe trigger size-cut + freeze new orders + alert」 |
| 9 | Operator 角色 + live_reserved 缺一即拒 | 🟡 **核心衝突點** | v2 明示「Operator role 永遠存在；toggle 切換 + fail-safe config 變更仍需 2FA + Operator role；fully autonomy ≠ Operator-less」 |

---

## 任務 3 — Hard Boundaries（CLAUDE.md §四）

| Gate | 狀態 |
|---|---|
| 1 Python `live_reserved` | ✅ 不動 — protected (b) |
| 2 Python Operator role auth | ✅ 不動 — Operator role gate 仍有意義；toggle / ADR-debt 創建仍需 Operator role |
| 3 `OPENCLAW_ALLOW_MAINNET=1` | ✅ 不動 — protected (b) |
| 4 secret slot 完整 | ✅ 不動 — protected (b) |
| 5 `authorization.json` HMAC + 未過期 + env_allowed | ✅ 不動 — fail-safe 不繞 |
| Signed authorization renew/approve path | ✅ PASS — 不可手寫 authorization.json |
| LiveDemo 不放鬆 authorization/TTL/risk/audit | ✅ PASS — ADR-0004 不變 |
| Mainnet env-var fallback closed | ✅ PASS |
| Bybit retCode fail-closed | ✅ PASS — fail-safe 觸發源之一 |
| `execution_authority` Rust denylist surface | ✅ PASS — **with hardening must-fix**（fail-safe trigger criteria 必 hard-coded in Rust compile-time const）|
| ML/DreamEngine/Executor/Strategist 不可 live-order without Guardian + Lease | ✅ PASS — 不變 |

**結論**：5-gate live boundary **完全 intact**；fully autonomy 只動 LAL 1/2 per-decision approval（opt-in scope），protected scope (b) 5-gate 永鎖。

---

## 任務 4 — Operator 三條 design 要求合規性

| 要求 | 狀態 | IMPL hard contract |
|---|---|---|
| **Observability** | ✅ Conceptually PASS | 6 條：(1) Slack best-effort 非 trading 依賴 (2) Console banner persist ≥ 24h (3) email free tier (4) 三路任一 fail 不阻 trading (5) notification 落 `notification_audit` append-only (6) operator 可關 Slack 但 Console banner 不可關 |
| **Auditability** | ✅ PASS — with ADR-0034 §1+5 cross-ref | v2 明示「fail-safe trigger event 也落 `failsafe_trigger_audit` 與 lease 同 audit chain」 |
| **Intervention** | 🟡 CONDITIONAL | (1) emergency halt button always-on 無 toggle (2) 24h undo scope = config + risk envelope only，NOT fills（per ADR-0034 §5）(3) operator override 不可 override protected scope (e) kill criteria |

---

## 任務 5 — Fail-safe 設計反模式黑名單（6 條，PM v2 draft 必明示禁止）

| # | 反模式 | 為什麼禁 |
|---|---|---|
| **A** | fail-safe 用 runtime config 可被 override | 退化為任何 toggle 可繞過；必 hard-coded in Rust (compile-time const) |
| **B** | fail-safe 只 log 不 trigger 實際 freeze（Pseudo-fail-safe） | log without action = 形同虛設；必有 actuator + trigger hard-tied |
| **C** | fail-safe 觸發後可被 Operator session 一鍵 dismiss 不留 trace | 違反 #8 + 不變量 #1；dismiss 必 emit `failsafe_dismiss_audit` + 2FA |
| **D** | fail-safe trigger threshold 寫在 GUI 可被改 | GUI 對 threshold 是 read-only display，禁所有寫路徑 |
| **E** | fail-safe 自動 recovery（觸發後自動回 NORMAL） | 違反 #6 失敗收縮；recovery 必 operator click |
| **F** | fully autonomy 被讀作 protected scope 也可 auto（命名誤讀） | v2 第一段必 hard-disambiguate；建議改名「bounded fully autonomy within opt-in scope」或「evidence-gated autonomy expansion with hard-coded fail-safe」 |

---

## 任務 6 — CLAUDE.md baseline 動 amendment 影響評估

**CC 建議**：**Amendment + 並存**，不 inline 修改 CLAUDE.md §二。

**理由**：

1. CLAUDE.md §二 16 root principles 是 root canon，14 sub-agent profile 啟動序列都讀；inline 修改 #5 wording → cascade re-read 全部 agent
2. v1 AMD-2026-05-21-01 已 Accepted（per file §Sign-off operator D5 ✅ 2026-05-21），已實質為 priority #5 加 sub-scope；v2 是 enhancement 不是替代
3. amendment 並存的 SSOT 紀律：CLAUDE.md §二 wording 保留「human final review」；AMD v2 §1 明示「priority #5 = protected scope operator click + opt-in scope evidence-gated autonomy + hard-coded fail-safe robustness」三維度並列
4. 避免 baseline drift risk
5. 若 operator 堅持 inline：CC must-fix = commit message 明示 baseline amend + 派 R4/FA/E3/QC/BB/MIT 6 agent 並行 re-read + sign-off + memory log 全 agent profile 加標記

**CC 推薦路徑**：amendment + 並存（Option A）；inline 修改僅在 operator 顯式要求 + 6-agent sign-off 後才接受。

---

## 給 PM v2 draft 的 7 條硬約束（HC-1 ~ HC-7）

| # | 硬約束 | 為什麼 |
|---|---|---|
| **HC-1** | v2 第一段必明示「fully autonomy ≠ protected scope (a)-(f) 可 auto；fully autonomy = opt-in scope (g)-(n) 內 evidence-gated bounded autonomy + hard-coded fail-safe robustness」 | 反模式 F；防 sub-agent 誤讀 |
| **HC-2** | AI ≠ 命令 absolute invariant：每筆 LAL 1/2 auto-approve 仍 emit individual lease + Guardian replay；禁 umbrella lease | 原則 #3 + 不變量 #2 BLOCKER 解除條件 |
| **HC-3** | fail-safe trigger criteria 必 hard-coded in Rust (compile-time const)，不在 runtime config 也不在 GUI toggle | 反模式 A+D |
| **HC-4** | fail-safe trigger 必有 actuator（freeze / cancel-all / size-cut），trigger 與 actuator hard-tied 不可拆分 | 反模式 B |
| **HC-5** | fail-safe 觸發後不可 auto-recover；recovery 必 operator click | 反模式 E + 原則 #6 |
| **HC-6** | Operator role gate 永遠存在；toggle 切換 + fail-safe config 變更 + dismiss 仍需 2FA + Operator role；fully autonomy ≠ Operator-less | 不變量 #9 + Hard Boundary Gate 2 |
| **HC-7** | CLAUDE.md §二 amend 採 amendment + 並存路徑，不 inline 修改 baseline | 任務 6 結論 |

---

## Critical Cross-Reference

- `srv/CLAUDE.md` §二 priority order #5 + §四 hard boundaries
- `srv/docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md` v1（已 Accepted；v2 enhancement 對象）
- `srv/docs/adr/0034-decision-lease-layered-approval-lal.md` §Decision 1+5
- `srv/docs/decisions/DOC-08_OpenClaw_Bybit_Implementation_Bridge_实施桥梁_V1.md` §12（9 safety invariants）
- `srv/docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-21--v58_executability_audit.md`（5.21 audit grounding）

---

**CC AUDIT DONE: CONDITIONAL APPROVE** — PM v2 draft 落地必含 7 HC + 6 反模式 + amendment 並存路徑，CC 即可 re-audit 全 PASS。
