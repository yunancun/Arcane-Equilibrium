# ADR 0023: SourceAvailability Schema — 共享 Alpha Source 可用性分類 enum

Date: 2026-05-18
Status: **Accepted (pre-merge)**
Operator Sign-off Date: 2026-05-18（主會話 PM 派發 + B-REM-5 E2 APPROVE 後 PA 落地）
Sign-off Mode: 主會話 PM dispatch via W-AUDIT-8a Phase B; E2 review (`2026-05-18--w_audit_8a_b_rem_5_e2_review.md`) APPROVE schema + MUST-FIX ADR-0023 documentation
Pending: merge of `feature/w-audit-8a-b-rem-5-source-availability` to main
Related: ADR-0021 (Alpha Source Architecture Upgrade R-1) / W-AUDIT-8a Phase B/C/D decomposition

## Context

### 起源

W-AUDIT-8a Phase B/C/D（per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md`）11-worktree decomposition 把 alpha source bundle 落地拆成 Wave 1/2/3 依賴鏈。`B-REM-5` 在 Wave 1 是 **critical bottleneck** — 推遲到 Wave 2 會強制下游 7 個 worktree（B-REM-2 funding consumer report / B-REM-3 OI consumer report / C2-ORDERFLOW / C3-SPREAD / D1-EVENT / D2-REGIME / D3-SENTIMENT）各自重新發明「為什麼 alpha source 在當前 tick 不可用」的分類 schema，導致報告層分歧 + audit trail 失對齊。

### 既有兩條 schema 不足以承擔此責任

1. **既存 `source_tier: String` 字段**（FundingCurveSnapshot / BasisCurveSnapshot / OIDeltaPanel / OrderflowFeatures / LiquidationPulse / SentimentPanel 等 panel snapshot）= 自由文本 provenance（如 `"bybit_v5_ws_tickers"`），用於 PG 寫入 lineage 對齊；**無分類語意**，無法回答「為什麼這個 surface field 是 None」。

2. **V050 `evidence_source_tier` enum**（`calibrated_replay` / `synthetic_replay` / `counterfactual_replay`）= replay lineage enum，是 **fill-level 不是 surface-level**；無法用於 candidate report 表達「surface field 不可用的真實成因」。

### Phase B/C/D 7 個下游 worktree 的共同需求

下游 candidate report writer（B-REM-2/3 + C2/C3 + D1/D2/D3）需要把 `surface.<field> = None` 的真正成因標準化為分類成因（不能只看「None vs Some」黑盒），以便：

- Stage 0R promotion gate 做精確 reason 聚合（如「funding panel 因 stale 還是 cohort-excluded 而被 skip」決定不同 promotion path）
- Healthcheck 對應分項（如 `oi_panel_unavailable_breakdown{reason=...}`）
- Strategy consumer fail-closed 路徑可被 audit 對齊（B-REM-3 unit test 要求合成每條 unavailable variant 證明 fail-closed 不退化到 TA1m fallback）

### 兩個替代路徑（已評估 + 棄）

**Option A**：flat enum `{ WsLive, RestSeed, CohortExcluded, StalePanel, MissingSymbol, NonFiniteAbsolute, NonFiniteDelta, Absent }`（PA §6.2 raw spec）— 棄。理由：(a) 允許非法組合（如 `WsLive + StalePanel`，但 stale 就不是 ws_live 實時源 而是過期源）；(b) tier（WS-live vs REST-seed）與 availability（available vs unavailable）是兩個正交問題，平鋪混淆語意；(c) 下游 report writer 必須維護 explicit 「tier 與 reason 不能同時 set」的 invariant，易漂移。

**Option B**：拆兩個獨立 enum — `enum AvailabilityTier { WsLive, RestSeed }` + `enum UnavailableReason { CohortExcluded, StalePanel, ... }`，下游欄位同時帶兩者 `(tier: Option<AvailabilityTier>, reason: Option<UnavailableReason>)` — 棄。理由：(a) 雙 field 互斥但不可從型別系統強制（編譯器允許 `tier=Some + reason=Some` 非法狀態）；(b) Prometheus / PG label 對齊複雜（雙 join）；(c) 下游 7 worktree 重複 boilerplate。

**Option C**：free-text `source_tier: String` 沿用既存欄位塞「reason」分類— 棄。理由：(a) 無 compile-time enum allowlist，typo / 拼字 drift 不可阻擋；(b) 與既存 `source_tier` 字面值的「具體 endpoint 描述」語意衝突；(c) audit aggregation 必須做字串歸一化，是反模式。

## Decision

採用 **巢狀 `Available { tier: AvailabilitySource }` enum 設計**（per E2 §4.2 verify legitimate enhancement 過 PA §6.2 raw spec）：

```rust
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SourceAvailability {
    /// Alpha source 在當前 tick 可用；`tier` 標記資料來自哪一層 producer。
    Available { tier: AvailabilitySource },
    /// Symbol 不在當前 cohort（如 BUSDT 在 BTCUSDT cohort 外）；非錯誤，是定義域排除。
    CohortExcluded,
    /// Panel 存在但 freshness 超 threshold（funding 1h-cycle panel > 75min；OI 5m panel > 15min）。
    StalePanel,
    /// Panel 存在但對應 symbol 缺失（panel 涵蓋部分 cohort 而非全部）。
    MissingSymbol,
    /// 數值非有限（NaN / Inf）— 標記 absolute 值錯誤（如 oi_abs = NaN）。
    NonFiniteAbsolute,
    /// 數值非有限（NaN / Inf）— 標記 delta 值錯誤（如 oi_delta_5m_pct = Inf）。
    NonFiniteDelta,
    /// Panel slot 完全不存在（IPC slot 未 publish / collector 未啟動 / try_read soft-fail）。
    Absent,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AvailabilitySource {
    /// WS-first 實時源（Bybit V5 WS / orderbook.50 / allLiquidation / tickers）。
    WsLive,
    /// REST 冷啟動 seed（pipeline 啟動前 N 分鐘的 REST one-shot 補齊；後續 WS 接管）。
    RestSeed,
}
```

### 8 variant 完整集（lock 治理基線）

| Variant | 語意 | 下游引用情境 |
|---|---|---|
| `Available { WsLive }` | 可用 + WS-first 實時源 | B-REM-2/3 + C2/C3 + D1/D2/D3 所有可用情境（panel collector 正在 publish 新值） |
| `Available { RestSeed }` | 可用 + REST 冷啟動 seed | Pipeline 啟動前 N 分鐘 cold-start window（per `funding_curve_aggregator.rs` cold-start 路徑） |
| `CohortExcluded` | symbol 不在 cohort | B-REM-3（BUSDT 在 BTCUSDT cohort 外）+ C2/C3 + D3 |
| `StalePanel` | freshness 超 threshold | B-REM-2/3（funding panel > 75min；OI panel > 15min）+ C2/C3 + D1/D2 |
| `MissingSymbol` | panel 部分覆蓋 cohort 但對應 symbol 缺 | B-REM-3 + C2/C3 + D2/D3 |
| `NonFiniteAbsolute` | 絕對值非有限 (NaN/Inf) | B-REM-3 + C2/C3 numeric 欄位 |
| `NonFiniteDelta` | delta 值非有限 (NaN/Inf) | B-REM-3 + C2/C3 numeric 欄位 |
| `Absent` | panel slot 完全不存在 | Phase A 全 None 預設原因；C1-LIQ-WRITER 前的 LiquidationPulse 預設 |

### 設計約束

1. **Internally-tagged serde**（`#[serde(tag = "kind", rename_all = "snake_case")]`）— 跨語言 IPC 一致；Python 端 candidate report writer 產出對應 `{"kind":"available","tier":"ws_live"}` / `{"kind":"stale_panel"}` JSON 結構，與 Rust deserialize 對齊。
2. **完整 derive**：`Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize`。
3. **故意不 derive `Copy`** — 雖然當前所有變體都 Copy-safe（AvailabilitySource 是 Copy + 其他變體 unit），但未來變體可能帶 String reason / source chain，forward-compat 設計選擇。
4. **`as_metric_label()` 對 Available 統一回 `"available"`** — Prometheus tag cardinality bounded 在 8 個 string（tier 子標籤透過獨立 `availability_tier_label()` API 提供，僅 Available 時回 ws_live/rest_seed）。
5. **`is_available()` / `unavailable_reason()` 互逆 API** — 下游 candidate report 寫入 `unavailable_reason` 欄位時直接 `availability.unavailable_reason()` 即可；E1 對應 test `source_availability_is_available_and_unavailable_reason_inverse` 鎖死互逆契約。
6. **Display impl 對 Available 與 unavailable 分別處理**（`"available(ws_live)"` vs `"stale_panel"`）— 日誌人讀友善。

### enum 變更治理（governance discipline）

**添加 / 刪除 / 重命名 variant 必經 ADR**：

- 添加新 variant（如未來引入 `NonFiniteRelative` / `SchemaVersionMismatch`）— 必須開新 ADR 補件，列出新 variant 的下游引用點 + 預期 healthcheck 配套。
- 刪除既存 variant — 必須開新 ADR 列出 deprecation path 與 superseder（無 superseder 不允許刪）。
- 重命名 variant — 必須開新 ADR 同時更新 serde `rename_all` 與下游引用，且必須有 dual-write 過渡期（PG enum column 不可一次性 rename）。
- `as_metric_label()` 字串值 / serde `tag="kind"` 字串值改動 = breaking change，視同重命名。

ADR-0023 本文是該治理基線的初始 lock。後續 variant 變更開 ADR-002X 補件並 cross-ref 本 ADR。

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **Flat enum `{ WsLive, RestSeed, CohortExcluded, ... }`**（PA §6.2 raw spec） | 允許非法組合（如 `WsLive + StalePanel`）；tier 與 availability 平鋪混淆語意；下游 report writer 必須維護 explicit invariant |
| **拆兩個獨立 enum**（`AvailabilityTier` + `UnavailableReason`） | 雙 field 互斥但不可從型別系統強制（編譯器允許非法雙 Some 狀態）；Prometheus / PG label 對齊複雜；下游 7 worktree 重複 boilerplate |
| **Free-text `source_tier: String`** 沿用既存欄位塞分類 | 無 compile-time enum allowlist；與既存 `source_tier` 字面值（具體 endpoint 描述）語意衝突；audit aggregation 需字串歸一化是反模式 |

## Consequences

### Positive

- **7 個下游 worktree（B-REM-2/3 + C2/C3 + D1/D2/D3）可 import without divergence** — 共享 schema = 單一 source of truth；候選 report `unavailable_reason` 欄位直接寫 `availability.unavailable_reason()` 即可。
- **Stage 0R promotion gate 可做精確 reason 聚合** — 不再黑盒 None vs Some，可區分 stale / cohort-excluded / non-finite 不同 promotion path。
- **Prometheus / PG label cardinality bounded** — `as_metric_label()` 8 string + `availability_tier_label()` 2 子標籤 only when Available。
- **Schema change requires new ADR**（governance discipline）— 阻擋下游 worktree 自定義 reason variant + 防止 enum 漂移。
- **既存 `source_tier: String` 字段 0 break** — 兩者並存：本 enum 描述語意層次（available/unavailable + tier producer 層），既存字串描述具體 endpoint（`"bybit_v5_ws_tickers"`），正交設計。
- **Strategy consumer fail-closed 路徑可被 audit 對齊** — B-REM-3 unit test 合成每條 unavailable variant，證明 strategy（如 bb_breakout enable_oi_signal）對每條都 fail-closed 不退化到 TA1m fallback。

### Negative / Risk

- **enum 治理紀律必須維持** — variant 變更必經 ADR 是新增的 process tax；mitigation = ADR template 階段已含 §Decision 鎖定 8 variant 完整集 + 變更治理規則。
- **`AvailabilitySource` 拓展空間有限** — 當前 2 變體（WsLive / RestSeed），若未來引入第三層 producer（如 historical_backfill），需新 ADR 補件擴展 enum + 同步 serde + 同步 `as_metric_label()`。
- **巢狀 `Available { tier }` 增加 match 樣板** — 下游 report writer 必須處理 `Available { tier: WsLive }` vs `Available { tier: RestSeed }` 兩種可用 case；mitigation = `is_available()` / `as_metric_label()` 提供 fast-path API。
- **Forward reference to ADR-0023 at code line 191 (commit `5997dd43`)** — schema IMPL 先 land、ADR 文檔後補；本 ADR commit 後此 forward reference 即實體化，後續 worktree IMPL 引用本 ADR 為 governance baseline。

### 與既存設計的協作

| 既存元素 | 與 SourceAvailability 的關係 |
|---|---|
| `source_tier: String` 字段（panel snapshot） | **正交並存**；本 enum 描述語意層次（available/unavailable + tier 層），既存字串描述具體 endpoint；下游可同時帶兩者 |
| `AlphaSurface { funding_curve: Option<&FundingCurveSnapshot>, ... }` | **不改 surface 型別**；surface field 仍是 `Option<&T>`，策略 consumer 仍用 `is_none() → fail-closed skip` pattern；本 enum 僅用於 candidate report writer 的 post-hoc classification（per E2 §4.8） |
| V050 `evidence_source_tier` enum | **無關**；V050 是 fill-level replay lineage，本 enum 是 surface-level availability classification；不重疊 |
| ADR-0021 Alpha Source Architecture Upgrade R-1 | **直接 enabler**；R-1 AlphaSurface bundle + Strategy interface upgrade 是本 enum 的設計前提；ADR-0023 是 R-1 implementation 階段的 schema lock |

### 變更下游影響

| Wave | Worktree | 引用點 |
|---|---|---|
| Wave 2 | B-REM-2 (funding consumer report) | `surface.funding_curve` 可用性分類；candidate report `availability` 欄位 |
| Wave 2 | B-REM-3 (OI consumer report) | `surface.oi_delta_panel` 可用性 + 5 unavailable variants（absent / stale / missing-symbol / non-finite-absolute / non-finite-delta）；fail-closed unit test 合成每條 |
| Wave 2 | C2-ORDERFLOW | `surface.orderflow` 可用性分類 |
| Wave 2 | C3-SPREAD | C2 panel spread 欄位可用性分類 |
| Wave 3 | D1-EVENT | `surface.event_alerts` 可用性分類 |
| Wave 3 | D2-REGIME | `surface.regime != Unknown` 可用性分類；Unknown = unavailable not neutral |
| Wave 3 | D3-SENTIMENT | `surface.sentiment_panel` 可用性分類；low-sample = unavailable |

### LOW finding 配套

E2 review §5 LOW 1：`alpha_surface.rs:176` doc-comment 寫「6 個下游 worktree」但 parenthesized list 與下方表均列 7 個（B-REM-2/3 + C2/C3 + D1/D2/D3），test fixture assert downstream.len() == 7。PA + E1 配套 by separate trivial commit 1-字符 edit（6 → 7）；不在本 ADR 範圍。

## Implementation

### 主要 IMPL 位置

- File: `rust/openclaw_core/src/alpha_surface.rs:113-272`（B-REM-5 SourceAvailability section）
- Branch: `feature/w-audit-8a-b-rem-5-source-availability`
- Commit: `5997dd43`（schema IMPL）
- 後續 commit：本 ADR-0023 文檔 + alpha_surface.rs:176 doc-comment 6 → 7 trivial edit（分開 commit）

### 測試證據

- 442 unit tests pass（workspace `cargo test -p openclaw_core --lib`）
- 6 B-REM-5 specific tests + 2 AvailabilitySource tests = 8 tests cover：
  - 8 variant `as_metric_label()` 對齊
  - 8 variant serde JSON internally-tagged round-trip
  - `is_available()` / `unavailable_reason()` 互逆契約
  - `availability_tier_label()` 在 Available 時回 tier 字串，否則 None
  - Display impl 對 Available 與 unavailable 分別格式化
- 0 compile error；4 pre-existing warnings（不 B-REM-5 related）

### 治理引用點

- 添加 / 刪除 / 重命名 variant → 開新 ADR 補件 cross-ref 本 ADR
- 下游 worktree IMPL spec（Wave 2 / Wave 3）必須引用本 ADR 為 governance baseline；不允許 downstream 自定義 reason variant
- ADR-0023 status = Accepted（pre-merge）；merge `feature/w-audit-8a-b-rem-5-source-availability` 到 main 後同步更新本 ADR header `Pending` field 清掉

## §二 16 根原則合規確認（per ADR template + CLAUDE.md §二）

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | 純 schema enum；不觸 IntentProcessor / submit_intent |
| 2 | 讀寫分離 | ✅ | 純 type definition；無 IO 路徑 |
| 3 | AI 輸出 ≠ 命令 | ✅ | 不創造任何 AI → trade 路徑 |
| 4 | 策略不繞風控 | ✅ | 不接線任何策略消費；策略接線在 W-AUDIT-8e/8f 才處理 |
| 5 | 生存 > 利潤 | ✅ | 不觸 StopManager / liquidation_buffer |
| 6 | 失敗默認收縮 | ✅ | enum 設計顯化 unavailable variant；下游 strategy consumer 必 fail-closed（B-REM-3 unit test 強制） |
| 7 | 學習 ≠ Live | ✅ | 純 schema；不影響 live state |
| 8 | 交易可解釋 | ✅ | candidate report `unavailable_reason` 欄位由本 enum 標準化；audit aggregation 可對齊 |
| 9 | 雙重防線 | ✅ | 不影響本地 + 交易所條件單 |
| 11 | Agent 最大自主 | ✅ | 不限縮 Agent 行為；提供 surface availability 共享 schema 服務下游 candidate report |
| 13 | cost 感知 | ✅ | 不增加 AI call 成本 |
| 14 | 零外部成本 | ✅ | 純 type definition；不依賴外部服務 |

## Cross-References

- **B-REM-5 commit**: `5997dd43`（branch `feature/w-audit-8a-b-rem-5-source-availability`，schema IMPL +369 LOC）
- **E2 review**: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8a_b_rem_5_e2_review.md`（APPROVE schema + MUST-FIX ADR-0023 documentation）
- **PA decomposition spec**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md` §6.2 + §6.4（11-worktree decomposition；B-REM-5 critical bottleneck）
- **ADR-0021**: `docs/adr/0021-alpha-source-architecture-upgrade.md`（R-1 AlphaSurface bundle + Strategy interface upgrade；本 enum 為 R-1 IMPL 階段的 schema lock）
- **ADR-0022**: `docs/adr/0022-strategist-cap-wide-parameter-adjustment-skill.md`（前一份 ADR；ADR-0023 沿用同 ADR template format）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via W-AUDIT-8a Phase B；B-REM-5 schema IMPL + E2 APPROVE 後 PA ADR 落地 | 2026-05-18 | ✅ Accepted (pre-merge) |
| PA | 本文件作者（W-AUDIT-8a B-REM-5 ADR-0023 dispatch） | 2026-05-18 | ✅ Drafted |
| E1 | B-REM-5 schema IMPL（commit `5997dd43`，442 tests pass） | 2026-05-18 | ✅ IMPL DONE |
| E2 | review report `2026-05-18--w_audit_8a_b_rem_5_e2_review.md` APPROVE schema + MUST-FIX ADR-0023 | 2026-05-18 | ✅ APPROVE (schema) |
| E4 | regression on `feature/w-audit-8a-b-rem-5-source-availability` | TBD | 🟡 PENDING |
| PM | 本 ADR commit + merge `feature/w-audit-8a-b-rem-5-source-availability` 到 main 後 sign-off | TBD | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0023 — SourceAvailability Schema (Shared Alpha Source Availability Classification enum)*
