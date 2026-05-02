# E4 Funding-Arb Tight-SL Feature Branch Regression — 2026-05-02

**Verdict**: **PASS** — ready for PM Sign-off

**Branch**: `feature/2026-05-02-funding-arb-tight-sl-base-ratio`
**HEAD after E4 commit**: `73ea4ca` (parent `a19797d` E1 demo TOML edit)
**Linux test host**: trade-core, `~/BybitOpenClaw/srv`
**E4 commit**: `73ea4ca` test(risk-demo) — single test fn appended to `risk_checks_per_strategy_tests.rs` via `git commit --only` (not amended onto a19797d).

---

## Test 結果

### PA-required 4 targets (Linux release, post-E4 commit)

| 引擎 / suite | passed | failed | baseline (a19797d) | delta | verdict |
|---|---|---|---|---|---|
| `config::risk_config::tests::g2_03_per_strategy_tests` | **12** | 0 | 12 | +0 | OK (new test landed in `risk_checks::*` namespace) |
| `risk_checks` | **36** | 0 | 35 | +1 | OK (new ad-hoc test) |
| `config::risk_config::advanced` (incl. DynamicStop validate) | **13** | 0 | 13 | +0 | OK |
| `config::risk_config` | **115** | 0 | 115 | +0 | OK |

PA report quoted "13 tests" for G2-03 schema suite; runtime real count is 12 — verified at baseline `a19797d`.

### Full lib regression

| 引擎 | passed | failed | baseline | delta |
|---|---|---|---|---|
| `cargo test --release -p openclaw_engine --lib` (run 1) | **2405** | 0 | 2404 (a19797d) | +1 |
| `cargo test --release -p openclaw_engine --lib` (run 2) | **2405** | 0 | 2405 | match (non-flaky) |

Both runs 0.52s — identical runtime (cached release build).

### Workspace regression

| 引擎 | passed | failed | binaries | ignored |
|---|---|---|---|---|
| `cargo test --release --workspace` | **3008** | **0** | 21 | 3 (pre-existing) |

All 21 test binaries green. 3 pre-existing ignored tests are platform/runtime gated (require `OPENCLAW_TEST_PG` / `OPENCLAW_TEST_PG_DESTRUCTIVE=1`), not related to this wave.

---

## 新增 ad-hoc 測試

| File | New fn | Lines | Scope |
|---|---|---|---|
| `srv/rust/openclaw_engine/src/risk_checks_per_strategy_tests.rs` | `test_demo_toml_funding_arb_3pct_override_2026_05_02` | +93 (line ~311–399) | TOML round-trip + Defense A (validate) + Defense B (effective_sl runtime cap) |

### 9 個 assertion

1. `dynamic_stop.base_ratio == 0.25` (1e-9 tol, was 0.4 prior)
2. `per_strategy.funding_arb.enabled == true`
3. `per_strategy.funding_arb.stop_loss_max_pct_override == Some(3.0)`
4. `per_strategy.funding_arb.take_profit_max_pct_override == None` (commented-out → fall back limits)
5. `per_strategy.funding_arb.trailing_activation_pct_override == None` (fall back agent.*)
6. `per_strategy.funding_arb.trailing_distance_pct_override == None` (fall back agent.*)
7. `per_strategy.ma_crossover.stop_loss_max_pct_override == None` (schema-only block unchanged by 3C)
8. `RiskConfig::validate()` PASS — Defense A (3.0 < limits.stop_loss_max_pct=25.0 + finite + > 0)
9. `effective_sl_max_pct(&cfg.limits, Some(funding_arb)) == 3.0` (1e-9 tol) — Defense B runtime cap = `min(3.0, 25.0)`

### Placement rationale

Test placed in `risk_checks_per_strategy_tests.rs` (not the sibling `config/risk_config_per_strategy_tests.rs`) because:
- This sibling's `super::*` resolves to `risk_checks` module scope, exposing `effective_sl_max_pct` (`pub(crate)` in `risk_checks.rs`) directly — required for Defense B assertion
- Its sibling counterpart in `config/` cannot reach `effective_sl_max_pct` (different mod path)
- Both files already load TOML fixtures, so shared infrastructure available either side; defender-coverage decided the placement

### 不做事項

- 不改 `risk_config_demo.toml` (E1 commit a19797d 的內容)
- 不改 `risk_config.rs` / `risk_checks.rs` schema or production logic
- 不新建檔，加進現有 sibling test module
- Single test fn, single commit, not amended onto `a19797d` (per task spec)

---

## Mock 安全 audit

N/A — 純讀真實 fixture (`settings/risk_control_rules/risk_config_demo.toml`) + 跑 production `RiskConfig::validate()` + production `effective_sl_max_pct()`. 0 mock。

---

## SLA 壓測

新 test runtime `<10ms`（filesystem read + TOML parse + validate + effective_sl call）— 非 hot path，遠低於 SLA <1ms hot-path 邊界。`risk_checks` 套件整體完成 0.10s（36 tests），未引入慢測試。

---

## 跨語言浮點 1e-4 一致性

N/A — 改動為 TOML config wire-shape + Rust internal cap； 0 indicator/計算公式變動。

---

## 跑兩遍非 flaky 驗證

- Lib regression run 1: **2405 passed / 0 failed** in 0.52s
- Lib regression run 2: **2405 passed / 0 failed** in 0.52s
- New test ad-hoc 2nd run: **1 passed / 0 failed** in <0.01s

Non-flaky ✅.

---

## Healthcheck (post-task)

未跑（本任務純 Rust unit-test 範疇 + feature branch 未 deploy；runtime 未變）。Operator promote 此 branch 進 main + `restart_all.sh --rebuild` 後，建議重跑 healthcheck 對齊 §三 baseline。

---

## 退回 E1 修復清單

**N/A**（PASS）。

---

## Operator 下一步

1. **PM Sign-off** — 引本 report 為 E4 verdict
2. **Merge 路徑**：feature branch `73ea4ca` → main，再 `ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild --keep-auth"` 才生效（純 TOML 改動透過 `reload_risk_config` IPC 即可熱重載，無需 rebuild — operator 視 PA plan 決策）
3. **新 test 作哨兵**：未來任何 demo TOML schema drift 或 `effective_sl` runtime cap regression 會在 CI 此 test 觸發 fail，先於 paper/live runtime 受影響

---

## Reports / commits

- 本 report: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--funding_arb_tight_sl_regression.md`
- E4 memory log: `srv/docs/CCAgentWorkSpace/E4/memory.md`（追加區塊「2026-05-02 — Funding-arb tight-SL feature branch regression」）
- Test commit: `73ea4ca` test(risk-demo) on `feature/2026-05-02-funding-arb-tight-sl-base-ratio`（origin pushed）

E4 REGRESSION DONE: PASS · report path: srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--funding_arb_tight_sl_regression.md
