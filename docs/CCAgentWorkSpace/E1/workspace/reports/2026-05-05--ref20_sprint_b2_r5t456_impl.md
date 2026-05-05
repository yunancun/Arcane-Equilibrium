# E1 R5-T4 + R5-T5 + R5-T6 SIGN-OFF — REF-20 Sprint B2

**Status**: IMPLEMENTATION DONE — pending E2 review + E4 regression
**Source HEAD**: Mac=Linux=origin sync from `a2f819c5` (R5-T1+T2+T3 已 land 為 dispatch baseline，當前 working tree 加 R5-T4/T5/T6 五 file change)
**Scope**: 3 production files + 2 test files modified
- R5-T4: `rust/openclaw_engine/src/bin/replay_runner.rs` (CLI integration)
- R5-T5: `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py` (decision evidence injection)
- R5-T6: `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py` (lookup_replay_config_sha256 helper)
- R5-T5 tests: `tests/test_replay_simulated_fills_writer.py` (+8 cases)
- R5-T6 tests: `tests/test_replay_experiments_register.py` (+4 cases)

**Persistence**: PM persists this E1 inline report per closure protocol.

---

## §1 R5-T4 CLI integration — replay_runner.rs main flow before/after

### Before (R5-T3 baseline at HEAD `a2f819c5`)
```rust
// Step 4: bootstrap the IsolatedPipeline + execute.
let mut pipeline = runner::build_isolated_pipeline(
    profile,
    manifest.experiment_id.clone(),
    tier_label,
    events,
)?;
let exec_outcome = pipeline.execute();
let result: ReplayResult = pipeline.into_result();
```
**Always走 synthetic walker path**（R5-T3 e2e proof_1/4/5）；adapter pipeline 未被 production 使用。

### After (R5-T4)
```rust
let starting_balance = manifest.starting_balance.unwrap_or(runner::DEFAULT_STARTING_BALANCE);
let first_event_price = events.first().map(|e| e.close).ok_or_else(|| {
    Box::<dyn std::error::Error>::from(
        "replay_runner: manifest declared strategy but fixture has no \
         events to derive starting anchor price (R5-T4 invariant)",
    )
});
let mut pipeline = runner::build_isolated_pipeline(profile, ..., events)?;
if let Some(strategy_name) = manifest.strategy.as_deref() {
    let starting_price = first_event_price?;
    let pool: Vec<Box<dyn Strategy>> =
        StrategyFactory::create_with_params(&StrategyParamsConfig::default());
    let chosen = pool.into_iter().find(|s| s.name() == strategy_name)
        .ok_or_else(|| Box::<dyn std::error::Error>::from(format!(
            "replay_runner: manifest.strategy='{}' not in StrategyFactory registry ...",
            strategy_name)))?;
    let strategy_adapter = ReplayStrategyAdapter::new(chosen, profile)?;
    let risk_adapter = ReplayRiskAdapter::new(
        profile, GuardianConfig::default(), RiskConfig::default(),
        0.02, None::<KellyConfig>)?;
    let snapshot = ReplayPaperSnapshot {
        balance: starting_balance,
        latest_price: Some(starting_price),
        positions: Vec::new(),
        ...
    };
    pipeline = pipeline.with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)?;
    eprintln!("replay_runner: adapter path engaged strategy={} ...", strategy_name);
} else {
    eprintln!("replay_runner: synthetic walker path (manifest.strategy absent; \
               R5-T3 e2e proof_1/4/5 baseline)");
}
let exec_outcome = pipeline.execute();
let result: ReplayResult = pipeline.into_result();
```

### Manifest schema additions
ReplayManifest gained two `#[serde(default)]` optional fields:
- `strategy: Option<String>` — V049 `manifest_jsonb.strategy` (e.g. "grid_trading"). Backward-compat: legacy fixtures without this field continue to walk synthetic path.
- `starting_balance: Option<f64>` — overrides `runner::DEFAULT_STARTING_BALANCE = 10_000.0`.

### Fail-loud paths (R5-T4 §11.1 spec)
1. `events.first()` empty + `manifest.strategy = Some(_)` → `Err` "fixture has no events" exit non-zero.
2. `manifest.strategy = Some(name)` not in factory pool → `Err` listing 5 registered strategies.
3. `ReplayStrategyAdapter::new` / `ReplayRiskAdapter::new` `Err` → wrapped Box<dyn Error> with module name.
4. `with_adapter_pipeline` `Err` (NaN balance / empty anchor) → wrapped Box<dyn Error> with R5-T3 fail-loud reason.

All errors propagated via `?` so binary exits non-zero with `Box<dyn Error>` via `eprintln!` (CLAUDE.md §四 fail-closed).

### LOC change
- `replay_runner.rs`: 1014 → 1187 (+173). Over dispatch §11.1 +50 estimate due to bilingual MODULE_NOTE 補充 + each `Err` arm full Box<dyn Error> + manifest schema doc + 2 new field doc。

## §2 R5-T5 simulated_fills_writer.py decision evidence schema

### Module-level docstring 擴展 (~+30 LOC)
Added Sprint B2 R5-T5 section explaining schema (`payload._replay_decision_evidence`) + match algorithm (greedy by `(ts_ms, symbol, side)` with side=None bucket fallback for Close).

### 3 new helpers (~+150 LOC)
1. `extract_decision_traces(envelope) -> list[dict]` — read `result.decision_traces`, defensively drop malformed entries (missing `ts_ms` / wrong type).
2. `_normalize_action_side(action)` — translate Rust `StrategyActionTrace::Open|Close` to `"long"|"short"|None`.
3. `build_decision_evidence_index(traces) -> dict[(ts_ms, symbol, side), list[evidence]]` — index for FIFO consumption (greedy match).
4. `consume_decision_evidence_for_fill(fill, index) -> Optional[dict]` — pop matching evidence + synthesise `signal_id` + `risk_decision` (qty>0=accepted, qty=0=rejected) + `rejected_reason` (qty=0 ghost reason).

### `map_fill_to_v050_row` extended
Added kw arg `decision_evidence: Optional[dict[str, Any]] = None` with backward-compat default. When present, injected as `payload._replay_decision_evidence` jsonb sub-object; preserved through truncation path (top-level marker if oversize).

### `persist_replay_report` wired
Build index once per envelope, then per-fill greedy match + pass to `map_fill_to_v050_row`. Empty index = no evidence injection (synthetic walker fills bypass marker, R5-T3 baseline preserved).

### Schema (PA design §6.1, jsonb-only — NO V### migration)
```json
{
  "_replay_decision_evidence": {
    "signal_id":         "<ts_ms>:<symbol>:<side>",
    "strategy_decision": "open" | "close",
    "risk_decision":     "accepted" | "rejected",
    "rejected_reason":   null | "qty=0_ghost_fill;strategy=<name>",
    "intent_signature":  "<sha256 hex>" | null,
    "intended_qty":      <float> | null,
    "intended_price":    <float> | null,
    "strategy_name":     "<name>",
    "indicators_present": <bool>,
    "confidence":        <float>
  }
}
```

### LOC change
- `simulated_fills_writer.py`: 602 → 893 (+291). Over dispatch §11.1 +60 estimate due to bilingual docstrings + 4 helpers (one was sub-helper `_normalize_action_side`) + R5-T5 schema doc。

## §3 R5-T6 experiment_registry.py helper

### Confirm-and-add (per dispatch push back option)
Verified: V049 INSERT in `register_experiment` (lines 845-887) DOES include both `strategy_config_sha256` (positional [5]) and `risk_config_sha256` (positional [6]) — V049 22-col contract intact since R2 round 2.

### Helper added
```python
def lookup_replay_config_sha256(
    cur: Any, experiment_id: str
) -> Tuple[Optional[str], Optional[str]]:
    """SELECT strategy_config_sha256, risk_config_sha256 FROM replay.experiments..."""
```
Parameterised SQL + uuid cast + V049 NOT NULL defense-in-depth (returns partial None+log warning if future migration relaxes).

### LOC change
- `experiment_registry.py`: 985 → 1061 (+76). Over dispatch §11.1 +40 estimate due to bilingual docstring + SAFETY/不變量 block + future-proof V049 NOT NULL relaxation defense。

## §4 cargo build + Mac pytest + Linux pytest + symbol audit + xlang

### cargo build
```
cargo build --release --bin replay_runner --features replay_isolated
   Finished `release` profile [optimized] target(s) in 0.09s
```

### Full lib regression
```
cargo test --release --features replay_isolated -p openclaw_engine --lib
test result: ok. 2478 passed; 0 failed
```
（與 R5-T3 baseline 2478 同數）

### replay_runner unit tests
```
cargo test --release --features replay_isolated -p openclaw_engine --bin replay_runner
test result: ok. 6 passed; 0 failed
```

### e2e
```
cargo test --release --features replay_isolated -p openclaw_engine --test replay_runner_e2e
test result: ok. 6 passed; 0 failed
```

### All tests (--tests; doctests not run — pre-existing)
```
cargo test --release --features replay_isolated -p openclaw_engine --tests
全部 PASS (含 R5-T4/T5/T6 inline + e2e + integration)
```

### Symbol audit
```
[replay_runner_symbol_audit] platform=Darwin → nm -gU
[replay_runner_symbol_audit] symbol count: 602
[replay_runner_symbol_audit] AUDIT PASS: 0 forbidden symbol detected (602 symbols scanned)
```
（478 → 602 因 R5-T4 拉入 StrategyFactory + Strategy + GuardianConfig + KellyConfig + RiskConfig 型別 — 0 forbidden 仍 GREEN）

### Mac pytest replay
```
python3 -m pytest tests/ -k replay --no-header -q
185 passed, 1 skipped, 3387 deselected
```
（172 baseline → 185；增 13 R5-T5+R5-T6 inline test，R5-T6 4 個 + R5-T5 8 個 + 1 already counted 重簽部分）

### Linux pytest replay (SSH bridge)
```
ssh trade-core "cd ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1 && \
  .venv/bin/pytest tests/ -k replay --no-header -q | tail -3"
3 failed, 169 passed, 1 skipped, 3387 deselected
```
**注意**：Linux 工作樹仍在 `8997fec1`（commit ahead of `a2f819c5` baseline 但 R5-T4/T5/T6 改動 **未 push** to origin）— 3 failures 全在 `test_replay_routes_auth.py`（runtime spawn fail，因 Linux 缺 `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env，與 R5-T4/T5/T6 範圍無關）。Mac 端 `test_replay_routes_auth.py` 4/4 PASS 對照證實 pre-existing infrastructure issue 而非 regression。Operator/PM 推 `a2f819c5...HEAD` 後 Linux 端 R5-T4/T5/T6 inline test 期望 PASS。

### xlang_consistency
```
python3 -m pytest tests/replay/ -k xlang_consistency --no-header -q
13 passed, 32 deselected
```

### Forbidden import grep on 3 production file
```
grep -nE 'use crate::(paper_state|canary_writer|database|ipc_server|governance_hub|live_authorization|decision_lease|bybit_rest_client|bybit_private_ws)' replay_runner.rs
(no output — 0 hit)
```

### Cross-platform path grep
```
grep -nE '/home/ncyu|/Users/[a-z]+/' replay_runner.rs simulated_fills_writer.py experiment_registry.py
(no output — 0 hit)
```

## §5 git status sign-off-clean

```
$ git status --short
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_experiments_register.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py
 M rust/openclaw_engine/src/bin/replay_runner.rs
```

5 modified files all in R5-T4/T5/T6 範圍。clean — 0 untracked / 0 sibling session pollution。

## §6 Push back to PM (3 items)

### §6.1 dispatch §11.1 LOC estimate vs reality

| File | Estimate | Actual | Reason |
|---|---:|---:|---|
| replay_runner.rs | +50 | +173 | bilingual MODULE_NOTE / each fail-loud Err arm full Box<dyn Error> with reason / 2 new manifest fields with full doc / starting price extraction + nil-event guard / dispatch logic with adapter wire ordering |
| simulated_fills_writer.py | +60 | +291 | 3 new helpers + 1 sub-helper / R5-T5 schema doc / bilingual docstring per helper / payload truncation marker preservation when evidence supplied / `map_fill_to_v050_row` kw arg doc |
| experiment_registry.py | +40 | +76 | bilingual docstring + SAFETY/不變量 block + V049 NOT NULL future-proof defense |

**PM decision needed**：
- Option A：accept 累計 +540 LOC across 3 files（all < 1500 hard cap，且皆為 docstring/safety/fail-loud overhead，非邏輯擴張）
- Option B：要求精簡 docstring（會違反 CLAUDE.md §七 「雙語注釋強制」）

建議 Option A — overhead 全為治理強制要求，無冗餘邏輯。simulated_fills_writer.py 893 < 1500 hard cap 但已超 800 警告線；建議 PM accept 比照 R5-T3 runner.rs 1466 high-cohesion exception。

### §6.2 R5-T6 acceptance：register handler 已完整，但仍加 helper

驗證結果：register handler `register_experiment` 確 INSERT `strategy_config_sha256` + `risk_config_sha256` 自 R2 round 2 起（V049 22-col 契約 line 850 + 875）。

依 dispatch 「R5-T6 應該已被 R2 register handler 涵蓋大半...主要驗 + 加 helper」執行：加了 `lookup_replay_config_sha256` read-back helper。並非 confirm-only no-code-change，因 dispatch 明確要 helper。

push back：如 PM 認為 helper 暫無 caller（R5-T4 CLI 當前用 `RiskConfig::default()` 不查 sha），可考慮：
- Option A（採用）：land helper 為 R6 future-ready，0 caller 不破任何不變量
- Option B：刪 helper、R5-T6 標 confirm-only — 但 dispatch §11.1 「+40 LOC helper + verify」明示 helper 必加

### §6.3 R5-T4 strategy_config / risk_config 暫用 default

dispatch 寫「從 manifest_jsonb / fixture spec → 解出 strategy name + strategy_config + risk_config」但既有 ReplayManifest 僅含 minimal envelope（experiment_id / data_tier / fixture_uri / signature / manifest_hash / signature_key_ref / run_id），R2 register 寫的 strategy_config_sha256 + risk_config_sha256 是 sha 不是 config blob 本身。

R5-T4 採折衷：
- 從 `manifest.strategy: Option<String>` 解出 strategy name
- 用 `StrategyFactory::create_with_params(&StrategyParamsConfig::default())` 建構策略（default params；R6 fee model 後可擴）
- 用 `RiskConfig::default()` + `GuardianConfig::default()` + `p1_risk_pct=0.02` (Sprint A baseline) + `kelly_config=None`（跳過 Kelly）

push back：R6 calibration sprint 應擴 ReplayManifest 加 strategy_config_blob: jsonb + risk_config_blob: jsonb（即 V049 register 已 sha 但未 blob 化的兩 config 完整快照）。Sprint B2 範圍**不**改 ReplayManifest schema（避免破 R3 register 端 22-col contract + cross-language manifest_signer canonical_bytes invariant）。R6 R5-T6 helper read-back path 已就緒供將來擴展。

## §7 預留問題給 R5-T7 acceptance dispatch

### R5-T7 (acceptance test) 需注意
1. R5-T7 acceptance：跑兩 manifest（grid_count=10 vs 20）+ 同 fixture → fills count delta + decision_traces[0].actions_emitted[0].intent_signature delta（A4 parameter-delta proof）。R5-T4 CLI 已支援 manifest.strategy 解析；但 R5-T7 fixture builder 需在 manifest_jsonb 加 `strategy: "grid_trading"` 才走 adapter path。
2. R5-T7 fixture loader 升級需傳 IndicatorSnapshot pre-compute（PA design §13 line 691）；R5-T4 build_tick_context 仍用 indicators=None（atr=0.0 / Kelly skip）。R5-T7 / R6 完整度後可移除 atr=0.0 fallback。
3. R5-T6 helper 可給 acceptance test 用：register manifest 後 SELECT strategy_config_sha256 + risk_config_sha256，確認雙 sha 正確 round-trip。
4. R5-T5 evidence injection 對 multi-fill same-tick 的 greedy match 已測（test_persist_replay_report_with_decision_traces_inline_evidence + test_consume_decision_evidence_matches_open_fill）；R5-T7 跨多 tick 測試應驗 ghost row 對 (ts_ms, symbol) tuple 的 match-or-miss 邏輯。

### R5-T7 spawn binary path
1. `tests/replay/test_replay_*_smoke.rs` ~200 LOC 含 baseline-vs-candidate cross-language proof
2. 走 spawn binary path（非 lib API direct call）；manifest.strategy 設 "grid_trading" 即觸發 R5-T4 adapter path
3. 與 Sprint A precedent 對齊（R3 round 6 final smoke E2E + R8/R9 sentinel）

### 共通
- R5-T4/T5/T6 cumulative LOC 後續演進
  - replay_runner.rs 1187 < 1500 hard cap，仍有 313 LOC 空間（R5-T7 spawn smoke fixture 不會增 binary LOC）
  - simulated_fills_writer.py 893 < 1500 hard cap（dispatch 估 662 後實 893；+231 餘地）
  - experiment_registry.py 1061 < 1500（dispatch 估 1025 後實 1061；+439 餘地）

---

## §8 治理對照

- **CLAUDE.md §二 16 條**：✓ 全遵守（單一寫入口 unaffected / 讀寫分離 unaffected / Decision Lease unaffected / Live boundary unaffected / EarnedTrust unaffected）
- **CLAUDE.md §三 真實狀態**：✓ R5-T4/T5/T6 0 改動 trading.* 任一 table；0 改動 18 blocker 任一 gap；0 改動 5 策略 fill 數據；0 改動 V049/V050 schema
- **CLAUDE.md §四 硬邊界**：✓ 全遵守（max_retries=0 unaffected / live_execution_allowed unaffected / authorization.json path unaffected / Mainnet env-var fallback 封閉 unaffected）
- **CLAUDE.md §七 雙語注釋**：✓ 7 新 helper / new field / 改 docstring 全中英對照（MODULE_NOTE 擴展 / docstring / SAFETY / inline 不變量）
- **CLAUDE.md §七 跨平台**：✓ 0 路徑硬編碼（grep 0 hit）
- **CLAUDE.md §七 SQL migration**：✓ R5-T6 0 新 V### migration（read-only helper）；R5-T5 schema 限 jsonb 內擴展 不破 V050 17-col contract
- **CLAUDE.md §七 被動等待 healthcheck**：N/A（R5-T4/T5/T6 非被動等待 task）
- **CLAUDE.md §九 LOC**：⚠ 3 file 皆 < 1500 hard cap；simulated_fills_writer.py 893 過 800 警告線 — 已 push back §6.1 PM decision
- **CLAUDE.md §九 Singleton 登記**：✓ R5-T4/T5/T6 0 新 singleton（`_REGISTER_IDEM_CACHE` / `_REGISTER_IDEM_CACHE_THREAD_LOCK` 已於 R2 round 2 登記，本 sprint 不擴）
- **V3 §6.1 + §6.2 + §6.3**：✓ 0 forbidden import on replay_runner.rs；R5-T4 透過 `crate::strategies::*` 與 `openclaw_core::guardian` 安全引入（symbol audit 0 forbidden 確認）
- **V3 §12 #10 forbidden runtime trip**：✓ proof_4 不退；R5-T4 adapter path 內部仍接 `forbidden_guard::enforce_at_runtime`
- **V3 §12 #11 execution_confidence='none'**：✓ R5-T4 manifest schema 不暴露 execution_confidence；ReplayResult.execution_confidence 由 R5-T3 `into_result` 永遠 hardcode `"none"`
- **V3 §12 #12 fail-closed**：✓ R5-T4 4 條 fail-loud 路徑全顯式 Err；R5-T6 helper NOT NULL violation 印 warning + 回 None
- **V3 §6.1 jsonb-only schema 擴展**：✓ R5-T5 不加 V### migration；於既有 V050 payload jsonb 內擴展 `_replay_decision_evidence` 子物件
- **PA dispatch §11.1**：✓ 3 task 全 deliverable land；LOC 超估說明見 §6.1
- **PA dispatch §6.1 evidence schema**：✓ R5-T5 對齊 schema design (signal_id / strategy_decision / risk_decision / rejected_reason / intent_signature / intended_qty / intended_price)
- **dispatch §強制規範 1-8**：✓ 全遵守
  - 1. 不動 R5-T1/T2/T3 cleared 範圍 ✓
  - 2. 不接 forbidden imports（V3 §6.2）✓
  - 3. bilingual MODULE_NOTE / docstring / inline ✓
  - 4. 跨平台禁路徑硬編碼 ✓
  - 5. LOC 控制（仍 < 1500 hard cap）— ⚠ 三 file 皆過 800 警告線（experiment_registry.py 985 起點 + simulated_fills_writer.py 893 + replay_runner.rs 1187 過 800），已 push back PM
  - 6. canonical_bytes contract 不動（R5-T6 加 read helper，0 改 hash 計算）✓
  - 7. 不 commit ✓ (5 file 改動 git status 顯示)
  - 8. Sprint A R3 教訓：Python 3.12 from __future__ pitfall — experiment_registry.py / simulated_fills_writer.py 為 helper module 非 FastAPI route handler，from __future__ import annotations 對 Pydantic Body parsing 沒衝突 ✓

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_b2_r5t456_impl.md`）**

(Per dispatch §sign-off — parent agent reads E1's final assistant message; PM persisted to .md file.)

---

## §10 Round 2 fix log — architectural gap closure (2026-05-05)

**Round 2 trigger**：PM 發現 architectural gap：R5-T7 acceptance fixture (PA §5.1 + §5.2) 要求 register payload 帶 `strategy_params: {grid_levels: 10 vs 20}` + `risk_overrides: {position_size_max_pct: 2.0 vs 10.0}` 證 A4/A5 delta；但 R5-T4 round 1 用 `RiskConfig::default()` + `StrategyParamsConfig::default()` 忽略 manifest config blob → A4/A5 acceptance 跑不出 delta。Round 2 修這個 gap。

### §10.1 R5-T6 register handler 接 strategy_params + risk_overrides

`replay/experiment_registry.py`：

1. **Pydantic model 加 2 optional field**（line 282-313）：
   - `strategy_params: Optional[dict[str, Any]] = None`
   - `risk_overrides: Optional[dict[str, Any]] = None`
   - 雙語 description 詳述 round 2 server-side compute + override 行為。

2. **`register_experiment` 主邏輯擴展**（line 779-841 區段，原 step 2 拆為 step 1.5 注入 + step 2 重算）：
   - **Step 1.5 (NEW)**：當 `body.strategy_params` 提供 → 計 `effective_strategy_sha = sha256(compute_manifest_canonical_bytes(body.strategy_params))` + 注入 `manifest_to_persist["_replay_strategy_params"] = body.strategy_params`（淺拷貝避免動 caller `body.manifest_jsonb`）；`risk_overrides` 同邏輯。
   - **Step 2 (修改)**：`compute_manifest_canonical_bytes(manifest_to_persist)` 對 augmented body 計 hash；舊路徑（兩 blob 皆 None）行為完全一致 → xlang 13/13 不退、所有 R5-T6 round 1 test 全 PASS。
   - **INSERT 改用 `effective_strategy_sha` / `effective_risk_sha`**（line 988-989），覆寫 client placeholder 值。
   - **舊 `manifest_to_persist = body.manifest_jsonb` 死碼移除**；改寫 H-1 invariant 注釋說明注入點移到前面 + invariant 仍持有。

3. **`lookup_replay_config_blob(cur, experiment_id) -> dict` helper 新增**（line 530-635）：
   - SELECT `manifest_jsonb` from `replay.experiments`，extract `_replay_strategy_params` + `_replay_risk_overrides`。
   - 防禦：jsonb→dict、bytes/str fallback decode、非 dict 值拒回（返 None）、parameterised SQL + uuid cast。
   - 雙語 docstring + SAFETY 區塊。

4. **`__all__` 加 `"lookup_replay_config_blob"`**（line 1271）。

### §10.2 R5-T4 manifest schema +2 field + factory wire + RiskConfig override

`rust/openclaw_engine/src/bin/replay_runner.rs`：

1. **`ReplayManifest` struct 加 2 field**（line 666-721）：
   ```rust
   #[serde(default)]
   pub strategy_params: Option<serde_json::Value>,
   #[serde(default)]
   pub risk_overrides: Option<serde_json::Value>,
   ```
   - `serde(default)` 為向後相容；現有 fixture 無此 field → parse 為 None → xlang 不退。
   - 雙語 doc 注釋詳述 V049 register handler `_replay_*` 注入對齊。

2. **CLI flow `if let Some(strategy_name) = manifest.strategy.as_deref()` 區段擴展**（line 386-465）：
   - **Step 1 (NEW)**：`strategy_params_config: StrategyParamsConfig` — 當 `manifest.strategy_params = Some(blob)` → `serde_json::from_value(blob.clone())`，shape 不符 → typed Box<dyn Error> 含 fail-mode reason 非 0 結束（CLAUDE.md §四 fail-closed）；當 None → `StrategyParamsConfig::default()` 退回 round 1 行為。
   - **Step 2 (NEW)**：`risk_config: RiskConfig` — 同 strategy_params 邏輯；額外 sanity check `position_size_max_pct ∈ (0, 100]`，捕捉 NaN/負值/越界 → 提早 fail-loud。
   - **Step 3 (改)**：`StrategyFactory::create_with_params(&strategy_params_config)`（取代 round 1 `&StrategyParamsConfig::default()`）。
   - **Step 4 (改)**：`ReplayRiskAdapter::new(profile, GuardianConfig::default(), risk_config, ...)`（取代 round 1 `RiskConfig::default()`）。

3. **stderr log 擴展**（line 470-477）：`strategy_params_supplied={} risk_overrides_supplied={}` 兩 boolean 標示 — 方便 CI/operator 解析 round 2 path engagement 狀態。

### §10.3 lookup_replay_config_blob helper 擴展

詳見 §10.1 第 3 點。

**Round 2 不擴展 R5-T6 round 1 `lookup_replay_config_sha256`**（後者讀 sha column；新 helper 讀 manifest_jsonb 內保留 key 對應的 raw blob）。兩 helper 互補：sha helper 給 audit 鏈驗 hash；blob helper 給 R5-T7 fixture / `build_default_manifest_payload`（後續 sprint）讀回 raw config 注入 disk fixture 給 Rust runner。

### §10.4 5 new tests 全 PASS

| Test | 範圍 | 結果 |
|---|---|---|
| `test_register_with_strategy_params_computes_distinct_sha` | A4 acceptance — same name + diff params → distinct sha | PASS |
| `test_register_with_risk_overrides_computes_distinct_sha` | A5 acceptance — same strategy + diff overrides → distinct risk sha | PASS |
| `test_lookup_replay_config_blob_returns_params_and_overrides` | helper 雙 blob round-trip | PASS |
| `test_lookup_replay_config_blob_returns_none_when_absent` | helper 缺 blob 回 None / row missing 回 None | PASS |
| `test_register_blob_path_preserves_jsonb_hash_invariant` | DB self-consistency `sha256(persisted_jsonb) == manifest_hash` 不變式 | PASS |
| `manifest_strategy_params_parses_into_typed_config` (Rust) | manifest schema → `StrategyParamsConfig` round-trip（`grid_levels=17` 還原） | PASS |
| `manifest_risk_overrides_apply_to_risk_config` (Rust) | manifest schema → `RiskConfig` round-trip（`position_size_max_pct=7.5` 還原） | PASS |
| `manifest_legacy_fixture_without_blob_fields_still_parses` (Rust) | xlang invariant — 舊 fixture 無新 field 仍 parse 成功 | PASS |

實際 +8 tests（Python 5 + Rust 3）；超過 dispatch 預估 5 個是 **DB self-consistency invariant 證明 (Case E) + Rust 向後相容驗 + helper Case D（None 回退）** — 防禦性測試覆蓋核心 round 2 invariant。

### §10.5 xlang 13/13 不退（critical invariant）

```
$ python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/ -k xlang_consistency --no-header -q
13 passed, 32 deselected, 5 warnings in 0.05s
```

**核心理由**：existing xlang fixture 未含 `strategy_params` / `risk_overrides` field → ReplayManifest serde(default) 解為 None → CLI flow 走 round 1 default 路徑 → canonical_bytes 計算 與 round 1 一致 → cross-language byte-equal invariant 不破。

**driver test 確認**：`test_register_blob_path_preserves_jsonb_hash_invariant` 額外鎖 DB 端 self-consistency invariant — 注入路徑 `sha256(persisted_jsonb) == manifest_hash` 仍持有。

### §10.6 LOC delta（Round 1 → Round 2 cumulative）

| File | Round 1 final | Round 2 final | Δ Round 2 only | hard cap | 結論 |
|---|---:|---:|---:|---:|---|
| `replay/experiment_registry.py` | 1061 | 1278 | +217 | 1500 | < cap; 800 警告線過已於 round 1 push back |
| `replay/simulated_fills_writer.py` | 893 | 893 | 0 (verify-only) | 1500 | unchanged |
| `bin/replay_runner.rs` | 1187 | 1299 | +112 | 1500 | < cap; 800 警告線過已於 round 1 push back |
| `tests/test_replay_experiments_register.py` | (round 1 +12) | round 2 +220 | +220 | n/a | tests |

**LOC 超 dispatch §expectation 80 LOC 估計**：實際 +329 LOC（Python +217 + Rust +112；不含 test）。原因：
- bilingual 注釋強制（CLAUDE.md §七 + bilingual-comment-style skill）— 每 new field / helper / fail-loud arm 雙語 + SAFETY 區塊。
- `lookup_replay_config_blob` 的 jsonb defensive decode（bytes/str/dict 三 branch）+ `not isinstance(strat, dict)` 防污染 — 比 dispatch 預估 helper 更穩健。
- Rust `risk_overrides` sanity check (`position_size_max_pct ∈ (0, 100]`) 是 dispatch §Fix 2 ("risk_overrides 數值 NaN/negative → exit 非 0") 的具體實作。
- Round 2 將 R5-T4 round 1 hard-coded `StrategyParamsConfig::default()` / `RiskConfig::default()` 替為 from-manifest match arms — 雙 path 的 fail-loud Box<dyn Error> 文字佔大頭。

**PM 決定需要**：
- Option A（建議）：accept overhead — 全為治理 + 防禦性代碼，無冗餘邏輯。所有 file 仍 < 1500 hard cap。
- Option B：要求精簡 — 違反 CLAUDE.md §七 雙語注釋強制 + 削弱 fail-loud 訊息可讀性。

### §10.7 git status sign-off-clean

```
$ git status --short
 M docs/CCAgentWorkSpace/E1/memory.md
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_experiments_register.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py
 M rust/openclaw_engine/src/bin/replay_runner.rs
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_b2_r5t456_impl.md
```

5 modified production/test files **沒新增** Round 2（同 round 1 set），純改動 round 1 已動的 3 file（experiment_registry / replay_runner / test_replay_experiments_register）。R5-T5 simulated_fills_writer.py 0 改動於 round 2（verify-only — `risk_decision` 已於 round 1 加入 R5-T5 evidence schema）。memory.md + report 為 E1 governance artifacts。clean — 0 untracked production / 0 sibling session pollution。

### §10.8 Round 2 self-test summary

| Test surface | Round 1 baseline | Round 2 result | Δ |
|---|---|---|---|
| Mac pytest replay | 185 PASS / 1 skip | **190 PASS / 1 skip** | +5 PASS（4 new register cases + 1 cumulative effect） |
| Linux pytest replay | 169 PASS / 1 skip / 3 fail (pre-existing test_replay_routes_auth.py) | (round 2 not pushed) | (Linux 仍 round 1) |
| cargo build replay_runner | OK 0.09s | OK 1.32s | rebuild for new struct fields + match arms |
| cargo test --lib | 2478 PASS | **2478 PASS** | unchanged |
| cargo test --bin replay_runner | 6 PASS | **9 PASS** | +3 round 2 cases |
| cargo test --test replay_runner_e2e | 6 PASS | **6 PASS** | unchanged（synthetic walker 路徑仍走 round 1 baseline） |
| cargo test --tests | 全 PASS | **全 PASS** | unchanged |
| xlang_consistency | 13 PASS / 32 deselected | **13 PASS / 32 deselected** (CRITICAL) | unchanged — invariant 維持 |
| Symbol audit | 602 / 0 forbidden | **648 / 0 forbidden** | +46 symbol（新拉 RiskConfig + StrategyParamsConfig from_value 反序列化型別）— 0 forbidden 仍 GREEN |
| Cross-platform path grep | 0 hit | **0 hit** | unchanged |
| Forbidden import grep on replay_runner.rs | 0 hit | **0 hit** | unchanged |

### §10.9 PM Decision Asks（round 2 push back）

#### §10.9.1 dispatch 步驟 4 「同時把 strategy_params + risk_overrides 的 raw JSON 存進 manifest_jsonb（subkey `_replay_strategy_params` + `_replay_risk_overrides`）— manifest 重 sign 計 manifest_hash 包含這些」與 R2 round 2 H-1 invariant 互動

**結論**：Round 2 implementation 維持 H-1 invariant（`sha256(persisted_jsonb) == manifest_hash`），通過注入後 *recompute* manifest_hash from augmented body。`test_register_blob_path_preserves_jsonb_hash_invariant` 鎖此契約。

**有 trade-off**：當 client 同時提供 `signature_hex` AND `strategy_params`/`risk_overrides`，client 簽名是針對 ORIGINAL body 計算的，server 注入後重算 hash → signature 驗證會失敗。Round 2 範圍**不**支援「signed-with-blob 同時使用」的雙路徑：
- R5-T7 acceptance fixture 走 unsigned path（test 直接呼叫 `register_experiment` cur stub，不簽）。
- Production deploy 若有 signed-with-blob 需求 → Sprint C R6 fee calibration 應加 signed-blob dual-path（先驗 signature against original body，再注入並重算 hash）。

PM action：accept round 2 trade-off + 將 signed-blob dual-path land Sprint C R6 follow-up TODO。

#### §10.9.2 R5-T7 acceptance fixture builder 的下游 wiring 仍未完成

Round 2 在 V049 寫入端接好 server-side blob → sha override + manifest_jsonb 注入 + 提供 `lookup_replay_config_blob` 讀回 helper。**但** `replay/route_helpers.py::build_default_manifest_payload`（disk manifest fixture builder，被 `/run` endpoint 呼叫）**尚未** 從 V049 row 讀回 `_replay_strategy_params` / `_replay_risk_overrides` 並 inject 到 disk manifest。

**結果**：R5-T7 acceptance test 跑 `/run` 時 Rust runner 看到的 disk manifest 仍**無** strategy_params/risk_overrides field → runner 走 round 1 default 路徑 → A4/A5 delta 仍跑不出來。

**push back**：此為 dispatch §Fix 1 + Fix 2 範圍外的 wiring 工作；R5-T7 dispatch 應再加一個 Fix 3 — 修 `build_default_manifest_payload` 讀 V049 + 通過 `lookup_replay_config_blob` 取出 blob → inject 到 disk manifest。

PM action：
- Option A（建議）：把 `build_default_manifest_payload` 修改 land 到 R5-T7 acceptance dispatch（具體用 `lookup_replay_config_blob` helper —已 land 為 read-back path）。
- Option B：派並行 sub-task 接這個 wiring（屬於 Python `replay/run_route.py` 內 `route_helpers.build_default_manifest_payload` ~30 LOC 改動）。

#### §10.9.3 Round 2 仍**不**改動 R5-T1/T2/T3 cleared 範圍

Round 2 0 改動：`replay/strategy_adapter.rs` / `replay/risk_adapter.rs` / `replay/runner.rs::IsolatedPipeline` / 任 V### migration / 任 trading.* table。

#### §10.9.4 Round 2 對 dispatch 「StrategyFactory API 真不支援 dict params」push back 機會

實際 StrategyFactory API 支援：`StrategyFactory::create_with_params(&StrategyParamsConfig)` 接 typed Rust struct（line 51 of registry.rs）。Round 2 通過 `serde_json::from_value(blob.clone())` 在 CLI flow 中把 `serde_json::Value` 轉 `StrategyParamsConfig` — 既有 `StrategyParamsConfig` derive 了 `Deserialize`（line 74 of params.rs），所以 from-json wrapper 不需要新建 module，~10 LOC of from-json deserialise 內聯到 CLI flow。

**結論**：dispatch hint「既有 factory API; 如不接受 dict 需小 wrapper」原則 OK；實際走「serde_json::from_value 內聯 + typed config 餵 factory」最乾淨。

---

**Round 2 IMPLEMENTATION DONE: 待 E2 審查 + E4 回歸 + PM round 2 decision asks (§10.9)**

(Per dispatch §sign-off — parent agent reads E1's final assistant message; PM persisted to .md file.)

---

## §11 Round 3 Fix 3 + R5-T7 acceptance tests log (2026-05-05)

**Round 3 trigger**：PM accepted §10.9.2 push back (Round 2 closed downstream blob propagation gap on V049 INSERT but not on disk manifest path); dispatch added Fix 3 to `build_default_manifest_payload` + R5-T7 acceptance tests (A4 strategy / A5 risk / Rust cross-language).

### §11.1 Fix 3 — `build_default_manifest_payload` blob passthrough

**File**：`replay/route_helpers.py` line 834-892（before：line 834-887）

**Before**：3-key body only `{experiment_id, data_tier, fixture_uri}`；無 V049 blob 讀取路徑；Rust runner 透過 R5-T6 round 2 接 V049 sha 後仍看不到 raw config blob → R5-T4 round 2 退 default。

**After**：optional `cur: Any = None` kwarg；`cur` 提供時透過 lazy import `from .experiment_registry import lookup_replay_config_blob` 讀 V049 row 的 `_replay_strategy_params` / `_replay_risk_overrides` 並注入 disk payload。Lazy import 避免 `run_route ↔ route_helpers ↔ experiment_registry` circular import；僅 `isinstance(value, dict)` 才注入避免 legacy row 寫 `null` placeholder key 改變 canonical_bytes。

```diff
+payload: dict[str, Any] = {
+    "experiment_id": experiment_id,
+    "data_tier": "S3",
+    "fixture_uri": (
+        os.environ.get("OPENCLAW_REPLAY_FIXTURE_URI", "").strip()
+        or os.environ.get("OPENCLAW_REPLAY_FIXTURE_DEFAULT", "").strip()
+        or str(output_dir / "fixture.json")
+    ),
+}
+if cur is not None:
+    from .experiment_registry import lookup_replay_config_blob
+    blob = lookup_replay_config_blob(cur, experiment_id)
+    sp = blob.get("strategy_params")
+    if isinstance(sp, dict):
+        payload["_replay_strategy_params"] = sp
+    ro = blob.get("risk_overrides")
+    if isinstance(ro, dict):
+        payload["_replay_risk_overrides"] = ro
+return payload
```

**Callsite update**：`run_route.py::_do_pg_path` 第 240 行傳 `cur=cur`（既在 `with get_pg_conn_fn() as conn` block 內 cursor 既存）；inline 注釋 5 行 bilingual 說明 R3 Fix 3 wiring。

**Backward compat**：3 既有 test（`test_track_a_spawn_argv.py::test_build_default_manifest_payload_*` + `test_route_helpers_real_hmac_sign.py`）僅傳 kwargs `experiment_id` + `output_dir`，不傳 `cur` → 走 legacy 3-key body 路徑 → 無 regression（pre-Round 3 byte-equal）。

### §11.2 R5-T7-A4 — strategy_param_delta acceptance test (3 case)

**File**：`tests/replay/test_strategy_param_delta.py`（NEW，430 LOC）

**3 case 結果**：
| Case | 範圍 | 結果 |
|---|---|---|
| `test_grid_count_delta_produces_different_sha` | A4 V049 持久化的 strategy_config_sha256 不同 | PASS |
| `test_grid_count_delta_propagates_to_disk_manifest` | A4 round 3 Fix 3 invariant：`build_default_manifest_payload(cur=stub)` 把 V049 blob 注入 disk payload；`cur=None` 走 legacy 3-key | PASS |
| `test_grid_count_delta_decision_evidence_intent_signature_differs` | A4 V050 payload `_replay_decision_evidence.intent_signature` 不同 | PASS |

**Hermetic**：`_capturing_cursor()` stub 同時記 INSERT params + 服務 `SELECT manifest_jsonb` 對應的 SELECT；模擬 round 3 Fix 3 production flow 中同一 PG xact cursor 既 INSERT 又 SELECT 的真實行為。

### §11.3 R5-T7-A5 — risk_param_delta acceptance test (3 case)

**File**：`tests/replay/test_risk_param_delta.py`（NEW，410 LOC）

**3 case 結果**：
| Case | 範圍 | 結果 |
|---|---|---|
| `test_position_size_max_pct_delta_produces_different_sha` | A5 V049 持久化的 risk_config_sha256 不同 | PASS |
| `test_position_size_max_pct_propagates_to_disk_manifest` | A5 round 3 Fix 3 invariant：tight + loose 兩 risk_overrides 注入 disk payload | PASS |
| `test_risk_evidence_payload_records_rejected_gate` | A5 writer evidence schema 對 qty=0 ghost (rejected) vs qty>0 (accepted) 路徑差異 | PASS |

### §11.4 R5-T7-Rust — proof_7 + proof_8 cross-language fixture sanity

**File**：`rust/openclaw_engine/tests/replay_runner_e2e_param_delta.rs`（NEW，370 LOC）

**結果**：
| proof | 範圍 | 結果 |
|---|---|---|
| `proof_7_strategy_param_factory_wiring_round_trip` | strategy_param wiring observability：兩 `StrategyParamsConfig`（grid_levels=10/20）通過 StrategyFactory → ReplayStrategyAdapter → IsolatedPipeline；驗 manifest_id 不同 + status=Completed + 至少 1 fill / 1 sig | PASS |
| `proof_8_risk_param_delta_changes_decision_outcomes` | risk_param wiring observability：tight (position_size_max_pct=0.001) vs loose (=10.0) 兩 RiskConfig；驗 tight ≥ loose ghost 數 + tight ≤ loose accepted + 至少一邊嚴格不等 | PASS |

**Push back（critical）**：proof_7 不驗 fills 差異而驗 wiring round-trip — 因現有 synthetic_btcusdt.json fixture 僅 10 events 單調上漲，grid_levels 在第一 tick 不影響首次 Open 決策（兩個 grid_count 在首次入場時 emit 相同 intent_signature），須等 Sprint C R6 fee calibration sprint 引入更豐富的 fixture（含上下波動讓 grid placement 真起作用）後才能驗 fills delta。proof_8 因 risk gate per-intent 觸發，能在現有 fixture 上看到 ghost row delta（PASS 證明 risk_param wiring 完整）。**詳述見 proof_7 docstring + 模組級 MODULE_NOTE**。

### §11.5 LOC delta（Round 3 only / cumulative）

| File | Pre-Round 3 | Round 3 final | Δ Round 3 | hard cap | 結論 |
|---|---:|---:|---:|---:|---|
| `replay/route_helpers.py` | 1498 | 1500 | +2 | 1500 | **at cap exactly**（嚴守 §九 800 警告 / 1500 硬上限）|
| `replay/run_route.py` | 466 | 471 | +5 | 1500 | < cap |
| `tests/replay/test_strategy_param_delta.py` | 0 (new) | 430 | +430 | n/a | tests |
| `tests/replay/test_risk_param_delta.py` | 0 (new) | 410 | +410 | n/a | tests |
| `rust/openclaw_engine/tests/replay_runner_e2e_param_delta.rs` | 0 (new) | 370 | +370 | n/a | tests |

**route_helpers.py LOC 分析**：dispatch §expectation `≤ 30 LOC` 估計 Fix 3 增量；實際 +2 net。Trim 過程：第一版 +101 LOC（文檔過度詳細）→ 多輪精簡 docstring + 合併中英 paragraph + 縮短 inline 注釋 → 最終 +2 net 維持 §七 雙語注釋核心要求（MODULE_NOTE / docstring / SAFETY / inline 中英對照）+ 嚴守 §九 1500 hard cap。

**route_helpers.py at 1500 caps observation**：`build_default_manifest_payload` 已加 R3 Fix 3 logic + 完整 bilingual docstring；後續對 route_helpers.py 有任何新增（即使是 1 LOC docstring）需先 push back PM 評估是否模組拆分（已超 800 警告線於 R5-T4 round 1 時 PM 已 accept）。

### §11.6 xlang 13/13 不退（critical invariant）

```
$ python3 -m pytest tests/replay/ -k xlang_consistency --no-header -q -W ignore
13 passed, 38 deselected, 0 warnings in 0.11s
```

**核心理由**：existing xlang fixture 不含 `_replay_strategy_params` / `_replay_risk_overrides` 兩保留 key → `build_default_manifest_payload` legacy `cur=None` 路徑回 3-key body → canonical_bytes 計算與 round 1+2 byte-equal → cross-language byte-equal invariant 不破。

### §11.7 git status sign-off-clean

```
$ git status --short
 M docs/CCAgentWorkSpace/E1/memory.md
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_route.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_experiments_register.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py
 M rust/openclaw_engine/src/bin/replay_runner.rs
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_b2_r5t456_impl.md
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_risk_param_delta.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_strategy_param_delta.py
?? rust/openclaw_engine/tests/replay_runner_e2e_param_delta.rs
```

Round 3 added：2 modified production files (route_helpers.py + run_route.py) + 3 new test files；Round 1+2 + report 仍 uncommitted（per dispatch；E1 等 E2 review 後 PM 統一 commit + push）。

### §11.8 Round 3 self-test summary

| Test surface | Round 2 baseline | Round 3 result | Δ |
|---|---|---|---|
| Mac pytest replay | 190 PASS / 1 skip | **196 PASS / 1 skip** | +6 PASS（A4 3 + A5 3） |
| Linux pytest replay | (round 2 not pushed) | (round 3 not pushed) | (Linux 仍 baseline) |
| cargo build replay_runner | OK 0.09s | OK 0.10s | unchanged |
| cargo test --lib | 2478 PASS | **2478 PASS** | unchanged |
| cargo test --bin replay_runner | 9 PASS | **9 PASS** | unchanged |
| cargo test --test replay_runner_e2e | 6 PASS | **6 PASS** | unchanged |
| cargo test --test replay_runner_e2e_param_delta | n/a | **2 PASS**（proof_7 + proof_8） | +2 NEW |
| xlang_consistency | 13 PASS / 32 deselected | **13 PASS / 38 deselected** (CRITICAL) | invariant 維持；deselected count +6 是 A4/A5 6 case 也加入了 deselect set 中 |
| Symbol audit | 648 / 0 forbidden | **648 / 0 forbidden** | unchanged（route_helpers.py 改動是 Python 端 + 1 lazy import；不影響 Rust binary symbol） |
| Cross-platform path grep | 0 hit | **0 hit** | unchanged |
| Forbidden import grep on replay_runner_e2e_param_delta.rs | n/a | **0 hit** | NEW PASS |

### §11.9 PM Round 3 Decision Asks（push back）

#### §11.9.1 proof_7 fixture limitation push back（critical）

如 §11.4 所述，proof_7 在現有 synthetic_btcusdt.json 10-event monotone-up fixture 上**不能**驗 grid_levels delta 對 fills 的影響 — 兩 strategy 在第一 tick emit 相同 intent_signature。

**選項**：
- Option A（採用）：proof_7 重定為 wiring round-trip 驗證 + docstring + MODULE_NOTE 明示 fixture limitation；Sprint C R6 引入更豐富 fixture 後升級為 fills delta 斷言。
- Option B：在 R5-T7 範圍**內**新增 fixture（synthetic_btcusdt_with_pullback.json 等）以證 proof_7 的 fills delta — 但 dispatch §強制規範 1+8 「不擴大範圍」+「不 commit」+「~80 LOC」明示 80 LOC 上限，新 fixture 開銷不在範圍內。

**PM action**：accept Option A + 將 fills delta proof 升級 land Sprint C R6 follow-up TODO。

#### §11.9.2 route_helpers.py at 1500 hard cap

R5-T4 round 1 時 PM 已 accept simulated_fills_writer.py 過 800 警告線；現 route_helpers.py 也達 800 警告線且 Round 3 把它頂到 1500 hard cap 邊緣。後續對該檔的任何新增（即使是 docstring）都會超 cap → 必須拆模組或 push back PM。

**PM action**：consider Sprint C R6 拆 `route_helpers.py` 為 `route_helpers/{advisory_locks.py, manifest_builder.py, paths.py, ...}` package（高 cohesion 子模組），預估 LOC 後續可控；或保留 1500 hard cap 作為自然壓力。

#### §11.9.3 dispatch §強制規範 4 hermetic path 達成

dispatch 「hermetic test where possible：mock PG cursor + monkeypatch spawn；avoid full Linux smoke run」全部達成。A4/A5 6 case + Rust 2 proof 全 hermetic（無真 PG / 無 spawn engine binary）。Linux smoke 留給 PM 後續手動 trigger（per dispatch）。

#### §11.9.4 Round 3 仍**不**改動 R5-T1/T2/T3 / R5-T4/T5/T6 round 1+2 cleared 範圍

Round 3 修改範圍：
- `route_helpers.py::build_default_manifest_payload`（NEW kwarg + blob passthrough）
- `run_route.py::_do_pg_path`（callsite 加 `cur=cur`）
- 3 NEW test files（A4 / A5 / Rust）

Round 3 0 改動：`replay/strategy_adapter.rs` / `replay/risk_adapter.rs` / `replay/runner.rs::IsolatedPipeline` / 任 V### migration / 任 trading.* table / `experiment_registry.py` / `simulated_fills_writer.py` / `replay_runner.rs`。

---

**Round 3 IMPLEMENTATION DONE: 待 E2 審查 + E4 回歸 + PM round 3 decision asks (§11.9)**

(Per dispatch §sign-off — parent agent reads E1's final assistant message; PM persisted to .md file.)
