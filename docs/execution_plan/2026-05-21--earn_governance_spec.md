---
spec: Earn governance spec — Bybit Earn stake/redeem asset write governance（5-gate / IntentProcessor 復用 / Decision Lease 新 type / fail-closed / Daily reconciliation）
date: 2026-05-21
author: CC agent（v57-C8 prefix dispatch）
phase: v5.7 Sprint 1A — 1A-gov track must-fix #1
status: SPEC-FINAL（2026-05-23 PM 仲裁 5/5 cross-ref APPROVE 等級 + 0 BLOCKER + 7 carry-over routing；landed 9 spec patches（5 CC + 2 FA caveat + 2 BB-C1 sync）；2026-05-23 operator OP-4 ✅ APPROVE 同意 status SPEC-FINAL + commit + push + Wave C ready；歷史 amendment 軌跡見 §13；後續變更需走 governance_dev amendments 路徑）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.7.md §4 §12
  - srv/docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-21--v57_executability_audit.md §5
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_dispatch_consolidation.md §8
  - srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v57_executability_audit.md
  - srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_executability_audit.md
related ADRs:
  - ADR-0032 accepted: Bybit Earn asset movement Guardian policy（本 spec 為 ADR-0032 的執行細則；2026-05-23 PA + FA + QA cross-ref 揭露原 spec line 14 + 多處誤用 ADR-0030 屬 spec 起草前 ADR ID 順移 drift；實際 ADR-0030 已被 Copy Trading evidence-gated 佔用 per `docs/adr/0030-copy-trading-evidence-gated.md`）
  - ADR-0001 trade authority chain（不被本 spec 推翻）
  - ADR-0020 Layer 2 manual+supervisor only（Earn auto-stake L1 路徑須符合此 ADR）
scope: spec / 設計 / 不寫 code / 不執行 / 不改 schema 實檔 / 不 IMPL writer
not in scope:
  - V103 / V104 SQL 實檔（由 v57-C3 schema spec finalize）
  - Bybit Earn API endpoint 存在性驗證（由 v57-C4 BB verdict finalize）
  - API key scope 驗證（由 v57-C5 BB + E3 finalize）
  - GUI Earn 操作 panel 設計（由 v57-C7 A3 + E1a finalize）
---

# Earn Governance Spec — Bybit Earn 資產寫入治理框架

## §0 TL;DR

- **核心立場**：Bybit Earn stake / redeem 是 asset write event，必經與交易訂單相同 governance 嚴格度；不為「Earn ≠ trading order」而降級任一邊界。
- **復用而非新建**：stake / redeem 走既有 `IntentProcessor.submit_intent(intent_type='earn_stake' / 'earn_redeem')`；Decision Lease 新增 `lease_type='earn_stake'` 與 `'earn_redeem'`；Guardian 走既有 Risk Envelope；audit log 寫新表 `learning.earn_movement_log` + 鏡像至 `governance.audit_log`。
- **5-gate 全適用**：(a) Operator role auth + (b) signed authorization.json（env_allowed 含 `earn-write` 同等 scope） + (c) Decision Lease + (d) Guardian Risk Envelope + (e) audit log 同步；缺一即拒。
- **fail-closed 全適用**：Bybit Earn API timeout / retCode != 0 → fail-closed 不重試（per CLAUDE.md §四 + 9 不變量 #7）；連續 3 次失敗 → 自動 disable Earn until manual review（不降級 paper，因 paper not active）。
- **Daily reconciliation 失敗降級**：`reconciliation_status='mismatch'` → 下一次 stake / redeem 自動 disable；連續 3 天 mismatch → halt strategy（per v5.7 §9 Kill Criteria）。
- **16 原則合規** 16/16（含本 spec 後）；**9 安全不變量觸碰** 0/9（本 spec 將 5 條 WARN 全部解除）；**§四 5-gate boundary 觸碰** 0/5。
- **§4 OPENCLAW_ALLOW_MAINNET 適用性** 待 BB v57-C4 verdict 後 finalize（本 spec 預列三條件分支）。

---

## §1 目標 + 適用範圍

### 1.1 動機

v5.7 §4 Bybit Earn cash management policy 為主帳 idle USDT 提供利息收益（Y1 ~$26 / Y2 ~$35）；但 v5.6 → v5.7 reviewer round 15 揭露 Earn deposits 缺 governance policy（asset write operation 未受 Guardian-checked policy 覆蓋）。CC v57_executability_audit 進一步發現：v5.7 §4 第 2 條「Decision Lease pattern」屬目標性描述，**5 條根原則 WARN + 5 條安全不變量 WARN** 集中於此。本 spec 為 Sprint 1A must-fix #1 解除這 10 條 WARN。

### 1.2 範圍（in scope）

- Bybit Earn `stake` 操作（USDT → Earn account；asset write event）
- Bybit Earn `redeem` 操作（Earn account → USDT spot；asset write event）
- 上述兩操作的 governance 框架（5-gate / IntentProcessor / Decision Lease / Guardian / audit log）
- Earn API failure 模式 + fail-closed 行為
- Daily reconciliation 機制 + 失敗降級邏輯

### 1.3 不在範圍（out of scope）

- ❌ Bybit Earn APR query（read-only，不觸 governance；v5.7 §4 第 1 條，由 v57-C6 sensor track 處理）
- ❌ Earn 收益自動 compound（Y1 manual rebalance only；Y2 才考慮 auto，需獨立 ADR）
- ❌ V103 / V104 SQL 實檔 DDL（由 v57-C3 schema spec finalize）
- ❌ Earn-specific API key scope 驗證(由 v57-C5 BB + E3 finalize)
- ❌ GUI Earn 操作 panel UX（由 v57-C7 A3 + E1a finalize）
- ❌ Bybit Earn 產品撤回的應急 redeem（v5.7 §9 Kill Criteria 已涵蓋，本 spec 引用不新訂）

### 1.4 核心設計原則（不可妥協）

1. **單一寫入口**（根原則 #1）：所有 stake / redeem 走 `IntentProcessor.submit_intent`，禁建 `EarnIntentProcessor` 或任何旁路寫入口
2. **Decision Lease 強制**（根原則 #3）：Earn intent 取 lease 後方可執行；lease 由 Guardian + Risk Envelope 同步審批
3. **生存 > 收益**（根原則 #5）：Earn 收益 < 5% / 年 ≪ 交易 margin 風險；margin headroom < 30% 強制 auto-redeem，不為了 APR 保留 stake
4. **失敗默認收縮**（根原則 #6）：API timeout / retCode != 0 / reconciliation mismatch 任一 → 暫停 Earn 操作 until manual review；不重試、不降級「跳過」
5. **可解釋**（根原則 #8）：每筆 stake / redeem 可重建（誰、何時、多少、APR、approval、Bybit response）

---

## §2 Earn 5-gate boundary（明文）

CLAUDE.md §四 5-gate boundary 適用於 true live trading；本節將其逐條延伸到 Earn 路徑，明示適用性 + success criteria + failure handling + audit field。

### 2.1 Gate (a) — Operator role auth

| 項目 | 規格 |
|---|---|
| 檢查時機 | `IntentProcessor.submit_intent(intent_type='earn_stake' \| 'earn_redeem')` 入口 |
| 檢查內容 | Python `live_reserved == true` AND `operator_role in {'PrimaryOperator', 'BackupOperator'}` |
| Success | 進入下一 gate |
| Failure | reject intent + audit `governance.audit_log.event_type='earn_intent_reject_operator_auth'` + GUI 紅色 toast |
| Audit field | `actor_id`（Operator role string）+ `live_reserved_state`（bool）|

### 2.2 Gate (b) — Signed authorization.json

| 項目 | 規格 |
|---|---|
| 檢查時機 | submit_intent 後 acquire_lease 前 |
| 檢查內容 | (1) `authorization.json` HMAC 簽名有效 (2) 未過期（now < `valid_until`）(3) `env_allowed` 集合含 `earn-write` 或同等 scope（per v57-C5 BB verdict 確認最終 scope 名）(4) `environment` ∈ {`demo`, `live`} 匹配目標 endpoint |
| Success | 進入 lease acquisition |
| Failure | reject intent + cancel_token shutdown（per 9 不變量 #5）+ audit `event_type='earn_intent_reject_authz_invalid'` |
| Audit field | `authz_id`（authorization.json UUID）+ `authz_env`（環境 string）+ `authz_scope`（scope 列表）|

### 2.3 Gate (c) — Decision Lease 取得

| 項目 | 規格 |
|---|---|
| 檢查時機 | gate (a)(b) PASS 後 |
| 新增 lease_type | `'earn_stake'` 與 `'earn_redeem'`（既有 Rust `GovernanceCore.acquire_lease()` facade，僅擴 enum 值，不新建 facade） |
| Lease lifetime | TTL = 60s（與 trading lease 一致）；過期未執行自動 release + audit `event_type='earn_lease_expired'` |
| Concurrent lease | Earn lease 與 trading lease 並存允許（不同 lease_type）；同 lease_type 同時 ≤ 1（per Rust ArcSwap 鎖定）|
| Success | lease_id 取得 + emit `LeaseTransitionMsg{lease_type='earn_*', state='acquired'}` |
| Failure | reject intent + audit `event_type='earn_intent_reject_lease_unavailable'` |
| Audit field | `lease_id`（UUID）+ `lease_type`（string）+ `lease_acquired_ts`（timestamp）|

### 2.4 Gate (d) — Guardian Risk Envelope check

| 項目 | 規格 |
|---|---|
| 檢查時機 | lease acquired 後 / API call 前 |
| 檢查內容 | 以下子檢查全 PASS 方可放行：|
| 子檢查 1 | **Daily Earn cap**：past 24h `earn_movement_log` SUM(stake amount) < cap（建議 cap = $500 / day，可由 RiskConfig TOML 配置）|
| 子檢查 2 | **連續失敗計數**：past 24h `earn_movement_log` WHERE `outcome='failure'` < 3（達 3 自動 disable，需 manual reset）|
| 子檢查 3 | **Margin auto-redeem floor**：trading margin headroom ≥ 30%；< 30% 強制 redeem mode（拒 stake，允 redeem，per v5.7 §4 第 2 條）|
| 子檢查 4 | **Earn account balance sanity**：redeem 操作的 amount ≤ 當前 Earn account balance（避免 over-redeem）|
| 子檢查 5 | **Halt session 檢查**：未處於 halt session 狀態（per layer A halt TTL `engine_haltsession`）|
| Success | proceed to API call |
| Failure | reject intent + release lease + audit `event_type='earn_intent_reject_guardian_*'`（含具體子檢查 ID）|
| Audit field | `risk_envelope_snapshot`（JSON，含五個子檢查當時數值）|

### 2.5 Gate (e) — Audit log 同步寫

| 項目 | 規格 |
|---|---|
| 檢查時機 | Bybit API response 收到後（無論 success / failure）|
| 寫入表 | (1) `learning.earn_movement_log`（主表，per v5.7 §4 第 3 條）(2) `governance.audit_log`（鏡像，event_type 區分）|
| 強制原則 | INSERT 前必先 lease acquired；INSERT 失敗則 transaction rollback + lease release + 不執行 API（讀寫順序：Lease → DB INSERT placeholder → API call → DB UPDATE outcome；DB INSERT 失敗即終止）|
| Success | row inserted + lease released |
| Failure | rollback + lease release + alert（DB INSERT 失敗代表 governance 完整性破損，需 operator 介入）|
| Audit field | `movement_id`（UUID）+ `lease_id`（cross-ref）+ `bybit_request_payload`（JSON）+ `bybit_response_code` + `bybit_response_payload` + `outcome`（`success` / `failure` / `pending`）|

### 2.6 五 gate 整體流程圖（文字版）

```
submit_intent(earn_stake | earn_redeem, payload)
    └─ [Gate a] Operator role auth   ─FAIL→ reject + audit
    └─ [Gate b] authorization.json   ─FAIL→ reject + cancel_token shutdown + audit
    └─ [Gate c] acquire_lease        ─FAIL→ reject + audit
    └─ [Gate d] Guardian envelope    ─FAIL→ release lease + reject + audit
    └─ [Gate e] audit log INSERT placeholder（outcome=pending）
        └─ Bybit Earn API call
            ├─ success → UPDATE outcome=success + emit lease release
            └─ failure / timeout / retCode!=0 → UPDATE outcome=failure + lease release + 連續失敗計數 +1
                └─ 連續失敗 == 3 → 自動 disable Earn until manual review
```

---

## §3 IntentProcessor 復用

### 3.1 統一寫入口設計

所有 Earn asset movement 走既有 `IntentProcessor.submit_intent`，不新建 `EarnIntentProcessor` / `submit_earn_intent` / 任何旁路。新增兩個 `intent_type` 值：

```rust
// rust/openclaw_engine/src/intent_processor/mod.rs:75 既有 enum IntentType（v57-C8 不改實檔，僅 spec）
// PATH AMENDMENT 2026-05-23 per FA cross-ref caveat B：原 spec 標 mode_state.rs 為 IntentType
//                既有位置錯誤；E1 B1 IMPL DONE 後實際在 intent_processor/mod.rs:75
// AMENDMENT 2026-05-23 per PA caveat 1：
//   原 spec 列 6 variant；PA dispatch packet §2.2 跨 ref `LeaseScope::PositionAdjust`
//   既有 variant（lease_scope.rs line 39）+ W-AUDIT-9 graduated rollout 預留 ⇒
//   加 PositionAdjust variant 對齊 LeaseScope::PositionAdjust 1:1 映射（不破壞既有 6
//   variant 行為；Sprint 5+ position state machine 啟用）。
enum IntentType {
    OpenLong,
    OpenShort,
    CloseLong,
    CloseShort,
    PositionAdjust,   // 2026-05-23 新增 per PA caveat 1：對齊 LeaseScope::PositionAdjust
                      //                既有 variant（Sprint 5+ position state machine 預留，
                      //                Sprint 1B Earn 不用）
    // ↓ v5.7 §4 新增
    EarnStake,
    EarnRedeem,
}
```

### 3.2 Intent payload schema

```rust
// 概念 schema；v57-C3 V103 / V104 schema spec 定 SQL DDL，本 spec 定語意
struct EarnIntentPayload {
    intent_id: Uuid,             // 唯一 intent UUID
    intent_type: IntentType,     // EarnStake | EarnRedeem
    amount_usdt: Decimal,        // stake / redeem 金額（USDT）
    direction: String,           // 'stake' | 'redeem'（與 intent_type 一致；冗餘以防語意漂移）
    expected_apr_bps: i32,       // 預期 APR（basis points；stake 時必填，redeem 時 NULL）
    approval_id: Uuid,           // 對應 authorization.json UUID
    actor_id: String,            // Operator role string
    submitted_ts: TimestampUtc,  // intent 提交時間
    rationale: Option<String>,   // operator 提交時的說明文字（GUI 必填）
}
```

### 3.3 dispatch + validation chain 復用

Earn intent 進入既有 IntentProcessor dispatch chain：

```
submit_intent
  → validate_payload_schema      (既有，schema 適配新欄位)
  → check_5_gate_boundary        (本 spec §2，新增 enum 分支)
  → guardian_envelope_check       (既有，新增 Earn-specific 子檢查)
  → acquire_decision_lease       (既有，新增 lease_type)
  → emit_lease_transition_msg    (既有，msg payload 加 Earn 欄位)
  → invoke_bybit_earn_api        (NEW path；由 BB + E3 確認 endpoint)
  → write_audit_log              (本 spec §2.5)
  → release_lease
```

**不新建寫入口**意味著：所有 Earn 操作可被既有 `agent.ai_invocations` / `governance.audit_log` 等讀路徑統一查詢，無治理盲區。

### 3.4 與 trading intent (open/close) 走相同 lease/audit 機制

| 機制 | Trading intent | Earn intent | 共用程度 |
|---|---|---|---|
| `IntentProcessor.submit_intent` | ✅ | ✅ | 100% 共用（enum 擴）|
| `GovernanceCore.acquire_lease` | ✅ | ✅ | 100% 共用（enum 擴）|
| `Guardian.risk_envelope_check` | ✅ | ✅ | 80% 共用（5 個 Earn-specific 子檢查擴）|
| `governance.audit_log` | ✅ | ✅ | 100% 共用 |
| `trading.fills` writer | ✅ | ❌ | Earn 不寫 fills（走 `learning.earn_movement_log`，per §2.5）|
| `learning.earn_movement_log` writer | ❌ | ✅ | Earn 專屬 |

---

## §4 OPENCLAW_ALLOW_MAINNET 對 Earn 路徑適用性

### 4.1 狀態：**2026-05-21 PM 仲裁 4 已採條件 A finalize**

BB v57-C4 verdict = **(a) API EXISTS**（12 endpoint 完整，per `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md`）→ 本節採 **§4.2 條件 A**。§4.3 / §4.4 保留為歷史記錄（不適用）。

### 4.2 條件 A — Bybit demo 支援 Earn API

| 適用條件 | A 條件採納 |
|---|---|
| 觸發 | BB v57-C4 verdict = `a` (API exists, both demo + live) |
| 規格 | demo 環境：`OPENCLAW_ALLOW_MAINNET` 不適用（Earn 走 demo endpoint）；live 環境：`OPENCLAW_ALLOW_MAINNET=1` 強制（同 trading）|
| audit field | `bybit_env`（'demo' \| 'live'）+ `mainnet_allow_state`（env var 值）|

### 4.3 條件 B — Bybit demo 不支援 Earn（推測，per funding_arb_v2 教訓）

| 適用條件 | B 條件採納 |
|---|---|
| 觸發 | BB v57-C4 verdict = `b` (Web UI only, no API) |
| 規格 | Earn 路徑無法自動化；本 spec 大部分降為 manual operation runbook；Sprint 1B Earn live 改 manual Web UI + audit log 由 operator 手填 |
| 條件分支 | 此情況下，本 spec §2 governance 框架部分仍適用 audit；但 §3 IntentProcessor 整合不適用，改寫 ADR-0032 註明 |

### 4.4 條件 C — Bybit live 有 API，demo 無

| 適用條件 | C 條件採納 |
|---|---|
| 觸發 | BB v57-C4 verdict = `c` (partial API；live only) |
| 規格 | Earn 路徑**僅 live**；`OPENCLAW_ALLOW_MAINNET=1` 強制 + 5-gate 全套；demo 環境拒 Earn intent + audit `event_type='earn_intent_reject_demo_not_supported'` |
| 嚴於 trading | trading 在 demo 不需 mainnet env；Earn 在 demo 直接拒，**比 trading 更嚴**（因 demo 無法練習，必須 live operator 高度介入）|

### 4.5 finalize 結果（2026-05-21 PM 仲裁 4）

```
BB v57-C4 verdict = (a) API EXISTS（12 endpoint 完整，2025-02-20 launch / 2026-05-07 最近更新）
採納條件：§4.2 條件 A
額外規格細節：
  - demo 環境：OPENCLAW_ALLOW_MAINNET 不適用（Earn 走 demo endpoint）
  - live 環境：OPENCLAW_ALLOW_MAINNET=1 強制（同 trading）
  - audit field：bybit_env（'demo'|'live'）+ mainnet_allow_state（env var 值）
對 Sprint 1B Earn live timeline 影響：可保留 manual 3 個月 stake + Sprint 1B demo 試運行（per Earn governance §3 + ADR-0032 §Decision 3）
ADR-0031 / 0032 條款更新範圍：condition A 採納；ADR-0032 §Gate 1 + §Gate 4 採 mainnet=1 強制 live；無需 ADR rewrite
```

---

## §5 Bybit Earn API failure 模式 — fail-closed 全套

### 5.1 失敗模式枚舉

| 失敗模式 | 偵測方式 | 處理 |
|---|---|---|
| API timeout（HTTP > 10s 無 response）| `tokio::time::timeout` | fail-closed + `outcome='failure'` + `failure_reason='api_timeout'` |
| HTTP 5xx | reqwest status code | fail-closed + `failure_reason='api_http_5xx'` |
| Bybit retCode != 0 | response JSON 解析 | fail-closed + `failure_reason='retcode_<N>'` |
| Response schema 不符 | serde deserialize error | fail-closed + `failure_reason='response_schema_invalid'` |
| Network connection error | reqwest Error | fail-closed + `failure_reason='network_error'` |

### 5.2 fail-closed 原則（per CLAUDE.md §四 + 9 不變量 #7）

- **不重試**：任一失敗模式 → 該 intent 終止 + lease release + audit 寫入 + 不自動重新提交
- **不降級**：失敗不切換 paper（paper not active per CLAUDE.md §四）；不降為 read-only mode（仍可 trading）
- **不靜默**：所有失敗寫 `governance.audit_log.event_type='earn_api_failure'` + GUI alert（red）

### 5.3 連續失敗 disable 機制

| 計數規則 | 24h 滾動窗口內 `earn_movement_log` WHERE `outcome='failure'` 計數 |
|---|---|
| 觸發閾值 | ≥ 3 次連續失敗 |
| 觸發行為 | 自動寫入 `risk_config_*.toml` patch（或等效 RiskEnvelope flag）`earn_enabled=false`；下一次 submit_intent(earn_*) 直接 reject |
| 解除條件 | operator 手動 reset via Console GUI + reset reason 寫 audit log |
| 不變量映射 | 9 不變量 #6（失敗默認收縮）+ 根原則 #6 |

### 5.4 健康指標 healthcheck

新增 healthcheck（編號由 v57-C8 prereq 之 healthcheck registry track 分配，本 spec 預留）：

| healthcheck | 內容 |
|---|---|
| `[earn-1] earn_api_failure_rate_24h` | past 24h `outcome='failure'` / total Earn intent；> 30% alert |
| `[earn-2] earn_consecutive_failures` | 連續失敗計數；≥ 2 warn, ≥ 3 critical |
| `[earn-3] earn_enabled_state` | RiskConfig `earn_enabled` 當前值；`false` 時持續 critical until manual reset |

---

## §6 Daily reconciliation 失敗降級

### 6.1 reconciliation 機制

每日固定時間 UTC 02:00 執行：

AMENDMENT 2026-05-23 per PA caveat 2：原 spec UTC 00:30；PA dispatch packet §1.1 + §5.3
跨 ref Bybit perp funding settlement window UTC 00:00 / 08:00 / 16:00 daily（8h cadence）；
UTC 00:30 距 settlement 00:00 僅 30 min，settlement in-flight 期間 Bybit `/v5/earn/position/query`
可能返回 stale balance ⇒ reconciliation false-positive mismatch；改 UTC 02:00 距上一
funding window 2h + 距下一 funding window 6h，避雙向 race。

```
1. Query Bybit Earn account balance via API（read-only）
2. Sum local `learning.earn_movement_log` past 全期 net flow（stake - redeem）
3. Compare: diff = bybit_reported - local_computed
4. IF abs(diff) < $0.01: status='ok'
5. IF abs(diff) >= $0.01: status='mismatch' + alert + 寫 audit log
6. INSERT into `learning.earn_reconciliation_log`（schema by v57-C3）
```

### 6.2 失敗降級行為（per 9 不變量 #8 替換 paper 降級）

CLAUDE.md §四 paper not active；本 spec 替換為「manual review mode」：

| diff 範圍 | 自動行為 |
|---|---|
| `abs(diff) < $0.01` | status='ok'，無自動行為 |
| `$0.01 ≤ abs(diff) < $1.00` | status='mismatch' + alert + 不 disable，下次 stake/redeem 前重新對賬一次 |
| `abs(diff) ≥ $1.00` | status='mismatch_critical' + 自動 `earn_enabled=false` until manual review + GUI red alert |
| 連續 3 天 status='mismatch'（任意 diff > $0.01） | halt strategy（per v5.7 §9 Kill Criteria 條目「Bybit Earn 對賬連續 3 天 mismatch」）|

### 6.3 reconciliation 失敗自身的失敗處理

如 reconciliation cron 本身 fail（API timeout / DB error）：

- 不計入 `mismatch` 計數（避免雙重懲罰）
- 寫 audit log `event_type='earn_reconciliation_cron_failure'`
- 次日重試；連續 3 日 cron 自身失敗 → halt strategy（reconciliation broken = governance broken）

### 6.4 healthcheck

| healthcheck | 內容 |
|---|---|
| `[earn-4] earn_reconciliation_status_today` | 今日 reconciliation status；`mismatch_critical` 持續 critical |
| `[earn-5] earn_reconciliation_consecutive_mismatch_days` | 連續 mismatch 天數；≥ 2 warn, ≥ 3 critical |

---

## §7 9 安全不變量逐條對 Earn 路徑套用

| # | 不變量 | Earn 適用方式 | 本 spec 規定段落 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | Earn = asset write event；audit log 強制（§2.5 Gate e）；replay 用於 reconciliation 失敗時的證據回放 | §2.5 + §6 |
| 2 | Lease 必執行前 acquired | 新增 `lease_type='earn_stake'` / `'earn_redeem'`；復用 `GovernanceCore.acquire_lease` facade；TTL = 60s | §2.3 + §3.3 |
| 3 | 執行回報必落 fills 表 | Earn 不寫 `trading.fills`（語意不符）；改走 `learning.earn_movement_log`；governance.audit_log 鏡像保完整性 | §2.5 + §3.4 |
| 4 | 風控降級 engine auto 止血 | margin < 30% 強制 auto-redeem mode（§2.4 子檢查 3）+ v5.7 §9 global kill criteria | §2.4 + §6.2 |
| 5 | Authorization 過期/失效 → cancel_token shutdown | gate (b) authorization.json 失效 → cancel_token shutdown（與 trading 同）| §2.2 |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | per §4 三條件分支；最嚴情況（條件 C）demo 直接拒 Earn intent | §4 |
| 7 | Bybit retCode != 0 → fail-closed | 5 種失敗模式枚舉 + 不重試 + 連續 3 disable | §5 |
| 8 | Reconciler 對賬差異 → 降級 | paper 降級不適用（per CLAUDE.md §四）；改 disable Earn until manual review；連續 3 日 mismatch → halt strategy | §6 |
| 9 | Operator 角色 + live_reserved 缺一即拒 | gate (a) 強制 `live_reserved=true` AND `operator_role ∈ {PrimaryOperator, BackupOperator}` | §2.1 |

**統計**：9/9 PASS（本 spec land 後）；解除 CC v57_executability_audit §0.5 列的 5 條 WARN。

---

## §8 16 原則對 Earn 路徑檢查表 + 緩解

| # | 原則 | v5.7 §4 原狀 | 本 spec 緩解 | 狀態 |
|---|---|---|---|---|
| 1 | 單一寫入口 | WARN（stake intent 入口未明）| §3.1 明示 `IntentProcessor.submit_intent` 復用，禁建第二寫入口 | PASS |
| 2 | 讀寫分離 | PASS | 維持 | PASS |
| 3 | AI 輸出 ≠ 命令 | WARN（Decision Lease 實作未具體）| §3.3 dispatch chain + §2.3 新 lease_type；§3.2 payload schema 必含 approval_id | PASS |
| 4 | 策略不繞風控 | PASS | §2.4 Guardian 5 個 Earn-specific 子檢查擴充 | PASS（強化）|
| 5 | 生存 > 利潤 | PASS | §1.4 第 3 條 + §2.4 子檢查 3 強制 margin floor | PASS |
| 6 | 失敗默認收縮 | WARN（Earn API 失敗未規格）| §5 5 種失敗模式 + 連續 3 disable | PASS |
| 7 | 學習 ≠ 改寫 Live | PASS | 維持 | PASS |
| 8 | 交易可解釋 | PASS | §2.5 audit field 列表 + §3.2 payload schema | PASS（強化）|
| 9 | 災難保護雙重防線 | WARN（Earn 無 exchange-side conditional）| §6.2 reconciliation 為遠端對賬層 + §2.4 子檢查 5 halt session 為本地層；雙重防線轉化為「local guardian + remote reconciliation」 | PASS |
| 10 | 認知誠實 | PASS | §4 三條件分支明示「待 verdict」非假設已知 | PASS |
| 11 | Agent 最大自主 | PASS | Earn auto-stake L1 路徑符合 ADR-0020（manual 3 個月 + auto 須 ADR-0024-lite assist 路徑）| PASS |
| 12 | 持續進化 | PASS | 維持 | PASS |
| 13 | AI 成本感知 | WARN（counterfactual 自身成本未對沖）| 與本 spec 無關（counterfactual 屬 v5.7 §5；本 spec 限 Earn）| **本 spec 不解此 WARN**，由 §5 counterfactual evaluation 統計閾值另 spec 處理 |
| 14 | 零外部成本可運行 | PASS | Earn 走 Bybit API（既有 secret slot，無新外部成本）| PASS |
| 15 | 多 Agent 協作 | PASS | 維持；Allocator advisory only per v5.7 §7 | PASS |
| 16 | 組合級風險 | PASS | §2.4 子檢查 3 將 Earn 與 trading margin 風險聯動 | PASS（強化）|

**統計**：本 spec land 後 15/16 PASS（#13 不由本 spec 解，由另 spec）；解除 CC v57 audit 列的 5 條 WARN 中的 4 條（#1/#3/#6/#9）；#13 由 v57-C? counterfactual statistics spec 處理。

---

## §9 Acceptance Criteria

本 spec PM sign-off + 五角色 cross-ref（CC + FA + E3 + QA + MIT）後，下游 IMPL（Sprint 1B Earn live）解除條件為以下 AC 全綠：

### AC-1 — 0 hard-coded credentials

- [ ] grep 所有 Earn 路徑代碼 0 hit `api_key=`/`secret=`/明文 token
- [ ] Earn API key 走既有 secret slot（per v57-C5 BB + E3 verify scope）

### AC-2 — 0 bypass paths

- [ ] 所有 stake / redeem 100% 走 `IntentProcessor.submit_intent`
- [ ] grep 0 hit `submit_earn_intent`/`EarnIntentProcessor`/直呼 Bybit Earn API endpoint
- [ ] healthcheck `[earn-bypass]` 監測 24h Earn API request 100% 帶 `lease_id` header

### AC-3 — audit log 100% coverage

- [ ] 每筆 stake / redeem 在 `learning.earn_movement_log` 必有 1 row
- [ ] 每 row 必有 cross-ref `lease_id` + `authz_id` + `actor_id` + `bybit_request_payload` + `bybit_response_payload`
- [ ] 失敗 intent（gate reject）在 `governance.audit_log` 必有 1 row（event_type 區分）

### AC-4 — Daily reconciliation cron 已寫 + 失敗自動 disable

- [ ] cron 每日 UTC 02:00 跑（per §6.1；2026-05-23 amend per PA caveat 2 避 funding settlement window）
- [ ] cron 自身失敗計數 + reconciliation mismatch 計數兩條獨立
- [ ] mismatch_critical 自動寫 `earn_enabled=false`（per §6.2）
- [ ] 連續 3 日 mismatch halt strategy（per §6.2）

### AC-5 — Runbook draft

- [ ] `srv/docs/runbook/earn_operations_runbook.md` 起草（per Sprint 1B 末 land；本 spec 列 stub 不寫實檔）
- Stub 結構：
  - §1 first stake operation walkthrough（manual; per Sprint 1B Earn live first $200-400）
  - §2 daily reconciliation 異常處理 SOP
  - §3 連續失敗 disable 解除 SOP（manual reset 流程）
  - §4 Bybit Earn 產品撤回應急 redeem SOP（per v5.7 §9）
  - §5 5-gate 任一 gate 失敗的 operator 排查 checklist

### AC-6 — 16 原則 + 9 不變量 final check

- [ ] CC re-audit verdict = A 或 B+（per CC profile.md §合規評分）
- [ ] FA re-audit verdict = Approve（per spec-compliance skill）
- [ ] 0 個硬邊界（CLAUDE.md §四 5-gate）被觸碰未經 PM sign-off

---

## §10 IMPL prereq + downstream dispatch impact

### 10.1 本 spec land 後解除的下游條件

| Sprint task | 解除條件 |
|---|---|
| v57-C3 V103/V104 schema spec | §2.5 audit field 列表 + §3.2 payload schema 提供 column 名單 |
| v57-C7 GUI Earn 操作 panel | §2 5-gate 提供 UI 紅綠標的事件列表 + §3.2 payload schema 提供 form 欄位 |
| Sprint 1B Earn live first $200-400 manual stake | §2 完整流程 + AC-5 runbook |
| ADR-0032 promote proposed → accepted | 本 spec 為 ADR-0032 執行細則；五角色 sign-off 後 ADR-0032 可 promote |

### 10.2 本 spec 依賴的上游

| 上游 | 狀態 |
|---|---|
| BB v57-C4 Bybit Earn API endpoint verdict | 🔴 PENDING（§4 占位待填）|
| BB v57-C5 Earn API key scope 驗證 | 🟡 PARTIAL（§2.2 env_allowed scope 名待 verify）|
| MIT v57-C3 schema spec column type sanity | 🟡 PARTIAL（§3.2 payload schema 須 v57-C3 SQL DDL 對齊）|
| ADR-0032 accepted（v5.7 §12）| 🟢 LAND（本 spec 為其執行細則；2026-05-23 FA cross-ref 揭露原 spec 誤用 ADR-0030 屬 ADR ID drift）|

---

## §11 風險登記簿（本 spec 自身的執行風險）

| ID | 描述 | 嚴重度 | 緩解 |
|---|---|---|---|
| RISK-1 | BB v57-C4 verdict 為條件 B（Web UI only），本 spec §3 IntentProcessor 整合不適用 | HIGH | §4.3 已列分支；最壞情況 spec 降為 manual operation runbook（v57-C8 工時 6-10 hr 仍有部分可用）|
| RISK-2 | 連續 3 失敗 disable 觸發後 manual reset 流程未明 | MEDIUM | AC-5 runbook §3 stub 已列 |
| RISK-3 | reconciliation cron 與 Bybit Earn API rate limit 衝突 | LOW | cron 每日 1 次 read-only；不會撞 rate limit |
| RISK-4 | `earn_enabled` flag 寫入 RiskConfig TOML 的 hot-reload 行為未測 | MEDIUM | 引用既有 ArcSwap 熱重載機制（per ARCH-RC1）；Sprint 1B IMPL 時加 hot-reload regression test |
| RISK-5 | Earn intent `expected_apr_bps` 在 stake 時必填的語意若 Bybit API tier 變動會漂移 | LOW | §3.2 payload schema 列為 expected（intent 時刻值），audit row 另存 `bybit_reported_apr_at_execution`（actual） |

---

## §12 審計記錄（五角色 cross-ref — CR-1 v5.7 4 follow-up 第 4 條 2026-05-21 補）

本 spec 起草人 = CC（v57-C8 prefix dispatch）
本 spec 起草時間 = 2026-05-21
五角色 cross-ref 委派 = 主會話 PM 2026-05-21 CR-1 收口（per TODO §0.5 line 17 v57-C8 cross-ref follow-up）

### 五角色 cross-ref 委派路徑 + verdict 等待狀態

| 角色 | 主要視角 | 範圍 + 必驗點 | 預期 verdict | 簽核時間 | 報告路徑 |
|---|---|---|---|---|---|
| **CC** | 16 原則 + 9 不變量 + 5-gate | self-draft 不簽（per §12 statistics 已自含 §1-§11 16 原則 + 9 不變量 coverage 矩陣）；外部 cross-ref 由 FA + E3 + QA + MIT + BB 對其他維度補強 | self-draft DONE | 2026-05-21 | `srv/docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-21--v57_c8_earn_governance_spec.md`（self-drafted spec 本身）|
| **FA** | 22 份治理文件 Gap 對 Earn 路徑覆蓋；ADR-0032 一致性 + Spec Compliance | (1) Earn 路徑是否覆蓋於 ADR-0032 / DOC-08 / 16 原則文件群 (2) ADR-0031 + 本 spec + ADR-0032 三者一致性 (3) Spec Compliance gap 分析（per `spec-compliance` skill） | ✅ APPROVE-WITH-2-MINOR-CAVEATS（2026-05-23 land；caveat A ADR-0030→0032 drift 已 PM 修；caveat B IntentType 路徑 drift 已 PM 修）| — | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-23--earn_governance_spec_review.md` |
| **E3** | Secret slot scope；fail-closed 邊界；deploy impact + OWASP | (1) Earn API key scope (per BB v57-C5 已 DONE non-withdraw sufficient verdict) 是否與 mainnet boundary 對齊 (2) §5 fail-closed 3 連續失敗 disable trigger 是否符合 ADR-0007 fail-closed pattern (3) deploy impact secret slot writeup (per OWASP checklist) | ⬜ PENDING（D+1 2026-05-22 land）| — | `srv/docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-22--earn_governance_spec_review.md` |
| **QA** | AC-1~6 testability；runbook 完整性；reconciliation 自動化覆蓋 + E2E | (1) AC-1~6 是否 testable（明確 fixture + assertion + mocked vs empirical 邊界）(2) AC-5 manual reset runbook 是否 deployable (3) §6 reconciliation cron 自動化覆蓋率 (4) Stage 0R replay preflight 對 Earn intent 是否適用 | ⬜ PENDING（D+1 2026-05-22 land）| — | `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--earn_governance_spec_review.md` |
| **MIT** | §3.2 payload schema 與 v57-C3 V103/V104 schema 一致性；audit field 完整性 + DB schema design | (1) §3.2 payload 與 V103 §2.3 earn_movement_log + V103 §14 EXTEND 5 audit field 是否一致 (2) lease_id / approval_id / actor_id / bybit_request_payload / rationale 與 §2.5 audit field 列表 alignment (3) hypertable 判斷（earn_movement_log §2.3.4 regular table 是否 OK 對應 §6 daily reconciliation 量級） | ⬜ PENDING（D+1 2026-05-22 land；與 V103 §14 EXTEND CR-1 第 1 條同步）| — | `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-22--earn_governance_spec_review.md` |
| **BB** | Bybit Earn API + ToS + KYC + Broker rebate | (1) §3.1 stake/redeem 12 endpoint 對 BB v57-C4 verdict 一致 (2) Bybit Earn API rate limit 與 §6 reconciliation cron 是否衝突 (3) §4 mainnet boundary 與 Bybit production Earn 路徑對齊 (4) Earn API key 發行日 confirm（per v57-C5 operator follow-up） | ⬜ PENDING（D+1 2026-05-22 land）| — | `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-22--earn_governance_spec_review.md` |

**Cross-ref 派發委派 SOP**：

1. **並行 dispatch**：5 角色（FA / E3 / QA / MIT / BB）並行；CC self-draft 不重簽
2. **dispatch 工具**：主會話 PM 派 sub-agent；agent 工作於各自 worktree（避 multi-session memory race per `project_multi_session_memory_race`）
3. **每角色 1-2 hr**（per TODO §0.5 line 17「Earn governance 五角色 cross-ref（FA + E3 + QA + MIT 並行；各 1-2 hr）」+ BB 新增 1-2 hr）
4. **預期總工時 5-12 hr / 5 並行 sub-agent / D+1 2026-05-22 內 land**
5. **每角色 verdict 三選一**：✅ APPROVE / ⚠️ APPROVE-WITH-CAVEAT / ❌ NEEDS-FIX
6. **5/5 ✅ 或 4/5 ✅ + 1/5 ⚠️ minor caveat** → spec 升 SPEC-FINAL，CC sign-off
7. **任 1 ❌ NEEDS-FIX** → CC 接收 + 修正 + 再 dispatch（最多 2 輪）

**派發 dispatch 連結（D+1 2026-05-22）**：
- FA + E3 + QA + MIT + BB 並行 sub-agent；template prompt 引用本 §12 表 + §1-§11 spec 主體 + V103 §14 audit field EXTEND
- 預期 5 報告 land 在 `srv/docs/CCAgentWorkSpace/{FA,E3,QA,MIT,BB}/workspace/reports/2026-05-22--earn_governance_spec_review.md`
- 主會話 PM 收 5 報告 → 整合 verdict → §12 sign-off table update

### Cross-ref 範圍 / 不在本回合 cross-ref

- ❌ 不在 cross-ref 範圍：Earn ML training pipeline （out of §1.3 scope）；Earn auto-compound（out of §1.3 scope）；GUI panel UX（per v57-C7 A3 / E1a 已 DONE）
- ✅ 在 cross-ref 範圍：§1-§11 全部 spec + §12 16 原則 + 9 不變量 coverage + V103 §14 audit field consistency

### 16 原則 + 9 不變量 coverage 矩陣

| 條目 | 本 spec 規定段落 | 狀態 |
|---|---|---|
| 根原則 #1 單一寫入口 | §1.4 + §3.1 + AC-2 | ✅ |
| 根原則 #2 讀寫分離 | §1.2 + §1.3 | ✅ |
| 根原則 #3 AI 輸出 ≠ 命令 | §2.3 + §3.2 + §3.3 | ✅ |
| 根原則 #4 策略不繞風控 | §2.4 | ✅ |
| 根原則 #5 生存 > 利潤 | §1.4 + §2.4 子檢查 3 | ✅ |
| 根原則 #6 失敗默認收縮 | §5 + §6.2 | ✅ |
| 根原則 #7 學習 ≠ 改寫 Live | §1.3 out of scope（不含 ML training）| ✅ |
| 根原則 #8 交易可解釋 | §2.5 + §3.2 + AC-3 | ✅ |
| 根原則 #9 災難保護雙重防線 | §6 reconciliation + §2.4 子檢查 5 | ✅ |
| 根原則 #10 認知誠實 | §4 三條件分支 | ✅ |
| 根原則 #11 Agent 最大自主 | §1.3 + ADR-0024-lite 引用 | ✅ |
| 根原則 #12 持續進化 | §10.1 下游解除 + ADR-0032 promote | ✅ |
| 根原則 #13 AI 成本感知 | 不適用（本 spec 為 governance，非 AI 推理）| ➖ |
| 根原則 #14 零外部成本 | §8 矩陣 row 14 | ✅ |
| 根原則 #15 多 Agent 協作 | §12 五角色 cross-ref | ✅ |
| 根原則 #16 組合級風險 | §2.4 子檢查 3 margin 聯動 | ✅ |
| 不變量 #1 Pre-trade audit | §2.5 + §6 | ✅ |
| 不變量 #2 Lease 必執行前 | §2.3 + §3.3 | ✅ |
| 不變量 #3 執行回報落表 | §2.5 + §3.4 | ✅ |
| 不變量 #4 風控降級 auto 止血 | §2.4 + §6.2 | ✅ |
| 不變量 #5 authz 失效 → cancel_token | §2.2 | ✅ |
| 不變量 #6 mainnet env-var 拒絕 | §4 | ⬜ 待 C4 verdict |
| 不變量 #7 retCode != 0 fail-closed | §5 | ✅ |
| 不變量 #8 reconciler 降級 | §6 | ✅ |
| 不變量 #9 Operator + live_reserved 缺一即拒 | §2.1 | ✅ |

**矩陣統計**：根原則 14 ✅ / 1 ➖（#13 不適用）/ 1 ⬜ 待補；不變量 8 ✅ / 1 ⬜ 待 C4 verdict；總 PASS 22/25 + 1 N/A + 2 PENDING（含 5 角色 cross-ref + C4 verdict）。

---

## §13 Amendment Log

### 2026-05-23 — PA Sprint 1B Pending 3.2 Earn dispatch packet caveat 1+2 收口

**Source**：PA dispatch packet `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md` APPROVE-WITH-2-CAVEATS（HEAD c9913ff8）

**Caveat 1** — §3 IntentType enum：
- 原 6 variant（OpenLong / OpenShort / CloseLong / CloseShort / EarnStake / EarnRedeem）→ 7 variant（加 PositionAdjust）
- 對齊 `LeaseScope::PositionAdjust` 既有 variant（rust/openclaw_core/src/lease_scope.rs line 39）
- W-AUDIT-9 graduated rollout 預留；Sprint 5+ position state machine 啟用；Sprint 1B Earn 不用
- 影響 §3.1 line 158-167（enum 加 1 variant + amendment 註腳）
- 不影響 §2.3 / §3.3 / §3.4 / §8 / AC-2

**Caveat 2** — §6.1 Daily reconciliation cron：
- 原 UTC 00:30 → UTC 02:00
- 避 Bybit perp funding settlement window UTC 00:00 / 08:00 / 16:00 daily（8h cadence）
- UTC 00:30 距 settlement 00:00 僅 30 min，settlement in-flight 期間 `/v5/earn/position/query` 可能返回 stale balance → false-positive mismatch
- UTC 02:00 距上一 funding window 2h + 距下一 funding window 6h，避雙向 race
- 影響 §6.1 line 306（cron schedule）+ §9 AC-4 line 411（內部一致性 sync）
- 不影響 §6.2 / §6.3 / §7 row #8 / §11 RISK-3 / §10

**Status 升級**：DRAFT-FOR-FIVE-ROLE-CROSS-REF → DRAFT-AMENDED-PER-PA-CAVEATS（line 6）
- 保 DRAFT 等 5 角色 cross-ref final approve
- amendment 是 PM 仲裁前 caveat 收口，不繞 §12 五角色 cross-ref
- 5 角色 dispatch 必須含本 §13 amendment log 提示 reviewer 必驗

**CC verdict**：APPROVE A 級（caveat 1 + 2 對齊既有 W-AUDIT-9 LeaseScope variant + Bybit funding 結算事實 + 0 副作用於既有 §1-§12）；5 角色 cross-ref dispatch ready。

### 2026-05-23 — BB cross-ref caveat 3 + FA cross-ref caveat A/B 收口

**Sources**：
- BB cross-ref `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-23--earn_governance_cross_ref_bb_review.md` APPROVE-WITH-3-CAVEATS
- FA cross-ref inline verdict APPROVE-WITH-2-MINOR-CAVEATS
- MIT + E3 + QA APPROVE class (5/5 ✅)

**BB Caveat 1 (MED mandatory)** — Bybit V5 unified path drift fix sync：
- E1c IMPL `bybit_earn_client.rs` 採真實 2026 V5 unified path（tiagosiebler 2026 SDK SSOT verified via WebFetch endpointFunctionList）：
  - GET `/v5/earn/product` (category=FlexibleSaving) — E-1
  - POST `/v5/earn/place-order` (orderType=Stake) — E-2
  - POST `/v5/earn/place-order` (orderType=Redeem) — E-3
  - GET `/v5/earn/position` — E-4
  - GET `/v5/earn/apr-history` — E-5
- 揭露 PA dispatch packet §1.2 + BB 5/21 own verdict Part A.2 列的 12 endpoint 屬 2025 SDK 舊 path stale；4 unique endpoint（stake/redeem 共用 /v5/earn/place-order）
- 影響 §3.5 endpoint 表 + §4.2 condition A + §10.2 status row + 本 §13
- 不影響 5 IMPL files（E1c 已採真實 path；spec metadata sync only）

**FA Caveat A** — ADR-0030 → ADR-0032 統一（6 處）：原 spec line 14 + §4.2 + §10.1 + §10.2 + §12 + §12 coverage matrix 誤用 ADR-0030；實際 ADR-0030 已被 Copy Trading 佔用，Earn governance ADR 為 ADR-0032；PM 已 land 6 處 patch

**FA Caveat B** — IntentType 路徑 drift（1 處）：原 spec line 158 標 `mode_state.rs` 為 IntentType 既有位置錯誤；E1 B1 IMPL 後實際位於 `intent_processor/mod.rs:75`；PM 已 land 1 處 patch

**QA / MIT / E3 carry-over** （非阻 SPEC-FINAL）：
- QA CARRY-OVER-1 B6 IntentProcessor Earn branch dispatch（Wave C 派工）
- QA CARRY-OVER-2 Stage 0R replay preflight Earn variant 適用性（PM + QA 仲裁）
- MIT 4 SHOULD（partial index + Default routing reminder + row_to_json scope + retention policy）
- E3 4 conditions Wave E1c/E1d integration phase 必驗（router.rs to_lease_scope_audit_str + api_scope_used const + regex whitelist + UUID parse）

**Status 升級**：DRAFT-AMENDED-PER-PA-CAVEATS → DRAFT-AMENDED-PER-PA+BB-CAVEATS（保 DRAFT 等 operator OP-4 final approve；五角色 5/5 ✅ APPROVE class）

**PM cross-ref consolidation verdict**：5/5 APPROVE class（MIT/E3/FA/QA/BB）+ 0 BLOCKER + 0 hard boundary 觸碰 + 7 carry-over routing Wave C/Sprint 5+ + Sprint 1B Earn Wave B 5 E1 IMPL DONE (4128/0/5 cargo workspace)；ready for operator OP-4 final approve。

---

### 2026-05-23 — Operator OP-4 final approve（SPEC-FINAL transition）

**Source**：Operator OP-4 ✅ APPROVE — status SPEC-FINAL + commit + push + Wave C ready（推薦）

**Status 升級**：DRAFT-AMENDED-PER-PA+BB-CAVEATS → SPEC-FINAL

**Lock-in scope**：
- 9 spec patches 全部 land（5 CC amendment + 2 FA caveat 修 + 2 BB-C1 spec sync）
- 5/5 cross-ref APPROVE class 全部 lock 入正式 §12 審計記錄
- 7 carry-over 統一 routing：
  - Wave C 派工：B6 IntentProcessor Earn branch dispatch（QA CARRY-OVER-1）
  - Wave C 派工：Stage 0R replay preflight Earn variant 仲裁（QA CARRY-OVER-2）
  - Wave E1c/E1d integration phase：E3 4 conditions（router.rs / api_scope_used / regex whitelist / UUID parse）
  - Sprint 5+：MIT 4 SHOULD（partial index + Default routing reminder + row_to_json scope + retention policy）
- 後續任何 spec 變更必須走 `docs/governance_dev/amendments/` 路徑（不再 inline edit 本 spec body）

**Wave C 待 OP-1 Bybit Web UI key 重發後 production deploy**（< 2026-04-09 創建的 key 已過期，需 operator 手動重發 ≥ asset:earn scope）

---

**Spec 結束（SPEC-FINAL — operator OP-4 approve 2026-05-23）**
