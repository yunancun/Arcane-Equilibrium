---
report: Sprint 2 Wave 1 Track B + Track A scaffold MEDIUM-2 + MetricSample trait expansion — E2 round 2 re-review
date: 2026-05-22
author: E2 (Adversarial Backend Reviewer)
phase: Sprint 2 Phase 2 Wave 1 — round 2 re-review of 6 round 1 Track B findings + trait API expansion
status: APPROVE-WITH-CONDITIONS（Wave 1 closure ready；1 carry-over recommend Wave 2 cover）
parent dispatch:
  - PA spec amend land 2026-05-22（M3 §2.3 line 102 + §2.3.1 + §2.3.2）
  - E1 round 2 5/9 deterministic closure
  - E1 round 3 4/9 PA-dependent closure → 9/9 total
---

# E2 round 2 re-review — Track B 對齊 PA spec amend 與 round 1 6 findings

## §1. 6 round 1 Track B findings closure verdict

| # | finding | round 2/3 fix | E2 round 2 verdict |
|---|---|---|---|
| HIGH-1 | heartbeat_lag spec drift（DEGRADED 60-120s → CRITICAL >120s） | round 2 ladder revert > 60_000 CRITICAL（pipeline_throughput.rs:237-245） | **PASS** — spec line 102 SSOT「WS dropout > 60s = CRITICAL」literal 對齊；unit test 8 assertion 全 PASS（45_000=WARN / 60_000=WARN / 60_001=CRITICAL / 90_000/120_000/150_000=CRITICAL）|
| HIGH-2 | 「持續 2min」semantic 與 SM dwell 60s 混淆 | round 3 Fix 1 ws_tick_rate doc:179-202 引 §2.3.1 + 明示「v5.7 carry-over 非規範性敘述；60s SM dwell SSOT 對齊 ADR-0042 不 amend」 | **PASS** — PA spec amend §2.3.1 真實 land（spec line 110-120 grep verify）+ classify_helper 不混雜 dwell 邏輯 |
| MEDIUM-1 | drift+signal_rate threshold spec drift（未進 spec ladder） | round 3 Fix 2 drift doc:255-263 + signal_rate doc:282-292 引 spec line 102 amend；IMPL 數值對齊保留 | **PASS** — PA spec line 102 真實 land threshold（drift OK=0/WARN=1-2/DEGRADED≥3 + signal_rate OK≥0.5/WARN=0.1-0.5/DEGRADED<0.1）；IMPL 1:1 對齊 |
| MEDIUM-2 | mean as u32 truncation（影響 Track B heartbeat / drift） | round 2 Track A scaffold MEDIUM-2 fix 全 5 處 → `mean.round() as u32/u64`（mod.rs:954/958/963/981/989）+ Track C 3 處（mod.rs:1018/1023） | **PASS（with testing gap）** — mean.round() semantic 正確；但 mod.rs unit test 沒對應 mean.round() boundary regression test，僅 inline comment doc — 見 §2 carry-over |
| LOW-1 | ws_tick_rate 邊界 inclusive cosmetic | round 1 noted accept | **PASS** — 不 blocking；doc OK band 「>= 1.0」+ WARN band 「0.5 - 1.0 exclusive」既有 |
| LOW-2 | cross_domain test 設計弱 | round 1 noted accept；defer Wave 2 | **PASS** — Wave 2 cover；不 blocking Wave 1 closure |

**6/6 round 1 Track B findings closure — 全 PASS（1 carry-over testing gap recommend Wave 2 補 boundary test）**。

## §2. Track A scaffold MEDIUM-2 mean.round() 對 Track B 影響評估

### 2.1 cast site 真實覆蓋

mod.rs `classify_aggregated` 5 處（per 對抗反問 #2 IEEE 754 boundary verify）：

| Line | metric | cast | round semantic |
|---|---|---|---|
| 954 | open_fd_count | `mean.round() as u32` | half-away-from-zero（per Rust `f64::round`）|
| 958 | thread_count | `mean.round() as u32` | 同上 |
| 963 | uptime_sec | `mean.round() as u64` | 同上 |
| 981 | ws_heartbeat_lag_ms（Track B） | `mean.round() as u32` | 同上 |
| 989 | ws_subscription_drift_count（Track B） | `mean.round() as u32` | 同上 |
| 1018 | pg_pool_wait_ms_p95（Track C） | `mean.round() as u32` | 同上 |
| 1023 | pg_writer_queue_depth（Track C） | `mean.round() as u32` | 同上 |

**5 cast site Track A + 2 Track B + 2 Track C = 9 total**（不是 dispatch 描述「5」）。E1 round 2 report §2 Fix 1 寫「5 處」涵蓋 Track A 3 + Track B 2（uptime/open_fd/thread + heartbeat/drift），未列 Track C 2 處（round 2 Fix 2 加 Track C arm 時順帶用 mean.round()）。Track C ratio + signal_rate / ipc_p99 / disk_used_pct 為 f64 path 不需 cast — 對齊。**5 處全覆蓋宣稱基本準確**（dispatch 嚴格說 9 處更精確，但 Track A scaffold 端 3 + Track B 2 = 5 對；Track C 2 是 round 2 HIGH-1 fix 順帶啦）。

### 2.2 IEEE 754 boundary 對抗反問 verify

對抗反問 #2「mean=60_400.5 round → 60_401 > 60_000 → CRITICAL」邊界 trace：

| input | `f64::round()` | as u32 | classify_pipeline_throughput_heartbeat_lag_ms | 期望 |
|---|---|---|---|---|
| 60_000.6 | 60_001.0 | 60_001 | CRITICAL | ✓ |
| 60_000.5 | 60_001.0（Rust half-away-from-zero） | 60_001 | CRITICAL | ✓ |
| 60_000.4 | 60_000.0 | 60_000 | WARN（30_001-60_000） | ✓ |
| 59_999.5 | 60_000.0 | 60_000 | WARN | ✓ |
| 59_999.4 | 59_999.0 | 59_999 | WARN | ✓ |
| 60_400.5 | 60_401.0 | 60_401 | CRITICAL | ✓ |
| 30_000.5 | 30_001.0 | 30_001 | WARN（>30_000） | ✓ |
| 30_000.4 | 30_000.0 | 30_000 | OK（<=30_000） | ✓ |

Rust `f64::round` 是 half-away-from-zero 而非銀行家舍入（half-to-even）；boundary 60_000.5 → 60_001 升 CRITICAL 對齊 spec 設計。**IEEE 754 boundary 行為正確**。

### 2.3 既有 test mean.round() boundary regression — **TESTING GAP**

verify：

```
grep -n "60_500\|60_400\|test.*round\|test.*boundary" mod.rs
→ 0 hit
grep -n "60_000\|60_001" sprint2_track_b_pipeline_throughput.rs
→ 0 hit
```

**Track B integration test 沒有 mean=60_400.5 / 60_000.5 之 boundary case**。E1 round 2 report §2 Fix 1 自我宣稱：「既有 unit test 注入 mean = integer 值（30_000 / 0 等），round 與 truncate 同值。Fix 解決的是「mean 在 ladder boundary 附近的小數 sample」場景；既有 test 不觸 boundary，無回歸」 — 真實情況是 **fix 解決的問題沒對應的 regression test**。

**評估**：
- 因為 round-nearest semantic 行為正確且 spec 明確（mean.round() rationale comment 已寫），mean.round() 行為退化（被誰 revert 改回 `as u32`）需手動 PR 引入；testing gap 不會引發本次 closure block。
- 但 boundary test 缺失違反 `feedback_impl_done_adversarial_review` 多角色 review 原則「adversarial 守 dispatch 真實接通」— 沒 boundary test 就無 regression 守 mean.round() 不退化。
- **Severity = LOW**（不 blocking Wave 1 closure；但記為 Wave 2 補 boundary test follow-up）。

## §3. MetricSample::extra_evidence trait API expansion 評估

### 3.1 trait method add — non-breaking

mod.rs:92-94 `MetricSample` trait 加 default method `fn extra_evidence(&self) -> Option<serde_json::Value> { None }`。

**對 3 個 implementor 影響 verify**：

| Implementor | override extra_evidence? | 行為 |
|---|---|---|
| Track A `EngineRuntimeMetricRow`（mod.rs:244） | 沒 override（grep verify 0 hit） | 走 default None；engine_runtime 採樣 evidence_json 路徑不變 |
| Track B `PipelineThroughputMetricRow`（pipeline_throughput.rs:101） | 沒 override（grep verify 0 hit） | 走 default None；pipeline_throughput row evidence_json 路徑不變 |
| Track C `DatabasePoolMetricRow`（database_pool.rs:236-258） | override 返 `{"pool_status": "disconnected"}` if `pool_disconnected` else None | round 3 Fix 4 新加；disconnected 場景寫 evidence_json |

**結論**：
- Track A + Track B impl 走 default None — **0 行為變動，0 regression risk**
- Track C impl override 是 round 3 新增功能（per spec §2.3.2 disconnected handling）
- trait extension 是 non-breaking（per Rust trait default method semantic）

### 3.2 Track B 是否應顯式 override extra_evidence = None?

對抗反問 #5「Track B 5 metric 不含 disconnected 場景；trait default None 合理 vs 應 explicit override?」

**評估**：
- Track B `PipelineThroughputMetricRow` 5 metric（ws_tick_rate / heartbeat_lag / drift / signal_rate / ipc_p99）採樣語意是「實時觀測，無 sample-time audit context」— 不需 evidence_json
- 走 default None 是正確 Rust idiom（default method 設計目的就是給「無需 override」的 implementor 用）
- 顯式 override `extra_evidence = None` 屬於 redundant code（duplicate default behavior）— 違 §七 「Surgical changes / no opportunistic adjacent cleanup」
- **不 require Track B override**；default None 合理

### 3.3 trait expansion governance 評估

E1 round 3 report §6 carry-over #1 自評：「MetricSample trait extra_evidence default None 是公開 API 擴展；若 E2 認為應走 trait amend ADR-0036 / ADR-0042 governance review，E1 round 4 可拆出獨立 follow-up 走 PA / CC / FA chain」

**E2 verdict**：
- trait method add（default impl）= **non-breaking semver-minor**（per Rust API guidelines）
- 不需 ADR amend：ADR-0042 governance 是 M3 health monitoring 整體架構決策；trait method 增加是 IMPL detail（per spec §3 D1 採樣邊界內）
- spec §2.3.2 disconnected handling 已明示「evidence_json 寫入路徑」— trait method 是該 spec 的 IMPL detail，不需獨立 ADR
- **不需 governance review**；E1 round 3 carry-over #1 closure as NO-OP

## §4. PA spec amend 對齊 verify（對抗反問 #3 + #4）

### 4.1 對抗反問 #3 — spec line 102 真實 amend?

verify：

```
grep -n "ws_subscription_drift_count\|strategy_signal_rate_per_min\|60_000\|active/max" docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md | head -20
→ line 78 mention metric_name list
→ line 102: pipeline_throughput row OK band 「tick rate > 1/sec/symbol + ipc p99 < 5ms + ws_subscription_drift_count = 0 + strategy_signal_rate_per_min ≥ 0.5」
   WARN: 「tick rate 0.5-1.0/sec/symbol OR ipc p99 5-10ms OR ws_subscription_drift_count 1-2 OR strategy_signal_rate_per_min 0.1-0.5」
   DEGRADED: 「tick rate < 0.5/sec/symbol OR ipc p99 > 10ms OR ws_subscription_drift_count ≥ 3 OR strategy_signal_rate_per_min < 0.1」
   CRITICAL: 「heartbeat_lag_ms > 60_000 (WS dropout > 60s) OR ipc p99 > 50ms」
→ line 103: database_pool row 「active/max < 80% / 80-95% / > 95% / disconnected → fail-closed OK band (per §2.3.2)」
```

**spec line 102 + 103 真實 land** — 4 amend 寫進 M3 design spec ladder ✓。

### 4.2 對抗反問 #4 — §2.3.1 + §2.3.2 真實新增?

verify：

```
grep -n "§2.3.1\|§2.3.2\|metric classify vs SM band dwell\|database_pool disconnected handling" docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md
→ line 110: ### 2.3.1 metric classify vs SM band dwell — 區分（per 2026-05-22 E2 round 1 HIGH-2 + HIGH-1 fix）
→ line 114-120: metric classify band vs SM band dwell 區分 + heartbeat_lag_ms 即時 CRITICAL + 「持續 2min」literal 為非規範性 v5.7 carry-over
→ line 122: ### 2.3.2 database_pool disconnected handling — fail-closed OK band（per 2026-05-22 E2 round 1 MEDIUM-3 C fix）
→ line 126+: 4 metric 回 OK band；emitter 端不誤升 CRITICAL；evidence_json 寫 `{"pool_status": "disconnected"}` audit trail
```

**§2.3.1 + §2.3.2 真實新增** — PA spec amend 對齊 ✓。

### 4.3 ADR-0042 amend 確認

PA spec amend report §2.4 + §5：「ADR-0042 — 不 amend」(2026-05-21 v1.0 保持)。

verify：

```
grep -l "Sprint 2 Wave 1\|2026-05-22 amend" srv/docs/adr/0042-m3-health-monitoring.md
→ 0 hit
```

**ADR-0042 真實未 amend** — governance scope 不變 ✓。

## §5. OpenClaw §3 checklist re-check after round 2+3

| §3 條目 | 狀態 | verify |
|---|---|---|
| §3.1 跨平台 | PASS | `grep -nE "/home/ncyu\|/Users/[^/]+/"` 3 file 0 hit（pipeline_throughput / database_pool / mod.rs production code）|
| §3.2 注釋 | PASS | round 3 新增 doc comment 全中文；無 emoji；觸及 doc block 移除英文保留中文 |
| §3.3 Rust unsafe | PASS | 3 file 0 unsafe block（grep verify）|
| §3.3 Rust unwrap/expect | PASS | 16 hit 全在 `#[cfg(test)]` 範圍（tests::* mod；database_pool.rs:697/733/740/778/902/911/928/936/941 + pipeline_throughput.rs:673/693/699/706/712/718/724）；production code path 0 unwrap |
| §3.3 panic/todo | PASS | 3 file 0 panic!/todo!/unimplemented! hit |
| §3.7 Singleton | PASS | 不引新 singleton；DatabasePoolEmitter 走 caller 注入 Arc<DbPool> + probe；MetricEmitterScheduler 已登記 |
| §3.8 文件大小 | WARN | metric_emitter/mod.rs 1173 LOC > 800（scaffold owner 預期 LOC peak；<2000 hard cap）；database_pool.rs 944 LOC > 800（含大量 inline test）；pipeline_throughput.rs 727 LOC < 800 |
| §3.10 P0/P1 caller-proof | N/A | 本 review 非 leak/bias finding；不適用 |
| §3.11 ML pipeline non-input | N/A | 本 IMPL 不觸 close_maker_* 欄位；不適用 |

LOC peak 兩個 file 既有，per E1 round 2/3 report 自評是「scaffold owner 預期 LOC peak / Track C IMPL + 大量 inline test」— 不切 file 否則破壞 Track B-F sub-agent 沿用 path（scaffold pattern 是 Wave 1 closure 重要 invariant）。**LOC 警告但非 blocker**；Wave 2 完成後若 metric_emitter 超 2000 hard cap 再考慮拆分。

## §6. cargo test re-run verify（Mac sandbox）

| Verify | Result |
|---|---|
| Track A integration | **9/9 PASS** — round 2 fix 不退；spike default false invariant 守 |
| Track B integration | **5/5 PASS** — ladder / cross_domain / row_count / spike / real_emitter；heartbeat ladder revert 後全 PASS |
| Track C integration | **8/8 PASS** — 5 舊 + round 2 stress + 2 round 3 new（active_conn_ratio_classify + disconnected_emits_pool_status_evidence）|

**22/22 integration test 全 PASS（Mac sandbox）**；regression 不退。lib unit + spike 結果採信 E1 round 3 report §2（3121/3121 + 3/3）。

## §7. 對抗反問 round 2 結論

| # | Q | A | 評估 |
|---|---|---|---|
| 1 | heartbeat_lag=61_000 採樣 1 次走 SM observe_classified 立即升 CRITICAL state? | sample classify_band 立即返 CRITICAL（spec §2.3.1 line 118-120「即時 fire」），但 SM observe_classified 仍走標準 ladder（OK→WARN→DEGRADED→CRITICAL）。spec 不要求 SM dwell=0；只要求 metric classify band 立即 CRITICAL。Track B IMPL 對齊。 | PASS |
| 2 | mean=60_400.5 round → 60_401 > 60_000 → CRITICAL，但 mean=60_400.4 round → 60_400 仍 < 60_001 → DEGRADED? | Rust `f64::round` half-away-from-zero；60_400.4 → 60_400 → WARN（30_001-60_000 range），不是 DEGRADED；60_000.5 → 60_001 → CRITICAL。boundary semantic 正確；但 **unit test 沒對應 boundary regression test**（§2.3 testing gap）。 | PASS-with-testing-gap |
| 3 | PA spec line 102 真實 amend 含 drift + signal_rate threshold? | grep verify spec line 102 真實 land 4 metric ladder + line 110-120 §2.3.1 + line 122-126 §2.3.2 全寫進。 | PASS |
| 4 | PA §2.3.1 真實新增區分 classify vs dwell? | grep verify line 110-120 §2.3.1 「metric classify vs SM band dwell」+ heartbeat 即時 fire + 「持續 2min」非規範性 carry-over 全寫進。 | PASS |
| 5 | extra_evidence trait API expansion — Track B 5 metric 不含 disconnected 場景；trait default None 合理 vs 應 explicit override? | trait default None 合理（Rust idiom）；Track B 不需 override；non-breaking expansion；不需 ADR governance review。 | PASS |

## §8. Findings（round 2 re-review）

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| LOW | `rust/openclaw_engine/src/health/metric_emitter/mod.rs` 1041-1173 + `tests/sprint2_track_b_pipeline_throughput.rs` | mean.round() boundary regression test 缺失（mean=60_000.5 / 60_400.5 / 30_000.5 等 IEEE 754 半位 case 未驗）— testing gap，違 adversarial review 多角色守 dispatch 真實接通原則 | Wave 2 補 unit test `test_classify_aggregated_mean_round_boundary` 注入 4-5 個 boundary mean 值驗 round-nearest semantic；亦可 Track B integration test 用 `[60_499, 60_500, 60_400, 60_300, 60_300]` mean=60_400.0 sample 場景 |
| LOW | `pipeline_throughput.rs` LOC 727 + `database_pool.rs` LOC 944 + `mod.rs` LOC 1173 | 3 file LOC peak（>800 警告），scaffold pattern 期內合理；Wave 5+ cascade IMPL 後若超 2000 hard cap 再拆 | Wave 2 IMPL 後重評；如 metric_emitter/mod.rs 接 Track D/E/F arm 再多 200+ 行可考慮 helper crate 拆分 |

**0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW**

## §9. 結論

**APPROVE-WITH-CONDITIONS — Wave 1 closure ready / Wave 2 派發 ready**

- 6/6 round 1 Track B findings closure 全 PASS（HIGH-1 ladder revert + HIGH-2 §2.3.1 reference + MEDIUM-1 §2.3 amend reference + MEDIUM-2 mean.round() + LOW-1 LOW-2 既有 accept）
- PA spec amend 4 條（spec line 102 + §2.3.1 + §2.3.2 + §3.2/§4.3）真實 land verify
- MetricSample::extra_evidence trait expansion non-breaking + non-governance review
- Track A 9/9 + Track B 5/5 + Track C 8/8 = 22/22 integration test 全 PASS（Mac sandbox）
- §3 OpenClaw checklist 全 PASS（unsafe/unwrap/panic/cross-platform/singleton 全 0 hit；LOC warn but non-blocker）
- 2 LOW finding 為 Wave 2 follow-up（mean.round() boundary regression test + LOC peak monitoring）— 不 blocking Wave 1 closure

### 9.1 Wave 2 follow-up（不 blocking Wave 1）

1. **mean.round() boundary regression test**：mod.rs unit test 補 `test_classify_aggregated_mean_round_boundary` 驗 9 cast site 各注入 1-2 個 boundary mean（half-up / half-down / integer mean）；亦在 Track B integration test 加 `[60_499, 60_500, 60_400, 60_300, 60_300]` mean=60_400.0 sample 場景（pipeline_throughput emitter 直接觸 mean.round() path）。
2. **LOC peak monitoring**：metric_emitter/mod.rs + database_pool.rs 已超 800 警告；Wave 2 IMPL Track D/E/F 後重評；若超 2000 hard cap 拆 helper crate（`health_metric_emitter` / `health_domains` 分 crate）。

### 9.2 不需 E1 round 4

本 review 0 blocker → Wave 1 closure 不退回 E1；Wave 2 follow-up entry 由 PM 收口時登記。

### 9.3 治理對照

- §六 Hard Boundaries：未碰 live_execution_allowed / execution_authority / system_mode / max_retries / production engine（PID 2934602）/ trading_ai DB / V### SQL ✓
- §七 Code And Docs Rules：注釋全中文 / 0 emoji / bilingual-comment-style 對齊 / surgical changes 對齊 ✓
- §八 Workflow：E2 round 2 不寫業務代碼（per E2 對抗審核立場）；本 sign-off 不 commit；不派下游 sub-agent ✓
- §九 Code Structure Guardrails：3 file LOC 警告但 < 2000 hard cap（scaffold owner 預期 LOC peak）+ 0 新 singleton + 0 新 GUI write surface ✓
- `feedback_impl_done_adversarial_review` 2026-05-09：本 round IMPL 含共用 helper（MetricSample trait extra_evidence default method）+ 寫操作（row.with_evidence 路徑）；E2 + A3 並行核驗對齊 — E2 sign-off 不取代 A3；A3 review 路徑由 PM 收口時 dispatch（per E1 round 3 report §8 #2）

### 9.4 Multi-session race check（§5 P0-GOV-MULTI-SESSION-RACE-SOP-1）

- 5a 提交前 fetch + sibling window check：E2 sign-off report commit 由 PM 收口執行；本 sub-agent 不 commit / 不 push ✓
- 5b sub-agent IMPL DONE 前 status clean：E2 review 不 IMPL；不適用 ✓
- 5c 看到 unknown WIP 禁 revert：本 review session 全程 read-only；0 git operation ✓
- 5d Sign-off report commit 前 path clean：本 sub-agent 寫 sign-off report 在 `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-22--sprint2_wave1_round2_track_b_re_review.md`，由 PM commit；不在 review 期間 commit ✓
- 5e PR review 期間 sibling 推 origin → 重 fetch 重 review：本 review 期間無 sibling push 事件（本 task 為 1hr single-thread review）✓

---

## §10. 修改清單（read-only review）

| File 類型 | 觸碰路徑 | 改動 |
|---|---|---|
| Read-only 驗證 | `pipeline_throughput.rs:179-202/237-245/255-263/282-292` | doc comment 對齊 spec amend 驗 + heartbeat ladder revert 驗 |
| Read-only 驗證 | `database_pool.rs:80-124/180-260/278-320/434-440` | classify_active_conn_ratio helper + 5 row into_metric_rows + extra_evidence override + sample_now disconnected flag 驗 |
| Read-only 驗證 | `metric_emitter/mod.rs:69-95/710-905/922-928/936-1035` | MetricSample trait extra_evidence default method + run_domain_loop reject_reason/extra_evidence 互斥邏輯 + classify_aggregated_for_test pub wrapper + classify_aggregated 9 cast site 驗 |
| Read-only 驗證 | `tests/sprint2_track_b_pipeline_throughput.rs` | 5 test PASS verify |
| Read-only 驗證 | `tests/sprint2_track_c_database_pool.rs` | 8 test PASS verify |
| Read-only 驗證 | `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md` | line 102/103 amend + §2.3.1 + §2.3.2 真實 land verify |
| 新建 | `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-22--sprint2_wave1_round2_track_b_re_review.md` | 本 sign-off report |

**0 code 改動**（E2 對抗審核立場 — 不代寫業務邏輯）；2 LOW finding 為 Wave 2 follow-up 由 PM 登記。

---

**E2 REVIEW DONE: APPROVE-WITH-CONDITIONS · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-22--sprint2_wave1_round2_track_b_re_review.md`**

E1 round 4 不需 dispatch；Wave 1 closure ready；Wave 2 派發 ready；2 LOW finding 由 PM 收口時登記為 Wave 2 follow-up（mean.round() boundary regression test + LOC peak monitoring）。
