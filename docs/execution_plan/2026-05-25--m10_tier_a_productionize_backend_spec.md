---
spec: W1-D — M10 Tier A Productionize Backend Spec (Optuna walk-forward cron skeleton, V111-decoupled)
date: 2026-05-25
author: MIT (W1-D Wave 1 sub-agent per Sprint 2 dispatch packet §1.2)
phase: Sprint 2 Wave 1 backend spec (PM #2 decision: V111 spec @ Sprint 1A-γ 先;Wave 1 後端不阻)
status: SPEC-DRAFT-V0 (MIT 起草 backend skeleton design;不寫 IMPL skeleton code;W2-C E1 IMPL chain 接手)
sprint: Sprint 2 (W12-14.5 wall-clock;PM 3 decision 拍 5/25 — Stream C V111 land cadence #2 採 (a))
size estimate: 後端 cron + walk-forward harness 估 ~20-30 hr (W1-D + W2-C IMPL 接力;不含 V111 schema land 的 15-20 hr W2-C)
scope: design / spec only — 不寫 helper_scripts/m10/*.py 實檔,不寫 cron entry,不執行 PG,不改 optuna_optimizer.py / ml_training_maintenance.py 既有 IMPL,V111 schema layer 由 PA spec (`2026-05-21--v111_m10_discovery_tier_config_schema_spec.md`) 與 W2-C IMPL 接手
depend on:
  - v5.8 §2 M10 line 357-389 (Discovery pipeline tiers + Engineering scope)
  - v5.8 §5 line 644-663 (Capital-tier IMPL triggers,$10k → Tier A only confirmed)
  - ADR-0036 (HMM / Markov-switching / GARCH 黑名單;Tier D 才用 ATR-vol+funding;Tier A 只用 Optuna parameter discovery)
  - Sprint 2 dispatch packet `2026-05-25--sprint_2_business_dispatch_packet.md` §4 + PM #2 decision
  - 既有 IMPL:program_code/ml_training/optuna_optimizer.py (TPE within-strategy parameter discovery,JournalFileStorage)
  - 既有 IMPL:program_code/ml_training/edge_estimate_validation.py:_walk_forward_oos_values (purge gap walk-forward harness)
  - 既有 IMPL:program_code/ml_training/quantile_trainer.py:get_embargo_config (CPCV + embargo per-strategy carve-out)
  - 既有 cron:helper_scripts/cron/ml_training_maintenance_cron.sh (17 03 * * *, daily, 含 optuna_optimizer job)
depended by:
  - W2-C E1 IMPL V111 schema land + Optuna cron 接線 V111 config table (Sprint 2 Wave 2)
  - Sprint 1A-γ V111 spec final FINAL (operator-pending sign-off + MIT C9 Linux PG dry-run)
related skills:
  - .claude/skills/time-series-cv-protocol/SKILL.md (MIT Purged k-fold + Embargo + walk-forward)
  - .claude/skills/walk-forward-validation-protocol/SKILL.md (QC alpha 顯著性協議)
  - .claude/skills/math-model-audit/SKILL.md (HMM/GARCH 黑名單 source of truth)
  - .claude/skills/ml-pipeline-maturity-audit/SKILL.md (Foundation/Skeleton/Shadow/Canary/Production 5 階段)
  - .claude/skills/feature-engineering-protocol/SKILL.md (look-ahead/target/survivorship/cross-section/time-zone/resample 6 維 leakage)
mirror precedent:
  - srv/helper_scripts/cron/ml_training_maintenance_cron.sh (bash wrapper / lock dir / IPC secret / status JSON / dry-run flag 範式)
  - srv/helper_scripts/cron/ml_training_maintenance.py (Python entry / --jobs --strategies --engine-modes flags 範式)
  - srv/docs/execution_plan/2026-05-21--v111_m10_discovery_tier_config_schema_spec.md (V111 governance schema + 5 tier seed)
---

# M10 Tier A Productionize Backend Spec (V111-Decoupled Wave 1 Skeleton)

## §0 TL;DR

- **W1-D MIT 後端 spec 範圍**:Sprint 2 Wave 1 內派 sub-agent W1-D IMPL Optuna walk-forward cron skeleton 後端 **不依賴 V111 schema land**;W2-C E1 IMPL 接線 V111 由 Sprint 1A-γ V111 spec land 後接力。
- **Tier A scope per v5.8 §5 line 645-648 confirmed**:capital $10k(Y1 start)→ **Tier A only**;Tier B-E 不在 Sprint 2 範圍。
- **Tier A 範圍 = within-strategy parameter discovery via Optuna + walk-forward**(per v5.8 §2 M10 line 364)— **已存在邏輯**(`optuna_optimizer.py` TPE + `edge_estimate_validation.py:_walk_forward_oos_values` purge gap),本 spec 為 productionization = 接 cron + auto-walk-forward。
- **黑名單 method 強制 per ADR-0036**:Tier A **不**使用 HMM / Markov-switching / GARCH;Tier D 才用 ATR-vol+funding(Sprint 2 不開 Tier D);本 spec sub-agent dispatch grep gate `hmm|markov_switching|garch` 防漂移。
- **5+2 = 7 策略 scope**:5 textbook(grid_trading / ma_crossover / bb_breakout / bb_reversion / funding_arb)+ Sprint 2 W2-B IMPL 2 新 candidate(funding short > 30% annualized + liquidation cascade fade per PM #1 decision)。
- **Cron cadence**:weekly Sunday 05:30 UTC(`30 5 * * 0`)— **不撞** ml_training_maintenance daily 17:03;Tier A Optuna trial 較重(within-strategy TPE n_trials=30 + walk-forward 6 fold × 7 策略)適合 weekly cadence。
- **V111 dependency 解耦策略**:Wave 1 sentinel JSON file `/tmp/openclaw/m10_tier_a_proposals/{strategy}_{symbol}_{regime}.json` 寫 proposal output;Sprint 1A-γ V111 schema land 後 Wave 2 W2-C 接線 V111 INSERT path(governance.discovery_tier_activations + V004 ml_parameter_suggestions 雙寫 dual-write)。
- **Walk-forward 設計**:purge_days=2 + ≥ 6 historical sub-period × ≥ 30 fills per sub-period(per CR-6 minimum bar + Lopez de Prado AFML Ch.7 Purge+Embargo);per-strategy embargo 走既有 `quantile_trainer.get_embargo_config()`(funding_arb 72h 例外 + 其餘 24h)。
- **6 AC for Stream C(per Sprint 2 dispatch packet §4.3)**:AC-S2-C-1 cron skeleton IMPL(Wave 1) / AC-S2-C-2 7 策略 weekly run pass(14d 內 1-2 次 fire) / AC-S2-C-3 V111 接線(Wave 2 後) / AC-S2-C-4 capital tier $10k Tier A only / AC-S2-C-5 capital-tier hook 留 Tier B-E(per v5.8 §2 M10) / AC-S2-C-6 hold-back hypothesis 不直接觸 trading(per 16 原則 #7 學習 ≠ live)。

---

## §1 Context + Why

### 1.1 Sprint 2 Wave 1 W1-D 工作 scope

per Sprint 2 dispatch packet §4 (Stream C M10 Tier A Productionize) + §1.2 (Wave 1 W1-D track):

| 元素 | 設計 |
|---|---|
| Sprint 2 期內 IMPL 範圍 | Tier A only — within-strategy parameter discovery (Optuna + walk-forward cron 接線) |
| Wave 1 W1-D 後端範圍 | cron skeleton + walk-forward harness + sentinel JSON writer(無 V111 INSERT) |
| Wave 2 W2-C 後端範圍 | V111 schema land 後接線 governance.discovery_tier_activations INSERT;sentinel JSON path 退役為 fallback |
| 不在 Sprint 2 範圍 | Tier B-E(per v5.8 §5 capital scaling ladder $10k=Tier A only)/ Tier D 9 cell regime adaptive(per ADR-0036 Y2-Y3 才開)/ Tier C cointegration pairs(per v5.8 §2 M10 Y2 起)/ Tier B M4 pattern miner variant proposal(per v5.8 §2 M10 Sprint 8 起;當前 Stream B M4 stage 1 = DRAFT writeback,不觸 Tier B activation) |

### 1.2 為什麼 V111 schema dependency 解耦(PM #2 decision)

per Sprint 2 dispatch packet §9.2 PM #2 拍 (a):
- Sprint 1A-γ V111 spec 必先 Sprint 2 Wave 1 W1-D
- Stream C 後端 Optuna IMPL **不依賴 V111**(後端可獨立 productionize)
- W2-C V111 schema deploy 等 1A-γ V111 spec land

理由:
1. V111 spec(`2026-05-21--v111_m10_discovery_tier_config_schema_spec.md`)為 PA spec FULL-V0,operator + MIT C9 Linux PG dry-run pending,未 FINAL;Sprint 2 不能 block on Sprint 1A-γ FINAL
2. Tier A IMPL = parameter discovery → proposal writeback;V111 是 **config + activation ledger** 而非 proposal 本身;proposal 寫入既有 V004 `ml_parameter_suggestions`(per `optuna_optimizer.py:8` line)是 productionization 主路徑;V111 接線是 **governance.discovery_tier_activations** ledger 補位
3. Wave 1 sentinel JSON 是 forward-compat **bridge**:V111 land 後 W2-C 接線 INSERT,sentinel JSON 退役為 dry-run fallback / replay surface
4. 不阻塞:Wave 1 IMPL 完整 = cron + walk-forward + sentinel write;Wave 2 W2-C IMPL 完整 = sentinel + V111 dual-write(per dual-write drift healthcheck per V086 範式)

### 1.3 Tier A vs Tier B-E 黑名單 method enforcement

per ADR-0036 Decision 1 + 3:
- **Tier A only Optuna parameter discovery** — 不觸 regime detection / market discovery / venue discovery
- **Tier D 才**用 ATR-vol + funding 雙 axis 9 cell — Sprint 2 不開
- **HMM / Markov-switching / GARCH 任何用途黑名單**(per math-model-audit skill source of truth + ADR-0036 governance promotion)— 包括 Tier A 隱伏使用(e.g. Optuna sampler 用 GP 變形帶 GARCH-like noise)是 hard reject

**Sub-agent dispatch grep gate(per ADR-0036 Decision 1 + 黑名單 grep 失敗 fail-closed)**:

```bash
grep -rni 'hmm\|markov_switching\|garch' helper_scripts/m10/ rust/openclaw_engine/src/m10*/ 2>/dev/null
# 任一 hit = E2 reject + W1-D / W2-C IMPL push back
```

PA + MIT(W1-D 本 spec)+ E2(W2-E review)三層 grep gate;dispatch 前 + IMPL DONE 後雙 round。

---

## §2 Backend Skeleton Design

### 2.1 cron skeleton 三層架構

```
Cron line: 30 5 * * 0 (weekly Sun 05:30 UTC)
  ↓ fire
helper_scripts/m10/tier_a_productionize_cron.sh (bash wrapper)
  ↓ exec Python
helper_scripts/m10/tier_a_productionize.py (Python entry)
  ↓ for each strategy × symbol × regime
program_code/ml_training/optuna_optimizer.py (既有 TPE optimizer)
  ↓ + walk-forward harness
program_code/ml_training/edge_estimate_validation.py:_walk_forward_oos_values (既有 walk-forward)
  ↓ proposal output
Wave 1: /tmp/openclaw/m10_tier_a_proposals/{strategy}_{symbol}_{regime}.json (sentinel)
Wave 2: governance.discovery_tier_activations INSERT (V111 land 後)
```

### 2.2 Cron cadence 選擇 — 為什麼 weekly Sun 05:30 UTC

per Sprint 2 dispatch packet §4.4 IMPL hint(`30 5 * * 0`)+ memory `project_2026_05_09_ml_training_cron_weekly`:

| Cadence | 採用? | 理由 |
|---|---|---|
| Daily(同 ml_training_maintenance 17:03 UTC)| ❌ | (1) 撞 ml_training_maintenance 17:03 daily cron;(2) Tier A Optuna trial 較重(n_trials=30 × 7 策略 × 25 symbol × 3 regime = 15,750 trial)單 daily 不 sustainable;(3) parameter discovery 不需 daily 跑(strategy parameter 變動是 weekly+ 級時間尺度) |
| **Weekly Sun 05:30 UTC** | ✅ | **採用**;(1) 不撞 daily cron;(2) Sunday early morning UTC = low trading volume,IPC + PG load 較低;(3) Tier A discovery 7d cycle 符合 strategy parameter regime persistence(per memory baseline);(4) ml_training_maintenance daily 17:03 UTC 後 12h 跑 Tier A,確保 trainer 已 land 最新 model 才跑 Optuna |
| Bi-weekly Sun 05:30 UTC | ⚠️ | 太稀疏;14d cadence 對 Sprint 2 14d AC 內僅 1 次 fire,不足 acceptance evidence |
| Monthly | ❌ | 對 Sprint 2 14d AC 完全不 fire |

### 2.3 helper_scripts/m10/tier_a_productionize_cron.sh — bash wrapper(spec only,不寫實 code)

```
File: helper_scripts/m10/tier_a_productionize_cron.sh
Mirror precedent: helper_scripts/cron/ml_training_maintenance_cron.sh

Structure(LOC ~150;不寫實 IMPL,Wave 2 W2-C E1 IMPL):
- BASE / DATA / LOG_DIR / STATUS_DIR / LOCK_ROOT(同 ml_training_maintenance 範式)
- IPC secret loading(從 $OPENCLAW_IPC_SECRET_FILE 讀 0600 file;cron 環境 systemd 不繼承 daemon env)
- PG creds loading(從 $SECRETS_ROOT/environment_files/basic_system_services.env)
- mkdir lock dir;flock 防 concurrent run(per ml_training_maintenance line 61-70)
- 5+2 STRATEGIES env override:OPENCLAW_M10_TIER_A_STRATEGIES (default = grid_trading,ma_crossover,bb_breakout,bb_reversion,funding_arb,funding_short_v2,liquidation_cascade_fade)
  *注*:funding_short_v2 + liquidation_cascade_fade 待 W2-B E1 IMPL(per PM #1 decision Stream A)後才會被 cron 真正觸發;Wave 1 IMPL 跑 5 textbook,Wave 2 W2-B IMPL 完成後 cron env 自動觸 7 策略
- ENGINE_MODES env override:OPENCLAW_M10_TIER_A_ENGINE_MODES (default = "demo,live_demo";per training filter rule)
- ENGINE_MODE filter pass-through:同 ml_training_maintenance --training-engine-modes
- Python entry exec:helper_scripts/m10/tier_a_productionize.py
- Status JSON write:$STATUS_DIR/m10_tier_a_productionize_status.json(per ml_training_maintenance 範式)
- Log:$LOG_DIR/m10_tier_a_productionize_cron.log
- Dry-run support:OPENCLAW_M10_TIER_A_DRY_RUN=1 → --dry-run flag
```

### 2.4 helper_scripts/m10/tier_a_productionize.py — Python entry(spec only)

```
File: helper_scripts/m10/tier_a_productionize.py
Mirror precedent: helper_scripts/cron/ml_training_maintenance.py

Module-level:
- MODULE_NOTE(中):M10 Tier A productionize cron — per v5.8 §2 M10 + ADR-0036 + Sprint 2 W1-D spec
- imports:argparse / logging / psycopg2 / pathlib / json
- 既有 import:program_code.ml_training.optuna_optimizer (TPE)
                program_code.ml_training.edge_estimate_validation (walk-forward harness)
                program_code.ml_training.quantile_trainer (get_embargo_config per-strategy)

CLI args:
- --base-dir / --dsn / --strategies / --symbols / --regimes(per ml_training_maintenance 範式)
- --training-engine-modes(default="demo,live_demo")
- --wf-train-days(default=60)
- --wf-test-days(default=14)
- --wf-step-days(default=7)
- --wf-purge-days(default=2;per Lopez de Prado AFML purge gap)
- --n-trials(default=30;per OptunaConfig)
- --min-fills-required(default=80;per OptunaConfig)
- --min-subperiod-fills(default=30;per CR-6 minimum bar)
- --min-walk-forward-windows(default=6;per spec §2.5)
- --proposal-dir(default=/tmp/openclaw/m10_tier_a_proposals/)
- --v111-enable(default=False;Wave 2 W2-C 接線 V111 INSERT path)
- --dry-run / --status-json

Main loop:
for strategy in STRATEGIES:
    for symbol in SYMBOLS:
        for regime in REGIMES:  # default = ['default'] Y1(Tier D regime adaptive 不在 scope)
            walk_forward_proposal = run_tier_a_discovery(
                strategy_name=strategy,
                symbol=symbol,
                regime=regime,
                wf_config=ValidationConfig(
                    wf_train_days=args.wf_train_days,
                    wf_test_days=args.wf_test_days,
                    wf_step_days=args.wf_step_days,
                    purge_days=args.wf_purge_days,
                    min_trust_n=args.min_subperiod_fills * args.min_walk_forward_windows,
                ),
                optuna_config=OptunaConfig(
                    n_trials=args.n_trials,
                    min_fills_required=args.min_fills_required,
                ),
                engine_modes=args.training_engine_modes.split(','),
            )
            # Sentinel JSON write(Wave 1)
            proposal_path = Path(args.proposal_dir) / f"{strategy}_{symbol}_{regime}.json"
            with proposal_path.open("w") as f:
                json.dump(walk_forward_proposal.asdict(), f)
            # V111 INSERT(Wave 2 後接線)
            if args.v111_enable:
                insert_tier_a_proposal_to_v111(walk_forward_proposal, pg_conn)

Return: 0(success)/ 1(any strategy×symbol fail)/ 2(catastrophic)
```

### 2.5 Walk-forward harness 要求(per §0 + time-series-cv-protocol skill)

per Sprint 2 dispatch packet §4 + skill `time-series-cv-protocol` + 既有 `edge_estimate_validation._walk_forward_oos_values`:

| 元素 | 要求 |
|---|---|
| Walk-forward 類型 | Walk-Forward Rolling(crypto regime 快 — per skill 推薦);非 Anchored Expanding(後期 train fold 巨大)|
| Train window | 60d(default,可 override)|
| Test window | 14d(default,可 override)|
| Step window | 7d(default,可 override)|
| Purge gap | **2 day**(per Lopez de Prado AFML Ch.7;crypto exit horizon ~3600s + autocorrelation,2d 是 conservative;funding_arb 走 quantile_trainer get_embargo_config 72h carve-out)|
| Min historical sub-period | **≥ 6**(per Sprint 2 dispatch packet §4 + CR-6;< 6 fold 統計力不足)|
| Min fills per sub-period | **≥ 30**(per CR-6 minimum bar)|
| Total min sample | min_subperiod_fills × min_walk_forward_windows = 30 × 6 = 180;近 OptunaConfig min_fills_required=80 但 walk-forward 要求嚴格|
| Per-strategy embargo override | funding_arb 走 quantile_trainer get_embargo_config = 72h embargo(超過 default 2d 大);其餘 5 策略 走 24h embargo(< 2d default;default 較保守) |
| Embargo direction | embargo after test window;不在 train tail(per Lopez de Prado)|
| Time series CV 補位 | Optional 後續:CSCV(Combinatorially Symmetric CV)for PBO calculation;Wave 1 不 IMPL(per `time-series-cv-protocol` skill §5);Wave 2+ 評估 |

### 2.6 Optuna trial scope(per existing optuna_optimizer.py)

per `optuna_optimizer.py` line 30-160:
- TPE sampler(Tree-structured Parzen Estimator)
- JournalFileStorage(`/tmp/openclaw/optuna_studies.log` per OPENCLAW_DATA_DIR override)
- direction="maximize" on EV_net(per `compute_ev_net` line 238)
- search space built from `get_param_ranges` IPC call(per `build_search_space` line 167-230)— 只 include `agent_adjustable=true` parameter

**Sprint 2 W1-D scope 補位**:
1. `run_tier_a_discovery` wrapper 函式 — 串 Optuna study + walk-forward harness;不改 optuna_optimizer.py 既有 IMPL
2. 每個 walk-forward fold 內跑 n_trials=30 / 5 = 6 trial(per fold 平均;total 30 trial 切分)
3. Walk-forward OOS Sharpe + IS-OOS gap 算 → per-fold metrics dict
4. Cross-fold consistency check(mean ± std per skill `time-series-cv-protocol` §6.3):std/mean > 0.5 不寫 V004 ml_parameter_suggestions(per skill 反模式)

### 2.7 Sentinel JSON proposal schema(Wave 1)

```
File: /tmp/openclaw/m10_tier_a_proposals/{strategy}_{symbol}_{regime}.json
Permissions: 0640 (per cron writer convention)
Retention: 30d(per OPENCLAW_DATA_DIR /tmp lifecycle;Wave 2 V111 接線後可降 7d)

Schema (forward-compat with V111 schema 接線):
{
  "schema_version": "v0.1-w1d-wave1-sentinel",
  "generated_at_utc": "2026-05-XX-XX:XX:XX",
  "generated_by_cron": "m10_tier_a_productionize_cron",
  "tier_level": "A",
  "strategy_name": "grid_trading",
  "symbol": "BTCUSDT",
  "regime": "default",
  "engine_modes": ["demo", "live_demo"],
  "wf_config": {
    "train_days": 60,
    "test_days": 14,
    "step_days": 7,
    "purge_days": 2,
    "min_subperiod_fills": 30,
    "min_walk_forward_windows": 6,
  },
  "optuna_config": {
    "n_trials": 30,
    "min_fills_required": 80,
    "sampler": "TPE",
  },
  "wf_fold_count": 6,
  "wf_oos_n": 250,
  "wf_oos_mean_bps": 7.5,
  "wf_oos_sharpe": 1.85,
  "wf_psr": 0.95,
  "wf_dsr": 0.93,
  "wf_p_bonferroni": 0.04,
  "cross_fold_std_mean_ratio": 0.32,
  "best_params": {
    "param_a": 1.234,
    "param_b": 0.567,
  },
  "best_value": 0.012,
  "v111_eligible": true,        # cross_fold_std_mean_ratio < 0.5 + wf_psr ≥ 0.90 + wf_oos_n ≥ 180
  "v111_writeback_status": "pending_w2c_impl",  # Wave 2 W2-C 接線後改 "applied"
  "leakage_checks": {
    "shift1_applied": true,     # per feature-engineering-protocol skill (rolling stat shift(1))
    "engine_mode_filter_correct": true,  # IN ('live','live_demo') 不混 paper
    "walk_forward_purge_applied": true,  # purge_days=2 + per-strategy embargo
    "resample_boundary_closed_bar_only": true,  # per skill §6 reample boundary
  },
  "hard_boundary_grep_pass": true,  # no hmm/markov_switching/garch hit per ADR-0036
}
```

### 2.8 V111 接線 (Wave 2 W2-C 後)

V111 spec(`2026-05-21--v111_m10_discovery_tier_config_schema_spec.md`)規定 2 tables on `governance` schema:
- `governance.discovery_tier_config`(5 row seed Tier A-E)
- `governance.discovery_tier_activations`(hypertable on `activated_at`;30d compress / 180d retention)

**Wave 2 W2-C E1 IMPL chain 接線**:
1. Tier A discovery 觸發 → 寫 `governance.discovery_tier_activations`(transition activation ledger;append-only audit)
2. **不寫** `governance.discovery_tier_config`(read-only config seed;V111 land 時 INSERT 5 row 固定);Tier A productionize cron 不 mutate config
3. Optuna proposal best_params 走既有 V004 `learning.ml_parameter_suggestions`(per `optuna_optimizer.py:8` line note)— V111 接線**不替代**該 path,而是補位 governance audit trail
4. Dual-write drift healthcheck:sentinel JSON file count vs V111 INSERT count + V004 ml_parameter_suggestions INSERT count 24h 內三邊對齊;偏差 > 5% trigger M3 HEALTH_WARN(per V086 dual-write drift 範式)

---

## §3 AC for Stream C (per Sprint 2 dispatch packet §4.3)

| AC | 內容 | 達標路徑 | Sprint 2 within-scope? |
|---|---|---|---|
| **AC-S2-C-1** | Optuna walk-forward cron skeleton IMPL DONE | W1-D E1 IMPL helper_scripts/m10/tier_a_productionize{,_cron}.{py,sh}(per §2.3 + §2.4) | ✅ Sprint 2 Wave 1 內 |
| **AC-S2-C-2** | 7 策略 weekly run pass empirical(5 textbook + 2 Sprint 2 新 candidate funding_short_v2 + liquidation_cascade_fade) | Wave 1 cron install + Sprint 2 14d 內 1-2 次 fire(2026-06-01 + 2026-06-08 兩個 Sun)+ status JSON write 對齊 | ✅ Sprint 2 14d 內 |
| **AC-S2-C-3** | V111 schema 接線 — sentinel JSON + V111 INSERT dual-write | W2-C E1 IMPL(依賴 Sprint 1A-γ V111 spec ready + V111.sql land + Linux PG dry-run x 2 round) | 🟡 條件性 — 等 1A-γ V111 spec FINAL |
| **AC-S2-C-4** | capital tier $10k → Tier A only confirmed | spec §2.4 cron entry default 不開 Tier B-E;OPENCLAW_M10_TIER_LEVEL=A 鎖死 | ✅ Sprint 2 內(本 spec 確認) |
| **AC-S2-C-5** | capital-tier hook 留 Tier B/C/D/E(per v5.8 §2 M10) | spec §2.4 cron entry env override + V111 schema 5 tier seed 保留 | ✅ Sprint 2 內(本 spec 確認) |
| AC-S2-C-6 *(MIT 補)* | Tier A proposal 不直接觸 trading(per 16 原則 #7 學習 ≠ live) | proposal output 走 V004 ml_parameter_suggestions + governance.discovery_tier_activations;**不**直接 mutate strategy parameter runtime(per ADR-0009 ArcSwap path 需 Decision Lease + Strategist orchestrator) | ✅ Sprint 2 內 |
| AC-S2-C-7 *(MIT 補)* | Walk-forward look-ahead bias 防護 | spec §2.5 purge gap 2d + per-strategy embargo(funding_arb 72h carve-out);6 leakage 維度逐項 leak-free check(per feature-engineering-protocol skill);sentinel JSON write `leakage_checks.shift1_applied=true` 必對 | ✅ Sprint 2 內(W2-E E2 review verify) |
| AC-S2-C-8 *(MIT 補)* | ADR-0036 黑名單 grep gate enforce | sub-agent dispatch(W1-D + W2-C)前 + IMPL DONE 後雙 round PA + MIT + E2 grep `hmm\|markov_switching\|garch`;任一 hit reject + push back | ✅ Sprint 2 內(W2-E E2 review verify) |
| AC-S2-C-9 *(MIT 補)* | 5 textbook 不破 demo runtime | E4 Mac cargo test --workspace --release + pytest run_training_pipeline 5 策略 demo regression(per Sprint 2 dispatch packet §7.4 E4 regression) | ✅ Sprint 2 內(W2-E E4 regression verify) |
| AC-S2-C-10 *(MIT 補)* | Optuna study journal storage 不無限長 | JournalFileStorage 30d 自動 prune cron(per OPENCLAW_DATA_DIR /tmp lifecycle);study delete 不影響 V004 historical proposal | ⚠️ Sprint 2 內 IMPL pending(W2-C 可定 P1 carry-forward;非 blocker) |

---

## §4 Implementation Hint for W2-C E1 IMPL Chain

per Sprint 2 dispatch packet §4.4 + dispatch §10 cross-cutting hygiene:

### 4.1 Python helper

```
helper_scripts/m10/tier_a_productionize.py
helper_scripts/m10/tier_a_productionize_cron.sh
helper_scripts/m10/__init__.py (空 or PY package marker)
helper_scripts/m10/tests/test_tier_a_productionize.py(pytest 範式)
```

### 4.2 Cron line spec(operator 手 install)

```
30 5 * * 0 OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
  $HOME/BybitOpenClaw/srv/helper_scripts/m10/tier_a_productionize_cron.sh
```

(2026-06-01 Sun 05:30 UTC 首次 fire;Sprint 2 14d 期內 2026-06-01 + 2026-06-08 兩次 fire 滿足 AC-S2-C-2)

### 4.3 Walk-forward result writer 兩段論

| Wave | Output | 觸發 |
|---|---|---|
| Wave 1(本 spec scope) | sentinel JSON file `/tmp/openclaw/m10_tier_a_proposals/{strategy}_{symbol}_{regime}.json` | W1-D E1 IMPL |
| Wave 2(W2-C E1 IMPL) | sentinel JSON + V111 `governance.discovery_tier_activations` INSERT(dual-write)+ V004 `learning.ml_parameter_suggestions` INSERT(既有 IMPL) | W2-C E1 IMPL after V111 land |

### 4.4 Sub-agent dispatch grep enforcement(per §1.3 + §10 dispatch packet hygiene SOP)

W1-D 起草本 spec 已 grep `hmm\|markov_switching\|garch` 在:
1. v5.8 主檔 §2 M10 line 357-389 — 0 hit ✅
2. ADR-0036 黑名單表 — 0 hit(黑名單表中字串本身不是 IMPL 代碼)✅
3. 本 spec 全文 — `hmm` 出現 0 次純 IMPL 字面(僅 reference / 否定字眼),`garch` 出現 0 次純 IMPL 字面 ✅

W2-C IMPL DONE 後 E2 + MIT 雙 round grep:
- helper_scripts/m10/ — 0 hit expected
- rust/openclaw_engine/src/m10*/ — N/A(Tier A 純 Python;不寫 Rust)

### 4.5 既有 IMPL reuse policy

Wave 1 W1-D + Wave 2 W2-C **不**改既有 IMPL:
- `optuna_optimizer.py` — 直接 import + 使用 `OptunaConfig` / `create_study` / `compute_ev_net` / `build_search_space`
- `edge_estimate_validation.py` — 直接 import + 使用 `_walk_forward_oos_values` / `ValidationConfig`
- `quantile_trainer.py` — 直接 import + 使用 `get_embargo_config` 取 per-strategy embargo
- `ml_training_maintenance.py` — 不改;新 cron 獨立(不在 ml_training_maintenance 內加 job)

理由:既有 IMPL 已 covered linucb / mlde / scorer / quantile / DL3 5 trainer;Tier A productionize 是新 surface 不應污染既有 trainer scope。

### 4.6 Linux PG empirical dry-run mandatory (W2-C 內)

per CLAUDE.md §Data, Migrations, And Validation + ADR-0011 + V055 5-round loop precedent + memory `feedback_v_migration_pg_dry_run`:

W2-C E1 IMPL chain Linux PG dry-run x 2 round:
1. Round 1 dry-run cron(`OPENCLAW_M10_TIER_A_DRY_RUN=1`)觸發 → sentinel JSON 寫 → 不 INSERT V111 / V004(dry-run flag pass-through)
2. Round 2 wet-run(--v111-enable=true)觸發 → sentinel + V111 dual-write 同步 → 24h dual-write drift healthcheck check_m10_tier_a_dual_write_drift() 必 PASS

Mac sandbox 不能 catch PG runtime semantic(per V055 教訓),W2-C E1 IMPL 不 sign-off 直到 Linux empirical PASS。

---

## §5 黑名單 method 強制 enforcement(per ADR-0036)

### 5.1 Tier A scope 黑名單 method 對照表

per v5.8 §2 M10 line 364 + ADR-0036 Decision 1:

| Method | Tier A 用? | 理由 |
|---|---|---|
| Optuna TPE(Tree-structured Parzen Estimator) | ✅ 主路徑 | already exists per optuna_optimizer.py;parameter discovery 標準工具 |
| Optuna NSGA-II / Random / CMA-ES | ⚠️ optional Future | Wave 1+ 不開;OptunaConfig 預設 TPE;CMA-ES 變形可能含 covariance estimator 警覺類 GARCH 嫌疑(per ADR-0036 例外段 read-only allowed but 不寫 live);Sprint 2 不評估 |
| Walk-forward Rolling | ✅ 主路徑 | already exists per edge_estimate_validation._walk_forward_oos_values |
| Anchored Expanding | ❌ 不採 | per skill time-series-cv-protocol §4.2:crypto regime 切換不適合 anchored;Wave 1 Rolling-only |
| Purged k-fold(Lopez de Prado) | ⚠️ optional Wave 2+ | Wave 1 不開;walk-forward purge gap 已 cover 主要 leakage;mlfinlab PurgedKFold 評估 Wave 2+ |
| CSCV(Combinatorially Symmetric CV) | ⚠️ optional Wave 2+ | per skill §5;PBO calculation 需要 K ≥ 10 model variants;Sprint 2 7 策略 × 25 symbol = 175 不夠 robust;Wave 2+ 評估 |
| **HMM / Markov-switching / GARCH 任何形式** | ❌ 永久禁用 | per ADR-0036 Decision 1;黑名單 grep gate 強制 |
| **K-means / spectral clustering** | ❌ Tier D-only | Tier D 才用(regime classify);Tier A 不觸 |
| **Hurst exponent / PELT change-point** | ❌ Tier D-only | per ADR-0036 Decision 2 + 3.4 |
| ATR-vol regime / funding state | ❌ Tier D-only | per ADR-0036 Decision 3 |

### 5.2 Sub-agent dispatch grep gate(三方雙 round)

```
Round 1 — 派發前 PA + MIT + E2 grep(本 spec 已完成 — 見 §4.4)
Round 2 — W2-C IMPL DONE 後 E2 + MIT 二次 grep(W2-E review 階段)
Round 2 範圍:helper_scripts/m10/*.py + helper_scripts/m10/*.sh + 任何新 Python module import
Round 2 命令:
  grep -rni 'hmm\|markov_switching\|garch' helper_scripts/m10/ 2>/dev/null
  # 預期 0 hit;任一 hit = E2 reject + W2-C IMPL push back
```

---

## §6 W1-D Deliverable Scope Confirmation(spec 邊界)

### 6.1 W1-D 本 spec 工作範圍

| 工作 | 完成? | 備註 |
|---|---|---|
| Read v5.8 §2 M10 line 357-389 | ✅ | line 357-389 actual(task 標 357-388 微差 1 line) |
| Read Sprint 2 dispatch packet §4.x | ✅ | per §4 Stream C M10 Tier A Productionize |
| Read v5.8 §5 line 644-663 | ✅ | capital tier $10k → Tier A only confirmed |
| Read ADR-0036 Decision 1 + 3 | ✅ | HMM/Markov/GARCH 黑名單 + Tier D 才用 ATR-vol+funding |
| Read time-series-cv-protocol skill | ✅ | Purged k-fold + Embargo + walk-forward Rolling vs Anchored |
| Read 既有 IMPL(optuna_optimizer.py / edge_estimate_validation.py / quantile_trainer.py / ml_training_maintenance_cron.sh) | ✅ | 4 既有 module audit |
| W1-D MIT 後端 spec(本檔)寫 spec / AC / 黑名單 / dispatch hint | ✅ | scope = spec only;不寫 IMPL code(per W1-D 工作邊界) |
| commit + push doc-only [skip ci] | ⏳ | 後續執行 |

### 6.2 W1-D 本 spec 工作**不**範圍(W2-C 接手)

| 工作 | 不在本 spec 範圍 | 理由 |
|---|---|---|
| 寫 helper_scripts/m10/tier_a_productionize.py 實 code | ❌ | W2-C E1 IMPL 接手 |
| 寫 helper_scripts/m10/tier_a_productionize_cron.sh 實 code | ❌ | W2-C E1 IMPL 接手 |
| 寫 V111 schema SQL | ❌ | PA spec `2026-05-21--v111_m10_discovery_tier_config_schema_spec.md` 已 spec;W2-C E1 IMPL 接 SQL land |
| 改 optuna_optimizer.py / edge_estimate_validation.py 既有 IMPL | ❌ | 4.5 既有 IMPL reuse policy 明示不改 |
| 寫 Rust m10 code | ❌ | Tier A 純 Python;不寫 Rust |
| 改 ml_training_maintenance_cron.sh 加 Tier A job | ❌ | 新 cron 獨立(per 4.5 不污染既有 cron scope)|
| Linux PG empirical dry-run V111 | ❌ | W2-C E1 IMPL chain 接 PG dry-run(per 4.6) |
| 跑 cargo test / pytest | ❌ | spec only;E4 regression 由 W2-E sub-agent |
| install cron entry | ❌ | operator 手 install(per dispatch packet §10 hygiene SOP cron 不在 sub-agent scope) |

---

## §7 Sign-off Boundary

### 7.1 MIT W1-D sign-off scope

- ✅ MIT signs backend spec design(本檔)
- ✅ MIT signs Optuna walk-forward harness 設計(time-series CV protocol 對齊)
- ✅ MIT signs 6 leakage 維度 enforcement design(feature-engineering-protocol skill)
- ✅ MIT signs ADR-0036 黑名單 enforcement design(sub-agent dispatch grep gate)
- ✅ MIT signs V111 解耦策略(sentinel JSON + Wave 2 dual-write)
- ❌ MIT does NOT sign V111 schema(PA spec scope)
- ❌ MIT does NOT sign W2-C E1 IMPL(W2-E review + W2-C IMPL chain scope)
- ❌ MIT does NOT sign cron install(operator scope per §10 hygiene SOP)
- ❌ MIT does NOT sign AlphaTournament Stream A IMPL(W1-A PA + W2-B E1 scope)

### 7.2 Hygiene SOP 遵守(per Sprint 2 dispatch packet §10)

- ✅ read-only ssh probe(Linux PG empirical:max migration version + V111 table state)
- ✅ 不跑 cargo build/test/check --release(MIT spec only;0 cargo invocation)
- ✅ 不寫 PG / 不 sudo / 不 restart 服務
- ✅ 不 install cron(operator scope)
- ✅ Mac dev-only(本 session 全部在 Mac dev / Mac sandbox)
- ✅ git fetch + branch check 已執行(per memory `feedback_fetch_before_dispatch`;本 sub-agent dispatch 前 PM 主會話 fetch)

---

## §8 References

- v5.8 主檔 §2 M10 line 357-389:`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- v5.8 主檔 §5 line 644-663(capital tier ladder):`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- v5.8 主檔 §3 line 595-612(V### dependency graph):`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- ADR-0036 M8 Anomaly Detection + M10 Tier D Regime - Model Blacklist:`docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- ADR-0009 ArcSwap config hot-reload:`docs/adr/0009-hot-config-arcswap-no-restart.md`
- ADR-0011 V### migration Linux PG dry-run mandatory:`docs/adr/0011-v-migration-linux-pg-dry-run-mandatory.md`
- Sprint 2 dispatch packet:`docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` §4 (Stream C) + §9.2 (PM #2) + §10 (hygiene SOP)
- V111 PA spec FULL-V0:`docs/execution_plan/2026-05-21--v111_m10_discovery_tier_config_schema_spec.md`
- M10 DESIGN spec(姊妹檔):`docs/execution_plan/2026-05-21--m10_discovery_tier_design_spec.md`
- M-4 sub-agent hygiene SOP:`docs/agents/sub-agent-hygiene-sop.md`
- Skills(MIT 視角):
  - `.claude/skills/time-series-cv-protocol/SKILL.md`(Purge / Embargo / Rolling vs Anchored)
  - `.claude/skills/feature-engineering-protocol/SKILL.md`(6 leakage 維度 + shift(1) compliance)
  - `.claude/skills/ml-pipeline-maturity-audit/SKILL.md`(Foundation / Skeleton / Shadow / Canary / Production)
  - `.claude/skills/math-model-audit/SKILL.md`(HMM/GARCH/VPIN 黑名單 source of truth)
  - `.claude/skills/walk-forward-validation-protocol/SKILL.md`(QC alpha 顯著性協議)
- Existing IMPL refs(不改;Wave 2 W2-C 接 import):
  - `program_code/ml_training/optuna_optimizer.py`(TPE within-strategy)
  - `program_code/ml_training/edge_estimate_validation.py:_walk_forward_oos_values`(purge gap walk-forward)
  - `program_code/ml_training/quantile_trainer.py:get_embargo_config`(per-strategy embargo)
  - `helper_scripts/cron/ml_training_maintenance_cron.sh`(bash wrapper 範式)
  - `helper_scripts/cron/ml_training_maintenance.py`(Python entry 範式)
- Memory: `project_2026_05_09_ml_training_cron_weekly`(hybrid daily + weekday=6 gate cadence baseline)
- Memory: `feedback_v_migration_pg_dry_run`(Linux PG empirical mandatory)
- Memory: `feedback_indicator_lookahead_bias`(rolling stat shift(1) leak-free)
- Memory: `feedback_demo_over_paper_for_edge`(training filter 不混 paper)

---

## §9 W1-D Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| MIT(W1-D) | 本 spec drafted(per Sprint 2 dispatch packet §1.2 Wave 1 W1-D track) | 2026-05-25 | ✅ DRAFTED |
| PA | Sprint 2 dispatch packet §4 source verified | 2026-05-25 | ✅ source-aligned |
| Operator | PM 拍 PM #2 decision (a) — V111 spec @ Sprint 1A-γ 先;Stream C Wave 1 後端不阻 | 2026-05-25 | ✅ APPROVED |
| E1(W2-C) | W2-C E1 IMPL chain pending — 等 1A-γ V111 spec FINAL + 本 spec 提供 implementation hint | Sprint 2 Wave 2 | 🟡 PENDING |
| E2(W2-E) | W2-E review pending — adversarial review IMPL DONE 後三方 grep gate | Sprint 2 Wave 2 | 🟡 PENDING |
| E4(W2-E) | Mac cargo test --workspace --release + pytest 5 textbook regression | Sprint 2 Wave 2 | 🟡 PENDING |

---

**Report END**

MIT AUDIT DONE: srv/docs/execution_plan/2026-05-25--m10_tier_a_productionize_backend_spec.md
