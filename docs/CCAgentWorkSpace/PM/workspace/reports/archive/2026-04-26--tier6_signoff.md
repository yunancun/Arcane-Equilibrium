# PM Tier 6 Sign-off — Tier 5 §8 推薦 1-3 並行執行

**日期**：2026-04-26 CEST
**簽核人**：PM (Project Manager + Conductor)
**範圍**：Operator 接續 Tier 5 後說「@PM 接手 todo」（Tier 5 sign-off §8 推薦 3 件 next session ROI 排序：4 LOW quick wins 批次 + H3 schema A/B/C decision + dust restore audit design）
**狀態**：✅ **派發層面 100% 完成 + E2 batch review 3 task PASS / 0 退回（選項 B + 2 follow-up tickets）**

---

## § 1. 5 commits 完成記錄（git range `f4c5bad..e267b2d`）

| # | Commit | 任務 | Owner | E2 結論 |
|---|---|---|---|---|
| 1 | `306b549` | PA Track 2 G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN A/B/C decision (workspace report 511 + memory 18 = +529 / -0) | PA | ✅ PASS (4-axis SSOT 獨立驗證 0/7 schema mismatch + 0 hot-path consumer) |
| 2 | `dd4d64a` | PA Track 3 PAPER-STATE-DUST-RESTORE-AUDIT design (workspace report +442 / -0) | PA | ⚠️ PASS-with-LOW (T6.3-LOW-1: PA memory.md 索引未同步追加; PA push back MIT §6 #1 經 5-axis SSOT 100% 站得住腳) |
| 3 | `d8385e6` | E1 Track 1 4 LOW follow-ups (6 files +407 / -60) | E1 | ⚠️ PASS-with-LOW (T6.1-LOW-1: checks_derived 869 + ipc_client 899 進 §九 800 警告區漸增) |
| 4 | `56104de` | E1 memory append for Track 1 lessons (35 lines) | E1 | ✅ PASS (中英對照雙語 6 教訓條) |
| 5 | `e267b2d` | E2 batch review Tier 6 (8-axis audit + 4 commit verdict matrix + 2 pivot adversarial validation) | E2 | (review itself) |

## § 2. Test baseline（採集 2026-04-26 ~16:50 CEST）

- **Track 1 自驗證**：
  - 6 unit tests `test_ipc_client_update_risk_config_unit.py` Mac pytest **6/6 / 0.04s**（覆蓋 -1 / -1M / 0 boundary / positive forward / omitted no-inject / error-message contract）
  - 3 既有 `test_ipc_client_hmac_ts_unit.py` regressions PASS
  - `bash -n helper_scripts/cron_observer_cycle.sh` 0 exit
  - `pytest --collect-only -m "e2e or slow"` 1/36 collected, 0 warnings（從 `PytestUnknownMarkWarning` 完全消除）
  - [20] healthcheck env=0 path Mac smoke：`OPENCLAW_H_STATE_GATEWAY=unset (≠'1') — env=0 dormant by design; skip` ✅
- **Track 2/3 純 design**：0 production code touched，cargo + pytest baseline 不變
- **Linux ff-pull verified**：5 commits 全在 trade-core，0 merge conflict（`56104de` ff to Linux 8 files +442/-60 confirmed）

## § 3. Track 詳情

### Track 1 — E1 4 LOW follow-ups (commits `d8385e6` + `56104de`)

| Sub-task | 檔案 | 結論 | 備註 |
|---|---|---|---|
| G3-08-PHASE-1C-FUP-CHECK20-SYNC | `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` (+172/-60) | ✅ PASS | [20] expected value 升 v1 + h_states ⊇ {h1,h3}; set diff WARN 邏輯 Phase 3-4 friendly（additive 成長 = PASS） |
| EDGE-P1b-FUP-NEGATIVE-GUARD | `program_code/.../app/ipc_client.py` (+24) + `tests/test_ipc_client_update_risk_config_unit.py` (+194 NEW) | ✅ PASS | 6 unit tests 全綠 + 3 既有 regression 0；fail-fast in-process 不打 IPC roundtrip |
| TIER4-OBSERVER-LOW-1 | `helper_scripts/cron_observer_cycle.sh` (+17) | ✅ PASS | aggregate-exit log 保留 OBSERVER_RC + BRIDGE_RC 完整對；cron exit code 語意 byte-identical |
| G3-07-FUP-PYTEST-MARK | `tests/conftest.py` (+43) + `tests/test_layer2_tools.py` (+17) | ✅ PASS | `pytest_configure` 註冊 slow + e2e markers + `TestCheckDerivativesE2E` 加 e2e decorator |

**E1 兩個 sub-task pivot 經 E2 對抗驗證全 ACCEPT**：
- TIER4-OBSERVER pivot：「保留 BRIDGE_RC 在 final log」vs PA 提「BRIDGE_RC overshadow」— E2 確認 cron exit code 語意 byte-identical 保留，pivot 為 cosmetic 改善 postmortem readability ≠ 修不存在的 overshadow bug
- EDGE-P1b-FUP-NEGATIVE-GUARD pivot：「補首個 Python-side guard」vs PA 提「鏡射既有 7 guard」— E2 獨立 grep 確認 `ipc_client.py` L474 doc 自證 7 percentile 走 raw `self.call("update_risk_config", params=raw_dict)` NOT typed wrapper；calibrator producer-side clamping ≠ ipc_client guard；exit_stale_peak_ms 是 typed-wrapper 第一個 Python-side guard

### Track 2 — PA H3 schema A/B/C decision (commit `306b549`)

**Recommend Option B**（5/5 評分矩陣 vs A 1/5 / C 3/5）— Rust 端改 `H3RouteStats` 欄位對齊 Python keys。

| Option | 影響範圍 | 語意正確性 | Phase 3 affordability | Backward compat | 工時 |
|---|---|---|---|---|---|
| **B (推)** | Rust ~25 LOC（rename 7 fields + 加 3 fields） | ✅ Python = SSOT（model_router runtime authority）| ✅ Phase 3 接 real fetcher 直接 mirror Python，0 adapter | ✅ 0 production consumer broken（grep 確認 Rust H3RouteStats 0 hot-path consumer） | ~1.5h（Rust types + tests） |
| A | Python ~50+ LOC（含 StrategistAgent stats dict 改）| ❌ Rust types.rs 是 schema landing 後再對齊 | ⚠️ Phase 3 接 real fetcher 多 mapping layer | ❌ Python ecosystem 多處 break | ~3-4h |
| C | dual-vocab adapter | ⚠️ 永久維護兩套 vocab | ❌ Phase 3 接 real fetcher 兩套都要對 | ✅ 0 break | 永久 maintenance burden |

**Phase 3 dependency**：✅ unblock，Option B 完成後 Phase 3 H2+H4+H5 接 real fetcher 直接 mirror Python pattern。下次 session E1 ready-to-deploy（PA prompt template 已寫）。

### Track 3 — PA dust restore audit (commit `dd4d64a`)

**Recommend Option B**（status quo + healthcheck [19] paper_state_dust_inventory monitor only）— A/C 跨 env 都不安全。

**PA 揭發 MIT §6 follow-up #1 前提部分錯誤**（E2 5-axis SSOT 100% confirm）：
- `restore_from_db` **不重建倉位**（`fill_engine.rs:220-243` 確認只 SELECT 3 SCALAR counters）
- `paper_state_checkpoint` 表 schema 只 4 欄無倉位欄（`V018__paper_state_checkpoint.sql:30-39` 4 columns confirmed）
- STRKUSDT 0.1 dust 是 runtime partial close 殘留（`reduce_position` `fill_engine.rs:366-387` 留 `< 1e-12` threshold 不刪邏輯 confirmed）+ owner_strategy real-strategy 不進 SYNTHETIC_OWNER_LABELS retriage path（`owner_attribution.rs:112` confirmed）→ **與 restore 無關**
- EXIT-FEATURES-FIX A1 fast_track Gate 1 USD floor 已從消費端徹底防 spiral（`step_0_fast_track.rs:328-408` layered filter）— 不需再加生產端 evict

**Cross-env 安全性矩陣**：
| Option | paper | demo | live | 結論 |
|---|---|---|---|---|
| A 加 startup-time evict | ✅ | ✅ | ❌ FAIL（誤刪 user 真實小單 0.5 USD ATM 對沖 / scalper micro position）| Operator hard requirement reject |
| **B 維持現狀 + [19] monitor** | ✅ | ✅ | ✅ | PM accept |
| C EventConsumer bootstrap sweep | ⚠️ | ⚠️ | ❌ MEDIUM（real-strategy owner flip → DUST_FROZEN 卡 frozen） | reject |

**Healthcheck [19] one-liner SQL** ready-to-deploy（PA prompt template §7.4）：
```sql
SELECT COUNT(*) FILTER (WHERE realized_pnl=0) FROM trading.fills
WHERE strategy_name LIKE 'risk_close:fast_track%'
  AND ts > now() - interval '1 hour'
  AND engine_mode IN ('demo','live','live_demo')
```
- 0=PASS / 1-10=WARN / >10 OR distinct_dust_symbols≥3=FAIL
- 純 SELECT，0 mutation，fail-soft on PG unavail，跨 env 100% 安全
- TODO 條目改名建議：`PAPER-STATE-DUST-RESTORE-AUDIT` → `PAPER-STATE-DUST-INVENTORY-MONITOR`（spec 在 §7.4，E1 工時 ~1h healthcheck only）

## § 4. PM Sign-off

```
pm_approval:
  tier6_dispatch: ✅ COMPLETE (3 task: E1 quick wins + PA H3 schema + PA dust audit)
  tier6_e2_review: ✅ APPROVED (選項 B: 3 task PASS + 2 follow-up tickets)

  test_baseline:
    track1_pytest_unit: 6/0 (test_ipc_client_update_risk_config_unit.py)
    track1_pytest_regression: 3/0 (test_ipc_client_hmac_ts_unit.py)
    track1_bash_n_cron_observer: 0 exit
    track1_pytest_marker_collect: 0 warning (was PytestUnknownMarkWarning)
    track1_healthcheck_smoke_env0: PASS-skip (env=0 dormant by design)
    track2_track3: pure design (0 code touched, baseline unchanged)

  e2_review_results:
    t6_track1_4low: PASS-with-LOW (T6.1-LOW-1 §九 800 警告區 +52/+24, ACCEPT-with-FOLLOWUP)
    t6_track2_h3_schema: PASS (Option B 5/5 評分 + 4-axis SSOT 獨立驗證)
    t6_track3_dust_audit: PASS-with-LOW (T6.3-LOW-1 PA memory.md 索引未追加; push back MIT §6 #1 5-axis SSOT 100% 站得住腳)
    e2_recommendation: 選項 B (不退回, 2 follow-up tickets)

  pm_decision: ACCEPT 選項 B (對齊 Tier 3-5 慣例)

  pm_intervention_log: 1 (Track 1 sub-agent push 被 sandbox guardrail 擋, PM 補 commit E1 memory + push d8385e6 + 56104de + Linux ff-pull; Track 2/3 sub-agent 直 push 0 PM intervention)

  pivot_validations:
    track1_observer_pivot: ACCEPT (cron exit code byte-identical, 改善 postmortem readability)
    track1_negative_guard_pivot: ACCEPT (ipc_client L474 doc 自證 + 4-axis grep 驗證)
    track3_push_back_mit_section6_no1: ACCEPT (5-axis SSOT 100%; restore 不重建倉位 confirmed)

  follow_up_tickets_added: 2 (E2 推薦)
    LOW: T6-FUP-WARN-ZONE-FILES-SPLIT (1d, Wave 4 G5 refactor; checks_derived.py 869 + ipc_client.py 899 對齊既有 sibling pattern)
    LOW: T6-FUP-PA-MEMORY-INDEX-SYNC (10min, PA Track 3 dust audit memory 索引追加)

  ticket_renames: 1
    PAPER-STATE-DUST-RESTORE-AUDIT → PAPER-STATE-DUST-INVENTORY-MONITOR (per PA Track 3 §7.4 healthcheck [19] only spec, E1 ~1h)

  ticket_completed_marks: 6
    ✅ G3-08-PHASE-1C-FUP-CHECK20-SYNC (commit d8385e6)
    ✅ EDGE-P1b-FUP-NEGATIVE-GUARD (commit d8385e6)
    ✅ TIER4-OBSERVER-LOW-1 (commit d8385e6)
    ✅ G3-07-FUP-PYTEST-MARK (commit d8385e6)
    ✅ G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN (PA design 完成 commit 306b549; E1 impl 留 P1 backlog)
    ✅ PAPER-STATE-DUST-RESTORE-AUDIT → renamed PAPER-STATE-DUST-INVENTORY-MONITOR (PA design 完成 commit dd4d64a; E1 impl 留 P3 backlog)

  wave_progress:
    g3_08_phase_2_followups: 2/2 完成 (Phase 1C SYNC + H3 schema A/B/C decision)
    e2_review_followup_backlog_drain: 4/4 完成 (Tier 4-5 LOW backlog 全清)

  wave3_impact: 0 (passive observation 主軸不變)
  live_target: 2026-05-30 中位 ±7d (不變)

  pm_signature: PM (Project Manager + Conductor)
  pm_timestamp: 2026-04-26 16:55 CEST
```

## § 5. Backlog 新增（→ TODO.md，2 follow-up + 既有持續）

### 標完成（移自之前 backlog）

- **G3-08-PHASE-1C-FUP-CHECK20-SYNC**（LOW）→ ✅ commit `d8385e6`
- **EDGE-P1b-FUP-NEGATIVE-GUARD**（P3）→ ✅ commit `d8385e6`
- **TIER4-OBSERVER-LOW-1**（P3）→ ✅ commit `d8385e6`
- **G3-07-FUP-PYTEST-MARK**（LOW）→ ✅ commit `d8385e6`
- **G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN**（MED）→ ✅ PA design commit `306b549`，E1 impl 留 P1 backlog（~1.5h，per PA prompt template §7）
- **PAPER-STATE-DUST-RESTORE-AUDIT**（P2）→ ✅ PA design commit `dd4d64a`，rename `PAPER-STATE-DUST-INVENTORY-MONITOR`（P3，~1h healthcheck [19] only）

### 新增 follow-up（per E2 推薦選項 B）

1. **T6-FUP-WARN-ZONE-FILES-SPLIT**（🟢LOW，1d，Wave 4 G5 refactor wave）— `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` 869 行（817+52）+ `program_code/.../app/ipc_client.py` 899 行（875+24）兩檔對齊既有 sibling pattern split；對齊 Tier 5 T5.1-LOW-1 helpers.rs 1315 + Tier 3 G9-02-MED-1 ws_client.rs 1227 慣例
2. **T6-FUP-PA-MEMORY-INDEX-SYNC**（🟢LOW，10min）— PA Track 3 dust audit (`dd4d64a`) memory.md 索引條目未追加，PA 下次 audit 接手時補

### 既有 P1/P2 backlog 持續

- **G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN E1 impl**（P1，~1.5h，per PA prompt template）：Rust `H3RouteStats` rename 7 fields + 加 3 fields 對齊 Python；解阻 Phase 3 接 real fetcher
- **G3-08-PHASE-3-H2-H4-H5**（P1，~3.5d）：Phase 3 接 H2 budget + H4 validator + H5 cost_logging（per PA design §10.2 + §11.1）；解阻 G3-09 cost_edge_ratio (P3)
- **G3-08-PHASE-4-5AGENT**（P1，~4d）：Phase 4 5-Agent state events；解阻 G8-01 認知自適應 e2e
- **PAPER-STATE-DUST-INVENTORY-MONITOR**（P3，~1h）：healthcheck [19] paper_state_dust_inventory（per PA Track 3 §7.4 ready-to-deploy SQL）
- **MICRO-PROFIT-FIX-1-HEALTHCHECK**（P3，~1h）：MIT §6 follow-up #6 healthcheck `[21] fast_track_dust_spiral_guard`
- **G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE**（P2，1-2h）：`h_state_query_handler` 直接讀 H1/H3 私有 attribute → 改 PUBLIC facade method
- **EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT**（LOW，0.5d Wave 4 G5）：helpers.rs 1315 split sibling
- **ML-TRAINING-DATA-HYGIENE-1**（P2，1-2d）：歷史 EF noise 量化 + 補回填

## § 6. Wave 3 影響：**0**

所有 Tier 6 改動（pure design + LOW polish quick wins，0 業務邏輯修改）；不觸動 engine PID 2033577；passive observation 主軸不變：
- EDGE-P3 [11] 96%+ ETA ~04-27 滿 200 → ~04-30 連 3d PASS（不變）
- G2-02 雙軌驗證 ~05-01~05-03（不變）
- G2-01 PostOnly 1-2w 驗收 ~05-07/08（不變）
- EDGE-P1b per-strategy ≥200 rows ~05-10（不變）
- P0-3 邊評決策會 ~05-15（不變）
- **Live target ~2026-05-30 中位 ±7d（不變）**

Tier 6 為純 polish + design 性質，無 `--rebuild` 必要（Track 1 全 Python / shell hot-reload，cron 自然 pickup；Track 2/3 純 design，無 runtime impact）。

## § 7. 下一步（next session）

### 立即可派（按 ROI）

1. **G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN E1 impl**（P1，~1.5h，per PA prompt template `2026-04-26--g3_08_h3_schema_align_decision.md` §7）— Rust `H3RouteStats` rename + 加 fields 對齊 Python；解阻 Phase 3
2. **PAPER-STATE-DUST-INVENTORY-MONITOR**（P3，~1h，per PA Track 3 §7.4 healthcheck [19] SQL）— ready-to-deploy
3. **G3-08 Phase 3 H2+H4+H5 接入**（P1，~3.5d）— 解阻 G3-09 cost_edge_ratio + 開始 H state 完整覆蓋

### 並行 P2 wave 候選

4. **ML-TRAINING-DATA-HYGIENE-1**（MIT + E1，1-2d）— 歷史 EF noise 量化 + 補回填
5. **G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE**（P2，1-2h）— PUBLIC facade refactor

### LOW polish 候選

6. **MICRO-PROFIT-FIX-1-HEALTHCHECK**（P3，~1h）— [21] fast_track_dust_spiral_guard
7. **T6-FUP-WARN-ZONE-FILES-SPLIT**（LOW，1d Wave 4 G5）— checks_derived + ipc_client split
8. **T6-FUP-PA-MEMORY-INDEX-SYNC**（LOW，10min）— PA Track 3 memory 索引追加
9. **EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT**（LOW，0.5d Wave 4 G5）— helpers.rs 1315 split

---

**PM Sign-off DONE — Tier 6 派發層面 100% 完成 + E2 PASS (3 task / 0 退回) + 全 4 LOW backlog 清完 + 2 PA design ready-to-deploy** — 2026-04-26 16:55 CEST
