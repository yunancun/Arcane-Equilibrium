# E1 — REF-20 Wave 6 Batch 6A IMPL report

**Date / 日期**：2026-05-03
**Owner / 負責**：E1 (sequential single instance)
**Task scope / 範圍**：4 P4 advisory gate IMPL（順序執行 Q1 → Q2 → Q3 → Q6）
**PA dispatch reference**：Wave 6 Batch 6A — Q1 DSR + Q2 PBO + Q3 selection bias + Q6 cost_edge_ratio
**Status**：✅ COMPLETED — 47 pytest case PASS（4 task × 4 PA mandatory + 31 補強）

---

## 1. 任務摘要 / Task summary

PM 全自主推進至 Wave 7。Wave 5 closed (commit `457a458`)。Wave 6 = P4 MLDE/Dream advisory + 4 promotion gates。本 task 同 sub-agent 順序 IMPL 4 P4 gate（共用 `learning_engine/` 模組空間 + replay subsystem）。

每 task 都需：（1）pure-math IMPL 0 IPC / 0 DB / 0 exchange dispatch；（2）雙語 MODULE_NOTE + docstring；（3）4+ pytest case；（4）file < 800 LOC；（5）跨平台路徑；（6）0 trading/live mutate。

---

## 2. 修改清單 / Modified files

### 4 NEW source modules

| 檔 | LOC | 用途 |
|---|---:|---|
| `program_code/learning_engine/dsr_gate.py` | 490 | Bailey-LdP (2014) Deflated Sharpe Ratio promotion gate |
| `program_code/learning_engine/pbo_gate.py` | 496 | Bailey-Borwein-LdP-Zhu (2014) CSCV PBO < 0.5 gate |
| `program_code/learning_engine/cost_edge_advisor.py` | 349 | V3 §8.1 + §12 #24 cost/edge advisor (Python mirror, env-gated) |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/selection_bias_validator.py` | 407 | V3 §8.3 manifest selection-bias correction validator |

### 4 NEW test modules

| 檔 | LOC | Pytest cases |
|---|---:|---:|
| `program_code/learning_engine/tests/test_dsr_gate.py` | 286 | **10** (4 PA mandatory + 6 boundary/invariant) |
| `program_code/learning_engine/tests/test_pbo_gate.py` | 325 | **10** (4 PA mandatory + 6 boundary/invariant) |
| `program_code/learning_engine/tests/test_cost_edge_advisor.py` | 305 | **13** (4 PA mandatory + 9 boundary/env-matrix) |
| `program_code/exchange_connectors/.../replay/tests/test_selection_bias_validator.py` | 295 | **14** (4 PA mandatory + 10 boundary/edge) |

**TOTAL**: 8 new files, 2,953 LOC, **47 pytest cases PASS**.

---

## 3. 關鍵 diff (signature snippets) / Key signatures

### 3.1 dsr_gate.py
```python
class DsrGate:
    def __init__(self, threshold: float = 0.95) -> None: ...

    def compute_dsr(
        self,
        observed_sharpe: float,
        n_trials: int,
        n_observations: int = 100,
        trial_sharpes: Optional[Sequence[float]] = None,
        skew: float = 0.0,
        excess_kurtosis: float = 0.0,
    ) -> DsrResult: ...

    def gate(self, dsr_result: DsrResult) -> Literal["promote", "block", "borderline"]: ...

@dataclass
class DsrResult:
    observed_sharpe: float
    deflated_sharpe: float          # the DSR value, ∈ [0, 1]
    n_trials_K: int
    psr_at_threshold: float          # PSR(0) baseline diagnostic
    trials_max_sharpe: float         # E[max SR_k] under Gaussian null
    passes_threshold: bool
```

**Math IMPL（純 stdlib，0 scipy 依賴）**：
- `_normal_cdf` — math.erf
- `_normal_inv_cdf` — Beasley-Springer-Moro (accuracy ~1e-7 對 K<=10000)
- `_compute_expected_max_sharpe(K)` — Bailey-LdP Eq. 8 近似
- `_compute_psr` — handles skew + excess_kurtosis

### 3.2 pbo_gate.py
```python
class PboGate:
    def __init__(
        self,
        threshold: float = 0.5,
        min_K: int = 10,
        min_total_trades: int = 320,
        s_slices: int = 16,
    ) -> None: ...

    def compute_pbo(self, oos_returns_per_split: Sequence[np.ndarray]) -> PboResult: ...

    def gate(self, pbo_result: PboResult) -> Literal["promote", "block"]: ...

@dataclass
class PboResult:
    pbo: float                 # ∈ [0, 1]
    n_splits: int              # = C(s_slices, s_slices//2)
    total_trades: int          # = T × N_candidates
    median_oos_sharpe: float
    passes_threshold: bool
    insufficient_power: bool   # n_splits < min_K OR total_trades < min_total_trades
```

**CSCV IMPL（純 stdlib + numpy，0 sklearn）**：
- `itertools.combinations` 列舉 C(S, S/2) 分區
- per-combination: rank candidates by IS Sharpe → record OOS rank of best-IS → logit
- Tie handling: 用 mean rank 避免 logit ±inf

### 3.3 cost_edge_advisor.py
```python
class CostEdgeAdvisor:
    def __init__(self, ratio_threshold: float = 0.8) -> None: ...

    def compute_ratio(self, expected_edge_bps: float, expected_cost_bps: float) -> float: ...

    def evaluate(
        self,
        expected_edge_bps: float,
        expected_cost_bps: float,
        env_gate: Optional[bool] = None,
    ) -> CostEdgeResult: ...

    def gate(
        self,
        ratio_or_result: float | CostEdgeResult,
        env_gate: Optional[bool] = None,
    ) -> Literal["actionable", "advisory_only", "block"]: ...

ENV_VAR_NAME = "OPENCLAW_COST_EDGE_ADVISOR"  # strict-equal "1" semantics
ENV_VAR_TRUE_VALUE = "1"

def is_env_gate_enabled() -> bool:
    """Strict-equal "1" comparison; mirrors Rust spec at
    `rust/openclaw_engine/src/cost_edge_advisor_boot.rs:142`."""
    return os.environ.get(ENV_VAR_NAME) == ENV_VAR_TRUE_VALUE
```

**Verdict matrix (V3 §11 P4 footnote)**:
```
| env_gate | ratio   | verdict          |
|----------|---------|------------------|
| True     | >=0.8   | actionable       |
| True     | <0.8    | block            |
| True     | NaN     | block            | (fail-closed; cost<=0 degenerate)
| False    | any     | advisory_only    | (env-gate respect)
```

### 3.4 selection_bias_validator.py
```python
@dataclass
class SelectionBiasCorrection:
    n_trials_K: int
    backtest_period_days: int
    out_of_sample_pct: float
    cv_protocol: Literal['walk_forward', 'cscv', 'purged_kfold']
    embargo_days: int

ALLOWED_CV_PROTOCOLS = frozenset({"walk_forward", "cscv", "purged_kfold"})
MIN_TRIALS_K = 10
MIN_OOS_PCT = 0.20
MIN_EMBARGO_DAYS_FLOOR = 7  # 對齊 V041 CHECK constraint floor

def validate_selection_bias_correction(
    manifest: Mapping[str, object],
    *,
    block_key: str = "selection_bias_correction",
) -> ValidationResult: ...

class SelectionBiasFailMode(Enum):
    MISSING_BLOCK = "missing_block"
    K_TOO_LOW = "k_too_low"
    OOS_PCT_TOO_LOW = "oos_pct_too_low"
    UNKNOWN_CV_PROTOCOL = "unknown_cv_protocol"
    EMBARGO_TOO_LOW = "embargo_too_low"
```

---

## 4. 治理對照 / Governance compliance

### 4.1 V3 binding alignment

| V3 reference | 本 task 兌現 |
|---|---|
| §8.3 "DSR(K) > 0.95 for promotion" | `dsr_gate.py:DEFAULT_DSR_THRESHOLD=0.95` |
| §8.3 "PBO < 0.5 when K >= 10 and total trades >= 320" | `pbo_gate.py:DEFAULT_PBO_THRESHOLD=0.5 / DEFAULT_MIN_K=10 / DEFAULT_MIN_TOTAL_TRADES=320` |
| §8.3 "selection bias correction metadata mandatory" | `selection_bias_validator.py:validate_selection_bias_correction()` 5 fail-mode + 5 mandatory field |
| §8.1 "cost gate: cost_edge_ratio >= 0.8" | `cost_edge_advisor.py:DEFAULT_RATIO_THRESHOLD=0.8` |
| §11 P4 footnote "env_gate=False → advisory_only" | `cost_edge_advisor.py:gate()` `if not env_enabled: return 'advisory_only'` |
| §12 #17 `replay_cv_protocol` | DSR + PBO + cv_protocol allowlist 三者並存 |
| §12 #24 `replay_cost_edge_ratio_gate` | cost_edge_advisor + env-gated |

### 4.2 CLAUDE.md §七 跨平台 + 雙語

- ✅ 0 hardcoded `/home/ncyu` / `/Users/ncyu` 路徑（grep 命中 0）
- ✅ 4/4 modules MODULE_NOTE 雙語
- ✅ 4/4 modules + 4/4 tests 雙語 docstring
- ✅ 4/4 modules < 800 LOC 警告線（最大 496 PBO）
- ✅ 0 trading.* / live mutate / max_retries 修改
- ✅ 0 SQL migration（純 Python math + validate，無 DB schema 改動）

### 4.3 18 blocker 對齊

- **#10 HStateCache + CostEdgeAdvisor late-inject env-gated OFF**：本 task 的 `cost_edge_advisor.py` Python 端 `is_env_gate_enabled()` 嚴格鏡像 Rust 端 `OPENCLAW_COST_EDGE_ADVISOR=1` strict-equal "1" 比對（Rust spec at `rust/openclaw_engine/src/cost_edge_advisor_boot.rs:97 / 142 / 145`）。env_gate=False（預設）→ Python advisor 仍可 compute_ratio（純 math，不啟用 daemon）→ 但 gate() 一律回 'advisory_only'（V3 §11 P4 footnote 兌現）。

### 4.4 工作鏈

按 CLAUDE.md §七 強制鏈：E1（本 task）→ E2 review → E4 regression → QA → PM commit + push（不直接 commit）。

---

## 5. Pytest 結果 / Pytest results

```
program_code/learning_engine/tests/test_dsr_gate.py                       10 PASS
program_code/learning_engine/tests/test_pbo_gate.py                       10 PASS
program_code/learning_engine/tests/test_cost_edge_advisor.py              13 PASS
program_code/.../replay/tests/test_selection_bias_validator.py            14 PASS
─────────────────────────────────────────────────────────────────────────────
TOTAL                                                                     47 PASS
```

執行時間：~3.0s（含 PBO test_random_candidates_pbo_around_half ≈ 2.7s 因 C(16,8)=12870 enumeration）。

PA spec 要求 16 case；實 47 case 含：
- DSR 4 mandatory + 6 boundary（invalid threshold/n_trials/n_observations + explicit trial_sharpes override + module shortcut + borderline band）
- PBO 4 mandatory + 6 boundary（invalid threshold/s_slices + empty/single + module shortcut + random PBO ≈ 0.5）
- cost_edge 4 mandatory + 9 boundary（invalid threshold + NaN input + negative edge + zero cost + negative cost + module shortcut + env-var matrix monkeypatch + raw float ratio path + default env read）
- selection_bias 4 mandatory + 10 boundary（missing block / not dict / missing field / embargo too low / OOS boundary inclusive / OOS=1 fail / K boundary / bool reject / int→float coerce / dataclass roundtrip）

---

## 6. 不確定 / 向 PM push back

1. **DSR 用 Beasley-Springer-Moro inv_cdf 近似 vs scipy.stats.norm.ppf**：accuracy ~1e-7 對 K<=10000 充分。對齊 Wave 5 quantile_bootstrap 的「純 stdlib，0 scipy 依賴」政策。**生產 K 預期上限若 > 10000 應切 scipy.stats**。請 PM 在 wiring sub-task 確認。

2. **PBO test_pbo_high_blocks_promotion 用 s_slices=2 + sign-flip**：本 test 是 unit-level mathematical sanity（驗證 anti-persistent → high PBO 邏輯），非生產設定模擬（生產 s_slices=16）。**建議 wiring sub-task 補 integration test 用 S=16 + 真生產 returns** 以驗 CSCV C(16,8)=12870 enumeration 在實 returns matrix 下穩健。

3. **selection_bias_validator embargo_days 與 V041 CHECK 對齊**：本 module 只 check 下限 `>= MIN_EMBARGO_DAYS_FLOOR=7`，不檢上限 `>= max(7, ceil(2 × half_life))`（後者由 sibling `embargo_validator.py` 已處理）。caller 應同時 invoke 2 validator。**請 PM 在 wiring sub-task 確認 chain order**（建議：power_gate → DSR → PBO → cost_edge → selection_bias → embargo_validator）。

4. **cost_edge_advisor Python 端 RiskConfig.cost_edge.enabled 雙保險未鏡像**：Rust 端 `cost_edge_advisor_boot.rs:122` 寫「dual safeguard：env=1 仍須 RiskConfig.cost_edge.enabled=true 才完整 evaluate；false 走 Disabled short-circuit」。Python 端本 task 未鏡像（因 RiskConfig 為 Rust ConfigStore，Python 從 IPC 取會引入耦合，超出本 task 範圍）。**請 PM 確認 wiring sub-task 是否需 Python 端 IPC RiskConfig 雙保險**。

5. **Wave 6 P4-Q4/Q5/S11/S12 未在本 task 範圍**：plan §4 Wave 6 表列 P4 row 共 8 個（Q1/Q2/Q3/Q4/Q5/Q6 + S11 + S12）。本 task 4 (Q1/Q2/Q3/Q6)；Q4 (DreamEngine API) / Q5 (MLDE veto) / S11 (mlde_demo_applier source filter) / S12 (replay_routes safe query mirror) 待後續派發。

6. **47 case 超 PA mandatory 16**：補強為 boundary + invariant + module shortcut（cost_edge env-var matrix monkeypatch 算最值得補的，避免 P1-FAKE-3 環境變數設值錯誤被默默忽略）。**E2 review 若認為應控只 16 case，請告知是否該縮減**。

---

## 7. Operator 下一步 / Next steps

1. **E2 review** — 4 module + 4 test 雙語注釋一致性 / Beasley-Springer-Moro 數學 IMPL 數值準確性（vs scipy.stats.norm.ppf 在 K=10/100/1000 對照） / selection_bias_validator vs embargo_validator caller chain order 設計 / cost_edge_advisor 雙保險是否需 Python 端 IPC RiskConfig。
2. **E4 regression** — Linux trade-core 跑 `python3 -m pytest program_code/learning_engine/tests/ program_code/exchange_connectors/bybit_connector/control_api_v1/replay/tests/` 全綠；驗 Wave 5 sibling (cell_calibrator/regime_controller/quantile_bootstrap) 不退化。
3. **MIT review** — DSR PSR 數學 vs Bailey-LdP 2014 paper Eq. 11 / Eq. 8 對照；PBO CSCV vs Bailey-Borwein-LdP-Zhu 2014 paper Algorithm 1 對照；cost_edge_advisor env-gate 雙端（Rust strict "1" vs Python strict "1"）sync 對照。
4. **replay_routes wiring sub-task** — 將 4 gate 串入 `replay_routes.py::generate_handoff_verdict`；建議 chain：power_gate (P3a-Q6) → freshness_gate (P3a-Q6) → cell_status_gate (P3b-Q1) → DSR → PBO → cost_edge → selection_bias → embargo。
5. **PM commit + push** — E2 + E4 + MIT 全綠後 PM 用提交訊息：
   ```
   feat(replay): P4-Q1+Q2+Q3+Q6 — DSR + PBO + selection bias + cost_edge gate (Wave 6 Batch 6A)
   ```

---

## 8. Sign-off readiness / Sign-off 就緒

- ✅ 4 task 順序 IMPL 全完成
- ✅ 47 pytest case PASS (4 PA mandatory + 31 補強 + 0 fail)
- ✅ 0 cross-platform path violation
- ✅ 0 trading/live mutate
- ✅ 雙語 MODULE_NOTE 4/4
- ✅ LOC < 800 警告線 4/4
- ✅ NEW singleton 0（4 模組均 stateless class，不需登記 §九 表）
- ⏳ E2 review 等審
- ⏳ E4 regression 等審
- ⏳ MIT review 等審

E1 IMPLEMENTATION DONE: 待 E2 審查 (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_wave6_batch6a_p4_q1_q2_q3_q6.md`)
