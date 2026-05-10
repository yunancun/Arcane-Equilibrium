# P1-CANARY-COHORT-FREQ-23 — Cohort Frequency Cap + Invariant 23 Spec

**Status**: PA SPEC DRAFT 2026-05-10 ｜ Owner: PA design / E1 IMPL / E2+E4 review
**對應 dispatch**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.5 W5 P1 list
**對應 AMD**: AMD-2026-05-09-03 graduated canary default §2.2 + §2.4 + §4.2
**對應 invariant table**: §二 16 根原則 + §5.4 監督 invariant 22（funding_arb dormancy）→ 新增 invariant 23
**對應 healthcheck**: 新 `[63] check_cohort_freq_cap`

---

## 1. Background + Trigger

CC 在 Sprint N+1 dispatch v3 invariant audit 揭露 **22 invariant gap** — AMD-2026-05-09-03 §2.4 寫「cohort 切換 = 重置觀察期 timer」但**未寫**：

- 同一 (strategy × symbol × environment) cohort 在 30d 內可重新進入 Stage 1 幾次？
- 反復 demote → promote → demote 循環是否被偵測？
- 若 cohort N 進入 Stage 1 後 7d 內 demote，第 N+1 次再進可否「reset wall_clock 觀察期重來」？

**核心風險**：缺 frequency cap 會導致 cohort symbol 無限 retry → 殺 sample size pool（每 retry 都吃 24h+ wall-clock 但只累積稀疏 entry_fills）→ §3.3 W3 第一個 cohort 觀察期可能被「retry 雜訊」污染 → graduated canary state machine 失效。

**真實案例對齊**：W7 baseline ma_crossover INXUSDT hot loop 揭露 strategy 可在 1m 內發 2319 reject → 若同 strategy 進 Stage 1 cohort，第一波 entry_fills 可能 ≥10 但全是 hot-loop 噪音；demote 後若無 freq cap，operator 可立刻 retry 同 cohort，hot loop 再生。

---

## 2. Cohort Frequency Cap Rule（寫死）

### 2.1 規則

```
∀ cohort C = (strategy_X, symbol_Y, environment_E):
    在任何 rolling 30d window 內，C 進入 Stage 1 的次數 ≤ 2
    違反 → 第 3 次（含）以後進入需 PA + QC 雙人 sign-off + Decision Lease
```

「進入 Stage 1」定義 = `governance.canary_stage_log` 寫一筆 `to_stage=1 AND from_stage=0`（含 `manual_promote` + `auto_promote`）。

### 2.2 Cohort identity

cohort 比對 key = `(cohort_strategy, cohort_symbol, environment)` tuple。**任一不同** → 視為不同 cohort（如 `(grid, BTCUSDT, demo)` 與 `(grid, BTCUSDT, paper)` 是兩 cohort，各自獨立計算 cap）。

### 2.3 Window 計算

`current_ts_ms - 30 * 86_400_000` 內 `governance.canary_stage_log` 條目 `to_stage=1 AND from_stage=0` 的 row count。

```sql
SELECT COUNT(*) AS stage_1_entries_30d
FROM governance.canary_stage_log
WHERE cohort_strategy = $1
  AND cohort_symbol = $2
  AND environment = $3
  AND to_stage = 1
  AND from_stage = 0
  AND transitioned_at_ms >= $4 - (30 * 86400000);   -- $4 = current_ts_ms
```

如 ≥ 2 → 第 3 次進入需走 §3 override SOP。

---

## 3. Override Condition（PA + QC 雙人 sign-off）

第 3 次（含）以後進入 Stage 1 必走以下 SOP：

1. **operator 在 Settings tab 點 "Override Cohort Freq Cap"** → IPC `patch_risk_config` 帶 `override_cohort_freq_cap=true` + `cohort_strategy`/`cohort_symbol`/`environment` + `override_reason` (free text ≥ 50 char)
2. **PA review** 在 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/YYYY-MM-DD--cohort_freq_override_<C>.md` 寫評估報告（含 retry 必要性 + 預期 evidence + risk acceptance）
3. **QC review** 在 `srv/docs/CCAgentWorkSpace/QC/workspace/reports/YYYY-MM-DD--cohort_freq_override_<C>.md` 從統計獨立性視角 review（避免「retry 即 selection bias」）
4. **PA + QC 都 APPROVE** + operator 二次點 "Confirm Override" → IPC 觸 `LeaseScope::CanaryStagePromotion` Decision Lease（TTL 60s）+ override_lease_id
5. **`governance.canary_stage_log` row 寫入** `transition_kind='manual_promote_override'` + `decision_lease_id=<override_lease_id>` + `reason` 含 PA report path + QC report path

未走完 1-5 → IPC reject，cohort retain Stage 0；`[63]` healthcheck 標 `cohort_freq_violation_attempted`。

---

## 4. Tracking Mechanism

### 4.1 PG persistence

擴充 `governance.canary_stage_log`（已 in AMD-2026-05-09-03 §4.2）— `transition_kind` 加 enum value `'manual_promote_override'`（V086 sql migration patch；ALTER TABLE 不需新 column，只擴 CHECK constraint allowed values）。

新建 governance audit log table（V086 same migration）：

```sql
CREATE TABLE IF NOT EXISTS governance.cohort_freq_cap_attempts (
    id BIGSERIAL PRIMARY KEY,
    attempted_at_ms BIGINT NOT NULL,
    cohort_strategy TEXT NOT NULL,
    cohort_symbol TEXT NOT NULL,
    environment TEXT NOT NULL,
    stage_1_entries_30d INT NOT NULL,           -- 觸發時的 30d 計數
    cap INT NOT NULL DEFAULT 2,
    outcome TEXT NOT NULL,                       -- 'allowed' | 'rejected_no_override' | 'allowed_via_override'
    override_lease_id TEXT,                      -- nullable; allowed_via_override 必填
    pa_report_path TEXT,                         -- nullable; override 路徑
    qc_report_path TEXT,                         -- nullable; override 路徑
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cohort_freq_cap_attempts_cohort_time
    ON governance.cohort_freq_cap_attempts (cohort_strategy, cohort_symbol, environment, attempted_at_ms DESC);
```

Guard A/B/C + Linux PG dry-run 強制（per CLAUDE.md §七）。

### 4.2 Audit chain

每次 cohort entry attempt → 寫一筆 `governance.cohort_freq_cap_attempts` row（無論 outcome）。`[63]` healthcheck 對 `outcome='rejected_no_override'` 24h count 監測 alert。

---

## 5. Invariant 23 Wording

**新 invariant 23** — Cohort Frequency Cap Stability（land `srv/docs/decisions/DOC-01_..._V2.md` §5.4 補件 + AMD-2026-05-10-06）：

> **Invariant 23 Cohort Frequency Cap**：在任何 rolling 30d window 內，同一 (strategy, symbol, environment) cohort 進入 graduated canary Stage 1 的次數 ≤ 2 次。第 3 次（含）以後進入必須走 PA + QC 雙人 sign-off + `LeaseScope::CanaryStagePromotion` Decision Lease + audit log row。違反 = `[63]` healthcheck FAIL → cohort retain Stage 0 + incident log。

**對應 §二 16 根原則**：
- 原則 4（策略不繞風控）— freq cap 是 cohort-level 風控
- 原則 6（失敗默認收縮）— 第 3 次 retry 默認 reject，需 explicit override
- 原則 8（交易可解釋）— 每次 attempt + override 都落 audit log
- 原則 16（組合級風險意識）— 防同 cohort 反復進入污染 evidence pool

---

## 6. Healthcheck `[63] check_cohort_freq_cap`

**Cron**：`0 */6 * * *`（與 `[58]` 同期）

**語義**：
1. **Cap 違反偵測**：對所有 active cohort，跑 §2.3 SQL → 若 `stage_1_entries_30d > 2` AND 對應 `governance.canary_stage_log` 最新 row `transition_kind != 'manual_promote_override'` → **FAIL**
2. **Override audit completeness**：`outcome='allowed_via_override'` row 必有非 NULL `override_lease_id` + `pa_report_path` + `qc_report_path` → 任缺 = **FAIL**
3. **Attempt rate alert**：24h `outcome='rejected_no_override'` count > 5 → **WARN**（spec drift signal — 過頻 retry 想繞 cap）
4. **Override rate alert**：30d `outcome='allowed_via_override'` count > 3 → **WARN**（policy too lax 提示）

Exit code：FAIL → exit 1（silent-dead 自動偵測）；WARN → exit 0 + log。

---

## 7. IMPL Scope

### 7.1 Rust（E1-A）

- `rust/openclaw_engine/src/risk_control/canary_promotion.rs`（與 P1-CANARY-STAGE-CRITERIA-1 同檔）— 加 `check_cohort_freq_cap(cohort: &CanaryCohort, override_lease_id: Option<&str>) -> CapVerdict` method
- `rust/openclaw_engine/src/governance/lease.rs` — `LeaseScope::CanaryStagePromotion` 加 `cohort` 字段（複用 AMD-2026-05-09-03 §4.5 提的新 scope）

### 7.2 Python（E1-B）

- `program_code/.../healthcheck/checks_governance.py` — `[63] check_cohort_freq_cap` 加 §6 4 項
- `program_code/.../api/v1/risk_config_routes.py` — `patch_risk_config` 加 `override_cohort_freq_cap` 處理路徑（驗 override_lease_id + pa_report_path + qc_report_path 完整）
- `program_code/.../api/v1/canary_governance_routes.py` (新檔, ~80 LOC) — `POST /api/v1/canary/cohort/check_freq_cap` + `POST /api/v1/canary/cohort/log_attempt`

### 7.3 PG（E1-C）

- 新 migration `V0XX__governance_cohort_freq_cap.sql` — §4.1 兩 ALTER TABLE / CREATE TABLE + Guard A/B/C + Linux PG dry-run

### 7.4 GUI（E1-D, optional W5 內 land OR 留 N+2）

- Settings tab 加 "Cohort Frequency Cap Status" 區塊 — read `governance.cohort_freq_cap_attempts` 顯示最近 30d attempts；override 時顯示 PA/QC report path link
- 不阻塞 IMPL 主路徑（Settings tab GUI 留 N+2 acceptable）

**LOC 估**：Rust ~50 + Python ~140 + SQL ~50 + GUI ~60 (optional) = **~240-300 LOC + ~60 LOC test**。

---

## 8. Acceptance Criteria

1. `[63] check_cohort_freq_cap` 4 項 healthcheck 全 unit test PASS（cap_violation / override_completeness / attempt_rate / override_rate）
2. `governance.cohort_freq_cap_attempts` table sqlx success + Guard A/B/C 全綠
3. `LeaseScope::CanaryStagePromotion` 加 `cohort` 字段後既有 lease IPC 不 break（regression PASS）
4. `POST /api/v1/canary/cohort/check_freq_cap` 對 mock cohort 第 1/2/3 次 entry 返回正確 verdict (`allowed` / `allowed` / `requires_override`)
5. AMD-2026-05-10-06 + invariant 23 wording land DOC-01 §5.4
6. dispatch §0.7 + §6 acceptance gate 加 invariant 23（`22 + invariant 23 全 PASS`）— 已在 dispatch v3.5 寫；本 spec land 後 PA confirm 對齊
7. E2 review confirm `cohort identity` 三元組比對在 Rust + Python + SQL 三處一致
8. E4 regression 驗 cohort C 進 Stage 1 第 1/2/3 次（第 3 次 reject + override SOP success path 全綠）
9. 16 原則 / DOC-08 §12 / 硬邊界 5 項 0 觸碰

---

## 9. Risk + Side Effect

- **與 W3 同窗依賴**：W5 此 spec IMPL 必先 close（spec + AMD + V086 patch land），W3 第 4 次以上 cohort retry 才被機制保護；W3 第 1-2 次 cohort entry 不受影響
- **Race condition**：兩 operator 在 1ms 內同時點 promote → §2.3 SQL 用 `SELECT ... FOR UPDATE` 鎖 cohort row → 第二者 retry 時必看到第一者已 inserted log 計入 30d count
- **Override report path 驗證**：`pa_report_path` / `qc_report_path` 在 IPC 收 string 但**不**驗 path 真實存在（避免 file race）— `[63]` WARN 抓 path 但實際 IMPL 信任 operator + lease 的雙鎖
- **Backward compat**：dispatch v3.5 已寫「invariant 23 全 PASS」入 acceptance gate（§6 #14）— 此 spec land 後字句保持
- **與 invariant 22 互動**：funding_arb 已 retire（per ADR-0018），其 cohort 不會進 Stage 1（§3.5 排除），故 invariant 22 + 23 兩規則互不衝突

---

*PA spec for P1-CANARY-COHORT-FREQ-23, Sprint N+1 W5*
