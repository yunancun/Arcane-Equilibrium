# MIT LG-3 Spec v1 Review — Wave 2.1.5

**Date**: 2026-05-11
**Reviewer**: MIT (Database + ML pipeline audit)
**Scope**: PA spec v1 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md`
**Read-only**: yes (no Write/Edit/E1/commit/TODO/CLAUDE.md changes)
**Boundary**: audit mirror schema + ML data integrity + 5 SoT outbox + time-series CV + data drift；不重 QC math / 不重 BB Bybit endpoint

---

## 1. Verdict

**APPROVE WITH 6 MUST + 3 SHOULD**（**接近 unconditional APPROVE**；6 MUST 多為「PA spec v2 補一句話 / 補一段 schema 子句」級，0 個是「設計缺陷需 redesign」級）。

理由 outline：
- PA spec §4 audit mirror schema 設計 sound，Guard A 覆蓋（V054 lease_transitions + V035 governance_audit_log 兩前置存在性 check），hypertable + index design 對齊既有 V054 / V064 / V080 既有 audit precedent。
- ML pipeline 風險 LOW：spec §9.3 + §15.1 原則 7 明文「supervised_live_audit 不直接餵 ML pipeline」，sub-agent grep 確認無既有 Python/Rust reader pattern。R-4 forward-compat 設計（`alpha_source_id` NULLable）正確但可進一步補欄位。
- 5 SoT outbox 設計符合 lease_transition_writer.rs 既有 pattern（bridge thread / batch / fail-soft retry / fail-closed at buffer overflow），無新 schema pattern。
- 6 MUST 全可在 spec v2 編輯（PA spec v1 → v2 +0.5d）內 land；無 redesign。

---

## 2. A-E 逐條結論

### A. Audit mirror schema (11 columns + 6 補)

#### A.1 Schema design correctness — PASS

| 維度 | PA spec v1 設計 | MIT 評 |
|---|---|---|
| **PK** | `(event_id, created_at)` mirror V054 lease_transitions pattern | ✅ TimescaleDB hypertable 要求 partition key in PK，spec 正確 |
| **Hypertable on `created_at`** | `chunk_time_interval => INTERVAL '7 days'` | ⚠️ MED：V054 用 1-day chunk（高寫入頻率 lease transitions ~50-200 row/day per active 5-Agent）；supervised_live_audit 預估 row 量低（per session ~20 row × 每天少量 supervised session）→ 7-day chunk 可接受但與 V054 不一致；建議 1-day 或 7-day 都 OK，但 PA spec v2 補理由 statement |
| **Sort key** | `created_at DESC` index 4 條（session_id / request_id / action / operator_id 各 + `created_at DESC`） | ✅ 4 個 hot-path partial 不需要，全表 index 對齊 §4.1 |
| **Index 設計** | 4 secondary index + PK | ✅ 與 §db-schema-design-financial-time-series skill `(session_id, ts DESC)` / `(request_id, ts DESC)` 教訓對齊；hot-path query (per session lookup / per operator audit / per action histogram) 覆蓋 |
| **Schema 哲學** | append-only event log（reason_codes TEXT[] 對齊 V035 / V064 governance_audit_log pattern） | ✅ 一致於 lease_transitions + decision_state_changes + governance_audit_log 既有三條 audit 線；無新 schema pattern 引入 |
| **Foreign key vs append-only** | 無 FK（與 lease_transitions / decision_state_changes / governance_audit_log 一致） | ✅ append-only 設計不需 FK；reconcile via JOIN keys (`session_id` / `request_id` / `decision_lease_id`) |
| **NULL-able 設計** | `decision_lease_id NULLable` / `src_state NULLable`（first row）/ `alpha_source_id NULLable`（R-4）/ `cohort_ref NULLable`（W-AUDIT-9 Stage<3） | ✅ 各 NULLable 都有業務語意理由 |
| **`payload JSONB`** | 額外彈性欄 | ⚠️ MED：JSONB 無 schema constraint = future schema drift 風險；建議 PA spec v2 +1 句明文 payload 結構 stable 期內鎖死或 documented contract |

#### A.2 預留欄位完備性

| R-4 / 未來補完 欄位 | PA spec v1 含 | MIT 建議 |
|---|---|---|
| `alpha_source_id` | ✅ 已預留 NULLable TEXT | ✅ ok |
| `cohort_ref` | ✅ 已預留 NULLable TEXT (W-AUDIT-9 Stage≥3) | ✅ ok |
| `strategy_alpha_score` (R-4) | ❌ 未列 | **SHOULD-2**: 建議補 NULLable FLOAT(8) `strategy_alpha_score`（Alpha-bearing strategy 評分 R-4 routing 決策依據）|
| `regime_tag` (regime-aware live) | ❌ 未列 | **SHOULD-3**: 建議補 NULLable TEXT `regime_tag`（R-2 Strategist reframe 配套）|
| `evidence_source_tier` (replay 對齊) | ❌ 未列 | 不需要（supervised_live_audit 與 replay 是 disjoint domain）|

#### A.3 Guard A/B/C check — PASS

| Guard | PA spec v1 涵蓋 | MIT 評 |
|---|---|---|
| **Guard A** (prereq + column existence) | ✅ §4.1 line 386-402：V054 + V035 必存在 RAISE EXCEPTION；但**缺**對 supervised_live_audit 自身已存在情況下的 column required list check（mirror V054 §155-188 14-column required check）| **MUST-1**: PA spec v2 補 Guard A part 2，driver column allowlist (`event_id` / `ts_ms` / `operator_id` / `session_id` / `request_id` / `decision_lease_id` / `engine_mode` / `symbols` / `strategies` / `risk_limits` / `action` / `src_state` / `dst_state` / `result` / `reason_codes` / `alpha_source_id` / `cohort_ref` / `payload` / `created_at`) 19 column 驗 `array_append(v_missing, v_col)` |
| **Guard B** (type mutation) | ❌ N/A (new table no ALTER TYPE)；但**缺 CHECK constraint 顯式 add 段** | **MUST-2**: PA spec v2 補 ADD CONSTRAINT block（mirror V054 line 245-317）：(1) `action` enum 17 值 (2) `result` enum 3 值 (3) `engine_mode` enum 2 值 (4) `ts_ms > 0` sanity；CHECK constraint 加在 IF NOT EXISTS in pg_constraint guard 之內，re-runs no RAISE |
| **Guard C** (index drift) | ✅ §4.1 line 453-460：4 CREATE INDEX IF NOT EXISTS；但**缺 pg_get_indexdef cmpare** 已存在 index 與 spec define 是否一致 | **SHOULD-1**: PA spec v2 補 pg_get_indexdef 比對（mirror schema_guard_template.sql Guard C pattern）防 future drift；但 mirror V054 line 331-338 也未做此驗，PA 一致 ok，列為 SHOULD 而非 MUST |
| **Idempotency** | ✅ §4.4 line 519 + 既有 lease_transition_writer pattern | ⚠️ MED：spec 未明文「migration 跑 2 次第 2 次不 RAISE」AC，建議補 LG3-T4 AC-T4-1a「local psql -f V094 × 2 second run no-op」condition |

#### A.4 Linux PG dry-run mandatory check — PASS

| 項目 | PA spec v1 涵蓋 | MIT 評 |
|---|---|---|
| Mandatory clause | ✅ §8 LG3-T4 AC-T4-2「Linux PG dry-run 必驗（per `feedback_v_migration_pg_dry_run.md`）」+ §9.3 MIT review 列項 + §16 風險評級「Linux PG dry-run mandatory」 | ✅ 三處重複登記，0 缺漏 |
| **何時做** | spec v1 未明文 dispatch | **MUST-3**: PA spec v2 補 §13.4 Wave 2.4 IMPL phase 加一句「LG3-T4 V094 sub-task：Mac 端 IMPL → push Linux 端 dry-run × 2 round → reject if any RAISE / orphan row / sqlx checksum drift → 再進 E2 / E4」；對齊 V055 / V083+V084 既有 SOP precedent |
| `bin/repair_migration_checksum` SOP | ❌ 未提 | **MUST-4**: PA spec v2 補 §4.1 注釋一行：「V094 file edit 後若 DB 已 apply 過手動 `psql -f` 路徑，必跑 `bin/repair_migration_checksum` 或 unset OPENCLAW_AUTO_MIGRATE=1 重 apply」（V083 + V084 同樣 SOP，per `project_2026_05_02_p0_sqlx_hash_drift.md`）|

#### A.5 Append-only event log philosophy — PASS

| 對照 | lease_transitions (V054) | decision_state_changes (V064) | governance_audit_log (V035) | **supervised_live_audit (V094 new)** |
|---|---|---|---|---|
| Hypertable | yes (1-day chunks) | yes | yes | yes (7-day) |
| `engine_mode` CHECK | 5-value (paper/demo/live_demo/live_mainnet/shadow) | TEXT(no CHECK) | n/a | 2-value (live/live_demo) — **嚴格** |
| Append-only | yes (PK 唯一) | yes | yes | yes |
| `reason_codes TEXT[]` | yes | n/a (`details JSONB`) | yes | yes |
| PK partition key | `(transition_id, created_at)` | `(transition_id, created_at)` | `(audit_id, created_at)` | `(event_id, created_at)` |
| **CHECK constraints** | profile + to_state + engine_mode + ts_ms > 0 | n/a | event_type CHECK 21-value | **缺**（per MUST-2）|

**結論**：PA 設計 100% 對齊既有 audit precedent 三條，**無新 schema pattern 引入**。唯一 outstanding = MUST-1 / MUST-2（CHECK constraint）+ Hypertable chunk size justify。

#### A.6 UPDATE / 寫操作哲學

| 行為 | PA spec v1 | MIT 評 |
|---|---|---|
| INSERT only? | ✅ 全部 SM transition flow 都是 audit row INSERT | ✅ append-only |
| UPDATE existing row? | ❌ 0 path | ✅ ok |
| DELETE / TRUNCATE? | ❌ 0 path | ✅ ok（與 V054 retention TODO 一致）|

---

### B. ML pipeline data integrity — PASS

#### B.1 Downstream ML training 影響

sub-agent grep 確認 (`/Users/ncyu/Projects/TradeBot/srv` `--include="*.py" --include="*.rs"` 全表掃描):
- `lease_transitions` 只在 (1) 既有 writer (`lease_transition_writer.rs`) (2) tests (`lease_flag_flip_e2e.rs`) (3) healthcheck reader (`checks_agent_spine.py`) 路徑 — 無 MLDE/scorer/LinUCB/DreamEngine ingest
- `decision_state_changes` 只在既有 writer + healthcheck reader
- `supervised_live_audit` 在 v1 spec 之前**完全不存在**

**ML pipeline target leakage 風險評估**：

| Stage | leakage 風險 |
|---|---|
| MLDE shadow recommendations | 無 (consume `learning.mlde_shadow_recommendations` view 不 JOIN supervised_live_audit) |
| Scorer trainer (regression) | 無 (consume `learning.decision_features` view) |
| LinUCB online learner | 無 (consume `learning.directive_executions`) |
| Dream Engine | 無 (consume `replay.calibrated_replay` + `learning.dream_*`) |
| Thompson sampling / Optuna | 無 (consume `learning.experiment_ledger`) |

**結論**：spec §9.3 + §15.1 原則 7 明文「ML 不讀 supervised_live_audit」**符合 grep 結果，0 leakage path**。

但 PA spec v1 缺**1 個顯式安全護欄**：

| MUST-5 | description |
|---|---|
| schema-level safety | PA spec v2 補 §4.1 注釋一行：「**Non-training surface invariant**: `learning.supervised_live_audit` 是 operator-bound control plane audit；E3 安全審計加 grep rule reject 任何 `SELECT ... FROM learning.supervised_live_audit` 出現在 `program_code/**/ml/**`, `program_code/**/training/**`, `program_code/**/learning/**` 路徑 outside `program_code/**/healthcheck/**` + `helper_scripts/db/passive_wait_healthcheck/**`」對齊既有 CLAUDE.md §九 `replay.simulated_fills synthetic_replay` 防護 SOP |

#### B.2 Feature engineering leakage 風險 (per `feature-engineering-protocol`)

| 6 維 leakage | PA spec v1 風險 |
|---|---|
| **Look-ahead** | 不適用 (audit table 不參與 ML training) |
| **Target leakage** | 不適用 |
| **Survivorship** | 不適用 |
| **Cross-section** | 不適用 |
| **Time-zone** | ✅ `ts_ms BIGINT` ms-epoch-UTC + `created_at TIMESTAMPTZ` PG 自帶 TZ；無模糊 |
| **Resample boundary** | 不適用 |

**結論**：因 audit table 在 ML pipeline 外，6 維 leakage 不適用。MIT pushback **無**（spec §9.3 MIT review 預設答案「ML 不讀 supervised_live_audit；payload 為 operator-side audit context」**正確**）。

#### B.3 時序 CV 設計 (per `time-series-cv-protocol`)

不適用（audit table 不參與 ML training）。

#### B.4 Data drift monitoring (per `data-drift-detection`)

PA spec §10 既有 healthcheck `[59]` / `[60]` / `[61]` 設計覆蓋 audit table 三維監控：
- `[59]` invariant (5 SoT consistency)
- `[60]` approval rate health (24h `approval_rejected/approval_granted > 50%` → WARN — 高 reject ratio detection)
- `[61]` freshness + reconcile_force_close 異常頻率 (`> 3` WARN / `> 10` FAIL split-brain epidemic)

**MIT 評估 data drift 監控**：

| MIT 應監控指標 | PA spec v1 涵蓋 | 評 |
|---|---|---|
| SM state transition frequency drift | ❌ 未列 | **SHOULD-1 (extends from A.3)**: 補 `[59]` 加 sub-check session_max_duration / drawdown_breach / kill_api 三種 transition 頻率 baseline + KS test p-value 對比上週 |
| session_override 改動率 KS test | ❌ 未列 | 不必（session_override 由 operator-bound approval 一次性鎖定，runtime 不變）|
| `reconcile_force_close` PSI | ✅ `[61]` last 24h count > 3 / > 10 階梯 gate | ✅ ok |
| approval rate drift | ✅ `[60]` 50% threshold | ✅ ok（但 SHOULD-1 補 baseline reference window）|

**結論**：data drift 維度設計**符合**核心需求。SHOULD-1 補強 baseline reference window 對齊 `data-drift-detection` skill PSI / KS test 推薦 framework。

---

### C. 5 SoT outbox 設計 — PASS

#### C.1 Outbox pattern 正確性

PA spec §4.3 dual-write outbox 設計 mirror 既有 lease_transition_writer.rs pattern：

```
1. Lock self.state mutex
2. Validate (src, event) in LEGAL_TRANSITIONS
3. Compute next state + audit row
4. Push audit row to mpsc::Sender<SupervisedLiveAuditMsg> (bounded 1024)
   - try_send; if full → log ERROR + drop transition (fail-closed; SM stays in src state)
5. If audit send OK → mutate self.state to next
6. Release lock
7. Notify reconciler + Python SM mirror via IPC broadcast
```

**MIT 評**：

| 維度 | PA spec v1 設計 | MIT 評 |
|---|---|---|
| **Atomic SM + audit** | audit-first（push to channel）→ mutate state；buffer 滿 → fail-closed SM 不 advance | ✅ 正確；audit-precedes-state-mutation 確保「SM 已 advance 但 audit 沒寫」不可發生 |
| **Buffer size** | bounded 1024 | ⚠️ MED：相對 lease_transition_writer 預設 size 對比可考慮 explicit cite；7-day chunk 對應預估 row volume（per session ~20 row × demo session count），1024 過大不浪費，<10% 警戒線；ok |
| **PG transaction 同步?** | ❌ no | ✅ 正確設計（§4.3 line 515 解釋「SM transition in-memory state mutation，無 PG IO；hot path 不引 PG round-trip」） — 對齊原則 14 零外部成本 |
| **Fail-soft retry** | 3 次 → engine shutdown signal | ✅ §4.4 line 520 mirror existing `_REGISTER_IDEM_CACHE` 重啟丟 cache 既有 pattern |
| **PG down 不阻 SM transition** | yes (buffered pending vec 10k cap) | ⚠️ MED：10k row pending vec 過大可能 OOM 風險 (10k row × ~2KB JSONB payload = ~20MB) — Mac dev 128GB 統一記憶體無影響，Linux 是 trade-core 16GB 也 ok；不阻 sign-off |
| **Bridge thread std::sync→tokio** | yes | ✅ mirror lease_transition_writer.rs |

#### C.2 Reconcile correctness (5 SoT)

5 SoT 對賬:
- #1 Rust SM (`Arc<RwLock<SupervisedLiveSm>>`)
- #2 Python SM mirror (`supervised_live_state.py` + JSON disk)
- #3 `authorization.json` ($OPENCLAW_SECRETS_DIR/live)
- #4 `learning.lease_transitions` (V054)
- #5 `learning.supervised_live_audit` (V094 — **SoT 真值權威**)

**對賬規則** (§2.2):
- 每 30s reconcile loop
- 4 derived view（#1-#4）與 #5 audit table 比對
- disagree → reconcile_force_close transition
- 連 2 cycle 防 false-positive

**MIT 評**:

| 維度 | PA spec v1 設計 | MIT 評 |
|---|---|---|
| **SoT 真值權威** | #5 supervised_live_audit | ✅ 對齊 db-schema-design-financial-time-series skill「append-only audit log 為 SoT」教訓 |
| **30s interval** | 非 hot path | ✅ ok |
| **Leader election** | local process-wide singleton | ✅ ok (engine binary 單一 process) |
| **Schema 相互可比** | #1/#2/#3/#4 各 projected_state 計算 → 與 #5 audit row last action map 比對（per §1.2 inverse table）| ✅ 設計清晰，但**未列 inverse map table 公開定義** |
| **MUST-6** | **MUST**：PA spec v2 補 §2.2 inverse map 完整表（17 action × 7 state，map projected_state from audit action）— 否則 IMPL 隱性決定可能不一致 |
| **False-positive 防衛** | 連 2 cycle disagree 才升 force_close (§2.5) | ✅ ok |

#### C.3 Data lineage

從 audit → 上游 reconstruction 可行性:

| query | PA spec v1 covered | MIT 評 |
|---|---|---|
| `learning.supervised_live_audit WHERE session_id = $1 ORDER BY created_at` | ✅ index `idx_supervised_live_audit_session_id (session_id, created_at DESC)` | ✅ ok |
| JOIN `learning.lease_transitions ON decision_lease_id = lease_id` | ✅ both tables have `decision_lease_id` / `lease_id` matching | ✅ ok |
| JOIN `authorization.json` snapshot (read on demand) | ✅ §2.1 #3 既有 LiveAuthWatcher 路徑 | ✅ ok |
| JOIN `governance.canary_stage_log ON cohort_ref = cohort_id` (W-AUDIT-9) | ✅ `cohort_ref` 預留 + §1.2 mention | ✅ ok |
| JOIN ML decision_features for **未來** alpha source attribution | ❌ 不需要 — non-training surface | ✅ 設計正確 (B.1 confirms) |

---

### D. ML pipeline maturity audit (per `ml-pipeline-maturity-audit`)

LG-3 supervised_live_audit 在 ML pipeline 5 階段 + 4 維度 grid 中的位置:

| Component | Writer spawn | Consumer exists | Row accumulation | Decision impact | Stage |
|---|---|---|---|---|---|
| **supervised_live_audit V094** | future (LG3-T4 IMPL) | reconciler (`reconciler.rs`) + healthcheck `[59]/[60]/[61]` | 0 (spec phase) | reconcile_force_close → SM CLOSED transition (operator-bound, 非 ML) | **Foundation (spec phase) → Skeleton (post-IMPL)** |

**結論**：LG-3 audit **不是** ML pipeline component。Stage 評級套到 ML pipeline 5 階段 framework 是 **categorical mismatch**：
- 它是 **control plane audit**（與 lease_transitions / decision_state_changes / governance_audit_log 同族）
- 非 **learning surface**
- 非 Foundation / Skeleton / Shadow / Canary / Production 評級對象（這 5 階段 = ML pipeline 專屬）
- 應評為 **「Governance audit foundation table」**（與 W-AUDIT-9 governance.canary_stage_log 同類）

PA spec §non-scope 列明:
> ❌ R-4 Per-alpha-source Live Promotion Gate（→ W-AUDIT-8g DEFER N+7+，本 spec 為 `alpha_source_id` 留 NULLable 接口而已）

**MIT 確認**：`alpha_source_id NULLable` 是 R-4 forward-compat 唯一接口，**不引入 ML pipeline 訓練責任**。

---

### E. 與既有 ML 6 dead schema (W-AUDIT-4b) 對齊 — PASS

W-AUDIT-4b ML 6 dead schema (V068/V070/V071) 已併入 W-AUDIT-8f (R-3) Hypothesis Pipeline。

**MIT 評估 LG-3 與 W-AUDIT-4b 衝突 / 互補**:

| 維度 | W-AUDIT-4b dead schema | LG-3 supervised_live_audit |
|---|---|---|
| **Schema 類型** | ML learning surface (foundation_model_features / scorer_predictions 等) | Governance control plane audit |
| **生命週期** | 9-12 月內可能 ML pipeline mature 時激活 | 立即 ship (LG-3 IMPL) |
| **使用 ML** | 是 | 否 |
| **R-3 Hypothesis Pipeline 引用** | foundation_model_features / dream_engine / Teacher-Student v0.4 | 不引用 supervised_live_audit |
| **R-4 forward-compat 補完** | per-alpha-source promotion gate | `alpha_source_id NULLable` 預留接口 |

**結論**：LG-3 audit 與 W-AUDIT-4b 完全 disjoint domain，**0 衝突 / 0 互補**。可同期並行 IMPL，無 schema 衝突。

---

## 3. Schema design audit + Guard A/B/C check

### Summary table

| 項目 | PASS / WARN / FAIL | 細節 |
|---|---|---|
| Schema design correctness | **PASS** | hypertable + PK + 4 index + append-only 全對齊既有 audit precedent |
| Hypertable chunk size | **WARN** | 7-day vs V054 1-day 不一致；PA spec v2 補 justify ok |
| Index design | **PASS** | 4 secondary index 覆蓋 hot path (session/request/action/operator) |
| NULL-able 設計 | **PASS** | decision_lease_id / src_state / alpha_source_id / cohort_ref 各有業務語意 |
| **Guard A** (prereq + column existence) | **WARN** | prereq check ✅；missing supervised_live_audit own column allowlist check (MUST-1) |
| **Guard B** (CHECK constraint) | **WARN** | new table no ALTER TYPE 但缺 ADD CONSTRAINT block (MUST-2) |
| **Guard C** (index drift) | **PASS** | 4 CREATE INDEX IF NOT EXISTS ok；pg_get_indexdef 比對 nice-to-have (SHOULD-1) |
| Idempotency | **PASS** | spec mention; AC-T4-1 補 explicit 「× 2 second run」test 即可 |
| Linux PG dry-run mandatory | **PASS** | spec 3 處重複登記 |
| `bin/repair_migration_checksum` SOP | **WARN** | 未提；對齊 V083+V084 / V028-V034 既有 SOP (MUST-4) |
| Append-only event log | **PASS** | 與既有 3 audit table 一致 |
| `engine_mode` CHECK 2-value | **PASS** | live/live_demo 對齊 §3.1 + §4.1 spec |
| `action` enum 17 values | **WARN** | spec column-level CHECK ok 但無顯式 ADD CONSTRAINT IF NOT EXISTS block (MUST-2 涵蓋) |

### Critical findings — 0 blockers

- ❌ 0 個 schema bug
- ❌ 0 個 silent-noop 風險 (V094 Guard A 設計正確)
- ❌ 0 個 ML leakage path
- ❌ 0 個 5 SoT split-brain 邏輯洞
- ❌ 0 個 V### naming conflict (V094 編號正確 - V093 W-AUDIT-9 T4 既有 / V094 LG-3 新)

---

## 4. ML data integrity + leakage risk

### Risk level: **VERY LOW**

| 風險路徑 | 評估 |
|---|---|
| supervised_live_audit ingest 到 ML training? | **❌ NO** (sub-agent grep 確認 + spec §9.3 + §15.1 原則 7 明文) |
| Target leakage? | 不適用 |
| Look-ahead bias? | 不適用 |
| Survivorship bias? | 不適用 |
| Time-zone bug? | **PASS** (ts_ms BIGINT + created_at TIMESTAMPTZ) |
| Resample boundary? | 不適用 |
| Data drift monitoring 覆蓋? | **PASS** (`[59]` / `[60]` / `[61]` 三 healthcheck + SHOULD-1 補 baseline reference) |

### 防護建議 (MUST-5)

PA spec v2 §4.1 補一行明文:

> **Non-training surface invariant**: `learning.supervised_live_audit` 是 operator-bound control plane audit；E3 安全審計加 grep rule reject `SELECT ... FROM learning.supervised_live_audit` 出現在 `program_code/**/ml/**`, `program_code/**/training/**`, `program_code/**/learning/**` 路徑（healthcheck + reconciler 路徑除外）。

對齊既有 CLAUDE.md §九 `replay.simulated_fills synthetic_replay` non-training tier 防護 SOP。

---

## 5. PA spec v2 必補（MUST / SHOULD 分級）

### MUST (6 條 - spec v2 必須含)

**MUST-1**: §4.1 Guard A part 2 加 supervised_live_audit own column allowlist 19-column check（mirror V054 §155-188 pattern）。如 supervised_live_audit 已存在但缺欄位 → RAISE EXCEPTION + `v_missing_cols` array_to_string。

**MUST-2**: §4.1 補完 ADD CONSTRAINT IF NOT EXISTS block（mirror V054 line 245-317 pattern）：
- `chk_supervised_live_audit_action` 17-value CHECK
- `chk_supervised_live_audit_result` 3-value CHECK (ok / rejected / forced)
- `chk_supervised_live_audit_engine_mode` 2-value CHECK
- `chk_supervised_live_audit_ts_ms_positive` `ts_ms > 0` (epoch-0 reject)

每 constraint 套 `IF NOT EXISTS in pg_constraint WHERE conname = '...'` guard，re-runs no RAISE。

**MUST-3**: §13.4 Wave 2.4 IMPL phase 加 Linux PG dry-run dispatch SOP 一段：
- Mac 端 IMPL → push commit → Linux 端 dry-run × 2 round → reject if any RAISE / orphan row / sqlx checksum drift → 進 E2 / E4
- 對齊 V055 + V083 + V084 既有 SOP precedent

**MUST-4**: §4.1 注釋頭部補 sqlx checksum 處理一段：
- V094 file edit 後若 DB 已手動 `psql -f` apply 過，必跑 `bin/repair_migration_checksum` 或 `unset OPENCLAW_AUTO_MIGRATE=1` 重 apply
- 對齊 `project_2026_05_02_p0_sqlx_hash_drift.md` V028-V034 既有教訓

**MUST-5**: §4.1 補一行 Non-training surface invariant 注釋 (per §4 of this report):
> supervised_live_audit 是 operator-bound control plane audit；E3 安全審計加 grep rule reject `SELECT ... FROM learning.supervised_live_audit` 在 ML/training/learning path（healthcheck + reconciler 路徑除外）

對齊既有 CLAUDE.md §九 `replay.simulated_fills synthetic_replay` non-training tier 防護 SOP。

**MUST-6**: §2.2 補 inverse map 完整表（17 action × 7 state），map audit row last `action` → projected_state：
- `request_registered` → REGISTERED
- `approval_granted` → ACTIVE_PRE_AUTH
- `approval_rejected` → CLOSED
- `auth_file_observed` → ACTIVE_AUTHED
- `auth_file_invalid` → CLOSED
- `lease_acquired` → ACTIVE_TRADING
- `lease_released` → ACTIVE_AUTHED
- ... 等 17 條完整 mapping

否則 IMPL 階段 sub-agent 隱性決定可能不一致；reconciler.rs 跟 reconciler_python.py 兩 SM mirror 對 audit→state 解讀不一致 = split-brain epidemic 風險。

### SHOULD (3 條 - spec v2 建議含)

**SHOULD-1**: §10 `[59]` invariant healthcheck 補 sub-check 對 SM state transition frequency baseline + KS test p-value (per `data-drift-detection` skill PSI / KS framework)：
- last_24h_transition_count vs trailing_7d_average
- KS p < 0.01 持續 1h → WARN
- 對齊 §10 already 既有 `[61]` `> 3 / > 10` 階梯 gate 設計風格

**SHOULD-2**: §4.1 schema 加 NULLable `strategy_alpha_score FLOAT(8)` column — R-4 forward-compat (Alpha-bearing strategy 評分 routing 決策依據)。

**SHOULD-3**: §4.1 schema 加 NULLable `regime_tag TEXT` column — R-2 Strategist reframe + regime-aware live 配套。

### MUST/SHOULD count summary

- **MUST**: 6 條 (4 schema-side V094 SQL 修補 + 1 Linux PG dry-run SOP + 1 §2.2 inverse map)
- **SHOULD**: 3 條 (drift baseline + 2 future-proof column)
- **REJECT (REQUEST CHANGES)**: 0 條 (spec 不需 redesign)

---

## 6. 結論 + 三方並行 review 配合

### MIT 視角 verdict: **APPROVE WITH 6 MUST + 3 SHOULD**

PA spec v1 audit mirror schema 設計 sound，ML data integrity 風險 LOW，5 SoT outbox 對齊既有 lease_transition_writer pattern，0 schema bug / 0 ML leakage path / 0 V### naming conflict。

6 MUST 全 schema-side 「PA spec v2 編輯 1-2 段 SQL/注釋」級工作，**0 個** 需要 redesign 設計核心。

### PA spec v2 預計工期

per PA spec §13.3「PA spec v2 final (0.5d 收 review feedback)」估計：
- MIT 6 MUST = ~1-2 hour PA edit
- QC + BB MUST 收聚後共計 ~0.5d ok
- 不超 PA spec §13.3 0.5d window

### 與 QC / BB 預期重疊區

| 項目 | MIT 主負 | QC 主負 | BB 主負 |
|---|---|---|---|
| V094 schema correctness | ✅ | - | - |
| Guard A/B/C completeness | ✅ | - | - |
| Linux PG dry-run SOP | ✅ | - | - |
| ML data integrity | ✅ | - | - |
| 5 SoT outbox 設計 | ✅ | partial (math consistency invariant) | - |
| min-only invariant 數學 | partial (LG3-T5 IMPL ref) | ✅ | - |
| Bybit V5 endpoint constraints | - | - | ✅ |
| HMAC envelope + authorization.json renew | - | - | ✅ |

**0 重疊衝突**；MIT 6 MUST + QC / BB MUST 可獨立 land。

---

MIT AUDIT DONE: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-11--lg3_spec_mit_review.md`
