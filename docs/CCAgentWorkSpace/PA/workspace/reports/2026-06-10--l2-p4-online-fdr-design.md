# L2 Advisory Mesh — P4 online-FDR research loop 技術設計（design-only, E1-READY 候選）

日期：2026-06-10 ｜ 作者：PA ｜ 狀態：**設計完成，待 MIT（M1+M2 final ratification）/ QC / operator 三點確認後 E1-READY**
基線：origin/main `13ae589f`（worktree `/tmp/wt-l2-p4`，branch `feat/l2-p4-design`）
SSOT：`L2_TODO.md` §3 P4 行 + §4 P4 驗收 + §5（M1/M2 = ENDORSED）；執行方案 §1/§2 Phase 4；設計母本 §G.1/G.1.1/G.1.2/G.2。
本設計 0 碼 / 0 migration apply / 0 DB write / 0 deploy。

---

## 0. TL;DR

P4 不是新管線——**P3b 已把 §G.2 Q3 cascade（Ollama generate → guard → novelty → 確定性 math gate → cloud survivors）整條 ship 進 `_run_hypothesize_cascade`**。P4 是把「無限測試流的統計紀律」包上去：

1. **α-wealth controller**（M1）：純函數核心（`learning_engine`，0 DB）+ PG append-only 事件帳本（V137 `research.alpha_wealth_ledger`）。debit-on-test、**φ=1.0 proportional refund 只在 demo-confirmed**、`W_0=0.10·α_target` per family、`α_i ≤ α_target/min_batch_size`。
2. **N_eff cluster**（M2）：hand-rolled average-linkage（Pearson corr>0.5 cut），單一 N_eff 同時餵 `dsr_gate`（`K_for_dsr=N_eff`）與 α-wealth 單 debit；無 variant 序列時誠實 fallback raw `k_trials`（保守向）。
3. **V132 sealer 真寫**：寫入者=既有 stage0r preflight → bridge → registry xact 鏈（**代碼已在，runtime 0 rows，三重 flag-OFF**）；P4 補 double-seal 觀測性 3 行 + activation runbook，不建第二 sealer。
4. **Q4 答案**：P4 loop 是 hypothesize cascade 的**上游守門（STAGE 3.7 wealth admission + pre-registration）+ 下游消費者（debit 記帳 + refund reconciler）**，同一條軌，非平行軌。
5. **tier-gate 現實**：orchestrator 構造默認 L1 且 `tier_flag_value=None` → hypothesize 今天**結構性 TIER_LOCKED**。P4 wire 唯讀 tier projection（fail-closed 默認 L1）；L3 真實可達性（in-memory tier 重啟歸零）是獨立 governance 缺口，**P4 全量 ship 於 dormant 之上，誠實聲明不造假 tier**。
6. **demo-confirm 資料面**：fills/round-trip 管道與量都夠（grid 3777 fills/60d）；缺的是 **debit↔demo 部署 binding**（新 operator-scope route，新檔）。
7. E1 三線並行（檔零重疊）；**全部新測試連線層隔離**（承 2026-06-10 prod 污染 RCA）。
8. **sealed-holdout 證實 = 5 條可執行證據**（§9），任一缺 gate 不過。

風險評級：**中**（邏輯改動、測試覆蓋完整的模組；不碰 GovernanceHub SM 主路徑 / lease / API schema 變更 / H0）。硬邊界 0 觸碰（§12）。

---

## 1. Grounding（事實層；全部親驗，非引 plan 文字）

### 1.1 代碼事實（file:line）

| 事實 | 位置 |
|---|---|
| Q3 cascade 已實作：generate→guard→novelty→math gate→cloud | `l2_ml_advisory_executor.py:729` `_run_hypothesize_cascade`；novelty `:817-823`；math gate `:825-831` |
| math gate stage 序 Q1→DSR→PBO→B1→leak，strictest-wins | `l2_ml_advisory_executor.py:993-1067`（`_run_math_gate`） |
| DSR K 接縫 = `gate_inputs["n_trials"]` → `compute_dsr(n_trials=...)` | executor `:1032,:1070-1088`；`dsr_gate.py:520-535`（`n_trials:int`，**接口無需破壞性變更=M2 NOTE 證實**） |
| DSR 閾值=0.95、`threshold` 參數可注入、`min_observations` DEFER | `dsr_gate.py:76`（`DEFAULT_DSR_THRESHOLD=0.95`）`:357-379,:520-526` |
| adapter 現以 AEG `k_trials` 填 `n_trials` | `l2_candidate_evidence_adapter.py:145-148` |
| adapter regime 多行無顯式選擇 → DEFER（anti-cherry-pick） | `l2_candidate_evidence_adapter.py:195-218` |
| B1 簽名（int-bar-index 契約 fail-loud；altcap=None→DEFER） | `beta_neutral_check.py:122-158` |
| reindex 純函數（ordinal-day offset） | `bar_index_reindex.py:80` |
| PBO hand-rolled 無 scipy（repo 慣例） | `pbo_gate.py:20,36`；`compute_pbo(oos_returns_per_split)` `:384-404,:480` |
| V132 schema：state ∈ sealed/opened/consumed/invalidated + 雙 UK + flags CHECK | `sql/migrations/V132__hidden_oos_state_registry.sql:81-160` |
| sealer 寫入鏈存在：stage0r→bridge→registry xact `INSERT ... 'sealed'` | `residual_stage0r_preflight.py:687`（三重 flag `:698-710`）→ `residual_hidden_oos_bridge.py:164,:398-402` → `experiment_registry.py:1067,:1113-1131` |
| double-seal 現為 **silent** `ON CONFLICT (replay_experiment_id) DO NOTHING`（無 NOTICE/log） | `experiment_registry.py:1131` |
| sealer family 慣例 = `f"{strategy}::{symbol}"` | `residual_stage0r_preflight.py:476` |
| hypothesize TOML 雙閘（enabled=false + min_tier=L3 + flag 綁 `can_generate_hypotheses`） | `settings/l2_capability_registry.toml`（hypothesize stanza） |
| tier 閘 STEP-2：`current_tier < min_tier` OR `flag and not tier_flag_value` → TIER_LOCKED | `l2_capability_registry.py:122-126` |
| orchestrator 默認 `current_tier=L1`、admission 傳 `tier_flag_value=None` | `l2_advisory_orchestrator.py:219,:580,:739-744`（無參構造 singleton） |
| runtime LearningTierGate 實例（in-memory；`export_state` 0 持久化 caller） | `paper_trading_wiring.py:376`；`learning_tier_gate.py:675`（grep export/restore 0 prod caller） |
| tier 唯讀/promote 端點已存在（operator 路徑） | `governance_extended_routes.py:289,:316` |
| demo round-trip 管道：`trading.fills` FIFO 配對 reuse | `residual_alpha_producer_db.py:586-616`（`load_round_trips`，經 `realized_edge_stats`） |
| `forward_oos` 在任何 applier = **0 hits**（B2 enforcement 待建） | grep 全 repo：僅 `edge_estimate_validation.py:116` walk-forward（語義不同） |
| α-wealth / LORD / SAFFRON = **0 hits（GREENFIELD 證實）** | grep `alpha_wealth` program_code = 0 |
| hypothesize contract 已要求 `falsification_test`（**自由字串**，非結構化三欄） | `l2_prompt_contract_registry.py:245-292` |
| guard clause A-E 結構（P4 加 clause F） | `l2_out_of_bound_guard.py:175-281` |
| 測試隔離鐵閘 v2（進程級 `_init_pool` block） | control_api `tests/conftest.py:488-534` |
| `layer2_routes.py` 已 861 行（>800 review 線；新 route 須開新檔） | `wc -l` |
| V134 append-only REVOKE role-absent 範本 | `V134__l2_calls_ledger.sql:230-238` |
| ADR-0010 Guard A/B/C + 雙 apply 冪等鐵則 | `docs/adr/0010-...md` |

### 1.2 Linux runtime 事實（2026-06-10 親查，DB=`trading_ai`）

- `learning.hidden_oos_state_registry` = **0 rows**（sealer runtime 0-write 證實；cron 僅 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` @03:17，無 STAGE0R flag/job）。
- `replay.experiments` = 38 rows；`learning.mlde_shadow_recommendations` = **21,046 rows**（sealer 候選池充足）。
- `research` schema 已存在（V125/V127 AEG 表）；**無** `alpha_wealth_ledger` / `pre_registered_hypotheses` → V137 建。
- `_sqlx_migrations` max = **136**；repo head V136 → **V137 兩端皆 free**。
- demo fills（60d）：grid_trading 3777 / ma_crossover 1518 / funding_arb 125 / bb_reversion 93；30d 全 demo = 1391。
- prod 無 `trading_ai` **role**（P1 deploy-NOTE）→ V137 REVOKE 必走 V134 同款 role-absent DO-block。

---

## 2. Q1 — α-wealth controller 模組設計（M1）

### 2.1 分層

```
[純函數核心]  program_code/learning_engine/alpha_wealth_controller.py   （0 DB / 0 I/O / 0 async）
      ↑ 常數 + 狀態轉移數學；與 dsr_gate/pbo_gate/beta_neutral_check 同住同慣例
[PG 帳本層]   control_api app/l2_alpha_wealth_store.py                  （psycopg2，append-only INSERT + SELECT SUM）
[消費點]      l2_ml_advisory_executor.py STAGE 3.7 / 3.9（§5）
[對帳/退款]   ml_training/alpha_wealth_refund_reconciler.py（cron，flag-OFF）
```

**語言判定**：Python（偏離 Rust-first 的明示理由）——P4 是 research-plane 統計紀律層，必須與已 vetted 的 `dsr_gate`/`pbo_gate`/`beta_neutral_check`（全 Python+numpy）同棧互調；零熱路徑、零交易效果、零 IPC。與 P1-P3b 既有判例一致。

**無新 runtime mutable singleton（明示偏離 execution-plan 字面）**：plan §0 要求把 `ResearchAlphaWealthController` 註冊 singleton——但 M1 NOTE 本身規定 `debit_state` 必須在 PG「not in-memory fail-safe」。設計成 **wealth 真值=PG、process 零 authoritative state**（store 層 stateless 函數），singleton 註冊義務自然消滅、stale-state 風險歸零。若 CC/E2 堅持字面，fallback=註冊一個 stateless facade（行為不變）。

### 2.2 純函數核心 API（E1-A 契約）

```python
ALPHA_TARGET_DEFAULT = 0.05      # 名目 FDR target（family_init 事件 evidence 持久化當時值）
W0_GAMMA = 0.10                  # M1: W_0 = 0.10 · α_target
PHI_REFUND = 1.0                 # M1: proportional refund（exactly self-funding）
MIN_BATCH_SIZE_DEFAULT = 10     # M1 NOTE: α_i ≤ α_target / min_batch_size（MIT ratify）
SPEND_FRACTION_DEFAULT = 0.10   # PA default α_i 序列：α_i = min(0.10·W_t, cap)（MIT ratify）
REFUND_MIN_TRADES = 30           # M1 demo-confirm bar（≠ Q1_MIN_TRADES_OOS=50：refund 帳務 bar
                                 # vs math-gate 樣本前置，docstring 並排講清——M1 NOTE 文檔義務）
MIN_FORWARD_OOS_DAYS = 21        # B2（posture-independent 常數，唯一定義點）

def init_family_wealth(alpha_target: float = ALPHA_TARGET_DEFAULT, gamma: float = W0_GAMMA) -> float
def assign_alpha_i(balance: float, *, alpha_target: float, min_batch_size: int,
                   spend_fraction: float) -> float | None      # None ⇒ 本 slot 不可測
def can_test(balance: float, alpha_i: float) -> bool           # G.1.1：W−α_i 會 ≤0 ⇒ False
def refund_amount(alpha_debited: float, phi: float = PHI_REFUND) -> float
def dsr_threshold_for(alpha_i: float, *, floor: float = 0.95) -> float   # max(floor, 1−α_i)
def demo_confirm_verdict(*, n_trades: int, stage0r_green: bool, demo_net_bps: float,
                         forward_oos_days: int) -> Literal["confirmed","failed","pending"]
```

`demo_confirm_verdict` 語義（M1 G.1.1 直譯）：
- `confirmed` ⇔ `n_trades≥30` AND `stage0r_green` AND `demo_net_bps≥0` AND `forward_oos_days≥21`（四條全滿足）。
- `failed` ⇔ `n_trades≥30` AND（`demo_net_bps<0` OR NOT `stage0r_green`）——樣本足且結論性壞。
- 其餘（含 n_trades<30）= `pending`（債留著，back-pressure 即設計意圖；G.1.1:1169-1172）。

**α_i ↔ DSR 閾值 mapping（MIT 在 P4 sign-off 拍板，兩案皆滿足 §4 驗收字面）**：
- **Option B（PA 推薦）**：math gate DSR stage 用 `threshold = max(0.95, 1−α_i)`——test level 真實生效、wealth 越枯 bar 越逼近 1（自然 throttle）、**單調只嚴不鬆**（0.95 floor 不可降，root principle 5/6）。接點=`_run_dsr_stage` 增 optional `threshold` 透傳 `compute_dsr(threshold=...)`（`dsr_gate.py:520-526` 已有參數，零 dsr_gate 改動）。
- Option A（fallback）：α-wealth 純記帳/admission，DSR 閾值恆 0.95。實作最小但「test level α_i」變名目（FDR 保證詮釋歸 MIT）。

### 2.3 V137 migration — `research.alpha_wealth_ledger` + `research.pre_registered_hypotheses`

單一 migration（兩表同為 greenfield CREATE、同 research-plane、無 ALTER 既有表、無未決反射 → 不重演 P1 拆 V136 的理由）。**Guard A/B/C per ADR-0010 + 雙 apply 冪等 + Linux PG dry-run（`feedback_v_migration_pg_dry_run`）皆 mandatory**。REVOKE 全套走 `V134:230-238` role-absent DO-block（prod 無 `trading_ai` role 的 NOTICE 分支）。

```sql
-- 表一：append-only 事件帳本（banking-ledger 式；debit_state 由事件導出 = M1「debit_state 在 PG」的落點）
CREATE TABLE IF NOT EXISTS research.alpha_wealth_ledger (
    event_id      BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    family_id     TEXT NOT NULL,            -- = capability_id || ':' || primary_axis（§2.4）
    capability_id TEXT NOT NULL,
    signal_axis   TEXT NOT NULL,            -- primary axis（enum 字彙=context available_signal_axes）
    event_type    TEXT NOT NULL CHECK (event_type IN
                    ('family_init','debit','refund','debit_failed','operator_adjustment')),
    debit_id      TEXT,                     -- 一次 test 的群組鍵（debit/refund/debit_failed 必填）
    amount        NUMERIC(14,10) NOT NULL,  -- init/refund/上調 >0；debit/下調 <0；debit_failed =0
    alpha_i       NUMERIC(14,10),           -- debit 事件必填（名目 test level）
    n_eff         INTEGER,                  -- M2：debit 事件必填，>=1（max(1,N_eff) guard）
    k_for_dsr     INTEGER,                  -- M2：必 = n_eff（單一 N_eff 餵兩機制的審計欄）
    pre_reg_id    BIGINT,                   -- → research.pre_registered_hypotheses（debit 必填）
    demo_strategy TEXT, demo_symbol TEXT, demo_deployed_at TIMESTAMPTZ,  -- binding（§7）
    evidence      JSONB NOT NULL DEFAULT '{}'::jsonb,   -- alpha_target/gamma/phi 當時值、對帳細節
    actor_id      TEXT NOT NULL,
    CONSTRAINT awl_amount_sign_chk CHECK (
        (event_type='family_init' AND amount>0) OR (event_type='debit' AND amount<0)
        OR (event_type='refund' AND amount>0) OR (event_type='debit_failed' AND amount=0)
        OR (event_type='operator_adjustment')),
    CONSTRAINT awl_debit_fields_chk CHECK (
        event_type<>'debit' OR (alpha_i IS NOT NULL AND n_eff>=1 AND k_for_dsr=n_eff
                                AND pre_reg_id IS NOT NULL AND debit_id IS NOT NULL))
);
-- 冪等/反重複（記帳正確性的 DB 層鐵閘）：
CREATE UNIQUE INDEX IF NOT EXISTS awl_one_init_per_family   ON research.alpha_wealth_ledger (family_id) WHERE event_type='family_init';
CREATE UNIQUE INDEX IF NOT EXISTS awl_one_debit_per_id      ON research.alpha_wealth_ledger (debit_id)  WHERE event_type='debit';
CREATE UNIQUE INDEX IF NOT EXISTS awl_one_refund_per_debit  ON research.alpha_wealth_ledger (debit_id)  WHERE event_type='refund';
CREATE UNIQUE INDEX IF NOT EXISTS awl_one_fail_per_debit    ON research.alpha_wealth_ledger (debit_id)  WHERE event_type='debit_failed';
CREATE INDEX IF NOT EXISTS awl_family_created ON research.alpha_wealth_ledger (family_id, created_at DESC);
-- balance = SELECT COALESCE(SUM(amount),0) WHERE family_id=...（無物化 running balance，審計純淨）
-- debit_state 視圖（M1 驗收字面落點）：
CREATE OR REPLACE VIEW research.alpha_wealth_debit_state AS
SELECT d.debit_id, d.family_id, d.pre_reg_id, d.alpha_i, d.n_eff, d.created_at AS debited_at,
       CASE WHEN r.debit_id IS NOT NULL THEN 'confirmed'
            WHEN f.debit_id IS NOT NULL THEN 'failed' ELSE 'pending' END AS debit_state
FROM research.alpha_wealth_ledger d
LEFT JOIN research.alpha_wealth_ledger r ON r.debit_id=d.debit_id AND r.event_type='refund'
LEFT JOIN research.alpha_wealth_ledger f ON f.debit_id=d.debit_id AND f.event_type='debit_failed'
WHERE d.event_type='debit';

-- 表二：pre-registration（immutable；修訂=新 row + supersedes 血緣，永不 UPDATE）
CREATE TABLE IF NOT EXISTS research.pre_registered_hypotheses (
    pre_reg_id    BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    family_id     TEXT NOT NULL, capability_id TEXT NOT NULL, signal_axis TEXT NOT NULL,
    source_l2_reply_id TEXT,                 -- D3 provenance（V134 ledger 鏈）
    spec_jsonb    JSONB NOT NULL,            -- {statement, mechanism, signal_axes_used,
                                             --  falsification_test:{null_hypothesis,test_statistic,reject_condition}}
    spec_sha256   TEXT NOT NULL CHECK (spec_sha256 ~ '^[0-9a-f]{64}$'),   -- canonical_sha256（與 bridge 同算法）
    supersedes_pre_reg_id BIGINT REFERENCES research.pre_registered_hypotheses(pre_reg_id),
    actor_id      TEXT NOT NULL,
    CONSTRAINT prh_falsification_chk CHECK (
        spec_jsonb->'falsification_test' ? 'null_hypothesis'
        AND spec_jsonb->'falsification_test' ? 'test_statistic'
        AND spec_jsonb->'falsification_test' ? 'reject_condition')
);
CREATE UNIQUE INDEX IF NOT EXISTS prh_family_spec_uk ON research.pre_registered_hypotheses (family_id, spec_sha256);

-- 兩表 + 視圖：REVOKE UPDATE, DELETE FROM PUBLIC + role-absent DO-block（V134 範本）
```

### 2.4 debit/refund 狀態機（φ=1.0）與 family 定義

```
 (test 完成 verdict∈{pass,fail})            (reconciler: demo_confirm_verdict)
        INSERT debit ──────────► pending ──┬──► confirmed：INSERT refund(+φ·|debit|)（φ=1.0）
        (W ← W − α_i)                      ├──► failed   ：INSERT debit_failed(0)（wealth 留 spent）
                                           └──► pending  ：不動（n_trades<30 / forward<21d）
 math gate verdict = DEFER ⇒ 不 INSERT debit（test not conducted；seam 記 deferred_no_debit）
```

- **debit 時機 = math gate 渲染 pass/fail 的那一刻**（test 被真正執行）。DEFER=證據不足、test 未執行、無 discovery 鑄造可能 → 不扣（否則資料稀缺把 family 扣破產卻一次 test 都沒做）。**[MIT ratify #3]**。
- **family = `capability_id:primary_axis`**。hypothesis 必須宣告 `primary_axis ∈ signal_axes_used`（guard clause F 一併驗）；**不用 axes 組合當 family**——有限軸的組合爆炸=「開新 family 鑄新 W_0」的 wealth-inflation 攻擊面。配 family cardinality healthcheck（維度衛生慣例）。**[MIT ratify #4]**。
- in-flight 債照 G.1.1 不還；refund 唯一性由 partial unique index 在 DB 層封死（應用層 bug 不可能 double-refund）。

---

## 3. Q2 — N_eff cluster（M2）

### 3.1 模組

`program_code/learning_engine/n_eff_cluster.py`（純函數，hand-rolled numpy——`pbo_gate.py:20` 同款「避 scipy 硬依賴」慣例；scipy 在 repo 僅 optional-fallback 用法）：

```python
def n_eff_average_linkage(
    variant_returns: Sequence[Mapping[int, float]],   # int-bar-index 契約（與 B1 同；reindex 上游做）
    *, corr_cut: float = 0.5,                          # M2: Pearson corr > 0.5 ⇒ 同 cluster
    min_overlap_bars: int = 20,
    max_variants_per_cluster: int = 25,                # M2 NOTE anti-abuse
) -> NEffResult   # {n_eff:int>=1, clusters:list[list[int]], reasons:list[str]}
```

- average-linkage 聚合：距離 = 1−corr；合併條件=兩 cluster 平均相關 > 0.5。O(M³) 對 M≤~50 充分。
- **`max(1, N_eff)` guard**（M2 NOTE；空/單一輸入 → n_eff=1，K=0 永不可能流向 `compute_dsr` 的 `n_trials<1` raise，`dsr_gate.py:421`）。
- **overlap 不足兩兩對 → 視為不相關（各自獨立 trial）**：無法證明相關 ⇒ 不合併 ⇒ N_eff 偏大 ⇒ DSR 扣更兇、wealth 扣更多 = 保守方向。**[MIT ratify #5]**。
- **cluster 超 cap**：超過 `max_variants_per_cluster` 的 cluster 計為 `ceil(size/cap)` 個 effective trials（防「千變體藏一桶付一次債」）。**[MIT ratify #6]**。

### 3.2 與現 dsr_gate K 參數的接縫（零破壞）

- 接點唯一：`l2_candidate_evidence_adapter.py:145-148`。現規則 `gi["n_trials"] ← k_trials`。P4 改為：
  evidence 含新 optional `variant_returns`（list of series）→ reindex → `n_eff_average_linkage` → `gi["n_trials"] = n_eff`（+ `gi["n_eff_source"]="avg_linkage_corr_gt_0p5"`）；
  缺 series → 保留 `k_trials` + reason `n_eff_unavailable_raw_k_trials`（raw M 過度 deflate=保守；G.1.2 自己說 over-states rigor on duplicates 是「對 duplicates 過嚴」的方向）。
- 事實（2026-06-10 owed 設計已證）：**AEG candidate evidence v1 無 per-variant daily series** → 上線初期幾乎全走 raw-K fallback。N_eff 機制照 B1-altcap 模式 ship：確定性機器 + 誠實 fallback + 契約預留；series 供應是 AEG evidence v2 / Rust replay variant series（`replay_runner.rs` T2 註解）未來工作，**嚴禁從標量合成序列**（常數序列 corr 未定義/退化 → N_eff 假縮 → 比 fallback 危險）。
- **單 debit 合約**（G.1.2）：一次 math-gate 完成 test（= adapter 單 evidence row 經 gate）⇒ 恰一筆 debit 事件，且該事件 `n_eff` 與 DSR 消費的 `n_trials` **同值同源**（DB CHECK `k_for_dsr=n_eff` + E4 golden test 斷言「同 run 內 compute_dsr 收到的 n_trials == ledger debit.n_eff」）。`dsr_gate` 本體零改動（M2「no breaking change」已 ground `:520-535`）。

---

## 4. Q3 — V132 sealer 真寫接線

### 4.1 寫入者與時機（結論：不建第二 sealer）

**寫入者=既有鏈**：`run_residual_stage0r_preflight`（`residual_stage0r_preflight.py:687`）→ `register_residual_candidate_experiment`（bridge `:164`，4 道 leak guard）→ `run_register_in_pg_xact` → `_persist_hidden_oos_state_registry`（`experiment_registry.py:1067`）xact 內 `INSERT ... state='sealed'`。**代碼完整、已測、含 V132 全 CHECK 前置守衛；runtime 0 rows 唯因三重 flag-OFF + cron 未掛**（§1.2）。在 V132 雙 UK（one-row-per-experiment + family/split）語義下建第二個 L2 專屬 sealer = 兩 producer 撞 UK 慣例 → 否決。

**時機**：(a) cron——`ml_training_maintenance` 註冊 flag-gated job（不進 DEFAULT_JOBS；`OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1` + `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` 才跑），off-peak 對齊 03:17 慣例；(b) operator one-shot（單行 shell，runbook 附）。**activation 本身 operator-gated**（評估後開 flag），P4 交付=接線+runbook+觀測性，不替 operator 開閘。

**P4 唯一代碼 delta（~3 行，surgical）**：`_persist_hidden_oos_state_registry` 在 `cur.execute` 後檢 `cur.rowcount==0` → `logger.warning("hidden_oos double-seal skipped (already sealed): experiment_id=%s family=%s", ...)`（執行方案 folded MEDIUM「ON CONFLICT 須可觀測」；現為 silent DO NOTHING `:1131`。回傳值不變——stage0r 冪等重跑是設計行為，不可把重複當 error）。注意：此函數在 residual producer 生產鏈上（cron flag-ON），log-only 改動，E2 確認 psycopg2 `rowcount` 在 conflict-skip 時=0 的語義。

### 4.2 pre-registration immutable 的 enforce（三層）

1. **DB 層**：`research.pre_registered_hypotheses` append-only（REVOKE UPDATE/DELETE + role-absent 分支）；修訂=新 row + `supersedes_pre_reg_id`（血緣保留，AMD-callout 慣例，不刪不改）。
2. **Hash 層**：INSERT 時 `spec_sha256 = canonical_sha256(spec_jsonb)`（**與 bridge `_canonical_sha256` byte-identical 算法**：sort_keys/separators/ensure_ascii，`residual_hidden_oos_bridge.py:103-114`——跨表比對才不誤判）。
3. **消費層**：executor math gate 前重算「正要被測的 spec」canonical hash，≠ 註冊 hash → **DEFER `pre_registration_mismatch`**（post-hoc spec mining 的確定性封堵=QC sign-off 點）。
4. **結構化 falsification_test**：現 contract 是自由字串（`l2_prompt_contract_registry.py:278-279`）→ P4 bump `ml_advisory.hypothesize.v2`（template+schema 要求 `falsification_test:{null_hypothesis,test_statistic,reject_condition}` 三欄非空）+ guard **clause F** 驗三欄（沿 A-E 結構 `l2_out_of_bound_guard.py:215-281`）+ V137 表二 JSONB CHECK 兜底。v1 契約保留（D3 歷史 row 引用不可變）；TOML stanza `prompt_contract_ref` 同步指 v2。

---

## 5. Q4 — Q3 cascade 與 hypothesize cascade 的關係 + 調用流程

**判定：同一條軌。** P3b `_run_hypothesize_cascade`（executor `:729`）就是設計母本 §G.2「Q3 research pipeline LLM cascade」的實作。P4 loop 既非平行軌也不只是下游消費者——它是**同一 cascade 的上游守門 + 下游記帳**：

```
trigger → orchestrator admission（§F.1 dedup→debounce→coalesce→budget→tier/posture；P4 tier_provider 真值化）
  → executor _run_hypothesize_cascade：
      STAGE 1   Ollama screen（M4 calibration 既有）
      STAGE 2   Ollama generate（checked-in template；contract v2 結構化 falsification）
      STAGE 3   guard（clause A-E + 新 F：primary_axis + falsification 三欄）
      STAGE 3.5 novelty dedupe（既有 :817-823；= §G.1 novelty gate 成員，P4 零結構改動）
   ★  STAGE 3.6 pre-registration（INSERT research.pre_registered_hypotheses；得 pre_reg_id + spec_sha256）
   ★  STAGE 3.7 wealth admission（load balance（PG SUM）→ assign_alpha_i → can_test？
                 false → DEFER reason alpha_wealth_exhausted：不跑 math gate、不 debit、seam 記錄）
      STAGE 4   math gate（既有 :825-831 + P4 注入：n_trials=N_eff（§3.2）、
                 threshold=dsr_threshold_for(α_i)（Option B 時）、sealed-boundary clip（§9.4））
   ★  STAGE 4.5 記帳（verdict∈{pass,fail} → INSERT debit(pending)；DEFER → deferred_no_debit）
      STAGE 5   cloud interpret survivors（既有；只 pass 花 cloud——cost 紀律不變）
      sink      agent.lessons inert backlog（既有；晉升 demo_stage1=expand=MANUAL 不變）
  [異步閉環] refund reconciler（cron flag-OFF）：pending debit × demo binding →
      demo_confirm_verdict（30 trades / 0R green / net≥0 / ≥21d）→ refund 或 debit_failed；
      failed → 順手 persist dead_mode lesson（英文主幹，餵回 STAGE 3.5 novelty=自饋失敗庫）
```

★ = P4 新增。wealth 餘額同時餵 prompt context `alpha_wealth_remaining`（設計 §E 既留鍵位，informational）。STAGE 3.7/4.5 只進 hypothesize 分支——**P3a diagnose/interpret 路徑零波及**。

---

## 6. Q5 — tier-gate L3+ 接線（誠實語義）

**現實（fact，§1.1）**：hypothesize 今天**三重 dormant**——(i) TOML `enabled=false`；(ii) `effective_autonomy` STEP-2 TIER_LOCKED（orchestrator 默認 L1 + `tier_flag_value=None`，即便 operator 開 enabled 也鎖）；(iii) runtime LearningTierGate in-memory 無持久化、重啟歸 L1。

**P4 接線 delta（讓閘「真」而非「假鎖」）**：
- orchestrator 增 injectable `tier_provider: Callable[[], tuple[LearningTier, Mapping[str,bool]]] | None`（默認 None）。admission STEP-5 前 lazy 呼叫；**fail-closed**：provider None / raise → `(L1, {})` → 行為與今日 byte-identical。
- wiring 點：`layer2_routes.py:110-112` `_get_orchestrator` lazy 注入 GovernanceHub 投影（`paper_trading_wiring.LEARNING_TIER_GATE` 的 `current_tier` + `capabilities` flags；**唯讀**，lazy import 防環）。`tier_flag_value` 由 capability 的 `tier_capability_flag` 名查 flags dict。
- **C1 鐵則不變**：P4 任何模組 0 個 `promote_tier` / autonomy-raiser 引用（grep AC）。tier 只讀不寫。

**誠實聲明（P4 全 dormant 語義）**：系統真值 tier=L1（in-memory 默認；無持久化 caller，`export_state` `:675` 0 prod consumer）→ 接線後 hypothesize 依然 TIER_LOCKED，**這是正確行為非缺陷**。L3 真實可達（L2 跑 2+ 週 + 3 confirmed patterns + 跨重啟持久化）是獨立 governance 工作，**不在 P4 範圍、不為 P4 造假**：E4 測試以注入 fake provider 驗閘邏輯，prod 不 promote。P4 因此可以全量 merge+deploy 而行為中性——與 P1-P3b dormant 部署慣例一致。activation 序（全 operator-gated）：tier 持久化/晉升 → TOML enabled → cron flags。

---

## 7. Q6 — demo-confirm bar 資料依賴（n_trades≥30 等）

**夠不夠？管道與量：夠。缺一塊 binding，P4 補。**

- **n_trades**：`load_round_trips`（`residual_alpha_producer_db.py:586`，reuse `realized_edge_stats` FIFO 配對+扣費）讀 `trading.fills` demo。量（§1.2）：grid 3777 fills/60d、ma 1518；低頻 funding_arb 125/60d（≈60 RT）。→ 中高頻 cell 30 round trips 數天-數週可達；低頻 ~30-60 天。
- **green Stage 0R**：stage0r preflight 產 drar verdict + replay 註冊（`:589-622`）；候選池 21,046 mlde_shadow_recs。reconciler 以 replay/drar registry 讀 verdict（既有表，零新 schema）。
- **≥21 forward-OOS days**：= `now − demo_deployed_at` calendar 天數（B2 常數 `MIN_FORWARD_OOS_DAYS=21` 唯一定義在純核心，posture-independent）。**B2「applier 強制」的落點**：本 loop 無 auto-promote applier（晉升=MANUAL expand），故 enforcement 落在 (a) refund reconciler（唯一 deterministic applier 面）硬常數；(b) 契約條款：未來任何 auto-promote applier 必須 import 同一常數（驗收寫進 §13 AC，CC stress-test 17）。
- **缺口=debit↔demo 部署 binding**：晉升是人工動作，系統不知道「哪筆 debit 對應哪個 demo cell、何時起算」。P4 補：**新檔 `l2_fdr_routes.py`**（`layer2_routes.py` 已 861 行超 800 review 線，不再加）一條 operator-scope route `POST /api/v1/paper/layer2/fdr/bind-demo`（reuse `require_scope_and_operator` 模式 `layer2_routes.py:254`；auth 第一行；body={debit_id, demo_strategy, demo_symbol, demo_deployed_at}）→ append `operator_adjustment` 性質的 binding 事件欄位（寫進該 debit 的 binding 欄；實作=INSERT 新事件 row 帶 demo_* 欄 + debit_id，reconciler 取最新 binding）。讀端點 `GET .../fdr/wealth`（唯讀 balance/debit_state 視圖）。
- attribution 紀律：reconciler 嚴格按 binding 的 `strategy::symbol` + `ts≥demo_deployed_at` 查 fills；binding 缺 → debit 永 pending（誠實，不猜）。

---

## 8. Q7 — E1 拆分（並行軸）+ 風險 + 測試隔離鐵則

### 8.1 三線並行（檔案零重疊；可同 wave 全並行）

| 線 | 檔（全新建除註明外） | 內容 | 依賴 |
|---|---|---|---|
| **E1-A**（learning_engine 純數學） | `alpha_wealth_controller.py`、`n_eff_cluster.py` + 兩測試檔 | §2.2 純核心 + §3.1 聚類；0 DB 0 I/O | 無（簽名以本報告為契約） |
| **E1-B**（control_api app） | 改 `l2_ml_advisory_executor.py`（STAGE 3.6/3.7/4.5）、`l2_candidate_evidence_adapter.py`（N_eff seam + sealed clip）、`l2_prompt_contract_registry.py`（hypothesize v2）、`l2_out_of_bound_guard.py`（clause F）、`l2_advisory_orchestrator.py`（tier_provider）、`layer2_routes.py`（僅 `_get_orchestrator` 注入 ~6 行）；新 `l2_alpha_wealth_store.py`、`l2_fdr_routes.py` + 測試 | §5 cascade 接線 + §6 tier + §7 routes | E1-A 簽名（報告已鎖）；V137 schema（報告已鎖，可並行） |
| **E1-C**（sql + ml_training + helper_scripts） | `V137__research_fdr_tables.sql`、`ml_training/alpha_wealth_refund_reconciler.py`、`experiment_registry.py`（**僅** double-seal warning 3 行）、cron job 註冊（flag-gated）、`SCRIPT_INDEX.md` | §2.3 migration + §4 sealer delta + §7 reconciler | 無 |

E1-B 檔數偏多，可再對切 **B1**（executor+adapter+store）/ **B2**（contract+guard+orchestrator+routes）——介面以本報告鎖定，互不重疊。`l2_ml_advisory_executor.py` 現 1274 行，P4 後估 ~1450：超 800 review 線（既有事實），**2000 hard cap 內但要求 E1 報行數 + E2 評 sibling-extract 時機**（§九 headroom 慣例）。

### 8.2 測試隔離鐵則（承 2026-06-10 prod 污染 RCA，無例外）

- control_api 新測試：自動受進程級鐵閘 v2（`tests/conftest.py:488-534` block `db_pool._init_pool`）；**store/route 測試一律注入 fake conn，0 真連線**。
- learning_engine 新測試：純函數，**模組禁 import psycopg2 / db**（E2 grep AC）。
- ml_training reconciler 測試：注入 conn fake（stage0r tests 既有模式）；**禁任何 fallback 真 DSN**。Mac fail-soft 吞錯假綠 + 連得上 prod 的環境就真寫——對偶律：mock 不掩蓋邏輯 ⇔ 連線層必隔離。
- seed/SQL 類驗收（如 reconciler 落 dead_mode lesson）：INSERT 成功不算數，必以 `retrieve_lessons` 真查驗收（pg_trgm 三重對齊教訓）——放 E4 Linux 段，不放單元測試。

### 8.3 風險點（評級：中）

- 最脆弱：既有 admission 測試 mock 了 `effective_autonomy` 入參形狀——tier_provider 改動須保 default-None 路徑 byte-identical（E4 全量 layer2 家族迴歸 450+/0 fail 基線）。
- async/sync 邊界：executor async path 內 PG 呼叫一律 `to_thread`（P3b dispatch route 同款）；store 層同步 psycopg2 不得直呼於 event loop（E2 四輪對抗的 event-loop 阻塞殷鑑）。
- `experiment_registry.py` 是 residual producer 生產鏈共用檔（cron flag-ON）——E1-C 只准動 3 行 log，E2 diff 範圍審查。

---

## 9. Q8 — sealed-holdout「證實」gate 的可執行定義

P4→P5 gate（L2_TODO §3）「sealed-holdout 證實」= 以下 **5 條證據全綠**（任一缺 = gate 不過）：

1. **真寫**：Linux prod `learning.hidden_oos_state_registry` ≥1 row `state='sealed'`，由生產路徑寫入（`source='replay_experiment_register'`、actor 非測試、附 cron/one-shot 執行 log + 時間戳）；windows/embargo 過 V132 全 CHECK（INSERT 成功即證）。
2. **hash 對賬**：row `residual_alpha_report_hash` == `canonical_sha256(manifest report)` == `replay.experiments` manifest 同欄（source-contract 既有 gate 跑通，三 hash byte-identical）。
3. **double-seal 可觀測**：同 experiment 重跑 → 第二次 `rowcount=0` + warning log 出現 + 表行數不變（§4.1 delta 的落地證明）。
4. **auto-loop 盲視**：(a) grep proof——`l2_*.py` 模組對 registry **0 UPDATE/DELETE/INSERT**、adapter 只 SELECT `(family_id, window_start, state)` 邊界元資料、不 SELECT OOS 窗內任何 series；(b) E4 測試——evidence 窗尾端 > 該 family sealed `oos_start` → math gate DEFER reason `sealed_holdout_overlap`（adapter clip 新檢查，§5 STAGE 4 注入）。
5. **consumed 轉移不可由 L2 觸發**：grep proof L2 模組 0 個 state-transition 寫點；`sealed→consumed` 唯 mlde live-candidate 消費路徑（既有，P4 不碰）。

家族對齊註記：V132 `family_id = "strategy::symbol"`（`residual_stage0r_preflight.py:476`）是 cell 級；L2 wealth family 是 `capability:axis` 級——**兩個 family 體系不合併**。adapter 的 sealed-boundary 查詢按 evidence 的 cell（strategy::symbol）查 registry；查無 sealed row → 該候選無 sealed-holdout 主張（reason `no_sealed_split_for_cell`，不阻 math gate 其他 stage，但 gate-to-P5 的「證實」要求至少一條真實 cell 走通全鏈）。

---

## 10. 副作用清單（PA checklist 逐項）

1. **誰 import 被改檔**：executor ← orchestrator dispatch（P3a 分支不經 STAGE 3.6-4.5，零波及）；adapter ← 僅 dispatch route 鏈；`experiment_registry` ← residual producer cron（log-only delta）；contract/guard registry ← executor（v1 保留，additive v2）。
2. **mock 脆弱點**：admission 測試（tier 入參）、executor cascade 測試（stage 序斷言會因新 STAGE 變）——E1 必同步更新 stage 斷言而非繞過；E4 以 0-fail 基線判 regression。
3. **asyncio/threading**：新 PG 呼叫全 `to_thread`；orchestrator `_lock` 為 threading.Lock（admission 同步路徑，既有邊界不變）。
4. **API schema**：只新增 `l2_fdr_routes.py` 端點；既有 response 0 變更（前端零波及）。
5. **Rust↔Python IPC**：零接觸。
6. **TOML/契約漂移**：hypothesize stanza `prompt_contract_ref` v1→v2 必與 registry 同 commit 落（不同步=loader/contract mismatch fail-closed reject，行為=disabled，安全但要在 E4 驗）。
7. **D3 ledger 量**：每 hypothesize run 多 2-4 條 seam row（pre-reg/wealth/debit）——量級遠低於 retention 經濟性閾值（open question #1 不惡化）。

---

## 11. 降級 / rollback 路徑

| 層 | 降級行為 | rollback |
|---|---|---|
| 部署即態 | TOML enabled=false + TIER_LOCKED + cron flag-OFF + V137 表 0 rows = **行為中性**（與 P1-P3b dormant 慣例同） | 無需動作 |
| wealth store 不可達 | hypothesize **DEFER（fail-closed）** reason `alpha_wealth_store_unavailable`；P3a 路徑不受影響 | 修庫即復原；無狀態損失（真值在 PG） |
| executor 故障 | 既有 fail-safe SM（HEALTHY→…→NO_ADVICE）；worst case=NO_ADVICE=今日 baseline | `report_call_outcome` 既有復位 |
| V137 錯誤 | 表 additive、無 ALTER 既有表 → **留表停用**；schema 修正走 V138 前進式遷移（**禁改已 apply 的 V137**——sqlx hash drift 殷鑑） | flags OFF 即無讀寫方 |
| reconciler 壞帳 | reconciler 冪等（partial unique indexes 封死重複 refund/fail）；錯誤 refund 唯一修正=operator_adjustment 事件（審計留痕，不 DELETE） | flag OFF 停 cron |
| contract v2 問題 | loader fail-closed reject → capability 等效 disabled | TOML 指回 v1（v1 未刪） |

---

## 12. 硬邊界 / 16 根原則合規（CC 每 phase 覆驗基線）

- **0 觸碰**：`live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` / `execution_authority` / `system_mode` / lease trading authority（L2_TODO §6 不變量全維持；P4 新模組 grep 指紋 AC 寫進 §13）。
- 原則 1/3/4：L2 仍無 order path；proposal→確定性 gate→人工 live；wealth/pre-reg 全是 gate 的**加法**（更嚴），無任何 gate 移除。
- 原則 5/6：α_i→threshold 映射帶 0.95 floor 永不鬆；DEFER/缺資料/store 故障全收縮向。
- 原則 7：學習平面寫 research/learning schema；0 live state 寫點。
- 原則 8：append-only 雙表 + D3 seam + canonical hash 鏈=每筆 debit/refund 可重建。
- 原則 11/C1：tier 只讀；0 `promote_tier`。
- 原則 13：cloud 只花在 math survivors（cascade 序不變）；wealth 枯竭在 math gate 前短路=再省 cloud。
- 原則 14：FDR loop 全本地（Ollama+PG+純數學）；cloud 不可用 → 既有 degrade，loop 不依賴付費服務。
- AgentTool 訪問分類：新 store=受限寫（research schema append-only）；新 route=operator-scope 寫；讀面唯讀——登記於 §13 AC。

---

## 13. 驗收 AC 對照（L2_TODO §4 P4 逐條）+ sign-off 點

| §4 P4 驗收項 | 本設計落點 |
|---|---|
| M1 φ=1.0 proportional refund | §2.2 `PHI_REFUND=1.0` + §2.4 狀態機 + DB partial-unique 反重複 |
| M1 `W_0=0.10·α_target` | §2.2 `W0_GAMMA` + family_init 事件持久化當時常數 |
| M1 demo-confirm bar（30/0R/net≥0/≥21d） | §2.2 `demo_confirm_verdict` + §7 reconciler |
| M1 `debit_state` 在 PG `research.alpha_wealth_ledger` | §2.3 事件帳本 + `alpha_wealth_debit_state` 視圖（持久、非 in-memory） |
| M1 `α_i ≤ α_target/min_batch_size` | §2.2 `assign_alpha_i` cap（單元測試 AC） |
| M1 NOTE 文檔 30 vs 50 區分 | §2.2 常數 docstring 並排 + 本報告 §2.2 |
| M2 average-linkage corr>0.5 | §3.1 |
| M2 `K_for_dsr=N_eff` 單 debit | §3.2 + DB CHECK `k_for_dsr=n_eff` + E4 golden test |
| M2 `max(1,N_eff)` guard | §3.1 |
| M2 `max_variants_per_cluster` | §3.1（超 cap=ceil(size/cap) trials） |
| B2 applier 強制 `forward_oos_days≥21` | §7（reconciler 硬常數 posture-independent + 未來 applier 契約條款；CC stress-test 17） |
| V132 sealer 真寫 `state='sealed'` | §4.1（既有鏈 + 3 行觀測性 + runbook；§9.1-9.3 證據） |
| pre-registration immutable | §4.2 三層 enforce + §2.3 表二 |

**grep 指紋 AC（E2/CC）**：P4 全新模組 0 hits on `promote_tier|acquire_lease|IntentProcessor|submit_intent|live_execution_allowed|execution_authority|system_mode|OPENCLAW_ALLOW_MAINNET|authorization\.json`；executor math gate 函數內 0 LLM invocation（既有鐵則延續）；`l2_*.py` 對 hidden_oos_state_registry 0 寫點。

**MIT ratify 清單（P4 gate；M1/M2 已 ENDORSED 常數之外的 PA defaults）**：#1 α_i spend 序列（0.10·W_t）；#2 α_i→DSR threshold mapping（Option B vs A）；#3 DEFER-no-debit；#4 primary-axis family；#5 overlap 不足=不相關；#6 cluster 超 cap 算法；#7 `min_batch_size=10`。
**QC sign-off**：pre-registration hash 鏈防 spec mining（§4.2）+ sealed-holdout 5 條 gate（§9）。
**E3 sign-off**：`l2_fdr_routes.py` 寫端點 operator-scope；reconciler/sealer cron 資源隔離（off-peak + 獨立 psycopg2 conn 非 api pool + nice）。
**Operator 確認 1 條**：V137 取號 + 兩表一遷移（§2.3）；sealer activation flags 維持 operator-gated（本設計不開）。

---

## 14. E2 重點審查 3 點

1. **記帳正確性與冪等**：debit/refund/debit_failed 的 DB partial-unique 鐵閘 + reconciler 重跑冪等 + `amount` 符號 CHECK——double-refund / double-debit 必須在 DB 層就不可能，不靠應用層自律。
2. **「不鬆閘」單調性**：α_i→threshold 帶 `max(0.95,·)` floor；DEFER-no-debit 的 gaming 面（重試到 pass？→ 已由 pre-reg hash + novelty + 每次完成 test 必 debit 封堵）逐條對抗推演。
3. **sealed-boundary clip 與測試隔離**：adapter 的 `sealed_holdout_overlap` 檢查是新 leak 防線（boundary 思想實驗：evidence 窗尾 == oos_start 的半開區間語義須與 bridge `_bucket_admissible` 一致）；全部新測試 0 真連線（prod 污染殷鑑）。

---

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--l2-p4-online-fdr-design.md（worktree /tmp/wt-l2-p4，未 commit，主 session 收）
