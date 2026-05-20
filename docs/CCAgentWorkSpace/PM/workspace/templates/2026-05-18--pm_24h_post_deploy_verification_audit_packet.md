# PM 24h Post-Deploy Verification Audit Packet

**Date**: 2026-05-{{DAY}}（dispatch 時間）
**Trigger**: 24h after Phase 1b RUNTIME ACTIVATOR fix deploy + restart
**Scope**: 全鏈 post-deploy verification — Phase 1b runtime / W-AUDIT-8c liquidation revival / W-AUDIT-8b panel / 3-Gate / fix plan v1.x update
**Author**: Main session PM + Conductor
**Status**: TEMPLATE — pending operator dispatch authorization

> **Fill-in markers**: `{{...}}` 在 dispatch 前必填或留 placeholder by agent。

---

## §1 Dispatch Conditions

**Prerequisites all met before dispatch**:
- [ ] Phase 1b RUNTIME ACTIVATOR feature branch (`feature/phase-1b-runtime-activator`) E2 review APPROVED + E4 regression PASS + QA deploy readiness GREEN
- [ ] Operator authorized `restart_all.sh --rebuild` on Linux
- [ ] Engine pid changes confirmed (post-restart timestamp `{{RESTART_TS}}`)
- [ ] 24h elapsed since restart
- [ ] AMD v0.5 land (`23e6b6b2`)

---

## §2 Agent Owner

**Recommended**: **QA** agent (full-system end-to-end integration acceptance role per CLAUDE.md §八)

**Alternative**: PM main session does it directly (no sub-agent dispatch) if QA agent unavailable.

---

## §3 Audit Scope — 8 sections

### §3.1 Phase 1b Runtime Activator Verification

Verify `use_maker_close` is actually ON in Demo runtime post-deploy.

**設計理由 — 為什麼用 attempt × fallback matrix 拆而不是 ID prefix**：

過去（≤ 2026-05-19 v55）的 QA 模板用 `order_id LIKE 'oc_%' AND NOT LIKE 'oc_risk_%'` 區分 entry-close vs risk-exit 兩條 path。QC v55 critical reframe 指出**這個拆法是結構性人為誤分類**：

- entry-close 與 risk-exit 兩者都走同一條 `execute_position_close()`；差別只在「誰觸發 close」（strategy whitelist exit vs risk module stop）
- 一次 attempt 內若 maker limit 超時 fallback 成 market exit（或 PostOnly reject 後重試 / cancel 失敗轉 risk-exit），同筆訂單會先有 `oc_close_mf_fb_*` 又會在 fallback 後出 `oc_risk_*`，**ID prefix 拆法會把同一個 attempt 的 maker 階段 + fallback 階段算成「entry path 0% maker fill / risk path 100% maker fill」這種誤導性結論**
- 真實的分析軸是「**這次 attempt 走了什麼 fallback**」，不是「order_id 開頭是什麼」

因此本 template 改採 **attempt（主路徑）× fallback（後備路徑）matrix**：

- **attempt 軸（主路徑）**：策略試圖用什麼方式平倉 — `maker_close_attempt`（PostOnly limit @ BBO ± offset）vs `sweep_taker`（直接 IOC market，不嘗試 maker；負面 whitelist 如 `halt_session` 走這條）
- **fallback 軸（後備路徑）**：attempt 命運落點 — `maker_filled`（成功，liquidity_role='maker'） / `timeout_taker`（限時 fallback 成 taker） / `postonly_reject_retry`（PostOnly 被拒，retry 一次後成或最終 taker） / `cancel_grace_expired`（cancel 失敗後強制 taker） / `risk_exit_takeover`（attempt 內 risk module 強制轉 stop）

**Schema 提醒**：`close_maker_attempt` boolean + `close_maker_fallback_reason` enum（V094）已支援 attempt × fallback 兩軸切。`close_maker_fallback_reason IS NULL` 即「maker filled 成功」（沒走 fallback）；非 NULL 必為合法 enum 值。不再用 `order_id LIKE` 為拆法軸。

```sql
-- AC-1（attempt 軸）：策略 close 主路徑分布 — maker_close_attempt vs sweep_taker
-- 預期：whitelist closes 上 attempt_pct ≥25%（≥ spec §4.3 保守 floor）；negative whitelist 0%
SELECT engine_mode,
       CASE WHEN exit_reason IN ('grid_close_short','grid_close_long','bb_mean_revert',
                                  'ma_reverse_cross','bw_squeeze','pctb_revert')
            THEN 'whitelist_close'
            WHEN exit_reason LIKE 'risk_close:%' OR exit_reason = 'halt_session'
            THEN 'negative_close'
            ELSE 'other' END AS attempt_class,
       COUNT(*) FILTER (WHERE close_maker_attempt = TRUE) AS maker_close_attempt,
       COUNT(*) FILTER (WHERE close_maker_attempt = FALSE) AS sweep_taker,
       COUNT(*) AS total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE close_maker_attempt = TRUE)
             / NULLIF(COUNT(*), 0), 2) AS attempt_pct
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '24 hours'
   AND engine_mode IN ('demo','live_demo')
 GROUP BY engine_mode, attempt_class
 ORDER BY engine_mode, attempt_class;

-- AC-2（fallback 軸）：attempt=TRUE 的命運分布 — maker_filled vs 4 種 fallback
-- 預期：fallback_reason 在 attempt=TRUE 上非 NULL ≥ 90%（NULL 即 maker_filled，剩餘為合法 enum）
SELECT engine_mode,
       COALESCE(close_maker_fallback_reason, 'maker_filled') AS fallback_class,
       COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) OVER (PARTITION BY engine_mode)
             / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY engine_mode), 0), 2) AS pct
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '24 hours'
   AND engine_mode IN ('demo','live_demo')
   AND close_maker_attempt = TRUE
 GROUP BY engine_mode, fallback_class
 ORDER BY engine_mode, n DESC;

-- AC-3（attempt × fallback 二維 matrix）：策略級拆分 — 全 attempt 命運 × 後備
-- 預期：whitelist_close × maker_filled 列存在實際 row 數；
--      negative_close × maker_close_attempt = 0（負面 whitelist 不該走 maker path）
SELECT engine_mode,
       CASE WHEN exit_reason IN ('grid_close_short','grid_close_long','bb_mean_revert',
                                  'ma_reverse_cross','bw_squeeze','pctb_revert')
            THEN 'whitelist_close'
            WHEN exit_reason LIKE 'risk_close:%' OR exit_reason = 'halt_session'
            THEN 'negative_close'
            ELSE 'other' END AS attempt_class,
       CASE WHEN close_maker_attempt = FALSE THEN 'sweep_taker'
            WHEN close_maker_fallback_reason IS NULL THEN 'maker_filled'
            ELSE close_maker_fallback_reason END AS fallback_class,
       COUNT(*) AS n
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '24 hours'
   AND engine_mode IN ('demo','live_demo')
 GROUP BY engine_mode, attempt_class, fallback_class
 ORDER BY engine_mode, attempt_class, n DESC;
```

**Acceptance**:
- AC-1 attempt_pct ≥ 25% on demo+live_demo `whitelist_close` rows；`negative_close` rows attempt_pct = 0% (per AC-3 cross-check)
- AC-2 fallback_reason non-NULL coverage ≥ 90% on attempt=TRUE rows；maker_filled 列必出現（非全 fallback）
- AC-3 二維 matrix 必有 `whitelist_close × maker_filled` 非零；`negative_close × maker_close_attempt`/`maker_filled`/任何 fallback 行 = 0

#### §3.1.1 Example — grid family（grid_close_short / grid_close_long）

策略族 `grid_trading` 平倉走 whitelist；典型 attempt × fallback matrix（24h demo，n 為實際 fill 數）：

| attempt | fallback | n | 說明 |
|---|---|---:|---|
| `maker_close_attempt` | `maker_filled` | k1 | PostOnly limit @ BBO ± offset 在 timeout 內成交，liquidity_role='maker'，fee_rate=0.0002（理想路徑）|
| `maker_close_attempt` | `timeout_taker` | k2 | timeout（90s 校準後）內 maker 未成，fallback IOC market；同筆 attempt 內 BBO 漂走 = 微結構主因 |
| `maker_close_attempt` | `postonly_reject_retry` | k3 | maker price 跨價成 taker → PostOnly Bybit 拒；engine retry 後最終為 taker 或 maker 二嘗試成 |
| `maker_close_attempt` | `cancel_grace_expired` | k4 | timeout 後 cancel 失敗超 grace；本筆強制走 taker 結束 |
| `maker_close_attempt` | `risk_exit_takeover` | k5 | maker attempt 進行中 risk module 介入（例：halt_session）；同筆 attempt 由 risk path 接手結束 |
| `sweep_taker` | (N/A) | k6 | `use_maker_close=false`（live/paper 預設）或 attempt cooldown；直接 IOC，fee_rate=0.00055 |

**注意**：上表每一行都是「**同一筆 attempt** 在不同 fallback 命運下的計數」，不是「ID prefix 出現兩種 order_id 就算兩筆」。同一筆 attempt 若先 maker→fallback→taker fill，**只算一行**（attempt=`maker_close_attempt`, fallback=`timeout_taker`/`cancel_grace_expired`/`postonly_reject_retry`/`risk_exit_takeover` 取最終命運）。

#### §3.1.2 Example — bb_breakout family（bw_squeeze / pctb_revert）

策略族 `bb_breakout` close 走 `bw_squeeze` / `pctb_revert` whitelist；典型 matrix（24h demo）：

| attempt | fallback | n | 說明 |
|---|---|---:|---|
| `maker_close_attempt` | `maker_filled` | k1 | breakout reversion 觸發時 spread 通常較寬 → maker fill 機率高於 grid（empirical 觀察待 sample 累積驗）|
| `maker_close_attempt` | `timeout_taker` | k2 | breakout 後 BBO 動能快，maker 漂走概率高；典型 timeout fallback 比例 |
| `maker_close_attempt` | `postonly_reject_retry` | k3 | breakout 高 vol bar 內 BBO 跨價，PostOnly 拒概率上升 |
| `maker_close_attempt` | `cancel_grace_expired` | k4 | 罕見，rate_limit 緊張時才出現 |
| `maker_close_attempt` | `risk_exit_takeover` | k5 | bb_breakout 收益 / 風險不對稱，risk_close:halt_session 觸發比 grid 高 |
| `sweep_taker` | (N/A) | k6 | 同 §3.1.1 — `use_maker_close=false` 或 cooldown 路徑 |

**對比觀察點**（grid vs bb_breakout）：兩族 `maker_filled / total_attempt` 比例可能差 ≥ 10pp，**屬不同微結構特性而非 IMPL bug**；報告需分別列、不可只報合併數。`negative_close`（如 `halt_session`）兩族都應落到 `sweep_taker` 列，attempt=TRUE 數 = 0。

#### §3.1.3 SOP — 為什麼禁止再用 ID prefix 拆法

從本 template 起，post-deploy verification SQL **禁止**用 `order_id LIKE 'oc_%' AND NOT LIKE 'oc_risk_%'` 作為 entry vs risk-exit 拆法軸：

1. **語意誤導**：ID prefix 反映「最終訂單由哪個 producer 開單」，不反映「策略想做什麼 attempt」。`oc_close_mf_fb_*` 是 maker close attempt 的 fallback 訂單，`oc_risk_*` 是 risk module 開的 stop 訂單；同一 attempt 在 fallback 後出現 `oc_risk_*` 並**不**等於「策略改用 risk-exit 平倉」
2. **歷史教訓**：QA memory.md 2026-05-11 W-C lesson §1.2「entry vs risk_exit 分流必要」原意是 spine lineage 對接（emit_fill_completion_lineage 不覆 StopManager path），**不**是 close attempt 分類軸；v55 之前的 QA report 把它套到 close maker 分析上是誤用
3. **正確 spine lineage SQL**：若驗證的是 `agent.decision_state_changes` lineage propagation（W-C Caveat 2 場景），那是「fill 必有對應 ExecutionReport」的 join 驗證；可繼續用 `order_id LIKE` 區分 spine-covered fill（`oc_*` AND NOT `oc_risk_*`）vs StopManager path（`oc_risk_*`），但**僅限該語境**。post-deploy maker close 分析改用本 §3.1 attempt × fallback matrix

如未來新增 close path（例：iceberg / TWAP），擴 attempt enum 與本 §3.1 SQL 三段；不要再加新 ID prefix 拆法。

### §3.2 Healthcheck [62][63][64][65] Pass

Run per Phase 1b spec §11 + AMD v0.5 §3 Rollout Posture:

```bash
ssh trade-core "python3 helper_scripts/canary/healthchecks/{62,63,64,65}.py --report"
```

**Acceptance**: all 4 healthchecks PASS with Wilson 95% CI lower bound ≥ threshold

### §3.3 W-AUDIT-8c Liquidation Revival 24h Health

```sql
-- 24h liquidation rows growth + WS uptime + side mapping
SELECT COUNT(*) AS rows_24h, MAX(ts) AS latest_ts, NOW() - MAX(ts) AS latest_age,
       COUNT(*) FILTER (WHERE side = 'Buy') AS buy_long_liquidation,
       COUNT(*) FILTER (WHERE side = 'Sell') AS sell_short_liquidation
  FROM market.liquidations
 WHERE ts > NOW() - INTERVAL '24 hours';

-- C1 v2 probe artifact freshness
ls -la /tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.{md,json}
```

**Acceptance**:
- rows_24h ≥ 100 (per BB rate expectation)
- latest_age < 30min (WS stable)
- side mapping: Buy=long liquidation / Sell=short liquidation correct (per BB approved 2026-05-17)
- C1 probe artifact within last 24h freshness

### §3.4 W-AUDIT-8b Panel Days + Round 2 Status

```sql
SELECT EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000.0)
                          -to_timestamp(MIN(snapshot_ts_ms)/1000.0)))/86400 AS days
  FROM panel.funding_rates_panel;
```

**Acceptance**:
- panel ≥7.0d ✅
- Round 2 4-agent review verdict consensus available (`{{4AGENT_VERDICT_PATH}}`)

### §3.5 Engine Watchdog + IPC Liveness

```bash
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --status"
```

**Acceptance**:
- demo + live engine alive
- snapshot age < 45s
- paper engine = expected dead (per `project_paper_pipeline_disabled_by_default`)

### §3.6 3-Gate Status Update

| Gate | Pre-fix | Post-fix Expected | Verified? |
|---|---|---|---|
| P0-EDGE-1 [40] negative edge | ❌ ACTIVE | Still ACTIVE (alpha 結構性) | {{P0_EDGE_1_STATUS}} |
| W-AUDIT-8b Stage 0R | 🟡 Round 2 preliminary RED | RED_FINAL post-4-agent review | {{W_AUDIT_8B_STATUS}} |
| W-AUDIT-8a C1 sign-off | ✅ technical PASS + revival LANDED | Stable 24h+ | {{W_AUDIT_8A_C1_STATUS}} |

### §3.7 Fix Plan v1.x Patch

Update `docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md`:
- §9.1 Phase 1b RUNTIME ACTIVATOR — mark RESOLVED + post-fix measured `attempt_pct`
- §9.2 W-AUDIT-8b Round 2 — RED_FINAL verdict + AMD §8 wording revision link
- §9.4 Tier 2 Roadmap — update Phase 2a observation reset trigger timestamp
- §8 Changelog — add v1.2 row

### §3.8 Operator Follow-up Checklist

| Action | Priority | Owner |
|---|---|---|
| Confirm Phase 2a 14d observation clock starts at `{{RESTART_TS}} + 2h verification`（不是 restart 本身）| P0 | Operator |
| Schedule Phase 2a → 2b transition (≈ 14d later) | P1 | Operator |
| Restart B-REM-1 + C1-LIQ-WRITER single-agent IMPL dispatch | P1 | PM main |
| Restart PA Phase 2c LiveDemo Counterfactual harness spec finalize | P1 | PM main |
| W-AUDIT-8a Wave 1 dispatch packet preparation | P1 | PM main |
| phys_lock Live AMD v0.2 operator self-review | P2 | Operator |

---

## §4 Output Schema

QA report written to `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-{{DAY}}--phase_1b_24h_post_deploy_verification.md`:

1. §1 Executive Summary（1 sentence each section PASS/RETURN/RED_FLAG）
2. §2 AC-1/2/3 raw data + verdict
3. §3 Healthcheck [62][63][64][65] full output
4. §4 W-AUDIT-8c 24h growth + Side mapping verify
5. §5 W-AUDIT-8b panel days + Round 2 verdict
6. §6 Engine watchdog snapshot
7. §7 3-Gate status table
8. §8 Fix plan v1.x patch diff
9. §9 Operator follow-up checklist
10. §10 QA sign-off + recommendation: PASS to Phase 2a → 2b transition, or RETURN to fix-plan loop

---

## §5 Boundaries

- **Read-only verification + reporting** — 不動 production config / runtime
- 不 enable any new feature / strategy launch
- 不 mutate `risk_config_live.toml`
- 不 enable any paper pipeline
- 不 dispatch downstream agents (operator does)

---

## §6 Estimated Time

**Total ETA**: 1-2 hours QA execution + 30min PM consolidation = ~2-3 hours from dispatch trigger to operator-actionable verdict.

---

**Template END**. Dispatch trigger: operator authorization post-{{RESTART_TS}} + 24h.
