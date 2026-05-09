# MIT 對抗性核實 v2 — 2026-05-09 v1 → v2 修復狀態

**Verification window**: 2026-05-09 16:30 UTC+2  
**Baseline**: v1 HEAD `455d796e` → v2 HEAD `1bd55689`（34 commits, 24h delta）  
**Engine**: PID 298034 active 15:50（leader 0.7h ago）· uvicorn 4 workers · binary built 14:02  
**SSOT**: Linux PG `trading_ai` (host TCP) 直查 + crontab 實測 + Rust binary deploy 驗證 + 引擎 BYPASS audit row 驗  
**對抗性原則**：commit message + Rust source ≠ runtime live；migration success=t ≠ writer 啟動；in-memory 模組 ≠ pipeline integration

---

## §1 Executive Summary

**ML 基座達標率**：v1 42% → **v2 44%**（淨進步 +2 pp，1 component 真升 1 階：lease_transitions BYPASS Foundation→Production）

| v1 5/12 grid 5×4 dimension | v2 實測 | Δ | 評語 |
|---|---|---|---|
| Production 5 | **6** | +1 | V078 lease_transitions BYPASS audit live（7955 row/24h） |
| Canary 4 | 4 | = | model_registry 仍 stale 16d（4/23 last_train） |
| Shadow 5 | 5 | = | replay simulated_fills 維持 5 calibrated_replay row（5/7 burst 後 2 day 0 new） |
| Skeleton 3 | 3 | = | cost_edge_advisor_log 仍 0 row（env OFF） |
| Foundation 4 | **3** | -1 | feature_baselines V072 contract guard + Rust writer source-only（CLI dry-run only），仍 0 row |
| Aspirational 4 | 4 | = | Teacher-Student / counterfactual_replay 仍 0 IMPL |

**24 dead schema 真實 IMPL 變化**（v2 commits 在 v1 表的更新）：

| Component | v1 | v2 | Δ |
|---|---|---|---|
| feature_baselines（drift chain）| 0 row, V072 contract guard only | **0 row**（Rust binary 編譯但**未自動執行**，default `--dry-run`，無 cron 排程） | ❌ 0 改變 |
| cost_edge_advisor_log | 0 row（env OFF）| **0 row**（env 仍 OFF） | ❌ 0 改變 |
| drift_events | 0 row | **0 row** | ❌ 0 改變 |
| scorer_predictions | DROPPED | **DROPPED** | ✅ 維持 |
| model_performance | 0 row | **0 row** | ❌ 0 改變 |
| **lease_transitions BYPASS** | n/a | **24h=7955 BYPASS row** | ✅ **新 IMPL 真生效** |
| simulated_fills calibrated | 5 row（5/7 burst） | **5 row（仍 5/7 burst, 2 day 0 new）** | ❌ 仍非 steady state |

**attribution_chain_ok 24h**：v1 0.0188% (44/234416) → **v2 0.5041% (65/12894)**（+0.486 pp）

| Period | ok_n | total | pct |
|---|---:|---:|---:|
| v1 24h | 44 | 234,416 | 0.0188% |
| v2 24h | **65** | **12,894** | **0.5041%** |
| v2 7d | 274 | 556,775 | 0.0492% |

**重大 anomaly**：24h total 從 234416 跌至 12894（-94.5%）— denominator 急縮使 ratio 看起來大幅改善，但 absolute attribution=true 只從 44→65（+47%）。**MIT 警告**：這是 view definition 改回 narrow 條件 OR mlde_edge_training_rows writer 嚴重減產（5/8 一天 266977 row → 5/9 部份 day 2917 row, total 12894 24h）。**ratio 改善 ≠ 真改善**；建議 RCA。

**MIT VERDICT v2**：v2 commits 中**1 真 runtime IMPL（V078 BYPASS audit）/ 4 source-only / 3 接線無實質 runtime 影響 / 多項 missing**。

---

## §2 v2 Commits 真實 IMPL 逐條核實

### 2.1 v2 5 大 commits 對抗性核實

| Commit | 聲稱 | 實際 IMPL | Runtime impact | Verdict |
|---|---|---|---|---|
| `7657bd25 ml: add 34-dim feature baseline writer` | 34-dim feature baseline writer | **Rust CLI binary**（`feature_baseline_writer`）+ `drift_detector.rs` rebuild API；default `--dry-run`，需手動 `--apply --i-understand-this-modifies-db` | **0 runtime impact**（binary built 14:02, **never invoked --apply**, feature_baselines 仍 0 row, **無 cron 排程**） | ❌ **誤導**：「writer」字眼暗示 daemon/cron writer，實為 manual CLI tool |
| `a904e273 docs: mark fup2 cron verified` | FUP-2 cron verified | crontab 實測 `*/30 * * * * edge_label_backfill_cron.sh` ✅ installed；docs only | ✅ **truthful**（docs 標記真實狀態） | ✅ truthful |
| `cc6476dd learning: add portfolio tail risk gate` | portfolio VaR/CVaR/EVT/GPD + promotion_pipeline integration | `portfolio_var.py` 312 LOC + `cvar.py` 295 LOC + `promotion_pipeline.py` `update_demo_portfolio_tail_risk_evidence()` integration | **0 runtime impact**（PromotionPipeline class **無外部 caller** — 只有 pipeline 本身的 method、test 文件 import；無 route handler / agent / scheduler 呼叫；in-memory `_entries: dict` 從未被 populated） | ❌ **誤導**：「portfolio tail risk gate」聽起來像 active gate，實為 dormant code，無 promotion flow 真經過 |
| `716eb3d6 learning: enforce selection bias promotion gate` | selection bias DSR/PBO promotion gate | `promotion_gate.py` 141 LOC + `promotion_pipeline.py` `update_demo_selection_bias_evidence()` integration | **0 runtime impact**（同上：PromotionPipeline 無外部 caller） | ❌ **誤導**：「enforce」字眼暗示 fail-closed 阻擋 promotion，實為 dormant code |
| `48401727 docs: record blocker runtime closure` | 3 blocker runtime closure | docs only：(1) signed LiveDemo auth restored, (2) lease-bypass audit live, (3) operator decision audit closed | ✅ **truthful**（live_demo pipeline 確 active，BYPASS row 確真寫） | ✅ truthful |

### 2.2 v2 全部 34 commits 分類

| 類型 | count | 範例 |
|---|---:|---|
| **真 runtime IMPL** | 3 | V078 BYPASS audit (e97a333b) / API tailnet bind (c187fd99) / context_distiller wired (35f81a7b) |
| **Source-only / dormant code** | 12 | feature_baseline_writer (7657bd25) / promotion gate (716eb3d6, cc6476dd) / live cookie security (cfadc339) |
| **docs / closure record** | 11 | 48401727 / 1bd55689 / 8226a67f / 8dcc1f17 |
| **Strategy / risk config** | 5 | bb_breakout 5m (6d3ea046) / fast_track thresholds (8df29e9e) / kelly tier (45f1139f) / per-trade risk sizing (d65bf617) / strategist cap (a0bbde58) |
| **Test/coverage only** | 3 | rust replay runner test split (477b5cc0) / launchd bind hardening (b658e18c) / shadow provider fail-closed (caf973fb) |

**對抗性 push back**：v2 commits 中**3/34 (8.8%) 真有 runtime 影響**；**24/34 (70.6%) source-only/docs/test**；**5 strategy config 改動需 next deploy 才生效**（風控配置 reload 走 RiskConfig hot-reload，部分要 engine restart）。

### 2.3 V078 BYPASS audit — 唯一真升級

V078 lease_transitions to_state 加 'BYPASS'。Rust `governance_emit.rs::emit_bypass_lease_transition()` 在 facade bypass 路徑直接 INSERT BYPASS row。

實測：
```
24h BYPASS rows:  7,955 (since 12:39, ~33/min steady)
4h BYPASS rows:   7,465
Engine PID:       298034 (started 15:52, binary built 14:02)
```

**Verdict**：✅ **V078 是 v2 唯一真進度**。BYPASS audit row 持續寫入（~33/min）證明 Rust runtime 真接到 V078 schema + 真 emit。Stage：Foundation → **Production**。

---

## §3 5×4 Grid 5/12 復評

### 3.1 18 components 對比 v1 vs v2

| # | Component | v1 stage | v2 stage | Δ | 證據 |
|---|---|---|---|---|---|
| 1 | Strategist live | Production | Production | = | demo+live_demo intents 24h 174 fills |
| 2 | Risk gate | Production | Production | = | risk_verdicts 24h 257k+ |
| 3 | Reconciler / position_snapshots | Production | Production | = | 1 day chunk + retention live |
| 4 | decision_outcomes backfiller | Canary fragile | **Canary fragile**（live cohort 仍 19d stale） | = | live latest_backfill 仍 4/20，V074 cron **未 install** |
| 5 | MLDE shadow recommendations | Shadow | Shadow | = | demo+live_demo 24h 1071 row |
| 6 | MLDE param applications | Canary | Canary | = | demo only |
| 7 | Edge estimator | Production | Production | = | edge_estimates.json 15min age |
| 8 | Edge estimate snapshots V059 | Foundation | **Foundation**（仍 stale 5/7 00:46） | = | 457 row 5/7 後 0 new；V073 cron **未 install** |
| 9 | Model registry | Canary fragile | **Canary fragile**（17d stale） | = | 仍 4/23 last_train, 0 production status |
| 10 | Drift detector | Aspirational | **Aspirational**（V072 contract guard + Rust CLI dry-run only） | = | feature_baselines 仍 0 row, drift_events 0 row |
| 11 | Cost edge advisor | Skeleton | Skeleton | = | cost_edge_advisor_log 0 row, env OFF |
| 12 | Decision lease audit V054 | Foundation | Foundation | = | governance_audit_log 22802 row（5/8 audit baseline 22793→22802，+9 only）|
| 13 | Replay simulated_fills | Shadow（5 calibrated）| Shadow（仍 5 calibrated，5/7 burst 後 2 day 0 new） | = | tier 維持但 daily 0 |
| 14 | Counterfactual generator | Aspirational | Aspirational | = | 0 row, 0 producer code |
| 15 | Calibrated replay | Foundation | Foundation | = | 5 row stuck |
| 16 | Dream engine | Shadow（burst then dormant）| **Shadow**（仍 5/7 burst dormant） | = | 12 experiments 不變 |
| 17 | LinUCB shadow compare | Shadow | Shadow | = | 維持 |
| 18 | LG-5 reviewer scheduler | Canary | Canary | = | governance_audit_log +9 only（基本 idle） |
| **NEW v2** | **lease_transitions BYPASS audit** | n/a | **Production** | +1 | V078 真 IMPL，24h 7955 BYPASS row（~33/min） |
| **NEW v2** | promotion_pipeline tail risk + selection bias gate | n/a | **Aspirational**（code-in-place but no caller） | 0 | dormant module |
| **NEW v2** | layer2 context distiller | n/a | **Skeleton**（wired in layer2_engine but Layer 2 仍 manual） | 0 | wired but Layer 2 not in production loop |

### 3.2 5 階段 final 歸類 v1 vs v2

| 階段 | v1 數量 | v2 數量 | Δ |
|---|---:|---:|---:|
| **Production** | 5 | **6** | +1（V078 BYPASS audit） |
| **Canary** | 4 | 4 | = |
| **Shadow** | 5 | 5 | = |
| **Skeleton** | 3 | **4** | +1（context_distiller 新加）|
| **Foundation** | 4 | **3** | -1（feature_baselines 從 Foundation→Aspirational，因 Rust CLI dry-run 不算 writer） |
| **Aspirational** | 4 | **5** | +1（promotion_pipeline 新加 dormant code）|

**Total component**：v1 21（含 14 base + 7 new from v1）→ v2 23（+2 new from v2 batch）

**MIT 真實達標率**：
- v1: 42%（geometric mean of 4 dimensions, A/B/C/D weighted）
- v2: **44%**（V078 BYPASS audit 升 1 → 真升 +2 pp；其他 commits 全是 source-only 不貢獻）

---

## §4 Dream Engine 仍 Foundation only 確認

**v1 verdict**：Foundation only（5/7 burst 後 0 new）  
**v2 verdict**：**仍 Foundation/Shadow boundary**（5/7 burst 5 calibrated_replay row，2 day 0 new）

實測：
```
calibrated_replay row count:    5（unchanged from v1）
calibrated_replay max(ts):      5/7 01:24（unchanged from v1）
synthetic_replay row count:     1
counterfactual_replay row:      0
```

**Push back**：v2 commits 完全沒有 dream_engine 改動。`dream.rs` + `dream_engine.py` 仍存在但**從 5/7 burst 後 dormant**。Replay simulated_fills 升 Shadow stage（v1 升的）但**未進入 steady production**。Sprint 3 預估「12 個月內不可能 ready」對 1k sample LightGBM 仍成立。

---

## §5 attribution_chain_ok 24h delta 深度分析

### 5.1 v1 vs v2 數據

```
v1（5/9 03:30）24h:  44 / 234,416   = 0.0188%
v2（5/9 16:30）24h:  65 /  12,894   = 0.5041%
v2 7d:               274 / 556,775   = 0.0492%
```

### 5.2 Daily breakdown v2

```
2026-05-09:     35 / 2917      1.1999%   ← 2917 row total（vs 5/8 一天 266977 row）
2026-05-08:     43 / 266,977   0.0161%
2026-05-07:     36 / 264,546   0.0136%
2026-05-06:     23 / 22,036    0.1044%   ← 5/6 explosion 起點
2026-05-05:     39 / 86       45.3488%
2026-05-04:     47 / 129      36.4341%
2026-05-03:     35 / 57       61.4035%
2026-05-02:     42 / 67       62.6866%
2026-05-01:     15 / 36       41.6667%
```

### 5.3 對抗性 verdict

**v2 ratio 0.50% 看似 26× v1 改善，但 denominator 暴跌 18× 才是主因**：
- absolute ok_n: 44 → 65（+47%，正常 daily noise）
- denominator: 234416 → 12894（-94.5%，**source 異常**）

**3 假設**：
1. **mlde_edge_training_rows view 改 narrow filter**（SELECT WHERE clause 縮窄）
2. **mlde_edge_training_rows producer 5/9 後嚴重減產**（live_demo intent 數量真跌）
3. **5/8 後 outcome backfill 一次性釋放**（5/6→5/7→5/8 暴增是 backfill 釋放，5/9 用完 → 真實 daily ~3000）

**MIT 強烈建議**：dispatch sub-agent 跑 `git log --oneline 5/8..5/9 -- "*.py" "*.sql" | grep -E 'mlde|attribution|edge_training'` 找 view definition / writer 改動。

**結論**：v1 verdict「FUP-2 commit 在 main 但 source bug 未根治」**仍成立**；v2 ratio 的 26× 改善是 **denominator artifact 不是 IMPL 改善**。

---

## §6 V### Migration + Guard 檢查

### 6.1 V068-V078 總狀態（v2 新增 V078）

| V### | name | applied | Guard A retrofit | runtime impact |
|---|---|---|---|---|
| V068-V077 | (v1 已驗，無 v2 改動) | success=t | 見 v1 報告 | 見 v1 報告 |
| **V078** `lease transitions bypass state` | **2026-05-09 11:33** | t | ✅（schema 加 to_state CHECK 含 BYPASS） | ✅ **真生效**（7955 BYPASS row 24h） |

### 6.2 Guard A/B/C 違規回報（v2 commits）

V078 SQL 檢查（讀 file）：
- ✅ Guard A：`information_schema.tables` check ✅
- ✅ Guard B：CHECK constraint 替換（DROP + ADD CHECK）含 fail-fast 確認舊 constraint 存在
- ✅ idempotency：跑兩次第二次 no-op

**違規**：0（V078 規範 compliant）

---

## §7 Healthcheck 覆蓋

v1 已有 51 healthcheck。v2 commits 中：
- **未新增** healthcheck（檢查 `helper_scripts/db/passive_wait_healthcheck.py` 無 v2-related new check function）
- V078 BYPASS audit **無對應** check function（建議新增 `check_lease_transitions_bypass_freshness()`）

**Push back**：CLAUDE.md §七「被動等待 TODO 必附 healthcheck」要求 V078 應同步新增 healthcheck。**violations: 1**。

---

## §8 對抗性 Push Back

### 8.1 「34-dim feature baseline writer」commit message 嚴重誤導

`7657bd25 ml: add 34-dim feature baseline writer` 字面暗示 ML feature baseline writer added。實際：
- ✅ Rust CLI binary `feature_baseline_writer` 存在 + 編譯
- ❌ default `--dry-run`，無自動執行
- ❌ **無 cron 排程**
- ❌ **無 daemon spawn**
- ❌ **feature_baselines 表仍 0 row**
- ❌ drift_detector chain 仍 broken

**正確 commit message 應為**：「ml: add 34-dim feature baseline rebuild CLI tool (dry-run default, manual --apply only, no scheduling)」

### 8.2 「portfolio tail risk gate」+「selection bias promotion gate」是 dormant code

`cc6476dd` + `716eb3d6` 加了 `portfolio_var.py` (312 LOC) + `cvar.py` (295 LOC) + `promotion_gate.py` (141 LOC) + `promotion_pipeline.py` 整合。

實測：
- `PromotionPipeline` class 在 `promotion_pipeline.py` 但**無外部 caller**
- `_entries: dict[str, PromotionEntry]` 從未被 populated（grep 無 `register()` call）
- 5 promotion gate methods（DEMO_ACTIVE → LIVE_PENDING）只在 `promote()` 內部 chain 被檢查

**Push back**：promotion_pipeline 是 standalone module 寫了一年沒 wire 到任何 promotion route / scheduler / agent。v2 加 fail-closed gate 是「在沒人走的路上加防火牆」。應同步：
1. wire promotion_pipeline 到 `mlde_param_applications` 真實路徑，或
2. 標明「LG-3 supervised-live state machine 未到位前 dormant」（誠實寫 commit message）

### 8.3 W-AUDIT-4 closure 仍未補完

v1 報告列出 P0 立即 operator action：
1. install crontab `outcome_backfiller_live_cron.sh`（V074）— **v2 仍未 install**
2. install crontab `edge_estimate_snapshots_cycle_cron.sh`（V059）— **v2 仍未 install**
3. PG `ALTER SYSTEM SET work_mem='32MB'`+ reload — **v2 未驗（M5 Ultra 部署前必修）**
4. RCA mlde_edge_training_rows 5/6 explosion source — **v2 未驗（且 5/9 又出新 anomaly）**

**MIT 強烈建議**：W-AUDIT-5 必須包含這 4 條。否則 v2 → v3 仍是 schema-side 推進、runtime-side 停滯。

### 8.4 v2 真升級總結

**確認真升級的 1 個**：
- ✅ V078 lease_transitions BYPASS audit live（7955 row/24h，~33/min）— Rust runtime 真接到 + 真 emit + 真 INSERT

**Marketing 但實質 0 改善的 4 個**：
- ❌ feature_baseline_writer（Rust CLI dry-run，仍 0 row）
- ❌ portfolio tail risk gate（dormant module）
- ❌ selection bias promotion gate（dormant module）
- ❌ context_distiller wiring（Layer 2 不在 production loop）

**docs 真實 closure 1 個**：
- ✅ FUP-2 cron 確 install（a904e273 是 docs verification）

---

## §9 結論 + 立即建議

### 9.1 對抗性核實 5 已驗事項

1. ✅ **V078 BYPASS audit 真實生效**（7955 row 24h，~33/min steady）
2. ⚠️ **attribution_chain_ok 24h 0.0188% → 0.5041%**（**denominator artifact 不是真改善**；absolute ok_n 只 +47%）
3. ❌ **feature_baselines 仍 0 row**（V072 contract guard + Rust CLI dry-run，drift chain **仍 broken**）
4. ❌ **cost_edge_advisor_log 仍 0 row**（env 仍 OFF；無進度）
5. ❌ **decision_outcomes.live latest_backfill 仍 4/20**（19d stale；V074 cron 未 install）

### 9.2 結論

**v2 修復 1/3 到位**：
- **schema-side**: V078 BYPASS audit 真補（+1 Production stage）
- **runtime-side**: 0 進度（cron 仍未 install，feature_baselines 仍 0 row, attribution chain ratio 改善只是 denominator artifact）
- **dormant code-side**: +2 module（promotion gate + tail risk）但無 runtime caller，等於**債務新增**

**ML 基座達標率**：v1 42% → v2 **44%**（+2 pp，僅 V078 vital；其他 commits 不貢獻 grid）

**距 Mainnet ML-driven**：仍 **3-4 sprint**（樂觀 8/15 / 中位 9/15 / 悲觀 11/15，**未變**）

### 9.3 W-AUDIT-5 建議 P0

1. **operator action**：install crontab outcome_backfiller_live_cron.sh + edge_estimate_snapshots_cycle_cron.sh + 觸發 feature_baseline_writer 一次 `--apply`（seed 第一批 baseline 啟動 drift chain）
2. **RCA mlde_edge_training_rows 5/6 + 5/9 anomaly**（denominator volatility 拖低 ratio 信號）
3. **PromotionPipeline 接線**：wire 到 mlde_param_applications 路徑或標 dormant pending LG-3
4. **新增 healthcheck `check_lease_transitions_bypass_freshness()`**（V078 規範 compliance）

---

**MIT VERIFICATION DONE v2** — `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--db_ml_verification_v2.md`
