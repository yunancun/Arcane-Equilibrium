# LG5-W3-FUP-2 Fix 2 IMPL-2-consumer — R-meta low_sample defer + audit JSONB sub-key

Date: 2026-05-02
Author: E1
Sprint: LG5-W3-FUP-2 Fix 2
Round: 1 (initial impl, awaiting E2 review)
Status: DONE — awaiting E2 review

---

## 1. 任務摘要

PA RFC §3 + Q3 + 任務派發單明確的 6 項 IMPL-2-consumer scope：

1. 加 `_R_META_MIN_SAMPLE_PER_STRATEGY: int = 10` 常數 + 新 reason enum `defer_attribution_chain_low_sample`
2. `evaluate_r_meta()` 邏輯擴展 sample threshold check（**ratio check 之前**）
3. Backward compat: 既有 27 pending candidate payload 缺 `demo_attribution_sample_count_by_strategy` → 略過 sample check 沿用 ratio path
4. `ReviewVerdict` dataclass 加 `attribution_sample_count: Optional[int]` field
5. Audit emission V035 column 不存在 → 寫 payload JSONB sub-key
6. 5 new tests（low_sample defer / pass / ratio reject with sufficient sample / 2 backward-compat 路徑）

不動：producer (`mlde_demo_applier.py`)、V035 SQL migration、healthcheck `[42c]`。

## 2. 修改清單

| 路徑 | 變更 | 行數 | 說明 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_live_candidate_review.py` | 修 | -9 net | 移除 evaluator + 大塊 caller branch dispatch；新增 sample dict pull + 4-line caller helper invocation + dataclass field + _make_verdict param + audit JSONB sub-key |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub_lg5_r_meta.py` | **新檔** | +180 | LG-5 R-meta sibling helper：2 const + `evaluate_r_meta` + `evaluate_r_meta_sample_threshold` + 新 `build_r_meta_gate_verdict_kwargs` helper |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_review_live_candidate.py` | 加 | +165 | 5 new caller-integration tests（class `TestRMetaSampleThreshold`，借用 `TestReviewLiveCandidateRound2` `_patch_module`/`_FakeHub` fixture pattern） |

無 SQL migration / 無新 singleton / 無新 IPC / 無 risk config 改動。

## 3. 關鍵 diff

### 3.1 Sibling helper module（governance_hub_lg5_r_meta.py 新檔）

主要 helper 三件：

```python
def evaluate_r_meta(candidate_strategy, attribution_dict)
    -> tuple[Literal["pass","fail","unknown"], str, Optional[float]]

def evaluate_r_meta_sample_threshold(candidate_strategy, sample_count_dict)
    -> tuple[bool, str, Optional[int]]
    # sample_count_dict is None → return (False, "skip (no sample dict)", None)
    # candidate not in dict → return (False, "skip (strategy missing)", None)
    # n < _R_META_MIN_SAMPLE_PER_STRATEGY → (True, "n=N < 10 (3d insufficient)", n)
    # n ≥ threshold → (False, "n=N sufficient", n)

def build_r_meta_gate_verdict_kwargs(
    candidate_strategy, attribution_dict, sample_count_dict,
    expected_net_bps_demo, decided_by_full,
) -> tuple[Optional[dict], Optional[int], str]
    # returns (verdict_kwargs|None, sample_n, r_meta_msg)
    # Order: unknown → low_sample → ratio fail
    # None → R-meta passed; caller proceeds to R1-R5
```

### 3.2 Consumer main file: re-export + caller compaction

**Re-export（保 backward-compat for tests + producer NA caller）**：
```python
from .governance_hub_lg5_r_meta import (
    R_META_RATIO_FLOOR, _R_META_MIN_SAMPLE_PER_STRATEGY,
    evaluate_r_meta, evaluate_r_meta_sample_threshold,
    build_r_meta_gate_verdict_kwargs,
)
```

**Caller from ~45 LOC → 9 LOC**：
```python
# R-meta per-strategy gate (Fix 2 IMPL-2-consumer split): helper resolves
# unknown / low_sample (Fix 2 PA Q3) / ratio fail in one call.
r_meta_kwargs, r_meta_sample_n, r_meta_msg = build_r_meta_gate_verdict_kwargs(
    candidate_strategy, attribution_dict, sample_count_dict,
    expected_net_bps_demo, decided_by_full,
)
if r_meta_kwargs is not None:
    verdict = _make_verdict(**r_meta_kwargs)
    _emit_audit_row("review_live_candidate", candidate_id, verdict)
    return verdict
```

### 3.3 ReviewVerdict 新 field + _make_verdict 透傳

```python
@dataclass(frozen=True)
class ReviewVerdict:
    ...
    payload_snapshot: dict = field(default_factory=dict)
    # Fix 2 NEW：候選 strategy 3d attribution sample 數，IMPL-5 retro 校準用。
    attribution_sample_count: Optional[int] = None
```

`_make_verdict()` 加 `attribution_sample_count: Optional[int] = None` kwarg + 在 `ReviewVerdict(...)` 構造傳遞（共 2 行新增）。

### 3.4 Audit emission（V035 column 不存在 → payload JSONB sub-key）

V035 schema grep 確認無 `attribution_sample`/`sample_count` column，僅有 forward-compat `payload JSONB`。`_emit_audit_row` + `_emit_approve_audit_and_persist_lease_atomic` 兩處 audit insert 的 `json.dumps({...})` block 加一個 sub-key：

```python
json.dumps({
    "payload_snapshot": verdict.payload_snapshot,
    "decided_at_ts": verdict.decided_at_ts,
    # Fix 2 IMPL-2 (V035 has no column → JSONB sub-key, schema unchanged).
    # Fix 2 IMPL-2：V035 無對應 column，寫入 payload JSONB sub-key 維持 schema 不變。
    "attribution_sample_count": verdict.attribution_sample_count,
}, default=str)
```

### 3.5 Caller 提取 sample_count_dict from payload（4 行）

```python
# Fix 2 IMPL-2 PA Q3: per-strategy sample count dict for R-meta low-sample
# defer; missing (pre-Fix 2 payload) → None → skip sample check (preserves
# 27 pending candidates per RFC §6.1).
_raw_smp = payload.get("demo_attribution_sample_count_by_strategy")
sample_count_dict: Optional[dict[str, int]] = _raw_smp if isinstance(_raw_smp, dict) else None
```

## 4. 5 new tests（class `TestRMetaSampleThreshold`，覆蓋 PA 任務 6 個 case）

| Test | 驗證 |
|---|---|
| `test_r_meta_defer_when_sample_below_threshold` | sample=5 + ratio=0.80 → defer reason=`defer_attribution_chain_low_sample`（**不是** `reject_attribution_chain_too_broken`）；`attribution_sample_count == 5`；`payload_snapshot.min_sample_threshold == 10` + msg 含 "n=5"；hub.acquire/atomic 都未觸發 |
| `test_r_meta_pass_when_sample_above_threshold` | sample=20 + ratio=0.80 → R-meta pass → 進 approve path → atomic commit invoked → verdict.decision="approve" |
| `test_r_meta_reject_when_ratio_low_with_sufficient_sample` | sample=20 + ratio=0.20 → defer reason=`reject_attribution_chain_too_broken`（既有 RFC §3 R-meta 行為不變；sample_n=20 仍寫 audit 區分 reason） |
| `test_r_meta_backward_compat_no_sample_dict` | payload 無 `demo_attribution_sample_count_by_strategy` → 視 v1 → skip sample check → ratio=0.80 path → approve；`attribution_sample_count is None` |
| `test_r_meta_backward_compat_strategy_missing_in_sample_dict` | sample dict 含 `ma_crossover` 但不含 `grid_trading` → grid_trading skip sample check → ratio path → approve；`attribution_sample_count is None` |

## 5. 治理對照

- **CLAUDE.md §七 ★★ 跨平台**：`grep -nE '/home/ncyu|/Users/[^/]+'` 0 hit on 3 修改檔。
- **CLAUDE.md §七 雙語注釋**：sibling 新檔有 MODULE_NOTE + 雙語 docstring + inline 雙語注釋；主檔新增段落（sample_count_dict pull / R-meta caller helper invocation / dataclass field / audit JSONB sub-key）全部中英對照。
- **CLAUDE.md §七 SQL migration**：V035 schema 0 改動（PA RFC §6 + 派發明示）。
- **CLAUDE.md §九 singleton**：未新增 singleton。
- **CLAUDE.md §二 16 條根原則**：原則 6 (失敗收縮) + 8 (可解釋) + 12 (持續進化) 強化（PA RFC §11 root-principle check）；其餘 13 條 0 觸碰。
- **CLAUDE.md §四 硬邊界**：sibling 檔硬邊界 grep（execution_state / execution_authority / live_execution_allowed / decision_lease_emitted / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved / authorization.json）0 hit。
- **CLAUDE.md §九 1500 LOC 硬上限**：consumer **1487** < 1500 ✅（baseline 1496 → -9 net；R-meta 邏輯抽走比新加邏輯量還多）；sibling **180** 遠 < 800 warn。
- **PA RFC Q3 拍板**：`_R_META_MIN_SAMPLE_PER_STRATEGY=10` + 新 defer reason `defer_attribution_chain_low_sample` 落實在 sibling helper（pure function）+ caller 串接（順序：unknown → low_sample → ratio fail）。

## 6. 不確定之處

1. **Caller helper `build_r_meta_gate_verdict_kwargs` 收 5 個參數 + 回 3-tuple**：簽名稍胖。E2 若覺得應更平鋪（unknown/low_sample/fail 三 branch 留在 caller 主流程而不抽 helper），需重新權衡 LOC budget — 但實測純 inline 版本 = 1521-1530 over cap，必須抽。當前 helper 簽名雖胖但呼叫處只 4 行（`helper → if → make_verdict → emit/return`）。
2. **`_R_META_MIN_SAMPLE_PER_STRATEGY` 在 producer + consumer 兩處各定義**：producer `mlde_demo_applier.py:92` + consumer sibling `governance_hub_lg5_r_meta.py:53` 兩個檔各有一個 `=10`。實作上互不 import（避開跨層 dependency）；數值協議同步靠 PA RFC + memory + 雙語 inline 註解。E2 若覺得該以單一 source-of-truth 集中，需新增 `program_code/lg5/constants.py` 共享，但本輪未動以最小化 scope。
3. **Audit 寫入 V035 payload JSONB sub-key vs IMPL-5 retro 工具**：`attribution_sample_count` 寫進 `payload->>'attribution_sample_count'`（JSONB 子鍵）；IMPL-5 7d retro 校準工具 SELECT 時要 `payload->>'attribution_sample_count'::int` 解；E2 若需直接 column 索引（避免 JSONB 解析開銷），需 V### 加 column。本輪採 PA RFC §6 + 派發明示「不動 V### / 用 payload JSONB」路徑，符合 forward-compat 設計意圖。

## 7. Operator 下一步

### 已驗（Mac CC，無 ssh）
- `python3 -m py_compile <consumer> <sibling>` exit 0
- `pytest test_lg5_review_live_candidate.py -q` → **49 passed in 0.05s** (44 baseline + 5 new = 49)
- `pytest control_api_v1/tests/ -q` → **3316 passed, 10 skipped**, 0 fail (cross-suite 0 regression)
- `pytest test_mlde_demo_applier.py -q` → **19 passed**（producer side 0 regression）
- `wc -l consumer` = **1487** < 1500 ✅；`wc -l sibling` = **180** < 800 ✅
- `git diff --check` exit 0
- 跨平台 grep `/home/ncyu|/Users/[^/]+` 0 hit on 3 檔
- 硬邊界 grep on sibling 0 hit

### 等待 / 不做
- **不 commit / 不 push** — 等 E2 round 1 review → E4 SSH Linux regression → QA → PM 統一 commit
- **不 deploy** — 等 sibling tasks（IMPL-3 healthcheck `[42c]` + IMPL-4 doc）全 land 後 PM 一次 `restart_all --rebuild --keep-auth`

### E2 round 1 審查重點
1. **Split 決策正當性**：consumer 1487 < 1500 但 sibling 180 LOC 是否合理（vs inline trim docstring 路徑）。本輪選 split 因 inline 變體實測 1521+ 撞 cap + trim docstring 違 §七 雙語強制。
2. **`build_r_meta_gate_verdict_kwargs` 5-arg helper signature**：是否該再 refactor 成 dataclass-input（`R_MetaGateInputs`）讓 caller 更乾淨。本輪採直接 5 arg 因 caller 處只 1 處呼叫。
3. **`_R_META_MIN_SAMPLE_PER_STRATEGY` 雙處定義（producer + consumer）**：是否要抽共享常數模組。本輪保兩份各檔，協議 by RFC + memory + 雙語注解。
4. **Audit JSONB sub-key vs V### column**：V035 不動是 PA RFC + 派發明示路徑；E2 若 push 加 column 需另起 V036 ticket（不在本 ticket 範圍）。
5. **5 new tests fixture 重用 pattern**：`TestRMetaSampleThreshold` class-attr alias `_patch_module = TestReviewLiveCandidateRound2._patch_module` —— 是否該抽 `module-level pytest fixture`。本輪沿用 class-method-as-fixture pattern 與既有 Round 2 一致。

---

E1 Fix 2 IMPL-2-consumer DONE: 待 E2 審查
report path: `srv/.claude_reports/20260502_223000_lg5_w3_fup2_fix2_impl_2_consumer.md`
