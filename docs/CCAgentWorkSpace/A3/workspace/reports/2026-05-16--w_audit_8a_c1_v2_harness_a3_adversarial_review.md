---
report: A3 對抗審查 — W-AUDIT-8a C1 v2 Resilient Harness
date: 2026-05-16
auditor: A3（UX + first-time operator + 業務邏輯防禦性視角）
subject: E1 IMPL DONE worktree `agent-a58d99ef4ea1a440b` commit `5983f955`
mode: Read-only adversarial review per `feedback_impl_done_adversarial_review.md`
trigger: Round 2 alpha source push P0b — v2 IMPL chain step A3
written-by: PM main session (A3 frontmatter read-only — A3 提供完整 summary 由 PM 代寫)
verdict: **APPROVE-CONDITIONAL 7.5/10** — 2 CRITICAL（24h proof 前必修）+ 3 WARN + 4 ADV
---

# A3 對抗審查報告 — W-AUDIT-8a C1 v2 Resilient Harness

**Files reviewed**:
- `/Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-a58d99ef4ea1a440b/helper_scripts/bybit/liquidation_topic_probe_v2.py` (942 LOC NEW)
- `/Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-a58d99ef4ea1a440b/helper_scripts/bybit/test_liquidation_topic_probe_v2.py` (656 LOC NEW, 36 tests)
- v1 control: `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/bybit/liquidation_topic_probe.py` (351 LOC unchanged)

---

## §1 6 方向逐項 verdict

| 方向 | Verdict | 評分 |
|---|---|---|
| A. 業務邏輯防禦性 | **CONDITIONAL** | 7/10（2 critical bug） |
| B. UX / 第一次 operator 觀感 | **CONDITIONAL** | 7/10（oneliner 過長 + checkpoint 膨脹風險） |
| C. 不變式不破 | **PASS** | 10/10 |
| D. 隔離性 | **PASS** | 10/10 |
| E. 注釋規範 | **PASS** | 9/10 |
| F. 16-Root + 9 安全不變式 | **PASS** | 10/10 |

---

## §2 CRITICAL 發現（需 E1 fix）

### CRITICAL-1: UTC midnight cutoff 在 00:00:30 之後啟動會延遲 24h

**檔位**: `liquidation_topic_probe_v2.py:710-726` `_wait_until_next_utc_midnight()`

**Root cause**:

```python
if now.hour == 0 and now.minute == 0 and now.second <= 30:
    time.sleep(max(0, 30 - now.second))
    return
# 距下次 midnight 還多久
next_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
if next_midnight <= now:
    next_midnight = next_midnight + timedelta(days=1)
```

**Bug scenario**: Operator 在 `2026-05-17T00:00:45Z` 啟 script with `--start-utc-midnight`:
1. `now.second = 45 > 30` → 跳過 early return
2. `next_midnight = now.replace(hour=0, minute=0, second=0)` = `2026-05-17T00:00:00Z`（同一天）
3. `next_midnight <= now` → 加一天 → `2026-05-18T00:00:00Z`
4. **Wait nearly 24h instead of starting immediately**

**業務影響**: Per design §3.6, UTC midnight cutoff 是為「24h 對齊 Bybit funding cycle / OI panel 對賬 SLA」設計，明明意圖是「在午夜附近啟動」。45s 偏差延遲 24h = 嚴重違反 operator 預期。

**Operator 體驗**: oneliner 含 `--start-utc-midnight` + `$(date -u +%Y%m%dT%H%M%SZ)` 動態 session_id — operator paste 完 → 看到 PID 但 progress.json 24h 不出現 → 大概率以為 script hang → kill -9 → 真實開始 → 第二天 operator 又看到 24h 沒進度 → 重派整套流程。

**Fix**:
```python
# 容差 buffer 改 5min（300s）— 如果 now 在 00:00:00 ~ 00:05:00 內 → 直接開始
seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
if seconds_since_midnight < 300:
    return
```

---

### CRITICAL-2: Checkpoint write 不是 atomic — `jq` 並發讀可能看到 partial JSON

**檔位**: `liquidation_topic_probe_v2.py:390-399` `_write_checkpoint()`

**Root cause**:
```python
checkpoint_path = output_dir / CHECKPOINT_FILE_NAME
payload = json.dumps(asdict(stats), ...) + "\n"
checkpoint_path.write_text(payload, encoding="utf-8")  # 直接覆寫
```

**Bug scenario**: 24h 內 operator 透過 status oneliner `ssh trade-core 'jq . /tmp/openclaw/audit/.../c1_proof_progress.json'` 隨時看狀態。`Path.write_text()` 不是 atomic — 在 disk flush 過程中 `jq` 讀到 truncated file → `jq: error: parse error: Unfinished string ...`。

**業務影響**: 進度 JSON 在 24h 過程中至少寫 24 次（per-hour checkpoint）+ 1 次 final flush。每次寫入有 ~1-10ms race window。Operator 監控頻率高（每 5-15min 跑一次 jq）→ 24h 內中 race 機率不低。

**Operator 體驗**: 看到 `jq: parse error` 兩次後就會懷疑「探針壞了 / 資料污染了 / progress.json 不可信」→ 失去信心提前 abort。

**Fix**（atomic rename pattern，標準 POSIX 慣用法）:
```python
tmp = checkpoint_path.with_suffix(".json.tmp")
tmp.write_text(payload, encoding="utf-8")
tmp.replace(checkpoint_path)  # POSIX atomic rename
```

**E1 self-report §9 risk-2** 提到「checkpoint 與 disconnect race」但 focus 在 `stats.uptime_sec` 內部一致性，**漏掉了 disk-level reader race** — 這是 BB sign-off oneliner `jq` 賴以判 PASS 的依賴。

---

## §3 WARN 發現（advisory，不阻 smoke run，建議 24h 前修）

### WARN-1: 24h 啟動 oneliner ~380 字超過 paste-safety 容差

字數約 380 chars（含 ssh 包裝）。Per `feedback_shell_paste_safety.md` 規則 D：**>120 char 容易軟折行**。此外含 `$(date ...)` × 2 shell 變數展開，在某些 zsh 設定（`HISTSUBST`）下 paste 過程中可能被局部解析。

**Fix**:
1. 提供 wrapper script `helper_scripts/bybit/run_c1_v2_proof.sh`，operator 只跑 `bash helper_scripts/bybit/run_c1_v2_proof.sh`
2. 或將 oneliner 拆 2 行
3. 但 ssh 包裝下 `export` 不會 propagate — 還是建議 wrapper script

---

### WARN-2: `--max-restart 3` 語意對 first-time operator 有歧義

**Root cause**: 邏輯是 `if stats.restart_count > args.max_restart: break`。意即 `max_restart=3` 允許 **4 個 sessions**（initial + 3 restarts → restart_count 累計 0/1/2/3 都 OK，第 4 個 restart 才 fail）。

**對 first-time operator**: 看 `--max-restart 3` 大概率理解為「最多 3 次重連」，但實際是「除 initial session 外，最多 3 次重啟」（即 max 4 sessions）。

**Fix**:
1. 改 help message 為「Maximum number of session restarts after the initial session (initial + N restarts allowed). max-restart=3 means up to 4 total sessions.」
2. 或將 `args.max_restart` 改為 `args.max_total_sessions`，default=4，邏輯改 `if (stats.restart_count + 1) > args.max_total_sessions`

---

### WARN-3: Checkpoint JSON 24h 內會持續膨脹（candidate_samples + reconnect_events + connection_errors）

**證據**: `ProbeV2Stats` 含：
- `candidate_samples: list[dict]` (cap 20，每 sample 含完整 Bybit payload JSON，可達 KB 級)
- `reconnect_events: list[ReconnectEvent]` (無 cap)
- `restart_events: list[RestartEvent]` (無 cap)
- `connection_errors: list[str]` (無 cap)
- `poison_events: list[str]` (無 cap，但 24h 內期望 0)

**業務影響**: 24h × 1 reconnect/hr × ~200 bytes/event = ~5KB；加 candidate_samples cap 20 × ~1KB = ~20KB。總膨脹 ~25-50KB checkpoint。看似不大，但 operator 每 5min `jq .` 累 24h × 288 次 × 50KB = ~14MB IO（無痛但低效）。

**Fix**:
1. Checkpoint JSON 只 dump「summary fields」（elapsed_sec / uptime_sec / uptime_ratio / counts / verdict / last_reconnect_reason），**不含** events / samples / errors list
2. Events / samples 寫獨立 `c1_proof_events.jsonl`（append-only 一行一 event）
3. Final report `liquidation_topic_probe_v2_latest.json` 仍完整 dump（一次性）

或更簡單：cap events list 至 last 50 entries（per render_markdown 已 `[-20:]` slice 顯示，但底層 list 未截斷）。

---

## §4 ADVISORY 觀察（minor / nice-to-have）

### ADV-1: `args.duration_sec` 全局 mutation pattern smelly

**檔位**: `liquidation_topic_probe_v2.py:665-671`

```python
original_duration = args.duration_sec
args.duration_sec = int(remaining_target)
outcome = _run_session(args, stats, websocket, session_start_mono, output_dir)
args.duration_sec = original_duration
```

非 thread-safe 模式（雖本 probe 單 thread），且若 `_run_session` 內未 catch 的異常 escape，`args.duration_sec` 不會還原。建議改傳 `effective_duration_sec` 參數給 `_run_session()`，不 mutate args。

---

### ADV-2: `blocker_if_aborted_now` 在 elapsed > 23h 後仍印 SMOKE_PASS 字串

固定字串，不隨 `elapsed_sec` 動態。Operator 在第 23h 看 progress.json 仍看到此字串會困惑。Fix 加條件分支。

---

### ADV-3: Design §3.4 CONTROL_SILENT trigger 未實現

Design §3.4 列 3 種 restart trigger：RECONNECT_EXHAUSTED ✅ / CONTROL_SILENT ⚠️ 未實現 / WATCHDOG_REVIVE（外層 cron，N/A）

CONTROL_SILENT 邏輯應該是：監控每 control topic `last_seen_by_topic_utc`，若任一 ≥ 300s 未更新但連線仍 alive → restart session。

當前 IMPL 完全不檢查這個 → 若 Bybit 端某個 control topic 默默停推但 ws 仍開著（partial-silent case），probe 不會 trigger restart → 仍累計 uptime_sec 直到 24h 過 → `assess()` 階段才發現 control alive 不夠 → `FAIL_CANARY_SILENT` 但已浪費 23h。

**E1 self-report 沒提這個 gap**。design plan 與 IMPL 之間有靜默漂移。

**建議**: 不阻 24h proof，但需在 E1 self-report 明確列為 "design §3.4 CONTROL_SILENT 暫不實現，accepted trade-off due to low empirical likelihood"，或 P2 追加 IMPL。

---

### ADV-4: TCP keepalive Darwin fallback 沒有真實機測試

E1 self-report §9 自承「本地 unittest 不觸 socket 層；Mac 上跑 dry-run 不觸發此邏輯」。Mac dev 上跑 probe → keepalive_warning 字串會被加到 `connection_errors`（看起來像錯，實是 warning），但 probe 仍能跑。

**Operator 體驗風險**: 第一次跑 Mac smoke 看到 `connection_errors` 非空 → 以為失敗 → kill。

**Fix**: 將 keepalive warning 拆出獨立 field `keepalive_warnings: list[str]`，不混進 `connection_errors`。

---

## §5 強項（值得保留）

1. **v1 100% untouched**
2. **不變式 100% 不破** — 不觸 production builder / writer / authorization / lease / risk_config / Mainnet 邊界
3. **獨立 audit dir** — 與 production runtime path 完全分離
4. **Exit code 清晰** — 0 / 1 / 2 對 PASS / FAIL_* / FATAL
5. **8 verdict 路徑全測** — 覆蓋扎實
6. **注釋全中文 + 解釋 WHY** — RECONNECT_BACKOFF_SEC 序列 / ping interval 10s / 24h tolerance 0.95 都有 in-code 解釋
7. **跨平台 hasattr 守衛** — `_apply_tcp_keepalive()` Darwin vs Linux 容錯
8. **Operator-facing error messages 清楚**
9. **PASS 條件鬆綁合理** — 23h + 0.95 uptime + ≥3/4 control 比 v1 strict 24h 更實務

---

## §6 Sign-off 建議

### 對 smoke 60s 測試（E4 review 期）

**PASS** — 兩 CRITICAL 在 60s smoke 內影響可忽略（midnight cutoff 不啟用、checkpoint atomicity race 視窗 60s 內罕見）。E4 可放行 60s smoke 用於 IMPL 驗證。

### 對 24h proof（operator 啟動前）

**CONDITIONAL** — 強烈建議：
1. **CRITICAL-1 必修**：UTC midnight cutoff 5min buffer，否則 operator 啟 script 後 24h 不出進度
2. **CRITICAL-2 必修**：atomic rename pattern，否則 `jq .` race 損害 BB sign-off 信心
3. **WARN-1 建議改**：oneliner 改 wrapper script `run_c1_v2_proof.sh`，避 paste-safety 違規
4. **WARN-2 + WARN-3 + ADV-1~4**：accept 為 known limitation，記入 E1 self-report 即可

### 給 PM 的決策框架

```
若 operator 急於啟 24h proof：
    → Skip CRITICAL-1 fix（accept manual `date -u` 時機選擇）
    → Skip CRITICAL-2 fix（accept ~1% jq race，加 retry oneliner）
    → 但 explicit document 為 "known limitations" in PM Sign-off

若 PM 走標準 IMPL → A3+E2+E4 → 24h 派發流程（推薦）：
    → 派 E1 fix CRITICAL-1 + CRITICAL-2（< 1h IMPL）
    → 派 E1 寫 wrapper script `run_c1_v2_proof.sh`（30min）
    → 重審後啟動 24h proof
    → 延遲 ~1 工作日 vs 完整修正後 confidence 高
```

A3 推薦：**走標準流程**（修兩 CRITICAL + 包 wrapper script）。延遲 1 天換 24h proof 高信心 = 划算交易。Per design §8.1，整體 ETA 已 ~3 工作日，不差這 1 天。

---

## §7 Follow-up 清單

| Item | Priority | Owner |
|---|---|---|
| CRITICAL-1 UTC midnight 5min buffer fix | P0 (24h proof 前必修) | E1 |
| CRITICAL-2 atomic rename checkpoint write | P0 (24h proof 前必修) | E1 |
| WARN-1 wrapper script `run_c1_v2_proof.sh` | P0 (24h proof 前必修) | E1 |
| WARN-2 `--max-restart` help text 改清楚 | P1 | E1 |
| WARN-3 checkpoint summary-only mode + events.jsonl 拆檔 | P2 (24h proof 後再修) | E1 |
| ADV-1 `args.duration_sec` 不 mutate refactor | P2 (code hygiene) | E1 |
| ADV-2 `blocker_if_aborted_now` 動態文字 | P2 | E1 |
| ADV-3 CONTROL_SILENT trigger IMPL | P2 (design §3.4 完整性) | E1 |
| ADV-4 keepalive_warnings 拆獨立 field | P2 | E1 |

---

## §8 最終 verdict

**APPROVE-CONDITIONAL 7.5/10**

可 commit + 走 E2 / E4 / BB / MIT review；**但 24h proof 啟動前必須 fix 兩 CRITICAL + WARN-1**。

A3 視角結論：v2 設計方向正確（reconnect / TCP keepalive / checkpoint / tolerance gate 全合理），但兩個 operator-facing 細節（midnight buffer + atomic write）若不修，會在實機 24h 跑時造成 operator 信心崩潰 → 重派整套 → 浪費更多時間。值得在 commit 之前 fix。
