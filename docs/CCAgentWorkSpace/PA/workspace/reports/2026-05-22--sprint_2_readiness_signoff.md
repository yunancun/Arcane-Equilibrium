# PA Sprint 2 readiness sign-off — 2026-05-22

**Author**: PA (Project Architect)
**Phase**: Sprint 2 pre-readiness Track 1（spec D1/D2/D3 整合 + Phase 1 refine + 6 Track dispatch packet）
**Parent spec**: `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md`
**Dispatch packet**: `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md`

---

## §1 Operator decisions integrated

per operator brief 2026-05-22 task dispatch，3 決策 D1/D2/D3 已整合於 parent spec：

### §1.1 D1 sysinfo crate adopted (a)

- **位置**：parent spec §3 D1（新增段）+ §9.3 NEEDS_OPERATOR table RESOLVED marker
- **內容**：
  - 採 (a) `sysinfo` crate（跨平台 + Mac 部署目標）
  - workspace `sysinfo = "0.32"` (latest stable as of 2026-05；Track A E1 IMPL 動工前 confirm crates.io 最新 stable)
  - 影響檔：`rust/Cargo.toml` (workspace deps) + `rust/openclaw_engine/Cargo.toml` (dep 引) + `rust/openclaw_engine/src/health/mod.rs` (sysinfo backed `EngineRuntimeSample` + 6 metric)

### §1.2 D2 並行 with Sprint 1B mid items (operator override)

- **位置**：parent spec §3 D2 + §4.1 cross-Sprint conflict matrix + §4.2 sub-agent ceiling 預警 + §4.3 wave 拆分執行順序
- **內容**：
  - operator override PA 原推 single-thread
  - Sprint 2 6 Track 與 Sprint 1B mid 3 NEW carry-over（PA-DRIFT-1/2 + E3-MED-2）並行運行
  - **Sub-agent ceiling 預警**：Phase 2 Wave 1 dispatch 階段為唯一 tight 階段（6 sub-agent peak；嚴守 stagger 5min dispatch + 不接受第 4 個並行請求）
  - Wave 1 (Track A + B + C) + Wave 2 (Track D + E + F) 各 3 並行

### §1.3 D3 Sprint 5 cascade reject log emit minimal IMPL 包含 (~2 hr E1 cost in Track A)

- **位置**：parent spec §3 D3 + §8.2 Track A 工時 4-6 hr → 6-8 hr
- **內容**：
  - Sprint 2 Track A 含 Sprint 5 cascade reject log emit minimal IMPL
  - 補 spike Track B E2 round 1 LOW-2 + Track B round 2 1 new LOW carry-over
  - V106 row INSERT with `evidence_json={"reject_reason": "amp_cap_>=2_fail_closed" | "amp_cap_same_anomaly_24h_suppress"}`
  - 不接 Slack / Console badge / halt strategy / 降 LAL Tier（Sprint 5/7/8 才接）

### §1.4 LOC diff in parent spec

- §0 TL;DR rewrite（5 並行 → 6 Track Wave 1+2；Phase chain estimate 12-18→2-3 hr Phase 1 + 30-45→38-52 hr Phase 2；readiness gate PENDING → OPEN with carry-over conditions；治理硬邊界補 D3 minimal reject log）
- §3 Decisions Finalized 新增（~50 行）
- §4 IMPL plan adjust 新增（§4.1 conflict matrix + §4.2 sub-agent ceiling + §4.3 wave 拆分 + cross-Track shared scaffold；~90 行）
- §8.1 Phase 1 12-18 hr → ~2-3 hr 縮版（更新）
- §8.2 Phase 2 5 Track → 6 Track + Wave 1/2 table + D3 +2hr（更新）
- §9.3 NEEDS_OPERATOR → RESOLVED 2026-05-22 verdict table（縮短）

**Total LOC diff**：parent spec +130-150 行（新增 §3 + §4）+ 既有 §0/§8.1/§8.2/§9.3 替換更新

---

## §2 Dispatch packet created

**Path**: `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md`（~370 行）

### §2.1 6 Track summary

| Track | Domain | Wave | 估時 | File scope |
|---|---|---|---|---|
| **Track A** | engine_runtime (沿用升級 + D3 cascade reject) | Wave 1 | 6-8 hr (含 D3 ~2 hr) | `rust/Cargo.toml` / `rust/openclaw_engine/Cargo.toml` / `health/mod.rs` / `health/metric_emitter/mod.rs`（新）/ `health/writer.rs`（新）/ `health/event_bus.rs`（新）/ `tests/sprint2_track_a_engine_runtime.rs`（新） |
| **Track B** | pipeline_throughput | Wave 1 | 6-8 hr | `health/domains/pipeline_throughput.rs`（新）/ `health/domains/mod.rs`（新）/ `tests/sprint2_track_b_pipeline_throughput.rs`（新） |
| **Track C** | database_pool | Wave 1 | 6-8 hr | `health/domains/database_pool.rs`（新）/ `tests/sprint2_track_c_database_pool.rs`（新） |
| **Track D** | api_latency | Wave 2 | 6-8 hr | `health/domains/api_latency.rs`（新）/ `tests/sprint2_track_d_api_latency.rs`（新） |
| **Track E** | strategy_quality (最高工時) | Wave 2 | 8-12 hr | `health/domains/strategy_quality.rs`（新）/ `tests/sprint2_track_e_strategy_quality.rs`（新） |
| **Track F** | risk_envelope | Wave 2 | 6-8 hr | `health/domains/risk_envelope.rs`（新）/ `tests/sprint2_track_f_risk_envelope.rs`（新） |

### §2.2 Wave 拆分

- **Wave 1** (D0-D3)：Track A + B + C 3 並行；Track A 24h 內 commit scaffold (trait + writer + event bus + observe_classified) 後 Track B/C 才能用
- **Wave 2** (D3-D6)：Track D + E + F 3 並行；用 Wave 1 已穩定 scaffold

### §2.3 Phase chain

| Phase | Item | 估時 |
|---|---|---|
| Phase 1 | 本 packet (PA single-thread) | ~2-3 hr DONE |
| Phase 2 Wave 1 | Track A + B + C 3 並行 | 18-24 hr 並行 (3 day wall-clock) |
| Phase 2 Wave 2 | Track D + E + F 3 並行 | 20-28 hr 並行 (3 day wall-clock) |
| Phase 3a Wave 1 E2 review | E2 × 3 並行 | 4-6 hr 並行 (1 day) |
| Phase 3a Wave 2 E2 review | E2 × 3 並行 | 4-6 hr 並行 (1 day) |
| Phase 3b | E4 regression single | 4-6 hr |
| Phase 3c | QA empirical single (需 E3-MED-2 closed) | 4-6 hr |
| Phase 3d | TW Acceptance | 2-3 hr |
| Phase 3e | PM sign-off | 1-2 hr |

**Total wall-clock**：1-1.5 week（D0-D10）
**Total 真實工時**：70-104 hr（含 buffer 75-115 hr）

---

## §3 Sprint 1B mid concurrent conflict check

per parent spec §4.1 conflict matrix + 本 packet §1.2：

### §3.1 File scope overlap 評估

| Sprint 1B mid item | File scope | Sprint 2 6 Track 重疊 | 結論 |
|---|---|---|---|
| **PA-DRIFT-1** governance.audit_log alignment | `docs/execution_plan/*` / `sql/migrations/V###` audit_log schema | Sprint 2 6 Track 不碰 `governance.audit_log`（emitter 寫 `learning.health_observations` only） | ✅ 0 file overlap |
| **PA-DRIFT-2** V103 file HARD BLOCKER | `sql/migrations/V103__*.sql`（V103 EXTEND outline → 真實 .sql 檔 land） | Sprint 2 6 Track 不碰 V103；新增 V### 走 V117+ reserved | ✅ 0 file overlap |
| **E3-MED-2** sandbox_admin hypertable OWNER | sandbox PG role GRANT + TimescaleDB hypertable owner 補位 | Sprint 2 6 Track Phase 3c QA empirical 需 sandbox_admin access | ⚠️ 時序依賴：Phase 3c 起跑前必確認 E3-MED-2 closed |

**結論**：0 file scope overlap；1 條時序依賴（E3-MED-2 必早於 Sprint 2 Phase 3c 收口；Phase 2 IMPL 階段不受影響）。

### §3.2 Cross-Track 評估

per Sprint 1A-ζ 範式 + 本 packet §1.7 scaffold contract：

- Wave 1 Track A 24h 內 land scaffold（trait + writer + event bus + observe_classified API + sysinfo）
- Wave 1 Track B/C dispatch packet 含「等 Track A scaffold commit SHA 才動工」hint
- Wave 1 內 stagger 5min dispatch（T+0/T+5/T+10）
- Wave 2 開派時 Wave 1 已 closure，無 trait re-design drift

### §3.3 Sub-agent ceiling 預警 (per parent spec §4.2)

| 階段 | Sprint 2 並行 | Sprint 1B mid 並行 | 主會話 PM | Peak total | 7 ceiling 餘量 |
|---|---|---|---|---|---|
| Phase 0 (本 packet land) | 0 | 3 (PA-DRIFT-1/2 + E3-MED-2 PM 派發) | PM | 4 | 3 ✅ |
| Phase 1 (本 packet review) | 0 | 3 (3 carry-over IMPL) | PM | 4 | 3 ✅ |
| **Phase 2 Wave 1** | **3** (Track A/B/C) | 0-3 (3 carry-over 收尾) | PM | **6-7** | **0-1 tight** |
| **Phase 2 Wave 2** | **3** (Track D/E/F) | 0 (3 carry-over DONE) | PM | **4** | 3 ✅ |
| Phase 3a Wave 1 E2 review | 3 | 0 | PM | 4 | 3 ✅ |
| Phase 3a Wave 2 E2 review | 3 | 0 | PM | 4 | 3 ✅ |
| Phase 3b/3c/3d/3e | 1 single each | 0 | PM | 2 | 5 ✅ |

**結論**：Phase 2 Wave 1 dispatch 階段為唯一 tight 階段（6-7 sub-agent peak）；嚴守 stagger 5min dispatch + 不接受第 4 個並行請求（PM hands-on）；其餘階段全 healthy 餘量。

### §3.4 E2 review ceiling 預警

per parent spec §8.3 Phase 3a：

- Phase 3a Wave 1 E2 × 3 並行 + Phase 3a Wave 2 E2 × 3 並行 = 共 6 E2 review (不同步；wave 間 sequential)
- 不撞 ceiling（每 wave 3 並行 + PM = 4 sub-agent）

---

## §4 Sprint 2 readiness gate

### §4.1 Gate verdict

**OPEN with carry-over conditions** ✅

**Rationale**：
- D1/D2/D3 operator-signed 2026-05-22 (parent spec §3 RESOLVED)
- Phase 1 PA refine deliverable land（本 packet + dispatch packet）
- Sprint 1B early IMPL 已 DONE (commit 9cf0fe82 per TODO §1.1) — 不阻 Sprint 2 dispatch
- 0 file scope overlap with Sprint 1B mid 3 carry-over (PA-DRIFT-1/2 + E3-MED-2)
- 1 條時序依賴（E3-MED-2 必早於 Phase 3c 收口；Phase 2 IMPL 階段不受影響）
- Sub-agent ceiling check：Phase 2 Wave 1 為唯一 tight 階段（6-7 sub-agent peak），其餘全 healthy

### §4.2 阻塞剩餘 (carry-over conditions)

| # | Item | Owner | Block 哪個 Phase | Severity | Status |
|---|---|---|---|---|---|
| 1 | E3-MED-2 sandbox_admin hypertable OWNER 補位 | E3 | Phase 3c QA empirical（不阻 Phase 2 IMPL） | MED | TODO §1.1 marked carry-over，Sprint 1B mid 派發中 |
| 2 | PA-DRIFT-1 governance.audit_log alignment | PA | 0 (不阻 Sprint 2 Phase 2/3) | LOW | TODO §1.1 marked carry-over |
| 3 | PA-DRIFT-2 V103 file HARD BLOCKER | E1 + PA | 0 (不阻 Sprint 2 Phase 2/3；阻 Sprint 4 first Live) | HIGH (對 Sprint 4) | TODO §1.1 marked carry-over |

**Severity**：
- 對 Sprint 2 Phase 2 IMPL：0 BLOCKER
- 對 Sprint 2 Phase 3c QA empirical：1 條時序依賴（E3-MED-2 必早 closed）
- 對 Sprint 4 first Live：1 條 HIGH（PA-DRIFT-2 V103 file；本 Sprint 2 不阻）

### §4.3 16 根原則合規確認

per parent spec §10 + 16-root-principles-checklist skill 的 16 根原則 + DOC-08 §12 9 條安全不變量：

- **16/16 原則合規** ✅（parent spec §10 已 land）
- **0 BLOCKER** ✅
- **0 硬邊界觸碰** ✅（emitter 不創新 order 寫入口 / 不寫 live state / 不繞 Decision Lease）
- **D3 cascade reject minimal IMPL 合規**：fail-closed default (V106 audit row only) + 不接 halt strategy / 降 LAL Tier（保 16 原則 #4 策略不繞風控 + #6 失敗默認收縮）

### §4.4 雙進程 / 三引擎合規

- Rust Engine 為 emitter SSOT（per parent spec §1.4 + §3.1）；Python 0 寫入
- 3E-ARCH paper/demo/live：Sprint 2 emitter 寫 paper + demo + live_demo (engine_mode tag)；不寫 live（Sprint 4 first Live 才接）
- L0 降級時 emitter 16 條原則全部仍成立（純 sysinfo 觀測，不依賴 AI）

---

## §5 Next action

### §5.1 PM action

1. **接收本 readiness sign-off**：approve Phase 1 PA refine 縮版（~2-3 hr）DONE，dispatch packet land
2. **Wave 1 dispatch**：
   - PM 派 Wave 1 Track A E1 (T+0min)
   - PM 派 Wave 1 Track B E1 (T+5min)
   - PM 派 Wave 1 Track C E1 (T+10min)
   - 嚴守 stagger 5min + 不接受第 4 個並行請求（per §3.3 sub-agent ceiling 預警）
3. **Wave 1 完成 + E2 review × 3 並行 PASS 後**：
   - PM 派 Wave 2 Track D E1 (T+0min)
   - PM 派 Wave 2 Track E E1 (T+5min)（最高工時 8-12 hr）
   - PM 派 Wave 2 Track F E1 (T+10min)
4. **Phase 3b/3c/3d/3e**：sequential single-thread；Phase 3c QA empirical 起跑前確認 E3-MED-2 closed

### §5.2 Operator action

- 接收 Sprint 2 readiness gate OPEN verdict
- 確認 Sprint 1B mid 3 carry-over（PA-DRIFT-1/2 + E3-MED-2）routing 與 Sprint 2 並行 OK
- Phase 3c 起跑前 sign-off E3-MED-2 closure

---

## §6 PA 簽收

- **PA 主會話 PA** 完成 Sprint 2 pre-readiness Track 1（spec D1/D2/D3 整合 + Phase 1 refine + 6 Track dispatch packet）
- **工時消耗**：~3 hr（spec 整合 ~1.5 hr + dispatch packet ~1.5 hr；對齊 operator 任務 brief 3-4 hr single-thread）
- **Verdict**：Sprint 2 readiness gate **OPEN with carry-over conditions**
- **下一步**：PM 拍 sign-off + 派 Wave 1 Track A/B/C 3 並行 (stagger 5min)

### §6.1 Spec section 編號 disambiguation note

parent spec 新增「§3 Decisions Finalized」+「§4 IMPL plan adjust」與既有 spec body「§3 Emitter trait design」+「§4 Sample / window / aggregation design」共用 §3/§4 編號，靠 heading 字串 disambiguate：

- `§3 Decisions Finalized (operator-signed 2026-05-22)` — operator decisions ledger（本 sign-off + dispatch packet 引「§3 D1/D2/D3」）
- `§3 Emitter trait design` — Sprint 2 spec body trait design
- `§4 IMPL plan adjust (per D2 並行 + D3 工時延伸)` — IMPL plan ledger（本 sign-off + dispatch packet 引「§4.1 conflict matrix」/「§4.2 sub-agent ceiling」/「§4.3 wave 拆分」）
- `§4 Sample / window / aggregation design` — Sprint 2 spec body sample aggregation

此 pattern 與 Sprint 1A-ζ spike scope spec §3/§4 既有 + 後續 sign-off chain 引用 §3/§4 共存模式一致；PM Phase 1 review 時 acknowledge。

---

**END PA Sprint 2 readiness sign-off — 2026-05-22**

**PA DESIGN DONE**: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_readiness_signoff.md`
