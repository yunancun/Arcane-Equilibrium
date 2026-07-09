# MIT Short Re-Review — AMD v0.3 + spec v1.2 + V094 spec

**Reviewer**: MIT (DB schema + ML pipeline + Data calibration auditor)
**Date**: 2026-05-15
**Subject**: AMD-2026-05-15-02 v0.3/v0.4 + spec v1.2/v1.3 + V094 hybrid schema migration spec short re-review (Wave 3a re-review consolidation)
**Mode**: Short focused re-review — verify Wave 1 + Wave 2a hybrid schema spec land 滿足 round-2 F-MIT-* must-fix + 增量 DB/ML risk 評估
**Method**: AMD v0.4 全文 + spec v1.3 §1-§4 + V094 spec §0-§3 (read) + PA Wave 1.5b consolidated report §1-§7 cross-reference + 過去 round-2 verdict 對照

> 註：MIT agent read-mostly；本檔由主會話按 MIT agent 返回原文存檔（governance trail completeness 補錄，內容已被 PA Wave 1.5b consolidated 報告 inline integrated 進 spec v1.3 + AMD v0.4）。

---

## §1 Review Scope（MIT round 2 must-fix 對照 v0.3/v0.4 + v1.2/v1.3 + V094 land 狀態）

| MIT round-2 finding | 原 must / should | v0.3/v0.4 land 機制 | 對照 V094 spec | 狀態 |
|---|---|---|---|---|
| F-MIT-1 JSONB vs new column trade-off | MUST HIGH | AMD §4.1 hybrid schema 明文 5 欄位分配（2 column + 3 JSONB key）；§7 #8 條 spec §4.4 hybrid mapping | V094 spec §1.2 hybrid 設計選項對照表 + §2.1/§2.2 schema changes | ✅ SATISFIED |
| F-MIT-2 healthcheck [62] sample-size + Wilson-CI | MUST HIGH | AMD §3 rollout footnote per-cell Wilson-CI（FA-SF-2 + spec §11 AC-14 Wilson-CI gate）；v1.3 AC-18 sub-clause 補 fallback rate Wilson-CI lower bound | V094 spec §2.1.2 healthcheck [62] sub-check Wilson-CI 對齊 spec §8.1 | ✅ SATISFIED |
| F-MIT-3 AC-6 NULL ladder 0.1%/1.0% | MUST MED | AMD §7 #8 CONDITIONAL + AC-16 NULL ladder（per Consensus-MF-3）；spec §11 AC-6 NULL ladder + healthcheck [63] dual gate | V094 spec §2.1.2 NULL ladder exclude safety path 3 enum（fast_escalate / not_attempted / engine_shutdown） | ✅ SATISFIED |
| F-MIT-4 Linux PG dry-run mandate | SHOULD | AMD §4.1 Linux PG dry-run × 2 round + sqlx checksum repair SOP（per V055/V083/V084 incident） | V094 spec §3 Guard A/B/C + Linux PG dry-run protocol（empirical + idempotent） | ✅ SATISFIED |
| F-MIT-5 V### number 指定 + naming | SHOULD | AMD §4.1 明指 V094 + file `V094__fills_close_maker_audit.sql`（mirror V083） | V094 spec §0 TL;DR + §2 schema changes 明文 V094 | ✅ SATISFIED |
| F-MIT-6 spec §4.3 bw_squeeze/pctb_revert min_samples_gate=30 升 normative | SHOULD | AMD §2.2 footnote CONDITIONAL with healthcheck min_samples_gate=30；spec §11 AC-4 per-strategy ≥10 + n<30 NEUTRAL | V094 spec §2.1.1 partial index 對 sparse strategy 自動稀疏化 | ✅ SATISFIED |
| F-MIT-7 close_maker_* non-training surface invariant | MUST MED | AMD §7 #7 PASS+強化 + E3 grep guard rule permanent；§9 Removed Path 顯式禁餵 ML training pipeline + spine + replay.simulated_fills | V094 spec §1.4 banned scope + §2 enum 不入 ML training | ✅ SATISFIED |
| F-MIT-8 replay.simulated_fills 不寫 close_maker_* | SHOULD P2 | AMD §9 Removed Path 顯式禁；E3 grep guard rule + non-training tier 對齊 §五 'synthetic_replay' 不可餵 ML | V094 spec §1.4 banned scope 列入 | ✅ SATISFIED |
| F-MIT-9 365d retention / 14d compression 不需動 | SHOULD informational | AMD §5.1 MIT-SF-4 footnote `trading.fills 365d retention + 14d after compress` audit 跨 Phase 充足 | V094 spec §1 不動 compression / retention policy | ✅ SATISFIED |

**結論**：MIT round-2 6 MUST + 4 SHOULD 全 9/9 SATISFIED；無 outstanding round-2 unresolved finding。

---

## §2 V094 hybrid schema spec verdict

V094 spec（1176 LOC / 15 sections）對齊 MIT round-2 F-MIT-1 hybrid schema 推薦完整度：

| Spec section | MIT 評估 |
|---|---|
| §1.2 Hybrid trade-off 表（全 column / 全 JSONB / hybrid） | ✅ JSONB GIN vs partial BTREE 100x perf gap 顯式量化；對齊 F-MIT-1 推薦 |
| §2.1 `close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE` + partial index `WHERE close_maker_attempt = TRUE` | ✅ partial index 高效 100x（per MIT F-MIT-1 verified）；hot-path filter 對 healthcheck [62] SLA |
| §2.1.2 enum allowlist 10 values（spec/AMD 8 + 補 2: rate_limit_backoff_per_symbol + fallback_to_taker_mandatory） | ✅ superset 對 AMD §4.1 enum 8 完整覆蓋；NOT VALID 對齊 V083 precedent；safety path 3 enum exclude NULL ladder（per F-MIT-3 階梯）；mirror V083 不掃 historical row |
| §2.2 JSONB key contract（3 keys append-only `close_*` prefix） | ✅ V003 details usage backward-compat 不衝突；既有 5 fa_phantom_1 contamination row 互斥 namespace |
| §3 Guard A/B/C templates | ✅ Guard A 驗 column exists / B 驗 data_type / C 驗 enum CHECK + partial index def 對齊 |
| §1.4 Banned scope（不入 ML training / 不寫 spine lineage / 不寫 replay.simulated_fills） | ✅ F-MIT-7 / F-MIT-8 / W-C Caveat 2 三線都 land |
| Empirical critical findings × 3（V003 details JSONB 存在 / 24h 98 fills 0% details rate / Linux runtime max V90 not V93） | ✅ 真實 Linux PG empirical verified；對齊 V055 5-round loop 教訓的 Mac mock 反模式 |

**整體 V094 spec 評級**：spec finalize 品質 = MIT round-2 F-MIT-1 推薦上 superset；無 schema 缺口；無 silent-noop / sqlx checksum drift 風險（per V055/V083/V084 incident precedent already addressed by §3.4 dry-run × 2 round + sqlx checksum repair SOP）。

---

## §3 AC-18 / AC-19 統計嚴謹性 advisory

### MIT-AC-18-CI-NOTE (P3, 重疊 QC-SF-6)

**Finding**：AC-18 fallback rate point estimate（PASS ≥ 95% / WARN 90-95% / FAIL < 90%）small-n window 統計檢驗不夠嚴謹；應加 Wilson-CI lower bound 防小樣本誤判（同樣是 binomial CI 邏輯，與 round-2 F-MIT-2 healthcheck [62] sample-size gate 同類型問題）。

**結論**：與 **QC-SF-6 重疊**，已被 QC-SF-6 cover（spec v1.3 §11.7 AC-18 sub-clause 補「per env 7d 樣本算 Wilson 95% CI lower vs 95%；CI lower < 90% → WARN；CI lower < 85% → FAIL（mirror AC-14 mechanism）」）。**無獨立 MIT patch**，避免雙 footnote drift（per FA-SF-2 SoT 不重述原則）。

### MIT-AC-19-Stratification-NOTE (P3 OPTIONAL deferred)

**Finding**：AC-19 close_maker_fill_rate 14d ≥ 30% threshold 全 per-strategy 統計 — 可能 dilute per-symbol pattern。例如 grid 在 BTCUSDT / ETHUSDT 高流動性 symbol fill rate 50%，但 1000PEPEUSDT / 1000BONKUSDT 等 small-tick / low-liquidity symbol fill rate 10%，aggregate 仍 PASS 30% 但 micro-tier 隱性 broken。建議 per-strategy + per-symbol 分層計算 healthcheck。

**結論**：**OPTIONAL deferred IMPL phase healthcheck**（不入 spec text，避免 over-spec）：IMPL 階段 healthcheck [62]/[65] SQL 自行加 stratification breakdown（per-strategy × per-symbol granularity），supplementary 報告 attached to PASS evidence，不作為 normative gate。對齊 PA Wave 1.5b 結論 + spec v1.3 §11.7 AC-19 不變。

---

## §4 ML pipeline / DB schema risk verify

**V094 對 ML training pipeline 影響**：
- 既有 6 個 details JSONB reader 全是 `trading.intents.details`（scanner json / source command filter），**非 fills.details**（per round-2 §5 ML pipeline 互動 grep evidence）
- `mlde_edge_training_rows` VIEW 不 JOIN `trading.fills`（per round-2 §6），V094 新欄位**自動不曝露**給此 view 消費者
- `label_generator.py` / `realized_edge_stats.py` / `mlde_demo_applier.py` / `parquet_etl.py` / `dl3_ab_runner.py` / `edge_label_backfill.py` 全 0 reference to fills.details（per round-2 §5）
- E3 grep guard rule 已 permanent（AMD §7 #7 invariant + §9 Removed Path）
- V094 IMPL kickoff 必含 `trading_writer.rs:430` upgrade（per AMD §10.1 v0.4 + Wave 1 Track A4 §4.4 + V094 spec §6），TradingMsg::Fill enum 21→24 + 13 caller sites enumeration，避免 5 audit 欄位中 3 個 JSONB key 100% NULL fail 風險

**Hypertable / chunk / compression risk**：
- V094 `ADD COLUMN` to hypertable 不會 lock chunks（PostgreSQL 11+ + TimescaleDB 2.x metadata-only operation）（per round-2 §2）
- 6 已壓縮 chunks 對新 column 預設 NULL，pre-IMPL row 對 healthcheck [63] 是 known-acceptable
- partial index build 對 13,991 row 表 < 1s
- 365d retention + 14d compression policy 不需為本 AMD 改（per F-MIT-9）

**Engine_mode filter**：V094 spec §2.1.1 + healthcheck [62]/[63] 必加 `engine_mode IN ('demo', 'live_demo', 'live')` filter（per CLAUDE.md §三 stable rule + memory `project_engine_mode_tag_live_demo`）。V094 spec § healthcheck integration 已對齊。

**V### Guard 完整性**：V094 spec §3 Guard A/B/C 模板完整 + idempotency mandate（per CLAUDE.md §七 + V055/V083/V084 incident precedent）+ Linux PG dry-run × 2 round + sqlx checksum repair SOP。**無 silent-noop / sqlx hash drift 風險**。

**Wave 3a v0.4 增量無新風險**：
- FA-#1 AC range 「AC-1..AC-16」→「AC-1..AC-19」純 cosmetic 對齊 spec v1.2/v1.3 AC 增量
- FA-#2 V094 backward-compat IMPL kickoff 必含項是 V094 spec §6 既有要求的 AMD-side trace
- FA-#3 negative whitelist 補 `risk_close:fast_track*` / `halt_session*` 對齊 spec §4.3 已列
- FA-#4 16 原則表 #3/#11/#13/#15 明列 PASS 是治理 trace 完整度提升（7/12 → 11/12），無 schema / writer / consumer / ML 影響

---

## §5 MIT verdict

**APPROVED** — 2 P3 advisory（MIT-AC-18-CI-NOTE 重疊 QC-SF-6 cover / MIT-AC-19-Stratification-NOTE OPTIONAL deferred IMPL phase healthcheck）；**無 BLOCKER**。

**核心結論**：
- AMD v0.4 + spec v1.3 + V094 spec 完整滿足 MIT round-2 6 MUST + 4 SHOULD（9/9 SATISFIED）
- V094 hybrid schema spec 對齊 F-MIT-1 推薦（2 hot column + 3 JSONB key）；enum allowlist 10 values superset；Linux PG dry-run × 2 round + sqlx checksum repair SOP 對齊 V055/V083/V084 incident precedent；Guard A/B/C 模板完整
- Non-training surface invariant（close_maker_* 禁餵 ML / 禁寫 spine / 禁寫 replay.simulated_fills）E3 grep guard permanent；既有 ML pipeline 0 fills.details dependency = silent leakage 風險封閉
- AC-18 / AC-19 統計嚴謹性 2 P3 advisory 都 deferred IMPL phase 處理（不阻 spec finalize）
- v0.4 純 cosmetic / numerical 增量無新 ML / DB / writer / consumer 風險

**對 IMPL Prereq 條件 2 status**：✅ **SATISFIED**（4-agent re-review 4/4 verdict + spec v1.3 / AMD v0.4 land + V094 spec finalize 對齊 F-MIT-1 全 satisfied）。

**對 IMPL Prereq 條件 5 status**：✅ **全 RESOLVED**（F-FA-1 V094 spec ✅ DONE Wave 2a Track A2 / F-FA-2 portfolio_var verify ✅ Wave 1 Track A3 / F-FA-3 W-C Caveat 2 guard tests ✅ Wave 1 Track A4）。

**IMPL 階段 MIT 監察項**（不阻 spec finalize；IMPL phase 自動進入監察）：
1. Healthcheck [62]/[65] SQL 加 per-strategy + per-symbol stratification breakdown（OPTIONAL per MIT-AC-19；supplementary report；不作 normative gate）
2. E3 grep guard rule 永久化 land verify：`grep -nrE '(linucb|scorer|quantile|mlde|dl3).*close_maker_(attempt|fallback_reason|initial_limit|final_fill|eligible_reason)' program_code/` 必 0 hit
3. V094 SQL Linux PG empirical dry-run × 2 round + sqlx checksum repair binary 跑通 evidence ID 必含於 E2 / E4 / A3 review

---

**Patch land 狀態（post-Wave 1.5b consolidation by PA）**：所有 MIT round-2 F-MIT-1..9 finding ✅ SATISFIED on v0.3/v0.4 + v1.2/v1.3 + V094 spec；2 P3 advisory 處理（QC-SF-6 cover MIT-AC-18 / IMPL phase healthcheck deferred MIT-AC-19）。本短 re-review 為 audit trail completeness 追補。
