# W-AUDIT-8a C1 v2 Resilient Harness — Consolidated 6-fix E1 Self-Report

Date: 2026-05-16
Owner: E1
Ticket: P1-W-AUDIT-8A-C1-RETRY-PLAN-1（Phase 2 IMPL consolidated fix）
Worktree branch: `worktree-agent-a58d99ef4ea1a440b`
Base commit: `5983f955`（v2 IMPL DONE）
Design SoT: `docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md`
Adversarial review sources:
- A3: `docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_a3_adversarial_review.md`（APPROVE-CONDITIONAL 7.5/10）
- E2: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_e2_review.md`（RETURN to E1）
Status: **IMPL DONE — 待 E2 re-review + PM merge + operator deploy**

---

## §1 6 Fix Diff Summary

### Fix 1: A3 CRITICAL-1 — UTC midnight cutoff 5min buffer

**檔位**: `helper_scripts/bybit/liquidation_topic_probe_v2.py:710-733` `_wait_until_next_utc_midnight()`

**前**：30s buffer + `now.hour == 0 and now.minute == 0 and now.second <= 30`
**後**：5min buffer + `seconds_since_midnight = now.hour*3600 + now.minute*60 + now.second; if seconds_since_midnight < 300: return`

**核心改動 diff**：
```diff
-        if now.hour == 0 and now.minute == 0 and now.second <= 30:
-            time.sleep(max(0, 30 - now.second))
+        seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
+        if seconds_since_midnight < 300:
             return
```

**效果**：operator 在 `2026-05-17T00:00:45Z` paste 啟動 script → 進 5min buffer 內 → 立即開始，不會走「加一天」分支等近 24h。新增中文 docstring 解釋為什麼 5min（避免 operator hang 誤判 → kill → 重派 cycle）。

---

### Fix 2: A3 CRITICAL-2 + E2 MEDIUM-2 — Atomic checkpoint write

**檔位**: `helper_scripts/bybit/liquidation_topic_probe_v2.py:390-422` 新增 `_atomic_write_text()` + 改 `_write_checkpoint()` + L908-933 改 `write_reports()` 用 atomic for latest only

**核心改動**：
```python
def _atomic_write_text(target_path: Path, payload: str, *, encoding: str = "utf-8") -> None:
    """POSIX atomic rename pattern：tmp 寫完 flush + rename 一次性切換 inode。"""
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding=encoding)
    tmp_path.replace(target_path)
```

**Scope（per task constraint）**：
- `_write_checkpoint` (`c1_proof_progress.json`) → atomic ✅（24h × 24 次 overwrite，operator `jq` 監控 high frequency）
- `write_reports` latest 兩檔 (`liquidation_topic_probe_v2_latest.{json,md}`) → atomic ✅
- `write_reports` dated 兩檔 (`liquidation_topic_probe_v2_<UTC>.{json,md}`) → 直接寫 ✅（一次性 final write，路徑唯一無 concurrent overwrite，per task 明示）

**效果**：24h proof 期間 operator `jq . progress.json` 隨時看狀態，永遠看到 old 或 new 完整 JSON，不會 `jq: parse error: Unfinished string`。

---

### Fix 3: E2 HIGH-1 + A3 ADV-4 — `connection_errors` vs `keepalive_warnings` 拆分

**檔位**:
- `liquidation_topic_probe_v2.py:164-170` 新 `ProbeV2Stats.keepalive_warnings: list[str]` field
- `liquidation_topic_probe_v2.py:437-440` initial connect keepalive warning path 改寫入 `keepalive_warnings`
- `liquidation_topic_probe_v2.py:588-590` reconnect keepalive warning path 改寫入 `keepalive_warnings`
- `liquidation_topic_probe_v2.py:729-758` 新增 `_FATAL_CONNECTION_ERROR_PREFIXES` whitelist + `_has_fatal_connection_error()` helper
- `liquidation_topic_probe_v2.py:805-810` `assess()` 致命條件改用 whitelist prefix match（取代「非空 list」judge）
- `liquidation_topic_probe_v2.py:898-905` `render_markdown()` 新增 `## Keepalive Warnings (non-fatal, last 20)` section

**核心改動**：
```python
_FATAL_CONNECTION_ERROR_PREFIXES = (
    "initial_connect_failed:",
    "recv_failed:",
    "ping_send_failed:",
    "subscribe_failed:",
    "websocket-client unavailable:",
    "restart_budget_exhausted:",
)
# assess() 內：
if (
    _has_fatal_connection_error(stats.connection_errors)  # 改：白名單 prefix match
    and stats.elapsed_sec < args.proof_min_duration_sec
    and not stats.c1_proof_eligible
):
    ...
```

**效果**：
- Mac dev / sandbox 受限 sockopt 環境跑 60s smoke 不再系統性誤判 `FAIL_RECONNECT_EXHAUSTED`
- `non_json_message: ...` data-quality warning 也不再觸發 FAIL（whitelist 不含）
- Operator 看 markdown report 在 「Connection Errors」與「Keepalive Warnings (non-fatal)」兩 section 分離

---

### Fix 4: E2 MEDIUM-1 — assess() PASS path 加 `reconnect_failures < 3` gate + new `FAIL_RECONNECT_INSTABILITY` verdict

**檔位**: `liquidation_topic_probe_v2.py:760-802` `assess()` PASS path 修改

**核心改動**：
```python
stats.c1_proof_eligible = (
    stats.elapsed_sec >= args.proof_min_duration_sec
    and stats.uptime_ratio >= args.proof_min_uptime_ratio
    and stats.reconnect_failures < 3                # 新增 gate
)

# 24h+ 跑滿但 reconnect_failures ≥ 3 → 顯式 FAIL_RECONNECT_INSTABILITY
if (
    stats.elapsed_sec >= args.proof_min_duration_sec
    and stats.uptime_ratio >= args.proof_min_uptime_ratio
    and stats.reconnect_failures >= 3
):
    stats.verdict = "FAIL_RECONNECT_INSTABILITY"
    stats.c1_blocker = (
        f"Reconnect failures ({stats.reconnect_failures}) reach threshold; "
        f"instability undermines BB sign-off invariant (c) reconnect_failures<3."
    )
    return
```

**效果**：BB sign-off invariant (c) `reconnect_failures < 3` 在 assess() 內顯式 enforce。原 design §5.3 此條件只在 markdown sign-off oneliner 才查（`test "$(jq ...)" -lt 3`），現在 verdict 級 short-circuit。

---

### Fix 5: A3 WARN-1 — Wrapper script `helper_scripts/bybit/run_c1_v2_proof.sh`（新檔）

**檔位**: `helper_scripts/bybit/run_c1_v2_proof.sh`（NEW，138 LOC，`chmod +x`）

**設計**：
- `set -euo pipefail` 安全模式
- 統一 `SESSION_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"` 一次（避兩次 date 不一致 nanosecond race）
- 自動定位 `PROBE_PY` 透過 `SCRIPT_DIR`（不寫死路徑）
- 兩 mode 二選一（per task 明示「合一含 flag 二選一；E1 判」）：
  - 預設 `proof` (24h)：`nohup` background + redirect 全 log + echo PID + checkpoint hint + early-abort hint
  - `--smoke-60s`：foreground exec（retcode 立即可見）+ 60s checkpoint interval
- 中文 module header 注釋說明 v1 vs v2 / design plan ref / 為何 wrapper
- `--help / -h` flag 顯示 usage

**Operator UX**：
```bash
# 24h proof：
ssh trade-core 'bash ~/BybitOpenClaw/srv/helper_scripts/bybit/run_c1_v2_proof.sh'
# 60s smoke：
ssh trade-core 'bash ~/BybitOpenClaw/srv/helper_scripts/bybit/run_c1_v2_proof.sh --smoke-60s'
```

兩條 oneliner 都 < 120 char，paste-safe per `feedback_shell_paste_safety.md` 規則 D。

---

### Fix 6: A3 WARN-2 — `--max-restart` help text 改清楚

**檔位**: `liquidation_topic_probe_v2.py:243-251` argparse `--max-restart` help

**前**：`"連續 reconnect 用盡時的 session restart 上限（design §3.4 = 3）"`
**後**：`"Maximum number of session restarts after the initial session (initial + N restarts allowed). max-restart=3 means up to 4 total sessions (1 initial + 3 restarts). Design §3.4."`

**效果**：operator 跑 `--help` 看到 4 total sessions 語意（不再歧義為「3 次重連總共」）。業務邏輯（`if stats.restart_count > args.max_restart`）未動。

---

## §2 Test 新增 + Run Result

| Suite | baseline | 新增 | 累計 |
|---|---:|---:|---:|
| TestBuildTopics | 3 | 0 | 3 |
| TestParseArgs | 3 | 0 | 3 |
| TestBackoffSequence | 4 | 0 | 4 |
| TestClassifyPayload | 6 | 0 | 6 |
| TestInterimVerdict | 5 | 0 | 5 |
| TestAssess | 9 | 0 | 9 |
| TestCheckpointWrite | 2 | 0 | 2 |
| TestReconnectPath | 2 | 0 | 2 |
| TestRestartCap | 2 | 0 | 2 |
| **TestUtcMidnightBuffer** (Fix 1) | — | **3** | 3 |
| **TestAtomicWrite** (Fix 2) | — | **3** | 3 |
| **TestKeepaliveWarningsSeparation** (Fix 3) | — | **4** | 4 |
| **TestReconnectFailuresInstabilityGate** (Fix 4) | — | **3** | 3 |
| **Total** | **36** | **13** | **49** |

新增 13 test（**比預計 4-6 多**，覆蓋更扎實）。

### Run Result（non-flaky 兩遍）

```
$ python3 -m unittest test_liquidation_topic_probe_v2 -v
...
Ran 49 tests in 0.007s
OK

$ python3 -m unittest test_liquidation_topic_probe_v2 -v
...
Ran 49 tests in 0.006s
OK
```

49/49 PASS，0.007s + 0.006s（deterministic + fast）。

### 重點測試覆盤

1. **Fix 1**: `test_00_00_45_within_buffer_returns_immediately` + `test_00_04_59_within_buffer_returns_immediately` + `test_00_05_00_exact_outside_buffer`（boundary case）
2. **Fix 2**: `test_atomic_write_creates_final_file`（無 .tmp residue）+ `test_atomic_write_overwrites_existing`（覆寫 working）+ `test_checkpoint_uses_atomic_no_tmp_residue`（_write_checkpoint integration）
3. **Fix 3**: `test_keepalive_warning_alone_does_not_fail_reconnect`（核心 fix scenario）+ `test_non_fatal_connection_error_does_not_trigger_fail`（whitelist edge）+ `test_fatal_recv_failed_still_triggers_fail`（regression guard：whitelist 不漏接致命）+ `test_keepalive_warnings_field_exists_in_dataclass`（schema sanity）
4. **Fix 4**: `test_reconnect_failures_2_full_window_still_pass`（< 3 boundary PASS）+ `test_reconnect_failures_3_boundary_blocks_pass`（= 3 boundary FAIL）+ `test_reconnect_failures_5_blocks_pass`（far above boundary FAIL）

---

## §3 Wrapper script content + UX

**Path**: `helper_scripts/bybit/run_c1_v2_proof.sh`（NEW，138 LOC，executable）

### Help output validated

```
$ bash helper_scripts/bybit/run_c1_v2_proof.sh --help
W-AUDIT-8a C1 v2 resilient harness wrapper

Usage:
  bash run_c1_v2_proof.sh                # 24h proof (default)
  bash run_c1_v2_proof.sh --smoke-60s    # 60s smoke (verify tooling reachable)
  bash run_c1_v2_proof.sh --help

Flags:
  --smoke-60s    Run 60s smoke mode (non-blocking; immediate result)
  --help, -h     Show this help

[...]
```

### Operator UX 對比

| | 改前（A3 WARN-1 揭露） | 改後 |
|---|---|---|
| 24h proof 啟動 oneliner 長度 | ~380 chars（含 ssh + 全 flag + 兩 $(date) 展開 + nohup redirect） | ~85 chars（`ssh trade-core 'bash ~/...run_c1_v2_proof.sh'`） |
| `$(date ...)` 展開次數 | 2 次（session_id + nohup log path）有 nanosecond drift race | 0 次外層；wrapper 內統一 SESSION_STAMP 一次 |
| paste-safety per `feedback_shell_paste_safety.md` D | ⚠️ >120 char + 動態變數雙展開 | ✅ <120 char + 純靜態 ssh argument |
| Smoke mode 支援 | 需要 operator 自己改 oneliner（容易漏 flag） | `--smoke-60s` flag 即可，common flags 已封裝 |
| 早期 abort 提示 | 無 | wrapper echo `kill PID + touch ABORTED_<UTC>.flag` 提示 |

---

## §4 Defer ADV/LOW 列表 (P2 follow-up — 不在本 fix scope)

per task 明示「其他 ADV/WARN defer 不修，commit message 列入 P2 follow-up」：

| Item | Source | Severity | Status |
|---|---|---|---|
| Checkpoint JSON 24h 膨脹（events.jsonl 拆檔） | A3 WARN-3 / E2 LOW-1 | P2 | DEFER |
| `args.duration_sec` mutation refactor | A3 ADV-1 | P2 | DEFER |
| `blocker_if_aborted_now` dynamic text by elapsed | A3 ADV-2 | P2 | DEFER |
| CONTROL_SILENT trigger IMPL（design §3.4 完整性） | A3 ADV-3 | P2 | DEFER |
| `consecutive_attempt` dead parameter | E2 LOW-2 | P2 | DEFER |
| disk-full OSError graceful handling | E2 LOW-3 | P2 | DEFER |
| File size 1045 > 800 警告（accept high-cohesion exception） | E2 LOW-1 | governance | ACCEPT |
| BB A-1 ping 10s vs docs 20s | BB advisory | Phase C IMPL | DEFER |
| BB A-2 reconnect base 1s vs production 3s | BB advisory | Phase C IMPL | DEFER |
| BB A-3 字典 §2.1 補錄 | BB advisory | C1 PASS 後 BB1 task | DEFER |
| MIT HIGH-1 V002 chunk_interval drift | MIT advisory | P2 doc fix | DEFER |
| MIT MED-1 side CHECK constraint | MIT advisory | Phase C IMPL OPTIONAL | DEFER |

**Test 檔同樣超 800**（913 LOC）— 視為 test 檔 high-cohesion 例外（accept；不需 PM exception clause，因 test 檔治理寬鬆）。

---

## §5 Cross-platform + chinese-only-comment check

| Check | 結果 |
|---|---|
| `grep -E '(/home/ncyu|/Users/[^/]+)' <3 changed files>` | ✅ 0 命中 |
| `OPENCLAW_DATA_DIR` env usage | ✅ wrapper + probe 都用 `${OPENCLAW_DATA_DIR:-/tmp/openclaw}` fallback |
| `OPENCLAW_BASE_DIR` env usage | ✅ wrapper 用 `SCRIPT_DIR` 動態定位，不寫死 base |
| 注釋只中文（per `feedback_chinese_only_comments.md` 2026-05-05 governance change） | ✅ 新增/修改 inline / docstring 全中文；shell help text 英文（technical reference，是 operator-facing flag desc）；技術名詞（atomic rename / POSIX / sockopt）保留 English token |
| Python source TCP keepalive cross-platform guard | ✅ 既有 `hasattr(socket, "TCP_KEEPIDLE")` fallback 邏輯未動 |
| Bash wrapper `set -euo pipefail` | ✅ 安全模式 |
| Bash wrapper `bash -n` syntax check | ✅ pass |

注：`_FATAL_CONNECTION_ERROR_PREFIXES` 內字串如 `"recv_failed:"` 是 internal protocol tag（不是用戶可讀 message），保留 English 與 source-level appended 字串對齊。

---

## §6 Sign-off prereq：E2 re-review + PM merge

### 強制鏈狀態

| Step | 狀態 |
|---|---|
| E1 IMPL DONE（consolidated 6 fix） | ✅ 本 report 標記 |
| E2 re-review | ⏳ 待派 |
| E4 regression smoke (60s real WS) | ⏳ 待派（E2 通過後） |
| BB advisory recheck | ⏳ 待派（schema 0 改，可能 skip） |
| MIT advisory recheck | ⏳ 待派（schema 0 改，可能 skip） |
| PM merge | ⏳ 待 E2/E4 全綠 |
| Operator deploy | ⏳ 待 PM merge |

### 不自評 sign-off

per task constraint + `feedback_impl_done_adversarial_review.md`：
- 高風險 IMPL（GUI / IPC / 寫操作 / 共用 helper 改動）E1 自評 IMPL DONE **不接受單獨 sign-off**
- 本 commit 改 `assess()` 邏輯（共用判定 helper）+ atomic write helper（filesystem 寫操作）
- 必走 E2 re-review；E4 regression 後 PM merge

### 維持在現有 worktree

- ✅ 在 worktree branch `worktree-agent-a58d99ef4ea1a440b` 上加 commit（不開新 worktree）
- ✅ Worktree 與 origin 同步至 `5983f955`，新 fix commit 將在此基礎上加 1
- ✅ Self-report 寫至 main repo `srv/docs/CCAgentWorkSpace/E1/workspace/reports/`（per task 明示）

### Diff summary

```
helper_scripts/bybit/liquidation_topic_probe_v2.py  | +124 / -18  (942→1045)
helper_scripts/bybit/test_liquidation_topic_probe_v2.py | +257 / 0  (656→913)
helper_scripts/bybit/run_c1_v2_proof.sh             | +138 / 0  (NEW)
Total: 3 files, +519 / -18
```

v1 (`liquidation_topic_probe.py`) 0 改動（diff 0 byte，control comparison 完整保留）。

---

## §7 改動 limits 自審

| 限制 | 自審 |
|---|---|
| 不開新 worktree（在現有 branch 加 commit） | ✅ |
| 注釋全中文（除 technical token / operator-facing flag desc / internal protocol tag） | ✅ |
| 禁止 spawn 第二層 sub-agent | ✅ 單 E1 instance |
| v1 100% 保留不動 | ✅ diff 0 byte |
| 不動 production builder / writer / authorization | ✅ 改動全在 probe_v2 / test_v2 / wrapper script |
| IMPL DONE 後不自評 sign-off | ✅ 本 report 標 「待 E2 re-review + PM merge」 |
| 9 安全不變式 / 16 根原則 | ✅ 0 觸碰（read-only WS probe + atomic file write only） |
| 硬邊界（max_retries / live_execution / execution_authority） | ✅ 0 觸碰 |

---

**E1 IMPL DONE — 待主 session 派 E2 re-review。**
