# Wave 1.6 P1-FILL-LINEAGE-DROP — E2 對抗審查報告

**Date**: 2026-05-11
**Auditor**: E2 (Senior Backend Reviewer + Adversarial Auditor)
**Scope**: working tree HEAD未 commit + 3 檔 / +422 / -6 LOC
- `rust/openclaw_engine/src/tasks.rs:641-655` (cap 1024→8192)
- `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:1-792` (counter + retry helper + emit_fill_completion 接 retry)
- `rust/openclaw_engine/src/agent_spine/tests.rs:1247-1476` (3 new test)
**Parallel**: E5 hot-path perf re-audit（同時跑，本 E2 只 correctness + thread-safety + governance）

---

## 1. Verdict

**APPROVE WITH MINOR · PASS to E4** · 0 BLOCKER / 0 HIGH / 2 MEDIUM / 3 LOW / 2 P2-governance-ticket

E1 IMPL 設計（B-2 + 局部 B-3 hybrid）正確映射 QA RCA §D.3 Option F4；entry hot path 0 spawn/sleep/lock 嚴守 SLA；fill_completion path retry 設計合理；Atomic Relaxed counter 對 metric 屬性 correct；3 new unit test 真實驗 invariant 非 mock-pass；cargo test 2810 PASS 連跑 3 次 retry test 穩定不 flaky。

2 MEDIUM 屬「governance exception clause 適用範圍誤引用」+「counter 語意需明確化」，**不阻 E4 / deploy**；建議 PM commit 前同步修報告 + 注釋。

---

## 2. A 條：Thread-safety + race condition

| 項 | 結論 |
|---|---|
| Atomic Relaxed ordering | ✅ **CORRECT**：counter 屬統計屬性無 happens-before 需求，Relaxed 是 metric counter 慣用實踐；`fetch_add(1, Relaxed)` 並發單調遞增 race-free |
| spawn task 過量風險 | ✅ **SAFE**：worst case 1秒 1000 fail → 1000 spawn × 3 retry × 50ms = 同時點積壓 ~1000 task × 200-500 bytes = ~200-500KB memory，遠低於 tokio runtime 處理能力；實況 24h 86 fully_filled × 4 try_send = 344 spawn / 24h 遠低風險 |
| Sender clone 成本 + 計數 | ✅ **CORRECT**：tokio mpsc Sender Clone 是 Arc-wrap 內部，~ns 級操作；retry 結束 task drop 自動 dec 引用計數 |
| retry 期間 channel writer drop | ✅ **HANDLED**：line 761-769 `Err(Closed)` arm 主動 return；無 leak |
| retry inside spawn 最終 drop event | ✅ **LOGGED**：line 773-778 計入 `retry_fail_total` + warn log；下游可觀察 |
| AgentSpineMsg Clone 是否安全 | ✅ **SAFE**：`store.rs:8 #[derive(Debug, Clone, PartialEq)]` + variants 全 Owned struct（無 unsafe / 無 raw pointer），retry_msg.clone() loop 內合法且安全 |

**對抗反問結果**：
- Q：「兩個 fill_completion 同時觸 retry，都 spawn 4 task，會否 race？」
  A：8 task 各自持 cloned msg；tokio runtime task scheduler 線程安全；channel.try_send 內部 Mutex；無 race ✅
- Q：「task 在 engine cancel 期會否 leak？」
  A：retry task **不接** CancellationToken，但 channel 關閉時 `Err(Closed)` 自動 return；最壞 case 4×50ms = 200ms 過渡期，無 long-lived leak ✅

**A 結論**：thread-safe，無 race。

---

## 3. B 條：Hot path SLA correctness（cross-check E5）

| 項 | 結論 |
|---|---|
| emit_entry_lineage 0 spawn / 0 sleep / 0 mutex | ✅ **VERIFIED**：grep `tokio::spawn|spawn|.lock()|Mutex::|RwLock::|tokio::time::sleep` 在 entry path 函式體（line 105-426）= 0 hit；全 sync try_send 4 callsite |
| drop_counter Atomic fetch_add lockless | ✅ **VERIFIED**：std::sync::atomic 是 hardware-level CAS，<5ns，無 OS lock |
| channel full fast-fail 不阻 | ✅ **VERIFIED**：try_send 在 hot path 中失敗即 fetch_add + warn + return false，0 retry 0 sleep |
| retry path 嚴格 caller-aware | ✅ **VERIFIED**：retry helper 僅 emit_fill_completion_lineage 用（4 callsite line 584/589/613/639）；emit_entry_lineage 全用 plain try_send（line 336/339/341/418）|
| caller-aware grep | ✅ entry caller = `step_4_5_dispatch.rs:664/932`（tick hot path），fill_completion caller = `loop_exchange.rs:283`（WS Fill event consumer，非 tick path）|

**B 結論**：hot path SLA 不變。E5 perf re-audit 主審；E2 cross-check 0 concern。

---

## 4. C 條：邊界與失敗模式

| 項 | 結論 |
|---|---|
| cap 1024→8192 memory pressure | ✅ **OK**：buf × 4 msg type × event size (~500B avg) = ~16MB worst-case，遠低於 engine RAM budget |
| 8K cap 對 batch_insert PG bind | ✅ **OK**：PG bind 65535 / Object 20col = 3276 chunk_rows；writer 用 chunked insert 自動分塊，cap 增到 8192 不破 PG bind |
| retry 50ms×3 累計 spawn task 在 24h | ✅ **OK**：實況 24h ~86 fully_filled × 4 try_send × spawn worst case = 344 spawn / 24h，可忽略 |
| spawn retry 過程中 engine 重啟 | ✅ **HANDLED**：channel close → retry task `Err(Closed)` arm 主動 return；無 panic / 無 leak |
| retry 期 channel writer 已 drop | ✅ **HANDLED**：Err(Closed) 對應退出 |
| spawn 過程同 fill_completion 結構性 burst | ✅ **OK**：分析見 §2 spawn 過量風險 |
| Counter overflow risk | ✅ **OK**：AtomicU64 max 1.8e19，process 24h 不可能達到 |

**C 結論**：邊界安全，無 leak/panic 路徑。

---

## 5. D 條：governance compliance

| 項 | 結論 | 詳細 |
|---|---|---|
| **§七 中文注釋** | ✅ PASS | grep 中文關鍵字 28 hit；新增注釋全含中文成分；混英技術詞（Fast path / Channel full）合法 |
| **§七 跨平台路徑** | ✅ PASS | diff grep `/home/ncyu\|/Users/[^/]+` = 0 hit |
| **§四 unsafe / unwrap 新增** | ✅ PASS | diff +addition 行 `unsafe|unwrap\(|expect\(` = 0 hit；既有 4 處 `expect()` 都是 pre-fix（line 118/501 `tx.expect("checked Some above")` after None early return = safe pattern；line 139 `.unwrap_or` 是 Option API；line 144 `.unwrap_or_else` 同） |
| **§九 800 行警告**：runtime_shadow.rs | ⚠️ **WARN-EXISTS** | 657 → 828，超 800 警告線 28 LOC（< 2000 hard cap）|
| **§九 Singleton 表** | ⚠️ **必更新** | CLAUDE.md §九 表 0 hit `SPINE_CHANNEL`；應加 3 行（spine_channel_drop_total / retry_success / retry_fail） |
| **§九 pre-existing baseline exception 引用** | ❌ **MEDIUM-1 MISAPPLICATION** | E1 report §9 Caveat 1 引用該 clause 為 runtime_shadow.rs 657→828 辯護；但 §九 原文 **明確 "僅適用 baseline > 2000 行 pre-existing violation"**；657 < 2000 不適用此 exception；屬 "新 wave 推 ≤2000 到 ≤2000" 場景（E2 memory 2026-05-11 W2 lesson #1 同型）|
| **§九 800 / 2000 hard cap** | ✅ PASS | 828 < 2000 hard cap；E2 必標警告 + 應開 P2 split ticket，但**不禁 merge** |
| **§七 SQL migration Guard A/B/C** | N/A | 本 fix 0 schema change |

**MEDIUM-1 修法（E2 不代寫業務代碼，但屬「報告 governance reference 修正」可建議）**：
- E1 report §9 Caveat 1 改用 W2 lesson #1 pattern 表述：「超 800 警告線；§九 pre-existing baseline exception clause **不適用**（僅適用 baseline > 2000）；屬警告線 watch，建議開 P2 split ticket，不阻 merge」
- 同步在 PM commit message 寫明 governance exception accept 理由（或開 P2 不引用 exception）

**Singleton 表新增（PM commit 時必加 3 行）**：
```markdown
| `SPINE_CHANNEL_DROP_TOTAL` / `SPINE_CHANNEL_RETRY_SUCCESS_TOTAL` / `SPINE_CHANNEL_RETRY_FAIL_TOTAL` | runtime_shadow.rs:57-59 | Wave 1.6 P1-FILL-LINEAGE-DROP；process-wide AtomicU64 counter；對外 `spine_channel_*_total()` 三 accessor；下游 P1-FILL-LINEAGE-MONITOR healthcheck [55] 用 |
```

---

## 6. E 條：unit test 真實驗

3 個新 test 逐個 read source code review：

| Test | 真實機制 | 驗的 invariant | E2 結論 |
|---|---|---|---|
| `fill_completion_channel_full_increments_drop_counter` | cap=1 + prefill 1 obj 塞滿；call emit_fill_completion → 4 try_send 全 fail；assert `accepted=0` + `drop_total delta >= 4` | (a) channel full → drop counter 嚴格遞增 4 | ✅ **TRUE INVARIANT**；非 mock，真實 channel + 真實 emit；delta >= 4 是合理 lower bound（其它 test 並行 +N 不破 assertion）|
| `fill_completion_burst_with_8192_cap_no_drop` | 私有 cap=8192 channel；100 iter × emit_fill_completion 各寫 4 msg；rx 不消費；assert 每次 `accepted=4`+最終 `queued=400` | (b) 8192 cap 下 burst 0 drop | ✅ **TRUE INVARIANT**；私有 channel 排除並行 test 污染；真實 try_recv 計 400 是 cap 真正生效強證據 |
| `fill_completion_retry_succeeds_after_slot_released` | cap=4 + prefill 4 obj 塞滿；call emit → 4 try_send fail spawn 4 retry task；drain 4 pre-fill 騰 slot；500ms deadline 等 retry msg 收齊 | (c) retry path 真實救援 | ✅ **TRUE INVARIANT**；真實 tokio::spawn + real time::sleep + 真實 rx.recv；deadline 500ms = 50ms×3 retry + 350ms scheduler buffer 合理 |

**對抗反問結果**：
- Q：「mock 是不是真實送 message？」答：3 個 test 全用真實 tokio::sync::mpsc::channel，0 mock；prefill 是真 SpineObjectEnvelope 構造 (strategy_signal_from_open_intent + from_strategy_signal)
- Q：「counter assertion 是否真實驗 atomic？」答：test (a) `drop_after - drop_before` 是真實 load + diff（並行 test 加 N 不破 lower bound）
- Q：「retry test 是否真模擬 tokio::spawn 行為？」答：用 #[tokio::test] runtime 真實 spawn + sleep；3 連跑 0 flaky（驗證見 §1 verdict）
- Q：「burst test 模擬多少 N? 確認 8192 cap 足？」答：100 × 4 = 400 << 8192 cap；rx 不消費 = worst case；queued=400 證 0 drop

**E 結論**：3 test 是真實 invariant 驗證，**非 happy-path mock**。

---

## 7. F 條：E1 自報 caveats verify

| Caveat | E1 自報 | E2 verify | 結論 |
|---|---|---|---|
| C1: runtime_shadow.rs 828 LOC > 800 警告 | E1 認為屬 §九 pre-existing exception clause 框架接受 | §九 原文 "僅適用 pre-existing 2000+"；657 < 2000 不適用此 exception；應引用 "警告線 < hard cap" 框架 + 開 P2 split ticket（E2 memory 2026-05-11 W2 lesson #1 同型） | ❌ **MEDIUM-1**：misapplication of clause；需修報告 + 開 P2 split ticket |
| C2: retry 用盡仍 fail = 永久 drop | E1 計 `retry_fail_total` 但 msg 永久 lost；屬 Option F4 known trade-off | ✅ verify 確認：line 773 `retry_fail_total.fetch_add(1)` + warn log；下游 healthcheck 可觀察；QA RCA expected residual <1% | ✅ **ACCEPTED**；trade-off 合理；ER 是 audit-trail 非 trading authority |
| C3: spawn 成本 micro-bench 未測 | 用估算 spawn ~10μs / Sender clone ~20ns | ✅ 理論推算合理；24h 累積上限 ~3.4ms 遠低於任何 SLA；E5 perf re-audit 主審 | ✅ **ACCEPTED**；P2 ticket 補 bench harness 可選 |
| C4: tests.rs 1476 LOC pre-existing 已超警告 | E1 認為屬 §九 pre-existing exception 接受 | tests.rs 1245→1476，pre-fix 已 1245 > 800 也不是 2000+ pre-existing；屬「test 檔政策一般寬」慣例 + W-D wave 後跟 G5-09 拆 sibling 合理 | ✅ **ACCEPTED**（test 檔慣例）+ 建議 P3 拆 sibling |

**process-wide counter 並行 test 污染問題**（E1 自報 §5 設計亮點）：
- test (a) 用 `drop_after - drop_before` lower bound `delta >= 4` 不破 ✓
- test (b) 用私有 channel + try_recv 計數，**不依賴 counter** ✓
- test (c) 用私有 channel + rx.recv，**不依賴 counter** ✓

E2 結論：**設計合理**，非「逃避測試」；process-wide counter 並行污染問題真實存在，E1 用對策略避開。

**multi-process scenario per-process vs global**：
- Linux trade-core 同時只跑一個 engine process（per `/tmp/openclaw/engine_*.lock` flock 護衛）
- Mac dev mode 不 spawn writer（`writes_enabled()` 需 demo/live_demo + agent_spine_mode 設定）
- → 不需 per-process counter

---

## 8. 跨 E2 + E5 議題協同

E5 perf re-audit 主審：spawn cost 真實 bench / cap 8K writer DB pressure / retry latency tail percentile。

E2 cross-check 上方 §3 + §4：
- spawn cost 理論可忽略（86 next/24h × 10μs ≈ 860μs/24h）
- 8K cap 對 batch_insert PG bind 不破（chunked insert 65535 param guard）
- retry latency 不在 hot path，不影響 tick SLA

如 E5 perf re-audit 發現 spawn cost 大於估算 → 需另外 P2 ticket 改 fixed-pool retry queue。

---

## 9. Findings 表

| 嚴重性 | 位置 | 描述 | 修法 |
|---|---|---|---|
| **MEDIUM-1** | `E1 report 2026-05-11--p1_fill_lineage_drop_fix.md` §9 Caveat 1 | 引用 §九 「pre-existing baseline exception clause」為 runtime_shadow.rs 657→828 辯護；但 §九 原文明確「僅適用 baseline > 2000 行」；657 < 2000 不適用 | E1 修報告 §9 Caveat 1 表述為「超 800 警告線；§九 pre-existing exception **不適用**；屬警告線 watch + 建議 P2 split ticket」；PM 同步開 P2 split ticket（與 W2 lesson #1 對齊）|
| **MEDIUM-2** | `runtime_shadow.rs:42-50` SPINE_CHANNEL_DROP_TOTAL 注釋 | drop_total 同時包含「entry path 永久丟失」+「fill_completion path 初始失敗（多數會 retry 救回）」；下游 healthcheck 直接用此 counter 當「最終丟失」會 over-report | E1 在 line 42-50 注釋明確標：drop_total = initial fail 計數，**不是** final loss；final loss = entry path 部分 drop + fill_completion path retry_fail_total；或拆出 `entry_drop_total` / `fill_completion_retry_initial_fail_total` 兩 counter（P1-FILL-LINEAGE-MONITOR 接線時必確認）|
| **LOW-1** | `runtime_shadow.rs:580` 注釋 | 「entry path 仍用 sync try_send (hot path SLA)」這句完美，但 §九 Singleton 表 PM 必加 3 行（E1 自報已點，E2 verify 表確實 0 hit） | PM commit 時加 3 行（內容見 §5）|
| **LOW-2** | `runtime_shadow.rs:725` `try_send_with_background_retry` 函式名 | 函式名 16-char 偏長，但語意 self-explanatory；對齊既有 `try_send` 命名 | 可保留 |
| **LOW-3** | `tests.rs:1247` 3 個新 test 緊密綁 process-wide counter 設計 | 未來如 P1-FILL-LINEAGE-MONITOR 拆 counter，需同步更新 3 個 test | 留 follow-up 注意（不阻 deploy）|
| **P2-1** | `runtime_shadow.rs` 828 LOC | 超 800 警告線（< 2000 hard cap） | 建議 PA 開 P2 split ticket 將 runtime_shadow.rs 拆為 `lineage_emit.rs` + `channel_helpers.rs` 兩 sibling（與 E5 W-C review §D-5/D-6 同方向）|
| **P2-2** | `tests.rs` 1476 LOC | pre-existing 已 1245 > 800；本 PR +231 LOC 增 18.5%；test 檔政策慣例寬，但仍應 split | 建議 PA 開 P2 split ticket，W-D wave 後一起 G5-09 拆 sibling |

---

## 10. governance exception 3 條件 E2 判斷

§九 Pre-existing baseline exception clause **不適用** 本 fix（runtime_shadow.rs 657 baseline < 2000）：

| 條件 | E2 判 |
|---|---|
| (1) wave 後 LOC ≤ pre-existing baseline + 5 LOC | ❌ 828 - 657 = +171 LOC >> +5 |
| (2) 同時開新 P2 ticket | ✅ 應開（見 §9 P2-1 / P2-2）|
| (3) PM Sign-off 明文 governance exception accept 理由 | N/A（不適用 exception clause）|

**E2 結論**：本 fix 不走 pre-existing exception clause；走「警告線 watch + 開 P2 split ticket + 不阻 merge」常規 path（與 2026-05-11 W2 IMPL btc_lead_lag.rs 1771 LOC 同型）。E1 report §9 Caveat 1 表述需修正。

---

## 11. 結論

**APPROVE WITH MINOR · PASS to E4**

- 設計 correct（B-2 caller-aware + B-3 局部融合）✓
- thread-safety 安全（Atomic Relaxed + 私有 channel 測試 + AgentSpineMsg Clone safe）✓
- hot path SLA 守住（entry path 0 spawn/sleep/lock）✓
- 邊界 / 失敗模式 handled（leak / panic 0）✓
- governance 95% PASS（中文注釋 + 跨平台 + unsafe/unwrap）✓
- 2810 lib test PASS + 3 new test 真實驗 + retry test 3 連跑穩定 ✓

**E4 可派**。

**PM commit 前必修**：
1. E1 report §9 Caveat 1 表述（MEDIUM-1）
2. drop_total counter 注釋語意（MEDIUM-2）
3. CLAUDE.md §九 Singleton 表加 3 行
4. PA 開 P2 split ticket（runtime_shadow.rs / tests.rs）

---

## 12. Cross-references

- E1 IMPL report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_fill_lineage_drop_fix.md`
- QA RCA: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--p1_rca_1_orphan_er_investigation.md`
- E2 lesson 2026-05-11 W2 (governance exception 適用範圍): `srv/docs/CCAgentWorkSpace/E2/memory.md:51-95`
- 源碼路徑:
  - `rust/openclaw_engine/src/tasks.rs:641-655` (cap 1024→8192)
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:33-93` (counter + accessor)
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:580-643` (emit_fill_completion 接 retry helper)
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:665-792` (try_send + try_send_with_background_retry)
  - `rust/openclaw_engine/src/agent_spine/tests.rs:1247-1476` (3 new test)

---

**E2 REVIEW DONE: APPROVE WITH MINOR · PASS to E4 · 2 MEDIUM + 3 LOW + 2 P2-governance-ticket · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_fill_lineage_drop_e2_review.md`**
