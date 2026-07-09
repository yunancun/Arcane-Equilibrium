# E4 Quick Regression — W-AUDIT-8a C1 v2 Harness Consolidated Fix (`dbd0277c`)

- **Date**: 2026-05-16 (UTC ~09:02)
- **Branch**: `worktree-agent-a58d99ef4ea1a440b`
- **HEAD verified**: `dbd0277c` (parent `5983f955` already E4-PASSED 2026-05-16 08:33)
- **Scope**: 6 consolidated fix (A3 CRIT-1/2, E2 HIGH-1+ADV-4, E2 MED-1, A3 WARN-1, A3 WARN-2) + 13 new test + wrapper script
- **Linux host**: `trade-core`
- **Scratch dir**: `/tmp/e4-v2-recheck-1778922043` (cleaned at finish)
- **Verdict**: **PASS**

---

## §1 — Linux fetch + HEAD verify

```
$ ssh trade-core "cd ~/BybitOpenClaw/srv && git fetch origin worktree-agent-a58d99ef4ea1a440b"
   5983f955..dbd0277c  worktree-agent-a58d99ef4ea1a440b -> origin/worktree-agent-a58d99ef4ea1a440b

$ ssh trade-core "cd /tmp/e4-v2-recheck-1778922043 && git log --oneline -3"
dbd0277c W-AUDIT-8a C1 v2 harness — consolidated 6-fix (A3 CRIT + E2 RETURN)
5983f955 W-AUDIT-8a C1 v2 resilient harness IMPL (待 A3+E2+E4+BB+MIT+PM 對抗審)
42558035 fix(gui): tab-demo loadDemoStatus race — serial-first fills + Option B
```

HEAD = `dbd0277c` ✅（consolidated fix commit on top of base `5983f955`）

Clone pattern: `git clone ~/BybitOpenClaw/srv` + `remote set-url origin git@github.com:yunancun/BybitOpenClaw.git` + `git fetch origin worktree-agent-a58d99ef4ea1a440b` + `git checkout -b worktree-agent-a58d99ef4ea1a440b FETCH_HEAD`（local repo 沒本地 branch ref，必須走 GitHub remote）。

對 Linux runtime 0 影響（scratch dir 在 `/tmp`, 0 修改 `~/BybitOpenClaw/srv` working tree, 0 影響 engine PID）。

## §2 — pytest 49/49 result (non-flaky 2x)

| Run | Result | Duration |
|---|---|---|
| Run 1 (`-v`) | **49 passed** in 0.05s | 0.05s |
| Run 2 (`-q`) | **49 passed** in 0.04s | 0.04s |

**Non-flaky**: GREEN-GREEN 兩 run 同綠 ✅

13 suites (baseline 9 + 新 4) 全 PASS：

| Suite | tests | new (Fix #) |
|---|---:|---|
| TestBuildTopics | 3 | — |
| TestParseArgs | 3 | — |
| TestBackoffSequence | 4 | — |
| TestClassifyPayload | 6 | — |
| TestInterimVerdict | 5 | — |
| TestAssess | 9 | — |
| TestCheckpointWrite | 2 | — |
| TestReconnectPath | 2 | — |
| TestRestartCap | 2 | — |
| **TestUtcMidnightBuffer** | **3** | Fix 1 (UTC 00:00:00 5min buffer) |
| **TestAtomicWrite** | **3** | Fix 2 (POSIX atomic rename) |
| **TestKeepaliveWarningsSeparation** | **4** | Fix 3 (whitelist + keepalive split) |
| **TestReconnectFailuresInstabilityGate** | **3** | Fix 4 (reconnect_failures < 3 gate) |
| **Total** | **49** | **13 new** |

Linux 49/49 = Mac 49/49 baseline ✅ (E1 self-verified Mac local 49/49 PASS in 0.007s + 0.006s)

## §3 — wrapper `--help` verify

```
$ bash helper_scripts/bybit/run_c1_v2_proof.sh --help
W-AUDIT-8a C1 v2 resilient harness wrapper

Usage:
  bash run_c1_v2_proof.sh                # 24h proof (default)
  bash run_c1_v2_proof.sh --smoke-60s    # 60s smoke (verify tooling reachable)
  bash run_c1_v2_proof.sh --help
[...]
EXIT_CODE=0
```

✅ Usage displayed, exit 0, Fix 5 wrapper functional。

## §4 — 60s smoke via wrapper (real WS)

### CLI 輸出

```
[run_c1_v2_proof.sh] mode=smoke session_id=c1_v2_smoke_20260516T090120Z
[run_c1_v2_proof.sh] expected duration=60s + ~5s final report write
verdict=SMOKE_PASS_NOT_C1_PROOF
session_id=c1_v2_smoke_20260516T090120Z
latest_report=/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.md
dated_report=/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_20260516T090219Z.md
checkpoint=/tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json
EXIT_CODE=0
```

### Checkpoint JSON 結構驗證

```
$ jq '{verdict, elapsed_sec, reconnect_failures, keepalive_warnings_count: (.keepalive_warnings | length), subscribe_success_count, subscribe_failure_count, raw_message_count, uptime_ratio, connection_errors_count: (.connection_errors | length)}' c1_proof_progress.json
{
  "verdict": "SMOKE_PASS_NOT_C1_PROOF",
  "elapsed_sec": 59.19,
  "reconnect_failures": 0,
  "keepalive_warnings_count": 0,
  "subscribe_success_count": 6,
  "subscribe_failure_count": 0,
  "raw_message_count": 2015,
  "uptime_ratio": 0.9876,
  "connection_errors_count": 0
}
```

| Check | Result | Evidence |
|---|---|---|
| 60s 跑完 + exit 0 | ✅ | wrapper retcode 0, `elapsed_sec=59.19` |
| verdict=SMOKE_PASS_NOT_C1_PROOF | ✅ | 60s 設計值 (24h proof 才能 PASS_C1_PROOF_CANDIDATE) |
| 0 stack trace / 0 fatal | ✅ | exit 0, `connection_errors=[]` |
| candidate topic 不 reject | ✅ | `subscribe_success_count=6` / `subscribe_failure_count=0` |
| 4 control topics 收 data | ✅ | kline=37 / orderbook=1495 / publicTrade=142 / tickers=335 |

### 4 control topics verify

```
$ jq '.topic_message_counts' c1_proof_progress.json
{
  "allLiquidation.BTCUSDT": 0,           # 60s 等不到 event 預期
  "kline.1.BTCUSDT": 37,                 # control alive
  "orderbook.50.BTCUSDT": 1495,          # control alive
  "publicTrade.BTCUSDT": 142,            # control alive
  "tickers.BTCUSDT": 335                 # control alive
}
```

## §5 — Atomic write 無 .tmp 殘留

```
$ ls -la /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json*
-rw-rw-r-- 1 ncyu ncyu 1643  5月 16 11:02 /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json

$ ls /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json.tmp
ls: 无法访问 '...c1_proof_progress.json.tmp': 没有那个文件或目录
```

✅ Fix 2 verified：
- `c1_proof_progress.json` final file present (1643 bytes, valid JSON parse OK)
- `c1_proof_progress.json.tmp` **NOT present** (POSIX atomic rename cleanup successful)
- 證明 `_atomic_write_text()` helper 兩階段 (write tmp + rename) 工作正常，無遺留 .tmp 殘留 race

## §6 — `keepalive_warnings` field 出現驗證

Fix 3 將 `connection_errors`（致命）vs `keepalive_warnings`（非致命）拆分：

```
$ jq 'keys | map(select(. | test("keepalive|connection"))) | .[]' c1_proof_progress.json
"connection_errors"
"keepalive_warnings"
```

兩 field 並存於 dataclass + JSON output ✅。

```
$ jq '.keepalive_warnings | length' = 0
$ jq '.connection_errors | length' = 0
```

60s smoke 無 keepalive event 觸發（network healthy），但 **field 確實存在於 dataclass schema** — Fix 3 schema patch verified。

`assess()` whitelist prefix match 邏輯透過 unit test `TestKeepaliveWarningsSeparation` 4 個 covered (含 regression guard `test_fatal_recv_failed_still_triggers_fail`：whitelist 不漏接致命)。

## §7 — Linux runtime 安全性

| 項 | 狀態 |
|---|---|
| Engine PID 不變 | ✅ engine_alive=true, demo age=25.8s, live age=15.2s |
| Production WS 0 影響 | ✅ v2 probe 連 Bybit public WS（非 demo/live private） |
| PG 0 寫入 | ✅ probe 只寫 `/tmp/openclaw/audit/liquidation_topic_probe/` |
| GovernanceHub 0 觸發 | ✅ probe 不走 Decision Lease |
| Branch 不 merge | ✅ `worktree-agent-a58d99ef4ea1a440b` 保留 origin，等 PM merge |
| Scratch cleanup | ✅ `/tmp/e4-v2-recheck-1778922043` rm -rf 完成 |

## §8 — 4 Fix runtime verify summary

| Fix | Static unit test | Runtime smoke verify |
|---|---|---|
| Fix 1 (UTC 5min buffer) | 3 PASS (00:00:45 / 00:04:59 / 00:05:00 boundary) | N/A（smoke 不觸及 midnight cutoff path） |
| Fix 2 (Atomic write) | 3 PASS (final file / overwrite / no .tmp residue) | ✅ `.tmp` NOT present at smoke end |
| Fix 3 (Keepalive split) | 4 PASS (whitelist match / regression guard / schema sanity) | ✅ `keepalive_warnings` field 存在於 60s smoke checkpoint |
| Fix 4 (Reconnect gate) | 3 PASS (=2 PASS / =3 FAIL / =5 FAIL boundary) | ✅ `reconnect_failures=0` < 3 → `c1_proof_eligible=false` (60s 不夠 24h, 不是 reconnect gate trigger) |
| Fix 5 (Wrapper) | N/A | ✅ `--help` + `--smoke-60s` 兩 mode 工作；exit 0 |
| Fix 6 (max-restart help text) | N/A | N/A (help text 文檔變更，邏輯未動) |

## §9 — 結論

**E4 REGRESSION DONE: PASS**

- Linux pytest **49/49** PASS (Mac 49/49 baseline 完全對齊)，non-flaky 兩遍 (0.05s + 0.04s)
- Wrapper `--help` + `--smoke-60s` 兩 mode 全 functional
- 60s real WS smoke：verdict=`SMOKE_PASS_NOT_C1_PROOF` 設計預期，exit 0
- 0 stack trace, 0 fatal, 0 connection errors
- candidate topic 不 reject (subscribe_success=6 / subscribe_failure=0)
- 4 control topics 全收 data
- atomic write 無 `.tmp` 殘留 → Fix 2 POSIX rename cleanup verified
- `keepalive_warnings` field 出現於 JSON → Fix 3 schema patch verified
- Linux runtime engine PID 不變

**對於 W-AUDIT-8a C1 v2 harness consolidated fix `dbd0277c`：強制工作鏈最後一棒（E4 quick regression）綠燈，PM merge READY。**

24h proof 仍需 BB+MIT signed full-duration run，非 E4 scope。

## §10 — 下游動作

1. ✅ Linux scratch `/tmp/e4-v2-recheck-1778922043` cleanup
2. ✅ E4 report 寫入 main repo
3. ✅ Memory 1 行 append
4. ✅ branch `worktree-agent-a58d99ef4ea1a440b` HEAD `dbd0277c` 保留 origin
5. ✅ Linux runtime engine PID 不變確認
6. → 主 session 一頁 summary（PM 接手 merge）

---

E4 verdict: **REGRESSION-PASS, 0 push-back to E1**。
