# PA Design — AEG-S2 Component (b) Breadth Ladder Runner IMPL

| 項目 | 內容 |
|------|------|
| Date | 2026-06-03 |
| Author | PA |
| Mode | DESIGN-only（PA 不寫 feature code）。read-from-storage-only；0 DB write / 0 backfill / 0 schema / 0 migration / 0 deploy / 0 auth / 0 order / 0 IPC。 |
| Status | DONE — E1 dispatch-ready；回 PM 摘要附後 |
| Binding sources | MIT AEG-S2 `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-03--aeg_s2_evidence_automation_design.md`（Component (b) b.1–b.6 + cross-component graph）；AEG-S0 `docs/execution_plan/2026-05-31--aeg_s0_contracts.md` §1.3/§1.4/§2.8/§2.9；FND-2 contract `docs/execution_plan/2026-06-01--aeg_s1_fnd2_pit_universe_builder_contract.md`；FND-2 PA design `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--fnd2_pit_universe_builder_impl_design.md`；**FND-2 IMPL（已 DONE，輸入契約權威）** `helper_scripts/research/fnd2_pit_universe/{builder,cohorts,data_loader,artifact,harness,__init__}.py`；sibling 候選 harness `helper_scripts/research/{multiday_trend_diagnostic,funding_tilt_diagnostic}/`；cost-wall report `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--cost_wall_escape_2_multiday_trend_diagnostic.md`（§n_independent ceiling） |
| 改動風險評級 | **中**：新獨立 read-only research module，0 import 既有 runtime，0 寫面，0 IPC，0 硬邊界接觸。風險集中在「正確性」（survivorship 繼承 / cross-section rank PIT / breadth≠n_independent）非「副作用」。 |

---

## 0. Executive summary

Breadth ladder runner = read-only batch research module，把**任一候選的 per-symbol PnL 生成**在 FND-2 PIT universe 的 **4 個 breadth tier** 上各跑一次，產 deterministic `breadth_ladder.parquet`（S0 §1.3），報 per-tier net edge + significance + **monotonicity**（edge 隨 breadth 加寬存活，還是塌成 1-2 symbol fluke）。是 (c) robustness matrix `breadth_cohort` 軸的證據源。

**三個 load-bearing 設計判斷（每個都覆寫 naive 直覺，E2/MIT must-check）**：

1. **【tier 組裝】用 FND-2 `cohort_ids`（multi-membership）組 cumulative-nested tier，NOT `recommended_tier`（single-pick priority）。** FND-2 `recommended_tier`（`cohorts.py:69 classify_recommended_tier`）對每 symbol 只給**一個** tier（core25 > scanner > top_liq > full 優先序裁決）→ BTCUSDT 只會是 `core25_pinned`，**不在** `top_liquidity_40_50` 集。但 breadth ladder 的語義是**嵌套加寬**（core25 ⊂ top_liquidity ⊂ full_survivorship），core25 成員必須同時出現在更寬 tier。故 (b) 必須讀 **`cohort_ids`（array，multi-membership，`cohorts.py:93 cohort_ids_for`）** 並自行組 nested set，不能用 `recommended_tier`。誤用 `recommended_tier` 會讓 tier 互斥、monotonicity 比較完全失真（每 tier 是 disjoint 子集而非嵌套）。

2. **【candidate-agnostic】(b) 是 candidate-agnostic harness（吃 candidate 的 per-symbol PnL provider callable + universe），NOT 綁特定候選。** sibling 候選 harness（`multiday`/`funding_tilt`）的核心 `run_diagnostic(panel, universe)`（`multiday/harness.py:280`）**已經把 universe 當參數**，per-symbol 迭代（:307）、close-matrix（:324）、`pca_effective_n`（:325）全依 `universe` 收斂。breadth runner 的工作就是用 4 個 tier 的 symbol-set 各呼一次候選評估器。**recommend：(b) 定義一個窄 `CandidateEvaluator` protocol（`evaluate(universe, panel) -> TierResult`），由 caller 注入具體候選**（首個消費者 = listing-fade，其次 funding-tilt）。理由見 §3。

3. **【breadth ≠ n_independent】加寬 breadth 報 symbol-count，但 `n_independent` 保持 time-cluster-bound，絕不隨 symbol 數膨脹。** cost-wall report 已實證（§51/§97-99）：「binding constraint 是 independent TIME periods（weekly+ ~8 max），NOT symbol count；即使 59 long-short legs，independent time clusters = 8。」故 (b) 每 tier **分開報** `breadth_symbol_count`（加寬）與 `n_independent`（time-cluster，**不**因加 symbol 而增）。current `multiday` 的 `eff_n = pooled_flips × cluster_factor`（:337）會隨 symbol 數經 `pooled_flips` 漲——(b) 不可沿用此式作 `n_independent`；須用 **time-cluster-aware** 計數（§4 Step 4）。S0 §2.9 明令：cross-sectional strategies count one independent rebalance timestamp after BTC-beta clustering；symbols-per-rebalance = breadth。

**無 V127 / component (a) 依賴**：(b) 只需 FND-2 universe artifact（done）+ S1 daily-kline/funding storage（live）+ candidate PnL provider。regime labels 是 (c) 才消費。**S2 = read-from-storage-only 成立**（讀 `market.klines`/`market.funding_rates` + FND-2 artifact，無重抓 Bybit，無新 public-data client）。詳見回 PM 摘要。

---

## 1. 輸入契約（FND-2 artifact，code-authoritative 非文檔）

（親讀 `fnd2_pit_universe/builder.py:UNIVERSE_COLUMNS` + `cohorts.py` + SCRIPT_INDEX 真跑記錄，不採信契約字面。）

### 1.1 FND-2 universe artifact（(b) 的 universe 來源 — 凍結事實）
- 路徑：`${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<fnd2_run_id>/universe.csv`（SoT）+ `universe.parquet`（duckdb 鏡像，可選）+ `universe_summary.json` + `manifest.json` + `artifact_index.json`。
- Linux 真跑（2026-06-03，asof 2026-06-03 / window 2024-06-03→2026-06-03，SCRIPT_INDEX 權威記錄）：`included=829` / `delisted_proof_count=255` / `survivor_rejection_status=PASS` / `unknown_lifetime=0` / `universe_id` 兩跑一致。**(b) 不重跑 FND-2，直接消費此 artifact。**
- per-symbol 欄（`builder.py:42 UNIVERSE_COLUMNS` 凍結 37 欄，(b) 用以下子集）：

| FND-2 欄 | (b) 用途 |
|---|---|
| `symbol` | universe 成員 |
| `cohort_ids`（array，CSV 為 JSON array string）| **tier 組裝唯一正確源**（§1.2）。含 `full_survivorship` / `core25_pinned` / `scanner_active_asof` / `top_liquidity_40_50` / `historical_delisted` |
| `recommended_tier` | **(b) 不用作 tier 組裝**（single-pick，會破 nested 語義）；僅可作診斷欄 passthrough |
| `alive_from_utc` / `alive_to_utc` | **per-symbol PIT mask（繼承，不重算 — MIT b.2）**；候選評估只在 [alive_from, alive_to] 內持倉 |
| `seen_delisted` | healthcheck `check_aeg_breadth_universe_pit()` 斷言（MIT b.6）+ delisted-proof count |
| `unknown_lifetime` | 排除（不入任何 tier 的 scoring；診斷）|
| `included` | **只取 `included=true` 行入 universe**（excluded 是 FND-2 診斷行）|
| `in_core25_pinned` | core25 tier 交叉驗證（應與 `cohort_ids` 含 `core25_pinned` 一致）|
| `status_class` | `prelaunch` row 標記（universe metadata，非 scoring-ready；下游 coverage gate 判）|

### 1.2 4 breadth tier 組裝（凍結，manifest-pinned `aeg_breadth_v0.1.0`）

tier 定義凍結，**從 FND-2 `cohort_ids` membership 組 cumulative-nested set**（MIT b.1 表 + S0 §1.3）：

| Tier（凍結名）| 組裝邏輯（從 `cohort_ids`）| 來源 / 守則 |
|---|---|---|
| `core25_pinned` | `included=true AND 'core25_pinned' ∈ cohort_ids` | FND-2 seed 凍結 25 成員（`cohorts.py:27 CORE25_PINNED`）。窄基線。 |
| `scanner_active_asof` | `included=true AND 'scanner_active_asof' ∈ cohort_ids`（overlap-only）| `trading.scanner_snapshots` asof overlap（FND-2 `data_loader:_load_scanner_active`）。S0「不足夠單用」→ 作 tier 不作 universe gate。 |
| `top_liquidity_40_50` | `included=true AND ('core25_pinned' ∈ cohort_ids OR 'top_liquidity_40_50' ∈ cohort_ids)` | turnover rank≤50（FND-2 `cohorts.py:88`）。**僅當 liquidity source PIT-documented**（見 R-1 leak flag §5）。**含 core25**（nested）。 |
| `full_survivorship` | `included=true`（全 included，等價 `'full_survivorship' ∈ cohort_ids` 因 FND-2 給所有 included symbol 此 cohort，`cohorts.py:104`）| FND-2 builder 全 PIT universe incl. delisted。最寬。 |

**Nested 不變量（(b) 測試斷言，T-tier-nest）**：`core25_pinned ⊆ top_liquidity_40_50 ⊆ full_survivorship`（成員集合包含關係）。`scanner_active_asof` 與其他 tier 是 overlap（非嚴格 nested），單獨報。**E1 必須機械驗此包含關係**（FND-2 `cohort_ids` 已保證 core25 symbol 同時帶 `full_survivorship`；top_liquidity 用 OR core25 顯式補 nested）。

tier 定義凍結為 `BREADTH_TIERS` 常數（`cohorts_tiers.py`），任何 tier 成員規則變更須升 `BREADTH_LADDER_VERSION`（進 ladder digest），否則 monotonicity 對帳會誤判。**候選不能挑有利 tier 組成**（MIT b.4）。

### 1.3 候選 per-symbol PnL 輸入（中心設計決策，§3 詳述）
(b) 不重新發明信號/PnL——它消費候選評估器產的 **per-symbol PnL 原料**。候選評估器（如 `multiday.run_diagnostic` / `funding_tilt`）對給定 universe 已能產：per-symbol 日報酬序列、pooled trades、net edge、Sharpe、per-leg。breadth runner 對 4 個 tier 各餵一次 universe，收齊 4 組 TierResult 比較。**輸入 schema（candidate evaluator → breadth runner）= `TierResult`，§3.2 定義。**

---

## 2. 架構決策（PA 拍板）

### D-1 放哪 + 形態：`helper_scripts/research/aeg_breadth_ladder/`（package-dir module，CLI via `harness.py`）
**決策：新建 package-dir，mirror FND-2 + 兩 sibling harness（`<name>/` dir 含 `harness.py` CLI + 領域 modules + 共用 `research/tests/`）。不 standalone bin、不 lib、不 Rust。**

理由（read-before-design）：
1. **與 FND-2/sibling 對稱**：FND-2 + multiday + funding_tilt 三 harness 同形態（`research/<name>/` package-dir，`research/tests/conftest.py` 已把 `research/` 加 sys.path）。breadth runner 是同類「read artifact + read-only PG → deterministic artifact」研究器，落同處 = 0 學習成本、E2/MIT 已熟 pattern。
2. **不放 lib**：`lib/`（`pg_connect`/`stats_common`）是 byte-identical 共用 helper 邊界；breadth 有 tier/monotonicity 業務語義，屬 research module。**但 (b) 應 import `lib.stats_common`**（PSR/DSR/PBO/block-bootstrap，funding_tilt 已用）+ 可選 import sibling `funding_tilt_diagnostic.stats`（`pca_effective_n` / HAC `_newey_west_mean_tstat`）避免重抄統計（見 D-2）。
3. **Rust-first 例外**：memory `feedback_new_code_rust_first` 預設 Rust，但本模組是 **one-shot read-only research artifact builder**（非交易/風控/config runtime 邏輯），整個 AEG-S2 證據鏈（FND-2 + (a)/(b)/(c)）MIT 已定調 Python batch + parquet（pyarrow/duckdb 已在 Linux），下游 (c) robustness matrix 是 Python harness，跨語言邊界 0 收益。CLAUDE §七「new standalone trading/risk/config logic should be Rust-first **unless the local design clearly says otherwise**」——本設計明確 says otherwise：research-evidence-builder lane 是 Python（與 FND-2 OQ-1 同決策，PM 已就 FND-2 批准此 lane；breadth 同 lane 應繼承，OQ-B1 確認）。
4. **不 bin**：bin 適合需編譯/部署的 runtime collector；breadth 是 dev/research 觸發的離線 builder，CLI module 足夠。

模組拆分（mirror FND-2 結構，每檔 < 800 行）：
```
helper_scripts/research/aeg_breadth_ladder/
  __init__.py            # package marker + 版本常數 BREADTH_LADDER_VERSION / LADDER_SCHEMA_VERSION
  tiers.py               # 凍結 BREADTH_TIERS 定義 + assemble_tiers(universe_rows) → {tier: set[symbol]}
                         #   + nested 不變量斷言 + manifest-pinned digest
  universe_artifact.py   # read FND-2 universe.csv/.parquet（含 alive_from/alive_to/cohort_ids/included）
                         #   + survivorship mask 繼承（不重算）。0 DB（讀檔）。
  ladder.py              # 純函數核心：對 {tier→TierResult} 算 per-tier net edge + significance
                         #   + monotonicity 判定 + breadth≠n_independent 分離。0 DB / 0 候選耦合。
  evaluator.py           # CandidateEvaluator protocol + adapter（包 sibling candidate harness
                         #   為 per-tier evaluate(universe) → TierResult）
  artifact.py            # breadth_ladder.parquet/.csv writer + summary.json + manifest.json
                         #   + artifact_index.json + sha256 + ladder_id digest（mirror FND-2 artifact.py）
  harness.py             # CLI 編排：parse args → load FND-2 artifact → assemble tiers →
                         #   per-tier evaluate → ladder → write → 印 summary
research/tests/test_aeg_breadth_ladder.py   # 與 sibling 同處（conftest 已 wire sys.path）
```
**關鍵切分**：`ladder.py` + `tiers.py` = 純函數（input: universe rows + {tier→TierResult}；output: ladder rows + summary），**0 DB / 0 候選耦合** → 全 synthetic 可測（mirror FND-2 `builder.py` 哲學）。`universe_artifact.py` 只讀檔。`evaluator.py` 是候選注入邊界（唯一碰 PG 的層，且 PG 讀委派給候選 harness 既有 read-only loader）。

### D-2 與既有 candidate harness / lib 的關係：**消費不修改；統計復用不重抄**
- **不改既有 harness**：`multiday`/`funding_tilt` 已跑完 verdict（trend NO-GO / funding NO-GO-C）。(b) 透過 `evaluator.py` adapter **呼用**其評估器（universe 已是參數），**不改其源碼**。若候選評估器需要小重構成可被 universe-parametrized 呼用（例如抽出 `evaluate_universe(universe, panel) -> dict`），那是該候選 IMPL 的 follow-up，**不在 (b) 範圍**——(b) 設計 adapter 容忍「候選評估器目前以 `run_diagnostic(panel, universe)` 形式存在」（multiday 已是此形）。
- **統計復用（不重抄）**：`ladder.py` 的 significance 用 `lib.stats_common`（PSR/DSR/PBO/block-bootstrap）+ sibling `funding_tilt_diagnostic.stats` 的 `pca_effective_n`（time-cluster N_eff 原料）與 `_newey_west_mean_tstat`（overlap-corrected HAC t）。**(b) 不新增第 17 個統計函數複製**（memory 精簡審計教訓：16 統計函數已被複製過度）。若 sibling stats import 不便（research/ 非 package），用 conftest 同款 sys.path adapter（harness.py 已示範 dual-import）。
- **共用點僅 DSN + artifact root**：`evaluator.py` 委派候選 harness 既有 `lib.pg_connect.resolve_report_dsn()` + `set_session(readonly=True)`；`artifact.py` mirror FND-2 `resolve_artifact_root()`（`${OPENCLAW_DATA_DIR}` 跨平台）。**不新增連線/路徑 helper。**

### D-3 read-only / read-from-storage 紅線機械化
1. `universe_artifact.py` 只**讀**檔（FND-2 artifact），0 PG、0 寫。
2. `evaluator.py` 經候選 harness 讀 PG（`market.klines`/`market.funding_rates`），全 `set_session(readonly=True)`（候選 loader 既有紀律，FND-2/funding_tilt 已驗）。
3. `artifact.py` 寫**本地檔系統**（`OPENCLAW_DATA_DIR`），非 PG。0 import `control_api_v1/app/` runtime 模組（同 FND-2/gate_b_artifact 紅線）。
4. **絕不重抓 Bybit**（無 public-data client）；universe 來自 FND-2 artifact，價格/funding 來自 S1-stored `market.*`（PM 已裁 S2=read-from-storage-only）。
5. **絕不**自寫 survivorship mask——`alive_from_utc`/`alive_to_utc` 從 FND-2 artifact 繼承（MIT b.2「繼承，不重算」）。

---

## 3. 中心設計決策：candidate-agnostic 輸入契約（OQ #3 — PA recommend）

### 3.1 兩個選項
- **Option A — candidate-bound**：(b) 內嵌特定候選（如 listing-fade）的信號/PnL 生成，per tier 重跑。
- **Option B — candidate-agnostic harness**（**PA recommend**）：(b) 定義窄 `CandidateEvaluator` protocol，吃 universe + panel 回 `TierResult`；具體候選由 caller 注入。

### 3.2 PA recommend = Option B（candidate-agnostic）+ TierResult schema

**理由**：
1. **既有結構已支持**：`multiday.run_diagnostic(panel, universe)` 已 universe-parametrized（:280-331），universe 換成 tier symbol-set 即得 per-tier 結果——零候選改動即可被 adapter 包裝。
2. **AEG 通用性**：breadth ladder 是 ADR-0047 證據基質，**每個** alpha 候選晉升都要過（S0 §1.3 verdict required artifact）。綁單一候選 = 每候選重寫 breadth runner = 違背「可重用、凍結 evidence 基質」mandate。listing-fade 是首消費者，但 funding-tilt/trend/未來候選都要用。
3. **leak 隔離單點**：candidate-agnostic 把 survivorship/PIT-mask/tier 邏輯收斂在 (b)，候選評估器只負責「給 universe + mask 算 PnL」——leak-free 編碼（§4）在 (b) 一處驗，不散到每候選。
4. **monotonicity 是 candidate-orthogonal**：monotonicity 判定（edge 隨 breadth 存活）對任何候選同邏輯，屬 (b) 純函數 `ladder.py`，與候選無關。

**`TierResult` schema（candidate evaluator → breadth runner 的契約，凍結）**：
```python
@dataclass
class TierResult:
    tier: str                       # 'core25_pinned' / ...（凍結 tier 名）
    breadth_symbol_count: int       # 該 tier 入選 symbol 數（加寬軸；含 delisted）
    seen_delisted_count: int        # 該 tier 含 delisted symbol 數（healthcheck 用）
    # 候選評估器產出（per-tier，已 PIT-mask + leak-free）：
    net_bps: float                  # per-trade 或 per-period net edge（bps）
    gross_bps: float
    cost_bps: float
    net_to_cost_ratio: Optional[float]
    is_sharpe: Optional[float]      # annualized
    oos_sharpe: Optional[float]     # 若候選提供 walk-forward；否則 None
    # 顯著性原料（time-cluster-aware，breadth≠n_independent）：
    n_independent: int              # ★ time-cluster-bound（NOT symbol-scaled，§4 Step 4）
    sample_unit: str                # 'non_overlapping_holding_window' / 'rebalance_timestamp_btc_beta_clustered'
    t_stat_hac: Optional[float]     # overlap-corrected HAC t
    psr_0: Optional[float]
    dsr_k: Optional[float]
    pbo: Optional[float]
    k_trials: Optional[int]
    # per-leg（候選若 market-neutral，沿用 funding_tilt per-leg 哲學防單邊偽裝）：
    long_leg_net_bps: Optional[float]
    short_leg_net_bps: Optional[float]
    # PIT/leak 自證：
    pit_mask_source: str            # 'fnd2_alive_from_alive_to'（繼承證據）
    leak_free_signal: bool          # 候選自證 leak-free（leak-free vs naive 已驗）
    notes: dict
```
**`CandidateEvaluator` protocol**：
```python
class CandidateEvaluator(Protocol):
    candidate_id: str
    def evaluate(self, *, tier: str, universe: tuple, alive_mask: dict) -> TierResult: ...
    # alive_mask: {symbol: (alive_from_utc, alive_to_utc)} 從 FND-2 繼承（MIT b.2）
```
**E1 交付 (b) + 一個 reference adapter**（包 multiday 或 listing-fade，看 PM 指定首候選），證明 protocol 可被既有候選滿足。**listing-fade 候選本身的 IMPL 不在 (b) 範圍**（OQ-B2）。

---

## 4. Leak-free 編碼（MIT b.5 — (b) 主 gate，不可協商）

### Step 1 — survivorship（繼承，不重算）
- universe 來自 FND-2 artifact `included=true` 行；per-symbol PIT mask = `alive_from_utc`/`alive_to_utc`（**直接繼承，MIT b.2「不重算」**）。
- `evaluator.py` 把 `alive_mask` 傳給候選評估器；候選只能在 [alive_from, alive_to] 內持倉（上市前/delist 後 signal=0）。**(b) 不自寫 listed_at 查詢**（避免 FND-2 已修的 R-1 trap：snapshot ts 僅 27d 不可作 lifetime 邊界）。
- **禁** current-survivor 捷徑：每 tier 必含窗內 delisted（FND-2 universe 已保證 `delisted_proof_count=255`）。tier 過濾只按 `cohort_ids` membership，**絕不**加「current-trading only」過濾。

### Step 2 — cross-section（top_liquidity rank 須 PIT/asof）
- **R-1 KNOWN LEAK FLAG（E2/MIT must-check）**：FND-2 `top_liquidity_40_50` 的 turnover rank 來自 **`data_loader._load_turnover`（latest snapshot at asof，single point）**——是「asof 當下的 liquidity rank」常數套用整窗。MIT b.5 要求「rank 須 PIT（rebalance/asof 當下已知，非 full-period 平均）」。
  - **asof-snapshot rank 是 full-window-constant**，對 18mo 窗，「哪些 symbol 在 2026-06-03 流動」被回溯套到 2024-06——這對「2024 當時哪些 symbol 流動」是 **mild look-ahead**（後來才流動的 symbol 被選入 2024 的 top_liquidity）。
  - **(b) 設計選擇（PA recommend）**：top_liquidity tier **標 `tier_rank_pit_mode='asof_constant'`** 並在 `breadth_ladder.parquet` 顯式記錄此 caveat（誠實標記，非靜默）。**真 PIT per-rebalance rank 需 per-rebalance turnover 歷史**——而 `market.market_tickers` 是 latest-snapshot（S0 §3.1「latest snapshot only; not historical proof」）+ index/mark persistence bug（S0 §1.7 排除）。故 **per-rebalance liquidity rank 目前無 PIT 資料源**。
  - **決策**：top_liquidity tier **降級為 `tier_quality='liquidity_source_not_pit'`**，其 verdict 行標 `excluded_from_promotion=true`（diagnostic-only），**除非 PM/MIT 批准 asof-constant 近似**（OQ-B3）。core25 + full_survivorship 兩 tier 無此問題（成員資格不依 liquidity），是 monotonicity 主軸。scanner_active_asof 同樣是 asof-snapshot（overlap-only，本就 diagnostic）。
- 候選評估器內部若有 cross-section 標準化（如 funding tertile rank），必須 per-rebalance-day（同日橫截面，rebalance 當下已知），**非 full-period standardization**（cost-wall report §134 已立此守則；funding_tilt `signals._rank_one_day_tertile` 已正確）。(b) 在 `TierResult.leak_free_signal` 要求候選自證。

### Step 3 — breadth ≠ n_independent（(b) 最核心，cost-wall 實證）
- **規則（S0 §2.9 + cost-wall §51/§97-99）**：同 rebalance 的 symbols 是 **breadth** 非 independent time draws。加寬 breadth（core25→full）會增 `breadth_symbol_count`，但 `n_independent` 是 **time-cluster-bound**，**不得**因 symbol 增而膨脹。
- **(b) 編碼**：
  - `breadth_symbol_count` = tier 入選 symbol 數（純計數，per tier 不同）。
  - `n_independent` = **time-cluster count**：
    - multi-day time-series 候選：non-overlapping holding-period windows 數（與 symbol 數無關，受窗長/holding 決定）。
    - cross-sectional 候選：independent rebalance timestamps 數 after BTC-beta clustering（cost-wall：weekly+ ~8 max，**不因 59 legs 變多**）。
  - **斷言（T-breadth-not-nindep，bite-proof）**：把 core25（25 sym）→ full（829 sym）的 tier 比較，斷言 `n_independent(full) ≈ n_independent(core25)`（time-cluster 不變），**而非** `n_independent(full) ≈ 33× n_independent(core25)`（symbol-scaled 錯誤）。若實作讓 n_independent 隨 symbol 漲，此 test 必 fail。
  - **不沿用 `multiday` 的 `eff_n = pooled_flips × cluster_factor`**（:337）——該式經 `pooled_flips`（pooled 跨 symbol）隨 symbol 數漲，是 breadth-contaminated。(b) 的 n_independent 用 PCA N_eff 限制 cross-section 維度 + **time-period count 取 min**（time-cluster 是 binding ceiling）。

### Step 4 — n_independent 計算規則（MIT-owned，(b) 機械化）
```
n_independent = min(
    time_period_count,         # binding ceiling（cost-wall：weekly+ ~8）
    pca_neff_adjusted_count    # cross-section 維度 clamp（N_eff/n_sym × pooled，但上限 time_period_count）
)
sample_unit 記錄於每 tier 行（S0 §2.9 mandatory）
```
- **time_period_count** = candidate-specific（holding window 數 / rebalance 數）；對固定 18mo 窗，core25 與 full **相同**（時間軸一致，只是 symbol 數不同）→ 這正是「breadth 不增 n_independent」的機械保證。
- **方法權威拆分（S0 c.5）**：`n_independent` clustering 正確性 = **MIT review**（time-cluster/BTC-beta 規則）；DSR/PBO/PSR 門檻數學 = **QC review**。(b) **計算並記錄** psr_0/dsr_k/pbo（用 lib.stats_common），門檻判定留 (c)/QC。

---

## 5. 輸出 `breadth_ladder.parquet` schema（S0 §1.3 + (c) `breadth_cohort` 軸對齊）

### breadth_ladder.csv / .parquet（每 tier 一行，凍結欄序）
```
run_id, ladder_id, candidate_id, breadth_ladder_version,
asof_utc, window_start_utc, window_end_utc, fnd2_universe_id, fnd2_run_id,
breadth_cohort,                          -- = tier 名（對齊 (c) verdict_matrix.breadth_cohort 軸）
breadth_symbol_count, seen_delisted_count,
tier_quality,                            -- 'ok' / 'liquidity_source_not_pit' / 'overlap_only'
tier_rank_pit_mode,                      -- 'n/a' / 'asof_constant'（top_liquidity caveat）
gross_bps, cost_bps, net_bps, net_to_cost_ratio,
is_sharpe, oos_sharpe,
n_independent, sample_unit, t_stat_hac,
psr_0, dsr_k, pbo, k_trials,
long_leg_net_bps, short_leg_net_bps,
pit_mask_source, leak_free_signal,
monotonicity_rank,                       -- tier 在 breadth 軸的序（core25=0 < top_liq=1 < full=2）
excluded_from_promotion, exclusion_reason
```

### breadth_ladder_summary.json
```
run_id, ladder_id, candidate_id, breadth_ladder_version,
fnd2_universe_id, fnd2_run_id, asof_utc, window_*,
tiers_evaluated[], per_tier_net_bps{}, per_tier_n_independent{}, per_tier_breadth{},
monotonicity{
  net_bps_monotonic_in_breadth: bool,    -- net edge 是否隨 breadth 加寬存活（非塌成 fluke）
  net_bps_trend: 'survives'|'decays'|'collapses_to_narrow'|'inconclusive',
  narrow_only_edge: bool,                -- edge 只在 core25 顯著 → breadth-limited 標記
  n_independent_invariant_to_breadth: bool,  -- ★ n_independent 不隨 symbol 膨脹（自證）
  binding_ceiling: 'time_period_count',  -- cost-wall：time-cluster 是 binding
},
delisted_proof_total, survivorship_inherited_from_fnd2: true,
verdict_hint: 'breadth_real' | 'breadth-limited' | 'narrow_fluke' | 'insufficient_n_independent'
```
- **monotonicity 判定邏輯（`ladder.py` 純函數）**：
  - `survives`：net_bps 在 core25→top_liq→full 不顯著衰減（且 full tier `n_independent ≥ 30` + significance hold）。
  - `collapses_to_narrow`：net_bps 在 full 顯著 < core25（edge 集中窄基）→ `narrow_only_edge=true` → S0 §2.8 `low_breadth` overlay → (c) 標 `breadth-limited`。
  - `insufficient_n_independent`：任何 tier `n_independent < 30`（S0 §2.9 gate 3）→ 整 ladder verdict_hint = sample-bound（cost-wall 8-rebalance 牆的機械化）。
- **`breadth_cohort` 欄直接餵 (c) verdict_matrix 的 `breadth_cohort` 軸**（S0 §2.9）。(b) **不**算 final_label（那是 (c) 的 5-axis 合成 + QC 門檻）；(b) 只供 `verdict_hint`（advisory）+ 機械化 monotonicity 證據。

### manifest.json（AEG-S0 §1.4 子集 — mirror FND-2 `artifact.build_manifest`）
`schema_version='aeg.alpha_history_run_manifest.v0.1'` / `run_id` / `program='AEG'` / `session_id` / `created_at_utc` / `created_by_role` / git provenance（sha/dirty/diff_sha256）/ `runtime_host` / `window_*` / `asof_utc` / `closed_bar_cutoff_utc` / `timezone='UTC'` / `ladder_id` / **`breadth_ladder_version='aeg_breadth_v0.1.0'`** / `candidate_id` / `fnd2_universe_id` / `fnd2_run_id`（provenance 鏈到 universe artifact）/ `source_tables=['market.klines','market.funding_rates','<fnd2 universe artifact>']` / `provenance_mode='artifact_manifest'` / `artifacts[]`（child digests）。

### Artifact root（跨平台，禁硬編碼 — mirror FND-2）
```
${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<run_id>/breadth_ladder.parquet (+ .csv/summary/manifest/index)
```

### `ladder_id` digest（determinism，mirror FND-2 `compute_universe_id`）
```
ladder_id = sha256( fnd2_universe_id || candidate_id || BREADTH_LADDER_VERSION ||
                    ordered_tier_digest )
ordered_tier_digest = sha256 of canonical-sorted (by tier name) TierResult rows
                      （float %.12g 固定格式化，row 固定排序）
```
同 FND-2 universe + 同 candidate + 同 storage → 同 ladder_id（T-determinism）。

---

## 6. Healthcheck `check_aeg_breadth_universe_pit()`（MIT b.6）

**斷言（FND-2 acceptance gate 機械化，抓 silent regression 回 current-survivor）**：
- 消費的 universe（任一 tier，至少 `full_survivorship`）在窗含 delisted 時，必有 `seen_delisted=true` 列 → `delisted_proof_total >= 1`（FND-2 真跑 255，遠超）。
- 若 `delisted_proof_total == 0` 但 FND-2 summary `survivor_rejection_status != PROVEN_NONE_IN_WINDOW` → **FAIL**（universe 被 silently truncate 成 current-survivor）。
- `survivorship_inherited_from_fnd2 == true`（(b) 沒自寫 mask）。
- **註冊位置**：`passive_wait_healthcheck/`（mirror 既有 `check_*` cron wrapper，與 FND-2 healthcheck 同處）。**read-only**，0 寫。CLAUDE「passive wait 須 healthcheck」滿足。
- 此 healthcheck 是 **artifact-level**（讀 breadth_ladder_summary.json + FND-2 universe_summary.json），非 DB freshness（(b) 0 DB 表）。

---

## 7. 測試計劃（E1/E4 用 — `ladder.py`+`tiers.py` 純函數 synthetic，Mac 可跑）

| # | Case | 構造 | 斷言（bite-proof）|
|---|---|---|---|
| **T-tier-nest** | tier 嵌套 | synthetic universe rows：BTCUSDT cohort_ids=[full,core25]、ALTUSDT=[full,top_liquidity_40_50]、DEADUSDT=[full,historical_delisted] | `core25 ⊆ top_liquidity_40_50 ⊆ full_survivorship`；BTCUSDT ∈ 全 3 tier；用 `recommended_tier` 組裝會 fail（互斥）→ 證明必須用 cohort_ids |
| **T-survivor-inherit** | mask 繼承 | universe row alive_from/alive_to 給定 | `evaluator` 收到的 alive_mask 精確 = FND-2 行值；(b) 0 自寫 listed_at 查詢（grep 靜態：無 `listed_at`/`symbol_universe_snapshots` SELECT in ladder/tiers/universe_artifact）|
| **T-breadth-not-nindep** | ★ breadth≠n_independent | 同時間窗、core25(25 sym) vs full(800 sym) 餵相同 time-period 結構的 synthetic TierResult | `n_independent(full) == n_independent(core25)`（time-cluster 不變）；`breadth_symbol_count(full) >> core25`；**若實作讓 n_independent 隨 symbol 漲 → fail**（核心 leak gate）|
| **T-monotonic-survives** | monotonicity 存活 | net_bps[core25]=10, [top_liq]=9, [full]=8（衰減但存活，n_indep≥30）| `net_bps_monotonic_in_breadth=true`；`net_bps_trend='survives'`；`verdict_hint='breadth_real'` |
| **T-monotonic-collapse** | narrow fluke | net_bps[core25]=20, [full]=1（塌縮窄基）| `narrow_only_edge=true`；`net_bps_trend='collapses_to_narrow'`；`verdict_hint='breadth-limited'`；S0 `low_breadth` overlay 標記 |
| **T-insufficient-n** | sample 牆 | 任一 tier n_independent=8（cost-wall weekly 牆）| `verdict_hint='insufficient_n_independent'`；該 tier `excluded_from_promotion=true`，reason 含 `n_independent_below_30` |
| **T-top-liq-pit-flag** | cross-section leak 標記 | top_liquidity tier | `tier_rank_pit_mode='asof_constant'`；`tier_quality='liquidity_source_not_pit'`；`excluded_from_promotion=true`（除非 OQ-B3 批准）|
| **T-determinism** | ladder_id 穩定 | 同 universe + 同 candidate 跑兩次 | `ladder_id` 相同；row bytes 相同；artifact_index sha256 相同（跨進程穩定）|
| **T-candidate-agnostic** | protocol 可插 | 兩個 stub CandidateEvaluator（不同 candidate_id）| 同 (b) 跑出兩組 ladder，`candidate_id` 正確隔離；(b) 0 候選硬編碼（grep：ladder/tiers 無候選名）|
| **T-forbidden-route** | read-only 靜態 | grep ladder/tiers/universe_artifact/artifact 源碼 | 0 `control_api_v1` import；0 DB write；0 `_fetch_historical_universe_snapshot_sync`；0 Bybit client；artifact root 用 `OPENCLAW_DATA_DIR`（無硬編碼 /tmp/openclaw）|
| **T-manifest-index** | artifact 完整 | 跑全 write（tmp dir）| breadth_ladder.csv + summary.json + manifest.json + artifact_index.json 皆生成；manifest 含 `fnd2_universe_id`/`fnd2_run_id` provenance 鏈；每 child 在 index 有 path/sha256/byte_size/row_count/schema_version |

**bite 證明哲學**（mirror FND-2/sibling）：T-tier-nest / T-breadth-not-nindep / T-monotonic-collapse / T-top-liq-pit-flag 必須證「錯誤實作會 fail」——特別 **T-breadth-not-nindep 是 (b) 的招牌 leak gate**（symbol-scaled n_independent = false-rich-sample 必被抓）。

**E4 regression**：`python3 -m pytest helper_scripts/research/tests/test_aeg_breadth_ladder.py -q` 全綠 + Linux read-only 真跑一次（用 FND-2 已存 artifact + 一個 reference candidate adapter，產 breadth_ladder artifact，summary `survivorship_inherited_from_fnd2=true` / `delisted_proof_total>=200`）。

---

## 8. 模組清單 + 每模組職責（acceptance #1）

| 模組 | 職責 | DB? | 純函數? |
|---|---|---|---|
| `__init__.py` | package marker + `BREADTH_LADDER_VERSION='aeg_breadth_v0.1.0'` / `LADDER_SCHEMA_VERSION` | 否 | n/a |
| `tiers.py` | 凍結 `BREADTH_TIERS` 定義 + `assemble_tiers(universe_rows)→{tier:set[symbol]}`（從 `cohort_ids` 組 nested）+ nested 不變量斷言 | 否 | 是 |
| `universe_artifact.py` | 讀 FND-2 universe.csv/.parquet（`included`/`cohort_ids`/`alive_from`/`alive_to`/`seen_delisted`）+ 組 alive_mask | 否（讀檔）| 近純（IO） |
| `ladder.py` | 純函數核心：{tier→TierResult}→per-tier net edge + significance + monotonicity + **breadth≠n_independent 分離** + ladder rows/summary + `ladder_id` digest | 否 | 是 |
| `evaluator.py` | `CandidateEvaluator` protocol + adapter（包 sibling candidate harness 為 per-tier `evaluate(universe,alive_mask)→TierResult`）| 是（委派候選 loader，read-only）| 否（注入邊界）|
| `artifact.py` | breadth_ladder.csv/.parquet + summary.json + manifest.json + index + sha256（mirror FND-2 artifact.py）| 否（寫本地檔）| 否（IO） |
| `harness.py` | CLI 編排：load FND-2 artifact → assemble tiers → per-tier evaluate → ladder → write → 印 summary（顯式窗無隱式 now()）| 否（編排）| 否 |
| `research/tests/test_aeg_breadth_ladder.py` | T-tier-nest..T-manifest-index（synthetic，Mac 可跑）| 否 | 是 |

---

## 9. E1 IMPL 任務分解（acceptance #3）

| 欄 | 值 |
|---|---|
| Ticket | AEG-S2-B-BREADTH-IMPL |
| Owner chain | PM → PA(done) → **E1** → E2 → MIT(leak/n_independent) + QC(significance 門檻 advisory) → PM |
| Branch | `feature/aeg-breadth-ladder`（fetch 已確認無同名 branch / 無 IMPL commit / 無 breadth 檔，§紀律對帳）|
| Mode | **read-from-storage-only**；0 DB write / 0 backfill / 0 schema / 0 migration / 0 deploy / 0 auth / 0 order / 0 IPC。CLAUDE 硬邊界 0 接觸。|
| Files（E1 新建，互不重疊）| `helper_scripts/research/aeg_breadth_ladder/{__init__,tiers,universe_artifact,ladder,evaluator,artifact,harness}.py` + `helper_scripts/research/tests/test_aeg_breadth_ladder.py` + `passive_wait_healthcheck/` 加 `check_aeg_breadth_universe_pit()` wrapper + 更新 `helper_scripts/SCRIPT_INDEX.md`（新 section）|
| 禁碰 | 既有 `fnd2_pit_universe/`（消費不改）；既有 `multiday_trend_diagnostic/` / `funding_tilt_diagnostic/`（adapter 呼用不改源碼）；任何 `control_api_v1/` runtime；任何 V### SQL；任何 platform-session 平行檔 |
| tier 組裝權威 | **本報告 §1.2（用 `cohort_ids` multi-membership 組 nested，NOT `recommended_tier`）**。E1 誤用 `recommended_tier` = E2 must-check #1 |
| n_independent 權威 | **本報告 §4 Step 3-4（time-cluster-bound，NOT symbol-scaled；不沿用 multiday `eff_n=pooled_flips×cluster_factor`）**。cost-wall report §51/§97-99 實證 |
| 統計復用 | `lib.stats_common`（PSR/DSR/PBO/bootstrap）+ sibling `funding_tilt_diagnostic.stats`（`pca_effective_n`/HAC）；**不新增統計函數複製**（memory 精簡審計）|
| 連線紀律 | 委派候選 harness 既有 `lib.pg_connect.resolve_report_dsn()` + `set_session(readonly=True)`（不新增連線 helper）|
| artifact 紀律 | mirror FND-2 `artifact.py`：`OPENCLAW_DATA_DIR` 跨平台 root + sha256 + manifest `fnd2_universe_id`/`fnd2_run_id` provenance 鏈 |
| 測試 | §7 全 case，`ladder.py`+`tiers.py` 純函數 synthetic（Mac 可跑），`python3 -m pytest helper_scripts/research/tests/test_aeg_breadth_ladder.py -q` 全綠才 IMPL DONE |
| 並行性 | **單一 E1**（檔互不重疊但 tiers↔ladder↔artifact↔harness 共享 TierResult schema 邏輯耦合度高，拆多 E1 反增協調成本）。**不拆並行。** |
| DoD | 11 test 綠 + 真跑一次 Linux read-only（用 FND-2 已存 artifact + 一 reference candidate adapter，產 breadth_ladder artifact，summary `survivorship_inherited_from_fnd2=true` / `delisted_proof_total>=200` / monotonicity 判定有值 / `n_independent_invariant_to_breadth=true`）。**E1 不自簽**：交 E2 對抗審 + MIT leak/n_independent 審（MIT b.5/b.6 機械化驗證）。|
| 估時 | ~7-9h（純函數 ladder/tiers 3h + universe_artifact 讀檔 1h + evaluator adapter 2h + artifact/manifest 1.5h + healthcheck 0.5h + 真跑驗 1h）|
| NO-OP exit | 若 E1 fetch 發現 branch 已有 IMPL commit → 停，回報，不重做。|

---

## 10. 副作用清單（PA 強制四問）

1. **有無其他模塊 import 這些檔？** 無——全新 package-dir，0 既有 caller。`research/` 非 Python package（靠 conftest sys.path），不會被 runtime 意外 import。
2. **改動函數在哪些測試被 mock？** 無——0 既有測試觸及；新檔自帶 test。**不改** sibling candidate harness（adapter 呼用既有 `run_diagnostic`，不動其源碼/測試）。
3. **asyncio/threading 邊界？** 無——純 sync batch CLI，無 async。
4. **改 API response schema？** 無——0 endpoint、0 route、0 IPC、0 schema。
5. **RustEngine↔Python IPC？** 無接觸。
6. **DB 寫面？** 0——`evaluator` 委派 read-only loader（`set_session(readonly=True)`）；artifact 寫本地檔系統，非 PG。**S2 無新 DB 表/migration**（MIT b.3：breadth artifact-only，DB 表 defer S3+）。
7. **改既有候選 harness？** 0——adapter 包裝呼用，不改源碼。若候選需重構成 universe-parametrized，那是該候選 follow-up（multiday 已是此形，listing-fade 待其 IMPL）。

---

## 11. 開放問題 / 風險（IMPL 前須解 / PM 確認）— acceptance #4

| # | 開放問題 | 建議 | gate |
|---|---|---|---|
| **OQ-B1** | Rust-first 例外是否 PM 批准（同 FND-2 OQ-1）? | 批准 Python research-builder lane（§D-1：one-shot read-only artifact builder，下游 (c) 全 Python；CLAUDE §七「unless local design says otherwise」；FND-2 已就此 lane 批准，breadth 繼承）| **PM sign-off** |
| **OQ-B2** | (b) 的**首個消費候選**是誰（決定 reference adapter）? | listing-fade（PM brief 指首消費者）；若 listing-fade IMPL 未就緒，先用 multiday 作 reference adapter 證 protocol（multiday 已 universe-parametrized）。**listing-fade 候選本身 IMPL 不在 (b) 範圍** | **PM 指定** |
| **OQ-B3** | top_liquidity_40_50 tier 的 asof-constant rank（非 per-rebalance PIT）可接受嗎? | **PA recommend：標 `liquidity_source_not_pit` + `excluded_from_promotion=true`（diagnostic-only），不阻 monotonicity 主軸（core25/full）**。真 per-rebalance PIT rank 無資料源（`market.market_tickers` latest-only，S0 §3.1；index/mark persistence bug S0 §1.7）。若 PM/MIT 接受 asof-constant 近似 → 改標 `asof_constant_accepted` 並納 promotion | **MIT + PM** |
| **OQ-B4** | candidate evaluator 需提供 oos_sharpe / walk-forward 嗎? | (b) schema 容忍 `oos_sharpe=None`（候選若無 walk-forward）；但 S0 §2.9 gate 7 `oos_sharpe>=0.5*is_sharpe` 是 (c) promotion gate——若候選不產 OOS，(c) 標 insufficient。**(b) 不強制候選做 walk-forward**（屬候選 IMPL）；只 passthrough | (c)/QC |
| **OQ-B5** | window / asof 確切值（首跑）? | CLI 參數，無隱式 now()；首跑用 FND-2 同窗（asof 2026-06-03 / window 2024-06-03→2026-06-03 / cutoff 2026-06-02）以對齊 universe artifact（PM 提供確切值）| PM 提供 |
| **R-1（風險）** | top_liquidity cross-section rank look-ahead（asof-constant）| §4 Step 2 已硬標 caveat + excluded_from_promotion（除非 OQ-B3 批准）。**E2 must-check #2**：確認 (b) 不把 asof-constant rank 偽裝成 PIT | E2/MIT must-check |
| **R-2（風險）** | breadth 偽裝 n_independent 膨脹（false-rich-sample）| §4 Step 3 T-breadth-not-nindep bite test：n_independent(full)==n_independent(core25)。**E2 must-check #3**：確認 n_independent 不隨 symbol 漲（這是 6 週 down-beta 偽裝 edge 教訓的機械防線；cost-wall 8-rebalance 牆）| E2/MIT must-check |
| **R-3（風險）** | 誤用 `recommended_tier`（single-pick）破 nested tier | §1.2 + T-tier-nest test。**E2 must-check #1**：確認 tier 組裝用 `cohort_ids` membership，BTCUSDT 同時在 core25/top_liq/full | E2 must-check |
| **R-4（風險）** | float 格式化平台漂移破 determinism（ladder_id）| mirror FND-2：`%.12g` 固定格式 + tier 固定排序；T-determinism 跨兩跑驗 byte-identical | E2 must-check |

---

## 12. E2 重點審查 3 點（PA 指定）

1. **tier 組裝源（R-3）**：確認 `tiers.py` 用 FND-2 `cohort_ids`（multi-membership）組 cumulative-nested，**NOT** `recommended_tier`（single-pick）。構造「BTCUSDT cohort_ids=[full,core25]」case，斷言 BTCUSDT 同時出現在 core25 / top_liquidity / full 三 tier。誤用 recommended_tier 會讓 tier 互斥、monotonicity 失真。**最易出錯點。**
2. **breadth ≠ n_independent 真有 bite（R-2，(b) 招牌 leak gate）**：確認 `n_independent(full 829 sym) ≈ n_independent(core25 25 sym)`（time-cluster 不變），**不**隨 symbol 數膨脹。確認 (b) 不沿用 multiday `eff_n=pooled_flips×cluster_factor`（symbol-contaminated）。這是「down-beta 偽裝 edge / cost-wall 8-rebalance 牆」教訓的機械防線。
3. **survivorship 繼承 + cross-section PIT + read-only（R-1）**：確認 alive_mask 從 FND-2 artifact 繼承（(b) 0 自寫 listed_at 查詢，靜態 grep）；top_liquidity tier 標 `asof_constant` caveat（不偽裝 PIT）；`evaluator` 全 `set_session(readonly=True)`；artifact 0 import runtime 模組；artifact root 用 `OPENCLAW_DATA_DIR`（無硬編碼）。

---

## 紀律對帳
全 read-from-storage-only 設計；fact（FND-2 IMPL code §1 + cost-wall 實證 §4 + FND-2 真跑數字）/inference（架構決策 §2-3）/assumption（OQ §11）分離；硬邊界 0 觸碰（無 execution/lease/live/order/auth/IPC 面）；S2 無新 DB 表/migration（MIT b.3）；不寫 feature code / 不執行回填 / 不改 TODO / 不建 SQL。NO-OP 確認：無同名 branch（`git branch -a` grep breadth/aeg-s2/ladder 空）/ 無 IMPL commit（`git log --all` grep 僅無關 live-trust ladder + memory log）/ 無同名 Python 檔（`find helper_scripts -iname *breadth*` 空）。multi-session：本報告具名檔 commit --only，不碰平行 session 檔。

**PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--aeg_s2_breadth_ladder_runner_impl_design.md**
