# E4 Regression Report — P0-ENGINE-HALTSESSION-STUCK-FIX Layer B (Python watchdog inert probe)

**Date**: 2026-05-20
**Author**: E4
**Object**: E1 Layer B IMPL（`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_impl_report.md`），Python-only watchdog inert probe（spec v0.2 §4 + §10.2 B-1..B-7）。
**Branch / state**: `main` HEAD `7fb46387`；Layer B IMPL 在 Mac dirty working tree（`engine_watchdog.py M` + `test_engine_watchdog.py ??` + `watchdog_inert_probe.toml ??` + SCRIPT_INDEX.md M）。未 commit / 未 push。
**Cargo regression**: 不適用 — Python-only 改動，無 Rust 變更、無 V### migration、無 engine binary 重建。

---

## 1. Verdict

**E4 REGRESSION DONE: PASS**

- Mac pytest `test_engine_watchdog.py`：32 / 0 PASS（2 runs identical → non-flaky）
- 廣域 canary 回歸 `helper_scripts/canary/`：170 / 0 PASS（2 runs identical）
- py_compile + CLI --help 全 OK，新增 `--disable-inert-probe` / `--inert-probe-config` 兩 flag 可見
- Layer A 文件零變更（scope creep check 通過）
- Layer A halt_audit.log 2 rows 保留 + governance_audit_log 24h 內 2 rows 保留（cron infra intact）
- Mock 審查：0 anti-pattern（test 用真 tempfile / 真 engine_watchdog 函式；無 `unittest.mock.patch` / 無 MagicMock / 無外部 IO）
- AC B-1..B-7 全有 test cover；B-1a per-env threshold 差 (live 15min vs demo 60min) 直接斷言

允許 PM sign-off → push → 部署 Linux watchdog。**不阻塞** A3 / E2 並行 review（不同 surface）。

---

## 2. Mac pytest 主結果

### 2.1 Layer B 新測試檔（E1 主要交付物）

命令：
```
cd /Users/ncyu/Projects/TradeBot/srv
python3 -m pytest helper_scripts/canary/test_engine_watchdog.py -v
```

| Run | passed | failed | E1 self-claim 對比 |
|---|---|---|---|
| #1 | 32 | 0 | E1 claim 32 new → ✅ identical |
| #2 | 32 | 0 | non-flaky ✅ |

7 個 TestClass：
- `TestResolveEngineLabel` (4)
- `TestLoadInertProbeConfig` (5)
- `TestDetectPaperPausedStuck` (5)
- `TestDetectIntentsZeroDelta` (5)
- `TestEvaluateInertProbe` (6)
- `TestInertStatePersistence` (4)
- `TestRunInertProbeOnce` (3)
合計 32 個 test functions（grep 數雙驗）。

### 2.2 廣域 canary 回歸

命令：
```
cd /Users/ncyu/Projects/TradeBot/srv
python3 -m pytest helper_scripts/canary/
```

| Run | passed | failed |
|---|---|---|
| #1 | 170 | 0 |
| #2 | 170 | 0（identical）|

包含：
- `healthchecks/tests/test_62_fill_rate.py` 7
- `healthchecks/tests/test_63_fallback_audit.py` 5
- `healthchecks/tests/test_64_rate_limit.py` 6
- `healthchecks/tests/test_65_reject_sample.py` 6
- `healthchecks/tests/test_67_pulse_freshness.py` 16
- `healthchecks/tests/test_common.py` 20
- `test_canary.py` 58
- `test_engine_watchdog.py` 32（新）
- `test_halt_audit_pg_writer.py` 20（Layer A，preserved）

→ **138 existing canary tests + 32 new Layer B = 170**

E1 self-report 寫 "90/90"（58 existing + 32 new）是針對單一 file 的口徑問題；以 directory-level 廣域回歸看是 170/0 全綠。差異不是測試數退化，是 E1 報告分子分母統計範圍不一致，但對 PASS verdict 無影響。

### 2.3 句法 + CLI

```
python3 -m py_compile helper_scripts/canary/engine_watchdog.py  # OK
python3 helper_scripts/canary/engine_watchdog.py --help          # 顯示 --disable-inert-probe + --inert-probe-config
```

兩個新 flag 在 argparse output 中可見，help 文字中英雙語。

---

## 3. AC B-1..B-7 對應驗證

| AC | 條件 | 對應 test | E4 驗 |
|---|---|---|---|
| B-1 | demo paper_paused 60min+ alarm | `test_fires_alarm_paper_paused_stuck` | ✅ PASSED |
| B-1a | live 15min vs demo 60min 差異 | `test_per_env_threshold_live_stricter` + `test_per_env_threshold_demo_not_fire_at_live_threshold` | ✅ PASSED |
| B-2 | intents zero-delta > window alarm | `test_fires_alarm_intents_zero_delta` | ✅ PASSED |
| B-3 | cooldown 同 incident 不重發 | `test_cooldown_no_duplicate_alarms` | ✅ PASSED（第二次評估 result=None，alarm 計數 1）|
| B-4 | clear transition 寫 CLEARED | `test_paper_paused_clears_state` | ✅ PASSED（result=cleared、CLEARED 條 1 行、previous_trigger 保留）|
| B-5 | watchdog restart 不重置 incident | `test_state_persistence_across_restart` + `test_save_load_roundtrip` + halt_set_ts_ms anchor (`test_uses_halt_set_ts_ms_as_anchor`) | ✅ PASSED（save→load 後 cooldown 仍生效）|
| B-6 | 7d false-positive reconcile | passive deploy-watch（cron post-deploy 觀察）— **不在 E4 階段驗** | ⏳ deploy 後驗 |
| B-7 | multi-engine 獨立 alarm state | `test_multi_engine_independent_state`（demo halt + live 正常 → 只 demo alarm） | ✅ PASSED |

### 額外覆蓋（spec § 邊界）

| 額外 case | test | E4 驗 |
|---|---|---|
| stale snapshot skip | `test_stale_snapshot_skipped` | ✅ |
| corrupted snapshot fail-soft | `test_corrupted_snapshot_skipped` | ✅ |
| TOML parse error fail-loud | `test_parse_error_raises` | ✅ |
| repo canonical TOML loads | `test_repo_canonical_toml_loads` | ✅ |
| invalid TOML value fallback | `test_invalid_value_fallback_default` | ✅ |
| corrupted state file fail-soft | `test_corrupted_state_file_returns_empty` | ✅ |
| missing state file 冷啟 | `test_missing_state_file_returns_empty` | ✅ |
| compat snapshot (top-level trading_mode) | `test_compat_snapshot_reads_trading_mode` | ✅ |
| mode_snapshots 優先讀 | `test_mode_snapshots_takes_priority` | ✅ |

→ 所有 spec §4 + §10.2 acceptance criteria 都有具體 unit test，且 E4 親自跑全綠。

---

## 4. Named test enumeration

E1 prompt 期望 `grep -E "def test_b[0-9]|def test_inert|def test_TRADING_INERT" wc -l ~32`。

實測：上面 grep 模式 **0 matches**。原因是 E1 採描述式命名（`test_fires_alarm_*` / `test_per_env_threshold_*` / `test_paper_paused_clears_state` 等），不是 `test_b1_xxx` AC-id 嵌入式命名。

但 **`grep -c "^\s*def test_" test_engine_watchdog.py` = 32**，與 E1 自報 32 new tests 數字一致。AC ↔ test 對應靠 §3 表格 + E1 IMPL 報告 §4 對照表，不靠檔名 substring。

E4 結論：E1 命名風格選擇 acceptable（描述式更可讀），但 prompt 寫的 grep 模式錯誤；32 個 test functions 確實存在 + 全綠 + 完整 cover AC B-1..B-7。

---

## 5. Layer A files unchanged check（scope creep guard）

```
git diff HEAD --stat | grep -iE "halt_audit|risk_config|step_6|halt_ttl|paper_state_restore|halt_session"
```

結果：**唯一 match = `helper_scripts/canary/engine_watchdog.py | 525 +++`**。

Layer A 真正核心檔案（`rust/openclaw_engine/src/risk/halt_session.rs` / `risk_config.rs` / `halt_audit_pg_writer.py` / V096-V098 migrations / `paper_state_restore_*`）**0 diff**。

E1 守住 Layer B only boundary。**無 scope creep**。

---

## 6. Layer A cron still working post Layer B

### 6.1 halt_audit.log file

```
ssh trade-core "wc -l /tmp/openclaw/halt_audit.log && tail -3 /tmp/openclaw/halt_audit.log"
```

結果：**2 行**，內容對齊 Round 2 真實事件鏈：
- L1: `halt_session_set` (kind=session_drawdown, halt_set_ts_ms=1779231585423, reason="SESSION DRAWDOWN: 27.51% >= 25.00%", paper_state_balance_history 含 peak+current)
- L2: `halt_session_manual_cleared` (clear_path=ipc_resume, elapsed_ms=827617)

→ Layer A forensic log 保留完整，Layer B 無寫入 halt_audit.log（spec 明示 Layer B 走獨立 `watchdog_inert_events.jsonl` channel）。

### 6.2 governance_audit_log PG rows

```
SELECT COUNT(*) FROM learning.governance_audit_log
WHERE event_type LIKE 'halt_session_%' AND ts >= NOW() - INTERVAL '24 hours';
```

結果：**2 rows**（Layer A Round 2 forensic chain set + manual_cleared，與 halt_audit.log 對齊）。

→ Layer A cron infrastructure（`/usr/local/bin/halt_audit_pg_writer_wrapper.sh` + cron 6h / boundary 24h）post Layer B Mac dirty-tree 改動仍正常工作。Layer B 不依賴 cron（Layer B 是 watchdog inline probe，獨立路徑），所以邏輯上不該影響 Layer A — 此查詢只是合理性確認。

---

## 7. Mock 審查

```
grep -nE "patch|MagicMock|Mock\(\)" helper_scripts/canary/test_engine_watchdog.py
```

結果：**0 matches**。

Test 設計：
- `tempfile.mkdtemp()` 隔離真實 filesystem（每 test 獨立 data_dir）
- 真 `evaluate_inert_probe` / `detect_paper_paused_stuck` / `detect_intents_zero_delta` / `run_inert_probe_once` 全跑業務邏輯
- 真 `save_inert_state` / `load_inert_state` JSON round-trip
- 不 mock 時間（用 `time.time()` 取 now，然後在 state.paper_paused_since 上做相對偏移）
- 不 mock JSON parse（測 `test_parse_error_raises` 用真 `"not valid toml ["` 字串）

→ **0 anti-pattern**。E2 mock safety rule 全遵守（不 mock 業務邏輯 / 不 mock 計算 / 不 mock IPC protocol）。

---

## 8. Linux pytest 狀態

```
ssh trade-core "ls helper_scripts/canary/test_engine_watchdog.py helper_scripts/canary/watchdog_inert_probe.toml"
```

結果：**NOT_PRESENT**。

Layer B IMPL 仍在 Mac dirty tree，未 commit、未 push。Linux pull 拿不到，所以 Linux pytest 此次跳過。

Python 是平台無關語言；不需要 cross-arch byte-equiv 驗證。Mac unit test 全綠 + py_compile 0 error 對 Linux runtime 充分。Layer B push 後 Linux deploy 之前如要保險可重跑 `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull && python3 -m pytest helper_scripts/canary/test_engine_watchdog.py -v"` 確認 0 regression（建議 PM 在 push 後做一次）。

---

## 9. 設計觀察（不阻塞 PASS）

### 9.1 `[live_demo]` 是 documented dead config（E1 §5.1）

`watchdog_inert_probe.toml` 含 `[live_demo]` 30min/15min 段，但 `pipeline_snapshot_live.json` 寫 `trading_mode="live"`，無 endpoint hint 區分 LiveDemo vs Live。Resolver 對 `pipeline_snapshot_live.json` 落 `[live]`（15min/10min）。LiveDemo 走較嚴 threshold = fail-strict，符合 "LiveDemo 不因 endpoint 降級" feedback。

E4 認為這 trade-off 合理（fail-strict 比 fail-loose 安全；且若有日後 endpoint hint 加入，TOML 段已預留）。E2 review 階段 operator 可決定是否在 spec L-3 加 endpoint hint 字段；此次 IMPL acceptable。

### 9.2 E1 「90/90」口徑（無實質 BLOCKER）

E1 self-report 稱「90/90 PASS（58 existing canary + 32 new）」是只計 `test_canary.py + test_engine_watchdog.py`（58 + 32 = 90），未把 `healthchecks/tests/*` 60 個 + `test_halt_audit_pg_writer.py` 20 個算入。從廣域 canary 看是 **170/0**；無誤、無倒退；只是口徑差異。E4 主以實際 directory-level pytest 數為準。

### 9.3 LOC governance（§九）

| File | LOC | 上限 |
|---|---|---|
| `engine_watchdog.py` | 1285 | 2000 hard cap ✅ |
| `test_engine_watchdog.py` | 581 | 2000 hard cap ✅ |
| `watchdog_inert_probe.toml` | 38 | 不適用 ✅ |

`engine_watchdog.py` 1285 > 800 警戒線；但 Layer B 加 525 是合理（spec §4 全部功能納在同檔內，符合既有 watchdog 慣例）。E4 標記 attention 給 operator 知悉但不阻塞 PASS。

### 9.4 SLA 觀察

Layer B 加 per-iteration probe（spec §4），每 poll_interval（預設 10s）跑一次。實測 32 個 test 跑 0.02s 已包含 inert_probe 全路徑。Watchdog 是長住 loop process，per-iter cost 毫秒級對 watchdog 健康監控延遲無感影響。

無 hot-path bench 需求（Layer B 不在 tick path 上）。Layer A 已驗 hot_path p99=27.79μs，Layer B 不影響此路徑。

---

## 10. 結論 + 建議

**PASS to PM sign-off**。

理由整理：
1. Mac pytest 32/0 PASS x2 non-flaky；廣域 canary 170/0 全綠 x2
2. 7 個 AC B-1..B-7 全有具名 test cover，B-1/B-1a/B-2/B-3/B-4/B-5/B-7 直接斷言；B-6 是 deploy 後 7d passive 觀察（不在 E4 階段範圍）
3. Mock 審查 0 anti-pattern（無 mock 業務邏輯 / 無外部 IO 依賴 / 真函式真 tempfile）
4. Layer A 文件零 diff，scope creep 0
5. Layer A halt_audit.log + governance_audit_log 完整保留，post Layer B cron infra 0 regression
6. CLI 兩 flag 可見、py_compile 0 error
7. §九 LOC 0 hard-cap breach
8. 設計 trade-off（`[live_demo]` dead config + 「90/90」vs 170 口徑）皆 documented，不阻塞

**建議 push 後動作**（不在 E4 階段執行，留給 PM/operator）：
1. push commit 後 `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only && python3 -m pytest helper_scripts/canary/test_engine_watchdog.py -v"` 確認 Linux 0 regression
2. Linux watchdog restart（如 PM 決定部署）後觀察 7d false-positive rate（spec B-6）
3. 若 LiveDemo endpoint 區分將來成需求，spec L-3 加 endpoint hint 字段 + watchdog 端 resolver 升級（目前 dead config 預留即可）

**退回 E1 清單**：無。

---

## 11. 命令證據附錄（E4 親跑時間戳）

```
2026-05-20 (Asia/Taipei timezone)

# Mac unit test run 1
$ cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest helper_scripts/canary/test_engine_watchdog.py -v
============================== 32 passed in 0.02s ==============================

# Mac unit test run 2 (flaky check)
$ python3 -m pytest helper_scripts/canary/test_engine_watchdog.py -q
32 passed in 0.02s

# Wider canary run 1
$ python3 -m pytest helper_scripts/canary/
============================= 170 passed in 31.17s =============================

# Wider canary run 2 (flaky check)
$ python3 -m pytest helper_scripts/canary/ -q
170 passed in 31.13s

# py_compile + CLI help
$ python3 -m py_compile helper_scripts/canary/engine_watchdog.py
(silent success)
$ python3 helper_scripts/canary/engine_watchdog.py --help
... --disable-inert-probe ... --inert-probe-config ...

# Scope creep check (Layer A files)
$ git diff HEAD --stat | grep -iE "halt_audit|risk_config|step_6|halt_ttl|paper_state_restore|halt_session"
 helper_scripts/canary/engine_watchdog.py | 525 +++  (only match — Layer B file itself)

# Layer A cron post-Layer B integrity
$ ssh trade-core "wc -l /tmp/openclaw/halt_audit.log"
2 /tmp/openclaw/halt_audit.log

$ ssh trade-core "psql 'postgresql://...' -c \"SELECT COUNT(*) FROM learning.governance_audit_log WHERE event_type LIKE 'halt_session_%' AND ts >= NOW() - INTERVAL '24 hours';\""
 rows_24h = 2
```

---

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_e4_regression.md`

**E4 REGRESSION DONE: PASS**
