# PA 報告 — ADR-0028 + ADR-0029 起草（FA P2-ENTRY-CLOSE-MAKER SPEC-1/EVID-1 結案）

Date: 2026-05-21
Role: PA (Project Architect)
Trigger: 主會話 PM dispatch via 2026-05-20 FA P2-ENTRY-CLOSE-MAKER analysis SPEC-1 + EVID-1 closure
Status: Drafted（不 commit；交主會話 PM review）

## Scope

起草 2 個 ADR：
1. **ADR-0028** — V094 `close_maker_fallback_reason` 3 dead variants safety reservation（FA SPEC-1）
2. **ADR-0029** — `market.public_trades` + `market.orderbook_l2_snapshot` storage policy proposal（FA EVID-1）

不 commit；交主會話 PM 主導 commit + 後續 MIT/BB/QC review 派發。

## Deliverables

| Artifact | Path | Status |
|---|---|---|
| ADR-0028 | `docs/adr/0028-close-maker-fallback-reason-dead-enum-reservation.md` | Accepted-pending-commit |
| ADR-0029 | `docs/adr/0029-market-trade-tape-and-orderbook-l2-storage-policy.md` | Proposed |
| PA memory log | `docs/CCAgentWorkSpace/PA/memory.md` (appended 2026-05-21 entry) | DONE |
| PA report | 本文件 | DONE |
| Operator mirror | `docs/CCAgentWorkSpace/Operator/2026-05-21--adr_0028_0029_close_maker_dead_enum_trade_tape_storage.md` | DONE（同檔案複製） |

## ADR-0028 核心要點

### Decision

保留 V094 全部 10 個 `close_maker_fallback_reason` enum 值；3 個 dead-by-observation variants（`fast_escalate_safety_upgrade` / `not_attempted_safety_path` / `engine_shutdown_safety`）正式紀錄為 **safety-path reservation**。

### 為什麼不 sunset

1. V094 CHECK constraint 已 hard-code 10 值；sunset 需新 migration + Rust enum 同步刪 + emit 路徑改動，是 breaking change
2. 三個 variants 在 `close_maker_fallback_decision()` 純決策狀態機中是 **live code path** 而非 dead code（`maker_rejection.rs:221-258`）；屬「設計上罕見/未觸發」非「沒接線」
3. 14d demo runtime 樣本量不足以做 statistical sunset judgement——應以 event frequency 推估而非 observation duration
4. `NotAttemptedSafetyPath` 是 `requires_market_fallback() == false` 的唯一反向 invariant slot；不可刪

### 配套治理規則

- Dashboard / healthcheck 對 3 個 reserved variants 不可觸發 alert（明確區分 dead-by-design vs missing-data-quality）
- Analytics 報告必須在 footnote 標 `[reserved — expected sparse]`
- `close_maker_fallback_decision()` unit test 覆蓋全 10 event→reason 映射為 E2 review 釘住的 baseline
- 90d cadence review（calendar trigger 2026-08-21）

### 與 FA SPEC-1 點名 3 dead variants 之外其他 6 個 0-row variants 的區別

FA 只點名 3 個 safety reservation；本 ADR 明確 scope：

| Variant | 14d 0 rows | 本 ADR 處理 | 性質 |
|---|---|---|---|
| `fast_escalate_safety_upgrade` | ✅ | ✅ | safety reservation — 待 ops emergency |
| `not_attempted_safety_path` | ✅ | ✅ | safety reservation — invariant 反向 slot |
| `engine_shutdown_safety` | ✅ | ✅ | safety reservation — shutdown audit slot |
| `postonly_reject` | ✅ | ❌ | runtime under-observation — 常規 race path |
| `cancel_grace_expired` | ✅ | ❌ | runtime under-observation — 常規 race path |
| `ack_lost` | ✅ | ❌ | runtime under-observation — unknown-reject 兜底 |
| `rate_limit_pause_global` | ✅ | ❌ | runtime under-observation — rate limit |
| `rate_limit_backoff_per_symbol` | ✅ | ❌ | runtime under-observation — rate limit |
| `fallback_to_taker_mandatory` | ✅ | ❌ | runtime under-observation — strategy-decided fallback |

6 個 runtime under-observation 不在本 ADR 範圍；需獨立評估（可能屬 calibration data quality 或 strategy 接線 audit）。

## ADR-0029 核心要點

### Decision

**Proposed**——立 2 個新 market 表 + WS 接線 + 治理 storage policy；但**不 finalize schema**。

### 為什麼是 Proposed 不是 Accepted

Schema 細節（sample rate / levels / retention / compression）需 MIT calibration 後才能定，否則 PA 越界 MIT calibration 工作。本 ADR lock 的是：

1. 設計意圖（為什麼要 trade tape + L2 snapshot）
2. 既有 V002 表的 fidelity gap 證據錨點（`phase_1b_sweep_replay.py:187-191`）
3. 治理基線（migration timing 不擾動 V094 14d freeze / storage hard cap / WS subscription gate / fail-closed writer）
4. 5 個明確的 Open Questions 留給 MIT / BB / QC

### 候選 schema（待 MIT cross-review）

```sql
-- public_trades (tick-level trade tape)
ts TIMESTAMPTZ + symbol TEXT + trade_id TEXT (PK 必含) + price REAL + qty REAL + side TEXT + is_block_trade BOOLEAN

-- orderbook_l2_snapshot (L2 snapshot)
ts TIMESTAMPTZ + symbol TEXT + bids REAL[] + asks REAL[] + levels SMALLINT + seq BIGINT + update_kind TEXT
```

PK 設計對齊 V095 lossy-pk 教訓（必含 trade_id / seq 避免 ms-collision 丟事件）。

### Sample rate options（MIT calibrate）

- **Track A trade tape**：T-1 full / T-2 threshold / T-3 symbol-tier；建議起點 T-2 或 T-3
- **Track B L2 snapshot**：L-1 tick / L-2 1s / L-3 5s / L-4 event-triggered；建議起點 L-2 + L-20 levels

### Storage budget hard cap

Daily insert ≤ PG 4-8GB shared_buffers 50%（per `project_hardware_constraints`）；超過需 partition + batch + compression 加固。

### 治理基線（lock）

1. Migration land 不擾動 V094 14d freeze
2. Storage budget hard cap 對齊 PG 限制
3. WS subscription enablement 對齊 ADR-0003 default-disabled pattern
4. 三引擎適用（paper/demo/live）
5. Writer fail-closed 不阻塞 trading thread（per ADR-0001）
6. Guard A/B/C migration 範式對齊 V094/V095（per `feedback_v_migration_pg_dry_run.md`）

### 5 個 Open Questions

- **OQ-1**: Sample rate（tick/1s/5s）— MIT + PA
- **OQ-2**: Bybit WS topic 接線 + quota — BB review
- **OQ-3**: 與既有 V002 表共存路由 — QC define
- **OQ-4**: Phase 1b calibration upgrade timing + dual-write 過渡 — MIT + QC
- **OQ-5**: V### migration 編號分配 + Guard 對齊 — PM + E1（dry-run mandatory）

## 16 根原則合規

兩個 ADR 都通過 §二 16 根原則合規確認（見 ADR 本體 §合規確認 表格）：

- ADR-0028：純治理 artifact；不觸 IntentProcessor；強化原則 4/5/8/9 audit 可解釋性
- ADR-0029：純 market data 層；不觸 trade 路徑；writer fail-closed 對齊原則 5/6/9；不依賴外部付費服務（原則 14）

## 副作用 / 風險清單

### ADR-0028

- **副作用**：增加 90d cadence governance 工作量；mitigation = 加 TODO calendar trigger 2026-08-21；review ≤30 min
- **退化風險**：未來 maker_rejection.rs 改架構可能誤刪 `EngineShutdownSafety` emit；mitigation = E2 review cross-check ADR-0028 + unit test 覆蓋全 10 event 映射

### ADR-0029

- **副作用**：MIT calibration 工作派發；BB Bybit WS quota review；QC dual-write 過渡規則
- **風險 1**：Storage 2-5x increase 觸 PG 限制；mitigation = §治理基線 storage budget hard cap + sample rate calibration matrix
- **風險 2**：WS subscription quota；mitigation = BB OQ-2 review + risk_config gate
- **風險 3**：Migration land timing 擾動 V094 freeze；mitigation = 等 freeze 結束（per FA 2026-05-20 estimate）
- **風險 4**：Hot insert path 阻塞 trading thread；mitigation = fail-closed writer + batch insert + ADR-0001 對齊

## Push Back（給主會話 PM）

1. **FA SPEC-1 範圍精確**：FA 只點名 3 個 dead variants 為 safety reservation；ADR-0028 嚴守此範圍，**不**處理其他 6 個 0-row variants（屬 runtime under-observation 性質不同）。如 PM 想擴展到 9 個 0-row variants，需獨立 review + 可能不同 verdict（如 `postonly_reject` / `cancel_grace_expired` 可能是 calibration data 不足而非 reserved）。

2. **ADR-0029 status = Proposed 是有意設計**：Schema 細節（sample rate / levels / retention）屬 MIT calibration 工作；PA 起草 ADR-0029 finalize schema 是越界。建議路徑：
   - PM 下 dispatch MIT calibration task → MIT 出 calibration report → PA 出 ADR-0029 補件或 ADR-0030/0031 拆分 → promote to Accepted
   - **不要** push PA 在無 MIT calibration data 下 finalize ADR-0029 schema

3. **V094 14d freeze 結束日期需 PM confirm**：ADR-0029 多處引用「freeze 結束後 land migration」；確切日期由 FA 2026-05-20 報告估算，需 PM 對齊 freeze calendar。

4. **建議下一步 dispatch 順序**：
   - **Step 1（PM 立即）**：commit ADR-0028 + ADR-0029（兩個 ADR 不互鎖；ADR-0028 立 Accepted、ADR-0029 立 Proposed）
   - **Step 2（PM 接續）**：dispatch MIT calibration task — public_trades + orderbook_l2_snapshot sample rate / storage budget
   - **Step 3（並行）**：dispatch BB Bybit WS quota + topic 接線 review
   - **Step 4（並行）**：dispatch QC review fidelity uplift 假設與 dual-write 過渡規則
   - **Step 5**：MIT/BB/QC review 完成後 PA 出 ADR-0029 promote 補件
   - **Step 6**：E1 IMPL（Linux PG dry-run mandatory per `feedback_v_migration_pg_dry_run.md`）

5. **與 EDGE-P2-3 promotion gate 的時序**：Phase 1b 14d freeze 結束 → ADR-0029 schema finalize → migration land + WS subscription enable → 14d 樣本累積 → Phase 1b replay rerun。整體 calendar ~4-6 週，需 PM 對齊到 active TODO。

## Cross-References

- ADR-0028 path: `srv/docs/adr/0028-close-maker-fallback-reason-dead-enum-reservation.md`
- ADR-0029 path: `srv/docs/adr/0029-market-trade-tape-and-orderbook-l2-storage-policy.md`
- V094 schema: `srv/sql/migrations/V094__fills_close_maker_audit.sql:144-153`
- Rust enum: `srv/rust/openclaw_engine/src/strategies/maker_rejection.rs:115-126`
- Phase 1b replay: `srv/helper_scripts/calibration/phase_1b_sweep_replay.py:187-191` + line 82-87 + line 347-350
- V002 既有 market 表: `srv/sql/migrations/V002__market_tables.sql`
- V095 lossy-pk 教訓: `srv/sql/migrations/V095__market_liquidations_identity.sql`
- Related ADRs: ADR-0001 / ADR-0003 / ADR-0010 / ADR-0021 / ADR-0023 / ADR-0026
- Related memory: `feedback_v_migration_pg_dry_run.md` / `project_hardware_constraints.md`

---

PA DESIGN DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--adr_0028_0029_close_maker_dead_enum_trade_tape_storage.md`
