# FA Audit Report — P2-EDGE-EST-SNAPSHOTS-STALE-FOLLOWUP

**日期**：2026-05-21
**Owner**：FA
**Trigger**：FA G2 audit §1.4 衍生 + PA D3 §A verify item 2
**Status**：✅ AUDIT DONE — verdict LOW now / MEDIUM future-risk；推薦 Path A（cron install operator action）

## §1 PG Empirical 引用

| Source | Evidence |
|---|---|
| PA D3 §A verify item 2（2026-05-21 12:08 UTC ssh empirical）| `learning.edge_estimate_snapshots`: 7d=0 / 14d=n/a / max_ts=2026-05-07 |
| MIT 2026-05-09 db_ml_verification_v3 §3.2 | `F-edge-cycle (V073) cron 未 install` |
| MIT memory line 112 | V059 = Foundation only (457 row 一次性 ref21_backfill；無 cycle writer) |
| PM cron reconcile 2026-05-16 §3.2 | `edge_estimate_snapshots_cycle_cron.sh` ❌ NOT INSTALLED |

**綜合事實**：457 rows 一次性 burst 來自 2026-05-07 00:46 UTC ref21 backfill；14d 無新 row；root cause = cron **從未 install**（非 writer 崩潰）。

## §2 Writer 位置 + 預期頻率

| 元件 | 位置 | 預期頻率 | 實際狀態 |
|---|---|---|---|
| Schema | `srv/sql/migrations/V059__edge_estimate_snapshots.sql` (L16-37) | one-shot DDL | ✅ deployed |
| Writer 核心 | `srv/helper_scripts/db/ref21_backfill_v058_v059.py` (L357-382 `insert_edge_snapshots`) | one-shot | ✅ source land |
| Cron wrapper | `srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh` (76 LOC) | `12 * * * *` per header L5 | ❌ **NOT INSTALLED** |
| 輸入源 | `settings/edge_estimates*.json`（4 mode）| 每小時 daemon 刷新 | ✅ daemon active |
| 上游 daemon | `program_code/.../edge_estimator_scheduler.py:209-226` | 每 3600s | ✅ active |

**Root cause 鎖定**：deploy chain 缺最後一步 — operator approve cron `crontab -e` 添加 wrapper line。

## §3 Downstream Consumer 鏈

### 任務 prompt 假設修正

任務 prompt §3 列「`[40] realized_edge_acceptance`」「cost_gate advisor」「cost_edge_advisor_log writer」為 consumer — **錯誤推斷**。Grep verify：

| Consumer | 依賴 V059？ | 證據 |
|---|---|---|
| `[40] realized_edge_acceptance` | ❌ 不依賴 | `helper_scripts/db/passive_wait_healthcheck/checks_execution.py:1133-1207` 讀 `learning.mlde_edge_training_rows`，無 V059 reference |
| `cost_gate` runtime | ❌ 不依賴 | Rust engine 讀 `settings/edge_estimates.json` 檔案；`rg edge_estimate_snapshots /Users/ncyu/Projects/TradeBot/srv/rust` = 0 命中 |
| `cost_edge_advisor_log` writer | ❌ 不依賴 | `learning_engine/cost_edge_advisor.py` 寫 `learning.cost_edge_advisor_log`；不讀 V059 |
| Strategist agent edge calibration | ❌ 不依賴 | 讀 `learning.james_stein_estimates` + edge_estimates.json |

### 實際 consumer 鏈

| Consumer | 位置 | Stale 衝擊 |
|---|---|---|
| **REF-21 Replay Engine** | `program_code/.../replay_full_chain_routes.py:1061-1146`（`_fetch_edge_estimate_snapshot_sync`）| **MEDIUM** — replay window 2026-05-08+ 跑 = 用 5/7 stale snapshot；返回 status=ok 但 stale data |
| **V061 SQL function** | `sql/migrations/V061__replay_promotion_metrics_calculator.sql:543` | **DORMANT** — 0 production caller；W-AUDIT-8a Phase B/C/D 啟用後 wired |
| Rust hot path | n/a | ✅ **0 衝擊**（0 reference） |
| Live trading decision | n/a | ✅ **0 衝擊** |
| `[40]` / `cost_gate` / `cost_edge_advisor` | n/a | ✅ **0 衝擊** |

## §4 衝擊評級

**LOW now / MEDIUM future-risk**

### LOW 證據

1. Trading 熱路徑 0 影響
2. 學習熱路徑 0 影響（james_stein_estimates + edge_estimates.json 是權威）
3. Healthcheck 0 影響（`[40]` 讀 mlde_edge_training_rows）
4. Phase 2a verdict / P0-EDGE-1 / true-live blocker 0 影響
5. 唯一 active consumer = REF-21 replay 離線分析（非 trading decision）
6. V061 promotion function = dormant 0 caller

### Future MEDIUM 升級 trigger

- **W-AUDIT-8a Phase B/C/D 啟用時**：V061 wired；若 V059 仍 stale → `predicted_edge_bps` 計算用 5/7 舊 cells → 阻塞 promotion
- **REF-21 replay window 2026-05-08+ 跑**：edge calibration 偏離

## §5 Fix 路徑（A/B/C/D cost-benefit）

### Path A — Install cron + optional one-shot backfill（✅ FA 推薦）

**動作**：operator approve `crontab -e` 添加：
```
12 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_SECRETS_ROOT=$HOME/BybitOpenClaw/secrets $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh >> /tmp/openclaw/logs/edge_estimate_snapshots_cycle.log 2>&1
```

**Cost**：~5 min operator action
**Benefit**：立即恢復 hourly snapshot；修 future MEDIUM risk
**Risk**：PG INSERT 每小時 ~50-200 rows × 24 = ~1.2k-4.8k/day；75d retention → 60d 後 ~100k rows 規模可控；與既有 cron schedule 無衝突 ✅

### Path B — Schema fix（❌ Reject）

無實質收益；當前 schema 已支持 hourly insert；瓶頸是 cron 沒跑。

### Path C — Deprecate V059 + V061（❌ Reject）

違反 REF-21 設計意圖（「promotion 必須讀歷史快照」）；W-AUDIT-8a Phase B/C/D 設計依賴 V059 immutable history。

### Path D — Defer（⚠️ Acceptable fallback）

若 operator 不批 cron install，須加 healthcheck `edge_estimate_snapshots_freshness` (max_asof_ts > NOW() - 2h) + 90d review date 滿足 CLAUDE.md passive-wait 規則。

## §6 Priority 判定：維持 P2

**證據**：衝擊評級 LOW；0 active blocker；不阻塞 LG-3 / P0-FUNDING-ARB / Phase 2a / true-live。

**Trigger condition**：
- W-AUDIT-8a Phase B/C/D dispatch 前必須 closure（否則 V061 wired 時暴露）
- 14d 後若 cron 仍 not installed 由 PA / FA 升 P1
- REF-21 replay 2026-05-08+ window 跑出明顯偏差 → 升 P1

## §7 5 條 Follow-up OQ

| # | OQ |
|---|----|
| OQ-1 | PM cron reconcile 2026-05-16 §六 5 條 P1 cron install batch — `edge_estimate_snapshots_cycle_cron.sh` 是否加入 P1 batch 一起批准？ |
| OQ-2 | 若 defer Path A，是否新增 healthcheck slot `[NN] edge_estimate_snapshots_freshness`（CLAUDE.md passive-wait 規則）？ |
| OQ-3 | PA D3 §D 列 `[48] replay_manifest_registry_growth 7d=0 → replay_runner stalled`。replay_runner stall 與 V059 stale 是否同源 governance debt？ |
| OQ-4 | W-AUDIT-8a Phase B/C/D 預計何時 wire V061？此日期 = V059 stale 硬 deadline |
| OQ-5 | 是否該定義「新 cron wrapper land 必跟 cron install evidence」SOP，避免類似漏接？（11 wrapper 中 8 NOT INSTALLED）|

## FA 三句話結論

1. **Stale 衝擊評級 = LOW now / MEDIUM future-risk**：Trading 熱路徑 / `[40]` / cost_gate / Decision Lease / true-live blocker 全 0 影響；任務 prompt 列的 consumer 是錯誤推斷（grep verify 0 V059 reference）；唯一 active = REF-21 replay；V061 dormant 0 caller。
2. **推薦 fix = Path A（install cron）**：5 min operator action；對齊 cron header design intent；Path B/C reject；Path D fallback 須加 freshness healthcheck + 90d review。
3. **是否需 source fix = NO**：V059 schema / V073 contract guard / cron wrapper source 均 ✅；root cause = **deploy chain 漏 cron install 最後一步**；governance debt 屬 ops 層；維持 P2 但綁 W-AUDIT-8a Phase B/C/D 為硬 deadline。

## 報告交付規範注

FA 因 system override 未自行寫此 .md report；本檔由 PM 主會話從 sub-agent 對話成果落檔（內容 1:1 自 FA findings）。
