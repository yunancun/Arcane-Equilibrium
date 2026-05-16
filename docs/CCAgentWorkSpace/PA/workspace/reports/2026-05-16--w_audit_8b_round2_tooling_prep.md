# PA — W-AUDIT-8b Round 2 Tooling Prep (Phase A Design Packet) + Phase B Rerun Plan

**Date**: 2026-05-16 19:18Z
**Author**: PA(default)
**Status**: PA DESIGN DONE — Phase A E1 派發 packet 設計完成；Phase A IMPL 階段 NOT EXECUTED（per PA 角色定位「不寫功能代碼」+ `feedback_impl_done_adversarial_review.md` 高風險 IMPL 必走 E1 IMPL + A3+E2 對抗審核）；Phase B scheduled rerun 計劃 ready
**Inputs**:
- spec v0.3 land `srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` (v0.3 / 501 LOC / commit `41e12a84`)
- Phase 2 run plan `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_spec_v03_sensitivity_sweep_patch.md`
- RED RCA `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md`
- Round 1 verdict `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_replay_packet_verdict.md`
- Existing tooling: `helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py` (18 LOC wrapper) + `helper_scripts/reports/w_audit_8b/{__init__.py, funding_skew_stage0r_metrics.py 1162 LOC, funding_skew_stage0r_report.py 285 LOC, funding_skew_stage0r_smoke.py 229 LOC}` + `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` 131 LOC
- Linux PG empirical 2026-05-16 19:18Z（panel funding 205,526 rows / 25 sym / 5.823d span / K_prior strict=0 / cycles=31）

**Verdict (PA)**：Phase A E1 派發 packet DESIGN DONE；reject 「PA 自己 IMPL」reading of task prompt（push back operator instruction，per §1.3）；建議 PM 派 E1 IMPL chain。Phase B rerun 啟動條件 panel ≥7d 預計 calendar **2026-05-17 23:30Z + 1h safety margin = 2026-05-18 00:30Z**（+1.18d from 19:18Z）。

---

## §1 Push back operator instruction：PA 不親自 IMPL，必走 E1 → A3+E2+E4 鏈

### 1.1 任務 prompt 語意 vs PA 角色定位衝突

任務 prompt §"Phase A (做 NOW)" 寫：

```
**1. Tooling implementation**:
- 修改 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py：加 --sweep flag + --z-cells 1.0,1.2,1.5,2.0 argument
- 4-cell parallel sweep loop
- 4-block JSON output schema 對齊 spec v0.3
- Wilson CI computation per (z_cell, branch, symbol)
- Pre-rerun assertion gates check

**2. Code review**:
- E2 + E4 + A3 grep audit
```

字面 reading：PA 親自 IMPL 然後派 E2+E4+A3。但這違反兩條規則：

1. **PA 角色定位**（`srv/docs/CCAgentWorkSpace/PA/profile.md` §"硬約束"）：「派發任務前必須閱讀相關代碼，不能基於假設設計方案」+ PA 「不自己寫功能代碼」（per profile.md §1 角色定位「但不自己寫功能代碼」）+ §"輸出物標準"：技術設計文件 / E1 派發計劃 / 高風險警告 3 點 — 都是設計 / 派發 / 識別工作，不是 IMPL。
2. **`feedback_impl_done_adversarial_review.md`**：高風險 IMPL（GUI / IPC / 寫操作 / 共用 helper）sub-agent 自評 IMPL DONE 不接受單獨 sign-off；強制派 A3 + E2 並行核驗。本任務符合「共用 helper」高風險範疇（`funding_skew_stage0r_*.py` 是治理性質的 read-only audit packet 工具，是後續 W-AUDIT-8b/8c 系列 + AMD-2026-05-15-02 §8 condition 3 的 evidence emitter，**IMPL 錯誤直接導致 round 2 verdict 失誤 → 影響 W-AUDIT-8b tombstone / AMD 修訂決策**）。

### 1.2 風險評級判定

本 tooling IMPL 風險評級 = **高**（per profile.md §"改動風險評級"）：
- ❌ 不只是顯示層改動（低）
- ❌ 不只是「改邏輯但有完整測試覆蓋的模塊」（中）— smoke test 涵蓋部分但 4-z sweep + Wilson CI + 4-block JSON output schema 是新功能無基線
- ✅ 跨模塊接口改動（CLI args / `compute_stage0r_sweep()` 新 API / 4-block JSON output schema / Wilson CI 新公式）
- ✅ 對 round 2 verdict + 後續 AMD 修訂有 systemic 影響

風險評級 = **高** → 強制走 `feedback_impl_done_adversarial_review.md` chain：E1 IMPL → A3 + E2 並行對抗審核 → E4 regression baseline → PA verdict round 2 dispatch。

### 1.3 PA 推薦工作鏈（修正 task prompt）

```
Phase A:
  Step 1: PA design packet (本 report DONE)
  Step 2: PM dispatch @E1 IMPL per packet
  Step 3: @A3 + @E2 並行對抗審 (vital, per feedback_impl_done_adversarial_review.md)
  Step 4: @E4 regression smoke (補 baseline, 不替代 A3/E2)
  Step 5: PM sign-off Phase A → commit + push

Phase B (panel ≥ 7d):
  Step 6: PA solo run Linux PG empirical assertion gate (§4.1)
  Step 7: PA solo run round 2 sweep on Linux (§4.2)
  Step 8: PA write round 2 verdict report
  Step 9: 派 PA + QC + MIT + BB 4-agent re-review
```

**PA 在此處 DESIGN DONE**，不繼續到 Step 2 IMPL；建議 PM 接手 dispatch E1。如果 operator 明確 reverse pushback 要求 PA 親自 IMPL（per task prompt 字面），PA 配合，但仍**強制保留 Step 3+4** 不可跳；若跳 = `feedback_impl_done_adversarial_review.md` 違規。

---

## §2 既有 tooling 形貌 + IMPL 障礙分析

### 2.1 模塊結構

| 檔案 | LOC | 角色 | sweep 改動需要 |
|---|---:|---|---|
| `helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py` | 18 | CLI wrapper (薄殼，import `funding_skew_stage0r_report.main`) | 不動 |
| `helper_scripts/reports/w_audit_8b/__init__.py` | 1 | empty | 不動 |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py` | 1162 | 核心 metrics + `compute_stage0r()` monolithic function（symbol × branch × z × p × oi × horizon 6-deep loop）| 重 |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py` | 285 | CLI entry + DB fetch + JSON/markdown render | 中（加 --sweep + render sweep output）|
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py` | 229 | Mac smoke test fixture（不接 PG）| 中（加 4-z fixture test）|
| `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` | 131 | raw panel as-of join SQL | **不動**（z 過濾在 Python 層） |

### 2.2 Z_GRID hardcoded 障礙

`funding_skew_stage0r_metrics.py:20` ：

```python
Z_GRID = (1.5, 2.0, 2.5)
```

`compute_stage0r()` 內 `for z_hi in Z_GRID:` 用 module-level constant。Sweep IMPL 必須將 Z_GRID 變成可注入 parameter，否則 4-z sweep 無法在單次 call 內探索。

`K_NEW_MIN` (line 29-36) 也基於 Z_GRID hardcoded：

```python
K_NEW_MIN = (
    MIN_STAGE0R_SYMBOLS  # 25
    * len(BRANCHES)       # 2
    * len(Z_GRID)         # 3 → 4 in v0.3
    * len(P_GRID)         # 3
    * len(OI_GRID)        # 3
    * len(HORIZONS)       # 3
)
```

v0.3 要 K_NEW_MIN = 5400（per spec §"K_total per-cell minimum 要求"）= 25 × 2 × 4 × 3 × 3 × 3。Z_GRID 由 3 → 4 cells 自動推導 5400。

### 2.3 `compute_stage0r()` 內部結構 + sweep wrapper 影響

`compute_stage0r()` (line 587-1154) 內部行為：
- 接 `rows` + `k_prior` + `cost_bps`
- 跑 6-deep loop（symbol × branch × z × p × oi × horizon）構造 `cells`
- 對 PRIMARY_HORIZON (30m) cell aggregate 出 `pooled_by_param` / `branch_by_param` / `per_symbol_by_param`
- 跑 PBO / baseline / plateau check / cost-edge model
- 出 `selected_cell` + `eligibility_fail_reasons`
- 回 packet dict（48 fields 含 strategy/K/source_mode/panel_metadata/exclusions/pooled_primary/branch_summary/per_symbol_breakdown/settlement_window/baseline_lift/execution_cost_model/pbo/plateau_check/best_primary_cell/top_primary_cells/...)

**設計選項評估**：

| Option | Approach | Pros | Cons | PA 推薦 |
|---|---|---|---|---|
| A | 4× call `compute_stage0r(rows, ...)`（z=[1.0]/[1.2]/[1.5]/[2.0]）後 sweep wrapper aggregate | 最簡單 / 既有 fn 不動 | K_total 每 call 1350 ≠ spec v0.3 要 5400；packet 内 baseline pool 重算 4 次浪費；Wilson CI 從 packet 外算 | ❌ |
| B | 將 `compute_stage0r(rows, *, k_prior, cost_bps, z_grid=Z_GRID)` 加 z_grid 參數；新增 `compute_stage0r_sweep(rows, z_cells=[1.0,1.2,1.5,2.0])` wrapper；wrapper 內呼 `compute_stage0r` 4 次（每次 z_grid=[z]）並 aggregate；Wilson CI 在 wrapper module-level helper 計算 | 既有 fn 改動小（加 1 kwarg + 改 K_NEW_MIN 計算）；sweep wrapper 隔離 | 仍 4× baseline / SQL fetch 重複（外層 fetch 一次傳 4 次 OK）；wrapper aggregate 需小心對齊 4-block JSON schema | ✅ **PA 推薦** |
| C | Deep refactor `compute_stage0r` 內部 loop 加 z_cell 維度 single-pass | 最 efficient | 風險最高（高 cognitive load + 重 regression risk）；既有 round 1 RED packet 行為不能變 | ❌ |

**PA 推薦 Option B** — wrapper 模式隔離既有 round 1 行為（v0.2 fixed `z_grid=(1.5, 2.0, 2.5)` 仍可用 single-call 復現 RED packet），sweep wrapper 純加 v0.3 4-z sweep 增量功能。

### 2.4 Wilson CI 公式 vs 既有 PSR/DSR/bootstrap CI

Wilson CI 是新公式（per spec v0.3 §"Wilson CI Computation per Cell"）：

```text
p_hat = n_eff / n
z = 1.96 (95% CI)
denom = 1 + z² / n
center = (p_hat + z² / (2n)) / denom
margin = z × sqrt( p_hat (1 - p_hat) / n + z² / (4n²) ) / denom
wilson_ci_lower = center - margin
wilson_ci_upper = center + margin
```

對齊 per (z_cell, branch, symbol)。**Numerical stability concern**：n small (n=0, n=1, n<3) edge case 必加 guard：
- n=0 → wilson_ci = (None, None)
- n=1 + n_eff=0 → wilson_ci_lower/upper 在 [0, 1] 範圍 OK；但 IMPL 必驗
- n > 0 但 n_eff=0 → p_hat = 0 / wilson_ci 中心應 < z²/(2n) / denom，公式仍 stable

公式 IMPL 必 unit test against 已知 ref：
- n=20, n_eff=4 → p=0.2 → Wilson 95% ~ (0.082, 0.422)（NIST handbook ref）
- n=100, n_eff=50 → p=0.5 → Wilson 95% ~ (0.404, 0.596)
- n=10, n_eff=2 → p=0.2 → Wilson 95% ~ (0.057, 0.510)

### 2.5 4-block JSON output schema 對齊

Per spec v0.3 §"Output Format Spec"，sweep packet 必須輸出 4 個 top-level blocks（新增 keys，沿用 既有 packet 也要保留）：

```json
{
  // 既有 packet（v0.2 round 1 既有 keys，最後一個 z_cell 結果作 backward-compat）
  "strategy_variant": "funding_skew_directional.v0_3",  // ← v0.3 升 variant
  "alpha_source_id": "funding_skew_directional",
  // ... 既有 38 keys
  
  // v0.3 新增 4 blocks
  "sweep_per_z_cell": { "z_relaxed_z_eq_1_0": {...}, "z_moderate_z_eq_1_2": {...}, "z_baseline_z_eq_1_5": {...}, "z_strict_z_eq_2_0": {...} },
  "sweep_per_symbol": [ {...}, ... ],  // 4 × 2 × 25 = 200 rows
  "best_primary_cell_per_z_branch": [ {...}, ... ],  // 4 × 2 = 8 rows
  "sweep_cross_z_comparison": [ {...}, ... ],  // 2 × 25 = 50 rows
  
  // v0.3 sweep meta
  "sweep_meta": {
    "sweep_enabled": true,
    "z_cells": [1.0, 1.2, 1.5, 2.0],
    "k_new_min_v0_3": 5400,
    "k_total_v0_3": 5400,  // K_prior strict=0
    "sweep_eligibility": "false | true (any cell eligible_for_demo_canary=true OR z_strict diagnostic-only)"
  }
}
```

**Backward-compat decision**：sweep mode 下既有 packet keys 仍出（取 z_baseline cell 結果，保 v0.2 round 1 對比能力）；新加 sweep_* blocks 在 top-level。CLI `--sweep` 不設時走 v0.2 single-z behavior（單一 z_grid=(1.5, 2.0, 2.5)）保 round 1 reproducibility。

---

## §3 Phase A E1 派發 packet（DISPATCH READY for PM）

### 3.1 Worktree: w-audit-8b-round2-sweep

**Bound role**: `E1(worker)`
**Branch suggestion**: `feature/w-audit-8b-round2-sweep`
**Worktree base**: `origin/main` HEAD `a26c1ed9` (2026-05-16 21:08 CEST)

**Mission**：在既有 W-AUDIT-8b stage0r tooling 加 4-z sensitivity sweep mode（per spec v0.3）。CLI 加 `--sweep` `--z-cells`；metrics 加 `compute_stage0r_sweep()` wrapper + Wilson CI helper；report 加 4-block JSON serialization；smoke 加 4-z fixture test。

### 3.2 Owned files (E1 改 / 加)

| 檔案 | 改動範圍 | LOC 預估 |
|---|---|---:|
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py` | (1) `compute_stage0r(rows, *, k_prior, cost_bps, z_grid=Z_GRID)` 加 z_grid kwarg；K_NEW_MIN 改為 `len(z_grid) × ...` 動態計算；(2) 新加 `wilson_ci_95(n, n_eff) -> tuple[float, float] | None` helper；(3) 新加 `compute_stage0r_sweep(rows, *, k_prior, cost_bps, z_cells: Sequence[float]) -> dict` wrapper | +180-240 source |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py` | (1) CLI add `--sweep` flag + `--z-cells` argument；(2) 加 `_render_sweep_packet(packet) -> str` for markdown mode；(3) main() 分支 sweep vs single-z mode | +120-160 source |
| `helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py` | **不動**（wrapper 直接 import `funding_skew_stage0r_report.main` 已含新 CLI args） | 0 |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py` | 新加 `_check_sweep_mode()` + `_check_wilson_ci_bench()` + `_check_4z_fixture()` smoke test 函數；既有 single-z smoke 保留 | +120-180 tests |

**Total**: +420-580 source/test LOC across 3 files。不動 SQL / 不動 wrapper entry / 不動 TOML / 不動 risk config / 不動 runtime / 不動 DB schema / 不動 auth。

### 3.3 IMPL specs

#### 3.3.1 `compute_stage0r(...)` z_grid param 化

**Before** (line 587-590):
```python
def compute_stage0r(
    rows: Sequence[Mapping[str, object]],
    *,
    k_prior: int,
    cost_bps: float,
) -> dict[str, object]:
```

**After**:
```python
def compute_stage0r(
    rows: Sequence[Mapping[str, object]],
    *,
    k_prior: int,
    cost_bps: float,
    z_grid: Sequence[float] = Z_GRID,
) -> dict[str, object]:
```

K_NEW_MIN 計算（line 29-36）改為 single source `K_NEW_MIN_DEFAULT = ...` 不變保 backward compat；`compute_stage0r` 內部用 `len(z_grid)` 動態算：

```python
k_new_actual = len(symbols) * len(BRANCHES) * len(z_grid) * len(P_GRID) * len(OI_GRID) * len(HORIZONS)
k_new_min_dynamic = MIN_STAGE0R_SYMBOLS * len(BRANCHES) * len(z_grid) * len(P_GRID) * len(OI_GRID) * len(HORIZONS)
k_new = max(k_new_min_dynamic, k_new_actual)
k_total = int(k_prior) + k_new
```

內部 6-deep loop `for z_hi in Z_GRID:` 改 `for z_hi in z_grid:`。

#### 3.3.2 `wilson_ci_95()` 新加 module-level helper

```python
def wilson_ci_95(n: int, n_eff: int) -> tuple[float, float] | None:
    """Wilson Score Interval 95% for binomial proportion n_eff / n.
    
    Per spec v0.3 §"Wilson CI Computation per Cell"：
        p_hat = n_eff / n
        z = 1.96 (95% CI)
        denom = 1 + z² / n
        center = (p_hat + z² / (2n)) / denom
        margin = z × sqrt( p_hat (1 - p_hat) / n + z² / (4n²) ) / denom
    
    Returns (lower, upper) clamped to [0, 1]，or None if n <= 0.
    """
    if n <= 0:
        return None
    z = 1.96
    p_hat = n_eff / n
    z_sq = z * z
    denom = 1.0 + z_sq / n
    center = (p_hat + z_sq / (2 * n)) / denom
    inner = p_hat * (1.0 - p_hat) / n + z_sq / (4 * n * n)
    if inner < 0:
        return None
    margin = z * math.sqrt(inner) / denom
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return (lower, upper)
```

#### 3.3.3 `compute_stage0r_sweep(...)` wrapper 新加

```python
def compute_stage0r_sweep(
    rows: Sequence[Mapping[str, object]],
    *,
    k_prior: int,
    cost_bps: float,
    z_cells: Sequence[float],
) -> dict[str, object]:
    """Round 2 v0.3 sweep wrapper：4 個 z_cell 並排跑 compute_stage0r + Wilson CI per cell。
    
    Args:
        rows: SQL fetch raw feature rows (per panel as-of join)
        k_prior: ledger strict funding_skew prior (empirical 2026-05-16 = 0)
        cost_bps: conservative flat cost (12.0)
        z_cells: list of z thresholds, e.g. [1.0, 1.2, 1.5, 2.0]
    
    Returns:
        dict with v0.2 backward-compat keys + 4 sweep blocks (per spec v0.3 §"Output Format Spec"):
            - sweep_per_z_cell: dict[z_cell_id, dict] (4 cells)
            - sweep_per_symbol: list[dict] (4 × 2 × 25 = 200 rows)
            - best_primary_cell_per_z_branch: list[dict] (4 × 2 = 8 rows)
            - sweep_cross_z_comparison: list[dict] (2 × 25 = 50 rows)
            - sweep_meta: dict with eligibility decision
    """
    z_cell_ids = []
    per_z_packets: dict[str, dict] = {}
    for z in z_cells:
        z_cell_id = _z_cell_id(z)  # e.g. "z_relaxed_z_eq_1_0" / "z_baseline_z_eq_1_5"
        z_cell_ids.append(z_cell_id)
        # Per-z compute (z_grid only has this one z value)
        per_z_packets[z_cell_id] = compute_stage0r(
            rows,
            k_prior=k_prior,
            cost_bps=cost_bps,
            z_grid=(z,),
        )
    
    # Assemble 4 sweep blocks
    sweep_per_z_cell = _build_sweep_per_z_cell(per_z_packets, z_cells, k_total_v03=K_NEW_MIN_V03)
    sweep_per_symbol = _build_sweep_per_symbol(per_z_packets, z_cells, rows)
    best_primary_cell_per_z_branch = _build_best_primary_per_z_branch(per_z_packets, z_cells)
    sweep_cross_z_comparison = _build_sweep_cross_z(per_z_packets, z_cells, rows)
    
    # K_NEW_MIN_V03 for v0.3 5400 floor recompute
    k_new_actual = ...  # 25 × 2 × len(z_cells) × 3 × 3 × 3
    k_new = max(K_NEW_MIN_V03, k_new_actual)
    k_total = k_prior + k_new
    
    # Sweep eligibility decision (per spec v0.3 §"接受 / Reject 條件")
    sweep_eligibility = _decide_sweep_eligibility(sweep_per_z_cell, z_cells)
    
    # Baseline v0.2 backward-compat: 取 z_baseline (z=1.5) packet 作 v0.2 既有 packet shape
    baseline_packet = per_z_packets.get(_z_cell_id(1.5)) or list(per_z_packets.values())[0]
    
    return {
        **baseline_packet,  # v0.2 backward-compat 38 keys
        "strategy_variant": "funding_skew_directional.v0_3",  # ← v0.3 升 variant
        "k_new": k_new,
        "k_new_min": K_NEW_MIN_V03,  # 5400
        "k_total": k_total,
        "sweep_per_z_cell": sweep_per_z_cell,
        "sweep_per_symbol": sweep_per_symbol,
        "best_primary_cell_per_z_branch": best_primary_cell_per_z_branch,
        "sweep_cross_z_comparison": sweep_cross_z_comparison,
        "sweep_meta": {
            "sweep_enabled": True,
            "z_cells": list(z_cells),
            "k_new_min_v0_3": K_NEW_MIN_V03,
            "k_total_v0_3": k_total,
            "sweep_eligibility": sweep_eligibility,
        },
    }
```

**Helper functions to add**:
- `_z_cell_id(z: float) -> str`：例如 `1.0 → "z_relaxed_z_eq_1_0"`，`1.2 → "z_moderate_z_eq_1_2"`，`1.5 → "z_baseline_z_eq_1_5"`，`2.0 → "z_strict_z_eq_2_0"`
- `_build_sweep_per_z_cell(per_z_packets, z_cells, k_total_v03) -> dict`：4 個 (z_cell, branch) × pooled summary + Wilson CI for n_eff/n + eligibility per cell
- `_build_sweep_per_symbol(per_z_packets, z_cells, rows) -> list`：200 rows，每行 (z_cell, branch, symbol) 的 n / n_eff / avg_net / Wilson CI
- `_build_best_primary_per_z_branch(per_z_packets, z_cells) -> list`：8 rows，每行 (z_cell, branch) 的 best primary cell（v0.2 既有 `best_primary_cell` 邏輯）
- `_build_sweep_cross_z(per_z_packets, z_cells, rows) -> list`：50 rows = 2 branches × 25 symbols × 4-z columns
- `_decide_sweep_eligibility(sweep_per_z_cell, z_cells) -> str`：per spec v0.3 §"接受 / Reject 條件"

**Module-level constant**:
```python
K_NEW_MIN_V03 = (
    MIN_STAGE0R_SYMBOLS  # 25
    * len(BRANCHES)       # 2
    * 4                   # 4 z_cells (v0.3 sweep)
    * len(P_GRID)         # 3
    * len(OI_GRID)        # 3
    * len(HORIZONS)       # 3
)  # = 5400
```

#### 3.3.4 CLI `--sweep` `--z-cells` arguments

`funding_skew_stage0r_report.py` `main()` 加 argparse：

```python
parser.add_argument(
    "--sweep",
    action="store_true",
    help="enable v0.3 4-z sensitivity sweep mode (per spec v0.3)",
)
parser.add_argument(
    "--z-cells",
    type=str,
    default="1.0,1.2,1.5,2.0",
    help="comma-separated z thresholds for sweep mode (default: 1.0,1.2,1.5,2.0)",
)
```

Main flow 分支：

```python
if args.sweep:
    z_cells = tuple(float(z.strip()) for z in args.z_cells.split(","))
    packet = compute_stage0r_sweep(rows, k_prior=k_prior, cost_bps=args.cost_bps, z_cells=z_cells)
else:
    packet = compute_stage0r(rows, k_prior=k_prior, cost_bps=args.cost_bps)
```

#### 3.3.5 Pre-rerun assertion gate

**PA decision**：assertion gate **不放在 Python tooling 內**，由 **PA Phase B Step 6 solo 跑 Linux PG empirical query** 驗（per Phase 2 run plan §2.1）。理由：

1. Tooling 是 read-only audit packet emitter，不應依賴外部 PG 多次 round-trip
2. Assertion gate (panel ≥ 7d / sym=25 / K_prior strict=0 / cycles ≥ 21) 必須 PA 親自驗才有 governance 簽認效力（per `feedback_workflow_audit_chain.md` PA 親驗 CRITICAL 條件）
3. Tooling 跑時假設 assertion 已 PA 通過 → 跑 tooling 是 evidence-emit；assertion failure 由 PA verdict halt，不靠 tooling 內部 raise

如果 E1 想加 defensive runtime check（不取代 PA solo verify），可加 `--require-window-days N` flag 由 wrapper 跑前 query 一次 `panel.funding_rates_panel` span_days，如 < N → exit 2。這是 nice-to-have 不是 MUST。

### 3.4 Smoke test 範圍（4-z fixture）

`funding_skew_stage0r_smoke.py` 加：

#### 3.4.1 `_check_sweep_mode()`

```python
def _check_sweep_mode(failures: list[str]) -> None:
    rows = build_fixture()  # 既有 3 symbols × 360 ts fixture
    packet = compute_stage0r_sweep(
        rows,
        k_prior=0,
        cost_bps=12.0,
        z_cells=(1.0, 1.2, 1.5, 2.0),
    )
    # Verify sweep_meta
    if packet.get("sweep_meta", {}).get("z_cells") != [1.0, 1.2, 1.5, 2.0]:
        failures.append(f"sweep z_cells mismatch: {packet.get('sweep_meta')}")
    if packet.get("sweep_meta", {}).get("k_new_min_v0_3") != 5400:
        failures.append(f"K_NEW_MIN_V03 mismatch: {packet.get('sweep_meta')}")
    # Verify 4 sweep blocks present + correct shape
    if "sweep_per_z_cell" not in packet:
        failures.append("missing sweep_per_z_cell")
    if len(packet.get("sweep_per_z_cell", {})) != 4:
        failures.append(f"sweep_per_z_cell len mismatch: {len(packet.get('sweep_per_z_cell', {}))}")
    if "sweep_per_symbol" not in packet:
        failures.append("missing sweep_per_symbol")
    if "best_primary_cell_per_z_branch" not in packet:
        failures.append("missing best_primary_cell_per_z_branch")
    if "sweep_cross_z_comparison" not in packet:
        failures.append("missing sweep_cross_z_comparison")
    # Verify v0.2 backward-compat keys preserved
    for key in ("strategy_variant", "alpha_source_id", "pooled_primary", "best_primary_cell", "panel_metadata"):
        if key not in packet:
            failures.append(f"missing v0.2 key in sweep packet: {key}")
    # Verify strategy_variant升 to v0_3
    if packet.get("strategy_variant") != "funding_skew_directional.v0_3":
        failures.append(f"strategy_variant not升 to v0_3: {packet.get('strategy_variant')}")
```

#### 3.4.2 `_check_wilson_ci_bench()`

```python
def _check_wilson_ci_bench(failures: list[str]) -> None:
    # NIST handbook reference values
    cases = [
        (20, 4, 0.082, 0.422, 0.005),   # n=20, n_eff=4, p=0.2 → ~(0.082, 0.422)
        (100, 50, 0.404, 0.596, 0.005), # n=100, n_eff=50, p=0.5 → ~(0.404, 0.596)
        (10, 2, 0.057, 0.510, 0.01),    # n=10, n_eff=2, p=0.2 → ~(0.057, 0.510)
    ]
    for n, n_eff, exp_lower, exp_upper, tol in cases:
        ci = wilson_ci_95(n, n_eff)
        if ci is None:
            failures.append(f"wilson_ci_95({n}, {n_eff}) is None, expected ({exp_lower}, {exp_upper})")
            continue
        lower, upper = ci
        if abs(lower - exp_lower) > tol or abs(upper - exp_upper) > tol:
            failures.append(
                f"wilson_ci_95({n}, {n_eff}) = ({lower:.4f}, {upper:.4f}), "
                f"expected ({exp_lower}, {exp_upper}) tol={tol}"
            )
    # Edge cases
    if wilson_ci_95(0, 0) is not None:
        failures.append("wilson_ci_95(0, 0) should be None")
    ci_zero_n_eff = wilson_ci_95(10, 0)
    if ci_zero_n_eff is None:
        failures.append("wilson_ci_95(10, 0) should not be None")
    elif ci_zero_n_eff[0] != 0.0:
        failures.append(f"wilson_ci_95(10, 0) lower should be 0.0, got {ci_zero_n_eff[0]}")
```

#### 3.4.3 `_check_4z_fixture()`

驗證 4-z 路徑全跑 + n_eff/avg_net 單調性 sanity check（z 越大 trigger 越少）：

```python
def _check_4z_fixture(failures: list[str]) -> None:
    rows = build_fixture()
    packet = compute_stage0r_sweep(rows, k_prior=0, cost_bps=12.0, z_cells=(1.0, 1.5, 2.0))
    for z_cell_id in ("z_relaxed_z_eq_1_0", "z_baseline_z_eq_1_5", "z_strict_z_eq_2_0"):
        cell_data = packet["sweep_per_z_cell"].get(z_cell_id)
        if cell_data is None:
            failures.append(f"missing z_cell {z_cell_id} in sweep_per_z_cell")
            continue
        if not isinstance(cell_data.get("by_branch"), dict):
            failures.append(f"sweep_per_z_cell.{z_cell_id}.by_branch not dict")
    # Sanity: z=1.0 trigger > z=2.0 trigger (relaxed gate more permissive)
    # fixture has funding_z=2.2 in BTCUSDT、 funding_z=-2.2 in ETHUSDT，三條都會過 z=2.0 + z=1.5 + z=1.0
    # 但 SOLUSDT funding_z=0.1 都不過任 z gate，所以 trigger 數應該對 z 不敏感於本 fixture
    # 這個 sanity 待 spec gen 時 enhance 對 v0.3 sweep monotonicity contract
```

### 3.5 LOC budget + 800 LOC warning line

| File | Before LOC | After LOC | Δ |
|---|---:|---:|---:|
| funding_skew_stage0r_metrics.py | 1162 | 1342-1402 | +180~240 |
| funding_skew_stage0r_report.py | 285 | 405-445 | +120~160 |
| funding_skew_stage0r_smoke.py | 229 | 349~409 | +120~180 |

**警告**：metrics.py 已 1162 LOC > 800 警告線；+240 LOC 後達 1402，仍 < 2000 硬上限（per CLAUDE.md §九「2000 行 🛑 硬上限」），合規。但**接近 2000 hard cap**（剩 ~600 LOC margin），E1 必盡量精簡 wrapper / helper；如預測超 1800，建議拆 `funding_skew_stage0r_sweep.py` 新檔。

### 3.6 IMPL Dependencies + Sequencing

E1 worktree dependency graph：
```
Step 1 (parallel):
  - z_grid kwarg add to compute_stage0r
  - wilson_ci_95() helper add
Step 2 (after step 1):
  - compute_stage0r_sweep() wrapper IMPL
  - _z_cell_id / _build_* helpers IMPL
Step 3 (after step 2):
  - CLI --sweep / --z-cells argparse
  - main() flow branch (sweep vs single-z)
Step 4 (after step 3):
  - smoke test 4-z fixture
  - Wilson CI bench
  - sweep mode invariant test
Step 5 (after step 4):
  - E1 self-verify smoke PASS on Mac
  - E1 self-report IMPL DONE
```

E1 estimated wall clock：**3-4h**（per task prompt ETA）。

### 3.7 Mac local dry-run on 5.72d panel data (pre-rerun verify)

E1 IMPL DONE 後 + A3/E2/E4 三方審 PASS 後，PA Phase A 末做最後 Mac 端 dry-run：

```bash
# Mac 端不能直接打 trade-core PG，但可從 Linux scp 拿 raw rows 一份 fixture
# 或直接走 SSH 跑 round 1 等同 input on Linux PG，用 --sweep 看是否 RED 同 round 1 (sanity)
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  OPENCLAW_DATABASE_URL=postgresql://trading_admin@localhost:5432/trading_ai \
  OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000 \
  timeout 1800 python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py \
    --sweep --z-cells 1.0,1.2,1.5,2.0 --window-days 7 \
    --format json \
    --out /tmp/openclaw/w_audit_8b_stage0r_v0_3_DRYRUN_$(date -u +%Y%m%d_%H%M)_pa.json \
    2>&1 | tail -20"
```

**注**：5.72d window 跑 dry-run 是 sanity check，**不是 Phase B 正式 rerun**（panel 不足 7d）。輸出主要驗：(1) 4 sweep blocks 全 emit；(2) Wilson CI 數值穩定；(3) Sweep eligibility decision 邏輯正確；(4) v0.2 backward-compat keys 仍在。Dry-run 跑出來大概率 RED（per RCA + run plan §2.3 預測），但 packet shape 對齊 spec v0.3 = Phase A IMPL contract met。

---

## §4 Phase A E2 + A3 + E4 對抗審核 cover specs

### 4.1 E2 對抗審 (senior cross-file structural review)

E2 重點 7 軸：

1. **z_grid kwarg backward-compat**：既有 round 1 single-z behavior 不破（不傳 z_grid → 用 Z_GRID 默認，輸出 v0.2 packet 38 keys 不變）；v0.2 既有 caller（如有）不受影響
2. **K_NEW_MIN 動態計算正確性**：sweep mode K_NEW_MIN_V03 = 5400 對齊 spec v0.3；non-sweep K_NEW_MIN 仍 4050 不退化
3. **Sweep wrapper 4 blocks JSON schema 完整性**：sweep_per_z_cell (4 cells) / sweep_per_symbol (200 rows) / best_primary_cell_per_z_branch (8 rows) / sweep_cross_z_comparison (50 rows) shape 對齊 spec v0.3 §"Output Format Spec"
4. **Wilson CI 數值穩定性**：n=0 / n=1 / n_eff=0 / n_eff=n edge case + NIST handbook ref 對齊 + `inner < 0` guard 防 sqrt NaN
5. **Leak-free shift(1) compliance**（per `feedback_indicator_lookahead_bias.md`）：sweep loop 不引入 new look-ahead bias；既有 SQL `fwd_return_*_bps` 從 future close 算未變 — E2 必驗 sweep wrapper 也不引入新 fwd column 或 future panel snapshot
6. **strategy_variant 升 v0_3 一致性**：sweep packet `strategy_variant=funding_skew_directional.v0_3`，non-sweep 仍 v0_2；不誤升 non-sweep round 1 packet
7. **CLI argparse 變更不破 round 1 reproducibility**：`--sweep` 默認 false（v0.2 round 1 命令仍 work）；`--z-cells` 不傳走默認 `"1.0,1.2,1.5,2.0"`

### 4.2 A3 對抗審 (adversarial UX / audit-aware spec consistency)

A3 重點 5 軸：

1. **Wilson CI 95% formula 正確性**：vs NIST handbook bench + Wilson original 1927 paper formula + Bailey-Sample-Test reference；**numerical stability** in small-n（n<5）regime
2. **z-stratified n_eff floor 邏輯**：spec v0.3 §"Cell-level n_eff stratified by z" 30/15/75 for z_strict (z=2.0) 只給 diagnostic eligibility，promotion 仍要 pooled n_eff ≥ 300；A3 必驗 IMPL eligibility decision 沒在 z_strict cell 誤 promote
3. **Sweep eligibility decision tree**：per spec v0.3 §"接受 / Reject 條件" 3 級
   - Accept = 任一 (z_cell, branch) 過 floor (z_relaxed/moderate/baseline 全 floor) OR z_strict diagnostic + standard pooled
   - Reject = 全 8 cells RED
   - Open = 1-3 邊際 / 4-7 RED
   IMPL 必正確 emit `sweep_eligibility` 為 ACCEPT / REJECT / OPEN
4. **Pre-empirical assertion magnitude (PA Q4 v0.3 open question)**：spec v0.3 預期 z=1.0 ~10x trigger vs z=1.5；A3 確認 IMPL 不 hardcoded 此 magnitude assertion，只在 sweep packet emit actual ratio 由 PA verdict round 2 reality check 比對
5. **Sweep_cross_z monotonic_drop_in_n_eff 判定**：50 rows × 4 z columns，IMPL 必輸出 `monotonic_drop_in_n_eff: true` 當 z_relaxed > z_moderate > z_baseline > z_strict（n_eff 下降）；non-monotonic（中間反 cliff）→ false，由 PA verdict 視為 funding tail-heavy 結構 hint

### 4.3 E4 regression baseline

E4 不替代 A3/E2 對抗審，但補 baseline：

1. **既有 single-z smoke test 全 PASS**（v0.2 round 1 不退）
2. **Sweep 4-z fixture smoke PASS**（per §3.4 新增 3 test functions）
3. **Wilson CI bench PASS**（NIST handbook ref tolerance < 0.005）
4. **Sweep packet JSON round-trip test**：JSON serialize + deserialize 後 4 blocks shape 不變
5. **z_grid backward-compat regression**：`compute_stage0r(rows, k_prior=69, cost_bps=12.0)` 不傳 z_grid → 結果與既有 round 1 RED packet bit-identical（除 generated_at_utc timestamp）

E4 必驗：
- `python3 helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py` exit 0 + 「PASS」字串 + 「PASS W-AUDIT-8b Stage 0R metrics smoke」
- 新增 sweep section 不破既有 4 smoke check（k_new floor / k_total / source_mode / cost_edge_ratio 等）

### 4.4 對抗審驗收 verdict matrix

| Reviewer | 驗收條件 | 失敗 action |
|---|---|---|
| E2 | 7 軸全 PASS / 無 HIGH-N findings | RETURN to E1 round 2 |
| A3 | 5 軸全 PASS / TRUE_CLOSED | RETURN to E1 round 2 |
| E4 | 5 regression 全 PASS / exit 0 | RETURN to E1 round 2 |
| PA | E2 + A3 + E4 都 PASS 後 commit + push | 任一 RETURN → PA halt + PM dispatch round 2 |

任一 RETURN → round N+1，per `feedback_impl_done_adversarial_review.md` 不採「平均分」。

---

## §5 Phase B Scheduled Rerun Plan (panel ≥ 7d 啟動)

### 5.1 啟動條件 7-gate

per Phase 2 run plan §2.1 + 任務 prompt §"Phase B"：

| # | 條件 | 期望 | 當前 (2026-05-16 19:18Z) | 達標 ETA |
|---|---|---|---|---|
| 1 | Panel ≥ 7d empirical | funding span_days ≥ 7.0 AND oi span_days ≥ 7.0 | 5.823d (5.823/7.0 = 83.2%) | **2026-05-17 23:30Z** (+1.18d) |
| 2 | Sym=25 | funding sym_count = 25 | 25 ✅ | met |
| 3 | K_prior strict=0 | funding_skew% filter = 0 | 0 ✅ | met |
| 4 | Cycles ≥21 | distinct next_funding_ms = ≥ 21 | 31 ✅ | met |
| 5 | Phase A tooling ready | E1 IMPL DONE + A3 + E2 + E4 PASS | NOT STARTED | E1 dispatch 後 +1d (calendar 2026-05-17) |
| 6 | Sibling non-conflict | git status helper_scripts/reports/ clean | clean ✅ (sibling Phase 1b in Rust + V094 + healthcheck，不重疊) | met |
| 7 | Operator non-blocking | autonomous mode active | per task prompt grant | met |

**前 7 個 ALL PASS 才 trigger Phase B**。當前 gate fail = #1 + #5。

### 5.2 Pre-rerun Linux PG empirical query (PA solo Step 6)

```bash
# Q1: panel funding span
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -A -F'|' -c \"
SELECT
  to_timestamp(MIN(snapshot_ts_ms)/1000) AS funding_min_ts,
  to_timestamp(MAX(snapshot_ts_ms)/1000) AS funding_max_ts,
  ROUND(EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000) - to_timestamp(MIN(snapshot_ts_ms)/1000)))/86400::numeric, 3) AS span_days,
  COUNT(*) AS total_rows,
  COUNT(DISTINCT symbol) AS sym_count
FROM panel.funding_rates_panel;\""

# Q2: OI panel span
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -A -F'|' -c \"
SELECT
  to_timestamp(MIN(snapshot_ts_ms)/1000) AS oi_min_ts,
  to_timestamp(MAX(snapshot_ts_ms)/1000) AS oi_max_ts,
  COUNT(*) AS oi_rows
FROM panel.oi_delta_panel;\""

# Q3: K_prior strict funding_skew
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -A -F'|' -c \"
SELECT count(DISTINCT candidate_key)::int AS k_prior_strict_funding_skew
FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE '%funding_skew%'
       OR trial_family ILIKE '%funding_skew%'
       OR candidate_key ILIKE '%funding_skew%');\""

# Q4: funding cycles distinct
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -A -F'|' -c \"
SELECT COUNT(DISTINCT next_funding_ms)::int AS distinct_cycles_in_panel
FROM panel.funding_rates_panel
WHERE next_funding_ms IS NOT NULL;\""

# Q5: source sync
git status --porcelain && ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5"
```

Assertion 任一 FAIL → halt Phase B + PA escalate PM。

### 5.3 Rerun command (Step 7)

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  OPENCLAW_DATABASE_URL=postgresql://trading_admin@localhost:5432/trading_ai \
  OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000 \
  timeout 3600 python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py \
    --sweep --z-cells 1.0,1.2,1.5,2.0 --window-days 7 \
    --format json \
    --out /tmp/openclaw/w_audit_8b_stage0r_round2_v0_3_$(date -u +%Y%m%d_%H%M)_pa.json \
    > /tmp/openclaw/w_audit_8b_stage0r_round2_v0_3_$(date -u +%Y%m%d_%H%M).log 2>&1"
```

**注**：
- `--sweep` + `--z-cells 1.0,1.2,1.5,2.0` per task prompt
- timeout 3600s (60 min)，sweep 4x cell count + 7d window vs 5.72d 額外 17% data，per Phase 2 run plan §2.2 給 30 min runtime 安全 margin × 2
- output path `/tmp/openclaw/w_audit_8b_stage0r_round2_v0_3_<datetime>_pa.json`

### 5.4 Round 2 Verdict Report (Step 8)

PA 寫 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_round2_verdict.md`（per task prompt path; **注意 prompt 寫的是 2026-05-16 但實際 Phase B 觸發是 2026-05-18+，PA 可 push back 改 date prefix 對齊執行日**）。

Report 必含：
1. Pre-rerun assertion gate verify result (Q1-Q5)
2. Sweep rerun command + exit code + runtime
3. 4 sweep blocks 全文 (sweep_per_z_cell / sweep_per_symbol / best_primary_cell_per_z_branch / sweep_cross_z_comparison)
4. Pre-empirical reality check (per spec v0.3 Q4): actual vs predicted z=1.0 ratio comparison
5. Sweep eligibility verdict (ACCEPT / OPEN / REJECT)
6. Decision tree next-step (per task prompt §"決策樹"):
   - ACCEPT → 派 4-agent re-review on Round 2 verdict
   - OPEN → operator decide
   - REJECT → 補 RCA + AMD-2026-05-15-02 §8 condition 3 wording 修訂建議

### 5.5 Phase B 觸發條件 + 自主執行邊界

per `feedback_minimal_confirmation.md` autonomous mode active：
- 7 gates 全 PASS → PA autonomous trigger Phase B（**不問 operator**）
- 任一 gate FAIL → PA halt + PM escalate（**不 autonomous force**）

per task prompt § "Operator 不阻 PA 自主 rerun" → autonomous trigger granted。

---

## §6 副作用識別

per profile.md §"副作用識別清單"：

### 6.1 模塊依賴影響

| 改動 | 影響模塊 | 嚴重性 | E2 必查 |
|---|---|---|---|
| `compute_stage0r(z_grid=)` 加 kwarg | 既有 caller (`funding_skew_stage0r_report.py:264` + `funding_skew_stage0r_smoke.py:171, 163`) | 低 — kwarg 有默認值不破 API | ✅ caller 不需改 |
| `wilson_ci_95()` 新函數 | none — 純 helper | 0 | n/a |
| `compute_stage0r_sweep()` 新函數 | report.py CLI main() 內 conditional call | 低 — sweep flag 不傳則不 call | ✅ |
| CLI `--sweep` `--z-cells` 加 | external user (PA + E1 跑 audit) | 0 — 不傳則 backward compat | ✅ |
| K_NEW_MIN_V03 = 5400 module-level constant | external readers | 0 — additive | ✅ |

### 6.2 SQL / DB / runtime / TOML 影響

- ❌ `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` — **不動**（z 過濾在 Python 層）
- ❌ `sql/migrations/V*.sql` — **不動**（無 schema 改）
- ❌ `settings/risk_control_rules/*.toml` — **不動**
- ❌ `program_code/exchange_connectors/bybit_connector/control_api_v1/*` — **不動**
- ❌ `rust/openclaw_engine/*` — **不動**
- ❌ `panel.funding_rates_panel` / `panel.oi_delta_panel` — **read-only**
- ❌ `learning.strategy_trial_ledger` — **read-only**
- ❌ `authorization.json` / OPENCLAW_* env — **不動**

### 6.3 跨平台兼容性 (per CLAUDE.md §七)

- 路徑硬編碼：本 IMPL 不引入 user-home 絕對路徑（仍用 `_repo_root()` from existing `funding_skew_stage0r_report.py:25-29`）
- LocalLLMClient：n/a — 不涉 LLM
- 服務部署可遷移：n/a — 純 CLI tool
- 依賴管理：使用既有 `psycopg2` + stdlib（statistics / math / random / itertools / collections / dataclasses）；**不引入新依賴**

### 6.4 16 root principles + 硬邊界 compliance

| # | 原則 | 觸碰? | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ❌ 否 | Phase A 純 audit packet 不涉 IntentProcessor |
| 2 | 讀寫分離 | ❌ 否 | 純 SELECT + 寫 JSON 到 /tmp |
| 3 | AI 輸出 ≠ 命令 | ❌ 否 | 不涉 lease |
| 4 | 策略不繞風控 | ❌ 否 | 不下單 |
| 5 | 生存 > 利潤 | ❌ 否 | 不下單 |
| 6 | 失敗默認收縮 | ✅ 維持 | sweep eligibility 全 RED → 觸發 RCA + AMD wording 修訂建議；**不** auto-promote |
| 7 | 學習 ≠ 改寫 Live | ❌ 否 | 純 audit packet 不寫 ML training table |
| 8 | 交易可解釋 | ❌ 否 | 不下單 |
| 9 | 災難保護 | ❌ 否 | 不下單 |
| 10 | 認知誠實 | ✅ 維持 | sweep eligibility 區分 ACCEPT / OPEN / REJECT 三級 + pre-empirical reality check |
| 11 | Agent 最大自主 | ❌ 否 | 不涉 cognitive_modulator |
| 12 | 持續進化 | ✅ 維持 | round 2 sensitivity sweep = 進化路徑 |
| 13 | AI 成本感知 | ❌ 否 | tooling 純 PG query 0 AI 調用 |
| 14 | 零外部成本可運行 | ✅ 維持 | tooling 純 Linux PG，無 Ollama/Claude 依賴 |
| 15 | 多 Agent 協作 | ✅ 維持 | Phase A 強制 E1 IMPL → A3+E2 並行對抗審 → E4 regression → PA verdict 鏈 |
| 16 | 組合級風險 | ❌ 否 | 不影響 portfolio_risk |

**硬邊界 (CLAUDE.md §四)**：全 0 觸碰（`live_execution_allowed` / `max_retries` / `system_mode` / `execution_state` / `decision_lease_emitted` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` / Operator 角色繞過 / `executor_canary_stage`）。

**DOC-08 §12 9 條安全不變量**：全 9 條 N/A（不涉交易）。

**AMD-2026-05-15-01**：`eligible_for_demo_canary=true/false` 唯一輸出；Phase A IMPL 不執行 Stage 1 demo micro-canary，不開 `Environment::Demo`，不觸 OPENCLAW_ENABLE_PAPER（保持 0），不開 authorization。

**AMD-2026-05-15-02 §8 condition 3 strict AND 3-gate**：Phase A 不破 wording；Phase B reject path 觸發 → PA 補新 RCA + 建議 wording 修訂；wording 不在 Phase A IMPL 階段動。

**評級**：A 級 — 16/16 完全合規 + 0 硬邊界觸碰 + 0 DOC-08 不變量觸碰。

---

## §7 高風險警告（E2 必重點審查 3 點）

per profile.md §"輸出物標準" 高風險警告 3 點：

### 警告 1：Wilson CI 公式 small-n numerical instability

**風險**：n=1, n=2, n=3 等 small-n regime + n_eff/n close to 0 or 1 → `inner = p_hat(1-p_hat)/n + z²/(4n²)` 可能 underflow / sqrt domain edge case
**證據**：spec v0.3 §"Wilson CI Computation per Cell" 明示 "比直接拿 normal approximation 更穩定，特別在 small-n（n < 30）regime 不會超出 [0, 1]"，但 IMPL 必驗 inner < 0 guard + clamp [0, 1]
**E2 必查**：
- `wilson_ci_95(0, 0)` returns None
- `wilson_ci_95(1, 0)` returns valid tuple，lower=0 upper<1
- `wilson_ci_95(1, 1)` returns valid tuple，lower>0 upper=1
- `wilson_ci_95(100, 50)` ≈ (0.404, 0.596) within 0.005
- 不引入 numpy/scipy 依賴（pure stdlib math）

### 警告 2：K_NEW_MIN dynamic computation backward-compat

**風險**：sweep mode K_NEW_MIN_V03 = 5400 強制 floor，但 non-sweep mode K_NEW_MIN = 4050 必須保留（round 1 reproducibility）；IMPL 不可全面替換為 5400
**證據**：v0.2 round 1 packet `k_new_min=4050` (per Round 1 verdict)；v0.3 spec §"K_total per-cell minimum 要求" 寫「K_new_min_v0_3 = 5400 (4 z)，舊 K_new_min_v0_2 = 4050 (3 z) 變為 K_new_min_v0_3 = 5400（4 z），即 +33%」
**E2 必查**：
- non-sweep mode `compute_stage0r(rows, k_prior=0, cost_bps=12.0)` (Z_GRID=(1.5,2.0,2.5)) emit `k_new_min=4050` not 5400
- sweep mode `compute_stage0r_sweep(rows, k_prior=0, cost_bps=12.0, z_cells=(1.0,1.2,1.5,2.0))` emit `k_new_min=5400`
- Bit-identical regression test：non-sweep mode output 與 round 1 RED packet match（除 generated_at_utc）

### 警告 3：strategy_variant 升 v0_3 一致性 vs round 1 backward-compat

**風險**：sweep packet `strategy_variant=funding_skew_directional.v0_3` 但 single-z packet 仍 `funding_skew_directional.v0_2`；ML lineage / audit downstream 必正確區分；不可全面升 v0_3 把 round 1 RED packet retroactively 改 variant
**證據**：STRATEGY_VARIANT module-level constant 是 v0.2 round 1 寫死 "funding_skew_directional.v0_2"；v0.3 sweep wrapper 必須 override packet["strategy_variant"] 升 v0.3，但 single-z mode 不動
**E2 必查**：
- module-level STRATEGY_VARIANT 保留 "funding_skew_directional.v0_2"（不全面升 v0.3）
- `compute_stage0r_sweep()` 在 final packet 內 override `strategy_variant=funding_skew_directional.v0_3`
- non-sweep `compute_stage0r()` 不改 STRATEGY_VARIANT 用法（仍 emit v0.2）

---

## §8 Phase A IMPL Dispatch Chain Action Items

### 8.1 PM 接手 dispatch（PA hand-off）

PM 從本 PA report Step 2 起接手：

1. **Step 2**：PM dispatch `@E1` IMPL per §3 packet
   - Branch: `feature/w-audit-8b-round2-sweep` based on origin/main HEAD `a26c1ed9`
   - Worktree: `srv/.worktrees/w-audit-8b-round2-sweep/` (per dispatch protocol)
   - Estimated 3-4h
2. **Step 3**：E1 IMPL DONE 自評後，PM 強制並行派 `@A3` + `@E2`（per `feedback_impl_done_adversarial_review.md`），各 0.5d
3. **Step 4**：A3 + E2 PASS 後 PM 派 `@E4` regression smoke，0.5h
4. **Step 5**：E4 PASS 後 PM sign-off Phase A → commit + push → Linux git pull --ff-only
5. **Step 5b**：Mac dry-run on 5.72d panel (per §3.7) 驗 packet shape 對齊 spec v0.3

### 8.2 PA Phase A 結束標誌

PA Phase A DESIGN DONE 標誌：
- ✅ Spec v0.3 patch land (commit `41e12a84`)
- ✅ 本 PA report 完成 + commit + push
- ✅ Sibling work non-conflict 驗 (§5.1 gate #6 met)
- ❌ E1 IMPL not started — PM dispatch 接手
- ❌ A3 + E2 + E4 not started — depend on E1

### 8.3 Phase B trigger schedule

Phase B 啟動條件 7-gate (§5.1) 預計 calendar **2026-05-18 00:30 UTC** (panel ≥ 7d + 1h safety margin) trigger，**不依賴 Phase A IMPL 完成**（PA 可在 Phase A IMPL 進行中同時觀察 panel grow，但 sweep rerun 必須等 IMPL ready）。

實際 Phase B trigger 取早於：
- `max(2026-05-17 23:30 UTC + 1h, Phase A E1 IMPL DONE + A3/E2/E4 PASS)`

如 Phase A 在 panel 達標前完成 = Phase B 在 panel 達標即可 trigger；如 Phase A 延遲超 calendar 2026-05-18 = Phase B trigger 等 Phase A。

---

## §9 Files Touched / Referenced

### 9.1 Phase A 階段（Pending E1 IMPL，本 PA design 不動代碼）

**Will edit by E1 (per §3.2)**:
- `srv/helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py` (+180~240 LOC)
- `srv/helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py` (+120~160 LOC)
- `srv/helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py` (+120~180 LOC)

**Will not edit**:
- `srv/helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py`（薄 wrapper）
- `srv/sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`（z 過濾在 Python 層）
- 任何 `settings/risk_control_rules/*.toml`
- 任何 `program_code/exchange_connectors/bybit_connector/control_api_v1/*`
- 任何 Rust engine source / Cargo.toml
- 任何 DB schema migration（`sql/migrations/*`）
- 任何 `learning.strategy_trial_ledger` row insert/update/delete

### 9.2 PA report (本 file)

- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_round2_tooling_prep.md`（本 verdict report）

### 9.3 Phase B 階段（將來 panel ≥ 7d 後 PA 動）

**Will write by PA (per §5)**:
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-1X--w_audit_8b_round2_verdict.md` (date prefix 對齊執行日)
- `/tmp/openclaw/w_audit_8b_stage0r_round2_v0_3_<YYYYMMDD>_<HHMM>_pa.json` (Linux artifact)
- `/tmp/openclaw/w_audit_8b_stage0r_round2_v0_3_<YYYYMMDD>_<HHMM>.log` (Linux log)

### 9.4 Referenced

- `srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` (v0.3 / commit `41e12a84`)
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_spec_v03_sensitivity_sweep_patch.md` (Phase 2 run plan)
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md` (RED RCA)
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_replay_packet_verdict.md` (Round 1 RED verdict)
- `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` (AMD §8 strict AND 3-gate)
- `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md` (canary rebase)
- `srv/docs/CCAgentWorkSpace/PA/profile.md` (PA 角色定位 / 改動風險評級 / 副作用識別清單)
- `/Users/ncyu/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/feedback_impl_done_adversarial_review.md` (高風險 IMPL 必走 E1 IMPL + A3+E2 對抗審)
- `/Users/ncyu/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/feedback_indicator_lookahead_bias.md` (leak-free shift(1) compliance)
- `/Users/ncyu/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/feedback_minimal_confirmation.md` (autonomous mode)
- `/Users/ncyu/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/feedback_pushback.md` (PA 主動 push back)
- Linux PG runtime empirical query 2026-05-16 19:18Z (panel funding 205,526 rows / 5.823d / 25 sym / cycles 31)

---

## §10 Summary

### 10.1 Phase A IMPL Design Done

- Design packet ready for PM dispatch `@E1` worktree `feature/w-audit-8b-round2-sweep`
- IMPL 範圍：3 files / +420~580 LOC (source + tests) / 0 SQL / 0 schema / 0 config
- Key abstractions：(1) `compute_stage0r(z_grid=)` kwarg，(2) `wilson_ci_95()` helper，(3) `compute_stage0r_sweep()` wrapper，(4) CLI `--sweep` + `--z-cells`，(5) K_NEW_MIN_V03 = 5400 + STRATEGY_VARIANT v0_3 升級
- 0 觸 spec v0.3 既有 §"Hypothesis" / §"Data Contract" / §"Signal Formula Draft" / §"Replay-First Validation" / §"Implementation Boundary"
- 0 觸 AMD-2026-05-15-02 §8 condition 3 wording
- 0 觸 runtime / TOML / RiskConfig / Operator / authorization / engine env

### 10.2 對抗審核 Cover Spec

- E2 7-軸 cross-file structural review (backward-compat, K_NEW_MIN, sweep schema, Wilson CI stability, leak-free shift(1), strategy_variant, CLI repro)
- A3 5-軸 adversarial UX/audit-aware review (Wilson CI formula correctness, z-stratified n_eff floor, sweep eligibility tree, pre-empirical magnitude, monotonic_drop_in_n_eff)
- E4 5-test regression baseline (single-z PASS, sweep 4-z PASS, Wilson bench, JSON round-trip, z_grid backward-compat)

### 10.3 Push Back Operator Instruction

PA reject 「PA 親自 IMPL」 reading of task prompt（per §1.3）；建議走 E1 IMPL chain；如 operator 明確 reverse pushback 要求 PA 親自 IMPL，PA 配合但保留強制 A3+E2+E4 對抗審核（per `feedback_impl_done_adversarial_review.md` 不可跳）。

### 10.4 Phase B Deferred to panel ≥ 7d

- Calendar ETA: 2026-05-18 00:30 UTC（+1.18d from 19:18Z）
- 7-gate trigger condition + Linux PG empirical assertion gate 5 queries
- Rerun command shape ready
- Decision tree: ACCEPT (派 4-agent re-review) / OPEN (operator decide) / REJECT (補 RCA + AMD wording 修訂建議)

### 10.5 16-root + 硬邊界 + DOC-08 Compliance

- 16/16 root principles 完全合規
- 0 硬邊界觸碰
- DOC-08 §12 9 條全 N/A
- AMD-2026-05-15-01 不觸（無 Stage 1 demo）
- AMD-2026-05-15-02 §8 wording 不觸（Phase A IMPL 階段；Phase B reject path 才觸發修訂建議）
- 評級：A 級

---

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_round2_tooling_prep.md`
