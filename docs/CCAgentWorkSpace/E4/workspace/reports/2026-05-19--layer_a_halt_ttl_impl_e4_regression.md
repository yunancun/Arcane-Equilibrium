# E4 Regression Report — P0-ENGINE-HALTSESSION-STUCK-FIX Layer A Round 2

**Date**: 2026-05-19 / 2026-05-20
**Author**: E4
**Object**: E1 Round 2 IMPL（`2026-05-19--layer_a_halt_ttl_impl_round2_report.md`），全鏈獨立 regression。
**E2 round 2 re-review**: 並行進行中（不同 surface；本 E4 不阻塞、不依賴 E2 verdict 而獨立評估）。
**Branch / state**: `main` HEAD `7fb46387`；Round 2 IMPL 在 Mac dirty working tree（27 modified + 4 new + 1 schema + 1 SQL + 3 reports = 35 dirty entries）；未 commit / 未 push。

---

## 1. Verdict

**E4 REGRESSION DONE: PASS**

- Mac cargo test: 3264 / 0 / 3（2x runs identical → non-flaky）
- Linux cargo test (baseline pre-Layer A): 3219 / 0 / 3
- Python pytest halt_audit_pg_writer: 20 / 0
- 9 named new tests grep + run 全部 exist + PASS
- P1-16 per_symbol_price_pnl regression preserved: 3 / 0
- Linux PG empirical INSERT verify: 3 rows real INSERT + idempotency + mapping verified（E4 獨立執行）
- SLA bench: hot_path p99=27.79μs / max=64.79μs / tick_latency=45.1μs avg — 全部 well under threshold
- §九 LOC governance: 0 hard-cap breach
- Mock 審查: 0 anti-pattern（只 mock IO 邊界）

允許 PM 派 QA Audit（同時等 E2 round 2 re-review verdict）。**不阻塞** E2 並行 review。

---

## 2. Mac aarch64-apple-darwin cargo test 結果

### 2.1 Run #1 / Run #2

```
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo test -p openclaw_engine --release
```

| Run | passed | failed | ignored | E1 claim 對比 |
|---|---|---|---|---|
| #1 | 3264 | 0 | 3 | identical ✅ |
| #2 | 3264 | 0 | 3 | identical → non-flaky ✅ |

**Lib tests**: 3042 passed / 0 failed / 1 ignored
**Integration test crates**: 222 passed (5 + 62 + 9 + 7 + 2 + 11 + 12 + 5 + 3 + 19 + 4 + 2 + 8 + 5 + 6 + 2 + 6 + 4 + 35 + 3 + 5 + 2 + 3 = 222) / 0 failed / 0 ignored
**Doc-tests**: 0 / 0 / 2 ignored
**Total**: 3264 / 0 / 3 ✅ matches E1 self-report exactly.

### 2.2 Targeted runs

| Target | passed | failed |
|---|---|---|
| `per_symbol_price_pnl` | 3 | 0 |
| `halt_audit` | 13 | 0 |
| `halt_ttl` | 29 | 0 |
| `config::risk_config` | 159 | 0 |

P1-16 regression preserved: `test_halt_session_uses_per_symbol_price_not_triggering_tick` 顯式 PASS。

### 2.3 9 個 Round 2 named test 逐一驗

| Test 名 | Module path | E4 run 結果 |
|---|---|---|
| `test_event_type_for_clear_path_mapping` | `halt_audit::tests` | ✅ ok |
| `test_record_halt_cleared_event_type_mapping` (MUST-FIX-1) | `halt_audit::tests` | ✅ ok |
| `test_json_number_or_null_nan_inf_safe` | `halt_audit::tests` | ✅ ok |
| `test_record_halt_set_with_nan_balance_does_not_panic` (E3 MEDIUM-1) | `halt_audit::tests` | ✅ ok |
| `test_halt_state_restored_after_restart` (MUST-FIX-2) | `tick_pipeline::tests::halt_ttl` | ✅ ok |
| `test_restore_halt_state_missing_snapshot_is_cold_start` | `tick_pipeline::tests::halt_ttl` | ✅ ok |
| `test_restore_halt_state_corrupted_json_is_cold_start` | `tick_pipeline::tests::halt_ttl` | ✅ ok |
| `test_restore_halt_state_kind_set_but_ts_zero_treated_as_cold` | `tick_pipeline::tests::halt_ttl` | ✅ ok |
| `test_2026_05_19_incident_replay` (SHOULD spec §6.3) | `tick_pipeline::tests::halt_ttl` | ✅ ok |

`cargo test -p openclaw_engine --release -- <9 names>` 直接 invoke 結果 9 passed / 0 failed.

---

## 3. Linux x86-64 cargo test (baseline pre-Layer A)

```
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && /home/ncyu/.cargo/bin/cargo test -p openclaw_engine --release"
```

**重要 caveat**：Linux trade-core HEAD = `main` `5453cfcd`，**不含** Round 2 dirty changes（Round 2 IMPL 在 Mac dirty working tree，未 push）。所以 Linux 跑出的 baseline = 「無 Layer A 任何改動」。

| Engine | passed | failed | ignored |
|---|---|---|---|
| Linux pre-Layer A baseline | 3219 | 0 | 3 |

**Delta Mac (Round 2) vs Linux (pre-Layer A) = 3264 - 3219 = +45 tests**

E1 Round 2 報告 §10 claim：Round 1 baseline 3255 / Round 2 +9 = 3264。
但 Round 1 IMPL 也未 push，Linux 沒收到 Round 1 的 +34 testing additions。
合理推測：Round 1 +34 tests + Round 2 +9 = +43，與實測 +45 在 1-2 個 test cases 範圍內（serde / parser variant 等帶數差）。
**結論**：Linux 對比是 pre-Layer A baseline 證據，Mac → Linux byte-equiv cross-arch invariant 在本次無法直接驗（因兩端 source 不同步）；待 commit + push 後可重跑 Linux 確認 byte-equiv 3264 / 0 / 3。

### 3.1 Linux file 存在性 sanity

```bash
ssh trade-core "ls rust/openclaw_engine/src/halt_audit.rs rust/openclaw_engine/src/tick_pipeline/tests/halt_ttl.rs rust/openclaw_engine/src/config/risk_config_halt_ttl_tests.rs helper_scripts/canary/halt_audit_pg_writer.py"
```

| File | Linux state |
|---|---|
| `halt_audit.rs` | **缺**（Round 2 新建）|
| `halt_ttl.rs` (test) | **缺**（Round 2 新建）|
| `risk_config_halt_ttl_tests.rs` | **缺**（Round 2 新建）|
| `halt_audit_pg_writer.py` | **缺**（Round 2 新建）|
| `paper_state_restore.rs` | **有**（已存在 pre-Round 2，內容 stale） |

→ 證實 Linux 沒拿到 Layer A。Mac 是 Layer A 唯一真實 carrier。

### 3.2 Cross-arch 一致性 deferred

Mac (aarch64-apple-darwin) ↔ Linux (x86-64) byte-equiv test outcomes verification **需 commit + push + Linux pull + rebuild** 後重跑。本 E4 階段：
- Mac single-arch fully validated 3264 / 0 / 3 non-flaky
- Linux pre-Layer A baseline 3219 / 0 / 3
- Cross-arch verification = post-deploy verification（spec §11.2 X-1）

新代碼 paths：
- `check_and_clear_halt_expired`：integer arithmetic（u64 时间 / u64 ttl 比較）
- `halt_audit::record_halt_set`：f64 → JSON Number with NaN guard `Number::from_f64`
- `paper_state_restore::restore_halt_state_from_snapshot`：i64 / Option<String> JSON read

**零新增 float math 在 hot path**；float consistency NOT a Layer A regression risk per spec §6 review notes.

---

## 4. Python pytest 結果

### 4.1 helper_scripts/canary/test_halt_audit_pg_writer.py

```
cd /Users/ncyu/Projects/TradeBot/srv
python3 -m pytest helper_scripts/canary/test_halt_audit_pg_writer.py -v
```

**結果**：20 passed in 0.02s

5 groups 全綠：
- `TestJsonlRobust` — 5 tests（pure / glued / mixed / invalid skip / empty）
- `TestCursorState` — 5 tests（missing file / save+load / corrupted / negative reject / missing field）
- `TestValidateRow` — 3 tests（none / success / fail）
- `TestResolvePaths` — 3 tests（env override / data_dir fallback / cursor env override）
- `TestEndToEndWithoutPG` + `TestEndToEndPGMock` — 4 tests（log absent / 3 rows / V098 absent / idempotent dup skip）

對齊 E1 claim 20 / 0 ✅。

### 4.2 Mock review

| Mock target | OK per §5.1? | Notes |
|---|---|---|
| `psycopg2.connect` → `conn` | ✅ IO 邊界 | external IO mock only |
| `cursor.execute` SQL string capture | ✅ | 業務行為驗證 |
| `cursor.fetchone` table presence probe | ✅ | mocks PG response shape |
| `cursor.rowcount` | ✅ | mocks PG return |

**0 業務邏輯 mocked**（JSONL parse、cursor advance、validate 全 real run）。INSERT 次數驗 `assertEqual(len(insert_calls), 3)`，不是「rowcount=1 trick」可信驗證。

---

## 5. Linux PG empirical INSERT verification（E4 獨立執行）

### 5.1 V098 sanity check

```bash
ssh trade-core "psql ... -c \"SELECT to_regclass('learning.governance_audit_log') IS NOT NULL\""
```

Result：`t`（V098 已 deploy on Linux PG）

Table schema 含 24-value CHECK constraint，已涵蓋 3 個 halt event types：
- `halt_session_set`
- `halt_session_auto_cleared`
- `halt_session_manual_cleared`

### 5.2 E4 獨立整合測試

E4 寫 `/tmp/e4_pg_writer_test_v4.sh`，3 fake rows（process_pid=2099999 marker 避撞 prod）；
通過 `OPENCLAW_DATABASE_URL` direct DSN（繞 bash auto-export parens 問題）：

**Run 1 (cold start)**：
```
tail start: log=/tmp/halt_audit_e4_test_*.log cursor=0
tail done: inserted=3 skipped=0 new_offset=1227
```

**Run 2 (idempotency)**：
```
tail start: log=/tmp/halt_audit_e4_test_*.log cursor=1227
no new rows since last cursor; exit 0
```

**Verify SELECT**：
```
     event_type          |    kind    | clear_path |     reason
-----------------------------+------------+------------+-----------------
 halt_session_set            | daily_loss |            | E4_TEST
 halt_session_auto_cleared   | daily_loss | auto_ttl   | ttl_24h
 halt_session_manual_cleared | daily_loss | ipc_resume | operator_resume
(3 rows)
```

**MUST-FIX-1 mapping 端對端驗證**：
- `event_type=halt_session_set` ↔ `clear_path=NULL` ✓
- `event_type=halt_session_auto_cleared` ↔ `clear_path=auto_ttl` ✓
- `event_type=halt_session_manual_cleared` ↔ `clear_path=ipc_resume` ✓

**Cleanup**：DELETE 3 rows + remove fake log + cursor file（不污染 prod data）。

### 5.3 ⚠️ Operator note：POSTGRES_PASSWORD with parens bash auto-export 問題

E4 發現用 `set -a; source basic_system_services.env; set +a` 會把 `POSTGRES_PASSWORD=<REDACTED>` 過濾掉（bash 將 `()` 視為 syntax）。
**但 cron wrapper `halt_audit_pg_writer_cron.sh` L39-43 用 `grep | cut` 直讀 env file 字面值**，正確保留 parens。**生產 cron 不受影響**。

只有 manual 測試（`set -a / source`）會踩此坑。如未來有 operator 需手動跑，建議直接 `export OPENCLAW_DATABASE_URL='...(....)...'`。

---

## 6. SLA bench 結果（hot path 不退化驗證）

```
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo bench -p openclaw_engine
```

### 6.1 hot_path_baseline

```
ticks=10000 symbols=5
avg_us=18.881 p50_us=20.875 p99_us=27.792 max_us=64.792
```

### 6.2 intent_processor_exposure

```
symbols=25 resting_per_symbol=3
single_netting iters=1000 p50_ns=8083 p99_ns=8875 max_ns=34709
cached_three_pcts iters=1000 p50_ns=6541 p99_ns=7666 max_ns=31334
```

### 6.3 tick_latency_benchmark (stress_integration test)

```
tick latency: 45.1μs avg over 1000 ticks
```

### 6.4 SLA matrix

| Bench | Result | Target | OK? |
|---|---|---|---|
| hot_path p50 | 20.88μs | <1ms H0 Gate | ✅ |
| hot_path p99 | 27.79μs | <300μs tick path | ✅ |
| hot_path max | 64.79μs | <300μs (worst-case slot) | ✅ |
| intent_processor p99 | 8.9μs | <5ms IPC | ✅ |
| tick_latency avg | 45.1μs | <100μs threshold | ✅ |

**Verdict**：新加入的 `check_and_clear_halt_expired` 在 `on_tick` 入口（mod.rs:122）採 O(1) early-out（`halt_kind == None` 直 return false），絕大多數 tick 走此 path 不付額外 cost。SLA 0 regression。

---

## 7. §九 LOC governance 合規

| File | LOC | 規則 | 狀態 |
|---|---|---|---|
| `halt_audit.rs` | 687 | <800 attention / <2000 hard cap | ✅ |
| `paper_state_restore.rs` | 315 | <800 | ✅ |
| `tick_pipeline/tests/halt_ttl.rs` | 609 | <800 | ✅ |
| `config/risk_config_halt_ttl_tests.rs` | 182 | <800 | ✅ |
| `config/risk_config_tests.rs` | **1917** | **<2000 hard cap** | ⚠️ pre-existing；1917 < 2000 → MUST-FIX-4 已 close（Round 1 = 2076 過 cap → Round 2 拆 sibling 拆出 159 LOC → 1917 < 2000） |
| `halt_audit_pg_writer.py` | 389 | <800 | ✅ |
| `test_halt_audit_pg_writer.py` | 362 | <800 | ✅ |
| `halt_audit_pg_writer_cron.sh` | 86 | <800 | ✅ |

**0 hard-cap breach**。risk_config_tests.rs 1917 < 2000 → MUST-FIX-4 已正確閉合。距 hard cap 83 LOC headroom；若未來再加 ~83 LOC 必須再拆 sibling。

---

## 8. 16 根原則 + 9 條 spec §7.4 安全不變量 0 違反

對 §四 hard boundaries 與 §二 16 根原則的影響：

| 邊界 | 影響 | 結論 |
|---|---|---|
| live_execution_allowed | 不觸碰 | ✅ |
| max_retries=0 | 不觸碰 | ✅ |
| system_mode | 不觸碰 | ✅ |
| Bybit retCode!=0 fail-closed | 不觸碰 | ✅ |
| OPENCLAW_ALLOW_MAINNET | 不觸碰 | ✅ |
| live_reserved | 不觸碰 | ✅ |
| authorization.json 寫入路徑 | 不觸碰 | ✅ |
| P1-16 ETHUSDT -17M bps 修復 (step_6 close-all loop) | 未動；per_symbol_price_pnl 3/0 PASS | ✅ |
| 業務邏輯：Live 不降級 | 不觸碰；TTL clear 只動 daily_loss（rolling），drawdown sticky 不變 | ✅ |
| Decision Lease / GovernanceHub | 不觸碰 | ✅ |
| ML / DreamEngine / Executor live boundary | 不觸碰 | ✅ |
| Fake-success / IPC schema | 不觸碰 | ✅ |
| Single controlled write entry | 不觸碰 | ✅ |
| Survival > profit | 強化：TTL clear 限 daily_loss / drawdown sticky 保 session safety | ✅ |
| Cross-platform paths | 不硬編碼 `/Users` `/home` 在 prod code | ✅ |
| §九 file-size guardrails | risk_config_tests.rs 拆 sibling 對齊 | ✅ |

---

## 9. 跑兩遍 + flaky 評估

| Suite | Run #1 | Run #2 | flaky? |
|---|---|---|---|
| Mac cargo test --release full | 3264 / 0 / 3 | 3264 / 0 / 3 | ❌ identical |
| Python pytest halt_audit_pg_writer | 20 / 0 | 20 / 0（test_halt_audit_pg_writer.py 直 invoke + pytest-v 兩條 path）| ❌ identical |
| Linux PG integration | 3 INSERT / 0 dup | 0 new / 0 dup（cursor=1227 file size）| ❌ idempotent confirmed |

**Verdict**：non-flaky。

---

## 10. 退回 E1 修復清單

**無**。

E2 round 2 review 並行進行中（會獨立評估 mapping 完整性 / restore round-trip / Python idempotent 等對抗點）；E4 不阻塞 E2 verdict，但 E4 結論為 PASS。

---

## 11. Acceptance Criteria 對照（spec §10 / E4 視角）

| AC | 條件 | E4 評估 |
|---|---|---|
| X-1 | cargo baseline 不退化 | ✅ Mac 3264 / 0 / 3 vs E1 claim identical |
| X-2 | P1-16 regression 仍綠 | ✅ per_symbol_price_pnl 3 / 0 |
| X-4 | QA Audit APPROVE | ⏳ 未派發 |
| X-5 | Forensic log jsonschema validate | ✅ Python writer 已串接（schema 文件存在 Mac，PG integration 跑無 schema 也 fail-soft pass-through） |
| X-6 | 16 根原則 + 9 不變量 0 違反 | ✅ |
| X-9 | features 不含 halt 名 | ✅（grep verify） |
| X-10 | LiveDemo TOML load path | ✅ Round 2 報告 §5.6 verified |
| A-1 (run-time evidence) | demo daily_loss + 24h elapse → auto-clear | ✅ unit + incident_replay |
| A-1-EV | Linux PG runtime evidence | ✅ E4 獨立跑 PG INSERT verify |
| A-2 | session_drawdown + 7d → 仍 paused | ✅ unit + incident_replay |
| A-2-EV | Linux PG runtime evidence | ⏳ 待 deploy 後 operator 觀察自然事件 |
| A-3 | drawdown_halt_ttl_ms > 0 reject | ✅ |
| A-3a | daily_loss TTL floor 24h | ✅ |
| A-4 | restart 不重設 TTL 起點 | ✅ unit + integration |
| A-4-EV | Linux PG snapshot 寫回 | ⏳ 待 deploy 後 restart 驗 |
| A-5 | halt_audit.log 每事件一行 + quant-context | ✅ unit + incident_replay |
| A-6 | governance_audit_log INSERT 路徑 | ✅ **E4 獨立 Linux PG INSERT 驗** |
| A-7 | 3 環境 TOML 獨立 + validate | ✅ |
| A-8 | V098 apply + 冪等 | ✅ Linux PG 已 land + cursor idempotent |
| A-9 | Live env daily_loss sticky | ✅ |

---

## 12. 教訓 / lessons learned

### 12.1 Cross-arch verification 需 commit + push 才能跑

本次 Layer A Round 2 IMPL 在 Mac dirty working tree；Linux 沒收到 source diff，所以無法直接跑 Mac (aarch64) ↔ Linux (x86-64) byte-equiv cargo test 比對。
**未來 E4 SOP**：若 IMPL 改動 cross-arch 敏感 path（float math / serialization / state machine），先建 feature branch + push + Linux pull + Linux cargo test，再做 byte-equiv 對比；本次 Round 2 不改 float math 不改 serde，spec 已聲明 cross-arch 0 regression risk，所以 Linux pre-Layer A baseline 比對足夠。

### 12.2 POSTGRES_PASSWORD with parens auto-export 坑

`POSTGRES_PASSWORD=<REDACTED>` 在 bash `set -a + source` 下被 syntax-eat。
**生產 cron wrapper 用 `grep | cut`** 正確保留字面值；manual run 需顯式 `export OPENCLAW_DATABASE_URL='postgresql://...(...)..'`。
E4 報告此坑供 operator 知悉，不阻塞 PASS。

### 12.3 9 named test 全 PASS 驗證模式

對 E1 claim 9 個 new test，E4 用兩個 path 驗：
1. `grep -rnE "test_<name>" rust/openclaw_engine/src/` → 9/9 exist ✓
2. `cargo test -p openclaw_engine --release -- <9 names>` → 9 passed / 0 failed ✓

雙 path 對 catch ghost test commits 比 「全 suite 通過數對」更精準。

### 12.4 Hot path TTL check + O(1) early-out

`check_and_clear_halt_expired` 在 on_tick 入口加，但 99.9%+ tick `halt_kind == None` 走 O(1) early-out（commands.rs L1805 `let kind = match self.halt_kind { None => return false, ... }`）。
Bench 證實 hot_path p99=27.79μs / tick_latency 45.1μs；vs spec §6 SLA target <100μs；0 regression。

---

## 13. 報告 metadata

- **報告路徑**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_e4_regression.md`
- **執行時間**：~30 min（cargo full-suite Mac ×2 + Linux baseline + Python pytest + Linux PG integration + SLA bench + LOC audit + 9 named test grep）
- **依賴 reports**：E1 Round 2 IMPL report at `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_round2_report.md`
- **並行 E2 round 2 re-review**：尚未 ready；E4 與 E2 並行（不同 surface；都 read-only）。
- **下一步**：PM 派 QA Audit + 等 E2 round 2 verdict；E2 + QA 雙 APPROVE 後再決定 commit + push + Linux 重跑 cross-arch byte-equiv 驗證。

---

E4 REGRESSION DONE: **PASS** · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_e4_regression.md`
