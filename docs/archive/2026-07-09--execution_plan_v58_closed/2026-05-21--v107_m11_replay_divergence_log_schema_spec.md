---
spec: V107 — M11 Replay Divergence Log Schema (Hypertable Mandatory)
date: 2026-05-21
author: MIT (full DDL spec; lifts placeholder from earlier same-day frontmatter)
phase: v5.8 Sprint 1A-β schema prerequisite CRITICAL deliverable
status: SPEC-FULL-V0(MIT 起草;待 PA C9 Linux PG dry-run 實測補資料 + Sprint 1A-β reviewer 對齊後 SPEC-FINAL)
sprint: Sprint 1A-β (DESIGN phase; IMPL Phase A Sprint 3 W15-18 nightly job; Phase B Sprint 8 W30-33 down-stream integration)
size estimate: 100-140 LOC SQL (CREATE TABLE 1 hypertable + 4 indexes + multi-ENUM CHECK + Guard A/C + compression + retention + materialized view) + 80-120 hr E1 IMPL (含 Linux PG dry-run x 2 round; healthcheck wiring deferred to Sprint 1B; writer 接線 Sprint 3 W15-18 M11 nightly job Phase A)
depend on:
  - V096 boundary (TimescaleDB extension; drop dead learning tables)
  - V098 (learning.governance_audit_log; M11 H-11 audit cross-ref;2026-05-22 PA reconcile §4 — 真實 schema 表名 `learning.governance_audit_log` per V035 baseline)
  - V103 (learning.hypotheses; hypothesis-grounded replay 用 hypothesis_id 寬 FK reference; nightly hygiene 走 NULL)
  - V108 (M9 A/B test schema; γ; bi-directional cross-ref via ab_test_id in evidence_json) — placeholder FK
  - V113 (M7 decay schema; M7 detector read-only pull V107 last 14d) — placeholder FK
depended by:
  - V109 (M8 anomaly cross-ref; CR-7 §5 4 級 severity 對齊 — CRITICAL divergence 同步寫 V109 anomaly event)
  - V113 (M7 reference; divergence signal 餵 M7 single decay authority)
  - V112 (M1 LAL; CRITICAL → M3 HEALTH_WARN → LAL 1/2 auto-approve 暫停; cross-ref query 非 FK)
  - V108 (M9 ab_results; A/B test 評估 cadence 內 V107 不 clean → conclusion 改 inconclusive; bi-directional cross-ref)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M11 Replay
  - srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md (PA module DESIGN 619 行;本 spec column 行為 derive)
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md (CR-14 已 land; M11 治理邊界 + 3σ 統計推導)
  - srv/docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md (M11 三級 threshold + M7 dedup contract + DECAY_ENFORCED rename)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §6 cross-V### dependency graph + H-11 反向 attack 6 條 mitigation
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (940 行 baseline; §14 EXTEND 5 audit field 範式)
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md (Linux PG dry-run protocol 範式;PG conn = 127.0.0.1:5432 trading_admin/trading_ai)
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md (姊妹 hypertable spec; 同 MIT batch; 14 section 結構參照)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + partial index 範式)
  - srv/sql/migrations/templates/schema_guard_template.sql (Guard A/B/C template)
scope: design / spec only — 不寫 V107.sql 實檔, 不在 Mac 跑 SQL, 不改 Rust/Python M11 replay engine writer, 不執行 PG, 不擴張 M11 module 行為 (PA m11 design spec 已 land 619 行), 不擴張到 V108/V112 schema 細節 (placeholder FK 即可)
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# V107 M11 Replay Divergence Log Schema Migration Spec

## §0 TL;DR

- **V107 新增 1 個 hypertable**:`learning.replay_divergence_log`(M11 nightly counterfactual replay vs live execution divergence audit trail; 每 nightly run 對 7 種 divergence type 偵測產生 row)。
- **17 主要 column + 5 audit field = 22 column 總計** per `m11_continuous_counterfactual_replay_design_spec.md` §3.2 + operator H-11 反向 attack mitigation 字段補強 + V103 §14 EXTEND audit field 範式對齊。
- **7 種 divergence_type ENUM**:`fill_chain` / `position` / `pnl` / `fee` / `liquidation` / `regime` / `risk` (per M11 design spec §4.2 D1-D7)。
- **3 級 severity ENUM**:`NOISE` / `WARN` / `CRITICAL` (per ADR-0038 Decision 3 + CR-7;對齊 M8 anomaly_severity vocabulary;NOISE 不寫 row 由 writer 端 gate;V107 schema 允許 INSERT NOISE 為 debug 用但 production writer 不 emit)。
- **5 級 flag_action_taken ENUM**:`m9_inconclusive` / `m7_decay_candidate` / `m3_health_recheck` / `operator_alert` / `none` (per M11 design spec §5.1 flag-action map 主路由結果)。
- **不含 `auto_demote` / `target_state` / `decay_recommendation` column** (per CR-7 contract — **M7 是 single decay authority**;M11 只發 signal 不發 action;違反 = AC-5 sub-agent PR 拒絕)。
- **H-11 passive Slack 5d unack auto-escalate 字段**:`passive_slack_ack_at TIMESTAMPTZ` NULL — observed_at>5d 且 ack=null → 自動升 M3 HEALTH_WARN (per M11 design spec §8 + dispatch consolidation H-11 反向 attack #6)。
- **Hot index `(strategy_name, symbol, divergence_detected_at DESC)`** + `(severity, divergence_detected_at DESC)` partial WHERE severity IN (WARN,CRITICAL) + `(replay_run_id)` + `(hypothesis_id) WHERE hypothesis_id IS NOT NULL` partial — per M11 design spec hot path query 對齊。
- **Hypertable mandatory**:divergence_detected_at 為 time dim + 7d chunk + 30d compression policy + 90d retention(per ADR-0038 H-22 R4 governance + E5 5.21 hypertable audit;對齊 V106 sister table 範式)。
- **engine_mode CHECK 5 值齊全**(paper/demo/live_demo/live/replay) — 額外加 `replay` 因 V107 row 本身可由 replay engine 寫入(不同於 live trace 寫入路徑);training filter 必 `IN ('live','live_demo')` (per CLAUDE.md §七 + MIT memory baseline);**M11 自身寫入時 engine_mode='replay'** 但 evidence_json 內含原 live trace 的 engine_mode。
- **Cross-V### dependencies**:V096 boundary(TimescaleDB extension)+ V098(learning.governance_audit_log)+ V103(learning.hypotheses hypothesis_id 寬參照)+ V108(M9 ab_test_id 寬參照;γ 待 land)+ V113(M7 m7_decay_signal_id 寬參照;待 land);**所有跨 module 引用採 nullable FK pattern 或 cross-ref query 而非 hard FK** 避免循環依賴 + writer hot path INSERT 過熱。
- **5 audit field** per V103 §14 EXTEND 範式:`created_by` / `created_at` / `updated_by` / `updated_at` / `source_version` — 對齊 ADR-0024-lite Cowork operator-assistant + ADR-0008 Decision Lease audit chain。
- **Materialized view (optional)** `mv_latest_divergence_per_strategy` — A3 Lv 3 GUI Console Banner + monthly review wizard 用 last divergence per strategy × symbol;refresh policy 4h cron(per A3 design)。
- **Sprint 1A-β scheduling**:V107 必先 land(Sprint 1A-β CRITICAL);V113(M7) + V108(M9 γ) + V109(M8) 後續 land 後 Phase B Sprint 8 hookup。V107 stand-alone apply 後 0 row(Foundation stage per MIT pipeline maturity);Phase A Sprint 3 M11 nightly job spawn writer 後升 Skeleton → 累積 baseline 後 Shadow → CRITICAL 觸發 M7 dispatch 後 Canary。
- **Linux PG empirical dry-run mandatory**(per CLAUDE.md §Data, Migrations, And Validation + V055 5-round loop precedent + V083/V084 incident chain)。

---

## §1 Context + 為什麼

### 1.1 v5.8 §2 M11 module 出處 + 動機

v5.8 §2 M11 Continuous Counterfactual Replay module 將 v5.7 baseline 的「Stage 0R replay one-time preflight」升級為 **continuous nightly counterfactual replay**:每晚 02:00-06:00 UTC cron window 內,跑 5 strategy × all live symbols 過去 24h 對比 replay vs live execution → 7 種 divergence type 三級 severity 寫入 V107 表。

per `m11_continuous_counterfactual_replay_design_spec.md` §1.1 三個升級理由:
1. **Silent strategy drift detection** — strategy 在 production 期可能因 hot-reload param 錯、配置漂移、IPC schema 升級遺漏而 silently 改變行為
2. **Infra-induced behavioral change** — IPC tick latency spike / Bybit WS reconnect / cancel-on-disconnect 失效 / fill ack 漏接
3. **Strategy alpha 真實驗證** — P0-EDGE-1 Y1 持續 negative edge 根因之一是「無法區分策略本體 edge 不足 vs production noise 污染」

V107 是 M11 **唯一 write target**(M11 sensor / signal source;不寫 live state)。M11 不可寫:`learning.decay_signals`(由 V113 M7 own) / 改 strategy sizing / 自行 emit demote proposal。

### 1.2 v5.8 §2 M11 與 ADR-0038 + CR-7 dedup contract 約束

per CR-7 single decay authority 紀律:
- M11 是 **sensor**;M7 是 **single decay authority / actuator**
- V107 schema 嚴禁含 `auto_demote` / `target_state` / `decay_recommendation` / `demote_proposal_id` / `decay_stage` / `stage_demoted` column
- AC-5 mandate:grep 上述禁忌字段在 V107 spec + IMPL PR 中 → 0 hit 才 PASS

### 1.3 v5.8 §2 M11 H-11 反向 attack 6 條 mitigation 對應

per `2026-05-21--v58_dispatch_consolidation.md` H-11 反向 attack 6 條,本 V107 schema 對 5 條設計加 mitigation:

| H-11 # | 反向 attack | V107 schema 對應 |
|---|---|---|
| #1 | False positive 噪音灌爆 V107 | severity ENUM 3 級;NOISE 不寫 row(writer 端 gate);WARN+CRITICAL 才入 V107 |
| #2 | Threshold drift 不被偵測 | `baseline_5d_mean` + `baseline_5d_sigma` 在每 row 鎖當下 baseline 值;後續 audit 可重構 threshold derivation |
| #3 | M11 寫入失敗導致 M7 收不到 signal | V107 writer 端 INSERT 失敗 emit M3 HEALTH_WARN(不在 schema 層;Sprint 3 IMPL 期由 writer 處理)|
| #4 | M7 反向 attack 14d × 50% 持續虧 | V107 schema 含 `flag_action_taken='m7_decay_candidate'` 路由標記;M7 detector read 14d 窗 query 走 hot index |
| #5 | M11 + M7 雙寫 race | V107 寫入後 M7 pull (read-only);no double-write;`m7_decay_signal_id` placeholder FK 是 read-only pointer |
| #6 | passive Slack 5d unack | `passive_slack_ack_at TIMESTAMPTZ` NULL column;ack=null + observed_at>5d → 自動升 M3 HEALTH_WARN(writer 端 cron 邏輯;V107 schema 提供 column) |

### 1.4 Cross-V### 影響

| 下游 | M11 觸發路徑 | 是否 FK |
|---|---|---|
| **V113 (M7)** | CRITICAL divergence → M7 strong candidate (14d window 內 ≥ 7d CRITICAL) | 否(`m7_decay_signal_id` BIGINT placeholder FK soft reference;讀取由 M7 detector 主動 pull V107) |
| **V108 (M9 γ)** | A/B test 進行中 + WARN/CRITICAL → variant outcome inconclusive flag | 否(`m9_ab_test_id` UUID placeholder soft reference;bi-directional cross-ref via evidence_json 內 ab_test_id + V108.ab_results.inconclusive_reason write-back) |
| **V109 (M8)** | CRITICAL → M8 anomaly event cross-ref (4 級 severity 對齊 per CR-7 §5) | 否(cross-ref query 走 evidence_json + V109 anomaly_event_id soft pointer) |
| **V112 (M1 LAL)** | CRITICAL → M3 HEALTH_WARN → LAL 1/2 auto-approve 暫停 | 否(cross-ref via M3 health state machine;非 V107 直接 FK) |
| **V103 (hypotheses)** | hypothesis-grounded replay 用 hypothesis_id 標記;nightly hygiene 為 NULL | **可選 nullable FK** `REFERENCES learning.hypotheses(hypothesis_id)` 或 soft reference;本 spec 採 nullable FK(V103 已 land Sprint 1A-α) |

### 1.5 不在本 spec 範圍

- ❌ V107.sql 實檔寫作(E1 IMPL Sprint 3 W15-18 工作)
- ❌ Mac 跑 V107 SQL(必 Linux PG empirical)
- ❌ M11 replay engine writer code(`rust/openclaw_engine/src/m11/replay_divergence_writer.rs`;E1 Sprint 3 工作)
- ❌ Python healthcheck wiring(`helper_scripts/passive_wait_healthcheck.py` 加 `check_replay_divergence_writer()`;Sprint 1B+ 工作)
- ❌ ML training pipeline integration(V107 是 governance / audit 層,非 ML training feature;M11 自身用 V103 hypothesis registry pre-registration 紀律不入 V107 schema)
- ❌ M11 module 行為設計(已由 `m11_continuous_counterfactual_replay_design_spec.md` 619 行 cover)
- ❌ Slack daily digest webhook spec / GUI Banner spec(Phase A Sprint 3 + A3 Sprint 1A-ε 分別處理)
- ❌ V108 / V112 / V113 schema 細節(placeholder FK 即可;各自 V### spec own)
- ❌ M7 / M8 / M9 module 行為(各自 module design spec own)

---

## §2 Schema Design

### 2.1 `learning.replay_divergence_log` 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.replay_divergence_log (
    id                          BIGSERIAL,
    divergence_detected_at      TIMESTAMPTZ NOT NULL,
    replay_run_id               UUID NOT NULL,
    divergence_type             TEXT NOT NULL
                                CHECK (divergence_type IN (
                                    'fill_chain',
                                    'position',
                                    'pnl',
                                    'fee',
                                    'liquidation',
                                    'regime',
                                    'risk'
                                )),
    severity                    TEXT NOT NULL
                                CHECK (severity IN (
                                    'NOISE',
                                    'WARN',
                                    'CRITICAL'
                                )),
    divergence_metric_name      TEXT NOT NULL,
    divergence_value            NUMERIC(20,8) NOT NULL,
    divergence_pnl_usdt         NUMERIC(20,8),
    divergence_qty              NUMERIC(20,8),
    baseline_5d_mean            NUMERIC(20,8),
    baseline_5d_sigma           NUMERIC(20,8),
    noise_floor_threshold       NUMERIC(20,8),
    strategy_id                 TEXT NOT NULL,
    symbol                      TEXT NOT NULL,
    fill_chain_id               UUID,
    hypothesis_id               BIGINT REFERENCES learning.hypotheses(hypothesis_id),
    m9_ab_test_id               UUID,
    m7_decay_signal_id          BIGINT,
    flag_action_taken           TEXT
                                CHECK (flag_action_taken IS NULL OR flag_action_taken IN (
                                    'm9_inconclusive',
                                    'm7_decay_candidate',
                                    'm3_health_recheck',
                                    'operator_alert',
                                    'none'
                                )),
    passive_slack_ack_at        TIMESTAMPTZ,
    evidence_json               JSONB,
    engine_mode                 TEXT NOT NULL
                                CHECK (engine_mode IN (
                                    'paper',
                                    'demo',
                                    'live_demo',
                                    'live',
                                    'replay'
                                )),
    created_by                  TEXT NOT NULL DEFAULT 'm11_replay_engine',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V107',
    PRIMARY KEY (id, divergence_detected_at)
);
```

### 2.2 Column 設計理由

| Column | Type | NULL | 設計理由 |
|---|---|---|---|
| `id` | BIGSERIAL | NOT NULL | sequential ID(hypertable PK 必含 partition column,複合 `(id, divergence_detected_at)`);per V106 sister table 範式 |
| `divergence_detected_at` | TIMESTAMPTZ | NOT NULL | hypertable time dimension;UTC 統一(per CLAUDE.md §六 Mac/Linux runtime);M11 nightly job 偵測時間,非原 live trace 時間(原 live trace 時間在 evidence_json) |
| `replay_run_id` | UUID | NOT NULL | 每 M11 nightly run 一個 UUID(per M11 design spec §2.1 Stage 6 metadata);用於 group by per-run divergence 列表;hot index 對齊 |
| `divergence_type` | TEXT + CHECK 7 值 | NOT NULL | 7 種 divergence type D1-D7 per M11 design spec §4.2;新 type 需 amend ENUM(controlled drift) |
| `severity` | TEXT + CHECK 3 值 | NOT NULL | 3 級 NOISE/WARN/CRITICAL per ADR-0038 Decision 3;對齊 M8 anomaly_severity vocabulary;NOISE writer 端 gate 不寫(schema 仍允許用於 debug fixture) |
| `divergence_metric_name` | TEXT | NOT NULL | metric 名稱(e.g. `pnl_diff_bps`, `position_diff_qty`, `fill_count_diff`, `fee_diff_bps`, `liq_event_count_diff`, `regime_label_drift`, `risk_envelope_breach_diff`);不 enum 因 metric 名稱動態擴增,writer 端維持 naming consistency |
| `divergence_value` | NUMERIC(20,8) | NOT NULL | 高精度(避 FLOAT 精度誤差;crypto bps 小數 8 位、qty 小數 8 位、count 整數皆能容);per `db-schema-design-financial-time-series` skill;NUMERIC(20,8) 對齊 V106 metric_value |
| `divergence_pnl_usdt` | NUMERIC(20,8) | YES | divergence 對 PnL 衝擊 USDT 計;D3 pnl divergence 必填,其他 type 選填 |
| `divergence_qty` | NUMERIC(20,8) | YES | divergence 對 qty 衝擊;D1 fill_chain + D2 position 必填,其他 type 選填 |
| `baseline_5d_mean` | NUMERIC(20,8) | YES | 該 divergence_type × strategy × symbol 的 5d empirical baseline mean(per ADR-0038 Decision 3 統計推導);H-11 #2 mitigation:每 row 鎖當下 baseline,後續 audit 可重構 threshold derivation;cold_start 期 NULL allowed |
| `baseline_5d_sigma` | NUMERIC(20,8) | YES | 5d empirical sigma;同上 |
| `noise_floor_threshold` | NUMERIC(20,8) | YES | 觸發 NOISE/WARN/CRITICAL 分級的 threshold value(per ADR-0038 Decision 3:NOISE < mean+0.5σ / WARN ≥ mean+2.5σ / CRITICAL ≥ mean+3σ;此 column 鎖該 row 級別所對應的 threshold);用於 audit trail + reproducibility |
| `strategy_id` | TEXT | NOT NULL | per CR-7 attribution chain;對齊 V094 / V099/V100 strategy_track ENUM 既有 strategy_id 命名;5 active strategy(grid/ma/bb_breakout/bb_reversion/funding_arb)動態擴增不 enum |
| `symbol` | TEXT | NOT NULL | per ADR-0029 symbol attribution;25 live symbol;not enum 因 cohort 動態變 |
| `fill_chain_id` | UUID | YES | 對 D1 fill_chain + D2 position divergence,引用 originating fill chain ID(逻辑 ref V099/V100 track-attribution schema);不強制 FK constraint 因 V099/V100 cross-V### dependency direction + 大量 INSERT 不適合 hard FK lookup overhead |
| `hypothesis_id` | BIGINT + FK | YES | hypothesis-grounded replay 用(per ADR-0026 v3 pre-registration);nullable FK to `learning.hypotheses(hypothesis_id)`(V103 已 land Sprint 1A-α);nightly hygiene 為 NULL |
| `m9_ab_test_id` | UUID | YES | M9 A/B test 進行中時 evidence_json 攜帶 ab_test_id;此 column 是 placeholder soft reference,實際 FK 待 V108 γ Sprint 1A-γ land;bi-directional cross-ref via V108.ab_results.inconclusive_reason write-back(per M11 design spec §6.3) |
| `m7_decay_signal_id` | BIGINT | YES | M7 decay signal ID 對應(placeholder soft reference;實際 V113 M7 schema land Sprint 8 後 retrofit FK);M7 是 read-only consumer 走 pull/poll V107 而非 push,故此 column 由 M7 detector ingestion 端 backfill 而非 M11 writer fill |
| `flag_action_taken` | TEXT + CHECK 5 值 + NULL | YES | per M11 design spec §5.1 flag-action map 主路由結果:`m9_inconclusive`(WARN+M9 active) / `m7_decay_candidate`(CRITICAL 14d 累積) / `m3_health_recheck`(CRITICAL) / `operator_alert`(passive Slack 5d unack) / `none`(NOISE 或無下游);writer 端 INSERT 後 flag-action map 計算結果 backfill;NULL = 尚未決定 |
| `passive_slack_ack_at` | TIMESTAMPTZ | YES | H-11 #6 mitigation:operator Slack reaction / GUI sign-off 時間;NULL = 未 ack;writer 端 cron 邏輯:observed_at>5d 且 ack=null → 自動升 M3 HEALTH_WARN(per M11 design spec §8) |
| `evidence_json` | JSONB | YES | 富 context:raw live trace ID + replay output snapshot + diff breakdown + cohort metadata + ab_test_id(若 M9 active);per M11 design spec §3.2 + ADR-0038 schema candidate |
| `engine_mode` | TEXT + CHECK 5 值 | NOT NULL | 5 值齊全(paper/demo/live_demo/live/**replay**) — 額外加 `replay` 因 V107 row 由 M11 replay engine 寫入(replay 本身 = 重放原 live trace);training filter 必 `IN ('live','live_demo')`(per CLAUDE.md §七);writer 端 INSERT 一般填 `'replay'` 表 M11 自身寫入,evidence_json 內含原 live trace 的 engine_mode |
| `created_by` | TEXT + DEFAULT 'm11_replay_engine' | NOT NULL | per V103 §14 EXTEND 範式 + V106 sister table;預設 M11 writer 名;允許 `cowork-agent` / `operator` / `m11_replay_engine` 多 actor |
| `created_at` | TIMESTAMPTZ + DEFAULT now() | NOT NULL | row insert 時間(server-side trusted) |
| `updated_by` | TEXT | YES | 後續 update 寫入者(如 flag_action_taken backfill / passive_slack_ack_at backfill) |
| `updated_at` | TIMESTAMPTZ | YES | last update 時間;flag/ack backfill 後寫入 |
| `source_version` | TEXT + DEFAULT 'V107' | NOT NULL | schema version tag;未來 schema migration audit;預設 V107 |

### 2.3 為什麼 `severity` 採 NOISE/WARN/CRITICAL 3 級(而非 M8 anomaly_severity 4 級 INFO/WARN/CRITICAL/HALT)

per ADR-0038 Decision 3 + `m11_threshold_m7_dedup_decay_enforced_rename.md` §5:

- M11 divergence 是 **continuous-state observation**(每 nightly run 對每 strategy×symbol 計算 7 種 divergence;絕大多數時間是 NOISE level;不寫入 row)
- M8 anomaly 是 **event-discrete trigger**(INFO baseline / WARN / CRITICAL / HALT 4 級;INFO 即可代表 baseline noise)
- M11 不需 HALT 級(per CR-7 M7 是 single decay authority;M11 CRITICAL = M7 input source 1-of-4,不獨立 HALT)
- M11 採 NOISE/WARN/CRITICAL 3 級對齊 M8 後三級 vocabulary,差在 NOISE vs INFO 命名(NOISE 強調 statistical noise floor;INFO 強調 anomaly baseline 事件)

兩 enum 不同對齊規則由 PA dispatch §1 CR-X 仲裁;本 spec 採 PA verdict(M11 3 級 / M8 4 級 各自 enum)。

### 2.4 為什麼 `divergence_value` 與 `divergence_pnl_usdt` / `divergence_qty` 分開三個 column

per M11 design spec §4.2 7 種 divergence type 對應不同單位:

- D1 fill_chain → fill count diff(整數)
- D2 position → qty diff(USDT 等值 + native qty)
- D3 pnl → bps + USDT
- D4 fee → bps
- D5 liquidation → event count + PnL impact USDT
- D6 regime → label drift count
- D7 risk → breach count + position size ratio

統一一個 `divergence_value` column 不足表達多單位;故拆 3 column:
- `divergence_value` 是 metric 主 value(bps / count / ratio)— NUMERIC(20,8) 統一表示
- `divergence_pnl_usdt` 是 PnL 衝擊(USDT)— D3/D5 必填 NULL allowed for 其他 type
- `divergence_qty` 是 qty 衝擊(USDT 等值)— D1/D2 必填 NULL allowed for 其他 type

writer 端責任維持 per-type 對應 column 填值 consistency。

### 2.5 為什麼 `m7_decay_signal_id` / `m9_ab_test_id` 採 soft reference 而非 hard FK

per `db-schema-design-financial-time-series` skill + M11 design spec §11 cross-V### dependency 紀律:

- V113(M7)+ V108(M9 γ)Sprint 1A-β 後續 land,V107 land Sprint 1A-β 早於 V108/V113;hard FK 會鎖 dispatch sequence
- M7 是 read-only consumer 走 pull;hard FK 不必要
- M9 bi-directional cross-ref via V108.ab_results.inconclusive_reason write-back(per M11 design spec §6.3);hard FK 會循環依賴
- 大量 INSERT 不適合 hard FK lookup overhead(M11 nightly job 預估 ~100-200 row per night)

故 `m7_decay_signal_id` 採 BIGINT placeholder(soft reference);`m9_ab_test_id` 採 UUID placeholder(soft reference)。

### 2.6 為什麼 `hypothesis_id` 採 nullable hard FK

- V103(learning.hypotheses)Sprint 1A-α 已 land(per dependency line);hard FK 可行
- hypothesis-grounded replay 是 ADR-0026 v3 pre-registration 紀律重要 audit trail(per V103 §14 audit field)
- nullable 因 nightly hygiene replay 不 ground hypothesis(NULL allowed)
- 預期 row 量 < 100 row/yr 走 hypothesis-grounded 路徑(per V103 §2.1.4 hypothesis row 量級)→ FK lookup overhead 可忽略

### 2.7 為什麼 `fill_chain_id` 採 soft reference

per V099/V100 spec(track-attribution Sprint 1A-α 已 land):
- `trading.fills` 含 fill_chain_id column(per V099/V100)但無 separate fill_chain master table
- hard FK 目標不存在 → 採 soft reference(UUID)
- 邏輯一致性由 writer 端 + 後續 audit query 保證

---

## §3 Hypertable / Partitioning

### 3.1 Hypertable 設定

```sql
SELECT create_hypertable(
    'learning.replay_divergence_log',
    'divergence_detected_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);
```

**chunk_time_interval = 7d 理由**(per `db-schema-design-financial-time-series` skill + V106 sister table 範式):

- 預估 row 量:M11 nightly run 1 次/天 × 5 strategy × 25 symbol × 7 種 divergence type × ~30% emit rate(WARN+CRITICAL 比例)= ~262 row/day(進取估算 ~500 row/day 含 evidence_json overhead)
- 500 row/day × 7d = 3,500 row/chunk(估 ~25 KB/row 含 JSONB)= ~85 MB/chunk(uncompressed)
- 對齊 V106 7d chunk 範式;適合 PG memory hint
- 7d 對齊 weekly rollup query pattern + M7 14d window detector 走 2 chunk scan

### 3.2 Compression policy

```sql
ALTER TABLE learning.replay_divergence_log SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'strategy_id, symbol, divergence_type',
    timescaledb.compress_orderby = 'divergence_detected_at DESC, id DESC'
);

SELECT add_compression_policy(
    'learning.replay_divergence_log',
    INTERVAL '30 days'
);
```

- `compress_segmentby = 'strategy_id, symbol, divergence_type'`:同 strategy × symbol × type 連續 row segment 壓縮率最高(80-90%)
- `compress_orderby = 'divergence_detected_at DESC, id DESC'`:time-DESC 最近資料 close 在 chunk 邊界,decompress 成本最低
- 30d 後自動壓縮(避免 hot data + M7 14d window detector 期間壓縮影響 query)— **較 V106 7d 寬鬆** 因 M11 14d window detector 需要 hot read 14d 範圍

### 3.3 Retention policy

```sql
SELECT add_retention_policy(
    'learning.replay_divergence_log',
    INTERVAL '90 days'
);
```

- 90d 後自動 drop chunk
- 對 long-term trend 分析需求走 daily aggregate 表(本 spec 不含,Sprint 1B+ 補)
- per ADR-0038 H-22 R4 governance retention 規範對齊 learning.* 表標準

### 3.4 為什麼 compression 30d 而非 7d(與 V106 不同)

per M11 design spec §7 M7 integration + ADR-0038 Decision 3 14d window:

- M7 detector 走 `pull V107 last 14d WARN+CRITICAL row` query(per M11 design spec §7.4)
- 若 7d 後即壓縮 → 14d window 內 7d-14d 範圍是 compressed chunk;每次 M7 pull 都 decompress overhead 顯著
- 30d compress 確保 14d window detector hot path 全在 uncompressed chunk;30d-90d 範圍是 audit drill-down(infrequent query)走 compressed chunk 可接受

### 3.5 為什麼不採 30d 或 365d retention

- **30d 過短**:M11 nightly 連續 14d-30d divergence pattern 觀察需 30d+;30d retention 無法 cover M7 30d Sharpe<thr cross-source(per M11 design spec §7.2)
- **365d 過長**:占 storage 過多(~90 GB 一年);M11 是 operational audit 非 strategy alpha,90d 足夠 trend analysis + M7 decay 14d window detector + M9 30d evaluation cadence;long-term trend 走 aggregate 表

---

## §4 Index Strategy

### 4.1 Hot-path query → index map

per M11 design spec hot path + `db-schema-design-financial-time-series` skill:

| Query pattern | 命中 index | 範例 SQL |
|---|---|---|
| per-strategy-symbol divergence timeline (M7 detector 14d pull / GUI drill-down) | `idx_div_strategy_symbol_detected` | `SELECT * FROM learning.replay_divergence_log WHERE strategy_id='grid' AND symbol='BTCUSDT' AND divergence_detected_at > now() - INTERVAL '14 days' ORDER BY divergence_detected_at DESC` |
| per-severity alert dashboard (Slack daily digest + GUI Banner) | `idx_div_severity_detected` (partial) | `SELECT * FROM learning.replay_divergence_log WHERE severity IN ('WARN','CRITICAL') ORDER BY divergence_detected_at DESC LIMIT 100` |
| per-replay-run group by (nightly run summary) | `idx_div_run_id` | `SELECT divergence_type, count(*), avg(divergence_value) FROM learning.replay_divergence_log WHERE replay_run_id=$1 GROUP BY divergence_type` |
| hypothesis-grounded replay drill-down | `idx_div_hypothesis_detected` (partial) | `SELECT * FROM learning.replay_divergence_log WHERE hypothesis_id=$1 ORDER BY divergence_detected_at DESC` |
| passive Slack 5d unack escalate cron query | `idx_div_unack_detected` (partial) | `SELECT * FROM learning.replay_divergence_log WHERE passive_slack_ack_at IS NULL AND severity IN ('WARN','CRITICAL') AND divergence_detected_at < now() - INTERVAL '5 days'` |

### 4.2 Index DDL

```sql
-- 主要 hot-path: per-strategy-symbol timeline (M7 14d detector + GUI drill-down)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_strategy_symbol_detected
    ON learning.replay_divergence_log (strategy_id, symbol, divergence_detected_at DESC);

-- Alert dashboard hot-path: WARN+CRITICAL query (partial,絕大多數 row 是 WARN/CRITICAL 因 NOISE 不寫;但保留 partial 防 NOISE debug fixture INSERT)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_severity_detected
    ON learning.replay_divergence_log (severity, divergence_detected_at DESC)
    WHERE severity IN ('WARN', 'CRITICAL');

-- per-replay-run group by (nightly run summary)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_run_id
    ON learning.replay_divergence_log (replay_run_id);

-- hypothesis-grounded replay drill-down (partial,僅 hypothesis-grounded replay 才有 hypothesis_id)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_hypothesis_detected
    ON learning.replay_divergence_log (hypothesis_id, divergence_detected_at DESC)
    WHERE hypothesis_id IS NOT NULL;

-- passive Slack 5d unack escalate cron (partial,H-11 #6 mitigation)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_unack_detected
    ON learning.replay_divergence_log (passive_slack_ack_at, divergence_detected_at DESC)
    WHERE passive_slack_ack_at IS NULL AND severity IN ('WARN', 'CRITICAL');
```

> **註(2026-05-22 PA reconcile §5)**:`CREATE INDEX CONCURRENTLY` 對 TimescaleDB hypertable 在 `psql -v ON_ERROR_STOP=1 -f` transaction-implicit 內不可用(per V094 sister table 範式 + V106 / V107 IMPL §6.5 / §2.3 empirical);hypertable 走非 CONCURRENT path 改用 `CREATE INDEX IF NOT EXISTS`,TimescaleDB 自動逐 chunk 建 index;greenfield 0 row 時 0 lock cost。本 §4.2 DDL 保留 CONCURRENTLY 字面用於 spec 設計意圖呈現;.sql 實檔已對齊 V094 / V106 / V107 落地範式採非 CONCURRENT。Materialized view `REFRESH ... CONCURRENTLY` 仍適用(per §7.3 + UNIQUE INDEX 滿足前提),不在此 reconcile 範圍。
>
> **補(2026-05-22 Sprint 1A-ε P1 patch)**:V107 IMPL `.sql` 落地 reality = non-CONCURRENT(對齊 V094/V106 hypertable empirical;Round 1 sandbox dry-run 0 RAISE);上方 §4.2 DDL `CREATE INDEX CONCURRENTLY` 字面僅保留設計意圖呈現,非 IMPL reality;若 Sprint 1B M11 production grade 評估後需要 CONCURRENTLY non-blocking semantics(production hypertable 有 row + 真實 lock 競爭情境),走獨立 EXTEND migration 路徑:`CREATE INDEX CONCURRENTLY` 必須在 transaction 外執行,需單獨 `psql` 連線 + 顯式 NOT IN transaction wrapping(per PostgreSQL doc + 對齊 V094 footnote 範式)。

### 4.3 Partial index 理由

per `db-schema-design-financial-time-series` skill §4.2:partial index 對 filter 條件穩定的場景大幅縮小索引(60-80% 空間節省):

- `idx_div_severity_detected` partial WHERE severity IN ('WARN','CRITICAL'):雖然 production writer NOISE 不寫(>99% row 是 WARN/CRITICAL),但保留 partial 防 NOISE debug fixture INSERT 污染索引 + 對 future schema 演進(可能新增更低級 severity)安全
- `idx_div_hypothesis_detected` partial WHERE hypothesis_id IS NOT NULL:hypothesis-grounded replay 預估 < 5% row(nightly hygiene 為 NULL)→ partial 縮 95% 空間
- `idx_div_unack_detected` partial WHERE passive_slack_ack_at IS NULL AND severity IN ('WARN','CRITICAL'):此 index 服務 escalate cron query,只索引 unack + warn/critical row;預估 < 10% row 同時滿足

### 4.4 為什麼不加 `(divergence_type, divergence_detected_at)` index

divergence_type CHECK 7 值 cardinality 中等;但實際 query pattern 都帶 `strategy_id` 或 `severity` 作主 filter,divergence_type 只作 secondary filter;不需顯式 index,PG 會用既有 hot index 加 in-memory filter。

### 4.5 為什麼不加 `(engine_mode, divergence_detected_at)` index

per V106 sister table §4.4:engine_mode CHECK 5 值 cardinality 太低 → index selectivity 不佳;PG 會用 bitmap scan 或全表 scan;不需顯式 index。M11 自身寫入時 engine_mode 99% 是 'replay';evidence_json 內含原 live trace 的 engine_mode(供 audit query 用 JSONB GIN index 走 future Sprint 1B+ 補)。

---

## §5 Guard A / B / C(per CLAUDE.md §Data, Migrations, And Validation + V094/V106 mirror)

V107 涉及 1 個 NEW hypertable CREATE + nullable FK to V103 hypotheses,需 Guard A + Guard C(無 ALTER 既有 column 不需 Guard B)。

### 5.1 Guard A — table existence + 既有 schema 對齊驗證 + 依賴表存在驗證

```sql
-- ============================================================
-- Guard A: V107 預檢 — 若 learning.replay_divergence_log 已存在,必驗 V107 spec
-- column 全俱在;缺即 RAISE。同時驗 TimescaleDB extension + V096 boundary + V098
-- learning.governance_audit_log + V103 learning.hypotheses 三依賴表存在。
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
DECLARE v_ts_ver TEXT;
BEGIN
    -- TimescaleDB extension prereq (V096 boundary)
    SELECT extversion INTO v_ts_ver
    FROM pg_extension WHERE extname='timescaledb';
    IF v_ts_ver IS NULL THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: TimescaleDB extension missing. '
            'V096 boundary not satisfied. Apply V096 first.';
    END IF;

    -- learning.replay_divergence_log 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='replay_divergence_log'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'divergence_detected_at', 'replay_run_id', 'divergence_type',
            'severity', 'divergence_metric_name', 'divergence_value',
            'divergence_pnl_usdt', 'divergence_qty',
            'baseline_5d_mean', 'baseline_5d_sigma', 'noise_floor_threshold',
            'strategy_id', 'symbol', 'fill_chain_id', 'hypothesis_id',
            'm9_ab_test_id', 'm7_decay_signal_id', 'flag_action_taken',
            'passive_slack_ack_at', 'evidence_json', 'engine_mode',
            'created_by', 'created_at', 'updated_by', 'updated_at',
            'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='replay_divergence_log'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V107 Guard A FAIL: learning.replay_divergence_log exists but missing columns: %. '
                'Possible legacy stub conflict — resolve schema reconciliation before applying V107.',
                v_missing;
        END IF;

        -- 反模式檢測:per CR-7 + AC-5 + m11_threshold_m7_dedup_decay_enforced_rename §3.3
        -- M11 schema 嚴禁 含 auto_demote / target_state / decay_recommendation / demote_proposal_id / decay_stage / stage_demoted column
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='replay_divergence_log'
              AND column_name IN (
                  'auto_demote', 'target_state', 'decay_recommendation',
                  'demote_proposal_id', 'decay_stage', 'stage_demoted'
              )
        ) THEN
            RAISE EXCEPTION
                'V107 Guard A FAIL: learning.replay_divergence_log contains FORBIDDEN action column. '
                'Per CR-7 + ADR-0038 Decision 3, M11 is SENSOR only — M7 (V113) is single decay authority. '
                'V107 schema must not contain auto_demote / target_state / decay_recommendation / '
                'demote_proposal_id / decay_stage / stage_demoted. Remove offending column or move to V113.';
        END IF;
    END IF;

    -- learning.governance_audit_log 必須存在(M11 H-11 audit cross-ref 雖無 FK 但 query JOIN 需要)
    -- 2026-05-22 PA reconcile §4: V098 baseline 真實表名為 learning.governance_audit_log
    -- (per V035 baseline);本 spec 前版「governance.audit_log」屬概念命名漂移。
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='governance_audit_log'
    ) THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: learning.governance_audit_log missing — '
            'V098 must apply before V107 (cross-ref query target). Verify _sqlx_migrations.';
    END IF;

    -- learning.hypotheses 必須存在(V103 已 land Sprint 1A-α; hypothesis_id FK target)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='hypotheses'
    ) THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: learning.hypotheses missing — '
            'V103 must apply before V107 (hypothesis_id FK target). Verify _sqlx_migrations.';
    END IF;
END $$;
```

### 5.2 Guard B — 不適用

V107 不 ALTER 既有 column;無 type-sensitive 檢查需求。

### 5.3 Guard C — CHECK constraint + ENUM 值齊全 + hypertable + index + policy 對齊驗證

```sql
-- ============================================================
-- Guard C: V107 預檢 — 重跑 V107 時 idempotent 檢查 CHECK constraint + 
-- hypertable + compression policy + retention policy + index 對齊
-- ============================================================
DO $$
DECLARE v_actual TEXT;
DECLARE v_chunk_interval BIGINT;
BEGIN
    -- divergence_type CHECK constraint 7 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.replay_divergence_log'::regclass
      AND conname LIKE '%divergence_type%check%';
    IF v_actual IS NOT NULL THEN
        IF position('fill_chain' IN v_actual) = 0
           OR position('position' IN v_actual) = 0
           OR position('pnl' IN v_actual) = 0
           OR position('fee' IN v_actual) = 0
           OR position('liquidation' IN v_actual) = 0
           OR position('regime' IN v_actual) = 0
           OR position('risk' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V107 Guard C FAIL: learning.replay_divergence_log divergence_type CHECK enum mismatch. '
                'Actual: %. Expected to contain all 7 divergence type values '
                '(fill_chain/position/pnl/fee/liquidation/regime/risk per M11 design spec §4.2 D1-D7).',
                v_actual;
        END IF;
    END IF;

    -- severity CHECK 3 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.replay_divergence_log'::regclass
      AND conname LIKE '%severity%check%';
    IF v_actual IS NOT NULL THEN
        IF position('NOISE' IN v_actual) = 0
           OR position('WARN' IN v_actual) = 0
           OR position('CRITICAL' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V107 Guard C FAIL: learning.replay_divergence_log severity CHECK enum mismatch. '
                'Actual: %. Expected NOISE/WARN/CRITICAL per ADR-0038 Decision 3.',
                v_actual;
        END IF;
    END IF;

    -- flag_action_taken CHECK 5 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.replay_divergence_log'::regclass
      AND conname LIKE '%flag_action_taken%check%';
    IF v_actual IS NOT NULL THEN
        IF position('m9_inconclusive' IN v_actual) = 0
           OR position('m7_decay_candidate' IN v_actual) = 0
           OR position('m3_health_recheck' IN v_actual) = 0
           OR position('operator_alert' IN v_actual) = 0
           OR position('none' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V107 Guard C FAIL: flag_action_taken CHECK enum mismatch. '
                'Actual: %. Expected m9_inconclusive/m7_decay_candidate/m3_health_recheck/operator_alert/none '
                'per M11 design spec §5.1.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 5 值齊全(額外 replay 值)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.replay_divergence_log'::regclass
      AND conname LIKE '%engine_mode%check%';
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V107 Guard C FAIL: engine_mode CHECK enum mismatch. '
                'Actual: %. Expected paper/demo/live_demo/live/replay '
                '(replay 為 M11 自身寫入 engine_mode;原 live trace mode 在 evidence_json).',
                v_actual;
        END IF;
    END IF;

    -- hypothesis_id FK to learning.hypotheses 存在
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class r ON c.conrelid = r.oid
        JOIN pg_namespace n ON r.relnamespace = n.oid
        WHERE n.nspname='learning' AND r.relname='replay_divergence_log'
          AND c.contype='f'
          AND c.conname LIKE '%hypothesis%'
    ) THEN
        RAISE NOTICE 'V107 Guard C NOTE: hypothesis_id FK to learning.hypotheses not yet applied. '
                     'Will be added by main migration body.';
    END IF;

    -- Hypertable 已建立 + chunk_time_interval = 7 days
    SELECT
        EXTRACT(EPOCH FROM time_interval) * 1000000  -- 轉 microseconds
    INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name='replay_divergence_log'
      AND column_name='divergence_detected_at';
    -- 7 days = 604800 sec = 604800000000 microseconds
    IF v_chunk_interval IS NOT NULL AND v_chunk_interval != 604800000000 THEN
        RAISE EXCEPTION
            'V107 Guard C FAIL: learning.replay_divergence_log chunk_time_interval mismatch. '
            'Actual: % microseconds. Expected: 604800000000 (7 days).',
            v_chunk_interval;
    END IF;

    -- Compression policy 存在(30 day after — M11 14d window detector hot read 需求)
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_compression'
          AND hypertable_name='replay_divergence_log'
    ) THEN
        RAISE NOTICE 'V107 Guard C NOTE: compression policy not yet applied. '
                     'Will be added by main migration body (compress_after=30d for M11 14d window).';
    END IF;

    -- Retention policy 存在(90 day after)
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention'
          AND hypertable_name='replay_divergence_log'
    ) THEN
        RAISE NOTICE 'V107 Guard C NOTE: retention policy not yet applied. '
                     'Will be added by main migration body (drop_after=90d).';
    END IF;
END $$;
```

### 5.4 Guard 設計理念(per V094/V106 mirror)

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件(idempotent)|
|---|---|---|---|
| A | NEW table 已存在但 column 缺;TimescaleDB / learning.governance_audit_log / learning.hypotheses 缺;**或 V107 含 forbidden action column** | RAISE | 全 column 俱在 + 0 forbidden column / table 不存在(首次跑) |
| C | CHECK constraint 缺 enum 值;hypertable interval 不對 | RAISE | constraint 不存在(首次跑) / constraint 完整(重跑) |
| C policy | compression / retention policy 首次跑不存在 | NOTICE(不 RAISE,migration body 會建)| policy 已存在重跑(skip) |
| C FK | hypothesis_id FK 首次跑不存在 | NOTICE(不 RAISE,migration body 會建) | FK 已存在重跑(skip) |

重跑 V107 第二次必不 RAISE(idempotency per CLAUDE.md §Data, Migrations, And Validation V055/V083/V084 incident precedent)。

---

## §6 Migration up + down SQL

### 6.1 Migration UP(完整 V107.sql 設計)

```sql
-- ============================================================
-- V107: learning.replay_divergence_log + hypertable + compression + retention + 5 indexes + mv
-- M11 Continuous Counterfactual Replay Divergence Log
-- (7 divergence types × 3 severity levels × hypertable; per ADR-0038 + M11 design spec)
-- ============================================================

-- Step 1: Guard A (per §5.1) — 含 forbidden action column 反模式檢測
-- [全文見 §5.1]

-- Step 2: Guard C 預檢 (per §5.3 重跑 idempotency)
-- [全文見 §5.3]

-- Step 3: CREATE TABLE
CREATE TABLE IF NOT EXISTS learning.replay_divergence_log (
    -- (per §2.1 完整 DDL)
    id                          BIGSERIAL,
    divergence_detected_at      TIMESTAMPTZ NOT NULL,
    replay_run_id               UUID NOT NULL,
    divergence_type             TEXT NOT NULL CHECK (divergence_type IN (
        'fill_chain', 'position', 'pnl', 'fee', 'liquidation', 'regime', 'risk'
    )),
    severity                    TEXT NOT NULL CHECK (severity IN ('NOISE', 'WARN', 'CRITICAL')),
    divergence_metric_name      TEXT NOT NULL,
    divergence_value            NUMERIC(20,8) NOT NULL,
    divergence_pnl_usdt         NUMERIC(20,8),
    divergence_qty              NUMERIC(20,8),
    baseline_5d_mean            NUMERIC(20,8),
    baseline_5d_sigma           NUMERIC(20,8),
    noise_floor_threshold       NUMERIC(20,8),
    strategy_id                 TEXT NOT NULL,
    symbol                      TEXT NOT NULL,
    fill_chain_id               UUID,
    hypothesis_id               BIGINT REFERENCES learning.hypotheses(hypothesis_id),
    m9_ab_test_id               UUID,
    m7_decay_signal_id          BIGINT,
    flag_action_taken           TEXT CHECK (flag_action_taken IS NULL OR flag_action_taken IN (
        'm9_inconclusive', 'm7_decay_candidate', 'm3_health_recheck', 'operator_alert', 'none'
    )),
    passive_slack_ack_at        TIMESTAMPTZ,
    evidence_json               JSONB,
    engine_mode                 TEXT NOT NULL CHECK (engine_mode IN (
        'paper', 'demo', 'live_demo', 'live', 'replay'
    )),
    created_by                  TEXT NOT NULL DEFAULT 'm11_replay_engine',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V107',
    PRIMARY KEY (id, divergence_detected_at)
);

-- Step 4: Hypertable
SELECT create_hypertable(
    'learning.replay_divergence_log',
    'divergence_detected_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Step 5: Compression
ALTER TABLE learning.replay_divergence_log SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'strategy_id, symbol, divergence_type',
    timescaledb.compress_orderby = 'divergence_detected_at DESC, id DESC'
);

-- Step 6: Compression + Retention policies (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_compression' AND hypertable_name='replay_divergence_log'
    ) THEN
        PERFORM add_compression_policy('learning.replay_divergence_log', INTERVAL '30 days');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention' AND hypertable_name='replay_divergence_log'
    ) THEN
        PERFORM add_retention_policy('learning.replay_divergence_log', INTERVAL '90 days');
    END IF;
END $$;

-- Step 7: Hot-path indexes (CONCURRENTLY for non-blocking;per §4.2)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_strategy_symbol_detected
    ON learning.replay_divergence_log (strategy_id, symbol, divergence_detected_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_severity_detected
    ON learning.replay_divergence_log (severity, divergence_detected_at DESC)
    WHERE severity IN ('WARN', 'CRITICAL');

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_run_id
    ON learning.replay_divergence_log (replay_run_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_hypothesis_detected
    ON learning.replay_divergence_log (hypothesis_id, divergence_detected_at DESC)
    WHERE hypothesis_id IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_div_unack_detected
    ON learning.replay_divergence_log (passive_slack_ack_at, divergence_detected_at DESC)
    WHERE passive_slack_ack_at IS NULL AND severity IN ('WARN', 'CRITICAL');

-- Step 8: Materialized view for A3 GUI Console Banner + monthly review wizard (per §7)
-- (idempotent via CREATE MATERIALIZED VIEW IF NOT EXISTS;PG 12+ 支援)
CREATE MATERIALIZED VIEW IF NOT EXISTS learning.mv_latest_divergence_per_strategy AS
SELECT DISTINCT ON (strategy_id, symbol, divergence_type)
    strategy_id,
    symbol,
    divergence_type,
    severity,
    divergence_value,
    divergence_pnl_usdt,
    flag_action_taken,
    passive_slack_ack_at,
    divergence_detected_at,
    replay_run_id
FROM learning.replay_divergence_log
WHERE severity IN ('WARN', 'CRITICAL')
ORDER BY strategy_id, symbol, divergence_type, divergence_detected_at DESC;

-- mv refresh policy (4h cron;per §7 A3 design)
-- (refresh 命令由 helper_scripts/cron/m11_mv_refresh.sh 持有;V107 schema 只建 mv)

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_mv_latest_div_strategy_symbol_type
    ON learning.mv_latest_divergence_per_strategy (strategy_id, symbol, divergence_type);

-- Step 9: COMMENT (audit metadata)
COMMENT ON TABLE learning.replay_divergence_log IS
    'M11 Continuous Counterfactual Replay Divergence Log (V107). '
    '7 divergence types (D1-D7 per M11 design spec §4.2) × 3 severity (NOISE/WARN/CRITICAL per ADR-0038); '
    'hypertable + 7d chunk + 30d compression (對齊 M7 14d window detector) + 90d retention. '
    'M11 為 sensor;M7 (V113) 為 single decay authority (per CR-7);V107 禁含 action column。';

COMMENT ON COLUMN learning.replay_divergence_log.severity IS
    '3 級 severity per ADR-0038 Decision 3 (NOISE<mean+0.5σ / WARN≥mean+2.5σ / CRITICAL≥mean+3σ); '
    'production writer NOISE 不寫 row (schema 允許用於 debug fixture)。';

COMMENT ON COLUMN learning.replay_divergence_log.passive_slack_ack_at IS
    'H-11 #6 mitigation: operator Slack reaction / GUI sign-off 時間; '
    'NULL=未ack; ack=null + observed_at>5d → 自動升 M3 HEALTH_WARN (per M11 design spec §8)。';

COMMENT ON COLUMN learning.replay_divergence_log.engine_mode IS
    '5 值齊全;M11 自身寫入時 engine_mode=replay;原 live trace mode 在 evidence_json; '
    'ML training filter 必 IN (live, live_demo) per CLAUDE.md §七。';
```

### 6.2 Migration DOWN(rollback;dev-only,production 慎用)

```sql
-- ============================================================
-- V107 ROLLBACK: 刪 mv + hypertable + policies + indexes + table
-- ⚠️ DESTRUCTIVE: 90d 之內所有 divergence log 全 drop;不可恢復。
-- 僅 dev/staging 使用;production rollback 走 V### 升級而非 down。
-- ============================================================

-- Step 1: Drop materialized view
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_mv_latest_div_strategy_symbol_type;
DROP MATERIALIZED VIEW IF EXISTS learning.mv_latest_divergence_per_strategy;

-- Step 2: Remove policies first (避免 dangling jobs)
SELECT remove_compression_policy('learning.replay_divergence_log', if_exists => TRUE);
SELECT remove_retention_policy('learning.replay_divergence_log', if_exists => TRUE);

-- Step 3: Drop indexes (CONCURRENTLY 不能在 transaction 內;rollback 走獨立 statement)
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_unack_detected;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_hypothesis_detected;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_run_id;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_severity_detected;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_strategy_symbol_detected;

-- Step 4: Drop hypertable + table (CASCADE 處理 chunks + FK)
DROP TABLE IF EXISTS learning.replay_divergence_log CASCADE;
```

### 6.3 Idempotency 驗證

per V055 5-round loop + V083/V084 incident precedent,V107.sql 必跑兩次:
- 第一次:CREATE TABLE + hypertable + policies + indexes + mv → 0 RAISE / 0 ERROR
- 第二次:全 IF NOT EXISTS / 已 hypertable / 已 policies / 已 mv → 0 RAISE / 0 重複 policy / 0 重複 mv

---

## §7 Materialized View — `mv_latest_divergence_per_strategy`

### 7.1 設計動機

per `m11_continuous_counterfactual_replay_design_spec.md` §8.3 A3 Sprint 1A-ε Monthly Review Wizard + GUI Banner:當 M11 unack 累積 ≥ 5d → GUI Console 頂部紅 Banner;需 last divergence per strategy × symbol 即時 query。

直接 query `replay_divergence_log` 走 DISTINCT ON + ORDER BY 雖有 hot index 支援,但每次 GUI Banner refresh 都打 hypertable 多 chunk scan 不經濟;走 mv 4h refresh 即可。

### 7.2 MV 定義

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS learning.mv_latest_divergence_per_strategy AS
SELECT DISTINCT ON (strategy_id, symbol, divergence_type)
    strategy_id,
    symbol,
    divergence_type,
    severity,
    divergence_value,
    divergence_pnl_usdt,
    flag_action_taken,
    passive_slack_ack_at,
    divergence_detected_at,
    replay_run_id
FROM learning.replay_divergence_log
WHERE severity IN ('WARN', 'CRITICAL')
ORDER BY strategy_id, symbol, divergence_type, divergence_detected_at DESC;

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_mv_latest_div_strategy_symbol_type
    ON learning.mv_latest_divergence_per_strategy (strategy_id, symbol, divergence_type);
```

- DISTINCT ON 取每 (strategy, symbol, divergence_type) 三元組的最新 row(by divergence_detected_at DESC)
- WHERE severity IN (WARN,CRITICAL):mv 只 cache 需要 alert 的 row(NOISE writer 不寫;但 partial filter 防 future NOISE debug INSERT 污染 mv)
- Unique index 必含(允許 CONCURRENTLY refresh per PG 12+)

### 7.3 Refresh policy

```bash
# helper_scripts/cron/m11_mv_refresh.sh (Phase A Sprint 3 W15-18 land)
# 4h cron:
#   0 */4 * * * psql -d trading_ai -c "REFRESH MATERIALIZED VIEW CONCURRENTLY learning.mv_latest_divergence_per_strategy;"
```

CONCURRENTLY refresh 走 unique index;refresh 期間 mv 仍可 query(unblock GUI Banner refresh)。

### 7.4 GUI / A3 / monthly review wizard 用法

- GUI Console Banner:query `SELECT count(*) FROM learning.mv_latest_divergence_per_strategy WHERE passive_slack_ack_at IS NULL AND divergence_detected_at > now() - INTERVAL '5 days'` → 若 > 0 顯示紅 Banner
- monthly review wizard:query `SELECT * FROM learning.mv_latest_divergence_per_strategy ORDER BY divergence_detected_at DESC` 列每 strategy × symbol × type 最近 divergence 一覽
- M7 detector:**不**走 mv,走 hot index `idx_div_strategy_symbol_detected` query last 14d 全 row(mv 只 cache 最新一筆,不足 14d window aggregation)

---

## §8 Cross-V### Dependency + Cross-Ref Schema

### 8.1 Cross-V### dependency 圖

```
V096 (drop dead learning tables; TimescaleDB extension) ← V107 (prereq;hypertable infra)
V098 (learning.governance_audit_log)                     ← V107 (cross-ref query target;非 FK)
V103 (learning.hypotheses)                               ← V107 (hypothesis_id nullable FK)
V108 (M9 A/B test schema;Sprint 1A-γ 後續 land)         ← V107 (m9_ab_test_id soft reference;evidence_json bi-directional cross-ref)
V113 (M7 decay schema;Sprint 8 後續 land)               ← V107 (m7_decay_signal_id soft reference;M7 detector pull V107)
V107 (M11 replay divergence log; this spec)
       │
       ├─→ V109 (M8 anomaly cross-ref) — CRITICAL → M8 anomaly event (cross-ref query 非 FK)
       ├─→ V112 (M1 LAL) — CRITICAL → M3 HEALTH_WARN → LAL 1/2 暫停 (cross-ref via M3 state machine)
       ├─→ V113 (M7) — divergence signal 餵 M7 single decay authority (M7 pull V107;非 V107 push)
       └─→ V108 (M9 ab_results) — A/B test inconclusive flag write-back (bi-directional)
```

### 8.2 為什麼 M11 採 sensor / signal source posture(無 hard FK to V113)

per CR-7 + M11 design spec §7.1:

- M11 是 **sensor**;V113 (M7) 是 **single decay authority / actuator**
- V107 ↔ V113 無 hard FK 避免循環依賴 + 維持 M11 nightly job 不阻 M7 detector
- M7 detector 走 pull V107 last 14d WARN+CRITICAL row(read-only consumer)
- 此設計也允許 V107 land Sprint 1A-β 早於 V113 (Sprint 8) 而無 FK ordering blocker

### 8.3 V103 (hypotheses) cross-ref pattern

```sql
-- 例: M11 hypothesis-grounded replay (ADR-0026 v3 pre-registration 紀律)
INSERT INTO learning.replay_divergence_log
    (divergence_detected_at, replay_run_id, divergence_type, severity,
     divergence_metric_name, divergence_value, divergence_pnl_usdt,
     strategy_id, symbol, hypothesis_id,
     evidence_json, engine_mode, baseline_5d_mean, baseline_5d_sigma, noise_floor_threshold)
VALUES
    (now(), 'a1b2c3d4-...', 'pnl', 'WARN',
     'pnl_diff_bps', 8.5, 245.30,
     'grid', 'BTCUSDT', 42,
     jsonb_build_object(
        'live_trace_id', '...',
        'replay_output', '...',
        'diff_breakdown', '...',
        'live_engine_mode', 'live'
     ),
     'replay', 4.2, 2.1, 9.45);  -- threshold = 4.2 + 2.5*2.1 = 9.45
```

### 8.4 V112 (M1 LAL) cross-ref pattern

```sql
-- 例: M1 LAL 1/2 auto-approve eligibility check 需查 M3 HEALTH_WARN 是否由 M11 CRITICAL 觸發
SELECT COUNT(*) FROM learning.replay_divergence_log
WHERE strategy_id = 'grid'
  AND severity = 'CRITICAL'
  AND divergence_detected_at > now() - INTERVAL '14 days'
  AND flag_action_taken = 'm7_decay_candidate'
  AND engine_mode = 'replay';
-- > 7 (per M11 design spec §7.2 14d 內 ≥ 7d CRITICAL) → M7 strong candidate → LAL 1/2 暫停
```

### 8.5 V113 (M7) cross-ref pattern

```sql
-- 例: M7 detector nightly pull V107 last 14d WARN+CRITICAL for decay signal computation
-- (M7 是 read-only consumer;V107 nightly writer 不 push)
SELECT strategy_id, symbol, count(*) as critical_days
FROM learning.replay_divergence_log
WHERE severity = 'CRITICAL'
  AND divergence_detected_at > now() - INTERVAL '14 days'
  AND engine_mode = 'replay'
GROUP BY strategy_id, symbol
HAVING count(*) >= 7;
-- 結果 → M7 multi-source confirm 流程 (per M11 design spec §7.2)
```

### 8.6 V108 (M9) bi-directional cross-ref pattern

```sql
-- 例 1: M11 寫 V107 row 時 attach ab_test_id (若該 strategy×symbol 處於 active M9 test)
-- evidence_json 攜帶 ab_test_id,m9_ab_test_id column soft reference
INSERT INTO learning.replay_divergence_log
    (..., m9_ab_test_id, flag_action_taken, evidence_json, ...)
VALUES
    (..., 'b2c3d4e5-...'::uuid, 'm9_inconclusive',
     jsonb_build_object('ab_test_id', 'b2c3d4e5-...', 'arm', 'variant'), ...);

-- 例 2: M9 final conclusion 必檢查 evaluation cadence 內 V107 是否 clean (per M11 design spec §6.3)
-- V108 ab_results 寫 row 時 query V107:
SELECT count(*) FROM learning.replay_divergence_log
WHERE m9_ab_test_id = $1
  AND severity IN ('WARN', 'CRITICAL')
  AND divergence_detected_at BETWEEN $2 AND $3;  -- evaluation cadence window
-- > 0 → V108.ab_results.inconclusive_reason = 'm11_divergence_flagged'
```

### 8.7 V109 (M8 anomaly) cross-ref pattern

```sql
-- 例: M11 CRITICAL → 同步寫 V109 anomaly event (per CR-7 §5 4 級 severity 對齊)
-- M11 writer 端在 INSERT V107 後 INSERT V109:
INSERT INTO learning.anomaly_events  -- (V109 待 land;此為 placeholder pattern)
    (anomaly_severity, source_module, source_event_id, ...)
VALUES
    ('CRITICAL', 'm11_replay', $v107_id, ...);
```

### 8.8 為什麼 V113 / V108 / V109 走 soft reference / cross-ref 而非 hard FK

| 設計選擇 | 優 | 缺 | 採用 |
|---|---|---|---|
| **Hard FK constraint** | 強約束;join 簡單 | INSERT cost(每筆查 FK target);**鎖 dispatch sequence**(V113/V108/V109 必先 land);**潛在循環依賴**(M7↔M11 / M9↔M11);schema drift 風險 | ❌ 不採 |
| **Soft reference column + cross-ref query** | INSERT 0 overhead;dispatch sequence 解耦;無循環依賴 | 弱約束;依 application logic 維持 referential integrity;需 healthcheck 補 | ✅ 採 |

V107 land Sprint 1A-β 早於 V108/V113 Sprint 1A-γ / Sprint 8 → 必走 soft reference 才能 land。

---

## §9 Linux PG Empirical Dry-Run Protocol(mandatory)

per CLAUDE.md §Data, Migrations, And Validation + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain + V103/V104 dry-run §1 PG connection 範式,V107 涉及:
- TimescaleDB extension hypertable creation (PG-specific syntax)
- compression / retention policy add_*_policy() function 真實返回
- partial index CONCURRENTLY 在 hypertable chunks 上的行為
- CHECK constraint ENUM runtime semantic (5 ENUM 同時)
- nullable FK constraint 在 hypertable 上的行為
- materialized view + CONCURRENTLY refresh + unique index 設計
- 反模式檢測(forbidden action column 偵測 Guard A RAISE 路徑)

**必先 Linux PG empirical 驗證**,禁 Mac mock pytest 代替。

### 9.1 PG 連線範式(per V103/V104 dry-run §1 確認)

```bash
# Connection (per V103/V104 dry-run §1 PG conn confirmed):
# Host: 127.0.0.1
# Port: 5432
# User: trading_admin
# Database: trading_ai
# Auth: ~/.pgpass (chmod 600)

# 連線一行:
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c '<SQL>'"
```

**重要 caveat**(per V103/V104 dry-run §1):DB 名稱 `trading_ai` 而非 `openclaw`;user `trading_admin` 而非 `openclaw`。

### 9.2 PA C9 待補的 PG reflection query(spec sign-off 前必補)

per CLAUDE.md `docs/agents/context-loading.md` "PG Connection Examples"(Linux runtime authoritative):

```bash
# Query 1: _sqlx_migrations head + V103/V108/V113 sequence 確認
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT version, success FROM _sqlx_migrations WHERE version IN (96, 98, 103, 107, 108, 109, 112, 113) ORDER BY version'"
# Expected: ≥ V103 (Sprint 1A-α land); V107 = pending; V108/V109/V112/V113 各自 sprint land

# Query 2: TimescaleDB extension 確認
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT extversion FROM pg_extension WHERE extname='timescaledb'\""
# Expected: ≥ 2.13 (per OpenClaw TimescaleDB minimum)

# Query 3: learning.governance_audit_log + learning.hypotheses 已 land 驗(V098 + V103 prereq)
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT count(*) FROM information_schema.tables WHERE (table_schema='learning' AND table_name='governance_audit_log') OR (table_schema='learning' AND table_name='hypotheses')\""
# Expected: 2 (V098 + V103 都已 land)

# Query 4: learning.hypotheses.hypothesis_id column type 驗(V107 FK target)
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='learning' AND table_name='hypotheses' AND column_name='hypothesis_id'\""
# Expected: hypothesis_id | bigint (per V103 §2.1.1)

# Query 5: learning.replay_divergence_log 是否已存在(legacy stub conflict 檢測)
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name='replay_divergence_log'\""
# Expected: 0 rows (greenfield); 若 1 row → 觸 Guard A 反向檢查

# Query 6: 反模式檢測 — V107 schema 不應含 forbidden action column
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT column_name FROM information_schema.columns WHERE table_schema='learning' AND table_name='replay_divergence_log' AND column_name IN ('auto_demote', 'target_state', 'decay_recommendation', 'demote_proposal_id', 'decay_stage', 'stage_demoted')\""
# Expected: 0 rows (per AC-5 + CR-7); 若 ≥ 1 row → AC-5 FAIL,IMPL block
```

**待 PA C9 補資料的 6 處 placeholder**(spec sign-off 前必更新):
1. `_sqlx_migrations` head 真實 = ?
2. TimescaleDB extension version 真實 = ?
3. learning.governance_audit_log 已 land 確認 = ?
4. learning.hypotheses 已 land + hypothesis_id type 確認 = ?
5. learning.replay_divergence_log stub 不存在確認 = ?
6. 反模式 forbidden action column 0 hit 確認 = ?

### 9.3 Round 1 — V107 SQL 真實 PG semantic empirical 驗證

```bash
# ssh trade-core 執行(不在 Mac 跑)
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V107__m11_replay_divergence_log_hypertable.sql
"
```

**Round 1 必驗 10 項**(empirical SELECT verify after V107 apply):

```sql
-- 1. learning.replay_divergence_log 表存在 + 27 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='replay_divergence_log';
-- Expected: 27

-- 2. Hypertable 真建立 + chunk_time_interval = 7 days
SELECT hypertable_name, time_interval, column_name
FROM timescaledb_information.dimensions
WHERE hypertable_name='replay_divergence_log';
-- Expected: 1 row; time_interval = '7 days'; column_name = 'divergence_detected_at'

-- 3. Compression policy 真設定 (compress_after=30d 對齊 M7 14d window detector)
SELECT proc_name, hypertable_name, config
FROM timescaledb_information.jobs
WHERE proc_name='policy_compression' AND hypertable_name='replay_divergence_log';
-- Expected: 1 row; config 含 compress_after = '30 days'

-- 4. Retention policy 真設定 (drop_after=90d)
SELECT proc_name, hypertable_name, config
FROM timescaledb_information.jobs
WHERE proc_name='policy_retention' AND hypertable_name='replay_divergence_log';
-- Expected: 1 row; config 含 drop_after = '90 days'

-- 5. divergence_type CHECK 7 值齊全
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.replay_divergence_log'::regclass AND conname LIKE '%divergence_type%check%';
-- Expected: 含 fill_chain/position/pnl/fee/liquidation/regime/risk

-- 6. severity CHECK 3 值齊全 + flag_action_taken CHECK 5 值齊全 + engine_mode CHECK 5 值齊全
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.replay_divergence_log'::regclass AND contype='c'
ORDER BY conname;
-- Expected: severity (NOISE/WARN/CRITICAL) + flag_action_taken (5 值) + engine_mode (5 值 含 replay)

-- 7. hypothesis_id FK to learning.hypotheses 真存在
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.replay_divergence_log'::regclass AND contype='f';
-- Expected: 1 row 含 REFERENCES learning.hypotheses(hypothesis_id)

-- 8. 5 hot-path indexes + 1 mv unique index 確認
SELECT indexname FROM pg_indexes
WHERE schemaname='learning' AND tablename='replay_divergence_log'
ORDER BY indexname;
-- Expected: ≥ 6 (1 PK + 5 hot-path indexes)
-- mv unique index separate:
SELECT indexname FROM pg_indexes
WHERE schemaname='learning' AND tablename='mv_latest_divergence_per_strategy';
-- Expected: 1 (idx_mv_latest_div_strategy_symbol_type)

-- 9. materialized view 存在 + 可 query
SELECT count(*) FROM learning.mv_latest_divergence_per_strategy;
-- Expected: 0 (empty);0 row 是預期(V107 apply 後 0 row in base table)

-- 10. engine_mode CHECK 真 reject 6th value + divergence_type CHECK 真 reject 8th value
--     + severity CHECK 真 reject 4th value (empirical INSERT test)
BEGIN;
SAVEPOINT test_engine_mode;
INSERT INTO learning.replay_divergence_log
    (divergence_detected_at, replay_run_id, divergence_type, severity,
     divergence_metric_name, divergence_value,
     strategy_id, symbol, engine_mode)
VALUES
    (NOW(), gen_random_uuid(), 'pnl', 'WARN',
     'test_metric', 1.0,
     'test_strat', 'BTCUSDT', 'INVALID_MODE');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_engine_mode;

SAVEPOINT test_divergence_type;
INSERT INTO learning.replay_divergence_log
    (divergence_detected_at, replay_run_id, divergence_type, severity,
     divergence_metric_name, divergence_value,
     strategy_id, symbol, engine_mode)
VALUES
    (NOW(), gen_random_uuid(), 'INVALID_TYPE', 'WARN',
     'test_metric', 1.0,
     'test_strat', 'BTCUSDT', 'replay');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_divergence_type;

SAVEPOINT test_severity;
INSERT INTO learning.replay_divergence_log
    (divergence_detected_at, replay_run_id, divergence_type, severity,
     divergence_metric_name, divergence_value,
     strategy_id, symbol, engine_mode)
VALUES
    (NOW(), gen_random_uuid(), 'pnl', 'INVALID_SEVERITY',
     'test_metric', 1.0,
     'test_strat', 'BTCUSDT', 'replay');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_severity;

-- 同時測 hypothesis_id FK reject 不存在的 hypothesis
SAVEPOINT test_fk_hypothesis;
INSERT INTO learning.replay_divergence_log
    (divergence_detected_at, replay_run_id, divergence_type, severity,
     divergence_metric_name, divergence_value,
     strategy_id, symbol, hypothesis_id, engine_mode)
VALUES
    (NOW(), gen_random_uuid(), 'pnl', 'WARN',
     'test_metric', 1.0,
     'test_strat', 'BTCUSDT', 999999999, 'replay');
-- Expected: ERROR: violates foreign key constraint (no such hypothesis_id)
ROLLBACK TO SAVEPOINT test_fk_hypothesis;

ROLLBACK;
```

### 9.4 Round 2 — Idempotency 驗證

重跑 V107.sql 第二次必不 RAISE / 必不重複建 hypertable / 必不重複 policy / 必不重複 mv:

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V107__m11_replay_divergence_log_hypertable.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**:
```sql
-- 確認 V107 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='learning' AND table_name='replay_divergence_log';
-- Expected: 1

-- 確認 hypertable 不 double
SELECT count(*) FROM timescaledb_information.dimensions
WHERE hypertable_name='replay_divergence_log';
-- Expected: 1

-- 確認 policies 不 double (2 jobs: compression + retention)
SELECT count(*) FROM timescaledb_information.jobs
WHERE hypertable_name='replay_divergence_log';
-- Expected: 2

-- 確認 indexes 不 double (5 hot-path + 1 PK)
SELECT count(*) FROM pg_indexes
WHERE schemaname='learning' AND tablename='replay_divergence_log'
  AND indexname IN (
    'idx_div_strategy_symbol_detected',
    'idx_div_severity_detected',
    'idx_div_run_id',
    'idx_div_hypothesis_detected',
    'idx_div_unack_detected'
  );
-- Expected: 5

-- 確認 mv 不 double
SELECT count(*) FROM pg_matviews
WHERE schemaname='learning' AND matviewname='mv_latest_divergence_per_strategy';
-- Expected: 1
```

### 9.5 反模式檢測 dry-run(per AC-5)

```bash
# 對 V107.sql + IMPL PR grep forbidden action column
ssh trade-core "grep -E '(auto_demote|target_state|decay_recommendation|demote_proposal_id|decay_stage|stage_demoted)' ~/BybitOpenClaw/srv/sql/migrations/V107__*.sql"
# Expected: 0 hit (per CR-7 + AC-5)
```

### 9.6 為何 Mac mock pytest 不夠(V055 5-round loop 教訓)

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift`:
- Mac mock pytest 無法捕捉 TimescaleDB `create_hypertable()` 真實返回 metadata
- Mac static parse review 無法驗 `add_compression_policy()` / `add_retention_policy()` 對既有 job 衝突的處理
- Mac 無法驗 CHECK constraint runtime ENUM behavior (5 ENUM 同時)
- Mac 無法驗 nullable FK constraint 在 hypertable chunks 上的行為
- Mac 無法驗 materialized view + CONCURRENTLY refresh 對 unique index 的要求
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug;V094 / V106 / V107 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**(per CLAUDE.md §Data, Migrations, And Validation + V094 §4.3 範式)。

---

## §10 Engine Restart 實測 SOP(per 2026-05-02 sqlx hash drift 教訓)

per memory `project_2026_05_02_p0_sqlx_hash_drift`(commit `3681f83`),V107 file edit 後 DB checksum 必同步:

```bash
# E1 IMPL: 寫 V107.sql 完成後跑 Linux dry-run (per §9.3)
# 若 V107.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 107
"
# Expected: V107 checksum updated in _sqlx_migrations table to match new file SHA
```

### 10.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic'"
# Expected: 0 panic; 'Applied migrations' 正常 log; V107 success=t in _sqlx_migrations

ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=107;'"
# Expected: 1 row, success=t
```

### 10.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V094 §5.3:cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

### 10.3 M11 writer 接線 Sprint 3 W15-18 (Phase A) 驗 SOP

V107 schema apply 後 0 row(Foundation stage per MIT pipeline maturity);Sprint 3 W15-18 M11 nightly job IMPL 後驗 Skeleton stage:

```bash
# Phase A Sprint 3 W15-18 deploy 後 24h 驗
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT count(*) as total_row, count(DISTINCT replay_run_id) as nights, count(*) FILTER (WHERE severity='CRITICAL') as critical_count, max(divergence_detected_at) as last_detected FROM learning.replay_divergence_log WHERE divergence_detected_at > now() - INTERVAL '1 day';\""
# Expected (after Phase A Sprint 3): 
#   total_row ≥ 100 (5 strategy × 25 symbol × ~30% emit rate × 7 divergence types)
#   nights = 1 (one nightly run)
#   critical_count varies
#   last_detected within 24h
```

---

## §11 Rollback Plan

### 11.1 V107 rollback(dev/staging only)

per §6.2:

```sql
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_mv_latest_div_strategy_symbol_type;
DROP MATERIALIZED VIEW IF EXISTS learning.mv_latest_divergence_per_strategy;
SELECT remove_compression_policy('learning.replay_divergence_log', if_exists => TRUE);
SELECT remove_retention_policy('learning.replay_divergence_log', if_exists => TRUE);
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_unack_detected;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_hypothesis_detected;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_run_id;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_severity_detected;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_div_strategy_symbol_detected;
DROP TABLE IF EXISTS learning.replay_divergence_log CASCADE;
```

### 11.2 Production rollback 路徑

per CLAUDE.md §Data, Migrations, And Validation:production 不用 down migration;走 V### 升級覆寫(若需 schema 演進)或 `repair_migration_checksum` binary(若需 checksum repair)。

### 11.3 V096 boundary

per V101 spec v3 §7:rollback 路徑不跨 V096(V096 drop dead tables 不可逆)。V107 rollback 全在 V096 之後(V096 < V098 < V103 < V107),無 boundary 風險。

### 11.4 Cross-V### rollback ordering

若 V107 rollback,下游 V108(M9) / V109(M8) / V113(M7)的 soft reference / FK 需處理:
- V108 ab_results.inconclusive_reason='m11_divergence_flagged' row → 改為 'unknown' 或 NULL(per V108 spec own decision)
- V109 anomaly_events 含 source_module='m11_replay' row → NULL out source_event_id
- V113 m7_decay_signal 從 V107 ingest 的 signal → mark as 'm11_unavailable' status

實際 rollback 路徑由 sprint owner 處理;V107 spec 不寫死。

---

## §12 Audit Field (5 field per V103 §14 EXTEND 範式)

### 12.1 5 audit field 含於 §2.1 表定義內

per V103 §14 EXTEND 範式,V107 schema 在 §2.1 表定義內已含 5 audit field:

| Column | 用途 | DEFAULT | NULL |
|---|---|---|---|
| `created_by` | 寫入這 row 的 actor(`m11_replay_engine` / `cowork-agent` / `operator` 等) | DEFAULT 'm11_replay_engine' | NOT NULL |
| `created_at` | row insert 時間(server-side trusted) | DEFAULT now() | NOT NULL |
| `updated_by` | 後續 update 寫入者(flag_action_taken backfill / passive_slack_ack_at backfill) | (NULL default) | YES |
| `updated_at` | last update 時間 | (NULL default) | YES |
| `source_version` | schema version tag(未來 schema migration audit) | DEFAULT 'V107' | NOT NULL |

### 12.2 為什麼 V107 audit field 較 V103 §14 EXTEND 簡化(無 lease_id / approval_id / actor_id / bybit_payload / rationale)

per V103 §14 EXTEND 5 audit field 是針對 governance write event(hypothesis state transition / Earn stake/redeem)的設計;V107 M11 divergence log 性質不同:

- **V107 是 sensor write**,非 governance write event;不需 Decision Lease audit chain
- M11 nightly job 是 system process write,actor 永遠是 `m11_replay_engine`(或 cowork-agent backfill),不需 `actor_id` 額外 column(`created_by` 即可)
- M11 不發 Bybit API request → 不需 `bybit_request_payload`(M11 純 read self-hosted PG)
- M11 divergence rationale 已在 `evidence_json` JSONB 內提供;不需 separate `rationale` TEXT column
- Decision Lease 是 actuator concept,M11 是 sensor → 不需 `lease_id` / `approval_id`

故 V107 採 5 audit field(created_by/created_at/updated_by/updated_at/source_version),對齊 V106 sister table 範式,而非 V103 §14 EXTEND 10 audit field 範式。

### 12.3 Audit chain

per ADR-0024-lite Cowork operator-assistant + ADR-0008 Decision Lease audit chain:

- V107 row 寫入 audit chain:`created_by` ('m11_replay_engine' / 'cowork-agent') + `created_at` + `replay_run_id`(group by per-run)
- backfill audit:`updated_by` + `updated_at`(flag_action_taken / passive_slack_ack_at backfill)
- cross-module audit:`evidence_json` 內 `live_trace_id` + `replay_output` + `cohort_metadata` + `ab_test_id`(若 M9 active)

---

## §13 Acceptance Criteria (7 條)

### AC-1 Schema 完整性

- V107 apply 後 27 columns 齊全(per §2.1)
- 4 CHECK constraint 完整(divergence_type 7 值 + severity 3 值 + flag_action_taken 5 值 + engine_mode 5 值)
- 1 FK constraint(hypothesis_id → learning.hypotheses)
- 5 hot-path indexes + 1 mv unique index
- 1 hypertable + 2 policies(compression 30d + retention 90d)
- 1 materialized view

**Pass**:Round 1 dry-run 10 項全 PASS(per §9.3);Round 2 idempotency 全 PASS(per §9.4)。

### AC-2 Idempotency 驗證

V107.sql 重跑 2 次 → 0 RAISE / 0 重複 / NOTICE-only output

**Pass**:per §9.4 Round 2 後驗證 SQL 全 PASS。

### AC-3 反模式檢測 — Forbidden action column

per AC-5 (per M11 design spec) + CR-7:V107 schema 嚴禁含 `auto_demote` / `target_state` / `decay_recommendation` / `demote_proposal_id` / `decay_stage` / `stage_demoted` column

**Test**:per §9.5 grep V107.sql + IMPL PR

**Pass**:0 hit(per CR-7 M7 single decay authority 紀律)。任一 hit → AC FAIL,IMPL block,違反者 PR 拒絕。

### AC-4 H-11 反向 attack 6 條 mitigation 覆蓋

per §1.3 + M11 design spec §8:V107 schema 對 5/6 條 H-11 反向 attack 提供 mitigation 字段或設計

- H-11 #1(false positive 灌爆):severity ENUM 3 級 + writer NOISE gate
- H-11 #2(threshold drift):`baseline_5d_mean` + `baseline_5d_sigma` 每 row 鎖
- H-11 #4(M7 反向 attack 14d):`flag_action_taken='m7_decay_candidate'` 路由 + hot index 走 14d window query
- H-11 #5(M11+M7 race):soft reference m7_decay_signal_id(read-only consumer)
- H-11 #6(Slack 5d unack):`passive_slack_ack_at TIMESTAMPTZ` column + partial index `idx_div_unack_detected`

**Pass**:5/6 mitigation 覆蓋 + #3(M11 寫入失敗)由 writer 端處理(非 schema 層)。

### AC-5 Linux PG empirical dry-run gate

per CLAUDE.md §Data, Migrations, And Validation + V055/V083/V084 incident chain

**Test**:E2/E4/A3 review 必含 Linux PG dry-run × 2 round 證據 ID

**Pass**:Round 1 + Round 2 全 PASS + checksum repair binary 跑後 sqlx migrate runtime 0 panic。

### AC-6 Cross-V### dependency 解耦驗證

V107 land Sprint 1A-β 早於 V108 (Sprint 1A-γ) + V113 (Sprint 8),必走 soft reference 而非 hard FK 避免 dispatch ordering blocker

**Test**:V107 schema grep `REFERENCES learning.ab_tests`(V108)/ `REFERENCES learning.m7_decay_signals`(V113)

**Pass**:0 hit;`m9_ab_test_id` UUID soft reference + `m7_decay_signal_id` BIGINT soft reference;只 `hypothesis_id` 採 hard FK to V103(已 land Sprint 1A-α)。

### AC-7 MV CONCURRENTLY refresh 驗證

per §7.3 4h cron refresh,必走 CONCURRENTLY 路徑(unblock GUI Banner query)

**Test**:`REFRESH MATERIALIZED VIEW CONCURRENTLY learning.mv_latest_divergence_per_strategy;` 必成功(unique index 存在)

**Pass**:dry-run mv refresh CONCURRENTLY 不報錯;mv unique index `idx_mv_latest_div_strategy_symbol_type` 存在。

---

## §14 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT (drafted full DDL) | DONE | 2026-05-21 | 14 section + 22 column + 5 CHECK ENUM + 5 hot-path indexes + 1 mv + Guard A/C + Linux PG dry-run protocol;對齊 V106 sister table + V103 §14 EXTEND 範式 |
| PA | PENDING | — | C9 Linux PG dry-run 6 條 query 補資料(§9.2);M11 design spec §3.2 column 行為對齊驗證 |
| MIT (cross-check) | PENDING | — | feature-engineering-protocol skill leakage check(M11 replay engine 內 rolling-window 重建必並列 leak-free shift(1) 對比;per AC-7 of M11 design spec) |
| QC | PENDING | — | severity matrix 統計推導合理性 + per-strategy σ 對齊;OQ-2 per-strategy vs cohort-uniform σ 仲裁 |
| QA | PENDING | — | flag_action_taken 5 值 ENUM 對齊 §5.1 flag-action map + AC-4 proptest 規劃;passive_slack_ack 計時定義 |
| E4 | PENDING | — | Regression after IMPL Sprint 3 W15-18;AC-1/AC-2/AC-7 test harness 規劃 |
| E5 | PENDING | — | Hypertable + 30d compression(對齊 M7 14d window detector)+ 90d retention 驗證;mv refresh policy 4h cron 對 PG buffer 影響評估 |
| CC | PENDING | — | §13 14 section 完整性 + 16 原則合規 + Hard Boundaries 觸碰(0/5 預期);AC-5 反模式檢測證據 |
| FA | PENDING | — | Cross-V### dependency 解耦(AC-6) + soft reference vs hard FK 邊界紀律 + H-11 反向 attack 6 條覆蓋(AC-4) |
| PM | PENDING | — | Sprint 1A-β CRITICAL schema closure;V107 → V113/V108 land sequence ordering 仲裁 |

---

**END V107 M11 Replay Divergence Log Schema Migration Spec**
