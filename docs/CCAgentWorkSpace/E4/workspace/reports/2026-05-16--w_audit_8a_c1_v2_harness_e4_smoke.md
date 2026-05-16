# E4 Regression Report — W-AUDIT-8a C1 v2 Resilient Harness Linux Smoke

- **Date**: 2026-05-16 (UTC ~08:33)
- **Branch**: `worktree-agent-a58d99ef4ea1a440b`
- **E1 commit**: `5983f955` — W-AUDIT-8a C1 v2 resilient harness IMPL
- **Scope**: 942 LOC v2 probe Python (NEW) + 656 LOC test (NEW) + v1 unchanged
- **Linux host**: `trade-core`
- **Scratch dir**: `/tmp/e4-v2-test-1778920370` (cleaned at finish)
- **Verdict**: **PASS**

---

## §1 — Linux branch fetch + scratch dir verify

Linux trade-core local repo 初次 fetch 後拿到 `remotes/origin/worktree-agent-a58d99ef4ea1a440b`。
Clone 用 local repo as origin failed（local 沒 worktree-agent 本地 branch ref）；改用
`git clone ~/BybitOpenClaw/srv` + `git remote set-url origin git@github.com:yunancun/BybitOpenClaw.git`
+ `git fetch origin worktree-agent-a58d99ef4ea1a440b` + `git checkout -b worktree-agent-a58d99ef4ea1a440b FETCH_HEAD`。

驗：
- HEAD `5983f955` ✅
- `helper_scripts/bybit/liquidation_topic_probe_v2.py` size 39433 bytes ✅
- `helper_scripts/bybit/test_liquidation_topic_probe_v2.py` size 26914 bytes ✅
- 對 Linux runtime 0 影響（scratch dir 在 `/tmp`, 0 修改 `~/BybitOpenClaw/srv` working tree, 0 影響 engine PID）

## §2 — pytest result (non-flaky 2x)

| Run | Result | Duration |
|---|---|---|
| Run 1 (`-v`) | **36 passed** in 0.03s | 0.03s |
| Run 2 (`-q`) | **36 passed** in 0.02s | 0.02s |

**Non-flaky**: GREEN-GREEN 兩 run 同綠 ✅

9 test suites 全 PASS：
- TestBuildTopics (3 tests)
- TestParseArgs (3 tests)
- TestBackoffSequence (4 tests: 1→2→4→8→16→32→60 cap)
- TestClassifyPayload (6 tests: poison patterns / pong / subscribe success/failure)
- TestInterimVerdict (5 tests: healthy / low uptime / poison / reconnect unstable)
- TestAssess (9 tests: 5 verdict paths covered)
- TestCheckpointWrite (2 tests: atomic + same-path overwrite)
- TestReconnectPath (2 tests: exp backoff + first-attempt success)
- TestRestartCap (2 tests: 3 budget)

**Linux 36/36 = Mac 36/36 baseline** ✅

## §3 — py_compile + import test

```
$ python3 -m py_compile helper_scripts/bybit/liquidation_topic_probe_v2.py
py_compile PASS

$ PYTHONPATH=/tmp/$SCRATCH python3 -c "import helper_scripts.bybit.liquidation_topic_probe_v2 as mod; print(mod.__file__)"
import OK module= /tmp/e4-v2-test-1778920370/helper_scripts/bybit/liquidation_topic_probe_v2.py
```

✅ syntax clean, importable, no missing dependency。

## §4 — 60s smoke output + checkpoint JSON

### CLI 輸出

```
SESSION_ID=e4_v2_smoke_20260516T083317Z
verdict=SMOKE_PASS_NOT_C1_PROOF
session_id=e4_v2_smoke_20260516T083317Z
latest_report=/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.md
dated_report=/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_20260516T083416Z.md
checkpoint=/tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json
```

退出 exit code = 0；無 stack trace；無 connection error；無 timeout 觸發。

### Checkpoint JSON 結構驗證

| Field | 值 | OK? |
|---|---|---|
| `session_id` | `e4_v2_smoke_20260516T083317Z` | ✅ |
| `verdict` | `SMOKE_PASS_NOT_C1_PROOF` | ✅ 設計預期 (60s < 23h cutoff) |
| `c1_proof_eligible` | `false` | ✅ 不騙真實 24h proof |
| `c1_blocker` | "Duration 59s < required 82800s..." | ✅ |
| `interim_verdict` | `IN_PROGRESS_HEALTHY` | ✅ |
| `elapsed_sec` | `59.19` | ✅ ~60s target |
| `uptime_sec` | `58.44` | ✅ |
| `uptime_ratio` | `0.9874` | ✅ >0.95 健康 |
| `raw_message_count` | `2003` | ✅ WS stream alive |
| `subscribe_success_count` | `6` | ✅ 5 control + 1 candidate |
| `subscribe_failure_count` | `0` | ✅ **topic NOT rejected** |
| `reconnect_attempts` | `0` | ✅ |
| `reconnect_successes` | `0` | ✅ |
| `reconnect_failures` | `0` | ✅ |
| `restart_count` | `0` | ✅ |
| `restart_events` | `[]` | ✅ |
| `reconnect_events` | `[]` | ✅ |
| `poison_events` | `[]` | ✅ no liquidation poison |
| `candidate_messages_seen` | `0` | ✅ 60s 內無 liquidation event（預期） |
| `candidate_samples` | `[]` | ✅ |
| `pings_sent` / `pongs_seen` | `5` / `5` | ✅ keepalive 10s 間隔 |
| `topic_message_counts.kline.1.BTCUSDT` | `48` | ✅ control alive |
| `topic_message_counts.orderbook.50.BTCUSDT` | `1370` | ✅ control alive |
| `topic_message_counts.publicTrade.BTCUSDT` | `252` | ✅ control alive |
| `topic_message_counts.tickers.BTCUSDT` | `327` | ✅ control alive |
| `topic_message_counts.allLiquidation.BTCUSDT` | `0` | ✅ 60s 等不到 event 預期 |
| `last_seen_by_topic_utc` | 4 control 全有 timestamp | ✅ |
| `blocker_if_aborted_now` | "Duration shorter than 24h..." | ✅ |
| `url` | `wss://stream.bybit.com/v5/public/linear` | ✅ |
| `max_restart_budget` | `3` | ✅ |
| `target_sec` | `60` | ✅ |
| `started_at_utc` / `finished_at_utc` | 兩個 UTC timestamp | ✅ |

**結構驗證**：≥ 30 fields 全部 present 且 type-correct (design §3.3 14 mandatory fields 全有 + ext fields)。

### File proliferation 安全驗證

```
liquidation_topic_probe_v2_latest.json       (overwritten same path)
liquidation_topic_probe_v2_latest.md         (overwritten same path)
liquidation_topic_probe_v2_20260516T083416Z.json   (dated snapshot)
liquidation_topic_probe_v2_20260516T083416Z.md     (dated snapshot)
c1_proof_progress.json                       (per-hour checkpoint)
```

✅ Latest 用同 path overwrite + dated snapshot 一份。

## §5 — 5 Regression checks

| # | Check | Result | Evidence |
|---|---|---|---|
| (a) | Linux PASS = Mac PASS | ✅ | Mac local 36/36 PASS in 0.004s (E1 report) ↔ Linux 36/36 PASS in 0.03s + 0.02s |
| (b) | topic 不 reject | ✅ | `subscribe_success_count=6` / `subscribe_failure_count=0` |
| (c) | control topics 收 data | ✅ | kline=48 / orderbook=1370 / publicTrade=252 / tickers=327, 4 control 全 alive |
| (d) | checkpoint atomic write | ✅ | `c1_proof_progress.json` 1686 bytes ≥ 30 fields valid JSON; latest+dated proliferation 安全 |
| (e) | 0 crash / exception | ✅ | `connection_errors=[]`; exit 0; verdict=SMOKE_PASS_NOT_C1_PROOF (60s 預期) |

## §6 — Linux runtime 安全性驗證

- **Engine PID 不變**：smoke test 完全 `/tmp` 隔離；0 修改 engine 進程
- **Production WS 0 影響**：v2 probe 連 Bybit public WS 而非 demo/live private WS
- **PG 0 寫入**：probe 只寫 `/tmp/openclaw/audit/liquidation_topic_probe/`（已存在 audit 目錄）
- **GovernanceHub 0 觸發**：probe 不走 Decision Lease
- **branch 不 merge to main**：cleanup 後保留 origin/worktree-agent-a58d99ef4ea1a440b for A3+E2+BB+MIT review

## §7 — Mock 審查

v2 test suite 用 `unittest.mock`：
- `TestReconnectPath`: mock WS disconnect + 計算 backoff（不 mock 業務 reconnect 邏輯）✅
- `TestRestartCap`: mock RestartEvent 累積（不 mock budget gate 邏輯）✅
- `TestCheckpointWrite`: 用 tmp_path fixture（real file system, 不 mock）✅

驗：mock 只 stub IO 邊界 + WS event 觸發；業務邏輯（backoff exp 計算 / verdict 判定 / checkpoint atomic）真跑。
無 mock 業務邏輯反模式。

## §8 — 結論

**E4 REGRESSION DONE: PASS**

5 regression check 全 GREEN；non-flaky 2x verify；checkpoint JSON 結構完整；無 crash/exception；Linux trade-core runtime 0 影響。

**v2 resilient harness 對於 A3+E2+BB+MIT+PM 審查具備 production-readiness empirical evidence**：
- topic 不 reject + control topics 全 alive
- 60s smoke = `SMOKE_PASS_NOT_C1_PROOF`（設計預期）
- 24h proof 仍需 BB+MIT signed full-duration run，非本 E4 scope

## §9 — 下游動作

1. ✅ Linux scratch dir cleaned
2. ✅ E4 report 寫入此檔
3. ✅ Memory append
4. branch `worktree-agent-a58d99ef4ea1a440b` 保留 origin，不 merge main
5. 下一輪：BB+MIT sign-off + full 24h proof run（非 E4 scope）
