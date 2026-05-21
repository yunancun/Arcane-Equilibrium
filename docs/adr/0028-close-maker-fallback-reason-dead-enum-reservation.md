# ADR 0028: V094 close_maker_fallback_reason Dead Enum Variants — Safety Path Reservation

Date: 2026-05-21
Status: **Accepted-pending-commit**
Operator Sign-off: 2026-05-21（主會話 PM dispatch；本 ADR 為 FA 2026-05-20 P2-ENTRY-CLOSE-MAKER 分析 SPEC-1 結案文檔）
Related: V094 schema (`sql/migrations/V094__fills_close_maker_audit.sql`) / `rust/openclaw_engine/src/strategies/maker_rejection.rs:115-126` / 2026-05-20 FA P2-ENTRY-CLOSE-MAKER analysis report / ADR-0023 (SourceAvailability — enum governance baseline)

## Context

### 起源

2026-05-20 FA 對 EDGE-P2-3 Phase 1b close-maker-first observation 14d freeze 期數據做 SPEC 層審計，發現 V094 schema `close_maker_fallback_reason` enum 在 PG `trading.fills` 觀察期樣本中分佈嚴重偏斜：

- `timeout_taker` — 14d observation 期 100% 的非空 `close_maker_fallback_reason` rows
- 其他 9 個 variants — PG 0 rows

FA SPEC-1 點名其中 3 個 variants 為「dead by observation」且建議 PA 出 ADR 解決治理問題：

1. `FastEscalateSafetyUpgrade` / `fast_escalate_safety_upgrade`
2. `NotAttemptedSafetyPath` / `not_attempted_safety_path`
3. `EngineShutdownSafety` / `engine_shutdown_safety`

### 真實 enum 定義位置

`rust/openclaw_engine/src/strategies/maker_rejection.rs:115-126`：

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloseMakerFallbackReason {
    TimeoutTaker,
    PostOnlyReject,
    CancelGraceExpired,
    AckLost,
    RateLimitPauseGlobal,
    RateLimitBackoffPerSymbol,
    FastEscalateSafetyUpgrade,
    NotAttemptedSafetyPath,
    EngineShutdownSafety,
    FallbackToTakerMandatory,
}
```

V094 SQL CHECK constraint（`V094__fills_close_maker_audit.sql:144-153`）一一對應同 10 個字串標籤；schema lock 已就位。

### emit 路徑驗證

`close_maker_fallback_decision()`（`maker_rejection.rs:221-258`）為純決策狀態機，每個 `CloseMakerFallbackEvent` 變體都映射到唯一 `CloseMakerFallbackReason`；3 個被點名的 dead variants 對應如下 emit 路徑（**live code path 而非 dead code**）：

| Reason | Emit path | Trigger 條件 |
|---|---|---|
| `FastEscalateSafetyUpgrade` | `CloseMakerFallbackEvent::FastEscalateSafetyUpgrade → CloseMakerFallbackDecision::new(FastEscalateSafetyUpgrade, false, None)` | Engine safety upgrade fast-escalate 路徑觸發時 close-maker 取消轉 taker；屬 ops emergency 路徑 |
| `NotAttemptedSafetyPath` | `requires_market_fallback()` invariant 中唯一回 `false` 的 variant（line 149）；表示「未嘗試 maker，但也不應 fallback 到 taker market」的特殊安全分支 | Safety subsystem 顯式禁止後續 market fallback 的 reservation slot；當前狀態機未連線觸發點 |
| `EngineShutdownSafety` | `CloseMakerFallbackEvent::EngineShutdown → CloseMakerFallbackDecision::new(EngineShutdownSafety, false, None)` | Engine shutdown 時 close-maker 行為標記；shutdown 流程目前未 emit 此事件到 audit 路徑 |

### 為什麼 14d 樣本 0 rows 是預期 not bug

- **FastEscalateSafetyUpgrade**：fast-escalate 是 ops-driven safety upgrade（如 P0/P1 全域風控降級），14d 期間 demo runtime 無觸發；屬「**期望罕見**」事件，非「沒接線」。
- **NotAttemptedSafetyPath**：唯一 `requires_market_fallback() == false` variant，是 safety contract 反向 reservation——若未來某 safety subsystem 需要在 close-maker reject 後**不**走 market fallback（如 panic-halt 期僅取消），此 variant 已留 schema slot；目前無 emit caller 屬**意圖性 unused**。
- **EngineShutdownSafety**：engine shutdown 流程當前在更上層直接 cancel pending close orders（非透過 close-maker fallback 狀態機），所以 audit 表沒收到此 reason；emit 路徑保留以備未來 shutdown 流程改走 audit-first 路徑時使用。

三個 variants 共同特徵：**safety surface reservation**；屬「**罕見/未觸發但 schema 必須有預留**」的 audit slot。

### 為什麼不能簡單 sunset

1. **enum sunset 是 V094 schema 的 breaking change** — V094 CHECK constraint 把 10 值 enum 硬編碼進 SQL（`V094__fills_close_maker_audit.sql:144-153`）；移除任何 variant 需要新 migration 改 CHECK + Rust enum 同步刪 + 所有 emit 路徑同步刪；非小改動。
2. **safety reservation 的價值在於「empty 是預期狀態」** — 如果 14d 沒觸發 `EngineShutdownSafety` 就刪它，下次真的需要 engine shutdown audit trail 時要重新走整套 schema migration + Rust enum + emit wiring；ADR-0023 已建立「enum 變更必經 ADR」治理紀律，本 ADR 提前 lock dead-by-design 區別。
3. **observation 樣本量不足以做 statistical sunset 判斷** — 14d 在 demo runtime 期；fast-escalate / shutdown / not-attempted 三條都需要 ops-driven 罕見事件觸發；14d 看不到不等於「永遠看不到」。樣本量門檻應該以「事件 frequency 推估」而非「observation 期長度」決定。

### 與其他 6 個非 TimeoutTaker variants 的區別

FA SPEC-1 只點名 3 個 dead variants，但 14d 期間其實 9 個 non-`TimeoutTaker` variants 都是 0 rows。為什麼本 ADR 不一併處理其他 6 個？

| Variant | 14d 0 rows | 本 ADR 處理嗎 | 為什麼 |
|---|---|---|---|
| `PostOnlyReject` | ✅ | ❌ 不處理 | 常規 PostOnly reject 路徑；14d 0 rows 屬於 close-maker-first 行為未被觸發到 PostOnly reject 區段（如 spread 持續寬鬆），不是 safety reservation 性質；需獨立 SPEC 觀察期 |
| `CancelGraceExpired` | ✅ | ❌ 不處理 | 同 PostOnlyReject — 屬常規 race path 而非 ops safety reservation |
| `AckLost` | ✅ | ❌ 不處理 | 常規 unknown-reject 兜底；需獨立觀察 |
| `RateLimitPauseGlobal` | ✅ | ❌ 不處理 | rate-limit 觸發路徑；demo runtime 流量 < limit，14d 0 rows 預期但非「safety reservation」性質 |
| `RateLimitBackoffPerSymbol` | ✅ | ❌ 不處理 | 同上 |
| `FallbackToTakerMandatory` | ✅ | ❌ 不處理 | strategy-decided mandatory fallback；14d 0 rows = 無策略採用此路徑，需 strategy 接線 audit |
| `FastEscalateSafetyUpgrade` | ✅ | ✅ 本 ADR | safety reservation — 等 ops emergency |
| `NotAttemptedSafetyPath` | ✅ | ✅ 本 ADR | safety reservation — `requires_market_fallback() == false` 的反向 invariant slot |
| `EngineShutdownSafety` | ✅ | ✅ 本 ADR | safety reservation — engine shutdown audit slot |

**核心區別**：本 ADR 處理的 3 個是「**design-time intentional reservation**」（safety surface 需要的 audit slot），其他 6 個是「**runtime under-observation**」（普通 path 在 14d 期未觸發，但屬常規流量分佈）。前者不需要 sunset 評估；後者需要每 90d 累積樣本後獨立評估。

## Decision

**保留 V094 schema 全部 10 個 `close_maker_fallback_reason` enum 值，不 sunset 任何 variant；本 ADR 為 3 個 safety-reservation dead-by-design variants 做正式紀錄**：

1. `fast_escalate_safety_upgrade`
2. `not_attempted_safety_path`
3. `engine_shutdown_safety`

對齊 ADR-0023 enum governance baseline：未來任何 sunset / rename 必須開新 ADR 替換本 ADR。

### 配套 dashboard / healthcheck 治理規則

1. **Dashboard 與 healthcheck 對 3 個 safety-reservation variants 不可觸發 alert** — 0 rows 是預期。明確區分以下兩類：
   - **Dead by design**（本 ADR 列 3 個）— 不告警；展示時若需要應顯示「reserved — emit path live but trigger expected rare」
   - **Missing data quality issue**（如 V094 寫盤 bug 導致 `TimeoutTaker` 也 0 rows）— 必須告警；healthcheck 對 `close_maker_attempt = TRUE` row 計數降低做存活性監測，而非對 specific reason 0 rows 做監測

2. **Analytics / reporting 必須區分「dead by design」vs「missing data」** — 例如 Phase 1b candidate selection report 對 reason 分佈做 breakdown 時，本 ADR 列 3 個必須在 footnote / legend 顯式標 `[reserved — expected sparse]`，避免下游讀者誤以為 audit 路徑斷線。

3. **Code path liveness 必須持續驗證** — `close_maker_fallback_decision()` 純決策函數的 unit test 必須覆蓋全 10 個 event → reason 映射；E2 review 對 maker_rejection.rs 改動須驗 unit test 覆蓋率不退化。本 ADR 不增加新 test 要求，但釘住現有覆蓋為 governance baseline。

### 未來重新檢視 cadence

**90d 累積樣本後做一次 review**（建議 calendar trigger：2026-08-21）。Review 範圍：

- **`EngineShutdownSafety`**：若 90d demo + live_demo 累積樣本仍 0 rows——可接受持續 reserved；engine shutdown 流程改走 audit-first 路徑屬主動產品決策，非樣本不足驅動的 sunset
- **`FastEscalateSafetyUpgrade`**：若 90d 期間有 ≥1 次 fast-escalate ops 事件但仍 0 rows——需走 RCA 驗證 emit 路徑接線是否退化（屬「missing data」非「dead by design」）；若無 fast-escalate 事件則 reservation 持續
- **`NotAttemptedSafetyPath`**：因 invariant 性質（唯一 `requires_market_fallback() == false`），90d 0 rows 預期；review 重點不在數量而在「是否有 safety subsystem 提出觸發訴求」——若無訴求則持續 reservation；若有訴求則該 subsystem 開新 ADR 接線

90d review 結果三種可能 verdict：
- **Hold reservation**（最可能）— 不修改本 ADR；下次 review +90d
- **Promote to active**（如 fast-escalate 開始 emit）— 不修改本 ADR；只更新 dashboard 規則去除「reserved」標籤
- **Sunset proposal**（需 ops 提出明確「safety path 移除」決策）— 開新 ADR 替換本 ADR + V094 schema migration + Rust enum 同步刪

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **直接 sunset 3 個 dead-by-observation variants** | (a) breaking V094 CHECK constraint 需新 migration；(b) safety reservation 性質 — 移除後未來真的需要 fast-escalate / shutdown audit 時要重做整套 schema + Rust + emit wiring；(c) 14d 樣本量不足以做 statistical sunset 判斷（需 frequency 推估而非 duration） |
| **Sunset 全部 9 個非 `TimeoutTaker` variants** | 同上問題 + 額外 6 個 variants 屬「runtime under-observation」非「dead by design」，需各自獨立評估；單一 ADR 處理 9 個是過度範圍 |
| **不出 ADR，僅在 maker_rejection.rs 加 doc-comment 解釋** | (a) doc-comment 不是治理 artifact，無 cross-link 到 V094 schema + dashboard governance；(b) ADR-0023 已建立「enum 變更必經 ADR」紀律——dead-by-design 區別判定屬於同類治理判斷，需 ADR 等級紀錄；(c) FA SPEC-1 明確要求 PA 出 ADR |
| **把 3 個 variants 標 deprecated 但保留 enum** | enum 沒有 deprecation 中間態（要嘛在 CHECK constraint 內、要嘛不在）；deprecated 標籤無 enforcement，會漂移成「半 sunset」灰色狀態 |

## Consequences

### Positive

- **safety surface reservation 受治理保護** — 未來 ops 需要 fast-escalate / shutdown audit 時 schema slot 已就位，不需要重做 V094 migration
- **dashboard / healthcheck 不會誤告警** — 本 ADR 明確區分「dead by design」vs「missing data quality issue」，alert 規則對齊正確
- **Analytics 區分** — Phase 1b candidate selection report 與下游 ML training 不會誤把 0 rows 當作 data quality issue
- **與 ADR-0023 治理紀律對齊** — enum 變更必經 ADR 的紀律延伸到 V094 fallback_reason enum；未來 sunset / rename 路徑明確
- **emit path liveness 釘住** — `close_maker_fallback_decision()` 純決策函數 unit test 必須覆蓋 10 個 event 映射，code path 不可悄悄退化

### Negative / Risk

- **90d cadence 增加治理工作量** — mitigation：calendar trigger 加到 TODO active state；review 是 lightweight check (≤30 min) 而非 full ADR rewrite
- **3 個 variants 真的退化成「dead code」風險** — 如未來 engine shutdown 流程改架構，可能 `EngineShutdownSafety` emit 路徑被誤刪而本 ADR 沒同步更新——mitigation：E2 review 對 maker_rejection.rs `close_maker_fallback_decision()` 改動須 cross-check 本 ADR；unit test 覆蓋是兜底防線
- **「dead by design」與「missing data」邊界判定主觀** — mitigation：本 ADR §Context「為什麼不能簡單 sunset」+ §Decision「dashboard / healthcheck 治理規則」已明確列舉判定標準；未來 review 時若邊界模糊可開補件 ADR 細化

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| V094 schema CHECK constraint（`V094__fills_close_maker_audit.sql:144-153`） | **不改動**；本 ADR 為 schema 治理紀錄非 schema 變更 |
| `CloseMakerFallbackReason` Rust enum（`maker_rejection.rs:115-126`） | **不改動**；本 ADR 為 enum governance baseline |
| `close_maker_fallback_decision()` 純決策函數 | **釘住 liveness**；E2 對該函數改動須驗 10 event → 10 reason 映射 unit test 覆蓋不退化 |
| ADR-0023 SourceAvailability enum governance | **同類紀律延伸**；本 ADR 是同模式「enum 變更必經 ADR」治理在 V094 fallback_reason 的具體應用 |
| FA 2026-05-20 P2-ENTRY-CLOSE-MAKER analysis SPEC-1 | **本 ADR 為其結案文檔**；FA SPEC-1 提出「3 dead variants 治理建議」→ PA 出 ADR-0028 |
| Phase 1b candidate selection report（`2026-05-18--phase_1b_calibration_cell_selection_report.md`） | **下游 analytics consumer**；本 ADR 釘住下游報告對 0 rows variants 必須區分 reserved vs missing data |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | 不觸 IntentProcessor / submit_intent |
| 2 | 讀寫分離 | ✅ | 純治理 artifact；無 IO 路徑 |
| 3 | AI 輸出 ≠ 命令 | ✅ | 不創造任何 AI → trade 路徑 |
| 4 | 策略不繞風控 | ✅ | enum reservation 保留 safety path audit slot；強化非削弱風控可審計性 |
| 5 | 生存 > 利潤 | ✅ | safety reservation = 生存路徑可審計；對齊原則 5 |
| 6 | 失敗默認收縮 | ✅ | safety reservation 確保 emergency 事件 audit 不丟失；fail-closed 友善 |
| 7 | 學習 ≠ Live | ✅ | 純治理；不影響 live state |
| 8 | 交易可解釋 | ✅ | enum 完整保留 = 每筆 close-maker fallback 可追溯；對齊原則 8 |
| 9 | 雙重防線 | ✅ | safety path 包含 engine shutdown audit slot；對齊本地 + exchange 雙重防線可審計 |
| 11 | Agent 最大自主 | ✅ | 不限縮 Agent 行為；治理層 enum 紀律 |
| 13 | cost 感知 | ✅ | 不增加 AI call 成本 |
| 14 | 零外部成本 | ✅ | 純治理紀錄；不依賴外部服務 |

## Cross-References

- **V094 schema**：`sql/migrations/V094__fills_close_maker_audit.sql` line 144-153（10 值 CHECK constraint）
- **Rust enum 定義**：`rust/openclaw_engine/src/strategies/maker_rejection.rs:115-126`
- **emit 純決策函數**：`rust/openclaw_engine/src/strategies/maker_rejection.rs:221-258`（`close_maker_fallback_decision()`）
- **FA 2026-05-20 P2-ENTRY-CLOSE-MAKER analysis**：SPEC-1 為本 ADR 起源（FA 報告位置由 FA workspace 提供）
- **ADR-0023**：`docs/adr/0023-source-availability-schema.md`（同類 enum 治理紀律 baseline）
- **Phase 1b candidate selection report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_cell_selection_report.md`（下游 analytics consumer 需區分 reserved vs missing data）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via 2026-05-20 FA P2-ENTRY-CLOSE-MAKER analysis SPEC-1 closure | 2026-05-21 | ✅ Accepted-pending-commit |
| PA | 本文件作者（SPEC-1 ADR 起草） | 2026-05-21 | ✅ Drafted |
| FA | 2026-05-20 P2-ENTRY-CLOSE-MAKER analysis SPEC-1 提出 ADR 訴求 | 2026-05-20 | ✅ ORIGINATING |
| PM | 本 ADR commit + 90d cadence calendar trigger 落地 TODO | TBD | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0028 — V094 close_maker_fallback_reason Dead Enum Variants (Safety Path Reservation)*
