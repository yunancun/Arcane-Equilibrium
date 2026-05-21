# E4 Regression Report — H 批 5 件 cross-module verify · 2026-05-21

## 任務

H 批 5 件全 closure 後 E4 cross-module regression：
- H1 P3-AUDIT-SCRIPT-STALE-CONST（`helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py` + `test_funding_arb_14d_audit.py`）
- H2 P2-DYN-STOP-FLOOR-SENTINEL（`rust/openclaw_engine/src/risk_checks_per_strategy_tests.rs` +3 sentinel）
- H3 P2-PHYS-LOCK-72-HEALTHCHECK（`helper_scripts/canary/healthchecks/68_phys_lock_gate4_distribution.py` + `tests/test_68_phys_lock_gate4_distribution.py` NEW）
- H4 P1-HALT-TRIGGER healthcheck（`helper_scripts/canary/healthchecks/69_halt_session_root_cause_recurrence.py` + `tests/test_69_halt_session_root_cause_recurrence.py` NEW）
- H5 P2-EDGE-EST-SNAPSHOTS（FA audit only / no source change）

## Verdict

**PASS** — 全 pytest + cargo test 綠 + adversarial 4/4 真實 catcher + byte-identical restore + 規範全綠（1 nit emoji 為 pre-existing 引用 / 不擋）

## Test 結果

| 引擎 | passed | failed | baseline | delta | flaky? |
|---|---|---|---|---|---|
| Python healthcheck pytest (canary/healthchecks/tests/) | 111 | 0 | 88 baseline + hc68 10 + hc69 13 = 111 | 0 | N（兩遍同 0.05s） |
| Python audit pytest (db/audit/test_funding_arb_14d_audit.py) | 5 | 0 | 5 | 0 | N（兩遍同 0.02s） |
| Python canary 全集 (helper_scripts/canary/) | 235 | 0 | 235 (watchdog 124 + healthcheck 111) | 0 | N |
| Rust lib (cargo test --release --lib) | 3045 | 0 | 3045 | 0 | N（兩遍 0.70-0.72s） |
| Rust g2_03_per_strategy_tests | 26 | 0 | 23 (pre-H2) + 3 sentinel = 26 | +3 | N |

**Cross-namespace**：passive_wait_healthcheck `[68] portfolio_resting_exposure_lineage` 與 canary `[68] phys_lock_gate4_distribution` 物理分離（不同模塊 path + 不同 function name），Python import 雙路徑同時可用無衝突。

## 新增測試

| 文件 | tests count | scope |
|---|---|---|
| `test_68_phys_lock_gate4_distribution.py` | 10 | AC-4 PASS / AC-5 WARN / AC-6 FAIL 邊界 + production exit_reason fixture + SQL OR condition + multi-engine severity_max + insufficient_sample tier |
| `test_69_halt_session_root_cause_recurrence.py` | 13 | drawdown threshold 邊界 / clear vs set event semantics / forensic_log absence / daily_loss_kind null / multi-set severity / SQL filter + window_secs / 90d default alignment |
| `risk_checks_per_strategy_tests.rs` +3 sentinel | 3 / 26 total | demo base_ratio 0.25 lock / demo atr_mult+cap_ratio lock / live cross-env divergence policy invariant |
| `test_funding_arb_14d_audit.py` | 5 | global fallback / per_strategy override priority / missing per_strategy section / per_strategy without override key / real demo TOML smoke |

## Adversarial Probe 結果（4/4 catcher 真實）

| # | scope | injection | 預期紅 test | 實際結果 | restore byte-identical? |
|---|---|---|---|---|---|
| 1 | H1 audit | `risk_config_demo.toml` `limits.stop_loss_max_pct` 25.0→50.0 | `test_current_demo_toml_returns_25_pct` | FAILED: `AssertionError: 0.5 != 0.25 within 6 places` | ✓ MD5 `1b62cf37454a23b0abdd8c28edd74608` |
| 2 | H2 sentinel | `risk_config_demo.toml` `base_ratio` 0.25→0.20 | `test_demo_toml_dyn_stop_base_ratio_locked` + W-AUDIT-6 `test_demo_toml_retired_funding_arb_removed_from_risk_config` 雙紅 | 兩 test panic with explicit FA F2 OQ-4 警示 message | ✓ MD5 同上 |
| 3 | H3 hc68 邏輯 | source 行 `stale_roc_close_attempts_sum == 0` 改 `>= 5` | 3 FAIL boundary tests | 3 紅 (`test_fail_when_stale_roc_alive_but_close_path_broken` / `test_multi_engine_severity_max` / `test_fail_overrides_warn_when_both_conditions_met`) | ✓ MD5 `0c15fb98a3b1695fc8f707d7f493c821` |
| 4 | H4 hc69 SQL schema | source SQL `payload->>` 改 `details->>`（schema mismatch） | `test_sql_uses_window_secs_and_event_type_filter` | FAILED: `assert "payload->>'session_drawdown_pct'" in sql` | ✓ MD5 `1e1e62e167027152e213ba1eabdcba0c` |

**全 4 reset byte-identical 後 final sanity 116 Python + 3045 Rust green**。

## Mock 真實性 spot check

| Test scope | mock 內容 | OK? | 驗證 |
|---|---|---|---|
| H3 hc68 production exit_reason fixture | hardcoded string literal `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg` | ✓ | grep `exit_features/v2.rs` line 344/351/455/491/543/586/800 production code 完全 match |
| H4 hc69 payload JSONB schema | hardcoded `payload->>` access pattern + `event_type` + `ts TIMESTAMPTZ` | ✓ | `V035__governance_audit_log.sql` line 90-135 `payload JSONB NULL` + `event_type TEXT NOT NULL CHECK` 完全 match |
| H1 audit script real TOML smoke | `_load_audit_module()` 真實 import + module-level `_load_sl_hard_cap_pct()` 真實讀取（不 mock）；其他 3 unit test 只 mock `tomllib.load` 不 mock 業務邏輯 | ✓ | adversarial probe `25.0→50.0` 直接觸發 real toml read path 紅 |

**Mock-only IO（tomllib.load） / 不 mock 業務邏輯（`_load_sl_hard_cap_pct` 全 path 真跑）**：符合 §5.1/5.2 規範。

## 規範驗證

| 項 | 結果 |
|---|---|
| file size warn (800) | ✓ 全 < 800（最大 hc69 = 574 / risk_checks_per_strategy_tests.rs = 668） |
| file size hard cap (2000) | ✓ 全遠低於 |
| 中文注釋 default | ✓（Rust sentinel `dynamic_stop.base_ratio expected 0.25, got 0.2 — 任何動 base_ratio 之前須先跑 SL gate semantic impact audit（FA F2 OQ-4）` / Python hc68 hc69 全中文 docstring） |
| 0 emoji | ⚠ 1 nit — `2026-05-16_funding_arb_14d_audit.py:18` 有 1 個 emoji 在 docstring 引用 `TODO.md「📅 排程提醒」section`（pre-existing 引用 / 非新加 / 不擋 commit） |
| 0 hardcoded path | ✓ grep `/Users/\|/home/\|trade-core` 全空 |
| `__init__.py` entry | ✓ empty package marker（標準 pytest） |
| `conftest.py` merge | ✓ hc68 + hc69 兩 fixture 各帶 namespace 邊界註釋（[68] vs passive_wait portfolio_resting 物理分離說明 / [69] 占用 by P1-HALT-TRIGGER） |

## 跑兩遍結果（flaky check）

- Python healthcheck 111: run1 0.05s / run2 0.05s → 兩遍同綠
- Python audit 5: run1 0.02s / run2 0.02s → 兩遍同綠
- Rust lib 3045: run1 0.72s / run2 0.70s → 兩遍同綠
- Adversarial restore 後 final sanity 116 + 3045 全綠

非 flaky。

## 結論

**PASS** · ready for PM commit / push。

### Evidence summary

- H 批 5 件 cross-module 全綠：Python healthcheck 111 + audit 5 + canary 235 + Rust lib 3045
- Adversarial 4/4 真實 catcher 觸發紅後 byte-identical restore（3 file MD5 完全 match baseline）
- Mock 只 stub IO 不 stub 業務邏輯：H3 fixture 對齊 Rust `exit_features/v2.rs` 真實 string / H4 SQL 對齊 V035 schema / H1 unit test mock tomllib.load 但保留 `_load_sl_hard_cap_pct` 全 path 真跑
- Namespace 物理分離驗證：canary `[68]` vs passive_wait `[68]` 不同 module path / 不同 function name / 同時可 import
- 0 file size 警告 / 0 hardcoded path / 1 pre-existing emoji nit（不擋）

### 教訓 / 工程觀察

- **Sub-agent IMPL DONE 後派 E4 跑 cross-module + adversarial 真實性 = 必要環節**：4 個 adversarial probe（H1 stop_loss_max_pct / H2 base_ratio / H3 FAIL boundary / H4 payload→details）各觸發**不同 test pathway** 紅，證明 catcher 不是橡皮章。若改 default constant（如 H3 嘗試改 DEFAULT_WARN_GIVEBACK_THRESHOLD 10→5）所有 test 仍 PASS — 因 test 用 explicit arg 不依賴 default — 此時必須改 source 邏輯（boundary expression）才能 catch。**規則**：adversarial probe 必驗 source business logic semantic 而非 default constant；後者只測 arg propagation。

- **MD5 byte-identical restore 是 sentinel 真實性的最後一關**：4 個 probe 完成後 3 個檔（demo TOML / hc68 / hc69）MD5 與 baseline 完全 match，證明 probe 不留 dirt。**規則**：adversarial probe 必跑 4 步 (1) baseline backup + MD5 record (2) inject + 驗紅 (3) byte-restore (4) verify MD5 + green。

- **Cross-namespace `[68]` 物理分離靠 module path 不靠 slot name**：canary `[68] phys_lock_gate4_distribution` 與 passive_wait `[68] portfolio_resting_exposure_lineage` 同 slot name 不同 namespace；Python import 各走 module path 不衝突。但 PM / operator mixed report 容易混淆 — conftest.py `hc68` fixture 已加 namespace 邊界註釋（per R2 [66] 範本治理）。**規則**：cross-namespace 同名 slot 不算 conflict 只要 module path 物理分離；conftest fixture 必加 namespace 邊界 docstring。
