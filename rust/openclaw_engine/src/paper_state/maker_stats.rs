//! Paper maker-order statistics & KPI gate — EDGE-P2-3 Phase 1B-5.
//! 紙盤 maker 掛單統計 & KPI gate — EDGE-P2-3 Phase 1B-5。
//!
//! MODULE_NOTE (EN): Accumulates submit / fill-full / fill-partial / timeout
//!   counters for PostOnly resting orders on the Paper path, plus the running
//!   sum of `net_edge_bps` (bias-guard #4 adverse-selection metric). Offers a
//!   tri-state `MakerKpiStatus` gate the router consults before enqueuing so a
//!   symbol whose maker path is chronically unfilled or bleeding to adverse
//!   selection silently falls back to market execution instead of letting
//!   intents rot in the queue.
//!
//!   The statistics live on `PaperState` (one `MakerStats` per engine) — the
//!   exchange path tracks maker fills via WS and has its own observability, so
//!   there is no need to hoist this module above `paper_state`. Thresholds are
//!   hard-coded defaults now; a ConfigStore-backed override is a 1B-5 FUP.
//!
//! MODULE_NOTE (中): 累計紙盤 PostOnly 掛單的 submit / fill-full / fill-partial /
//!   timeout 計數器，以及 `net_edge_bps`（bias 保護 #4 adverse-selection）的
//!   running sum。Router 在 enqueue 前透過 `MakerKpiStatus` 三態 gate 檢查：
//!   若某 symbol 的 maker 路徑長期不成交或被 adverse-selection 侵蝕，靜默
//!   fallback 到市價成交，避免 intent 卡隊列。
//!
//!   統計資料掛在 `PaperState`（一引擎一份）—— 交易所路徑的 maker 成交走 WS
//!   + 自有 observability，不需把這模組升到 paper_state 之上。門檻暫時寫死；
//!   ConfigStore 動態覆寫列為 1B-5 FUP。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Per-scope counters (aggregate or per-symbol).
/// per-scope 計數器（總體或 per-symbol）。
///
/// `filled_full` / `filled_partial` are tracked separately so a future KPI can
/// distinguish "we cross the book" (full) vs "we sit at touch and coin-flip"
/// (partial) — the latter has inherently worse fill-rate predictability.
///
/// `sum_net_edge_bps` is a running sum across *all* fills whose
/// `mid_price_at_submit > 0.0`. Fills lacking a valid submit-mid (e.g. first
/// tick before any mid is available) still bump the fill counter but are
/// excluded from the edge sum so bootstrap ticks cannot poison the mean.
#[derive(Debug, Clone, Default)]
pub struct MakerStatsCounters {
    /// Total resting orders enqueued on this scope.
    /// 本 scope 累計進入 resting 隊列的掛單數。
    pub submitted: u64,
    /// Orders that filled via true cross (tick price crossed the limit).
    /// 經真實穿越（tick 價越過限價）成交的掛單數。
    pub filled_full: u64,
    /// Orders that filled via touch + deterministic coin-flip (1B-4.2 50%).
    /// 碰觸 + 確定性硬幣（1B-4.2 50%）成交的掛單數。
    pub filled_partial: u64,
    /// Orders drained by deadline without any fill.
    /// 到期未成交、被 sweep 清出隊列的掛單數。
    pub timedout: u64,
    /// Running sum of signed net edge in bps across valid fills. 1B-5 FUP-3:
    /// accumulated via Kahan summation (`sum_kahan_c` is the compensation
    /// term). Preserves low-order bits when adding small net_edge_bps values
    /// (±O(10⁰) bps) into a large running sum across thousands of fills.
    /// 有效成交的 net edge（bps）累加和。1B-5 FUP-3：以 Kahan summation 累加
    /// （`sum_kahan_c` 為補償項），於數千次成交的大總和中保留小增量精度。
    pub sum_net_edge_bps: f64,
    /// 1B-5 FUP-3: Kahan compensation term for `sum_net_edge_bps`. Should
    /// never be read by callers — exists purely to make the next add more
    /// precise. Keep `Default` so fresh instances start at 0.0.
    /// 1B-5 FUP-3：`sum_net_edge_bps` 的 Kahan 補償項。對外不應讀取，僅服務
    /// 於下一次加法精度。預設 0.0 與 `MakerStatsCounters::default()` 相容。
    pub sum_kahan_c: f64,
    /// Number of intents that skipped enqueue because the KPI gate reported
    /// `Degraded` — they silently fell back to market fill. Accumulated by
    /// caller (router) on gate rejection, not by the sweep path.
    /// KPI gate 回 `Degraded` 而被跳過 enqueue 的 intent 數（改走 market）。
    /// 由 router 在 gate 拒絕時累加，不由 sweep 路徑觸發。
    pub degraded_fallbacks: u64,
    /// EDGE-P2-3 Phase 1B-5 FUP-2: wall-clock ms of the most recent terminal
    /// event (fill or timeout) on this scope. 0 means "no terminal event yet"
    /// (distinct from a genuine timestamp since epoch). Drives the staleness
    /// gate: when `now - last_terminal_ms > cfg.stale_window_ms`, the KPI
    /// verdict resets to Cold regardless of sample count so a chronically idle
    /// symbol cannot stay stuck in a Degraded verdict from an old regime.
    /// 1B-5 FUP-2：本 scope 最後一次終局事件（fill / timeout）的 wall-clock ms。
    /// 0 = 尚未有終局事件。觸發 staleness gate：`now - last_terminal_ms > cfg
    /// .stale_window_ms` → KPI 結果重設為 Cold，避免長期閒置 symbol 卡在
    /// 舊 regime 的 Degraded 結論裡不得翻身。
    pub last_terminal_ms: u64,
    /// EDGE-P2-3 Phase 1B-4.3: number of sweep ticks on which the funding-drag
    /// guard (#3) converted a touch-equal `FillPartial` classification into
    /// `Keep`. Observability-only — it does NOT feed the KPI Degraded gate
    /// (chronic adverse funding is a real-world signal, not a maker-path
    /// defect) and it does NOT imply the order was cancelled (a deferred
    /// touch can still fill via true cross on a later tick, or time out).
    /// 1B-4.3：funding drag guard (#3) 把「碰觸」FillPartial 轉為 Keep 的 sweep
    /// 次數。僅供觀察 —— 不計入 KPI Degraded 判斷（長期負 funding 是市場
    /// 現象，非 maker 路徑故障），也不代表掛單被取消（後續 tick 仍可真實穿越
    /// 成交或超時）。
    pub funding_drag_skips: u64,
}

impl MakerStatsCounters {
    /// 1B-5 FUP-3: Kahan-style compensated add into `sum_net_edge_bps`.
    /// Preserves ≈1 ulp of precision per addition versus naive
    /// `sum += value`, which loses the low-order bits whenever the running
    /// sum dwarfs the increment — a common regime for `net_edge_bps` since
    /// individual fills typically report ±O(10⁰) bps while aggregate sums
    /// grow to O(10³) or larger across thousands of fills.
    /// 1B-5 FUP-3：Kahan 補償加法，單次加法保留約 1 ulp 精度；避免「大總和
    /// 蓋掉小增量」低位被截斷（net_edge_bps 單筆 ±O(1e0) bps，總和易長到
    /// O(1e3)+，正好踩中精度陷阱）。
    #[inline]
    fn kahan_add(&mut self, value: f64) {
        let y = value - self.sum_kahan_c;
        let t = self.sum_net_edge_bps + y;
        self.sum_kahan_c = (t - self.sum_net_edge_bps) - y;
        self.sum_net_edge_bps = t;
    }

    /// Total filled = full cross + partial (coin-flip). Used as edge-mean denom.
    /// 全部成交 = 真實穿越 + 碰觸硬幣。
    pub fn filled_total(&self) -> u64 {
        self.filled_full + self.filled_partial
    }

    /// Fill rate = filled / (filled + timedout). `None` when denom is zero so
    /// callers can distinguish "no samples" from "all timeouts".
    /// 成交率 = filled / (filled + timedout)。分母為 0 時回 None 以便區分
    /// 「無樣本」與「全超時」。
    pub fn fill_rate(&self) -> Option<f64> {
        let denom = self.filled_total() + self.timedout;
        if denom == 0 {
            None
        } else {
            Some(self.filled_total() as f64 / denom as f64)
        }
    }

    /// Mean `net_edge_bps` across filled orders with valid submit mid.
    /// `None` when there are zero valid samples.
    /// 平均 net_edge_bps（以 filled_total 為分母）。無樣本回 None。
    pub fn avg_net_edge_bps(&self) -> Option<f64> {
        let n = self.filled_total();
        if n == 0 {
            None
        } else {
            Some(self.sum_net_edge_bps / n as f64)
        }
    }

    /// Samples used for KPI gate freshness check = filled + timedout.
    /// Excludes `submitted`-only counts so a symbol with many in-flight
    /// resting orders but zero terminal events still reads as Cold.
    /// KPI gate 採用的樣本數 = filled + timedout。尚在隊列的 submitted
    /// 不計入，避免「很多掛單、零終局事件」被誤判為有效樣本。
    pub fn terminal_samples(&self) -> u64 {
        self.filled_total() + self.timedout
    }

    /// Evaluate KPI gate. Order of checks (first match wins):
    ///   0. staleness:    last terminal event older than stale_window_ms → Cold
    ///                    (1B-5 FUP-2: prevents sticky Degraded on idle symbols)
    ///   1. terminal_samples < min_samples → Cold (warmup, allow enqueue)
    ///   2. fill_rate < min_fill_rate       → Degraded("fill_rate_below_threshold")
    ///   3. avg_net_edge_bps < min_edge_bps → Degraded("net_edge_below_threshold")
    ///   4. otherwise                       → Healthy
    /// 先判 staleness → 樣本數 → 成交率 → 平均 edge → 其餘 Healthy。
    ///
    /// The staleness branch only fires when `cfg.stale_window_ms > 0` and
    /// `self.last_terminal_ms > 0` — a scope that never saw a terminal event
    /// is already Cold via the samples path, and `stale_window_ms = 0`
    /// disables decay entirely (useful in tests that pin to Healthy/Degraded).
    /// staleness 分支僅在 `cfg.stale_window_ms > 0` 且確實有過終局事件時觸發；
    /// `stale_window_ms = 0` 代表關閉衰減（測試鎖死 Healthy/Degraded 用）。
    pub fn kpi_status(&self, cfg: &MakerKpiConfig, now_ms: u64) -> MakerKpiStatus {
        if cfg.stale_window_ms > 0
            && self.last_terminal_ms > 0
            && now_ms.saturating_sub(self.last_terminal_ms) > cfg.stale_window_ms
        {
            return MakerKpiStatus::Cold;
        }
        if self.terminal_samples() < cfg.min_samples {
            return MakerKpiStatus::Cold;
        }
        if let Some(rate) = self.fill_rate() {
            if rate < cfg.min_fill_rate {
                return MakerKpiStatus::Degraded {
                    reason: "fill_rate_below_threshold",
                };
            }
        }
        if let Some(edge) = self.avg_net_edge_bps() {
            if edge < cfg.min_avg_net_edge_bps {
                return MakerKpiStatus::Degraded {
                    reason: "net_edge_below_threshold",
                };
            }
        }
        MakerKpiStatus::Healthy
    }
}

/// Top-level container: aggregate + per-symbol split.
/// 頂層容器：aggregate + per-symbol 拆分。
#[derive(Debug, Clone, Default)]
pub struct MakerStats {
    pub aggregate: MakerStatsCounters,
    pub per_symbol: HashMap<String, MakerStatsCounters>,
}

impl MakerStats {
    fn entry(&mut self, symbol: &str) -> &mut MakerStatsCounters {
        self.per_symbol
            .entry(symbol.to_string())
            .or_insert_with(MakerStatsCounters::default)
    }

    /// Record enqueue — bumps `submitted` on both aggregate and per-symbol.
    /// 記錄入隊 — aggregate 與 per-symbol 的 submitted 各 +1。
    pub fn record_submit(&mut self, symbol: &str) {
        self.aggregate.submitted += 1;
        self.entry(symbol).submitted += 1;
    }

    /// Record terminal fill event. `true_cross=true` → `filled_full`, else
    /// `filled_partial`. When `mid_price_at_submit > 0.0`, computes
    /// `net_edge_bps` (signed by side) minus fee bps and adds to sum on both
    /// aggregate and per-symbol scope. When submit-mid is 0 or fill-price is
    /// 0, counter is bumped but the edge sum is untouched (bootstrap safety).
    /// 記錄終局成交。`true_cross=true` 進 filled_full，否則 filled_partial。
    /// submit-mid > 0 時計算 `net_edge_bps`（含方向符號 − fee bps），並加到
    /// aggregate 與 per-symbol 的 sum。submit-mid 為 0 或成交價 0 → 只計數
    /// 不進 sum（bootstrap 保護）。
    #[allow(clippy::too_many_arguments)]
    pub fn record_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        mid_price_at_submit: f64,
        mid_price_at_fill: f64,
        qty: f64,
        fill_price: f64,
        fee: f64,
        true_cross: bool,
        now_ms: u64,
    ) {
        if true_cross {
            self.aggregate.filled_full += 1;
            self.entry(symbol).filled_full += 1;
        } else {
            self.aggregate.filled_partial += 1;
            self.entry(symbol).filled_partial += 1;
        }
        if let Some(net_bps) =
            compute_net_edge_bps(is_long, mid_price_at_submit, mid_price_at_fill, qty, fill_price, fee)
        {
            // 1B-5 FUP-3: Kahan-compensated add on both scopes. The helper
            // mutates `sum_net_edge_bps` + `sum_kahan_c` together.
            // 1B-5 FUP-3：兩個 scope 皆走 Kahan 補償加法。
            self.aggregate.kahan_add(net_bps);
            self.entry(symbol).kahan_add(net_bps);
        }
        // 1B-5 FUP-2: stamp last-terminal on both scopes so the staleness gate
        // can decay a chronically idle Degraded verdict back to Cold.
        // 1B-5 FUP-2：同步更新 aggregate 與 per-symbol 的終局時戳。
        self.aggregate.last_terminal_ms = now_ms;
        self.entry(symbol).last_terminal_ms = now_ms;
    }

    /// Record timeout — bumps `timedout` on both aggregate and per-symbol.
    /// 記錄超時 — aggregate 與 per-symbol 的 timedout 各 +1。
    pub fn record_timeout(&mut self, symbol: &str, now_ms: u64) {
        self.aggregate.timedout += 1;
        self.entry(symbol).timedout += 1;
        self.aggregate.last_terminal_ms = now_ms;
        self.entry(symbol).last_terminal_ms = now_ms;
    }

    /// Record a router-level degraded fallback (KPI gate rejected enqueue).
    /// 記錄 router 端的 Degraded fallback（KPI gate 拒絕 enqueue）。
    pub fn record_degraded_fallback(&mut self, symbol: &str) {
        self.aggregate.degraded_fallbacks += 1;
        self.entry(symbol).degraded_fallbacks += 1;
    }

    /// EDGE-P2-3 Phase 1B-4.3: bump `funding_drag_skips` on both aggregate and
    /// per-symbol when the sweep's funding-drag guard deferred a `FillPartial`
    /// touch into `Keep`. Observability-only — does not touch terminal counters
    /// or KPI inputs; same order may increment this across multiple ticks if
    /// funding stays adverse and price keeps touching the limit.
    /// EDGE-P2-3 Phase 1B-4.3：funding drag guard 將 FillPartial 改為 Keep 時，
    /// aggregate 與 per-symbol 的 `funding_drag_skips` 各 +1。純觀察用，不影響
    /// 終局 / KPI；同一張單在後續多個 tick 持續碰觸並逆向 funding 時會重複累計。
    pub fn record_funding_drag_skip(&mut self, symbol: &str) {
        self.aggregate.funding_drag_skips += 1;
        self.entry(symbol).funding_drag_skips += 1;
    }

    /// Resolve effective KPI status for `symbol`. Uses per-symbol counters
    /// when they have enough terminal samples; otherwise falls back to
    /// aggregate so cross-symbol experience can rescue a cold single symbol.
    /// 解析某 symbol 的有效 KPI 狀態。per-symbol 終局樣本足夠時以 per-symbol
    /// 判定；不足則 fallback 到 aggregate，讓單一 symbol 的冷啟動借用其他
    /// symbol 的經驗。
    pub fn status_for(&self, symbol: &str, cfg: &MakerKpiConfig, now_ms: u64) -> MakerKpiStatus {
        if let Some(per) = self.per_symbol.get(symbol) {
            // 1B-5 FUP-2: a per-symbol scope whose last terminal event is
            // older than the staleness window should not be "rescued" by its
            // own stale Degraded verdict — fall through to aggregate which
            // carries the freshest cross-symbol experience.
            // 1B-5 FUP-2：per-symbol 若自身終局事件已陳舊，不應被本身舊
            // Degraded 結論鎖定，直接落到 aggregate 借用其他 symbol 新經驗。
            let is_stale = cfg.stale_window_ms > 0
                && per.last_terminal_ms > 0
                && now_ms.saturating_sub(per.last_terminal_ms) > cfg.stale_window_ms;
            if !is_stale && per.terminal_samples() >= cfg.min_samples {
                return per.kpi_status(cfg, now_ms);
            }
        }
        self.aggregate.kpi_status(cfg, now_ms)
    }
}

/// KPI gate configuration. Conservative defaults chosen so the gate stays
/// *inactive* until enough data accumulates, then bites only on clearly bad
/// behaviour (fill rate <15% or avg edge <-5 bps).
///
/// EDGE-P2-3 Phase 1B-5: hot-reloadable via `ConfigStore<MakerKpiConfig>`.
/// `Serialize + Deserialize` are derived so the store can persist operator
/// patches to TOML via `with_toml_persist()`. All fields carry
/// `#[serde(default)]` + a matching module-level default fn so a partial TOML
/// (e.g. `funding_drag_threshold = 0.0008` only) leaves the rest at their
/// `impl Default` values — matches the RiskConfig / BudgetConfig pattern.
///
/// KPI gate 設定。預設保守：樣本不足時閒置，累積後只針對明確劣化（fill<15%
/// 或平均 edge<-5 bps）介入。EDGE-P2-3 Phase 1B-5：可透過
/// `ConfigStore<MakerKpiConfig>` 熱重載；`Serialize + Deserialize` 讓 store
/// 能以 `with_toml_persist()` 把 operator 補丁落回 TOML。每個欄位皆 `#[serde
/// (default)]` + 對應 module-level default fn，使部分 TOML（例如只寫
/// funding_drag_threshold）其餘欄位沿用 `impl Default`，與 RiskConfig /
/// BudgetConfig 模式一致。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MakerKpiConfig {
    /// Terminal samples required before the gate evaluates fill_rate / edge.
    /// gate 開始評估前的最少終局樣本數。
    #[serde(default = "default_min_samples")]
    pub min_samples: u64,
    /// Fill rate floor (filled / (filled + timedout)). Below → Degraded.
    /// 成交率下限。低於此值 → Degraded。
    #[serde(default = "default_min_fill_rate")]
    pub min_fill_rate: f64,
    /// Mean net edge floor in bps. Below → Degraded.
    /// 平均 net edge 下限（bps）。低於此值 → Degraded。
    #[serde(default = "default_min_avg_net_edge_bps")]
    pub min_avg_net_edge_bps: f64,
    /// 1B-5 FUP-2: staleness window in ms. When `now - last_terminal_ms`
    /// exceeds this, the KPI verdict resets to Cold regardless of sample
    /// count — prevents a symbol whose regime flipped (e.g. scanner swapped
    /// it out for an hour) from being stuck in a stale Degraded verdict.
    /// `0` disables staleness decay (tests + fixed-clock scenarios).
    /// 1B-5 FUP-2：陳舊窗口（ms）。`now - last_terminal_ms` 超過時 KPI 結論
    /// 重設為 Cold，避免 regime 已變（掃描器輪替等）卻被舊 Degraded 鎖住。
    /// `0` 關閉衰減（測試/固定時鐘情境）。
    #[serde(default = "default_stale_window_ms")]
    pub stale_window_ms: u64,
    /// EDGE-P2-3 Phase 1B-4.3: absolute funding-rate threshold above which the
    /// maker sweep defers touch-equal (`FillPartial`) fills whose side is on
    /// the wrong end of funding. Expressed as a decimal (0.0001 = 1 bps per
    /// 8h settlement). Default `0.0005` (≈5 bps / 8h ≈ 55% annualised) — well
    /// above the ±1 bps typical regime, bites only when funding is unambiguously
    /// hostile to one side. `0.0` disables the guard entirely (tests +
    /// deployments that don't want maker exposure shaped by funding).
    /// True-cross `FillFull` and deadline `Timeout` are NEVER shaped by this
    /// guard — it only touches the coin-flip branch where real-market fills
    /// are statistically adverse-selected.
    /// EDGE-P2-3 Phase 1B-4.3：funding rate 絕對值閾值，超過時 sweep 會把「碰觸」
    /// FillPartial 於逆向 funding 側的掛單改判 Keep。decimal 表示
    /// （0.0001 = 8h 1 bps）。預設 `0.0005`（≈5 bps / 8h ≈ 55% 年化）——遠高於
    /// ±1 bps 常態，只有 funding 明顯敵對時介入。`0.0` 關閉本 guard。真實穿越
    /// FillFull 與 Timeout 不受此 guard 影響 —— 僅限硬幣投擲分支，真實市場
    /// 於該分支存在統計意義上的 adverse selection。
    #[serde(default = "default_funding_drag_threshold")]
    pub funding_drag_threshold: f64,
}

// ─── module-level defaults / 模組級預設值 ───────────────────────────────────
// 與 `impl Default for MakerKpiConfig` 對齊；serde `#[serde(default = "...")]`
// 要求每欄位一個無引數 fn，所以分開寫而非直接讀 Default::default()。
fn default_min_samples() -> u64 {
    20
}
fn default_min_fill_rate() -> f64 {
    0.15
}
fn default_min_avg_net_edge_bps() -> f64 {
    -5.0
}
fn default_stale_window_ms() -> u64 {
    1_800_000
}
fn default_funding_drag_threshold() -> f64 {
    0.0005
}

impl Default for MakerKpiConfig {
    fn default() -> Self {
        // Delegate to the module-level defaults so `#[serde(default = ...)]`
        // and `impl Default` cannot drift. See defaults above for rationale:
        // * stale_window_ms = 30 min — longer than any normal trading lull so
        //   a quiet hour doesn't wipe a valid Degraded verdict, short enough
        //   to unlock a scanner-rotated symbol within a reasonable delay.
        // * funding_drag_threshold = 0.0005 = 5 bps / 8h ≈ 55% annualised —
        //   conservative ceiling so the guard bites only on unambiguously
        //   hostile regimes (steady-state funding is ±1 bps / 8h). Operators
        //   that want the guard disabled set this to `0.0`.
        // 統一指向 module-level defaults，避免 serde default 與 impl Default 漂移。
        Self {
            min_samples: default_min_samples(),
            min_fill_rate: default_min_fill_rate(),
            min_avg_net_edge_bps: default_min_avg_net_edge_bps(),
            stale_window_ms: default_stale_window_ms(),
            funding_drag_threshold: default_funding_drag_threshold(),
        }
    }
}

impl MakerKpiConfig {
    /// EDGE-P2-3 Phase 1B-5 FUP-4: validate invariants so `ConfigStore::apply_patch`
    /// (which accepts a `FnOnce(&T) -> Result<(), String>` validator) can reject
    /// bad operator patches atomically without polluting the live snapshot. Mirrors
    /// the RiskConfig / BudgetConfig validate contract (string error for operator
    /// readability, no panic). `MakerKpiConfig::default()` MUST satisfy `Ok(())` —
    /// enforced by `test_maker_kpi_config_validate_default_ok`.
    ///
    /// Rules:
    ///   * `min_fill_rate` ∈ [0.0, 1.0]                — rate is a fraction.
    ///   * `min_avg_net_edge_bps` ≤ 0.0 or finite      — a positive floor means
    ///                                                   "demand profit from day 1
    ///                                                   even in cold-start", which
    ///                                                   would deadlock the gate;
    ///                                                   reject >0 explicitly.
    ///   * `funding_drag_threshold` ≥ 0.0 and finite   — decimal, unsigned semantics
    ///                                                   (guard checks |rate|).
    ///                                                   `0.0` disables the guard.
    ///   * All f64 must be finite (NaN/Inf defeats comparisons silently).
    /// `stale_window_ms` / `min_samples` are `u64` so non-negative by type; `0`
    /// has well-defined semantics (disable staleness / evaluate-from-first-sample).
    ///
    /// EDGE-P2-3 Phase 1B-5 FUP-4：驗證不變量，供 `ConfigStore::apply_patch`
    /// 將錯誤 operator 補丁在未汙染 live snapshot 前就拒絕。與 RiskConfig /
    /// BudgetConfig 的 validate 契約一致（字串錯誤便於 operator 閱讀、不 panic）。
    /// `MakerKpiConfig::default()` 必須滿足 `Ok(())`。
    pub fn validate(&self) -> Result<(), String> {
        if !self.min_fill_rate.is_finite() || !(0.0..=1.0).contains(&self.min_fill_rate) {
            return Err(format!(
                "maker_kpi.min_fill_rate must be in [0.0, 1.0] and finite (got {})",
                self.min_fill_rate
            ));
        }
        if !self.min_avg_net_edge_bps.is_finite() {
            return Err(format!(
                "maker_kpi.min_avg_net_edge_bps must be finite (got {})",
                self.min_avg_net_edge_bps
            ));
        }
        if self.min_avg_net_edge_bps > 0.0 {
            return Err(format!(
                "maker_kpi.min_avg_net_edge_bps must be <= 0.0 (a positive floor would \
                 permanently mark cold-start symbols Degraded and deadlock the gate; got {})",
                self.min_avg_net_edge_bps
            ));
        }
        if !self.funding_drag_threshold.is_finite() || self.funding_drag_threshold < 0.0 {
            return Err(format!(
                "maker_kpi.funding_drag_threshold must be >= 0.0 and finite \
                 (guard uses |rate|; 0.0 disables; got {})",
                self.funding_drag_threshold
            ));
        }
        Ok(())
    }
}

/// Tri-state gate result. `Cold` means "insufficient samples, allow enqueue"
/// — treated as pass at call sites. `Degraded` is a hard stop that routes the
/// intent to market execution.
/// 三態 gate 結果。Cold=樣本不足，允許 enqueue；Degraded=強制 fallback 市價。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MakerKpiStatus {
    Cold,
    Healthy,
    Degraded { reason: &'static str },
}

impl MakerKpiStatus {
    /// True when the gate explicitly wants the caller to bypass enqueue.
    /// gate 明確要求 caller 跳過 enqueue 時為 true。
    pub fn is_degraded(&self) -> bool {
        matches!(self, MakerKpiStatus::Degraded { .. })
    }
}

/// Compute `net_edge_bps` for a single filled maker order.
///
/// Formula:
///   side_sign     = +1.0 long / -1.0 short
///   price_edge_bps = side_sign * (mid_fill - mid_submit) / mid_submit * 10_000
///   fee_bps        = fee / (qty * fill_price) * 10_000   (always ≥ 0)
///   net_edge_bps   = price_edge_bps - fee_bps
///
/// Returns `None` when the inputs cannot produce a meaningful metric:
///   * `mid_price_at_submit <= 0.0` (unknown at enqueue)
///   * `qty <= 0.0` or `fill_price <= 0.0` (can't normalise fee to bps)
/// The caller counts the fill regardless; the sum merely skips these cases
/// so bootstrap ticks can't poison the mean.
///
/// 公式：
///   side_sign     = 多 +1 / 空 −1
///   price_edge_bps = side_sign × (mid_fill − mid_submit) / mid_submit × 1e4
///   fee_bps        = fee / (qty × fill_price) × 1e4（恆 ≥ 0）
///   net_edge_bps   = price_edge_bps − fee_bps
///
/// 下列情況回 None（只計數、不進 sum）：submit-mid ≤ 0、qty ≤ 0、成交價 ≤ 0。
pub fn compute_net_edge_bps(
    is_long: bool,
    mid_price_at_submit: f64,
    mid_price_at_fill: f64,
    qty: f64,
    fill_price: f64,
    fee: f64,
) -> Option<f64> {
    if mid_price_at_submit <= 0.0 || qty <= 0.0 || fill_price <= 0.0 {
        return None;
    }
    let side_sign = if is_long { 1.0 } else { -1.0 };
    let price_edge_bps =
        side_sign * (mid_price_at_fill - mid_price_at_submit) / mid_price_at_submit * 10_000.0;
    let fee_bps = fee / (qty * fill_price) * 10_000.0;
    Some(price_edge_bps - fee_bps)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg_default() -> MakerKpiConfig {
        MakerKpiConfig::default()
    }

    // ────────────────────────────────────────────────────────────────
    // compute_net_edge_bps / net_edge 公式
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn net_edge_long_favorable_price_move() {
        // Long: submit mid 100 → fill mid 101 → +100 bps before fee.
        // Fee = 0.02 bps of notional. Net ≈ 100 - 0.02 (tiny) - actual.
        // qty=1, fill_price=100, fee=0.001 → fee_bps = 0.001/(1*100)*1e4 = 0.1
        let v = compute_net_edge_bps(true, 100.0, 101.0, 1.0, 100.0, 0.001).unwrap();
        assert!((v - (100.0 - 0.1)).abs() < 1e-9, "got {v}");
    }

    #[test]
    fn net_edge_long_adverse_move() {
        // Long: submit mid 100 → fill mid 99 → -100 bps price edge.
        let v = compute_net_edge_bps(true, 100.0, 99.0, 1.0, 100.0, 0.0).unwrap();
        assert!((v - (-100.0)).abs() < 1e-9, "got {v}");
    }

    #[test]
    fn net_edge_short_favorable_is_price_down() {
        // Short: favorable = mid dropped after submit.
        // side_sign=-1; (99-100)/100*1e4 = -100; signed = +100 (favorable).
        let v = compute_net_edge_bps(false, 100.0, 99.0, 1.0, 100.0, 0.0).unwrap();
        assert!((v - 100.0).abs() < 1e-9, "got {v}");
    }

    #[test]
    fn net_edge_short_adverse_is_price_up() {
        let v = compute_net_edge_bps(false, 100.0, 101.0, 1.0, 100.0, 0.0).unwrap();
        assert!((v - (-100.0)).abs() < 1e-9, "got {v}");
    }

    #[test]
    fn net_edge_returns_none_when_submit_mid_zero() {
        assert!(compute_net_edge_bps(true, 0.0, 100.0, 1.0, 100.0, 0.0).is_none());
    }

    #[test]
    fn net_edge_returns_none_when_qty_zero() {
        assert!(compute_net_edge_bps(true, 100.0, 100.0, 0.0, 100.0, 0.0).is_none());
    }

    #[test]
    fn net_edge_returns_none_when_fill_price_zero() {
        assert!(compute_net_edge_bps(true, 100.0, 100.0, 1.0, 0.0, 0.0).is_none());
    }

    // ────────────────────────────────────────────────────────────────
    // MakerStatsCounters: fill_rate / avg / kpi_status
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn fill_rate_zero_denom_returns_none() {
        let c = MakerStatsCounters::default();
        assert!(c.fill_rate().is_none());
    }

    #[test]
    fn fill_rate_with_samples() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 3;
        c.filled_partial = 1;
        c.timedout = 6;
        // 4 / (4 + 6) = 0.4
        assert!((c.fill_rate().unwrap() - 0.4).abs() < 1e-9);
    }

    #[test]
    fn avg_net_edge_zero_fills_returns_none() {
        let c = MakerStatsCounters::default();
        assert!(c.avg_net_edge_bps().is_none());
    }

    #[test]
    fn avg_net_edge_mean() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 2;
        c.sum_net_edge_bps = 10.0; // mean = 5.0
        assert!((c.avg_net_edge_bps().unwrap() - 5.0).abs() < 1e-9);
    }

    /// Convenience: "now" that is always past any seeded last_terminal_ms in
    /// non-staleness tests, but under the default 30-min window so staleness
    /// stays inactive.
    /// 測試輔助：代表「現在」，對 seed 的 last_terminal_ms 而言不會觸發 staleness。
    const NOW_MS_FRESH: u64 = 10_000;

    #[test]
    fn kpi_status_cold_when_samples_below_min() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 5;
        c.timedout = 5;
        c.last_terminal_ms = NOW_MS_FRESH;
        let cfg = cfg_default(); // min_samples = 20
        assert_eq!(c.kpi_status(&cfg, NOW_MS_FRESH), MakerKpiStatus::Cold);
    }

    #[test]
    fn kpi_status_healthy_when_above_thresholds() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 18;
        c.timedout = 2;
        c.sum_net_edge_bps = 18.0; // mean = +1.0 bps
        c.last_terminal_ms = NOW_MS_FRESH;
        let cfg = cfg_default();
        assert_eq!(c.kpi_status(&cfg, NOW_MS_FRESH), MakerKpiStatus::Healthy);
    }

    #[test]
    fn kpi_status_degraded_low_fill_rate() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 2; // fill_rate = 2/20 = 0.1 (< 0.15)
        c.timedout = 18;
        c.sum_net_edge_bps = 0.0;
        c.last_terminal_ms = NOW_MS_FRESH;
        let cfg = cfg_default();
        match c.kpi_status(&cfg, NOW_MS_FRESH) {
            MakerKpiStatus::Degraded { reason } => {
                assert_eq!(reason, "fill_rate_below_threshold")
            }
            other => panic!("expected Degraded fill_rate, got {:?}", other),
        }
    }

    #[test]
    fn kpi_status_degraded_low_edge() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 18; // fill_rate = 18/20 = 0.9
        c.timedout = 2;
        c.sum_net_edge_bps = -200.0; // mean = -11.1 bps (< -5)
        c.last_terminal_ms = NOW_MS_FRESH;
        let cfg = cfg_default();
        match c.kpi_status(&cfg, NOW_MS_FRESH) {
            MakerKpiStatus::Degraded { reason } => {
                assert_eq!(reason, "net_edge_below_threshold")
            }
            other => panic!("expected Degraded edge, got {:?}", other),
        }
    }

    #[test]
    fn kpi_status_fill_rate_beats_edge_when_both_bad() {
        // Both fill_rate and edge below thresholds → fill_rate reason wins
        // (checked first). Stable reason ordering keeps downstream histograms
        // single-bucketed.
        let mut c = MakerStatsCounters::default();
        c.filled_full = 2; // rate 0.1
        c.timedout = 18;
        c.sum_net_edge_bps = -200.0; // mean very negative
        c.last_terminal_ms = NOW_MS_FRESH;
        let cfg = cfg_default();
        match c.kpi_status(&cfg, NOW_MS_FRESH) {
            MakerKpiStatus::Degraded { reason } => {
                assert_eq!(reason, "fill_rate_below_threshold")
            }
            other => panic!("expected Degraded fill_rate precedence, got {:?}", other),
        }
    }

    // ────────────────────────────────────────────────────────────────
    // 1B-5 FUP-2: staleness window decay
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn staleness_decays_degraded_to_cold_after_window() {
        // Build a Degraded-by-fill-rate counter, then advance time past the
        // staleness window. Expect: verdict resets to Cold.
        // 建造 fill-rate Degraded 的計數器，時間過了 stale window 後應回 Cold。
        let mut c = MakerStatsCounters::default();
        c.filled_full = 2;
        c.timedout = 18;
        c.last_terminal_ms = 1_000;
        let cfg = cfg_default(); // stale_window_ms = 1_800_000 (30 min)

        // Still fresh — Degraded verdict holds.
        let now_fresh = 1_000 + 60_000; // +1 min
        assert!(matches!(
            c.kpi_status(&cfg, now_fresh),
            MakerKpiStatus::Degraded { .. }
        ));

        // Past window — Cold.
        let now_stale = 1_000 + cfg.stale_window_ms + 1;
        assert_eq!(c.kpi_status(&cfg, now_stale), MakerKpiStatus::Cold);
    }

    #[test]
    fn staleness_zero_window_disables_decay() {
        // With stale_window_ms = 0, the staleness branch is inactive — even a
        // very old last_terminal_ms keeps the verdict at Degraded.
        // stale_window_ms=0 表示關閉衰減，舊時戳仍保 Degraded。
        let mut c = MakerStatsCounters::default();
        c.filled_full = 2;
        c.timedout = 18;
        c.last_terminal_ms = 1_000;
        let mut cfg = cfg_default();
        cfg.stale_window_ms = 0;
        assert!(matches!(
            c.kpi_status(&cfg, 9_999_999_999),
            MakerKpiStatus::Degraded { .. }
        ));
    }

    #[test]
    fn staleness_not_triggered_when_no_terminal_events_yet() {
        // `last_terminal_ms = 0` sentinel means "never had a terminal event".
        // The staleness branch must not fire on the sentinel (else a fresh
        // counter would mis-trip on any now_ms > stale_window_ms).
        // 0 = sentinel「未有終局事件」，staleness 分支不應觸發。
        let c = MakerStatsCounters::default(); // last_terminal_ms = 0
        let cfg = cfg_default();
        // Cold comes from insufficient samples, not from staleness — both
        // paths return Cold here, but the point is "no spurious fire".
        assert_eq!(c.kpi_status(&cfg, 9_999_999_999), MakerKpiStatus::Cold);
    }

    #[test]
    fn staleness_per_symbol_falls_through_to_aggregate() {
        // Per-symbol BTCUSDT is stale-and-Degraded; aggregate is fresh-Healthy
        // via ETHUSDT. status_for(BTCUSDT) must ignore stale per-symbol and
        // fall through to aggregate → Healthy.
        // 過期 per-symbol 應被跳過，fallback 到新 aggregate → Healthy。
        let mut s = MakerStats::default();
        // BTCUSDT stuck Degraded at t=1_000
        for _ in 0..2 {
            s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, 1_000);
        }
        for _ in 0..18 {
            s.record_timeout("BTCUSDT", 1_000);
        }
        // ETHUSDT healthy, recent
        let now = 1_000 + 1_800_000 + 10_000; // past window for BTC
        for _ in 0..20 {
            s.record_fill("ETHUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, now);
        }
        let cfg = cfg_default();
        assert_eq!(s.status_for("BTCUSDT", &cfg, now), MakerKpiStatus::Healthy);
    }

    /// 1B-5 FUP-3: Kahan-compensated sum must preserve more precision than
    /// a naive `+=` when the running sum grows large relative to the
    /// increment. We exercise `kahan_add` directly against a naive `+=`
    /// control using bit-identical increments so the comparison isolates
    /// the accumulation strategy (not rounding in `compute_net_edge_bps`).
    /// 1B-5 FUP-3：Kahan 補償在「大總和 + 小增量」情境下保留多位精度；
    /// 直接對 `kahan_add` 與 naive `+=` 餵 bit-identical 增量，隔離出累加策略
    /// 的差異（不摻入 `compute_net_edge_bps` 的捨入）。
    #[test]
    fn kahan_sum_preserves_precision_vs_naive() {
        // One large seed + 10_000 tiny additions. Exact math:
        //   1e4 + 10_000 × 1e-8 = 10_000.0001
        // Naive f64 `+=` loses the low-order bits each add (the ulp of 1e4 is
        // ~2e-12, far larger than 1e-8 once accumulated), so the sum drifts.
        // Kahan keeps the compensation term and recovers ≈ full precision.
        let mut kahan = MakerStatsCounters::default();
        kahan.kahan_add(1e4);
        for _ in 0..10_000 {
            kahan.kahan_add(1e-8);
        }

        let mut naive: f64 = 1e4;
        for _ in 0..10_000 {
            naive += 1e-8;
        }

        let expected = 1e4 + 1e-4;
        let kahan_err = (kahan.sum_net_edge_bps - expected).abs();
        let naive_err = (naive - expected).abs();

        assert!(
            kahan_err <= naive_err,
            "Kahan err {kahan_err} must be ≤ naive err {naive_err}"
        );
        // Kahan should land within a few ulps of the exact sum; naive
        // typically drifts by ~1e-4 (essentially losing the entire tail sum).
        assert!(kahan_err < 1e-12, "Kahan err {kahan_err} should be ≤ 1e-12");
        assert!(
            naive_err > 1e-9,
            "naive err {naive_err} should visibly drift (control sanity)"
        );
    }

    #[test]
    fn kahan_sum_matches_reset_semantics() {
        // Default `MakerStatsCounters` has `sum_net_edge_bps = 0.0` and
        // `sum_kahan_c = 0.0` — clearing via `MakerStats::default()` must
        // zero both halves so no compensation bits survive reset.
        // default() 必須同時清零 sum + compensation，避免殘留。
        let mut s = MakerStats::default();
        s.record_fill("BTCUSDT", true, 100.0, 101.0, 1.0, 101.0, 0.0, true, NOW_MS_FRESH);
        assert!(s.aggregate.sum_net_edge_bps != 0.0);
        // Reset by replacement (mimics FUP-1 clear path).
        s = MakerStats::default();
        assert_eq!(s.aggregate.sum_net_edge_bps, 0.0);
        assert_eq!(s.aggregate.sum_kahan_c, 0.0);
    }

    #[test]
    fn record_fill_stamps_last_terminal_ms() {
        let mut s = MakerStats::default();
        s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, 42_000);
        assert_eq!(s.aggregate.last_terminal_ms, 42_000);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().last_terminal_ms, 42_000);
    }

    #[test]
    fn record_timeout_stamps_last_terminal_ms() {
        let mut s = MakerStats::default();
        s.record_timeout("BTCUSDT", 77_000);
        assert_eq!(s.aggregate.last_terminal_ms, 77_000);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().last_terminal_ms, 77_000);
    }

    // ────────────────────────────────────────────────────────────────
    // MakerStats: aggregate & per-symbol wiring
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn record_submit_updates_both_scopes() {
        let mut s = MakerStats::default();
        s.record_submit("BTCUSDT");
        s.record_submit("ETHUSDT");
        s.record_submit("BTCUSDT");
        assert_eq!(s.aggregate.submitted, 3);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().submitted, 2);
        assert_eq!(s.per_symbol.get("ETHUSDT").unwrap().submitted, 1);
    }

    #[test]
    fn record_fill_full_vs_partial_counters() {
        let mut s = MakerStats::default();
        // true_cross=true → filled_full
        s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, NOW_MS_FRESH);
        // true_cross=false → filled_partial
        s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, false, NOW_MS_FRESH);
        assert_eq!(s.aggregate.filled_full, 1);
        assert_eq!(s.aggregate.filled_partial, 1);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().filled_full, 1);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().filled_partial, 1);
    }

    #[test]
    fn record_fill_adds_to_sum_only_when_submit_mid_valid() {
        let mut s = MakerStats::default();
        // Valid submit mid → sum += net_edge_bps (= 0 in this case since
        // mid_fill == mid_submit and fee = 0).
        s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, NOW_MS_FRESH);
        assert_eq!(s.aggregate.sum_net_edge_bps, 0.0);
        assert_eq!(s.aggregate.filled_full, 1);

        // Unknown submit mid (0.0) → count the fill but skip sum.
        s.record_fill("BTCUSDT", true, 0.0, 100.0, 1.0, 100.0, 0.0, true, NOW_MS_FRESH);
        assert_eq!(s.aggregate.filled_full, 2);
        assert_eq!(s.aggregate.sum_net_edge_bps, 0.0, "bootstrap tick must not poison sum");
    }

    #[test]
    fn record_fill_accumulates_signed_edge() {
        let mut s = MakerStats::default();
        // Long favorable: mid 100 → 101 = +100 bps, fee=0 → net=+100
        s.record_fill("BTCUSDT", true, 100.0, 101.0, 1.0, 101.0, 0.0, true, NOW_MS_FRESH);
        // Short favorable: mid 100 → 99 = +100 bps (signed), fee=0 → net=+100
        s.record_fill("BTCUSDT", false, 100.0, 99.0, 1.0, 99.0, 0.0, true, NOW_MS_FRESH);
        assert!((s.aggregate.sum_net_edge_bps - 200.0).abs() < 1e-6);
        // Per-symbol should mirror aggregate (only 1 symbol active).
        let per = s.per_symbol.get("BTCUSDT").unwrap();
        assert!((per.sum_net_edge_bps - 200.0).abs() < 1e-6);
    }

    #[test]
    fn record_timeout_updates_both_scopes() {
        let mut s = MakerStats::default();
        s.record_timeout("BTCUSDT", NOW_MS_FRESH);
        s.record_timeout("ETHUSDT", NOW_MS_FRESH);
        assert_eq!(s.aggregate.timedout, 2);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().timedout, 1);
        assert_eq!(s.per_symbol.get("ETHUSDT").unwrap().timedout, 1);
    }

    #[test]
    fn record_degraded_fallback_bumps_counter() {
        let mut s = MakerStats::default();
        s.record_degraded_fallback("BTCUSDT");
        s.record_degraded_fallback("BTCUSDT");
        assert_eq!(s.aggregate.degraded_fallbacks, 2);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().degraded_fallbacks, 2);
    }

    // ────────────────────────────────────────────────────────────────
    // MakerStats::status_for — per-symbol with aggregate fallback
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn status_for_unknown_symbol_uses_aggregate() {
        let mut s = MakerStats::default();
        // Build healthy aggregate on a different symbol.
        for _ in 0..18 {
            s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, NOW_MS_FRESH);
        }
        for _ in 0..2 {
            s.record_timeout("BTCUSDT", NOW_MS_FRESH);
        }
        // Unknown symbol → no per-symbol entry → aggregate path.
        let cfg = cfg_default();
        assert_eq!(
            s.status_for("NEWCOIN", &cfg, NOW_MS_FRESH),
            MakerKpiStatus::Healthy
        );
    }

    #[test]
    fn status_for_per_symbol_takes_over_when_enough_samples() {
        let mut s = MakerStats::default();
        // Aggregate mixes two symbols into Healthy, but BTCUSDT alone is bad.
        // BTCUSDT: 2 fills / 18 timeouts → fill_rate 0.1 (Degraded)
        for _ in 0..2 {
            s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, NOW_MS_FRESH);
        }
        for _ in 0..18 {
            s.record_timeout("BTCUSDT", NOW_MS_FRESH);
        }
        // ETHUSDT: 30 fills / 0 timeouts → fill_rate 1.0 (Healthy)
        for _ in 0..30 {
            s.record_fill("ETHUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, NOW_MS_FRESH);
        }
        let cfg = cfg_default();
        // BTCUSDT has 20 terminal samples → its own counters decide → Degraded.
        match s.status_for("BTCUSDT", &cfg, NOW_MS_FRESH) {
            MakerKpiStatus::Degraded { reason } => {
                assert_eq!(reason, "fill_rate_below_threshold")
            }
            other => panic!("expected BTCUSDT Degraded, got {:?}", other),
        }
        // ETHUSDT: Healthy from its own counters.
        assert_eq!(
            s.status_for("ETHUSDT", &cfg, NOW_MS_FRESH),
            MakerKpiStatus::Healthy
        );
    }

    #[test]
    fn status_for_cold_symbol_falls_back_to_aggregate() {
        let mut s = MakerStats::default();
        // Aggregate healthy via ETHUSDT (20 fills, 0 timeouts).
        for _ in 0..20 {
            s.record_fill("ETHUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true, NOW_MS_FRESH);
        }
        // BTCUSDT only has 1 timeout → terminal_samples=1 < 20 → fallback.
        s.record_timeout("BTCUSDT", NOW_MS_FRESH);
        let cfg = cfg_default();
        assert_eq!(
            s.status_for("BTCUSDT", &cfg, NOW_MS_FRESH),
            MakerKpiStatus::Healthy
        );
    }

    #[test]
    fn is_degraded_matches_only_degraded_variant() {
        assert!(!MakerKpiStatus::Cold.is_degraded());
        assert!(!MakerKpiStatus::Healthy.is_degraded());
        assert!(MakerKpiStatus::Degraded { reason: "x" }.is_degraded());
    }
}
