# E4 Regression — P5-SM soak 監測基建 · feat/p5sm-soak-observability @ 0ce0874c（+E4 補測 d7a9eacf）· 2026-06-11

- 對象：worktree `/tmp/wt-p5sm-soak`，base main `bb02b14c`，6 commits（Wave1 `58ad4dba` → E2-fix `0ce0874c`）；E2 兩輪 ACCEPT（`2026-06-10--p5sm_soak_infra_review.md` re-E2 section）。
- 範圍：V137 事件帳本 / 唯讀 IPC canary（120s）/ flusher 擴充 / `[82]` soak-window healthcheck / restart_all+main.py 接線 / S5 smoke。0 Rust 改動（`git diff bb02b14c..0ce0874c -- rust/` = 空，親驗）。
- 測試環境：Mac `srv/venvs/mac_dev`（py3.12.13 / pytest 9.0.3）；Linux trade-core 系統 `/usr/bin/python3`（3.12.3 / pytest 9.0.2）+ `~/.cargo/bin/cargo`。

## Verdict：**PASS**（E4 +1 regression test `d7a9eacf`；0 業務邏輯 finding；0 退 E1 項）

---

## 軸 1 — 兩端全套回歸（base-vs-HEAD 失敗清單 diff 歸零法）

| Lane | base `bb02b14c` | HEAD | 跑兩遍 | FAILED 清單 diff |
|---|---|---|---|---|
| Mac 受影響 5 檔（canary/flusher/healthcheck/bridge/hub） | 149p+2s（4 檔，canary 不存在） | `0ce0874c` **256p+2s** ×2；`d7a9eacf` **257p+2s** ×2 | identical | 0 fail 兩側 |
| Mac control_api 全套（`control_api_v1/tests/ --ignore=tests/replay`，CSRF enforcement env-lane） | **66f / 4544p / 6s / 4xf** | **66f / 4618p / 6s / 4xf** ×2 | run1==run2 FAILED 清單 byte-identical | **base==HEAD 66 條 byte-identical = 空** |
| Mac srv-root `tests/`（457 items；`--import-mode=importlib` 繞 3 路 test_pure_utils 重名） | 8f / 447p / 2s | 8f / 447p / 2s | — | **base==HEAD 8 條 identical**（pre-existing env-lane，非本分支） |
| Linux 5 檔（/tmp overlay，md5 三檔對齊親驗） | — | **257p+2s** ×2 | identical | 0 fail |
| Linux control_api 全套（base=prod checkout `f6367983`，親驗 code-identical bb02b14c） | **66f / 4546p / 4s / 4xf** | **66f / 4620p / 4s / 4xf** ×2 | run1==run2 FAILED md5 identical | **base==HEAD 66 node-ID identical**（1 行差為 stdout 交錯 artifact，已正規化排除） |
| Rust 全套（Linux prod checkout，`--no-fail-fast`，54 targets） | —（分支 0 Rust 改動 = 同 main） | **4665 passed / 0 failed / 6 ignored** | 跑一輪（task 指定） | 0 fail |

- delta 歸因閉合：Mac +74 = Linux +74 = canary 53 items + flusher 21 items（healthcheck +34 在 helper_scripts scope 非 control_api）；0 unexplained。
- Mac 6s vs Linux 4s = 2 個 Mac-skip 測試在 Linux run+pass（平台差，base 側同形，非分支效應）。
- 66f = 已知 CSRF enforcement env-lane（無 `OPENCLAW_CSRF_SHADOW=1` → write-endpoint 403 mode，2026-05-30 F-NEW-1 一致）；Mac 66 == Linux 66 byte-identical（LC_ALL=C 正規化）。
- 觀察（無害）：sibling session 在本回歸中途對 prod checkout pull 進 P2p sentinel merge（f6367983→7712ec80，`helper_scripts/canary/*` 等 6 檔）——與 control_api tests scope / 5 檔 scope / 壓測（watchdog 進程 6月09 起跑，早於 pull）全不相交；我的 Linux base run 在 f6367983（當時親驗 code-identical bb02b14c）完成。

## 軸 2 — 測試數對賬（名字級 + node-ID 級，0 靜默消失）

- 全 diff 僅 3 個 test 檔變動（canary NEW / flusher M / healthcheck M），`--diff-filter=D` 全 repo 刪除檔 = **0**。
- 名字級 `def test_` diff vs `bb02b14c`：**REMOVED = 0**；ADDED = **90**（canary +36 / flusher +21 / healthcheck +33，逐名已列）+ E4 本輪 +1 = 91。
- node-ID 級（5 檔 scope，collect-only sort diff）：base **151** → HEAD **259**，**REMOVED=0 / ADDED=108** = canary 53 + flusher 21 + healthcheck 33 + E4 1（parametrize 使 item 數 > fn 數；151+108=259 精確守恆）。
- bridge 68 / hub 62 兩檔 0 byte 變動（基線守護面未被觸碰）。

## 軸 3 — mock 不掩蓋邏輯（毒注親驗 ×2 + M1b，全部精準咬合）

| Test 檔 | mock 邊界 | 判定 |
|---|---|---|
| test_lease_ipc_soak_healthcheck.py | MagicMock cursor 只腳本化 fetchone/fetchall（純 PG IO 邊界）；`check_82` 全鏈（active 推定/錨點/dedup/10b 四子軸/S3-S4 算術）真跑 | ✅ |
| test_governance_ipc_canary.py | `_FakeDispatcher` 注入於生產同一 seam（`dispatcher or _default_dispatcher()`，其下唯 `one_shot_ipc_call`/socket = IPC wire 層之下）；schema parsers / tick 記帳 / 連段 / backoff / loop 全真跑；`_acquire_canary_leadership` patch = flock IO；`_monotonic` patch = 時間（允許類） | ✅ |
| test_governance_divergence_flush.py | `get_pg_conn` patch（PG IO）+ `is_lease_ipc_enabled` patch（flag 讀=config IO）+ `get_canary_counters` 腳本化（外部模組輸入源）；`detect_and_record_soak_events_once`/`flush_canary_snapshot_once`/`record_epoch_start_events_once` 偵測與 SQL 構造全真跑，斷言真產 SQL/params | ✅ |

毒注實證（暫改生產碼 → 跑 → 還原，每輪 `git diff` 生產檔空 + marker grep=0 + 綠復跑）：
1. **POISON-A**（七支路軸）：`[82]` 步驟 8 `canary_fail_streak` FAIL 支路加 `and False` → 恰 **1 紅** `test_fail_streak_event_in_window_fails`，其餘 44 綠。
2. **POISON-B**（10b 子軸 (ii)）：heartbeat 新鮮度閾值 ×100（事實禁用）→ 恰 **1 紅** `test_heartbeat_chain_stopped_midwindow_fails`。
3. **M1b**（E2 LOW-A mutant redo）：dedup key 削 `prev_canary_updated_at_epoch_s` → 修補前 44 全綠存活（復現 E2）；補測後恰 **1 紅** = 新測試（下節）。

## 軸 4 — PM 指定 1s 過殺壓測（Linux trade-core，真實 engine IPC，唯讀）

設計：以**真 `governance_ipc_canary_loop`**（jitter/kill-switch/single-flight/記帳全真）+ timing-wrapper dispatcher（同生產注入 seam，內呼真 `one_shot_ipc_call` 全鏈 connect→HMAC auth→call→disconnect）打 `/tmp/openclaw/engine.sock`。進程級 env 注入（`OPENCLAW_SM_IPC_CANARY_ENABLED=1` / `OPENCLAW_SM_CANARY_INTERVAL_SECS=1` / `OPENCLAW_DATA_DIR=/tmp/e4_p5sm_stress_data` 私有 flock 不碰 prod 鎖 / `OPENCLAW_IPC_SECRET_FILE` 唯讀指 runtime secret），零持久層寫入。smoke 1 拍先驗鏈 → 20s sanity → **240s 正式窗**；health monitor 每 10s 查 snapshot 新鮮度/watchdog/engine PID，異常即中止（未觸發）。**0 PG 寫**（flusher 未啟動，canary 本身 0 PG by design）；窗口結束 cancel、進程退出、私有 dir 已刪。

**結果：COMPLETED，240/240 拍 ok（= 480 次 IPC one-shot），0 fail / 0 連段 / 0 backoff；引擎零退化。**

probe round-trip（ms，one-shot 全鏈含連線+HMAC 握手）：

| arm | n | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| governance.is_authorized | 240 | 0.808 | 1.048 | 1.146 | 1.268 |
| governance.get_status | 240 | 0.311 | 0.543 | 0.666 | 0.829 |

引擎健康前/中/後對照（pipeline_snapshot + watchdog + /proc CPU；snapshot 每 ~30s 一代）：

| 相位 | span | tick rate | engine CPU | H0 demo p50/p99/p999 (µs) | H0 max (µs) | snap age max | wd fail |
|---|---|---|---|---|---|---|---|
| PRE（0 canary，×3 樣本） | 30s | 818/s | 15.9% | 1 / 1 / 2 | 516 | 18s | 0 |
| DURING（1s canary，×12 樣本） | 220s | **818/s** | 16.7% | **1 / 1 / 2** | **516** | 28s | 0 |
| POST（0 canary，×2 樣本） | 15s | 1656/s* | 16.7% | 1 / 1 / 2 | 516 | 18s | 0 |

- H0 延遲分位 **前/中/後 byte-identical**（p99=1µs，距 PM 1ms SLA 1000× 餘量）；tick rate PRE==DURING；max_latency_us 516（開機以來高水位）窗內**無新高**。
- CPU +0.8pp 在 POST（無 canary）同值 → ambient 非 canary 歸因；同理 h0 per-check 均值 11→44ns 變動 POST 同值 = 市場活躍度噪音（且為 ns 級，低於 SLA 4-5 個量級）。*POST tick rate 為 15s 短 span 跨 2 代 snapshot 的 burst artifact，非退化方向。
- 引擎 PID 1823884 全程未換（uptime 13h+ 跨壓測窗），watchdog consecutive_failures 全程 0。
- **結論：canary 以 120× 設計頻率（1s vs 120s）持續 4 分鐘對真實引擎 fire 路徑零可測影響；PM「過殺餘量證明」達成。**

## 軸 5 — E2 LOW-A 補釘（E4 職權內新測試）

- 新測試：`TestCheck82DupRolloverDedup::test_distinct_updated_at_same_counts_both_counted_probe_f`（probe-F 形）：兩個真實不同 epoch 攜相同 prev 計數（290/290）但不同 `updated_at` → 斷言各計一次 PASS + `probes=590`。
- M1b mutant（key 只剩 prev 計數）下：過度去重 590→300 → S3 probes 假 FAIL（false-NOGO）→ **本測試恰 1 紅**（親驗；其餘 44 綠 = 復現 E2 的缺口形狀）；還原後 45p+1s 綠，生產檔 byte-clean。
- commit **`d7a9eacf`**（`git commit --only` 僅測試檔，+39 行，未 push）。

## 跑兩遍記錄

- Mac 5 檔：256+2 ×2（@0ce0874c）；257+2 ×2（@d7a9eacf）。Mac control_api：66f/4618p ×2，FAILED 清單 byte-identical。Linux 5 檔：257+2 ×2。Linux control_api：66f/4620p ×2，FAILED md5 identical。flaky = **0**（無任何兩遍不一致測試）。Rust 一輪（task 指定；0 Rust 改動）。

## 衛生

- 毒注/mutant 全還原（每輪 porcelain 驗證）；Linux /tmp e4_* 全清（殘留 0）；prod 樹 porcelain=0；base throwaway worktree 已 remove；分支 worktree 終態 `d7a9eacf` porcelain=0。
- 浮點一致性 = N/A（純 Python 控制面 + SQL 判定，無 indicator/共用浮點 lane）——明確聲明。
- owed（非阻塞，過往輪已標）：V137 正式 apply 前 per-SOP Linux PG 雙跑（E2 §3.5 同標；PM 已親驗 prod=136 + dry-run 重做 PASS）；soak 真啟動（flag-ON）後的 runtime 觀察期屬 deploy gate。

## 退回 E1 修復清單

無。

E4 REGRESSION DONE: **PASS** · 新 commit：`d7a9eacf`（僅測試）· 報告：本檔
