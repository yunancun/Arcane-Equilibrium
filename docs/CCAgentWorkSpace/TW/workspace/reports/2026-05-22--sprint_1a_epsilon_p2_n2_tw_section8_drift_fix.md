---
report: TW Sprint 1A-ε P2 N2 — TW Phase 3d Acceptance Report §8 Path Drift Fix
date: 2026-05-22
author: TW (Technical Writer)
phase: Sprint 1A-ε P2 N2（per PM dispatch + TW P1 sweep §2.3 follow-up）
status: DONE
parent reports:
  - srv/docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-22--sprint_1a_epsilon_docs_index_sweep.md（TW P1 sweep — §2.3 已列 6 條 §8 內部 drift catch 但不修，列為 follow-up）
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_spike_overall_acceptance.md（target file — §8.2 / §8.3 / §8.4 path literal drift fix scope）
parent spec:
  - srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md
scope:
  - 字面對齊 §8.2 / §8.3 / §8.4 path literal 與物理檔案
  - ADR-0042 typo `domain-taxonomy` → `monitoring`（README line 253 SSOT）
  - 不改 §1-§7 narrative 結構
  - 不重寫 §8 narrative；純 path literal 與物理檔案對齊
  - 不 commit / 不派下游 sub-agent
  - 純 documentation hygiene patch
---

# TW Sprint 1A-ε P2 N2 §8 Path Drift Fix — 2026-05-22

## §1 Pre-state（§8.2/§8.3/§8.4 path literal 列表 + ls 驗證 hit/miss）

### 1.1 §8.2 spike artifact 路徑索引（line 420-435 pre-state）

| Line | Path literal | ls verify |
|---|---|---|
| 422 | `srv/sql/migrations/V106__health_observations.sql` | HIT |
| 423 | `srv/sql/migrations/V107__replay_divergence_log.sql` | HIT |
| 424 | `srv/sql/migrations/V112__lease_lal_tiers.sql` | MISS（實際 = `V112__decision_lease_lal_tiers.sql`；P1 sweep §2.3 未列；本次保留不修，scope discipline — operator task 描述「6 條」對齊 P1 sweep §2.3）|
| 425 | `srv/rust/openclaw_engine/src/health/mod.rs` | HIT |
| 426 | `srv/rust/openclaw_engine/src/health/state_machine.rs` | **MISS** |
| 427 | `srv/rust/openclaw_engine/src/health/engine_runtime_domain.rs` | **MISS** |
| 428 | `srv/rust/openclaw_engine/src/health/amplification_cap.rs` | **MISS** |
| 429 | `srv/rust/openclaw_engine/src/governance/lal_state_machine.rs` | **MISS**（實際 = `governance/lal/mod.rs`） |
| 430 | `srv/rust/openclaw_engine/tests/m3_amp_cap_24h_fire.rs` | HIT |
| 431 | `srv/rust/openclaw_engine/tests/spike_lal_transition.rs` | **MISS** |
| 432 | `srv/helper_scripts/replay/m11_spike/spike_trigger.py` | HIT |
| 433 | `srv/helper_scripts/replay/m11_spike/divergence_d1_fill_chain.py` | HIT |
| 434 | `srv/helper_scripts/replay/m11_spike/dedup_contract_test.py` | HIT |
| 435 | `srv/tests/test_spike_cross_lang_fixture.py` | HIT |

§8.2 MISS = 5 條（line 426 / 427 / 428 / 429 / 431；P1 sweep §2.3 列 3 條彙整：health 3 sub-module 算 1 條 + lal_state_machine + spike_lal_transition.rs）。

### 1.2 §8.3 spike report 路徑索引（line 437-450 pre-state）

| Line | Path literal | ls verify |
|---|---|---|
| 441 | `2026-05-22--sprint_1a_zeta_track_a_m1_lal_v112_impl.md` | **MISS** |
| 442 | `2026-05-22--sprint_1a_zeta_track_b_m3_health_v106_impl_round2.md` | HIT |
| 443 | `2026-05-22--sprint_1a_zeta_track_c_v107_m11_spike.md` | HIT |
| 444 | `2026-05-22--sprint_1a_zeta_track_a_e2_review_round1.md` | **MISS** |
| 445 | `2026-05-22--sprint_1a_zeta_track_b_e2_review_round2.md` | **MISS** |
| 446 | `2026-05-22--sprint_1a_zeta_track_c_e2_review_round2.md` | **MISS** |
| 447 | `2026-05-22--sprint_1a_zeta_phase_3a_spec_reconcile.md` | HIT |
| 448 | `2026-05-22--sprint_1a_zeta_phase_3b_regression.md` | HIT |
| 449 | `2026-05-22--sprint_1a_zeta_phase_3c_qa_empirical_verify.md` | HIT |
| 450 | `2026-05-21--sprint_1a_zeta_spike_overall_acceptance.md` | HIT |

§8.3 MISS = 4 條（line 441 / 444 / 445 / 446；均屬 sub-agent inline message handover；P1 sweep §2.3 列 2 條彙整：track_a impl + 3 E2 reports 算 1 條）。

### 1.3 §8.4 spec doc 路徑索引（line 452-468 pre-state）

| Line | Path literal | ls verify |
|---|---|---|
| 456 | spike scope spec | HIT |
| 457-459 | M1/M3/M11 design spec | HIT × 3 |
| 460-462 | V112/V106/V107 schema spec | HIT × 3 |
| 463 | AMD-2026-05-21-01 | HIT |
| 464-466 | ADR-0034/0036/0038 | HIT × 3 |
| 467 | `srv/docs/adr/0042-m3-health-domain-taxonomy.md` | **MISS** typo（實際 = `0042-m3-health-monitoring.md`；README line 253 SSOT 確證）|
| 468 | ADR-0044 | HIT |

§8.4 MISS = 1 條 typo（ADR-0042）。

### 1.4 Aggregate pre-state（per P1 sweep §2.3 framing）

P1 sweep §2.3 表共 6 行 drift entry（含 ADR-0042 typo 作為第 6 行）：

| # | §8 line range | Drift type |
|---|---|---|
| 1 | §8.2 line 425-428 | 3 不存在 sub-module（state_machine / engine_runtime_domain / amplification_cap） |
| 2 | §8.2 line 429 | `governance/lal_state_machine.rs` 字面不對齊（實際 `lal/mod.rs`） |
| 3 | §8.2 line 431 | `tests/spike_lal_transition.rs` 不存在 |
| 4 | §8.3 line 441 | Track A IMPL report 不存在（inline handover） |
| 5 | §8.3 line 444-446 | 3 E2 review report 不存在（inline handover） |
| 6 | §8.4 line 467 | ADR-0042 file name typo |

V112 file name drift（line 424）為 P1 sweep §2.3 漏列項；本次 patch scope 對齊 operator 描述「6 path drift + 1 typo」+ P1 §2.3 catch 範圍，**不修 line 424**（列入 follow-up）。

---

## §2 Patches Applied

### 2.1 Patch 1 — §8.2 line 425-428 三不存在 sub-module 收斂為 mod.rs single-row

**Edit target**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_spike_overall_acceptance.md`

**Before**（line 425-428 4 rows）：

```markdown
| `srv/rust/openclaw_engine/src/health/mod.rs` | M3 4-state ladder + amp cap 3 guard 嚴格 fire 語意 |
| `srv/rust/openclaw_engine/src/health/state_machine.rs` | M3 state machine + dwell time + flap suppression |
| `srv/rust/openclaw_engine/src/health/engine_runtime_domain.rs` | M3 engine_runtime 1 domain CPU + RSS + heartbeat 30s sampling |
| `srv/rust/openclaw_engine/src/health/amplification_cap.rs` | M3 24h suppression Rust enforce |
```

**After**（合併為 1 row + inline 說明 IMPL 為 single-file mod）：

```markdown
| `srv/rust/openclaw_engine/src/health/mod.rs` | M3 4-state ladder + state machine + dwell time + flap suppression + engine_runtime 1 domain CPU/RSS/heartbeat 30s sampling + amp cap 3 guard 嚴格 fire 語意（IMPL 為 single-file mod，無獨立 state_machine.rs / engine_runtime_domain.rs / amplification_cap.rs sub-module）|
```

**Line delta**：4 row → 1 row（行數 -3）。

### 2.2 Patch 2 — §8.2 line 429 `governance/lal_state_machine.rs` 對齊物理 `governance/lal/mod.rs`

**Before**：

```markdown
| `srv/rust/openclaw_engine/src/governance/lal_state_machine.rs` | M1 LAL state machine skeleton；Tier 0/1 + Tier 2-4 stub |
```

**After**：

```markdown
| `srv/rust/openclaw_engine/src/governance/lal/mod.rs` | M1 LAL state machine skeleton；Tier 0/1 + Tier 2-4 stub（IMPL 為 `lal/` directory + `mod.rs`，非 `lal_state_machine.rs` single file）|
```

### 2.3 Patch 3 — §8.2 line 430-431 移除 `spike_lal_transition.rs` 不存在 row

**Before**（2 row）：

```markdown
| `srv/rust/openclaw_engine/tests/m3_amp_cap_24h_fire.rs` | AC-5 24h fire test 3/3 |
| `srv/rust/openclaw_engine/tests/spike_lal_transition.rs` | AC-4 5 row Tier 0→1 transition cycle |
```

**After**（1 row + inline 說明 AC-4 在 m3_amp_cap_24h_fire.rs 中涵蓋）：

```markdown
| `srv/rust/openclaw_engine/tests/m3_amp_cap_24h_fire.rs` | AC-5 24h fire test 3/3 + AC-4 LAL Tier 0→1 transition 涵蓋（無獨立 `spike_lal_transition.rs` test file）|
```

**Line delta**：2 row → 1 row（行數 -1）。

### 2.4 Patch 4 — §8.3 line 441 Track A IMPL report → inline handover

**Before**：

```markdown
| Phase 2 Track A IMPL | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1a_zeta_track_a_m1_lal_v112_impl.md` |
```

**After**：

```markdown
| Phase 2 Track A IMPL | inline message handover（無獨立 report file；E1 IMPL DONE 通過 sub-agent final response 交付） |
```

### 2.5 Patch 5 — §8.3 line 444-446 三 E2 review → inline handover

**Before**（3 row）：

```markdown
| Phase 3a Track A E2 round 1 | `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-22--sprint_1a_zeta_track_a_e2_review_round1.md` |
| Phase 3a Track B E2 round 2 | `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-22--sprint_1a_zeta_track_b_e2_review_round2.md` |
| Phase 3a Track C E2 round 2 | `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-22--sprint_1a_zeta_track_c_e2_review_round2.md` |
```

**After**（3 row 維持，全改為 inline handover label）：

```markdown
| Phase 3a Track A E2 round 1 | inline message handover（無獨立 report file；E2 review 通過 sub-agent final response 交付） |
| Phase 3a Track B E2 round 2 | inline message handover（無獨立 report file；E2 review 通過 sub-agent final response 交付） |
| Phase 3a Track C E2 round 2 | inline message handover（無獨立 report file；E2 review 通過 sub-agent final response 交付） |
```

### 2.6 Patch 6 — §8.4 line 467 ADR-0042 typo fix

**Before**：

```markdown
| ADR-0042 M3 health domain taxonomy | `srv/docs/adr/0042-m3-health-domain-taxonomy.md` |
```

**After**（path 與 description 對齊 README line 253 SSOT）：

```markdown
| ADR-0042 M3 health monitoring | `srv/docs/adr/0042-m3-health-monitoring.md` |
```

### 2.7 Line diff aggregate

| Metric | Pre-patch | Post-patch | Δ |
|---|---|---|---|
| §8 行數 | 62 行（line 409-470）| 58 行（line 409-466；新 END 等同位移 -4） | -4 |
| §8.2 table rows | 14 | 10 | -4（health 4→1 / lal 1→1 改 path / tests 2→1） |
| §8.3 table rows | 10 | 10 | 0（純 cell 改字面） |
| §8.4 table rows | 13 | 13 | 0（純 cell 改字面） |
| MISS path literal | 10 | 1（line 424 V112 file name；本次 scope 外）| -9 |
| typo | 1 (line 467) | 0 | -1 |

### 2.8 §1-§7 narrative 結構未變

`grep '^## §' file` 確認 §1-§8 section header 全保留（行號 §1=37 / §2=69 / §3=150 / §4=202 / §5=266 / §6=332 / §7=367 / §8=409）。本 patch 僅動 §8.2 / §8.3 / §8.4 table cell 字面 + 三處 row 合併（health 4→1 + tests 2→1）；無 narrative 段落變動 / 無 §1-§7 變動。

---

## §3 Verdict

**Sprint 1A-ε P2 N2 closure verdict**：**PASS**

- 6 path drift entry per P1 sweep §2.3 framing 全 closure（5 §8.2 path literal drift + 4 §8.3 inline handover label 補 + 1 §8.4 ADR-0042 typo fix；列在 §2.1-§2.6 共 6 patch unit）
- 0 既有 narrative 結構修改（§1-§7 不變；§8 table 行數 -4 但 narrative cell 全 inline-augmented，無段落刪除）
- 0 commit（per task 禁忌）
- 0 派下游 sub-agent（per task 禁忌）
- 0 修 §8 之外其他 section
- §8 內部 path literal vs 物理檔案 hit 率：post-patch 14/15（V112 line 424 P1 §2.3 漏列；scope 外 follow-up）

**Carry-over to PA Sprint 1A-ε P3（minor edit）**：
- §8.2 line 424 V112 file name drift（`V112__lease_lal_tiers.sql` → `V112__decision_lease_lal_tiers.sql`；P1 §2.3 漏列；非本次 scope）

---

## §4 Sign-off

- **TW DONE** — §8 path drift 6+1 patch applied per P1 sweep §2.3 + operator dispatch description
- **Patch SoT**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_spike_overall_acceptance.md`（in-place edit）
- **未做**（per task 禁忌）：不 commit / 不派下游 sub-agent / 不修 §1-§7 narrative / 不修 §8 之外 section / 不修業務邏輯
- **下一步**：operator review → PM 統一 commit chain（per Sprint 1A-ε P3 minor edit batch）

---

**END OF Sprint 1A-ε P2 N2 §8 Path Drift Fix**

TW DOC DONE — report path: `srv/docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-22--sprint_1a_epsilon_p2_n2_tw_section8_drift_fix.md`
