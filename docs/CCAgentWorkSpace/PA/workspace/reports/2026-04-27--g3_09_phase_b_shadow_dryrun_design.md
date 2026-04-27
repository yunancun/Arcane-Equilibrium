# PA RFC — G3-09 Phase B: cost_edge_advisor shadow dry-run 觀察期

- **Date**: 2026-04-27
- **Author**: PA
- **Source RFC (Phase A)**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_09_cost_edge_ratio_design.md` §7.2 (1.5d ETA)
- **Phase A E1 report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-27--g3_09_phase_a_cost_edge_advisor.md`
- **Phase A E2 review**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-27--g3_09_phase_a_review.md` (PASS, 0 finding)
- **Predecessor commit**: `00682ef` on main (HEAD `9e21a7f7`)
- **Phase B baseline**: cargo lib **2290 / 0 fail** + healthcheck `[30]` PASS-skip + 38 new tests
- **Risk class**: 中（Phase B advisory remains — 0 trade impact；新增 IPC schema 欄位 + 1 SQL migration + healthcheck upgrade）

---

## §1 Phase B 範圍與目的

### 1.1 為何要 Phase B（而非直接 Phase C）

Phase A advisor 已能 `evaluate()` 並 emit transition log，但有 **3 個 Phase C 必答而 Phase A 答不出** 的問題：

1. **Trigger 頻率分佈未知** — RFC §7.2 寫「每天 0-5 次合理 / >50 過敏」，但這是 PA 估算，**未經實測驗證**。Phase A 只在狀態**轉換**時 log（Trigger ≠ trigger event count；持續 Trigger 1h 只 emit 1 行）。
2. **threshold = -0.5 在真實 demo 分佈下是否合理** 未證 — 可能永不觸發（dead gate）or 永遠觸發（noise）。Phase A 沒有取樣機制可推導 ratio histogram。
3. **per-strategy / per-symbol breakdown 缺位** — Phase A `evaluate` 是 portfolio-level 單一 ratio，但 Phase C 設計含 `StrategyOverride.cost_edge_threshold_override`，沒有 per-strategy ratio 樣本就無法 calibrate override。

Phase B 補齊這 3 個 gap，提供 Phase C 啟動所需的證據。

### 1.2 範圍邊界（in / out）

**IN（Phase B 必做）**：
- 持久化 evaluate cycle 採樣（不只是轉換 log）→ 新 SQL table `learning.cost_edge_advisor_log` (hypertable)
- IPC `get_cost_edge_advisor_status` 增 4 欄（`evaluations_24h` / `triggers_24h` / `last_trigger_ms` / `dryrun_observation_window_ms`）
- Healthcheck `[30]` 升級從「schema 哨兵」→「trigger frequency sanity check」
- 觀察期 ≥48h Linux runtime（per memory `feedback_demo_over_paper_for_edge` + Live 階段 7-day acceptance；採 48h 為快速驗證閾，full 7d 為完整 acceptance）
- 觀察期 deliverable：`docs/audits/YYYY-MM-DD--cost_edge_advisor_phase_b_observation.md`（含 per-strategy heatmap）
- 補 Phase A FUP `G3-09-PHASE-A-DAEMON-INTEGRATION-TEST P3`（Phase B 前置 prerequisite）

**OUT（明確 Phase C 範圍，本 sub-task 不做）**：
- IntentProcessor `would_reject_intent()` shadow check（Phase B 是「觀察 advisor 行為」非「shadow IntentProcessor 行為」— 後者屬 Phase C 一半工作量）
- `shadow_reject_count_24h: AtomicU64` 計數器（這需要 IntentProcessor 對接，屬 Phase C 範圍）
- per-strategy ratio 計算（需要 H5 cost_tracker 拆 per-strategy bucket，屬 G3-09 Phase D 或 H5 升級）
- RiskConfig `cost_edge_gate_enabled` flag（Phase C）
- StrategyOverride 增欄（Phase C）

> **Phase B 重定義（vs RFC §7.2 原計畫）**：Phase A E1 self-report 5.4 已標 `shadow_reject_count` 屬 Phase B，但細看 RFC §7.2 line 511 寫的 shadow check 必須改 `intent_processor/`，**這違反 Phase B「0 trade impact」原則**（即使 would-reject 是 pure fn，掛 IntentProcessor 入口就改變了 hot path 形狀，且必須跟 cost_gate 並排做 audit）。本 RFC 把「shadow IntentProcessor」整塊移到 Phase C，Phase B 退回**純 advisor observability**（觀察 advisor 自己的 evaluate cadence + ratio distribution + status transitions），這樣 Phase B → C 的 risk delta 才匹配 1.5d 工時估算。

### 1.3 與 Phase A 對比表

| 維度 | Phase A（已 land） | Phase B（本 RFC） |
|---|---|---|
| evaluate 頻率 | 每 10s | 每 10s（不變） |
| Log 形式 | transition log only（status change 才 emit） | + 持久化採樣（每 N cycle 1 row 或每 transition 1 row） |
| IPC schema | `status / ratio / threshold / data_days / last_eval_ms / triggered_at_ms / env_enabled / phase` | + `evaluations_24h / triggers_24h / last_trigger_ms / dryrun_observation_window_ms` |
| Healthcheck | env=0 PASS-skip / env=1 驗 TOML+module 存在 | env=0 PASS-skip / env=1 驗 trigger frequency sanity（>100/hr WARN spam，<1/day WARN starvation 條件式） |
| Trade impact | 0 | 0（**unchanged**） |
| Schema migration | 0 | 1 (V026 `learning.cost_edge_advisor_log`) |
| Rust 新模組 | `cost_edge_advisor/` | 0 新模組（修 mod.rs daemon loop + types.rs 增欄 + handlers/cost_edge_advisor.rs 增欄） |

---

## §2 觀察期設計

### 2.1 觀察視窗長度

**推薦 ≥48h Linux runtime + 完整 acceptance 7d**：

- **Tier 1 早期信號 (≥48h)**：可確認 daemon spawn → poll → log → IPC schema 全鏈無 panic / DB 失常 / log spam；trigger frequency 數量級可初判
- **Tier 2 完整 acceptance (≥7d)**：對齊 CLAUDE.md §三 demo ≥21d 穩定期 + Live 階段 7-day acceptance；ratio distribution 採樣足以估算 percentile（5th/50th/95th）

**為何不直接 7d 才驗收**：
- ≥48h 早期信號可發現結構性 bug（log volume 失控 / DB INSERT 阻塞 daemon），早於 G3-09 Phase C 計畫前介入
- Phase A merge 後 `00682ef` 已 land，operator 隨時可開 env=1 + flag=true 啟動觀察；不必綁定固定 wall-clock 週數
- 對齊 memory `feedback_demo_over_paper_for_edge` — demo 才有意義 PnL 樣本；live 階段未到不能用 live 數據

**啟動條件**（**必須**全綠才開觀察期）：
1. ✅ Phase A `00682ef` 已 land + Linux engine restart 後 daemon spawned（log 含 `cost_edge_advisor daemon starting`）
2. ✅ env=1 + `RiskConfig.cost_edge.enabled=true` 兩條件 AND（雙保險）
3. ✅ V026 migration 套用（手動 `bash linux_bootstrap_db.sh --apply` 或 `OPENCLAW_AUTO_MIGRATE=1`）
4. ✅ `[30]` healthcheck 升級版 deploy（pure-Python TOML+SQL count check，無 IPC 依賴）
5. ✅ FUP `G3-09-PHASE-A-DAEMON-INTEGRATION-TEST` 補完（daemon spawn → poll → log → IPC 全鏈整合測試 1 個 cargo `--release` 通過）

### 2.2 觸發頻率合理性指標

**3 層 sanity range**（per environment / per measurement window）：

| 指標 | Healthy | WARN | FAIL |
|---|---|---|---|
| `evaluations_24h` | ≥ 8000（10s cycle × 86400s × 95% uptime） | 4000-8000（partial outage） | < 4000（daemon 半死） |
| `triggers_24h`（=== 進入 Trigger 狀態的 transition count） | 0-10/day | 11-50/day（noise risk） | > 50/day（calibrate threshold） |
| `triggers_per_hour` peak | ≤ 5/hr | 6-20/hr | > 20/hr |
| `triggers_per_hour` floor | ≥ 1/week (0.006/hr 累積，避 dead gate) | 0/week 但 ratio histogram 有靠近 threshold 的 sample | 0/week 且 ratio histogram 完全離 threshold ≥0.3 |

**rationale**：
- Phase A daemon 每 10s evaluate → 24h 預期 8640 cycle；`evaluations_24h` < 4000 必有 daemon 半死或 IPC 寫入阻塞
- `triggers_24h` 0-10 是 RFC §7.2 line 518 估算（PA 直覺），Phase B 觀察期取得真實數據後可在 deliverable 報告中校正
- per-hour peak 觀察是否有 burst pattern（如交易高峰時 H5 cost_edge_ratio 集中下跌）
- per-hour floor 觀察 dead gate（threshold 設太鬆，永不觸發） — 需要 ratio histogram 輔助判斷（不只看 trigger，還看「有多少 cycle 的 ratio 在 threshold ±0.1 帶內」）

### 2.3 Ratio distribution 採樣

**新增 column `ratio` 持久化** 在每次 `evaluate()` 都記錄一次（非僅 transition）。Phase B 取樣策略：

- **Down-sample to 1/min**：daemon 每 10s evaluate，但只每 6 cycle (60s) 寫一次 `learning.cost_edge_advisor_log` row，避免 24h 8640 row 過量（降為 1440 row/day）
- 24h 1440 row × 7d = 10k row（hypertable + retention 30d 自動清理）
- 觀察期 deliverable：histogram 用全 1440 × N day row 算 percentile，trigger transition 用獨立 emit log（不 down-sample）

### 2.4 Logging schema（避 `decision_outcomes` 2 bug 教訓）

**避 memory `project_decision_outcomes_not_dead` 2 bug**：
1. ❌ `outcome_*` 100% NULL（timeframe 字串格式 `'1' vs '1m'` 不一致）
2. ❌ `engine_mode` 100% `'paper'`（INSERT 漏接線）

**Phase B 對應防線**：
- ✅ schema 直接定義 `engine_mode TEXT NOT NULL CHECK (engine_mode IN ('paper','demo','live','live_demo'))` — 不允許默認值，INSERT 路徑必須顯式 bind
- ✅ 不存 `timeframe`（Phase B 觀察的是 advisor 全域 cycle，不依賴 K 線 timeframe）
- ✅ 所有欄位 NOT NULL 或 explicit DEFAULT，避免 silent NULL 蓄積
- ✅ Migration 加 Guard A（`learning.cost_edge_advisor_log` 已存在則驗欄位齊全；空表 + 欄位齊全 = no-op；表存在但欄位缺則 RAISE）
- ✅ Migration 加 Guard B（`engine_mode` column type 必須 TEXT；驗 `information_schema.columns.data_type`）
- ✅ healthcheck 加 INSERT smoke check（驗最近 1h 至少有 1 row 寫入；env=1 才查）

**Schema 提案**（V026）：

```sql
-- V026__cost_edge_advisor_log.sql
-- G3-09 Phase B: persist cost_edge_advisor evaluate cycles for trigger
-- frequency analysis (PA RFC 2026-04-27).

DO $$
DECLARE
    v_table_exists BOOLEAN;
    v_missing_cols TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='cost_edge_advisor_log'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        -- Guard A: legacy table must have all required columns.
        SELECT string_agg(c, ', ') INTO v_missing_cols FROM (
            SELECT unnest(ARRAY[
                'ts_ms','engine_mode','status','ratio','threshold',
                'data_days','ai_spend_7d_usd','paper_pnl_7d_usd',
                'is_stale','phase','transition_from'
            ]) AS c
            EXCEPT
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='cost_edge_advisor_log'
        ) sub;
        IF v_missing_cols IS NOT NULL THEN
            RAISE EXCEPTION
                'V026 Guard A FAIL: learning.cost_edge_advisor_log exists but '
                'missing columns: %. Drop legacy table or run rollback before '
                'retrying.', v_missing_cols;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.cost_edge_advisor_log (
    ts_ms              BIGINT  NOT NULL,
    engine_mode        TEXT    NOT NULL CHECK (engine_mode IN ('paper','demo','live','live_demo')),
    status             TEXT    NOT NULL,  -- CostEdgeAdvisorStatus serde string
    ratio              DOUBLE PRECISION,  -- nullable: WarmUp/Disabled/Anomaly
    threshold          DOUBLE PRECISION NOT NULL,
    data_days          INTEGER NOT NULL,
    ai_spend_7d_usd    DOUBLE PRECISION NOT NULL,
    paper_pnl_7d_usd   DOUBLE PRECISION NOT NULL,
    is_stale           BOOLEAN NOT NULL,
    phase              TEXT    NOT NULL DEFAULT 'B_shadow',
    transition_from    TEXT,              -- nullable: 只在狀態改變時填 prev_status
    PRIMARY KEY (ts_ms, engine_mode)
);

-- Guard B: engine_mode must be TEXT (legacy CREATE TABLE may have used VARCHAR).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='learning' AND table_name='cost_edge_advisor_log') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='cost_edge_advisor_log'
              AND column_name='engine_mode' AND data_type='text'
        ) THEN
            RAISE EXCEPTION
                'V026 Guard B FAIL: learning.cost_edge_advisor_log.engine_mode '
                'must be TEXT (got %)', (
                    SELECT data_type FROM information_schema.columns
                    WHERE table_schema='learning' AND table_name='cost_edge_advisor_log'
                      AND column_name='engine_mode'
                );
        END IF;
    END IF;
END $$;

-- Hypertable for time-series rotation.
SELECT create_hypertable(
    'learning.cost_edge_advisor_log', 'ts_ms',
    chunk_time_interval => 86400000,  -- 1 day in ms
    if_not_exists => TRUE
);

-- 30-day retention (Phase B observation period; can extend Phase C).
SELECT add_retention_policy(
    'learning.cost_edge_advisor_log', BIGINT '2592000000',
    if_not_exists => TRUE
);

-- Indexes (Guard C optional — analytical queries don't need hot-path indexes).
CREATE INDEX IF NOT EXISTS idx_cea_log_status_ts
    ON learning.cost_edge_advisor_log (status, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_cea_log_engine_mode_ts
    ON learning.cost_edge_advisor_log (engine_mode, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_cea_log_transitions
    ON learning.cost_edge_advisor_log (ts_ms DESC)
    WHERE transition_from IS NOT NULL;
```

**Idempotency**：套兩次 `psql -f V026__cost_edge_advisor_log.sql`，第二次 Guard A 看到表存在 + 欄位齊全 → no-op；Guard B 看到 TEXT 對 → no-op；CREATE TABLE/INDEX/hypertable/retention 都 IF NOT EXISTS。

### 2.5 INSERT 路徑

**Rust daemon 每 10s evaluate 後**：
- 若距離上次 INSERT < 60s 且 `new_state.status == prev_status` → 跳過（down-sample 到 1/min）
- 若 `new_state.status != prev_status` → 立即 INSERT（transition row，`transition_from = prev_status_serialized`）
- 否則（時間到 60s）→ INSERT（cycle row，`transition_from = NULL`）

**Pool**：複用既有 `database/quality_writer.rs` pattern — `tokio::spawn(async move {...})` fire-and-forget，不阻 daemon evaluate；INSERT 失敗 `warn!` log 但不 panic。

**INSERT failure mode**：
- DB down → log warn，下次 cycle 重試（最多 1/min log spam）
- INSERT slow → tokio::spawn 不阻 daemon，最多丟 row 但 daemon 持續運轉
- pool 耗盡 → 同上，warn log + drop row

---

## §3 IPC schema 升級

### 3.1 新增 4 欄

```rust
// types.rs CostEdgeAdvisorState extension (Phase B)
pub struct CostEdgeAdvisorState {
    // Phase A 既有欄位
    pub status: CostEdgeAdvisorStatus,
    pub ratio: Option<f64>,
    pub threshold: f64,
    pub data_days: i32,
    pub ai_spend_7d_usd: f64,
    pub paper_pnl_7d_usd: f64,
    pub last_eval_ms: i64,
    pub triggered_at_ms: i64,
    pub env_enabled: bool,
    pub phase: String,

    // Phase B 新增（4 欄）
    pub evaluations_24h: u64,           // rolling 24h cycle count
    pub triggers_24h: u64,              // rolling 24h Trigger transition count
    pub last_trigger_ms: i64,           // 最近一次 Trigger transition timestamp
    pub dryrun_observation_window_ms: i64,  // = now - daemon_start_ms (helps healthcheck judge maturity)
}
```

**Forward-compat**：使用 `#[serde(default)]` for new fields 讓 Phase A consumer (e.g. healthcheck `[30]` 已 deploy 版) 忽略未知欄位無 panic。

**Counters 在 daemon 內維護**：
- `evaluations_24h`：rolling window，每 cycle +1，每分鐘 sweep 移除 > 24h 舊 cycle 紀錄（簡化：daemon 內存 `VecDeque<i64>`，push_back + pop_front while ts < now - 86400000）
- `triggers_24h`：同 pattern，only transition into Trigger 才 push
- `last_trigger_ms`：transition into Trigger 時 update
- `dryrun_observation_window_ms`：daemon 啟動時記 `daemon_start_ms`，每次 IPC query 算差

### 3.2 `phase: "B_shadow"` 改名

Phase A 欄位 `phase: "A_advisory"` 在 Phase B 改 `"B_shadow"`（即使本 Phase B 重定義不再做 IntentProcessor shadow，沿用「shadow」字眼避免再改名 → 對應 RFC §7.2 與 PM Tier 9 命名連續性）。

> **替代方案考慮**：改 `"B_observation"` 更精確但破壞與 RFC §7.2 + 既有 audit log 的字串連續性。決策：保 `B_shadow`，docstring 標 「Phase B observation period — no IntentProcessor shadow check (deferred to Phase C)」。

---

## §4 Healthcheck `[30]` 升級

### 4.1 從 schema 哨兵 → trigger frequency sanity check

**Phase A `[30]`**：env=0 PASS-skip / env=1 驗 TOML + module 存在（pure-Python，無 DB query）

**Phase B `[30]` 升級版**：env=0 PASS-skip / env=1 驗 4 個 invariant（query DB + IPC optional）

```python
# helper_scripts/db/passive_wait_healthcheck/checks_derived.py
# Phase B 升級版（替換 Phase A check_cost_edge_advisor_status）

def check_cost_edge_advisor_status() -> tuple[str, str]:
    """[30] G3-09 Phase B (2026-04-29): cost_edge_advisor trigger frequency sanity.

    EN: Replaces Phase A schema sentinel with trigger-rate observability:
      Path A (env=0): PASS-skip (dormant by design)
      Path B (env=1):
        Inv 1: TOML [cost_edge] section parses (kept from Phase A)
        Inv 2: Rust module files exist (kept from Phase A)
        Inv 3: learning.cost_edge_advisor_log INSERTs in last 1h (DB freshness)
        Inv 4: triggers_per_hour within sanity range (peak <= 20/hr; if >20/hr WARN spam;
                if 0/week + ratio_distribution all >threshold+0.3 WARN dead gate)
    """
    # ... (Path A unchanged)
    # ... (Inv 1+2 reused from Phase A check)

    # Inv 3: DB freshness (1h INSERT proof)
    cur.execute("""
        SELECT COUNT(*) FROM learning.cost_edge_advisor_log
        WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 3600000
    """)
    inserts_1h = cur.fetchone()[0]
    if inserts_1h == 0:
        # daemon 應該每 60s INSERT 1 row → 1h 至少 50+ row（含 down-sample 容差）
        return ("FAIL", f"learning.cost_edge_advisor_log no INSERT in last 1h "
                        f"(env=1 但 daemon 寫入路徑斷)")
    if inserts_1h < 30:
        return ("WARN", f"learning.cost_edge_advisor_log only {inserts_1h} rows/1h "
                        f"(預期 ~60，可能 daemon 卡或 INSERT 慢)")

    # Inv 4: Trigger frequency sanity
    cur.execute("""
        SELECT COUNT(*) FROM learning.cost_edge_advisor_log
        WHERE ts_ms > (extract(epoch from now()) * 1000)::BIGINT - 3600000
          AND transition_from IS NOT NULL
          AND status = 'Trigger'
    """)
    triggers_1h = cur.fetchone()[0]
    if triggers_1h > 20:
        return ("WARN", f"cost_edge_advisor triggers_per_hour={triggers_1h} > 20 "
                        f"(可能 threshold 過嚴 / noise spam — calibrate before Phase C)")

    # Dead gate detection (only in mature observation window)
    cur.execute("""
        SELECT MIN(ts_ms), COUNT(*) FROM learning.cost_edge_advisor_log
    """)
    earliest_ms, total_rows = cur.fetchone()
    observation_days = (now_ms() - earliest_ms) / 86400000.0 if earliest_ms else 0
    if observation_days >= 7:
        cur.execute("""
            SELECT COUNT(*) FROM learning.cost_edge_advisor_log
            WHERE transition_from IS NOT NULL AND status = 'Trigger'
        """)
        total_triggers = cur.fetchone()[0]
        if total_triggers == 0:
            # ratio histogram check: any sample within threshold ±0.3?
            cur.execute("""
                SELECT COUNT(*) FROM learning.cost_edge_advisor_log
                WHERE ratio IS NOT NULL
                  AND ratio < threshold + 0.3
            """)
            near_threshold = cur.fetchone()[0]
            if near_threshold == 0:
                return ("WARN", f"cost_edge_advisor 0 triggers in {observation_days:.1f}d "
                                f"+ ratio histogram all > threshold+0.3 (DEAD GATE: "
                                f"threshold 過鬆，不 trigger calibrate to ratio 5th percentile)")

    return ("PASS", f"cost_edge_advisor env=1 healthy: {inserts_1h} insert/h, "
                    f"{triggers_1h} trigger/h, {total_rows} total rows, "
                    f"window={observation_days:.1f}d")
```

**為何不直接走 IPC `get_cost_edge_advisor_status`**：對齊 Phase A 設計哲學（避 cron 與 HMAC + 主進程耦合）— DB query 只需 PG 連線。IPC counter 仍由 Rust daemon 維護供 GUI 即時讀取。

### 4.2 上 / 下界錨定原則

| 偏好 | 上界（spam） | 下界（dead gate） |
|---|---|---|
| 偏嚴 | > 20/hr WARN | 0 trigger in 7d + ratio all > threshold+0.3 → WARN |
| 偏鬆 | > 50/hr FAIL | 0 trigger in 7d 但 ratio 有 < threshold+0.3 sample → PASS（threshold 設定 OK，只是 ratio 沒到） |

決策採偏嚴上界 + 偏鬆下界（fail-closed for spam，fail-open for starvation — starvation 不會壞事，spam 會撐爆 DB）。

---

## §5 觀察期 Deliverable 模板

### 5.1 報告路徑

`docs/audits/YYYY-MM-DD--cost_edge_advisor_phase_b_observation.md`

### 5.2 報告骨架

```markdown
# G3-09 Phase B cost_edge_advisor — Observation Report

- **Date range**: YYYY-MM-DD HH:MM ~ YYYY-MM-DD HH:MM (X.X days)
- **Engine PID(s)**: NNNN, NNNN (restart events: list)
- **Env**: OPENCLAW_COST_EDGE_ADVISOR=1 + RiskConfig.cost_edge.enabled=true
- **Threshold**: -0.5 (demo/paper) / -0.3 (live) — per Phase A lock-in

## §1 Counters (24h rolling at report time)

| Metric | Value | Verdict (per RFC §2.2) |
|---|---|---|
| evaluations_24h | NNNN | Healthy / WARN / FAIL |
| triggers_24h | NN | Healthy / WARN / FAIL |
| triggers_per_hour peak | NN | Healthy / WARN / FAIL |
| triggers_per_week count | NN | Healthy / WARN / FAIL |

## §2 Status distribution (% time in each status, last 7d)

| Status | % time | row count |
|---|---|---|
| Disabled | X.X% | NNNN |
| WarmUp | X.X% | NNNN |
| OK | X.X% | NNNN |
| Trigger | X.X% | NNNN |
| Stale | X.X% | NNNN |
| Anomaly | X.X% | NNNN |

## §3 Ratio histogram (per engine_mode)

(insert ASCII histogram or matplotlib png path; bins -2.0 / -1.5 / -1.0 / -0.5 / 0 / 0.5)

## §4 Per-strategy / per-symbol breakdown (defer if H5 not ready)

NOTE: Phase A H5 cost_edge_ratio is portfolio-level (not per-strategy).
This section reports portfolio-only until G3-09 Phase D / H5 升級 拆 per-strategy bucket.

## §5 Healthcheck [30] verdict trail (cron 6h × 7d = 28 samples)

| Time | Verdict | Message |
|---|---|---|
| YYYY-MM-DD HH:MM | PASS | ... |

## §6 Recommendation (Phase C readiness)

- [ ] >= 7d observation window matured
- [ ] triggers_per_day in healthy range (0-10)
- [ ] no FAIL on healthcheck [30] over 28 samples
- [ ] threshold calibration: keep at -0.5 / adjust to ratio 5th percentile = X.X
- [ ] per-strategy override candidates: list

GO / NO-GO Phase C: [PA + PM joint sign-off]
```

### 5.3 Heatmap 渲染（per-symbol per-strategy）

由於 Phase A H5 cost_edge_ratio 是 portfolio-level，per-symbol per-strategy heatmap 在 Phase B 暫不可行。**改提供**：

- per-status × per-engine_mode heatmap（status × {paper, demo, live} 6×3 grid，cell 值 = % time）
- per-hour-of-day Trigger count heatmap（24h × 7day 168 cell，揭露時段性 burst）

per-strategy heatmap 寫進 Phase D / H5 升級 backlog ticket（`G3-09-PHASE-D-PER-STRATEGY-RATIO P3`）。

---

## §6 風險識別 + Mitigation

### 6.1 Risk 矩陣

| # | 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|---|
| **R-B1** | advisory log volume 失控（per AI-E budget concerns）| 中 | 中（DB INSERT 慢拖 daemon）| (a) Down-sample 1/min（24h 1440 row）+ (b) hypertable 30d retention 自動 cleanup + (c) tokio::spawn 不阻 daemon + (d) healthcheck Inv 3 提前發現 INSERT 飽和 |
| **R-B2** | threshold = -0.5 真實分佈下永不觸發（dead gate）| 中 | 中（advisor 失效）| (a) Phase B 觀察期 ratio histogram 採樣 (b) healthcheck Inv 4 dead gate WARN at 7d (c) deliverable §6 提 calibrate to 5th percentile (d) Phase C 啟動前 PM 必審 deliverable |
| **R-B3** | threshold = -0.5 永遠觸發（noise）| 低（Phase A T9-LOW-1 已選保守 -0.5）| 中（healthcheck FAIL spam）| (a) healthcheck WARN at 20/hr (b) 觀察期 calibrate (c) IPC patch_risk_config 60s rollback |
| **R-B4** | Phase A FUP `daemon-integration-test` 缺 → Phase B observation 看到的 row 是否真的 daemon 寫入無從驗證 | 中 | 中（無 ground truth） | **本 RFC §7 派發加 prerequisite：先補 daemon integration test 再開觀察期**（FUP 升 P1）|
| **R-B5** | down-sample 1/min 漏 burst trigger | 低 | 低（transition row 不 down-sample）| transition_from IS NOT NULL 的 row 永遠 INSERT（非 down-sample），確保 burst 100% 紀錄 |
| **R-B6** | V026 migration 與 V025 順序衝突 | 低 | 中（migration 失敗）| V026 完全獨立 schema（learning.cost_edge_advisor_log 新表），與 V025 outcome_backfill_pending_index 0 overlap |
| **R-B7** | uvicorn 4 worker 各自 query DB → 4× load | 低 | 低（健康檢查 6h 1 次） | healthcheck 是 cron 跑（單進程），不在 uvicorn worker 內；DB query 6h 4 row + count 級別輕量 |
| **R-B8** | rolling 24h counter 在 daemon restart 後重置 → triggers_24h 短期偏低 | 中（每次 restart） | 低（healthcheck 用 DB 查不依賴 IPC counter） | (a) IPC counter 標 `dryrun_observation_window_ms` 暴露 daemon uptime (b) healthcheck §4.1 Inv 4 用 DB 查不依賴 in-memory counter |
| **R-B9** | engine_mode 寫死 vs 不同 worker 不同 mode | 低 | 中（log 失準）| daemon 啟動時讀 `RiskConfig.engine_mode`（已是 paper/demo/live 之一），bind 到 INSERT；engine_mode 變 = restart engine = 新 daemon 新 mode，不會 mid-run 跳變 |
| **R-B10** | Phase A E1 self-report 5.4 「daemon 整合測試屬 E4 regression scope」未補 → Phase B 上 1 SQL migration 又無 daemon 級驗證 | 中 | 高（積累技術債） | 本 RFC §7 強制把 daemon integration test 列為 Phase B prerequisite（不是 Phase B 內 E1 任務）|

### 6.2 Top 3 風險細解

#### R-B1 advisory log volume 失控

**情境**：daemon 改成每 cycle INSERT（沒 down-sample）→ 24h 8640 row × hypertable chunk 1day = chunk 撐爆；tokio::spawn DB pool 飽和導致 evaluate cycle 阻塞。

**緩解**：
- 1/min down-sample（cycle row）+ transition row immediate（不 down-sample 但 transition 罕見）
- INSERT 走 `tokio::spawn(async move {...})` 完全異步
- healthcheck Inv 3 設下限 30 row/h（< 30 WARN）+ 上限隱含（hypertable 自動 chunk）
- 30d retention auto-prune

#### R-B2 dead gate

**情境**：threshold = -0.5 太鬆，demo/paper ratio 永遠 > -0.5 → status 卡 OK → Phase C 啟動後 cost_edge_gate_enabled=true 無實際 gate 效果。

**緩解**：
- Phase B 7d 觀察期 ratio histogram 強制採樣（每分鐘 1 row × 7d = 10080 row）
- healthcheck Inv 4 在 7d 後若 0 trigger + ratio 全離 threshold ≥0.3 → WARN dead gate
- deliverable §6 強制算 ratio 5th percentile，建議 threshold calibrate
- Phase C 啟動前 PM checklist 必審 deliverable

#### R-B4 缺 daemon integration test

**情境**：Phase A 32 unit tests 全綠但缺 daemon level（spawn → 10s loop → IPC → 觀察 state 變化），Phase B 又上 SQL INSERT path，若 daemon spawn 路徑斷我們 0 個測試會失敗，只能等 healthcheck Inv 3 在 1h 後才察覺。

**緩解**：
- Phase B prerequisite：補 `tests/cost_edge_advisor_integration.rs`（cargo `--release`，spawn daemon → 模擬 H5 cache populate → 等 30s → 驗 advisor.state.status changed → 驗 audit emit hint counted）
- 此 prerequisite 屬 Phase A FUP `G3-09-PHASE-A-DAEMON-INTEGRATION-TEST` 升 P1（非本 Phase B 任務範圍，但 Phase B 啟動前必綠）

---

## §7 Phase B 範圍：是否需要新 Rust 程式碼

**有，但量很少** — 約 +180 LOC Rust + V026 SQL migration + Python healthcheck upgrade，**不算純 observability tooling**。

| Layer | 改動 | LOC 估算 |
|---|---|---|
| **Rust new** | 0 新 module | 0 |
| **Rust modified** | mod.rs daemon loop 加 INSERT path + counter maintenance + types.rs 增 4 欄 + handlers/cost_edge_advisor.rs serialize 4 欄 + daemon integration test | ~180 |
| **SQL** | V026 migration | ~120 (含 Guard A/B/C) |
| **Python** | healthcheck `[30]` 升級（替換 Phase A schema check 為 frequency sanity） | ~80 |
| **Tooling** | observation report generator script (`helper_scripts/research/cost_edge_advisor_observation_report.py`) | ~150 |

**為何不能純 Python observability tooling**：
- 持久化採樣必須在 daemon 內（Python 能查 IPC 但 IPC 是 snapshot，不能保證 cycle 級採樣不漏）
- counter 在 Rust daemon 內維護才能 lock-free 高頻 query（Python 走 IPC 加 6h cron 不可能 8640 cycle/day）
- transition_from 欄位必須 daemon prev_status 變化時 INSERT，Python 路徑無法觀察到 cycle-level transition

**為何 Rust 改動 ≤ 200 LOC**：daemon 主迴圈已就位，只加 INSERT path + counter window + 4 schema field；新測試 ~80 LOC；schema 升級 ~100 LOC。

---

## §8 副作用識別

| 改動面 | 副作用 | 緩解 |
|---|---|---|
| `cost_edge_advisor/mod.rs` daemon loop 加 INSERT | DB pool 多 1 connection user；INSERT 失敗 log | tokio::spawn fire-and-forget；warn-only |
| `types.rs` `CostEdgeAdvisorState` +4 fields | serde JSON shape 變 → Python consumer 需 forward-compat | 已在 §3.1 設 `#[serde(default)]` |
| IPC handler `cost_edge_advisor.rs` serialize 4 fields | wire size 略增（~80 bytes/request） | 可忽略（IPC binary 6h 1 次） |
| V026 migration | 新 hypertable 加 schema | Guard A/B 防 legacy drift；30d retention 自動清 |
| healthcheck `[30]` 升級 | Phase A 簡單 check → 多 DB query | env=0 PASS-skip 路徑不變；env=1 加 2 次 DB query（cron 6h 1 次無壓力） |
| Down-sample 1/min | observability 樣本減 6× | transition row 不 down-sample 確保 burst 100% 記錄；ratio histogram 1440/day 已足計 percentile |

**未涉及**：
- ❌ 不改 IntentProcessor（Phase C）
- ❌ 不改 cost_gate（Phase C）
- ❌ 不改 RiskConfig.cost_edge schema（Phase A 已就位）
- ❌ 不改 5 項 §四 live 硬邊界
- ❌ 不改 H5 cost_tracker（H5 升級屬 Phase D）

---

## §9 Cross-env 安全保證

| 環境 | Phase B 行為 |
|---|---|
| **paper** | env=1 + flag=true → INSERT log；engine_mode='paper'；ratio 計算同 Phase A；healthcheck Inv 3+4 啟用 |
| **demo** | 同 paper；engine_mode='demo'；**deliverable 主數據源**（per memory `feedback_demo_over_paper_for_edge`） |
| **live (LiveDemo)** | 同 paper；engine_mode='live_demo'；ratio 用 live paper_pnl proxy；deliverable 算 ratio histogram 但 trigger 解讀需附加 「LiveDemo simulation」marker |
| **live (Mainnet)** | 暫不 enable（Operator 顯式批准前不開）；env=0 default保護 |

3 env TOML `[cost_edge]` section 在 Phase A 已分離（per memory `feedback_env_config_independence`），Phase B 不改 TOML schema，僅延用。

---

## §10 16 根原則合規對照

| # | 原則 | 影響 | 措施 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | Phase B 不改寫入路徑 |
| 2 | 讀寫分離 | ✅ | advisor 仍只讀 H5；新 INSERT 寫到獨立 `learning.cost_edge_advisor_log`（observability schema）|
| 3 | AI 輸出 ≠ 命令 | ✅ | Phase B 仍 advisory only |
| 4 | 策略不繞風控 | ✅ | 不接 IntentProcessor |
| 5 | 生存 > 利潤 | ✅ | 0 close path 改動 |
| 6 | 失敗默認收縮 | ✅ | env=0 default + INSERT 失敗 warn-only 不阻 daemon |
| 7 | 學習 ≠ 改寫 Live | ✅ | 觀察期數據屬學習平面，calibration 走 Operator manual approve |
| 8 | 交易可解釋 | ✅ | log 含 ratio/threshold/data_days/transition_from |
| 9 | 災難保護 | ✅ | DB down → daemon 不 panic；最多丟 INSERT row |
| 10 | 認知誠實 | ✅ | engine_mode='live_demo' 標記；deliverable 必標 paper proxy |
| 11 | Agent 自主權 | ✅ | 不限制 Agent 能力 |
| 12 | 持續進化 | ⭐ | observation period 是 calibration 證據基礎 |
| 13 | AI 成本感知 | ⭐⭐⭐ | Phase B 是 #13 落地的證據環節 |
| 14 | 零外部成本 | ✅ | 0 新 LLM/API 依賴 |
| 15 | 多 Agent 協作 | 中性 |
| 16 | 組合級風險 | ✅ | log 是 portfolio-level metric |

**§四 5 項 live 硬邊界**：全 5 項零觸碰 ✅

---

## §11 E1 Prompt Template — Phase B 落地（self-contained）

下次 session PM 直接 paste 給 E1（含 logging schema / healthcheck upgrade / observation tooling / acceptance）。

````markdown
## 任務：G3-09 Phase B — cost_edge_advisor shadow dry-run observability

### 背景

PA RFC `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_09_phase_b_shadow_dryrun_design.md`
landed Phase A `00682ef`（2026-04-27）：Rust ~1338 LOC cost_edge_advisor + 38 tests +
3 TOML + healthcheck [30]，advisory only（0 trade impact）。Phase B 範圍 = 持久化
evaluate cycle 採樣（1/min down-sample）+ IPC schema 增 4 欄 + healthcheck [30] 升級
trigger frequency sanity check + V026 migration + observation report tooling。

**Phase B 仍是 advisory only — 0 trade impact 不變**（不接 IntentProcessor，那屬 Phase C）。

### 前置驗證（開工前必跑）

```bash
# Phase A 已 land
git log --oneline -10 | grep "G3-09 Phase A" || echo "❌ Phase A not landed"

# Phase A FUP G3-09-PHASE-A-DAEMON-INTEGRATION-TEST 必先綠（本 Phase B prerequisite）
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && \
  cargo test --release -p openclaw_engine --lib cost_edge_advisor::integration"
# 預期：≥1 integration test 通過（spawn daemon → mock H5 → state transition observed）
# 若無此 test：先派 E1 補完 prerequisite 再開 Phase B

# Phase A baseline cargo lib
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib | tail -3"
# 預期：2290 passed / 0 failed (Phase A baseline)

# 既有 healthcheck [30] PASS
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep '\[30\]'"
# 預期：[30] cost_edge_advisor_status PASS or PASS-skip
```

### 改動文件（修改 4 + 新建 4）

#### 修改（Rust，3 檔）

1. `rust/openclaw_engine/src/cost_edge_advisor/mod.rs` — daemon loop 加：
   - INSERT path：cycle row down-sample 1/min + transition row 即時 INSERT
   - counter window：`evaluations_24h` / `triggers_24h` / `last_trigger_ms` rolling
   - daemon_start_ms 記錄，IPC handler 算 `dryrun_observation_window_ms`
   - 估 ~120 LOC

2. `rust/openclaw_engine/src/cost_edge_advisor/types.rs` — `CostEdgeAdvisorState` 加 4 fields:
   - `evaluations_24h: u64` + `triggers_24h: u64` + `last_trigger_ms: i64`
     + `dryrun_observation_window_ms: i64`
   - 全用 `#[serde(default)]` for forward-compat
   - `phase` field default 改 `"B_shadow"`（保字串連續性，docstring 標 observation only）
   - 估 ~30 LOC

3. `rust/openclaw_engine/src/ipc_server/handlers/cost_edge_advisor.rs` — serialize 4 new fields
   - `advisor_disabled_response` 加 4 default 0 fields
   - 估 ~30 LOC

#### 新建（Rust，1 檔）

4. `rust/openclaw_engine/tests/cost_edge_advisor_integration.rs` (or `cost_edge_advisor/integration_tests.rs`)
   - 至少 3 test：
     - `daemon_spawns_and_polls`（env=1 + flag=true → daemon spawn → 30s 後 advisor.state populated）
     - `cycle_row_down_sampled_to_1_per_minute`（mock 60s × 6 cycle，驗 INSERT 1 次）
     - `transition_row_inserted_immediately`（mock state change，驗 transition row INSERT 即時）
   - 估 ~250 LOC

#### 新建（SQL，1 檔）

5. `sql/migrations/V026__cost_edge_advisor_log.sql` — per RFC §2.4 全文（含 Guard A + Guard B
   + create_hypertable + add_retention_policy + 3 indexes）
   - 估 ~120 LOC

#### 修改（Python，1 檔）

6. `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` —
   `check_cost_edge_advisor_status` 升級（替換 Phase A schema check）：
   - Path A env=0 PASS-skip（不變）
   - Path B env=1：加 Inv 3 (DB freshness 1h INSERT count) + Inv 4 (trigger frequency
     sanity, dead gate detection at 7d)
   - 估 ~80 LOC（保留 Phase A Inv 1+2，新增 Inv 3+4）

#### 新建（Python tooling，1 檔）

7. `helper_scripts/research/cost_edge_advisor_observation_report.py` —
   生成 deliverable markdown（per RFC §5.2 模板）：
   - PG 連線查 `learning.cost_edge_advisor_log`
   - 算 §1 counters / §2 status distribution / §3 ratio histogram (ASCII or matplotlib png)
     / §5 healthcheck verdict trail (查 cron log)
   - 輸出 `docs/audits/YYYY-MM-DD--cost_edge_advisor_phase_b_observation.md`
   - 估 ~150 LOC

#### 新建（docs，1 檔）

8. `docs/CCAgentWorkSpace/E1/workspace/reports/YYYY-MM-DD--g3_09_phase_b_observability.md` —
   E1 任務報告（per CLAUDE.md §七 6 節結構）

### 具體實作要點

#### Counter rolling window

```rust
// mod.rs daemon loop
struct EvalCounters {
    eval_timestamps: VecDeque<i64>,    // for evaluations_24h
    trigger_timestamps: VecDeque<i64>, // for triggers_24h
    last_trigger_ms: i64,
    daemon_start_ms: i64,
    last_insert_ms: i64,               // for 1/min down-sample
}

impl EvalCounters {
    fn record_cycle(&mut self, now_ms: i64) {
        self.eval_timestamps.push_back(now_ms);
        let cutoff = now_ms - 86400000;
        while self.eval_timestamps.front().map_or(false, |&ts| ts < cutoff) {
            self.eval_timestamps.pop_front();
        }
    }
    fn record_trigger(&mut self, now_ms: i64) {
        self.trigger_timestamps.push_back(now_ms);
        self.last_trigger_ms = now_ms;
        let cutoff = now_ms - 86400000;
        while self.trigger_timestamps.front().map_or(false, |&ts| ts < cutoff) {
            self.trigger_timestamps.pop_front();
        }
    }
}
```

#### INSERT path

```rust
// mod.rs in daemon loop, after evaluate()
let should_insert =
    new_state.status != prev_status                          // transition: always
    || (now_ms - counters.last_insert_ms) >= 60_000;         // cycle: 1/min

if should_insert && pool.is_some() {
    let pool = pool.clone().unwrap();
    let row = build_log_row(&new_state, prev_status, now_ms, engine_mode);
    tokio::spawn(async move {
        let res = sqlx::query(
            "INSERT INTO learning.cost_edge_advisor_log \
             (ts_ms, engine_mode, status, ratio, threshold, data_days, \
              ai_spend_7d_usd, paper_pnl_7d_usd, is_stale, phase, transition_from) \
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)"
        )
        .bind(row.ts_ms).bind(&row.engine_mode).bind(&row.status)
        .bind(row.ratio).bind(row.threshold).bind(row.data_days)
        .bind(row.ai_spend_7d_usd).bind(row.paper_pnl_7d_usd)
        .bind(row.is_stale).bind(&row.phase).bind(row.transition_from.as_deref())
        .execute(&pool).await;
        if let Err(e) = res {
            warn!(error=%e, "cost_edge_advisor_log INSERT failed");
        }
    });
    counters.last_insert_ms = now_ms;
}
```

#### Healthcheck Inv 3 + Inv 4

見 RFC §4.1 完整 Python 程式碼。

### Acceptance criteria

#### Rust
- [ ] cargo test --lib **+3-5 tests / 0 failed**（baseline 2290 → 2293-2295）
- [ ] cargo test --lib cost_edge_advisor 整合測試 ≥3 通過（包括 prerequisite daemon-integration-test
      + Phase B 新增 cycle_row_down_sample / transition_immediate / counter_window）
- [ ] CostEdgeAdvisorState +4 fields serde forward-compat（既有 Phase A consumer 0 panic）

#### SQL
- [ ] V026 套兩次 idempotent（Guard A + Guard B no-op；CREATE TABLE/INDEX/hypertable IF NOT EXISTS）
- [ ] `learning.cost_edge_advisor_log` is_hypertable=true + retention_policy=30d
- [ ] sql/migrations/tests/ 加 1 檔 `test_v026_guards.sql`（3 case：empty pass / legacy missing
      column FAIL / legacy correct shape no-op）

#### Python
- [ ] healthcheck [30] 升級版 4 案例 smoke 全綠：
      (a) env=0 → PASS-skip
      (b) env=1 + DB 0 row + window <1h → PASS（warm-up tolerant）
      (c) env=1 + DB 50 row/h + 5 trigger/h → PASS
      (d) env=1 + DB 50 row/h + 25 trigger/h → WARN spam
- [ ] observation report tooling 跑 demo DB 7d range → 輸出 markdown 結構符 RFC §5.2

#### Cross-env
- [ ] paper/demo/live engine_mode 皆能正確 INSERT（engine_mode='live_demo' 在 LiveDemo 環境）
- [ ] 三環境 healthcheck [30] 升級版 cron 6h 連續 24h PASS

#### Observation period（Operator 啟動後追蹤，非 E1 直接交付）
- [ ] env=1 + RiskConfig.cost_edge.enabled=true 連續運行 ≥48h Linux Tier 1 早期信號
- [ ] 連續 ≥7d 完整 acceptance window 後 PA 寫 deliverable report
- [ ] healthcheck [30] 28 個 cron 樣本內無 FAIL
- [ ] daemon 0 panic + 0 INSERT 失敗 spam（warn log <10 條）

### 工時

- E1 (Rust + SQL + Python)：1.0d
- E1 (integration test prerequisite + observation report tooling)：0.5d
- E2 review：0.25d
- E4 regression Linux + 4 案例 healthcheck smoke：0.25d
- **全鏈 wall-clock：1.5d**（與 RFC §7.2 原估算一致）

### Rollback

- env=0 unset → daemon dormant，Phase A behavior 復原
- RiskConfig.cost_edge.enabled=false → IPC patch_risk_config 60s 內生效，daemon 短路 evaluate
- DROP `learning.cost_edge_advisor_log` 不影響交易路徑（observability only）

### 高風險項（per RFC §6.1）

1. ★★★ **R-B4 prerequisite**：Phase B 開工前必補完 `G3-09-PHASE-A-DAEMON-INTEGRATION-TEST`
   （E1 任務 #4 第 1 個 test 即為此 prerequisite）— 否則 Phase B observation 無 ground truth
2. ★★ **R-B1 INSERT volume**：1/min down-sample + tokio::spawn fire-and-forget；E2 必查
   daemon loop 不 await INSERT future
3. ★★ **R-B2 dead gate**：threshold = -0.5 在真實 demo 分佈下可能永不觸發；deliverable §6
   必算 ratio 5th percentile，Phase C 啟動前 PM 必審

### Files changed (預計 8 files)

新建：
- `rust/openclaw_engine/tests/cost_edge_advisor_integration.rs`
- `sql/migrations/V026__cost_edge_advisor_log.sql`
- `sql/migrations/tests/test_v026_guards.sql`
- `helper_scripts/research/cost_edge_advisor_observation_report.py`
- `docs/CCAgentWorkSpace/E1/workspace/reports/YYYY-MM-DD--g3_09_phase_b_observability.md`

修改：
- `rust/openclaw_engine/src/cost_edge_advisor/mod.rs`
- `rust/openclaw_engine/src/cost_edge_advisor/types.rs`
- `rust/openclaw_engine/src/ipc_server/handlers/cost_edge_advisor.rs`
- `helper_scripts/db/passive_wait_healthcheck/checks_derived.py`
````

---

## §12 派發策略

### 12.1 Wave 順序（不可並行）

```
Wave 0 (prerequisite): E1 補 G3-09-PHASE-A-DAEMON-INTEGRATION-TEST
                       → cargo test 1 個 integration test 綠 (~2h)
Wave 1: E1 落 Rust 改動 (mod.rs + types.rs + handler) + V026 SQL + healthcheck 升級
        → cargo lib 2293-2295/0 + V026 idempotent + healthcheck 4 smoke
Wave 2: E2 adversarial review
Wave 3: E4 regression Linux + 啟用 env=1 + 觀察 daemon spawn log
Wave 4: PM Sign-off → operator 開觀察期
Wave 5 (passive): ≥48h Linux Tier 1 早期信號 + healthcheck cron 6h 跑無 FAIL
Wave 6 (passive): ≥7d 完整 acceptance + PA 寫 deliverable report
Wave 7 (PM decision): GO/NO-GO Phase C
```

### 12.2 並行不可行原因

- Wave 0 是 prerequisite — Phase B observation 沒 daemon 整合測試 = 無 ground truth
- Wave 1 改動互相依賴（types.rs +欄→handler 必跟著序列化→healthcheck 才有 schema 可查）
- Wave 5+6 是 passive observation，自然 wall-clock 不可加速

### 12.3 E2 必查 3 點

1. **daemon INSERT 不阻 evaluate cycle**：`tokio::spawn(async move {...})` 包 INSERT future，daemon 主迴圈下次 `tokio::time::sleep(10s).await` 不等 DB
2. **down-sample boundary 1/min 嚴格**：`(now_ms - last_insert_ms) >= 60_000` + transition 不 down-sample（必須在 transition 路徑無條件 INSERT）
3. **Counter rolling 24h 沒 leak**：`VecDeque::pop_front` while front < cutoff，每 cycle pop 直到 empty 或 ts >= cutoff（不要只 pop 1 次）

---

## §13 結語

Phase B = 「Phase A 已就位的 advisor 基礎上加 observability，產出 Phase C 啟動所需的證據」。範圍嚴格控在 advisor 自身觀察（不接 IntentProcessor），符合 1.5d 工時與 0 trade impact 設計。

**重定義 vs RFC §7.2 原計畫**：本 RFC 把 RFC §7.2 line 511 提到的「IntentProcessor 入口加 would_reject_intent shadow check」整塊移到 Phase C，原因 = 即使是 pure fn 也改變 hot path 形狀且必須 cost_gate 並排做 audit，這違反 Phase B「0 trade impact」原則。Phase B 退回純 advisor observability 後 1.5d 工時與工作量匹配。

**Phase A FUP 升級為 Phase B prerequisite**：`G3-09-PHASE-A-DAEMON-INTEGRATION-TEST` 從 P3 升 P1，必須在 Phase B 開工前綠，否則 Phase B observation period 無 ground truth 驗證 daemon 行為真實。

**Phase B → C 銜接**：Phase B deliverable §6 提供 GO/NO-GO 證據（threshold calibration、trigger frequency 健康範圍、per-status distribution），PM 審後決定 Phase C 啟動。Phase C 範圍預計 +2.5d wall-clock（per RFC §7.3）。

**全文完。next: PM 派 Wave 0 prerequisite (FUP daemon integration test) → Wave 1 派發 §11 prompt template 給 E1 → 觀察期 ≥48h Tier 1 → ≥7d Tier 2 → deliverable → Phase C GO/NO-GO 決策**
