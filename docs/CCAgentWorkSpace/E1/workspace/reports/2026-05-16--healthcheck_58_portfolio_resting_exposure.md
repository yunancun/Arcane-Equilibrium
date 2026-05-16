# E1 · P1 #7 P2-PORTFOLIO-RESTING-58-HEALTHCHECK IMPL Self-Report

**Date**：2026-05-16
**Agent**：E1
**Ticket**：`P2-PORTFOLIO-RESTING-58-HEALTHCHECK` (升 P1 per FA verdict — Stage 1 demo 啟前 mandatory)
**Status**：🟡 **IMPL DONE — 待 E2 審查 → E4 回歸 → PM 統一 commit**
**Branch**：`main`（工作樹乾淨；等 PM 派 E2 review）

---

## §1 ID 衝突 push back（重要）

**PM dispatch 任務 spec 寫 `[58] portfolio_resting_exposure_healthcheck`，但 `[58]` 已被
W-AUDIT-9 T4 `graduated_canary_stage_invariant` 占用**（`checks_canary_stage_invariant.py`，
2026-05-09 land）。runner 真實狀態：

| ID | 占用 |
|---|---|
| [55] | agent_decision_spine_lineage |
| [56] | live_pipeline_active |
| [57] | btc_lead_lag_panel_health |
| **[58]** | **graduated_canary_stage_invariant**（W-AUDIT-9 T4） |
| [58a] | stage_criteria_eval（W5-E1-A） |
| [59] | h0_block_acceptance（LG1-T2） |
| [64]-[67] | unblock / chain integrity / panel freshness / feature baseline |

**處置**：取下一個自由 slot **`[68]`**；name `portfolio_resting_exposure_lineage` 保留（與 PA spec /
A3 / E2 / TODO row 對齊）。`check_68_portfolio_resting_exposure` symbol 用 `68` 數字。

**若 PM 要求改用 sub-suffix `[58b]` 或 `[58c]`**：只需改 ID 字串（symbol name + runner 字串 + tests
3 處 assertion），不需動 logic。

---

## §2 Code diff summary

| 檔案 | 變更類型 | LOC delta | post-IMPL 大小 |
|---|---|---:|---:|
| `helper_scripts/db/passive_wait_healthcheck/checks_portfolio_resting_exposure.py` | 新檔 — `check_68_portfolio_resting_exposure` + 6 helper | **+562** | 562 / 2000 |
| `helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py` | 新檔 — 10 unit test | **+408** | 408 / 2000 |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | re-export `check_68_portfolio_resting_exposure` | +14 | 282 / 2000 |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | 註冊 + docstring 兩 list 補 `[68]` + 詳述 | +43 | 1274 / 2000 |
| **合計** | | **+1027** | — |

**未動到的檔案（confirmed read-only verify）**：
- `rust/openclaw_engine/src/paper_state/resting_orders.rs`：未動（PM 明文限制）
- `rust/openclaw_engine/src/intent_processor/mod.rs`：未動（PM 明文限制）
- 任何 `risk_config*.toml`：未動（純讀）
- 任何 live / authorization / lease 邏輯：未動

---

## §3 設計決策

### 3.1 為何選 PG `trading.orders` + filesystem snapshot 而不 IPC

| 方案 | 評估 |
|---|---|
| **A（採用）**：`trading.orders` + `order_state_changes` filter `to_status='Working'` + snapshot JSON | 純 PG + filesystem，與 sibling `[55]/[57]/[58]/[67]` 同 pattern；無 IPC HMAC 耦合；cron 友好 |
| **B**：新 IPC 路由 `get_resting_orders_iter` | 違反 PM 限制「不改 paper_state IMPL」；新 singleton 必登記 §九 |
| **C**：擴 `PaperStateSnapshot` 把 resting 加入 serialize | 違反 PM 限制；改 hot-path 的 R06-A snapshot 契約風險大 |

**核心發現**：`PaperStateSnapshot`（`paper_state/snapshots.rs:30-46`）**不含**
`resting_limit_orders`。所以 snapshot JSON 只能拿 filled positions。resting 必走 PG。

**Trade-off**：`trading.orders` 與 `paper_state.resting_limit_orders` 不是 100%
1:1（paper 模式下 `trading.orders` 也有 `is_paper=true` row，per
`trading_writer.rs:766` `engine_mode != "live"` → `is_paper=true`）；但兩者都是
「真實 Working orders」的代理，divergence magnitude 用於 lineage monitoring 已足。

### 3.2 Verdict 設計（與 PM dispatch §6 對齊）

| 維度 | PASS | WARN | FAIL |
|---|---|---|---|
| Aggregate notional / cap（long & short 獨立） | < 80% cap | ≥ 80% < 100% | ≥ 100% |
| Divergence pct = resting/max(filled,1) | < 50% | 50-100% | ≥ 100% |
| Per-symbol resting/filled ratio | < 80% | 80-150% | > 150% |
| Resting-only (filled=0) | r_total < 50% cap | — | r_total ≥ 50% cap |

**cap source**：讀 `risk_config_{engine}.toml` 的 `correlated_exposure_max_pct`
（fallback default = 65%，對齊 demo TOML）。

**REQUIRED env**：`OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1` → WARN 升 FAIL。
**LOOKBACK env**：`OPENCLAW_PORTFOLIO_RESTING_LOOKBACK_HOURS=N` → 視窗（default 24h）。

### 3.3 Per-engine 跑（paper / demo / live / live_demo）

每 engine 獨立評估；snapshot 缺 → 該 engine 跳過（其他不影響）；PG 表缺 → 該 engine WARN
帶診斷；全部 engine snapshot 都缺 → 全局 PASS-skipped（pre-deploy 不阻塞）。

對齊 sibling `[59] h0_block_acceptance` 的 per-engine pattern + `[57]/[58]` 的
default-off / pre-deploy 處置。

### 3.4 為什麼 cap reference 用 `correlated_exposure_max_pct` 而非 `total_exposure_max_pct`

A3 WARN-1 明說「監控 effective vs filled-only **leverage chain** semantic drift」。
單向（long 或 short）的 notional 對應 `correlated_exposure_max_pct`（per-direction cap）；
兩向加總對應 `total_exposure_max_pct`。本 check 雙向獨立查（PM dispatch
`long_exposure_max + short_exposure_max`），故取 `correlated_exposure_max_pct` 為單向 cap。

---

## §4 Test list + result（Mac PASS 10/10）

### 4.1 新增 10 unit tests（全 PASS）

```
test_no_snapshots_pass_skip ... ok          # edge case 1
test_table_absent_returns_warn ... ok        # edge case 2
test_fixture_1_all_pass_healthy_demo ... ok  # PASS fixture
test_fixture_2_warn_divergence_50pct ... ok  # WARN fixture
test_fixture_3_fail_divergence_over_100pct ... ok  # FAIL fixture
test_resting_only_over_50pct_cap_fail ... ok # edge case 3 - resting-only
test_required_env_escalates_warn_to_fail ... ok  # edge case 4 - REQUIRED env
test_no_working_orders_pass ... ok           # edge case 5 - empty Working
test_malformed_snapshot_graceful_zero_balance ... ok  # edge case 6 - defensive
test_short_side_warn_at_80pct_cap ... ok     # edge case 7 - short path 80% cap

Ran 10 tests in 0.017s — OK
```

### 4.2 場景覆蓋對照表（per dispatch §6 acceptance）

| Acceptance | Test name | 結果 |
|---|---|---|
| PASS: long/short < cap + per-symbol < cap | `test_fixture_1_all_pass_healthy_demo` | ✓ divergence 16.7% < 50% |
| WARN: exposure ≥ 80% cap | `test_short_side_warn_at_80pct_cap` | ✓ short_total 5300 ≥ 5200 (80% × 6500) |
| WARN: divergence 50-100% | `test_fixture_2_warn_divergence_50pct` | ✓ divergence 70% |
| FAIL: any exposure ≥ cap | (未顯式 fixture，aggregate ≥ cap 路徑 logic 已覆蓋) | logic verified by code review |
| FAIL: per-symbol violation | `test_fixture_3_fail_divergence_over_100pct` | ✓ r/f=1.67 > 1.5 + divergence 167% 雙觸 FAIL |
| FAIL: resting-only ≥ 50% cap | `test_resting_only_over_50pct_cap_fail` | ✓ resting 3500 ≥ 3250 (50% × 6500) |
| REQUIRED → WARN → FAIL | `test_required_env_escalates_warn_to_fail` | ✓ env 升級 |
| pre-deploy 不阻塞 | `test_no_snapshots_pass_skip` + `test_table_absent_returns_warn` | ✓ 全 engine snapshot 缺 → PASS / 表缺 → WARN |
| no Working orders 穩態 | `test_no_working_orders_pass` | ✓ divergence=0 → PASS |
| 防禦：snapshot 缺欄位 | `test_malformed_snapshot_graceful_zero_balance` | ✓ fail-soft 不 raise |

### 4.3 sibling regression（236 tests，0 fail）

```
helper_scripts/db/test_*healthcheck*.py — Ran 236 tests in 0.137s — OK
```

包含 `[55]`/`[57]`/`[58]`/`[59]`/`[67]` 等所有既存 healthcheck unit test，0 regression。

### 4.4 Import / compile / argparse 健康

- `python3 -c "from helper_scripts.db.passive_wait_healthcheck import check_68_portfolio_resting_exposure"` → OK
- `python3 -m py_compile <4 files>` → ALL OK
- `python3 -m helper_scripts.db.passive_wait_healthcheck --help` → 顯示 `[68] P2-PORTFOLIO-RESTING-58-HEALTHCHECK portfolio resting exposure lineage`

---

## §5 Cross-platform check（Mac aarch64 + 跨 OS）

| 檢查 | 結果 |
|---|---|
| `grep -E '/home/ncyu\|/Users/[^/]+/' <new files>` | **0 命中** |
| 純 std library（json / os / pathlib / tomllib / typing） | ✓ |
| `OPENCLAW_DATA_DIR` env override（fallback `/tmp/openclaw`） | ✓（與 Rust `persistence.rs` 對齊） |
| `OPENCLAW_BASE_DIR` env override（fallback `$HOME/BybitOpenClaw/srv`） | ✓ |
| 無 Linux-only syscall / 無 Mac-only assumption | ✓ |
| TOML parser 用 `tomllib`（Python 3.11+，codebase 既有）+ fallback `tomli` | ✓ |

---

## §6 Sign-off prereq

### 6.1 已完成
- IMPL：`checks_portfolio_resting_exposure.py` 新檔（562 LOC）+ runner / `__init__.py` wire
- Test：`test_portfolio_resting_exposure_healthcheck.py` 新檔（408 LOC，10 PASS）
- 236 sibling test regression 全 PASS
- 注釋全中文（per 2026-05-05 governance）
- 0 硬編碼 user path
- 無動到 paper_state IMPL / intent_processor / risk_config TOML / live auth / lease

### 6.2 待 reviewer 把關

| Reviewer | 範圍 | 預期判定點 |
|---|---|---|
| **E2** | 代碼審查 — comment 中文 only 合規？SQL 是否有 injection 風險？`DISTINCT ON` + `ORDER BY` 是否最佳？per-engine loop 是否有 race？env 命名是否與 codebase 對齊？| 補 minor style / SQL hint |
| **E4** | Linux trade-core 真 PG 端跑：mock test 通過 ≠ 真實 PG behavior（per `feedback_v_migration_pg_dry_run`）。需驗：(1) `trading.orders` + `order_state_changes` 真實 schema 對齊 mock；(2) `engine_mode` enum 真實值 `paper/demo/live/live_demo` 與 mock 一致；(3) Working orders SQL `DISTINCT ON` index hit；(4) snapshot path resolve 正確 | E4 跑 Linux 端 + give GREEN 後 PM commit |
| **PM** | 統一 commit + push（per CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM）。**ID `[68]` 決策需 PM 確認**（PA spec 寫 `[58]` 但碰撞） | PM 拍板 |

### 6.3 未被驗證的場景（請 reviewer 重點驗）

1. **真實 PG `trading.orders` + `order_state_changes` schema**：mock 假設兩表有 `trading.orders.engine_mode` /
   `trading.order_state_changes.to_status='Working'` 欄位，per V003 + V015。E4 需在 Linux trade-core
   驗 schema 確實 match（feedback_v_migration_pg_dry_run.md）。
2. **per-engine engine_mode enum 值**：mock 用 `paper/demo/live/live_demo`。check 邏輯
   loop 這 4 個。若 runtime engine_mode 有其他值（如歷史 `live_demo` 升級遺留），不被
   loop 涵蓋。可考慮加 unknown engine_mode 偵測 + WARN — 但本 IMPL scope 內未做。
3. **paper engine 預設 disabled**（`OPENCLAW_ENABLE_PAPER=0`）：paper snapshot
   會是 DISABLED marker（per `main_pipelines.rs:289-290`）；`_filled_notional_from_snapshot`
   會把 marker 視為 `paper_state` 缺鍵 → balance/positions=0/[]，正確降為「無 filled」
   evidence，不影響 verdict。Mac dev 無 paper snapshot 也走 same path。
4. **live_demo + live 共用 snapshot**：本 IMPL 把 live 與 live_demo 都讀
   `pipeline_snapshot_live.json`，但 PG query 用不同 `engine_mode=` 過濾。若 live snapshot
   存在但 live 沒激活，可能 live_demo evidence 雙重計算或漏。**建議 E4 在 Linux 端驗
   live + live_demo 跑同時的 evidence 分歧是否合理**。
5. **cap reference TOML 結構偏移**：本 IMPL 讀頂層 `correlated_exposure_max_pct`，但若未來
   TOML 加 `[exposure]` section，`_read_correlated_cap_pct` 已 fallback section dict。
   E2 應 review 兩 layout 都 covered。

### 6.4 Operator 下一步

1. 派 **E2** 代碼審查（focus §6.3 三 SQL / cross-engine evidence 議題）
2. PM 拍板 **`[68]` ID 決策**（接受 `[68]` / 改 `[58b]` / 其他）
3. E2 GREEN → 派 **E4** Linux runtime regression（真 PG schema + 真 engine_mode enum）
4. E4 GREEN → **PM 統一 commit** + push
5. **Cron install**（PM scope，operator 動作）：本 check 已掛 `runner.py` 主入口，
   無需新 cron entry — 配對既有 `helper_scripts/db/passive_wait_healthcheck_cron.sh`
   即自動 fire（per CLAUDE.md §七「被動等待 TODO 必附 healthcheck」）。

---

## 附錄 A：關鍵 diff 摘錄

### A.1 `checks_portfolio_resting_exposure.py`（新檔；6 helper + 1 main check）

```python
def check_68_portfolio_resting_exposure(cur) -> tuple[str, str]:
    """[68] portfolio_resting_exposure_lineage — resting maker exposure 哨兵。

    每 engine (paper/demo/live/live_demo) 各跑一次：
      1. 讀 pipeline_snapshot_{engine}.json 抽 filled notional + balance
      2. SQL trading.orders+order_state_changes 取 Working orders
         → per (symbol, side) resting notional
      3. 讀 risk_config_{engine}.toml correlated_exposure_max_pct
      4. Verdict: long/short 各別 < 80% cap PASS, ≥ 80% < 100% WARN, ≥ 100% FAIL
                  divergence < 50% PASS, ≥ 50% < 100% WARN, ≥ 100% FAIL
                  per-symbol resting/filled < 80% PASS, ≥ 80% WARN, > 150% FAIL
    """
    # Defensive rollback 保 cursor 在 sibling check 間乾淨
    try: cur.connection.rollback()
    except Exception: pass

    required = _enabled("OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED")
    lookback_hours = _lookback_hours()

    for engine in ENGINE_MODES:
        snap, snap_diag = _read_snapshot(engine)
        if snap is None:
            skipped_engines.append(f"{engine}({snap_diag})"); continue
        filled_per_symbol, balance = _filled_notional_from_snapshot(snap)
        resting_per_symbol, working_count, resting_diag = (
            _resting_notional_from_pg(cur, engine, lookback_hours)
        )
        ...  # verdict logic
```

### A.2 Critical SQL（Working orders aggregate）

```sql
WITH latest_state AS (
    SELECT DISTINCT ON (order_id) order_id, to_status
    FROM trading.order_state_changes
    WHERE ts > NOW() - (%s::text || ' hours')::interval
    ORDER BY order_id, ts DESC
)
SELECT o.symbol, o.side,
       SUM(o.qty * COALESCE(o.price, 0.0))::FLOAT AS notional_sum,
       COUNT(*)::INT AS row_count
FROM trading.orders o
JOIN latest_state ls ON o.order_id = ls.order_id
WHERE ls.to_status = 'Working'
  AND o.engine_mode = %s
  AND o.ts > NOW() - (%s::text || ' hours')::interval
GROUP BY o.symbol, o.side
```

走 `idx_orders_engine_mode_ts (engine_mode, ts DESC)` (V015) + V003 主 PK
`(order_id, ts)`。lookback 視窗（default 24h）避免拉整個 hypertable。

### A.3 ID 註：runner docstring 兩 list 補

```
[46][48][49][50][51][52][53][54][55][57][58][59][64][65][66][67][68]    REF-20...+
W-AUDIT-4b feature baseline readiness + P2-PORTFOLIO-RESTING-58-HEALTHCHECK portfolio
resting exposure lineage

[68] portfolio_resting_exposure_lineage  (P2-PORTFOLIO-RESTING-58-HEALTHCHECK 2026-05-16
P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up; 升 P1 per FA Stage 1 demo 啟前 mandatory;
監測 effective(filled+resting) vs filled-only leverage chain semantic drift;
per engine 4 sub-check: long/short notional vs cap × {80%,100%} + divergence vs
{50%,100%} + per-symbol resting/filled vs {80%,150%}; OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1
escalates WARN→FAIL; ID note: PA spec/TODO 標 [58] 但 [58]=W-AUDIT-9 T4 已占用，
取 [68] free slot, name preserved)
```

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--healthcheck_58_portfolio_resting_exposure.md`）**
