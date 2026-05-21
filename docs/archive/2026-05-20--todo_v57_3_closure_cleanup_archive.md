# TODO v57.3-zh → v57.4-zh 收口清理歸檔

**歸檔日期**：2026-05-20（UTC）
**動因**：進入 §-0 v57.2 雙軌制 v4.2 dispatch 前的 TODO 大規模清理；2026-05-20 一日內完成的 P0/P1/P2/P3 高密度 closure 已 verify，從 active 派工佇列搬到此 archive。

---

## §A v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 closure 收納

### A.1 Incident timeline

- **發生**：engine PID 1942669（2026-05-19 UTC 12:27:11 watchdog respawn）處理 2 次 FILUSDT halt_session emergency close 後（12:27:14 + 12:27:37）進入 **7h43m TRADING-INERT**（0 intents / 0 orders / 0 fills；WS alive、~1k ticks/sec、IPC alive；panel_aggregator channel_len=65+ backpressure）
- **救活**：operator `restart_all.sh --keep-auth` UTC 20:09:36 → 新 PID 2099215；首筆 fill 在 restart 後 1 分鐘；24 分鐘內 5 fills / 3 symbols 正常恢復
- **根因**：`paper_paused=true` sticky from Step 6 `RiskAction::HaltSession`（`step_6_risk_checks.rs:434-461`）**無 TTL auto-clear**；只 4 種 clearer：IPC Resume / Reset / SystemMode::ShadowOnly / restart default init
- **與 P1-WATCHDOG-STATUS2-RCA 不同根因**（先前只覆蓋 systemd cosmetic naming `sys.exit(2)`）
- **Watchdog 盲區**：無「alive but inert」偵測（只看 snapshot freshness；engine 每 30s 寫 status_report 不論是否交易）
- **Halt 觸發數學不通**：drawdown 10.2% vs TOML 25% threshold — trigger 根因仍 UNRESOLVED（log rotation 失了 UTC 12:27 那一行；可能 IPC patch / loading-order race / 第三條路徑）

### A.2 Operator 決議（2026-05-19 ~20:30 UTC）

- **Layer A**：TTL clear **只清 daily_loss**（rolling）；drawdown 維持 sticky（session safety-critical，operator-only resume）
- **Layer B**：Watchdog 業務 heartbeat probe **僅告警**（不自動 restart）

### A.3 修復鏈（~6h15m end-to-end）

```
PA spec v0.1 (1365 LOC)
  ↓
QC + MIT + FA 3 並行 review APPROVE-CONDITIONAL ×3（7 dedup MUST-FIX）
  ↓
PA spec v0.2
  ↓
[Layer A]
E1 Round 1 IMPL → E2 RETURN + E3 APPROVE-CONDITIONAL
  ↓
E1 Round 2 (6 fixes) → E2 R2 APPROVE + E4 PASS → QA APPROVE-CONDITIONAL
  ↓
operator commit/push/deploy commit `6cf476c4` UTC 22:59:36
  ↓
new engine PID 2099215 → 2182250
  ↓
🎉 real-event verify：drawdown halt 27.51% 啟動 9s 後觸發
  → forensic log + cron → governance_audit_log INSERT 2 rows
    (set + manual_cleared via ipc_resume)
  → operator GUI 平倉 + reset peak + Resume
  ↓
[Layer B]
E1 Round 1 IMPL 90/90 PASS → E2 RETURN（1 HIGH+1 MEDIUM+2 LOW+1 spec typo）+ E4 PASS
  ↓
E1 Round 2 (4 fixes) → E2 R2 APPROVE 40/0+118/0
  ↓
operator commit `fec63743` + `8ad70090` UTC 02:14
  ↓
watchdog process restart UTC 02:15:16 → 新 watchdog PID 2222237
  Inert probe enabled；inert_state.json tracking demo+live independent
```

### A.4 Files

**Layer A**：
- `rust/openclaw_engine/src/halt_audit.rs`
- V098 migration（governance_audit_log schema extension）
- `risk_config_*.toml ×3`（3 env：paper/demo/live）
- Python tail-writer `helper_scripts/canary/halt_audit_pg_writer.py` + cron wrapper

**Layer B**：
- `helper_scripts/canary/engine_watchdog.py` (+604 LOC)
- `watchdog_inert_probe.toml` 38 LOC
- 40 tests

### A.5 未來保護（per-env alarm window）

| env | inert_alarm_min | inert_alarm_critical_min |
|---|---|---|
| demo | 60min | 20min |
| live_demo | 30min | 15min |
| live | 15min | 10min |

+ operator-pause filter + transition-only write（95% I/O ↓）+ cron auto-INSERT

### A.6 Reports

- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19-20--*`（Layer A R1/R2 + Layer B R1/R2）
- `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19-20--*`（R1/R2）
- `docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-19--*`
- `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-19-20--*`
- `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-19--*`

### A.7 Halt trigger 根因仍開放

**P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1**（ticket spec §12.2）：drawdown 10.2% vs 25% threshold log 失證；forensic `halt_audit.log` 已 armed 用於下次自然事件 RCA。

### A.8 Commit chain

| commit | 描述 |
|---|---|
| `6cf476c4` | Layer A — daily_loss TTL + V098 migration + halt_audit forensic log |
| `fec63743` | Layer B — watchdog TRADING_INERT_PROLONGED business-heartbeat probe + R2 hardening |
| `8ad70090` | spec v0.3 §4.3 ts_ms→timestamp_ms typo + R2 changelog |
| `a9074611` | spec v0.2 — 3-agent review consolidated |
| `90d4df39` | TODO v56-zh → v57.3-zh — operator dual-track v4.2 RATIFY + v56 P0 CLOSED |

### A.9 Unblocks

§-0.C Sequencing 後續：
- PHASE-0-MIGRATION-DRIFT-RECONCILE
- V101/V102
- Track A LCS IMPL

---

## §B 2026-05-20 P3 + P1 source-only closure 收納

### B.1 `P3-SPINE-COUNTER-CACHE-ALIGN` ✅ DONE 2026-05-20

- **Scope**：E5 cosmetic；`channel.rs` 三個 static `AtomicU64`（drop / retry_success / retry_fail）改用 `#[repr(align(64))]` `CacheAlignedAtomic` wrapper（Deref→AtomicU64，callsite 不變）
- **Tests**：21/21 agent_spine unit tests pass
- **API**：無改動
- **狀態**：Mac source-only；待下次 Linux `--rebuild` 上線
- **Commit**：`879e3852`

### B.2 `P1-WATCHDOG-EXIT-CODE-CLARIFY` ✅ DONE 2026-05-20

- **改動**：`engine_watchdog.py` exit codes 重排
  - `--status` 0/1 保持（shell idiom）
  - lock contention 3 → **10**（startup/lock 區段 10-19）
  - rollback triggered 2 → **20**（runtime/rollback 區段 20-29）
- **影響檢查**：shell wrappers（`restart_all.sh` / `fresh_start.sh` / `clean_restart.sh`）僅用 `--status` 模式不受影響；無 systemd service file 引用舊 codes
- **Commit**：`dc33eb2d`
- **Sign-off**：`232c3aff`

---

## §C 2026-05-20 P2 sweep 6 項 closure 收納（同次 PM-conducted）

| ID | 任務 | 結果 | 報告 |
|---|---|---|---|
| `P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX` | TW 改 PM template §3.1（35→120 行）；用 V094 schema column 取代 ID prefix（attempt × fallback matrix）；給 grid + bb_breakout 雙範例 + 範圍鎖 spine lineage SOP | ✅ DONE | `docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-18--pm_24h_post_deploy_verification_audit_packet.md` §3.1 + QA/TW memory |
| `P2-STRUCT-2` | E5 inventory 25 項（H 0 / M 8 / L 17）；類 4 ADR-0015 sunset 殘留 = 0；S-Tier 2 項直接可清（governance_hub.py 4 RC-11 dead methods + risk_checks.rs DUAL-TRACK-EXIT-1 14 行 DEPRECATED comment）；3 處 push back（path 誤、V069 drop 數量、ADR-0015 scope） | ✅ DONE | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-20--zombie_code_inventory.md` |
| `P2-AUDIT-VERIFY-3` | E1 verify：V069 真實 drop **1 表**（`observability.scorer_predictions`），非 TODO 描述的 6 個；Python/Rust source grep **0 runtime writer + 0 runtime reader hits**；風險 LOW；5 條 ready-to-run SQL probe 已寫 | ✅ DONE | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--w_audit_4_v069_drop_verify.md` |
| `P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX` | FA evidence-based 分析：7 條改善建議（OBS-1/2/3 + SPEC-1/2 + EVID-1/2）+ 8 條 EVIDENCE-GAP + 5 條 OQ；16/16 root principles + 9/9 safety invariants PASS；operator 已對 5 OQ 決議全 A | ✅ ANALYSIS DONE（不動 runtime，Phase 1b 14d obs 中） | `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-20--entry_close_maker_real_fill_fix_analysis.md` |
| `P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS` | `rust/openclaw_engine/tests/stress_integration.rs` +92/-6；root cause = `EMPTY_ALPHA_SURFACE.oi_delta_panel=None` 命中 Phase 8a OI fail-closed gate（mod.rs:479）；修法 = `fresh_oi_surface` fixture + 7 切片 + control case；35/0 stress + 3042 lib + 3264 integration / 0 regression / 0 flaky | ✅ DONE（E1→E2 APPROVE→E4 PASS） | E1/E2/E4 reports `docs/CCAgentWorkSpace/*/workspace/reports/2026-05-20--p2_stress_bb_*` |
| `P2-SIM-QUEUE-AWARE-ADJUSTMENT` | 新 3 檔 + 改 3 檔；bias 從 +61.11pp 降至 -1.17pp（reduction 59.95pp，target ≤ 5pp PASS）；89/89 test PASS；R2 fix 加 `--sample-end-utc` pin + family-specific anchor disclaimer；honest finding：60pp gap 主由 `base_rejection` 非純 queue position，`base_rejection=0.70` family-specific anchor 不 hardcode | ✅ DONE（E1 R1→E2 APPROVE-COND→E4 PASS→E1 R2 fix→E2 R2 APPROVE） | E1×2/E2×2 reports `docs/CCAgentWorkSpace/*/workspace/reports/2026-05-20--p2_sim_queue_aware_*` + E4 cross-task regression |

**Commit chain**：`12dcdcbc` + `e2d213b5` + `a39dd11b`（reports + memory + PM template）+ `c3f25496`（TODO §12 closure summary）

---

## §D §-0 (LEGACY) v57.1 v4.1 RATIFY 全文歸檔

**狀態**：被 v4.2 (AMD-2026-05-20-03) supersede。本檔保留 audit trail；active planning authority 走 `srv/2026-05-20--dual-track-architecture-v4.2.md` + AMD-03。

### D.1 Operator 兩次 ratify

- 上午：v4 dual-track ratify（AMD-2026-05-20-01）
- 下午：reviewer parallel audit 提 5 條 critique；Claude 接受 5 條全 + push back 2 條；operator 批准 v4.1 修正包（AMD-2026-05-20-02）

### D.2 6 條原始批准（unchanged from v4）

1. Dual-Track 架構（Track A `direct_exploit` / Track B `asds_factory` / Track C `baseline`）
2. ADR-0025 Track-based attribution
3. ADR-0026 Direct Exploit bypass CPCV
4. V101/V102 Track schema migration
5. W8 fork criteria + W24 hard kill
6. Risk budget 切分：demo $10k = 40/50/10、live $1k = 70/10/0/20-reserve

### D.3 v4.1 reviewer corrections（5 接受 + 2 push-back）

**接受 reviewer 5 critique**：
1. Schema 對齊真實 DB（`trading.fills/intents/orders/position_snapshots + learning.lease_transitions/strategy_trial_ledger/cost_edge_advisor_log + agent.ai_invocations/decision_objects` — 取代虛構表名）
2. Phase 0 Migration Drift Reconcile（V096-V098 catch-up before V101 dispatch）
3. W8 milestone reframe：「demo evidence + live-ready proof」，live deploy 等 P0-LG/OPS clear
4. ADR-0026 tighten：event-study (Brown & Warner 1985) + pre-registration (OSF) + replay match ≥ 80% 三件套
5. Track A 順序 LCS-first（DB 已有 data 即可 replay）/ NLE shadow-collect 第二

**Claude push-back（接受）**：
A. Track B 不歸零（Tier 0/1 共享基建移到 Shared）→ capacity 改 50/10/40
B. GUI 漸進式（N+1 1 tab summary / N+2 +exploit tab / 後續 defer）

### D.4 governance artifacts（全部當日 land）

| Type | 文件 | Status（彼時） |
|---|---|---|
| AMD-01 | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-01-dual-track-architecture.md` | Accepted（§9 sprint banner + §3 schema + §5 kill ladder 被 AMD-02 supersede） |
| **AMD-02** | `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-02-v4.1-reviewer-corrections.md` | **Accepted（彼時 active planning authority；後被 AMD-03 supersede）** |
| ADR-0025 v2 | `docs/adr/0025-track-based-strategy-attribution.md` | Accepted-pending-commit（後 v3 rewrite） |
| ADR-0026 v2 | `docs/adr/0026-direct-exploit-bypass-cpcv.md` | Accepted-pending-commit（後 v3 rewrite） |
| V101/V102 spec v2 | `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md` | SPEC READY（彼時待 Phase 0 + v56 P0 完成；後 v3）|
| 規劃權威 v4.1 | `srv/2026-05-20--dual-track-architecture-v4.1.md` | 彼時 active；現轉 audit trail |

### D.5 Sequencing v4.1

```
v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle 收口   [現 ✅]
   ↓
PHASE-0-MIGRATION-DRIFT-RECONCILE（Linux DB head 對齊 repo V098）
   ↓
PA refresh dispatch plan（V### final + schema 欄位名 final 校對）
   ↓
V101 apply → 7d soak → V102 apply
   ↓
Track A LCS event-study + replay（per ADR-0026 v2）
+ Track A NLE listing watcher (shadow)
+ Track B Hypothesis Ledger CRUD
+ Shared: Tier 0/1 + GUI summary tab + Execution hardening
```

---

## §E §-1 v56 緊急狀態 incident 詳情歸檔

**狀態**：見 §A；本節保留 v57.3 TODO 內的 incident 描述（同 §A 部分內容；不再重複）。

P0 已於 2026-05-20 ~02:15 UTC CLOSED。

---

## §F §14 排程 stale 行歸檔

清除以下 stale 排程行（已通過或已完成）：

| 日期 | 工作 | 狀態（停更前） |
|---|---|---|
| 2026-05-10..16 | Sprint N+0 W1-W2 FOUNDATION HEAVY | Closed；細節歸檔於 v21 cleanup archive |
| 2026-05-16 | funding_arb 14d audit | verification/history；retirement 決議於 AMD-2026-05-09-02 / ADR-0018 |
| 2026-05-17..23 | Sprint N+1 ALPHA SURFACE PANEL WIRING | 8a C1 transport proof passed；8c source/test 修正 + V095 dry-run/MIT re-sign + Linux apply 完成；writer revival 完成；8b read-only Stage 0R query/report packet；Stage 1 Demo 限未來綠燈 Stage 0R 後 |

未來排程（2026-05-24+ Sprint N+2..N+5）保留在 active TODO §14。

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md` 將 active 派工佇列保持精煉；本歸檔不再回收進 active。
