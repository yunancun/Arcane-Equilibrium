# PA 技術派工核實 — v5.7 12 條 CRITICAL prefix 全部完成 verdict

**日期**：2026-05-21
**Verdict**：**NEEDS-PM-ARBITRATION**（4 仲裁項；非 NO-GO，可於 24-48 hr 內派發 Sprint 1A 中 3 個非阻塞 track）
**PA 一句話結論**：12 條 prefix land 完整度技術端 11/12 PASS（1 條需 PM 仲裁 V### re-number 路徑），Apple Silicon CI 對 `cargo check` enforceable / `cargo clippy -D warnings` 不可行需放寬；5 並行 track 中 1A-gov + 1A-sensor + 1A-earn 三條技術上 READY-TO-DISPATCH，1A-schema 阻塞於 V### re-number PM 仲裁，1A-gui 阻塞於 tab 歸屬 operator 拍板；C10 工時 90-130 與 BB 65-85 之間衝突需澄清。

---

## §1 12 條 prefix 技術完整度逐條核

| # | prefix | 完成證據 | 技術完整度 | 風險 |
|---|---|---|---|---|
| C1 | v5.7 主檔搬遷 + git tree | `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` 存在 | ✅ | 0 |
| C2 | 4 ADR draft（0030/0031/0032/0033）| 4 file land `docs/adr/`（17.1K / 18.1K / 21.2K / 20K，926 行）| ✅ | 0 — cross-ref 4 ADR 互相 link 全命中 + 風格 100% 對齊 0028/0029 |
| C3 | V103/V104 schema spec | `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` 52K 940 行 | ⚠️ | **與 V101 spec v3 字段集 ~60% 衝突**；MIT 採 v5.7 brief 路徑 A（廢棄 V101 §3.3.1/§3.3.2）；PM 仲裁項 |
| C4 | Bybit Earn API endpoint 存在性 | `BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md` Part A 直接 evidence | ✅ | 0 — (a) API exists + 12 endpoint enumerated + 字典 drift 5+ 月（BB1 sub-agent 補錄）|
| C5 | Bybit Earn API key scope | Part B + aotrading + Bybit help center evidence | ✅ | 0 — (a) dedicated `Earn` scope 不違 D1d；待 operator 查 OpenClaw key 發行日（5 min check）|
| C6 | liquidation writer 24h PROOF | Part C：PG empirical 31,473 rows 3.7 day | ✅ | 0 — **推翻 v57 executability audit Risk 1 BLOCKED claim**；字典 + W-AUDIT-8a C1 plan stale ~5 day 需同步 |
| C7 | Sprint 1B C10 reframe Stage 0R + Stage 1 Demo | dispatch_packet §1 含完整 Stage 真實 live 排程表（5-stage）| ✅ | 0 — 排程表覆蓋 AMD-2026-05-15-01 graduated canary；mainnet $2,000 落 Sprint 3-4 |
| C8 | Earn governance spec | `docs/execution_plan/2026-05-21--earn_governance_spec.md` 30K 516 行 | ⚠️ | §4 待 BB C4 verdict 後 finalize — 現可 finalize 為條件 A（API exists demo + live）|
| C9 | V103/V104 Linux PG dry-run | `PA/workspace/reports/2026-05-21--v57_c9_pg_dry_run.md` + `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` 17K | ✅ | 0 — PG empirical confirm head=V096, V101/V102 未 land；**重大建議 V### re-number 路徑 A**（V097/V098 catch-up → V099/V100 = Track v3 → V101/V102 = Earn schema）|
| C10 | 工時上修 + 並行 sub-agent mandate | dispatch_packet §2 工時表 + 39 週 calendar + LLM cost | ⚠️ | **與 BB C6 verdict 後 65-85 hr 衝突**；dispatch_packet 寫 90-130 hr 是 v57 audit 過度反估 +50 hr（BB 推翻 Risk 1）；PM 需重評是否回滾 |
| C11 | Apple Silicon CI tuple | dispatch_packet §3 cargo check + cargo clippy + features pyo3 | ⚠️ | **`cargo check --target aarch64-apple-darwin` ✅ enforceable**（實測 PASS 12 sec）；**`cargo clippy -- -D warnings` ❌ 不可行**（既有 17 clippy errors）|
| C12 | 中文注釋 + SCRIPT_INDEX + MODULE_NOTE | dispatch_packet §4 + grep enforcement | ✅ | 0 — SCRIPT_INDEX.md 179 行 table 格式既有；E2 review grep `rg -L 'MODULE_NOTE\|模塊用途'` 可行 |

**統計**：✅ 8 / ⚠️ 4（C3 仲裁 / C8 待 C4 / C10 衝突 / C11 部分不可行）/ ❌ 0

---

## §2 Sprint 1A 5 並行 track dispatch readiness

| Track | 工時 | 依賴 | 阻塞解除狀況 | dispatch verdict |
|---|---|---|---|---|
| **1A-gov** | 25-30 hr | 無 | ✅ C2 4 ADR land + C8 Earn governance spec land + C9 PG dry-run land | **READY-TO-DISPATCH** |
| **1A-schema** | 15-25 hr | 1A-gov C1 + C9 PG dry-run | ⚠️ C3 V103/V104 spec land 但 **V### re-number PM 仲裁未拍**（V101/V102 還是 V103/V104？V099/V100 Track v3 是否同時 dispatch？）| **NEEDS-PM-ARBITRATION** |
| **1A-sensor** | 50-70 hr（**修正為 35-55 hr**）| 1A-gov C2 ADR-0033 | ✅ C6 推翻 liquidation writer BLOCKED claim → 減 15-20 hr work（writer 已 production 31,473 rows / 3.7 day，只需 healthcheck + buffer 接線）| **READY-TO-DISPATCH** |
| **1A-earn** | 12-18 hr | C4 + C5 | ✅ C4 (a) API exists / C5 (a) non-withdraw scope sufficient；operator 查 OpenClaw key 發行日 5 min check **不阻塞 dispatch**（read-only 先 ship）| **READY-TO-DISPATCH** |
| **1A-gui** | 8-12 hr | H2 tab 歸屬決策 | ⚠️ A3 + E1a tab 歸屬決策（H2 governance/agents/learning sub-section）已寫進 dispatch_consolidation §5.2，**但 operator 未拍板** | **NEEDS-OPERATOR-DECISION** |

**真實 1A-sensor 工時修正**：
- v5.7 §9 estimate：60-80 hr（一部分）
- v57 audit estimate：90-130 hr（含 +30-50 hr 反估）
- **BB C6 真實**：65-85 hr 全 Sprint 1A（§4 Earn 18-25 hr + §4 Governance 20-25 hr + §6 healthcheck 0-1 hr wash + §8 sensor 65-95 hr）— **dispatch_packet §2 寫 90-130 hr 高估約 25 hr**

---

## §3 Interface 設計一致性 verdict

### §3.1 V103/V104 schema spec §3.2 vs Earn governance spec §3.2 EarnIntentPayload 對齊

| Column | V103 schema (`earn_movement_log`) | EarnIntentPayload (CC spec) | 對齊狀況 |
|---|---|---|---|
| `movement_id` BIGSERIAL PK | ✅ | — | spec 層；payload 不必含 |
| `event_ts` TIMESTAMPTZ NOT NULL | ✅ | `submitted_ts: TimestampUtc` | ✅ 一致 |
| `direction` CHECK (`stake`/`redeem`) | ✅ | `direction: String 'stake'\|'redeem'` | ✅ 一致 |
| `amount_usdt` NUMERIC(18,8) | ✅ | `amount_usdt: Decimal` | ✅ 一致（NUMERIC↔Decimal 對應）|
| `apr_at_time` REAL NULL | ✅ | `expected_apr_bps: i32` | ⚠️ 名稱不同（apr_at_time = actual; expected_apr_bps = intent-time expected）；**CC spec RISK-5 已標漂移** + `bybit_reported_apr_at_execution` 另存（語意 OK，但兩個欄位**需在 V103 spec 加上 `expected_apr_bps`**才完整） |
| `governance_approval_id` BIGINT FK | ✅ | `approval_id: Uuid` | ❌ **類型衝突**：V103 用 BIGINT FK → `governance.audit_log.id`，CC spec 用 UUID approval_id；需在 V103 加 `approval_uuid` 或 CC spec 改 BIGINT |
| `bybit_response_payload` JSONB | ✅ | — | spec 層；payload 不必含 |
| `engine_mode` CHECK | ✅ | — | spec 層 |
| `api_scope_used` TEXT NOT NULL | ✅ | — | spec 層 |
| `reconciliation_status` CHECK | ✅ | — | spec 層 |
| — | `intent_id` Uuid | ❌ V103 缺對應 column | **需新加 `intent_id UUID`** |
| — | `intent_type` IntentType enum | ❌ V103 缺對應 column | direction 部分代替；但 Rust IntentType enum 既不存在（見 §3.4）|
| — | `actor_id: String` | ❌ V103 缺對應 column | **需新加 `actor_id TEXT`** |
| — | `rationale: Option<String>` | ❌ V103 缺對應 column | **需新加 `rationale TEXT NULL`** |

**verdict**：⚠️ **V103 schema 與 EarnIntentPayload 缺 4-5 個欄位對齊**（intent_id / actor_id / rationale / approval UUID 或 BIGINT 統一 / expected_apr_bps）；不阻塞 Sprint 1A schema land，但 Sprint 1B Earn IMPL 前需 PA 補 V### follow-up（small migration ALTER ADD COLUMN）或 CC spec §3.2 patch 對齊 V103。

### §3.2 ADR-0030/0031/0032/0033 cross-ref 與 spec 雙向命中表

| ADR | Cross-ref to spec / TODO | 雙向命中 |
|---|---|---|
| ADR-0030 Copy Trading evidence-gated | ADR-0006/0008/0017/0033 | ✅ 全命中（ADR-0033 反向引 ADR-0030 已驗）|
| ADR-0031 Framework expansion (Earn/Macro/On-chain) | ADR-0006/0008/0017/0030/0032 | ✅ 全命中 |
| ADR-0032 Bybit Earn asset movement Guardian | ADR-0008/0031 | ✅ 命中；**未引 V103 schema spec / earn_governance spec**（draft 時兩 spec land 同日 16:00-16:08）— **HIGH 建議**：ADR-0032 §Cross-Reference 補 V103 spec + earn_governance spec |
| ADR-0033 ADR-0006 amendment | ADR-0006/0030/0031/0032 | ✅ 命中 |
| V103/V104 spec | parent specs 列 v5.7 主檔 + V101 spec + MIT audit | ✅ 命中 |
| Earn governance spec | parent specs 列 v5.7 + CC executability audit + PA dispatch_consolidation + MIT + BB audits | ✅ 命中；related ADRs 列 ADR-0030（**寫錯，應該是 ADR-0032**；參考 dispatch_packet §6.2 編號表）|

**verdict**：⚠️ **2 個 cross-ref minor 漂移**：(1) ADR-0032 漏引 V103 + earn_governance spec（補 5 行 cross-ref）(2) Earn governance spec related ADRs 寫 `ADR-0030` 但應該是 `ADR-0032`（per §6.2 編號表 ADR-0032 = Bybit Earn Guardian），這是 CC spec drafter typo。Sprint 1A dispatch 前 30 min patch 可補。

### §3.3 IntentProcessor enum extension（EarnStake / EarnRedeem）一致性

**重大發現**：Rust `OrderIntent` struct（`rust/openclaw_engine/src/intent_processor/mod.rs:60`）**沒有 IntentType enum**；只有：
- `is_long: bool`
- `order_type: String` ("market"/"limit")
- `qty: f64` / `confidence` / `strategy` / `symbol` / `confluence_score` / `persistence_elapsed_ms` / `time_in_force` / `maker_timeout_ms`

CC Earn governance spec §3.1 寫：
```rust
enum IntentType {
    OpenLong, OpenShort, CloseLong, CloseShort,
    EarnStake, EarnRedeem,
}
```

**是「概念性 placeholder」非實際既有 enum**。CC spec 標 「v57-C8 不改實檔，僅 spec」對齊本意，但 ADR-0032 + V103 schema + Earn governance spec 三件都假設「擴 enum」實作路徑 — **實際 IMPL 派發時 E1 需新建這個 enum**（或新建 `EarnIntent` struct 與 `OrderIntent` 並列）。

**影響**：
- Sprint 1A schema land 不受影響（V103 是 SQL spec，不依賴 Rust IntentType）
- Sprint 1A read-only Earn API recorder 不受影響（read-only path 不走 IntentProcessor）
- **Sprint 1B 程式化 stake/redeem IMPL 前**需先派 PA dispatch 設計 IntentType enum 結構（或 `EarnIntent` struct）— 預計 +1-2 hr design buffer，**不阻塞 Sprint 1A**

### §3.4 Decision Lease lease_type 'earn_stake' / 'earn_redeem' vs Rust LeaseScope enum

**Rust `LeaseScope` enum**（`rust/openclaw_core/src/lease_scope.rs:35`）目前 4 variant：
```rust
pub enum LeaseScope {
    TradeEntry,
    TradeExit,
    PositionAdjust,
    CanaryStagePromotion,
}
```

**CC Earn governance spec §2.3 + §3.3 + §10.1 + §12 全部假設**：「新增 lease_type='earn_stake' 與 'earn_redeem'」+「既有 Rust `GovernanceCore.acquire_lease()` facade，僅擴 enum 值，不新建 facade」

**verdict**：✅ **LeaseScope enum 真的可以擴**（添 `EarnStake` / `EarnRedeem` variant + `as_audit_str()` 加 2 條 string mapping + `default_ttl_ms()` 加 60_000 mapping + 不必動 facade）— CC spec 假設正確。**但**：
1. V094 / V083 mirror pattern 顯示，新 enum variant 必同步 SQL CHECK constraint（per `lease_scope.rs:55-58` 注釋警告）— V103 spec 已含這個（per `lease_transitions` 衍生 view 對應）
2. `requires_operator_authority()` for `EarnStake/Redeem` 需明示（per CC spec §2.1 Operator role auth gate (a)）— CC spec 寫 PrimaryOperator/BackupOperator，但 Rust facade 是 hard fail-closed 還是依 GovernanceProfile？建議**EarnStake/Redeem 設 `requires_operator_authority = true`**（與 CanaryStagePromotion 同等嚴格度）

---

## §4 技術風險矩陣

| # | Risk | 嚴重度 | 影響 Sprint 1A 範圍 | 緩解 |
|---|---|---|---|---|
| R1 | **C10 工時 90-130 hr 與 BB 真實 65-85 hr 衝突** | HIGH | dispatch_packet §2 + Y1 total 1,295-1,740 hr 上修依據被 BB Verdict 推翻部分 | PM 仲裁項 2；PA 建議 dispatch_packet §2 寫雙 estimate（v57 audit 90-130 hr / BB-real 65-85 hr）+ explicit reference C6 PROOF；不回滾 Y1 total 上修（含 GUI/TW/LLM buffer 仍合理）|
| R2 | **V### re-number 路徑 A vs B 未仲裁** | CRITICAL | 1A-schema dispatch 完全阻塞；影響 V103/V104 IMPL 是 V101/V102 還是 V103/V104 | PM 仲裁項 1；PA 強烈建議路徑 A（V097/V098 catch-up → V099/V100 Track v3 → V101/V102 Earn schema → V103/V104 reserve / no-op）；4 ADR/spec search/replace 30 min churn 可接受 |
| R3 | **Apple Silicon CI clippy -D warnings 不可行** | MEDIUM | C11 acceptance criteria 寫 `cargo clippy -- -D warnings` 真實 17 errors FAIL；不修則 sub-agent PR 全失敗 | PA 建議 dispatch_packet §3.1 修正：(a) `cargo check --target aarch64-apple-darwin --release` ✅ 強制 (b) `cargo check --target aarch64-apple-darwin --tests` ✅ 強制 (c) `cargo clippy --target aarch64-apple-darwin -- -A clippy::too_many_arguments` 軟強制（既有 baseline error 不擋新 code）或先解決 17 既有 clippy errors（拆 P2 ticket）|
| R4 | **CC Earn governance spec ADR cross-ref typo** | LOW | Earn governance spec related ADRs 寫 `ADR-0030` 應為 `ADR-0032` | dispatch 前 30 min patch；不阻塞 |
| R5 | **V103 schema 缺 EarnIntentPayload 對齊 4-5 column**（intent_id / actor_id / rationale / approval UUID 統一 / expected_apr_bps）| MEDIUM | V103 IMPL 後 Sprint 1B Earn live IMPL 才會撞 | Sprint 1A dispatch 前不阻塞；建議 PA Sprint 1B 開始前派 small migration V### follow-up（ALTER ADD COLUMN）或 CC spec §3.2 patch |
| R6 | **Rust IntentType enum 不存在 / OrderIntent 無 enum 字段** | LOW | Sprint 1B 程式化 Earn IMPL 前才會撞 | Sprint 1A 不阻塞；建議 PA Sprint 1B IMPL 派發前先設計 IntentType enum 結構（或 EarnIntent struct + OrderIntent 並列）|
| R7 | **ADR-0032 漏引 V103 spec + earn_governance spec cross-ref** | LOW | ADR-0032 §Cross-Reference 完整度 | dispatch 前 5 min patch；不阻塞 |
| R8 | **Earn governance spec §4 條件 A/B/C 未 finalize** | LOW | spec 自身 §4 status pending；BB C4 verdict 已 (a) API exists → 直接 finalize 為條件 A | dispatch 前 30 min patch（複製 §4.2 條件 A 內容到主 §4，刪 §4.3/§4.4 條件 B/C placeholder）|

---

## §5 Apple Silicon CI smoke test verdict

### §5.1 實測命中率

| 命令 | 實測 result | 用時 | enforceable |
|---|---|---|---|
| `cd rust/openclaw_engine && cargo check --target aarch64-apple-darwin` | ✅ Finished `dev` profile（2 warnings: unused import / method never used）| ~12 sec | ✅ **YES** |
| `cargo check --target aarch64-apple-darwin --tests` | ✅ Finished（2 warnings: dead_code）| ~13 sec | ✅ **YES** |
| `cargo clippy --target aarch64-apple-darwin -- -D warnings` | ❌ **error: could not compile `openclaw_core` (lib) due to 17 previous errors** | ~? sec | ❌ **NO** — 既有 17 clippy errors（`too_many_arguments` 等） |
| `cargo check --target aarch64-apple-darwin --features pyo3` | 未測（dispatch_packet §3.1 列為條件 fallback）| — | — |

### §5.2 對 dispatch_packet §3.1 acceptance criteria 的修正建議

**現寫**：
```bash
cargo check --target aarch64-apple-darwin --release
cargo check --target aarch64-apple-darwin --tests
cargo clippy --target aarch64-apple-darwin -- -D warnings   # ❌ 不可行
```

**PA 建議修正**：
```bash
cargo check --target aarch64-apple-darwin --release    # ✅ 強制
cargo check --target aarch64-apple-darwin --tests      # ✅ 強制
# 既有 17 baseline clippy errors，新 PR 不允許新增；既有錯誤拆 P2 ticket 漸進清
cargo clippy --target aarch64-apple-darwin -- -A clippy::too_many_arguments -A clippy::too_many_lines   # 軟強制
```

或者：**先派 E1 並行 clean 17 既有 clippy errors**（拆 P2-clippy-cleanup ticket），Sprint 1A 期間並行 land，Sprint 1B 後 `cargo clippy -- -D warnings` 正式啟用。

---

## §6 PA 對 PM 的仲裁建議

### 仲裁項 1：V### re-number 路徑 A vs B（CRITICAL — 阻塞 1A-schema dispatch）

**PA 強烈建議路徑 A**：
```
V097 / V098 catch-up Linux DB（per PA C9 PG dry-run, head=V096）
V099 / V100 = V101/V102 Track v3 Earn schema spec content（同 spec 邏輯，編號順移）
V101 / V102 = NEW Earn schema（hypotheses / preregistration / earn_movement_log）
V103 / V104 = reserve（per V104 退號 no-op 路徑）
```

**4 ADR/spec search/replace churn**：
- ADR-0032 V### references（如有）
- V103/V104 spec 文件名 + spec body V### 引用全改
- Earn governance spec V### refs（如有）
- dispatch_packet §1.4 + §5 D-1 check list 編號

**估算**：30 min（pure mechanical search/replace），可派 R4 + TW 並行 sub-agent

**PA verdict**：⚠️ PM 拍板後即可解除 1A-schema dispatch 阻塞

### 仲裁項 2：C10 工時 90-130 hr 是否回滾為 65-85 hr

**衝突來源**：
- dispatch_packet §2.1 寫 Sprint 1A `90-130 hr`（per v57 executability audit + 9/14 agent CRITICAL 共識）
- BB C6 verdict §E `65-85 hr`（推翻 v57 audit Risk 1 BLOCKED claim 後）

**PA 建議**：
- **不全回滾**為 65-85 hr，因為 v57 audit 的 90-130 hr 也含 GUI 8-12 hr（A3 H1）+ ADR draft buffer + spec land + 4 sensor pre-review，不只是 §6 liquidation writer 的 +50 hr
- **修正**為 `75-105 hr`（中間值）+ 明文說明依據：`§6 liquidation writer per BB C6 PROOF 為 wash 而非 +50 hr 反估；§4 Earn read-only per BB 18-25 hr；§8 sensor 含 ADR-0033 落地後 35-45 hr；GUI 8-12 hr；buffer 5-10 hr`
- **Y1 total 1,295-1,740 hr 上修不回滾**（含 GUI/TW/LLM buffer，與 §6 工時無關）

**PA verdict**：⚠️ PM 拍板 75-105 hr 中間值；保留 90-130 hr 為上界（含 unknown unknown buffer）

### 仲裁項 3：C8 Earn governance spec §4 finalize 為條件 A（HIGH）

**理由**：BB C4 verdict 已明示 (a) API exists demo + live；CC spec §4.2 條件 A 內容（demo 環境 `OPENCLAW_ALLOW_MAINNET` 不適用 / live 環境強制）為合理路徑

**PA 建議**：
- dispatch 前 30 min 派 CC sub-agent finalize spec §4（複製 §4.2 內容到主 §4，刪 §4.3/§4.4 placeholder）
- 補 CC spec related ADRs typo（ADR-0030 → ADR-0032）

**PA verdict**：⚠️ PM 拍板 finalize；不阻塞 Sprint 1A 派發但建議 Sprint 1A dispatch 前 30 min 完成

### 仲裁項 4：Apple Silicon CI clippy -D warnings 處理

**選項**：
- A. dispatch_packet §3.1 加 `-A clippy::too_many_arguments -A clippy::too_many_lines` 軟強制（current state allow）
- B. 派 E1 並行 clean 17 既有 clippy errors（P2-clippy-cleanup ticket Sprint 1A 期間並行）

**PA 建議**：**A + B 雙軌**
- A 立即生效（dispatch_packet patch）
- B 拆 P2 ticket Sprint 1A 期間 ~4-8 hr 並行 clean 17 errors
- Sprint 1B 後正式啟用 `cargo clippy -- -D warnings`

**PA verdict**：⚠️ PM 拍板雙軌；不阻塞 Sprint 1A 派發

---

## §7 dispatch verdict 與 next step

### 7.1 PA dispatch readiness final verdict：**NEEDS-PM-ARBITRATION**

- **READY-TO-DISPATCH**（technical complete）：1A-gov / 1A-sensor / 1A-earn 三 track
- **NEEDS-PM-ARBITRATION**：1A-schema（V### re-number）+ Apple Silicon CI clippy 修正 + 工時衝突 + Earn spec §4 finalize（共 4 仲裁項）
- **NEEDS-OPERATOR-DECISION**：1A-gui tab 歸屬決策（H2）

### 7.2 dispatch sequencing 建議

**D+0 PM 仲裁 4 項 + operator 拍板 1 項**（預計 1-2 hr）：
1. PM 仲裁項 1：V### re-number 路徑 A vs B
2. PM 仲裁項 2：C10 工時 75-105 hr 中間值（或保留 90-130 hr 上界）
3. PM 仲裁項 3：Earn governance spec §4 finalize 為條件 A + typo patch
4. PM 仲裁項 4：Apple Silicon CI clippy 雙軌（軟強制 + P2 ticket）
5. operator 拍板：tab 歸屬 H2 + OpenClaw API key 發行日 verify

**D+0~D+1 並行 patch（30 min-2 hr）**：
- ADR-0032 cross-ref 補 V103 + earn_governance spec（5 min）
- Earn governance spec typo patch ADR-0030 → ADR-0032（5 min）
- dispatch_packet §3.1 Apple Silicon CI clippy 軟強制（15 min）
- dispatch_packet §2.1 工時 patch（per 仲裁項 2）（15 min）
- V### re-number 全 spec/ADR search-replace（30 min，per 仲裁項 1）

**D+1 正式 dispatch 5 並行 track**

### 7.3 Sprint 1A → 1B gate 前置條件 watch

- V103（或 V101/V102 per 仲裁 1）land + healthcheck `_sqlx_migrations head = V104` (或 V102 per 仲裁 1)
- Earn APR recorder 24h 真有 row
- 12 個 healthcheck（per CC Earn governance spec §5.4 + §6.4 新增 [earn-1..5]）全 PASS
- 4 NEW sensor secret slot infra（per H3）land + outbound 域名白名單寫 RiskConfig

### 7.4 三 ready-to-dispatch track 詳細派工建議（PM 收到仲裁拍板後可直接派）

#### 1A-gov（25-30 hr / D+0~D+3）
- Owner：TW（ADR cross-ref + docs/README.md index）+ CC（governance spec finalize）+ FA（cross-ref verify）
- Deliverables：ADR-0032 cross-ref patch + Earn spec §4 finalize + dispatch_packet patch + docs/README.md ADR-0021..0033 index 補
- Sub-agent dispatch：可派 3 並行（TW patch / CC finalize / R4 index）

#### 1A-sensor（35-55 hr 修正後 / D+1~D+7）
- Owner：BB（4 sensor pre-review API + scope）+ E1×4 並行 + E2×2 review + E5 baseline profiling
- Deliverables：market.liquidations healthcheck（C6 PROOF wash + buffer 接線）+ Bybit options chain recorder + Binance MD-only WS + Tokenomist trial + Macro calendar
- Sub-agent dispatch：4 並行 E1（每 sensor 1 個 E1）+ 2 E2 並行 review + BB 集中 review

#### 1A-earn（12-18 hr / D+1~D+3）
- Owner：BB（endpoint + scope verdict 已 land）+ E1（read-only API client）+ E3（secret slot infra）
- Deliverables：Bybit Earn API APR + product + position read-only recorder + external sensor secret slot infra + Earn APR readonly viewer mockup（與 1A-gui 並行）
- Sub-agent dispatch：可派 2 並行（E1 client / E3 secret slot）

---

## 附：核驗用 Bash 證據（PA 親自跑）

```bash
# 1. Apple Silicon CI cargo check PASS（12 sec）
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
cargo check --target aarch64-apple-darwin 2>&1 | tail -5
# → Finished `dev` profile [unoptimized + debuginfo] target(s) in 12.20s

# 2. Apple Silicon CI cargo clippy FAIL（17 errors）
cargo clippy --target aarch64-apple-darwin -- -D warnings 2>&1 | tail -3
# → error: could not compile `openclaw_core` (lib) due to 17 previous errors

# 3. SCRIPT_INDEX 格式既存 + 179 行
wc -l /Users/ncyu/Projects/TradeBot/srv/helper_scripts/SCRIPT_INDEX.md
# → 179 lines

# 4. V101/V102 migration SQL 未 land（PA C9 PG dry-run confirm）
ls /Users/ncyu/Projects/TradeBot/srv/sql/migrations/V10*
# → no matches found

# 5. Rust LeaseScope enum 4 variants（無 EarnStake/EarnRedeem）
grep "^    [A-Z]" /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_core/src/lease_scope.rs | head -5
# → TradeEntry / TradeExit / PositionAdjust / CanaryStagePromotion

# 6. Rust OrderIntent struct 無 IntentType enum 字段
grep "pub.*intent_type\|enum.*IntentType" /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/mod.rs
# → 0 hits（CC Earn governance spec §3.1 IntentType enum 是「概念性 placeholder」）
```

---

**PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md**
