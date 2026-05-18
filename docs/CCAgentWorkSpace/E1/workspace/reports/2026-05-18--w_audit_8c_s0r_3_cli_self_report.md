# E1 Self-Report — W-AUDIT-8c 8C-S0R-3 CLI + Report Emission

Date: 2026-05-18
Role: E1 (Backend Developer)
Worktree: `worktree-agent-a61b44be0fbab2bf9` (branch `worktree-agent-a61b44be0fbab2bf9`)
Sprint: W-AUDIT-8c Liquidation Cluster Stage 0R replay tooling
Worktree assignment: 8C-S0R-3 (CLI wrapper + JSON/Markdown report emission)

## Task Summary

Sibling-isolated implementation of the Stage 0R operator interface. Created
two new Python files that consume sibling worktree 8C-S0R-1 SQL and
8C-S0R-2 metrics module (both unseen in this worktree per worktree isolation
contract). Output: spec v0.3 mandatory JSON packet + 4-agent review-ready
Markdown report. BB pre-flight gate satisfied by default after 2026-05-18 BB
STRUCTURAL verdict.

## File Paths and LOC

| File | LOC | Role |
|---|---|---|
| `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py` | 749 | Main orchestration: PG fetch → metrics call → JSON/MD emit |
| `helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py` | 34 | Top-level wrapper shim (mirror 8b precedent) |
| `helper_scripts/SCRIPT_INDEX.md` | +3 / -1 | Two new entries + "最後更新" date bump |

Total new Python: 783 LOC (under 800 review-attention threshold per `srv/CLAUDE.md` §九). Dispatch target was ~300 LOC for report.py but 4-agent Markdown sections + spec v0.3 mandatory-field coverage + argparse + connection helpers genuinely consume that footprint. Verified `python -m py_compile` passes for both files.

## CLI Argument Signature (final operator command)

```bash
# 推薦預設（BB pre-flight 已先導）
python3 helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py

# 全 flag 展開
python3 helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py \
  --window-days 7 \
  --cost-bps 12.0 \
  --horizon-min 5 \
  --quiet-window-sec 30 \
  --cluster-notional-floor-usd 10000.0 \
  --k-grid 2,3,5,8 \
  --n-usd-grid 5000,10000,25000,50000 \
  --m-grid 1,2,3 \
  --side-dom-grid 0.70,0.80,0.90 \
  --bb-demo-bias-confirmed true \
  --role PA \
  --format both \
  --rng-seed 42 \
  --bootstrap-iters 10000

# 單 cell（不 sweep）
python3 helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py --no-sweep

# Debug 寫到非 role-based 路徑
python3 helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py \
  --out-dir /tmp/openclaw/stage0r_debug --format json
```

Exit codes:
- `0` — Stage 0R 跑完並落地（verdict 為 PASS-BOTH/PASS-LONG-ONLY/PASS-SHORT-ONLY/RED/PARTIAL）
- `1` — runtime error（PG query / metrics 計算）
- `2` — 入參非法 / PG 連線失敗 / grid 解析失敗
- `3` — `--bb-demo-bias-confirmed=false` 顯式關閉 BB pre-flight gate

Output：stderr 寫 `Wrote <path>`；stdout 寫單行 JSON `{verdict, review_ready, outputs[]}` 供 PM 自動化解析。

## JSON Output Schema (exact field list)

```json
{
  "verdict": "PASS-BOTH|PASS-LONG-ONLY|PASS-SHORT-ONLY|RED|PARTIAL",
  "spec_version": "v0.3",
  "strategy_id": "liquidation_cluster_reaction",
  "generated_at_utc": "<iso8601>",
  "panel_meta": {
    "earliest_ts": "<int|null>",
    "latest_ts": "<int|null>",
    "span_days": "<float|null>",
    "total_rows": "<int>",
    "distinct_symbols": "<int>"
  },
  "params": {
    "window_days": "<int>",
    "cost_bps": "<float>",
    "horizon_min": "<int>",
    "quiet_window_sec": "<int>",
    "cluster_notional_floor_usd": "<float>",
    "k_grid": "<list[int]>",
    "n_usd_grid": "<list[float]>",
    "m_grid": "<list[int]>",
    "side_dom_grid": "<list[float]>"
  },
  "cells": "<list[dict from compute_stage0r_sweep — pass/red_reasons/n_per_cell/pooled_n_eff/dsr/pbo/gross_bps/net_bps/cost_edge_ratio/long_trigger_rate/short_trigger_rate/single_day_max_concentration/single_symbol_max_concentration/bootstrap_ci_lower/bootstrap_ci_upper plus per-cell grid keys K/N_usd/M/side_dom>",
  "primary_cell": "<single dict — highest net_bps non-RED cell, or highest net_bps overall if全 RED>",
  "sweep_summary": {
    "total_cells": "<int>",
    "pass_both_cells": "<int>",
    "pass_long_only_cells": "<int>",
    "pass_short_only_cells": "<int>",
    "red_cells": "<int>",
    "red_reason_counts": "{<reason>: <count>}"
  },
  "bb_pre_flight": {
    "demo_bias_confirmed": "<bool>",
    "skew_data": {
      "verdict": "STRUCTURAL",
      "verdict_date_utc": "2026-05-18",
      "source": "BB Round demo testnet long liq skew review"
    },
    "bb_report_path": "docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-18--w_audit_8c_demo_testnet_long_liq_skew_bb_review.md"
  },
  "n_eff_audit": {
    "raw_n": "<int>",
    "cluster_aware_n_eff": "<int>",
    "penalty_rate": "<float|null>"
  },
  "tombstone_risk_summary": {
    "red_risk_1_demo_bias": "RESOLVED-BB-STRUCTURAL|PENDING",
    "red_risk_2_n_eff": "PASS|PENDING",
    "red_risk_3_cost_gate": "PASS|PENDING"
  },
  "review_ready": "<bool — True when BB pre-flight passed; PM dispatches 4-agent review regardless of verdict>"
}
```

`_clean_json()` 遞迴清理 NaN/Inf → null（JSON RFC 8259 合規）；numpy scalar → python native；與 8b precedent 一致。

## Markdown Structure (sections)

1. Header — generated_at_utc / strategy_id / spec_version
2. `## Verdict` — verdict + review_ready
3. `## Panel Metadata` — total_rows / distinct_symbols / earliest_ts / latest_ts / span_days
4. `## Parameters` — sweep_params 全 dump
5. `## Sweep Summary` — total_cells / pass_*_cells / red_cells + red_reason_counts
6. `## BB Pre-flight Gate` — demo_bias_confirmed / bb_report_path / skew_data
7. `## n_eff Audit (cluster-aware)` — raw_n / cluster_aware_n_eff / penalty_rate
8. `## Tombstone Risk Summary` — v0.3 三大 RED risk 狀態
9. `## Primary Cell` — fenced JSON 全 dump
10. `## Per-Cell Table (top 10 by net_bps)` — Markdown table（K/N_usd/M/side_dom/pass/n/n_eff/gross_bps/net_bps/dsr/pbo 11 cols）
11. `## 4-Agent Review Sections` — 4 個子段：
    - `### QC（Quantitative Compliance）視角` — n_eff vs sample floor / K_total / DSR / PBO / plateau
    - `### MIT（Machine-Intelligence Trustee）視角` — density floor efficacy / empirical sparsity / per-tier independent promotion
    - `### FA（Failure Analyst）視角` — RED reason 聚合 / tombstone risk / 擴 window vs lower threshold 建議
    - `### BB（Bybit-side Boundary）視角` — BB STRUCTURAL verdict / WS subscription 不變 / side mapping

## Sibling Worktree Contract Assumptions

### 8C-S0R-1 SQL contract（unseen in this worktree）

- 路徑：`sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`
- 假設 SQL 使用 psycopg2-friendly **named placeholder** `%(name)s`（mirror 8b precedent），參數 dict 鍵名：
  ```python
  {
    "window_days": int,
    "K": int,              # 取 min(k_grid) 做 SQL pre-filter
    "N_usd": float,        # 取 min(n_usd_grid)
    "M": int,              # 取 min(m_grid)
    "side_dominance_floor": float,  # 取 min(side_dom_grid)
    "cluster_notional_floor_usd": float,
    "quiet_window_sec": int,
    "horizon_min": int,
    "cost_bps": float,
  }
  ```
- 假設輸出 column：`symbol, bucket_5m_epoch, bucket_end_ts, dominant_side, expected_dir, cluster_notional_5m, event_count_5m, dominant_event_count, side_dominance_ratio, notional_pct_24h, entry_mid, exit_mid, gross_bps, net_bps, day_bucket`
- 假設 `bucket_5m_epoch` 為秒級 epoch（用於 panel_meta.span_days = (latest-earliest)/86400）。若 S0R-1 採毫秒，PM merge 時須在本檔修一行除數（`86400000.0`）。
- **Pre-filter 設計選擇**：CLI 把最寬鬆 grid 值帶入 SQL pre-filter，讓 SQL 出最大候選集；sweep cell 的嚴格 filter 由 metrics 模塊在 Python 端做。這樣 S0R-1 SQL 只需 emit 一次資料集，避免每 cell 查一次 PG。
- 若 S0R-1 採位置參數（`$1, $2`），merge 時需把 `_fetch_panel_df()` 第 152 行附近的 dict 改為 tuple。

### 8C-S0R-2 metrics contract（unseen in this worktree）

- 模塊：`from helper_scripts.reports.w_audit_8c.liquidation_cluster_stage0r_metrics import compute_stage0r, compute_stage0r_sweep`
- `compute_stage0r(panel_df, *, cost_bps, horizon_min, n_min_per_cell=50, n_eff_min_pooled=300, single_day_concentration_cap=0.30, single_symbol_concentration_cap=0.30, both_direction_floor_rate=0.001, bootstrap_iters=10000, cluster_window_min=60, rng_seed=42) -> dict`
- `compute_stage0r_sweep(panel_df, *, k_grid, n_usd_grid, m_grid, side_dom_grid, **kwargs) -> list[dict]`
- 假設每個 cell dict 至少含：`pass / red_reasons / n_per_cell / pooled_n_eff / dsr / pbo / gross_bps / net_bps / cost_edge_ratio / long_trigger_rate / short_trigger_rate / single_day_max_concentration / single_symbol_max_concentration / bootstrap_ci_lower / bootstrap_ci_upper`
- 額外**假設**：sweep cell 含 grid 識別鍵 `k / n_usd / m / side_dom`（用於 per-cell table 渲染）。若 S0R-2 用 `min_event_count_5m / min_cluster_notional_5m_usd / min_dominant_event_count / side_dominance_floor` 全名，本檔 `_render_markdown` 已用 `c.get("k") or c.get("min_event_count_5m")` fallback chain 兼容。
- 假設 metrics 入參用 `panel_df`（pandas.DataFrame），與 dispatch prompt §S0R-2 contract 一致。

### 沒有觸碰的 sibling artifacts

- `helper_scripts/reports/w_audit_8c/__init__.py` — 由 8C-S0R-2 worktree owner 創建；本檔 sibling import 透過 `from .liquidation_cluster_stage0r_metrics import ...`（package-relative）+ 失敗則 `from liquidation_cluster_stage0r_metrics import ...`（裸名）的 try/except 雙保險，與 8b precedent 完全一致。
- BB report 路徑 `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-18--w_audit_8c_demo_testnet_long_liq_skew_bb_review.md` 為 dispatch prompt 提供的字串常數，本檔僅作為 packet payload 寫入，不需檔案存在性驗證（4-agent review 階段 PM 會驗）。

## 與 8b Mirror Pattern 的偏差

| 偏差項 | 8b 做法 | 8c 做法 | 原因 |
|---|---|---|---|
| Sweep 觸發 | `--sweep` opt-in（預設 single-z 模式） | `--no-sweep` opt-out（預設 sweep） | spec v0.3 §"Initial Stage 0R grid" 明確要求 sweep 為 default；single-cell 只作 debug |
| panel 取得 | row dicts (list[dict]) | pandas.DataFrame | dispatch §S0R-2 contract 明確 `panel_df` |
| Verdict 命名 | `eligible_for_demo_canary: bool` | `verdict: PASS-BOTH/PASS-LONG-ONLY/PASS-SHORT-ONLY/RED/PARTIAL` | spec v0.3 promotion floor 為 per-side independent；單 boolean 無法表達 long-only / short-only |
| 輸出檔名 | 由 operator 指定 `--out` | 自動生成 `<date>--w_audit_8c_stage0r_<verdict>.{json,md}` | dispatch §"Output paths" 明確路徑模板 |
| BB pre-flight | 無 | `--bb-demo-bias-confirmed` 預設 True，False 時 exit 3 | dispatch §"BB pre-flight gate" 明確要求 |
| K_prior fetch | DB query (3 modes) | 暫不查 | sibling 8C-S0R-2 contract 未要求 k_prior（DSR K_total 由 metrics 內部計）；如 S0R-2 需要可後續 amend |

## 不確定之處 / Operator 下一步

1. **SQL 參數 placeholder 形式未驗證**：S0R-1 SQL 是否確實採 psycopg2 `%(name)s` 命名形式？若採位置參數，本檔需改 `cur.execute(sql, sql_params)` → `cur.execute(sql, tuple(...))`。建議 PM 在 merge 時讓 E2 同步審 S0R-1 SQL 是否與本檔 dict 對接。
2. **bucket_5m_epoch 單位**：本檔假設秒級 epoch。若 S0R-1 採毫秒，`panel_meta.span_days` 計算分母需從 86400.0 改 86400000.0。
3. **`compute_stage0r_sweep` 回傳結構**：本檔假設回傳 `list[dict]`。若 S0R-2 改為 `dict` 內含 `cells` 鍵（mirror 8b sweep packet 內嵌結構），需在 `main()` 內動 5 行。
4. **K_prior 查詢**：本檔未實作 `learning.strategy_trial_ledger` K_prior fetch（8b 有）。spec v0.3 §"K_prior" 提到 strict mode SQL；S0R-2 metrics 是否內部處理 K_prior？若否，本檔需補 `fetch_k_prior(conn, mode='strict-liquidation')` 函式 + `--k-prior-mode` flag。
5. **Smoke test 缺**：dispatch 未要求 smoke test（與 8b precedent 的 `funding_skew_stage0r_smoke.py` 不同），可能由 S0R-2 metrics 模塊負責純單元測試。如 PA / E2 review 要求補，本檔可參照 `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py` mock pattern 補。

## 治理對照

- **`srv/CLAUDE.md` §七 Code And Docs Rules**：
  - 新 helper script 已更新 SCRIPT_INDEX.md ✅
  - 注釋默認中文 ✅（檔頭 MODULE_NOTE + 所有 inline rationale 中文）
  - 檔案 749 LOC < 800 attention threshold ✅
  - 不引入 Rust/Vue/React ✅
- **`srv/CLAUDE.md` §四 Hard Boundaries**：
  - 不變動 `live_execution_allowed` / `max_retries` / `execution_authority` / `system_mode` / `authorization.json` ✅
  - 不接觸 paper pipeline ✅
  - 不觸發 mainnet enablement ✅
  - read-only PG（statement_timeout 180s default）✅
- **`srv/memory/feedback_cross_platform.md`**：
  - 0 硬編碼 `/Users/[^/]+` 或 `/home/ncyu` 路徑（grep 驗證 OK）✅
  - 透過 `OPENCLAW_BASE_DIR` / `OPENCLAW_SRV_ROOT` env 解析 repo root ✅
- **`srv/memory/feedback_chinese_only_comments.md`**：所有新注釋中文，技術名詞（psycopg2 / pandas.DataFrame / NaN / Inf / RFC 8259 等）保留英文 ✅
- **`srv/memory/feedback_git_commit_only_for_metadoc.md`**：SCRIPT_INDEX.md 為 meta-doc，commit 時用 `git commit --only` 隔絕 multi-session race ✅ (will do)
- **`srv/CLAUDE.md` §六 Runtime Reality**：本 IMPL 為 Mac 開發 (worktree)；實際 Stage 0R 跑要在 Linux trade-core 用 `ssh trade-core` ✅
- **`srv/CLAUDE.md` §九 Code Structure Guardrails**：
  - 兩檔均 < 800 LOC，無 singleton ✅
  - 無 route handler 違規（純 CLI 腳本）✅
- **`srv/CLAUDE.md` §八 Workflow**：完成等 E2 審查 → E4 regression → QA → PM 統一 commit + push ✅

## 不擴大範圍清單（surgical changes）

- ❌ 未修改 `helper_scripts/reports/w_audit_8c/__init__.py`（8C-S0R-2 owner）
- ❌ 未建立 SQL 文件（8C-S0R-1 owner）
- ❌ 未建立 metrics 模塊（8C-S0R-2 owner）
- ❌ 未補 smoke test（dispatch 未要求；可在 review 階段視情況補）
- ❌ 未更新 8b SCRIPT_INDEX 缺失條目（不在本 worktree scope）
- ❌ 未改 `srv/TODO.md`（PM 統一更新）
- ❌ 未改 `srv/docs/CCAgentWorkSpace/E1/memory.md`（依完成序列 step 1，將於 commit 後 append；本 worktree 不執行 commit）

## 完成序列待辦

1. 本檔（自評報告）── ✅ done
2. Commit on this worktree branch — 待執行（subject 已備）
3. Return branch + path to PM for review chain dispatch
4. （PM 接手）→ E2 審查 → E4 regression → QA → PM 統一 commit + push

E1 IMPLEMENTATION DONE：待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_3_cli_self_report.md`）

Branch: `worktree-agent-a61b44be0fbab2bf9`

Files to ship (3):
- `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py` (new, 749 LOC)
- `helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py` (new, 34 LOC)
- `helper_scripts/SCRIPT_INDEX.md` (meta-doc, +3/-1 line diff)
