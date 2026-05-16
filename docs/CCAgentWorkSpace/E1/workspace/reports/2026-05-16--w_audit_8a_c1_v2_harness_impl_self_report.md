# W-AUDIT-8a C1 v2 Resilient Harness — E1 IMPL Self-Report

Date: 2026-05-16
Owner: E1
Ticket: P1-W-AUDIT-8A-C1-RETRY-PLAN-1（Phase 2 IMPL）
Design SoT: `docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md`
Worktree branch: `worktree-agent-a58d99ef4ea1a440b`
Status: **IMPL DONE → 待 A3 對抗審 + E2 代碼審 + E4 regression + BB+MIT schema delta pre-review + PM sign-off**

---

## §1 Code Diff Summary

| 檔 | LOC | 動作 |
|---|---|---|
| `helper_scripts/bybit/liquidation_topic_probe_v2.py` | 942 | **NEW**：v2 韌性探針本體 |
| `helper_scripts/bybit/test_liquidation_topic_probe_v2.py` | 470 | **NEW**：v2 unit tests（36 cases）|
| `helper_scripts/bybit/liquidation_topic_probe.py` | 351 | **UNCHANGED**（v1，保留歷史 control comparison） |

無其他 production source / config / TOML / migration / auth 改動。

---

## §2 設計決策

### 2.1 v2 為獨立檔（非 `--v2` flag）

- design plan §9 明示「不改 v1，新建 v2」
- 動機：v1 = 「最小可達」基線，後續可作 control-comparison；混在同檔 + flag 切換會（a）模糊兩種設計意圖 (b)風險破 v1 通過案
- 取捨：付 ~100 LOC 重複 const + helper（POISON_PATTERNS / classify_payload / build_topics）；換 v1 untouched 保證
- 維護成本可接受：兩檔 future drift 風險低（v1 是凍結 baseline，v2 才是進化）

### 2.2 Reconnect 退避序列

實作 `_backoff_for_attempt(attempt)`：
- attempt 1-6: 1s / 2s / 4s / 8s / 16s / 32s
- attempt 7+: 60s cap
- attempt ≤ 0: 0s（safety）
- 對應 design §3.2 序列 + test `test_first_six_attempts_exponential` + `test_seventh_attempt_caps_at_60` 覆盤

### 2.3 連續 6 attempt 用盡 = session restart 觸發

`RECONNECT_MAX_ATTEMPTS_PER_SESSION = 6` 常量（不可改）。每次 disconnect path：
- 第 1-5 attempt 失敗 → 增 counter + 退避 + retry
- 第 6 attempt 失敗 → `_try_reconnect` 回 None → session 觸 `RestartEvent`（reason=`RECONNECT_EXHAUSTED`）
- 主 loop 暫停 60s → 開新 session
- `restart_count > args.max_restart` → 整 probe 終結 `FAIL_RESTART_BUDGET_EXHAUSTED`

### 2.4 Reconnect 成功歸零 `consecutive_attempt`

設計：穩定收訊 = 重置 attempt counter，避免「歷史失敗」污染新一段中斷判定。
測試：`test_reconnect_success_first_attempt` 驗 `new_attempt_counter == 0`

### 2.5 TCP keepalive 跨平台容錯

Linux 的 `TCP_KEEPIDLE` 在 Mac (Darwin) 改名 `TCP_KEEPALIVE`。`_apply_tcp_keepalive`：
- 用 `hasattr(socket, "TCP_KEEPIDLE")` 判斷
- 對應 const 不存在時降級用 `TCP_KEEPALIVE`
- 全部 setsockopt 包 try/OSError，失敗回 warning string 而非 raise（probe 仍可運行）
- Mac 上跑 dry-run 不影響本邏輯（不開連線）；Linux 上跑時 4 個 sockopt 全 supported

### 2.6 Ping interval 10s（非 20s）

per design §3.2：v1 20s 偏寬鬆，server-side close 可能要 10s 才被偵測。v2 縮 10s 主動 ping。
測試：`test_default_values` 驗 `args.ping_interval_sec == DEFAULT_PING_INTERVAL_SEC == 10.0`

### 2.7 Checkpoint 機制（per-hour）

`_write_checkpoint(stats, output_dir)` 寫 JSON 到 `OPENCLAW_DATA_DIR/audit/liquidation_topic_probe/c1_proof_progress.json`：
- 覆寫同檔（不生 dated proliferation）— test `test_overwrites_same_path_no_dated_proliferation` 驗
- Schema 含 design §3.3 全部 mandatory field — test `test_writes_progress_json_with_required_fields` 驗
- 主 loop 在 `now_mono >= next_checkpoint_at` 觸發
- 含當前 conn-on 段（temp +current_segment，寫完還原 stats.uptime_sec）— 避免 disconnect path 重複累計

### 2.8 24h tolerance gate（≥23h + uptime≥0.95 + ≥3 control alive）

per design §3.5 vs v1 的 exact 24h：
- `PASS_MIN_OBSERVED_SEC = 23 * 3600 = 82800`
- `PASS_MIN_UPTIME_RATIO = 0.95`
- Control alive ≥ 3/4（而非 4/4）
- assess() 5 條 verdict 路徑全測：
  - PASS_C1_PROOF_CANDIDATE（test_pass_c1_proof_full_window + test_full_window_three_control_ok）
  - FAIL_TOPIC_POISON（test_fail_topic_poison_dominates）
  - FAIL_RESTART_BUDGET_EXHAUSTED（test_fail_restart_budget_exhausted）
  - FAIL_RECONNECT_EXHAUSTED（test_fail_reconnect_exhausted_when_enable_reconnect）
  - FAIL_CONNECTION（test_fail_connection_when_no_reconnect_flag — v1 兼容路徑）
  - FAIL_CANARY_SILENT（test_full_window_but_canary_silent）
  - SMOKE_PASS_NOT_C1_PROOF（test_smoke_pass_short_window）
  - FAIL_SMOKE_CANARY_SILENT（test_smoke_canary_silent）

### 2.9 UTC midnight cutoff（`--start-utc-midnight` flag）

per design §3.6：optional。實作 `_wait_until_next_utc_midnight()`：
- 計算下一個 UTC 00:00:00 + 30s buffer
- 用 30s 切片 sleep 避免 OS 長 sleep 不可中斷
- 預設 OFF（operator 啟動 oneliner 顯式給 `--start-utc-midnight` 才啟用）

### 2.10 `enable_reconnect=False` 時 v1 兼容

未顯式給 `--enable-reconnect` 旗標 → 任何 disconnect 直接走 `FAIL_CONNECTION` verdict（v1 行為）。
動機：smoke run 不需 reconnect 邏輯干擾；test `test_fail_connection_when_no_reconnect_flag` 驗。

---

## §3 Test List + 結果

跑兩遍 non-flaky：
```
Ran 36 tests in 0.004s  (first run)
Ran 36 tests in 0.005s  (second run)
OK
```

### 36 個 test cases 分布（6 suite）

| Suite | tests | 覆蓋 |
|---|---|---|
| TestBuildTopics | 3 | dedup / 預設 5 topics / custom symbol |
| TestParseArgs | 3 | 預設值 / `--enable-reconnect` / `--session-id` |
| TestBackoffSequence | 4 | 1-6 attempt exponential / 7+ cap / 0/負數 / 常量保護 |
| TestClassifyPayload | 6 | subscribe success/fail / pong / candidate sample cap / poison patterns 全 6 個 |
| TestInterimVerdict | 5 | healthy / poison / uptime degraded / warmup / reconnect unstable |
| TestAssess | 9 | 5 PASS/FAIL verdict 路徑 + 邊緣 case |
| TestCheckpointWrite | 2 | schema fields / 覆寫不增 file |
| TestReconnectPath | 2 | 第一次 attempt success / 6 attempts 用盡 |
| TestRestartCap | 2 | restart_count > max 觸 FAIL / `==` 不算超 |

### 跑命令

```bash
cd /Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-a58d99ef4ea1a440b/helper_scripts/bybit
python3 -m unittest test_liquidation_topic_probe_v2 -v
```

### Dry-run smoke

```bash
python3 helper_scripts/bybit/liquidation_topic_probe_v2.py --dry-run --enable-reconnect --max-restart 3 --session-id c1_v2_test
# => JSON output 全 design plan 旗標映射正確
```

### v1 unaffected

```bash
python3 helper_scripts/bybit/liquidation_topic_probe.py --dry-run
# => v1 JSON 一字不差，行為保留
```

---

## §4 Cross-Platform Check

- ✅ 0 hardcoded `/home/ncyu` 路徑
- ✅ 0 hardcoded `/Users/[a-z]+` 路徑
- ✅ output_dir 走 `OPENCLAW_DATA_DIR` env（與 v1 一致）
- ✅ TCP keepalive `_apply_tcp_keepalive` 用 `hasattr` 守衛 Darwin / Linux 差異（`TCP_KEEPIDLE` vs `TCP_KEEPALIVE`）
- ✅ `websocket-client` 依賴已存在 requirements.txt（line 13）`websocket-client>=1.8.0`
- ✅ Mac 可跑 dry-run + 全 36 unit test PASS（無需 websocket-client 安裝）
- ✅ Linux runtime（trade-core）有 websocket-client 已驗（v1 已跑）

---

## §5 BB + MIT Pre-review 需要的 fields 清單

### 5.1 BB Sign-off 4 條 invariant（design §5）

| Invariant | v2 stats / output 對應 field | 跑法 |
|---|---|---|
| (a) 24h+ wall-clock pin window | `elapsed_sec >= 82800` | `jq '.elapsed_sec' c1_proof_progress.json` |
| (b) 0 subscribe failures + 0 topic rejection | `subscribe_failure_count == 0` + `len(poison_events) == 0` | `jq '.subscribe_failure_count, (.poison_events \| length)' liquidation_topic_probe_v2_latest.json` |
| (c) Reconnect 自動恢復 + 累計 uptime ≥ 23h | `uptime_ratio >= 0.95` + `reconnect_failures < 3` | `jq '.uptime_ratio, .reconnect_failures' c1_proof_progress.json` |
| (d) Message schema 對齊 Bybit V5 official | MIT pre-review approved | `grep "verdict:" docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-1X--c1_v2_schema_delta_pre_review.md` |

v2 stats 全部欄位均已在 final report JSON 暴露。

### 5.2 MIT Schema Delta Pre-review 預審字段（design §4）

MIT 用 v1 已收的 15 candidate messages 對照 Bybit V5 official schema：

| Bybit V5 field | 現 `market.liquidations` column | MIT pre-review 任務 |
|---|---|---|
| `T` (timestamp ms) | `event_time` / `liquidation_time_ms` | Verify 1:1 map |
| `s` (symbol) | `symbol` | Verify str format |
| `S` (side) | `side` | Verify enum 'Buy'/'Sell' |
| `v` (qty) | `qty` | Verify decimal 精度 |
| `p` (price) | `price` | Verify decimal 精度 |
| 無 USD value | 若 schema 有 `value_usd` → 必須 calc | MED risk |
| Snapshot vs delta | 若 schema 有 `event_type` | MED risk |

MIT pre-review 寫至：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-1X--c1_v2_schema_delta_pre_review.md`

需含：
- v1 15 messages full JSON dump（已有，路徑見 design §4.1）
- 對 `market.liquidations` 1:1 mapping table
- delta 清單（若有）
- V09X migration draft（若需）
- MIT verdict: APPROVE / CONDITIONAL / DELTA-REQUIRES-MIGRATION

### 5.3 BB + MIT pre-review 4 條待答

1. **`market.liquidations` 現實際 schema**（PA pre-IMPL 期跑 `ssh trade-core "psql -d trading_bot -c '\d market.liquidations'"` 但本 E1 IMPL 不查 Linux PG — 留 MIT）
2. **v1 15 messages full JSON dump path**（在 `trade-core:/tmp/openclaw/audit/liquidation_topic_probe/` 內 `*20260515T195309Z*` 系列；MIT 自取）
3. **Schema delta 是否需 V09X migration**（MIT 預審結論）
4. **Bybit V5 `allLiquidation.{symbol}` payload type field**（snapshot vs delta；參 OFFICIAL_DOC_URL `https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation`）

---

## §6 Deploy 預覽

### 6.1 啟動 oneliner（operator 在 trade-core 跑）

短 smoke（60s，verify 工具可達）：
```
ssh trade-core 'cd ~/BybitOpenClaw/srv && python3 helper_scripts/bybit/liquidation_topic_probe_v2.py --duration-sec 60 --enable-reconnect --max-restart 3 --checkpoint-interval-sec 60 --session-id c1_v2_smoke_$(date -u +%Y%m%dT%H%M%SZ)'
```

24h 正式 proof（next UTC midnight）：
```
ssh trade-core 'cd ~/BybitOpenClaw/srv && nohup python3 helper_scripts/bybit/liquidation_topic_probe_v2.py --topic allLiquidation.BTCUSDT --duration-sec 86400 --enable-reconnect --max-restart 3 --checkpoint-interval-sec 3600 --start-utc-midnight --session-id c1_v2_$(date -u +%Y%m%dT%H%M%SZ) > /tmp/openclaw/audit/liquidation_topic_probe/nohup_c1_v2_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &'
```

### 6.2 狀態檢查 oneliner

```
ssh trade-core 'jq . /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json'
```

### 6.3 最終報告路徑

- Checkpoint: `/tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json`（per-hour overwrite）
- Final JSON latest: `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.json`
- Final JSON dated: `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_<UTC>.json`
- Final MD latest: `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.md`
- Final MD dated: `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_<UTC>.md`
- nohup stdout/stderr: `/tmp/openclaw/audit/liquidation_topic_probe/nohup_c1_v2_<UTC>.log`

### 6.4 Exit codes

| Exit | 含義 |
|---|---|
| 0 | PASS_C1_PROOF_CANDIDATE / SMOKE_PASS_NOT_C1_PROOF（含 dry-run） |
| 1 | FAIL_*（含 FAIL_RECONNECT_EXHAUSTED / FAIL_RESTART_BUDGET_EXHAUSTED / FAIL_TOPIC_POISON / FAIL_CONNECTION / FAIL_CANARY_SILENT / FAIL_SMOKE_CANARY_SILENT） |
| 2 | FATAL_DEPENDENCY_MISSING（websocket-client 未安裝） |

### 6.5 Early abort 流程

per design §6.5：
- `uptime_ratio < 0.85` 連續 2h → operator `kill <PID>`
- 同時 `touch /tmp/openclaw/audit/liquidation_topic_probe/ABORTED_<UTC>.flag`
- Ping PM 重新評估

---

## §7 嚴格限制守則自審

| 限制 | 自審 |
|---|---|
| 不改 v1 (`liquidation_topic_probe.py`) | ✅ 0 改動，dry-run 行為一字不差 |
| 不 trigger 24h probe | ✅ 純 IMPL + 36 unit tests，未啟動實 WS 連線 |
| 不 commit / push | ✅ worktree 等 PM 統一 commit |
| 不改 `rust/openclaw_engine/src/main.rs` | ✅ 0 改 |
| 不改 production `full_subscription_list()` | ✅ 0 改 |
| 不改 auth / GovernanceHub / Decision Lease | ✅ 0 改 |
| 注釋全中文 | ✅ E2 grep 應 PASS |
| IMPL DONE 後不自評 sign-off | ✅ 本 report 標 「待 A3+E2+E4+BB+MIT+PM」 |
| 不 spawn 第二層 sub-agent | ✅ E1 單 instance 完成 |

---

## §8 16 根原則合規

| 維度 | 評估 |
|---|---|
| 原則 1 單一寫入口 | N/A（read-only WS probe） |
| 原則 4 策略不能繞過風控 | N/A |
| 原則 6 失敗默認收縮 | ✅ Reconnect budget 用盡 / Restart budget 用盡 → 終結 FAIL（不 silent continue） |
| 原則 8 交易可解釋 | ✅ Per-hour checkpoint + ReconnectEvent + RestartEvent 全紀錄 |
| 原則 10 認知誠實 | ✅ 全 8 verdict 分類顯式區分；不偽造 PASS |
| 原則 14 零外部成本 | ✅ 0 paid API，純 Bybit public WS |
| DOC-08 §12 9 不變量 | 0 觸碰 |
| 硬邊界（max_retries / live_execution / execution_authority） | 0 觸碰 |

---

## §9 已知不確定點 / Risk Areas

1. **Mac TCP keepalive 行為差異**：本地 unittest 不觸 socket 層；Linux runtime 上 `TCP_KEEPIDLE/INTVL/CNT` 全 supported；Mac 上若意外被當 runtime 用，`TCP_KEEPALIVE` (Darwin) 取代 `TCP_KEEPIDLE` 是 fallback。E2 review 期可要求 Linux smoke 觀察 `dmesg` 或 `tcpdump` 驗 keepalive 真的發送（NICE-TO-HAVE，非 blocker）
2. **checkpoint 與 disconnect 並發 race**：當 checkpoint 寫入瞬間發生 disconnect，會出現 `stats.uptime_sec` 短暫上下調動。實作上 `_write_checkpoint` 完成後立即還原 `saved_uptime`，disconnect path 才加新段；race 視窗極窄但理論存在。E2 review 期可考慮要求 lock，或接受 1-hour 量級誤差（accept trade-off）
3. **`restart_count == max_restart` 邊界**：設計判斷 `> max_restart` 而非 `>= max_restart`。意即 max=3 時實際允許 4 個 session（0,1,2,3 → 4 個）。E2 / PM 確認此語意 = design §3.4 「累計 restart > 3」對齊
4. **session restart 後 stats accumulate**：設計上 reconnect_attempts / candidate_messages_seen / topic_message_counts 跨 session 累計（不重置）。E2 review 若有不同意見可調

---

## §10 完成序列 checklist

- ✅ §1 啟動序列：profile.md + memory.md（tail）+ 最新 report + design plan + v1 source 全讀
- ✅ §2 IMPL：v2 probe 942 LOC + tests 470 LOC
- ✅ §3 Unit tests：36/36 PASS（跑兩遍 non-flaky）
- ✅ §4 cross-platform check：0 hardcoded path / Darwin keepalive 容錯
- ✅ §5 dry-run smoke：v2 OK + v1 unaffected
- ✅ §6 注釋全中文（per `feedback_chinese_only_comments.md`）
- ✅ §7 worktree clean（無 staged 隔壁 session WIP）
- ⏳ §8 待 A3+E2 對抗審 + E4 regression + BB+MIT pre-review + PM sign-off
- ⏳ §9 Memory 1 行 append（done 後 finalize）

**E1 IMPL DONE — 待主 session 派 A3+E2+E4 三方並行核驗（per `feedback_impl_done_adversarial_review.md`）。**
