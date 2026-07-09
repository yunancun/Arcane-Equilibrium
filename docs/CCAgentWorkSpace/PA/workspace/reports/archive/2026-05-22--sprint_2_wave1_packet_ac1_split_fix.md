# PA Sprint 2 Wave 1 packet AC-1 split fix — 2026-05-22

## 1. E2 round 1 finding 引用

**HIGH-3 — AC-1 sign-off 不可達 Wave 1 phase**：

> packet §2.4 AC-1 寫「V106 30min window engine_runtime row count ≥ 5」(real PG SQL)；但 Wave 1 scaffold IMPL 不接 main.rs scheduler，只有 trait + writer + mock fixture；real PG row 永遠 0。Wave 1 scaffold sign-off 不能 claim AC-1 closed；Phase 3c QA 跑 SQL 必 fail。

**LOW-1 — AC-1 描述粗略**：

> packet 寫「5 sample = 5 row」描述 imprecise；engine_runtime 6 metric × 5 sample window tick = 30 V106 row 才對。

## 2. AC-1 拆分 (a/b)

- **AC-1a** (Wave 1 / Wave 2 scaffold sign-off)：cargo test `test_sprint2_track_*_in_memory_proxy` PASS；以 in-memory `HealthObservationWriter` mock fixture 驅動 5 sample window × N metric tick → ≥ N×5 V106 row written 至 mock writer；**不需 main.rs scheduler 接線 / 不需 real PG**。
- **AC-1b** (Wave 2+ real PG empirical)：Phase 3c QA 跑 real PG SQL；前置 = (1) main.rs 接 `MetricEmitterScheduler::run` (2) Linux runtime --rebuild (3) ≥30 min 樣本累積；scaffold sign-off 不 block；6 Track 並行 sign-off 不繞此前置。

**Rationale**：解開 Wave 1 阻塞（mock fixture 可獨立 sign-off）但保 Phase 3c 治理門檻（main.rs 接線 + real PG empirical 是 Sprint 2 整體交付證據）。

## 3. 6 Track packet patches

| Track | File line | 拆分後 line | 內容 |
|---|---|---|---|
| §2.4 Track A engine_runtime | line 134 (舊) | line 141-142 (新 a/b) | 6 metric (cpu_pct / rss_mb / fd_pct / event_loop_lag_p95_ms / scheduler_tick_skew_ms / disk_io_util_pct) × 5 sample = 30 row tick — 明示細化 (LOW-1 closure) |
| §3.4 Track B pipeline_throughput | line 191 (舊) | line 199-200 (新 a/b) | 5 sample × N metric → ≥ N×5 row |
| §4.4 Track C database_pool | line 238 (舊) | line 247-248 (新 a/b) | 同上 |
| §5.4 Track D api_latency | line 284 (舊) | line 294-295 (新 a/b) | 同上 |
| §6.4 Track E strategy_quality | line 334 (舊) | line 345-346 (新 a/b) | 5 sample × N metric per strategy × symbol pair → ≥ N×5 row |
| §7.4 Track F risk_envelope | line 382 (舊) | line 394-395 (新 a/b) | 同上 |
| §0 TL;DR | line 28 (新增) | bullet 5 | AC-1 拆分 a/b 全局聲明 + AC-1b 不阻 Wave 1 |
| §1 prerequisite §1.6.1 | line 72-75 (新增小節) | 1.6.1 | AC-1 拆分契約 + Rationale (HIGH-3 fix 引用) |

D3 cascade reject AC (Track A line 138 / 新 145) **不動** — 屬 D3 not AC-1，且 in-memory mock cargo test 已 PASS，不在 HIGH-3 範圍。

## 4. design spec sync

| 位置 | 修改 |
|---|---|
| `srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` line 33 | TL;DR AC-1..7 描述加 "AC-1 拆 a/b — AC-1a Wave 1 in-memory mock fixture / AC-1b Wave 2+ real PG empirical；per 2026-05-22 E2 round 1 HIGH-3 fix" |
| 同檔 §7 line 725-726 | AC-1 single row → AC-1a + AC-1b 兩 row；a 由 E2 sign-off / b 由 QA (Phase 3c) sign-off |
| 同檔 §AC-1 verify SQL detail (line 733-747) | **不動** — 該 SQL 仍是 AC-1b 的權威 verify pattern；無冗餘 |

## 5. LOW-1 描述細化

Track A 新 line 141：明示 6 metric (cpu_pct / rss_mb / fd_pct / event_loop_lag_p95_ms / scheduler_tick_skew_ms / disk_io_util_pct) × 5 sample = **30 V106 row tick**；以及 cycle 5 sample × 30s = 2.5 min mock Instant 推進。

Track B-F 描述為 N metric × 5 sample = N×5 row（N 由各 Track E1 IMPL 決定 metric 個數，不寫死避綁定）；strategy_quality 額外乘 per strategy × symbol pair。

LOW-1 「5 sample = 5 row」粗略描述 closure。

## 6. HIGH-3 + LOW-1 closure verdict

**HIGH-3 DONE / 修**：6 Track AC-1 → AC-1a/AC-1b 拆分全 land；§0 TL;DR + §1.6.1 prerequisite + design spec §AC-1 sync；Wave 1 scaffold sign-off 可獨立 fire（cargo in-memory test PASS）不阻 E1 round 2；real PG empirical 治理門檻保留至 Phase 3c。

**LOW-1 DONE / 修**：6 metric × 5 sample = 30 row tick 明示；N×5 row pattern 推廣其他 5 Track；不寫死 metric 個數避綁定 E1 IMPL choice。

**E1 round 2 阻塞**：無；E1 round 2 並行修 IMPL（per E2 round 1 其他 finding）即可。

**Sub-agent dispatch**：無；本 task 屬 PA single-thread doc edit。

**下一步**：E2 round 2 review 引用本 fix report 與 E2 round 1 比對；若 HIGH-3 + LOW-1 closure pattern 符合期望，packet + spec ready for Wave 1 E1 round 2 dispatch。

---

## Files touched

- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` (8 edits — 6 Track AC-1 拆分 + §0 TL;DR + §1.6.1)
- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` (2 edits — line 33 TL;DR + line 725-726 §AC-1)

## 風險評級

- **低**：純 doc edit；不觸 Rust IMPL / 不觸 V### SQL / 不改硬邊界（live_execution_allowed / max_retries / system_mode 全未碰）。
- **副作用**：無下游模組 import 此 doc；E1 round 2 / E2 round 2 / Phase 3c QA 依新 a/b AC 重新 sign-off pattern 即可。
- **16 根原則合規**：原則 1 (single write entry V106 不變) / 原則 6 (AC-1b 保 fail-closed 至 real PG empirical) / 原則 8 (cargo test + Phase 3c SQL 雙重 reconstructable) 全合規；DOC-08 §12 安全不變量 9 條無觸碰。
