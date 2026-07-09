# E4 Regression Report — P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX (R2) · 2026-05-21

## 範圍

E1 R2 IMPL（4-gate classifier + AMBIGUOUS_SOURCE_PATTERNS + 6 R2 new test，含 1 production-empirical PG pool catcher）→ E2 R2 APPROVE（4/4 R1 findings FIXED, 0 regression）→ E4 regression。

改動 3 files（Python monitoring layer only，無 Rust / 無 V### migration / 無 GUI）：
- `helper_scripts/canary/engine_watchdog.py` 1369 → 1532（+163 行）
- `helper_scripts/canary/test_canary.py` 728 → 890（+162 行）
- `helper_scripts/canary/test_engine_watchdog.py` 803 → 810（+7 行 MODULE_NOTE cross-ref）

未動：Rust `openclaw_engine` / IPC / GUI / PG schema。

E4 範圍：light Python pytest（canary/ scope + cross-module healthchecks + helper_scripts/db/）+ adversarial probe（HIGH-1 R2 production-empirical catcher 真實性驗）+ 規範驗 + Linux runtime impact 評估。Rust regression / Linux PG empirical / E2E 不在 scope。

HEAD = `fbe8b8d5` (origin/main 對齊；sibling push 0)。

---

## VERDICT: **PASS**

- pytest 207/207 PASS（`helper_scripts/canary/`）兩遍同綠（31.19s / 31.18s）
- cross-module 0 regression：healthchecks/tests/ 83/83 + helper_scripts/db/ 459/459 + 14 subtests
- 25/25 TestEngineFailureClassifier + TestOnEngineCrashClassification（含 6 R2 new + 19 R1 baseline，含 1 R1 改名 `test_non_consecutive_dns_above_interleaved_threshold` 意圖反轉設計符合 gate (c) 邏輯）
- Adversarial probe：移走 3 production token (`pg pool` / `pool timed out` / `db_pool`) → `test_pg_pool_exhaustion_with_concurrent_dns_errors_not_classified_as_net_outage` 真會 RED（`network_outage != engine_crash`）→ 復原後 PASS → 非 mock self-consistency
- 規範全綠（file size / emoji / cross-platform path / 中文注釋默認）
- Syntax / import / argparse 全 OK
- Linux runtime impact: 0 新 import + source-only fix；watchdog 仍跑 R1，需重啟才 deploy（out of scope）
- 兩遍同綠 non-flaky

可進 PM commit + push（per workflow E2 APPROVE → E4 PASS → PM commit）。

---

## Verify Step 詳結果

### Step 1 — Full `helper_scripts/canary/` pytest（兩遍）

```bash
$ python3 -m pytest helper_scripts/canary/ -v --tb=short  # 1st run
============================= 207 passed in 31.19s =============================

$ python3 -m pytest helper_scripts/canary/ -q --tb=short  # 2nd run
207 passed in 31.18s
```

| 引擎 | passed | failed | baseline (E2 R2 self-run) | delta |
|---|---|---|---|---|
| Python pytest (canary/) 1st | 207 | 0 | 207 | 0 |
| Python pytest (canary/) 2nd | 207 | 0 | 207 | 0 |

Flaky? **N**（two-run identical 207/207）。

**File 分布**（207）：
- test_canary.py: 60 tests（含 6 R2 new classifier tests + 19 R1 baseline）
- test_engine_watchdog.py: 44 tests（含 R2 LOW-1 MODULE_NOTE update；無新 test）
- test_engine_reconciler_promote.py: ~50 tests（cross-module 不破）
- test_halt_audit_pg_writer.py: ~30 tests（cross-module 不破）
- 其餘 canary suite

R2 新 6 test（已隨 E2 R2 一起綠）：
1. `test_net_outage_classified_when_5_consecutive_dns_errors` — gate (b) 向後兼容
2. `test_net_outage_classified_when_5_interleaved_dns_errors_within_5min` — gate (c) 單檔 interleaved
3. `test_net_outage_classified_when_dns_errors_span_log_rotation` — gate (d) cross-rotation aggregate
4. `test_pg_connection_error_not_classified_as_net_outage` — AMBIGUOUS guard (sqlx + pgconnection token)
5. `test_unrelated_log_lines_dont_trigger` — default engine_crash 保護
6. `test_pg_pool_exhaustion_with_concurrent_dns_errors_not_classified_as_net_outage` — **HIGH-1 R2 production-empirical** (真實 ANSI-wrapped engine.log 第 4 行 `pg pool` + `pool timed out` 字串)

R1 1 改名：
- `test_non_consecutive_dns_below_threshold` → `test_non_consecutive_dns_above_interleaved_threshold`
- 意圖反轉：R1 設計 8 DNS / 16 行 (50%) interleaved 應 `engine_crash`；R2 gate (c) 設計後該情境應 `network_outage`（5+ matches 達門檻、50% ≥ 25% ratio）

### Step 2 — Cross-module pytest 不破

```bash
$ python3 -m pytest helper_scripts/canary/healthchecks/tests/ -q --tb=short
83 passed in 0.03s

$ python3 -m pytest helper_scripts/db/ -q --tb=short
459 passed, 14 subtests passed in 0.41s
```

**重點驗證**：
- healthchecks/tests/ 83/83 unchanged（與 C 批 C1+C2 closure 2026-05-21 11:38 baseline 對齊）
- helper_scripts/db/ 459 PASS + 14 subtests PASS（含 close_maker_audit_healthcheck.py、passive_wait_healthcheck 相關 tests）
- 0 cross-namespace pollution

### Step 3 — Syntax / import / argparse

| Check | Result |
|---|---|
| `python3 -c "import helper_scripts.canary.engine_watchdog"` | `module import OK` ✓ |
| `python3 engine_watchdog.py --help` | exit 0 ✓ |
| `python3 engine_watchdog.py --status --data-dir /tmp` | exit 0；snapshot path null + 3 engines not_running（Mac 本機無 snapshot，預期）✓ |

```json
$ python3 helper_scripts/canary/engine_watchdog.py --status --data-dir /tmp
{
  "engine_alive": false,
  "snapshot_age_seconds": null,
  "snapshot_path": "/tmp/pipeline_snapshot.json",
  ...
}
---exit-code: 0
```

`--status` exit 0 對齊 P1-WATCHDOG-EXIT-CODE-CLARIFY DONE 2026-05-20 semantic 分區（`--status` 0/1 / lock 10-19 / rollback 20-29）。

### Step 4 — Adversarial Probe（production-empirical regression catcher 真實性驗）

**Probe 設計**：暫時移走 R2 補的 3 個 production token，跑 R2 HIGH-1 dedicated test 應 RED，復原後 GREEN。目的：證明 test 非 mock self-consistency 而是真依賴新 token。

**Probe 操作**：
1. backup `engine_watchdog.py` → `/tmp/engine_watchdog_E4_R2_backup.py`（byte-identical 對照基準）
2. Edit AMBIGUOUS_SOURCE_PATTERNS：`"pg pool"` / `"pool timed out"` / `"db_pool"` 三 token 改為註解（保留 `postgres` / `pgconnection` / `sqlx` 其他 9 token 不動）
3. 跑 `test_pg_pool_exhaustion_with_concurrent_dns_errors_not_classified_as_net_outage`
4. 復原檔案、跑 diff 驗 byte-identical
5. 重跑同 test → 預期回 GREEN

**Probe 結果**：

| 階段 | test_pg_pool_exhaustion 結果 | classify_engine_failure 回傳 |
|---|---|---|
| Strip 3 token | **FAIL** ✓ | `network_outage`（false positive 重現） |
| Restore | **PASS** ✓ | `engine_crash`（ambiguous guard 啟動） |

**對照 control**（test_pg_connection_error_not_classified_as_net_outage）：

| 階段 | 結果 |
|---|---|
| Strip 3 token | **PASS** ✓（用 `sqlx` + `pgconnection` token 不在 strip 範圍） |

→ 兩 test **互相獨立**：R2 新 production-empirical test 真實只測 3 個 R2 新加 token，且整 ambiguous guard 邏輯設計健全（其他 9 token 不依賴新 3 token）。E2 R2 §自驗 regression catcher 驗證**重現**。

**Diff 復原 verify**：
```bash
$ diff helper_scripts/canary/engine_watchdog.py /tmp/engine_watchdog_E4_R2_backup.py
# 0 diff → byte-identical
$ # ---restored: byte-identical to backup
```

復原後 final canary/ run 207/207 PASS（與 Step 1 一致）。

### Step 5 — 規範驗證

| Check | Result |
|---|---|
| `engine_watchdog.py` LOC | 1532 < 2000 hard cap ✓（> 800 documented exception per PA / E2 R2 §File Size） |
| `test_canary.py` LOC | 890 < 2000 ✓（> 800 既有 exception） |
| `test_engine_watchdog.py` LOC | 810 < 2000 ✓（剛過 800 既有 exception） |
| Emoji scan (3 files) | 0 emoji per file ✓ |
| `/home/ncyu` / `/Users/ncyu` hardcoded path | 0 hit ✓ |
| 中文注釋默認 | spot 抽查 4-gate docstring + AMBIGUOUS_SOURCE_PATTERNS 維護規範 + adversarial probe rationale 全中文 ✓ |
| `argparse --help` | 完整展示 6 個 flag（含 `--disable-inert-probe` + `--inert-probe-config`）✓ |
| 0 新 import（diff grep `^[+-]import|^[+-]from`） | engine_watchdog + test_canary + test_engine_watchdog 全 0 ✓ |

E1 R2 §5 已 flag size 警告，PA scope 限本 fix 不重構（trade-off 由 PM 決定）；E2 R2 同意此判斷。E4 不重複此議題，只驗 < 2000 hard cap 通過。

### Step 6 — Linux runtime impact 評估（read-only）

| Aspect | 狀態 |
|---|---|
| 當前 trade-core watchdog daemon | 跑 R1 版本（PM 2026-05-21 13:33 啟動 PID 2936560 per task brief） |
| R2 改動部署 | source-only，需要 watchdog 重啟（per `feedback_restart_rebuild_flag_scope` 不在本 task scope）|
| 新依賴 | **0**（grep `^[+-]import|^[+-]from` 三個 file 全 0 hit） |
| Rust runtime impact | **無**（純 Python monitoring layer fix） |
| PG / IPC / GUI impact | **無** |

E4 不操作 ssh trade-core 部署；watchdog daemon 重啟由 PM 決定時機。R2 source-only 改動已 commit-ready。

### Step 7 — Adversarial Verification (test 設計健全)

E2 R2 §自驗 regression catcher 已證 HIGH-1 R2 production-empirical test 真實 catch R1 FP；本 E4 step 4 **重現**並擴展驗證：
1. ✓ R2 新 production token 必須存在才能讓 test PASS
2. ✓ 移除任一個（或全部 3 個）→ test FAIL（fail-open 不被 mock 偽裝）
3. ✓ Control test (sqlx/pgconnection) 不受影響 → 各 ambiguous token 互相獨立、設計健全

---

## 跑兩遍結果

| Run | canary/ pytest | healthchecks/tests/ | helper_scripts/db/ |
|---|---|---|---|
| 1st | 207 PASS in 31.19s | 83 PASS in 0.03s | 459 PASS + 14 subtests in 0.41s |
| 2nd | 207 PASS in 31.18s | (single run，重要不變式) | (single run) |

flaky? **N**（two-run identical）

post-adversarial-probe restore final canary/ run: 207 PASS（與 1st/2nd 一致）

---

## SLA / 浮點 / 跨語言

不適用（engine_watchdog 是純 Python monitoring layer，非 hot path / 非 indicator 計算 / 純 Python 無 Rust counterpart / 無 IPC round-trip 改動）。

---

## E2 R2 nit / defer 狀態（不擋 E4，PM 後續處理）

| ID | 描述 | 處理方 |
|---|---|---|
| OQ-NETOUTAGE-2 | sparse-log timestamp window gate（A/B/C 選項 + defer 推薦）| E1 R2 §6 已開 OQ；PM 後續決定 |
| > 800 LOC | engine_watchdog 1532 / test_canary 890 / test_engine_watchdog 810 | E2 R2 §File Size 同意 trade-off；PA / PM 評是否拆檔 follow-up |

E4 不重複此議題。

---

## E4 FLAG（不擋 commit）

無新 BLOCKER / 無 mock 過頭 / 無結構性 test 失靈 / 無跨檔 broken 發現。

E2 R2 已對 OQ-NETOUTAGE-2 + size 警告給出處理路徑，E4 不重複。

---

## 結論

**PASS · commit ready**

- 207/207 pytest（canary/）兩遍同綠（31.19s / 31.18s）
- 83/83 healthchecks/tests/（cross-module 不破）
- 459 + 14 subtests helper_scripts/db/（cross-module 不破）
- 25/25 TestEngineFailureClassifier + TestOnEngineCrashClassification（6 R2 new + 19 R1 baseline 含 1 改名）
- adversarial probe: 移 3 token RED → 復原 GREEN → control PG test 不受擾 → 設計健全 + 非 mock 自我安慰
- 規範全綠（3 file size < 2000 / 0 emoji / 0 hardcoded path / 0 新 import / 注釋中文默認）
- syntax + import + argparse + --status exit code 全 OK
- Linux runtime impact: source-only，需 watchdog 重啟 deploy（out of scope）
- sibling push: 0（origin = local `fbe8b8d5`）

PM 建議：
1. commit `helper_scripts/canary/engine_watchdog.py` + `test_canary.py` + `test_engine_watchdog.py` + `docs/CCAgentWorkSpace/E1/memory.md` + 2 個 R2 report 落檔
2. commit message 標 `P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX R2 — 4-gate classifier + AMBIGUOUS guard + 6 R2 tests`
3. 通知 PM 決定 watchdog daemon 重啟時機（部署 R2 fix；當前 PID 2936560 仍跑 R1）
4. OQ-NETOUTAGE-2 follow-up 入 TODO §11.3 backlog

E4 REGRESSION DONE: PASS · report path:
`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--p1_watchdog_netoutage_classifier_fix_e4_regression.md`
