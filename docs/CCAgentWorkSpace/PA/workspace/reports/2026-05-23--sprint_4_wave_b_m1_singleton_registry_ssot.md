---
report: Sprint 4+ Wave B MEDIUM-1 closure — Singleton Registry SSOT 建立 + 6 new singleton 登記
date: 2026-05-23
author: PA (Project Architect)
task: Singleton Registry SSOT location 拍板 + 6 singleton 完整登記欄位 + docs/README.md index + M-1 closure
parent reports:
  - docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pm_phase_3e_signoff.md §4.1 (Sprint 4+ Wave B 派發來源)
  - docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-22--sprint2_wave1_round2_track_b_re_review.md (Wave 1 Track B round 2 APPROVE)
  - docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_overall_acceptance.md (TW Phase 3d Acceptance)
status: PA-DONE; PM 收口時 commit
spec ref:
  - docs/architecture/singleton-registry.md (本 task 新建 SSOT)
  - docs/README.md §文档索引 (本 task index entry)
---

# PA Singleton Registry SSOT + 6 singleton 登記 — 2026-05-23

## §1 Pre-state grep verify（M-1 governance gap evidence）

### §1.1 Singleton Registry SSOT 0 hit confirm

```bash
grep -rn -i "singleton.*table\|singleton.*registry\|singleton.*authority" CLAUDE.md docs/architecture/ docs/adr/
```

結果（pre-task）：

- `CLAUDE.md` 命中 2 處：`line 165 §七` + `line 196 §九`，皆為「must be registered in the singleton table's current authority location before merge」rule line — 但 0 hint 指向具體 SSOT path。
- `docs/architecture/` + `docs/adr/` 0 hit。

### §1.2 既有 SSOT location 確認（archive snapshot）

```bash
grep -rn "Singleton 表" docs/archive/
```

結果：

- `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md:73` — `## §九 Singleton 表（trim 前完整 5 條長注釋版）`，含 4 條 Python singleton（`_H_STATE_INVALIDATOR` / `MARKET_SCANNER` / `HStateCacheSlot` / `CostEdgeAdvisorDbSlot`）+ 1 行說明 line 474「新增 singleton 必須在此表登記」。
- `docs/archive/2026-04-29--CLAUDE-pre-trim-snapshot.md:474` — 同樣 archive snapshot；archive 純被動快照不再是 active SSOT。

### §1.3 M-1 governance gap 結論

per `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` line 11 trim narrative：

> §九 Singleton 表後 5 條長注釋（H_STATE_INVALIDATOR / scanner_wiring / HStateCacheSlot / CostEdgeAdvisorDbSlot / Lg5ReviewConsumer 等）→ 收成單行

trim 實際操作 = **整段 table 刪除沒搬位**。CLAUDE.md 保留 §七 + §九 abstract rule line，但 SSOT location 0 hit。21 天 governance gap，到 Sprint 4+ Wave B E2 round 2 MEDIUM-1 escalate 才被 catch。

---

## §2 SSOT location 拍板

### §2.1 候選方案 3 個

| 方案 | 優點 | 缺點 | PA verdict |
|---|---|---|---|
| **A. `docs/architecture/singleton-registry.md` 新建** | 與 `docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md` 同類 ongoing inventory pattern；path 直觀；不違 CLAUDE.md trim 意圖 | 新文件，需 docs/README.md index 補 entry | **採納** |
| B. ADR-0046 governance-level ADR | governance authority 強；ADR 連續編號 | ADR 是 "architecture decision record" 單一決策；不適合作 dynamic 登記表（會違 ADR 用途） | 拒絕 |
| C. CLAUDE.md inline restore §九 table | rule line 0 變更 | 違 trim 設計目標（memory file 保持輕量 + 路由到 docs） | 拒絕 |

### §2.2 拍板：`docs/architecture/singleton-registry.md`

理由：

1. **格式對齊**：與既有 `docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md`（同類 ongoing inventory）pattern 一致
2. **trim 意圖保留**：CLAUDE.md §七 + §九 abstract rule line 不變；只透過 cross-ref（本 doc §4.1 + §4.2）連結具體 path
3. **path 可達性**：`docs/README.md` 補 index entry 後 grep 即達
4. **演進性**：本 task scope 為 Sprint 4+ Wave A/B 6 singleton；Sprint 5+ re-ingest archive 4 條 Python singleton 自然擴 §6.1 carry-over

### §2.3 SSOT 內容架構 7 章

per PA 本 task land `docs/architecture/singleton-registry.md`（344 行）：

- §1 Purpose（範圍邊界 in scope / out of scope + 登記欄位定義 11 fields）
- §2 Registered Singletons (active)
  - §2.1 Wave A — Bybit Instrumentation 4 singleton（RestLatencyHistogram + RetCodeCounter + WsRttHistogram + WsDropoutCounter）
  - §2.2 Wave B — Health Emitter Cache + Bus 2 singleton（PortfolioStateCache + HealthEventBus）
- §3 Registration Rules（§3.1 PA/E1/E2 登記前 + §3.2 E2 review 必檢 + §3.3 PA dispatch packet 必含 + §3.4 反模式 4 條）
- §4 Cross-reference with CLAUDE.md（§4.1 §七 link + §4.2 §九 link + §4.3 不修 CLAUDE.md inline rationale + §4.4 path 變更需提醒 4 處）
- §5 Lessons Learned 3 條（§5.1 CLAUDE.md trim 反模式 + §5.2 MEDIUM-1 應 dispatch packet 階段預判 + §5.3 半實裝陷阱誠實揭露的價值）
- §6 Carry-over to Sprint 5+ 4 條（§6.1 archive 4 Python singleton re-ingest + §6.2 dispatch packet 模板補預登記 section + §6.3 BybitPrivateWs supervisor signature 改造 + §6.4 PortfolioStateCache update task wire-up）
- §7 Maintenance 5 規則

---

## §3 6 Singleton 登記欄位完整 LOC + 表

### §3.1 Wave A — Bybit Instrumentation（4）

per Sprint 4+ Wave A commit chain `5acd36e6` + `4c84d1bb` IMPL；Wave B commit chain `245216d1` + `4d4ff99f` + `82351b61` 接線。

#### 3.1.1 RestLatencyHistogram

- type: `pub struct { samples: std::sync::Mutex<Vec<(Instant, u64)>> }`
- location: `rust/openclaw_engine/src/bybit_rest_client.rs:335-339`
- caller_chain: producer = REST hot path `request_with_retry()`；consumer = `RealApiLatencySourceProbe` Track D emitter probe；handle exposer = `BybitRestClient::latency_histogram_handle()` (line 989)
- health_monitoring: YES — `api_latency` domain V106 row `__rest_p50_ms` / `__rest_p95_ms` / `__rest_p99_ms`
- 完整 12 欄位登記 → `docs/architecture/singleton-registry.md` §2.1.1

#### 3.1.2 RetCodeCounter

- type: `pub struct { samples_4xx: std::sync::Mutex<Vec<Instant>>, samples_5xx: std::sync::Mutex<Vec<Instant>> }`
- location: `rust/openclaw_engine/src/bybit_rest_client.rs:479-484`
- caller_chain: producer = `BybitApiError::Business` retCode 對映 4xx/5xx；consumer = `RealApiLatencySourceProbe`；handle exposer = `ret_code_counter_handle()` (line 994)
- health_monitoring: YES — V106 row `__ret_4xx_count` / `__ret_5xx_count`
- 完整 12 欄位 → `docs/architecture/singleton-registry.md` §2.1.2

#### 3.1.3 WsRttHistogram（含半實裝陷阱揭露）

- type: `pub struct { samples: std::sync::Mutex<Vec<(Instant, u64)>> }`
- location: `rust/openclaw_engine/src/bybit_private_ws.rs:102-105`
- caller_chain: producer = `BybitPrivateWs::run()` main loop pong handler；handle exposer 已實裝（line 577-585）但 **main_health_emitters.rs Wave B placeholder 未接** — 走 `Arc::new(WsRttHistogram::new())` fresh 0-state（main_health_emitters.rs:219）
- health_monitoring: YES BUT placeholder disconnect — §2.1.3.a 誠實揭露 30 天 V106 「全 0」row 不代表真實 WS 健康
- 完整 → `docs/architecture/singleton-registry.md` §2.1.3 + §2.1.3.a

#### 3.1.4 WsDropoutCounter（含半實裝陷阱揭露）

- type: `pub struct { samples: std::sync::Mutex<Vec<Instant>> }`
- location: `rust/openclaw_engine/src/bybit_private_ws.rs:216-218`
- caller_chain: producer = `BybitPrivateWs::run()` 6 reconnect 入口；handle exposer 已實裝但 placeholder 同 §3.1.3 disconnect
- health_monitoring: YES BUT placeholder disconnect — §2.1.4.a 誠實揭露
- 完整 → `docs/architecture/singleton-registry.md` §2.1.4 + §2.1.4.a

### §3.2 Wave B — Health Emitter Cache + Bus（2）

#### 3.2.1 PortfolioStateCache

- type: `Arc<parking_lot::Mutex<PortfolioStateCache>>`；內部 `{ realized_pnl_history: VecDeque<(u64, f64)>, equity_history: VecDeque<(u64, f64)>, latest_exposures: Vec<PositionExposure>, last_update_ts_ms: u64 }`
- location: `rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs:129-141`
- caller_chain: producer = 300s tick `spawn_portfolio_state_update_task`（main_health_emitters.rs ~line 519，目前 placeholder no-op tick；Wave C / Sprint 5+ 接 PaperState SSOT）；consumer = `RealRiskEnvelopeSourceProbe` 5 calculator method（cum_pnl_24h_usd / max_dd_pct_24h / position_count_active / correlation_avg_pairwise / concentration_top1_pct）
- F-2 NaN/inf sanitize: PA-DRIFT-5 round 2 P1 fail-loud warn + skip push（line 201/217/235）
- 三 mode share vs 獨立: Wave B 採 engine-wide single cache（per main_health_emitters.rs:305-316）；Sprint 5+ PM 拍板
- 完整 → `docs/architecture/singleton-registry.md` §2.2.1 + §2.2.1.a + §2.2.1.b

#### 3.2.2 HealthEventBus

- type: `pub struct { sender: tokio::sync::broadcast::Sender<HealthStateChangeEvent> }`
- location: `rust/openclaw_engine/src/health/event_bus.rs:80-82`
- caller_chain: producer = M3 emitter 6 DomainEmitter `observe_classified` state transition fire publish；consumer = 本 round 0 production subscriber（Sprint 5 cascade IMPL 接 LAL Tier / Strategy halt / Alert router / GUI 4-8 subscriber）
- lock_primitive: `tokio::sync::broadcast::Sender` capacity 256（per `HEALTH_EVENT_CHANNEL_CAPACITY`）；fail-soft publish
- 完整 → `docs/architecture/singleton-registry.md` §2.2.2

### §3.3 6 singleton 完整登記欄位總覽

每 singleton 在 `docs/architecture/singleton-registry.md` §2.x.y 完整 12 欄位 markdown table：

1. name
2. type_signature
3. location (file:line)
4. owner_lifecycle (構造端 / 銷毀端)
5. cross_task_pattern (跨 task 訪問)
6. lock_primitive
7. visibility
8. caller_chain (producer + consumer + handle exposer)
9. health_monitoring (是否被 M3 emitter 觀測)
10. registered_date (2026-05-23)
11. governance_authority (ADR / spec / amend)
12. migration_plan (Sprint 5+ wire-up)

---

## §4 CLAUDE §七/§九 + docs/README.md 同步 update

### §4.1 CLAUDE.md 是否更新

**PA verdict：不更新 CLAUDE.md inline**。

per `docs/architecture/singleton-registry.md` §4.3 rationale 3 條：

1. CLAUDE.md trim 設計目標是「memory file 保持輕量 + 路由到 docs」；inline restore singleton 違 trim 意圖
2. 既有 §七 + §九 兩條 rule line literal 已含「current authority location」abstract 表述；不依賴具體 path
3. 替代 — `docs/README.md` index entry 增本 SSOT path（per docs governance R4 docs index sweep rule）= 路徑可達

未來 SSOT 搬位（不建議）需同步更新 path literal 處（per singleton-registry.md §4.4）：

- `docs/README.md` index entry
- `singleton-registry.md` §4.1 + §4.2 path literal
- `CLAUDE_CHANGELOG.md` 記錄變更
- 若 governance authority shift，補 ADR

### §4.2 docs/README.md index 補 entry

✅ DONE — `docs/README.md` line 162-166 新增 section `### 2026-05-23 Singleton Registry SSOT 建立（Sprint 4+ Wave B M-1 closure）`，含 1 行表格 entry 指向 `architecture/singleton-registry.md`。

verify：

```bash
grep -n "singleton-registry\|Singleton Registry SSOT" docs/README.md docs/architecture/singleton-registry.md
```

結果：

- `docs/architecture/singleton-registry.md:4` 確認 Status: Active
- `docs/architecture/singleton-registry.md:235` 確認 §4.1 abstract rule line cross-ref
- `docs/README.md:162` 確認 section header
- `docs/README.md:166` 確認 table entry

---

## §5 M-1 closure verdict + Wave C unblock 進度

### §5.1 M-1 closure verdict

**CLOSED** — per E2 Wave B round 2 MEDIUM-1 escalate (2026-05-23) 規定：

> 穩定登記表 SSOT 不存在 (grep 0 hit)，意味 singleton table SSOT 自身有 governance gap (Sprint 4+ 是 first land 場景)；M-1 升級給 PM 派 PA 在 commit chain 收口前建立 SSOT location + 登記 6 singleton

本 task 5 deliverable：

| Deliverable | Status |
|---|---|
| 1. SSOT location 拍板 | ✅ `docs/architecture/singleton-registry.md` (344 LOC) |
| 2. 6 singleton 完整 12 欄位登記 | ✅ singleton-registry.md §2.1.1 / §2.1.2 / §2.1.3 / §2.1.4 / §2.2.1 / §2.2.2 |
| 3. CLAUDE.md §七 + §九 cross-ref | ✅ singleton-registry.md §4.1 / §4.2（不修 CLAUDE.md inline） |
| 4. docs/README.md index entry | ✅ docs/README.md:162-166 |
| 5. PA registry report | ✅ 本 report |

### §5.2 Wave C unblock 進度

per Sprint 4+ Wave B PM Sign-off 9/9 子目標檢核（per Sprint 2 PM Phase 3e §4.1 item routing）：

| 子目標 | Wave B 狀態 |
|---|---|
| 1. main.rs scheduler 接線 | ✅ commit 245216d1（5/6 emitter spawn + PortfolioStateCache + emitter batch path + F-2 NaN sanitize）|
| 2. PA-DRIFT-4 bybit instrumentation | ✅ commit 5acd36e6 + 4c84d1bb（IMPL 6/6 finding closure；Wave A 4 singleton land）|
| 3. PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up | ✅ commit 5acd36e6 + 4c84d1bb（IMPL F-1/3 closure）|
| 4. E2 Wave B round 1 6 finding | ✅ commit 4d4ff99f（H-1 placeholder OK band + M-2 doc + L-1/2/3 closure）|
| 5. E4 regression | ✅ commit 82351b61（cargo 3961/0 + pytest 6042/28 + Wave A+B 42 integration + spike + nm 0 hit）|
| **6. MEDIUM-1 Singleton Registry SSOT 建立** | ✅ **本 PA task closure** |
| 7. AC-1b 30 min wait healthcheck | ⏳ pending（per W-S4-AC1B-HEALTHCHECK；QA + PM owner；Linux deploy 後 land） |
| 8. PM sign-off | ⏳ pending PM 收口（本 PA task 收口） |
| 9. TODO §0/§1 status update | ⏳ pending PM 收口時統一 update |

**Wave C unblock ready 條件：6/9 已 closed；7/8/9 屬 PM 收口 + Linux deploy 視窗，不阻 PA 本 task closure**。

### §5.3 Sprint 5+ 4 條 carry-over routing

per `docs/architecture/singleton-registry.md` §6：

| # | Item | Owner | Priority | Est |
|---|---|---|---|---|
| §6.1 | re-ingest archive 4 條 Python singleton（_H_STATE_INVALIDATOR / MARKET_SCANNER / HStateCacheSlot / CostEdgeAdvisorDbSlot）| TW + PA | P2 LOW | 1-2 hr |
| §6.2 | dispatch packet 模板補「新 singleton 預登記」section | PA | P2 | 30 min |
| §6.3 | BybitPrivateWs supervisor signature 改造（解 Wave B WS half placeholder 半實裝陷阱）| E1 + E2 | **P1**（unblocks 真實 WS health observability） | 4-6 hr E1 + 1 hr E2 |
| §6.4 | PortfolioStateCache update task wire-up（接 PaperState SSOT）| E1 + PA | **P1**（unblocks 真實 portfolio risk envelope V106 emit） | 4-6 hr E1 + 1 hr E2 + 0.5 hr PA spec amend |

§6.3 + §6.4 屬 P1（Sprint 5+ cascade IMPL 必前置）；§6.1 + §6.2 屬 P2 governance hygiene。

---

## §6 Lessons Learned（PA task 期間揭露）

### §6.1 CLAUDE.md trim 反模式（同 singleton-registry.md §5.1）

2026-05-02 trim 期間 §九 Singleton 表「收成單行」實際操作 = 整段 table 刪除沒搬位。CLAUDE.md 保留 abstract rule line 但 SSOT 0 hit。21 天 governance gap。

修法：trim 任何 inline reference table 時必同時：

1. 建新 SSOT location（或選既有 location）
2. CLAUDE.md rule line 不變或加 cross-ref
3. CHANGELOG 明記「table moved to X」
4. archive snapshot 必註「new SSOT location = X」（archive 純被動快照不夠）

### §6.2 MEDIUM-1 不應在 E2 round 1 後才被 catch

E2 Wave B round 1 catch MEDIUM-1「6 new singleton 未登記」合理；但根因「SSOT 0 hit」應在 dispatch packet 階段 PA 預判（per singleton-registry.md §3.3 規則）。Sprint 2 Wave 1+2 dispatch packet (2026-05-22) 未含「新 singleton 預登記」section，是 PA gap。

修法：本 SSOT 建立後 dispatch packet 模板必加「新 singleton 預登記」section（per singleton-registry.md §6.2 carry-over）。

### §6.3 半實裝陷阱誠實揭露的價值

Wave B PA-DRIFT-4 round 2 揭露 WsRttHistogram / WsDropoutCounter placeholder 半實裝（singleton-registry.md §2.1.3.a / §2.1.4.a）— 不掩飾「V106 全 0」是 placeholder 副作用，不是真實 WS 健康。誠實揭露對 Wave C / Sprint 5+ wire-up scope 拍板極關鍵；caller_chain 欄位必反映此狀態（per singleton-registry.md §3.4 反模式 2）。

### §6.4 PA spec amend 不改 Rust IMPL（本 task 守住 scope）

本 task PA scope 嚴守「不 IMPL Rust code / 不改既有 singleton 業務邏輯 / 不改 ADR-0042 / 不改 ADR-0040 / 不 commit / 不派下游 sub-agent / 中文為主 / 0 emoji」。新增 2 個 doc file（`docs/architecture/singleton-registry.md` + `docs/README.md` index entry）；0 code 改動。

### §6.5 Scope 控制 — Python archive 4 條 re-ingest 留 Sprint 5+

archive `_H_STATE_INVALIDATOR` / `MARKET_SCANNER` / `HStateCacheSlot` / `CostEdgeAdvisorDbSlot` 4 條 Python singleton 仍在 production 跑 — 真實 SSOT 應全 cover；但本 task scope 是 Wave A/B 6 新 singleton，re-ingest 屬 §6.1 carry-over（P2 LOW；Sprint 5+ cascade IMPL 期間 docs/ sweep 順手）。

不擴 scope rationale：本 task 30-45 min single-thread；擴到 10 singleton + 4 條 Python archive re-ingest 會打破預估 time-budget；且 4 條 Python re-ingest 需各別盤點當前 production state（grep 確認還活著 + 確認當前 owner / cross_task / lock）— 屬獨立 audit task。

---

## §7 Sign-off

- **PA verdict**：M-1 CLOSED；Singleton Registry SSOT 已建立於 `docs/architecture/singleton-registry.md`；Wave A 4 + Wave B 2 共 6 new mutable singleton 完整 12 欄位登記；CLAUDE.md §七 + §九 cross-ref 經 `docs/architecture/singleton-registry.md` §4.1/§4.2 完成；docs/README.md index 補 entry land
- **Wave C unblock**：6/9 子目標 closed；3/9（AC-1b healthcheck + PM sign-off + TODO update）pending PM 收口；不阻 PA task closure
- **Sprint 5+ carry-over routing**：4 條（§6.1 P2 + §6.2 P2 + §6.3 P1 + §6.4 P1）已 land `singleton-registry.md` §6
- **PM 收口路徑**：（1）confirm 本 SSOT location 拍板 OK（2）commit chain land 2 docs/ 改動（3）統一 update TODO.md §0/§1.1 Sprint 4+ Wave B M-1 closed（4）Wave C dispatch readiness gate verdict（per §5.2 7-9 進度）

---

## §8 File 改動清單

| File | 類型 | LOC | 改動 |
|---|---|---|---|
| `docs/architecture/singleton-registry.md` | 新建 | 344 | Singleton Registry SSOT 主檔（7 章節 + 6 singleton 12 欄位 + §3 4 規則 + §4 CLAUDE cross-ref + §5 3 lessons + §6 4 carry-over + §7 maintenance）|
| `docs/README.md` | edit | +5 | line 162-166 補 `### 2026-05-23 Singleton Registry SSOT 建立` section + 1 table entry |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_wave_b_m1_singleton_registry_ssot.md` | 新建 | 本 report | PA registry sign-off report |

---

## §9 Multi-session race check（per CLAUDE.md `Git And Sync`）

- 本 task 全程 read + write 新 doc + edit docs/README.md；0 改 Rust code / 0 改 ADR / 0 改 CLAUDE.md inline
- 不 commit（per PA scope «PM 收口»）
- 不派下游 sub-agent
- 不認識改動禁 revert — 本 task 期間 0 revert
- 提交時 PM 走 `git commit --only <files>` 對齊 meta-doc multi-session race protocol（per `feedback_git_commit_only_for_metadoc`）

---

**END OF PA Singleton Registry SSOT establishment report**
