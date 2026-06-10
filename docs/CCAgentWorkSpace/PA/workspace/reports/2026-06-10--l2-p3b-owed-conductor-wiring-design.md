# PA — L2 P3b owed-before-enable：conductor wiring（owed ①③）+ dead-modes seed 設計（owed ②）+ deployed-E2E 入口

Date: 2026-06-10 · Author: PA · Type: **DESIGN-ONLY**（無功能碼、零 migration、零 deploy、零 enable）。
Worktree: `/tmp/wt-l2-owed` · branch `fix/l2-owed`（off main，HEAD `0ce45a09` = P3b sink 測試 DB 隔離修補）。

SSOT：`L2_TODO.md` §2②（owed-before-enable 清單）；PA P3b design `2026-06-09--l2-p3b-implementation-design.md`；execution plan `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md`。

本 session read-in-full / key-span ground（每個斷言有 file:line）：`l2_advisory_orchestrator.py`（dispatch :294-375 / dispatch_and_execute :379-468）、`l2_ml_advisory_executor.py`（_run_hypothesize_cascade :729-889 / _run_math_gate :984-1058 / _run_b1_stage :1102-1129 / _run_leak_stage :1132-1147 / _check_novelty :946-981 / sink 常數 :439-444）、`beta_neutral_check.py`（int-bar-index 契約 :148-183 / compute_down_market_mask :303-336 / _is_int_bar_index :458 / _chrono_key :539 / _span_days :569-592）、`altcap_basket.py`（full）、`aeg_candidate_metrics/{builder,harness}.py`（main 版 `f3d4a29e`，full）、`layer2_critic.py`（retrieve_lessons :278-379 / persist_lessons :395-469）、`V133__agent_lessons.sql`（full）、`layer2_routes.py`（router :61 / /trigger :241-306 / operator-scope :254）、`settings/l2_capability_registry.toml`（3 stanza enabled=false）、commit `0ce45a09`（測試隔離教訓）。

---

## 0. 三個 load-bearing 偵察事實（框定全部設計）

**F1 — math gate 真實輸入契約比任務描述多 2 個 key。** `_run_math_gate`（executor :984-1058）消費 `context["candidate_returns"]` + `context["math_gate_inputs"]`{`n_trades_oos`, `observed_sharpe`, `n_trials`, `cpcv_oos_returns_per_split`, `btc_returns`, `altcap_returns`, `down_market_mask`, `bar`} **加上** leak stage（:1139-1140）讀的 `shift1_compliance_leak_free` / `is_oos_gap_leak_free`（bool|None；皆 None → DEFER `leak_precondition_unmet_no_producer`，任一 False → fail）。conductor 映射表（§B）必含這兩鍵。

**F2 — AEG-S3 候選來源「沒有」daily return series。** `aeg_candidate_metrics/builder.py`（main `f3d4a29e`）的 `build_candidate_metrics`（:249-367）輸出 **per-regime 標量 rows**：`n_days/gross_bps/cost_bps/net_bps/net_to_cost_ratio/mean_daily_bps/annualized_net_sharpe/oos_sharpe/psr_0/dsr_k/pbo/k_trials/n_independent/sample_unit/recent_90d/180d/metric_status/reject_reasons`。diagnostic harness 內部有 daily series（`multiday_trend_diagnostic/pnl.daily_returns_from_positions:155`）但 **report JSON 不輸出序列**。residual_alpha_producer 是 mlde-demo fills 通道，非 AEG 研究通道。→ owed ③ 的誠實答案：**標量可映射、序列須 evidence 契約擴充供給；缺序列 → `candidate_returns=None` → B1 stage DEFER（executor :1116-1118 `b1_inputs_missing_defer`）**。嚴禁從 `mean_daily_bps` 合成常數序列——常數 y 對因子 OLS β≈0 → **B1 偽 pass**，比 DEFER 危險一個量級（直接放行 down-beta 偽裝，重開殺 5 候選的失敗模式）。

**F3 — novelty 檢索 `WHERE symbol = %s` 必過濾、source 完全不參與 filter。** `_retrieve_lessons_sync`（layer2_critic :326-340）：filter = `symbol`（必）+ `lesson_type`（可選）+ `content %% hint`（trgm sim ≥ 0.1，SET LOCAL :345-348）；SELECT 帶 source 但 WHERE 不含。executor `_check_novelty`（:973-974）用 `sym = symbol or "ml_advisory"`（`_SINK_SYMBOL_PLACEHOLDER` :444）查 `lesson_type="dead_mode"`。→ source 撞名不影響檢索（純 provenance 標記），**但 seed 的 symbol 欄位若與檢索 symbol 不一致 = seed 永遠 miss = 死資料**。這決定 §C 的 symbol 策略 + 一個 6 行的 `_check_novelty` 修補。

---

## A. 觸發入口（設計範圍 #1）— 新 operator-scope dispatch route（選 a），cron 不做（拒 b），CLI 為 a 的薄殼（c 併入 a）

### A.1 選項評估

| 選項 | 評估 | 裁決 |
|---|---|---|
| (a) 新 route `POST /api/v1/paper/layer2/ml-advisory/dispatch` | 對齊 LANE_DIRECTION manual 哲學；reuse `require_scope_and_operator(actor,"ai_budget:write")` 既有 pattern（layer2_routes :254 /trigger 同模式）；admission/budget/D3/fail-safe 全在 api 進程內已接線（orchestrator singleton :739）；deployed-E2E = 同一條路徑 curl 即測 | **採用** |
| (b) cron/scheduler | P2 open question「auto-trigger cadence vs $2/day」未解（L2_TODO §7）；enabled=false 期間 cron 純空轉；auto-trigger 與 manual-first 哲學衝突 | **本輪不做**（P4 再議） |
| (c) helper script 直呼 orchestrator | script 在 api 進程外自建 `Layer2Engine` = 第二個 engine 實例 + cost_tracker 分裂（layer2_routes :97-105 是 lazy singleton，進程外無共享）；違反單一 dispatch 路徑 | **拒絕直呼**；operator CLI = `curl` 打 (a)，寫進 runbook 一行，不新增 script |

### A.2 Route 設計（parse → call → format；薄投影）

```
POST /api/v1/paper/layer2/ml-advisory/dispatch          （layer2_router，prefix 既有 :62）
auth: base.require_scope_and_operator(actor, "ai_budget:write")   ← reuse :254 同模式

class MlAdvisoryDispatchRequest(BaseModel):
    capability_id: str = Field(max_length=64)        # 必須 startswith "ml_advisory."（route 層驗，fail-closed 400）
    mode: str = Field(max_length=32)                 # diagnose_leak | interpret_result | hypothesize（executor 自驗 _VALID_MODES :89）
    candidate_evidence: dict | None = None           # §B 契約 v1（inline-only；見 A.4 安全）
    context: dict | None = None                      # 直接 context（與 evidence 互斥；E2E/診斷用）
    symbol: str | None = Field(default=None, max_length=30)
    strategy_name: str | None = Field(default=None, max_length=64)
    bull_only: bool = False
    coarse_subject: str = Field(default="", max_length=128)   # admission dedup key 成分
```

handler 流程：auth → 驗 capability_id 前綴 → `candidate_evidence` 給定時呼 §B adapter 產 context（缺鍵=None，誠實 DEFER 語義內建）→ `await get_l2_advisory_orchestrator().dispatch_and_execute(capability_id=…, mode=…, context=…, trigger="manual", symbol=…, …)`（orchestrator :379 簽名原樣，**零改動**）→ 投影 `DispatchResult`（admitted/admission_reason/routed_to/guard_verdict/l2_reply_id/notes）回 `_layer2_response` envelope（:115）。

**不碰的東西**：orchestrator 鐵律段（:410-416 admitted+neutral_sink+ml_advisory 三條件）原樣；registry loader、guard、math gate、B1 全不動。route 是純 caller。

### A.3 deployed-E2E 驗收路徑（兩段式，第一段零 enable 零 model call）

- **E2E-0（zero-enable，隨 deploy 即可跑，無 operator 風險決策）**：registry 3 stanza 全 `enabled=false` 之下 `POST …/dispatch {capability_id:"ml_advisory.diagnose_leak", mode:"diagnose_leak", coarse_subject:"deployed_e2e_check"}` → 預期 `admitted=false, admission_reason="capability_disabled"`（orchestrator :327-331），且 `_record_admission_seam`（:330）**真寫一條 `learning.l2_gate_seam_log` row**。驗收 = SELECT 該 seam row 存在。這證明 route→orchestrator→registry→D3 seam 的 deployed 鏈路全通，**零 model call、零 enable、零交易效果**。該 row 是真實審計事件（真 dispatch 真被拒），非測試污染，不刪。
- **E2E-1（operator-gated，一次性）**：operator 設 `ml_advisory.diagnose_leak` `enabled=true`（L1 tier、no-alpha、per-call $0.50 cap）→ dispatch 一次 → 真 Ollama screen + 真 cloud call + `agent.l2_calls` 真 row + `agent.lessons` sink row → **立刻 `enabled=false` + `POST /registry/reload`**。選 diagnose_leak 而非 hypothesize：L1/no-alpha/最小 blast radius；hypothesize 是 L3 雙閘且其 enable 是 owed 清單收齊後的獨立 operator 決策（安全鐵則維持）。
- E2E-0 寫進 E1-B 的 Linux 驗收；E2E-1 標 operator-gated（L2_TODO §2 owed 對應項）。

### A.4 安全（E3 視角預答）

`candidate_evidence` **inline-only**（不收 server path → 零 path traversal 面；operator 用 `curl -d @evidence.json`）。body 上限：FastAPI 默認 + daily_returns 730 天 ≈ 30KB，遠低於限制。write-auth：operator-scope（E3-E1 既有結論：dispatch 是 state-change 類 write）。dispatch 本身的開銷護欄 = 既有 admission（dedup/debounce/budget $2/day 硬閘，orchestrator :488-499）——route 不另造預算邏輯。

---

## B. producer→math_gate_inputs 轉換層（owed ③）

### B.1 放哪：新模組 `app/l2_candidate_evidence_adapter.py`（control_api app/，executor sibling）

非 orchestrator 內 helper 的理由：orchestrator 是 admission/routing SM（760 行），混入資料 munging 增其面積且難純測；獨立模組 = 純函數可 synthetic 測（與 beta_neutral_check 同 posture），未來 P4 cron caller 可 reuse。內部兩層分離：

```python
# 純函數層（0 DB 0 IO；單測主體）
def build_math_gate_context(evidence: dict, *, factors: FactorBundle | None) -> tuple[dict, list[str]]:
    # 回 (context, reasons)。context = {"candidate_returns": …|None, "math_gate_inputs": {…}}
    # 缺值一律 None（誠實 DEFER），reasons 記每個缺口供 route notes/D3。

# DB 層（read-only SELECT；Linux smoke 對象）
@dataclass
class FactorBundle:
    btc_returns: dict | None          # market.klines BTCUSDT 1d → daily return（date key）
    altcap_returns: dict | None       # altcap_basket.build_altcap_returns(...).returns（date key；空→None）
    down_market_mask: dict | None     # beta_neutral_check.compute_down_market_mask(btc_closes)（date key）
    reasons: list[str]

def load_factor_bundle(window_start, window_end, *, dsn=None) -> FactorBundle:
    # BTC closes：唯讀 SELECT market.klines 1d（走既有 read 路徑）；
    # altcap：altcap_basket.load_fnd2_universe_rows + build_altcap_returns（producer 已 ship，零改動）；
    # mask：compute_down_market_mask（beta_neutral_check :303 已 ship，零改動）。
    # 任何子載入失敗 → 對應欄 None + reason（fail-soft；B1 自己 DEFER）。
```

`build_math_gate_context` 最後一步呼 §D 的 `reindex_to_int_bar_index` 把 candidate/btc/altcap/mask 統一轉 int bar index（滿足 B1 fail-loud 契約 beta_neutral_check :148-155）。

### B.2 candidate evidence 契約 v1（route 收的 inline JSON）

```json
{
  "evidence_schema": "aeg_candidate_evidence.v1",
  "candidate_id": "…", "run_id": "…", "strategy_family": "…",
  "regime_rows": [ …build_candidate_metrics rows（builder.py :312-344 欄位）… ],
  "selected_regime": "all",
  "daily_returns": {"2026-01-02": 0.0012, "…": "…"},
  "return_unit": "fraction",
  "cpcv_oos_returns_per_split": null,
  "leak_producers": {
    "shift1_compliance": { "source_class": "shift1_compliance", "leak_free": true, "…": "…" },
    "is_oos_gap":        { "source_class": "is_oos_gap",        "leak_free": true, "…": "…" }
  },
  "window_start": "2025-09-01", "window_end": "2026-06-01",
  "bull_only": false
}
```

`daily_returns` / `cpcv_oos_returns_per_split` / `leak_producers` 全部 **可選**——缺 = 對應 stage DEFER（誠實）。`daily_returns` 的供給屬 AEG-S3 runner 後續工作（harness 內 series 已存在，dump 到 report 是 research 端小改），**不在本輪 scope**；本輪交付契約 + 轉換層，序列缺時 hypothesize 走 B1-DEFER 的 backlog（non-promotable），不偽 pass。

### B.3 欄位映射表（adapter 唯一權威；E2 grep 對象）

| math gate 消費 key | evidence 來源 | 缺值語義（誠實 DEFER） |
|---|---|---|
| `context["candidate_returns"]` | `daily_returns`（`return_unit="bps"` → ÷1e4 正規化；再經 §D re-index） | None → B1 `b1_inputs_missing_defer`（executor :1116-1118） |
| `math_gate_inputs.n_trades_oos` | selected regime row 的 **`n_independent`**（cluster-adjusted N；builder :285-286 註解明禁用 n_days 冒充） | None → Q1 DEFER `q1_trades_oos_below_50`（:1014-1017） |
| `.observed_sharpe` | row `oos_sharpe`（OOS 觀測 sharpe = DSR deflation 的正確輸入；非 in-sample annualized_net_sharpe） | None → `dsr_inputs_missing`（:1024-1026） |
| `.n_trials` | row `k_trials` | None → `dsr_inputs_missing` |
| `.cpcv_oos_returns_per_split` | evidence 頂層（可選） | None/<2 → PBO `pbo_single_config_honest_defer`（:1033-1036；承 Gap-A 不捏造 peer） |
| `.btc_returns` | FactorBundle（非 evidence） | None → B1 DEFER |
| `.altcap_returns` | FactorBundle（altcap producer；空 returns → None） | None → B1 內部 `altcap_missing_btc_only_defer`（beta_neutral_check :193-194） |
| `.down_market_mask` | FactorBundle（compute_down_market_mask） | None → `down_mask_missing_defer`（:239-240） |
| `.bar` | 固定 `"daily"`（AEG-S3 = daily 研究；4h 不在本輪，§D.4） | — |
| `.shift1_compliance_leak_free` | `leak_producers.shift1_compliance.leak_free`，**僅當其 `source_class=="shift1_compliance"`**（M3 typing：report 自稱 leakfree 不算） | None → leak DEFER（:1146-1147） |
| `.is_oos_gap_leak_free` | 同上 `is_oos_gap` | None → leak DEFER |

**regime row 選擇規則（防 selection bias，QC 軸）**：`selected_regime` 顯式給 → 用之；缺省且 `regime_rows` 恰一行 → 用之；**多行且無顯式指定 → 全標量 None（DEFER）+ reason `regime_ambiguous_no_selection`**。adapter 絕不自動挑 best-Sharpe row——自動挑 = cherry-pick = selection bias 進 gate 輸入。

**捏造禁令（寫進 MODULE_NOTE，E2 grep target）**：adapter 內 `mean_daily_bps`/`net_bps` 只允許出現在禁令註釋，**不存在任何標量→序列合成路徑**（理由見 §0 F2：常數序列 → OLS β≈0 → B1 偽 pass）。

---

## D. int-bar-index re-index（owed ①）

### D.1 放哪：新純函數模組 `program_code/learning_engine/bar_index_reindex.py`

learning_engine sibling（beta_neutral_check / dsr_gate 同層）：0 DB / 0 IO / synthetic 可測。理由：int-bar-index 契約是 beta_neutral_check 定的（:148-155 明寫「date→int re-index 是 producer/conductor wiring 階段的責任」）——契約的官方 producer-side 對偶函數應住在同層，未來 mlde/residual 通道接 B1 時 reuse，不綁死 control_api。本輪 **不碰 residual_alpha_gate、不碰 beta_neutral_check**（後者 P3b 已 green+QC sign-off，改它要重開簽核）。

### D.2 簽名 + 輸入容忍

```python
def reindex_to_int_bar_index(
    candidate_returns: Mapping | None,
    btc_returns: Mapping | None,
    altcap_returns: Mapping | None,
    down_market_mask: Mapping | None,
    *, bar: str = "daily",
) -> ReindexResult:
    # ReindexResult{ candidate: dict[int,float]|None, btc: …, altcap: …, mask: dict[int,bool]|None,
    #                index_map: dict[int, dt.date],   # 審計：int → 原 date（D3 可重建）
    #                n_bars: int, reasons: list[str] }
```

- key 容忍：`dt.date` / `dt.datetime`（daily bar 取 `.date()`；**同日重複 key → fail-loud**：reasons `duplicate_date_after_normalize` + 全 None 結果，不靜默覆蓋）/ ISO 字串（含 Z/時區，語意同 altcap_basket._to_date :270-291，模組自帶等價小函數不跨模組 import 私有 helper）/ **已是 int**（全輸入全 int 且 key 對齊 → pass-through 原樣回 + reason `already_int_passthrough`）。
- 混型 / 不可解析 key → fail-loud：reasons + 全 None（對齊 B1 入口契約「mixed 也違規」精神，beta_neutral_check :498）。
- `altcap_returns=None`（producer 缺）→ 交集不含 altcap、輸出 altcap=None（B1 自己 DEFER）；`mask=None` 同理。

### D.3 對齊規則 + int 賦值（★ 含一處對任務描述的 push back）

1. 各輸入 key 正規化為 `dt.date`。
2. 共同 span = `candidate ∩ btc ∩ altcap` 的 date 交集（altcap=None 時 = candidate ∩ btc）。**mask 不參與交集**（mask 是 BTC closes 全集的衍生，date 域 ⊇ btc returns 域）；mask 在交集 date 上取值，交集內缺 date → 該 bar False + reason `mask_gap_filled_false:<n>`（與 B1 :242 `mask.get(ts, False)` 同保守語意，但顯式記帳）。
3. **int 賦值 = ordinal-day offset**：`idx = d.toordinal() − d0.toordinal()`，`d0` = 交集最早 date。
   **Push back（任務寫「交集後 0..N-1」）**：`_span_days` 對 int key 用 `max−min` 直接當天數（beta_neutral_check :569-592，docstring 明寫「每單位視為一天，與 daily bar 對齊」），而 down-leg 的 `≥180d` span 檢查（QC #3c-window）語意是 **calendar 跨度**。dense 0..N-1 在序列有缺 bar 時（backfill 洞、6 ex-BTC symbol 補齊前後的稀疏期）把 span 壓成 `N−1` → 系統性低估真 calendar 跨度；ordinal-offset 保真 span，**無缺 bar 時兩者完全相同（恰為 0..N-1）**。兩者皆滿足 `_is_int_bar_index`（:458）與 `_chrono_key` 數值分桶單調性（:539-553，DW/HAC 只用排序後殘差序，key 間隙不進公式）。dense 的失真方向是保守（多 DEFER）非危險，但 ordinal-offset 同樣保守界（mask gap 仍 False）且不無謂犧牲真資料窗。**採 ordinal-offset**；若 QC/PM 堅持字面 0..N-1，adapter 端一行可切（兩規則都實作為枚舉參數 `index_rule="ordinal_offset"|"dense"`，default ordinal_offset，測試覆蓋兩者）。
4. mask 用同一 `date→idx` map 轉換。四輸出 key 域 = 同一 int 集合（B1 的 `pooled_ts` 交集 :565 將是滿交集）。
5. 與 B1 串測驗收：reindex 輸出餵 `beta_neutral_check` → `_first_non_int_bar_index_key` 回 None（不觸 `temporal_keys_unsupported_need_int_bar_index`），synthetic 已知-β 資料回非 DEFER verdict。

### D.4 邊界

`bar != "daily"` → fail-loud reasons `bar_reindex_unsupported:<bar>` + 全 None。4h 的 bar-delta 規則（toordinal 取日會撞 key、span 換算 6x）顯式不在本輪——AEG-S3 是 daily 研究；4h 接入是未來另案 + 需重看 `_span_days` 語意。

---

## C. dead-modes seed 格式（owed ② 設計部分）

### C.1 欄位值決策（ground 在 retrieve_lessons filter，§0 F3）

| 欄位 | 值 | 理由 |
|---|---|---|
| `lesson_type` | `dead_mode` | executor :974 硬編檢索此值；M4 bad-set builder 同鍵掃 |
| `source` | **`dead_mode_seed`**（第 4 namespace） | 不撞 `l2_session`（critic 池，V133 default :90）/ `ml_advisory`（sink 輸出，executor :498）/ `ml_shadow`（別表）。**filter 不含 source**（layer2_critic :326-340）→ 檢索照常命中；source 純 provenance：審計可分 seed vs organic dead-mode，未來清理可 `WHERE source='dead_mode_seed'` 精確圈定 |
| `symbol` | **`ml_advisory`**（= `_SINK_SYMBOL_PLACEHOLDER` :444） | dead-mode 是 cross-symbol 失敗模式（down-beta 偽裝不分 symbol）；conductor 不帶 symbol 時 `_check_novelty` 用 placeholder 查 → 直接命中。**配套必要修補見 C.3**（否則帶 symbol 的 dispatch 會 miss 全部 seed） |
| `content` | **英文主幹**句式（C.2） | hypothesize statement 是英文 JSON（contract registry :278 `"statement":"…"`）；pg_trgm 是字面 trigram，中文 content vs 英文 hint 相似度≈0 → 全中文 seed = 永 miss 死資料 |
| `session_trigger` | `seed:2026-06-10` | 可追溯 seed 批次 |
| `context_id` | `seed:<slug>`（如 `seed:funding_arb_v2`） | 每條穩定 ID，idempotency 錨點 |
| `outcome_net_bps` | NULL | V133 forward-stub 規則（:104-105 readers must not assume non-null） |
| `session_cost_usd` | NULL | 非 session 產物 |

### C.2 六條 seed（全部 ground 在 memory 真實 NO-GO；content 模板：`DEAD MODE [<family>]: <english failed-hypothesis statement>. Why dead: <mechanism>. Evidence: <numbers>.`）

1. **funding_arb_v2** — `DEAD MODE [funding_arb]: Delta-neutral funding rate arbitrage long spot short perp harvesting funding payments. Why dead: delta-neutral math does not survive fees plus basis drift; carry edge below cost wall. Evidence: closed NEGATIVE avg net -36.76 bps, 0 win rate, n=13 (G-2 2026-04-18).`
2. **funding_short_v2 (A1)** — `DEAD MODE [funding_short]: Short perp on positive funding extreme expecting funding mean reversion. Why dead: positive-side cap is an IR floor fingerprint; regime-dormant; 160 percent break-even threshold vs realized carry. Evidence: 93 percent probe rejects missing_basis_asof (2026-05-31).`
3. **cascade_fade (H2)** — `DEAD MODE [cascade_fade]: Fade liquidation cascade with mean-reversion entry after forced-liquidation burst. Why dead: apparent edge was down-beta masquerade inside a BTC downtrend regime, not alpha. Evidence: 280 events, all demeaned |t| < 1.3 (2026-06-03 NO-GO).`
4. **funding_tilt** — `DEAD MODE [funding_tilt]: Cross-sectional funding tilt portfolio long low-funding short high-funding symbols. Why dead: funding tilt loads on market beta not alpha; carry cannot clear costs. Evidence: carry_cost_ratio 3.64, DSR 0, 82 percent down-beta share, NO-GO-C (2026-06-03).`
5. **grid_short_downtrend** — `DEAD MODE [grid_short]: Grid short bias harvesting volatility in a downtrend regime. Why dead: blocked-signal counterfactual shows demeaned alpha approx 0; any short bias in a down regime is trend beta in disguise; requires explicit beta neutralization. Evidence: blocked grid_short replay (2026-06-03).`
6. **textbook_scalping_family** — `DEAD MODE [micro_profit]: Textbook high-turnover scalping signals (micro profit lock, RSI reversal, breakout momentum) on 1m-5m bars. Why dead: gross edge 1-3 bps per trade below the 11-27 bps cost wall; textbook indicators carry no net alpha after costs. Evidence: five strategies alpha-deficient across sprints (2026-05-10 / 2026-06-01).`

（6 條落在 5-10 規格內。**不 seed listing fade**——它是 active 主路徑非 dead mode；P3b 報告 §F.2 把它列在 M4 *good set*（正確診斷樣本）側，與 dead-mode bad set 是兩回事。）

### C.3 配套修補：`_check_novelty` placeholder union（~6-8 行，本輪 scope 內）

現狀（executor :973-974）：dispatch 帶 `symbol="TONUSDT"` 時檢索 `WHERE symbol='TONUSDT' AND lesson_type='dead_mode'` → C.1 的 placeholder seed 全 miss → novelty 失明。修補：dead-mode 檢索改「先查具體 symbol，再查 placeholder，union 去重」：

```python
lessons = await _critic.retrieve_lessons(sym, statement, lesson_type="dead_mode")
if not lessons and sym != _SINK_SYMBOL_PLACEHOLDER:
    lessons = await _critic.retrieve_lessons(_SINK_SYMBOL_PLACEHOLDER, statement, lesson_type="dead_mode")
```

語意：dead-mode 教訓掛 placeholder = global namespace；symbol-specific dead-mode（未來 organic 寫入）仍優先命中。fail-soft 外殼（:979-981）不變；參數綁定不變（無注入面）。這是「novelty stage 真能比對」的必要條件，否則 seed 是擺設。

### C.4 seed 工具形態：helper script（拒一次性 SQL）

`helper_scripts/m4/seed_dead_mode_lessons.py`（M4 bad-set 是主要消費者，與 feature_engineering_validator 同家）+ `SCRIPT_INDEX.md` 條目。拒手寫 SQL 的理由：英文長文本 quoting 地獄（feedback_shell_paste_safety）；參數綁定防注入；**idempotent 可重跑**（`INSERT … WHERE NOT EXISTS (SELECT 1 FROM agent.lessons WHERE source='dead_mode_seed' AND context_id=%s)`——context_id 是穩定錨點）；**默認 `--dry-run`（print 不寫），顯式 `--write` 才落庫**（剛發生 prod 污染事故 `0ce45a09`，寫庫工具必須默認無害）；`--dsn` 顯式參數（不隱式吃 prod 連線）。驗收：`--write` 後 `SELECT count(*) FROM agent.lessons WHERE source='dead_mode_seed'` = 6；再跑一次仍 6（冪等）；`retrieve_lessons("ml_advisory","short perp funding mean reversion carry",lesson_type="dead_mode")` 真 PG 撈到 ≥1（驗 trgm 0.1 門檻真命中）。

---

## E. E1 任務拆分（檔案互不重疊，可並行）

### E1-A（learning_engine 純函數 + seed script；無 control_api 依賴）

| 檔案 | 動作 | 估行數 |
|---|---|---|
| `program_code/learning_engine/bar_index_reindex.py` | 新建（§D） | ~180 |
| `program_code/learning_engine/tests/test_bar_index_reindex.py` | 新建 | ~250 |
| `helper_scripts/m4/seed_dead_mode_lessons.py` | 新建（§C.4） | ~180 |
| `helper_scripts/m4/tests/test_seed_dead_mode_lessons.py` | 新建（fake conn 驗 SQL 構造/冪等分支） | ~120 |
| `helper_scripts/SCRIPT_INDEX.md` | 加一條 | +1 |

測試清單：date/datetime/ISO-str/int/mixed/duplicate-date key 矩陣；缺 bar 時 ordinal-offset span 保真 vs dense 對照；mask gap 記帳；4h reject；**串測**：reindex 輸出 → `beta_neutral_check` 不觸 `temporal_keys_unsupported_need_int_bar_index` 且 synthetic 已知-β 回真 verdict（β=0.5 注入 → fail；β=0 → pass/DEFER-by-down-bars）。

### E1-B（control_api conductor + route；§B/§D 介面已凍結故可並行，串接測試在 E1-A merge 後補跑）

| 檔案 | 動作 | 估行數 |
|---|---|---|
| `app/l2_candidate_evidence_adapter.py` | 新建（§B；含 FactorBundle loader） | ~320 |
| `app/layer2_routes.py` | 改：+1 route + request model（§A.2） | +75 → **~835 行，超 800 review 線，E2 標 review-attention**（hard cap 2000 未近；route 屬既有 L2 家族檔，拆檔反而割裂 singleton accessor） |
| `app/l2_ml_advisory_executor.py` | 改：`_check_novelty` placeholder union（§C.3） | +6-8 |
| `tests/test_l2_candidate_evidence_adapter.py` | 新建 | ~280 |
| `tests/test_l2_ml_advisory_dispatch_route.py` | 新建 | ~150 |

測試清單：缺值矩陣（每缺一鍵 → 斷言對應 stage verdict/reason，對齊 §B.3 表）；regime 多行無顯式 → DEFER `regime_ambiguous_no_selection`；bps→fraction 正規化；**禁捏造斷言**（evidence 無 daily_returns → `context["candidate_returns"] is None`，且 adapter 源碼 grep 無標量→序列路徑）；route disabled-dispatch 回 `capability_disabled`（E2E-0 的單測版）；route 拒非 `ml_advisory.` 前綴；`_check_novelty` union 兩分支。

**測試隔離鐵則（`0ce45a09` 教訓，全部新測試檔強制）**：每檔含 autouse `_no_real_db` fixture（monkeypatch 模組引用的 `db_pool.get_pg_conn` → MagicMock，邏輯全真走、只攔真連線）；需斷言 DB 參數的測試**顯式注入** conn/dsn/`conn_provider`。FactorBundle loader 測試注入 fake conn。**Mac 假綠 ≠ 安全：fail-soft 會吞連線錯誤，連得上 prod 的環境就真寫。**

### Linux real-smoke（安全做法）

1. seed script `--dry-run` 先看輸出 → `--write --dsn <顯式>` → count=6 → 重跑驗冪等 → `retrieve_lessons` 真 PG 命中（§C.4）。
2. FactorBundle loader 真 klines 唯讀 SELECT：btc_returns ≥ 90 bars、mask down-bars 計數對 MIT 基線（full-span≈309）sane、altcap 對現有 18/24 symbol 出 non-empty returns（6 缺 symbol 補齊另線，缺時 producer 自然縮 N_t，PIT 語意不破）。
3. E2E-0：deployed route 打 disabled dispatch → seam row 真落（§A.3）。
4. E2E-1：operator-gated（enable diagnose_leak 一次→真 l2_calls row→disable）。
5. **smoke 全程不 enable hypothesize**；任何 smoke 產生的 DB 行為僅：seed rows（deliberate、冪等、可圈定刪除）+ append-only seam/ledger rows（真實審計事件）。

依賴序：E1-A ∥ E1-B 並行 → 兩者綠後 E1-B 補跑串接測試（adapter→reindex→B1）→ E2 → E4（Linux smoke 1-3）→ QA。E2E-1 與 hypothesize enable 是 operator 的後續獨立決策。

---

## F. 風險與邊界（設計範圍 #6）+ E2 重點審查 3 點

**改動風險評級：中**（route +adapter 是新增 caller，不碰 SM/gate/registry/lease；`_check_novelty` 6 行是 fail-soft 函數內擴查）。對照高風險面：0 GovernanceHub、0 PipelineBridge、0 API schema 變更（新 endpoint 是加法）、0 Rust、0 migration、0 IPC。

邊界遵守清單：
- **不碰** `residual_alpha_gate` / `beta_neutral_check` / orchestrator 鐵律段（:410-416）/ registry loader / guard / math gate stage 函數。
- **不 enable 任何 capability**（registry 3 stanza enabled=false 原樣；enable 是 operator 之後的獨立決策，雙閘維持）。
- LANE_DIRECTION 無 live、sink=agent.lessons inert、math gate=唯一 alpha validator——全部零觸碰（本輪只是給既有 dispatch 一個 caller + 給 gate 真資料）。
- 硬邊界指紋（live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / authorization.json / execution_authority / lease）：本設計 0 觸碰。
- Rust-first 例外聲明：本輪是既有 Python L2 mesh 的 wiring/data 補完（P1-P3b 同 posture、設計鏈已 operator 認可），非新獨立 trading/risk 模組。
- 跨平台：無硬編 home path；reindex/adapter 純函數 Mac 可測；DB smoke 走 `ssh trade-core`。
- 檔案大小：唯 layer2_routes ~835 行超 800 review 線（標註，遠低 2000 hard cap）；其餘新檔 <400。

**E2 重點審查 3 點**：
1. **adapter 零捏造路徑**：grep `mean_daily_bps|net_bps` 在 adapter 只出現於禁令註釋；無任何標量→序列合成；regime 多行無顯式選擇必 DEFER（selection-bias 閘）。
2. **route 安全面**：`require_scope_and_operator` 在 handler 第一行；inline-only（無 server path read）；capability_id 前綴驗證 fail-closed；orchestrator 簽名零改動（diff 確認 dispatch_and_execute 未被觸）。
3. **`_check_novelty` 修補**：union 查詢保持 fail-soft 外殼 + 參數綁定；先具體 symbol 後 placeholder 的順序（不反轉）；executor 鐵律 MODULE_NOTE（:26-35）verbatim 未動 + 仍 0 order/lease/promote import。

**殘留 open item（不阻 E1）**：(i) `daily_returns` 供給端（AEG-S3 runner dump series 進 report）是 research 線後續——缺時 B1 誠實 DEFER，wiring 先就位；(ii) ordinal-offset vs dense 0..N-1 若 QC 有異見，`index_rule` 參數一行切換（§D.3 已雙實作）；(iii) V127 population、6 ex-BTC klines 補齊、E2E-1 執行＝既有 owed 清單 operator-gated 項，本設計不重複認領。

PA DESIGN DONE: report path: /tmp/wt-l2-owed/docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--l2-p3b-owed-conductor-wiring-design.md
