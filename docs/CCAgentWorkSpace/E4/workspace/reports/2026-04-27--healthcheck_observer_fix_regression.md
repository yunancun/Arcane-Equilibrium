# E4 Regression Report — `d4bc9eb` healthcheck+observer 4 stale/FAIL 修 · 2026-04-27

**Verdict: PASS — 0 regression / +5 new tests / 兩遍同綠**

---

## §1 Commit 範圍

`d4bc9eb` `fix(healthcheck+observer): 4 stale/FAIL fixes — [3][19][23][24] silent-noise cleanup`

7 files changed (482+ / 62-), **純 Python**, **無 Rust 變更**, **無業務邏輯改動**：

```
helper_scripts/db/passive_wait_healthcheck/checks_engine.py     ([3] ratio-band + [23] JOIN order_id)
helper_scripts/db/passive_wait_healthcheck/checks_strategy.py   ([24] paper-only context skip)
program_code/exchange_connectors/bybit_connector/io_and_persistence/
  _bybit_private_check_stub.py            (NEW shared helper, 155 行)
  bybit_private_account_check.py          (rewritten thin wrapper)
  bybit_private_positions_check.py        (rewritten thin wrapper)
  bybit_private_order_history_check.py    (rewritten thin wrapper)
  bybit_private_execution_history_check.py(rewritten thin wrapper)
```

OBSERVER-RESTORE-1 root cause：commit `f42face`（2026-04-23）刪除 `helper_scripts/maintenance_scripts/bybit_connector/` 98-shim 目錄含 `.py.orig` stubs，4 個 thin wrapper `os.execv` 進 deleted `.py.orig` → returncode=2 silent-fail 連續 8 天，由 `[19] observer_pipeline_alive` 揭發（2026-04-26 加入）。

---

## §2 測試結果

### Pytest control_api_v1（Linux trade-core）

| Run | passed | failed | skipped | baseline | delta |
|---|---|---|---|---|---|
| **parent `26e42fa`**（基準） | 2953 | 54 | 3 | n/a | n/a |
| **`d4bc9eb`** Run 1 | 2953 | 54 | 3 | 2953 | **0** ✓ |
| **`d4bc9eb` + new 5 tests** Run 1 | 2958 | 54 | 3 | 2953 | **+5** ✓ |
| **`d4bc9eb` + new 5 tests** Run 2 | 2958 | 54 | 3 | 2953 | **+5** ✓ |

**結論：54 pre-existing failures 在 parent 與 d4bc9eb **完全相同**（逐 test 名稱比對），證明 d4bc9eb 沒造成任何回歸。新 5 tests 兩遍同綠 = 非 flaky。**

54 pre-existing FAIL 集中於 `test_strategist_promote_api.py` / `test_executor_shadow_toggle_api.py` 等 — **不在 d4bc9eb 改動路徑（healthcheck + io_and_persistence wrappers）**。屬已知 baseline backlog（CLAUDE.md §十一 STRK-FUP-LOOP-HANDLERS-SPLIT P2 + HEALTHCHECK-PRE-EXISTING P2）。

### Rust cargo test --release -p openclaw_engine --lib（Linux）

| Run | passed | failed | baseline | delta |
|---|---|---|---|---|
| Run 1 | 2290 | 0 | 2290 | **0** ✓ |
| Run 2 | 2290 | 0 | 2290 | **0** ✓ |

預期：commit 0 Rust diff，數字不應動。

### 新 5 tests（`test_bybit_private_check_stub.py`）

| 環境 | passed | failed |
|---|---|---|
| Mac local Run 1 | 5 | 0 |
| Linux Run 1 | 5 | 0 |
| Linux Run 2 | 5 | 0 |

雙端跑 + Linux 兩遍同綠 = 跨平台 + 非 flaky。

---

## §3 命令驗證（PM 派發 1-7 步）

### Step 1 · pytest control_api_v1
```
ssh trade-core "bash -lc 'cd ~/BybitOpenClaw/srv && PYTHONPATH=. pytest -q --no-header program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ 2>&1 | tail -3'"
→ 54 failed, 2958 passed, 3 skipped, 408 warnings in 61.21s
```
PASS — baseline 不退（pre-existing 54 不變）。

### Step 2 · Rust cargo test
```
ssh trade-core "bash -lc 'cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -3'"
→ test result: ok. 2290 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.52s
```
PASS — 0 Rust diff，數字鎖死。

### Step 3 · Healthcheck import 不破
```
ssh trade-core "bash -lc 'cd ~/BybitOpenClaw/srv && python3 -c \"from helper_scripts.db.passive_wait_healthcheck.checks_engine import check_exit_features_writer, check_orders_fills_consistency; from helper_scripts.db.passive_wait_healthcheck.checks_strategy import check_signals_writer_freshness; print(\\\"OK\\\")\"'"
→ OK
```
PASS — 3 個被改的 check function 全可 import。

### Step 4 · 4 wrapper subprocess rc=0
```
ssh trade-core "bash -lc 'cd ~/BybitOpenClaw/srv && export OPENCLAW_SRV_ROOT=\$PWD && for s in account positions order_history execution_history; do python3 program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_\${s}_check.py >/dev/null; echo \$s rc=\$?; done'"
→ account rc=0
  positions rc=0
  order_history rc=0
  execution_history rc=0
```
PASS — 4/4 wrapper exit 0（pre-fix 連 8 天 rc=2）。

### Step 5 · cron observer cycle
```
ssh trade-core "bash -lc 'cd ~/BybitOpenClaw/srv && bash helper_scripts/cron_observer_cycle.sh 2>&1 | tail -10'"
→ steps_ok=5/5 (100%) overall_ok=False  -- by design (execution_history fossil LATEST 保留)
  Cron exit aggregation: OBSERVER_RC=1 BRIDGE_RC=0 → exit 1 (observer failure dominates)
```
PASS — `steps_ok=5/5` 對齊 PM 派發預期；`overall_ok=False` + observer exit 1 是 [19] healthcheck 對 execution_history fossil LATEST 保留的 by-design 行為，**對 d4bc9eb 4 修無影響**。

### Step 6 · passive_wait_healthcheck cron — 4 修目標 PASS
```
PASS [3] exit_features_writer             exit_features_24h=222 vs close_fills=223 (ratio 1.00)
PASS [19] observer_pipeline_alive         age=0.0h, ok=5/5 (100%)
PASS [23] orders_fills_consistency        30min: pairs_missing_orders=0/6, total_missing_orders=0
PASS [24] signals_writer_freshness        trading.signals writer is paper-only (Signal Diamond V015); paper disabled by-design — skip
```
PASS — d4bc9eb 4 目標 check 全 PASS。

⚠️ Cron 整體仍 SUMMARY: FAIL，但 root cause 是 **[27] `intents_counter_freeze`**（demo stale 1.8m + live_demo stale 30.9m + live never produced，Rust trading_writer intent INSERT path）— **不在 d4bc9eb scope**，已存在於 parent commit。

### Step 7 · 新 5 unit tests `test_bybit_private_check_stub.py`
```
test_no_key_configured_emits_credential_misconfigured  ✓
test_key_configured_emits_not_implemented              ✓
test_key_in_prod_slot_also_triggers_not_implemented    ✓
test_dated_copy_written_alongside_latest               ✓
test_payload_extra_does_not_clobber_base_schema        ✓ (pin 當前 merge 順序)
```
PASS — Mac + Linux 雙端 + Linux 兩遍同綠。

**新 commit `8df0a86`**（Mac local ahead origin）：
```
test(observer-restore): unit smoke for _bybit_private_check_stub.emit_stub (E4)
1 file changed, 212 insertions(+)
```

---

## §4 Mock 審查

| Test | Mock 內容 | OK? |
|---|---|---|
| `test_no_key_configured_*` | `monkeypatch.setenv("OPENCLAW_SECRETS_DIR")` + `tmp_path` | ✓ env / FS only |
| `test_key_configured_*` | 同上 + 寫真 api_key 檔到 tmp slot | ✓ env / FS only |
| `test_key_in_prod_slot_*` | 同上，key 在 prod/ 而非 demo/ | ✓ env / FS only |
| `test_dated_copy_*` | tmp_path 寫 LATEST + dated 後直接讀檔比對 | ✓ FS round-trip 真跑 |
| `test_payload_extra_*` | tmp_path + 直接驗 JSON merge 結果 | ✓ 邏輯真跑 |

**0 mock 業務邏輯 / 0 mock 計算函數** — 完全符合 `regression-testing-protocol` Mock 安全規則 §5。`emit_stub` 真跑，`_key_configured()` 真讀 FS，merge 真執行。

---

## §5 跨平台兼容性審查（CLAUDE.md §七.1）

新測試 + 新 helper：
- ✅ 無 user-home 絕對路徑字面值（`/home/ncyu/` / `/Users/ncyu/`）
- ✅ Path 解析走 `Path(__file__).resolve().parents[5]` 相對化
- ✅ Helper 走 `OPENCLAW_SRV_ROOT` → `OPENCLAW_BASE_DIR` → `"."` fallback
- ✅ Secrets 走 `OPENCLAW_SECRETS_DIR` → `OPENCLAW_SECRETS_ROOT/secret_files/bybit` → repo-relative fallback
- ✅ 雙語注釋齊全（MODULE_NOTE 中英 + per-fixture/test docstring）

`grep -E '(/home/ncyu|/Users/[^/]+)' diff` → 0 hits ✓。

---

## §6 Pre-existing failures 不變證明

逐 test 名稱比對 parent (`26e42fa`) vs `d4bc9eb` 兩次跑的 54 FAIL list：**完全相同集合**。54 個失敗集中於：
- `test_strategist_promote_api.py` (~30 個 — Strategist promote API contract drift)
- `test_executor_shadow_toggle_api.py` (~10 個 — TestEngineWhitelist / engine validation)
- 其他散落 (~14 個)

**全部在 d4bc9eb 0 改動路徑外**，根據 CLAUDE.md §九「passed >= baseline + failed <= pre-existing」規則 → 通過。

---

## §7 結論

**E4 REGRESSION DONE: PASS**

**證據鏈：**
1. parent vs d4bc9eb pytest 完全相同（2953/54/3）→ 0 regression
2. Rust 0 改動 → cargo lib 2290/0 鎖死
3. 4 wrapper rc=0 each（pre-fix 連 8 天 rc=2）
4. 4 healthcheck 目標全 PASS（pre-fix [3][19][23][24] 都會誤報 FAIL）
5. 新 5 unit tests 雙端兩遍同綠
6. cron observer cycle steps_ok=5/5
7. Mock 審查全綠（0 mock 業務邏輯）
8. 跨平台合規（CLAUDE.md §七.1）

**未 push commits（operator action needed）：**
- `d4bc9eb` 原 commit + `8df0a86` E4 新 test → 兩個 Mac local ahead origin
- 直接 push origin main 被 harness 鎖（"Pushing directly to main bypasses PR review"）— operator 手動 push 即可，不阻塞 PM Sign-off

**1 條 follow-up 建議（不阻塞）：**
- `test_payload_extra_does_not_clobber_base_schema` pin 當前 `{**base, **payload_extra}` 行為（caller 可覆蓋 base schema 欄位）。長期更安全應改 `{**payload_extra, **base}`，本測試提示 future contract change 同步更新。

**1 unrelated FAIL（不在 d4bc9eb scope）：**
- [27] `intents_counter_freeze` — Rust trading_writer intent INSERT path 死鎖 → 屬獨立 ticket（在 parent 也 FAIL）
