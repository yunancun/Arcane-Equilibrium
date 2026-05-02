# LG5-W3-FUP-2 Fix 2 — R-meta Window 7d → 3d Amendment RFC

**Date**: 2026-05-02
**Owner**: PA
**Status**: Design only (no code, no commit, no schema change)
**Spec parent**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md` (v2 frozen)
**Spec sibling (Fix 1)**: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-02--lg5_w3_fup_2_fix_1.md` (cron + `[43]`)
**Repo**: `/Users/ncyu/Projects/TradeBot/srv/`

> **本文件是 RFC v2 的 follow-up amendment**，**不修改 v2 spec 本體**。任何 amendment 與 v2 衝突時，amendment 優先（v2 spec 文中 `_DEMO_BASELINE_WINDOW_DAYS=7` 是「single window」，本 amendment 將之拆為兩個獨立常數，舊的「7d」語意對 cost baseline / realized window 維持，新的「3d」語意僅作用於 R-meta gate）。

---

## §1. Problem statement

### 1.1 v2 RFC 現況

LG-5 RFC v2 §2.1 producer payload 由 `mlde_demo_applier._build_live_candidate_payload()` 統一建構，包含：

- `demo_cost_baseline`（7d，鏡 `[33]` `[40]` healthcheck 窗口）
- `demo_realized_window`（7d）
- `demo_attribution_chain_ratio_by_strategy`（per-strategy 5-key dict，**目前 7d**）
- `demo_sample_count_strategy_cell`（7d）

R-meta gate（v2 §3）讀 `demo_attribution_chain_ratio_by_strategy[candidate_strategy]`：
- ratio < 0.50 → `defer reject_attribution_chain_too_broken`
- candidate strategy 不在 dict → `defer defer_attribution_chain_strategy_unknown`

### 1.2 MIT FUP-2 揭露的 root cause

MIT FUP-2 diagnosis（2026-05-02）發現「[42b] live_candidate_attribution_drift FAIL / WARN」並非全部由生產 attribution chain 健康度真實退化造成，而是**歷史殘留 + 修復前 bug 期樣本**仍佔 7d 窗口大宗：

| 區段 | 觀察 ratio | 解讀 |
|---|---|---|
| 4/24 – 4/28 修復前 | ~100% bug 期 | `attribution_chain_ok` 5-condition view 中 signal_id 結構 bug；ratio 數值假高 / 假低取決於哪個 sub-condition 先 NULL |
| 4/29 修復 ship | commits `ece31b6` + `45bbe4d` + `5895579` | 結構 bug 修好 |
| 4/30 ~ now (post-修復) | grid 39.6% / ma 44.8% | 真實當前能達標的天花板，仍受 `label_net_edge_bps NULL`（Fix 1 cron 補）影響 |
| 7d 窗口（含舊 bug 期） | grid 14.96% / ma ~15% | **7d 含 4/24-28 bug 期殘留**，被 over-penalized |

**結論**：7d window 對齊 `[33]` `[40]` 對 *cost baseline* 是合理的（cost baseline 需要大樣本 + 統計顯著性），但對 R-meta attribution gate 是**錯的對齊對象** —— R-meta 量的是「attribution chain 寫入面健康度」，這個語意只對「修復後時段」有意義；把 4/24-28 bug 期 sample 算進去 = 用已修 bug 不必要懲罰當前 promotion candidate。

### 1.3 Fix 2 設計目標

縮 R-meta gate 的 window 從 7d → 3d，對齊「已修 bug 後」純後時段（4/29 修復 + 一日 settle = 4/30 起，到 now = 約 3d），讓 R-meta 反映**當前 attribution chain 真實品質**，不被歷史 bug 殘留拖死。

cost baseline / realized window / sample count 維持 7d（保大樣本 + 統計顯著性 + 對齊 `[33]` / `[40]`）。

**不動**：R3 PSR window（v2 §11 Q3 拍板 7d/14d）、R5 cost_edge_ratio 公式（v2 §11 Q5 拍板 demo gross 公式）。

---

## §2. Design proposal

### 2.1 常數拆分

`mlde_demo_applier._DEMO_BASELINE_WINDOW_DAYS = 7` 拆為兩個獨立常數：

```python
# 既有（語意：cost baseline + realized window + sample count；對齊 [33]/[40]）
_BASELINE_WINDOW_DAYS: int = 7  # 重命名自 _DEMO_BASELINE_WINDOW_DAYS（grep-stable rename）

# 新增（語意：R-meta attribution gate 專用；對齊「已修 bug 後」健康度）
_R_META_WINDOW_DAYS: int = 3
```

**Rename 注意事項**：
- 既有 `_DEMO_BASELINE_WINDOW_DAYS` 在 `mlde_demo_applier.py` 共出現 6 處（line 70 定義 + 5 處呼叫）；test 檔（`test_mlde_demo_applier.py`）不直接 import 此常數（只 import 函數），所以 rename 不破測試 import。
- 為降低 review noise + grep 穩定性，**建議**保留 `_DEMO_BASELINE_WINDOW_DAYS` 名稱不改（語意不變 = 仍 7d），純新增 `_R_META_WINDOW_DAYS = 3` 常數。**Decision**：採此保守方案（見 §10 Open question 1）。

### 2.2 R-meta vs cost baseline window 拆分理由

| 用途 | Window | 理由 |
|---|---|---|
| cost baseline (`maker_fill_rate_7d`, `avg_realized_fee_bps_7d`) | **7d** | 對齊 `[33]` healthcheck；fee/maker fill 變化慢，需大樣本 |
| realized net_bps / slippage | **7d** | 對齊 `[40]` healthcheck；net edge 統計顯著性需 ≥7d |
| R3 PSR window | **7d/14d** | v2 §11 Q3 拍板，crypto fat-tail n≥100；**Fix 2 不動** |
| R5 cost_edge_ratio | demo gross 公式（無 explicit window；用 cost baseline 7d 數值） | v2 §11 Q5 拍板；**Fix 2 不動** |
| R-meta attribution gate | **3d** ← Fix 2 改 | 量「已修 bug 後 attribution chain 健康度」；7d 含 4/24-28 bug 期 sample → over-penalize |
| `[42b]` healthcheck observability | 見 §5（拍板：保 7d + 加 [42c] 3d 雙窗） | 7d 是 long-window observability，3d 對齊 R-meta gate 行為 |

### 2.3 為何 R-meta 對齊「healthcheck cycle 後」而非「healthcheck window 本身」

`[42b]` healthcheck 的目的是 **drift detection**（探查 attribution chain 是否突然壞掉）；window 大有助於降噪（避免單 hour 抖動觸發 FAIL）。

R-meta gate 的目的是 **promotion gate**（量 candidate 進入 live 時 attribution chain 是否「現在」健康）；window 應對齊「已修 bug 後」的純後時段，確保 gate 反映**當下**信號品質。

兩者語意不同，window 不該強制相同。

### 2.4 Backward compat 必須保留 v2 schema_version

producer payload 仍稱 `demo_attribution_chain_ratio_by_strategy`（**不重命名**），語意從 v1（7d）變成 v1.1（3d）；**新增 sub-key** `demo_attribution_window_days: 3` 明示 window 給 consumer / audit。

`_LIVE_CANDIDATE_EVAL_SCHEMA_VERSION` **不 bump**（仍 `live_candidate_eval_v1`）—— 純 window 數值縮放不算 schema break；既有 27 pending candidates 不會被 reject_schema_unknown。

---

## §3. Producer side change

### 3.1 `_compute_attribution_chain_ratio_by_strategy(cur)` 修改

**File**: `program_code/ml_training/mlde_demo_applier.py:882-936`

```python
def _compute_attribution_chain_ratio_by_strategy(cur: Any) -> dict[str, float]:
    """Compute per-strategy 3d attribution_chain_ok ratio.

    LG-5 RFC v2 §2.1 + MIT MF-M2 + Fix 2 amendment (2026-05-02):
    R-meta window aligned to "post-bug-fix" 3d to avoid 7d window
    over-penalizing candidates with 4/24-28 bug-era residual samples.

    Cost baseline / realized window 仍 7d；本 helper 是 R-meta 唯一輸入源。
    """
    ratios: dict[str, float] = {key: 0.0 for key in _ATTRIBUTION_STRATEGY_KEYS}

    # ... view existence check 不變 ...

    try:
        cur.execute(
            """
            SELECT
                strategy_name,
                count(*)::int AS total,
                count(*) FILTER (WHERE attribution_chain_ok)::int AS ok_count
              FROM learning.mlde_edge_training_rows
             WHERE ts > now() - (%s::int || ' days')::interval  -- ← 改 _R_META_WINDOW_DAYS
               AND engine_mode IN ('demo', 'live_demo')
               AND coalesce(strategy_name, '') = ANY(%s)
             GROUP BY strategy_name
            """,
            (_R_META_WINDOW_DAYS, list(_ATTRIBUTION_STRATEGY_KEYS)),  # ← 改常數
        )
        rows = cur.fetchall() or []
    # ... rest unchanged ...
```

**Diff scope**: 1 SQL parameter binding 改動 + docstring 更新 + 新增常數 `_R_META_WINDOW_DAYS = 3`（line 70 區）。LOC delta ≈ +5 / -1 = +4 net。

### 3.2 `_build_live_candidate_payload()` payload 增 window_days 子鍵

**File**: `program_code/ml_training/mlde_demo_applier.py:988-1063`

```python
return {
    "policy": "live_governed_promotion_candidate",
    "schema_version": _LIVE_CANDIDATE_EVAL_SCHEMA_VERSION,  # 不 bump，仍 v1
    "source_demo_recommendation_id": source_row.get("id"),
    "source_demo_application_id": application_id,
    "application_type": application_type,
    "patch": patch,
    "requires": ["GovernanceHub", "DecisionLease", "live_gates"],
    "demo_cost_baseline": demo_cost_baseline,
    "demo_realized_window": demo_realized_window,
    "demo_attribution_chain_ratio_by_strategy": attribution_by_strategy,
    "demo_attribution_window_days": _R_META_WINDOW_DAYS,   # ← Fix 2 NEW (=3)
    "demo_sample_count_strategy_cell": sample_count_strategy_cell,
}
```

**Diff scope**: +1 dict entry。LOC delta = +1。

### 3.3 不動的 producer surface

- `_compute_demo_cost_baseline(cur)` —— 仍用 `_DEMO_BASELINE_WINDOW_DAYS = 7`
- `_compute_demo_realized_window(cur, strategy_name)` —— 仍 7d
- `_compute_demo_sample_count_strategy_cell(cur, strategy_name)` —— 仍 7d（attribution-okay sample count；R3 PSR 用，**不**用 R-meta window）
- `_LIVE_CANDIDATE_EVAL_SCHEMA_VERSION = "live_candidate_eval_v1"` —— 不 bump

**重點**：Fix 2 只改一個 SQL window（attribution per-strategy ratio），其餘 4 個 baseline/window producer 全部不動。

---

## §4. Consumer side change

### 4.1 `evaluate_r_meta()` evaluator 改動

**File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py:1050-1064`

**直接讀 payload ratio**，邏輯本身**0 改動**：

```python
def evaluate_r_meta(
    candidate_strategy: str,
    attribution_dict: dict[str, float],
) -> tuple[Literal["pass", "fail", "unknown"], str, Optional[float]]:
    # ... unchanged: dict lookup + R_META_RATIO_FLOOR (=0.50) compare
```

R_META_RATIO_FLOOR 仍 0.50；只是 producer 餵入的 ratio 現在來自 3d 而非 7d。

### 4.2 audit row 加 window_days 欄位

**File**: `governance_hub_live_candidate_review.py` `_make_verdict()` payload_snapshot

R-meta defer / pass 的 audit row payload_snapshot 多 echo `demo_attribution_window_days` 一欄，例：

```python
verdict = _make_verdict(
    "defer", "reject_attribution_chain_too_broken",
    rule_failures=["R-meta"],
    expected_net_bps_demo=expected_net_bps_demo,
    payload_snapshot={
        "r_meta_msg": r_meta_msg,
        "demo_attribution_window_days": payload.get("demo_attribution_window_days", 7),  # default 7 = v1 backward compat
    },
    decided_by=decided_by_full,
)
```

**為何重要**：IMPL-5 7d retro 校準時要能區分「Fix 2 之前 ratio」（v1 7d）vs「Fix 2 之後 ratio」（v1.1 3d），否則回測 R-meta gate 行為會被混淆。

V035 audit row 已含 payload JSONB（v2 §13 schema），此改動只是把新 sub-key 寫進 payload_snapshot dict，**無 schema migration**。

### 4.3 不動的 consumer surface

- `R_META_RATIO_FLOOR = 0.50` —— 維持
- `EXPECTED_SCHEMA_VERSION = "live_candidate_eval_v1"` —— 維持
- `_fetch_strategy_return_distribution(strategy, window_days=7)` —— R3 PSR 用，**不動**
- R5 cost_edge_ratio 公式（demo gross） —— **不動**
- 所有 R1/R2/R3/R4/R5/R6 evaluator —— **不動**

---

## §5. Healthcheck change — 拍板：[42b] 維持 7d + 新增 [42c] 3d

### 5.1 三個方案分析

| 方案 | 描述 | 優點 | 缺點 |
|---|---|---|---|
| A. 改 `[42b]` 7d → 3d | 對齊 R-meta gate window | 一致；observation 直接反映 gate 行為 | 失去 7d long-window drift detection；4/24-28 bug 期殘留淡出後 7d 視角 sample 才足；MIT 已 ship 的 `[42b]` PASS/WARN/FAIL 三段閾值對 7d sample 校準 |
| B. 維持 `[42b]` 7d + 新 `[42c]` 3d | 雙窗 observability | 7d long-window drift + 3d gate-aligned；retro 校準 + IMPL-5 雙 source | +1 healthcheck 維護成本；wrapper SUMMARY 多一行 |
| C. 維持 `[42b]` 7d only，不加 3d | 最小改動 | 0 healthcheck change | observability gap：operator 看 `[42b]` PASS 但 R-meta gate 因 3d ratio 低而 defer 全部 candidates → 認知斷層 |

### 5.2 PA 拍板：方案 B

**`[42b]` 維持 7d**（long-window drift sentinel + first-deploy grace + RFC v2 §6 IMPL-3 三段閾值不動）。

**新增 `[42c]` 3d** = R-meta gate window 對齊版本，PASS/WARN/FAIL 同樣三段（0.50 / 0.30 / 0.10）但 SQL window 改 3d；msg 明示「3d window aligned to R-meta gate」。

**理由**：
1. **observability completeness**：operator 從 `[42b]` 看「長期趨勢」，從 `[42c]` 看「當下 gate 行為」；兩者背離（e.g. `[42b]` PASS 但 `[42c]` WARN）= 4/24-28 bug 期殘留尚未淡出，operator 知道為什麼 R-meta defer。
2. **retro 校準**：IMPL-5 7d 校準需要對比兩 window 的 ratio 演化，雙 healthcheck 雙 source。
3. **零 runtime risk**：`[42c]` 純 read-only SQL，與 `[42b]` 互不干擾。
4. **wrapper SUMMARY 影響極小**：current WARN/FAIL 列表已含 `[33]`/`[38]`/`[40]`/`[42b]` 等，多一個 `[42c]` 仍可 grep。

`[42c]` 預設 PASS = 表示 R-meta gate 不會 defer 該 strategy；WARN = R-meta 對該 strategy 會 defer（此狀態仍是「working as intended」非系統錯誤）；FAIL pipeline-alert 升級邏輯與 `[42b]` 同。

### 5.3 `[42c]` Implementation 概要

新 file 或 append 至 `helper_scripts/db/passive_wait_healthcheck/checks_governance.py`：

```python
ATTRIBUTION_DRIFT_WINDOW_3D: str = "interval '3 days'"

def check_42c_live_candidate_attribution_drift_3d(cur) -> tuple[str, str]:
    """[42c] 3d-window attribution drift aligned to R-meta gate.

    Mirrors [42b] structure but uses 3d window matching producer
    `_R_META_WINDOW_DAYS` (Fix 2). [42b] = long-window observability;
    [42c] = R-meta gate behavior 對齊。Operator 看 [42c] WARN = 知道
    R-meta gate 會 defer 該 strategy，是 working-as-intended 非 bug。
    """
    # ... mirror check_42b_live_candidate_attribution_drift but ATTRIBUTION_DRIFT_WINDOW_3D
```

`__init__.py` + `runner.py` 同 Fix 1 [43] pattern 加入 slot。

---

## §6. Backward compat

### 6.1 既有 27 pending candidates

- payload `schema_version = "live_candidate_eval_v1"` 維持有效 → consumer 不會 reject_schema_unknown
- payload **缺** `demo_attribution_window_days` sub-key → consumer 視為 v1（default 7）；audit row 寫 `7` 表示「pre-Fix 2 candidate」
- ratio 仍是當時 producer cycle 計算的 7d ratio → R-meta gate 用 7d ratio 評估
- **行為**：既有 27 candidates 沿用 7d ratio 評估，`[42b]` 7d 仍是其 retro 對齊 source；不重新計算

### 6.2 新 producer cycle

- 寫新 candidate 時：payload `demo_attribution_chain_ratio_by_strategy` 用 3d 計算；`demo_attribution_window_days = 3` sub-key 顯示 window
- consumer R-meta gate 用 3d ratio
- audit row payload_snapshot 寫 `demo_attribution_window_days: 3`

### 6.3 bulk re-evaluation policy

LG5-W2 已 ship 的 `lg5_re_evaluate_pending.py`（如有）對 27 既有 candidates 再次跑 review_live_candidate 時：

- **不重新合成 payload**（producer-side 寫入凍結；consumer 純讀 payload）
- consumer 看 `schema_version = v1` + 缺 `demo_attribution_window_days` → 視為 7d ratio 評估
- audit row 標記 `re_evaluated_with_v1_window` = true（payload_snapshot 加 marker）

**Operator 顯式 re-synth policy**（**不**自動執行）：

如 operator 確認「想對 27 candidates 用新 3d 視角重新評估」，可額外執行 one-off script `helper_scripts/lg5_resynth_pending_attribution_window.py`（**新檔**，**不在本 ticket 範疇**）：
- 對每個 pending candidate 重跑 `_compute_attribution_chain_ratio_by_strategy()`（3d）
- 用 `mlde_param_applications.payload` JSONB merge（PG `jsonb_set`）寫回新 sub-key + 新 ratio
- 加 audit row `event = "payload_resynth_attribution_window_3d"`

**本 Fix 2 預設**：**不** bulk re-synth；新 candidate 走新窗，舊 candidate 走舊窗。Operator 後續決定是否 explicit re-synth。

### 6.4 v2 RFC 文檔對齊

v2 RFC §2.1 `payload schema` 寫 `"window_days": 7`（line 115）—— **不修改 v2 文檔**；本 amendment RFC 自帶 superseding clause，consumer/producer 行為以本 amendment 為準。

下次 v3 RFC（如有）合併本 amendment + Fix 1 + 其他 follow-up 時統一 update v2 文本。

---

## §7. Implementation breakdown

### 7.1 Sub-task 派發

| Task ID | Scope | Owner | LOC est. | 並行 group |
|---|---|---|---|---|
| **LG5-FUP2-FIX2-IMPL-1** | Producer SQL 7d→3d：`mlde_demo_applier.py` `_compute_attribution_chain_ratio_by_strategy` 改 SQL parameter binding 用 `_R_META_WINDOW_DAYS=3`；新增常數 `_R_META_WINDOW_DAYS` 並更新 docstring | E1 | ~30 LOC（含 docstring） | A（獨立） |
| **LG5-FUP2-FIX2-IMPL-2** | Payload + audit window_days field：producer payload 加 `demo_attribution_window_days`；consumer audit_row payload_snapshot 加 `demo_attribution_window_days` echo | E1 | ~10 LOC | A（同檔可合併 IMPL-1） |
| **LG5-FUP2-FIX2-IMPL-3** | Healthcheck `[42c]`：新 `check_42c_live_candidate_attribution_drift_3d` mirror `[42b]` 但 3d window；`__init__.py` + `runner.py` 加 slot；`docs/healthchecks/2026-05-02--lg5_health_checks.md` 加章節 | E1 | ~50 LOC（含 docstring） | B（獨立檔） |
| **LG5-FUP2-FIX2-IMPL-4** | Unit tests：(a) `test_mlde_demo_applier.py` 加 test 驗 producer 用 3d window + payload 含 `demo_attribution_window_days`；(b) `test_lg5_review_live_candidate.py` 加 test 驗 audit row 含 window_days；(c) `test_lg5_healthchecks.py` 加 5 new tests for `[42c]` (PASS/WARN/FAIL 三段 + first-deploy grace + view missing fail) | E4 / E1 | ~80 LOC | C（依賴 IMPL-1/2/3） |

### 7.2 並行性 + 估時

```
Wave plan (PM 編排):

  Round 1 (parallel):
    Group A: IMPL-1 + IMPL-2 (E1 #1; same file mlde_demo_applier.py 合併 1 PR)
    Group B: IMPL-3 (E1 #2; healthcheck 獨立檔)
  Round 2 (sequential, depends on Round 1):
    Group C: IMPL-4 (E1 #3 or E4; tests 跨 3 檔)
  Round 3:
    @E2 review (parallel 3 PR)
    @E4 SSH Linux regression (sequential after E2 PASS)
  Round 4:
    @QA → PM Sign-off → commit + push → restart_all --rebuild --keep-auth
```

**估時**（保守，含 review round trip）：
- IMPL-1+2 (A): 1.5h coding + 1h E2 round + 0.5h fix loop = 3h
- IMPL-3 (B): 1.5h coding + 1h E2 + 0.5h fix loop = 3h（與 A 並行 → 純 wall 3h）
- IMPL-4 (C): 2h coding + 1h E2 + 0.5h fix loop = 3.5h
- E4 SSH regression: 0.5h
- QA + PM commit + deploy: 1h

**Total wall time**: 3h（並行 A+B）+ 3.5h (C) + 0.5h (E4) + 1h (PM) ≈ **8h end-to-end**。

### 7.3 派發風險

- IMPL-1+2 在同檔 → 不需 worktree isolation
- IMPL-3 在不同子目錄（`helper_scripts/db/passive_wait_healthcheck/`）→ 不重疊
- IMPL-4 在 3 個 test 檔，相互獨立
- 所有 IMPL 都是 read/SQL/dict tweak，**0** strategy params / risk config / live auth 改動 → 風險評級 **低**

---

## §8. Acceptance gate — 只需 PM Sign-off

### 8.1 拍板：**只需 PM**（不需 QC + MIT 三方 sign-off）

### 8.2 理由

1. **QC 已 sign-off R-meta 公式**：v2 RFC §11 Q5 拍板「per-strategy R-meta + 0.50 floor」；Fix 2 **不改公式 + 不改 floor + 不改 per-strategy structure**，純 window 數值縮放。
2. **MIT 已 sign-off per-strategy logic**：MF-M2 拍板 per-strategy dict + R-meta gate per-strategy lookup；Fix 2 **不改 5-strategy keyset + 不改 lookup logic**。
3. **MIT FUP-2 自身就是 Fix 2 trigger**：MIT 已在 FUP-2 diagnosis 中明確指出「7d 含 4/24-28 bug 期殘留 over-penalize」，Fix 2 直接執行 MIT 建議。
4. **零安全 / 風控 / live auth 邊界改動**：CLAUDE.md §四 硬邊界 0 觸碰；CLAUDE.md §二 16 條根原則 0 違反（見 §10 root-principle check）。
5. **純 producer-side window 數值縮放 + consumer audit echo**：技術風險 LOW，無需多角色 adversarial review。

### 8.3 PM Sign-off checklist

PM 在批准 Fix 2 前確認：
- [x] PA RFC 完整（本文件）
- [ ] E2 round 1 review PASS（all 3 PR）
- [ ] E4 SSH Linux regression PASS（producer test + consumer test + healthcheck test 全綠）
- [ ] §10 Open question 1（rename vs additive constant）拍板
- [ ] §10 Open question 2（bulk re-synth pending policy）拍板
- [ ] CLAUDE.md §三 update entry（[42c] 加 active gates 列）

---

## §9. Side-effect analysis

### 9.1 DB query latency

`_compute_attribution_chain_ratio_by_strategy` SQL 從 `interval '7 days'` 改 `interval '3 days'`：
- 預期 view 大小縮 ~57% (3/7) → query latency **下降**
- `mlde_edge_training_rows` hypertable chunk 切分對 3d range scan 更友善
- **0 risk**（純 SQL window 縮短）

`[42c]` 新 healthcheck 多一次 query：
- 同 query plan as `[42b]`，3d window → latency 與 `[42b]` 相當或更快
- wrapper SUMMARY 整體 latency +1 query（~50ms 量級）
- **0 risk**

### 9.2 Cardinality

3d 樣本約 7d 的 ~43%（理論值；實際視 demo + live_demo 流量分布）。Per-strategy n 可能落入：

| Strategy | 7d n（觀察）| 3d 預估 n（×0.43）| Risk |
|---|---|---|---|
| grid_trading | ~高（多 symbol active） | ~中-高 | 低 |
| ma_crossover | ~中 | ~中 | 低 |
| funding_arb | ~低 | ~低 | 中（fail-soft 0.0 已處理） |
| **bb_breakout** | **30** (per FUP-2 觀察) | **~13** | **中-高** |
| **bb_reversion** | **6** (per FUP-2 觀察) | **~2-3** | **高** |

bb_breakout / bb_reversion 在 7d 已是 cardinality 稀薄；3d 後可能 < 10 sample。

### 9.3 bb_breakout / bb_reversion 樣本不足 fallback policy

**現況** (v2 RFC + 既有 producer):
- producer fail-soft：SQL 異常 / 0 rows → ratio 0.0
- consumer R-meta gate：ratio < 0.50 → `defer reject_attribution_chain_too_broken`
- **後果**：bb_breakout / bb_reversion 在 3d window 下 n < 10 → ratio 易 0.0 / 0.20 → R-meta defer 全部 candidates

**Fix 2 拍板 fallback policy（建議）**：

加 producer-side **minimum sample threshold**（**新邏輯，本 amendment 一併處理**）：

```python
_R_META_MIN_SAMPLE_PER_STRATEGY: int = 10  # 3d 視窗下 strategy n < 10 視為「樣本不足」

# 在 _compute_attribution_chain_ratio_by_strategy 末尾：
for row in rows:
    name = str(row[0])
    if name not in ratios:
        continue
    total = _safe_int(row[1])
    ok_count = _safe_int(row[2])
    if total >= _R_META_MIN_SAMPLE_PER_STRATEGY and total > 0:
        ratios[name] = ok_count / total
    # else: ratio 維持初始 0.0（dict 預設）
```

並在 payload 加 sub-key：
```python
"demo_attribution_strategy_sample_count": {
    name: total_dict.get(name, 0) for name in _ATTRIBUTION_STRATEGY_KEYS
}
```

Consumer R-meta evaluator 增 strategy_sample_count check：
```python
def evaluate_r_meta(
    candidate_strategy: str,
    attribution_dict: dict[str, float],
    sample_count_dict: dict[str, int],  # ← Fix 2 NEW
) -> tuple[Literal["pass", "fail", "unknown", "deferred_low_sample"], str, Optional[float]]:
    if not candidate_strategy:
        return "unknown", "R-meta: candidate has no strategy_name", None
    if candidate_strategy not in attribution_dict:
        return "unknown", f"...", None

    sample_n = sample_count_dict.get(candidate_strategy, 0)
    if sample_n < 10:
        # 新增：3d window 樣本不足 → defer，不算 strategy 真正壞
        return "deferred_low_sample", f"R-meta: {candidate_strategy} n={sample_n} < 10 (3d insufficient)", None

    ratio = _safe_float(attribution_dict[candidate_strategy])
    if ratio < R_META_RATIO_FLOOR:
        return "fail", f"...", ratio
    return "pass", f"...", ratio
```

新增 `defer_attribution_chain_low_sample` reason；audit row 區別「strategy 真壞 (defer reject_attribution_chain_too_broken)」vs「3d 樣本不足 (defer_attribution_chain_low_sample)」。

**Operator policy**：見 §10 Open question 3 拍板。

### 9.4 認知斷層風險

operator 看 `[42b]` 7d PASS 但 candidate R-meta defer → 困惑。**緩解**：
- `[42c]` 直接 surface 3d gate 行為
- audit row 含 `demo_attribution_window_days = 3` echo
- healthcheck doc / RFC v2 supersede note 明文「R-meta gate 用 3d」

### 9.5 Rust 端

`HStateCacheSlot` / `CostEdgeAdvisorDbSlot` 不讀 attribution_chain_ratio；R-meta gate 純 Python 平面 → **0 Rust impact**。

### 9.6 既有 27 pending candidates

- 維持原 7d ratio + R-meta 7d gate 評估（v1 backward compat）
- 不重新合成（§6.3）
- **行為**：原本因 7d ratio 14% 被 defer 的 candidate 仍 defer；新進 candidate 用 3d ratio 評估有更高機會 pass

如 operator 想讓既有 candidates 也享 3d 評估，需 explicit run §6.3 描述的 one-off resynth script（**不在本 ticket 範疇**）。

---

## §10. Open questions for PM

### Open Q1: Rename `_DEMO_BASELINE_WINDOW_DAYS` 還是純新增 `_R_META_WINDOW_DAYS`?

| Option | Pros | Cons |
|---|---|---|
| A. Rename `_DEMO_BASELINE_WINDOW_DAYS` → `_BASELINE_WINDOW_DAYS` 並新增 `_R_META_WINDOW_DAYS` | 命名語意更清晰；防 future regression | 5 處 grep-rename + risk of merge conflict with 隔壁 worktree |
| **B. 保留 `_DEMO_BASELINE_WINDOW_DAYS=7` 不改名 + 純新增 `_R_META_WINDOW_DAYS=3`（PA 推薦）** | 0 rename noise；test import 完全不破 | 命名稍 ambiguous（needs docstring explain） |

**PA 推薦 B**；Open Q1 拍板影響 IMPL-1 LOC（B = +5；A = +25 含 rename）。

### Open Q2: 27 pending candidates bulk re-synth policy?

| Option | Pros | Cons |
|---|---|---|
| **A. 不 bulk re-synth（PA 推薦）** | 0 risk；新舊 candidate 行為清晰隔離；audit row 可區分 v1 vs v1.1 | 既有 candidates 仍會被 7d ratio 14% defer |
| B. Auto bulk re-synth on Fix 2 deploy | 既有 27 candidates 立即享 3d 視角 | bulk write 風險；需另寫 script + 額外測試 |
| C. Defer 拍板，先 deploy A，看 1 週後決定 | 漸進；可觀察 Fix 2 effect | 多一輪決策延遲 |

**PA 推薦 A**；Open Q2 拍板影響「是否需要 §6.3 一次性 script」。

### Open Q3: bb_breakout / bb_reversion 樣本不足 fallback policy?

| Option | Pros | Cons |
|---|---|---|
| **A. 加 `_R_META_MIN_SAMPLE_PER_STRATEGY=10` + `defer_attribution_chain_low_sample` reason（PA 推薦）** | 區分「strategy 真壞」vs「樣本不足」；audit 可分析；防 R-meta 對小流量 strategy 永久 defer | 加 ~20 LOC consumer + ~10 LOC producer + 2 new tests |
| B. 不加 sample threshold；ratio 0.0 一律 defer | 最簡單；零 LOC 變更 | bb_reversion 永遠 defer；無法區分原因 |
| C. fallback 7d window for low-sample strategy | 兼顧樣本量 + R-meta 信號 | per-strategy window 混用，audit 複雜；違反「單一 window 對齊」設計 |

**PA 推薦 A**；門檻 10 較寬鬆，Operator 可後續調整。Open Q3 影響 §9.3 是否落實 + IMPL-1 / IMPL-4 scope（含 evaluator signature 改動 = consumer test 需擴）。

---

## §11. Root-principle check (16 conditions, abridged)

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ 不變 | producer payload + consumer review path 不動 |
| 2 | 讀寫分離 | ✅ 不變 | R-meta gate 純 read |
| 3 | AI 輸出 ≠ 命令 | ✅ 不變 | LG-5 governance pipeline 結構不動 |
| 4 | 策略不繞風控 | ✅ 不變 | R-meta + R1-R6 gates 全保留 |
| 5 | 生存 > 利潤 | ✅ 不變 | R6 hard veto 全保留 |
| 6 | 失敗默認收縮 | ✅ 強化 | 加 sample threshold defer 反而更保守 |
| 7 | 學習 ≠ 改寫 Live | ✅ 不變 | promotion gate 改 window，本身仍 demo→live boundary |
| 8 | 交易可解釋 | ✅ 強化 | audit row 含 `demo_attribution_window_days` echo |
| 9 | 災難保護 | ✅ 不變 | 不影響 stop / liquidation |
| 10 | 認知誠實 | ✅ 本 RFC 標記事實 / 推斷 / 假設 | 本文 §1.2 引 MIT 觀察數據；§9.2 cardinality 為推斷 |
| 11 | Agent 最大自主 | ✅ 不變 | P0/P1 邊界不動 |
| 12 | 持續進化 | ✅ 強化 | R-meta 不再被舊 bug 殘留懲罰，promotion 路徑通暢 |
| 13 | 成本感知 | ✅ 不變 | R5 cost_edge_ratio 公式不動 |
| 14 | 零外部成本 | ✅ 不變 | 純 Python + PG SQL |
| 15 | 多 Agent 協作 | ✅ 不變 | 不影響 5-Agent 訊息 bus |
| 16 | 組合級風險 | ✅ 不變 | per-strategy attribution 仍對齊組合視角 |

**結論**：Fix 2 對 16 條根原則 **全部合規** + **加強原則 6 / 8 / 12**。

---

## §12. 硬邊界 grep check

```bash
grep -nE '(execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json)' \
  program_code/ml_training/mlde_demo_applier.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py \
  helper_scripts/db/passive_wait_healthcheck/checks_governance.py
```

預期結果：**0 hit on Fix 2 diff**（Fix 2 只動 SQL window + payload sub-key + audit echo）；既有檔內可能有歷史 hit 但與 Fix 2 改動行無關。

---

## §13. Cross-references

- Parent RFC v2: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md` §2.1 / §3 R-meta / §11 Q3 / Q5 拍板
- Sibling Fix 1 (cron + [43]): `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-02--lg5_w3_fup_2_fix_1.md`
- LG5-W3-FUP-1 ROUND 2 (consumer scheduler): `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-02--lg5_w3_fup_1_round2.md`
- MIT FUP-2 review: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-02--lg5_rfc_review.md`
- Producer source: `program_code/ml_training/mlde_demo_applier.py:55-936`（`_R_META_WINDOW_DAYS` 將加在 line 70 區）
- Consumer source: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py:1050-1064`（R-meta evaluator）
- Healthcheck source: `helper_scripts/db/passive_wait_healthcheck/checks_governance.py:240-388`（[42b]）+ 新 [42c] 將 append
- CLAUDE.md §二 #6 / #8 / #12 / #13 (root principles)
- CLAUDE.md §四 (硬邊界，本 amendment 0 觸碰)

---

## §14. PA Sign-off

- [x] 派發前已讀相關代碼（mlde_demo_applier.py / governance_hub_live_candidate_review.py / checks_governance.py / RFC v2 / Fix 1 report / FUP-1 round 2 report / MIT review report）
- [x] live_execution_allowed / max_retries=0 / system_mode 三硬邊界 0 觸碰
- [x] OpenClaw 通信不成單點故障（純 Python 平面 + 既有 PG）
- [x] 跨平台兼容（無新 path / 無 Linux-only API）
- [x] 16 條根原則全部合規（§11）
- [x] DOC-08 §12 安全不變量逐條核對 PASS（純 read-only / fail-soft）
- [x] 派發計劃含並行性（§7.1 三 group + Round dependency）
- [x] 高風險警告（§9.3 bb_breakout/bb_reversion sample 稀薄）
- [x] Open questions（§10 三項）給 PM 拍板
- [x] **不寫業務代碼 / 不動 v2 RFC / 不動 V### migration / 不動 producer/consumer 實檔 / 不 commit / 不 push** —— 本 RFC 為純 design

**Status**: PA design complete. Awaiting PM 拍板 Open Q1/Q2/Q3 + 派發 IMPL-1/2/3/4 to E1/E4。
