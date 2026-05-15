# W-AUDIT-8b — Strategist Scope Reframe + AlphaSourceRegistry（R-2 IMPL Spec）

> **2026-05-15 PM note**：This file is a legacy R-2 spec using the old
> `W-AUDIT-8b` name. Current `TODO.md` uses `W-AUDIT-8b` for A4-A Funding
> Skew Directional strategy, while R-2 Strategist Alpha Source Orchestrator is
> tracked as `W-AUDIT-8e`. Treat this document as the R-2 / `W-AUDIT-8e`
> architecture spec unless PM explicitly reassigns IDs.

**Wave 名稱**：W-AUDIT-8b "Strategist Alpha Orchestrator"
**對應 ARCH-04 amendment**：R-2（ADR-0021 Accepted 2026-05-09）
**起草者**：PA（Project Architect）
**日期**：2026-05-09
**對齊上游**：
- `docs/adr/0021-alpha-source-architecture-upgrade.md`（Accepted 2026-05-09）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` §1 Push Back 2 修正
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` Layer 3.2 + Layer 4 R-2
- `docs/decisions/EX-05_..._V2.md`（Hypothesis 既有定義）
- `docs/decisions/DOC-04_..._V2.md` §L1-L5 Analyst 進化階梯
**讀者**：Operator / PM / E1 / E2 / E4 / AI-E / QC
**前置**：W-AUDIT-8a Phase A 完成（`Strategy::on_tick(ctx, surface)` 簽名 + AlphaSurface struct + AlphaSourceTag enum 已 land）
**並行**：W-AUDIT-8a Phase B/C/D；W-AUDIT-9（不衝突）；W-AUDIT-3b/4b 可並行
**生效範圍**：Python `strategist_agent.py` + 新增 `alpha_source_registry.py` + `propose_hypothesis.py` + Analyst L2-L3 接線；**不**改 Rust strategies trait、**不**改 GovernanceHub / Decision Lease / SM-04 ladder

---

## §0 命名 + 編號 alignment（避免歧義）

PA fix plan v2 §5 表把 R-2 對應 W-AUDIT-8e；TODO.md v18 排序把 R-2 對應 W-AUDIT-8c；本 spec 使用 PM 任務指定的 W-AUDIT-8b 命名（與 R-2 直接對齊）。

| 來源 | R-2 對應 wave | 備註 |
|---|---|---|
| ADR-0021 | R-2 | architectural amendment 級命名（不綁 wave 編號） |
| PA fix plan v2 §5 | W-AUDIT-8e | fix plan v2 用「8a Foundation → 8b/c/d alpha candidates → 8e/f/g architectural amendments」schema |
| TODO.md v18 | W-AUDIT-8c | 「8a Foundation → 8b R-1 IMPL → 8c R-2 → 8d R-3 ...」schema |
| **本 spec** | **W-AUDIT-8b** | PM 任務指定 b/c/d/e 對應 R-2/3/4/5 |

對 IMPL 端：以本 spec 為 SoT；TODO.md v18 dispatch table 在 land 時用 W-AUDIT-8b 命名同步。

---

## §1 Wave 範圍 + Goal

### 1.1 North Star（修正版，Push Back 2 接受）

把 Strategist Agent 從 **「5 策略 weight 微調器」（`_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded dict）** 升級為 **「Alpha Source Orchestrator + Hypothesis Proposer」**：

- Strategist 維護 `AlphaSourceRegistry`（active / observing / deprecated / sunset 4 stage）
- Strategist 觀察 `surface.regime` + Analyst L2 模式輸出，**proposes Hypothesis**（不直接出 TradeIntent）
- Hypothesis 流給 Analyst L3 進實驗 pipeline（W-AUDIT-8c R-3 是真正 Hypothesis Pipeline IMPL）
- 保留 Strategist 的「5 策略參數調整」職責（已合 spec EX-06 + AMD-2026-05-09-02 §3 wide skill），不違反 Push Back 2

**修正點（vs PA fix plan v2 §0 + Push Back 2）**：
- **不**將 Strategist reframe 為「Alpha Source Orchestrator 唯一職責」 — 那違反 EX-06 V1 「策略匹配 / 參數優化 / 組合分配」的 spec
- Strategist scope = **既有調參職責 + 新加 alpha-source orchestrator + propose 通道** 三件事並存
- `_REGIME_STRATEGY_PREFERENCES` 4×5 dict **不全廢**，改為「Sharpe-by-regime 動態加 hardcoded 為 prior」（既保 backward compat 也加 evolution path）

### 1.2 Wave 範圍邊界

**本 wave 含**：
1. Python `app/agent_runtime/alpha_source_registry.py` 新模組（4-stage state machine）
2. `strategist_agent.py` 加 `propose_hypothesis()` 方法（產出 Hypothesis spec，發給 Analyst）
3. `_REGIME_STRATEGY_PREFERENCES` 從 hardcoded 4×5 dict 改為「dynamic Sharpe-by-regime + hardcoded prior fallback」
4. AlphaSourceRegistry 接 W-AUDIT-8a `AlphaSourceTag` enum 為 SoT
5. 新增 V### migration `learning.alpha_source_registry`（state + lifecycle metadata）
6. Strategist → Analyst MessageBus topic 新增（`alpha.hypothesis.proposed`）+ payload schema
7. Operator GUI 加「Alpha Source Inventory」view（read-only，A3 review）

**本 wave 不含**（明確邊界）：
- Hypothesis state machine 全 IMPL（→ W-AUDIT-8c R-3 IMPL）
- Per-alpha-source Live Promotion Gate（→ W-AUDIT-8d R-4）
- Layer 2 cloud reasoning 解封（ADR-0020 維持 manual + supervisor-only）
- AlphaSourceRegistry CRUD GUI write（read-only only）
- Analyst L4-L5 IMPL（dormant by ADR-0020 spec）

### 1.3 為什麼這是 Tier-1 leverage（修正版）

當前 Strategist 在 `surface.funding_curve` 是 `Some` 時會看到 25 symbols funding panel，但 **沒有任何代碼路徑會基於此 propose 新策略**。Strategist 的決策邊界 stop at「對 5 既存策略加減 weight」。

R-2 解這個 leverage 缺口：把 Strategist 的觀察輸出**接到 Analyst L3 hypothesis pipeline**。從此「Strategist 觀察到 funding skew dispersion 1.8σ → propose 假設『funding skew spread 在 ranging regime 有 alpha』」是合法 runtime 路徑，**不是文檔願景**。

---

## §2 接口設計

### 2.1 `AlphaSourceRegistry` 4-stage state machine

```python
# app/agent_runtime/alpha_source_registry.py
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List

class AlphaSourceStage(str, Enum):
    """Alpha source 生命週期 4 stage"""
    SUNSET = "sunset"           # 已退役（funding_arb v2 退役後狀態）
    DEPRECATED = "deprecated"   # 標記廢棄但仍 dispatch（避免 sudden drop）
    OBSERVING = "observing"     # 新孵化中，accumulate evidence
    ACTIVE = "active"           # 已通過 evidence gate，正式 dispatch

@dataclass(frozen=True)
class AlphaSourceMetadata:
    tag: str                          # AlphaSourceTag.lowercase（與 Rust enum 對齊）
    stage: AlphaSourceStage
    declared_strategies: List[str]    # 哪些 strategy ctor declare 此 tag
    promotion_evidence_n: int         # 多少 demo trial 樣本
    promotion_evidence_sharpe: Optional[float]
    promoted_at_ms: Optional[int]
    deprecated_at_ms: Optional[int]
    sunset_at_ms: Optional[int]
    last_dispatched_ms: Optional[int]
    notes: str

class AlphaSourceRegistry:
    """Strategist 維護的 Alpha Source 清單 + lifecycle 治理"""

    def list_active(self) -> List[AlphaSourceMetadata]:
        """當前可 dispatch 的 alpha sources"""

    def list_observing(self) -> List[AlphaSourceMetadata]:
        """孵化中（樣本不足 graduate ACTIVE）"""

    def transition_stage(
        self,
        tag: str,
        from_stage: AlphaSourceStage,
        to_stage: AlphaSourceStage,
        reason: str,
        evidence_summary: dict,  # DSR / PBO / Sharpe / n
    ) -> bool:
        """
        4-stage transition:
            OBSERVING → ACTIVE （需 evidence gate PASS）
            ACTIVE → DEPRECATED （手動 / Guardian veto）
            DEPRECATED → SUNSET （N 天後 auto-promote）

        強制：transition 必寫 PG `learning.alpha_source_registry` audit row
        """

    def query_by_strategy(self, strategy_name: str) -> List[AlphaSourceMetadata]:
        """查詢策略 ctor declare 的 alpha sources lifecycle 狀態"""
```

**設計約束**：
- AlphaSourceTag enum 是 Rust 端 SoT（W-AUDIT-8a §2.1 已定義），Python 端 Registry 用 `tag: str` lowercase snake_case 對齊
- `transition_stage` 必須 atomic（advisory xact lock + INSERT history row + UPDATE current state 三步在 one transaction）
- 任何 stage transition 必對應 PG row：`learning.alpha_source_registry_history`（V### migration 新增）
- Registry 啟動時從 PG load active state + history replay 重建 in-memory cache

### 2.2 `AlphaHypothesis` payload schema（Strategist→Analyst）

```python
# app/agent_runtime/alpha_hypothesis.py
@dataclass(frozen=True)
class AlphaHypothesis:
    """Strategist 提案，送 Analyst L3 實驗"""
    proposer: str = "strategist"
    proposed_at_ms: int
    statement: str                    # 「ranging regime + funding skew > 1.5σ → spread alpha」
    null_hypothesis: str              # 「funding skew dispersion 對 ranging regime 無 effect」
    target_alpha_sources: List[str]   # 對應 AlphaSourceTag
    evidence_required: dict           # {n_min: 100, dsr_min: 0.7, pbo_max: 0.3}
    experiment_target_strategy: Optional[str]  # 既有 strategy 套用 / None = 新 strategy 候選
    regime_context: str               # surface.regime tag at proposal time
    audit_trace_id: str               # 對應 Strategist 的 H1 ThoughtGate trace
```

**約束**：
- Strategist `propose_hypothesis()` 必經 H1 ThoughtGate 預算 check（不浪費 model token）
- Hypothesis 送出後 Strategist **不**等回應（async loop）；verdict 由 Analyst 寫回 PG `learning.hypotheses` + Strategist 下次 cycle 讀
- W-AUDIT-8b 階段 Hypothesis 落地僅 schema + audit row；W-AUDIT-8c R-3 IMPL state machine

### 2.3 `_REGIME_STRATEGY_PREFERENCES` 演化（漸進升級）

**現況**：`strategist_agent.py:128-134` hardcoded 4 regime × 5 strategy weight multiplier。

**新設計**：
```python
# strategist_agent.py
class RegimeStrategyAffinity:
    """從 hardcoded prior 漸進升級到 Sharpe-by-regime 動態"""

    HARDCODED_PRIOR: Dict[Regime, Dict[str, float]] = {
        Regime.TRENDING_UP: {"ma_crossover": 1.2, "bb_breakout": 1.1, ...},
        # ... (既有 4×5 dict 不刪，作為 prior)
    }

    def affinity_score(
        self,
        regime: Regime,
        strategy: str,
        recent_sharpe_by_regime: Optional[float],  # learning.attribution_chain 提供
        sample_size: int,
    ) -> float:
        """
        Bayesian update:
            prior = HARDCODED_PRIOR[regime][strategy]
            if sample_size >= 30 and recent_sharpe_by_regime is not None:
                # 樣本足夠，混合 prior 與觀測
                evidence_weight = min(sample_size / 100, 1.0)
                posterior = prior * (1 - evidence_weight) + sharpe_to_multiplier(recent_sharpe_by_regime) * evidence_weight
            else:
                posterior = prior
            return posterior
        """
```

**漸進升級理由**：
- `_REGIME_STRATEGY_PREFERENCES` 4×5 dict 是 day-1 prior，刪除會破現有 wide skill adjustment 行為
- Sharpe-by-regime 觀測樣本不足（W-AUDIT-4b INSERT path 修好前 attribution_chain 0.5%）→ 必須有 prior fallback
- 升級後**不違 Push Back 2**：Strategist 仍是「調參器」，但加 evidence-aware Bayesian update

### 2.4 GUI Read-only View（A3 review）

新增 GUI tab `alpha_sources`（13→14 tab，A3 v2 NEW-7/8 已建議擴展）：
- 顯示 `AlphaSourceRegistry.list_active()` + `list_observing()`
- 每行：tag / stage / declared_strategies / promotion_evidence_n / last_dispatched_ms
- A3 review：Operator 可見當前 alpha 清單；**不可** GUI 寫（write 走 Strategist `transition_stage` async loop）

---

## §3 Deliverable（Sub-task 拆分）

| Sub-task | Owner | Person-day | 並行度 |
|---|---|---:|---|
| **R2-T1** Python `alpha_source_registry.py` 新模組 + 單元測試 | E1 | 2.0 | 並行 |
| **R2-T2** V### migration `learning.alpha_source_registry` + history table | E1 + MIT review | 1.5 | 並行 |
| **R2-T3** `strategist_agent.propose_hypothesis()` 接 H1 ThoughtGate | E1 + AI-E review | 2.0 | 串行 R2-T1 |
| **R2-T4** `RegimeStrategyAffinity` Bayesian update + 5 strategy migration | E1 + QC review | 2.0 | 並行 |
| **R2-T5** MessageBus topic `alpha.hypothesis.proposed` + payload schema | E1 + E2 IPC review | 1.0 | 並行 |
| **R2-T6** GUI tab `alpha_sources` read-only view | E1a + A3 review | 2.0 | 並行 |
| **R2-T7** Integration test（Strategist propose → Registry stage transition → MessageBus emit）| E4 | 1.5 | 串行 R2-T1..T5 |
| **總計** | | **~12 person-day（1.5 sprint）** | |

### 3.1 與 W-AUDIT-8a Phase 對齊

| W-AUDIT-8a Phase | W-AUDIT-8b 可開始時點 |
|---|---|
| Phase A 完（trait + AlphaSurface + AlphaSourceTag enum land）| ✅ R2-T1/T2/T5 可開 |
| Phase B 完（Tier 2 panel 真實 populate）| ✅ R2-T3/T4 真實有 surface 觀察 |
| Phase C 完（liquidation_pulse）| 不阻塞 R2 |
| Phase D 完（5 策略 callsite migration）| ✅ R2-T7 integration test 才完整 |

**最小起步**：W-AUDIT-8a Phase A land 後即可開 R2-T1/T2/T5（不依賴 Tier 2 panel 真實有 data）。

---

## §4 Acceptance Criteria

### 4.1 R2-T1 alpha_source_registry.py
- 4-stage state machine 完整 IMPL（OBSERVING/ACTIVE/DEPRECATED/SUNSET）
- `transition_stage()` atomic（advisory lock + INSERT history + UPDATE current）
- 單元測試 coverage ≥ 90%
- pytest `test_alpha_source_registry_*` 全 PASS

### 4.2 R2-T2 V### migration
- `learning.alpha_source_registry`（current state，1 row per tag）
- `learning.alpha_source_registry_history`（每 transition 1 row）
- Guard A/B/C 完整（CLAUDE.md §七 V### migration 規範）
- 兩次 idempotent apply 驗 PASS
- Linux PG dry-run mandatory（per CLAUDE.md §七 V055 教訓）

### 4.3 R2-T3 propose_hypothesis()
- H1 ThoughtGate 預算 check 通過才 emit
- AlphaHypothesis payload schema validation
- 對 5 個 hardcoded regime × 5 strategy 的 affinity 觀測樣本不足時 fallback prior

### 4.4 R2-T4 RegimeStrategyAffinity
- Bayesian update 在 sample_size ≥ 30 才採觀測
- prior fallback 100% 通過（樣本不足時 score == HARDCODED_PRIOR[regime][strategy]）
- 5 既存策略 affinity_score 在 sample 足夠下與 hardcoded 不偏離 ≥ 3σ（避免 dramatic shift）

### 4.5 R2-T5 MessageBus topic
- topic name `alpha.hypothesis.proposed`（與既有 `agent.*` topic 命名規範對齊）
- Payload schema 序列化/反序列化驗 PASS
- E2 IPC review sign-off

### 4.6 R2-T6 GUI tab
- `/console#alpha_sources` 路由生效
- Read-only（任何 POST/PUT/DELETE 路由不存在）
- A3 a11y review PASS（focus-visible + keyboard nav）

### 4.7 R2-T7 Integration test
- Strategist `propose_hypothesis()` → Registry `transition_stage()` → MessageBus emit 全鏈路 E2E PASS
- 7d shadow run 證 Strategist 在 surface.funding_curve `Some` 時至少 propose 1 hypothesis
- AlphaSourceRegistry 24h 內 ≥ 1 stage transition（OBSERVING → ACTIVE 或反向）

### 4.8 Wave 整體 acceptance
- ADR-0021 R-2 IMPL 完成 → ADR 更新 status 補「R-2 IMPL DONE」
- AlphaSourceRegistry 在 demo runtime 24h 觀察穩定（無 panic / no orphan transition row）
- AMD-2026-05-09-02 §3 wide skill range（current 0.50）不被本 wave 改動
- TODO.md 加入 W-AUDIT-8b 完成 status row

---

## §5 依賴關係 + Risk

### 5.1 上下游依賴

| 依賴 | 性質 | 處理 |
|---|---|---|
| W-AUDIT-8a Phase A | **Hard** prerequisite | trait 簽名 + AlphaSourceTag enum 必先 land |
| W-AUDIT-8a Phase B | Soft（observation only）| 不阻塞 IMPL，但 7d integration test 需 Phase B 真實 panel |
| W-AUDIT-8c R-3 Hypothesis Pipeline | **Forward dependency** | R-3 land 前 hypothesis 只有 audit row + MessageBus emit；R-3 land 後接 state machine |
| W-AUDIT-4b INSERT path | Soft | Sharpe-by-regime 觀測需要 attribution_chain 修復；fallback prior 保證 R-2 IMPL 不被卡 |
| ADR-0020 Layer 2 manual | **Hard invariant** | Strategist propose Hypothesis 不 escalate Layer 2，全在 L0+L1 跑 |

### 5.2 Risk + Fallback

| Risk | 機率 | Mitigation | Fallback |
|---|---|---|---|
| Strategist `propose_hypothesis()` 觸 H1 ThoughtGate 預算 cap | 中 | propose 頻率限 ≤ 1/cycle（5min）| 預算耗盡 fallback skip propose（不 throw）|
| AlphaSourceRegistry stage transition race（multi-cycle 同時改）| 低 | advisory xact lock | E2 review 必驗 |
| `_REGIME_STRATEGY_PREFERENCES` 漸進升級破壞 wide skill 行為 | 中 | sample_size 門檻 30，樣本不足 100% prior | E4 regression test 必含 sample_size=0/10/30/100 對照 |
| MessageBus topic 不與既有 agent topic 衝突 | 低 | 命名 `alpha.*` 獨立前綴 | E2 IPC review |
| GUI tab 第 14 個破 13-tab dictionary（CLAUDE.md §五）| 中 | A3 v2 NEW-7/8 已建議 13→15 tab 擴展 | CLAUDE.md §五 同次 commit 補 14-tab |

### 5.3 與 W-AUDIT-3b/9 衝突點

| 衝突 | 性質 | Mitigation |
|---|---|---|
| W-AUDIT-3b ExecutorAgent runtime smoke 與 R-2 IMPL `executor_config_cache.py` shadow_mode | **無衝突** | R-2 不碰 ExecutorAgent / executor_config_cache |
| W-AUDIT-9 T3 改 `_read_shadow_mode` stage-aware 與 R-2 IMPL | **無衝突** | R-2 在 Strategist 端，不碰 Executor |
| W-AUDIT-4b label_close_tag NULL writer fix | **正交** | R-2 用 fallback prior，不依賴 attribution_chain 修復 |
| W-AUDIT-6 bb_reversion + portfolio_var review | **正交** | R-2 不重寫策略 |

**結論**：R-2 與 W-AUDIT-3b/9/4b/6 全並行，無 commit 序衝突。

---

## §6 E2 Review Checklist

**E2 review 必查 5 點**：
1. **AlphaSourceRegistry stage transition atomicity**：advisory xact lock 真使用 + INSERT history row + UPDATE current state 在一個 transaction（grep `ROLLBACK` + `COMMIT` 對齊）
2. **AlphaSourceTag string alignment**：Python `tag: str` lowercase snake_case 與 Rust enum `Display` 完全對齊（任何 mismatch = silent bug 5+ wave 後才浮現）
3. **`_REGIME_STRATEGY_PREFERENCES` Bayesian update 沒砍 hardcoded prior**：grep 確認 `HARDCODED_PRIOR` dict 仍存在 + `affinity_score` sample_size < 30 時 100% prior
4. **propose_hypothesis() 經 H1 ThoughtGate**：grep `_thought_gate_check` 在 propose 前
5. **MessageBus payload schema 序列化驗**：unit test 覆蓋 round-trip serialize/deserialize

**E2 推回情況**：
- 任一條漏 → 推回
- AlphaSourceRegistry CRUD 端 GUI 寫路徑出現 → 推回（W-AUDIT-8b 範圍只 read-only）
- 任何 Layer 2 cloud reasoning 出現 → 推回（ADR-0020 invariant）

---

## §7 E4 Regression Checklist

**E4 必跑 4 個 regression**：
1. **5 既存策略 affinity 不偏離**：sample_size = 0 時 affinity_score == HARDCODED_PRIOR[regime][strategy]，誤差 ≤ 1e-9
2. **AlphaSourceRegistry 4-stage transition 全路徑 PASS**：OBSERVING → ACTIVE / ACTIVE → DEPRECATED / DEPRECATED → SUNSET / SUNSET（terminal）4 種 transition 各 1 個 happy path test
3. **propose_hypothesis() 7d shadow run**：demo runtime 跑 7 day，至少觀察 1 次 hypothesis emit + 1 次 stage transition；無 panic / no orphan row
4. **MessageBus payload round-trip**：100 個 random AlphaHypothesis serialize → deserialize → equality check

---

## §8 落地 Side Effect

### 8.1 CLAUDE.md §三 加入 W-AUDIT-8b row
§三 `Active Blockers` 表 W-AUDIT-8a row 後加 W-AUDIT-8b row（INACTIVE → ACTIVE 隨 Phase A land 切換）。

### 8.2 CLAUDE.md §五 14-tab 擴展
從 13 tab 升 14 tab，加 `alpha_sources`：
```
"system", "replay", "paper", "demo", "live", "strategy", "risk",
"governance", "ai", "learning", "agents", "monitoring", "settings",
"alpha_sources"  ← 新加
```

### 8.3 ADR-0021 status update
ADR-0021 R-2 IMPL DONE 時補 References section：
```
- W-AUDIT-8b R-2 IMPL spec: docs/execution_plan/2026-05-09--w_audit_8b_strategist_alpha_orchestrator_spec.md
- W-AUDIT-8b R-2 IMPL completion commit: <hash>
```

### 8.4 PA memory 更新
- 教訓：Push Back 2 self-adversarial 結果採納，避免 PA 過度斷言「Strategist 越權」；Strategist scope EX-06 既定，R-2 是擴展不是 reframe
- 經驗：Bayesian update 漸進升級 hardcoded prior 比 hard replace 更安全

---

## §9 PM 接收後動作

PM 拿到本 spec 後：
1. 確認 W-AUDIT-8a Phase A 完成時點（gate R-2 開始）
2. 派 `@E1` 並行 R2-T1/T2/T5（無依賴）
3. R2-T1/T2 完 → 派 R2-T3/T4
4. 全 sub-task 完 → 派 `@E2` review + `@E4` regression
5. PASS 後 PM Sign-off → 進 W-AUDIT-8c R-3 Hypothesis Pipeline

---

`PA DESIGN DONE: report path: srv/docs/execution_plan/2026-05-09--w_audit_8b_strategist_alpha_orchestrator_spec.md`
