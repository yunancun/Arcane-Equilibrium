# E2 Adversarial Review — W-AUDIT-8a C1 v2 Resilient Harness

**Date**: 2026-05-16
**Reviewer**: E2 (Senior Backend Code Reviewer + Adversarial Auditor)
**Target branch**: `worktree-agent-a58d99ef4ea1a440b`
**Target commit**: `5983f955`
**Worktree path**: `/Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-a58d99ef4ea1a440b`
**E1 self-report**: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_impl_self_report.md`
**Design SoT**: `docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md`

---

## §1 改動範圍（diff stats）

| 檔 | LOC | 動作 | 驗證 |
|---|---|---|---|
| `helper_scripts/bybit/liquidation_topic_probe_v2.py` | 942 | NEW | 942 行 > 800 警告線 (§九) |
| `helper_scripts/bybit/test_liquidation_topic_probe_v2.py` | 656 | NEW | 656 行 < 800，PASS |
| `helper_scripts/bybit/liquidation_topic_probe.py` | 351 | UNCHANGED | `diff` 與 main branch 一字不差 ✅ |

無 production source / config / TOML / migration / auth 改動（self-report §1 truthful）。

---

## §2 八條 §九 既有 checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ | 對齊 design plan §3 (reconnect / checkpoint / TCP keepalive / restart cap / UTC cutoff)；無 scope creep |
| 沒有 except:pass 或靜默吞異常 | ✅ | `_close_connection_quietly` 是合理的 cleanup pattern；無業務路徑吞異常 |
| 日誌使用 %s 格式（非 f-string） | ⚠️ N/A | 本檔不用 logging 模組；改用 `print()` + dataclass dump 進 JSON。可接受（CLI 工具非長期 runtime daemon） |
| 新 API 端點有 `_require_operator_role()` | N/A | 非 FastAPI route，是 CLI |
| `except HTTPException: raise` 在 `except Exception` 之前 | N/A | 非 HTTP context |
| `detail=str(e)` 已改為 `"Internal server error"` | N/A | 非 HTTP context |
| asyncio 路由中沒有 blocking threading.Lock | ✅ | 純 sync code，無 async/threading |
| 沒有私有屬性穿透（`._xxx`） | ✅ | 唯一 `._xxx` 是 socket 內部 `getattr(ws_sock, "sock", None)` — 這是 `websocket-client` 官方 attribute，不是 private intrusion |

---

## §3 OpenClaw 9 條特殊 checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 1. 跨平台 grep（禁 `/home/ncyu` / `/Users/[^/]+`） | ✅ | grep -E '(/home/ncyu\|/Users/[^/]+)' 0 命中 |
| 2. 雙語注釋（新規 2026-05-05：純中文 OK） | ✅ | MODULE_NOTE 中文齊備；docstring 純英文（PEP 257 慣例 + v1 一致風格）；inline 注釋皆中文；無純英文 ≥3 行 comment block |
| 3. Rust unsafe / unwrap / panic | N/A | 純 Python |
| 4. 跨語言 IPC schema | N/A | 隔離 WS probe，無 IPC |
| 5. Migration Guard A/B/C | N/A | 無 SQL migration |
| 6. healthcheck 配對 | ⚠️ DEFER | "被動等待 24h" 確有 checkpoint JSON 作 self-state；外部 watchdog 在 design plan §3.4 點到（cron 補）但本 IMPL 不負責 — 接受 |
| 7. Singleton 登記 §九 表 | N/A | CLI 工具無 module-level singleton |
| 8. 文件大小（800/2000） | ⚠️ **WARN** | probe_v2 942 > 800 警告線（必標記，per CLAUDE.md §九） |
| 9. Bybit API 改動先查字典 | ✅ | `allLiquidation.{symbol}` + 4 control topics + ping/op:subscribe — 與 Bybit V5 字典 `2026-04-04--bybit_api_reference.md` 對齊；OFFICIAL_DOC_URL 注釋 reference |

---

## §4 對抗反問結果（adversarial probes）

### Q1：「你說 reconnect 邏輯正確」— 兩個 connection_errors source 是否會被 assess() 誤判？

`grep "stats.connection_errors.append"` 顯示 8 個 append site：

1. `initial_connect_failed` — fatal
2. `keepalive_warning` — **非致命警告（self-report §9 點 1 已自承）**
3. `ping_send_failed` — recovery-triggering
4. `recv_failed` — recovery-triggering
5. `non_json_message` — data quality（不影響連線）
6. `keepalive_warning_on_reconnect` — **非致命警告**
7. `websocket-client unavailable` — fatal
8. `restart_budget_exhausted` — fatal

`assess()` L760 條件：`if stats.connection_errors and elapsed_sec < proof_min_duration_sec and not c1_proof_eligible` → `FAIL_RECONNECT_EXHAUSTED`

**A**：**HIGH BUG**。`connection_errors` 是 grab-bag，將「警告」+「致命錯誤」混塞同 list；assess() 將任何非空 list 當作 fatal signal 判 FAIL_RECONNECT_EXHAUSTED。**實證**：

```
場景 1（misclassify smoke）：
  elapsed_sec=60, uptime=60, ratio=1.0, control alive=1
  + connection_errors=['keepalive_warning: TCP_KEEPCNT_failed: ...']
  + 0 reconnect_attempts
  期望：SMOKE_PASS_NOT_C1_PROOF
  實際：FAIL_RECONNECT_EXHAUSTED (Mac dev 或 Linux 受限 setsockopt 環境)

場景 2（misclassify 22.99h proof window）：
  elapsed_sec=82700 (22.99h, 1.5min 不夠), uptime_ratio=0.9915
  + connection_errors=['keepalive_warning'] only
  + 0 reconnect_attempts / 0 failures
  期望：SMOKE_PASS_NOT_C1_PROOF
  實際：FAIL_RECONNECT_EXHAUSTED
```

24h 跑後若 elapsed=85000 + c1_proof_eligible=True 不會誤判（c1_proof_eligible 條件 short-circuit），但**子 24h smoke 或邊界 case 系統性誤判**。

### Q2：「checkpoint 寫入是 atomic 嗎？」

**A**：**MEDIUM**。`_write_checkpoint` 用 `Path.write_text()` 直接覆寫，**非 atomic**。Operator `kill -9` / 異常 process death / disk-full 中段，第三方讀者會看到 partial / corrupt JSON。修法：寫 tmp file + `os.replace`（POSIX atomic rename）。對 24h 級 proof per-hour checkpoint，作 operator real-time monitoring 用，partial-write 機率非零但可接受 trade-off — **DEFER 修；標 P2**。

### Q3：「`_try_reconnect` 第 N attempt 後成功時 stats 哪些被更新？」

逐行追：
- L562 `time.sleep(backoff)` — backoff 期間若 KeyboardInterrupt 跳上去
- L563 `stats.reconnect_attempts += 1`
- L564-570 build `event` (success=False)
- L572 try connect → success → `event.success = True`
- L584 `stats.reconnect_events.append(event)`
- L585 `stats.reconnect_successes += 1`
- L586 `stats.last_reconnect_reason = reason`
- L588-589 keepalive warning（**再次 append connection_errors，加劇 Q1 bug**）
- L590 `return new_ws, now, now + ping_interval, 0` （reset attempt counter）

**A**：邏輯正確。但 keepalive_warning_on_reconnect append 進 connection_errors 加劇 Q1。

### Q4：`_try_reconnect` 的 `consecutive_attempt` 入參是否 dead code？

唯一 caller (`_run_session` L490 + L514) 從 `consecutive_reconnect_attempt` 傳值，但該 var 起始 0，reconnect 成功後重置 0，失敗則 `_try_reconnect` 直接回 None 觸 session restart — **`consecutive_attempt` 進 `_try_reconnect` 永遠是 0**。內部 L557 `attempt_global = consecutive_attempt + sub_attempt` 退化為 `sub_attempt`，L558-560 dead guard `if attempt_global > MAX`。

**A**：**LOW** dead code。可移除 `consecutive_attempt` 參數簡化，但 future-proofing future 跨呼叫保持狀態時有用 — DEFER。

### Q5：「`_wait_until_next_utc_midnight()` 是否有 timing race？」

Trace：
- 00:00:00 → sleep 30 → return ✅
- 00:00:15 → sleep 15 → return ✅
- 00:00:31 → wait_sec=86369s → sleep min(86369, 30)=30 → loop → 00:01:01 → wait_sec≈86339 → sleep 30 → loop ...（每 30s polling，~24h ~2880 次 iteration）→ 抵達 next midnight 後落入第一條件分支
- 23:59:30 → wait_sec=30, sleep 30, loop, exit branch within first 30s ✅

**A**：邏輯正確。輕量輪詢（每 30s 一次）非性能問題；UTC 0:30 啟動會 polling 23.5h × 30s = 2820 次，每次 sleep 30s — OS 級接受。但**注意**：probe 啟動後即使 `--start-utc-midnight` flag 沒給，現在 `_run_session` 內部對齊邏輯（CDU clock）也都用 `time.monotonic()` ≠ wall-clock UTC，這是好的（不受 DST / clock skew 影響）。

### Q6：「Mac TCP keepalive 真的容錯嗎？」

L320-325 `setsockopt(SO_KEEPALIVE)` failure 直接 return `f"SO_KEEPALIVE_failed: ..."`，但其他 setsockopt 仍 try。

實測（Mac venv 缺 `websocket` module → verdict=`FATAL_DEPENDENCY_MISSING`，未實際走到 setsockopt 邏輯）：
- 路徑 1：Linux production trade-core, `TCP_KEEPIDLE` + `TCP_KEEPINTVL` + `TCP_KEEPCNT` 全 supported（self-report claim）
- 路徑 2：Mac dev 環境若實裝 `websocket-client` 後跑：`hasattr(socket, "TCP_KEEPIDLE")` Mac 為 False，fallback `TCP_KEEPALIVE`（Mac socket 模組確有 `TCP_KEEPALIVE` 但語意接近 keepidle，OK）
- 路徑 3：受限 sandbox / docker 容器，`SO_KEEPALIVE` OSError → return 警告 string → caller append connection_errors → **加劇 Q1 bug**

**A**：跨平台容錯 OK，但與 Q1 bug 互動致命。

### Q7：「assess() 是否驗 `reconnect_failures < 3` per design §5.3 invariant (c)？」

`grep "reconnect_failures" liquidation_topic_probe_v2.py` 在 assess() 內**只**作 `_interim_verdict()` 的 DEGRADED hint，不作 final PASS gate。

**A**：**MEDIUM**。BB sign-off invariant (c) 含 `reconnect_failures < 3`，但 v2 assess() 只看 `elapsed >= 23h + uptime_ratio >= 0.95 + 0 poison + restart_count <= max + ≥3 control alive`。Theoretical edge case：probe 4 次 reconnect 都 fail（連續 4 attempt fail，不到 6 attempt 觸 restart），uptime_ratio 仍可 = 0.97（每次失敗短，30s 後重連成功）→ 通過 PASS gate，但**違反 BB invariant (c)**。

**修法建議**：assess() 在 `c1_proof_eligible` 路徑加 `and stats.reconnect_failures < 3` 條件，或新增獨立 verdict `FAIL_RECONNECT_FAILURES_HIGH`。

### Q8：「24h proof 中 disk full 怎麼辦？」

`_write_checkpoint` / `write_reports` 用 `Path.write_text()`，無 try/except OSError。disk full 中段 → 整個 probe crash → 失最終 report。

**A**：**LOW**。24h 內 disk full 機率低；但**對 governance 是 bad UX**：crash 後操作員看不到任何最終 verdict，必須翻 nohup.log 拼湊。可加 outer try/except 寫 `FATAL_DISK_OR_IO_ERROR` verdict。

---

## §5 Findings 表

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **HIGH** | `liquidation_topic_probe_v2.py:437-439, 588, 760-774` | `connection_errors` grab-bag 將 `keepalive_warning` 等非致命警告 與 `recv_failed` 等致命錯誤混塞同 list；assess() 把非空 list 當 FAIL 信號 → smoke run 或 sub-23h 邊界 case 在受限 sockopt 環境（Mac dev / sandbox）系統性誤判 `FAIL_RECONNECT_EXHAUSTED` | **退回 E1 修**。分兩類：(a) 拆 `stats.connection_warnings` (新 field) 與 `stats.connection_errors`；keepalive_warning 進 warnings，true connect / recv / ping fail 才進 errors。 (b) assess() L761 條件改為 `if any("failed" in e or "unavailable" in e for e in stats.connection_errors) and ...`（更精準 prefix match）。 補測試 case：`test_keepalive_warning_does_not_trigger_fail_reconnect`。 |
| **MEDIUM** | `liquidation_topic_probe_v2.py:741-805` | assess() 缺 `reconnect_failures < 3` explicit gate；違反 design plan §5.3 BB sign-off invariant (c)；4 短暫 reconnect failures + uptime_ratio≥0.95 case 會誤過 PASS_C1_PROOF_CANDIDATE | **退回 E1 修**。assess() 在 PASS 路徑加 `and stats.reconnect_failures < 3`，否則設 verdict = 新增 `FAIL_RECONNECT_FAILURES_HIGH`。補對應 unit test。 |
| **MEDIUM** | `liquidation_topic_probe_v2.py:390-399, 880-893` | `Path.write_text()` 非 atomic；operator kill -9 / process crash / disk-full 中段致 partial JSON；24h proof per-hour checkpoint 操作員 monitoring 時 `jq .` parse error 機率非零 | **退回 E1 修 OR DEFER P2**。修法：寫 `<path>.tmp` 後 `os.replace(<path>.tmp, <path>)`（POSIX atomic）。If DEFER：標 `# NOTE: non-atomic — accept partial-write risk`. |
| **LOW** | `liquidation_topic_probe_v2.py:942` | file size 942 > 800 警告線（§九 governance change 2026-05-05 警告線維持 800）| **標記不阻**。E1 self-report §1 已點到，PM Sign-off 必明文 accept exception；未來重構可拆 `probe_core.py` + `reconnect.py` + `checkpoint.py`，但目前單檔內聚性高接受。 |
| **LOW** | `liquidation_topic_probe_v2.py:543-592` | `_try_reconnect(consecutive_attempt=...)` 永遠傳 0，dead parameter；內部 L558-560 dead guard | **DEFER**。可移除參數簡化；或 future state-carrying 留接口。E1 自選。 |
| **LOW** | `liquidation_topic_probe_v2.py:390-399, 879-893` | disk-full / IO OSError 無 try/except，crash 後失最終 verdict | **DEFER P2**。加 outer try/except 包 run_probe，遇 OSError 設 verdict=`FATAL_IO_ERROR` 寫 stderr。 |
| **NIT** | E1 self-report §4 第 5 行 | claim "websocket-client 在 requirements.txt line 13" — 實際在 `program_code/exchange_connectors/bybit_connector/control_api_v1/requirements.txt:34`（根目錄無 requirements.txt） | E1 self-report 文字 minor error，不影響功能 |

---

## §6 直接修（無 — E2 不寫業務代碼）

**E2 frontmatter 允許範圍**：typo / lint / dead import / 小範圍格式。

掃描結果：
- 注釋 typo：未發現
- import dead：未發現（`from datetime import timedelta` 在 L722 inline import — minor style issue，但有正當用意（避免頂部 import 後不用），不修）
- 格式：PEP 8 大致對齊，無明顯違規

**E2 直接修 = 0 處。**

---

## §7 文件大小 + cross-platform 驗證明細

```
LOC counts:
  probe_v2.py:    942 (> 800 警告)
  test_probe_v2:  656 (OK)

cross-platform hardcoded path grep:
  /home/ncyu       → 0 命中 (probe_v2)
  /Users/[^/]+     → 0 命中 (probe_v2)

production module imports:
  from program_code.*   → 0 命中
  from settings.*       → 0 命中
  from trading_services.*  → 0 命中
  from app.*            → 0 命中
  from rust.*           → 0 命中

OPENCLAW_DATA_DIR usage:
  _default_output_dir() uses os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw") ✅

TCP keepalive cross-platform guard:
  hasattr(socket, "TCP_KEEPIDLE") fallback to "TCP_KEEPALIVE" ✅
  Each setsockopt 包 try/OSError → 警告 string (但仍寫 connection_errors，加劇 HIGH-1)
```

---

## §8 Test Coverage 評估

E1 跑 36/36 PASS 兩遍 non-flaky 在 0.005s（驗證 fast/deterministic）。Coverage 8 verdict path 全測。

**缺少的 corner case**（E2 補測試建議）：
1. `test_keepalive_warning_does_not_trigger_fail_reconnect`（覆 HIGH-1）
2. `test_reconnect_failures_high_blocks_pass`（覆 MEDIUM-1）
3. `test_non_json_message_does_not_trigger_fail`（覆 HIGH-1 子情境）
4. Network timeout during subscribe（`ws.send` raise 但 task 列為 spec edge — 目前沒測）
5. Disk full during checkpoint write（OSError handling — 目前沒測）
6. Both control + candidate disconnect simultaneously（多 disconnect 並發）
7. Session_id collision（罕見 — accept default：每次 datetime+rand 唯一）

**現有測試 strength**：8 verdict path 完整 + reconnect/restart sequence 完整 + checkpoint schema 對齊 design §3.3。

---

## §9 業務邏輯正確性 fail-mode 反向 probe

| 設計意圖 | Code 路徑 | 結論 |
|---|---|---|
| `consecutive_attempt` 重置 vs 累加 | `_try_reconnect` 成功 return ..., 0 → caller `_run_session` L497 update 為 0 | ✅ 正確（成功時重置） |
| RestartEvent 與 ReconnectEvent 區別 | RestartEvent = 一個 _run_session 完整 fail（連 6 attempts 用盡）；ReconnectEvent = 一次 attempt | ✅ 區分清晰 |
| `uptime_sec` 是否含 reconnect waiting | `uptime_sec += now - conn_on_mono` 累計只在 disconnect / completion / checkpoint 觸點 — 不含 backoff sleep | ✅ 正確（uptime 純連線在線時間，不含等待） |
| `elapsed_sec` vs `uptime_sec` 區別 | elapsed = wall-clock total; uptime = sum of connected segments. uptime_ratio = uptime/elapsed | ✅ 區分清晰，但 final report Markdown render 可加 1 行 explainer 讓 operator 不混淆 |
| `restart_count > max_restart` 還是 `>=`？ | L688 `if stats.restart_count > args.max_restart` → max=3 允許 4 sessions (0,1,2,3) | ⚠️ 與 design plan §3.4 字面「累計 restart > 3」一致；test_three_restart_within_budget_can_still_pass 驗證；但**注意**：max_restart=3 實際 4 sessions 是反直覺，E1 self-report §9 點 3 已標待 PM 確認 — **建議 PM 顯式 sign-off 確認語意** |
| `stats.uptime_sec` 在 disconnect 與 checkpoint race | L460-475 checkpoint 寫入時 saved_uptime + current_segment 計算後寫，再還原 saved_uptime；disconnect path L451 / L487 / L510 在實際斷線時再加當前段；E1 self-report §9 點 2 已自承 race window 極窄理論存在 | ✅ 可接受 trade-off |

---

## §10 結論

**Verdict**：**RETURN to E1**（**2** issues 待修）

**Critical blockers**（必修才能進 E4）：
1. **HIGH-1**：`connection_errors` grab-bag misclassify — `keepalive_warning` 等非致命警告觸發 `FAIL_RECONNECT_EXHAUSTED`；E2 已實證 Mac dev 60s smoke + Linux 22.99h 邊界都會誤判。修法 = 拆 warnings list + assess() 加精準 prefix match。
2. **MEDIUM-1**：assess() 缺 `reconnect_failures < 3` 顯式 gate；違反 design §5.3 BB sign-off invariant (c)；可能 4 次短暫 reconnect failure + uptime≥0.95 誤過 PASS_C1_PROOF_CANDIDATE。修法 = assess() PASS 路徑加 reconnect_failures gate。

**DEFER acceptable**（可隨後 commit / P2）：
- MEDIUM-2 atomic checkpoint write
- LOW-1 file size 942 > 800 警告
- LOW-2 `consecutive_attempt` dead param
- LOW-3 disk-full OSError graceful handling

**Verified strengths**：
- ✅ v1 untouched，diff 0 byte
- ✅ 0 production module imports / 0 hardcoded path
- ✅ MODULE_NOTE + Chinese-only comment 規範對齊新規（2026-05-05）
- ✅ TCP keepalive cross-platform guard 正確
- ✅ 36/36 test PASS 兩遍 non-flaky
- ✅ Cross-platform OPENCLAW_DATA_DIR usage
- ✅ Dry-run + verdict mapping + exit codes 對
- ✅ websocket-client dep already exists in nested requirements.txt
- ✅ design plan §3 全部 7 個 v2 改進 IMPL 完整對齊

---

## §11 退回 E1 修復清單

1. **HIGH-1**：`helper_scripts/bybit/liquidation_topic_probe_v2.py:437-439, 588, 760-774`
   - 拆 `ProbeV2Stats.connection_warnings: list[str] = field(default_factory=list)` 新 field
   - `_run_session` L439 + L588 將 `keepalive_warning*` 改寫入 `connection_warnings` 不寫 `connection_errors`
   - `assess()` L760 條件 grep filter 改 `if any(e.startswith(("initial_connect_failed:", "recv_failed:", "ping_send_failed:", "websocket-client unavailable:", "restart_budget_exhausted:")) for e in stats.connection_errors)`（白名單致命 prefix）
   - Test 新增 `TestAssess.test_keepalive_warning_does_not_trigger_fail_reconnect` + `TestAssess.test_non_json_message_does_not_trigger_fail`
   - Render Markdown 區分 "Connection Warnings" vs "Connection Errors" 兩 section

2. **MEDIUM-1**：`helper_scripts/bybit/liquidation_topic_probe_v2.py:741-744, 783-794`
   - assess() L741 `c1_proof_eligible = (elapsed >= proof_min AND uptime_ratio >= ratio_min)` 之後加 `AND stats.reconnect_failures < 3`
   - 或：assess() PASS 路徑 L784 之前加 `if stats.reconnect_failures >= 3: stats.verdict = "FAIL_RECONNECT_FAILURES_HIGH"; return`
   - Test 新增 `TestAssess.test_high_reconnect_failures_blocks_pass`：模擬 elapsed=85000 + uptime_ratio=0.97 + reconnect_failures=5 + 4 control alive → expect `FAIL_RECONNECT_FAILURES_HIGH`

3. **可選 DEFER**：MEDIUM-2 atomic checkpoint write — operator/PM 決定是否阻 24h 啟動。**建議**：DEFER（24h per-hour checkpoint 1 次 partial-write 風險可接受），但 E1 加 1 行 `# NOTE: non-atomic write` 注釋透明化。

修完後重 E2，然後進 E4 regression + BB+MIT schema delta pre-review。

---

## §12 PM Sign-off 提醒

PM Sign-off 時必明文 accept：
1. **File size exception**（probe_v2 942 > 800 警告）— 接受 high-cohesion single-file 設計，DEFER 拆檔
2. **`max_restart=3` 實際允許 4 sessions**（self-report §9 點 3）— 確認是 design plan §3.4 「累計 > 3」對齊，operator 預期清晰
3. **Per-hour checkpoint non-atomic write**（如 DEFER）— 接受 partial-write 風險作 trade-off

**修完 HIGH-1 + MEDIUM-1 後 PASS to E4。**
