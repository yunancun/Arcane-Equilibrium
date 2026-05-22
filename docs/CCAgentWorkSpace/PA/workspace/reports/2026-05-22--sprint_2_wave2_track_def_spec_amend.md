# PA Sprint 2 Wave 2 Track D/F spec amend — 2026-05-22

E2 round 1 Track D REJECT (CRIT-1 + 3 HIGH + 2 MED + 1 LOW)、Track E REJECT (1 HIGH + 3 LOW)、Track F APPROVE-WITH-CONDITIONS (1 MED + 2 LOW) 後 4 spec-dependent finding 需 PA single-thread spec amend land。

## 1. 4 amend 拍板

### 1.1 Track D CRITICAL-1 — `ApiLatencySample` 5→8 field 結構升級

**決議**：對齊 E1 IMPL reality 已落的 8 field（`api_latency.rs` line 103-120），補 spec 規範缺漏；非 revert 路徑，屬 spec 對齊 IMPL 的合法 amend 流程。

**修法**：
- M3 design spec §2.3 line 104 api_latency row 由舊 5-metric 文字（success_rate / p95 / 持續 5min）改為 8-metric 完整 ladder（rest_p50 / rest_p95 / rest_p99 / ws_rtt_p50 / ws_rtt_p99 / ret_4xx / ret_5xx / ws_dropout）
- M3 design spec 新增 §2.3.3「api_latency 8 metric 結構 — Track D Sprint 2 amend」段落：8 metric × 4 band 明示 + 5 條設計理由（三分位 latency / 4xx vs 5xx 分離 / ws_rtt 早預警 / count 而非 rate / 4 metric 含 CRITICAL band）
- Sprint 2 design spec §3.2 `ApiLatencySample` struct 由 5 field 改 8 field + 補設計理由 + Wave 2 main.rs 接線 carry-over 註腳
- Sprint 2 design spec §6.2 anomaly_id 命名表 api_latency row 由舊 2 例升級為 8 anomaly_id literal
- Sprint 2 design spec §0 TL;DR 加 amend bullet
- dispatch packet §5.2 E1 prompt skeleton scope #2 明示 8 field metric names
- dispatch packet §5.4 AC-1a 由「N metric tick → ≥ N×5 row」改為「8 metric tick → ≥ 40 row」literal
- dispatch packet §5.4 新增 AC-2b 8 anomaly_id 命名核驗條款
- dispatch packet §0 TL;DR 加 amend bullet

**CRITICAL band 分布**（4 含 / 4 不含）：
- 含 CRITICAL：rest_p99 > 2000ms / ws_rtt_p99 > 1500ms / ret_5xx > 20 / ws_dropout > 5
- 不含 CRITICAL：rest_p50 / rest_p95 / ws_rtt_p50 / ret_code_4xx

### 1.2 Track D MEDIUM-1 — OBSERVE-4 replay subprocess guard 升 Track A scaffold contract

**決議**：M3 design spec line 199-216 OBSERVE-4 invariant 真實存在於 Sprint 2 spec（grep verified）；但 dispatch packet §1.7 Track A scaffold contract 漏列 guard 為必交付項，造成 Wave 1 Track A scaffold round 1 漏實作。

**修法**：
- Sprint 2 design spec 新增 §5.0「OBSERVE-4 invariant — engine_mode replay subprocess emit forbidden」段（在 §5.1 spike Track B `HealthStateMachine` 升級點之前）
- §5.0 內含：設計合約重申 + scaffold-level guard 必加位置 + IMPL code snippet + E4 regression test 必加（`tests/m3_emitter_replay_forbidden.rs`）+ rationale
- dispatch packet §1.7 Track A scaffold contract 表加 row「OBSERVE-4 replay subprocess guard ~20 LOC」+ 升級總計 500→520 LOC
- dispatch packet §1.7 後置「OBSERVE-4 replay subprocess guard 詳述」段：guard code + 必交付測試 + 必交付 grep + 必交付 enum variant `M3Error::ReplaySubprocessForbidden` + 「不可推遲至 Track D/E/F」rationale
- dispatch packet §0 TL;DR 加 amend bullet

**Cross-Wave fix 標明**：屬 Track A scaffold round X 工作；新 test `tests/m3_emitter_replay_forbidden.rs` 屬 E4 regression suite；scaffold guard 必在 6 Track 共用 writer 入口（DRY 原則），Track D/E/F 不獨立 guard。

### 1.3 Track D HIGH-3 — bybit_rest_client + bybit_private_ws prerequisite false 修正 + PA-DRIFT-4 follow-up

**決議**：dispatch packet §5.1 原 prerequisite「既有 bybit_rest_client + bybit_ws_client 有 p95 / retCode / WS dropout hook」grep verify 0 hit（FALSE）；屬 PA 設計 packet 時誤判 existing instrumentation 已 land；amend 修正 prerequisite 並建立 PA-DRIFT-4 follow-up。

**修法**：
- dispatch packet §5.1 Track D prerequisite 由「既有 hook」改為「**hook 不存在**（grep verify 0 hit）→ Wave 2 main.rs 接 `ApiLatencySourceProbe` trait 前必先在 bybit wrapper 層補 instrumentation（PA-DRIFT-4 follow-up）」
- dispatch packet §5.1 補注「emitter 端 IMPL trait 抽象已落不需等 instrumentation；Wave 2 Track D E1 IMPL 用 in-memory mock fixture 通過 AC-1a」
- dispatch packet §5.2 Track D scope #4 改為「**不接** bybit wrapper instrumentation（屬 Wave 2 main.rs 責任 PA-DRIFT-4）；emitter 只走 trait 抽象」
- dispatch packet §5.4 AC-1b real PG empirical 條款補「**stub probe value > 0 sanity check** 避免「永 OK band」假陽性 sign-off」
- dispatch packet §5.5 反模式新增 (c)「emitter 修 bybit_rest_client / bybit_private_ws instrumentation（屬 PA-DRIFT-4 Wave 2 main.rs 責任）」+ (d)「emitter 直接 import bybit client struct（trait 抽象 + Arc<dyn> 依賴注入）」
- dispatch packet §1.2 Sprint 1B mid 3 carry-over table 升級為 4 row（新增 PA-DRIFT-4）
- §1.2 PA-DRIFT-4 entry 含：file scope（bybit_rest_client.rs + bybit_private_ws.rs wrapper 層）+ 重疊判定（0 overlap with Wave 2 Track D scaffold scope）+ 時序依賴（Wave 2 main.rs 接 ApiLatencySourceProbe 前必 closed）+ blocking 範圍（blocks AC-1b real PG empirical，不阻 AC-1a scaffold sign-off）+ 工作分解（5 工作項 4-6 hr）
- M3 design spec §2.3.3 補「Sprint 2 Wave 2 main.rs 接線 carry-over」段 + 「probe stub 預設值 = 0」設計 + AC-1b sanity check 條款

### 1.4 Track F MEDIUM-1 — `position_count_active` threshold ladder spec literal land（Option A）

**決議**：採 Option A — 在 M3 spec §2.3 line 106 risk_envelope row literal 補 `position_count_active` 4 band 規範；對齊 E1 IMPL `classify_risk_envelope_position_count` 既有設計（OK 0-8 / WARN 9-16 / DEGRADED >16）；對齊 `risk_config.max_open_positions=16` 上限預期；避 Sprint 5 cascade hot-fix 時無 SSOT 認可的 baseline threshold。

**修法**：
- M3 design spec §2.3 line 106 risk_envelope row 全 4 band（OK / WARN / DEGRADED / CRITICAL）補 `position_count_active` literal（0-8 / 9-16 / >16 / 不含 CRITICAL）
- CRITICAL band 補註腳「position_count_active 不含 CRITICAL band；位數本身不致命，致命層由 cum_pnl / dd / concentration 反映；對齊 risk_config max_open_positions 16 上限」
- dispatch packet §7.4 AC-2 補 position_count_active 加入 OK→WARN→DEGRADED ladder fire test 範圍
- dispatch packet §7.4 新增 AC-2b「position_count_active ladder」明示 4 band literal + 引 M3 spec §2.3 line 106 reference + risk_config 對齊 + E1 IMPL doc comment 補引條款

## 2. Spec patches applied (file:line diff 摘要)

### 2.1 M3 design spec (`docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`)

| 位置 | 變更 |
|---|---|
| §2.3 line 104 api_latency row | 5 metric ladder → 8 metric ladder 全 4 band literal（rest_p50 / rest_p95 / rest_p99 / ws_rtt_p50 / ws_rtt_p99 / ret_4xx / ret_5xx / ws_dropout） |
| §2.3 line 106 risk_envelope row | OK/WARN/DEGRADED 補 `position_count_active 0-8 / 9-16 / > 16`；CRITICAL band 補不含 position_count_active 註腳 |
| §2.3.3 新節 | 「api_latency 8 metric 結構 — Track D Sprint 2 amend」段：8 metric × 4 band 表 + 5 條設計理由 + Wave 2 main.rs 接線 carry-over 段 + PA-DRIFT-4 follow-up reference + probe stub 預設值 = 0 設計 + AC-1b sanity check 條款 |

### 2.2 Sprint 2 design spec (`docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md`)

| 位置 | 變更 |
|---|---|
| §0 TL;DR | 加 4 amend bullet（Track D CRIT-1 + MED-1 + HIGH-3 + Track F MED-1） |
| §3.2 ApiLatencySample struct | 5 field → 8 field；補設計理由 5 條 + Wave 2 main.rs 接線 carry-over 註腳 |
| §5.0 新節 | 「OBSERVE-4 invariant」段：設計合約重申 + scaffold-level guard 必加位置 + IMPL code snippet + `tests/m3_emitter_replay_forbidden.rs` 必加 + rationale |
| §6.2 anomaly_id 命名表 api_latency row | 2 例 → 8 literal（per Sprint 2 spec §3.2 amend） |

### 2.3 Sprint 2 dispatch packet (`docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md`)

| 位置 | 變更 |
|---|---|
| §0 TL;DR | 加 amend bullet |
| §1.2 carry-over file scope conflict 表 | 3 row → 4 row（新增 PA-DRIFT-4 entry）+ PA-DRIFT-4 工作分解 5 工作項 |
| §1.7 Track A scaffold contract 表 | 7 row → 8 row（新增 OBSERVE-4 replay subprocess guard ~20 LOC）+ 升級總計 500→520 LOC + 後置「OBSERVE-4 replay subprocess guard 詳述」段 |
| §5.1 Track D prerequisite | 「既有 hook」改為「hook 不存在 → PA-DRIFT-4 follow-up」 |
| §5.2 Track D E1 prompt skeleton | scope #2 明示 8 field literal；scope #4 改為「不接 bybit wrapper instrumentation」；scope #6 明示 replay forbidden test 屬 Track A scaffold scope |
| §5.4 Track D AC sub-step | AC-1a 改為「8 metric tick → ≥ 40 row」literal；AC-1b 補 stub probe sanity check 條款；新增 AC-2b 8 anomaly_id 命名核驗 |
| §5.5 Track D 反模式 | 新增 (c) 不修 bybit wrapper instrumentation + (d) trait 抽象不直接 import bybit client |
| §7.4 Track F AC sub-step | AC-2 補 position_count_active 加入 ladder fire test；新增 AC-2b position_count_active 0-8/9-16/>16 ladder 條款 |

### 2.4 ADR-0042 — **不 amend**（governance authority 不變）

- ApiLatencySample 8 field 結構是 Sprint 2 IMPL detail（V106 schema 不變 / engine_mode CHECK 不變 / amplification cap 不變 / SM dwell 不變）
- OBSERVE-4 replay subprocess guard 屬 Sprint 2 spec line 199-216 OBSERVE-4 invariant 既存 SSOT 的 scaffold-level IMPL 落地（不改 governance scope）
- bybit_rest_client + bybit_private_ws instrumentation 屬 Wave 2 main.rs 接線細節（不改 ADR governance scope）
- position_count_active ladder 屬 M3 design spec §2.3 line 106 既有 metric 的 threshold literal 落地（risk_envelope domain 已在 ADR-0042 Decision 3 列入 6 domain set）

## 3. E1 round 2 unblock 條件 per finding

| Finding | E1 round 2 unblock 條件 | 工作量 |
|---|---|---|
| Track D CRIT-1 ApiLatency 5→8 field | E1 IMPL 已落 8 field（`api_latency.rs` line 103-120）對齊 spec amend；doc comment 引正確 M3 spec §2.3.3 reference；E2 round 2 比對通過 | 0 logic 改動 / doc comment 補 reference |
| Track D MED-1 OBSERVE-4 replay guard | **Track A scaffold round X**：新 `M3Error::ReplaySubprocessForbidden` variant + `HealthObservationWriter::write` 入口加 guard + `tests/m3_emitter_replay_forbidden.rs` 新 test + 通過 grep `engine_mode.*replay` 0 hit / 必走 guard | ~20 LOC + 1 new test 5-10 case ~1.5 hr |
| Track D HIGH-3 bybit prerequisite | E1 IMPL acknowledge prerequisite Wave 2 carry-over（不 IMPL 改）；trait 抽象 + Arc<dyn ApiLatencySourceProbe> 已對齊；in-memory mock fixture 通過 AC-1a | 0 IMPL 改動 / 只需 PA-DRIFT-4 follow-up 待 Wave 2 main.rs 接線階段 |
| Track F MED-1 position_count_active ladder | E1 IMPL ladder 數值已對齊 spec amend（OK 0-8 / WARN 9-16 / DEGRADED >16）；`classify_risk_envelope_position_count` 函數 doc comment 補引 `M3 design spec §2.3 line 106` literal reference | 0 logic 改動 / doc comment 補 reference 1-2 行 |

**E1 round 2 並行修**：Track A scaffold round X（OBSERVE-4 guard + test）獨立分支 ~1.5 hr；Track D round 2 doc comment 補 reference ~0.5 hr；Track F round 2 doc comment 補 reference ~0.5 hr；3 並行最大 sub-agent peak ≤ 4。

**E1 round 2 不阻**：4 amend 全 spec-dependent doc/comment 對齊；Track A scaffold OBSERVE-4 guard 是 6 Track 共用前置但 ~20 LOC + 1 test 屬 minor scaffold extension，不阻 Track D/F doc-only fix 並行。

## 4. ADR-0042 amend 觸發否

**不 amend**：

- ApiLatencySample 8 field 結構：屬 Sprint 2 IMPL detail（V106 schema 不變 / engine_mode CHECK 不變 / amplification cap 不變 / SM dwell 不變）；ADR-0042 governance authority 未觸碰
- OBSERVE-4 replay subprocess guard：屬 Sprint 2 spec line 199-216 既存 invariant 的 scaffold-level IMPL 落地；ADR governance scope 未變
- bybit_rest_client + bybit_private_ws instrumentation：屬 Wave 2 main.rs 接線細節；ADR-0040 multi-venue 對齊不變
- position_count_active threshold ladder：屬 M3 design spec §2.3 line 106 既有 risk_envelope domain 的 threshold literal 落地；ADR-0042 Decision 3 6 domain set 不變

ADR-0042 保持 v1.0；本 4 amend 全 spec § level patch + dispatch packet 對齊。

## 5. E2 round 2 re-review readiness

| 檢點 | 期望 | 對齊路徑 |
|---|---|---|
| `ApiLatencySample` field 數 | 8 field（rest_p50/p95/p99 / ws_rtt_p50/p99 / ret_4xx/5xx / ws_dropout） | E1 IMPL 已落（`api_latency.rs` line 103-120）；comment 引 Sprint 2 spec §3.2 + M3 spec §2.3.3 |
| api_latency 8 metric ladder | 4 含 CRITICAL（rest_p99 / ws_rtt_p99 / ret_5xx / ws_dropout）+ 4 不含 CRITICAL（rest_p50 / rest_p95 / ws_rtt_p50 / ret_4xx） | E1 IMPL 8 `classify_*` fn 已落（`api_latency.rs` line 241-412）；E2 review 比對 M3 spec §2.3.3 |
| api_latency 8 anomaly_id 命名 | `api_latency__<metric_name>` 8 條 literal | E1 IMPL `into_metric_rows` 已落 8 row；E2 review 比對 Sprint 2 spec §6.2 |
| ApiLatencyEmitter trait 抽象 | `ApiLatencySourceProbe` trait + Arc<dyn> 注入；不直接 import bybit client | E1 IMPL 已落（`api_latency.rs` line 418-470 trait + line 483-485 Arc<dyn> field）|
| OBSERVE-4 replay guard | `HealthObservationWriter::write` 入口 guard + `M3Error::ReplaySubprocessForbidden` variant + `tests/m3_emitter_replay_forbidden.rs` 新 test | **E1 round 2 待 IMPL**（Track A scaffold round X 工作） |
| position_count_active ladder | OK 0-8 / WARN 9-16 / DEGRADED >16 / 無 CRITICAL | E1 IMPL 已落（`risk_envelope.rs` line 292-300）；E2 review 比對 M3 spec §2.3 line 106 + doc comment 補 spec line 106 reference |
| spec literal 引用 | E1 round 2 IMPL doc comment 引 M3 spec §2.3.3 / §2.3 line 104 / §2.3 line 106 / Sprint 2 spec §3.2 / §5.0 reference | E1 round 2 doc comment 對齊 amend |

**E2 round 2 verdict 條件**：4 finding 全 PASS：
1. Track A scaffold OBSERVE-4 guard IMPL DONE + grep verify 0 unguard hit + new test PASS
2. Track D doc comment 引 M3 spec §2.3.3 + 8 metric × 4 band ladder 對齊
3. PA-DRIFT-4 carry-over acknowledge（不阻 AC-1a scaffold sign-off）
4. Track F doc comment 引 M3 spec §2.3 line 106 reference

E2 round 2 不需重做 cargo test / pytest（4 amend doc-edit + scaffold round X minor 補 guard；spec amend 已對齊 E1 IMPL 既有 8 field + ladder reality）。

## 6. 風險評級 + 16 根原則 + 硬邊界

- **風險評級**：**低**——純 doc edit（M3 design spec 2 row + 1 新 §2.3.3）+ 1 新 §5.0 段 + dispatch packet 3 段補；Track A scaffold OBSERVE-4 guard ~20 LOC + 1 new test ~1.5 hr 屬 minor scaffold extension；E1 IMPL 8 field 已對齊不需改 logic
- **副作用**：E1 round 2 doc comment 補 spec reference + Track A scaffold round X OBSERVE-4 guard land；Wave 2 main.rs 接線時走 PA-DRIFT-4 follow-up（4-6 hr E1 IMPL）；V106 schema 不受影響；spike Track B 已 land code 不受影響
- **16 根原則合規**（per `srv/docs/decisions/DOC-01_..._V2.md` §5.1-§5.16 + 16-root-principles-checklist skill）：
  - 原則 1（single write entry）：V106 writer 唯一入口 + OBSERVE-4 guard 強化 ✅
  - 原則 4（策略不繞風控；M3 emitter 不繞 Guardian）✅
  - 原則 5（生存 > 利潤；position_count_active 不含 CRITICAL，避免位數誤升 CRITICAL 觸過激 cascade）✅
  - 原則 6（失敗默認收縮；OBSERVE-4 guard fail-loud；replay subprocess emit 拒收）✅
  - 原則 8（audit reconstructable；evidence_json 寫 audit trail）✅
  - 原則 13（cost 感知；8 metric × 60s sample 不額外 hot path）✅
  - 原則 16（portfolio risk；position_count_active + corr + top1 + dd 4 portfolio metric 同時觀測）✅
- **DOC-08 §12 安全不變量 9 條**：無觸碰（M3 emitter 為觀測層；訂單寫入 / Lease acquire / pre-trade audit / authorization 路徑全未碰）
- **硬邊界 grep**：0 hit（grep `execution_authority|live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json` 3 amend file 0 結果）

## 7. 下一步

1. PM 收本 amend report → 確認 4 amend 路徑符合期望
2. PM 派 E1 round 2 並行修：
   - Track A scaffold round X（OBSERVE-4 guard + `M3Error::ReplaySubprocessForbidden` + `tests/m3_emitter_replay_forbidden.rs`）~1.5 hr
   - Track D round 2 doc comment 補 spec §2.3.3 reference + acknowledge PA-DRIFT-4 ~0.5 hr
   - Track F round 2 doc comment 補 spec §2.3 line 106 reference ~0.5 hr
3. E1 round 2 IMPL DONE 後派 E2 round 2 re-review × 3 並行（per §5 readiness 檢點）
4. 若 E2 round 2 PASS → Wave 2 Track D/E/F scaffold sign-off + Phase 3b E4 regression run + Phase 3c QA AC-1b real PG empirical（Wave 2+ main.rs 接 scheduler + PA-DRIFT-4 instrumentation land 後）
5. PA-DRIFT-4 follow-up（bybit_rest_client + bybit_private_ws instrumentation 4-6 hr E1 IMPL）排 Wave 2 main.rs 接線階段；不阻 Wave 2 scaffold sign-off

---

## Files touched

- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`（2 edit — §2.3 line 104 + line 106 ladder amend + §2.3.3 新節）
- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md`（4 edit — §0 TL;DR + §3.2 ApiLatencySample struct + §5.0 OBSERVE-4 新節 + §6.2 anomaly_id 表）
- `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md`（5 edit — §0 TL;DR + §1.2 carry-over 表 PA-DRIFT-4 + §1.7 scaffold contract OBSERVE-4 + §5.1/§5.2/§5.4/§5.5 Track D + §7.4 Track F AC-2/2b）

未觸碰：
- `srv/docs/adr/0042-m3-health-monitoring.md`（不 amend，governance authority 不變）
- `srv/rust/openclaw_engine/src/health/domains/api_latency.rs`（E1 IMPL 8 field 已對齊；E1 round 2 僅 doc comment 補 reference）
- `srv/rust/openclaw_engine/src/health/domains/risk_envelope.rs`（E1 IMPL ladder 已對齊；E1 round 2 僅 doc comment 補 reference）
- `srv/rust/openclaw_engine/src/health/mod.rs`（Track A scaffold round X 補 `M3Error::ReplaySubprocessForbidden` variant + `HealthObservationWriter::write` guard）
- `srv/rust/openclaw_engine/src/bybit_rest_client.rs` + `bybit_private_ws.rs`（PA-DRIFT-4 follow-up；Wave 2 main.rs 接線階段 4-6 hr E1 IMPL）
- `srv/sql/migrations/V106__health_observations.sql`（schema 不變）

## PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave2_track_def_spec_amend.md`
