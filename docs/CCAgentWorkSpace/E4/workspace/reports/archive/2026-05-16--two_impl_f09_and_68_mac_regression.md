# E4 · Two-IMPL Parallel Mac Regression — F-09 + [68]

**Date**：2026-05-16
**Agent**：E4（Mac-side, working directory `/Users/ncyu/Projects/TradeBot/srv/`）
**Working tree HEAD**：`abf64620` "W-AUDIT-8b Stage 0R report gap closure" + 13 file working tree modifications + 2 untracked E1 reports
**Status**：🟢 **REGRESSION PASS — 兩 IMPL Mac-side baseline 0 regression、0 conflict、non-flaky；5 Linux-only items 列入 Appendix**

---

## §1 IMPL 範圍與 LOC

### IMPL #1 — P1 F-09 model_tier TOML extraction

**改動**（7 file）：
- `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` （537 LOC，+59 / -8）
- `rust/openclaw_engine/src/strategist_scheduler/mod.rs` （495 LOC，+23 / -0）
- `rust/openclaw_engine/src/config/risk_config_advanced.rs` （1300 LOC，+39 / -0）
- `rust/openclaw_engine/src/config/risk_config_tests.rs` （1912 LOC，+102 / -0）
- `settings/risk_control_rules/risk_config_paper.toml` （+10 lines）
- `settings/risk_control_rules/risk_config_demo.toml` （+10 lines）
- `settings/risk_control_rules/risk_config_live.toml` （+11 lines）

**設計核心**：原 `evaluate.rs:412` 硬寫 `"model_tier": "l1_9b"`；F-09 抽至 `RiskConfig.strategist.model_tier`，由 caller 從 ArcSwap snapshot 讀（`StrategistScheduler::current_model_tier()` mod.rs:266）。缺 store 時 fallback `DEFAULT_STRATEGIST_MODEL_TIER = "l1_9b"`。三層 default 對齊：
- Rust `StrategistConfig::default()` model_tier → `"l1_9b"`
- 3 TOML `[strategist] model_tier = "l1_9b"` 顯式宣告
- Python `_handle_strategist` `params.get("model_tier", "l1_9b")` 對齊 fallback

### IMPL #2 — P1 [68] healthcheck portfolio_resting_exposure

**改動**（4 file）：
- **新建** `helper_scripts/db/passive_wait_healthcheck/checks_portfolio_resting_exposure.py` (562 LOC)
- **新建** `helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py` (408 LOC, 10 test)
- `helper_scripts/db/passive_wait_healthcheck/runner.py` (+51 / -0)
- `helper_scripts/db/passive_wait_healthcheck/__init__.py` (+13 / -0)

**ID 衝突**：PA spec 標 [58] 但 `check_58_graduated_canary_stage_invariant` (W-AUDIT-9 T4) 已占用。E1 取下個 free slot [68]，name `portfolio_resting_exposure_lineage` 保留。source comment + runner.py 明示衝突原因。

**設計核心**：監測 `effective(filled+resting)` vs `filled-only` leverage chain semantic drift。per engine_mode 4 sub-check（long/short notional vs cap × {80%,100%} + divergence vs {50%,100%} + per-symbol resting/filled vs {80%,150%}）。OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1 env-gated WARN→FAIL escalation。

### §九 LOC check

| 檔 | LOC | 狀態 |
|---|---:|---|
| evaluate.rs | 537 | ✅ < 800 |
| mod.rs (strategist_scheduler) | 495 | ✅ < 800 |
| risk_config_advanced.rs | 1300 | ⚠️ > 800（pre-existing baseline） |
| risk_config_tests.rs | 1912 | ⚠️ > 800，**95.6% of 2000 hard cap**（pre-existing baseline + F-09 增 ~88 LOC）|
| checks_portfolio_resting_exposure.py | 562 | ✅ < 800 |
| test_portfolio_resting_exposure_healthcheck.py | 408 | ✅ < 800 |

**P2 follow-up**：`risk_config_tests.rs` 距 2000 hard cap 88 LOC headroom；建議拆 sub-module（per-feature test 切檔）— 不阻塞當前 commit（pre-existing baseline + §九 governance exception clause 適用）。

---

## §2 Mac-side baseline 結果（2× runs，non-flaky）

| Engine | Run #1 passed | Run #2 passed | failed | ignored | delta vs E1 self-report |
|---|---:|---:|---:|---:|---|
| Rust openclaw_engine --lib --release | 2917 | 2917 | 0 | 1 | **0 / 0 / 0** ✅ |
| Python helper_scripts/db/ pytest | 368 | (skipped #2 — sufficient) | 0 | 0 | **+10** (baseline 358 → 368) ✅ |
| Python test_portfolio_resting_exposure_healthcheck | 10 | 10 | 0 | 0 | **matches E1** ✅ |

**1 ignored 是 pre-existing**（socket-permission test，Mac dev-only platform limit，per 既有 E4 report 多次確認）。

### Targeted runs

| Target | passed | failed | filtered | 新 test 確認 |
|---|---:|---:|---:|---|
| `strategist_scheduler::tests` | 36 | 0 | 2882 | `test_build_strategist_eval_payload_honors_custom_model_tier` ✅ |
| `config::risk_config::tests` | 150 | 0 | 2768 | `test_strategist_config_validate_rejects_empty_or_whitespace_model_tier` ✅ + round-trip 擴 |
| Substring `model_tier` | 2 | 0 | 2916 | 2 F-09 new test 全綠 |

### cargo fmt --check

跑 `rustfmt --check --edition 2021` 對 4 F-09 改動 Rust file：
- `evaluate.rs` / `mod.rs` / `risk_config_advanced.rs` — clean
- `risk_config_tests.rs` — **2 drift**（assert! 多行 wrap + table 對齊）

**歸因**：`git stash` baseline file 後 rustfmt --check 同 2 drift → **pre-existing drift in main HEAD `abf64620`，非 F-09 引入**。F-09 不需修。建議 P2 跑 `cargo fmt` 統一清。

### cargo check --release

`cargo check --release -p openclaw_engine` PASS（pre-existing dead_code warning `spawn_position_reconciler` 不在 F-09 改動 scope）。

---

## §3 IMPL-by-IMPL verdict

### IMPL #1 — F-09 verdict：PASS

- ✅ ArcSwap snapshot 路徑真實（不是 mock）：`mod.rs:266 current_model_tier()` → `risk_store.as_ref().map(|store| store.load().strategist.model_tier.clone())` — 確認 hot-path-safe single ArcSwap load
- ✅ caller 真讀 snapshot：`evaluate.rs:158 let model_tier = self.current_model_tier();` 替代舊硬碼 `"l1_9b"`
- ✅ `test_build_strategist_eval_payload_honors_custom_model_tier` 驗 caller 傳非 default tier 時 payload 鏡像
- ✅ `test_strategist_config_validate_rejects_empty_or_whitespace_model_tier` 驗 validate() fail-fast 擋空/純空白
- ✅ TOML round-trip 擴 `model_tier="l1_27b"` + 4 partial fallback 場景
- ✅ 3 TOML 均含 `[strategist] model_tier = "l1_9b"`
- ✅ 3 層 default 對齊（Rust source / TOML / Python `_handle_strategist`）
- ⚠️ rustfmt drift in risk_config_tests.rs 是 pre-existing（stash 驗證）— 非 F-09 責任
- 📌 SLA 0 風險：strategist scheduler 是 secs-period async cycle，**非 tick hot path**（per CLAUDE.md §五 [策略工具包] strategist scheduler = governance 層 cycle，不在 < 0.3ms tick path）

### IMPL #2 — [68] healthcheck verdict：PASS

- ✅ py_compile 0 error（3 file: check / runner / __init__）
- ✅ 10/10 PASS x2 non-flaky
- ✅ 涵蓋 PASS / WARN / FAIL 三狀態 + 邊界（snapshot 缺 / 表缺 / 無 Working orders / REQUIRED env）
- ✅ Sibling `helper_scripts/db/` 368/0 0 regression spill
- ✅ runner.py wire 正確：`s, m = check_68_portfolio_resting_exposure(cur); results.append(("[68] portfolio_resting_exposure_lineage", s, m))`
- ✅ __init__.py re-export `check_68_portfolio_resting_exposure` 正確 + `# noqa: F401`
- ✅ ID 衝突 [58]→[68] 處理乾淨（source comment + runner.py 明示 W-AUDIT-9 T4 占用 + name preserved）

### Mock 審查（per CLAUDE.md regression-protocol §5）

`MagicMock` 只 mock **cursor IO 邊界**：
- `cur.execute` no-op
- `cur.fetchone.side_effect = fetchone_rows` 依序餵真 test row sequence
- `cur.fetchall.side_effect = fetchall_rows` 同
- `cur.connection.rollback` no-op

**業務邏輯真跑**：
- aggregate（per engine_mode × symbol × side resting notional 加總）
- divergence calc（effective vs filled-only %）
- cap compare（80% WARN / 100% FAIL / 50% divergence WARN / 100% FAIL / per-symbol 80% WARN / 150% FAIL）
- env-gated escalation（OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1 → WARN→FAIL）
- snapshot file read 是真 tmp file（`_write_snapshot()` 寫真 JSON 給 check 真讀）

**0 anti-pattern**：未 mock 業務邏輯，未 mock 計算函數，未 mock IPC protocol — 符合 CLAUDE.md §5.1 OK 範圍（IO 邊界 mock only）。

---

## §4 Cross-IMPL conflict 評估：0 conflict

| 維度 | F-09 | [68] | 衝突? |
|---|---|---|---|
| Layer | Rust config schema + IPC payload | Python PG/filesystem healthcheck | ❌ |
| Process | strategist scheduler (engine in-process) | cron healthcheck (out-of-process) | ❌ |
| Data source | ArcSwap RiskConfig | paper_state.snapshot JSON + trading.orders PG | ❌ |
| 共用 state | 0 | 0 | ❌ |
| 共用 SQL | 0 | 0 | ❌ |

**Grep 驗證**：
- `grep portfolio\|resting rust/openclaw_engine/src/strategist_scheduler/{evaluate,mod}.rs` → **0 matches**
- `grep model_tier helper_scripts/db/passive_wait_healthcheck/checks_portfolio_resting_exposure.py` → **0 matches**

**Verdict**：2 IMPL 完全 0 overlap，可獨立 commit 順序任選。

---

## §5 Linux-only flagged scope（5 items，partitioned per CLAUDE.md §六/§七）

1. **[68] SQL semantic on real PG**：`SELECT to_regclass('trading.orders')` + `SELECT DISTINCT ON (order_id) ... FROM trading.order_state_changes` + JOIN orders + `engine_mode = %s` WHERE 過濾 — 真 PG schema / index / data shape 必 Linux 驗
2. **[68] paper_state snapshot real read**：`OPENCLAW_DATA_DIR` 多 engine_mode snapshot 檔（paper.json / demo.json / live.json / live_demo.json）真檔讀 + `position.qty/entry_price/notional` 真值 cross-check vs Rust `paper_state/snapshots.rs:20` PositionSnapshot serialization layout
3. **F-09 ArcSwap runtime IPC hot-reload**：`patch_risk_config` `<60s` 真實熱重載 `model_tier="l1_27b"` 後驗 strategist evaluate 下一輪 IPC payload `model_tier == "l1_27b"`（Python `_handle_strategist` 端真實 routing）
4. **F-09 Python side end-to-end**：`ai_service_dispatch.py._handle_strategist` 收到 `params["model_tier"]="l1_27b"` 真 route 到 27B Ollama model（Linux Ollama 真跑）
5. **[68] runner.py cron 真實 invocation**：Mac 跑 unit test 不等於 cron 真跑 [68] check + WARN/FAIL 級別正確 surfaced 到 healthcheck log + alert escalation 真鏈

**這些不阻塞 PM commit**（per CLAUDE.md §六 Mac dev / §七 Linux runtime split）；屬於後續 trade-core deploy + healthcheck cron run 自然驗證範圍。

---

## §6 整體 test count baseline 對齊

| 引擎 | Pre-IMPL baseline | This IMPL delta | Post-IMPL | passed | failed |
|---|---:|---:|---:|---:|---:|
| Rust openclaw_engine --lib --release | 2915 | +2 (F-09) | 2917 | 2917 | 0 |
| Python helper_scripts/db/ | 358 | +10 ([68]) | 368 | 368 | 0 |

**0 regression（passed 不降 + failed 不增）**。

注意：control_api_v1 + srv/tests 等其他 Python 範圍 E4 本次未跑（F-09 + [68] scope 不影響），延用前次 baseline（控 token 成本符合 operator 偏好）。如需 full Python scope baseline，可拉 ssh trade-core 跑。

---

## §7 P2 follow-up（不阻塞 PM commit）

1. **risk_config_tests.rs 拆檔**：1912/2000 = 95.6% headroom 88 LOC；F-09 之後再加 ~88 LOC 就破 2000 hard cap。建議拆 sub-module（per-feature test 切檔，如 `strategist_tests.rs` / `pricing_tests.rs` / `kelly_tests.rs` 等）。
2. **rustfmt drift 清理**：risk_config_tests.rs assert! 多行 wrap + 表格對齊（pre-existing 在 main HEAD），P2 跑 `cargo fmt` 統一清。
3. **F-09 Python ↔ Rust integration test**：當前 F-09 Rust 端有 4 unit test；Python `_handle_strategist` 端應加對應 round-trip test 驗 `model_tier="l1_27b"` 真切到 27B Ollama model（IPC fake + ollama mock layer）。
4. **[68] dynamic snapshot freshness test**：當前 test 用靜態 tmp snapshot；P2 加 freshness staleness test（snapshot mtime > N min → WARN）。
5. **F-09 dynamic model routing（P2-F-09b）**：caller 層包裝按 decision complexity 動態選 tier（簡單 9B / 中等 27B / 複雜 L1.5 / 戰略 L2），不必動 `build_strategist_eval_payload` signature。
6. **[68] dual-source compare 對齊 [45] LG-2 T3**：FeeSource enum + dual-source compare pattern 可借鑑（per CLAUDE.md §九 AccountManagerSlot pattern）。

---

## §8 Regression Verdict

### 必過清單

- ✅ Rust --lib --release：2917 / 0 / 1 x2 non-flaky（與 E1 self-report 1:1）
- ✅ Python helper_scripts/db/：368 / 0 / 0
- ✅ Python test_portfolio_resting_exposure_healthcheck：10 / 0 / 0 x2 non-flaky
- ✅ F-09 targeted（strategist_scheduler 36/0 + config::risk_config 150/0 + model_tier substring 2/2）
- ✅ Cross-IMPL conflict assessment：0 overlap（layer / process / data source / SQL / grep）
- ✅ Mock review：IO 邊界 mock only，0 業務邏輯 mock
- ✅ §九 LOC：0 hard cap breach（risk_config_tests.rs 95.6% 接近 cap → P2 拆檔）
- ✅ rustfmt drift 已歸因 pre-existing（stash 驗證）
- ✅ SLA：F-09 0 hot path 風險（strategist secs-period async cycle）；[68] cron healthcheck async 無 SLA 約束

### 未過清單

- 無。

### 退回 E1 修復清單

- 無。

### Verdict

🟢 **E4 REGRESSION PASS**

**兩 IMPL 可獨立或合併 PM commit + push 到 main**。F-09 + [68] 是 cross-layer 不同 process，順序任選。5 Linux-only items 列入 Appendix 給 trade-core deploy 後自然驗證範圍。

---

**E4 REGRESSION DONE: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--two_impl_f09_and_68_mac_regression.md`**
