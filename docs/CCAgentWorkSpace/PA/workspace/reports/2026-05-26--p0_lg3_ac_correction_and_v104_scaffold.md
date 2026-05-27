# P0-LG-3 AC Correction + V104 Spec Scaffold

**Date**: 2026-05-26
**Owner**: PA
**Trigger**: 2026-05-26 §1 4 P0 並行 Pass A verify 揭 TODO §1 行 48 P0-LG-3 AC 3 drift；operator dispatch PA spec patch + V### renumber + V104 scaffold + TODO reframe text。
**Status**: DESIGN DONE — DISPATCH READY POST-AMENDMENT（待 v56 P0 Layer B gate + MIT dry-run）

---

## §1 任務 deliverables

### 1.1 Spec v2 patch — `2026-05-11--lg_3_spec_v2_final.md`

- **行數變化**：1767 → 1851（+83 行，~2800 字）
- **patch 段落**：§2026-05-26 AMENDMENT（自第 1771 行起）
  - **A1**（line ~1775-1786）：V### 號漂移事實表 — V094 占用 + V099/V100 占用對照 + V104 新分派
  - **A2**（line ~1789-1798）：dispatch trigger condition refresh — 移除 funding_arb dep / fee_source claim / V099/V100 reference
  - **A3**（line ~1801-1810）：dispatch readiness checklist 對齊 V104（含 grep gate `V094\|V099`）
  - **A4**（line ~1813-1820）：ETA 預估 0 變化（~2026-05-29 派 / ~2026-06-10~12 closure / ~2026-06-22~30 supervised live activation）
  - **A5**（line ~1823-1834）：spec v2 章節 1-17 不動之保證（3-review APPROVE baseline 保留；V094 字眼 IMPL 階段 1:1 替換）
  - **A6**（line ~1837-1842）：配套交付物索引
- **核心保證**：spec v2 章節 1-17 內容**不動**；只動末尾 + V### 替換規則；3-review APPROVE baseline 100% 保留

### 1.2 V104 migration spec scaffold — `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md`

- **行數**：378 行
- **章節大綱**：
  - §0 Scope & Non-Scope
  - §1 V104 migration file identity（檔名 / migration 號 / sqlx checksum 治理對齊 P0 hash drift 教訓）
  - §2 Schema spec — 21 column allowlist 表 + 4 CHECK constraint + TimescaleDB hypertable policy（引 V107 樣板）
  - §3 Guard A/B/C — A 三段（prereq + 21-col check + forbidden column 反模式 per MIT MUST-5）/ B N/A（無 ALTER COLUMN TYPE）/ C（enum + hypertable + index 完整性）
  - §4 Linux PG empirical dry-run plan — 4 step + 9 query + 9/9 PASS sign-off gate
  - §5 sqlx checksum 治理（對齊 `project_2026_05_02_p0_sqlx_hash_drift`）
  - §6 Non-training surface invariant（E3 grep guard 規則對齊 spec v2 §4.4B）
  - §7 V094 字眼 replacement 規則（V094 → V104 + grep gate enforcement）
  - §8 Dependency & ordering（V054+V035 prereq + Wave 2.4.A T1+T4 並行）
  - §9 Risk assessment（中；TimescaleDB 既有樣板 100% 對齊）
  - §10 PA sign-off + next step
- **樣板對齊**：V086（enum + NOT VALID + backfill）/ V090（governance schema + verdict/outcome 雙層）/ V107（TimescaleDB hypertable + forbidden column 反模式 Guard A）

### 1.3 TODO §1 行 48 reframe text（提供主會話 copy-paste）

```
**AMENDED 2026-05-26**：spec v2 §4.1 / §4.2 / AC-T4-1~10 內所有 V094 字眼
IMPL 階段 1:1 替換為 V104（V099/V100 與 LG-3 無關 — V099 已被
autonomy_level_config 預留 + V100 已 land m4_hypothesis_base_table；§2.4A
"fee_source tick-time consumer" 全 docs grep 0 hit 為 wording drift 移除）；
新真實 dispatch precondition = (1) V104 audit migration spec scaffold ship
(2) v56 P0 Layer B 7d observation gate ~2026-05-29 啟動 + 24h
(3) MIT 走 V104 spec scaffold §4 4-step Linux PG empirical dry-run 9/9 PASS
(4) race-aware Option B dispatch 確認（T1+T4 並行 → B-F sequential）；§15 #1
LG-3 ↔ funding_arb 是 FALSE dependency 已 reframed 2026-05-26
```

字數：197 字（≤200 字限制達標）。

---

## §2 v56 P0 Layer B observation gate 真實 trigger date 估計

| 階段 | ETA | 來源 |
|---|---|---|
| v56 P0 spec ship | 2026-05-19 ~20:30 UTC | TODO §-1 |
| Phase 2-6（E1 Worktree A + A3/E2/E4 + Salvage + QA + Layer A 24h watch） | ~7d | `2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md` §4.1 |
| Phase 7-8（E1 Worktree B + A3/E2/E4/QA） | ~3-4d | `2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md` §4.1 |
| **Phase 9 Layer B deploy 啟動** | **~2026-05-29 UTC** | 2026-05-19 + ~10d |
| Layer B + 24h gate（LG-3 Wave 2.4.A 可派最早） | ~2026-05-30 UTC | per spec v2 amendment §A4 |
| Layer B + 7d observation 結束 | ~2026-06-05 UTC | per `2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md` §4.1 Phase 9 |

**真實滑動**：由 v56 P0 IMPL/review/QA 進度決定，PM 監看 `P0-ENGINE-HALTSESSION-STUCK-FIX` cycle status。當前 ~2026-05-26，距 ~2026-05-29 還有 3-4d。

---

## §3 Dispatch readiness verdict

### 3.1 Verdict

**READY POST-AMENDMENT — 待 2 外部 gate**

### 3.2 Internal gate（PA scope）✅ DONE

- ✅ V104 number 確認可用（Linux PG empirical 2026-05-27 confirmed: V104/V105/V108/V110/V111 free，V104 為 next continuous）
- ✅ Spec v2 patch land（1851 行，6 段 amendment）
- ✅ V104 spec scaffold ship（378 行，10 章節）
- ✅ TODO §1 行 48 reframe text 提供（197 字）
- ✅ §15 #1 funding_arb FALSE dep 已 reframed（2026-05-26 commit）

### 3.3 External gate（PM + v56 + MIT scope）⏳ PENDING

- ⏳ **External gate 1**：v56 P0 Layer B deploy + 24h（~2026-05-29 預估啟動 + 24h gate ~2026-05-30）
- ⏳ **External gate 2**：MIT 走 V104 spec §4 4-step Linux PG empirical dry-run → 9/9 PASS sign-off → 出 `MIT/workspace/reports/<DATE>--v104_lg3_supervised_live_audit_pg_dryrun.md`

### 3.4 不阻 dispatch 條件 / 額外 follow-up

- 主會話 apply TODO §1 行 48 reframe（PA report 提供 197 字 copy-paste 文）— 0 工時，apply 後 §1 表內 P0-LG-3 行 AC drift fully resolved
- TODO §15 #1 (已 reframed line 377) 可進一步刪行（funding_arb dependency 100% 失效 post-amendment）— optional cleanup，不阻

---

## §4 不擴 scope 之保證

本 amendment / spec scaffold **嚴格限定** LG-3 + V104。**不碰**：

- ❌ V099 autonomy_level_config 預留（屬 AMD-2026-05-21-01 v2 範疇）
- ❌ V108 / V110 / V111 free slot（保留他用）
- ❌ V100/V101/V102/V103/V106/V107/V109/V112 既 land 內容
- ❌ spec v2 章節 1-17 設計核心（3-review APPROVE 不重置）
- ❌ V104 SQL 全文（E1+MIT 領域；本 spec 只 scaffold）
- ❌ Rust audit_writer.rs / Python checks_supervised_live_audit.py / e3_grep_non_training_surface.sh IMPL（LG3-T4 sub-task）
- ❌ healthcheck [59]/[60]/[61] IMPL（spec v2 §10 各自負責）

---

## §5 16 root principles compliance

A 級 16/16；§1 / §3 / §4 / §6 / §8 / §11 directly relevant：

| # | 原則 | 對應點 |
|---|---|---|
| 1 | 單一寫入口 | V104 audit 表只由 `supervised_live_audit_writer.rs` 寫入；reconciler 只讀 |
| 3 | AI 輸出 ≠ 命令 | 7-state SM (REGISTERED→ACTIVE_PRE_AUTH→ACTIVE_AUTHED→ACTIVE_TRADING) 強化 AI→Lease→複核→執行 鏈條 |
| 4 | 策略不繞風控 | session_override `min`-only enforcement + risk_limits column NOT NULL DEFAULT '{}' |
| 6 | 失敗默認收縮 | reconcile_force_close + drawdown_breach + auth_recheck_fail → CLOSED |
| 8 | 交易可解釋 | V104 21-column 含 src_state / dst_state / reason_codes[] / payload JSONB → 完整可重建 |
| 11 | Agent 最大自主 | 7-state SM 不縮 P1 / P2 cap；EarnedTrust tier authority Gate 6 不破能力上限 |

無硬邊界觸碰；無 P0/P1/P2 風控降級；live_reserved / max_retries / system_mode / live_execution_allowed / OPENCLAW_ALLOW_MAINNET 0 變動。

---

PA P0-LG-3 AC CORRECTION + V104 SCAFFOLD DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-26--p0_lg3_ac_correction_and_v104_scaffold.md`

Co-deliverables:
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`（+83 行 amendment）
- `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md`（378 行新檔）
- PA memory.md 追加（spec drift + V104 scaffold + 教訓 4 條）
