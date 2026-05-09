# E1-C — W-AUDIT-9 T3 shadow_mode_provider stage-aware（Python）

**Date**: 2026-05-09
**Sprint**: N+0 Day 0-3
**Wave**: W-AUDIT-9 Graduated Canary Foundation
**Owner**: E1-C
**Local commit**: `200188ad`（**未 push**，待 E2 review → E4 regression → PM 統一 push）
**狀態**: IMPL DONE, awaiting E2 review

---

## 1. 任務摘要

把 Python 端 `shadow_mode_provider` 從 binary `bool` 升級為 5-stage graduated canary cohort（per AMD-2026-05-09-03 §2.1/§2.2），同時保留 backward-compat lambda 與 fail-closed 不變式（TODO v19 §5 invariant 9：cache miss / IPC failure / schema fail / provider exception → Stage 0，**不是** Stage 1）。

範圍 source/test IMPL only；runtime apply 由 W-AUDIT-3b smoke 後處理（cross-wave conflict #2，TODO v19 §4.2）。

---

## 2. 修改清單

### 2.1 source（2 檔，+~400 LOC）

| File | Δ LOC | 變更 |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_config_cache.py` | +199 / -38 | `CanaryStage` IntEnum + `CanaryCohort` dataclass + 升級 `ExecutorRuntimeConfig` + `canary_stage_provider()` + `shadow_mode_provider()` 投影 + `_parse_response` stage 解析 + AMD §4.4 backward-compat reject |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py` | +89 / -27 | ctor 加 `canary_stage_provider` arg + `_read_canary_stage()` 新方法 + `_read_shadow_mode()` 改為 stage projection + 雙 provider 優先序 + invariant 9 fail-closed |

### 2.2 tests（3 檔，+~290 LOC，35 新測試）

| File | Δ LOC | 新測試 |
|---|---|---|
| `tests/test_executor_config_cache.py` | +297 / -2 | TestCanaryStageEnum (7) / TestCanaryStageParseResponse (4) / TestCanaryStageBackwardCompatReject (2) / TestCanaryStageProvider (3) / TestCanaryStageProviderShadowProjection (4) / TestCanaryStageBackwardCompatLegacyConfig (2) — 19 新增 + 既有 4 個 helper 升級 |
| `tests/test_executor_agent_unit.py` | +197 / -0 | TestExecutorAgentCanaryStage (13) + TestExecutorAgentLegacyTestFixturesUnchanged (3) — 16 新增 |
| `tests/test_executor_shadow_to_live_e2e.py` | +13 / -2 | `_make_runtime_config` helper auto-pair `shadow=False` 與 `canary_stage>=1`（避 §4.4 reject） |

### 2.3 LOC budget

- `executor_config_cache.py`: 613（< 800 警告線 ✅）
- `executor_agent.py`: 971（pre-existing 800 警告區，本任務僅增 ~89 LOC，未推超 1500）
- `test_executor_agent_unit.py`: 809（pre-existing baseline 612 + W-AUDIT-9 197；剛跨 800 警告，pre-existing baseline exception clause 不適用，但 < 2000 硬上限）

---

## 3. 關鍵 diff

### 3.1 `CanaryStage` enum 對齊 Rust

```python
class CanaryStage(enum.IntEnum):
    SHADOW = 0                # binary fail-closed；不送 intent
    PAPER_SINGLE_COHORT = 1   # 1 strategy × 1 symbol × paper（7d）
    DEMO_SINGLE_COHORT = 2    # 1 strategy × 1 symbol × demo（14d）
    DEMO_FULL_UNIVERSE = 3    # 5 active strategies × demo（21d）
    LIVE_PENDING = 4          # operator 顯式拍板

    @classmethod
    def from_raw(cls, value: Any) -> "CanaryStage":
        # fail-closed parse：任何不可解析 → SHADOW
        if value is None: return cls.SHADOW
        if isinstance(value, cls): return value
        try: int_val = int(value)
        except (TypeError, ValueError): return cls.SHADOW
        if 0 <= int_val <= 4: return cls(int_val)
        return cls.SHADOW
```

### 3.2 `_read_canary_stage` provider 優先序（invariant 9）

```python
def _read_canary_stage(self, engine=None) -> "CanaryStage":
    # 1. 優先 stage-aware provider
    if self._canary_stage_provider is not None:
        try:
            raw = self._canary_stage_provider(engine) if engine else self._canary_stage_provider()
            return raw if isinstance(raw, CanaryStage) else CanaryStage.from_raw(raw)
        except Exception:  # invariant 9
            return CanaryStage.SHADOW

    # 2. fallback legacy shadow_mode_provider（投影為 stage）
    if self._shadow_mode_provider is not None:
        try:
            is_shadow = bool(self._shadow_mode_provider(engine) if engine else self._shadow_mode_provider())
            return CanaryStage.SHADOW if is_shadow else CanaryStage.PAPER_SINGLE_COHORT
        except Exception:  # invariant 9
            return CanaryStage.SHADOW

    # 3. 雙 provider 缺失：fail-closed Stage 0
    return CanaryStage.SHADOW
```

### 3.3 backward-compat reject（AMD §4.4）

```python
# legacy `shadow_mode=false` 但 `canary_stage` 缺欄 → reject 至 Stage 0 + log
if shadow_raw is False and stage_raw is None:
    logger.warning("legacy shadow_mode=False without canary_stage detected — "
                   "fail-closed reject Stage 0 （per AMD-2026-05-09-03 §4.4）")
    canary_stage = CanaryStage.SHADOW

# `shadow_mode = (canary_stage == SHADOW)` projection
shadow_projected = canary_stage == CanaryStage.SHADOW
```

### 3.4 backward-compat `shadow_mode_provider` lambda

```python
def shadow_mode_provider(self) -> Callable[..., bool]:
    """Stage 0 → True；Stage ≥ 1 → False（zero-impact migration）。"""
    stage_provider = self.canary_stage_provider()
    return lambda engine=None: stage_provider(engine) == CanaryStage.SHADOW
```

---

## 4. 治理對照

| 條目 | 對照結果 |
|---|---|
| AMD-2026-05-09-03 §2.1 5-stage 定義 | ✅ enum SHADOW/PAPER_SINGLE_COHORT/DEMO_SINGLE_COHORT/DEMO_FULL_UNIVERSE/LIVE_PENDING 對齊 |
| AMD-2026-05-09-03 §2.2 stage 升級條件 | ⚠️ 本任務 IMPL source/test only；自動升級邏輯由 W-AUDIT-9 T4（healthcheck `[58]`）+ T6（manual promote lease）執行 |
| AMD-2026-05-09-03 §4.4 backward-compat | ✅ legacy `shadow_mode=false` 無 `canary_stage` → reject Stage 0 + log |
| AMD-2026-05-09-01 §3 SM-05 invariants | ✅ fail-closed for cache miss / IPC failure / schema failure / provider exception 全保留 |
| TODO v19 §5 invariant 9 | ✅ cache miss / IPC fail / schema fail / provider exception → Stage 0（**不是** Stage 1）— 5 條 unit test 直接 cover |
| TODO v19 §5 invariant 8 | ✅ §二 16 根原則合規（principle #6 失敗默認收縮、principle #4 不繞風控、principle #11 Agent 自主） |
| CLAUDE.md §七 跨平台 | ✅ grep `/home/ncyu` `/Users/[^/]+` = 0 命中 |
| CLAUDE.md §七 雙語注釋 | ✅ MODULE_NOTE + docstring + inline 已升級為 W-AUDIT-9 中文版（per 2026-05-05 governance change：默認中文，原有英文不主動清，動到 block 端只留中文）|
| CLAUDE.md §九 singleton registry | ✅ `_CACHE_INSTANCE` 已登記，無新 singleton |
| CLAUDE.md §九 文件大小 | ⚠️ `test_executor_agent_unit.py` 809 剛過 800 警告；無 pre-existing baseline exception；**< 2000 硬上限**，建議 E2 評估是否拆分（fixtures 可外移） |

---

## 5. 測試結果

### 5.1 Acceptance criteria

```
pytest -k test_executor_config_cache → 39 PASS, 0 FAIL
pytest -k test_canary_stage           → 19 PASS, 0 FAIL
```

### 5.2 Regression suite（executor + agents）

| Test file | Result |
|---|---|
| `test_executor_config_cache.py` | 39 PASS |
| `test_executor_agent_unit.py` | 46 PASS |
| `test_executor_decision_parity.py` | 7 skipped（pre-existing skip）|
| `test_executor_shadow_to_live_e2e.py` | 8 PASS（_make_runtime_config helper 升級後）|
| `test_agent_audit_bridge.py` + 6 sibling | 162 PASS |
| **TOTAL** | **255 PASS / 7 skipped / 0 FAIL** |

### 5.3 Smoke test

```
✅ imports OK
CanaryStage values: ['SHADOW=0', 'PAPER_SINGLE_COHORT=1', 'DEMO_SINGLE_COHORT=2',
                     'DEMO_FULL_UNIVERSE=3', 'LIVE_PENDING=4']
default snapshot stage: CanaryStage.SHADOW
default snapshot shadow: True
agent _read_canary_stage no-provider: CanaryStage.SHADOW
agent _read_shadow_mode no-provider: True
```

invariant 9 確認：ExecutorAgent 無 provider → fail-closed Stage 0（不是 Stage 1）。既有 `shadow_mode_provider unavailable` log 字串保留（test_executor_agent_has_no_unconditional_lambda_true_fallback grep PASS）。

---

## 6. 不確定之處 / 風險

1. **legacy False → Stage 1 投影是否合理？**
   `_read_canary_stage` 在 fallback path（legacy `shadow_mode_provider` 唯一存在）將 `False` 投影至 `PAPER_SINGLE_COHORT`。理由：legacy False 的語義最接近「最低非 shadow 暴露」（單 cohort paper），不能直接跳 Stage 2/3 demo。如 PA / E2 認為 legacy False 應全 reject 至 SHADOW（更嚴格 backward-compat），可改為 Stage 0。當前方案優先 graceful migration，但邊界值得 E2 review。

2. **test_executor_agent_unit.py 809 LOC 跨 800 警告**
   非 hard block，但非 pre-existing baseline exception clause 適用範圍（baseline 612）。建議 E2 評估是否：
   - (a) 接受（< 2000 硬上限，內聚高）
   - (b) 拆 W-AUDIT-9 stage tests 至獨立檔 `tests/test_executor_canary_stage.py`

3. **Rust schema 對齊**
   E1-A 並行做 Rust enum 定義；Python `CanaryStage` 用 IntEnum + integer mirror（per task 指示「schema 通過 IPC payload 對齊，不需等 Rust commit hash」）。Rust enum 名稱 / 序值可能微調 — 若有差異，IPC payload 的 `canary_stage` 是 int 0..=4，`CanaryStage.from_raw` 已具備 fail-closed 容錯。若 Rust 端用 string serde（`"shadow"` / `"paper_single_cohort"`），需 follow-up 加 string parse。

4. **runtime apply 阻塞**
   per cross-wave conflict #2，本任務 source/test IMPL only。完整 runtime 接線（spawn `canary_stage_provider` 至 ExecutorAgent ctor）由 W-AUDIT-3b runtime smoke land 後執行，**不在 T3 範圍**。當前 production wiring 仍走 `shadow_mode_provider`（backward-compat），所有現有行為不變。

5. **canary_cohort.environment string 對齊**
   `CanaryCohort.environment` 接受 `'paper' | 'demo' | 'live_demo' | 'mainnet'` 4 字串（per AMD §4.2 PG schema）。Python 端只做型別保留，不做 enum 化（避免和現有 `_normalize_engine_name` 重複）。E2 review 可決定是否需獨立 `Environment` enum。

---

## 7. 跨 sub-agent 同步狀態

| Owner | 並行任務 | 與 T3 互動 |
|---|---|---|
| E1-A | W-AUDIT-9 T1 Rust schema | 我 mirror IntEnum naming，IPC payload 通過 `canary_stage` int 對齊；不需等 Rust commit |
| E1-B | W-AUDIT-9 T2 V080 migration | 已存在 `sql/migrations/V080__governance_canary_stage.sql`（untracked）；表 `governance.canary_stage_log` / `canary_stage_metric_registry` 由 T4 healthcheck `[58]` 用，不影響 T3 source |
| E1-D | W-AUDIT-9 T6 LeaseScope::CanaryStagePromotion | 已 commit `063f12d0`；T3 不直接依賴，但 manual promote 流程會用 T6 lease scope |
| E2 first-pass review | Day 3-5 | 收到 T3 commit `200188ad` 後跑 review |

---

## 8. Operator 下一步

### 8.1 立即（E2 review 前）

無 — 本 IMPL 已自包含；不需 operator 介入。

### 8.2 E2 second-pass（Day 5-7）後

PM 統一 push 5 個 commit（T1 + T2 + T3 + T4 + T6）至 origin/main，+ ssh trade-core `git pull --ff-only` 同步 Linux runtime。注意 T3 commit `200188ad` **未加 `[skip ci]`**（per task 指示），CI 可在 push 後跑全部 39 + 46 + 8 = 93 個 stage-aware unit test。

### 8.3 W-AUDIT-3b runtime smoke land 後

T3 source/test 已就位，但**未** wire 至 production lifecycle。W-AUDIT-3b 後 PM 派 follow-up：在 ExecutorAgent runtime 構造處（`strategy_wiring.py` 對應 callsite）注入 `canary_stage_provider=cache.canary_stage_provider()`，然後跑 ssh `pytest -k test_executor_fail_closed` + engine restart 後 `[55] chains_with_lease > 0` 驗證（per TODO v19 §5 invariant 20）。

### 8.4 Sprint N+0 Day 5-7 之後

T4 healthcheck `[58]` (E1-D) + T5 GUI surface (E1-E) IMPL 後，graduated canary foundation 可 runtime active；operator 在 Settings tab 顯式選 Stage 1 cohort，T3 的 stage-aware provider 才會回 PAPER_SINGLE_COHORT 而非 SHADOW。

---

## 9. 檔案清單（absolute paths）

- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_config_cache.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_config_cache.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_agent_unit.py`
- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_shadow_to_live_e2e.py`

---

*E1-C report — W-AUDIT-9 T3 shadow_mode_provider stage-aware (Python)*
